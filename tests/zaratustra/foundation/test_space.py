from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

import zaratustra.foundation as core
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


def test_managed_client_is_idle_query_only_and_preserves_operation_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "space"
    root.mkdir()
    created, owner, bootstrap_receipt = bootstrap(root)
    original_connect = storage._connect
    clients: list[sqlite3.Connection] = []

    def connect(database: Path, *, writable: bool) -> sqlite3.Connection:
        connection = original_connect(database, writable=writable)
        clients.append(connection)
        return connection

    monkeypatch.setattr(storage, "_connect", connect)
    with core.managed_core_client(root) as handle:
        assert handle is None
        client = clients[0]
        assert not client.in_transaction
        assert client.execute("PRAGMA query_only").fetchone() == (1,)
        assert client.execute("PRAGMA synchronous").fetchone() == (2,)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            client.execute("UPDATE spaces SET state_revision = 999")
        request = core.CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=created.space_id,
            actor=owner.actor,
            artifact_id=uuid4(),
            media_type="text/plain",
            content="Committed while another client is idle: данные".encode(),
        )
        receipt = apply_operation(root, request, owner)
        assert apply_operation(root, request, owner) == receipt
        assert receipt.state_revision == bootstrap_receipt.state_revision + 1
        assert core.read_artifact(root, request.artifact_id, owner).content == request.content
        assert core.read_receipt(root, request.operation_id, owner) == receipt
        assert client.execute("SELECT state_revision FROM spaces").fetchone() == (
            receipt.state_revision,
        )
        assert not client.in_transaction
        assert read_space(root).execution_epoch == created.execution_epoch
        with pytest.raises(core.FoundationError, match="permission_denied"):
            core.read_artifact(
                root,
                request.artifact_id,
                authorize_local(root, actor="another-actor", source_ref="fictional-owner"),
            )
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        client.execute("SELECT 1")


def test_managed_clients_preserve_native_final_close_checkpoint_and_backup(
    tmp_path: Path,
) -> None:
    root = tmp_path / "space"
    root.mkdir()
    created, owner, _ = bootstrap(root)
    wal = created.database.with_name(created.database.name + "-wal")
    request = core.CreateArtifactRequest(
        operation_id=uuid4(),
        space_id=created.space_id,
        actor=owner.actor,
        artifact_id=uuid4(),
        media_type="text/plain",
        content=b"Final close must preserve this committed output",
    )
    with core.managed_core_client(root):
        with core.managed_core_client(root):
            receipt = apply_operation(root, request, owner)
            assert wal.is_file() and wal.stat().st_size > 0
            with pytest.raises(FoundationError, match="history_busy"):
                core.create_backup(root, uuid4(), owner)
        assert wal.is_file()
        assert core.read_artifact(root, request.artifact_id, owner).content == request.content
        with core.managed_core_client(root):
            assert core.read_receipt(root, receipt.operation_id, owner) == receipt
        with pytest.raises(FoundationError, match="history_busy"):
            with core.managed_pi_lock(root):
                raise AssertionError("The remaining client still owns the fence")
    assert not wal.exists()
    with storage.snapshot_connection(created.database) as snapshot:
        assert snapshot.execute("SELECT state_revision FROM spaces").fetchone() == (
            receipt.state_revision,
        )
        assert snapshot.execute(
            "SELECT payload FROM managed_content WHERE record_id = ?",
            (str(request.artifact_id),),
        ).fetchone() == (request.content,)
    snapshot.close()
    backup = core.create_backup(root, uuid4(), owner)
    restored = tmp_path / "restored"
    restored.mkdir()
    recovery = core.authorize_recovery(actor=owner.actor, source_ref="fictional-recovery")
    restored_info = core.restore_backup(backup.package, restored, recovery)
    assert restored_info.space_id == created.space_id
    assert restored_info.execution_epoch == created.execution_epoch + 1
    with storage.snapshot_connection(restored_info.database) as snapshot:
        assert snapshot.execute(
            "SELECT payload FROM managed_content WHERE record_id = ?",
            (str(request.artifact_id),),
        ).fetchone() == (request.content,)
    snapshot.close()


