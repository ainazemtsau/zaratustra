from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

import zaratustra.foundation.storage as storage
from zaratustra.foundation import (
    BootstrapRequest,
    FoundationError,
    LocalAuthority,
    OperationReceipt,
    SpaceInfo,
    apply_operation,
    authorize_local,
    initialize_space,
    inspect_space,
    read_space,
)


def bootstrap(
    root: Path, actor: str = "owner-local"
) -> tuple[SpaceInfo, LocalAuthority, OperationReceipt]:
    info = initialize_space(root)
    authority = authorize_local(root, actor=actor, source_ref="synthetic-owner-confirmation")
    receipt = apply_operation(
        root,
        BootstrapRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=actor,
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        authority,
    )
    return info, authority, receipt


def test_empty_space_has_own_identity_and_reopens_without_domain_state(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    created = initialize_space(root)
    reopened = read_space(root)

    assert reopened == created
    assert reopened.state_revision == 0
    assert reopened.database == root / ".zara-core" / "core.sqlite3"
    assert list((root / ".zara-core" / "backups").iterdir()) == []


@pytest.mark.parametrize("busy_reads", [1, 3])
@pytest.mark.parametrize("busy_at", ["execute", "fetch"])
@pytest.mark.parametrize(
    "statement,label",
    [
        ("PRAGMA application_id", "application_id"),
        ("PRAGMA user_version", "user_version"),
        ("PRAGMA journal_mode", "journal_mode"),
        (
            "SELECT version, name, sha256 FROM schema_migrations ORDER BY version",
            "schema_migrations",
        ),
        (
            "SELECT space_id, created_at, state_revision, execution_epoch, recovery_state "
            "FROM spaces",
            "spaces",
        ),
    ],
)
def test_first_deferred_read_only_retries_transient_busy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    busy_reads: int,
    busy_at: str,
    statement: str,
    label: str,
) -> None:
    root = tmp_path / "space"
    root.mkdir()
    created = initialize_space(root)
    original_connect = storage._connect
    connections: list[sqlite3.Connection] = []
    attempts = 0

    def encounter() -> None:
        nonlocal attempts
        attempts += 1
        if attempts <= busy_reads:
            error = sqlite3.OperationalError("database is locked")
            error.sqlite_errorcode = sqlite3.SQLITE_BUSY
            error.sqlite_errorname = "SQLITE_BUSY"
            raise error

    class BusyCursor:
        def __init__(self, actual: sqlite3.Cursor) -> None:
            self.actual = actual

        def fetchall(self) -> list[tuple[Any, ...]]:
            encounter()
            return self.actual.fetchall()

        def close(self) -> None:
            self.actual.close()

    class BusyFirstRead:
        def __init__(self, actual: sqlite3.Connection) -> None:
            self.actual = actual

        def execute(self, requested: str) -> sqlite3.Cursor | BusyCursor:
            if requested == statement and busy_at == "execute":
                encounter()
            cursor = self.actual.execute(requested)
            return BusyCursor(cursor) if requested == statement and busy_at == "fetch" else cursor

        def __getattr__(self, name: str) -> object:
            return getattr(self.actual, name)

    def connect(database: Path, *, writable: bool) -> BusyFirstRead:
        actual = original_connect(database, writable=writable)
        connections.append(actual)
        return BusyFirstRead(actual)

    monkeypatch.setattr(storage, "_connect", connect)
    if busy_reads == 1:
        assert read_space(root).space_id == created.space_id
        assert attempts == 2
    else:
        with pytest.raises(FoundationError) as refused:
            read_space(root)
        assert refused.value.code == "storage"
        assert "SQLite identity failed" in str(refused.value)
        assert f"at {label} (SQLITE_BUSY)" in str(refused.value)
        assert attempts == 3
    assert len(connections) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")
    monkeypatch.undo()
    assert read_space(root).state_revision == created.state_revision


def test_identity_non_busy_error_does_not_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "space"
    root.mkdir()
    initialize_space(root)
    original_connect = storage._connect
    attempts = 0

    class FailedRead:
        def __init__(self, actual: sqlite3.Connection) -> None:
            self.actual = actual

        def execute(self, statement: str) -> sqlite3.Cursor:
            nonlocal attempts
            if statement == "PRAGMA journal_mode":
                attempts += 1
                error = sqlite3.OperationalError("busy wording without a lock code")
                error.sqlite_errorcode = sqlite3.SQLITE_ERROR
                error.sqlite_errorname = "SQLITE_ERROR"
                raise error
            return self.actual.execute(statement)

        def __getattr__(self, name: str) -> object:
            return getattr(self.actual, name)

    monkeypatch.setattr(
        storage,
        "_connect",
        lambda database, writable: FailedRead(original_connect(database, writable=writable)),
    )
    with pytest.raises(FoundationError, match="at journal_mode .*SQLITE_ERROR"):
        read_space(root)
    assert attempts == 1


