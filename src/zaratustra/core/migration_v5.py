"""Explicit accepted-result storage; no authority grants or rewriting old migrations."""

import hashlib
import sqlite3

V5_NAME = "0005_accepted_handoffs"
V5_STATEMENTS = (
    """CREATE TABLE accepted_handoffs (
        id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE REFERENCES mutation_events(id),
        body TEXT NOT NULL CHECK (json_valid(body))
    ) STRICT""",
)
V5_SHA256 = hashlib.sha256(chr(10).join(V5_STATEMENTS).encode("utf-8")).hexdigest()


def migrate_v5(connection: sqlite3.Connection, applied_at: str) -> None:
    if not connection.in_transaction:
        raise ValueError("Migration v5 requires a transaction")
    for statement in V5_STATEMENTS:
        connection.execute(statement)
    connection.execute(
        "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
        (5, V5_NAME, V5_SHA256, applied_at),
    )
    connection.execute("PRAGMA user_version = 5")
