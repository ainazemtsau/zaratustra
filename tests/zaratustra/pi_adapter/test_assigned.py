"""Assigned bridge and managed technical-state boundaries without a model service."""

from __future__ import annotations

import pickle
import shutil
import sqlite3
import threading
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from dbos import DBOS, DBOSClient

from tests.zaratustra.foundation.test_continuation import ready
from zaratustra.foundation import (
    AssignAttemptRequest,
    CreateGrantRequest,
    CreateResourceRequest,
    CreateWorkRequest,
    DeleteArtifactRequest,
    DeleteWorkRequest,
    FoundationError,
    GrantState,
    LocalAuthority,
    OutputContract,
    RecordAttemptStopRequest,
    RequestAttemptStopRequest,
    ResourceState,
    RevokeGrantRequest,
    WorkState,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    inspect_space,
    managed_pi_lock,
    managed_pi_session_lock,
    read_artifact,
    read_execution,
    restore_backup,
)
from zaratustra.pi_adapter import Bridge
from zaratustra.pi_adapter.assigned import (
    EXECUTOR_VERSION,
    WORKFLOW_NAME,
    _purge_technical_data,
    complete_assigned_deletions,
    deliver_outbox,
    resolve_assigned_work,
)


def assigned(tmp_path: Path) -> tuple[Path, Path, UUID, UUID, UUID, UUID]:
    root, workspace, space_id, _, work_id, resource_id = ready(tmp_path)
    authority = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    attempt_id, session_id = uuid4(), uuid4()
    apply_operation(
        root,
        AssignAttemptRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            attempt_id=attempt_id,
            work_id=work_id,
            expected_work_revision=1,
            resource_id=resource_id,
            expected_resource_revision=1,
            session_id=session_id,
            executor_version=EXECUTOR_VERSION,
        ),
        authority,
    )
    return root, workspace, space_id, work_id, attempt_id, session_id


def test_assigned_bridge_saves_partial_question_and_one_addressed_answer(tmp_path: Path) -> None:
    root, workspace, _, work_id, attempt_id, session_id = assigned(tmp_path)
    authority = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    activity_id = read_execution(root, work_id, authority).activity.activity_id
    rpc = Bridge(
        root,
        authority,
        workspace,
        100,
        assigned_attempt_id=attempt_id,
        assigned_session_id=session_id,
    )
    rpc.connect(session_id)
    rpc.select(session_id, activity_id, work_id)
    with pytest.raises(FoundationError, match="unknown_session"):
        rpc.connect(uuid4())
    with pytest.raises(FoundationError, match="permission_denied"):
        rpc.start_attempt(session_id, interrupt_previous=False)
    wait_id = uuid4()
    rpc.open_wait(session_id, attempt_id, wait_id, "Partial fiction", "Which code?", "Add code")
    snapshot = read_execution(root, work_id, authority)
    wait = snapshot.waits[0]
    assert wait.status == "open" and wait.remainder == "Add code"
    assert (
        read_artifact(root, wait.partial_refs[0].artifact_id, authority).content
        == b"Partial fiction"
    )
    interactive = Bridge(root, authority, workspace, 100)
    user_session = uuid4()
    interactive.connect(user_session)
    interactive.select(user_session, activity_id, work_id)
    visible_waits = cast(list[dict[str, object]], interactive.snapshot(user_session)["waits"])
    assert visible_waits[0]["question"] == "Which code?"
    first = interactive.answer_wait(user_session, wait_id, "Code A")
    assert interactive.answer_wait(user_session, wait_id, "Code A") == first
    with pytest.raises(FoundationError, match="stale_wait"):
        interactive.answer_wait(user_session, wait_id, "Code B")
    after = read_execution(root, work_id, authority)
    assert [item.kind for item in after.outbox] == ["launch", "resume"]
    assert after.assignments[0].status == "ready"


def test_concurrent_pi_locks_exclude_deletion_maintenance(tmp_path: Path) -> None:
    root, _, _, _, _, _ = assigned(tmp_path)
    with managed_pi_session_lock(root), managed_pi_session_lock(root):
        with pytest.raises(FoundationError, match="history_busy"):
            with managed_pi_lock(root):
                raise AssertionError("Maintenance must not enter while Pi is active")
    with managed_pi_lock(root):
        assert root.is_dir()


