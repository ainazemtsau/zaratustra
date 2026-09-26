"""Assigned bridge and managed technical-state boundaries without a model service."""

from __future__ import annotations

import io
import json
import pickle
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4, uuid5

import pytest
from dbos import DBOS, DBOSClient

import zaratustra.pi_adapter.assigned as assigned_module
from tests.zaratustra.foundation.test_continuation import ready
from zaratustra.foundation import (
    ALL_ACTIONS,
    AdmitInvocationRequest,
    AssignAttemptRequest,
    ClaimAttemptLaunchRequest,
    CreateGrantRequest,
    CreateResourceRequest,
    CreateWorkRequest,
    DeleteArtifactRequest,
    DeleteWorkRequest,
    FinishInvocationRequest,
    FoundationError,
    GrantState,
    LocalAuthority,
    OutputContract,
    PrepareInvocationRequest,
    RecordAttemptStopRequest,
    RecoverRequest,
    RequestAttemptStopRequest,
    ResourceState,
    RevokeGrantRequest,
    SendInvocationRequest,
    WorkState,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    inspect_space,
    managed_executor_start_lock,
    managed_pi_lock,
    managed_pi_session_lock,
    read_artifact,
    read_assigned_control,
    read_execution,
    restore_backup,
)
from zaratustra.pi_adapter import Bridge
from zaratustra.pi_adapter.assigned import (
    EXECUTOR_VERSION,
    PI_VERSION,
    WORKFLOW_NAME,
    AssignedConfig,
    _purge_technical_data,
    _record_stop,
    _rpc_line_with_stop,
    _terminate_pi,
    _watch_core_stop,
    complete_assigned_deletions,
    create_assigned_backup,
    deliver_outbox,
    resolve_assigned_work,
    run_assigned,
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


def test_executor_start_serializes_processes_without_serializing_sessions(tmp_path: Path) -> None:
    root, _, _, _, _, _ = assigned(tmp_path)
    ready_file = tmp_path / "child-ready"
    script = (
        "from pathlib import Path\n"
        "from zaratustra.foundation import managed_executor_start_lock\n"
        "import sys\n"
        "Path(sys.argv[2]).write_text('ready', encoding='utf-8')\n"
        "with managed_executor_start_lock(Path(sys.argv[1])):\n"
        "    print('acquired', flush=True)\n"
    )
    with managed_pi_session_lock(root), managed_executor_start_lock(root):
        process = subprocess.Popen(
            [sys.executable, "-c", script, str(root), str(ready_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            deadline = time.monotonic() + 10
            while not ready_file.is_file() and time.monotonic() < deadline:
                assert process.poll() is None
                time.sleep(0.01)
            assert ready_file.is_file()
            time.sleep(0.1)
            assert process.poll() is None
        finally:
            if process.poll() is not None:
                process.communicate(timeout=10)
    stdout, stderr = process.communicate(timeout=10)
    assert process.returncode == 0, stderr
    assert stdout.strip() == "acquired"


def test_assigned_launch_delivery_and_backup_share_maintenance_boundary(
    tmp_path: Path, dbos_template: Path
) -> None:
    root, workspace, _, _, attempt_id, _ = _managed_space(tmp_path, dbos_template)
    owner = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    config = AssignedConfig(
        space=root,
        workspace=workspace,
        pi_cli=tmp_path / "unused-pi.js",
        pi_runtime=tmp_path / "unused-runtime",
        node="node",
        provider_profile="local-completions",
        provider_base_url="http://127.0.0.1:9/v1",
        provider_id="synthetic",
        model_id="synthetic",
        context_window=4096,
        max_tokens=512,
        reserve_units=10,
        limit_units=100,
    )
    with managed_pi_lock(root):
        with pytest.raises(FoundationError, match="history_busy"):
            deliver_outbox(root, owner)
        with pytest.raises(FoundationError, match="history_busy"):
            run_assigned(config, owner, attempt_id)
    with managed_pi_session_lock(root):
        with pytest.raises(FoundationError, match="history_busy"):
            create_assigned_backup(root, uuid4(), owner)
    with pytest.raises(FoundationError, match="maintenance_boundary"):
        create_backup(root, uuid4(), owner)
    assert inspect_space(root, owner).completed_backups == 0
    backup = create_assigned_backup(root, uuid4(), owner)
    assert backup.manifest.format_version == 2
    assert backup.manifest.technical_versions is not None
    assert backup.manifest.technical_versions.executor == EXECUTOR_VERSION


def test_dbos_writer_blocks_backup_without_publishing_partial_package(
    tmp_path: Path, dbos_template: Path
) -> None:
    root, _, _, _, attempt_id, _ = _managed_space(tmp_path, dbos_template)
    owner = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    copy = _managed_copy(root, attempt_id, "Synthetic retained data")
    database = root / ".zara-core" / "executor.sqlite3"
    with closing(sqlite3.connect(database, timeout=0.1)) as writer:
        writer.execute("BEGIN IMMEDIATE")
        with pytest.raises(FoundationError) as refused:
            create_assigned_backup(root, uuid4(), owner)
        assert refused.value.code == "maintenance_busy"
        writer.rollback()
    assert copy.read_text(encoding="utf-8") == "Synthetic retained data"
    assert inspect_space(root, owner).completed_backups == 0
    assert create_assigned_backup(root, uuid4(), owner).package.is_dir()


def test_dbos_writer_blocks_deletion_before_technical_payload_is_removed(
    tmp_path: Path, dbos_template: Path
) -> None:
    root, _, space_id, work_id, attempt_id, _ = _managed_space(tmp_path, dbos_template)
    owner = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    deliver_outbox(root, owner)
    copy = _managed_copy(root, attempt_id, "Synthetic retained data")
    _delete_work(root, space_id, work_id)
    database = root / ".zara-core" / "executor.sqlite3"
    with closing(sqlite3.connect(database, timeout=0.1)) as writer:
        writer.execute("BEGIN IMMEDIATE")
        with pytest.raises(FoundationError) as refused:
            complete_assigned_deletions(root, owner)
        assert refused.value.code == "maintenance_busy"
        writer.rollback()
    assert copy.read_text(encoding="utf-8") == "Synthetic retained data"
    assert inspect_space(root, owner).pending_deletions == 1
    assert len(_workflows(root)) == 1
    assert complete_assigned_deletions(root, owner).live_store_sanitized
    assert not copy.exists()


def test_composite_restore_preserves_question_usage_and_unknown(
    tmp_path: Path, dbos_template: Path
) -> None:
    root, workspace, space_id, work_id, attempt_id, session_id = _managed_space(
        tmp_path, dbos_template
    )
    owner = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    invocation_id = uuid4()
    apply_operation(
        root,
        PrepareInvocationRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            purpose="content",
            provider="local",
            model="synthetic",
            transport="http-sse",
            request_sha256="A" * 64,
            request_bytes=12,
            reserve_units=20,
            invocation_id=invocation_id,
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
        ),
        owner,
    )
    apply_operation(
        root,
        AdmitInvocationRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            invocation_id=invocation_id,
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
        ),
        owner,
    )
    apply_operation(
        root,
        SendInvocationRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            invocation_id=invocation_id,
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
        ),
        owner,
    )
    apply_operation(
        root,
        FinishInvocationRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            outcome="answered",
            usage_units=7,
            http_status=200,
            invocation_id=invocation_id,
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
        ),
        owner,
    )
    rpc = Bridge(
        root, owner, workspace, 100, assigned_attempt_id=attempt_id, assigned_session_id=session_id
    )
    rpc.connect(session_id)
    rpc.select(session_id, read_execution(root, work_id, owner).activity.activity_id, work_id)
    rpc.open_wait(session_id, attempt_id, uuid4(), "Synthetic partial", "Which code?", "Add code")
    waiting = read_execution(root, work_id, owner)
    apply_operation(
        root,
        RequestAttemptStopRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            attempt_id=attempt_id,
            session_id=session_id,
            expected_assignment_revision=waiting.assignments[0].revision,
            reason="Synthetic process outcome is uncertain",
        ),
        owner,
    )
    stopped = read_execution(root, work_id, owner)
    apply_operation(
        root,
        RecordAttemptStopRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            attempt_id=attempt_id,
            session_id=session_id,
            expected_assignment_revision=stopped.assignments[0].revision,
            outcome="unknown",
        ),
        owner,
    )
    backup = create_assigned_backup(root, uuid4(), owner)
    destination = tmp_path / "restored"
    destination.mkdir()
    recovery = authorize_recovery(actor="owner", source_ref="synthetic-recovery")
    restored = restore_backup(backup.package, destination, recovery)
    assert restored.recovery_state == "quarantined" and restored.execution_epoch == 2
    with pytest.raises(FoundationError, match="permission_denied"):
        read_execution(destination, work_id, owner)
    apply_operation(
        destination,
        RecoverRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        recovery,
    )
    new_owner = authorize_local(destination, actor="owner", source_ref="synthetic-new-epoch")
    snapshot = read_execution(destination, work_id, new_owner)
    assert snapshot.assignments[0].status == "unknown"
    assert snapshot.waits[0].question == "Which code?"
    assert snapshot.waits[0].remainder == "Add code"
    assert snapshot.committed_units == 7 and snapshot.held_units == 0
    assert snapshot.invocations[0].status == "answered"
    assert not (destination / ".zara-core" / "executor.sqlite3").exists()
    assert (destination / ".zara-core" / "executor-restored.sqlite3").is_file()
    resource = snapshot.resources[0]
    with pytest.raises(FoundationError, match="resource_busy"):
        apply_operation(
            destination,
            AssignAttemptRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor="owner",
                attempt_id=uuid4(),
                work_id=work_id,
                expected_work_revision=snapshot.work.revision,
                resource_id=resource.resource_id,
                expected_resource_revision=resource.revision,
                session_id=uuid4(),
                previous_attempt_id=attempt_id,
                executor_version=EXECUTOR_VERSION,
            ),
            new_owner,
        )


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
    backup = create_assigned_backup(root, uuid4(), authority)
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


