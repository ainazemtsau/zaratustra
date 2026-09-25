"""Explicit Method version transition of a started composite Work (pass 3.8)."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest

from tests.zaratustra.foundation.test_active_plan import _keep, _replace, _revision_request, _seeded
from tests.zaratustra.foundation.test_applicability import (
    ART,
    Case,
    _choose,
    _composite,
    _confirm_request,
    _issue,
    _refused,
    _resolve,
    _space,
    _work_scope,
)
from tests.zaratustra.foundation.test_child_execution import _assignment_revision, _invocation
from tests.zaratustra.foundation.test_composition import _apply, _result, _sqlite_contains
from tests.zaratustra.foundation.test_parallel_branches import _running
from tests.zaratustra.foundation.test_plan_transfers import _case, _pair, _prepare, _publish
from tests.zaratustra.foundation.test_waivers import _except, _waive_request
from zaratustra.foundation import (
    ChoiceApplicability,
    CreateDecisionRequest,
    CreateMethodVersionRequest,
    DecisionRef,
    DeleteArtifactRequest,
    DeleteMethodVersionRequest,
    DeleteWorkRequest,
    ExceptionState,
    FoundationError,
    IssueChildWorkRequest,
    MethodDefinition,
    MethodObligation,
    MethodRef,
    ObligationMapping,
    ObligationTarget,
    OutputContract,
    RecordAttemptStopRequest,
    RecoverRequest,
    ReviseActivePlanRequest,
    WorkPlan,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    read_execution,
    read_method_transition,
    read_method_version,
    read_obligation,
    read_plan_method,
    read_receipt,
    read_work,
    read_work_plan,
    restore_backup,
)


def _v2(case: Case, old: MethodRef) -> tuple[MethodRef, MethodDefinition]:
    root, space, owner = case.root, case.space, case.owner
    previous = read_method_version(root, old, owner).definition
    checked, final = previous.obligations
    definition = previous.model_copy(
        update={
            "instruction": "The second synthetic Method version",
            "obligations": (
                checked.model_copy(update={"key": "checked_v2"}),
                MethodObligation(
                    key="fresh",
                    source="new synthetic requirement",
                    role="b",
                    slot=final.slot,
                    media_type=final.media_type,
                ),
            ),
        }
    )
    receipt = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=old.method_id,
        version=old.version + 1,
        definition=definition,
    )
    return MethodRef(
        method_id=old.method_id,
        version=old.version + 1,
        checksum=str(receipt.result["checksum"]),
    ), definition


def _retirement(case: Case, old: MethodRef) -> DecisionRef:
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    decision = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateDecisionRequest,
        decision_id=decision,
        state=ExceptionState(
            statement="Retire the old final requirement at the version transition",
            target=ObligationTarget(work_id=parent, key="final"),
            methods=(old,),
        ),
    )
    return DecisionRef(decision_id=decision, revision=1)


def _transition_request(
    case: Case,
    plan: WorkPlan,
    method: MethodRef,
    mappings: tuple[ObligationMapping, ...],
) -> ReviseActivePlanRequest:
    a, b = plan.children
    return _revision_request(
        case, plan.model_copy(update={"rationale": "Use exact next Method"}), (_keep(a), _keep(b))
    ).model_copy(update={"target_method": method, "obligation_mapping": mappings})


def test_method_transition_maps_requirements_and_keeps_exact_history(tmp_path: Path) -> None:
    case, plan = _seeded(_space(tmp_path))
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    old = read_work(root, parent, owner).state.method
    assert isinstance(old, MethodRef)
    a, b = plan.children
    _issue(case, "a")
    evidence = _result(root, space, owner, a.work_id, "checked", b"independent result Y")
    apply_operation(root, _confirm_request(case, "checked", evidence), owner)
    v2, definition = _v2(case, old)
    assert read_work(root, parent, owner).state.method == old
    assert read_obligation(root, parent, "checked", owner).status == "satisfied"
    assert read_plan_method(root, parent, owner) == old
    exception = _retirement(case, old)
    request = _revision_request(
        case, plan.model_copy(update={"rationale": "Use v2"}), (_keep(a), _keep(b))
    ).model_copy(
        update={
            "target_method": v2,
            "obligation_mapping": (
                ObligationMapping(source_key="checked", action="carry", target_key="checked_v2"),
                ObligationMapping(source_key="final", action="retire", exception=exception),
            ),
        }
    )
    receipt = apply_operation(root, request, owner)
    assert apply_operation(root, request, owner) == receipt
    assert read_receipt(root, request.operation_id, owner) == receipt
    assert read_work(root, parent, owner).state.method == v2
    assert read_work_plan(root, parent, owner).revision == 2
    assert read_plan_method(root, parent, owner, revision=1) == old
    assert read_plan_method(root, parent, owner, revision=2) == v2
    transition = read_method_transition(root, parent, 2, owner)
    assert (transition.from_method, transition.to_method, transition.operation_id) == (
        old,
        v2,
        request.operation_id,
    )
    assert transition.mappings == tuple(
        sorted(request.obligation_mapping, key=lambda item: item.source_key)
    )
    assert read_method_version(root, old, owner).definition != definition
    assert read_method_version(root, v2, owner).definition == definition
    old_checked = read_obligation(root, parent, "checked", owner)
    old_final = read_obligation(root, parent, "final", owner)
    assert old_checked.status == "retired" and old_checked.transitioned_to == "checked_v2"
    assert old_final.status == "retired" and old_final.retired_by == exception
    carried = read_obligation(root, parent, "checked_v2", owner)
    assert carried.status == "satisfied" and carried.evidence == evidence
    assert (carried.carried_from_key, carried.carried_from_revision) == ("checked", 2)
    assert read_obligation(root, parent, "fresh", owner).status == "open"
    with pytest.raises(FoundationError, match="not_found"):
        read_method_transition(root, parent, 1, owner)
    contaminated = create_backup(root, uuid4(), owner)
    _apply(
        root,
        space,
        owner,
        DeleteMethodVersionRequest,
        method_id=old.method_id,
        version=old.version,
        checksum=old.checksum,
    )
    completed = complete_deletions(root, owner)
    assert completed.pending_jobs == 0 and completed.live_store_sanitized
    assert not contaminated.package.exists()
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_method_version(root, old, owner)
    assert read_plan_method(root, parent, owner, revision=1) == old
    assert read_method_transition(root, parent, 2, owner).from_method == old
    assert read_obligation(root, parent, "checked_v2", owner).status == "satisfied"
    clean = create_backup(root, uuid4(), owner)
    restored_root = tmp_path / "restored"
    restored_root.mkdir()
    restore_backup(clean.package, restored_root, authorize_recovery(actor="owner", source_ref="r"))
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
    assert read_plan_method(restored_root, parent, restored, revision=1) == old
    assert read_method_transition(restored_root, parent, 2, restored).to_method == v2
    assert read_obligation(restored_root, parent, "checked_v2", restored).status == "satisfied"
    restarted = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; from uuid import UUID; "
            "from zaratustra.foundation import authorize_local, read_plan_method, "
            "read_method_transition; p=Path(sys.argv[1]); "
            "o=authorize_local(p, actor='owner', source_ref='restart'); w=UUID(sys.argv[2]); "
            "assert read_plan_method(p,w,o,revision=1).version==1; "
            "assert read_method_transition(p,w,2,o).to_method.version==2",
            str(root),
            str(parent),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert restarted.returncode == 0, restarted.stderr


@pytest.mark.parametrize(
    ("variant", "code"),
    [
        ("missing", "obligation_unmapped"),
        ("no_exception", "exception_required"),
        ("stale_plan", "stale_plan"),
        ("stale_work", "stale_work"),
        ("incompatible", "method_incompatible"),
    ],
)
def test_method_transition_refuses_incomplete_or_stale_changes(
    tmp_path: Path, variant: str, code: str
) -> None:
    case, plan = _seeded(_space(tmp_path))
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    old = read_work(root, parent, owner).state.method
    assert isinstance(old, MethodRef)
    _issue(case, "a")
    if variant == "incompatible":
        previous = read_method_version(root, old, owner).definition
        definition = previous.model_copy(
            update={"named_outputs": (OutputContract(slot="another", media_type="text/plain"),)}
        )
        created = _apply(
            root,
            space,
            owner,
            CreateMethodVersionRequest,
            method_id=old.method_id,
            version=2,
            definition=definition,
        )
        v2 = MethodRef(method_id=old.method_id, version=2, checksum=str(created.result["checksum"]))
    else:
        v2, _definition = _v2(case, old)
    exception = _retirement(case, old)
    mappings = (
        ObligationMapping(source_key="checked", action="carry", target_key="checked_v2"),
        ObligationMapping(
            source_key="final",
            action="retire",
            exception=None if variant == "no_exception" else exception,
        ),
    )
    request = _transition_request(
        case, plan, v2, mappings[:1] if variant == "missing" else mappings
    )
    if variant == "stale_plan":
        request = request.model_copy(update={"expected_plan_revision": 2})
    elif variant == "stale_work":
        request = request.model_copy(update={"expected_work_revision": 2})
    _refused(case, code, request)
    assert read_work(root, parent, owner).state.method == old
    assert read_plan_method(root, parent, owner) == old


def test_next_transition_maps_only_the_current_method_keys(tmp_path: Path) -> None:
    case, plan = _seeded(_space(tmp_path))
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    old = read_work(root, parent, owner).state.method
    assert isinstance(old, MethodRef)
    _issue(case, "a")
    v2, definition = _v2(case, old)
    exception = _retirement(case, old)
    first = _transition_request(
        case,
        plan,
        v2,
        (
            ObligationMapping(source_key="checked", action="carry", target_key="checked_v2"),
            ObligationMapping(source_key="final", action="retire", exception=exception),
        ),
    )
    apply_operation(root, first, owner)
    created = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=old.method_id,
        version=3,
        definition=definition.model_copy(update={"instruction": "Third synthetic Method version"}),
    )
    v3 = MethodRef(method_id=old.method_id, version=3, checksum=str(created.result["checksum"]))
    second = _transition_request(
        case,
        read_work_plan(root, parent, owner).plan,
        v3,
        (
            ObligationMapping(source_key="checked_v2", action="carry", target_key="checked_v2"),
            ObligationMapping(source_key="fresh", action="carry", target_key="fresh"),
        ),
    )
    apply_operation(root, second, owner)
    assert read_plan_method(root, parent, owner, revision=1) == old
    assert read_plan_method(root, parent, owner, revision=2) == v2
    assert read_plan_method(root, parent, owner, revision=3) == v3
    assert {
        item.source_key for item in read_method_transition(root, parent, 3, owner).mappings
    } == {"checked_v2", "fresh"}
    assert read_obligation(root, parent, "final", owner).status == "retired"
    assert read_obligation(root, parent, "checked_v2", owner, revision=2).status == "retired"
    assert read_obligation(root, parent, "checked_v2", owner).revision == 3
    for child in plan.children:
        _apply(
            root,
            space,
            owner,
            DeleteWorkRequest,
            work_id=child.work_id,
            expected_revision=read_work(root, child.work_id, owner).revision,
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
        for table in ("work_plan_methods", "work_obligation_transitions"):
            assert connection.execute(
                f"SELECT count(*) FROM {table} WHERE parent_id = ?", (str(parent),)
            ).fetchone() == (0,)


def test_v2_transfers_kept_attempt_and_fences_replaced_attempt(tmp_path: Path) -> None:
    branches = _pair(tmp_path)
    root, space, owner, parent, works = branches
    case = _case(branches)
    old = read_work(root, parent, owner).state.method
    assert isinstance(old, MethodRef)
    a_attempt, a_session, _ = _running(branches, "a", "workspace-a")
    b_attempt, _b_session, _ = _running(branches, "b", "workspace-b")
    _invocation(root, space, owner, works["a"], a_attempt, a_session, finish=False)
    prior = read_method_version(root, old, owner).definition
    created = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=old.method_id,
        version=2,
        definition=prior.model_copy(update={"instruction": "Second execution Method"}),
    )
    v2 = MethodRef(method_id=old.method_id, version=2, checksum=str(created.result["checksum"]))
    plan = read_work_plan(root, parent, owner).plan
    a, b = plan.children
    a2 = a.model_copy(update={"work_id": uuid4()})
    revised = plan.model_copy(update={"children": (a2, b), "rationale": "Replace A under v2"})
    request = _revision_request(
        case, revised, (_replace(case, a, a2, outcome="cancelled"), _keep(b))
    ).model_copy(
        update={
            "target_method": v2,
            "obligation_mapping": tuple(
                ObligationMapping(source_key=item.key, action="carry", target_key=item.key)
                for item in prior.obligations
            ),
        }
    )
    receipt = apply_operation(root, request, owner)
    assert receipt.result["transfers"] == [
        {"attempt_id": str(b_attempt), "work_id": str(b.work_id), "plan_revision": 2}
    ]
    b_execution = read_execution(root, b.work_id, owner)
    assert b_execution.composition is not None
    assert [(item.plan_revision, item.method) for item in b_execution.composition.transfers] == [
        (2, v2)
    ]
    with pytest.raises(FoundationError, match="stale_plan"):
        apply_operation(root, _prepare(root, space, a.work_id, a_attempt, a_session), owner)
    with pytest.raises(FoundationError, match="stale_plan"):
        apply_operation(root, _publish(space, a.work_id, a_attempt, a_session, b"late v1"), owner)
    delete_old = DeleteMethodVersionRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        method_id=old.method_id,
        version=old.version,
        checksum=old.checksum,
    )
    _refused(case, "method_in_use", delete_old)
    _apply(
        root,
        space,
        owner,
        RecordAttemptStopRequest,
        attempt_id=a_attempt,
        work_id=a.work_id,
        session_id=a_session,
        expected_assignment_revision=_assignment_revision(root, owner, a.work_id, a_attempt),
        outcome="unknown",
    )
    assert [item.status for item in read_execution(root, a.work_id, owner).assignments] == [
        "unknown"
    ]
    _refused(case, "method_in_use", delete_old)


def test_replaced_v1_evidence_cannot_confirm_v2_requirement(tmp_path: Path) -> None:
    case, plan = _seeded(_space(tmp_path))
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    old = read_work(root, parent, owner).state.method
    assert isinstance(old, MethodRef)
    a, b = plan.children
    _issue(case, "a")
    x = _result(root, space, owner, a.work_id, "checked", b"old v1 evidence X")
    apply_operation(root, _confirm_request(case, "checked", x), owner)
    v2, _ = _v2(case, old)
    exception = _retirement(case, old)
    a2 = a.model_copy(update={"work_id": uuid4()})
    revised = plan.model_copy(update={"children": (a2, b), "rationale": "Replace A under v2"})
    request = _revision_request(case, revised, (_replace(case, a, a2), _keep(b))).model_copy(
        update={
            "target_method": v2,
            "obligation_mapping": (
                ObligationMapping(source_key="checked", action="carry", target_key="checked_v2"),
                ObligationMapping(source_key="final", action="retire", exception=exception),
            ),
        }
    )
    apply_operation(root, request, owner)
    assert read_obligation(root, parent, "checked_v2", owner).status == "open"
    _apply(
        root,
        space,
        owner,
        IssueChildWorkRequest,
        parent_work_id=parent,
        work_id=a2.work_id,
        expected_plan_revision=2,
        expected_work_revision=1,
    )
    y = _result(root, space, owner, a2.work_id, "checked", b"independent v2 evidence Y")
    _refused(case, "evidence_mismatch", _confirm_request(case, "checked_v2", x))
    apply_operation(root, _confirm_request(case, "checked_v2", y), owner)
    assert read_obligation(root, parent, "checked_v2", owner).evidence == y


def test_copied_confirmation_is_sanitized_after_artifact_deletion(tmp_path: Path) -> None:
    case, plan = _seeded(_space(tmp_path))
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    old = read_work(root, parent, owner).state.method
    assert isinstance(old, MethodRef)
    a, b = plan.children
    _issue(case, "a")
    marker = f"retired source {uuid4()}"
    evidence = _result(root, space, owner, a.work_id, "checked", marker.encode("utf-8"))
    confirmation = _confirm_request(case, "checked", evidence).model_copy(
        update={"basis": f"The source says {marker}"}
    )
    apply_operation(root, confirmation, owner)
    v2, _ = _v2(case, old)
    exception = _retirement(case, old)
    transition = _transition_request(
        case,
        plan,
        v2,
        (
            ObligationMapping(source_key="checked", action="carry", target_key="checked_v2"),
            ObligationMapping(source_key="final", action="retire", exception=exception),
        ),
    )
    apply_operation(root, transition, owner)
    assert marker in str(read_obligation(root, parent, "checked_v2", owner).basis)
    backup = create_backup(root, uuid4(), owner)
    _apply(
        root,
        space,
        owner,
        DeleteArtifactRequest,
        artifact_id=evidence.artifact_id,
        expected_revision=evidence.revision,
    )
    completed = complete_deletions(root, owner)
    assert completed.pending_jobs == 0 and completed.live_store_sanitized
    assert not backup.package.exists()
    assert read_obligation(root, parent, "checked_v2", owner).status == "open"
    assert read_obligation(root, parent, "checked_v2", owner).basis is None
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_obligation(root, parent, "checked_v2", owner, revision=1)
    assert read_method_transition(root, parent, 2, owner).to_method == v2
    assert not _sqlite_contains(root / ".zara-core", marker)
    assert not _sqlite_contains(create_backup(root, uuid4(), owner).package, marker)
    restarted = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; from uuid import UUID; "
            "from zaratustra.foundation import authorize_local, read_obligation, "
            "read_method_transition; p=Path(sys.argv[1]); "
            "o=authorize_local(p, actor='owner', source_ref='restart'); w=UUID(sys.argv[2]); "
            "assert read_obligation(p,w,'checked_v2',o).status=='open'; "
            "assert read_method_transition(p,w,2,o).plan_revision==2",
            str(root),
            str(parent),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert restarted.returncode == 0, restarted.stderr


def test_conditional_state_requires_same_applicability(tmp_path: Path) -> None:
    case = _composite(_space(tmp_path))
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    old = read_work(root, parent, owner).state.method
    assert isinstance(old, MethodRef)
    plan = read_work_plan(root, parent, owner).plan
    _issue(case, "a")
    choice = _choose(case, "required", _work_scope(case))
    _resolve(case, choice)
    assert read_obligation(root, parent, ART, owner).applicability == "active"
    prior = read_method_version(root, old, owner).definition
    made = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=old.method_id,
        version=2,
        definition=prior.model_copy(update={"instruction": "Same applicability"}),
    )
    v2 = MethodRef(method_id=old.method_id, version=2, checksum=str(made.result["checksum"]))
    mappings = tuple(
        ObligationMapping(source_key=item.key, action="carry", target_key=item.key)
        for item in prior.obligations
    )
    first = _revision_request(
        case,
        plan.model_copy(update={"rationale": "Use same condition under v2"}),
        tuple(_keep(child) for child in plan.children),
    ).model_copy(update={"target_method": v2, "obligation_mapping": mappings})
    apply_operation(root, first, owner)
    carried = read_obligation(root, parent, ART, owner)
    assert carried.applicability == "active" and carried.choice == choice
    altered = prior.model_copy(
        update={
            "instruction": "Changed applicability",
            "obligations": tuple(
                item.model_copy(
                    update={
                        "applicability": ChoiceApplicability(
                            choice=ART, active=("not_required",), inactive=("required",)
                        )
                    }
                )
                if item.key == ART
                else item
                for item in prior.obligations
            ),
        }
    )
    made3 = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=old.method_id,
        version=3,
        definition=altered,
    )
    v3 = MethodRef(method_id=old.method_id, version=3, checksum=str(made3.result["checksum"]))
    current_plan = read_work_plan(root, parent, owner).plan
    second = _revision_request(
        case,
        current_plan.model_copy(update={"rationale": "Recheck changed condition"}),
        tuple(_keep(child) for child in current_plan.children),
    ).model_copy(update={"target_method": v3, "obligation_mapping": mappings})
    apply_operation(root, second, owner)
    unresolved = read_obligation(root, parent, ART, owner)
    assert (unresolved.applicability, unresolved.status, unresolved.choice) == (
        "unresolved",
        "open",
        None,
    )


def test_waiver_carries_only_with_exact_v2_exception(tmp_path: Path) -> None:
    case, plan = _seeded(_space(tmp_path))
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    old = read_work(root, parent, owner).state.method
    assert isinstance(old, MethodRef)
    _issue(case, "a")
    prior = read_method_version(root, old, owner).definition
    made = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=old.method_id,
        version=2,
        definition=prior.model_copy(update={"instruction": "Waiver-compatible Method"}),
    )
    v2 = MethodRef(method_id=old.method_id, version=2, checksum=str(made.result["checksum"]))
    exception = _except(case, methods=(old, v2))
    apply_operation(root, _waive_request(case, exception), owner)
    first = _transition_request(
        case,
        plan,
        v2,
        tuple(
            ObligationMapping(source_key=item.key, action="carry", target_key=item.key)
            for item in prior.obligations
        ),
    )
    apply_operation(root, first, owner)
    carried = read_obligation(root, parent, "checked", owner)
    assert carried.status == "waived" and carried.exception == exception
    made3 = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=old.method_id,
        version=3,
        definition=prior.model_copy(update={"instruction": "Waiver-limited Method"}),
    )
    v3 = MethodRef(method_id=old.method_id, version=3, checksum=str(made3.result["checksum"]))
    second = _transition_request(
        case,
        read_work_plan(root, parent, owner).plan,
        v3,
        tuple(
            ObligationMapping(source_key=item.key, action="carry", target_key=item.key)
            for item in prior.obligations
        ),
    )
    apply_operation(root, second, owner)
    reopened = read_obligation(root, parent, "checked", owner)
    assert reopened.status == "open" and reopened.exception is None
