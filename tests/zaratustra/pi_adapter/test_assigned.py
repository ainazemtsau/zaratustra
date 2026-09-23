"""Assigned bridge and managed technical-state boundaries without a model service."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_continuation import ready
from zaratustra.foundation import (
    AssignAttemptRequest,
    DeleteWorkRequest,
    FoundationError,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    managed_pi_lock,
    managed_pi_session_lock,
    read_artifact,
    read_execution,
    restore_backup,
)
from zaratustra.pi_adapter import Bridge
from zaratustra.pi_adapter.assigned import EXECUTOR_VERSION


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
