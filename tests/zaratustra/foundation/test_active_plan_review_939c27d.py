"""Regressions from the Windows reviews of the 3.6–3.7 package."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from tests.zaratustra.foundation.test_active_plan import (
    _delete_in_new_process,
    _keep,
    _leave,
    _release,
    _replace,
    _revision_request,
    _seeded,
)
from tests.zaratustra.foundation.test_applicability import (
    Case,
    _confirm_request,
    _issue,
    _space,
)
from tests.zaratustra.foundation.test_composition import _apply, _result, _sqlite_contains
from tests.zaratustra.foundation.test_revalidation import _changed, _recheck_request
from zaratustra.foundation import (
    AcceptWorkRequest,
    ArtifactRef,
    CloseWorkRequest,
    CreateArtifactRequest,
    CreateCompositeWorkRequest,
    DeleteArtifactRequest,
    DeleteWorkRequest,
    DomainRequest,
    FoundationError,
    LinkedOutput,
    LinkWorkOutputRequest,
    PlanCondition,
    ReviseArtifactRequest,
    ReviseWorkPlanRequest,
    RoleFilling,
    apply_operation,
    complete_deletions,
    create_backup,
    read_obligation,
    read_plan_nodes,
    read_receipt,
    read_revalidation,
    read_role_history,
    read_work,
    read_work_plan,
)


def _fresh_plan_is_unavailable(root: Path, parent: str) -> None:
    code = """
import sys
from pathlib import Path
from uuid import UUID
from zaratustra.foundation import FoundationError, authorize_local, read_work_plan

p = Path(sys.argv[1])
owner = authorize_local(p, actor="owner", source_ref="restart")
try:
    read_work_plan(p, UUID(sys.argv[2]), owner, revision=2)
except FoundationError as error:
    assert error.code == "content_unavailable"
else:
    raise AssertionError("plan stayed readable")
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(root),
            parent,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_replacement_rationale_citing_departed_goal_is_sanitized(tmp_path: Path) -> None:
    setup = _space(tmp_path)
    root, space, owner = setup.root, setup.space, setup.owner
    original = read_work_plan(root, setup.seeded, owner).plan
    parent_state = read_work(root, setup.seeded, owner).state
    marker = f"replaced-work-goal-{uuid4()}"
    old_a, old_b = original.children
    a = old_a.model_copy(
        update={
            "work_id": uuid4(),
            "state": old_a.state.model_copy(update={"goal": marker}),
        }
    )
    b = old_b.model_copy(update={"work_id": uuid4()})
    parent = uuid4()
    plan = original.model_copy(update={"children": (a, b)})
    apply_operation(
        root,
        CreateCompositeWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=parent,
            state=parent_state,
            plan=plan,
        ),
        owner,
    )
    case = Case(root, space, owner, setup.activity, parent, {"a": a.work_id, "b": b.work_id})
    _issue(case, "a")
    a2 = a.model_copy(
        update={
            "work_id": uuid4(),
            "state": a.state.model_copy(update={"goal": "Independent replacement A2"}),
        }
    )
    revised = plan.model_copy(
        update={"children": (a2, b), "rationale": f"Replace A whose goal was {marker}"}
    )
    request = _revision_request(
        case, revised, (_replace(case, a, a2, outcome="cancelled"), _keep(b))
    )
    apply_operation(root, request, owner)
    assert read_work(root, a.work_id, owner).state.status == "cancelled"
    after = case._replace(works={"a": a2.work_id, "b": b.work_id})
    _issue(after, "a")
    y = _result(root, space, owner, a2.work_id, "checked", b"independent A2 evidence")
    apply_operation(root, _confirm_request(after, "checked", y), owner)

    old_backup = create_backup(root, uuid4(), owner)
    _apply(
        root,
        space,
        owner,
        DeleteWorkRequest,
        work_id=a.work_id,
        expected_revision=read_work(root, a.work_id, owner).revision,
    )
    complete = complete_deletions(root, owner)
    assert complete.live_store_sanitized and complete.pending_jobs == 0
    assert not old_backup.package.exists()
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_work_plan(root, parent, owner, revision=2)
    _fresh_plan_is_unavailable(root, str(parent))
    assert not _sqlite_contains(root / ".zara-core", marker)
    fresh_backup = create_backup(root, uuid4(), owner)
    assert not _sqlite_contains(fresh_backup.package, marker)
    node = read_plan_nodes(root, parent, owner, revision=2).nodes[0]
    assert (node.role, node.decision, node.work_id, node.replaced_work_id) == (
        "a",
        "replace",
        a2.work_id,
        a.work_id,
    )
    assert read_role_history(root, parent, "a", owner) == (
        RoleFilling(role="a", work_id=a.work_id, first_plan_revision=1, last_plan_revision=1),
        RoleFilling(role="a", work_id=a2.work_id, first_plan_revision=2),
    )
    checked = read_obligation(root, parent, "checked", owner)
    assert checked.status == "satisfied" and checked.evidence == y
    assert read_work(root, a2.work_id, owner).state.acceptance is not None
    assert read_work(root, a2.work_id, owner).state.acceptance.basis == "Checked synthetic output"  # type: ignore[union-attr]

    # The retained index still identifies A2 when another deletion runs after restart.
    _delete_in_new_process(root, space, a2.work_id, read_work(root, a2.work_id, owner).revision)
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_obligation(root, parent, "checked", owner, revision=checked.revision)
    assert read_obligation(root, parent, "checked", owner).status == "open"


