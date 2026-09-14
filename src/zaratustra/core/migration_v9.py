"""Explicit admission for Process-scoped ordinary Work creation events."""

import hashlib
import sqlite3

V9_NAME = "0009_explicit_ordinary_work_creation"
V9_FORMAT = (
    "Process-scoped WorkCreationRequest; exact saved PackReference; one ordinary ready Work "
    "and declared Artifact; immutable work_creation event and Process receipt"
)
V9_SHA256 = hashlib.sha256(V9_FORMAT.encode("utf-8")).hexdigest()


def migrate_v9(connection: sqlite3.Connection, applied_at: str) -> None:
    if not connection.in_transaction:
        raise ValueError("Migration v9 requires a transaction")
    connection.execute(
        "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
        (9, V9_NAME, V9_SHA256, applied_at),
    )
    connection.execute("PRAGMA user_version = 9")
