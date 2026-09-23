"""Model-free durable assignment, answer, recovery and deletion behavior."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from zaratustra.foundation import (
    AcceptWorkRequest,
    ActivityState,
    AdmitInvocationRequest,
    AnswerWaitRequest,
    ArtifactRef,
    AssignAttemptRequest,
    BootstrapRequest,
    CreateActivityRequest,
    CreateArtifactRequest,
    CreateGrantRequest,
    CreateResourceRequest,
    CreateWorkRequest,
    DeleteArtifactRequest,
    DeleteWorkRequest,
    FoundationError,
    GrantState,
    LinkedOutput,
    LinkWorkOutputRequest,
    OpenWaitRequest,
    OutputContract,
    PrepareInvocationRequest,
    RecordAttemptStopRequest,
    RecoverRequest,
    RequestAttemptStopRequest,
    ResourceState,
    RevokeGrantRequest,
    SendInvocationRequest,
    StopAttemptRequest,
    WorkState,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    initialize_space,
    inspect_recovery,
    read_execution,
    read_receipt,
    read_space,
    read_work,
    restore_backup,
    upgrade_continuation_space,
    upgrade_execution_space,
    upgrade_space,
)
from zaratustra.pi_adapter import Bridge


def ready(tmp_path: Path, *, upgrade: bool = True) -> tuple[Path, Path, UUID, UUID, UUID, UUID]:
    root = tmp_path / "space"
    root.mkdir()
    workspace = tmp_path / "fictional-workspace"
    workspace.mkdir()
    info = initialize_space(root)
    owner = authorize_local(root, actor="owner", source_ref="trusted-fictional-console")
    apply_operation(
        root,
        BootstrapRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        owner,
    )
    assert upgrade_space(root, owner).schema_version == 2
    assert upgrade_execution_space(root, owner).schema_version == 3
    artifact_id, activity_id, work_id, resource_id = (uuid4() for _ in range(4))
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="owner",
            artifact_id=artifact_id,
            media_type="text/plain",
            content=b"fictional input",
        ),
        owner,
    )
    apply_operation(
        root,
        CreateActivityRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="owner",
            activity_id=activity_id,
            state=ActivityState(title="Fictional activity", goal="Continue safely"),
        ),
        owner,
    )
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="owner",
            work_id=work_id,
            state=WorkState(
                activity_id=activity_id,
                goal="Summarize fictional material",
                inputs=(ArtifactRef(artifact_id=artifact_id, revision=1),),
                expected_outputs=(OutputContract(slot="summary", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    apply_operation(
        root,
        CreateResourceRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="owner",
            resource_id=resource_id,
            work_id=work_id,
            state=ResourceState(label="Fictional directory", root=workspace, limit_units=100),
        ),
        owner,
    )
    if upgrade:
        assert upgrade_continuation_space(root, owner).schema_version == 4
    return root, workspace, info.space_id, artifact_id, work_id, resource_id


def assign(
    root: Path,
    space_id: UUID,
    work_id: UUID,
    resource_id: UUID,
    *,
    previous: UUID | None = None,
) -> tuple[UUID, UUID, AssignAttemptRequest]:
    attempt_id, session_id = uuid4(), uuid4()
    request = AssignAttemptRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        attempt_id=attempt_id,
        work_id=work_id,
        expected_work_revision=1,
        resource_id=resource_id,
        expected_resource_revision=1,
        session_id=session_id,
        previous_attempt_id=previous,
        executor_version="synthetic-pi-rpc-contract-1",
    )
    apply_operation(
        root, request, authorize_local(root, actor="owner", source_ref="trusted-fictional-console")
    )
    return attempt_id, session_id, request


def ask(
    root: Path,
    space_id: UUID,
    artifact_id: UUID,
    work_id: UUID,
    attempt_id: UUID,
    session_id: UUID,
    *,
    expected_actor: str = "owner",
) -> OpenWaitRequest:
    request = OpenWaitRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        wait_id=uuid4(),
        attempt_id=attempt_id,
        work_id=work_id,
        session_id=session_id,
        expected_assignment_revision=1,
        question="Which fictional code should be used?",
        expected_actor=expected_actor,
        remainder="Keep the fictional summary open until the code is chosen.",
        partial_refs=(ArtifactRef(artifact_id=artifact_id, revision=1),),
    )
    apply_operation(
        root, request, authorize_local(root, actor="owner", source_ref="trusted-fictional-console")
    )
    return request


def test_upgrade_is_explicit_and_stage4_remains_available(tmp_path: Path) -> None:
    root, workspace, space_id, _, work_id, resource_id = ready(tmp_path, upgrade=False)
    owner = authorize_local(root, actor="owner", source_ref="trusted-fictional-console")
    before = read_execution(root, work_id, owner)
    assert read_space(root).schema_version == 3
    attempt_id, session_id = uuid4(), uuid4()
    assignment = AssignAttemptRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        attempt_id=attempt_id,
        work_id=work_id,
        expected_work_revision=1,
        resource_id=resource_id,
        expected_resource_revision=1,
        session_id=session_id,
        executor_version="synthetic-contract-1",
    )
    with pytest.raises(FoundationError, match="schema"):
        apply_operation(root, assignment, owner)
    assert read_space(root).schema_version == 3
    assert upgrade_continuation_space(root, owner).schema_version == 4
    after = read_execution(root, work_id, owner)
    assert after.work == before.work and after.attempts == before.attempts
    assert after.assignments == () and after.waits == () and after.outbox == ()
    bridge = Bridge(root, owner, workspace, 100)
    assert bridge.connect(session_id)["space_id"] == str(space_id)
    bridge.select(session_id, before.activity.activity_id, work_id)
    started = bridge.start_attempt(session_id, interrupt_previous=False)
    attempt_id = UUID(str(started["attempt_id"]))
    apply_operation(
        root,
        StopAttemptRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
            outcome="interrupted",
        ),
        owner,
    )


def test_reopen_answer_once_stop_unknown_and_fence_old_attempt(tmp_path: Path) -> None:
    root, _, space_id, artifact_id, work_id, resource_id = ready(tmp_path)
    attempt_id, session_id, assignment = assign(root, space_id, work_id, resource_id)
    owner = authorize_local(root, actor="owner", source_ref="trusted-fictional-console")
    assert apply_operation(root, assignment, owner).operation_id == assignment.operation_id
    wait_request = ask(root, space_id, artifact_id, work_id, attempt_id, session_id)
    assert apply_operation(root, wait_request, owner).operation_id == wait_request.operation_id
    before = read_execution(root, work_id, owner)
    assert before.work.state.status == "proposed"
    assert before.assignments[0].status == "waiting"
    assert before.waits[0].remainder == wait_request.remainder
    assert [item.kind for item in before.outbox] == ["launch"]

    child = """