def _pending_local_route(root: Path, work_id: UUID, attempt_id: UUID, owner: LocalAuthority) -> str:
    """Create the predecessor's addressed PENDING/local DBOS record without SQL edits."""

    entry = read_execution(root, work_id, owner).outbox[0]
    database = root / ".zara-core" / "executor.sqlite3"
    workflow_id = f"zara-{uuid5(attempt_id, 'launch')}"
    route = f"zara-assigned-rpc-{attempt_id}"
    source = """
import os
import sys
import time
from dbos import DBOS, DBOSClient

url, version, route, workflow_id, work_id, attempt_id, outbox_id, epoch, generation = sys.argv[1:]
DBOS(config={"name": "zaratustra-assigned-rpc", "system_database_url": url,
             "application_version": version, "executor_id": "local"})
@DBOS.workflow(name="zara-assigned-work-v1")
def crash_before_claim(*_args):
    os._exit(90)
DBOS.listen_queues([route])
DBOS.launch()
DBOS.register_queue(route, worker_concurrency=1)
client = DBOSClient(system_database_url=url, application_name="zaratustra-assigned-rpc",
                    retry_connection_errors=False)
client.enqueue({"workflow_name": "zara-assigned-work-v1", "queue_name": route,
                "workflow_id": workflow_id, "app_version": version,
                "deduplication_id": outbox_id, "duplication_policy": "return-existing",
                "attributes": {"work_id": work_id, "attempt_id": attempt_id}},
               work_id, attempt_id, int(epoch), int(generation))
client.destroy()
time.sleep(20)
raise SystemExit(1)
"""
    created = subprocess.run(
        [
            sys.executable,
            "-c",
            source,
            f"sqlite:///{database.resolve().as_posix()}",
            f"{EXECUTOR_VERSION}-{attempt_id}",
            route,
            workflow_id,
            str(work_id),
            str(attempt_id),
            str(entry.outbox_id),
            str(entry.execution_epoch),
            str(entry.generation),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert created.returncode == 90, created.stderr
    client = DBOSClient(
        system_database_url=f"sqlite:///{database.resolve().as_posix()}",
        application_name="zaratustra-assigned-rpc",
        retry_connection_errors=False,
    )
    try:
        records = client.list_workflows(workflow_ids=[workflow_id], load_output=False)
        assert len(records) == 1
        assert records[0].status == "PENDING" and records[0].executor_id == "local"
        assert records[0].queue_name == route
    finally:
        client.destroy()
    return workflow_id


def _valid_assigned_config(root: Path, workspace: Path, runtime: Path) -> AssignedConfig:
    package = runtime / "node_modules" / "@earendil-works" / "pi-coding-agent"
    cli = package / "dist" / "bundle" / "cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("synthetic", encoding="utf-8")
    (package / "package.json").write_text(
        '{"name":"@earendil-works/pi-coding-agent","version":"' + PI_VERSION + '"}',
        encoding="utf-8",
    )
    return AssignedConfig(
        space=root,
        workspace=workspace,
        pi_cli=cli,
        pi_runtime=runtime,
        node="node",
        provider_profile="local-completions",
        provider_base_url="http://127.0.0.1:9/v1",
        provider_id="synthetic",
        model_id="synthetic",
        context_window=4096,
        max_tokens=512,
        reserve_units=10,
        limit_units=100,
        offline=True,
    )


@pytest.mark.parametrize("claimed", [False, True])
def test_pending_local_addressed_workflow_recovers_at_core_claim_boundary(
    tmp_path: Path,
    dbos_template: Path,
    monkeypatch: pytest.MonkeyPatch,
    claimed: bool,
) -> None:
    root, workspace, space_id, work_id, attempt_id, session_id = _managed_space(
        tmp_path, dbos_template
    )
    owner = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    workflow_id = _pending_local_route(root, work_id, attempt_id, owner)
    config = _valid_assigned_config(root, workspace, tmp_path / "runtime")
    executed: list[UUID] = []
    if claimed:
        assignment = read_execution(root, work_id, owner).assignments[0]
        apply_operation(
            root,
            ClaimAttemptLaunchRequest(
                operation_id=uuid5(attempt_id, "rpc-launch-claim"),
                space_id=space_id,
                actor="owner",
                attempt_id=attempt_id,
                work_id=work_id,
                session_id=session_id,
                expected_assignment_revision=assignment.revision,
                claim_nonce=uuid4(),
            ),
            owner,
        )

        def no_pi(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("A recorded claim must not launch Pi again")

        monkeypatch.setattr(assigned_module, "BridgeServer", no_pi)
        with pytest.raises(FoundationError) as refused:
            run_assigned(config, owner, attempt_id)
        assert refused.value.code == "process_outcome_unknown"
        state = read_execution(root, work_id, owner)
        assert state.assignments[0].status == "unknown" and state.outputs == ()
        assert state.invocations == () and executed == []
        with pytest.raises(FoundationError) as replay:
            run_assigned(config, owner, attempt_id)
        assert replay.value.code == "process_outcome_unknown"
        assert read_execution(root, work_id, owner).assignments[0].status == "unknown"
    else:

        def execute(
            selected: AssignedConfig,
            _authority: LocalAuthority,
            selected_work: UUID,
            selected_attempt: UUID,
            _epoch: int,
            _generation: int,
        ) -> str:
            assert selected.workspace == workspace.resolve()
            assert selected_work == work_id and selected_attempt == attempt_id
            executed.append(selected_attempt)
            return "proposed"

        monkeypatch.setattr(assigned_module, "_execute", execute)
        assert run_assigned(config, owner, attempt_id) == "proposed"
        assert run_assigned(config, owner, attempt_id) == "proposed"
        assert executed == [attempt_id]
        assert deliver_outbox(root, owner) == (
            read_execution(root, work_id, owner).outbox[0].outbox_id,
        )

    client = DBOSClient(
        system_database_url=(
            f"sqlite:///{(root / '.zara-core' / 'executor.sqlite3').resolve().as_posix()}"
        ),
        application_name="zaratustra-assigned-rpc",
        retry_connection_errors=False,
    )
    try:
        records = client.list_workflows(workflow_ids=[workflow_id], load_output=True)
        assert len(records) == 1 and records[0].workflow_id == workflow_id
        assert records[0].executor_id == str(attempt_id)
        assert records[0].status == ("ERROR" if claimed else "SUCCESS")
        assert len(client.list_workflows(load_output=False)) == 1
    finally:
        client.destroy()


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
    backup = create_assigned_backup(root, uuid4(), owner)
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
        create_assigned_backup(root, uuid4(), owner)
    inspection = inspect_space(root, owner)
    assert copy.is_file() and inspection.pending_deletions == 1
    assert inspection.completed_backups == 0
    assert complete_assigned_deletions(root, owner).live_store_sanitized
    assert not copy.exists()
    assert create_assigned_backup(root, uuid4(), owner).package.is_dir()


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


def test_launch_claim_is_exact_and_rejects_a_second_process(tmp_path: Path) -> None:
    root, _, space_id, work_id, attempt_id, session_id = assigned(tmp_path)
    owner = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    claim_id = uuid5(attempt_id, "rpc-launch-claim")
    first = ClaimAttemptLaunchRequest(
        operation_id=claim_id,
        space_id=space_id,
        actor="owner",
        attempt_id=attempt_id,
        work_id=work_id,
        session_id=session_id,
        expected_assignment_revision=1,
        claim_nonce=uuid4(),
    )
    receipt = apply_operation(root, first, owner)
    assert receipt.result["launch_claimed"] is True
    assert apply_operation(root, first, owner) == receipt
    with pytest.raises(FoundationError, match="operation_conflict"):
        apply_operation(root, first.model_copy(update={"claim_nonce": uuid4()}), owner)
    snapshot = read_execution(root, work_id, owner)
    assert snapshot.assignments[0].status == "assigned"
    assert snapshot.attempts[0].status == "active"


def test_incompatible_pi_package_refuses_before_dbos_launch(tmp_path: Path) -> None:
    root, workspace, _, work_id, attempt_id, _ = assigned(tmp_path)
    owner = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    runtime = tmp_path / "runtime"
    package = runtime / "node_modules" / "@earendil-works" / "pi-coding-agent"
    cli = package / "dist" / "bundle" / "cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("synthetic", encoding="utf-8")
    (package / "package.json").write_text(
        '{"name":"@earendil-works/pi-coding-agent","version":"0.88.0"}',
        encoding="utf-8",
    )
    config = AssignedConfig(
        space=root,
        workspace=workspace,
        pi_cli=cli,
        pi_runtime=runtime,
        node="node",
        provider_profile="local-completions",
        provider_base_url="http://127.0.0.1:9/v1",
        provider_id="synthetic",
        model_id="synthetic",
        context_window=4096,
        max_tokens=512,
        reserve_units=10,
        limit_units=100,
        offline=True,
    )
    with pytest.raises(FoundationError, match="pi_version"):
        run_assigned(config, owner, attempt_id)
    assert not (root / ".zara-core" / "executor.sqlite3").exists()
    assert read_execution(root, work_id, owner).assignments[0].status == "assigned"


def test_refused_child_termination_records_unknown(tmp_path: Path) -> None:
    root, workspace, _, work_id, attempt_id, session_id = assigned(tmp_path)
    owner = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    config = AssignedConfig(
        space=root,
        workspace=workspace,
        pi_cli=tmp_path / "unused-pi.js",
        pi_runtime=tmp_path / "unused-runtime",
        node="node",
        provider_profile="local-completions",
        provider_base_url="http://127.0.0.1:9/v1",
        provider_id="synthetic",
        model_id="synthetic",
        context_window=4096,
        max_tokens=512,
        reserve_units=10,
        limit_units=100,
    )

    class RefusingChild:
        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            raise OSError("synthetic termination refusal")

        def kill(self) -> None:
            raise OSError("synthetic kill refusal")

        def wait(self, *, timeout: float) -> None:
            raise subprocess.TimeoutExpired("synthetic-pi", timeout)

    observed = _terminate_pi(cast(subprocess.Popen[bytes], RefusingChild()))
    assert not observed
    _record_stop(config, owner, work_id, attempt_id, session_id, observed=observed)
    state = read_execution(root, work_id, owner)
    assert state.assignments[0].status == "unknown"
    assert state.attempts[0].status == "active"
    assert state.work.state.status == "proposed"


def test_active_rpc_read_is_interruptible_when_stop_is_requested() -> None:
    release = threading.Event()

    class SilentOutput:
        def readline(self, _limit: int) -> bytes:
            release.wait()
            return b""

    class SilentChild:
        stdout = SilentOutput()

    stop = threading.Event()
    stop.set()
    try:
        with pytest.raises(FoundationError, match="rpc_stop_requested"):
            _rpc_line_with_stop(cast(subprocess.Popen[bytes], SilentChild()), stop)
    finally:
        release.set()


def test_control_read_follows_stop_and_current_runner_rights(tmp_path: Path) -> None:
    root, _, space_id, work_id, attempt_id, session_id = assigned(tmp_path)
    owner = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    grant_id = uuid4()
    apply_operation(
        root,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            grant_id=grant_id,
            state=GrantState(grantee="runner", actions=tuple(ALL_ACTIONS)),
        ),
        owner,
    )
    runner = authorize_local(root, actor="runner", source_ref="synthetic-runner")
    assert read_assigned_control(root, work_id, attempt_id, runner)
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
    with pytest.raises(FoundationError, match="permission_denied"):
        read_assigned_control(root, work_id, attempt_id, runner)
    assert read_assigned_control(root, work_id, attempt_id, owner)
    apply_operation(
        root,
        RequestAttemptStopRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
            expected_assignment_revision=1,
            reason="Stop this fictional assigned child",
        ),
        owner,
    )
    assert not read_assigned_control(root, work_id, attempt_id, owner)


def test_stop_monitor_terminates_before_failed_dbos_wake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, workspace, space_id, work_id, attempt_id, session_id = assigned(tmp_path)
    owner = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    apply_operation(
        root,
        RequestAttemptStopRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
            expected_assignment_revision=1,
            reason="Stop this fictional child before a failed technical wake",
        ),
        owner,
    )
    config = AssignedConfig(
        space=root,
        workspace=workspace,
        pi_cli=tmp_path / "unused-pi.js",
        pi_runtime=tmp_path / "unused-runtime",
        node="node",
        provider_profile="local-completions",
        provider_base_url="http://127.0.0.1:9/v1",
        provider_id="synthetic",
        model_id="synthetic",
        context_window=4096,
        max_tokens=512,
        reserve_units=10,
        limit_units=100,
    )

    class Child:
        def __init__(self) -> None:
            self.stdin = io.BytesIO()
            self.terminated = False

        def poll(self) -> int | None:
            return 1 if self.terminated else None

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.terminated = True

        def wait(self, *, timeout: float) -> int:
            assert self.terminated
            return 1

    child = Child()

    class FailedWake:
        def __init__(self) -> None:
            self.called = False
            self.destroyed = False

        def send(self, *args: object, **kwargs: object) -> None:
            assert child.terminated
            self.called = True
            raise OSError("synthetic DBOS wake failure")

        def destroy(self) -> None:
            self.destroyed = True

    wake = FailedWake()
    monkeypatch.setattr("zaratustra.pi_adapter.assigned._client", lambda _space: wake)
    stop = threading.Event()
    _watch_core_stop(
        config,
        owner,
        work_id,
        attempt_id,
        cast(subprocess.Popen[bytes], child),
        threading.Event(),
        stop,
        threading.Lock(),
    )
    commands = [json.loads(raw)["type"] for raw in child.stdin.getvalue().splitlines()]
    assert stop.is_set() and child.terminated
    assert commands == ["clear_queue", "abort"]
    assert wake.called and wake.destroyed
