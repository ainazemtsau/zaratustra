"""Explicit local backup and inspect-only restoration; no executor imports."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .storage import durable, exclusion, verified
from .types import CoreError, wire

if TYPE_CHECKING:
    from .api import Core


def integrity(path: Path) -> None:
    with closing(sqlite3.connect(path)) as db:
        if (
            db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
            or db.execute("PRAGMA foreign_key_check").fetchall()
        ):
            raise CoreError("invalid_request", "backup.integrity")
        db.row_factory = sqlite3.Row
        records = {(r["id"], r["revision"]): r for r in db.execute("SELECT * FROM records")}
        artifacts = {a["sha256"] for a in db.execute("SELECT * FROM artifacts")}
        for head in db.execute("SELECT * FROM heads"):
            record = records.get((head["id"], head["revision"]))
            if record is None or any(record[k] != head[k] for k in ("kind", "key", "scope")):
                raise CoreError("invalid_request", "backup.head_closure")
        for record in records.values():
            body = json.loads(record["body"])
            refs = list(body.get("source_refs", []))
            if body.get("schema_ref"):
                refs.append(body["schema_ref"])
            if any((r["id"], r["revision"]) not in records for r in refs) or any(
                a not in artifacts for a in body.get("artifact_refs", [])
            ):
                raise CoreError("invalid_request", "backup.reference_closure")
        for work in db.execute("SELECT body FROM works"):
            body = json.loads(work["body"])
            if any(
                (r["id"], r["revision"]) not in records
                for r in body.get("inputs", []) + [body["method_ref"]]
            ):
                raise CoreError("invalid_request", "backup.work_closure")


def target(source: Path, destination: Path) -> Path:
    destination = destination.resolve()
    if destination.exists() or destination.is_relative_to(source.resolve()):
        raise CoreError("invalid_request", "maintenance.destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".partial-" + secrets.token_hex(8))
    temporary.mkdir()
    return temporary


def backup(core: Core, token: str, destination: Path) -> dict[str, Any]:
    with exclusion(core.root):
        with core._locked_transaction() as db:
            actor = core._identity(db, token, "admin")
            if actor["origin"] != "human":
                raise CoreError("denied", "maintenance.origin")
            artifacts = [dict(r) for r in db.execute("SELECT * FROM artifacts ORDER BY sha256")]
            meta = dict(db.execute("SELECT * FROM meta").fetchone())
        temporary = target(core.root, destination)
        try:
            source = sqlite3.connect(core.path)
            copy = sqlite3.connect(temporary / "core.sqlite3")
            try:
                source.backup(copy)
            finally:
                copy.close()
                source.close()
            integrity(temporary / "core.sqlite3")
            for artifact in artifacts:
                raw = verified(core.root, artifact["sha256"], artifact["size"])
                durable(temporary / "artifacts" / artifact["sha256"], raw)
            # Rewrite through the same synchronization primitive before final publication.
            database = (temporary / "core.sqlite3").read_bytes()
            durable(temporary / "core.sqlite3", database)
            manifest = {
                "format": "backup/v1",
                "source": meta,
                "database_sha256": hashlib.sha256(database).hexdigest(),
                "database_size": len(database),
                "artifacts": artifacts,
            }
            durable(temporary / "manifest.json", wire(manifest))
            os.replace(temporary, destination)
            return manifest
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)


def restore(backup_root: Path, destination: Path) -> str:
    """Verify before publish. A partial backup never becomes an inspectable Core."""
    try:
        manifest = json.loads((backup_root / "manifest.json").read_bytes())
        database = (backup_root / "core.sqlite3").read_bytes()
        if (
            manifest["format"] != "backup/v1"
            or len(database) != manifest["database_size"]
            or hashlib.sha256(database).hexdigest() != manifest["database_sha256"]
        ):
            raise CoreError("invalid_request", "backup.manifest")
        integrity(backup_root / "core.sqlite3")
        with closing(sqlite3.connect(backup_root / "core.sqlite3")) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(r) for r in db.execute("SELECT * FROM artifacts ORDER BY sha256")]
            original = dict(db.execute("SELECT * FROM meta").fetchone())
            if rows != manifest["artifacts"] or original != manifest["source"]:
                raise CoreError("invalid_request", "backup.complete_manifest")
        materials = [(a, verified(backup_root, a["sha256"], a["size"])) for a in rows]
    except (OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError) as error:
        raise CoreError("invalid_request", "backup.invalid") from error
    temporary = target(backup_root, destination)
    try:
        durable(temporary / "core.sqlite3", database)
        for artifact, raw in materials:
            durable(temporary / "artifacts" / artifact["sha256"], raw)
        token = secrets.token_urlsafe(32)
        with closing(sqlite3.connect(temporary / "core.sqlite3")) as db, db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute(
                "UPDATE meta SET instance=?,space=?,epoch=epoch+1",
                (secrets.token_hex(16), secrets.token_hex(16)),
            )
            db.execute("DELETE FROM credentials")
            db.execute("DELETE FROM rights")
            db.execute(
                "INSERT INTO credentials VALUES(?, 'owner', 'human')",
                (hashlib.sha256(token.encode()).hexdigest(),),
            )
            db.execute("INSERT INTO rights VALUES('owner', '[\"*\"]')")
            db.execute("UPDATE lifecycle SET mode='quarantined'")
            db.execute(
                "UPDATE works SET status='paused',generation=generation+1,revision=revision+1 "
                "WHERE status NOT IN ('completed','cancelled')"
            )
            db.execute(
                "UPDATE attempts SET status='fenced' "
                "WHERE status IN ('prepared','claimed','unknown')"
            )
            db.execute("DELETE FROM intents")
        integrity(temporary / "core.sqlite3")
        durable(temporary / "core.sqlite3", (temporary / "core.sqlite3").read_bytes())
        durable(temporary / "owner.credential", token.encode())
        os.replace(temporary, destination)
        return token
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