def test_technical_backup_is_hashed_restored_inert_and_blocks_bare_cleanup(tmp_path: Path) -> None:
    root, _, space_id, work_id, _, _ = assigned(tmp_path)
    authority = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    state = root / ".zara-core"
    executor = state / "executor.sqlite3"
    with sqlite3.connect(executor) as connection:
        connection.execute("CREATE TABLE synthetic (value TEXT NOT NULL)")
        connection.execute("INSERT INTO synthetic(value) VALUES ('fictional')")
    home = state / "pi-rpc-home" / str(uuid4())
    home.mkdir(parents=True)
    (home / "synthetic.txt").write_text("fictional\n", encoding="utf-8", newline="\n")
    backup = create_backup(root, uuid4(), authority)
    assert backup.manifest.executor_sha256 is not None
    assert len(backup.manifest.pi_rpc_home_files) == 1
    restored_root = tmp_path / "restored"
    restored_root.mkdir()
    restored = restore_backup(
        backup.package,
        restored_root,
        authorize_recovery(actor="owner", source_ref="synthetic-recovery-console"),
    )
    assert restored.execution_epoch == 2 and restored.recovery_state == "quarantined"
    assert (restored_root / ".zara-core" / "executor-restored.sqlite3").is_file()
    assert not (restored_root / ".zara-core" / "executor.sqlite3").exists()
    revision = read_execution(root, work_id, authority).work.revision
    apply_operation(
        root,
        DeleteWorkRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            expected_revision=revision,
        ),
        authority,
    )
    with pytest.raises(FoundationError, match="technical_cleanup_required"):
        complete_deletions(root, authority)


@pytest.fixture(scope="module")
def dbos_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database = tmp_path_factory.mktemp("assigned-dbos") / "executor.sqlite3"
    DBOS(
        config={
            "name": "zaratustra-assigned-rpc",
            "system_database_url": f"sqlite:///{database.resolve().as_posix()}",
            "application_version": EXECUTOR_VERSION,
        }
    )
    DBOS.launch()
    DBOS.destroy(destroy_registry=True, workflow_completion_timeout_sec=1)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
    return database


def _managed_space(
    tmp_path: Path, dbos_template: Path
) -> tuple[Path, Path, UUID, UUID, UUID, UUID]:
    root, workspace, space_id, work_id, attempt_id, session_id = assigned(tmp_path)
    shutil.copyfile(dbos_template, root / ".zara-core" / "executor.sqlite3")
    return root, workspace, space_id, work_id, attempt_id, session_id


def _workflows(root: Path) -> list[dict[str, object]]:
    database = root / ".zara-core" / "executor.sqlite3"
    client = DBOSClient(
        system_database_url=f"sqlite:///{database.resolve().as_posix()}",
        application_name="zaratustra-assigned-rpc",
        retry_connection_errors=False,
    )
    try:
        return [
            dict(workflow.attributes or {})
            for workflow in client.list_workflows(
                name=WORKFLOW_NAME,
                application_name="zaratustra-assigned-rpc",
                load_input=False,
                load_output=False,
            )
        ]
    finally:
        client.destroy()


def _managed_copy(root: Path, attempt_id: UUID, content: str) -> Path:
    home = root / ".zara-core" / "pi-rpc-home" / str(attempt_id)
    home.mkdir(parents=True)
    copy = home / "synthetic-managed-copy.txt"
    copy.write_text(content, encoding="utf-8", newline="\n")
    return copy


def _delete_work(root: Path, space_id: UUID, work_id: UUID) -> None:
    owner = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    revision = read_execution(root, work_id, owner).work.revision
    apply_operation(
        root,
        DeleteWorkRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            expected_revision=revision,
        ),
        owner,
    )