@pytest.mark.parametrize("decision", ["cancel", "release"])
def test_departing_node_decisions_sanitize_revision_rationale(
    tmp_path: Path, decision: str
) -> None:
    case, plan = _seeded(_space(tmp_path))
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    a, b = plan.children
    _issue(case, "a")
    if decision == "release":
        _result(root, space, owner, a.work_id, "checked", b"finished A")
    marker = f"departed-{decision}-{uuid4()}"
    revised = plan.model_copy(
        update={
            "children": (b.model_copy(update={"readiness": None}),),
            "completion": PlanCondition(kind="work_succeeded", role="b"),
            "rationale": marker,
        }
    )
    leaving = _leave(case, a, "cancel") if decision == "cancel" else _release(a)
    apply_operation(root, _revision_request(case, revised, (leaving, _keep(b))), owner)
    _apply(
        root,
        space,
        owner,
        DeleteWorkRequest,
        work_id=a.work_id,
        expected_revision=read_work(root, a.work_id, owner).revision,
    )
    assert complete_deletions(root, owner).live_store_sanitized
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_work_plan(root, parent, owner, revision=2)
    assert not _sqlite_contains(root / ".zara-core", marker)
    assert read_plan_nodes(root, parent, owner, revision=2).nodes[0].work_id == a.work_id


