"""Explicit JSON format admission; old record/event bytes and tables stay intact."""

import hashlib
import sqlite3

V7_NAME = "0007_exact_process_work_pack_binding"
V7_FORMAT = (
    "Process/Work optional immutable PackReference; bind_pack request5; "
    "event Process before/after; Result continuation inherits exact source binding"
)
V7_SHA256 = hashlib.sha256(V7_FORMAT.encode("utf-8")).hexdigest()


def migrate_v7(connection: sqlite3.Connection, applied_at: str) -> None:
    if not connection.in_transaction:
        raise ValueError("Migration v7 requires a transaction")
    connection.execute(
        "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
        (7, V7_NAME, V7_SHA256, applied_at),
    )
    connection.execute("PRAGMA user_version = 7")
