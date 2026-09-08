"""Invisible persistence, refusal and transaction behavior of the bootstrap."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest

from zaratustra.core import WorkspaceError, init_workspace, read_workspace
from zaratustra.core.migrations import V1_NAME, V1_SHA256, migrate_v1


def test_reopen_preserves_metadata_and_database_bytes(tmp_path: Path) -> None:
    first = init_workspace(tmp_path)
    before = first.database.read_bytes()
    assert read_workspace(tmp_path) == first
    assert init_workspace(tmp_path) == first
    assert first.database.read_bytes() == before
    with closing(sqlite3.connect(first.database)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute(
            "SELECT version, name, sha256, applied_at FROM schema_migrations"
        ).fetchall() == [(1, V1_NAME, V1_SHA256, first.created_at.isoformat())]
        assert connection.execute("SELECT workspace_id, created_at FROM workspace").fetchall() == [
            (str(first.workspace_id), first.created_at.isoformat())
        ]
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]


def test_nonempty_directory_is_not_modified(tmp_path: Path) -> None:
    sentinel = tmp_path / "keep.txt"
    sentinel.write_bytes(b"original unrelated bytes")
    with pytest.raises(WorkspaceError, match="not empty"):
        init_workspace(tmp_path)
    assert sentinel.read_bytes() == b"original unrelated bytes"
    assert list(tmp_path.iterdir()) == [sentinel]


def test_status_does_not_initialize_and_init_does_not_choose_missing_folder(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError, match="No initialized workspace"):
        read_workspace(tmp_path)
    with pytest.raises(WorkspaceError, match="existing empty directory"):
        init_workspace(tmp_path / "missing")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("command", [read_workspace, init_workspace])
def test_newer_schema_is_refused_without_rewriting(tmp_path: Path, command: object) -> None:
    info = init_workspace(tmp_path)
    # Deliberately invalid isolated fixture, never a repair of acceptance data.
    with closing(sqlite3.connect(info.database)) as connection:
        connection.execute("PRAGMA user_version = 3")
    before = info.database.read_bytes()
    assert callable(command)
    with pytest.raises(WorkspaceError, match="Unsupported"):
        command(tmp_path)
    assert info.database.read_bytes() == before


def test_corrupt_or_partial_workspace_is_not_overwritten(tmp_path: Path) -> None:
    state = tmp_path / ".zara"
    state.mkdir()
    database = state / "state.sqlite3"
    database.write_bytes(b"not a database")
    for name in ("processes", "artifacts", "projections", "inbox"):
        (tmp_path / name).mkdir()
    with pytest.raises(WorkspaceError, match="Cannot initialize"):
        init_workspace(tmp_path)
    assert database.read_bytes() == b"not a database"
    (tmp_path / "inbox").rmdir()
    with pytest.raises(WorkspaceError, match="incomplete"):
        init_workspace(tmp_path)
    assert database.read_bytes() == b"not a database"


def test_migration_rolls_back_ddl_metadata_and_version_on_failure() -> None:
    with closing(sqlite3.connect(":memory:", isolation_level=None)) as connection:

        def deny_metadata(action: int, arg1: str | None, *_: object) -> int:
            return (
                sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_INSERT and arg1 == "schema_migrations"
                else sqlite3.SQLITE_OK
            )

        connection.set_authorizer(deny_metadata)
        with pytest.raises(sqlite3.DatabaseError):
            migrate_v1(connection, str(uuid4()), "2026-09-07T00:00:00+00:00")
        connection.set_authorizer(None)
        assert connection.execute("SELECT name FROM sqlite_master").fetchall() == []
        assert connection.execute("PRAGMA user_version").fetchone() == (0,)
        assert connection.execute("PRAGMA application_id").fetchone() == (0,)
        assert not connection.in_transaction