def test_deleting_old_artifact_preserves_replacement_evidence_and_replay(tmp_path: Path) -> None:
    case, plan = _seeded(_space(tmp_path))
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    a, b = plan.children
    _issue(case, "a")
    old_marker = f"old-X-{uuid4()}"
    x = _result(root, space, owner, a.work_id, "checked", old_marker.encode("utf-8"))
    old_confirmation = _confirm_request(case, "checked", x)
    apply_operation(root, old_confirmation, owner)
    a2 = a.model_copy(
        update={"work_id": uuid4(), "state": a.state.model_copy(update={"goal": "Independent A2"})}
    )
    revised = plan.model_copy(update={"children": (a2, b), "rationale": "Use A2"})
    apply_operation(
        root, _revision_request(case, revised, (_replace(case, a, a2), _keep(b))), owner
    )
    after = case._replace(works={"a": a2.work_id, "b": b.work_id})
    _issue(after, "a")
    y = _result(root, space, owner, a2.work_id, "checked", b"independent Y")
    new_confirmation = _confirm_request(after, "checked", y)
    new_receipt = apply_operation(root, new_confirmation, owner)
    before = read_obligation(root, parent, "checked", owner)
    assert before.status == "satisfied" and before.revision == 4 and before.evidence == y
    assert x not in read_work(root, a2.work_id, owner).state.inputs
    assert all(
        output.artifact != x for output in read_work(root, a2.work_id, owner).state.linked_outputs
    )
    assert all(
        output.artifact != x for output in read_work(root, parent, owner).state.linked_outputs
    )

    _apply(
        root, space, owner, DeleteArtifactRequest, artifact_id=x.artifact_id, expected_revision=1
    )
    complete = complete_deletions(root, owner)
    assert complete.live_store_sanitized and complete.pending_jobs == 0
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_obligation(root, parent, "checked", owner, revision=2)
    current = read_obligation(root, parent, "checked", owner)
    assert current == before
    acceptance = read_work(root, a2.work_id, owner).state.acceptance
    assert acceptance is not None and acceptance.basis == "Checked synthetic output"
    assert read_receipt(root, new_confirmation.operation_id, owner) == new_receipt
    assert apply_operation(root, new_confirmation, owner) == new_receipt
    assert not _sqlite_contains(root / ".zara-core", old_marker)
    new_backup = create_backup(root, uuid4(), owner)
    assert not _sqlite_contains(new_backup.package, old_marker)
    assert read_obligation(root, parent, "checked", owner).evidence == y
    restarted = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; from uuid import UUID; "
            "from zaratustra.foundation import authorize_local, read_obligation, "
            "read_receipt, read_work; p=Path(sys.argv[1]); "
            "o=authorize_local(p, actor='owner', source_ref='restart'); "
            "w=UUID(sys.argv[2]); a=UUID(sys.argv[3]); op=UUID(sys.argv[4]); "
            "assert read_obligation(p,w,'checked',o).status=='satisfied'; "
            "assert read_obligation(p,w,'checked',o).revision==4; "
            "assert read_work(p,a,o).state.acceptance.basis=='Checked synthetic output'; "
            "assert read_receipt(p,op,o).operation_id==op",
            str(root),
            str(parent),
            str(a2.work_id),
            str(new_confirmation.operation_id),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert restarted.returncode == 0, restarted.stderr


def _pre_issue_plan_basis(
    tmp_path: Path, *, with_input: bool
) -> tuple[Case, ArtifactRef, ArtifactRef | None, str]:
    """One Work A is named in plan 1 with X, then issued under plan 2 without X."""

    setup = _space(tmp_path)
    root, space, owner = setup.root, setup.space, setup.owner
    marker = f"historical-plan-X-{uuid4()}"
    x = ArtifactRef(artifact_id=uuid4(), revision=1)
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=x.artifact_id,
        media_type="text/plain",
        content=marker.encode("utf-8"),
    )
    z = ArtifactRef(artifact_id=uuid4(), revision=1) if with_input else None
    if z is not None:
        _apply(
            root,
            space,
            owner,
            CreateArtifactRequest,
            artifact_id=z.artifact_id,
            media_type="text/plain",
            content=b"independent input Z",
        )
    template = read_work_plan(root, setup.seeded, owner).plan
    old_a, old_b = template.children
    a = old_a.model_copy(
        update={
            "work_id": uuid4(),
            "state": old_a.state.model_copy(
                update={"inputs": old_a.state.inputs + ((z,) if z is not None else ())}
            ),
        }
    )
    b = old_b.model_copy(update={"work_id": uuid4()})
    plan1 = template.model_copy(
        update={"children": (a, b), "basis": template.basis + (x,), "rationale": "Plan 1"}
    )
    parent = uuid4()
    apply_operation(
        root,
        CreateCompositeWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=parent,
            state=read_work(root, setup.seeded, owner).state,
            plan=plan1,
        ),
        owner,
    )
    plan2 = plan1.model_copy(update={"basis": template.basis, "rationale": "Plan 2"})
    apply_operation(
        root,
        ReviseWorkPlanRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=parent,
            expected_plan_revision=1,
            plan=plan2,
        ),
        owner,
    )
    case = Case(root, space, owner, setup.activity, parent, {"a": a.work_id, "b": b.work_id})
    assert x in read_work_plan(root, parent, owner, revision=1).plan.basis
    assert read_work_plan(root, parent, owner).revision == 2
    assert x not in read_work_plan(root, parent, owner).plan.basis
    assert [node.work_id for node in read_work_plan(root, parent, owner).plan.children] == [
        a.work_id,
        b.work_id,
    ]
    _issue(case, "a")
    return case, x, z, marker


