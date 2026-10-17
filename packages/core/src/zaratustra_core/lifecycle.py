"""Mechanical compatibility and paired local restore activation."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import ExitStack, closing
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from .storage import exclusion, verified
from .types import CoreError, digest, wire

if TYPE_CHECKING:
    from .api import Core


def schema_rows(db: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return [
        tuple(r)
        for r in db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )
    ]


@lru_cache(maxsize=1)
def expected_schema() -> list[tuple[Any, ...]]:
    from .api import SCHEMA

    with closing(sqlite3.connect(":memory:")) as db:
        db.executescript(SCHEMA)
        return schema_rows(db)


def compatibility(db: sqlite3.Connection) -> dict[str, Any]:
    """Admit only the exact independent restart layout; never migrate implicitly."""
    rows = schema_rows(db)
    generation = db.execute("PRAGMA user_version").fetchone()[0]
    if rows != expected_schema() or generation not in {0, 1}:
        raise CoreError("unsupported_capability", "maintenance.schema")
    if generation == 1:
        validate_protocol(db, digest([list(row) for row in rows]))
    result = {
        "contract": "wire/v1",
        "schema": "restart/v1",
        "schema_sha256": digest([list(row) for row in rows]),
    }
    if generation:
        result["required_protocol"] = generation
    return result


def human(core: Core, db: sqlite3.Connection, token: str) -> None:
    if core._identity(db, token, "admin")["origin"] != "human":
        raise CoreError("denied", "maintenance.origin")


def event(db: sqlite3.Connection, kind: str, subject: str, body: dict[str, Any]) -> str:
    command = "maintenance:" + kind + ":" + subject + ":" + digest(body)
    seq = db.execute(
        "INSERT INTO events(kind,subject,body) VALUES(?,?,?)", (kind, command, wire(body).decode())
    ).lastrowid
    response = {
        "receipt_id": command,
        "command_id": command,
        "outcome": "committed",
        "result": body,
        "sequence": seq,
        "diagnostic_id": digest([command, seq])[:16],
    }
    db.execute(
        "INSERT INTO receipts VALUES(?,?,?,?)",
        (command, "owner", digest(body), wire(response).decode()),
    )
    return command


def latest(db: sqlite3.Connection, kind: str) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT body FROM events WHERE kind=? ORDER BY seq DESC LIMIT 1", (kind,)
    ).fetchone()
    return json.loads(row[0]) if row else None


def fence(db: sqlite3.Connection) -> None:
    db.execute(
        "UPDATE works SET status='paused',generation=generation+1,revision=revision+1 "
        "WHERE status NOT IN ('completed','cancelled')"
    )
    db.execute(
        "UPDATE attempts SET status='fenced' WHERE status IN ('prepared','claimed','unknown')"
    )
    db.execute("DELETE FROM intents")


def state_fingerprint(db: sqlite3.Connection) -> str:
    """Exclude read receipts; reject losing newer subject, execution or rights state."""
    return digest(
        {
            table: sorted((list(row) for row in db.execute("SELECT * FROM " + table)), key=wire)
            for table in (
                "records",
                "heads",
                "works",
                "attempts",
                "messages",
                "conversations",
                "waits",
                "results",
                "observations",
                "actions",
                "intents",
                "acceptance",
                "tool_calls",
                "artifacts",
                "rights",
            )
        }
    )


def activate(core: Core, token: str, source: Core, source_token: str) -> dict[str, Any]:
    """Commit retirement first. A crash between commits is recoverable by exact replay."""
    if core.root.resolve() == source.root.resolve():
        raise CoreError("invalid_request", "restore.same_root")
    with ExitStack() as stack:
        for root in sorted(
            (core.root.resolve(), source.root.resolve()),
            key=lambda root: os.path.normcase(str(root)),
        ):
            stack.enter_context(exclusion(root))
        # Hold both roots for the complete protocol, including the two durable commits.
        with core._locked_transaction() as target_db, source._locked_transaction() as source_db:
            human(core, target_db, token)
            human(source, source_db, source_token)
            lineage = latest(target_db, "restore_lineage")
            restored = dict(target_db.execute("SELECT * FROM meta").fetchone())
            original = dict(source_db.execute("SELECT * FROM meta").fetchone())
            if lineage is None or lineage["restored"] != restored:
                raise CoreError("invalid_request", "restore.lineage")
            evidence = {
                "source": lineage["source"],
                "restored": restored,
                "transfer_id": digest({"source": lineage["source"], "restored": restored}),
                "status": "active",
            }
            source_mode = source_db.execute("SELECT mode FROM lifecycle").fetchone()[0]
            target_mode = target_db.execute("SELECT mode FROM lifecycle").fetchone()[0]
            retirement = latest(source_db, "restore_retired")
            if source_mode == "retired":
                retired_identity = dict(lineage["source"], epoch=lineage["source"]["epoch"] + 1)
                if original != retired_identity or retirement != evidence:
                    raise CoreError("wrong_instance", "restore.retirement")
            elif source_mode == "active":
                if original != lineage["source"] or target_mode != "quarantined":
                    raise CoreError("wrong_instance", "restore.source")
                # Effects dispatched after the snapshot cannot silently disappear on restore.
                for query in (
                    "SELECT * FROM actions ORDER BY id",
                    "SELECT * FROM tool_calls ORDER BY attempt,native_id",
                ):
                    source_effects = [dict(r) for r in source_db.execute(query)]
                    target_effects = [dict(r) for r in target_db.execute(query)]
                    if source_effects != target_effects:
                        raise CoreError("outcome_unknown", "restore.source_effects", "reconcile")
                if state_fingerprint(source_db) != lineage.get("snapshot_state_sha256"):
                    raise CoreError("stale_basis", "restore.source_changed", "reconcile")
                source_db.execute("UPDATE lifecycle SET mode='retired'")
                source_db.execute("UPDATE meta SET epoch=epoch+1")
                fence(source_db)
                event(source_db, "restore_retired", restored["instance"], evidence)
            else:
                raise CoreError("denied", "restore.source_mode")
            if target_mode not in {"quarantined", "active"}:
                raise CoreError("denied", "restore.target_mode")
            source_db.commit()  # Never make the replacement active before durable retirement.
            if target_mode == "quarantined":
                target_db.execute("UPDATE lifecycle SET mode='active'")
                event(target_db, "restore_activated", restored["instance"], evidence)
            elif latest(target_db, "restore_activated") != evidence:
                raise CoreError("invalid_request", "restore.activation")
            return evidence


def initialize_protocol(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA user_version=1")
    event(
        db,
        "protocol_initialized",
        "1",
        {"protocol": 1, "schema_sha256": digest([list(row) for row in schema_rows(db)])},
    )


def validate_protocol(db: sqlite3.Connection, schema_hash: str) -> None:
    row = db.execute(
        "SELECT * FROM events WHERE kind IN ('protocol_initialized','protocol_upgrade') "
        "ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    try:
        if row is None:
            raise ValueError("missing protocol evidence")
        # Connections used by backup metadata do not necessarily have a Row factory.
        fields = [column[0] for column in db.execute("SELECT * FROM events LIMIT 0").description]
        evidence = dict(zip(fields, row, strict=True))
        body = json.loads(evidence["body"])
        if body.get("protocol") != 1 or body.get("schema_sha256") != schema_hash:
            raise ValueError("protocol evidence mismatch")
        receipt = db.execute(
            "SELECT fingerprint,response FROM receipts WHERE command=?", (evidence["subject"],)
        ).fetchone()
        if receipt is None:
            raise ValueError("missing protocol receipt")
        response = json.loads(receipt[1])
        if (
            receipt[0] != digest(body)
            or response["result"] != body
            or response["sequence"] != evidence["seq"]
        ):
            raise ValueError("protocol receipt mismatch")
        if evidence["kind"] == "protocol_upgrade" and (
            body["from"] != 0 or body["to"] != 1 or len(body["database_sha256"]) != 64
        ):
            raise ValueError("protocol upgrade mismatch")
    except (ValueError, KeyError, TypeError) as error:
        raise CoreError("unsupported_capability", "maintenance.protocol_evidence") from error


def checked_snapshot(destination: Path) -> dict[str, Any]:
    from .maintenance import integrity

    try:
        manifest = json.loads((destination / "manifest.json").read_bytes())
        raw = (destination / "core.sqlite3").read_bytes()
        if (
            manifest["format"] != "backup/v1"
            or manifest["database_size"] != len(raw)
            or manifest["database_sha256"] != hashlib.sha256(raw).hexdigest()
        ):
            raise ValueError("snapshot hash")
        integrity(destination / "core.sqlite3")
        with closing(sqlite3.connect(destination / "core.sqlite3")) as db:
            db.row_factory = sqlite3.Row
            if dict(db.execute("SELECT * FROM meta").fetchone()) != manifest["source"]:
                raise ValueError("snapshot source")
            artifacts = [dict(r) for r in db.execute("SELECT * FROM artifacts ORDER BY sha256")]
            if artifacts != manifest["artifacts"] or compatibility(db) != manifest.get(
                "compatibility"
            ):
                raise ValueError("snapshot manifest")
        for artifact in artifacts:
            verified(destination, artifact["sha256"], artifact["size"])
        return cast(dict[str, Any], manifest)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError) as error:
        raise CoreError("invalid_request", "maintenance.update_snapshot") from error


def upgrade_fingerprint(db: sqlite3.Connection) -> str:
    from .api import READ_OPS

    ignored = sorted(READ_OPS | {"protocol_upgrade"})
    placeholders = ",".join("?" for _ in ignored)
    return digest(
        {
            "state": state_fingerprint(db),
            "credentials": sorted([list(r) for r in db.execute("SELECT * FROM credentials")]),
            "meta": list(db.execute("SELECT * FROM meta").fetchone()),
            "history": [
                list(r)
                for r in db.execute(
                    "SELECT * FROM events WHERE kind NOT IN (" + placeholders + ") ORDER BY seq",
                    ignored,
                )
            ],
            "receipts": [
                list(r)
                for r in db.execute(
                    "SELECT r.* FROM receipts r JOIN events e ON e.subject=r.command "
                    "WHERE e.kind NOT IN (" + placeholders + ") ORDER BY e.seq",
                    ignored,
                )
            ],
        }
    )


def prepare_update(core: Core, token: str, destination: Path) -> dict[str, Any]:
    """Snapshot before enabling protocol1. Re-entry recovers the same verified snapshot."""
    from .maintenance import backup_locked

    destination = destination.resolve()
    with exclusion(core.root):
        with core._locked_transaction() as db:
            human(core, db, token)
            generation = db.execute("PRAGMA user_version").fetchone()[0]
            source = dict(db.execute("SELECT * FROM meta").fetchone())
            prior = latest(db, "protocol_upgrade")
            before = upgrade_fingerprint(db)
            recovered_upgrade = False
        if destination.exists():
            manifest = checked_snapshot(destination)
            with closing(sqlite3.connect(destination / "core.sqlite3")) as snapshot:
                if manifest["source"] != source or upgrade_fingerprint(snapshot) != before:
                    raise CoreError("stale_basis", "maintenance.update_snapshot")
                snapshot_generation = snapshot.execute("PRAGMA user_version").fetchone()[0]
            if snapshot_generation != generation:
                recovered_upgrade = (
                    generation == 1
                    and snapshot_generation == 0
                    and prior is not None
                    and prior["backup"] == str(destination)
                    and prior["database_sha256"] == manifest["database_sha256"]
                    and prior["source"] == source
                )
                if not recovered_upgrade:
                    raise CoreError("invalid_request", "maintenance.destination")
        else:
            manifest = backup_locked(core, token, destination)
        with core._locked_transaction() as db:
            if generation == 0:
                evidence = {
                    "protocol": 1,
                    "from": 0,
                    "to": 1,
                    "source": source,
                    "schema_sha256": digest([list(row) for row in schema_rows(db)]),
                    "backup": str(destination),
                    "database_sha256": manifest["database_sha256"],
                    "state_sha256": before,
                }
                db.execute("PRAGMA user_version=1")
                receipt = event(db, "protocol_upgrade", "1", evidence)
                upgrade = {"from": 0, "to": 1, "receipt_id": receipt}
            elif recovered_upgrade:
                assert prior is not None
                receipt = "maintenance:protocol_upgrade:1:" + digest(prior)
                upgrade = {"from": 0, "to": 1, "receipt_id": receipt}
            else:
                upgrade = {"from": 1, "to": 1}
            admitted = compatibility(db)
        return {
            "status": "compatible",
            "compatibility": admitted,
            "source": source,
            "backup": str(destination),
            "manifest": manifest,
            "upgrade": upgrade,
        }