def _second_assigned_work(
    root: Path, workspace: Path, space_id: UUID, first: UUID
) -> tuple[UUID, UUID]:
    owner = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    activity_id = read_execution(root, first, owner).activity.activity_id
    work_id, resource_id, attempt_id = uuid4(), uuid4(), uuid4()
    workspace.mkdir()
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            state=WorkState(
                activity_id=activity_id,
                goal="Independent synthetic Work",
                expected_outputs=(OutputContract(slot="summary", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    apply_operation(
        root,
        CreateResourceRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            resource_id=resource_id,
            state=ResourceState(label="Synthetic second resource", root=workspace, limit_units=100),
        ),
        owner,
    )
    apply_operation(
        root,
        AssignAttemptRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            attempt_id=attempt_id,
            session_id=uuid4(),
            resource_id=resource_id,
            expected_work_revision=1,
            expected_resource_revision=1,
            executor_version=EXECUTOR_VERSION,
        ),
        owner,
    )
    return work_id, attempt_id


@pytest.mark.parametrize("grant_mode", ["missing", "revoked"])
def test_denied_maintenance_leaves_dbos_home_backup_and_job_untouched(
    tmp_path: Path, dbos_template: Path, grant_mode: str
) -> None:
    root, _, space_id, work_id, attempt_id, _ = _managed_space(tmp_path, dbos_template)
    owner = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    deliver_outbox(root, owner)
    copy = _managed_copy(root, attempt_id, "Synthetic private payload")
    backup = create_backup(root, uuid4(), owner)
    grant_id = uuid4()
    apply_operation(
        root,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            grant_id=grant_id,
            state=GrantState(
                grantee="observer",
                actions=("space.inspect",)
                if grant_mode == "missing"
                else ("space.inspect", "maintenance.delete"),
            ),
        ),
        owner,
    )
    if grant_mode == "revoked":
        apply_operation(
            root,
            RevokeGrantRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor="owner",
                grant_id=grant_id,
                expected_revision=1,
            ),
            owner,
        )
    observer = authorize_local(root, actor="observer", source_ref="synthetic-observer")
    _delete_work(root, space_id, work_id)
    with pytest.raises(FoundationError, match="permission_denied"):
        complete_assigned_deletions(root, observer)
    assert len(_workflows(root)) == 1
    assert copy.is_file() and backup.package.is_dir()
    assert inspect_space(root, owner).pending_deletions == 1


def test_technical_backup_waits_for_pending_deletion_cleanup(
    tmp_path: Path, dbos_template: Path
) -> None:
    root, _, space_id, work_id, attempt_id, _ = _managed_space(tmp_path, dbos_template)
    owner = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    deliver_outbox(root, owner)
    copy = _managed_copy(root, attempt_id, "Synthetic deleted payload")
    _delete_work(root, space_id, work_id)
    with pytest.raises(FoundationError, match="deletion_pending"):
        create_backup(root, uuid4(), owner)
    inspection = inspect_space(root, owner)
    assert copy.is_file() and inspection.pending_deletions == 1
    assert inspection.completed_backups == 0
    assert complete_assigned_deletions(root, owner).live_store_sanitized
    assert not copy.exists()
    assert create_backup(root, uuid4(), owner).package.is_dir()


def test_later_work_deletion_remains_pending_until_its_own_technical_cleanup(
    tmp_path: Path, dbos_template: Path
) -> None:
    root, _, space_id, first, first_attempt, _ = _managed_space(tmp_path, dbos_template)
    second, second_attempt = _second_assigned_work(
        root, tmp_path / "second-workspace", space_id, first
    )
    owner = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    deliver_outbox(root, owner)
    first_copy = _managed_copy(root, first_attempt, "Synthetic first payload")
    second_copy = _managed_copy(root, second_attempt, "Synthetic second payload")
    _delete_work(root, space_id, first)
    callback_ids: list[UUID] = []

    def interleaved_cleanup(path: Path, authority: LocalAuthority, ids: tuple[UUID, ...]) -> None:
        callback_ids.extend(ids)
        _purge_technical_data(path, authority, ids)
        failures: list[BaseException] = []

        def delete_second() -> None:
            try:
                _delete_work(root, space_id, second)
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=delete_second)
        worker.start()
        worker.join(timeout=10)
        assert not worker.is_alive() and not failures

    first_status = complete_deletions(root, owner, technical_cleanup=interleaved_cleanup)
    assert callback_ids == [first]
    assert first_status.pending_jobs == 1 and first_status.completed_jobs == 1
    assert not first_status.live_store_sanitized
    assert not first_copy.exists() and second_copy.is_file()
    assert [item["work_id"] for item in _workflows(root)] == [str(second)]
    second_status = complete_assigned_deletions(root, owner)
    assert second_status.pending_jobs == 0 and second_status.completed_jobs == 2
    assert second_status.live_store_sanitized
    assert not second_copy.exists() and not _workflows(root)