@pytest.mark.parametrize("failure_at", ["configure", "query_only", "commit"])
def test_managed_client_start_failure_closes_handle_and_releases_fence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_at: str
) -> None:
    root = tmp_path / "space"
    root.mkdir()
    created = initialize_space(root)
    actual_connect = sqlite3.connect
    actual_configure = storage._configure
    clients: list[sqlite3.Connection] = []
    failures = 0

    class FailedConnection:
        def __init__(self, actual: sqlite3.Connection) -> None:
            self.actual = actual

        def execute(self, statement: str, *args: Any) -> sqlite3.Cursor:
            nonlocal failures
            if statement == ("PRAGMA query_only = ON" if failure_at == "query_only" else "COMMIT"):
                failures += 1
                raise sqlite3.OperationalError("fictional client startup failure")
            return self.actual.execute(statement, *args)

        def __getattr__(self, name: str) -> Any:
            return getattr(self.actual, name)

    def connect(*args: Any, **kwargs: Any) -> sqlite3.Connection | FailedConnection:
        actual = actual_connect(*args, **kwargs)
        clients.append(actual)
        return actual if failure_at == "configure" else FailedConnection(actual)

    def configure(connection: sqlite3.Connection, *, writable: bool) -> None:
        nonlocal failures
        actual_configure(connection, writable=writable)
        failures += 1
        raise sqlite3.OperationalError("fictional client startup failure")

    monkeypatch.setattr(sqlite3, "connect", connect)
    if failure_at == "configure":
        monkeypatch.setattr(storage, "_configure", configure)
    with pytest.raises(FoundationError, match="fictional client startup failure"):
        with core.managed_core_client(root):
            raise AssertionError("Failed initialization cannot enter the caller body")
    assert failures == 1 and len(clients) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        clients[0].execute("SELECT 1")
    monkeypatch.undo()
    with core.managed_pi_lock(root):
        assert read_space(root) == created
    with core.managed_core_client(root):
        assert read_space(root) == created


def test_managed_client_bad_identity_releases_the_maintenance_fence(tmp_path: Path) -> None:
    root = tmp_path / "space"
    root.mkdir()
    created = initialize_space(root)
    with sqlite3.connect(created.database) as connection:
        connection.execute("PRAGMA application_id = 0")
    connection.close()
    with pytest.raises(FoundationError, match="unsupported_schema"):
        with core.managed_core_client(root):
            raise AssertionError("An unknown identity cannot enter the caller body")
    with core.managed_pi_lock(root):
        with sqlite3.connect(created.database) as connection:
            assert connection.execute("PRAGMA application_id").fetchone() == (0,)
            connection.execute(f"PRAGMA application_id = {storage.APPLICATION_ID}")
        connection.close()
    with core.managed_core_client(root):
        assert read_space(root) == created


def test_managed_client_caller_failure_and_repeated_exit_leave_no_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "space"
    root.mkdir()
    created = initialize_space(root)
    original_connect = storage._connect
    clients: list[sqlite3.Connection] = []

    def connect(database: Path, *, writable: bool) -> sqlite3.Connection:
        actual = original_connect(database, writable=writable)
        clients.append(actual)
        return actual

    monkeypatch.setattr(storage, "_connect", connect)
    context = core.managed_core_client(root)
    failure = ValueError("fictional caller error")
    with pytest.raises(ValueError) as propagated:
        with context:
            raise failure
    assert propagated.value is failure
    assert context.__exit__(None, None, None) is False
    assert len(clients) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        clients[0].execute("SELECT 1")
    with core.managed_pi_lock(root):
        assert read_space(root) == created


def test_managed_client_cannot_open_during_maintenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "space"
    root.mkdir()
    created = initialize_space(root)
    original_connect = storage._connect
    clients: list[sqlite3.Connection] = []

    def connect(database: Path, *, writable: bool) -> sqlite3.Connection:
        actual = original_connect(database, writable=writable)
        clients.append(actual)
        return actual

    monkeypatch.setattr(storage, "_connect", connect)
    with core.managed_pi_lock(root):
        with pytest.raises(FoundationError, match="history_busy"):
            with core.managed_core_client(root):
                raise AssertionError("Maintenance must fence a new client before SQL open")
        assert clients == []
    with core.managed_core_client(root):
        assert read_space(root) == created


