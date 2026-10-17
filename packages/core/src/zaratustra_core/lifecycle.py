"""Mechanical compatibility and paired local restore activation."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import ExitStack, closing
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .storage import exclusion
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
    if rows != expected_schema() or db.execute("PRAGMA user_version").fetchone()[0] != 0:
        raise CoreError("unsupported_capability", "maintenance.schema")
    return {
        "contract": "wire/v1",
        "schema": "restart/v1",
        "schema_sha256": digest([list(row) for row in rows]),
    }


def human(core: Core, db: sqlite3.Connection, token: str) -> None:
    if core._identity(db, token, "admin")["origin"] != "human":
        raise CoreError("denied", "maintenance.origin")


def event(db: sqlite3.Connection, kind: str, subject: str, body: dict[str, Any]) -> None:
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


def prepare_update(core: Core, token: str, destination: Path) -> dict[str, Any]:
    """Pre-update verified backup. Current compatible updates perform no data rewrite."""
    manifest = core.backup(token, destination)
    return {
        "status": "compatible",
        "compatibility": manifest["compatibility"],
        "source": manifest["source"],
        "backup": str(destination.resolve()),
        "manifest": manifest,
    }
