"""Deletion follows saved Artifact dependencies through nested Work membership."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from tests.zaratustra.foundation.test_applicability import (
    Case,
    _accept_request,
    _confirm,
    _confirm_request,
    _issue,
    _link_request,
)
from tests.zaratustra.foundation.test_composition import _apply, _result, _sqlite_contains
from tests.zaratustra.foundation.test_nested_composition import Nested, _add_nested, _nested
from zaratustra.foundation import (
    AcceptWorkRequest,
    ArtifactRef,
    CloseWorkRequest,
    CreateArtifactRequest,
    DeleteArtifactRequest,
    DomainRequest,
    FoundationError,
    PlanCondition,
    PlanNodeDecision,
    RecoverRequest,
    ReviseActivePlanRequest,
    ReviseArtifactRequest,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    read_artifact,
    read_obligation,
    read_receipt,
    read_revalidation,
    read_work,
    read_work_plan,
    restore_backup,
)


def _case_with_grandchild_input(
    tmp_path: Path, *, in_nested_plan: bool = False
) -> tuple[Nested, ArtifactRef, str]:
    case = _nested(tmp_path)
    marker = f"synthetic nested private input {uuid4()}"
    artifact_id = uuid4()
    _apply(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        CreateArtifactRequest,
        artifact_id=artifact_id,
        media_type="text/plain",
        content=marker.encode(),
    )
    source = ArtifactRef(artifact_id=artifact_id, revision=1)
    grandchild = case.nested_child.model_copy(
        update={
            "state": case.nested_child.state.model_copy(
                update={"inputs": () if in_nested_plan else (source,)}
            )
        }
    )
    case = case._replace(
        nested_child=grandchild,
        nested_plan=case.nested_plan.model_copy(
            update={
                "children": (grandchild,),
                "basis": (source,) if in_nested_plan else (),
            }
        ),
    )
    apply_operation(case.setup.root, _add_nested(case), case.setup.owner)
    return case, source, marker


def _accept_nested(case: Nested) -> ArtifactRef:
    _issue(case.parent, "review")
    _issue(case.node, "g")
    result = _result(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        case.nested_child.work_id,
        "final",
        b"Independent nested output Y",
    )
    _confirm(case.node, "g_final", result)
    apply_operation(case.setup.root, _link_request(case.node, result), case.setup.owner)
    apply_operation(case.setup.root, _accept_request(case.node), case.setup.owner)
    return result


def _delete_artifact(case: Nested, source: ArtifactRef) -> None:
    _apply(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        DeleteArtifactRequest,
        artifact_id=source.artifact_id,
        expected_revision=source.revision,
    )
    report = complete_deletions(case.setup.root, case.setup.owner)
    assert report.pending_jobs == 0 and report.live_store_sanitized


def _history_unavailable(case: Nested, request: DomainRequest) -> None:
    with pytest.raises(FoundationError, match="history_unavailable"):
        apply_operation(case.setup.root, request, case.setup.owner)
    with pytest.raises(FoundationError, match="not_found"):
        read_receipt(case.setup.root, request.operation_id, case.setup.owner)


@pytest.mark.parametrize("in_nested_plan", [False, True])
def test_grandchild_input_retires_root_acceptance_and_confirmation(
    tmp_path: Path, in_nested_plan: bool
) -> None:
    case, source, marker = _case_with_grandchild_input(tmp_path, in_nested_plan=in_nested_plan)
    result = _accept_nested(case)
    confirmation = _confirm_request(case.parent, "reviewed", result).model_copy(
        update={"basis": f"Confirmed after grandchild input: {marker}"}
    )
    apply_operation(case.setup.root, confirmation, case.setup.owner)
    apply_operation(case.setup.root, _link_request(case.parent, result), case.setup.owner)
    acceptance = _accept_request(case.parent).model_copy(
        update={"basis": f"Accepted after grandchild input: {marker}"}
    )
    apply_operation(case.setup.root, acceptance, case.setup.owner)
    old = create_backup(case.setup.root, uuid4(), case.setup.owner)

    _delete_artifact(case, source)
    assert not old.package.exists()
    accepted = read_work(case.setup.root, case.parent.parent, case.setup.owner).state.acceptance
    assert accepted is not None and accepted.basis is None
    assert (
        read_obligation(case.setup.root, case.parent.parent, "reviewed", case.setup.owner).basis
        is None
    )
    _history_unavailable(case, acceptance)
    _history_unavailable(case, confirmation)
    assert not _sqlite_contains(case.setup.root / ".zara-core", marker)
    clean = create_backup(case.setup.root, uuid4(), case.setup.owner)
    assert not _sqlite_contains(clean.package, marker)

    fresh = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-c",
            "from pathlib import Path; from uuid import UUID; "
            "from zaratustra.foundation import authorize_local, read_work; "
            "import sys; p=Path(sys.argv[1]); w=UUID(sys.argv[2]); "
            "a=authorize_local(p,actor='owner',source_ref='restart'); "
            "assert read_work(p,w,a).state.acceptance.basis is None",
            str(case.setup.root),
            str(case.parent.parent),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert fresh.returncode == 0, fresh.stderr

    restored = tmp_path / "restored"
    restored.mkdir()
    info = restore_backup(
        clean.package, restored, authorize_recovery(actor="owner", source_ref="restore")
    )
    assert info.recovery_state == "quarantined"
    assert not _sqlite_contains(restored / ".zara-core", marker)
    apply_operation(
        restored,
        RecoverRequest(
            operation_id=uuid4(),
            space_id=case.setup.space,
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        authorize_recovery(actor="owner", source_ref="recovery"),
    )
    reopened = authorize_local(restored, actor="owner", source_ref="new-epoch")
    restored_acceptance = read_work(restored, case.parent.parent, reopened).state.acceptance
    assert restored_acceptance is not None and restored_acceptance.basis is None


def test_grandchild_input_retires_root_closure_basis(tmp_path: Path) -> None:
    case, source, marker = _case_with_grandchild_input(tmp_path)
    _issue(case.parent, "review")
    _issue(case.node, "g")
    for work in (case.nested_child.work_id, case.node.parent, case.anchor.work_id):
        apply_operation(
            case.setup.root,
            CloseWorkRequest(
                operation_id=uuid4(),
                space_id=case.setup.space,
                actor="owner",
                work_id=work,
                expected_revision=read_work(case.setup.root, work, case.setup.owner).revision,
                outcome="cancelled",
                basis="Synthetic branch closure",
            ),
            case.setup.owner,
        )
    closure = CloseWorkRequest(
        operation_id=uuid4(),
        space_id=case.setup.space,
        actor="owner",
        work_id=case.parent.parent,
        expected_revision=read_work(case.setup.root, case.parent.parent, case.setup.owner).revision,
        outcome="failed",
        basis=f"Root failed after grandchild input: {marker}",
    )
    apply_operation(case.setup.root, closure, case.setup.owner)
    _delete_artifact(case, source)
    closed = read_work(case.setup.root, case.parent.parent, case.setup.owner).state.closure
    assert closed is not None and closed.basis is None
    _history_unavailable(case, closure)
    assert not _sqlite_contains(case.setup.root / ".zara-core", marker)


def test_grandchild_input_retires_result_recheck_basis(tmp_path: Path) -> None:
    from zaratustra.foundation import PremiseChange, RevalidateResultRequest

    case, source, marker = _case_with_grandchild_input(tmp_path)
    _issue(case.parent, "review")
    _issue(case.node, "g")
    _result(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        case.nested_child.work_id,
        "final",
        b"Independent grandchild result",
    )
    _apply(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        ReviseArtifactRequest,
        artifact_id=source.artifact_id,
        expected_revision=1,
        media_type="text/plain",
        content=b"Revised grandchild input",
    )
    recheck = RevalidateResultRequest(
        operation_id=uuid4(),
        space_id=case.setup.space,
        actor="owner",
        parent_work_id=case.node.parent,
        role="g",
        work_id=case.nested_child.work_id,
        outputs=read_work(
            case.setup.root, case.nested_child.work_id, case.setup.owner
        ).state.linked_outputs,
        expected_plan_revision=1,
        premises=(
            PremiseChange(kind="artifact", record_id=source.artifact_id, revision=1, current=2),
        ),
        basis=f"Rechecked with grandchild input: {marker}",
    )
    apply_operation(case.setup.root, recheck, case.setup.owner)
    _delete_artifact(case, ArtifactRef(artifact_id=source.artifact_id, revision=2))
    assert (
        read_revalidation(
            case.setup.root, case.node.parent, case.nested_child.work_id, case.setup.owner
        ).basis
        is None
    )
    _history_unavailable(case, recheck)
    assert not _sqlite_contains(case.setup.root / ".zara-core", marker)


def test_nested_index_survives_sequential_deletions_and_restart(tmp_path: Path) -> None:
    case, source, marker = _case_with_grandchild_input(tmp_path)
    # A separate role has its own readiness Artifact. The review confirmation must
    # survive its deletion, but the sanitized plan must still remember G's input X.
    unrelated_id = uuid4()
    _apply(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        CreateArtifactRequest,
        artifact_id=unrelated_id,
        media_type="text/plain",
        content=b"Unrelated anchor condition",
    )
    unrelated = ArtifactRef(artifact_id=unrelated_id, revision=1)
    anchor = case.anchor.model_copy(
        update={"readiness": PlanCondition(kind="artifact_current", artifact=unrelated)}
    )
    case = case._replace(
        anchor=anchor,
        next_plan=case.next_plan.model_copy(
            update={"children": (anchor, case.next_plan.children[1])}
        ),
    )
    # The nested node was already added in revision 2. A further revision keeps it
    # while adding an independent readiness leaf to anchor.
    revision = ReviseActivePlanRequest(
        operation_id=uuid4(),
        space_id=case.setup.space,
        actor="owner",
        work_id=case.parent.parent,
        expected_plan_revision=2,
        expected_work_revision=read_work(
            case.setup.root, case.parent.parent, case.setup.owner
        ).revision,
        plan=case.next_plan,
        nodes=(
            PlanNodeDecision(role="anchor", decision="keep", work_id=anchor.work_id),
            PlanNodeDecision(role="review", decision="keep", work_id=case.node.parent),
        ),
    )
    apply_operation(case.setup.root, revision, case.setup.owner)
    result = _accept_nested(case)
    confirmation = _confirm_request(case.parent, "reviewed", result).model_copy(
        update={"basis": f"Review is based on nested input: {marker}"}
    )
    apply_operation(case.setup.root, confirmation, case.setup.owner)

    _delete_artifact(case, unrelated)
    assert (
        read_obligation(case.setup.root, case.parent.parent, "reviewed", case.setup.owner).basis
        == confirmation.basis
    )
    assert (
        read_receipt(case.setup.root, confirmation.operation_id, case.setup.owner).operation_id
        == confirmation.operation_id
    )
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_work_plan(case.setup.root, case.parent.parent, case.setup.owner, revision=3)
    middle = create_backup(case.setup.root, uuid4(), case.setup.owner)

    fresh = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-c",
            "from pathlib import Path; from uuid import UUID,uuid4; "
            "from zaratustra.foundation import DeleteArtifactRequest,apply_operation,"
            "authorize_local,complete_deletions,read_artifact; import sys; "
            "p=Path(sys.argv[1]); s=UUID(sys.argv[2]); x=UUID(sys.argv[3]); "
            "a=authorize_local(p,actor='owner',source_ref='restart'); "
            "q=DeleteArtifactRequest(operation_id=uuid4(),space_id=s,actor='owner',"
            "artifact_id=x,expected_revision=read_artifact(p,x,a).revision); "
            "apply_operation(p,q,a); r=complete_deletions(p,a); "
            "assert r.pending_jobs==0 and r.live_store_sanitized",
            str(case.setup.root),
            str(case.setup.space),
            str(source.artifact_id),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert fresh.returncode == 0, fresh.stderr
    assert not middle.package.exists()
    assert (
        read_obligation(case.setup.root, case.parent.parent, "reviewed", case.setup.owner).basis
        is None
    )
    _history_unavailable(case, confirmation)
    assert not _sqlite_contains(case.setup.root / ".zara-core", marker)
    assert not _sqlite_contains(
        create_backup(case.setup.root, uuid4(), case.setup.owner).package, marker
    )


def test_replacement_nested_branch_keeps_independent_history(tmp_path: Path) -> None:
    case, source, marker = _case_with_grandchild_input(tmp_path)
    _accept_nested(case)
    replacement_id, next_grandchild_id = uuid4(), uuid4()
    replacement = case.next_plan.children[1].model_copy(update={"work_id": replacement_id})
    next_grandchild = case.nested_child.model_copy(
        update={
            "work_id": next_grandchild_id,
            "state": case.nested_child.state.model_copy(update={"inputs": (), "goal": "New work"}),
        }
    )
    next_nested_plan = case.nested_plan.model_copy(
        update={"children": (next_grandchild,), "rationale": "Independent new nested branch"}
    )
    next_root_plan = case.next_plan.model_copy(
        update={
            "children": (case.anchor, replacement),
            "rationale": "Replace old nested branch with independent work",
        }
    )
    apply_operation(
        case.setup.root,
        ReviseActivePlanRequest(
            operation_id=uuid4(),
            space_id=case.setup.space,
            actor="owner",
            work_id=case.parent.parent,
            expected_plan_revision=2,
            expected_work_revision=read_work(
                case.setup.root, case.parent.parent, case.setup.owner
            ).revision,
            plan=next_root_plan,
            nodes=(
                PlanNodeDecision(role="anchor", decision="keep", work_id=case.anchor.work_id),
                PlanNodeDecision(
                    role="review",
                    decision="replace",
                    work_id=case.node.parent,
                    replacement=replacement_id,
                    nested_plan=next_nested_plan,
                ),
            ),
        ),
        case.setup.owner,
    )
    replacement_case = case._replace(
        parent=Case(
            case.setup.root,
            case.setup.space,
            case.setup.owner,
            case.setup.activity,
            case.parent.parent,
            {"anchor": case.anchor.work_id, "review": replacement_id},
        ),
        node=Case(
            case.setup.root,
            case.setup.space,
            case.setup.owner,
            case.setup.activity,
            replacement_id,
            {"g": next_grandchild_id},
        ),
        nested_child=next_grandchild,
        nested_plan=next_nested_plan,
    )
    independent = _accept_nested(replacement_case)
    _issue(replacement_case.parent, "anchor")
    _result(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        case.anchor.work_id,
        "other",
        b"Independent sibling result Z",
    )
    confirmation = _confirm_request(replacement_case.parent, "reviewed", independent).model_copy(
        update={"basis": "New branch independently confirmed Y"}
    )
    receipt = apply_operation(case.setup.root, confirmation, case.setup.owner)
    replacement_work = read_work(case.setup.root, replacement_id, case.setup.owner)
    replacement_acceptance = replacement_work.state.acceptance
    assert replacement_acceptance is not None
    replacement_replay = AcceptWorkRequest(
        operation_id=replacement_acceptance.operation_id,
        space_id=case.setup.space,
        actor="owner",
        work_id=replacement_id,
        expected_revision=replacement_work.revision - 1,
        basis="Synthetic parent acceptance",
    )
    replacement_receipt = read_receipt(
        case.setup.root, replacement_acceptance.operation_id, case.setup.owner
    )
    sibling_work = read_work(case.setup.root, case.anchor.work_id, case.setup.owner)
    sibling_acceptance = sibling_work.state.acceptance
    assert sibling_acceptance is not None
    sibling_replay = AcceptWorkRequest(
        operation_id=sibling_acceptance.operation_id,
        space_id=case.setup.space,
        actor="owner",
        work_id=case.anchor.work_id,
        expected_revision=sibling_work.revision - 1,
        basis="Checked synthetic output",
    )
    sibling_receipt = read_receipt(
        case.setup.root, sibling_acceptance.operation_id, case.setup.owner
    )
    old = create_backup(case.setup.root, uuid4(), case.setup.owner)

    _delete_artifact(case, source)
    assert not old.package.exists()
    assert (
        read_work(case.setup.root, replacement_id, case.setup.owner).state.acceptance
        == replacement_acceptance
    )
    assert (
        read_work(case.setup.root, case.anchor.work_id, case.setup.owner).state.acceptance
        == sibling_acceptance
    )
    assert (
        apply_operation(case.setup.root, replacement_replay, case.setup.owner)
        == replacement_receipt
    )
    assert apply_operation(case.setup.root, sibling_replay, case.setup.owner) == sibling_receipt
    assert read_artifact(case.setup.root, independent.artifact_id, case.setup.owner).revision == 1
    assert (
        read_obligation(case.setup.root, case.parent.parent, "reviewed", case.setup.owner).basis
        == confirmation.basis
    )
    assert apply_operation(case.setup.root, confirmation, case.setup.owner) == receipt
    assert read_receipt(case.setup.root, confirmation.operation_id, case.setup.owner) == receipt
    assert read_work_plan(case.setup.root, case.parent.parent, case.setup.owner).revision == 3
    assert not _sqlite_contains(case.setup.root / ".zara-core", marker)


def test_historical_nested_plan_before_grandchild_issue_remains_dependency(
    tmp_path: Path,
) -> None:
    case, source, marker = _case_with_grandchild_input(tmp_path, in_nested_plan=True)
    _issue(case.parent, "review")
    apply_operation(
        case.setup.root,
        ReviseActivePlanRequest(
            operation_id=uuid4(),
            space_id=case.setup.space,
            actor="owner",
            work_id=case.node.parent,
            expected_plan_revision=1,
            expected_work_revision=read_work(
                case.setup.root, case.node.parent, case.setup.owner
            ).revision,
            plan=case.nested_plan.model_copy(
                update={"basis": (), "rationale": "Current nested plan omits old basis"}
            ),
            nodes=(PlanNodeDecision(role="g", decision="keep", work_id=case.nested_child.work_id),),
        ),
        case.setup.owner,
    )
    _issue(case.node, "g")
    result = _result(
        case.setup.root,
        case.setup.space,
        case.setup.owner,
        case.nested_child.work_id,
        "final",
        b"Result after nested plan revision",
    )
    _confirm(case.node, "g_final", result)
    apply_operation(case.setup.root, _link_request(case.node, result), case.setup.owner)
    apply_operation(case.setup.root, _accept_request(case.node), case.setup.owner)
    _confirm(case.parent, "reviewed", result)
    apply_operation(case.setup.root, _link_request(case.parent, result), case.setup.owner)
    acceptance = _accept_request(case.parent).model_copy(
        update={"basis": f"Historical nested plan source: {marker}"}
    )
    apply_operation(case.setup.root, acceptance, case.setup.owner)
    _delete_artifact(case, source)
    accepted = read_work(case.setup.root, case.parent.parent, case.setup.owner).state.acceptance
    assert accepted is not None and accepted.basis is None
    _history_unavailable(case, acceptance)
    assert not _sqlite_contains(case.setup.root / ".zara-core", marker)
