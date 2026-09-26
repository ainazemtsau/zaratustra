"""Own composite Attempt and roleless obligation through public Core operations."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_child_execution import (
    _assign,
    _claim,
    _invocation,
    _issue,
    _resource,
    _stop,
)
from tests.zaratustra.foundation.test_composition import _apply, _result, _seed, _sqlite_contains
from zaratustra.foundation import (
    AcceptWorkRequest,
    ArtifactRef,
    ConfirmObligationRequest,
    CreateCompositeWorkRequest,
    CreateMethodVersionRequest,
    CreateWorkRequest,
    DeleteArtifactRequest,
    DeleteMethodVersionRequest,
    DeleteWorkRequest,
    FoundationError,
    IssueChildWorkRequest,
    LinkedOutput,
    LinkWorkOutputRequest,
    LocalAuthority,
    MethodDefinition,
    MethodObligation,
    MethodRef,
    NamedInput,
    OutputContract,
    ParentOutputSlot,
    PlanChild,
    PlanCondition,
    PlanNodeDecision,
    PlanOutputBinding,
    PublishAttemptOutputRequest,
    RecordAttemptStopRequest,
    RecoverRequest,
    RequestAttemptStopRequest,
    ReviseActivePlanRequest,
    WorkPlan,
    WorkState,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    read_assigned_control,
    read_execution,
    read_obligation,
    read_parent_output_proof,
    read_parent_plan_pin,
    read_receipt,
    read_work,
    read_work_plan,
    read_work_status,
    restore_backup,
    upgrade_child_execution_space,
    upgrade_parent_execution_space,
    upgrade_plan_revision_space,
)


def _own_parent(
    tmp_path: Path,
    *,
    slots: tuple[str, ...] = ("final",),
    obligation_slots: tuple[str, ...] = ("final",),
    child_binding: bool = False,
) -> tuple[Path, UUID, LocalAuthority, UUID, UUID, UUID]:
    root, space, owner, activity, source, _old_method, _old_parent, _a, _b, _plan, _create = _seed(
        tmp_path
    )
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    assert upgrade_plan_revision_space(root, owner).schema_version == 7
    assert upgrade_parent_execution_space(root, owner).schema_version == 8
    source_ref = ArtifactRef(artifact_id=source, revision=1)
    method, parent, a, b = (uuid4() for _ in range(4))
    definition = MethodDefinition(
        instruction="Integrate the two checked synthetic results",
        named_inputs=(OutputContract(slot="source", media_type="text/plain"),),
        named_outputs=tuple(OutputContract(slot=slot, media_type="text/plain") for slot in slots)
        + ((OutputContract(slot="from_a", media_type="text/plain"),) if child_binding else ()),
        obligations=tuple(
            MethodObligation(
                key="summary_checked" if slot == "final" else f"{slot}_checked",
                source=f"Review the own {slot}",
                slot=slot,
                media_type="text/plain",
            )
            for slot in obligation_slots
        ),
        source_ref="synthetic-parent-method",
    )
    created = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=method,
        version=1,
        definition=definition,
    )
    ref = MethodRef(method_id=method, version=1, checksum=cast(str, created.result["checksum"]))
    child_a = WorkState(
        activity_id=activity,
        goal="Independent A",
        expected_outputs=(OutputContract(slot="result", media_type="text/plain"),),
    )
    child_b = child_a.model_copy(update={"goal": "Independent B"})
    plan = WorkPlan(
        named_inputs=(NamedInput(slot="source", artifact=source_ref),),
        parent_outputs=tuple(
            ParentOutputSlot(slot=slot, media_type="text/plain") for slot in slots
        ),
        output_bindings=(
            (
                PlanOutputBinding(
                    parent_slot="from_a", role="a", child_slot="result", media_type="text/plain"
                ),
            )
            if child_binding
            else ()
        ),
        children=(
            PlanChild(role="a", work_id=a, state=child_a),
            PlanChild(role="b", work_id=b, state=child_b),
        ),
        completion=PlanCondition(
            kind="all",
            members=(
                PlanCondition(kind="work_succeeded", role="a"),
                PlanCondition(kind="work_succeeded", role="b"),
            ),
        ),
        basis=(source_ref,),
        rationale="Own parent execution",
        source_ref="synthetic-plan",
    )
    _apply(
        root,
        space,
        owner,
        CreateCompositeWorkRequest,
        work_id=parent,
        state=WorkState(
            activity_id=activity,
            goal="Integrate A and B",
            method=ref,
            inputs=(source_ref,),
            expected_outputs=definition.named_outputs,
        ),
        plan=plan,
    )
    return root, space, owner, parent, a, b


def _ready_two_output_parent(
    tmp_path: Path,
    *,
    obligation_slots: tuple[str, ...] = (),
) -> tuple[Path, UUID, LocalAuthority, UUID, UUID]:
    root, space, owner, parent, a, b = _own_parent(
        tmp_path, slots=("final", "extra"), obligation_slots=obligation_slots
    )
    for child in (a, b):
        _issue(root, space, owner, parent, child)
        _result(root, space, owner, child, "result", b"independent child result")
    return root, space, owner, parent, _resource(root, space, owner, parent, "workspace-parent")


def test_one_parent_attempt_publishes_two_own_outputs(tmp_path: Path) -> None:
    root, space, owner, parent, resource = _ready_two_output_parent(tmp_path)
    attempt, session, _request, _receipt = _assign(root, space, owner, parent, resource)
    _claim(root, space, owner, parent, attempt, session)
    _invocation(root, space, owner, parent, attempt, session)
    final_request = PublishAttemptOutputRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        attempt_id=attempt,
        work_id=parent,
        session_id=session,
        slot="final",
        media_type="text/plain",
        content=b"own final",
    )
    final_receipt = apply_operation(root, final_request, owner)
    assert apply_operation(root, final_request, owner) == final_receipt
    extra_request = PublishAttemptOutputRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        attempt_id=attempt,
        work_id=parent,
        session_id=session,
        slot="extra",
        media_type="text/plain",
        content=b"own extra",
    )
    extra_receipt = apply_operation(root, extra_request, owner)
    assert apply_operation(root, extra_request, owner) == extra_receipt
    assert read_receipt(root, extra_request.operation_id, owner) == extra_receipt
    _stop(root, space, owner, parent, attempt, session)
    _apply(
        root,
        space,
        owner,
        AcceptWorkRequest,
        work_id=parent,
        expected_revision=read_work(root, parent, owner).revision,
        basis="Both own outputs are complete",
    )
    assert read_work_status(root, parent, owner).status == "succeeded"


def test_linked_parent_attempts_complete_distinct_own_slots(tmp_path: Path) -> None:
    root, space, owner, parent, resource = _ready_two_output_parent(tmp_path)
    first, first_session, _request, _receipt = _assign(root, space, owner, parent, resource)
    _claim(root, space, owner, parent, first, first_session)
    _invocation(root, space, owner, parent, first, first_session)
    final = _apply(
        root,
        space,
        owner,
        PublishAttemptOutputRequest,
        attempt_id=first,
        work_id=parent,
        session_id=first_session,
        slot="final",
        media_type="text/plain",
        content=b"own final",
    )
    _stop(root, space, owner, parent, first, first_session)
    second, second_session, _request, _receipt = _assign(
        root, space, owner, parent, resource, previous=first
    )
    _claim(root, space, owner, parent, second, second_session)
    _invocation(root, space, owner, parent, second, second_session)
    extra = _apply(
        root,
        space,
        owner,
        PublishAttemptOutputRequest,
        attempt_id=second,
        work_id=parent,
        session_id=second_session,
        slot="extra",
        media_type="text/plain",
        content=b"own extra",
    )
    _stop(root, space, owner, parent, second, second_session)
    assert (
        read_parent_output_proof(
            root, UUID(cast(str, final.result["artifact_id"])), owner
        ).attempt_id
        == first
    )
    assert (
        read_parent_output_proof(
            root, UUID(cast(str, extra.result["artifact_id"])), owner
        ).attempt_id
        == second
    )
    _apply(
        root,
        space,
        owner,
        AcceptWorkRequest,
        work_id=parent,
        expected_revision=read_work(root, parent, owner).revision,
        basis="Two linked own Attempts supplied distinct slots",
    )
    assert read_work_status(root, parent, owner).status == "succeeded"


def test_second_own_slot_needs_its_own_confirmation(tmp_path: Path) -> None:
    root, space, owner, parent, resource = _ready_two_output_parent(
        tmp_path, obligation_slots=("final", "extra")
    )
    attempt, session, _request, _receipt = _assign(root, space, owner, parent, resource)
    _claim(root, space, owner, parent, attempt, session)
    _invocation(root, space, owner, parent, attempt, session)
    final = _apply(
        root,
        space,
        owner,
        PublishAttemptOutputRequest,
        attempt_id=attempt,
        work_id=parent,
        session_id=session,
        slot="final",
        media_type="text/plain",
        content=b"own final",
    )
    final_ref = ArtifactRef(artifact_id=UUID(cast(str, final.result["artifact_id"])), revision=1)
    _apply(
        root,
        space,
        owner,
        ConfirmObligationRequest,
        work_id=parent,
        key="summary_checked",
        expected_plan_revision=1,
        expected_obligation_revision=1,
        evidence=final_ref,
        basis="Final checked",
    )
    extra = _apply(
        root,
        space,
        owner,
        PublishAttemptOutputRequest,
        attempt_id=attempt,
        work_id=parent,
        session_id=session,
        slot="extra",
        media_type="text/plain",
        content=b"own extra",
    )
    extra_ref = ArtifactRef(artifact_id=UUID(cast(str, extra.result["artifact_id"])), revision=1)
    _stop(root, space, owner, parent, attempt, session)
    assert read_obligation(root, parent, "summary_checked", owner).status == "satisfied"
    assert read_obligation(root, parent, "extra_checked", owner).status == "open"
    with pytest.raises(FoundationError, match="obligation_open"):
        _apply(
            root,
            space,
            owner,
            AcceptWorkRequest,
            work_id=parent,
            expected_revision=read_work(root, parent, owner).revision,
            basis="Extra still needs confirmation",
        )
    _apply(
        root,
        space,
        owner,
        ConfirmObligationRequest,
        work_id=parent,
        key="extra_checked",
        expected_plan_revision=1,
        expected_obligation_revision=1,
        evidence=extra_ref,
        basis="Extra checked separately",
    )
    _apply(
        root,
        space,
        owner,
        AcceptWorkRequest,
        work_id=parent,
        expected_revision=read_work(root, parent, owner).revision,
        basis="Both own slots checked",
    )
    assert read_work_status(root, parent, owner).status == "succeeded"


def test_other_work_revision_still_fences_next_own_publication(tmp_path: Path) -> None:
    root, space, owner, parent, a, b = _own_parent(
        tmp_path, slots=("final", "extra"), obligation_slots=(), child_binding=True
    )
    for child in (a, b):
        _issue(root, space, owner, parent, child)
    child_output = _result(root, space, owner, a, "result", b"independent A")
    _result(root, space, owner, b, "result", b"independent B")
    resource = _resource(root, space, owner, parent, "workspace-parent")
    attempt, session, _request, _receipt = _assign(root, space, owner, parent, resource)
    _claim(root, space, owner, parent, attempt, session)
    _invocation(root, space, owner, parent, attempt, session)
    _apply(
        root,
        space,
        owner,
        PublishAttemptOutputRequest,
        attempt_id=attempt,
        work_id=parent,
        session_id=session,
        slot="final",
        media_type="text/plain",
        content=b"own final",
    )
    _apply(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=parent,
        expected_revision=read_work(root, parent, owner).revision,
        output=LinkedOutput(slot="from_a", artifact=child_output),
    )
    with pytest.raises(FoundationError, match="stale_work"):
        _apply(
            root,
            space,
            owner,
            PublishAttemptOutputRequest,
            attempt_id=attempt,
            work_id=parent,
            session_id=session,
            slot="extra",
            media_type="text/plain",
            content=b"own extra",
        )


def test_parent_own_attempt_output_confirmation_and_acceptance(tmp_path: Path) -> None:
    root, space, owner, parent, a, b = _own_parent(tmp_path)
    _issue(root, space, owner, parent, a)
    _issue(root, space, owner, parent, b)
    _result(root, space, owner, a, "result", b"A checked")
    _result(root, space, owner, b, "result", b"B checked")
    resource = _resource(root, space, owner, parent, "workspace-parent")
    attempt, session, assigned, receipt = _assign(root, space, owner, parent, resource)
    assert apply_operation(root, assigned, owner) == receipt
    assert read_parent_plan_pin(root, parent, attempt, owner).plan_revision == 1
    view = read_execution(root, parent, owner).composition
    assert view is not None and [pin.attempt_id for pin in view.own_pins] == [attempt]
    assert read_work_status(root, parent, owner).attempt_id == attempt
    _claim(root, space, owner, parent, attempt, session)
    _invocation(root, space, owner, parent, attempt, session)
    published = _apply(
        root,
        space,
        owner,
        PublishAttemptOutputRequest,
        attempt_id=attempt,
        work_id=parent,
        session_id=session,
        slot="final",
        media_type="text/plain",
        content=b"A plus B summary",
    )
    artifact = ArtifactRef(artifact_id=UUID(cast(str, published.result["artifact_id"])), revision=1)
    proof = read_parent_output_proof(root, artifact.artifact_id, owner)
    assert proof.attempt_id == attempt and proof.plan_revision == 1
    foreign_output = read_execution(root, a, owner).outputs[-1]
    with pytest.raises(FoundationError, match="evidence_mismatch"):
        _apply(
            root,
            space,
            owner,
            ConfirmObligationRequest,
            work_id=parent,
            key="summary_checked",
            expected_plan_revision=1,
            expected_obligation_revision=1,
            evidence=ArtifactRef(
                artifact_id=foreign_output.artifact_id, revision=foreign_output.revision
            ),
            basis="Child output is not own evidence",
        )
    _stop(root, space, owner, parent, attempt, session)
    assert read_work_status(root, parent, owner).status == "ready"
    confirmation = _apply(
        root,
        space,
        owner,
        ConfirmObligationRequest,
        work_id=parent,
        key="summary_checked",
        expected_plan_revision=1,
        expected_obligation_revision=1,
        evidence=artifact,
        basis="Own summary checked",
    )
    assert confirmation.result["status"] == "satisfied"
    obligation = read_obligation(root, parent, "summary_checked", owner)
    assert obligation.parent_result is not None
    assert obligation.parent_result.attempt_id == attempt
    assert read_work_status(root, parent, owner).status == "ready"
    _apply(
        root,
        space,
        owner,
        AcceptWorkRequest,
        work_id=parent,
        expected_revision=read_work(root, parent, owner).revision,
        basis="Accepted own synthetic summary",
    )
    assert read_work_status(root, parent, owner).status == "succeeded"


def test_roleless_contract_requires_schema_eight(tmp_path: Path) -> None:
    root, space, owner, _activity, _source, _ref, _parent, _a, _b, _plan, _create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    assert upgrade_plan_revision_space(root, owner).schema_version == 7
    with pytest.raises(FoundationError, match="unsupported_schema"):
        _apply(
            root,
            space,
            owner,
            CreateMethodVersionRequest,
            method_id=uuid4(),
            version=1,
            definition=MethodDefinition(
                instruction="Own result",
                named_outputs=(OutputContract(slot="final", media_type="text/plain"),),
                obligations=(
                    MethodObligation(
                        key="checked",
                        source="Own proof",
                        slot="final",
                        media_type="text/plain",
                    ),
                ),
                source_ref="synthetic-parent-method",
            ),
        )


def test_new_attempt_same_plan_needs_new_confirmation(tmp_path: Path) -> None:
    root, space, owner, parent, a, b = _own_parent(tmp_path)
    for child in (a, b):
        _issue(root, space, owner, parent, child)
        _result(root, space, owner, child, "result", b"independent result")
    resource = _resource(root, space, owner, parent, "workspace-parent")
    first, first_session, _request, _receipt = _assign(root, space, owner, parent, resource)
    _claim(root, space, owner, parent, first, first_session)
    _invocation(root, space, owner, parent, first, first_session)
    published_x = _apply(
        root,
        space,
        owner,
        PublishAttemptOutputRequest,
        attempt_id=first,
        work_id=parent,
        session_id=first_session,
        slot="final",
        media_type="text/plain",
        content=b"old summary",
    )
    x = ArtifactRef(artifact_id=UUID(cast(str, published_x.result["artifact_id"])), revision=1)
    _stop(root, space, owner, parent, first, first_session)
    _apply(
        root,
        space,
        owner,
        ConfirmObligationRequest,
        work_id=parent,
        key="summary_checked",
        expected_plan_revision=1,
        expected_obligation_revision=1,
        evidence=x,
        basis="Old summary checked",
    )
    second, second_session, _request, _receipt = _assign(
        root, space, owner, parent, resource, previous=first
    )
    assert read_parent_plan_pin(root, parent, second, owner).plan_revision == 1
    with pytest.raises(FoundationError, match="stale_attempt"):
        _apply(
            root,
            space,
            owner,
            AcceptWorkRequest,
            work_id=parent,
            expected_revision=read_work(root, parent, owner).revision,
            basis="Cannot accept old Attempt result after assigning a new one",
        )
    _claim(root, space, owner, parent, second, second_session)
    _invocation(root, space, owner, parent, second, second_session)
    published_y = _apply(
        root,
        space,
        owner,
        PublishAttemptOutputRequest,
        attempt_id=second,
        work_id=parent,
        session_id=second_session,
        slot="final",
        media_type="text/plain",
        content=b"new independent summary",
    )
    y = ArtifactRef(artifact_id=UUID(cast(str, published_y.result["artifact_id"])), revision=1)
    reopened = read_obligation(root, parent, "summary_checked", owner)
    assert reopened.status == "open" and reopened.revision == 3
    assert reopened.evidence is None and reopened.parent_result is None
    assert reopened.basis is None and reopened.reopened == "parent_attempt_replaced"
    assert read_obligation(root, parent, "summary_checked", owner, revision=2).evidence == x
    with pytest.raises(FoundationError, match="evidence_mismatch"):
        _apply(
            root,
            space,
            owner,
            ConfirmObligationRequest,
            work_id=parent,
            key="summary_checked",
            expected_plan_revision=1,
            expected_obligation_revision=3,
            evidence=x,
            basis="Old proof cannot move",
        )
    _stop(root, space, owner, parent, second, second_session)
    _apply(
        root,
        space,
        owner,
        ConfirmObligationRequest,
        work_id=parent,
        key="summary_checked",
        expected_plan_revision=1,
        expected_obligation_revision=3,
        evidence=y,
        basis="New result separately checked",
    )
    new_confirmation = read_obligation(root, parent, "summary_checked", owner)
    assert new_confirmation.parent_result is not None
    assert new_confirmation.parent_result.attempt_id == second
    _apply(
        root,
        space,
        owner,
        AcceptWorkRequest,
        work_id=parent,
        expected_revision=read_work(root, parent, owner).revision,
        basis="Independent new own summary accepted",
    )


def test_plan_revision_fences_parent_attempt_before_late_publication(tmp_path: Path) -> None:
    root, space, owner, parent, a, b = _own_parent(tmp_path)
    for child in (a, b):
        _issue(root, space, owner, parent, child)
        _result(root, space, owner, child, "result", b"independent result")
    resource = _resource(root, space, owner, parent, "workspace-parent")
    attempt, session, _request, _receipt = _assign(root, space, owner, parent, resource)
    _claim(root, space, owner, parent, attempt, session)
    _invocation(root, space, owner, parent, attempt, session)
    old_plan = read_work_plan(root, parent, owner).plan
    _apply(
        root,
        space,
        owner,
        ReviseActivePlanRequest,
        work_id=parent,
        expected_work_revision=read_work(root, parent, owner).revision,
        expected_plan_revision=1,
        plan=old_plan.model_copy(update={"rationale": "New synthesis revision"}),
        nodes=(
            PlanNodeDecision(role="a", decision="keep", work_id=a),
            PlanNodeDecision(role="b", decision="keep", work_id=b),
        ),
    )
    assert read_work_plan(root, parent, owner).revision == 2
    assert not read_assigned_control(root, parent, attempt, owner)
    with pytest.raises(FoundationError, match="stale_plan"):
        _apply(
            root,
            space,
            owner,
            PublishAttemptOutputRequest,
            attempt_id=attempt,
            work_id=parent,
            session_id=session,
            slot="final",
            media_type="text/plain",
            content=b"late summary",
        )


def test_fenced_parent_sent_invocation_stays_unknown_and_holds_resource(tmp_path: Path) -> None:
    root, space, owner, parent, a, b = _own_parent(tmp_path)
    for child in (a, b):
        _issue(root, space, owner, parent, child)
        _result(root, space, owner, child, "result", b"independent result")
    resource = _resource(root, space, owner, parent, "workspace-parent")
    attempt, session, _request, _receipt = _assign(root, space, owner, parent, resource)
    _claim(root, space, owner, parent, attempt, session)
    invocation = _invocation(root, space, owner, parent, attempt, session, finish=False)
    old_plan = read_work_plan(root, parent, owner).plan
    _apply(
        root,
        space,
        owner,
        ReviseActivePlanRequest,
        work_id=parent,
        expected_work_revision=read_work(root, parent, owner).revision,
        expected_plan_revision=1,
        plan=old_plan.model_copy(update={"rationale": "Fenced synthetic synthesis"}),
        nodes=(
            PlanNodeDecision(role="a", decision="keep", work_id=a),
            PlanNodeDecision(role="b", decision="keep", work_id=b),
        ),
    )
    assert not read_assigned_control(root, parent, attempt, owner)
    snapshot = read_execution(root, parent, owner)
    assert (
        next(item for item in snapshot.invocations if item.invocation_id == invocation).status
        == "unknown"
    )
    assignment = snapshot.assignments[-1]
    if assignment.status != "stop_requested":
        _apply(
            root,
            space,
            owner,
            RequestAttemptStopRequest,
            attempt_id=attempt,
            work_id=parent,
            session_id=session,
            expected_assignment_revision=assignment.revision,
            reason="Synthetic parent fence",
        )
    assignment = read_execution(root, parent, owner).assignments[-1]
    _apply(
        root,
        space,
        owner,
        RecordAttemptStopRequest,
        attempt_id=attempt,
        work_id=parent,
        session_id=session,
        expected_assignment_revision=assignment.revision,
        outcome="unknown",
    )
    snapshot = read_execution(root, parent, owner)
    assert snapshot.assignments[-1].status == "unknown"
    assert snapshot.held_units >= 5
    with pytest.raises(FoundationError, match="stale_attempt"):
        _assign(root, space, owner, parent, resource, previous=attempt)


def test_own_proof_backup_restore_and_sequential_deletion(tmp_path: Path) -> None:
    root, space, owner, parent, a, b = _own_parent(tmp_path)
    for child in (a, b):
        _issue(root, space, owner, parent, child)
        _result(root, space, owner, child, "result", b"independent child result")
    resource = _resource(root, space, owner, parent, "workspace-parent")
    attempt, session, assign, assignment_receipt = _assign(root, space, owner, parent, resource)
    _claim(root, space, owner, parent, attempt, session)
    _invocation(root, space, owner, parent, attempt, session)
    marker = f"fictional own result {uuid4()}"
    publication = _apply(
        root,
        space,
        owner,
        PublishAttemptOutputRequest,
        attempt_id=attempt,
        work_id=parent,
        session_id=session,
        slot="final",
        media_type="text/plain",
        content=marker.encode(),
    )
    own = ArtifactRef(artifact_id=UUID(cast(str, publication.result["artifact_id"])), revision=1)
    _stop(root, space, owner, parent, attempt, session)
    confirm_request = ConfirmObligationRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        work_id=parent,
        key="summary_checked",
        expected_plan_revision=1,
        expected_obligation_revision=1,
        evidence=own,
        basis=marker,
    )
    confirmed = apply_operation(root, confirm_request, owner)
    _apply(
        root,
        space,
        owner,
        AcceptWorkRequest,
        work_id=parent,
        expected_revision=read_work(root, parent, owner).revision,
        basis=marker,
    )
    assert apply_operation(root, confirm_request, owner) == confirmed
    backup = create_backup(root, uuid4(), owner)
    assert backup.manifest.schema_version == 8
    restored_root = tmp_path / "restored"
    restored_root.mkdir()
    restored = restore_backup(
        backup.package, restored_root, authorize_recovery(actor="owner", source_ref="restore")
    )
    assert restored.schema_version == 8 and restored.execution_epoch == 2
    recovery = authorize_recovery(actor="owner", source_ref="recovery")
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
    assert read_parent_plan_pin(restored_root, parent, attempt, restored_owner).plan_revision == 1
    assert (
        read_parent_output_proof(restored_root, own.artifact_id, restored_owner).attempt_id
        == attempt
    )
    assert read_execution(restored_root, parent, restored_owner).assignments[0].status == "stopped"
    assert read_receipt(root, confirmed.operation_id, owner) == confirmed
    assert read_receipt(root, assignment_receipt.operation_id, owner) == assignment_receipt
    _apply(
        root,
        space,
        owner,
        DeleteArtifactRequest,
        artifact_id=own.artifact_id,
        expected_revision=1,
    )
    completed = complete_deletions(root, owner)
    assert completed.pending_jobs == 0 and completed.live_store_sanitized
    assert not backup.package.exists()
    assert read_obligation(root, parent, "summary_checked", owner).status == "open"
    acceptance = read_work(root, parent, owner).state.acceptance
    assert acceptance is not None and acceptance.basis is None
    assert read_receipt(root, assignment_receipt.operation_id, owner) == assignment_receipt
    with pytest.raises(FoundationError, match="history_unavailable"):
        apply_operation(root, confirm_request, owner)
    with pytest.raises(FoundationError, match="not_found"):
        read_receipt(root, confirmed.operation_id, owner)
    fresh = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-c",
            "from pathlib import Path; from uuid import UUID; import sys; "
            "from zaratustra.foundation import authorize_local,read_obligation,read_work; "
            "p=Path(sys.argv[1]); w=UUID(sys.argv[2]); "
            "a=authorize_local(p,actor='owner',source_ref='fresh'); "
            "assert read_work(p,w,a).state.acceptance.basis is None; "
            "assert read_obligation(p,w,'summary_checked',a).status == 'open'",
            str(root),
            str(parent),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert fresh.returncode == 0, fresh.stderr
    clean = create_backup(root, uuid4(), owner)
    assert not any(
        marker.encode() in path.read_bytes()
        for directory in (root / ".zara-core", clean.package)
        for path in directory.rglob("*")
        if path.is_file()
    )
    for child in (a, b):
        _apply(
            root,
            space,
            owner,
            DeleteWorkRequest,
            work_id=child,
            expected_revision=read_work(root, child, owner).revision,
        )
        assert complete_deletions(root, owner).live_store_sanitized
    _apply(
        root,
        space,
        owner,
        DeleteWorkRequest,
        work_id=parent,
        expected_revision=read_work(root, parent, owner).revision,
    )
    assert complete_deletions(root, owner).live_store_sanitized
    with closing(sqlite3.connect(root / ".zara-core" / "core.sqlite3")) as connection:
        assert connection.execute(
            "SELECT count(*) FROM execution_parent_pins WHERE work_id = ?", (str(parent),)
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM parent_output_proofs WHERE work_id = ?", (str(parent),)
        ).fetchone() == (0,)


def test_nested_own_attempt_full_grandchild_to_parent_acceptance(tmp_path: Path) -> None:
    root, space, owner, activity, source, _old_method, _old_parent, _a, _b, _plan, _create = _seed(
        tmp_path
    )
    upgrade_child_execution_space(root, owner)
    upgrade_plan_revision_space(root, owner)
    upgrade_parent_execution_space(root, owner)
    p, n, g, anchor = (uuid4() for _ in range(4))
    output = OutputContract(slot="final", media_type="text/plain")
    nested_method = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=uuid4(),
        version=1,
        definition=MethodDefinition(
            instruction="Integrate grandchild synthetically",
            named_outputs=(output,),
            obligations=(
                MethodObligation(
                    key="own_checked",
                    source="Check own synthesis",
                    slot="final",
                    media_type="text/plain",
                ),
            ),
            source_ref="nested-own-method",
        ),
    )
    nref = MethodRef(
        method_id=UUID(cast(str, nested_method.result["method_id"])),
        version=1,
        checksum=cast(str, nested_method.result["checksum"]),
    )
    parent_method_id = uuid4()
    parent_method = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=parent_method_id,
        version=1,
        definition=MethodDefinition(
            instruction="Integrate nested Work result",
            named_inputs=(OutputContract(slot="source", media_type="text/plain"),),
            named_outputs=(output,),
            obligations=(
                MethodObligation(
                    key="nested_checked",
                    source="Check nested result",
                    role="n",
                    slot="final",
                    media_type="text/plain",
                ),
            ),
            role_methods=(("n", nref),),
            source_ref="parent-nested-method",
        ),
    )
    pref = MethodRef(
        method_id=parent_method_id,
        version=1,
        checksum=cast(str, parent_method.result["checksum"]),
    )
    source_ref = ArtifactRef(artifact_id=source, revision=1)
    anchor_node = PlanChild(
        role="anchor",
        work_id=anchor,
        state=WorkState(
            activity_id=activity,
            goal="Independent unused sibling",
            expected_outputs=(OutputContract(slot="other", media_type="text/plain"),),
        ),
    )
    nested_node = PlanChild(
        role="n",
        work_id=n,
        state=WorkState(
            activity_id=activity,
            goal="Nested synthetic Work",
            method=nref,
            expected_outputs=(output,),
        ),
    )
    initial = WorkPlan(
        named_inputs=(NamedInput(slot="source", artifact=source_ref),),
        output_bindings=(
            PlanOutputBinding(
                parent_slot="final",
                role="n",
                child_slot="final",
                media_type="text/plain",
            ),
        ),
        children=(anchor_node,),
        completion=PlanCondition(kind="work_succeeded", role="n"),
        basis=(source_ref,),
        rationale="Nested role reserved",
        source_ref="parent-plan",
    )
    _apply(
        root,
        space,
        owner,
        CreateCompositeWorkRequest,
        work_id=p,
        state=WorkState(
            activity_id=activity,
            goal="Parent of nested executor",
            method=pref,
            inputs=(source_ref,),
            expected_outputs=(output,),
        ),
        plan=initial,
    )
    nested_plan = WorkPlan(
        parent_outputs=(ParentOutputSlot(slot="final", media_type="text/plain"),),
        children=(
            PlanChild(
                role="g",
                work_id=g,
                state=WorkState(
                    activity_id=activity,
                    goal="Grandchild source",
                    expected_outputs=(OutputContract(slot="result", media_type="text/plain"),),
                ),
            ),
        ),
        completion=PlanCondition(kind="work_succeeded", role="g"),
        rationale="Own synthesis after grandchild",
        source_ref="nested-plan",
    )
    _apply(
        root,
        space,
        owner,
        ReviseActivePlanRequest,
        work_id=p,
        expected_work_revision=read_work(root, p, owner).revision,
        expected_plan_revision=1,
        plan=initial.model_copy(update={"children": (anchor_node, nested_node)}),
        nodes=(
            PlanNodeDecision(role="anchor", decision="keep", work_id=anchor),
            PlanNodeDecision(role="n", decision="add", work_id=n, nested_plan=nested_plan),
        ),
    )
    _apply(
        root,
        space,
        owner,
        IssueChildWorkRequest,
        parent_work_id=p,
        work_id=n,
        expected_plan_revision=2,
        expected_work_revision=read_work(root, n, owner).revision,
    )
    _issue(root, space, owner, n, g)
    deleted_marker = f"fictional grandchild result {uuid4()}"
    grandchild_result = _result(root, space, owner, g, "result", deleted_marker.encode())
    resource = _resource(root, space, owner, n, "workspace-nested")
    attempt, session, _request, _receipt = _assign(root, space, owner, n, resource)
    view = read_execution(root, n, owner).composition
    assert view is not None and view.nested is not None
    assert view.pins[0].attempt_id == attempt
    assert view.nested.own_pins[0].attempt_id == attempt
    _claim(root, space, owner, n, attempt, session)
    _invocation(root, space, owner, n, attempt, session)
    publication = _apply(
        root,
        space,
        owner,
        PublishAttemptOutputRequest,
        attempt_id=attempt,
        work_id=n,
        session_id=session,
        slot="final",
        media_type="text/plain",
        content=b"nested synthesis",
    )
    result = ArtifactRef(artifact_id=UUID(cast(str, publication.result["artifact_id"])), revision=1)
    _stop(root, space, owner, n, attempt, session)
    _apply(
        root,
        space,
        owner,
        ConfirmObligationRequest,
        work_id=n,
        key="own_checked",
        expected_plan_revision=1,
        expected_obligation_revision=1,
        evidence=result,
        basis="Own synthesis checked",
    )
    _apply(
        root,
        space,
        owner,
        AcceptWorkRequest,
        work_id=n,
        expected_revision=read_work(root, n, owner).revision,
        basis="Nested result accepted",
    )
    _apply(
        root,
        space,
        owner,
        ConfirmObligationRequest,
        work_id=p,
        key="nested_checked",
        expected_plan_revision=2,
        expected_obligation_revision=1,
        evidence=result,
        basis="Nested result checked",
    )
    _apply(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=p,
        expected_revision=read_work(root, p, owner).revision,
        output=LinkedOutput(slot="final", artifact=result),
    )
    _apply(
        root,
        space,
        owner,
        AcceptWorkRequest,
        work_id=p,
        expected_revision=read_work(root, p, owner).revision,
        basis="Parent accepted separate nested result",
    )
    assert read_work_status(root, p, owner).status == "succeeded"
    assert read_work(root, anchor, owner).state.status == "proposed"
    independent = uuid4()
    independent_request = CreateWorkRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        work_id=independent,
        state=WorkState(
            activity_id=activity,
            goal="Independent synthetic Work outside the composition",
            expected_outputs=(OutputContract(slot="other", media_type="text/plain"),),
        ),
    )
    independent_receipt = apply_operation(root, independent_request, owner)
    _result(root, space, owner, independent, "other", b"unrelated branch result")
    archived = create_backup(root, uuid4(), owner)
    with pytest.raises(FoundationError, match="method_in_use"):
        _apply(
            root,
            space,
            owner,
            DeleteMethodVersionRequest,
            method_id=nref.method_id,
            version=nref.version,
            checksum=nref.checksum,
        )
    _apply(
        root,
        space,
        owner,
        DeleteArtifactRequest,
        artifact_id=grandchild_result.artifact_id,
        expected_revision=1,
    )
    assert complete_deletions(root, owner).live_store_sanitized
    assert not archived.package.exists()
    sanitation_steps = ["grandchild artifact: old backup purged"]
    fresh = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-c",
            "import sys; from pathlib import Path; from uuid import UUID; "
            "from zaratustra.foundation import authorize_local,read_work,read_receipt; "
            "p=Path(sys.argv[1]); a=authorize_local(p,actor='owner',source_ref='restart'); "
            "assert read_work(p,UUID(sys.argv[2]),a).state.status=='succeeded'; "
            "assert read_receipt(p,UUID(sys.argv[3]),a).operation_id==UUID(sys.argv[3])",
            str(root),
            str(independent),
            str(independent_request.operation_id),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert fresh.returncode == 0, fresh.stderr
    work_names = {g: "grandchild", n: "nested", anchor: "anchor", p: "root"}
    for work in (g, n, anchor, p):
        if work == n:
            _apply(
                root,
                space,
                owner,
                DeleteArtifactRequest,
                artifact_id=result.artifact_id,
                expected_revision=1,
            )
            assert complete_deletions(root, owner).live_store_sanitized
            sanitation_steps.append("nested own artifact")
        _apply(
            root,
            space,
            owner,
            DeleteWorkRequest,
            work_id=work,
            expected_revision=read_work(root, work, owner).revision,
        )
        assert complete_deletions(root, owner).live_store_sanitized
        assert read_receipt(root, independent_request.operation_id, owner) == independent_receipt
        assert apply_operation(root, independent_request, owner) == independent_receipt
        sanitation_steps.append(f"Work {work_names[work]}")
    for method in (nref, pref):
        _apply(
            root,
            space,
            owner,
            DeleteMethodVersionRequest,
            method_id=method.method_id,
            version=method.version,
            checksum=method.checksum,
        )
        assert complete_deletions(root, owner).live_store_sanitized
        sanitation_steps.append("Method nested" if method == nref else "Method root")
    clean = create_backup(root, uuid4(), owner)
    assert not _sqlite_contains(root / ".zara-core", deleted_marker)
    assert not _sqlite_contains(clean.package, deleted_marker)
    assert read_work(root, independent, owner).state.status == "succeeded"
    print(
        json.dumps(
            {
                "phase": "nested-own-sequential-deletion",
                "steps": sanitation_steps,
                "independent_status": read_work(root, independent, owner).state.status,
                "independent_replay": True,
                "old_backup_purged": True,
                "new_backup_clean": True,
                "http": 0,
            },
            sort_keys=True,
        )
    )