import json, sys
from pathlib import Path
from uuid import UUID, uuid4
from zaratustra.foundation import (
    AnswerWaitRequest, apply_operation, authorize_local, read_execution,
)
root = Path(sys.argv[1])
space_id, work_id, attempt_id, session_id = map(UUID, sys.argv[2:6])
authority = authorize_local(root, actor="owner", source_ref="fresh-fictional-console")
wait = read_execution(root, work_id, authority).waits[0]
assert wait.remainder == "Keep the fictional summary open until the code is chosen."
request = AnswerWaitRequest(
    operation_id=uuid4(), space_id=space_id, actor="owner",
    wait_id=wait.wait_id, attempt_id=attempt_id, work_id=work_id,
    session_id=session_id, expected_wait_revision=wait.revision,
    answer="Use fictional code A")
receipt = apply_operation(root, request, authority)
assert apply_operation(root, request, authority) == receipt
print(json.dumps({"wait": str(wait.wait_id), "operation": str(receipt.operation_id)}))
"""
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            child,
            str(root),
            str(space_id),
            str(work_id),
            str(attempt_id),
            str(session_id),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    evidence = json.loads(process.stdout)
    after = read_execution(root, work_id, owner)
    assert evidence["wait"] == str(wait_request.wait_id)
    assert read_receipt(root, UUID(evidence["operation"]), owner).kind == "answer_wait"
    assert after.waits[0].answer == "Use fictional code A"
    assert after.waits[0].answer_source == "fresh-fictional-console"
    assert after.assignments[0].status == "ready"
    assert [item.kind for item in after.outbox] == ["launch", "resume"]
    with pytest.raises(FoundationError):
        apply_operation(
            root,
            AnswerWaitRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor="owner",
                wait_id=wait_request.wait_id,
                attempt_id=attempt_id,
                work_id=work_id,
                session_id=session_id,
                expected_wait_revision=1,
                answer="Duplicate fictional answer",
            ),
            owner,
        )
    assert len(read_execution(root, work_id, owner).outbox) == 2

    apply_operation(
        root,
        RequestAttemptStopRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
            expected_assignment_revision=3,
            reason="Synthetic stop request",
        ),
        owner,
    )
    apply_operation(
        root,
        RecordAttemptStopRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
            expected_assignment_revision=4,
            outcome="unknown",
        ),
        owner,
    )
    unknown = read_execution(root, work_id, owner)
    assert unknown.assignments[0].status == "unknown"
    assert all(item.status == "cancelled" for item in unknown.outbox)
    with pytest.raises(FoundationError):
        assign(root, space_id, work_id, resource_id, previous=attempt_id)
    apply_operation(
        root,
        RecordAttemptStopRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
            expected_assignment_revision=5,
            outcome="stopped",
        ),
        owner,
    )
    new_attempt, _, _ = assign(root, space_id, work_id, resource_id, previous=attempt_id)
    assert new_attempt != attempt_id
    with pytest.raises(FoundationError):
        apply_operation(
            root,
            OpenWaitRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor="owner",
                wait_id=uuid4(),
                attempt_id=attempt_id,
                work_id=work_id,
                session_id=session_id,
                expected_assignment_revision=6,
                question="Late fictional question",
                expected_actor="owner",
                remainder="Do not continue old Attempt",
            ),
            owner,
        )
    assert len(read_execution(root, work_id, owner).outbox) == 3


def test_answer_requires_replay_right_and_exact_retry_is_one_continuation(tmp_path: Path) -> None:
    root, _, space_id, artifact_id, work_id, resource_id = ready(tmp_path)
    owner = authorize_local(root, actor="owner", source_ref="trusted-fictional-console")
    apply_operation(
        root,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            grant_id=uuid4(),
            state=GrantState(grantee="responder", actions=("record.read", "work.write")),
        ),
        owner,
    )
    attempt_id, session_id, _ = assign(root, space_id, work_id, resource_id)
    question = ask(
        root,
        space_id,
        artifact_id,
        work_id,
        attempt_id,
        session_id,
        expected_actor="responder",
    )
    responder = authorize_local(root, actor="responder", source_ref="fictional-responder")
    answer = AnswerWaitRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="responder",
        wait_id=question.wait_id,
        attempt_id=attempt_id,
        work_id=work_id,
        session_id=session_id,
        expected_wait_revision=1,
        answer="Fictional reply",
    )
    with pytest.raises(FoundationError, match="receipt.read"):
        apply_operation(root, answer, responder)
    assert read_execution(root, work_id, owner).waits[0].status == "open"
    apply_operation(
        root,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            grant_id=uuid4(),
            state=GrantState(grantee="responder", actions=("receipt.read",)),
        ),
        owner,
    )
    first = apply_operation(root, answer, responder)
    retry_authority = authorize_local(root, actor="responder", source_ref="reopened-responder")
    assert apply_operation(root, answer, retry_authority) == first
    after = read_execution(root, work_id, owner)
    assert after.waits[0].answer_source == "fictional-responder"
    assert [item.kind for item in after.outbox] == ["launch", "resume"]


def test_revoked_answer_right_does_not_create_continuation(tmp_path: Path) -> None:
    root, _, space_id, artifact_id, work_id, resource_id = ready(tmp_path)
    owner = authorize_local(root, actor="owner", source_ref="trusted-fictional-console")
    grant_id = uuid4()
    apply_operation(
        root,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            grant_id=grant_id,
            state=GrantState(grantee="responder", actions=("record.read", "work.write")),
        ),
        owner,
    )
    attempt_id, session_id, _ = assign(root, space_id, work_id, resource_id)
    question = ask(
        root,
        space_id,
        artifact_id,
        work_id,
        attempt_id,
        session_id,
        expected_actor="responder",
    )
    responder = authorize_local(root, actor="responder", source_ref="synthetic-responder")
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
    with pytest.raises(FoundationError, match="Grant"):
        apply_operation(
            root,
            AnswerWaitRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor="responder",
                wait_id=question.wait_id,
                attempt_id=attempt_id,
                work_id=work_id,
                session_id=session_id,
                expected_wait_revision=1,
                answer="An answer without a current right",
            ),
            responder,
        )
    current = read_execution(root, work_id, owner)
    assert current.waits[0].status == "open" and current.waits[0].answer is None
    assert [item.kind for item in current.outbox] == ["launch"]


def test_stop_closes_admission_and_preserves_uncertain_reserve(tmp_path: Path) -> None:
    root, _, space_id, _, work_id, resource_id = ready(tmp_path)
    owner = authorize_local(root, actor="owner", source_ref="trusted-fictional-console")
    attempt_id, session_id, _ = assign(root, space_id, work_id, resource_id)
    invocation_id = uuid4()
    apply_operation(
        root,
        PrepareInvocationRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            invocation_id=invocation_id,
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
            purpose="content",
            provider="synthetic",
            model="fixture",
            transport="http-sse",
            request_sha256="A" * 64,
            request_bytes=10,
            reserve_units=20,
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
        RequestAttemptStopRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
            expected_assignment_revision=1,
            reason="Synthetic stop before send",
        ),
        owner,
    )
    with pytest.raises(FoundationError, match="cannot send"):
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
        RecordAttemptStopRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
            expected_assignment_revision=2,
            outcome="unknown",
        ),
        owner,
    )
    unknown = read_execution(root, work_id, owner)
    assert unknown.held_units == 20 and unknown.invocations[0].status == "admitted"
    apply_operation(
        root,
        RecordAttemptStopRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
            expected_assignment_revision=3,
            outcome="stopped",
        ),
        owner,
    )
    stopped = read_execution(root, work_id, owner)
    assert stopped.held_units == 20 and stopped.invocations[0].status == "unknown"
    assert stopped.attempts[0].status == "interrupted"


def test_backup_quarantine_epoch_and_managed_deletion(tmp_path: Path) -> None:
    root, _, space_id, artifact_id, work_id, resource_id = ready(tmp_path)
    owner = authorize_local(root, actor="owner", source_ref="trusted-fictional-console")
    attempt_id, session_id, _ = assign(root, space_id, work_id, resource_id)
    question = ask(root, space_id, artifact_id, work_id, attempt_id, session_id)
    apply_operation(
        root,
        AnswerWaitRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            wait_id=question.wait_id,
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
            expected_wait_revision=1,
            answer="Fictional recovery answer",
        ),
        owner,
    )
    backup = create_backup(root, uuid4(), owner)
    destination = tmp_path / "restored"
    destination.mkdir()
    recovery = authorize_recovery(actor="owner", source_ref="fresh-recovery-console")
    restored = restore_backup(backup.package, destination, recovery)
    assert restored.schema_version == 4 and restored.recovery_state == "quarantined"
    assert restored.execution_epoch == 2
    assert inspect_recovery(destination, recovery)["schema_version"] == 4
    with pytest.raises(FoundationError):
        authorize_local(destination, actor="owner", source_ref="old-console")
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
    restored_owner = authorize_local(
        destination, actor="owner", source_ref="fresh-recovery-console"
    )
    resumed = read_execution(destination, work_id, restored_owner)
    assert resumed.waits[0].question == question.question
    assert resumed.waits[0].remainder == question.remainder
    assert resumed.waits[0].answer == "Fictional recovery answer"
    assert resumed.assignments[0].status == "interrupted"
    assert all(item.status == "cancelled" for item in resumed.outbox)
    with pytest.raises(FoundationError):
        apply_operation(
            destination,
            AnswerWaitRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor="owner",
                wait_id=question.wait_id,
                attempt_id=attempt_id,
                work_id=work_id,
                session_id=session_id,
                expected_wait_revision=1,
                answer="Cannot revive the old epoch",
            ),
            restored_owner,
        )

    apply_operation(
        root,
        DeleteWorkRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            expected_revision=1,
        ),
        owner,
    )
    deletion = complete_deletions(root, owner)
    assert deletion.live_store_sanitized and deletion.purged_backups == 1
    assert not backup.package.exists()
    with pytest.raises(FoundationError):
        read_execution(root, work_id, owner)
    database = root / ".zara-core" / "core.sqlite3"
    assert question.question.encode("utf-8") not in database.read_bytes()
    assert question.remainder.encode("utf-8") not in database.read_bytes()
    assert b"Fictional recovery answer" not in database.read_bytes()


def test_artifact_deletion_purges_dependent_wait_content(tmp_path: Path) -> None:
    root, _, space_id, artifact_id, work_id, resource_id = ready(tmp_path)
    owner = authorize_local(root, actor="owner", source_ref="trusted-fictional-console")
    attempt_id, session_id, _ = assign(root, space_id, work_id, resource_id)
    question = ask(root, space_id, artifact_id, work_id, attempt_id, session_id)
    apply_operation(
        root,
        DeleteArtifactRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            artifact_id=artifact_id,
            expected_revision=1,
        ),
        owner,
    )
    current = read_execution(root, work_id, owner)
    assert current.waits[0].status == "purged"
    assert current.waits[0].question is None and current.waits[0].remainder is None
    assert current.assignments[0].status == "interrupted"
    assert all(item.status == "cancelled" for item in current.outbox)
    with pytest.raises(FoundationError):
        read_receipt(root, question.operation_id, owner)
    assert complete_deletions(root, owner).live_store_sanitized
    database = root / ".zara-core" / "core.sqlite3"
    assert question.question.encode("utf-8") not in database.read_bytes()
    assert question.remainder.encode("utf-8") not in database.read_bytes()


@pytest.mark.parametrize("terminal_status", ["stopped", "interrupted"])
def test_artifact_deletion_purges_terminal_stop_reason_and_backups(
    tmp_path: Path, terminal_status: str
) -> None:
    root, _, space_id, artifact_id, work_id, resource_id = ready(tmp_path)
    owner = authorize_local(root, actor="owner", source_ref="trusted-fictional-console")
    attempt_id, session_id, _ = assign(root, space_id, work_id, resource_id)
    question = ask(root, space_id, artifact_id, work_id, attempt_id, session_id)
    reason = "Fictional stop refers to fictional input only"
    stop_request = RequestAttemptStopRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        attempt_id=attempt_id,
        work_id=work_id,
        session_id=session_id,
        expected_assignment_revision=2,
        reason=reason,
    )
    apply_operation(root, stop_request, owner)
    if terminal_status == "stopped":
        apply_operation(
            root,
            RecordAttemptStopRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor="owner",
                attempt_id=attempt_id,
                work_id=work_id,
                session_id=session_id,
                expected_assignment_revision=3,
                outcome="stopped",
            ),
            owner,
        )
    else:
        source_backup = create_backup(root, uuid4(), owner)
        restored_root = tmp_path / "restored"
        restored_root.mkdir()
        recovery = authorize_recovery(actor="owner", source_ref="fresh-recovery-console")
        restore_backup(source_backup.package, restored_root, recovery)
        apply_operation(
            restored_root,
            RecoverRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor="owner",
                decision_id=uuid4(),
                grant_id=uuid4(),
            ),
            recovery,
        )
        root = restored_root
        owner = authorize_local(root, actor="owner", source_ref="fresh-recovery-console")
    assert read_execution(root, work_id, owner).assignments[0].status == terminal_status
    assert read_execution(root, work_id, owner).assignments[0].stop_reason == reason
    affected_backup = create_backup(root, uuid4(), owner)
    apply_operation(
        root,
        DeleteArtifactRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            artifact_id=artifact_id,
            expected_revision=1,
        ),
        owner,
    )
    current = read_execution(root, work_id, owner)
    assert current.assignments[0].status == terminal_status
    assert current.assignments[0].stop_reason is None
    assert current.waits[0].status == "purged" and current.waits[0].question is None
    with pytest.raises(FoundationError):
        read_receipt(root, stop_request.operation_id, owner)
    with pytest.raises(FoundationError, match="history_unavailable"):
        apply_operation(root, stop_request, owner)
    deletion = complete_deletions(root, owner)
    assert deletion.live_store_sanitized and deletion.purged_backups >= 1
    assert not affected_backup.package.exists()
    database = root / ".zara-core" / "core.sqlite3"
    assert reason.encode("utf-8") not in database.read_bytes()
    assert question.question.encode("utf-8") not in database.read_bytes()


def test_accept_work_keeps_unknown_assignment_until_stopped(tmp_path: Path) -> None:
    root, workspace, space_id, artifact_id, work_id, resource_id = ready(tmp_path)
    owner = authorize_local(root, actor="owner", source_ref="trusted-fictional-console")
    attempt_id, session_id, _ = assign(root, space_id, work_id, resource_id)
    output_id = uuid4()
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            artifact_id=output_id,
            media_type="text/plain",
            content=b"Reviewed fictional output",
        ),
        owner,
    )
    apply_operation(
        root,
        LinkWorkOutputRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            expected_revision=1,
            output=LinkedOutput(
                slot="summary", artifact=ArtifactRef(artifact_id=output_id, revision=1)
            ),
        ),
        owner,
    )
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
            reason="Fictional process outcome pending",
        ),
        owner,
    )
    apply_operation(
        root,
        RecordAttemptStopRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
            expected_assignment_revision=2,
            outcome="unknown",
        ),
        owner,
    )
    next_work_id, next_resource_id = uuid4(), uuid4()
    current = read_work(root, work_id, owner)
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=next_work_id,
            state=WorkState(
                activity_id=current.state.activity_id,
                goal="Independent fictional work",
                inputs=(ArtifactRef(artifact_id=artifact_id, revision=1),),
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
            work_id=next_work_id,
            resource_id=next_resource_id,
            state=ResourceState(label="Same exclusive directory", root=workspace, limit_units=100),
        ),
        owner,
    )
    next_attempt = AssignAttemptRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        attempt_id=uuid4(),
        work_id=next_work_id,
        expected_work_revision=1,
        resource_id=next_resource_id,
        expected_resource_revision=1,
        session_id=uuid4(),
        executor_version="synthetic-pi-rpc-contract-1",
    )
    with pytest.raises(FoundationError, match="resource_busy"):
        apply_operation(root, next_attempt, owner)
    apply_operation(
        root,
        AcceptWorkRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            expected_revision=2,
            basis="Accept fictional output without claiming process stopped",
        ),
        owner,
    )
    after_accept = read_execution(root, work_id, owner)
    assert after_accept.work.state.status == "succeeded"
    assert after_accept.assignments[0].status == "unknown"
    assert after_accept.attempts[0].status == "active"
    assert all(item.status == "cancelled" for item in after_accept.outbox)
    with pytest.raises(FoundationError, match="resource_busy"):
        apply_operation(root, next_attempt, owner)
    apply_operation(
        root,
        RecordAttemptStopRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
            expected_assignment_revision=3,
            outcome="stopped",
        ),
        owner,
    )
    after_stop = read_execution(root, work_id, owner)
    assert after_stop.assignments[0].status == "stopped"
    assert after_stop.attempts[0].status == "interrupted"
    assert apply_operation(root, next_attempt, owner).result["attempt_id"] == str(
        next_attempt.attempt_id
    )


def test_accept_work_requests_stop_for_assigned_attempt(tmp_path: Path) -> None:
    root, _, space_id, _, work_id, resource_id = ready(tmp_path)
    owner = authorize_local(root, actor="owner", source_ref="trusted-fictional-console")
    attempt_id, session_id, _ = assign(root, space_id, work_id, resource_id)
    output_id = uuid4()
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            artifact_id=output_id,
            media_type="text/plain",
            content=b"Independent fictional result",
        ),
        owner,
    )
    apply_operation(
        root,
        LinkWorkOutputRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            expected_revision=1,
            output=LinkedOutput(
                slot="summary", artifact=ArtifactRef(artifact_id=output_id, revision=1)
            ),
        ),
        owner,
    )
    apply_operation(
        root,
        AcceptWorkRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            expected_revision=2,
            basis="Independent fictional result accepted",
        ),
        owner,
    )
    after_accept = read_execution(root, work_id, owner)
    assert after_accept.assignments[0].status == "stop_requested"
    assert after_accept.attempts[0].status == "active"
    assert all(item.status == "cancelled" for item in after_accept.outbox)
    apply_operation(
        root,
        RecordAttemptStopRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
            expected_assignment_revision=2,
            outcome="stopped",
        ),
        owner,
    )
    assert read_execution(root, work_id, owner).attempts[0].status == "interrupted"


def test_schema4_accept_work_keeps_interactive_stage4_interrupt(tmp_path: Path) -> None:
    root, workspace, space_id, _, work_id, _ = ready(tmp_path)
    owner = authorize_local(root, actor="owner", source_ref="trusted-fictional-console")
    session_id = uuid4()
    bridge = Bridge(root, owner, workspace, 100)
    bridge.connect(session_id)
    activity_id = read_work(root, work_id, owner).state.activity_id
    bridge.select(session_id, activity_id, work_id)
    started = bridge.start_attempt(session_id, interrupt_previous=False)
    output_id = uuid4()
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            artifact_id=output_id,
            media_type="text/plain",
            content=b"Interactive fictional result",
        ),
        owner,
    )
    apply_operation(
        root,
        LinkWorkOutputRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            expected_revision=1,
            output=LinkedOutput(
                slot="summary", artifact=ArtifactRef(artifact_id=output_id, revision=1)
            ),
        ),
        owner,
    )
    apply_operation(
        root,
        AcceptWorkRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            expected_revision=2,
            basis="Interactive fictional result accepted",
        ),
        owner,
    )
    after = read_execution(root, work_id, owner)
    assert after.attempts[0].attempt_id == UUID(str(started["attempt_id"]))
    assert after.attempts[0].status == "interrupted"
    assert after.assignments == ()
