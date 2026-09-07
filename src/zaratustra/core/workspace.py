"""Bootstrap and read workspace metadata; no domain records or authority grants."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError

from .migrations import APPLICATION_ID, SCHEMA_VERSION, V1_NAME, V1_SHA256, migrate_v1

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
    schema_version: Literal[1]


def _root(path: Path) -> Path:
    root = path.expanduser().resolve()
    if not root.is_dir():
        raise WorkspaceError("Choose an existing empty directory for the workspace.")
    return root


def _plain_path(path: Path) -> None:
    if path.is_symlink() or path.is_junction():
        raise WorkspaceError(f"Workspace entries must not be links: {path}")


def _read_workspace(root: Path) -> WorkspaceInfo:
    state = root / ".zara"
    database = state / "state.sqlite3"
    for path in (state, database, *(root / name for name in WORKSPACE_DIRECTORIES)):
        _plain_path(path)
    if not state.is_dir() or not database.is_file():
        raise WorkspaceError(
            "No initialized workspace at this path; run zara init in an empty folder."
        )
    if any(not (root / name).is_dir() for name in WORKSPACE_DIRECTORIES):
        raise WorkspaceError("Workspace layout is incomplete; existing files were left unchanged.")
    with closing(
        sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, autocommit=True, timeout=5.0)
    ) as connection:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        application = connection.execute("PRAGMA application_id").fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if application != APPLICATION_ID or version != SCHEMA_VERSION:
            raise WorkspaceError(f"Unsupported workspace database/schema version: {version}.")
        migrations = connection.execute(
            "SELECT version, name, sha256, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
        records = connection.execute(
            "SELECT singleton, workspace_id, created_at FROM workspace"
        ).fetchall()
        if len(records) != 1 or records[0][0] != 1:
            raise WorkspaceError("Invalid workspace metadata; existing files were left unchanged.")
        _, workspace_id, created_at = records[0]
        if migrations != [(SCHEMA_VERSION, V1_NAME, V1_SHA256, created_at)]:
            raise WorkspaceError("Migration history does not match this installed version.")
        return WorkspaceInfo(
            workspace=root,
            database=database,
            workspace_id=workspace_id,
            created_at=created_at,
            schema_version=version,
        )


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
    except (OSError, sqlite3.Error, ValidationError) as error:
        # Never delete/rewrite user data to force success. A partially initialized
        # folder remains visible and is rejected on the next run if incomplete.
        raise WorkspaceError(f"Cannot initialize workspace; files retained: {error}") from error
