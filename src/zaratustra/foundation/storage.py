"""SQLite layout, checked transactions and maintenance primitives."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from .models import BackupInfo, BackupManifest, SpaceInfo
from .runtime import ensure_sqlite_runtime

ensure_sqlite_runtime()

import sqlite3  # noqa: E402

APPLICATION_ID = 0x5A434631
SCHEMA_VERSION = 1
SCHEMA_NAME = "core-v0.1-foundation-1"
STATE_DIRECTORY = ".zara-core"
DATABASE_NAME = "core.sqlite3"
EXECUTOR_DATABASE_NAME = "executor.sqlite3"
RESTORED_EXECUTOR_NAME = "executor-restored.sqlite3"
RPC_HOME_DIRECTORY = "pi-rpc-home"
RESTORED_RPC_HOME_DIRECTORY = "pi-rpc-home-restored"
BACKUP_DIRECTORY = "backups"
BUSY_TIMEOUT_MS = 250
BUSY_ATTEMPTS = 3


class FoundationError(Exception):
    """A structured foundation refusal or storage failure."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")

    def __reduce__(self) -> tuple[type[FoundationError], tuple[str, str]]:
        return type(self), (self.code, self.detail)


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        applied_at TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE spaces (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        space_id TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        state_revision INTEGER NOT NULL CHECK (state_revision >= 0),
        execution_epoch INTEGER NOT NULL CHECK (execution_epoch >= 1),
        recovery_state TEXT NOT NULL CHECK (recovery_state IN ('active', 'quarantined'))
    ) STRICT
    """,
    """
    CREATE TABLE records (
        record_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('artifact', 'decision', 'grant')),
        current_revision INTEGER NOT NULL CHECK (current_revision >= 1),
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE operations (
        operation_id TEXT PRIMARY KEY,
        fingerprint TEXT NOT NULL,
        kind TEXT NOT NULL,
        actor TEXT NOT NULL,
        committed_at TEXT NOT NULL,
        state_revision INTEGER NOT NULL UNIQUE CHECK (state_revision >= 1)
    ) STRICT
    """,
    """
    CREATE TABLE record_revisions (
        record_id TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK (revision >= 1),
        operation_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        actor TEXT NOT NULL,
        status TEXT NOT NULL,
        body_json TEXT NOT NULL,
        PRIMARY KEY (record_id, revision),
        FOREIGN KEY (record_id) REFERENCES records(record_id),
        FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
    ) STRICT
    """,
    """
    CREATE TABLE managed_content (
        record_id TEXT NOT NULL,
        revision INTEGER NOT NULL,
        media_type TEXT NOT NULL,
        payload BLOB NOT NULL,
        sha256 TEXT NOT NULL,
        PRIMARY KEY (record_id, revision),
        FOREIGN KEY (record_id, revision)
            REFERENCES record_revisions(record_id, revision) ON DELETE CASCADE
    ) STRICT
    """,
    """
    CREATE TABLE revision_provenance (
        record_id TEXT NOT NULL,
        revision INTEGER NOT NULL,
        ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
        relation TEXT NOT NULL,
        source_record_id TEXT,
        source_revision INTEGER,
        external_ref TEXT,
        PRIMARY KEY (record_id, revision, ordinal),
        FOREIGN KEY (record_id, revision)
            REFERENCES record_revisions(record_id, revision) ON DELETE CASCADE,
        FOREIGN KEY (source_record_id, source_revision)
            REFERENCES record_revisions(record_id, revision),
        CHECK (
            (source_record_id IS NOT NULL AND source_revision IS NOT NULL AND external_ref IS NULL)
            OR (source_record_id IS NULL AND source_revision IS NULL AND external_ref IS NOT NULL)
        )
    ) STRICT
    """,
    """
    CREATE TABLE operation_audit (
        operation_id TEXT PRIMARY KEY,
        authority_source TEXT NOT NULL,
        target_refs_json TEXT NOT NULL,
        grant_refs_json TEXT NOT NULL,
        decision_refs_json TEXT NOT NULL,
        FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
    ) STRICT
    """,
    """
    CREATE TABLE receipts (
        operation_id TEXT PRIMARY KEY,
        fingerprint TEXT NOT NULL,
        receipt_json TEXT NOT NULL,
        FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
    ) STRICT
    """,
    """
    CREATE TABLE deletion_jobs (
        operation_id TEXT PRIMARY KEY,
        record_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('pending', 'complete')),
        created_at TEXT NOT NULL,
        completed_at TEXT,
        FOREIGN KEY (operation_id) REFERENCES operations(operation_id),
        FOREIGN KEY (record_id) REFERENCES records(record_id)
    ) STRICT
    """,
    """
    CREATE TABLE backup_inventory (
        backup_id TEXT PRIMARY KEY,
        package_name TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        state_revision INTEGER NOT NULL CHECK (state_revision >= 0),
        database_sha256 TEXT,
        status TEXT NOT NULL CHECK (
            status IN ('planned', 'complete', 'failed', 'contaminated', 'purged')
        )
    ) STRICT
    """,
    """
    CREATE TABLE backup_records (
        backup_id TEXT NOT NULL,
        record_id TEXT NOT NULL,
        PRIMARY KEY (backup_id, record_id),
        FOREIGN KEY (backup_id) REFERENCES backup_inventory(backup_id),
        FOREIGN KEY (record_id) REFERENCES records(record_id)
    ) STRICT
    """,
    """
    CREATE TABLE maintenance_events (
        event_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        detail_json TEXT NOT NULL
    ) STRICT
    """,
    "CREATE INDEX record_revisions_operation ON record_revisions(operation_id)",
    "CREATE INDEX provenance_source ON revision_provenance(source_record_id, source_revision)",
    "CREATE INDEX records_kind ON records(kind, record_id)",
)
SCHEMA_SHA256 = (
    hashlib.sha256("\n".join(statement.strip() for statement in SCHEMA_STATEMENTS).encode())
    .hexdigest()
    .upper()
)
SUBJECT_SCHEMA_NAME = "core-v0.1-activity-work-2"
SUBJECT_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE subject_records (
        record_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('activity', 'work')),
        parent_id TEXT,
        current_revision INTEGER NOT NULL CHECK (current_revision >= 1),
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK ((kind = 'activity' AND parent_id IS NULL)
            OR (kind = 'work' AND parent_id IS NOT NULL)),
        FOREIGN KEY (parent_id) REFERENCES subject_records(record_id)
    ) STRICT
    """,
    """
    CREATE TABLE subject_revisions (
        record_id TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK (revision >= 1),
        operation_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        actor TEXT NOT NULL,
        status TEXT NOT NULL,
        PRIMARY KEY (record_id, revision),
        FOREIGN KEY (record_id) REFERENCES subject_records(record_id),
        FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
    ) STRICT
    """,
    """
    CREATE TABLE subject_content (
        record_id TEXT NOT NULL,
        revision INTEGER NOT NULL,
        payload BLOB NOT NULL,
        sha256 TEXT NOT NULL,
        PRIMARY KEY (record_id, revision),
        FOREIGN KEY (record_id, revision)
            REFERENCES subject_revisions(record_id, revision) ON DELETE CASCADE
    ) STRICT
    """,
    """
    CREATE TABLE backup_subjects (
        backup_id TEXT NOT NULL,
        record_id TEXT NOT NULL,
        PRIMARY KEY (backup_id, record_id),
        FOREIGN KEY (backup_id) REFERENCES backup_inventory(backup_id),
        FOREIGN KEY (record_id) REFERENCES subject_records(record_id)
    ) STRICT
    """,
    """
    CREATE TABLE subject_deletion_jobs (
        operation_id TEXT PRIMARY KEY,
        record_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('pending', 'complete')),
        created_at TEXT NOT NULL,
        completed_at TEXT,
        FOREIGN KEY (operation_id) REFERENCES operations(operation_id),
        FOREIGN KEY (record_id) REFERENCES subject_records(record_id)
    ) STRICT
    """,
    "CREATE INDEX subject_records_kind ON subject_records(kind, record_id)",
    "CREATE INDEX subject_revisions_operation ON subject_revisions(operation_id)",
)
SUBJECT_SCHEMA_SHA256 = (
    hashlib.sha256("\n".join(statement.strip() for statement in SUBJECT_SCHEMA_STATEMENTS).encode())
    .hexdigest()
    .upper()
)
EXECUTION_SCHEMA_NAME = "core-v0.1-interactive-execution-3"
EXECUTION_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE execution_resources (
        resource_id TEXT PRIMARY KEY,
        work_id TEXT NOT NULL,
        current_revision INTEGER NOT NULL CHECK (current_revision >= 1),
        status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
        state_json TEXT NOT NULL,
        FOREIGN KEY (work_id) REFERENCES subject_records(record_id)
    ) STRICT
    """,
    """
    CREATE TABLE execution_resource_revisions (
        resource_id TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK (revision >= 1),
        operation_id TEXT NOT NULL,
        state_json TEXT NOT NULL,
        PRIMARY KEY (resource_id, revision),
        FOREIGN KEY (resource_id) REFERENCES execution_resources(resource_id),
        FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
    ) STRICT
    """,
    """
    CREATE TABLE execution_attempts (
        attempt_id TEXT PRIMARY KEY,
        revision INTEGER NOT NULL CHECK (revision >= 1),
        work_id TEXT NOT NULL,
        work_revision INTEGER NOT NULL,
        resource_id TEXT NOT NULL,
        resource_revision INTEGER NOT NULL,
        session_id TEXT NOT NULL,
        previous_attempt_id TEXT,
        execution_epoch INTEGER NOT NULL,
        generation INTEGER NOT NULL CHECK (generation >= 1),
        input_refs_json TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('active', 'completed', 'interrupted')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (work_id, generation),
        FOREIGN KEY (work_id) REFERENCES subject_records(record_id),
        FOREIGN KEY (resource_id) REFERENCES execution_resources(resource_id)
    ) STRICT
    """,
    """
    CREATE TABLE execution_invocations (
        invocation_id TEXT PRIMARY KEY,
        revision INTEGER NOT NULL CHECK (revision >= 1),
        attempt_id TEXT NOT NULL,
        work_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        purpose TEXT NOT NULL,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        transport TEXT NOT NULL,
        request_sha256 TEXT,
        request_bytes INTEGER NOT NULL CHECK (request_bytes >= 1),
        reserve_units INTEGER NOT NULL CHECK (reserve_units >= 1),
        usage_units INTEGER CHECK (usage_units >= 0),
        status TEXT NOT NULL CHECK (status IN
            ('prepared', 'admitted', 'sent', 'answered', 'unknown')),
        http_status INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (attempt_id) REFERENCES execution_attempts(attempt_id)
    ) STRICT
    """,
    """
    CREATE TABLE execution_events (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        operation_id TEXT NOT NULL,
        work_id TEXT NOT NULL,
        attempt_id TEXT,
        invocation_id TEXT,
        kind TEXT NOT NULL,
        created_at TEXT NOT NULL
    ) STRICT
    """,
    "CREATE INDEX execution_attempt_work ON execution_attempts(work_id, generation)",
    "CREATE INDEX execution_invocation_work ON execution_invocations(work_id, status)",
    "CREATE INDEX execution_event_work ON execution_events(work_id, sequence)",
)
EXECUTION_SCHEMA_SHA256 = (
    hashlib.sha256(
        "\n".join(statement.strip() for statement in EXECUTION_SCHEMA_STATEMENTS).encode()
    )
    .hexdigest()
    .upper()
)
CONTINUATION_SCHEMA_NAME = "core-v0.1-durable-continuation-4"
CONTINUATION_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE execution_assignments (
        attempt_id TEXT PRIMARY KEY,
        work_id TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK (revision >= 1),
        executor_version TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN
            ('assigned', 'waiting', 'ready', 'stop_requested',
             'stopped', 'unknown', 'interrupted')),
        stop_reason BLOB,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (attempt_id) REFERENCES execution_attempts(attempt_id)
    ) STRICT
    """,
    """
    CREATE TABLE execution_waits (
        wait_id TEXT PRIMARY KEY,
        attempt_id TEXT NOT NULL,
        work_id TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK (revision >= 1),
        status TEXT NOT NULL CHECK (status IN ('open', 'answered', 'closed', 'purged')),
        question BLOB,
        expected_actor TEXT NOT NULL,
        remainder BLOB,
        partial_refs_json TEXT NOT NULL,
        answer BLOB,
        answer_source TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (attempt_id) REFERENCES execution_attempts(attempt_id)
    ) STRICT
    """,
    """
    CREATE TABLE execution_outbox (
        outbox_id TEXT PRIMARY KEY,
        attempt_id TEXT NOT NULL,
        work_id TEXT NOT NULL,
        wait_id TEXT,
        execution_epoch INTEGER NOT NULL,
        generation INTEGER NOT NULL,
        kind TEXT NOT NULL CHECK (kind IN ('launch', 'resume')),
        status TEXT NOT NULL CHECK (status IN ('pending', 'cancelled')),
        created_at TEXT NOT NULL,
        UNIQUE (wait_id, kind),
        FOREIGN KEY (attempt_id) REFERENCES execution_attempts(attempt_id),
        FOREIGN KEY (wait_id) REFERENCES execution_waits(wait_id)
    ) STRICT
    """,
    "CREATE INDEX assignment_work ON execution_assignments(work_id)",
    "CREATE INDEX wait_work ON execution_waits(work_id, status)",
    "CREATE INDEX outbox_work ON execution_outbox(work_id, status)",
)
CONTINUATION_SCHEMA_SHA256 = (
    hashlib.sha256(
        "\n".join(statement.strip() for statement in CONTINUATION_SCHEMA_STATEMENTS).encode()
    )
    .hexdigest()
    .upper()
)

