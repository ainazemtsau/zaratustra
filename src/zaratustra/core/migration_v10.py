"""Admit standalone Process bootstrap without rewriting released records."""

import hashlib
import sqlite3

V10_NAME = "0010_standalone_process"
V10_FORMAT = "Process purpose; process_created bootstrap event; zero historical Works allowed"
V10_SHA256 = hashlib.sha256(V10_FORMAT.encode("utf-8")).hexdigest()


def migrate_v10(connection: sqlite3.Connection, applied_at: str) -> None:
    if not connection.in_transaction:
        raise ValueError("Migration v10 requires a transaction")
    connection.execute(
        "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
        (10, V10_NAME, V10_SHA256, applied_at),
    )
    connection.execute("PRAGMA user_version = 10")
