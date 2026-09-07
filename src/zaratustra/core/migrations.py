"""Explicit sequential SQLite migrations. Version 1 contains bootstrap metadata only."""

from __future__ import annotations

import hashlib
import sqlite3

SCHEMA_VERSION = 1
APPLICATION_ID = 0x5A415241  # ZARA
V1_NAME = "0001_workspace"
V1_STATEMENTS = (
    """CREATE TABLE schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        applied_at TEXT NOT NULL
    ) STRICT""",
    """CREATE TABLE workspace (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        workspace_id TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    ) STRICT""",
)
V1_SHA256 = hashlib.sha256(chr(10).join(V1_STATEMENTS).encode("utf-8")).hexdigest()


def migrate_v1(connection: sqlite3.Connection, workspace_id: str, created_at: str) -> None:
    """Create the first schema and metadata in one explicit transaction on a new DB."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        for statement in V1_STATEMENTS:
            connection.execute(statement)
        connection.execute("INSERT INTO workspace VALUES (1, ?, ?)", (workspace_id, created_at))
        connection.execute(
            "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
            (SCHEMA_VERSION, V1_NAME, V1_SHA256, created_at),
        )
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
