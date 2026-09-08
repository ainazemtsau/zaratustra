"""Explicit versioned content metadata; no record changes or authority grants."""

import hashlib
import sqlite3

V4_NAME = "0004_artifact_versions"
V4_STATEMENTS = (
    """CREATE TABLE artifact_versions (
        id TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL REFERENCES core_records(id),
        body TEXT NOT NULL CHECK (json_valid(body))
    ) STRICT""",
)
V4_SHA256 = hashlib.sha256(chr(10).join(V4_STATEMENTS).encode("utf-8")).hexdigest()


def migrate_v4(connection: sqlite3.Connection, applied_at: str) -> None:
    if not connection.in_transaction:
        raise ValueError("Migration v4 requires a transaction")
    for statement in V4_STATEMENTS:
        connection.execute(statement)
    connection.execute(
        "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
        (4, V4_NAME, V4_SHA256, applied_at),
    )
    connection.execute("PRAGMA user_version = 4")