@pytest.mark.parametrize("outcome", ["accepted", "failed", "revalidated"])
def test_pre_issue_plan_basis_retires_later_outcome_text(tmp_path: Path, outcome: str) -> None:
    case, x, z, marker = _pre_issue_plan_basis(tmp_path, with_input=outcome == "revalidated")
    root, space, owner, parent, a = case.root, case.space, case.owner, case.parent, case.works["a"]
    basis = f"Independent outcome quotes historical X: {marker}"
    request: DomainRequest
    if outcome == "failed":
        request = CloseWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=a,
            expected_revision=read_work(root, a, owner).revision,
            outcome="failed",
            basis=basis,
        )
    else:
        result = ArtifactRef(artifact_id=uuid4(), revision=1)
        _apply(
            root,
            space,
            owner,
            CreateArtifactRequest,
            artifact_id=result.artifact_id,
            media_type="text/plain",
            content=b"neutral result",
        )
        _apply(
            root,
            space,
            owner,
            LinkWorkOutputRequest,
            work_id=a,
            expected_revision=read_work(root, a, owner).revision,
            output=LinkedOutput(slot="checked", artifact=result),
        )
        accepted = AcceptWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=a,
            expected_revision=read_work(root, a, owner).revision,
            basis=basis if outcome == "accepted" else "Neutral acceptance",
        )
        apply_operation(root, accepted, owner)
        if outcome == "accepted":
            request = accepted
        else:
            assert z is not None
            _apply(
                root,
                space,
                owner,
                ReviseArtifactRequest,
                artifact_id=z.artifact_id,
                expected_revision=1,
                media_type="text/plain",
                content=b"changed Z",
            )
            request = _recheck_request(case, (_changed(z.artifact_id, 1, 2),), basis=basis)
    receipt = (
        apply_operation(root, request, owner)
        if outcome != "accepted"
        else read_receipt(root, request.operation_id, owner)
    )
    old_backup = create_backup(root, uuid4(), owner)
    _apply(
        root, space, owner, DeleteArtifactRequest, artifact_id=x.artifact_id, expected_revision=1
    )
    completed = complete_deletions(root, owner)
    assert completed.live_store_sanitized and completed.pending_jobs == 0
    assert not old_backup.package.exists()
    assert read_work(root, a, owner).state.status == (
        "failed" if outcome == "failed" else "succeeded"
    )
    if outcome == "revalidated":
        assert read_revalidation(root, parent, a, owner).basis is None
        assert read_work(root, a, owner).state.acceptance is not None
        # The earlier acceptance is structurally dependent on plan 1 as well.
        assert read_work(root, a, owner).state.acceptance.basis is None  # type: ignore[union-attr]
    elif outcome == "accepted":
        assert read_work(root, a, owner).state.acceptance is not None
        assert read_work(root, a, owner).state.acceptance.basis is None  # type: ignore[union-attr]
    else:
        assert read_work(root, a, owner).state.closure is not None
        assert read_work(root, a, owner).state.closure.basis is None  # type: ignore[union-attr]
    with pytest.raises(FoundationError, match="history_unavailable"):
        apply_operation(root, request, owner)
    with pytest.raises(FoundationError, match="not_found"):
        read_receipt(root, receipt.operation_id, owner)
    assert not _sqlite_contains(root / ".zara-core", marker)
    assert not _sqlite_contains(create_backup(root, uuid4(), owner).package, marker)
    code = """
import sys
from pathlib import Path
from uuid import UUID
from zaratustra.foundation import authorize_local, read_revalidation, read_work
p = Path(sys.argv[1])
owner = authorize_local(p, actor="owner", source_ref="restart")
parent, a, mode = UUID(sys.argv[2]), UUID(sys.argv[3]), sys.argv[4]
state = read_work(p, a, owner).state
if mode == "revalidated":
    assert read_revalidation(p, parent, a, owner).basis is None
elif mode == "accepted":
    assert state.acceptance is not None and state.acceptance.basis is None
else:
    assert state.closure is not None and state.closure.basis is None
"""
    restarted = subprocess.run(
        [sys.executable, "-c", code, str(root), str(parent), str(a), outcome],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert restarted.returncode == 0, restarted.stderr