def test_managed_client_retains_schema_18_history_and_epoch_without_migration(
    tmp_path: Path,
) -> None:
    root = tmp_path / "space"
    root.mkdir()
    _, owner, receipt = bootstrap(root)
    for upgrade in (
        core.upgrade_space,
        core.upgrade_execution_space,
        core.upgrade_continuation_space,
        core.upgrade_composition_space,
        core.upgrade_child_execution_space,
        core.upgrade_plan_revision_space,
        core.upgrade_parent_execution_space,
        core.upgrade_binding_space,
        core.upgrade_knowledge_space,
        core.upgrade_development_space,
        core.upgrade_change_package_space,
        core.upgrade_memory_space,
        core.upgrade_activity_setup_space,
        core.upgrade_structures_space,
        core.upgrade_workflow_space,
        core.upgrade_conversation_space,
        core.upgrade_delivery_correlation_space,
    ):
        upgrade(root, owner)
    before = inspect_space(root, owner)
    audit = core.read_operation_audit(root, receipt.operation_id, owner)
    with core.managed_core_client(root):
        assert read_space(root).schema_version == 18
        assert inspect_space(root, owner) == before
        assert core.read_operation_audit(root, receipt.operation_id, owner) == audit
        assert core.read_receipt(root, receipt.operation_id, owner) == receipt
    assert inspect_space(root, owner) == before


def test_killed_managed_client_reopens_committed_wal_and_releases_maintenance(
    tmp_path: Path,
) -> None:
    root = tmp_path / "space"
    root.mkdir()
    created, owner, _ = bootstrap(root)
    ready_file = tmp_path / "child-ready"
    artifact_id, operation_id = uuid4(), uuid4()
    payload = b"Committed before abrupt client process death"
    script = (
        "from pathlib import Path\n"
        "from uuid import UUID\n"
        "import sys\n"
        "import zaratustra.foundation as core\n"
        "root = Path(sys.argv[1])\n"
        "owner = core.authorize_local(root, actor='owner-local', "
        "source_ref='fictional-process')\n"
        "with core.managed_core_client(root):\n"
        "    core.apply_operation(root, core.CreateArtifactRequest(\n"
        "        operation_id=UUID(sys.argv[4]), space_id=core.read_space(root).space_id,\n"
        "        actor=owner.actor, artifact_id=UUID(sys.argv[3]),\n"
        "        media_type='text/plain',\n"
        "        content=b'Committed before abrupt client process death'), owner)\n"
        "    Path(sys.argv[2]).write_text('committed', encoding='utf-8')\n"
        "    sys.stdin.read(1)\n"
    )

    def committed_child_exit() -> None:
        # wait/communicate observe exit but Popen still owns the process handle.
        # Release that owning object before testing a new first WAL client.
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(root),
                str(ready_file),
                str(artifact_id),
                str(operation_id),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            deadline = time.monotonic() + 10
            while (
                not ready_file.is_file() and process.poll() is None and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            if not ready_file.is_file():
                process.kill()
                stdout, stderr = process.communicate(timeout=10)
                raise AssertionError(f"Client failed before its commit barrier: {stdout}\n{stderr}")
            assert ready_file.read_text(encoding="utf-8") == "committed"
            assert core.read_artifact(root, artifact_id, owner).content == payload
            with pytest.raises(FoundationError, match="history_busy"):
                core.create_backup(root, uuid4(), owner)
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)
        assert process.returncode is not None

    committed_child_exit()
    with core.managed_core_client(root):
        reopened = read_space(root)
        assert reopened.space_id == created.space_id
        assert reopened.execution_epoch == created.execution_epoch
        assert core.read_artifact(root, artifact_id, owner).content == payload
        assert core.read_receipt(root, operation_id, owner).operation_id == operation_id
    backup = core.create_backup(root, uuid4(), owner)
    assert backup.manifest.space_id == created.space_id
    assert backup.manifest.state_revision == reopened.state_revision


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
