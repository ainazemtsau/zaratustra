"""Nested composite Work follows exact Methods and closes explicitly."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import NamedTuple
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_applicability import (
    Case,
    Space,
    _accept_request,
    _confirm,
    _issue,
    _issue_request,
    _link_request,
    _refused,
    _space,
)
from tests.zaratustra.foundation.test_child_execution import (
    _assign,
    _assignment_revision,
    _claim,
    _invocation,
    _resource,
)
from tests.zaratustra.foundation.test_composition import _apply, _result, _sqlite_contains
from zaratustra.foundation import (
    AcceptWorkRequest,
    AnswerWaitRequest,
    ArtifactRef,
    AssignAttemptRequest,
    CloseWorkRequest,
    CreateArtifactRequest,
    CreateCompositeWorkRequest,
    CreateGrantRequest,
    CreateMethodVersionRequest,
    DeleteWorkRequest,
    DescendantClosure,
    FoundationError,
    GrantState,
    LinkedOutput,
    LinkWorkOutputRequest,
    MethodDefinition,
    MethodObligation,
    MethodRef,
    NamedInput,
    NodeClosure,
    ObligationMapping,
    OpenWaitRequest,
    OutputContract,
    PlanChild,
    PlanCondition,
    PlanNodeDecision,
    PlanOutputBinding,
    PrepareInvocationRequest,
    RecordAttemptStopRequest,
    ReviseActivePlanRequest,
    ReviseArtifactRequest,
    WorkPlan,
    WorkState,
    apply_operation,
    authorize_local,
    complete_deletions,
    create_backup,
    read_execution,
    read_method_version,
    read_obligation,
    read_receipt,
    read_work,
    read_work_plan,
    read_work_status,
)

MARKER = "nested-grandchild-addressed-marker-3901"


class Nested(NamedTuple):
    setup: Space
    parent: Case
    node: Case
    anchor: PlanChild
    nested_child: PlanChild
    initial: WorkPlan
    next_plan: WorkPlan
    nested_plan: WorkPlan
    n2: MethodRef
    n3: MethodRef


def _method(setup: Space, method_id: UUID, version: int, definition: MethodDefinition) -> MethodRef:
    receipt = _apply(
        setup.root,
        setup.space,
        setup.owner,
        CreateMethodVersionRequest,
        method_id=method_id,
        version=version,
        definition=definition,
    )
    return MethodRef(method_id=method_id, version=version, checksum=str(receipt.result["checksum"]))


def _nested(tmp_path: Path) -> Nested:
    setup = _space(tmp_path)
    output = (OutputContract(slot="final", media_type="text/plain"),)
    nid = uuid4()
    versions = tuple(
        _method(
            setup,
            nid,
            version,
            MethodDefinition(
                instruction=f"Produce an exact synthetic nested result, version {version}.",
                named_outputs=output,
                obligations=(
                    MethodObligation(
                        key="g_final",
                        source=f"Synthetic nested requirement {version}",
                        role="g",
                        slot="final",
                        media_type="text/plain",
                    ),
                ),
                source_ref=f"synthetic-nested-method-{version}",
            ),
        )
        for version in (1, 2, 3)
    )
    n2, n3 = versions[1:]
    pmethod = _method(
        setup,
        uuid4(),
        1,
        MethodDefinition(
            instruction="Integrate the nested review result.",
            named_inputs=(OutputContract(slot="source", media_type="text/plain"),),
            named_outputs=output,
            obligations=(
                MethodObligation(
                    key="reviewed",
                    source="Synthetic parent requirement",
                    role="review",
                    slot="final",
                    media_type="text/plain",
                ),
            ),
            role_methods=(("review", n2),),
            source_ref="synthetic-parent-method",
        ),
    )
    anchor = PlanChild(
        role="anchor",
        work_id=uuid4(),
        state=WorkState(
            activity_id=setup.activity,
            goal="Independent anchor",
            expected_outputs=(OutputContract(slot="other", media_type="text/plain"),),
        ),
    )
    nested_child = PlanChild(
        role="g",
        work_id=uuid4(),
        state=WorkState(
            activity_id=setup.activity,
            goal=MARKER,
            expected_outputs=output,
        ),
    )
    nested_plan = WorkPlan(
        output_bindings=(
            PlanOutputBinding(
                parent_slot="final",
                role="g",
                child_slot="final",
                media_type="text/plain",
            ),
        ),
        children=(nested_child,),
        completion=PlanCondition(kind="work_succeeded", role="g"),
        rationale="Nested result comes from the grandchild",
        source_ref="synthetic-nested-plan",
    )
    review = PlanChild(
        role="review",
        work_id=uuid4(),
        state=WorkState(
            activity_id=setup.activity,
            goal="Nested review",
            expected_outputs=output,
            method=n2,
        ),
    )
    initial = WorkPlan(
        named_inputs=(NamedInput(slot="source", artifact=setup.source),),
        output_bindings=(
            PlanOutputBinding(
                parent_slot="final",
                role="review",
                child_slot="final",
                media_type="text/plain",
            ),
        ),
        children=(anchor,),
        completion=PlanCondition(kind="work_succeeded", role="review"),
        basis=(setup.source,),
        rationale="The review role is reserved",
        source_ref="synthetic-parent-plan",
    )
    next_plan = initial.model_copy(
        update={
            "children": (anchor, review),
            "rationale": f"The exact nested review contains {MARKER}",
        }
    )
    parent_id = uuid4()
    _apply(
        setup.root,
        setup.space,
        setup.owner,
        CreateCompositeWorkRequest,
        work_id=parent_id,
        state=WorkState(
            activity_id=setup.activity,
            goal="Parent integration",
            inputs=(setup.source,),
            expected_outputs=output,
            method=pmethod,
        ),
        plan=initial,
    )
    return Nested(
        setup,
        Case(
            setup.root,
            setup.space,
            setup.owner,
            setup.activity,
            parent_id,
            {"anchor": anchor.work_id, "review": review.work_id},
        ),
        Case(
            setup.root,
            setup.space,
            setup.owner,
            setup.activity,
            review.work_id,
            {"g": nested_child.work_id},
        ),
        anchor,
        nested_child,
        initial,
        next_plan,
        nested_plan,
        n2,
        n3,
    )


def _add_nested(case: Nested, *, method: MethodRef | None = None) -> ReviseActivePlanRequest:
    review = case.next_plan.children[1]
    plan = case.next_plan
    if method is not None:
        review = review.model_copy(
            update={"state": review.state.model_copy(update={"method": method})}
        )
        plan = plan.model_copy(update={"children": (case.anchor, review)})
    return ReviseActivePlanRequest(
        operation_id=uuid4(),
        space_id=case.setup.space,
        actor="owner",
        work_id=case.parent.parent,
        expected_plan_revision=read_work_plan(
            case.setup.root, case.parent.parent, case.setup.owner
        ).revision,
        expected_work_revision=read_work(
            case.setup.root, case.parent.parent, case.setup.owner
        ).revision,
        plan=plan,
        nodes=(
            PlanNodeDecision(role="anchor", decision="keep", work_id=case.anchor.work_id),
            PlanNodeDecision(
                role="review", decision="add", work_id=review.work_id, nested_plan=case.nested_plan
            ),
        ),
    )


def test_nested_method_pin_issue_and_full_acceptance(tmp_path: Path) -> None:
    case = _nested(tmp_path)
    _refused(case.parent, "method_mismatch", _add_nested(case, method=case.n3))
    apply_operation(case.setup.root, _add_nested(case), case.setup.owner)
    visible = read_execution(case.setup.root, case.node.parent, case.setup.owner).composition
    assert visible is not None and visible.nested is not None
    assert visible.method.version == 1 and visible.plan_revision == 2
    assert visible.nested.method == case.n2 and visible.nested.plan_revision == 1
    assert [(item.role, item.work_id) for item in visible.nested.children] == [
        ("g", case.nested_child.work_id)
    ]
    assert [(item.key, item.status) for item in visible.nested.obligations] == [("g_final", "open")]
    assert [(item.role, item.decision) for item in visible.nodes] == [
        ("anchor", "keep"),
        ("review", "add"),
    ]
    assert (
        read_obligation(case.setup.root, case.node.parent, "g_final", case.setup.owner).revision
        == 1
    )
    _refused(case.node, "child_not_issued", _issue_request(case.node, "g"))
    _issue(case.parent, "review")
    _issue(case.node, "g")
    _refused(
        case.node,
        "unsupported_composite_execution",
        AssignAttemptRequest(
            operation_id=uuid4(),
            space_id=case.setup.space,
            actor="owner",
            attempt_id=uuid4(),
            work_id=case.node.parent,
            expected_work_revision=read_work(
                case.setup.root, case.node.parent, case.setup.owner
            ).revision,
            resource_id=uuid4(),
            expected_resource_revision=1,
            session_id=uuid4(),
            executor_version="synthetic-child-contract-1",
        ),
    )
    y = uuid4()
    _apply(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        CreateArtifactRequest,
        artifact_id=y,
        media_type="text/plain",
        content=b"nested independent result",
    )
    result = ArtifactRef(artifact_id=y, revision=1)
    _apply(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        LinkWorkOutputRequest,
        work_id=case.nested_child.work_id,
        expected_revision=read_work(
            case.setup.root, case.nested_child.work_id, case.setup.owner
        ).revision,
        output=LinkedOutput(slot="final", artifact=result),
    )
    _apply(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        AcceptWorkRequest,
        work_id=case.nested_child.work_id,
        expected_revision=read_work(
            case.setup.root, case.nested_child.work_id, case.setup.owner
        ).revision,
        basis="Accepted independent grandchild result",
    )
    _confirm(case.node, "g_final", result)
    apply_operation(case.setup.root, _link_request(case.node, result), case.setup.owner)
    apply_operation(case.setup.root, _accept_request(case.node), case.setup.owner)
    _confirm(case.parent, "reviewed", result)
    apply_operation(case.setup.root, _link_request(case.parent, result), case.setup.owner)
    apply_operation(case.setup.root, _accept_request(case.parent), case.setup.owner)
    assert (
        read_work_status(case.setup.root, case.parent.parent, case.setup.owner).status
        == "succeeded"
    )
    prior = create_backup(case.setup.root, uuid4(), case.setup.owner)
    _apply(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        DeleteWorkRequest,
        work_id=case.nested_child.work_id,
        expected_revision=read_work(
            case.setup.root, case.nested_child.work_id, case.setup.owner
        ).revision,
    )
    assert complete_deletions(case.setup.root, case.setup.owner).live_store_sanitized
    assert not prior.package.exists()
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_work_plan(case.setup.root, case.parent.parent, case.setup.owner, revision=2)
    nested_acceptance = read_work(
        case.setup.root, case.node.parent, case.setup.owner
    ).state.acceptance
    parent_acceptance = read_work(
        case.setup.root, case.parent.parent, case.setup.owner
    ).state.acceptance
    assert nested_acceptance is not None and nested_acceptance.basis is None
    assert parent_acceptance is not None and parent_acceptance.basis is None
    assert not _sqlite_contains(case.setup.root / ".zara-core", MARKER)
    clean = create_backup(case.setup.root, uuid4(), case.setup.owner)
    assert not _sqlite_contains(clean.package, MARKER)
    fresh = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-c",
            "from pathlib import Path; from uuid import UUID; "
            "from zaratustra.foundation import authorize_local, read_work, "
            "read_work_plan, FoundationError; "
            "p=Path(__import__('sys').argv[1]); w=UUID(__import__('sys').argv[2]); "
            "a=authorize_local(p, actor='owner', source_ref='new-process'); "
            "assert read_work(p,w,a).state.acceptance.basis is None; "
            "\ntry: read_work_plan(p,w,a,revision=2)\n"
            "except FoundationError as e: assert e.code == 'content_unavailable'\n"
            "else: raise AssertionError('plan remained readable')",
            str(case.setup.root),
            str(case.parent.parent),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert fresh.returncode == 0, fresh.stderr
    _apply(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        DeleteWorkRequest,
        work_id=case.node.parent,
        expected_revision=read_work(case.setup.root, case.node.parent, case.setup.owner).revision,
    )
    assert (
        read_obligation(case.setup.root, case.parent.parent, "reviewed", case.setup.owner).key
        == "reviewed"
    )
    for work_id in (case.anchor.work_id, case.parent.parent):
        _apply(
            case.setup.root,
            case.setup.space,
            case.setup.owner,
            DeleteWorkRequest,
            work_id=work_id,
            expected_revision=read_work(case.setup.root, work_id, case.setup.owner).revision,
        )
    assert complete_deletions(case.setup.root, case.setup.owner).live_store_sanitized
    assert not clean.package.exists()
    assert not _sqlite_contains(case.setup.root / ".zara-core", MARKER)


def test_departing_nested_node_requires_explicit_grandchild_closure(tmp_path: Path) -> None:
    case = _nested(tmp_path)
    apply_operation(case.setup.root, _add_nested(case), case.setup.owner)
    _issue(case.parent, "review")
    _issue(case.node, "g")
    resource = _resource(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        case.nested_child.work_id,
        "nested-grandchild-resource",
    )
    attempt, session, _request, _receipt = _assign(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        case.nested_child.work_id,
        resource,
    )
    _claim(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        case.nested_child.work_id,
        attempt,
        session,
    )
    assert (
        read_work_status(case.setup.root, case.parent.parent, case.setup.owner).status == "running"
    )
    invocation = _invocation(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        case.nested_child.work_id,
        attempt,
        session,
        finish=False,
    )
    wait_id = uuid4()
    _apply(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        OpenWaitRequest,
        wait_id=wait_id,
        attempt_id=attempt,
        work_id=case.nested_child.work_id,
        session_id=session,
        expected_assignment_revision=_assignment_revision(
            case.setup.root,
            case.setup.owner,
            case.nested_child.work_id,
            attempt,
        ),
        question="Which synthetic source is authoritative?",
        expected_actor="owner",
        remainder="Continue nested grandchild review",
    )
    assert (
        read_work_status(case.setup.root, case.parent.parent, case.setup.owner).status == "waiting"
    )
    replacement = case.next_plan.children[1].model_copy(
        update={
            "work_id": uuid4(),
            "state": case.next_plan.children[1].state.model_copy(update={"method": "none"}),
        }
    )
    # The declared role pins N@2, so a replacement must also be composite.
    replacement = replacement.model_copy(
        update={
            "state": replacement.state.model_copy(update={"method": case.n2}),
        }
    )
    plan = case.next_plan.model_copy(update={"children": (case.anchor, replacement)})

    def request(descendants: tuple[DescendantClosure, ...]) -> ReviseActivePlanRequest:
        return ReviseActivePlanRequest(
            operation_id=uuid4(),
            space_id=case.setup.space,
            actor="owner",
            work_id=case.parent.parent,
            expected_plan_revision=read_work_plan(
                case.setup.root, case.parent.parent, case.setup.owner
            ).revision,
            expected_work_revision=read_work(
                case.setup.root, case.parent.parent, case.setup.owner
            ).revision,
            plan=plan,
            nodes=(
                PlanNodeDecision(role="anchor", decision="keep", work_id=case.anchor.work_id),
                PlanNodeDecision(
                    role="review",
                    decision="replace",
                    work_id=case.node.parent,
                    replacement=replacement.work_id,
                    closure=NodeClosure(
                        expected_revision=read_work(
                            case.setup.root, case.node.parent, case.setup.owner
                        ).revision,
                        outcome="cancelled",
                        basis="Replace nested review",
                    ),
                    nested_plan=case.nested_plan.model_copy(
                        update={
                            "children": (
                                case.nested_child.model_copy(update={"work_id": uuid4()}),
                            ),
                        }
                    ),
                    descendants=descendants,
                ),
            ),
        )

    _refused(case.parent, "open_children", request(()))
    close = DescendantClosure(
        parent_work_id=case.node.parent,
        expected_plan_revision=read_work_plan(
            case.setup.root, case.node.parent, case.setup.owner
        ).revision,
        role="g",
        work_id=case.nested_child.work_id,
        closure=NodeClosure(
            expected_revision=read_work(
                case.setup.root, case.nested_child.work_id, case.setup.owner
            ).revision,
            outcome="cancelled",
            basis="Explicit grandchild cancellation",
        ),
    )
    _refused(
        case.parent,
        "stale_plan",
        request((close.model_copy(update={"expected_plan_revision": 9}),)),
    )
    _refused(
        case.parent,
        "stale_work",
        request(
            (
                close.model_copy(
                    update={
                        "closure": close.closure.model_copy(update={"expected_revision": 1}),
                    }
                ),
            )
        ),
    )
    _refused(
        case.parent,
        "mapping_invalid",
        request((close.model_copy(update={"work_id": uuid4()}),)),
    )
    _apply(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        CreateGrantRequest,
        grant_id=uuid4(),
        state=GrantState(grantee="worker", actions=("work.write", "method.use", "record.read")),
    )
    worker = authorize_local(case.setup.root, actor="worker", source_ref="synthetic-worker")
    denied = request((close,)).model_copy(update={"operation_id": uuid4(), "actor": "worker"})
    before = read_work_plan(case.setup.root, case.parent.parent, case.setup.owner).revision
    with pytest.raises(FoundationError, match="permission_denied"):
        apply_operation(case.setup.root, denied, worker)
    assert read_work_plan(case.setup.root, case.parent.parent, case.setup.owner).revision == before
    apply_operation(case.setup.root, request((close,)), case.setup.owner)
    assert (
        read_work(case.setup.root, case.nested_child.work_id, case.setup.owner).state.status
        == "cancelled"
    )
    assert (
        read_work(case.setup.root, case.node.parent, case.setup.owner).state.status == "cancelled"
    )
    execution = read_execution(case.setup.root, case.nested_child.work_id, case.setup.owner)
    assert next(item for item in execution.assignments if item.attempt_id == attempt).status == (
        "stop_requested"
    )
    assert next(item for item in execution.waits if item.wait_id == wait_id).status == "closed"
    assert next(
        item for item in execution.invocations if item.invocation_id == invocation
    ).status == ("unknown")
    _refused(
        case.node,
        "stale_wait",
        AnswerWaitRequest(
            operation_id=uuid4(),
            space_id=case.setup.space,
            actor="owner",
            wait_id=wait_id,
            attempt_id=attempt,
            work_id=case.nested_child.work_id,
            session_id=session,
            expected_wait_revision=1,
            answer="Late answer",
        ),
    )
    _refused(
        case.node,
        "work_closed|stale_plan",
        PrepareInvocationRequest(
            operation_id=uuid4(),
            space_id=case.setup.space,
            actor="owner",
            invocation_id=uuid4(),
            attempt_id=attempt,
            work_id=case.nested_child.work_id,
            session_id=session,
            purpose="content",
            provider="synthetic",
            model="synthetic",
            transport="http-sse",
            request_sha256="A" * 64,
            request_bytes=10,
            reserve_units=5,
        ),
    )
    _apply(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        RecordAttemptStopRequest,
        attempt_id=attempt,
        work_id=case.nested_child.work_id,
        session_id=session,
        expected_assignment_revision=_assignment_revision(
            case.setup.root,
            case.setup.owner,
            case.nested_child.work_id,
            attempt,
        ),
        outcome="unknown",
    )
    replacement_grandchild = (
        read_work_plan(case.setup.root, replacement.work_id, case.setup.owner)
        .plan.children[0]
        .work_id
    )
    replacement_case = Case(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        case.setup.activity,
        replacement.work_id,
        {"g": replacement_grandchild},
    )
    _issue(
        case.parent._replace(works={"review": replacement.work_id, "anchor": case.anchor.work_id}),
        "review",
    )
    _issue(replacement_case, "g")
    replacement_resource = _resource(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        replacement_grandchild,
        "nested-grandchild-resource",
    )
    with pytest.raises(FoundationError, match="resource_busy"):
        _assign(
            case.setup.root,
            case.setup.space,
            case.setup.owner,
            replacement_grandchild,
            replacement_resource,
        )
    _issue(case.parent, "anchor")


def test_nested_acceptance_rechecks_current_ancestor_inputs(tmp_path: Path) -> None:
    case = _nested(tmp_path)
    root, space, owner = case.setup.root, case.setup.space, case.setup.owner
    apply_operation(root, _add_nested(case), owner)
    _issue(case.parent, "review")
    _issue(case.node, "g")
    result = _result(root, space, owner, case.nested_child.work_id, "final", b"Independent Y")
    _confirm(case.node, "g_final", result)
    apply_operation(root, _link_request(case.node, result), owner)
    assert read_work_status(root, case.node.parent, owner).status == "ready"

    _apply(
        root,
        space,
        owner,
        ReviseArtifactRequest,
        artifact_id=case.setup.source.artifact_id,
        expected_revision=1,
        media_type="text/plain",
        content=b"Changed root prerequisite",
    )
    status = read_work_status(root, case.node.parent, owner)
    assert status.status == "blocked"
    assert any(reason.code == "stale_basis" for reason in status.reasons)
    _refused(case.node, "stale_basis", _accept_request(case.node))
    assert read_work(root, case.node.parent, owner).state.status == "proposed"

    fresh = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-c",
            "from pathlib import Path; from uuid import UUID; import sys; "
            "from zaratustra.foundation import authorize_local, read_work, read_work_status; "
            "p=Path(sys.argv[1]); w=UUID(sys.argv[2]); "
            "a=authorize_local(p,actor='owner',source_ref='restart'); "
            "assert read_work(p,w,a).state.status == 'proposed'; "
            "assert read_work_status(p,w,a).status == 'blocked'",
            str(root),
            str(case.node.parent),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert fresh.returncode == 0, fresh.stderr


@pytest.mark.parametrize("running_spare", [False, True])
def test_departing_nested_node_closes_open_child_below_succeeded_composite(
    tmp_path: Path, running_spare: bool
) -> None:
    case = _nested(tmp_path)
    root, space, owner = case.setup.root, case.setup.space, case.setup.owner
    apply_operation(root, _add_nested(case), owner)
    _issue(case.parent, "review")
    old = case.nested_child
    middle = old.model_copy(
        update={
            "work_id": uuid4(),
            "state": old.state.model_copy(update={"method": case.n2, "goal": "Intermediate H"}),
        }
    )
    required = old.model_copy(
        update={"work_id": uuid4(), "state": old.state.model_copy(update={"goal": "Required L"})}
    )
    spare = old.model_copy(
        update={
            "role": "spare",
            "work_id": uuid4(),
            "state": old.state.model_copy(update={"goal": "Optional S"}),
        }
    )
    middle_plan = case.nested_plan.model_copy(update={"children": (required, spare)})
    nested_plan = case.nested_plan.model_copy(update={"children": (middle,)})
    apply_operation(
        root,
        ReviseActivePlanRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=case.node.parent,
            expected_work_revision=read_work(root, case.node.parent, owner).revision,
            expected_plan_revision=1,
            plan=nested_plan,
            nodes=(
                PlanNodeDecision(
                    role="g",
                    decision="replace",
                    work_id=old.work_id,
                    replacement=middle.work_id,
                    closure=NodeClosure(
                        expected_revision=1, outcome="cancelled", basis="Replace plain child"
                    ),
                    nested_plan=middle_plan,
                ),
            ),
        ),
        owner,
    )
    nested_case = case.node._replace(works={"g": middle.work_id})
    middle_case = Case(
        root,
        space,
        owner,
        case.setup.activity,
        middle.work_id,
        {
            "g": required.work_id,
            "spare": spare.work_id,
        },
    )
    _issue(nested_case, "g")
    _issue(middle_case, "g")
    _issue(middle_case, "spare")
    result = _result(root, space, owner, required.work_id, "final", b"Required result")
    attempt = invocation = None
    if running_spare:
        resource = _resource(root, space, owner, spare.work_id, "optional-spare-resource")
        attempt, session, _request, _receipt = _assign(root, space, owner, spare.work_id, resource)
        _claim(root, space, owner, spare.work_id, attempt, session)
        invocation = _invocation(root, space, owner, spare.work_id, attempt, session, finish=False)
    _confirm(middle_case, "g_final", result)
    apply_operation(root, _link_request(middle_case, result), owner)
    acceptance = _accept_request(middle_case)
    accepted = apply_operation(root, acceptance, owner)
    assert read_work(root, middle.work_id, owner).state.status == "succeeded"
    assert read_work(root, spare.work_id, owner).state.status == "proposed"

    replacement = case.next_plan.children[1].model_copy(update={"work_id": uuid4()})
    fresh = old.model_copy(update={"work_id": uuid4()})
    parent_plan = case.next_plan.model_copy(update={"children": (case.anchor, replacement)})

    def request(descendants: tuple[DescendantClosure, ...]) -> ReviseActivePlanRequest:
        return ReviseActivePlanRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=case.parent.parent,
            expected_work_revision=read_work(root, case.parent.parent, owner).revision,
            expected_plan_revision=read_work_plan(root, case.parent.parent, owner).revision,
            plan=parent_plan,
            nodes=(
                PlanNodeDecision(role="anchor", decision="keep", work_id=case.anchor.work_id),
                PlanNodeDecision(
                    role="review",
                    decision="replace",
                    work_id=case.node.parent,
                    replacement=replacement.work_id,
                    closure=NodeClosure(
                        expected_revision=read_work(root, case.node.parent, owner).revision,
                        outcome="cancelled",
                        basis="Replace N",
                    ),
                    nested_plan=case.nested_plan.model_copy(update={"children": (fresh,)}),
                    descendants=descendants,
                ),
            ),
        )

    _refused(case.parent, "open_children", request(()))
    _refused(
        case.parent,
        "work_closed",
        CloseWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=spare.work_id,
            expected_revision=read_work(root, spare.work_id, owner).revision,
            outcome="cancelled",
            basis="Direct close below accepted H",
        ),
    )
    close = DescendantClosure(
        parent_work_id=middle.work_id,
        expected_plan_revision=read_work_plan(root, middle.work_id, owner).revision,
        role="spare",
        work_id=spare.work_id,
        closure=NodeClosure(
            expected_revision=read_work(root, spare.work_id, owner).revision,
            outcome="cancelled",
            basis="Explicitly stop optional S",
        ),
    )
    apply_operation(root, request((close,)), owner)
    assert read_work(root, case.node.parent, owner).state.status == "cancelled"
    assert read_work(root, spare.work_id, owner).state.status == "cancelled"
    middle_state = read_work(root, middle.work_id, owner).state
    assert middle_state.status == "succeeded"
    assert middle_state.acceptance is not None and middle_state.acceptance.basis is not None
    assert apply_operation(root, acceptance, owner) == accepted
    assert read_work(root, required.work_id, owner).state.status == "succeeded"
    assert read_work(root, case.anchor.work_id, owner).state.status == "proposed"
    assert read_work(root, replacement.work_id, owner).state.status == "proposed"
    if running_spare:
        assert attempt is not None and invocation is not None
        execution = read_execution(root, spare.work_id, owner)
        assert next(a for a in execution.assignments if a.attempt_id == attempt).status == (
            "stop_requested"
        )
        assert next(i for i in execution.invocations if i.invocation_id == invocation).status == (
            "unknown"
        )
        assert execution.held_units == 5


def test_nested_method_input_media_type_matches_direct_creation(tmp_path: Path) -> None:
    case = _nested(tmp_path)
    root, space, owner = case.setup.root, case.setup.space, case.setup.owner
    nested_definition = read_method_version(root, case.n2, owner).definition.model_copy(
        update={"named_inputs": (OutputContract(slot="document", media_type="application/json"),)}
    )
    nested_method = _method(case.setup, uuid4(), 1, nested_definition)
    new_node = case.next_plan.children[1].model_copy(
        update={
            "state": case.next_plan.children[1].state.model_copy(
                update={"method": nested_method, "inputs": (case.setup.source,)}
            )
        }
    )
    nested_plan = case.nested_plan.model_copy(
        update={"named_inputs": (NamedInput(slot="document", artifact=case.setup.source),)}
    )
    parent_method = read_work(root, case.parent.parent, owner).state.method
    assert isinstance(parent_method, MethodRef)
    parent_definition = read_method_version(root, parent_method, owner).definition.model_copy(
        update={"role_methods": (("review", nested_method),)}
    )
    parent_v2 = _method(case.setup, parent_method.method_id, 2, parent_definition)
    case = case._replace(
        next_plan=case.next_plan.model_copy(update={"children": (case.anchor, new_node)}),
        nested_plan=nested_plan,
    )

    def add() -> ReviseActivePlanRequest:
        return _add_nested(case).model_copy(
            update={
                "target_method": parent_v2,
                "obligation_mapping": (
                    ObligationMapping(source_key="reviewed", action="carry", target_key="reviewed"),
                ),
            }
        )

    _refused(case.parent, "output_mismatch", add())
    assert read_work_plan(root, case.parent.parent, owner).revision == 1
    json_id = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=json_id,
        media_type="application/json",
        content=b"{}",
    )
    document = ArtifactRef(artifact_id=json_id, revision=1)
    valid_node = new_node.model_copy(
        update={"state": new_node.state.model_copy(update={"inputs": (document,)})}
    )
    valid_plan = nested_plan.model_copy(
        update={"named_inputs": (NamedInput(slot="document", artifact=document),)}
    )
    case = case._replace(
        next_plan=case.next_plan.model_copy(update={"children": (case.anchor, valid_node)}),
        nested_plan=valid_plan,
    )
    apply_operation(root, add(), owner)
    assert read_work(root, valid_node.work_id, owner).state.inputs == (document,)
    assert read_work_plan(root, valid_node.work_id, owner).plan.named_inputs == (
        NamedInput(slot="document", artifact=document),
    )


def test_replacement_nested_method_input_media_type(tmp_path: Path) -> None:
    case = _nested(tmp_path)
    root, space, owner = case.setup.root, case.setup.space, case.setup.owner
    apply_operation(root, _add_nested(case), owner)
    nested_definition = read_method_version(root, case.n2, owner).definition.model_copy(
        update={"named_inputs": (OutputContract(slot="document", media_type="application/json"),)}
    )
    nested_method = _method(case.setup, uuid4(), 1, nested_definition)
    parent_method = read_work(root, case.parent.parent, owner).state.method
    assert isinstance(parent_method, MethodRef)
    parent_definition = read_method_version(root, parent_method, owner).definition.model_copy(
        update={"role_methods": (("review", nested_method),)}
    )
    parent_v2 = _method(case.setup, parent_method.method_id, 2, parent_definition)
    replacement = case.next_plan.children[1].model_copy(
        update={
            "work_id": uuid4(),
            "state": case.next_plan.children[1].state.model_copy(
                update={"method": nested_method, "inputs": (case.setup.source,)}
            ),
        }
    )
    nested_plan = case.nested_plan.model_copy(
        update={
            "children": (case.nested_child.model_copy(update={"work_id": uuid4()}),),
            "named_inputs": (NamedInput(slot="document", artifact=case.setup.source),),
        }
    )
    descendant = DescendantClosure(
        parent_work_id=case.node.parent,
        expected_plan_revision=1,
        role="g",
        work_id=case.nested_child.work_id,
        closure=NodeClosure(expected_revision=1, outcome="cancelled", basis="Replace N"),
    )

    def replace(node: PlanChild, plan: WorkPlan) -> ReviseActivePlanRequest:
        return ReviseActivePlanRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=case.parent.parent,
            expected_work_revision=read_work(root, case.parent.parent, owner).revision,
            expected_plan_revision=read_work_plan(root, case.parent.parent, owner).revision,
            plan=case.next_plan.model_copy(update={"children": (case.anchor, node)}),
            nodes=(
                PlanNodeDecision(role="anchor", decision="keep", work_id=case.anchor.work_id),
                PlanNodeDecision(
                    role="review",
                    decision="replace",
                    work_id=case.node.parent,
                    replacement=node.work_id,
                    closure=NodeClosure(
                        expected_revision=read_work(root, case.node.parent, owner).revision,
                        outcome="cancelled",
                        basis="Replace N",
                    ),
                    nested_plan=plan,
                    descendants=(descendant,),
                ),
            ),
            target_method=parent_v2,
            obligation_mapping=(
                ObligationMapping(source_key="reviewed", action="carry", target_key="reviewed"),
            ),
        )

    _refused(case.parent, "output_mismatch", replace(replacement, nested_plan))
    assert read_work(root, case.node.parent, owner).state.status == "proposed"
    assert read_work(root, case.nested_child.work_id, owner).state.status == "proposed"

    json_id = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=json_id,
        media_type="application/json",
        content=b"{}",
    )
    document = ArtifactRef(artifact_id=json_id, revision=1)
    valid = replacement.model_copy(
        update={"state": replacement.state.model_copy(update={"inputs": (document,)})}
    )
    valid_plan = nested_plan.model_copy(
        update={"named_inputs": (NamedInput(slot="document", artifact=document),)}
    )
    apply_operation(root, replace(valid, valid_plan), owner)
    assert read_work(root, case.node.parent, owner).state.status == "cancelled"
    assert read_work(root, case.nested_child.work_id, owner).state.status == "cancelled"
    assert read_work(root, valid.work_id, owner).state.inputs == (document,)


@pytest.mark.parametrize("running_spare", [False, True])
def test_replace_succeeded_composite_root_closes_its_open_optional_child(
    tmp_path: Path, running_spare: bool
) -> None:
    case = _nested(tmp_path)
    root, space, owner = case.setup.root, case.setup.space, case.setup.owner
    apply_operation(root, _add_nested(case), owner)
    _issue(case.parent, "review")
    old = case.nested_child
    middle = old.model_copy(
        update={
            "work_id": uuid4(),
            "state": old.state.model_copy(update={"method": case.n2, "goal": "Accepted H"}),
        }
    )
    required = old.model_copy(
        update={"work_id": uuid4(), "state": old.state.model_copy(update={"goal": "Required L"})}
    )
    spare = old.model_copy(
        update={
            "role": "spare",
            "work_id": uuid4(),
            "state": old.state.model_copy(update={"goal": "Optional S"}),
        }
    )
    middle_plan = case.nested_plan.model_copy(update={"children": (required, spare)})
    nested_plan = case.nested_plan.model_copy(update={"children": (middle,)})
    apply_operation(
        root,
        ReviseActivePlanRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=case.node.parent,
            expected_work_revision=read_work(root, case.node.parent, owner).revision,
            expected_plan_revision=1,
            plan=nested_plan,
            nodes=(
                PlanNodeDecision(
                    role="g",
                    decision="replace",
                    work_id=old.work_id,
                    replacement=middle.work_id,
                    closure=NodeClosure(
                        expected_revision=1, outcome="cancelled", basis="Replace old G"
                    ),
                    nested_plan=middle_plan,
                ),
            ),
        ),
        owner,
    )
    nested_case = case.node._replace(works={"g": middle.work_id})
    middle_case = Case(
        root,
        space,
        owner,
        case.setup.activity,
        middle.work_id,
        {"g": required.work_id, "spare": spare.work_id},
    )
    _issue(nested_case, "g")
    _issue(middle_case, "g")
    _issue(middle_case, "spare")
    result = _result(root, space, owner, required.work_id, "final", b"Required L result")
    leaf_acceptance = read_work(root, required.work_id, owner).state.acceptance
    assert leaf_acceptance is not None
    leaf_receipt = read_receipt(root, leaf_acceptance.operation_id, owner)
    attempt = invocation = None
    if running_spare:
        resource = _resource(root, space, owner, spare.work_id, "replaced-root-resource")
        attempt, session, _request, _receipt = _assign(root, space, owner, spare.work_id, resource)
        _claim(root, space, owner, spare.work_id, attempt, session)
        invocation = _invocation(root, space, owner, spare.work_id, attempt, session, finish=False)
    _confirm(middle_case, "g_final", result)
    apply_operation(root, _link_request(middle_case, result), owner)
    middle_acceptance = _accept_request(middle_case)
    middle_receipt = apply_operation(root, middle_acceptance, owner)
    assert read_work(root, middle.work_id, owner).state.status == "succeeded"
    assert read_work(root, spare.work_id, owner).state.status == "proposed"

    replacement = middle.model_copy(update={"work_id": uuid4()})
    fresh = old.model_copy(update={"work_id": uuid4()})
    next_plan = nested_plan.model_copy(update={"children": (replacement,)})

    def request(descendants: tuple[DescendantClosure, ...]) -> ReviseActivePlanRequest:
        return ReviseActivePlanRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=case.node.parent,
            expected_work_revision=read_work(root, case.node.parent, owner).revision,
            expected_plan_revision=read_work_plan(root, case.node.parent, owner).revision,
            plan=next_plan,
            nodes=(
                PlanNodeDecision(
                    role="g",
                    decision="replace",
                    work_id=middle.work_id,
                    replacement=replacement.work_id,
                    nested_plan=case.nested_plan.model_copy(update={"children": (fresh,)}),
                    descendants=descendants,
                ),
            ),
        )

    _refused(case.node, "open_children", request(()))
    _refused(
        case.node,
        "work_closed",
        CloseWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=spare.work_id,
            expected_revision=read_work(root, spare.work_id, owner).revision,
            outcome="cancelled",
            basis="Direct action below accepted H",
        ),
    )
    closure = DescendantClosure(
        parent_work_id=middle.work_id,
        expected_plan_revision=read_work_plan(root, middle.work_id, owner).revision,
        role="spare",
        work_id=spare.work_id,
        closure=NodeClosure(
            expected_revision=read_work(root, spare.work_id, owner).revision,
            outcome="cancelled",
            basis="Explicitly stop S under replaced H",
        ),
    )
    _refused(
        case.node,
        "stale_plan",
        request((closure.model_copy(update={"expected_plan_revision": 99}),)),
    )
    _refused(
        case.node,
        "stale_work",
        request(
            (
                closure.model_copy(
                    update={"closure": closure.closure.model_copy(update={"expected_revision": 1})}
                ),
            )
        ),
    )
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest,
        grant_id=uuid4(),
        state=GrantState(grantee="worker", actions=("work.write", "method.use", "record.read")),
    )
    worker = authorize_local(root, actor="worker", source_ref="synthetic-worker")
    denied = request((closure,)).model_copy(update={"operation_id": uuid4(), "actor": "worker"})
    _refused(case.node._replace(owner=worker), "permission_denied", denied)
    committed = request((closure,))
    receipt = apply_operation(root, committed, owner)
    assert apply_operation(root, committed, owner) == receipt
    assert read_work(root, case.node.parent, owner).state.status == "proposed"
    assert read_work(root, middle.work_id, owner).state.status == "succeeded"
    assert read_work(root, required.work_id, owner).state.status == "succeeded"
    assert read_work(root, spare.work_id, owner).state.status == "cancelled"
    assert read_work(root, replacement.work_id, owner).state.status == "proposed"
    assert read_work(root, case.anchor.work_id, owner).state.status == "proposed"
    assert apply_operation(root, middle_acceptance, owner) == middle_receipt
    assert read_receipt(root, middle_acceptance.operation_id, owner) == middle_receipt
    assert read_receipt(root, leaf_acceptance.operation_id, owner) == leaf_receipt
    if running_spare:
        assert attempt is not None and invocation is not None
        execution = read_execution(root, spare.work_id, owner)
        assert next(a for a in execution.assignments if a.attempt_id == attempt).status == (
            "stop_requested"
        )
        assert next(i for i in execution.invocations if i.invocation_id == invocation).status == (
            "unknown"
        )
        assert execution.held_units == 5