COMPOSITION_SCHEMA_NAME = "core-v0.1-composite-work-5"
COMPOSITION_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE method_versions (
        method_id TEXT NOT NULL,
        version INTEGER NOT NULL CHECK (version >= 1),
        checksum TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('active', 'deleted')),
        payload BLOB,
        operation_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        actor TEXT NOT NULL,
        PRIMARY KEY (method_id, version),
        FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
    ) STRICT
    """,
    """
    CREATE TABLE work_plan_revisions (
        parent_id TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK (revision >= 1),
        payload BLOB NOT NULL,
        operation_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        actor TEXT NOT NULL,
        PRIMARY KEY (parent_id, revision),
        FOREIGN KEY (parent_id) REFERENCES subject_records(record_id),
        FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
    ) STRICT
    """,
    """
    CREATE TABLE work_plan_children (
        child_id TEXT PRIMARY KEY,
        parent_id TEXT NOT NULL,
        role TEXT NOT NULL,
        issued_plan_revision INTEGER,
        issue_operation_id TEXT,
        UNIQUE (parent_id, role),
        FOREIGN KEY (parent_id) REFERENCES subject_records(record_id),
        FOREIGN KEY (child_id) REFERENCES subject_records(record_id)
    ) STRICT
    """,
    """
    CREATE TABLE work_obligation_revisions (
        parent_id TEXT NOT NULL,
        key TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK (revision >= 1),
        payload BLOB NOT NULL,
        operation_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (parent_id, key, revision),
        FOREIGN KEY (parent_id) REFERENCES subject_records(record_id),
        FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
    ) STRICT
    """,
    """
    CREATE TABLE method_deletion_jobs (
        operation_id TEXT PRIMARY KEY,
        method_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('pending', 'complete')),
        created_at TEXT NOT NULL,
        completed_at TEXT,
        FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
    ) STRICT
    """,
    "CREATE INDEX work_plan_children_parent ON work_plan_children(parent_id)",
    "CREATE INDEX work_obligation_parent ON work_obligation_revisions(parent_id, key)",
)
COMPOSITION_SCHEMA_SHA256 = (
    hashlib.sha256(
        "\n".join(statement.strip() for statement in COMPOSITION_SCHEMA_STATEMENTS).encode()
    )
    .hexdigest()
    .upper()
)

CHILD_EXECUTION_SCHEMA_NAME = "core-v0.1-child-execution-6"
CHILD_EXECUTION_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE execution_plan_pins (
        attempt_id TEXT PRIMARY KEY,
        work_id TEXT NOT NULL,
        parent_id TEXT NOT NULL,
        role TEXT NOT NULL,
        plan_revision INTEGER NOT NULL CHECK (plan_revision >= 1),
        method_id TEXT NOT NULL,
        method_version INTEGER NOT NULL CHECK (method_version >= 1),
        method_checksum TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (attempt_id) REFERENCES execution_attempts(attempt_id),
        FOREIGN KEY (work_id) REFERENCES subject_records(record_id),
        FOREIGN KEY (parent_id) REFERENCES subject_records(record_id),
        FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
    ) STRICT
    """,
    "CREATE INDEX plan_pin_work ON execution_plan_pins(work_id)",
    "CREATE INDEX plan_pin_parent ON execution_plan_pins(parent_id, plan_revision)",
)
CHILD_EXECUTION_SCHEMA_SHA256 = (
    hashlib.sha256(
        "\n".join(statement.strip() for statement in CHILD_EXECUTION_SCHEMA_STATEMENTS).encode()
    )
    .hexdigest()
    .upper()
)

