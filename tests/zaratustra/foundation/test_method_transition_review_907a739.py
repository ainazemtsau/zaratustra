"""Review regressions for exact Method transition, history, and deletion (part 3.8)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from tests.zaratustra.foundation.test_active_plan import (
    _keep,
    _replace,
    _revision_request,
    _seeded,
)
from tests.zaratustra.foundation.test_applicability import (
    ART,
    Case,
    _accept_request,
    _choose,
    _composite,
    _confirm_request,
    _issue,
    _link_request,
    _refused,
    _resolve_request,
    _space,
    _work_scope,
)
from tests.zaratustra.foundation.test_composition import _apply, _result, _sqlite_contains
from tests.zaratustra.foundation.test_method_transition import (
    _retirement,
    _transition_request,
    _v2,
)
from zaratustra.foundation import (
    CreateArtifactRequest,
    CreateCompositeWorkRequest,
    CreateDecisionRequest,
    CreateMethodVersionRequest,
    DecisionRef,
    DeleteArtifactRequest,
    DeleteMethodVersionRequest,
    ExceptionState,
    MethodRef,
    ObligationMapping,
    ObligationTarget,
    apply_operation,
    complete_deletions,
    create_backup,
    read_method_transition,
    read_method_version,
    read_obligation,
    read_plan_method,
    read_receipt,
    read_work,
    read_work_plan,
)


def test_retired_requirements_do_not_block_v2_parent_acceptance(tmp_path: Path) -> None:
    case, plan = _seeded(_space(tmp_path))
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    old = read_work(root, parent, owner).state.method
    assert isinstance(old, MethodRef)
    a, b = plan.children
    _issue(case, "a")
    x = _result(root, space, owner, a.work_id, "checked", b"synthetic A X")
    apply_operation(root, _confirm_request(case, "checked", x), owner)
    v2, _ = _v2(case, old)
    exception = _retirement(case, old)
    request = _transition_request(
        case,
        plan,
        v2,
        (
            ObligationMapping(source_key="checked", action="carry", target_key="checked_v2"),
            ObligationMapping(source_key="final", action="retire", exception=exception),
        ),
    )
    apply_operation(root, request, owner)
    _issue(case, "b")
    y = _result(root, space, owner, b.work_id, "final", b"synthetic B Y")
    apply_operation(root, _confirm_request(case, "fresh", y), owner)
    apply_operation(root, _link_request(case, y), owner)
    assert read_obligation(root, parent, "checked", owner).status == "retired"
    assert read_obligation(root, parent, "final", owner).status == "retired"
    assert read_obligation(root, parent, "checked_v2", owner).status == "satisfied"
    assert read_obligation(root, parent, "fresh", owner).status == "satisfied"
    apply_operation(root, _accept_request(case), owner)
    assert read_work(root, parent, owner).state.status == "succeeded"


def test_retired_conditional_requirement_cannot_be_resolved(tmp_path: Path) -> None:
    case = _composite(_space(tmp_path))
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    old = read_work(root, parent, owner).state.method
    assert isinstance(old, MethodRef)
    plan = read_work_plan(root, parent, owner).plan
    _issue(case, "a")
    definition = read_method_version(root, old, owner).definition
    changed = definition.model_copy(
        update={
            "instruction": "Remove the optional review",
            "obligations": definition.obligations[:2],
        }
    )
    made = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=old.method_id,
        version=2,
        definition=changed,
    )
    v2 = MethodRef(method_id=old.method_id, version=2, checksum=str(made.result["checksum"]))
    decision = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateDecisionRequest,
        decision_id=decision,
        state=ExceptionState(
            statement="Retire optional review",
            target=ObligationTarget(work_id=parent, key=ART),
            methods=(old,),
        ),
    )
    mappings = (
        ObligationMapping(source_key="checked", action="carry", target_key="checked"),
        ObligationMapping(source_key="final", action="carry", target_key="final"),
        ObligationMapping(
            source_key=ART, action="retire", exception=DecisionRef(decision_id=decision, revision=1)
        ),
    )
    request = _revision_request(
        case,
        plan.model_copy(update={"rationale": "Retire optional review"}),
        tuple(_keep(child) for child in plan.children),
    ).model_copy(update={"target_method": v2, "obligation_mapping": mappings})
    apply_operation(root, request, owner)
    assert read_obligation(root, parent, ART, owner).status == "retired"
    choice = _choose(case, "required", _work_scope(case))
    _refused(case, "not_found", _resolve_request(case, choice, key=ART))
    assert read_obligation(root, parent, ART, owner).status == "retired"


def test_deleting_v1_removes_retired_definition_copy(tmp_path: Path) -> None:
    setup = _space(tmp_path)
    root, space, owner = setup.root, setup.space, setup.owner
    original = read_work(root, setup.seeded, owner)
    original_plan = read_work_plan(root, setup.seeded, owner).plan
    original_method = original.state.method
    assert isinstance(original_method, MethodRef)
    old_definition = read_method_version(root, original_method, owner).definition
    checked, final = old_definition.obligations
    marker = f"retired method source {uuid4()}"
    old_definition = old_definition.model_copy(
        update={"obligations": (checked, final.model_copy(update={"source": marker}))}
    )
    method_id = uuid4()
    made = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=method_id,
        version=1,
        definition=old_definition,
    )
    old = MethodRef(method_id=method_id, version=1, checksum=str(made.result["checksum"]))
    children = tuple(
        child.model_copy(update={"work_id": uuid4()}) for child in original_plan.children
    )
    plan = original_plan.model_copy(update={"children": children})
    parent = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateCompositeWorkRequest,
        work_id=parent,
        state=original.state.model_copy(update={"method": old}),
        plan=plan,
    )
    case = Case(root, space, owner, setup.activity, parent, {c.role: c.work_id for c in children})
    _issue(case, "a")
    new_definition = old_definition.model_copy(
        update={
            "instruction": "Replacement without old source",
            "obligations": (checked.model_copy(update={"source": "independent v2 requirement"}),),
        }
    )
    made2 = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=method_id,
        version=2,
        definition=new_definition,
    )
    v2 = MethodRef(method_id=method_id, version=2, checksum=str(made2.result["checksum"]))
    exception = _retirement(case, old)
    transition = _transition_request(
        case,
        plan,
        v2,
        (
            ObligationMapping(source_key="checked", action="carry", target_key="checked"),
            ObligationMapping(source_key="final", action="retire", exception=exception),
        ),
    )
    apply_operation(root, transition, owner)
    assert marker in read_obligation(root, parent, "final", owner).definition.source
    contaminated = create_backup(root, uuid4(), owner)
    _apply(
        root,
        space,
        owner,
        DeleteMethodVersionRequest,
        method_id=method_id,
        version=1,
        checksum=old.checksum,
    )
    completed = complete_deletions(root, owner)
    assert completed.pending_jobs == 0 and completed.live_store_sanitized
    assert not contaminated.package.exists()
    retired = read_obligation(root, parent, "final", owner)
    assert retired.status == "retired" and marker not in retired.model_dump_json()
    assert marker not in read_obligation(root, parent, "final", owner, revision=1).model_dump_json()
    assert read_obligation(root, parent, "checked", owner).definition.source == (
        "independent v2 requirement"
    )
    assert read_method_transition(root, parent, 2, owner).from_method == old
    assert read_work(root, parent, owner).state.method == v2
    assert not _sqlite_contains(root / ".zara-core", marker)
    assert not _sqlite_contains(create_backup(root, uuid4(), owner).package, marker)
    v3_definition = new_definition.model_copy(
        update={
            "instruction": "Third independent Method",
            "obligations": (
                new_definition.obligations[0].model_copy(update={"source": "independent v3"}),
            ),
        }
    )
    made3 = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=method_id,
        version=3,
        definition=v3_definition,
    )
    v3 = MethodRef(method_id=method_id, version=3, checksum=str(made3.result["checksum"]))
    next_plan = read_work_plan(root, parent, owner).plan
    apply_operation(
        root,
        _transition_request(
            case,
            next_plan,
            v3,
            (ObligationMapping(source_key="checked", action="carry", target_key="checked"),),
        ),
        owner,
    )
    _apply(
        root,
        space,
        owner,
        DeleteMethodVersionRequest,
        method_id=method_id,
        version=2,
        checksum=v2.checksum,
    )
    assert complete_deletions(root, owner).live_store_sanitized
    assert read_obligation(root, parent, "checked", owner).definition.source == "independent v3"
    assert read_obligation(root, parent, "checked", owner, revision=4).status == "retired"
    assert read_obligation(root, parent, "checked", owner, revision=4).definition.source != (
        "independent v2 requirement"
    )
    assert read_plan_method(root, parent, owner, revision=1) == old
    assert read_plan_method(root, parent, owner, revision=2) == v2
    assert read_plan_method(root, parent, owner, revision=3) == v3
    restarted = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; from uuid import UUID; "
            "from zaratustra.foundation import authorize_local, read_obligation; "
            "p=Path(sys.argv[1]); o=authorize_local(p,actor='owner',source_ref='restart'); "
            "x=read_obligation(p,UUID(sys.argv[2]),'final',o); "
            "assert x.status=='retired' and sys.argv[3] not in x.model_dump_json()",
            str(root),
            str(parent),
            marker,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert restarted.returncode == 0, restarted.stderr


def test_fresh_confirmation_drops_sanitized_carry_origin(tmp_path: Path) -> None:
    case, plan = _seeded(_space(tmp_path))
    root, space, owner, parent = case.root, case.space, case.owner, case.parent
    old = read_work(root, parent, owner).state.method
    assert isinstance(old, MethodRef)
    a, b = plan.children
    _issue(case, "a")
    x = _result(root, space, owner, a.work_id, "checked", b"synthetic old X")
    apply_operation(root, _confirm_request(case, "checked", x), owner)
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
    _apply(
        root,
        space,
        owner,
        DeleteArtifactRequest,
        artifact_id=x.artifact_id,
        expected_revision=x.revision,
    )
    assert complete_deletions(root, owner).live_store_sanitized
    assert read_obligation(root, parent, "checked_v2", owner).status == "open"
    a2 = a.model_copy(update={"work_id": uuid4()})
    updated = plan.model_copy(update={"children": (a2, b), "rationale": "Independent A2"})
    apply_operation(
        root, _revision_request(case, updated, (_replace(case, a, a2), _keep(b))), owner
    )
    after = Case(root, space, owner, case.activity, parent, {"a": a2.work_id, "b": b.work_id})
    _issue(after, "a")
    y = _result(root, space, owner, a2.work_id, "checked", b"independent new Y")
    marker = f"independent confirmation {uuid4()}"
    confirmation = _confirm_request(after, "checked_v2", y).model_copy(update={"basis": marker})
    receipt = apply_operation(root, confirmation, owner)
    before = read_obligation(root, parent, "checked_v2", owner)
    assert before.status == "satisfied" and before.evidence == y
    q = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=q,
        media_type="text/plain",
        content=b"unrelated Q",
    )
    _apply(root, space, owner, DeleteArtifactRequest, artifact_id=q, expected_revision=1)
    completed = complete_deletions(root, owner)
    assert completed.pending_jobs == 0 and completed.live_store_sanitized
    assert read_obligation(root, parent, "checked_v2", owner) == before
    assert read_receipt(root, confirmation.operation_id, owner) == receipt
    assert apply_operation(root, confirmation, owner) == receipt
    assert before.basis is not None and marker in before.basis
