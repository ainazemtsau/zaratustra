"""Explicit DB-only mutation journal; no data changes or authority grants."""

import hashlib
import sqlite3

V3_NAME = "0003_mutation_protocol"
V3_STATEMENTS = (
    """CREATE TABLE mutation_events (
        id TEXT PRIMARY KEY,
        state_revision INTEGER NOT NULL UNIQUE CHECK (state_revision >= 2),
        body TEXT NOT NULL CHECK (json_valid(body))
    ) STRICT""",
    """CREATE TABLE mutation_receipts (
        operation_id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE REFERENCES mutation_events(id),
        fingerprint TEXT NOT NULL,
        body TEXT NOT NULL CHECK (json_valid(body))
    ) STRICT""",
)
V3_SHA256 = hashlib.sha256(chr(10).join(V3_STATEMENTS).encode("utf-8")).hexdigest()


def migrate_v3(connection: sqlite3.Connection, applied_at: str) -> None:
    if not connection.in_transaction:
        raise ValueError("Migration v3 requires a transaction")
    for statement in V3_STATEMENTS:
        connection.execute(statement)
    connection.execute(
        "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
        (3, V3_NAME, V3_SHA256, applied_at),
    )
    connection.execute("PRAGMA user_version = 3")
