"""Explicit atomic Result/continuation storage; released migrations stay unchanged."""

import hashlib
import sqlite3

V6_NAME = "0006_work_results"
V6_STATEMENTS = (
    """CREATE TABLE work_results (
        operation_id TEXT PRIMARY KEY REFERENCES mutation_receipts(operation_id),
        work_id TEXT NOT NULL UNIQUE REFERENCES core_records(id),
        next_work_id TEXT NOT NULL UNIQUE REFERENCES core_records(id),
        body TEXT NOT NULL CHECK (json_valid(body))
    ) STRICT""",
)
V6_SHA256 = hashlib.sha256(chr(10).join(V6_STATEMENTS).encode("utf-8")).hexdigest()


def migrate_v6(connection: sqlite3.Connection, applied_at: str) -> None:
    if not connection.in_transaction:
        raise ValueError("Migration v6 requires a transaction")
    for statement in V6_STATEMENTS:
        connection.execute(statement)
    connection.execute(
        "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
        (6, V6_NAME, V6_SHA256, applied_at),
    )
    connection.execute("PRAGMA user_version = 6")
