"""Bootstrap and read workspace metadata; no domain records or authority grants."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError

from .migration_v2 import V2_NAME, V2_SHA256, migrate_v2
from .migration_v3 import V3_NAME, V3_SHA256, migrate_v3
from .migration_v4 import V4_NAME, V4_SHA256, migrate_v4
from .migrations import APPLICATION_ID, V1_NAME, V1_SHA256, migrate_v1

WORKSPACE_DIRECTORIES = ("processes", "artifacts", "projections", "inbox")


class WorkspaceError(Exception):
    """The selected directory cannot be initialized or read safely."""


class WorkspaceInfo(BaseModel):
    """Persisted bootstrap facts returned by Core, not a Work revision or permission."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    workspace: Path
    database: Path
    workspace_id: UUID
    created_at: AwareDatetime
    schema_version: Literal[1, 2, 3, 4]


def _root(path: Path) -> Path:
    root = path.expanduser().resolve()
    if not root.is_dir():
        raise WorkspaceError("Choose an existing empty directory for the workspace.")
    return root


def _plain_path(path: Path) -> None:
    if path.is_symlink() or path.is_junction():
        raise WorkspaceError(f"Workspace entries must not be links: {path}")


def _database_path(root: Path) -> Path:
    state = root / ".zara"
    database = state / "state.sqlite3"
    for path in (state, database, *(root / name for name in WORKSPACE_DIRECTORIES)):
        _plain_path(path)
    if not state.is_dir() or not database.is_file():
        raise WorkspaceError(
            "No initialized workspace at this path; run zara init in an empty folder."
        )
    if any(not (root / name).is_dir() for name in ("processes", "inbox")):
        raise WorkspaceError("Workspace layout is incomplete; existing files were left unchanged.")
    return database


def _metadata(connection: sqlite3.Connection, root: Path, database: Path) -> WorkspaceInfo:
    application = connection.execute("PRAGMA application_id").fetchone()[0]
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if application != APPLICATION_ID or version not in (1, 2, 3, 4):
        raise WorkspaceError(f"Unsupported workspace database/schema version: {version}.")
    for name in ("artifacts", "projections"):
        entry = root / name
        if (entry.exists() or version < 4) and not entry.is_dir():
            raise WorkspaceError(
                "Workspace layout is incomplete; existing files were left unchanged."
            )
    migrations = connection.execute(
        "SELECT version, name, sha256, applied_at FROM schema_migrations ORDER BY version"
    ).fetchall()
    records = connection.execute(
        "SELECT singleton, workspace_id, created_at FROM workspace"
    ).fetchall()
    if len(records) != 1 or records[0][0] != 1:
        raise WorkspaceError("Invalid workspace metadata; existing files were left unchanged.")
    _, workspace_id, created_at = records[0]
    if len(migrations) != version or migrations[0] != (1, V1_NAME, V1_SHA256, created_at):
        raise WorkspaceError("Migration history does not match this installed version.")
    if version >= 2:
        if migrations[1][:3] != (2, V2_NAME, V2_SHA256):
            raise WorkspaceError("Migration history does not match this installed version.")
        applied = datetime.fromisoformat(migrations[1][3])
        if applied.tzinfo is None:
            raise WorkspaceError("Migration timestamp must have a timezone.")
        connection.execute("SELECT singleton, revision FROM core_state").fetchall()
        connection.execute("SELECT id, kind, revision, body FROM core_records LIMIT 0")
    if version >= 3:
        if migrations[2][:3] != (3, V3_NAME, V3_SHA256):
            raise WorkspaceError("Migration history does not match this installed version.")
        if datetime.fromisoformat(migrations[2][3]).tzinfo is None:
            raise WorkspaceError("Migration timestamp must have a timezone.")
        connection.execute("SELECT id, state_revision, body FROM mutation_events LIMIT 0")
        connection.execute(
            "SELECT operation_id, event_id, fingerprint, body FROM mutation_receipts LIMIT 0"
        )
    if version >= 4:
        if migrations[3][:3] != (4, V4_NAME, V4_SHA256):
            raise WorkspaceError("Migration history does not match this installed version.")
        if datetime.fromisoformat(migrations[3][3]).tzinfo is None:
            raise WorkspaceError("Migration timestamp must have a timezone.")
        connection.execute("SELECT id, artifact_id, body FROM artifact_versions LIMIT 0")
    return WorkspaceInfo(
        workspace=root,
        database=database,
        workspace_id=workspace_id,
        created_at=created_at,
        schema_version=version,
    )


