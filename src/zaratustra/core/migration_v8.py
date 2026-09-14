"""Optional Result continuation and Process-owned material; released bytes stay intact."""

import hashlib
import sqlite3

V8_NAME = "0008_process_material_and_terminal_result"
V8_STATEMENTS = (
    "ALTER TABLE work_results RENAME TO work_results_v6",
    """CREATE TABLE work_results (
        operation_id TEXT PRIMARY KEY REFERENCES mutation_receipts(operation_id),
        work_id TEXT NOT NULL UNIQUE REFERENCES core_records(id),
        next_work_id TEXT UNIQUE REFERENCES core_records(id),
        body TEXT NOT NULL CHECK (json_valid(body))
    ) STRICT""",
    (
        "INSERT INTO work_results "
        "SELECT operation_id, work_id, next_work_id, body FROM work_results_v6"
    ),
    "DROP TABLE work_results_v6",
    """CREATE TABLE process_materials (
        material_id TEXT PRIMARY KEY,
        process_id TEXT NOT NULL REFERENCES core_records(id),
        operation_id TEXT NOT NULL UNIQUE REFERENCES mutation_receipts(operation_id),
        content BLOB NOT NULL
    ) STRICT""",
)
V8_SHA256 = hashlib.sha256(chr(10).join(V8_STATEMENTS).encode("utf-8")).hexdigest()


def migrate_v8(connection: sqlite3.Connection, applied_at: str) -> None:
    if not connection.in_transaction:
        raise ValueError("Migration v8 requires a transaction")
    for statement in V8_STATEMENTS:
        connection.execute(statement)
    connection.execute(
        "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
        (8, V8_NAME, V8_SHA256, applied_at),
    )
    connection.execute("PRAGMA user_version = 8")
