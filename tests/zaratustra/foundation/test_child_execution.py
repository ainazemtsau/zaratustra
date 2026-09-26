"""Assigned composite child Attempts, plan pins and derived Work states without a model."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_composition import (
    _apply,
    _delete_after_upgrade,
    _result,
    _seed,
    _sqlite_contains,
)
from zaratustra.foundation import (
    AcceptWorkRequest,
    AdmitInvocationRequest,
    AnswerWaitRequest,
    ArtifactRef,
    AssignAttemptRequest,
    ClaimAttemptLaunchRequest,
    ConfirmObligationRequest,
    CreateArtifactRequest,
    CreateDecisionRequest,
    CreateResourceRequest,
    CreateWorkRequest,
    DecisionState,
    DeleteArtifactRequest,
    DeleteWorkRequest,
    FinishInvocationRequest,
    FoundationError,
    IssueChildWorkRequest,
    LinkedOutput,
    LinkWorkOutputRequest,
    LocalAuthority,
    OpenWaitRequest,
    OperationReceipt,
    OutputContract,
    PlanCondition,
    PrepareInvocationRequest,
    PublishAttemptOutputRequest,
    RecordAttemptStopRequest,
    RecoverRequest,
    RequestAttemptStopRequest,
    ResourceState,
    ReviseArtifactRequest,
    ReviseDecisionRequest,
    SendInvocationRequest,
    StartAttemptRequest,
    WorkState,
    WorkStatus,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    read_activity,
    read_assigned_control,
    read_execution,
    read_obligation,
    read_receipt,
    read_space,
    read_work,
    read_work_status,
    restore_backup,
    upgrade_child_execution_space,
    upgrade_parent_execution_space,
    upgrade_plan_revision_space,
)

EXECUTOR = "synthetic-child-contract-1"


def _codes(status: WorkStatus) -> list[str]:
    return [reason.code for reason in status.reasons]


def _resource(root: Path, space: UUID, owner: LocalAuthority, work: UUID, name: str) -> UUID:
    directory = root.parent / name
    directory.mkdir(exist_ok=True)
    resource = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateResourceRequest,
        resource_id=resource,
        work_id=work,
        state=ResourceState(label=name, root=directory, limit_units=100),
    )
    return resource


def _assign(
    root: Path,
    space: UUID,
    owner: LocalAuthority,
    work: UUID,
    resource: UUID,
    *,
    previous: UUID | None = None,
) -> tuple[UUID, UUID, AssignAttemptRequest, OperationReceipt]:
    attempt, session = uuid4(), uuid4()
    request = AssignAttemptRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        attempt_id=attempt,
        work_id=work,
        expected_work_revision=read_work(root, work, owner).revision,
        resource_id=resource,
        expected_resource_revision=1,
        session_id=session,
        previous_attempt_id=previous,
        executor_version=EXECUTOR,
    )
    return attempt, session, request, apply_operation(root, request, owner)


def _assignment_revision(root: Path, owner: LocalAuthority, work: UUID, attempt: UUID) -> int:
    snapshot = read_execution(root, work, owner)
    return next(item.revision for item in snapshot.assignments if item.attempt_id == attempt)


def _claim(
    root: Path, space: UUID, owner: LocalAuthority, work: UUID, attempt: UUID, session: UUID
) -> OperationReceipt:
    return _apply(
        root,
        space,
        owner,
        ClaimAttemptLaunchRequest,
        attempt_id=attempt,
        work_id=work,
        session_id=session,
        expected_assignment_revision=_assignment_revision(root, owner, work, attempt),
        claim_nonce=uuid4(),
    )


def _invocation(
    root: Path,
    space: UUID,
    owner: LocalAuthority,
    work: UUID,
    attempt: UUID,
    session: UUID,
    *,
    finish: bool = True,
) -> UUID:
    invocation = uuid4()
    common: dict[str, Any] = {
        "invocation_id": invocation,
        "attempt_id": attempt,
        "work_id": work,
        "session_id": session,
    }
    _apply(
        root,
        space,
        owner,
        PrepareInvocationRequest,
        purpose="content",
        provider="synthetic",
        model="synthetic",
        transport="http-sse",
        request_sha256="A" * 64,
        request_bytes=10,
        reserve_units=5,
        **common,
    )
    _apply(root, space, owner, AdmitInvocationRequest, **common)
    _apply(root, space, owner, SendInvocationRequest, **common)
    if finish:
        _apply(
            root, space, owner, FinishInvocationRequest, outcome="answered", usage_units=3, **common
        )
    return invocation


def _request_stop(
    root: Path, space: UUID, owner: LocalAuthority, work: UUID, attempt: UUID, session: UUID
) -> None:
    _apply(
        root,
        space,
        owner,
        RequestAttemptStopRequest,
        attempt_id=attempt,
        work_id=work,
        session_id=session,
        expected_assignment_revision=_assignment_revision(root, owner, work, attempt),
        reason="Synthetic child process was observed stopped",
    )


def _stop(
    root: Path, space: UUID, owner: LocalAuthority, work: UUID, attempt: UUID, session: UUID
) -> None:
    snapshot = read_execution(root, work, owner)
    assignment = next(item for item in snapshot.assignments if item.attempt_id == attempt)
    if assignment.status != "stop_requested":
        _request_stop(root, space, owner, work, attempt, session)
    _apply(
        root,
        space,
        owner,
        RecordAttemptStopRequest,
        attempt_id=attempt,
        work_id=work,
        session_id=session,
        expected_assignment_revision=_assignment_revision(root, owner, work, attempt),
        outcome="stopped",
    )


def _issue(root: Path, space: UUID, owner: LocalAuthority, parent: UUID, child: UUID) -> None:
    _apply(
        root,
        space,
        owner,
        IssueChildWorkRequest,
        parent_work_id=parent,
        work_id=child,
        expected_plan_revision=1,
        expected_work_revision=1,
    )


def test_child_execution_needs_explicit_schema_6_and_keeps_old_routes(tmp_path: Path) -> None:
    root, space, owner, activity, _source, _ref, parent, a, _b, _plan, _create = _seed(tmp_path)
    _issue(root, space, owner, parent, a)
    with pytest.raises(FoundationError, match="unsupported_composite_execution"):
        _resource(root, space, owner, a, "workspace-a")
    before = read_execution(root, a, owner)
    assert read_space(root).schema_version == 5
    assert before.status is not None and before.status.status == "ready"
    assert before.composition is not None and before.composition.role == "a"
    assert before.composition.pins == ()
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    assert read_execution(root, a, owner).work == before.work

    plain = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=plain,
        state=WorkState(
            activity_id=activity,
            goal="Plain synthetic Work",
            expected_outputs=(OutputContract(slot="summary", media_type="text/plain"),),
        ),
    )
    plain_resource = _resource(root, space, owner, plain, "workspace-plain")
    assert read_work_status(root, plain, owner).status == "ready"
    attempt, session, _request, receipt = _assign(root, space, owner, plain, plain_resource)
    assert "plan" not in receipt.result
    assert read_execution(root, plain, owner).composition is None
    assert _codes(read_work_status(root, plain, owner)) == ["launch_pending"]
    _claim(root, space, owner, plain, attempt, session)
    assert read_work_status(root, plain, owner).status == "running"
    _stop(root, space, owner, plain, attempt, session)
    assert read_work_status(root, plain, owner).status == "ready"

    a_resource = _resource(root, space, owner, a, "workspace-a")
    with pytest.raises(FoundationError, match="unsupported_composite_execution"):
        _apply(
            root,
            space,
            owner,
            StartAttemptRequest,
            attempt_id=uuid4(),
            work_id=a,
            expected_work_revision=read_work(root, a, owner).revision,
            resource_id=a_resource,
            expected_resource_revision=1,
            session_id=uuid4(),
        )
    with pytest.raises(FoundationError, match="unsupported_composite_execution"):
        _apply(
            root,
            space,
            owner,
            AssignAttemptRequest,
            attempt_id=uuid4(),
            work_id=parent,
            expected_work_revision=1,
            resource_id=a_resource,
            expected_resource_revision=1,
            session_id=uuid4(),
            executor_version=EXECUTOR,
        )


@pytest.mark.parametrize("schema_version", (6, 7, 8))
def test_legacy_plain_work_publication_fences_next_invocation(
    tmp_path: Path, schema_version: int
) -> None:
    root, space, owner, activity, source, _ref, _parent, _a, _b, _plan, _create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    if schema_version >= 7:
        assert upgrade_plan_revision_space(root, owner).schema_version == 7
    if schema_version == 8:
        assert upgrade_parent_execution_space(root, owner).schema_version == 8
    work = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=work,
        state=WorkState(
            activity_id=activity,
            goal="Plain synthetic Work",
            inputs=(ArtifactRef(artifact_id=source, revision=1),),
            expected_outputs=(OutputContract(slot="final", media_type="text/plain"),),
            method="none",
        ),
    )
    resource = _resource(root, space, owner, work, "plain-work-resource")
    attempt, session, _request, _receipt = _assign(root, space, owner, work, resource)
    _claim(root, space, owner, work, attempt, session)
    _invocation(root, space, owner, work, attempt, session)
    _apply(
        root,
        space,
        owner,
        PublishAttemptOutputRequest,
        attempt_id=attempt,
        work_id=work,
        session_id=session,
        slot="final",
        media_type="text/plain",
        content=b"first synthetic result",
    )
    assert read_work(root, work, owner).revision == 2
    assert read_execution(root, work, owner).attempts[0].work_revision == 1
    with pytest.raises(FoundationError, match="stale_work"):
        _apply(
            root,
            space,
            owner,
            PrepareInvocationRequest,
            invocation_id=uuid4(),
            attempt_id=attempt,
            work_id=work,
            session_id=session,
            purpose="content",
            provider="synthetic",
            model="synthetic",
            transport="http-sse",
            request_sha256="B" * 64,
            request_bytes=10,
            reserve_units=5,
        )


def test_assigned_child_pins_plan_moves_through_states_and_unblocks_next(
    tmp_path: Path,
) -> None:
    root, space, owner, activity, _source, ref, parent, a, b, _plan, _create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    a_resource = _resource(root, space, owner, a, "workspace-a")
    b_resource = _resource(root, space, owner, b, "workspace-b")
    a_status = read_work_status(root, a, owner)
    assert a_status.status == "proposed" and _codes(a_status) == ["issue_pending"]
    b_status = read_work_status(root, b, owner)
    assert b_status.status == "blocked" and _codes(b_status) == ["dependency_open"]
    assert b_status.reasons[0].role == "a" and b_status.reasons[0].record_id == a
    assert read_work_status(root, parent, owner).status == "ready"

    with pytest.raises(FoundationError, match="child_not_issued"):
        _assign(root, space, owner, b, b_resource)
    early = read_execution(root, b, owner)
    assert early.attempts == () and early.assignments == () and early.outbox == ()

    _issue(root, space, owner, parent, a)
    assert read_work_status(root, a, owner).status == "ready"
    attempt, session, assign, receipt = _assign(root, space, owner, a, a_resource)
    pinned = {
        "parent_work_id": str(parent),
        "role": "a",
        "plan_revision": 1,
        "method": ref.model_dump(mode="json"),
    }
    assert receipt.result["plan"] == pinned
    assert apply_operation(root, assign, owner) == receipt
    with pytest.raises(FoundationError, match="stale_attempt"):
        _assign(root, space, owner, a, a_resource, previous=attempt)
    snapshot = read_execution(root, a, owner)
    assert snapshot.composition is not None
    assert [pin.plan_revision for pin in snapshot.composition.pins] == [1]
    assert snapshot.composition.pins[0].method == ref
    assert [item.kind for item in snapshot.outbox] == ["launch"]
    assert _codes(read_work_status(root, a, owner)) == ["launch_pending"]

    _claim(root, space, owner, a, attempt, session)
    assert read_work_status(root, a, owner).status == "running"
    assert read_work_status(root, parent, owner).status == "running"
    assert read_assigned_control(root, a, attempt, owner)
    _invocation(root, space, owner, a, attempt, session)
    wait_id, partial = uuid4(), uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=partial,
        media_type="text/plain",
        content=b"synthetic partial check",
    )
    _apply(
        root,
        space,
        owner,
        OpenWaitRequest,
        wait_id=wait_id,
        attempt_id=attempt,
        work_id=a,
        session_id=session,
        expected_assignment_revision=_assignment_revision(root, owner, a, attempt),
        question="Which synthetic source line is authoritative?",
        expected_actor="owner",
        remainder="Finish the synthetic check",
        partial_refs=(ArtifactRef(artifact_id=partial, revision=1),),
    )
    waiting = read_work_status(root, a, owner)
    assert waiting.status == "waiting" and waiting.wait_id == wait_id
    parent_waiting = read_work_status(root, parent, owner)
    assert parent_waiting.status == "waiting" and _codes(parent_waiting) == ["child_waiting"]
    answer = AnswerWaitRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        wait_id=wait_id,
        attempt_id=attempt,
        work_id=a,
        session_id=session,
        expected_wait_revision=1,
        answer="Use the first synthetic line",
    )
    answered = apply_operation(root, answer, owner)
    assert apply_operation(root, answer, owner) == answered
    assert _codes(read_work_status(root, a, owner)) == ["continuation_ready"]
    _invocation(root, space, owner, a, attempt, session)
    assert read_work_status(root, a, owner).status == "running"
    published = _apply(
        root,
        space,
        owner,
        PublishAttemptOutputRequest,
        attempt_id=attempt,
        work_id=a,
        session_id=session,
        slot="checked",
        media_type="text/plain",
        content=b"synthetic checked source",
    )
    _request_stop(root, space, owner, a, attempt, session)
    stopping = read_work_status(root, a, owner)
    assert stopping.status == "running" and _codes(stopping) == ["stop_requested"]
    assert read_work(root, a, owner).state.status == "proposed"
    _stop(root, space, owner, a, attempt, session)
    result = read_work_status(root, a, owner)
    assert result.status == "proposed" and _codes(result) == ["result_proposed"]
    assert read_work(root, a, owner).state.status == "proposed"
    assert read_work_status(root, b, owner).status == "blocked"

    _apply(
        root,
        space,
        owner,
        AcceptWorkRequest,
        work_id=a,
        expected_revision=read_work(root, a, owner).revision,
        basis="Separate synthetic child acceptance",
    )
    assert read_work_status(root, a, owner).status == "succeeded"
    unblocked = read_work_status(root, b, owner)
    assert unblocked.status == "proposed" and _codes(unblocked) == ["issue_pending"]
    _issue(root, space, owner, parent, b)
    a_output = ArtifactRef(artifact_id=UUID(str(published.result["artifact_id"])), revision=1)
    assert a_output in read_work(root, b, owner).state.inputs
    assert read_work_status(root, b, owner).status == "ready"
    parent_view = read_execution(root, parent, owner).composition
    assert parent_view is not None
    assert {child.role: child.status.status for child in parent_view.children} == {
        "a": "succeeded",
        "b": "ready",
    }
    assert read_activity(root, activity, owner).state.status == "ongoing"


def test_stale_pin_and_lost_dependency_refuse_effects_but_not_stop(tmp_path: Path) -> None:
    root, space, owner, _activity, _source, _ref, parent, a, b, plan, create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    decision = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateDecisionRequest,
        decision_id=decision,
        state=DecisionState(
            statement="Synthetic branch decision",
            effect="require_grant",
            actions=("space.inspect",),
            subjects=("synthetic-nobody",),
        ),
    )
    gated = plan.children[1].model_copy(
        update={
            "work_id": uuid4(),
            "readiness": PlanCondition(
                kind="all",
                members=(
                    PlanCondition(
                        kind="accepted_output", role="a", slot="checked", media_type="text/plain"
                    ),
                    PlanCondition(
                        kind="decision_active", decision_id=decision, decision_revision=1
                    ),
                ),
            ),
        }
    )
    other_a = plan.children[0].model_copy(update={"work_id": uuid4()})
    other_parent = uuid4()
    apply_operation(
        root,
        create.model_copy(
            update={
                "operation_id": uuid4(),
                "work_id": other_parent,
                "plan": plan.model_copy(update={"children": (other_a, gated)}),
            }
        ),
        owner,
    )
    _issue(root, space, owner, other_parent, other_a.work_id)
    _result(root, space, owner, other_a.work_id, "checked", b"synthetic checked source")
    _issue(root, space, owner, other_parent, gated.work_id)
    resource = _resource(root, space, owner, gated.work_id, "workspace-gated")
    attempt, session, _assign_request, _receipt = _assign(
        root, space, owner, gated.work_id, resource
    )
    _claim(root, space, owner, gated.work_id, attempt, session)
    sent = _invocation(root, space, owner, gated.work_id, attempt, session, finish=False)
    _apply(
        root,
        space,
        owner,
        ReviseDecisionRequest,
        decision_id=decision,
        expected_revision=1,
        state=DecisionState(
            statement="Synthetic branch decision changed",
            effect="require_grant",
            actions=("space.inspect",),
            subjects=("synthetic-nobody",),
        ),
    )
    before = read_execution(root, gated.work_id, owner)
    with pytest.raises(FoundationError, match="stale_basis"):
        _invocation(root, space, owner, gated.work_id, attempt, session)
    assert len(read_execution(root, gated.work_id, owner).invocations) == len(before.invocations)
    with pytest.raises(FoundationError, match="stale_basis"):
        _apply(
            root,
            space,
            owner,
            PublishAttemptOutputRequest,
            attempt_id=attempt,
            work_id=gated.work_id,
            session_id=session,
            slot="final",
            media_type="text/plain",
            content=b"late synthetic output",
        )
    assert not read_assigned_control(root, gated.work_id, attempt, owner)
    blocked = read_work_status(root, gated.work_id, owner)
    assert blocked.status == "blocked" and "stale_basis" in _codes(blocked)
    _apply(
        root,
        space,
        owner,
        FinishInvocationRequest,
        invocation_id=sent,
        attempt_id=attempt,
        work_id=gated.work_id,
        session_id=session,
        outcome="unknown",
    )
    _stop(root, space, owner, gated.work_id, attempt, session)
    stopped = read_execution(root, gated.work_id, owner)
    assert stopped.assignments[0].status == "stopped" and not stopped.outputs
    assert stopped.held_units == 5

    _issue(root, space, owner, parent, a)
    a_resource = _resource(root, space, owner, a, "workspace-a")
    a_attempt, a_session, _request, _a_receipt = _assign(root, space, owner, a, a_resource)
    with closing(sqlite3.connect(root / ".zara-core" / "core.sqlite3")) as connection:
        # Fault injection: a later plan generation must not accept an older pin.
        connection.execute(
            "UPDATE execution_plan_pins SET plan_revision = 99 WHERE attempt_id = ?",
            (str(a_attempt),),
        )
        connection.commit()
    with pytest.raises(FoundationError, match="stale_plan"):
        _claim(root, space, owner, a, a_attempt, a_session)
    assert not read_assigned_control(root, a, a_attempt, owner)
    assert _codes(read_work_status(root, a, owner)) == ["stale_plan"]
    _stop(root, space, owner, a, a_attempt, a_session)
    assert read_work_status(root, a, owner).status == "ready"
    assert read_work_status(root, b, owner).status == "blocked"


def test_restore_keeps_pins_and_deletion_removes_child_execution_data(tmp_path: Path) -> None:
    root, space, owner, _activity, _source, _ref, parent, a, b, _plan, _create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    marker = f"synthetic child question {uuid4()}"
    _issue(root, space, owner, parent, a)
    resource = _resource(root, space, owner, a, "workspace-a")
    attempt, session, assign_request, _receipt = _assign(root, space, owner, a, resource)
    _claim(root, space, owner, a, attempt, session)
    _apply(
        root,
        space,
        owner,
        OpenWaitRequest,
        wait_id=uuid4(),
        attempt_id=attempt,
        work_id=a,
        session_id=session,
        expected_assignment_revision=1,
        question=marker,
        expected_actor="owner",
        remainder=marker,
    )
    backup = create_backup(root, uuid4(), owner)
    assert backup.manifest.schema_version == 6
    restored_root = tmp_path / "restored"
    restored_root.mkdir()
    restored = restore_backup(
        backup.package, restored_root, authorize_recovery(actor="owner", source_ref="restore")
    )
    assert restored.schema_version == 6 and restored.execution_epoch == 2
    recovery = authorize_recovery(actor="owner", source_ref="fresh-recovery")
    apply_operation(
        restored_root,
        RecoverRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        recovery,
    )
    restored_owner = authorize_local(restored_root, actor="owner", source_ref="new-epoch")
    history = read_execution(restored_root, a, restored_owner)
    assert history.waits[0].question == marker and history.waits[0].status == "closed"
    assert history.assignments[0].status == "interrupted"
    assert all(item.status == "cancelled" for item in history.outbox)
    assert history.composition is not None
    assert [pin.attempt_id for pin in history.composition.pins] == [attempt]
    assert read_work_status(restored_root, a, restored_owner).status == "ready"
    with pytest.raises(FoundationError, match="stale_attempt"):
        _claim(restored_root, space, restored_owner, a, attempt, session)
    next_attempt, _next_session, _next, next_receipt = _assign(
        restored_root, space, restored_owner, a, resource, previous=attempt
    )
    assert cast(dict[str, object], next_receipt.result["plan"])["plan_revision"] == 1
    assert [
        pin.attempt_id
        for pin in cast(Any, read_execution(restored_root, a, restored_owner).composition).pins
    ] == [attempt, next_attempt]

    _stop(root, space, owner, a, attempt, session)
    _apply(
        root,
        space,
        owner,
        DeleteWorkRequest,
        work_id=a,
        expected_revision=read_work(root, a, owner).revision,
    )
    deleted = complete_deletions(root, owner)
    assert deleted.live_store_sanitized and not backup.package.exists()
    with closing(sqlite3.connect(root / ".zara-core" / "core.sqlite3")) as connection:
        assert connection.execute(
            "SELECT count(*) FROM execution_plan_pins WHERE work_id = ?", (str(a),)
        ).fetchone() == (0,)
    assert not _sqlite_contains(root / ".zara-core", marker)
    assert read_obligation(root, parent, "checked", owner).status == "open"
    assert read_work_status(root, b, owner).status == "blocked"
    view = read_execution(root, parent, owner).composition
    assert view is not None and not view.plan_available
    assert {child.role: _codes(child.status) for child in view.children}["a"] == [
        "content_unavailable"
    ]
    with pytest.raises(FoundationError, match="history_unavailable"):
        apply_operation(root, assign_request, owner)
    with pytest.raises(FoundationError, match="not_found"):
        read_receipt(root, assign_request.operation_id, owner)


def test_parent_state_follows_obligations_and_acceptance(tmp_path: Path) -> None:
    root, space, owner, activity, _source, _ref, parent, a, b, _plan, _create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    _issue(root, space, owner, parent, a)
    a_output = _result(root, space, owner, a, "checked", b"synthetic checked")
    confirm = read_work_status(root, parent, owner)
    assert confirm.status == "ready"
    assert {(reason.code, reason.role) for reason in confirm.reasons} == {
        ("issue_pending", "b"),
        ("confirmation_pending", "a"),
    }
    _issue(root, space, owner, parent, b)
    b_output = _result(root, space, owner, b, "final", b"synthetic final")
    for key, evidence in (("checked", a_output), ("final", b_output)):
        _apply(
            root,
            space,
            owner,
            ConfirmObligationRequest,
            work_id=parent,
            key=key,
            expected_plan_revision=1,
            expected_obligation_revision=1,
            evidence=evidence,
            basis="Synthetic confirmation",
        )
    # Core acceptance still needs the exact bound child result in the parent slot.
    link = read_work_status(root, parent, owner)
    assert link.status == "ready"
    assert [(item.code, item.role, item.record_id, item.revision) for item in link.reasons] == [
        ("output_link_pending", "b", b_output.artifact_id, b_output.revision)
    ]
    with pytest.raises(FoundationError, match="output_mismatch"):
        _apply(
            root,
            space,
            owner,
            AcceptWorkRequest,
            work_id=parent,
            expected_revision=1,
            basis="Premature synthetic parent acceptance",
        )
    _apply(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=parent,
        expected_revision=1,
        output=LinkedOutput(slot="final", artifact=b_output),
    )
    ready = read_work_status(root, parent, owner)
    assert ready.status == "ready" and _codes(ready) == ["acceptance_pending"]
    _apply(
        root,
        space,
        owner,
        AcceptWorkRequest,
        work_id=parent,
        expected_revision=2,
        basis="Separate synthetic parent acceptance",
    )
    assert read_work_status(root, parent, owner).status == "succeeded"
    assert read_activity(root, activity, owner).state.status == "ongoing"


def _confirmed_parent(
    root: Path, space: UUID, owner: LocalAuthority, parent: UUID, a: UUID, b: UUID
) -> None:
    _issue(root, space, owner, parent, a)
    a_output = _result(root, space, owner, a, "checked", b"synthetic checked")
    _issue(root, space, owner, parent, b)
    b_output = _result(root, space, owner, b, "final", b"synthetic final")
    for key, evidence in (("checked", a_output), ("final", b_output)):
        _apply(
            root,
            space,
            owner,
            ConfirmObligationRequest,
            work_id=parent,
            key=key,
            expected_plan_revision=1,
            expected_obligation_revision=1,
            evidence=evidence,
            basis="Synthetic confirmation",
        )
    _apply(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=parent,
        expected_revision=1,
        output=LinkedOutput(slot="final", artifact=b_output),
    )
    assert _codes(read_work_status(root, parent, owner)) == ["acceptance_pending"]


def _assert_parent_blocked(
    root: Path, space: UUID, owner: LocalAuthority, parent: UUID, record: UUID
) -> None:
    for status in (
        read_work_status(root, parent, owner),
        read_execution(root, parent, owner).status,
    ):
        assert status is not None and status.status == "blocked"
        assert [(item.code, item.record_id, item.revision) for item in status.reasons] == [
            ("stale_basis", record, 1)
        ]
    with pytest.raises(FoundationError, match="stale_basis"):
        _apply(
            root,
            space,
            owner,
            AcceptWorkRequest,
            work_id=parent,
            expected_revision=2,
            basis="Synthetic acceptance over a stale prerequisite",
        )
    assert read_work(root, parent, owner).state.status == "proposed"


def test_parent_blocks_when_its_input_revision_changes(tmp_path: Path) -> None:
    root, space, owner, _activity, source, _ref, parent, a, b, _plan, _create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    _confirmed_parent(root, space, owner, parent, a, b)
    _apply(
        root,
        space,
        owner,
        ReviseArtifactRequest,
        artifact_id=source,
        expected_revision=1,
        media_type="text/plain",
        content=b"synthetic source revised",
    )
    _assert_parent_blocked(root, space, owner, parent, source)


def test_unissued_child_and_parent_show_the_issue_refusal_address(tmp_path: Path) -> None:
    root, space, owner, _activity, source, _ref, parent, a, _b, _plan, _create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    _apply(
        root,
        space,
        owner,
        ReviseArtifactRequest,
        artifact_id=source,
        expected_revision=1,
        media_type="text/plain",
        content=b"synthetic source revised before issue",
    )
    for work in (a, parent):
        status = read_work_status(root, work, owner)
        assert status.status == "blocked"
        assert [(item.code, item.record_id, item.revision) for item in status.reasons] == [
            ("stale_basis", source, 1)
        ]
    with pytest.raises(FoundationError, match="stale_basis"):
        _issue(root, space, owner, parent, a)


def test_parent_blocks_when_its_completion_decision_is_revoked(tmp_path: Path) -> None:
    root, space, owner, _activity, _source, _ref, _parent, _a, _b, plan, create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    decision = uuid4()
    decision_state = DecisionState(
        statement="Synthetic completion decision",
        effect="require_grant",
        actions=("space.inspect",),
        subjects=("synthetic-nobody",),
    )
    _apply(root, space, owner, CreateDecisionRequest, decision_id=decision, state=decision_state)
    parent, a, b = uuid4(), uuid4(), uuid4()
    assert plan.completion is not None
    apply_operation(
        root,
        create.model_copy(
            update={
                "operation_id": uuid4(),
                "work_id": parent,
                "plan": plan.model_copy(
                    update={
                        "children": (
                            plan.children[0].model_copy(update={"work_id": a}),
                            plan.children[1].model_copy(update={"work_id": b}),
                        ),
                        "completion": PlanCondition(
                            kind="all",
                            members=(
                                plan.completion,
                                PlanCondition(
                                    kind="decision_active",
                                    decision_id=decision,
                                    decision_revision=1,
                                ),
                            ),
                        ),
                    }
                ),
            }
        ),
        owner,
    )
    _confirmed_parent(root, space, owner, parent, a, b)
    _apply(
        root,
        space,
        owner,
        ReviseDecisionRequest,
        decision_id=decision,
        expected_revision=1,
        state=decision_state.model_copy(update={"status": "revoked"}),
    )
    _assert_parent_blocked(root, space, owner, parent, decision)


def test_sequential_sanitation_keeps_child_addresses_until_child_deletion(
    tmp_path: Path,
) -> None:
    root, space, owner, _activity, _source, _ref, parent, a, b, _plan, _create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    marker = f"synthetic dependent child question {uuid4()}"
    _issue(root, space, owner, parent, a)
    a_output = _result(root, space, owner, a, "checked", b"synthetic accepted check")
    _issue(root, space, owner, parent, b)
    resource = _resource(root, space, owner, b, "workspace-b")
    attempt, session, _request, _receipt = _assign(root, space, owner, b, resource)
    _claim(root, space, owner, b, attempt, session)
    _apply(
        root,
        space,
        owner,
        OpenWaitRequest,
        wait_id=uuid4(),
        attempt_id=attempt,
        work_id=b,
        session_id=session,
        expected_assignment_revision=1,
        question=marker,
        expected_actor="owner",
        remainder=marker,
    )
    old_backup = create_backup(root, uuid4(), owner)
    # A's acceptance basis depends on its output: schema 6 needs the explicit upgrade first.
    _delete_after_upgrade(
        root,
        space,
        owner,
        DeleteArtifactRequest,
        artifact_id=a_output.artifact_id,
        expected_revision=1,
    )
    assert complete_deletions(root, owner).live_store_sanitized
    assert not old_backup.package.exists()
    sanitized = read_execution(root, b, owner)
    assert sanitized.attempts[0].status == "interrupted"
    assert sanitized.assignments[0].status == "interrupted"
    assert sanitized.waits[0].status == "purged" and sanitized.waits[0].question is None
    assert [item.status for item in sanitized.outbox] == ["cancelled"]
    assert sanitized.composition is not None
    assert [pin.attempt_id for pin in sanitized.composition.pins] == [attempt]
    assert read_obligation(root, parent, "checked", owner).status == "open"
    blocked = read_work_status(root, b, owner)
    assert blocked.status == "blocked" and "content_unavailable" in _codes(blocked)
    assert not _sqlite_contains(root / ".zara-core", marker)
    restarted = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; from uuid import UUID; "
            "from zaratustra.foundation import authorize_local, read_work_status; "
            "p=Path(sys.argv[1]); o=authorize_local(p, actor='owner', source_ref='restart'); "
            "print(read_work_status(p, UUID(sys.argv[2]), o).status)",
            str(root),
            str(b),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert restarted.returncode == 0, restarted.stderr
    assert restarted.stdout.strip() == "blocked"
    _apply(
        root,
        space,
        owner,
        DeleteWorkRequest,
        work_id=b,
        expected_revision=read_work(root, b, owner).revision,
    )
    assert complete_deletions(root, owner).live_store_sanitized
    with closing(sqlite3.connect(root / ".zara-core" / "core.sqlite3")) as connection:
        assert connection.execute("SELECT count(*) FROM execution_plan_pins").fetchone() == (0,)
    assert read_obligation(root, parent, "final", owner).status == "open"
    assert read_work_status(root, a, owner).status == "succeeded"
    acceptance = read_work(root, a, owner).state.acceptance
    assert acceptance is not None and acceptance.basis is None