@contextmanager
def workspace_connection(
    path: Path, *, write: bool = False
) -> Iterator[tuple[sqlite3.Connection, WorkspaceInfo]]:
    """Validate metadata in the same transaction as the operation; never create a DB."""
    try:
        root = _root(path)
        database = _database_path(root)
        mode = "rw" if write else "ro"
        with closing(
            sqlite3.connect(
                database.as_uri() + f"?mode={mode}", uri=True, autocommit=True, timeout=5.0
            )
        ) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            if write:
                connection.execute("PRAGMA synchronous = FULL")
            else:
                connection.execute("PRAGMA query_only = ON")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield connection, _metadata(connection, root, database)
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
    except (OSError, sqlite3.Error, ValueError) as error:
        raise WorkspaceError(f"Cannot access workspace: {error}") from error


def _read_workspace(root: Path) -> WorkspaceInfo:
    with workspace_connection(root) as (_, info):
        return info


def migrate_workspace(path: Path, *, target_version: Literal[2, 3, 4] = 4) -> WorkspaceInfo:
    """Explicit sequential upgrade; never grant rights, silently downgrade or repair."""
    if type(target_version) is not int or target_version not in (2, 3, 4):
        raise WorkspaceError("Unsupported migration target")
    with workspace_connection(path, write=True) as (connection, info):
        if info.schema_version > target_version:
            raise WorkspaceError("Schema downgrade is not supported")
        if info.schema_version == 1:
            migrate_v2(connection, datetime.now(UTC).isoformat())
        if info.schema_version < 3 and target_version >= 3:
            # Local import avoids a module initialization cycle with record models.
            from .records import _read_records

            legacy = _read_records(connection, info.workspace_id)
            if legacy.state_revision not in (0, 1):
                raise WorkspaceError("Schema 2 only supports initial records")
            migrate_v3(connection, datetime.now(UTC).isoformat())
        if info.schema_version < 4 and target_version == 4:
            from .mutations import _history
            from .records import _read_records

            _history(connection, _read_records(connection, info.workspace_id))
            migrate_v4(connection, datetime.now(UTC).isoformat())
        return _metadata(connection, info.workspace, info.database)


def read_workspace(path: Path) -> WorkspaceInfo:
    """Read a selected workspace without creating a DB or applying migrations."""
    try:
        return _read_workspace(_root(path))
    except (OSError, sqlite3.Error, ValidationError) as error:
        raise WorkspaceError(f"Cannot read workspace: {error}") from error


def init_workspace(path: Path) -> WorkspaceInfo:
    """Initialize an empty selected folder; an existing workspace is read without writes.

    Bootstrap is an explicit local invocation before Work exists. It creates no
    Process, Work, actor, owner receipt or permissions for later mutations.
    """
    try:
        root = _root(path)
        entries = list(root.iterdir())
        if entries:
            if (root / ".zara").exists() or (root / ".zara").is_symlink():
                return _read_workspace(root)
            raise WorkspaceError("Directory is not empty; choose an empty workspace folder.")
        state = root / ".zara"
        state.mkdir()  # Exclusive reservation: a competing init cannot own this directory.
        database = state / "state.sqlite3"
        with database.open("xb"):
            pass
        # Explicit autocommit mode, with BEGIN/COMMIT owned by the migration.
        with closing(sqlite3.connect(database, autocommit=True, timeout=5.0)) as connection:
            connection.execute("PRAGMA journal_mode = DELETE")
            connection.execute("PRAGMA synchronous = FULL")
            migrate_v1(connection, str(uuid4()), datetime.now(UTC).isoformat())
        for name in WORKSPACE_DIRECTORIES:
            (root / name).mkdir()
        return _read_workspace(root)
    except (OSError, sqlite3.Error, ValidationError, WorkspaceError) as error:
        # Never delete/rewrite user data to force success. A partially initialized
        # folder remains visible and is rejected on the next run if incomplete.
        raise WorkspaceError(f"Cannot initialize workspace; files retained: {error}") from error