def test_deleted_partial_of_stopped_assignment_cleans_only_its_addresses(
    tmp_path: Path, dbos_template: Path
) -> None:
    root, workspace, space_id, work_id, attempt_id, session_id = _managed_space(
        tmp_path, dbos_template
    )
    other_work, other_attempt = _second_assigned_work(
        root, tmp_path / "other-workspace", space_id, work_id
    )
    owner = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    deliver_outbox(root, owner)
    rpc = Bridge(
        root, owner, workspace, 100, assigned_attempt_id=attempt_id, assigned_session_id=session_id
    )
    rpc.connect(session_id)
    rpc.select(session_id, read_execution(root, work_id, owner).activity.activity_id, work_id)
    rpc.open_wait(
        session_id, attempt_id, uuid4(), "Synthetic partial payload", "Which code?", "Finish it"
    )
    partial_id = read_execution(root, work_id, owner).waits[0].partial_refs[0].artifact_id
    assignment = read_execution(root, work_id, owner).assignments[0]
    apply_operation(
        root,
        RequestAttemptStopRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            attempt_id=attempt_id,
            session_id=session_id,
            expected_assignment_revision=assignment.revision,
            reason="Synthetic observed stop",
        ),
        owner,
    )
    assignment = read_execution(root, work_id, owner).assignments[0]
    apply_operation(
        root,
        RecordAttemptStopRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            attempt_id=attempt_id,
            session_id=session_id,
            expected_assignment_revision=assignment.revision,
            outcome="stopped",
        ),
        owner,
    )
    deleted_copy = _managed_copy(root, attempt_id, "Synthetic partial payload")
    other_copy = _managed_copy(root, other_attempt, "Unrelated technical payload")
    apply_operation(
        root,
        DeleteArtifactRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            artifact_id=partial_id,
            expected_revision=1,
        ),
        owner,
    )
    assert complete_assigned_deletions(root, owner).live_store_sanitized
    after = read_execution(root, work_id, owner)
    assert after.assignments[0].status == "stopped"
    assert after.assignments[0].stop_reason is None
    assert not after.waits[0].partial_refs and not after.work.unavailable_refs
    assert not deleted_copy.exists() and other_copy.is_file()
    assert [item["work_id"] for item in _workflows(root)] == [str(other_work)]


def test_live_attempt_resolves_past_unrelated_deleted_work(
    tmp_path: Path, dbos_template: Path
) -> None:
    root, _, space_id, live_work, attempt_id, _ = _managed_space(tmp_path, dbos_template)
    owner = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    activity_id = read_execution(root, live_work, owner).activity.activity_id
    deleted_work = UUID(int=1)
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=deleted_work,
            state=WorkState(
                activity_id=activity_id,
                goal="Synthetic deleted history",
                expected_outputs=(OutputContract(slot="summary", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    _delete_work(root, space_id, deleted_work)
    assert resolve_assigned_work(root, owner, attempt_id) == live_work
    deliver_outbox(root, owner)
    assert [item["work_id"] for item in _workflows(root)] == [str(live_work)]
    _delete_work(root, space_id, live_work)
    with pytest.raises(FoundationError, match="stale_attempt"):
        resolve_assigned_work(root, owner, attempt_id)


def test_assigned_refusal_survives_dbos_exception_serialization() -> None:
    original = FoundationError("rpc_extension", "Synthetic local provider is unavailable")
    restored = pickle.loads(pickle.dumps(original))
    assert isinstance(restored, FoundationError)
    assert restored.code == "rpc_extension"
    assert str(restored) == str(original)