@pytest.mark.parametrize("failure_at", ("body", "commit"))
def test_identity_retry_never_replays_body_or_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_at: str
) -> None:
    root = tmp_path / "space"
    root.mkdir()
    created = initialize_space(root)
    original_connect = storage._connect
    commits = 0
    bodies = 0

    class FailedCommit:
        def __init__(self, actual: sqlite3.Connection) -> None:
            self.actual = actual

        def execute(self, statement: str) -> sqlite3.Cursor:
            nonlocal commits
            if statement == "COMMIT":
                commits += 1
                raise sqlite3.OperationalError("database is locked")
            return self.actual.execute(statement)

        def __getattr__(self, name: str) -> object:
            return getattr(self.actual, name)

    if failure_at == "commit":
        monkeypatch.setattr(
            storage,
            "_connect",
            lambda database, writable: FailedCommit(original_connect(database, writable=writable)),
        )
    with pytest.raises(FoundationError, match=f"SQLite {failure_at} failed"):
        with storage.space_connection(root, writable=True):
            bodies += 1
            if failure_at == "body":
                raise sqlite3.OperationalError("database is locked")
    assert bodies == 1 and commits == int(failure_at == "commit")
    monkeypatch.undo()
    assert read_space(root).state_revision == created.state_revision


def test_failed_sqlite_configuration_closes_its_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenConnection:
        closed = False

        def create_function(self, *args: object, **kwargs: object) -> None:
            pass

        def execute(self, _statement: str) -> None:
            raise sqlite3.OperationalError("synthetic configuration failure")

        def close(self) -> None:
            self.closed = True

    broken = BrokenConnection()
    monkeypatch.setattr(sqlite3, "connect", lambda *_args, **_kwargs: broken)
    with pytest.raises(sqlite3.OperationalError, match="synthetic configuration failure"):
        storage._connect(tmp_path / "synthetic.sqlite3", writable=False)
    assert broken.closed


def test_initialization_refuses_legacy_or_nonempty_directory_without_change(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    legacy = root / ".zara" / "state.sqlite3"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"legacy sentinel")

    with pytest.raises(FoundationError, match="empty") as refusal:
        initialize_space(root)

    assert refusal.value.code == "layout"
    assert legacy.read_bytes() == b"legacy sentinel"
    assert not (root / ".zara-core").exists()


def test_unknown_schema_is_refused_without_replacement_or_migration(tmp_path: Path) -> None:
    root = tmp_path / "space"
    root.mkdir()
    created = initialize_space(root)
    with sqlite3.connect(created.database) as connection:
        connection.execute("PRAGMA user_version = 99")
    before = {
        path.name: path.read_bytes()
        for path in created.database.parent.iterdir()
        if path.is_file()
        and path.name.startswith("core.sqlite3")
        and not path.name.endswith("-shm")
    }

    with pytest.raises(FoundationError) as refusal:
        read_space(root)
    after = {
        path.name: path.read_bytes()
        for path in created.database.parent.iterdir()
        if path.is_file()
        and path.name.startswith("core.sqlite3")
        and not path.name.endswith("-shm")
    }

    assert refusal.value.code == "unsupported_schema"
    assert after == before
    with sqlite3.connect(created.database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (99,)


def test_model_free_inspection_sees_bootstrap_records_and_no_payload(tmp_path: Path) -> None:
    root = tmp_path / "space"
    root.mkdir()
    _, authority, receipt = bootstrap(root)

    inspection = inspect_space(root, authority)

    assert inspection.operation_count == 1
    assert inspection.audit_count == 1
    assert inspection.receipt_count == 1
    assert {record.kind for record in inspection.records} == {"decision", "grant"}
    assert receipt.state_revision == inspection.space.state_revision


def test_import_refuses_unfixed_sqlite_runtime_in_a_fresh_process() -> None:
    environment = os.environ.copy()
    environment.pop("ZARATUSTRA_SQLITE_DLL", None)
    result = subprocess.run(
        [sys.executable, "-c", "import zaratustra.foundation"],
        check=False,
        capture_output=True,
        encoding="utf-8",
        env=environment,
    )

    assert result.returncode != 0
    assert "Unsupported SQLite runtime" in result.stderr
