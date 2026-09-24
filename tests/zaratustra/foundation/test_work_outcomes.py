"""Explicit schema 7 Work outcomes: failed, cancelled and stale, without a model."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_child_execution import (
    _assign,
    _assignment_revision,
    _claim,
    _codes,
    _invocation,
    _issue,
    _resource,
    _stop,
)
from tests.zaratustra.foundation.test_composition import _apply, _seed, _sqlite_contains
from zaratustra.foundation import (
    AcceptWorkRequest,
    ActivityState,
    ArtifactRef,
    CloseWorkRequest,
    CreateArtifactRequest,
    CreateCompositeWorkRequest,
    CreateDecisionRequest,
    CreateGrantRequest,
    CreateWorkRequest,
    DecisionRef,
    DecisionState,
    DeleteArtifactRequest,
    DeleteWorkRequest,
    FoundationError,
    GrantState,
    IssueChildWorkRequest,
    LinkedOutput,
    LinkWorkOutputRequest,
    LocalAuthority,
    MethodDefinition,
    MethodObligation,
    MethodRef,
    NamedInput,
    OpenWaitRequest,
    OutputContract,
    PlanChild,
    PlanCondition,
    PlanOutputBinding,
    PrepareInvocationRequest,
    RecordAttemptStopRequest,
    RecoverRequest,
    ReviseActivityRequest,
    ReviseArtifactRequest,
    ReviseDecisionRequest,
    ReviseWorkPlanRequest,
    StartAttemptRequest,
    WorkPlan,
    WorkState,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    fingerprint,
    method_checksum,
    read_execution,
    read_method_version,
    read_receipt,
    read_space,
    read_work,
    read_work_status,
    restore_backup,
    upgrade_child_execution_space,
    upgrade_plan_revision_space,
)

# Computed by the owner-accepted pass-2 code (d33b676) for the requests built below.
PASS2_CANONICAL = {
    "method": "6090453771D0AC124A8783ADDBBCA701E3971827485157E44E8E3FA3E0374746",
    "create_work": "4B973FF6A355E5B3AF8978F23A538BD55A2A9689C9BE705A7CE93F2AAB52D310",
    "create_composite_work": "77F58270FBF3C6C76FE586979A99353092B334BA547C74E5523568F5406532F6",
    "revise_work_plan": "08B8BAE2629A71322C7833C8DA6A049E6E8C36664BC266BE21E2D89E928EAA85",
    "create_decision": "F83E7EAD4B2215CB9DAD81630FC4D1AC12832E58E74D9B9E63728DC3EB0E1692",
}


def _fixed(number: int) -> UUID:
    return UUID(f"00000000-0000-4000-8000-{number:012d}")


def _pass2_canonical_values() -> dict[str, str]:
    """Rebuild fixed pass-2 requests; their canonical forms must not change."""

    source = ArtifactRef(artifact_id=_fixed(11), revision=1)
    definition = MethodDefinition(
        instruction="Check the synthetic source, then write a synthetic summary.",
        named_inputs=(OutputContract(slot="source", media_type="text/plain"),),
        named_outputs=(OutputContract(slot="final", media_type="text/plain"),),
        obligations=(
            MethodObligation(
                key="checked",
                source="synthetic method contract",
                role="a",
                slot="checked",
                media_type="text/plain",
            ),
            MethodObligation(
                key="final",
                source="synthetic method contract",
                role="b",
                slot="final",
                media_type="text/plain",
            ),
        ),
        source_ref="synthetic-method-proposal",
    )
    method = MethodRef(method_id=_fixed(21), version=1, checksum=method_checksum(definition))
    plain = CreateWorkRequest(
        operation_id=_fixed(31),
        space_id=_fixed(1),
        actor="owner",
        work_id=_fixed(41),
        state=WorkState(
            activity_id=_fixed(2),
            goal="Synthetic plain goal",
            inputs=(source,),
            constraints=("synthetic constraint",),
            expected_outputs=(OutputContract(slot="result", media_type="text/plain"),),
        ),
    )
    plan = WorkPlan(
        named_inputs=(NamedInput(slot="source", artifact=source),),
        output_bindings=(
            PlanOutputBinding(
                parent_slot="final", role="b", child_slot="final", media_type="text/plain"
            ),
        ),
        children=(
            PlanChild(
                role="a",
                work_id=_fixed(51),
                state=WorkState(
                    activity_id=_fixed(2),
                    goal="Check source",
                    inputs=(source,),
                    expected_outputs=(OutputContract(slot="checked", media_type="text/plain"),),
                ),
            ),
            PlanChild(
                role="b",
                work_id=_fixed(52),
                state=WorkState(
                    activity_id=_fixed(2),
                    goal="Write final summary",
                    expected_outputs=(OutputContract(slot="final", media_type="text/plain"),),
                ),
                readiness=PlanCondition(
                    kind="all",
                    members=(
                        PlanCondition(
                            kind="accepted_output",
                            role="a",
                            slot="checked",
                            media_type="text/plain",
                        ),
                        PlanCondition(
                            kind="decision_active", decision_id=_fixed(61), decision_revision=1
                        ),
                        PlanCondition(kind="artifact_current", artifact=source),
                    ),
                ),
            ),
        ),
        completion=PlanCondition(
            kind="any",
            members=(
                PlanCondition(kind="work_succeeded", role="a"),
                PlanCondition(kind="work_succeeded", role="b"),
            ),
        ),
        basis=(source,),
        rationale="Initial synthetic plan",
        source_ref="fictional-owner-plan",
    )
    composite = CreateCompositeWorkRequest(
        operation_id=_fixed(32),
        space_id=_fixed(1),
        actor="owner",
        work_id=_fixed(42),
        state=WorkState(
            activity_id=_fixed(2),
            goal="Prepare the synthetic packet",
            inputs=(source,),
            expected_outputs=definition.named_outputs,
            method=method,
        ),
        plan=plan,
    )
    revise = ReviseWorkPlanRequest(
        operation_id=_fixed(33),
        space_id=_fixed(1),
        actor="owner",
        work_id=_fixed(42),
        expected_plan_revision=1,
        plan=plan.model_copy(update={"rationale": "Reviewed synthetic plan"}),
    )
    decision = CreateDecisionRequest(
        operation_id=_fixed(34),
        space_id=_fixed(1),
        actor="owner",
        decision_id=_fixed(61),
        state=DecisionState(
            statement="Synthetic branch decision",
            effect="require_grant",
            actions=("space.inspect",),
            subjects=("synthetic-nobody",),
        ),
    )
    values = {"method": method_checksum(definition)}
    values.update(
        (request.kind, fingerprint(request)) for request in (plain, composite, revise, decision)
    )
    return values


def _schema7(tmp_path: Path) -> tuple[Path, UUID, LocalAuthority, UUID, UUID, UUID, UUID, UUID]:
    root, space, owner, activity, source, _ref, parent, a, b, _plan, _create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    assert upgrade_plan_revision_space(root, owner).schema_version == 7
    return root, space, owner, activity, source, parent, a, b


def _plain(
    root: Path, space: UUID, owner: LocalAuthority, activity: UUID, *inputs: ArtifactRef
) -> UUID:
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
            inputs=inputs,
            expected_outputs=(OutputContract(slot="summary", media_type="text/plain"),),
        ),
    )
    return work


def _close(
    root: Path,
    space: UUID,
    authority: LocalAuthority,
    work: UUID,
    outcome: str,
    basis: str,
    *,
    premises: tuple[ArtifactRef, ...] = (),
    decision_premises: tuple[DecisionRef, ...] = (),
) -> CloseWorkRequest:
    return CloseWorkRequest.model_validate(
        {
            "operation_id": uuid4(),
            "space_id": space,
            "actor": authority.actor,
            "work_id": work,
            "expected_revision": read_work(root, work, authority).revision,
            "outcome": outcome,
            "basis": basis,
            "premises": premises,
            "decision_premises": decision_premises,
        }
    )


def test_schema_7_upgrade_is_explicit_and_keeps_pass2_replay(tmp_path: Path) -> None:
    assert _pass2_canonical_values() == PASS2_CANONICAL

    root, space, owner, activity, _source, ref, _parent, a, _b, _plan, create = _seed(tmp_path)
    create_receipt = read_receipt(root, create.operation_id, owner)
    with pytest.raises(FoundationError, match="unsupported_schema"):
        upgrade_plan_revision_space(root, owner)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    plain = _plain(root, space, owner, activity)
    for work in (plain, a):
        with pytest.raises(FoundationError, match="unsupported_schema"):
            apply_operation(root, _close(root, space, owner, work, "failed", "Too early"), owner)
    assert read_space(root).schema_version == 6
    assert read_work(root, plain, owner).state.status == "proposed"

    assert upgrade_plan_revision_space(root, owner).schema_version == 7
    assert upgrade_plan_revision_space(root, owner).schema_version == 7
    assert apply_operation(root, create, owner) == create_receipt
    assert read_method_version(root, ref, owner).reference == ref
    assert read_work_status(root, a, owner).status == "proposed"


def test_failed_plain_work_is_terminal_with_exact_history_and_rights(tmp_path: Path) -> None:
    root, space, owner, activity, source, _parent, _a, _b = _schema7(tmp_path)
    work = _plain(root, space, owner, activity, ArtifactRef(artifact_id=source, revision=1))
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest,
        grant_id=uuid4(),
        state=GrantState(grantee="worker", actions=("work.write", "record.read", "receipt.read")),
    )
    worker = authorize_local(root, actor="worker", source_ref="fictional-worker")
    resource = _resource(root, space, owner, work, "workspace-plain")

    def start() -> None:
        _apply(
            root,
            space,
            owner,
            StartAttemptRequest,
            attempt_id=uuid4(),
            work_id=work,
            expected_work_revision=read_work(root, work, owner).revision,
            resource_id=resource,
            expected_resource_revision=1,
            session_id=uuid4(),
        )

    start()
    assert read_work_status(root, work, owner).status == "running"
    with pytest.raises(FoundationError, match="permission_denied"):
        apply_operation(root, _close(root, space, worker, work, "failed", "Worker verdict"), worker)
    assert read_work(root, work, owner).revision == 1
    assert [item.status for item in read_execution(root, work, owner).attempts] == ["active"]

    request = _close(root, space, owner, work, "failed", "Synthetic check found the goal unmet")
    receipt = apply_operation(root, request, owner)
    assert receipt.result == {"record_id": str(work), "revision": 2, "status": "failed"}
    assert "goal unmet" not in json.dumps(receipt.model_dump(mode="json"))
    # The interactive Attempt is interrupted in the same transaction as the outcome.
    assert [item.status for item in read_execution(root, work, owner).attempts] == ["interrupted"]
    with pytest.raises(FoundationError, match="work_closed"):
        start()
    assert apply_operation(root, request, owner) == receipt
    with pytest.raises(FoundationError, match="stale_revision"):
        apply_operation(root, request.model_copy(update={"operation_id": uuid4()}), owner)
    artifact = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=artifact,
        media_type="text/plain",
        content=b"late synthetic summary",
    )
    with pytest.raises(FoundationError, match="work_closed"):
        _apply(
            root,
            space,
            owner,
            LinkWorkOutputRequest,
            work_id=work,
            expected_revision=2,
            output=LinkedOutput(
                slot="summary", artifact=ArtifactRef(artifact_id=artifact, revision=1)
            ),
        )
    with pytest.raises(FoundationError, match="work_closed"):
        _apply(
            root, space, owner, AcceptWorkRequest, work_id=work, expected_revision=2, basis="Late"
        )
    with pytest.raises(FoundationError, match="work_closed"):
        apply_operation(root, _close(root, space, owner, work, "cancelled", "Again"), owner)

    assert read_work(root, work, owner, revision=1).state.status == "proposed"
    failed = read_work(root, work, owner, revision=2).state
    assert failed.status == "failed" and failed.closure is not None
    assert failed.closure.operation_id == request.operation_id
    assert failed.closure.basis == "Synthetic check found the goal unmet"
    assert failed.closure.authority_source == "fictional-trusted-console"
    status = read_work_status(root, work, owner)
    assert status.status == "failed" and status.reasons == ()


def _waiting_child(
    root: Path, space: UUID, owner: LocalAuthority, parent: UUID, child: UUID, name: str
) -> tuple[UUID, UUID, UUID]:
    _issue(root, space, owner, parent, child)
    resource = _resource(root, space, owner, child, name)
    attempt, session, _request, _receipt = _assign(root, space, owner, child, resource)
    _claim(root, space, owner, child, attempt, session)
    return attempt, session, resource


def test_cancel_assigned_child_holds_execution_until_stop_is_recorded(tmp_path: Path) -> None:
    root, space, owner, _activity, _source, parent, a, _b = _schema7(tmp_path)
    attempt, session, resource = _waiting_child(root, space, owner, parent, a, "workspace-a")
    wait = uuid4()
    _apply(
        root,
        space,
        owner,
        OpenWaitRequest,
        wait_id=wait,
        attempt_id=attempt,
        work_id=a,
        session_id=session,
        expected_assignment_revision=_assignment_revision(root, owner, a, attempt),
        question="Which synthetic line is authoritative?",
        expected_actor="owner",
        remainder="Finish the synthetic check",
    )
    assert read_work_status(root, a, owner).status == "waiting"
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest,
        grant_id=uuid4(),
        state=GrantState(grantee="worker", actions=("work.accept", "record.read", "receipt.read")),
    )
    worker = authorize_local(root, actor="worker", source_ref="fictional-worker")
    with pytest.raises(FoundationError, match="permission_denied"):
        apply_operation(root, _close(root, space, worker, a, "cancelled", "No Method use"), worker)
    assert read_work_status(root, a, owner).status == "waiting"

    apply_operation(root, _close(root, space, owner, a, "cancelled", "Branch not needed"), owner)
    snapshot = read_execution(root, a, owner)
    assert [item.status for item in snapshot.assignments] == ["stop_requested"]
    assert [item.status for item in snapshot.waits] == ["closed"]
    assert {item.status for item in snapshot.outbox} == {"cancelled"}
    assert snapshot.status is not None and snapshot.status.status == "cancelled"
    assert _codes(snapshot.status) == ["stop_requested"]
    assert snapshot.status.reasons[0].record_id == attempt
    with pytest.raises(FoundationError, match="work_closed"):
        _apply(
            root,
            space,
            owner,
            PrepareInvocationRequest,
            invocation_id=uuid4(),
            attempt_id=attempt,
            work_id=a,
            session_id=session,
            purpose="content",
            provider="synthetic",
            model="synthetic",
            transport="http-sse",
            request_sha256="A" * 64,
            request_bytes=10,
            reserve_units=5,
        )
    _stop(root, space, owner, a, attempt, session)
    stopped = read_work_status(root, a, owner)
    assert stopped.status == "cancelled" and stopped.reasons == ()
    assert read_work(root, a, owner).state.closure is not None
    with pytest.raises(FoundationError, match="work_closed"):
        _assign(root, space, owner, a, resource, previous=attempt)
    assert [item.question for item in read_execution(root, a, owner).waits] == [
        "Which synthetic line is authoritative?"
    ]


def test_cancelled_child_with_sent_call_keeps_unknown_reserve_and_resource(tmp_path: Path) -> None:
    root, space, owner, activity, _source, parent, a, _b = _schema7(tmp_path)
    attempt, session, _resource_id = _waiting_child(root, space, owner, parent, a, "workspace-a")
    _invocation(root, space, owner, a, attempt, session, finish=False)
    apply_operation(root, _close(root, space, owner, a, "cancelled", "Stop this branch"), owner)
    held = read_execution(root, a, owner)
    assert [item.status for item in held.invocations] == ["unknown"]
    assert held.held_units == 5
    _apply(
        root,
        space,
        owner,
        RecordAttemptStopRequest,
        attempt_id=attempt,
        work_id=a,
        session_id=session,
        expected_assignment_revision=_assignment_revision(root, owner, a, attempt),
        outcome="unknown",
    )
    status = read_work_status(root, a, owner)
    assert status.status == "cancelled" and _codes(status) == ["outcome_unknown"]
    assert read_execution(root, a, owner).held_units == 5
    other = _plain(root, space, owner, activity)
    other_resource = _resource(root, space, owner, other, "workspace-a")
    with pytest.raises(FoundationError, match="resource_busy"):
        _assign(root, space, owner, other, other_resource)
    assert read_execution(root, other, owner).attempts == ()


def test_stale_plain_work_names_only_changed_own_premises(tmp_path: Path) -> None:
    root, space, owner, activity, source, _parent, _a, _b = _schema7(tmp_path)
    source_v1 = ArtifactRef(artifact_id=source, revision=1)
    work = _plain(root, space, owner, activity, source_v1)
    unrelated = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=unrelated,
        media_type="text/plain",
        content=b"unrelated synthetic note",
    )
    with pytest.raises(FoundationError, match="premise_current"):
        apply_operation(
            root, _close(root, space, owner, work, "stale", "Premise", premises=(source_v1,)), owner
        )
    _apply(
        root,
        space,
        owner,
        ReviseArtifactRequest,
        artifact_id=unrelated,
        expected_revision=1,
        media_type="text/plain",
        content=b"unrelated synthetic note revised",
    )
    with pytest.raises(FoundationError, match="premise_mismatch"):
        apply_operation(
            root,
            _close(
                root,
                space,
                owner,
                work,
                "stale",
                "Not mine",
                premises=(ArtifactRef(artifact_id=unrelated, revision=1),),
            ),
            owner,
        )
    assert read_work_status(root, work, owner).status == "ready"
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
    assert _codes(read_work_status(root, work, owner)) == ["stale_input"]
    apply_operation(
        root,
        _close(root, space, owner, work, "stale", "Source changed", premises=(source_v1,)),
        owner,
    )
    closed = read_work(root, work, owner).state
    assert closed.status == "stale" and closed.closure is not None
    assert closed.closure.premises == (source_v1,)
    assert read_work_status(root, work, owner).status == "stale"


def _decision_child(
    root: Path,
    space: UUID,
    owner: LocalAuthority,
    create: CreateCompositeWorkRequest,
    plan: WorkPlan,
) -> tuple[UUID, UUID, UUID, DecisionState]:
    decision = uuid4()
    decision_state = DecisionState(
        statement="Synthetic branch decision",
        effect="require_grant",
        actions=("space.inspect",),
        subjects=("synthetic-nobody",),
    )
    _apply(root, space, owner, CreateDecisionRequest, decision_id=decision, state=decision_state)
    parent, a, b = uuid4(), uuid4(), uuid4()
    readiness = PlanCondition(
        kind="all",
        members=(
            PlanCondition(kind="work_succeeded", role="a"),
            PlanCondition(kind="decision_active", decision_id=decision, decision_revision=1),
        ),
    )
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
                            plan.children[1].model_copy(
                                update={"work_id": b, "readiness": readiness}
                            ),
                        )
                    }
                ),
            }
        ),
        owner,
    )
    return decision, parent, b, decision_state


def test_stale_child_names_a_revised_decision_leaf(tmp_path: Path) -> None:
    root, space, owner, _activity, _source, _ref, _parent, _a, _b, plan, create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    assert upgrade_plan_revision_space(root, owner).schema_version == 7
    decision, _parent2, b, decision_state = _decision_child(root, space, owner, create, plan)
    leaf = DecisionRef(decision_id=decision, revision=1)
    with pytest.raises(FoundationError, match="premise_current"):
        apply_operation(
            root,
            _close(root, space, owner, b, "stale", "Still valid", decision_premises=(leaf,)),
            owner,
        )
    _apply(
        root,
        space,
        owner,
        ReviseDecisionRequest,
        decision_id=decision,
        expected_revision=1,
        state=decision_state.model_copy(update={"status": "revoked"}),
    )
    # Core never records stale by itself; until the explicit outcome the leaf blocks.
    before = read_work_status(root, b, owner)
    assert before.status == "blocked"
    assert ("stale_basis", decision, 1) in [
        (item.code, item.record_id, item.revision) for item in before.reasons
    ]
    assert read_work(root, b, owner).state.status == "proposed"
    apply_operation(
        root,
        _close(
            root, space, owner, b, "stale", "Branch decision revoked", decision_premises=(leaf,)
        ),
        owner,
    )
    closed = read_work(root, b, owner).state
    assert closed.closure is not None and closed.closure.decision_premises == (leaf,)
    assert read_work_status(root, b, owner).status == "stale"


def test_stale_parent_needs_closed_children_and_its_own_premise(tmp_path: Path) -> None:
    root, space, owner, _activity, source, parent, a, b = _schema7(tmp_path)
    source_v1 = ArtifactRef(artifact_id=source, revision=1)
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
    before = read_work_status(root, parent, owner)
    assert before.status == "blocked"
    assert ("stale_basis", source, 1) in [
        (item.code, item.record_id, item.revision) for item in before.reasons
    ]
    stale_parent = _close(
        root, space, owner, parent, "stale", "Source changed", premises=(source_v1,)
    )
    with pytest.raises(FoundationError, match="open_children") as waiting:
        apply_operation(root, stale_parent, owner)
    assert f"a:{a}" in waiting.value.detail and f"b:{b}" in waiting.value.detail
    apply_operation(
        root, _close(root, space, owner, a, "stale", "Input changed", premises=(source_v1,)), owner
    )
    apply_operation(root, _close(root, space, owner, b, "cancelled", "Nothing to write"), owner)
    unrelated = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=unrelated,
        media_type="text/plain",
        content=b"unrelated synthetic note",
    )
    with pytest.raises(FoundationError, match="premise_mismatch"):
        apply_operation(
            root,
            _close(
                root,
                space,
                owner,
                parent,
                "stale",
                "Not the parent's premise",
                premises=(ArtifactRef(artifact_id=unrelated, revision=1),),
            ),
            owner,
        )
    apply_operation(root, stale_parent, owner)
    assert read_work_status(root, parent, owner).status == "stale"
    assert read_work(root, parent, owner).state.closure is not None


def test_sanitized_plan_keeps_membership_but_not_unverifiable_premises(tmp_path: Path) -> None:
    root, space, owner, _activity, _source, _ref, parent, a, b, plan, _create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    assert upgrade_plan_revision_space(root, owner).schema_version == 7
    extra = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=extra,
        media_type="text/plain",
        content=b"synthetic extra basis",
    )
    extra_v1 = ArtifactRef(artifact_id=extra, revision=1)
    _apply(
        root,
        space,
        owner,
        ReviseWorkPlanRequest,
        work_id=parent,
        expected_plan_revision=1,
        plan=plan.model_copy(update={"basis": plan.basis + (extra_v1,)}),
    )
    _apply(root, space, owner, DeleteArtifactRequest, artifact_id=extra, expected_revision=1)
    assert complete_deletions(root, owner).live_store_sanitized
    # The current plan is sanitized; its basis revision can no longer be verified.
    with pytest.raises(FoundationError, match="premise_mismatch"):
        apply_operation(
            root,
            _close(root, space, owner, b, "stale", "Basis deleted", premises=(extra_v1,)),
            owner,
        )
    apply_operation(root, _close(root, space, owner, a, "cancelled", "Plan unreadable"), owner)
    apply_operation(root, _close(root, space, owner, b, "failed", "Plan unreadable"), owner)
    apply_operation(root, _close(root, space, owner, parent, "failed", "Plan unreadable"), owner)
    assert [read_work_status(root, item, owner).status for item in (a, b, parent)] == [
        "cancelled",
        "failed",
        "failed",
    ]


def test_closed_child_blocks_dependents_and_parent_waits_for_open_children(tmp_path: Path) -> None:
    root, space, owner, activity, _source, parent, a, b = _schema7(tmp_path)
    _issue(root, space, owner, parent, a)
    apply_operation(root, _close(root, space, owner, a, "failed", "Check failed"), owner)
    with pytest.raises(FoundationError, match="dependency_closed") as refused:
        _issue(root, space, owner, parent, b)
    assert str(a) in refused.value.detail
    status = read_work_status(root, b, owner)
    assert status.status == "blocked"
    assert [(item.code, item.role, item.record_id) for item in status.reasons] == [
        ("dependency_closed", "a", a)
    ]
    # Part 3.2: the failed branch is reviewed by address, not a global parent failure.
    parent_status = read_work_status(root, parent, owner)
    assert parent_status.status == "ready"
    assert [(item.code, item.role, item.record_id) for item in parent_status.reasons] == [
        ("branch_review", "a", a)
    ]
    with pytest.raises(FoundationError, match="open_children") as waiting:
        apply_operation(root, _close(root, space, owner, parent, "failed", "Too early"), owner)
    assert f"b:{b}" in waiting.value.detail and str(a) not in waiting.value.detail
    assert read_work(root, parent, owner).state.status == "proposed"
    completed = ActivityState(
        title="Synthetic packet", goal="Prepare a synthetic packet", status="completed"
    )
    with pytest.raises(FoundationError, match="dependent_work"):
        _apply(
            root,
            space,
            owner,
            ReviseActivityRequest,
            activity_id=activity,
            expected_revision=1,
            state=completed,
        )

    apply_operation(
        root, _close(root, space, owner, b, "cancelled", "Depends on failed check"), owner
    )
    apply_operation(
        root, _close(root, space, owner, parent, "failed", "Packet not produced"), owner
    )
    assert read_work_status(root, parent, owner).status == "failed"
    _apply(
        root,
        space,
        owner,
        ReviseActivityRequest,
        activity_id=activity,
        expected_revision=1,
        state=completed,
    )


def test_any_condition_closes_only_when_every_member_is_closed(tmp_path: Path) -> None:
    root, space, owner, _activity, _source, _ref, _parent, _a, _b, plan, create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    assert upgrade_plan_revision_space(root, owner).schema_version == 7
    parent, a, b, c = uuid4(), uuid4(), uuid4(), uuid4()
    first, second = plan.children
    alternative = PlanChild(
        role="c",
        work_id=c,
        state=WorkState(
            activity_id=first.state.activity_id,
            goal="Alternative synthetic check",
            expected_outputs=(OutputContract(slot="checked", media_type="text/plain"),),
        ),
    )
    readiness = PlanCondition(
        kind="any",
        members=(
            PlanCondition(kind="work_succeeded", role="a"),
            PlanCondition(kind="work_succeeded", role="c"),
        ),
    )
    apply_operation(
        root,
        create.model_copy(
            update={
                "operation_id": uuid4(),
                "work_id": parent,
                "plan": plan.model_copy(
                    update={
                        "children": (
                            first.model_copy(update={"work_id": a}),
                            second.model_copy(update={"work_id": b, "readiness": readiness}),
                            alternative,
                        )
                    }
                ),
            }
        ),
        owner,
    )
    apply_operation(root, _close(root, space, owner, a, "failed", "First check failed"), owner)
    with pytest.raises(FoundationError, match="dependency_open"):
        _issue(root, space, owner, parent, b)
    status = read_work_status(root, b, owner)
    # The closed alternative is hidden while another member may still become true.
    assert status.status == "blocked"
    assert [(item.code, item.role) for item in status.reasons] == [("dependency_open", "c")]
    apply_operation(root, _close(root, space, owner, c, "cancelled", "No alternative"), owner)
    with pytest.raises(FoundationError, match="dependency_closed"):
        _issue(root, space, owner, parent, b)
    assert [(item.code, item.role) for item in read_work_status(root, b, owner).reasons] == [
        ("dependency_closed", "a"),
        ("dependency_closed", "c"),
    ]
    with pytest.raises(FoundationError, match="work_closed"):
        _apply(
            root,
            space,
            owner,
            IssueChildWorkRequest,
            parent_work_id=parent,
            work_id=c,
            expected_plan_revision=1,
            expected_work_revision=2,
        )


def test_outcomes_survive_restore_and_are_deleted_with_their_work(tmp_path: Path) -> None:
    root, space, owner, activity, source, parent, a, b = _schema7(tmp_path)
    marker = f"synthetic closure basis {uuid4()}"
    work = _plain(root, space, owner, activity)
    apply_operation(root, _close(root, space, owner, work, "failed", marker), owner)
    attempt, _session, resource = _waiting_child(root, space, owner, parent, a, "workspace-a")
    apply_operation(root, _close(root, space, owner, a, "cancelled", "Branch dropped"), owner)
    assert _codes(read_work_status(root, a, owner)) == ["stop_requested"]
    source_v1 = ArtifactRef(artifact_id=source, revision=1)
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
    # B's premise is the parent's plan basis, not one of B's own inputs.
    apply_operation(
        root,
        _close(root, space, owner, b, "stale", "Plan basis changed", premises=(source_v1,)),
        owner,
    )
    old_backup = create_backup(root, uuid4(), owner)
    restored_root = tmp_path / "restored"
    restored_root.mkdir()
    restore_backup(
        old_backup.package, restored_root, authorize_recovery(actor="owner", source_ref="restore")
    )
    apply_operation(
        restored_root,
        RecoverRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        authorize_recovery(actor="owner", source_ref="fresh-recovery"),
    )
    restored_owner = authorize_local(restored_root, actor="owner", source_ref="reopened")
    assert read_space(restored_root).schema_version == 7
    restored = read_work(restored_root, work, restored_owner).state
    assert restored.status == "failed" and restored.closure is not None
    assert restored.closure.basis == marker
    assert read_work_status(restored_root, b, restored_owner).status == "stale"
    # Recovery interrupts the held assignment; the outcome stays and nothing resumes.
    history = read_execution(restored_root, a, restored_owner)
    assert [item.status for item in history.assignments] == ["interrupted"]
    assert history.status is not None and history.status.status == "cancelled"
    assert history.status.reasons == ()
    with pytest.raises(FoundationError, match="work_closed"):
        _assign(restored_root, space, restored_owner, a, resource, previous=attempt)

    reopened = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; from uuid import UUID; "
            "from zaratustra.foundation import authorize_local, read_work, read_work_status; "
            "p=Path(sys.argv[1]); o=authorize_local(p, actor='owner', source_ref='restart'); "
            "w=read_work(p, UUID(sys.argv[2]), o).state; "
            "print(w.status, w.closure.outcome, read_work_status(p, UUID(sys.argv[3]), o).status)",
            str(root),
            str(work),
            str(b),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert reopened.returncode == 0, reopened.stderr
    assert reopened.stdout.split() == ["failed", "failed", "stale"]

    _apply(root, space, owner, DeleteArtifactRequest, artifact_id=source, expected_revision=2)
    assert source_v1 in read_work(root, b, owner).unavailable_refs
    assert source_v1 not in read_work(root, b, owner).state.inputs
    _apply(root, space, owner, DeleteWorkRequest, work_id=work, expected_revision=2)
    assert complete_deletions(root, owner).live_store_sanitized
    assert not old_backup.package.exists()
    assert not _sqlite_contains(root / ".zara-core", marker)
    fresh = create_backup(root, uuid4(), owner)
    assert not _sqlite_contains(fresh.package, marker)
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_work(root, work, owner)
    # B named the plan basis source@1 and A's input is source@1: both bases depended on it.
    for child in (b, a):
        closure = read_work(root, child, owner).state.closure
        assert closure is not None and closure.basis is None
    assert read_work(root, b, owner).state.status == "stale"
    assert read_work(root, a, owner).state.status == "cancelled"
    assert read_work(root, parent, owner).state.status == "proposed"


def _artifact(root: Path, space: UUID, owner: LocalAuthority, *contents: bytes) -> UUID:
    """One Artifact whose revisions 1..n hold the given synthetic contents."""

    artifact = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=artifact,
        media_type="text/plain",
        content=contents[0],
    )
    for revision, content in enumerate(contents[1:], start=1):
        _apply(
            root,
            space,
            owner,
            ReviseArtifactRequest,
            artifact_id=artifact,
            expected_revision=revision,
            media_type="text/plain",
            content=content,
        )
    return artifact


def test_deleted_artifact_sanitizes_only_dependent_closure_bases(tmp_path: Path) -> None:
    root, space, owner, activity, _source, _parent, _a, _b = _schema7(tmp_path)
    marker = f"synthetic premise quote {uuid4()}"
    input_marker = f"synthetic input quote {uuid4()}"
    kept = f"synthetic independent basis {uuid4()}"
    x = _artifact(root, space, owner, b"synthetic draft", marker.encode(), b"synthetic plain")
    x_v2, x_v3 = ArtifactRef(artifact_id=x, revision=2), ArtifactRef(artifact_id=x, revision=3)
    y = _artifact(root, space, owner, b"synthetic other", b"synthetic other revised")
    y_v1 = ArtifactRef(artifact_id=y, revision=1)
    stale = _plain(root, space, owner, activity, x_v2)
    failed = _plain(root, space, owner, activity, x_v3)
    independent_stale = _plain(root, space, owner, activity, y_v1)
    independent_failed = _plain(root, space, owner, activity)
    dependent = [
        _close(root, space, owner, stale, "stale", f"X@2 said: {marker}", premises=(x_v2,)),
        _close(root, space, owner, failed, "failed", f"X@3 lacked: {input_marker}"),
    ]
    independent = [
        _close(root, space, owner, independent_stale, "stale", kept, premises=(y_v1,)),
        _close(root, space, owner, independent_failed, "failed", kept),
    ]
    receipts = [apply_operation(root, request, owner) for request in dependent + independent]
    old_backup = create_backup(root, uuid4(), owner)

    _apply(root, space, owner, DeleteArtifactRequest, artifact_id=x, expected_revision=3)
    assert complete_deletions(root, owner).live_store_sanitized
    assert not old_backup.package.exists()

    for work, request, address in ((stale, dependent[0], x_v2), (failed, dependent[1], x_v3)):
        revision = read_work(root, work, owner)
        closure = revision.state.closure
        # The terminal outcome stays; the deleted basis is never returned as available.
        assert revision.state.status == request.outcome and closure is not None
        assert closure.outcome == request.outcome and closure.basis is None
        assert closure.premises == request.premises and address in revision.unavailable_refs
        assert read_work_status(root, work, owner).status == request.outcome
        assert read_work(root, work, owner, revision=1).state.status == "proposed"
        with pytest.raises(FoundationError, match="history_unavailable"):
            apply_operation(root, request, owner)
        with pytest.raises(FoundationError, match="not_found"):
            read_receipt(root, request.operation_id, owner)
        with pytest.raises(FoundationError, match="work_closed"):
            apply_operation(root, _close(root, space, owner, work, "cancelled", "Again"), owner)
    for work, request, receipt in zip(
        (independent_stale, independent_failed), independent, receipts[2:], strict=True
    ):
        closure = read_work(root, work, owner).state.closure
        assert closure is not None and closure.basis == kept
        assert apply_operation(root, request, owner) == receipt

    for text in (marker, input_marker):
        assert not _sqlite_contains(root / ".zara-core", text)
    assert _sqlite_contains(root / ".zara-core", kept)
    fresh = create_backup(root, uuid4(), owner)
    assert not _sqlite_contains(fresh.package, marker)
    assert not _sqlite_contains(fresh.package, input_marker)
    assert _sqlite_contains(fresh.package, kept)
    restarted = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; from uuid import UUID; "
            "from zaratustra.foundation import authorize_local, read_work; "
            "p=Path(sys.argv[1]); o=authorize_local(p, actor='owner', source_ref='restart'); "
            "w=read_work(p, UUID(sys.argv[2]), o).state; "
            "print(w.status, w.closure.outcome, w.closure.basis is None)",
            str(root),
            str(stale),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert restarted.returncode == 0, restarted.stderr
    assert restarted.stdout.split() == ["stale", "stale", "True"]


def test_stale_refuses_premise_addresses_that_never_existed(tmp_path: Path) -> None:
    root, space, owner, _activity, source, _ref, _parent, _a, _b, plan, create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    assert upgrade_plan_revision_space(root, owner).schema_version == 7
    never_revision = ArtifactRef(artifact_id=source, revision=999)
    never_artifact = ArtifactRef(artifact_id=uuid4(), revision=1)
    never_decision = DecisionRef(decision_id=uuid4(), revision=1)
    revoked = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateDecisionRequest,
        decision_id=revoked,
        state=DecisionState(
            statement="Synthetic decision recorded as revoked",
            effect="require_grant",
            actions=("space.inspect",),
            subjects=("synthetic-nobody",),
            status="revoked",
        ),
    )
    never_active = DecisionRef(decision_id=revoked, revision=1)
    parent, a, b = uuid4(), uuid4(), uuid4()
    first, second = plan.children
    readiness = PlanCondition(
        kind="any",
        members=(
            PlanCondition(
                kind="artifact_current", artifact=ArtifactRef(artifact_id=source, revision=1)
            ),
            PlanCondition(kind="artifact_current", artifact=never_revision),
            PlanCondition(kind="artifact_current", artifact=never_artifact),
            PlanCondition(
                kind="decision_active",
                decision_id=never_decision.decision_id,
                decision_revision=never_decision.revision,
            ),
            PlanCondition(
                kind="decision_active",
                decision_id=never_active.decision_id,
                decision_revision=never_active.revision,
            ),
        ),
    )
    apply_operation(
        root,
        create.model_copy(
            update={
                "operation_id": uuid4(),
                "work_id": parent,
                "plan": plan.model_copy(
                    update={
                        "children": (
                            first.model_copy(update={"work_id": a}),
                            second.model_copy(update={"work_id": b, "readiness": readiness}),
                        )
                    }
                ),
            }
        ),
        owner,
    )
    attempt, session, _resource_id = _waiting_child(root, space, owner, parent, b, "workspace-b")
    _apply(
        root,
        space,
        owner,
        OpenWaitRequest,
        wait_id=uuid4(),
        attempt_id=attempt,
        work_id=b,
        session_id=session,
        expected_assignment_revision=_assignment_revision(root, owner, b, attempt),
        question="Which synthetic line is authoritative?",
        expected_actor="owner",
        remainder="Finish the synthetic summary",
    )
    before = read_execution(root, b, owner)
    for premises, decision_premises in (
        ((never_revision,), ()),
        ((never_artifact,), ()),
        ((), (never_decision,)),
        ((), (never_active,)),
    ):
        with pytest.raises(FoundationError, match="premise_unknown"):
            apply_operation(
                root,
                _close(
                    root,
                    space,
                    owner,
                    b,
                    "stale",
                    "Named premise never held",
                    premises=premises,
                    decision_premises=decision_premises,
                ),
                owner,
            )
    after = read_execution(root, b, owner)
    # A refused outcome changes neither the Work nor its execution.
    assert after.work == before.work and after.work.state.status == "proposed"
    assert after.assignments == before.assignments and after.waits == before.waits
    assert after.outbox == before.outbox and after.invocations == before.invocations
    assert after.status == before.status and after.status is not None
    assert after.status.status == "waiting"


def test_stale_accepts_a_deleted_known_premise(tmp_path: Path) -> None:
    root, space, owner, activity, _source, _parent, _a, _b = _schema7(tmp_path)
    z = _artifact(root, space, owner, b"synthetic premise")
    z_v1 = ArtifactRef(artifact_id=z, revision=1)
    work = _plain(root, space, owner, activity, z_v1)
    _apply(root, space, owner, DeleteArtifactRequest, artifact_id=z, expected_revision=1)
    assert complete_deletions(root, owner).live_store_sanitized
    # Retained revision metadata proves Z@1 existed; its content is not restored.
    apply_operation(
        root, _close(root, space, owner, work, "stale", "Premise deleted", premises=(z_v1,)), owner
    )
    closed = read_work(root, work, owner)
    assert closed.state.status == "stale" and closed.state.closure is not None
    assert closed.state.closure.premises == (z_v1,) and z_v1 in closed.unavailable_refs