# Schema 7 fences the new subject outcomes stored in Work revisions from older code.
# Later pass-3 parts add their tables here; the DDL is frozen only when pass 3 is released.
PLAN_REVISION_SCHEMA_NAME = "core-v0.1-plan-revision-7"
PLAN_REVISION_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE result_revalidations (
        parent_id TEXT NOT NULL,
        child_id TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK (revision >= 1),
        role TEXT NOT NULL,
        payload BLOB NOT NULL,
        operation_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (parent_id, child_id, revision),
        FOREIGN KEY (parent_id) REFERENCES subject_records(record_id),
        FOREIGN KEY (child_id) REFERENCES subject_records(record_id),
        FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
    ) STRICT
    """,
    "CREATE INDEX result_revalidation_child ON result_revalidations(child_id)",
    # Part 3.6: a role keeps its schema 5 member row; Works that fill a role through an
    # active plan revision are members here, and every such revision records its node
    # decisions as addresses.
    """
    CREATE TABLE work_plan_members (
        child_id TEXT PRIMARY KEY,
        parent_id TEXT NOT NULL,
        role TEXT NOT NULL,
        plan_revision INTEGER NOT NULL CHECK (plan_revision >= 2),
        issued_plan_revision INTEGER,
        issue_operation_id TEXT,
        FOREIGN KEY (parent_id) REFERENCES subject_records(record_id),
        FOREIGN KEY (child_id) REFERENCES subject_records(record_id)
    ) STRICT
    """,
    """
    CREATE TABLE work_plan_nodes (
        parent_id TEXT NOT NULL,
        plan_revision INTEGER NOT NULL CHECK (plan_revision >= 2),
        role TEXT NOT NULL,
        decision TEXT NOT NULL CHECK (decision IN
            ('keep', 'replace', 'cancel', 'stale', 'release', 'add')),
        work_id TEXT NOT NULL,
        replaced_work_id TEXT,
        issue_carried INTEGER NOT NULL CHECK (issue_carried IN (0, 1)),
        closed_revision INTEGER,
        operation_id TEXT NOT NULL,
        PRIMARY KEY (parent_id, plan_revision, role),
        FOREIGN KEY (parent_id) REFERENCES subject_records(record_id),
        FOREIGN KEY (work_id) REFERENCES subject_records(record_id),
        FOREIGN KEY (replaced_work_id) REFERENCES subject_records(record_id),
        FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
    ) STRICT
    """,
    # Part 3.7: an active Attempt of a kept node is transferred explicitly; its pin stays.
    """
    CREATE TABLE execution_plan_transfers (
        attempt_id TEXT NOT NULL,
        plan_revision INTEGER NOT NULL CHECK (plan_revision >= 2),
        work_id TEXT NOT NULL,
        parent_id TEXT NOT NULL,
        role TEXT NOT NULL,
        from_plan_revision INTEGER NOT NULL CHECK (from_plan_revision >= 1),
        method_id TEXT NOT NULL,
        method_version INTEGER NOT NULL CHECK (method_version >= 1),
        method_checksum TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (attempt_id, plan_revision),
        FOREIGN KEY (attempt_id) REFERENCES execution_attempts(attempt_id),
        FOREIGN KEY (work_id) REFERENCES subject_records(record_id),
        FOREIGN KEY (parent_id) REFERENCES subject_records(record_id),
        FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
    ) STRICT
    """,
    # Part 3.8: every plan revision has one exact Method; a transition keeps only
    # addresses of the old requirements, their successors and retiring exceptions.
    """
    CREATE TABLE work_plan_methods (
        parent_id TEXT NOT NULL,
        plan_revision INTEGER NOT NULL CHECK (plan_revision >= 1),
        method_id TEXT NOT NULL,
        method_version INTEGER NOT NULL CHECK (method_version >= 1),
        method_checksum TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        PRIMARY KEY (parent_id, plan_revision),
        FOREIGN KEY (parent_id) REFERENCES subject_records(record_id),
        FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
    ) STRICT
    """,
    """
    CREATE TABLE work_obligation_transitions (
        parent_id TEXT NOT NULL,
        plan_revision INTEGER NOT NULL CHECK (plan_revision >= 2),
        source_key TEXT NOT NULL,
        source_revision INTEGER NOT NULL CHECK (source_revision >= 1),
        action TEXT NOT NULL CHECK (action IN ('carry', 'retire')),
        target_key TEXT,
        exception_id TEXT,
        exception_revision INTEGER,
        operation_id TEXT NOT NULL,
        PRIMARY KEY (parent_id, plan_revision, source_key),
        FOREIGN KEY (parent_id) REFERENCES subject_records(record_id),
        FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
    ) STRICT
    """,
    "CREATE INDEX work_plan_member_parent ON work_plan_members(parent_id)",
    "CREATE INDEX work_plan_node_work ON work_plan_nodes(work_id)",
    "CREATE INDEX plan_transfer_work ON execution_plan_transfers(work_id)",
    "CREATE INDEX work_plan_method_version ON work_plan_methods(method_id, method_version)",
)
PLAN_REVISION_SCHEMA_SHA256 = (
    hashlib.sha256(
        "\n".join(statement.strip() for statement in PLAN_REVISION_SCHEMA_STATEMENTS).encode()
    )
    .hexdigest()
    .upper()
)
SUPPORTED_SCHEMA_VERSIONS = (1, 2, 3, 4, 5, 6, 7)


def utc_now() -> datetime:
    return datetime.now(UTC)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _plain(path: Path) -> None:
    if path.is_symlink() or path.is_junction():
        raise FoundationError("layout", f"Managed paths must not be links: {path}")


def _new_root(path: Path) -> Path:
    root = path.expanduser().resolve()
    if not root.is_dir():
        raise FoundationError("layout", "Choose an existing empty directory")
    _plain(root)
    try:
        occupied = next(root.iterdir(), None)
    except OSError as error:
        raise FoundationError("layout", f"Cannot inspect selected directory: {error}") from error
    if occupied is not None:
        raise FoundationError("layout", "New spaces require an empty directory")
    return root


def layout(path: Path) -> tuple[Path, Path, Path]:
    root = path.expanduser().resolve()
    state = root / STATE_DIRECTORY
    database = state / DATABASE_NAME
    backups = state / BACKUP_DIRECTORY
    for entry in (root, state, database, backups):
        if entry.exists():
            _plain(entry)
    if not root.is_dir() or not state.is_dir() or not backups.is_dir() or not database.is_file():
        raise FoundationError("layout", "No complete Core v0.1 space at this path")
    return root, database, backups


def _configure(connection: sqlite3.Connection, *, writable: bool) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    if writable:
        connection.execute("PRAGMA secure_delete = ON")
        connection.execute("PRAGMA synchronous = FULL")
    else:
        connection.execute("PRAGMA query_only = ON")


def _connect(database: Path, *, writable: bool) -> sqlite3.Connection:
    mode = "rw" if writable else "ro"
    connection = sqlite3.connect(
        database.as_uri() + f"?mode={mode}",
        uri=True,
        autocommit=True,
        timeout=BUSY_TIMEOUT_MS / 1000,
    )
    _configure(connection, writable=writable)
    return connection


def snapshot_connection(database: Path) -> sqlite3.Connection:
    """Inspect a closed backup image without creating WAL sidecars in its package."""

    connection = sqlite3.connect(
        database.as_uri() + "?mode=ro&immutable=1", uri=True, autocommit=True
    )
    _configure(connection, writable=False)
    return connection


def _begin(connection: sqlite3.Connection, *, writable: bool) -> None:
    statement = "BEGIN IMMEDIATE" if writable else "BEGIN"
    for attempt in range(BUSY_ATTEMPTS):
        try:
            connection.execute(statement)
            return
        except sqlite3.OperationalError as error:
            busy = "locked" in str(error).casefold() or "busy" in str(error).casefold()
            if not busy or attempt + 1 == BUSY_ATTEMPTS:
                if busy:
                    raise FoundationError(
                        "busy", "SQLite write/read boundary remained busy"
                    ) from error
                raise
            time.sleep(0.05 * (attempt + 1))


def _space_info(connection: sqlite3.Connection, root: Path, database: Path) -> SpaceInfo:
    application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
    schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if application_id != APPLICATION_ID or schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise FoundationError(
            "unsupported_schema",
            f"Unsupported application/schema identity: {application_id}/{schema_version}",
        )
    journal = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).casefold()
    if journal != "wal":
        raise FoundationError("unsupported_configuration", f"Expected WAL, found {journal}")
    migration = connection.execute(
        "SELECT version, name, sha256 FROM schema_migrations ORDER BY version"
    ).fetchall()
    expected = [(SCHEMA_VERSION, SCHEMA_NAME, SCHEMA_SHA256)]
    if schema_version >= 2:
        expected.append((2, SUBJECT_SCHEMA_NAME, SUBJECT_SCHEMA_SHA256))
    if schema_version >= 3:
        expected.append((3, EXECUTION_SCHEMA_NAME, EXECUTION_SCHEMA_SHA256))
    if schema_version >= 4:
        expected.append((4, CONTINUATION_SCHEMA_NAME, CONTINUATION_SCHEMA_SHA256))
    if schema_version >= 5:
        expected.append((5, COMPOSITION_SCHEMA_NAME, COMPOSITION_SCHEMA_SHA256))
    if schema_version >= 6:
        expected.append((6, CHILD_EXECUTION_SCHEMA_NAME, CHILD_EXECUTION_SCHEMA_SHA256))
    if schema_version >= 7:
        expected.append((7, PLAN_REVISION_SCHEMA_NAME, PLAN_REVISION_SCHEMA_SHA256))
    if migration != expected:
        raise FoundationError("unsupported_schema", "Schema history does not match installed code")
    rows = connection.execute(
        "SELECT space_id, created_at, state_revision, execution_epoch, recovery_state FROM spaces"
    ).fetchall()
    if len(rows) != 1:
        raise FoundationError("corrupt_space", "Expected exactly one space identity")
    space_id, created_at, state_revision, execution_epoch, recovery_state = rows[0]
    return SpaceInfo(
        root=root,
        database=database,
        space_id=UUID(space_id),
        created_at=datetime.fromisoformat(created_at),
        schema_version=cast(Literal[1, 2, 3, 4, 5, 6, 7], schema_version),
        state_revision=state_revision,
        execution_epoch=execution_epoch,
        recovery_state=recovery_state,
        sqlite_version="3.53.3",
    )


@contextmanager
def space_connection(
    path: Path, *, writable: bool = False
) -> Iterator[tuple[sqlite3.Connection, SpaceInfo]]:
    """Open, validate and close one bounded transaction; never migrate or repair."""

    connection: sqlite3.Connection | None = None
    try:
        root, database, _ = layout(path)
        connection = _connect(database, writable=writable)
        _begin(connection, writable=writable)
        info = _space_info(connection, root, database)
        yield connection, info
        connection.execute("COMMIT")
    except FoundationError:
        if connection is not None and connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    except (OSError, ValueError, sqlite3.Error) as error:
        if connection is not None and connection.in_transaction:
            connection.execute("ROLLBACK")
        raise FoundationError("storage", str(error)) from error
    finally:
        if connection is not None:
            connection.close()


def initialize_space(path: Path, *, space_id: UUID | None = None) -> SpaceInfo:
    """Create a new empty Core space without reading or importing any old workspace."""

    root = _new_root(path)
    state = root / STATE_DIRECTORY
    backups = state / BACKUP_DIRECTORY
    database = state / DATABASE_NAME
    created_at = utc_now().isoformat()
    identity = space_id or uuid4()
    try:
        state.mkdir()
        backups.mkdir()
        with closing(sqlite3.connect(database, autocommit=True, timeout=0.25)) as connection:
            _configure(connection, writable=True)
            journal = connection.execute("PRAGMA journal_mode = WAL").fetchone()
            if journal is None or str(journal[0]).casefold() != "wal":
                raise FoundationError("unsupported_configuration", "SQLite refused WAL mode")
            connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.execute("BEGIN IMMEDIATE")
            try:
                for statement in SCHEMA_STATEMENTS:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations(version, name, sha256, applied_at) "
                    "VALUES (?, ?, ?, ?)",
                    (SCHEMA_VERSION, SCHEMA_NAME, SCHEMA_SHA256, created_at),
                )
                connection.execute(
                    "INSERT INTO spaces(singleton, space_id, created_at, state_revision, "
                    "execution_epoch, recovery_state) VALUES (1, ?, ?, 0, 1, 'active')",
                    (str(identity), created_at),
                )
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        return read_space(root)
    except BaseException:
        if state.exists():
            shutil.rmtree(state)
        raise


def read_space(path: Path) -> SpaceInfo:
    with space_connection(path) as (_, info):
        return info


def backup_database(source: Path, backup_id: UUID, created_at: datetime) -> BackupInfo:
    """Prepare one hidden SQLite Backup API package for later publication."""

    root, database, backups = layout(source)
    partial = backups / f".{backup_id}.partial"
    package = backups / str(backup_id)
    if partial.exists() or package.exists():
        raise FoundationError("backup_exists", f"Backup package already exists: {backup_id}")
    partial.mkdir()
    backup_database_path = partial / DATABASE_NAME
    try:
        with space_connection(root) as (source_connection, info):
            with closing(sqlite3.connect(backup_database_path, autocommit=True)) as target:
                source_connection.backup(target)
        digest = file_sha256(backup_database_path)
        executor = root / STATE_DIRECTORY / EXECUTOR_DATABASE_NAME
        _plain(executor)
        executor_digest: str | None = None
        if executor.is_file():
            executor_copy = partial / EXECUTOR_DATABASE_NAME
            try:
                with closing(sqlite3.connect(executor, timeout=0.25)) as origin:
                    origin.execute("BEGIN IMMEDIATE")
                    origin.rollback()
                    checkpoint = origin.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                    if checkpoint is None or int(checkpoint[0]) != 0:
                        raise FoundationError(
                            "maintenance_busy", "DBOS SQLite checkpoint remained blocked"
                        )
                    if origin.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                        raise FoundationError("technical_state", "DBOS SQLite integrity failed")
                    with closing(sqlite3.connect(executor_copy, autocommit=True)) as target:
                        origin.backup(target)
            except sqlite3.OperationalError as error:
                raise FoundationError(
                    "maintenance_busy", f"DBOS SQLite cannot be closed for backup: {error}"
                ) from error
            executor_digest = file_sha256(executor_copy)
        home = root / STATE_DIRECTORY / RPC_HOME_DIRECTORY
        _plain(home)
        home_files: dict[str, str] = {}
        if home.exists():
            if not home.is_dir():
                raise FoundationError("layout", "Managed Pi RPC home is not a directory")
            for entry in sorted(home.rglob("*")):
                _plain(entry)
                if entry.is_dir():
                    continue
                if not entry.is_file():
                    raise FoundationError("layout", "Unsupported Pi RPC home entry")
                relative = entry.relative_to(home).as_posix()
                copy = partial / RPC_HOME_DIRECTORY / relative
                copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(entry, copy)
                home_files[relative] = file_sha256(copy)
        manifest = BackupManifest(
            backup_id=backup_id,
            space_id=info.space_id,
            schema_version=info.schema_version,
            state_revision=info.state_revision,
            execution_epoch=info.execution_epoch,
            created_at=created_at,
            database_sha256=digest,
            executor_sha256=executor_digest,
            pi_rpc_home_files=home_files,
        )
        (partial / "manifest.json").write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8", newline="\n"
        )
        return BackupInfo(manifest=manifest, package=partial)
    except BaseException:
        if partial.exists():
            shutil.rmtree(partial)
        raise


def load_backup(package: Path) -> BackupInfo:
    package = package.expanduser().resolve()
    manifest_path = package / "manifest.json"
    database = package / DATABASE_NAME
    if not package.is_dir() or not manifest_path.is_file() or not database.is_file():
        raise FoundationError("invalid_backup", "Backup package is incomplete")
    try:
        manifest = BackupManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise FoundationError("invalid_backup", f"Invalid backup manifest: {error}") from error
    if package.name != str(manifest.backup_id):
        raise FoundationError("invalid_backup", "Backup package was not published")
    technical_present = bool(manifest.executor_sha256 or manifest.pi_rpc_home_files)
    if manifest.format_version == 2:
        complete = package / "complete.json"
        if not complete.is_file() or complete.is_symlink():
            raise FoundationError("invalid_backup", "Backup publication is incomplete")
        try:
            marker = json.loads(complete.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise FoundationError(
                "invalid_backup", "Backup completion marker is invalid"
            ) from error
        if marker != {"manifest_sha256": file_sha256(manifest_path)}:
            raise FoundationError("invalid_backup", "Backup manifest was not completed")
        if (
            not manifest.sqlite_version
            or not manifest.core_version
            or (manifest.maintenance_boundary != "exclusive-managed")
        ):
            raise FoundationError("invalid_backup", "Backup has no common maintenance boundary")
        if technical_present != (manifest.technical_versions is not None):
            raise FoundationError("invalid_backup", "Backup technical versions are incomplete")
        expected = {"manifest.json", "complete.json", DATABASE_NAME}
        if manifest.executor_sha256 is not None:
            expected.add(EXECUTOR_DATABASE_NAME)
        if manifest.pi_rpc_home_files:
            expected.add(RPC_HOME_DIRECTORY)
        if {entry.name for entry in package.iterdir()} != expected:
            raise FoundationError("invalid_backup", "Backup file inventory differs from manifest")
    elif technical_present:
        raise FoundationError(
            "invalid_backup", "Legacy technical backup has no verified common boundary"
        )
    managed_database = package.parent.parent / DATABASE_NAME
    if (
        package.parent.name == BACKUP_DIRECTORY
        and package.parent.parent.name == STATE_DIRECTORY
        and managed_database.is_file()
    ):
        try:
            with closing(_connect(managed_database, writable=False)) as inventory:
                row = inventory.execute(
                    "SELECT status FROM backup_inventory WHERE backup_id = ?",
                    (str(manifest.backup_id),),
                ).fetchone()
        except sqlite3.Error as error:
            raise FoundationError(
                "invalid_backup", f"Managed backup inventory is unavailable: {error}"
            ) from error
        if row != ("complete",):
            raise FoundationError("invalid_backup", "Managed backup is not current and complete")
    if file_sha256(database) != manifest.database_sha256:
        raise FoundationError("invalid_backup", "Backup database hash mismatch")
    executor = package / EXECUTOR_DATABASE_NAME
    if executor.is_file() != (manifest.executor_sha256 is not None):
        raise FoundationError("invalid_backup", "Backup executor inventory mismatch")
    if manifest.executor_sha256 is not None and file_sha256(executor) != manifest.executor_sha256:
        raise FoundationError("invalid_backup", "Backup executor hash mismatch")
    home = package / RPC_HOME_DIRECTORY
    actual_home: set[str] = set()
    if home.exists():
        _plain(home)
        if not home.is_dir():
            raise FoundationError("invalid_backup", "Backup Pi RPC home is invalid")
        for entry in home.rglob("*"):
            _plain(entry)
            if entry.is_file():
                actual_home.add(entry.relative_to(home).as_posix())
            elif not entry.is_dir():
                raise FoundationError("invalid_backup", "Unsupported Pi RPC backup entry")
    if actual_home != set(manifest.pi_rpc_home_files):
        raise FoundationError("invalid_backup", "Backup Pi RPC file inventory mismatch")
    for relative, digest in manifest.pi_rpc_home_files.items():
        parts = PurePosixPath(relative).parts
        if (
            not parts
            or any(part in (".", "..") or ":" in part for part in parts)
            or PureWindowsPath(relative).as_posix() != relative
            or file_sha256(home.joinpath(*parts)) != digest
        ):
            raise FoundationError("invalid_backup", "Backup Pi RPC file is invalid")
    with closing(snapshot_connection(database)) as connection:
        _begin(connection, writable=False)
        try:
            application = int(connection.execute("PRAGMA application_id").fetchone()[0])
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            row = connection.execute(
                "SELECT space_id, state_revision, execution_epoch FROM spaces"
            ).fetchone()
            if (
                application != APPLICATION_ID
                or version != manifest.schema_version
                or row is None
                or UUID(row[0]) != manifest.space_id
                or int(row[1]) != manifest.state_revision
                or int(row[2]) != manifest.execution_epoch
            ):
                raise FoundationError("invalid_backup", "Manifest/database boundary mismatch")
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
    return BackupInfo(manifest=manifest, package=package)


def restore_database(package: Path, destination: Path) -> SpaceInfo:
    """Restore only into a new quarantined space and rotate the execution epoch."""

    backup = load_backup(package)
    root = _new_root(destination)
    state = root / STATE_DIRECTORY
    backups = state / BACKUP_DIRECTORY
    database = state / DATABASE_NAME
    try:
        state.mkdir()
        backups.mkdir()
        shutil.copy2(backup.package / DATABASE_NAME, database)
        if backup.manifest.executor_sha256 is not None:
            shutil.copy2(
                backup.package / EXECUTOR_DATABASE_NAME,
                state / RESTORED_EXECUTOR_NAME,
            )
        if backup.manifest.pi_rpc_home_files:
            shutil.copytree(
                backup.package / RPC_HOME_DIRECTORY,
                state / RESTORED_RPC_HOME_DIRECTORY,
            )
        with closing(_connect(database, writable=True)) as connection:
            _begin(connection, writable=True)
            now = utc_now().isoformat()
            connection.execute(
                "UPDATE spaces SET state_revision = state_revision + 1, "
                "execution_epoch = execution_epoch + 1, recovery_state = 'quarantined' "
                "WHERE singleton = 1"
            )
            connection.execute(
                "INSERT INTO maintenance_events(event_id, kind, occurred_at, detail_json) "
                "VALUES (?, 'restore', ?, ?)",
                (
                    str(uuid4()),
                    now,
                    canonical_json(
                        {
                            "backup_id": str(backup.manifest.backup_id),
                            "source_state_revision": backup.manifest.state_revision,
                        }
                    ),
                ),
            )
            connection.execute("COMMIT")
        return read_space(root)
    except BaseException:
        if state.exists():
            shutil.rmtree(state)
        raise


def sanitize_database(path: Path) -> None:
    """Checkpoint and compact after all product connections have been closed."""

    _, database, _ = layout(path)
    try:
        with closing(_connect(database, writable=True)) as connection:
            checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint is None or int(checkpoint[0]) != 0:
                raise FoundationError("maintenance_busy", "WAL checkpoint remained blocked")
            connection.execute("VACUUM")
            checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint is None or int(checkpoint[0]) != 0:
                raise FoundationError("maintenance_busy", "Final WAL checkpoint remained blocked")
    except FoundationError:
        raise
    except sqlite3.Error as error:
        code = "maintenance_busy" if "locked" in str(error).casefold() else "storage"
        raise FoundationError(code, f"Cannot sanitize SQLite store: {error}") from error


__all__ = [
    "BACKUP_DIRECTORY",
    "CHILD_EXECUTION_SCHEMA_NAME",
    "CHILD_EXECUTION_SCHEMA_SHA256",
    "CHILD_EXECUTION_SCHEMA_STATEMENTS",
    "CONTINUATION_SCHEMA_NAME",
    "CONTINUATION_SCHEMA_SHA256",
    "CONTINUATION_SCHEMA_STATEMENTS",
    "DATABASE_NAME",
    "EXECUTOR_DATABASE_NAME",
    "RESTORED_EXECUTOR_NAME",
    "RPC_HOME_DIRECTORY",
    "RESTORED_RPC_HOME_DIRECTORY",
    "FoundationError",
    "PLAN_REVISION_SCHEMA_NAME",
    "PLAN_REVISION_SCHEMA_SHA256",
    "PLAN_REVISION_SCHEMA_STATEMENTS",
    "SCHEMA_SHA256",
    "SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "SUBJECT_SCHEMA_NAME",
    "SUBJECT_SCHEMA_SHA256",
    "SUBJECT_SCHEMA_STATEMENTS",
    "STATE_DIRECTORY",
    "backup_database",
    "canonical_json",
    "file_sha256",
    "initialize_space",
    "layout",
    "load_backup",
    "read_space",
    "restore_database",
    "sanitize_database",
    "snapshot_connection",
    "space_connection",
    "utc_now",
]
