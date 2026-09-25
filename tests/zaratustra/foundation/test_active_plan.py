"""A started plan is revised only with an explicit decision for every node.

Part 3.6 of Stage 6 pass 3, model-free through public Core operations.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import Literal, NamedTuple
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from tests.zaratustra.foundation.test_applicability import (
    Case,
    Space,
    _accept_request,
    _confirm,
    _confirm_request,
    _issue,
    _issue_request,
    _link_request,
    _refused,
    _space,
    _statuses,
    _statuses_in_new_process,
)
from tests.zaratustra.foundation.test_composition import _apply, _result, _sqlite_contains
from zaratustra.foundation import (
    AcceptWorkRequest,
    ArtifactRef,
    CreateArtifactRequest,
    CreateCompositeWorkRequest,
    CreateDecisionRequest,
    CreateGrantRequest,
    CreateMethodVersionRequest,
    DecisionRef,
    DeleteArtifactRequest,
    DeleteWorkRequest,
    ExceptionState,
    FoundationError,
    GrantState,
    LinkedOutput,
    LinkWorkOutputRequest,
    MethodDefinition,
    MethodObligation,
    MethodRef,
    NamedInput,
    NodeClosure,
    ObligationTarget,
    OperationReceipt,
    OutputContract,
    PlanChild,
    PlanCondition,
    PlanNode,
    PlanNodeDecision,
    PlanOutputBinding,
    RecoverRequest,
    ReviseActivePlanRequest,
    ReviseArtifactRequest,
    ReviseWorkPlanRequest,
    RoleFilling,
    StatusReason,
    WaiveObligationRequest,
    WorkPlan,
    WorkState,
    WorkStatus,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    read_artifact,
    read_execution,
    read_obligation,
    read_plan_nodes,
    read_receipt,
    read_role_history,
    read_space,
    read_work,
    read_work_plan,
    read_work_status,
    restore_backup,
)

type Leaving = Literal["cancel", "stale"]


class WPlan(NamedTuple):
    """The W20-W23 example: W20 and W21 run, W22 is prepared on constraint C@1."""

    case: Case
    plan: WorkPlan
    constraint: UUID
    method: MethodRef


def _node(
    activity: UUID,
    role: str,
    slot: str,
    *,
    inputs: tuple[ArtifactRef, ...] = (),
    readiness: PlanCondition | None = None,
    goal: str | None = None,
) -> PlanChild:
    return PlanChild(
        role=role,
        work_id=uuid4(),
        state=WorkState(
            activity_id=activity,
            goal=goal or f"Synthetic {role}",
            inputs=inputs,
            expected_outputs=(OutputContract(slot=slot, media_type="text/plain"),),
        ),
        readiness=readiness,
    )


def _current(artifact: ArtifactRef) -> PlanCondition:
    return PlanCondition(kind="artifact_current", artifact=artifact)


def _accepted(role: str, slot: str) -> PlanCondition:
    return PlanCondition(kind="accepted_output", role=role, slot=slot, media_type="text/plain")


def _w_plan(tmp_path: Path) -> WPlan:
    setup = _space(tmp_path)
    root, space, owner, activity, source = (
        setup.root,
        setup.space,
        setup.owner,
        setup.activity,
        setup.source,
    )
    constraint = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=constraint,
        media_type="text/plain",
        content=b"synthetic constraint, first revision",
    )
    definition = MethodDefinition(
        instruction="Experiment and prototype in parallel, then integrate under the constraint.",
        named_inputs=(OutputContract(slot="source", media_type="text/plain"),),
        named_outputs=(OutputContract(slot="final", media_type="text/plain"),),
        obligations=tuple(
            MethodObligation(
                key=key,
                source="synthetic revision contract",
                role=role,
                slot=slot,
                media_type="text/plain",
            )
            for key, role, slot in (
                ("finding", "experiment", "finding"),
                ("integration", "integration", "final"),
            )
        ),
        source_ref="synthetic-revision-method",
    )
    method_id = uuid4()
    created = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=method_id,
        version=1,
        definition=definition,
    )
    method = MethodRef(method_id=method_id, version=1, checksum=str(created.result["checksum"]))
    plan = WorkPlan(
        named_inputs=(NamedInput(slot="source", artifact=source),),
        output_bindings=(
            PlanOutputBinding(
                parent_slot="final", role="integration", child_slot="final", media_type="text/plain"
            ),
        ),
        children=(
            _node(activity, "experiment", "finding", inputs=(source,)),
            _node(activity, "prototype", "ui", inputs=(source,)),
            _node(
                activity,
                "integration",
                "final",
                readiness=_current(ArtifactRef(artifact_id=constraint, revision=1)),
            ),
        ),
        completion=PlanCondition(
            kind="all",
            members=tuple(
                PlanCondition(kind="work_succeeded", role=role)
                for role in ("experiment", "prototype", "integration")
            ),
        ),
        basis=(source,),
        rationale="Parallel experiment and prototype; integration prepared in advance",
        source_ref="fictional-owner-plan",
    )
    parent = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateCompositeWorkRequest,
        work_id=parent,
        state=WorkState(
            activity_id=activity,
            goal="Integrate the synthetic experiment and prototype",
            inputs=(source,),
            expected_outputs=definition.named_outputs,
            method=method,
        ),
        plan=plan,
    )
    case = Case(
        root, space, owner, activity, parent, {child.role: child.work_id for child in plan.children}
    )
    return WPlan(case, plan, constraint, method)


def _seeded(setup: Space) -> tuple[Case, WorkPlan]:
    """The pass 1 composite of the shared seed: A checks, B summarizes after A."""

    plan = read_work_plan(setup.root, setup.seeded, setup.owner).plan
    case = Case(
        setup.root,
        setup.space,
        setup.owner,
        setup.activity,
        setup.seeded,
        {child.role: child.work_id for child in plan.children},
    )
    return case, plan


def _keep(child: PlanChild) -> PlanNodeDecision:
    return PlanNodeDecision(role=child.role, decision="keep", work_id=child.work_id)


def _add(child: PlanChild) -> PlanNodeDecision:
    return PlanNodeDecision(role=child.role, decision="add", work_id=child.work_id)


def _release(child: PlanChild) -> PlanNodeDecision:
    return PlanNodeDecision(role=child.role, decision="release", work_id=child.work_id)


def _closure(
    case: Case,
    work: UUID,
    outcome: Literal["cancelled", "stale"],
    *,
    premises: tuple[ArtifactRef, ...] = (),
    basis: str | None = None,
) -> NodeClosure:
    return NodeClosure(
        expected_revision=read_work(case.root, work, case.owner).revision,
        outcome=outcome,
        basis=basis or f"Synthetic node {outcome} by the plan revision",
        premises=premises,
    )


def _replace(
    case: Case,
    old: PlanChild,
    new: PlanChild,
    *,
    outcome: Literal["cancelled", "stale"] | None = None,
    premises: tuple[ArtifactRef, ...] = (),
) -> PlanNodeDecision:
    return PlanNodeDecision(
        role=old.role,
        decision="replace",
        work_id=old.work_id,
        replacement=new.work_id,
        closure=(
            None if outcome is None else _closure(case, old.work_id, outcome, premises=premises)
        ),
    )


def _leave(
    case: Case,
    child: PlanChild,
    decision: Leaving,
    *,
    premises: tuple[ArtifactRef, ...] = (),
    basis: str | None = None,
) -> PlanNodeDecision:
    outcome: Literal["cancelled", "stale"] = "cancelled" if decision == "cancel" else "stale"
    return PlanNodeDecision(
        role=child.role,
        decision=decision,
        work_id=child.work_id,
        closure=_closure(case, child.work_id, outcome, premises=premises, basis=basis),
    )


def _revision_request(
    case: Case,
    plan: WorkPlan,
    nodes: tuple[PlanNodeDecision, ...],
    *,
    actor: str = "owner",
) -> ReviseActivePlanRequest:
    return ReviseActivePlanRequest(
        operation_id=uuid4(),
        space_id=case.space,
        actor=actor,
        work_id=case.parent,
        expected_plan_revision=read_work_plan(case.root, case.parent, case.owner).revision,
        expected_work_revision=read_work(case.root, case.parent, case.owner).revision,
        plan=plan,
        nodes=nodes,
    )


def _revise(case: Case, plan: WorkPlan, nodes: tuple[PlanNodeDecision, ...]) -> OperationReceipt:
    return apply_operation(case.root, _revision_request(case, plan, nodes), case.owner)


def _reasons(status: WorkStatus) -> list[tuple[str, str | None, UUID | None]]:
    return [(reason.code, reason.role, reason.record_id) for reason in status.reasons]


def _exception(case: Case, method: MethodRef, key: str) -> DecisionRef:
    decision = uuid4()
    _apply(
        case.root,
        case.space,
        case.owner,
        CreateDecisionRequest,
        decision_id=decision,
        state=ExceptionState(
            statement=f"Synthetic exception: {key} is not needed without its branch",
            target=ObligationTarget(work_id=case.parent, key=key),
            methods=(method,),
        ),
    )
    return DecisionRef(decision_id=decision, revision=1)


def test_w20_to_w23_replaces_the_stale_integration_while_other_nodes_are_kept(
    tmp_path: Path,
) -> None:
    w = _w_plan(tmp_path)
    case = w.case
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    experiment, prototype, integration = w.plan.children
    # W20 and W21 run in parallel; W22 is prepared in advance and not issued.
    _issue(case, "experiment")
    _issue(case, "prototype")
    # W20 establishes that the constraint must change: C@1 -> C@2.
    _apply(
        root,
        space,
        owner,
        ReviseArtifactRequest,
        artifact_id=w.constraint,
        expected_revision=1,
        media_type="text/plain",
        content=b"synthetic constraint, second revision",
    )
    c1 = ArtifactRef(artifact_id=w.constraint, revision=1)
    c2 = ArtifactRef(artifact_id=w.constraint, revision=2)
    blocked = read_work_status(root, integration.work_id, owner)
    assert blocked.status == "blocked"
    assert [(item.code, item.record_id, item.revision) for item in blocked.reasons] == [
        ("stale_basis", w.constraint, 1)
    ]
    w23 = _node(
        case.activity,
        "integration",
        "final",
        readiness=_current(c2),
        goal="Reconsider the integration under the second constraint",
    )
    revised = w.plan.model_copy(
        update={
            "children": (experiment, prototype, w23),
            "rationale": "The constraint changed to its second revision",
        }
    )
    request = _revision_request(
        case,
        revised,
        (
            _keep(experiment),
            _keep(prototype),
            _replace(case, integration, w23, outcome="stale", premises=(c1,)),
        ),
    )
    receipt = apply_operation(root, request, owner)
    expected_nodes = (
        PlanNode(
            role="experiment", decision="keep", work_id=experiment.work_id, issue_carried=True
        ),
        PlanNode(
            role="integration",
            decision="replace",
            work_id=w23.work_id,
            replaced_work_id=integration.work_id,
            closed_revision=2,
        ),
        PlanNode(role="prototype", decision="keep", work_id=prototype.work_id, issue_carried=True),
    )
    # The receipt names the decisions in request order, by address only.
    assert receipt.result == {
        "work_id": str(parent),
        "plan_revision": 2,
        "nodes": [expected_nodes[index].model_dump(mode="json") for index in (0, 2, 1)],
    }
    assert "Synthetic node" not in str(receipt.model_dump(mode="json"))
    nodes = read_plan_nodes(root, parent, owner)
    assert nodes.plan_revision == 2 and nodes.operation_id == request.operation_id
    assert nodes.nodes == expected_nodes
    # W22 rested on C@1 and never started: it is stale with that exact premise.
    w22 = read_work(root, integration.work_id, owner)
    assert w22.revision == 2 and w22.state.status == "stale" and w22.state.closure is not None
    assert w22.state.closure.premises == (c1,)
    assert w22.state.closure.operation_id == request.operation_id
    assert read_work_status(root, integration.work_id, owner).status == "stale"
    # W23 fills the same role on C@2; the role's obligation stays open until its result.
    after = case._replace(works={**case.works, "integration": w23.work_id})
    assert read_work_status(root, w23.work_id, owner) == WorkStatus(
        work_id=w23.work_id,
        status="proposed",
        reasons=(StatusReason(code="issue_pending", role="integration", record_id=parent),),
    )
    pending = read_obligation(root, parent, "integration", owner)
    assert pending.revision == 1 and pending.status == "open"
    # The issue of revision 1 admits nothing in revision 2 but for the kept nodes.
    stale_issue = _issue_request(after, "integration").model_copy(
        update={"expected_plan_revision": 1}
    )
    _refused(after, "stale_plan", stale_issue)
    # W21 kept its issue: its result links and is accepted under revision 2.
    _result(root, space, owner, prototype.work_id, "ui", b"synthetic prototype")
    finding = _result(root, space, owner, experiment.work_id, "finding", b"synthetic finding")
    _refused(
        after,
        "stale_plan",
        _confirm_request(after, "finding", finding).model_copy(
            update={"expected_plan_revision": 1}
        ),
    )
    _confirm(after, "finding", finding)
    _issue(after, "integration")
    assert c2 in read_work(root, w23.work_id, owner).state.inputs
    final = _result(root, space, owner, w23.work_id, "final", b"synthetic integration on C@2")
    _confirm(after, "integration", final)
    apply_operation(root, _link_request(after, final), owner)
    assert apply_operation(root, _accept_request(after), owner).result["status"] == "succeeded"

    assert read_role_history(root, parent, "integration", owner) == (
        RoleFilling(
            role="integration",
            work_id=integration.work_id,
            first_plan_revision=1,
            last_plan_revision=1,
        ),
        RoleFilling(role="integration", work_id=w23.work_id, first_plan_revision=2),
    )
    assert read_role_history(root, parent, "prototype", owner) == (
        RoleFilling(role="prototype", work_id=prototype.work_id, first_plan_revision=1),
    )
    assert read_work_plan(root, parent, owner, revision=1).plan == w.plan
    assert read_work_plan(root, parent, owner, revision=2).plan == revised
    assert apply_operation(root, request, owner) == receipt
    assert read_receipt(root, request.operation_id, owner) == receipt
    view = read_execution(root, parent, owner).composition
    assert view is not None
    assert [(item.role, item.work_id) for item in view.children] == [
        ("experiment", experiment.work_id),
        ("integration", w23.work_id),
        ("prototype", prototype.work_id),
    ]
    assert [(item.role, item.work_id, item.status.status) for item in view.departed] == [
        ("integration", integration.work_id, "stale")
    ]
    works = {"parent": parent, "w22": integration.work_id, **after.works}
    assert _statuses_in_new_process(after, works) == _statuses(after, works)


def test_replacing_an_accepted_node_reopens_its_obligation_by_role(tmp_path: Path) -> None:
    case, plan = _seeded(_space(tmp_path))
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    a, b = plan.children
    _issue(case, "a")
    checked = _result(root, space, owner, a.work_id, "checked", b"synthetic check by A")
    _confirm(case, "checked", checked)
    satisfied = read_obligation(root, parent, "checked", owner)
    assert satisfied.revision == 2 and satisfied.evidence == checked
    a2 = a.model_copy(
        update={
            "work_id": uuid4(),
            "state": a.state.model_copy(update={"goal": "Check the source once more"}),
        }
    )
    revised = plan.model_copy(update={"children": (a2, b), "rationale": "Check once more"})
    receipt = _revise(case, revised, (_replace(case, a, a2), _keep(b)))
    assert receipt.result["reopened"] == ["checked"]
    reopened = read_obligation(root, parent, "checked", owner)
    assert reopened.revision == 3 and reopened.status == "open"
    assert reopened.evidence is None and reopened.reopened == "node_replaced"
    assert reopened.operation_id == receipt.operation_id
    assert read_obligation(root, parent, "checked", owner, revision=2) == satisfied
    progress = read_execution(root, parent, owner).composition
    assert progress is not None
    assert [(item.key, item.status, item.reopened) for item in progress.obligations] == [
        ("checked", "open", "node_replaced"),
        ("final", "open", None),
    ]
    # A stays a really performed, accepted action and its Artifact reads.
    assert read_work_status(root, a.work_id, owner) == WorkStatus(
        work_id=a.work_id, status="succeeded"
    )
    assert read_artifact(root, checked.artifact_id, owner).content == b"synthetic check by A"
    after = case._replace(works={"a": a2.work_id, "b": b.work_id})
    waiting = read_work_status(root, b.work_id, owner)
    assert waiting.status == "blocked"
    assert _reasons(waiting) == [("dependency_open", "a", a2.work_id)]
    _issue(after, "a")
    rechecked = _result(root, space, owner, a2.work_id, "checked", b"synthetic check by A2")
    _refused(after, "evidence_mismatch", _confirm_request(after, "checked", checked))
    _confirm(after, "checked", rechecked)
    confirmed = read_obligation(root, parent, "checked", owner)
    assert confirmed.revision == 4 and confirmed.evidence == rechecked
    assert confirmed.reopened is None
    _issue(after, "b")
    inputs = read_work(root, b.work_id, owner).state.inputs
    assert rechecked in inputs and checked not in inputs
    view = read_execution(root, parent, owner).composition
    assert view is not None
    assert [(item.role, item.work_id) for item in view.children] == [
        ("a", a2.work_id),
        ("b", b.work_id),
    ]
    assert [(item.role, item.work_id, item.status.status) for item in view.departed] == [
        ("a", a.work_id, "succeeded")
    ]
    assert read_role_history(root, parent, "a", owner) == (
        RoleFilling(role="a", work_id=a.work_id, first_plan_revision=1, last_plan_revision=1),
        RoleFilling(role="a", work_id=a2.work_id, first_plan_revision=2),
    )


def _without_b(plan: WorkPlan, a: PlanChild) -> WorkPlan:
    """The seed plan without its summary branch: the parent output comes from A."""

    return plan.model_copy(
        update={
            "children": (a,),
            "output_bindings": (
                PlanOutputBinding(
                    parent_slot="final", role="a", child_slot="checked", media_type="text/plain"
                ),
            ),
            "completion": PlanCondition(kind="work_succeeded", role="a"),
            "rationale": "The summary branch is dropped",
        }
    )


def test_node_removed_from_the_plan_keeps_its_obligation_open_until_a_waiver(
    tmp_path: Path,
) -> None:
    case, plan = _seeded(_space(tmp_path))
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    a, b = plan.children
    _issue(case, "a")
    _revise(
        case,
        _without_b(plan, a),
        (_keep(a), _leave(case, b, "cancel", basis="The summary is no longer planned")),
    )
    removed = read_work(root, b.work_id, owner).state
    assert removed.status == "cancelled" and removed.closure is not None
    final = read_obligation(root, parent, "final", owner)
    assert final.revision == 1 and final.status == "open"
    # The removed branch stays under review while its requirement is open.
    assert _reasons(read_work_status(root, parent, owner)) == [
        ("child_ready", "a", a.work_id),
        ("branch_review", "b", b.work_id),
    ]
    checked = _result(root, space, owner, a.work_id, "checked", b"synthetic check")
    _confirm(case, "checked", checked)
    apply_operation(root, _link_request(case, checked), owner)
    _refused(case, "obligation_open", _accept_request(case))
    method = read_work(root, parent, owner).state.method
    assert isinstance(method, MethodRef)
    exception = _exception(case, method, "final")
    _apply(
        root,
        space,
        owner,
        WaiveObligationRequest,
        work_id=parent,
        key="final",
        expected_plan_revision=2,
        expected_obligation_revision=1,
        exception=exception,
        basis="Synthetic waiver of the dropped summary",
    )
    accepted = apply_operation(root, _accept_request(case), owner)
    assert accepted.result["waived"] == [
        {"key": "final", "exception": exception.model_dump(mode="json")}
    ]


def test_role_that_left_the_plan_is_filled_again_only_by_an_explicit_add(
    tmp_path: Path,
) -> None:
    case, plan = _seeded(_space(tmp_path))
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    a, b = plan.children
    # Before any issue a revision may drop a node; the output binding may name a role
    # that is not planned, which leaves the parent unacceptable until it is filled.
    dropped = plan.model_copy(update={"children": (a,), "rationale": "Summary postponed"})
    _revise(case, dropped, (_keep(a), _leave(case, b, "cancel")))
    b2 = b.model_copy(update={"work_id": uuid4()})
    refilled = plan.model_copy(update={"children": (a, b2), "rationale": "Summary again"})
    # A pre-issue revision cannot fill a role that was filled before.
    _refused(
        case,
        "unsupported_plan_change",
        ReviseWorkPlanRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=parent,
            expected_plan_revision=2,
            plan=refilled,
        ),
    )
    # Filling it again with the old Work, or without a decision, is refused as well.
    _refused(case, "record_exists", _revision_request(case, plan, (_keep(a), _add(b))))
    _refused(case, "mapping_incomplete", _revision_request(case, refilled, (_keep(a),)))
    receipt = _revise(case, refilled, (_keep(a), _add(b2)))
    assert receipt.result["nodes"] == [
        PlanNode(role="a", decision="keep", work_id=a.work_id).model_dump(mode="json"),
        PlanNode(role="b", decision="add", work_id=b2.work_id).model_dump(mode="json"),
    ]
    assert read_role_history(root, parent, "b", owner) == (
        RoleFilling(role="b", work_id=b.work_id, first_plan_revision=1, last_plan_revision=1),
        RoleFilling(role="b", work_id=b2.work_id, first_plan_revision=3),
    )
    after = case._replace(works={"a": a.work_id, "b": b2.work_id})
    _issue(after, "a")
    _confirm(after, "checked", _result(root, space, owner, a.work_id, "checked", b"check"))
    _issue(after, "b")
    summary = _result(root, space, owner, b2.work_id, "final", b"synthetic summary again")
    _confirm(after, "final", summary)
    apply_operation(root, _link_request(after, summary), owner)
    assert apply_operation(root, _accept_request(after), owner).result["status"] == "succeeded"


def test_revision_refusals_name_the_node_and_write_nothing(tmp_path: Path) -> None:
    w = _w_plan(tmp_path)
    case = w.case
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    experiment, prototype, integration = w.plan.children
    _issue(case, "experiment")
    _issue(case, "prototype")
    fresh = integration.model_copy(update={"work_id": uuid4()})
    replaced = w.plan.model_copy(update={"children": (experiment, prototype, fresh)})
    good = (
        _keep(experiment),
        _keep(prototype),
        _replace(case, integration, fresh, outcome="cancelled"),
    )

    error = _refused(case, "mapping_incomplete", _revision_request(case, replaced, good[1:]))
    assert "experiment" in error.detail and str(experiment.work_id) in error.detail
    review = _node(case.activity, "review", "notes")
    extended = w.plan.model_copy(update={"children": (*w.plan.children, review)})
    error = _refused(
        case,
        "mapping_incomplete",
        _revision_request(
            case, extended, (_keep(experiment), _keep(prototype), _keep(integration))
        ),
    )
    assert "review" in error.detail and str(review.work_id) in error.detail
    # An issued kept node keeps its exact definition; a changed node is replaced explicitly.
    regated = prototype.model_copy(update={"readiness": _accepted("experiment", "finding")})
    error = _refused(
        case,
        "mapping_invalid",
        _revision_request(
            case,
            w.plan.model_copy(update={"children": (experiment, regated, integration)}),
            (_keep(experiment), _keep(regated), _keep(integration)),
        ),
    )
    assert "prototype" in error.detail and str(prototype.work_id) in error.detail
    renamed = integration.model_copy(
        update={"state": integration.state.model_copy(update={"goal": "Another goal"})}
    )
    _refused(
        case,
        "mapping_invalid",
        _revision_request(
            case,
            w.plan.model_copy(update={"children": (experiment, prototype, renamed)}),
            (_keep(experiment), _keep(prototype), _keep(renamed)),
        ),
    )
    without_integration = w.plan.model_copy(
        update={"children": (experiment, prototype), "completion": None}
    )
    error = _refused(
        case,
        "mapping_invalid",
        _revision_request(
            case, without_integration, (_keep(experiment), _keep(prototype), _release(integration))
        ),
    )
    assert "integration" in error.detail and "cancel or stale" in error.detail
    _refused(
        case,
        "mapping_invalid",
        _revision_request(case, replaced, (_keep(experiment), _keep(prototype), _add(fresh))),
    )
    _refused(
        case,
        "mapping_invalid",
        _revision_request(
            case,
            replaced,
            (_keep(experiment), _keep(prototype), _replace(case, integration, fresh)),
        ),
    )
    other = integration.model_copy(update={"work_id": uuid4()})
    _refused(
        case,
        "mapping_invalid",
        _revision_request(
            case,
            replaced,
            (
                _keep(experiment),
                _keep(prototype),
                _replace(case, integration, other, outcome="cancelled"),
            ),
        ),
    )
    _refused(
        case,
        "stale_plan",
        _revision_request(case, replaced, good).model_copy(update={"expected_plan_revision": 2}),
    )
    _refused(
        case,
        "stale_work",
        _revision_request(case, replaced, good).model_copy(update={"expected_work_revision": 9}),
    )
    late = good[2].model_copy(
        update={"closure": good[2].closure.model_copy(update={"expected_revision": 5})}  # type: ignore[union-attr]
    )
    error = _refused(case, "stale_work", _revision_request(case, replaced, (*good[:2], late)))
    assert str(integration.work_id) in error.detail
    # A replacement is a new Work, never an existing record.
    reused = _space_seeded_child(case)
    taken = integration.model_copy(update={"work_id": reused})
    _refused(
        case,
        "record_exists",
        _revision_request(
            case,
            w.plan.model_copy(update={"children": (experiment, prototype, taken)}),
            (
                _keep(experiment),
                _keep(prototype),
                _replace(case, integration, taken, outcome="cancelled"),
            ),
        ),
    )
    # A stale outcome names a premise that really changed.
    _refused(
        case,
        "premise_current",
        _revision_request(
            case,
            without_integration,
            (
                _keep(experiment),
                _keep(prototype),
                _leave(
                    case,
                    integration,
                    "stale",
                    premises=(ArtifactRef(artifact_id=w.constraint, revision=1),),
                ),
            ),
        ),
    )
    # The revision needs work.write and method.use; closing a node also needs work.accept.
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest,
        grant_id=uuid4(),
        state=GrantState(
            grantee="planner",
            actions=("work.write", "record.read", "receipt.read"),
            resource_type="work",
            resource_id=parent,
        ),
    )
    planner = authorize_local(root, actor="planner", source_ref="fictional-planner")
    before = read_space(root)
    with pytest.raises(FoundationError, match="method.use"):
        apply_operation(root, _revision_request(case, replaced, good, actor="planner"), planner)
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest,
        grant_id=uuid4(),
        state=GrantState(grantee="planner", actions=("method.use", "record.read")),
    )
    before = read_space(root)
    with pytest.raises(FoundationError, match="work.accept"):
        apply_operation(root, _revision_request(case, replaced, good, actor="planner"), planner)
    assert read_space(root) == before
    assert read_work_plan(root, parent, owner).revision == 1
    assert read_work(root, integration.work_id, owner).revision == 1
    with pytest.raises(FoundationError, match="not_found"):
        read_plan_nodes(root, parent, owner)
    # Malformed decisions never reach Core.
    for fields in (
        {"role": "integration", "decision": "cancel", "work_id": integration.work_id},
        {"role": "integration", "decision": "replace", "work_id": integration.work_id},
        {
            "role": "prototype",
            "decision": "keep",
            "work_id": prototype.work_id,
            "closure": _closure(case, prototype.work_id, "cancelled"),
        },
        {
            "role": "integration",
            "decision": "stale",
            "work_id": integration.work_id,
            "closure": _closure(case, integration.work_id, "cancelled"),
        },
    ):
        with pytest.raises(ValidationError):
            PlanNodeDecision.model_validate(fields)
    with pytest.raises(ValidationError):
        ReviseActivePlanRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=parent,
            expected_plan_revision=1,
            expected_work_revision=1,
            plan=w.plan,
            nodes=(_keep(experiment), _keep(experiment)),
        )


def _space_seeded_child(case: Case) -> UUID:
    """A Work id already taken by another composite Work of the same space."""

    with closing(sqlite3.connect(case.root / ".zara-core" / "core.sqlite3")) as connection:
        row = connection.execute(
            "SELECT child_id FROM work_plan_children WHERE parent_id != ? LIMIT 1",
            (str(case.parent),),
        ).fetchone()
    assert row is not None
    return UUID(row[0])


def test_kept_issued_node_is_rechecked_in_the_new_revision(tmp_path: Path) -> None:
    w = _w_plan(tmp_path)
    case = w.case
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    experiment, prototype, integration = w.plan.children
    _issue(case, "experiment")
    review = _node(case.activity, "review", "notes", readiness=_accepted("experiment", "finding"))
    with_review = w.plan.model_copy(update={"children": (*w.plan.children, review)})
    _revise(
        case, with_review, (_keep(experiment), _keep(prototype), _keep(integration), _add(review))
    )
    finding = _result(root, space, owner, experiment.work_id, "finding", b"synthetic finding")
    after = case._replace(works={**case.works, "review": review.work_id})
    _issue(after, "review")
    assert finding in read_work(root, review.work_id, owner).state.inputs
    # Replacing the experiment would leave the issued review without its exact input.
    experiment2 = experiment.model_copy(update={"work_id": uuid4()})
    error = _refused(
        after,
        "dependency_open",
        _revision_request(
            after,
            with_review.model_copy(
                update={"children": (experiment2, prototype, integration, review)}
            ),
            (
                _replace(after, experiment, experiment2),
                _keep(prototype),
                _keep(integration),
                _keep(review),
            ),
        ),
    )
    assert f"Kept node review ({review.work_id})" in error.detail
    assert "plan revision 3" in error.detail
    # Deciding the review explicitly lets the revision pass.
    review2 = review.model_copy(update={"work_id": uuid4()})
    _revise(
        after,
        with_review.model_copy(update={"children": (experiment2, prototype, integration, review2)}),
        (
            _replace(after, experiment, experiment2),
            _keep(prototype),
            _keep(integration),
            _replace(after, review, review2, outcome="cancelled"),
        ),
    )
    assert read_work(root, review.work_id, owner).state.status == "cancelled"
    assert read_work_plan(root, parent, owner).revision == 3


def test_revision_history_survives_restore_and_node_deletion_is_independent(
    tmp_path: Path,
) -> None:
    case, plan = _seeded(_space(tmp_path))
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    a, b = plan.children
    marker = f"synthetic replaced node {uuid4()}"
    kept = f"synthetic replacement confirmation {uuid4()}"
    _issue(case, "a")
    checked = _result(root, space, owner, a.work_id, "checked", b"synthetic check by A")
    apply_operation(
        root,
        _confirm_request(case, "checked", checked).model_copy(update={"basis": marker}),
        owner,
    )
    a2 = a.model_copy(update={"work_id": uuid4()})
    request = _revision_request(
        case,
        plan.model_copy(update={"children": (a2, b), "rationale": "Check again"}),
        (_replace(case, a, a2), _keep(b)),
    )
    receipt = apply_operation(root, request, owner)
    after = case._replace(works={"a": a2.work_id, "b": b.work_id})
    _issue(after, "a")
    rechecked = _result(root, space, owner, a2.work_id, "checked", b"synthetic check by A2")
    apply_operation(
        root,
        _confirm_request(after, "checked", rechecked).model_copy(update={"basis": kept}),
        owner,
    )

    backup = create_backup(root, uuid4(), owner)
    restored_root = tmp_path / "restored"
    restored_root.mkdir()
    restore_backup(backup.package, restored_root, authorize_recovery(actor="owner", source_ref="r"))
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
    restored = authorize_local(restored_root, actor="owner", source_ref="new-epoch")
    assert read_plan_nodes(restored_root, parent, restored) == read_plan_nodes(root, parent, owner)
    assert read_role_history(restored_root, parent, "a", restored) == read_role_history(
        root, parent, "a", owner
    )
    restored_view = read_execution(restored_root, parent, restored).composition
    assert restored_view is not None
    assert [item.work_id for item in restored_view.departed] == [a.work_id]

    # Deleting the replaced node removes what depends on it, not its replacement's record.
    _apply(
        root,
        space,
        owner,
        DeleteWorkRequest,
        work_id=a.work_id,
        expected_revision=read_work(root, a.work_id, owner).revision,
    )
    assert complete_deletions(root, owner).live_store_sanitized
    assert not backup.package.exists()
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_obligation(root, parent, "checked", owner, revision=2)
    latest = read_obligation(root, parent, "checked", owner)
    assert latest.revision == 4 and latest.status == "satisfied" and latest.basis == kept
    assert latest.evidence == rechecked
    # The replacement never rested on the node it replaced: its acceptance basis stays.
    replacement = read_work(root, a2.work_id, owner).state.acceptance
    assert replacement is not None and replacement.basis == "Checked synthetic output"
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_work_plan(root, parent, owner, revision=1)
    assert read_work_plan(root, parent, owner, revision=2).plan.children == (a2, b)
    assert read_plan_nodes(root, parent, owner).nodes[0] == PlanNode(
        role="a", decision="replace", work_id=a2.work_id, replaced_work_id=a.work_id
    )
    assert read_role_history(root, parent, "a", owner) == (
        RoleFilling(role="a", work_id=a.work_id, first_plan_revision=1, last_plan_revision=1),
        RoleFilling(role="a", work_id=a2.work_id, first_plan_revision=2),
    )
    assert not _sqlite_contains(root / ".zara-core", marker)
    assert _sqlite_contains(root / ".zara-core", kept)
    # The revision holds only addresses of the deleted node: its receipt stays exact.
    assert apply_operation(root, request, owner) == receipt
    assert receipt.result["reopened"] == ["checked"]
    fresh_backup = create_backup(root, uuid4(), owner)
    assert not _sqlite_contains(fresh_backup.package, marker)

    # The parent goes last and takes its decisions and role history with it.
    for work in (a2.work_id, b.work_id):
        _apply(
            root,
            space,
            owner,
            DeleteWorkRequest,
            work_id=work,
            expected_revision=read_work(root, work, owner).revision,
        )
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
        for table in ("work_plan_nodes", "work_plan_members"):
            assert connection.execute(
                f"SELECT count(*) FROM {table} WHERE parent_id = ?", (str(parent),)
            ).fetchone() == (0,)
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_plan_nodes(root, parent, owner)


def _delete_in_new_process(root: Path, space: UUID, work: UUID, revision: int) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; from uuid import UUID, uuid4; "
            "from zaratustra.foundation import DeleteWorkRequest, apply_operation, "
            "authorize_local, complete_deletions; "
            "p=Path(sys.argv[1]); o=authorize_local(p, actor='owner', source_ref='restart'); "
            "apply_operation(p, DeleteWorkRequest(operation_id=uuid4(), "
            "space_id=UUID(sys.argv[2]), actor='owner', work_id=UUID(sys.argv[3]), "
            "expected_revision=int(sys.argv[4])), o); "
            "assert complete_deletions(p, o).live_store_sanitized",
            str(root),
            str(space),
            str(work),
            str(revision),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_role_history_in_the_retained_index_finds_dependents_after_restart(
    tmp_path: Path,
) -> None:
    case, plan = _seeded(_space(tmp_path))
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    a, b = plan.children
    marker = f"synthetic downstream acceptance {uuid4()}"
    _issue(case, "a")
    _result(root, space, owner, a.work_id, "checked", b"synthetic check by A")
    side = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=side,
        media_type="text/plain",
        content=b"synthetic side material",
    )
    a2 = a.model_copy(update={"work_id": uuid4()})
    c = _node(case.activity, "c", "notes", inputs=(ArtifactRef(artifact_id=side, revision=1),))
    _revise(
        case,
        plan.model_copy(update={"children": (a2, b, c), "rationale": "Check again, add notes"}),
        (_replace(case, a, a2), _keep(b), _add(c)),
    )
    after = case._replace(works={"a": a2.work_id, "b": b.work_id, "c": c.work_id})
    _issue(after, "a")
    _result(root, space, owner, a2.work_id, "checked", b"synthetic check by A2")
    _issue(after, "b")
    summary = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=summary,
        media_type="text/plain",
        content=b"synthetic summary",
    )
    linked = _apply(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=b.work_id,
        expected_revision=read_work(root, b.work_id, owner).revision,
        output=LinkedOutput(slot="final", artifact=ArtifactRef(artifact_id=summary, revision=1)),
    )
    _apply(
        root,
        space,
        owner,
        AcceptWorkRequest,
        work_id=b.work_id,
        expected_revision=linked.result["revision"],
        basis=marker,
    )
    # Deleting the side material sanitizes revision 2 into its index; B's basis is independent.
    _apply(root, space, owner, DeleteArtifactRequest, artifact_id=side, expected_revision=1)
    assert complete_deletions(root, owner).live_store_sanitized
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_work_plan(root, parent, owner, revision=2)
    acceptance = read_work(root, b.work_id, owner).state.acceptance
    assert acceptance is not None and acceptance.basis == marker
    # After a restart only the retained index knows that A2 filled role a in revision 2.
    _delete_in_new_process(root, space, a2.work_id, read_work(root, a2.work_id, owner).revision)
    retired = read_work(root, b.work_id, owner).state.acceptance
    assert retired is not None and retired.basis is None
    assert not _sqlite_contains(root / ".zara-core", marker)
    assert read_role_history(root, parent, "a", owner) == (
        RoleFilling(role="a", work_id=a.work_id, first_plan_revision=1, last_plan_revision=1),
        RoleFilling(role="a", work_id=a2.work_id, first_plan_revision=2),
    )
