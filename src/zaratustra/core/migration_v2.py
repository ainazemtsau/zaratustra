"""Add initial domain records without changing the released migration v1."""

from __future__ import annotations

import hashlib
import sqlite3

V2_NAME = "0002_core_records"
V2_STATEMENTS = (
    """CREATE TABLE core_state (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        revision INTEGER NOT NULL CHECK (revision >= 0)
    ) STRICT""",
    """CREATE TABLE core_records (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('process', 'work', 'artifact', 'event')),
        revision INTEGER NOT NULL CHECK (revision >= 1),
        body TEXT NOT NULL CHECK (json_valid(body))
    ) STRICT""",
    "INSERT INTO core_state VALUES (1, 0)",
)
V2_SHA256 = hashlib.sha256(chr(10).join(V2_STATEMENTS).encode("utf-8")).hexdigest()


def migrate_v2(connection: sqlite3.Connection, applied_at: str) -> None:
    """Caller validates v1 and owns the write transaction, including migration history."""
    if not connection.in_transaction:
        raise ValueError("Migration v2 requires a transaction")
    for statement in V2_STATEMENTS:
        connection.execute(statement)
    connection.execute(
        "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
        (2, V2_NAME, V2_SHA256, applied_at),
    )
    connection.execute("PRAGMA user_version = 2")
