"""Conditional obligations resolve by addressed choices; overlapping scopes conflict.

Part 3.3 of Stage 6 pass 3, model-free through public Core operations.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import Literal, NamedTuple
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from tests.zaratustra.foundation.test_composition import _apply, _result, _seed, _sqlite_contains
from zaratustra.foundation import (
    AcceptWorkRequest,
    Action,
    ArtifactRef,
    AuditReference,
    ChoiceApplicability,
    ChoiceState,
    CloseWorkRequest,
    ConfirmObligationRequest,
    CreateArtifactRequest,
    CreateCompositeWorkRequest,
    CreateDecisionRequest,
    CreateGrantRequest,
    CreateMethodVersionRequest,
    DecisionRef,
    DecisionScope,
    DecisionState,
    DeleteWorkRequest,
    DomainRequest,
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
    OperationReceipt,
    OutputContract,
    PlanChild,
    PlanCondition,
    PlanOutputBinding,
    RecoverRequest,
    ResolveObligationApplicabilityRequest,
    ReviseDecisionRequest,
    ReviseWorkPlanRequest,
    StatusReason,
    WorkPlan,
    WorkState,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    inspect_space,
    read_decision,
    read_execution,
    read_obligation,
    read_operation_audit,
    read_receipt,
    read_space,
    read_work,
    read_work_plan,
    read_work_status,
    restore_backup,
    upgrade_child_execution_space,
    upgrade_plan_revision_space,
)

ART = "art_review"
APPLICABILITY = ChoiceApplicability(choice=ART, active=("required",), inactive=("not_required",))


class Space(NamedTuple):
    root: Path
    space: UUID
    owner: LocalAuthority
    activity: UUID
    source: ArtifactRef
    # The pass 1 composite Work of the shared seed, with unconditional obligations only.
    seeded: UUID


class Case(NamedTuple):
    root: Path
    space: UUID
    owner: LocalAuthority
    activity: UUID
    parent: UUID
    works: dict[str, UUID]


def _space(tmp_path: Path, *, schema: int = 7) -> Space:
    root, space, owner, activity, source, _ref, seeded, _a, _b, _plan, _create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    if schema == 7:
        assert upgrade_plan_revision_space(root, owner).schema_version == 7
    return Space(root, space, owner, activity, ArtifactRef(artifact_id=source, revision=1), seeded)


def _definition() -> MethodDefinition:
    def obligation(
        key: str, role: str, slot: str, applicability: ChoiceApplicability | None = None
    ) -> MethodObligation:
        return MethodObligation(
            key=key,
            source="synthetic applicability contract",
            role=role,
            slot=slot,
            media_type="text/plain",
            applicability=applicability or "always",
        )

    return MethodDefinition(
        instruction="Check the source, write the summary and review art only when required.",
        named_inputs=(OutputContract(slot="source", media_type="text/plain"),),
        named_outputs=(OutputContract(slot="final", media_type="text/plain"),),
        obligations=(
            obligation("checked", "a", "checked"),
            obligation("final", "b", "final"),
            obligation(ART, "art", "reviewed", APPLICABILITY),
        ),
        source_ref="synthetic-applicability-method",
    )


def _child(
    activity: UUID,
    role: str,
    slot: str,
    *,
    inputs: tuple[ArtifactRef, ...] = (),
    readiness: PlanCondition | None = None,
) -> PlanChild:
    return PlanChild(
        role=role,
        work_id=uuid4(),
        state=WorkState(
            activity_id=activity,
            goal=f"Synthetic {role}",
            inputs=inputs,
            expected_outputs=(OutputContract(slot=slot, media_type="text/plain"),),
        ),
        readiness=readiness,
    )


def _value(choice: DecisionRef, value: str, *, name: str = ART) -> PlanCondition:
    return PlanCondition(
        kind="decision_value",
        decision_id=choice.decision_id,
        decision_revision=choice.revision,
        name=name,
        value=value,
    )


def _method(setup: Space) -> MethodRef:
    method = uuid4()
    created = _apply(
        setup.root,
        setup.space,
        setup.owner,
        CreateMethodVersionRequest,
        method_id=method,
        version=1,
        definition=_definition(),
    )
    return MethodRef(method_id=method, version=1, checksum=str(created.result["checksum"]))


def _composite_request(
    setup: Space,
    method: MethodRef,
    *,
    art_readiness: PlanCondition | None = None,
    extra: tuple[PlanChild, ...] = (),
    completion: PlanCondition | None = None,
) -> CreateCompositeWorkRequest:
    activity, source = setup.activity, setup.source
    accepted_a = PlanCondition(
        kind="accepted_output", role="a", slot="checked", media_type="text/plain"
    )
    return CreateCompositeWorkRequest(
        operation_id=uuid4(),
        space_id=setup.space,
        actor="owner",
        work_id=uuid4(),
        state=WorkState(
            activity_id=activity,
            goal="Prepare the synthetic packet",
            inputs=(source,),
            expected_outputs=_definition().named_outputs,
            method=method,
        ),
        plan=WorkPlan(
            named_inputs=(NamedInput(slot="source", artifact=source),),
            output_bindings=(
                PlanOutputBinding(
                    parent_slot="final", role="b", child_slot="final", media_type="text/plain"
                ),
            ),
            children=(
                _child(activity, "a", "checked", inputs=(source,)),
                _child(activity, "b", "final", readiness=accepted_a),
                _child(activity, "art", "reviewed", readiness=art_readiness),
                *extra,
            ),
            completion=completion
            or PlanCondition(
                kind="all",
                members=(
                    PlanCondition(kind="work_succeeded", role="a"),
                    PlanCondition(kind="work_succeeded", role="b"),
                ),
            ),
            basis=(source,),
            rationale="Synthetic plan with a conditional review",
            source_ref="fictional-owner-plan",
        ),
    )


def _composite(
    setup: Space,
    *,
    art_readiness: PlanCondition | None = None,
    extra: tuple[PlanChild, ...] = (),
    completion: PlanCondition | None = None,
) -> Case:
    request = _composite_request(
        setup, _method(setup), art_readiness=art_readiness, extra=extra, completion=completion
    )
    apply_operation(setup.root, request, setup.owner)
    return Case(
        setup.root,
        setup.space,
        setup.owner,
        setup.activity,
        request.work_id,
        {child.role: child.work_id for child in request.plan.children},
    )


def _work_scope(case: Case) -> DecisionScope:
    return DecisionScope(kind="work", record_id=case.parent)


def _activity_scope(case: Case | Space) -> DecisionScope:
    return DecisionScope(kind="activity", record_id=case.activity)


def _choose(
    case: Case | Space, value: str, scope: DecisionScope, *, name: str = ART
) -> DecisionRef:
    decision = uuid4()
    _apply(
        case.root,
        case.space,
        case.owner,
        CreateDecisionRequest,
        decision_id=decision,
        state=ChoiceState(
            statement=f"Synthetic choice: {name} is {value}", name=name, value=value, scope=scope
        ),
    )
    return DecisionRef(decision_id=decision, revision=1)


def _revise_choice(
    case: Case, choice: DecisionRef, *, status: Literal["active", "revoked"] = "active"
) -> DecisionRef:
    current = read_decision(case.root, choice.decision_id, case.owner)
    assert isinstance(current.state, ChoiceState) and current.revision == choice.revision
    _apply(
        case.root,
        case.space,
        case.owner,
        ReviseDecisionRequest,
        decision_id=choice.decision_id,
        expected_revision=choice.revision,
        state=current.state.model_copy(
            update={"statement": f"{current.state.statement} (revised)", "status": status}
        ),
    )
    return DecisionRef(decision_id=choice.decision_id, revision=choice.revision + 1)


def _revoke(case: Case, choice: DecisionRef) -> DecisionRef:
    return _revise_choice(case, choice, status="revoked")


def _resolve_request(
    case: Case,
    choice: DecisionRef,
    *,
    key: str = ART,
    basis: str = "Synthetic applicability",
    obligation_revision: int | None = None,
) -> ResolveObligationApplicabilityRequest:
    return ResolveObligationApplicabilityRequest(
        operation_id=uuid4(),
        space_id=case.space,
        actor="owner",
        work_id=case.parent,
        key=key,
        expected_plan_revision=read_work_plan(case.root, case.parent, case.owner).revision,
        expected_obligation_revision=obligation_revision
        or read_obligation(case.root, case.parent, key, case.owner).revision,
        choice=choice,
        basis=basis,
    )


def _resolve(case: Case, choice: DecisionRef) -> OperationReceipt:
    return apply_operation(case.root, _resolve_request(case, choice), case.owner)


def _refused(case: Case | Space, code: str, request: DomainRequest) -> FoundationError:
    """A refused operation names its reason and writes nothing."""

    before = read_space(case.root)
    with pytest.raises(FoundationError, match=code) as refused:
        apply_operation(case.root, request, case.owner)
    assert read_space(case.root) == before
    return refused.value


def _issue_request(case: Case, role: str) -> IssueChildWorkRequest:
    return IssueChildWorkRequest(
        operation_id=uuid4(),
        space_id=case.space,
        actor="owner",
        parent_work_id=case.parent,
        work_id=case.works[role],
        expected_plan_revision=read_work_plan(case.root, case.parent, case.owner).revision,
        expected_work_revision=read_work(case.root, case.works[role], case.owner).revision,
    )


def _issue(case: Case, role: str) -> None:
    apply_operation(case.root, _issue_request(case, role), case.owner)


def _confirm_request(case: Case, key: str, evidence: ArtifactRef) -> ConfirmObligationRequest:
    return ConfirmObligationRequest(
        operation_id=uuid4(),
        space_id=case.space,
        actor="owner",
        work_id=case.parent,
        key=key,
        expected_plan_revision=read_work_plan(case.root, case.parent, case.owner).revision,
        expected_obligation_revision=read_obligation(
            case.root, case.parent, key, case.owner
        ).revision,
        evidence=evidence,
        basis=f"Synthetic confirmation of {key}",
    )


def _confirm(case: Case, key: str, evidence: ArtifactRef) -> None:
    apply_operation(case.root, _confirm_request(case, key, evidence), case.owner)


def _accept_request(case: Case) -> AcceptWorkRequest:
    return AcceptWorkRequest(
        operation_id=uuid4(),
        space_id=case.space,
        actor="owner",
        work_id=case.parent,
        expected_revision=read_work(case.root, case.parent, case.owner).revision,
        basis="Synthetic parent acceptance",
    )


def _link_request(case: Case, artifact: ArtifactRef) -> LinkWorkOutputRequest:
    return LinkWorkOutputRequest(
        operation_id=uuid4(),
        space_id=case.space,
        actor="owner",
        work_id=case.parent,
        expected_revision=read_work(case.root, case.parent, case.owner).revision,
        output=LinkedOutput(slot="final", artifact=artifact),
    )


def _cancel(case: Case, role: str) -> None:
    apply_operation(
        case.root,
        CloseWorkRequest(
            operation_id=uuid4(),
            space_id=case.space,
            actor="owner",
            work_id=case.works[role],
            expected_revision=read_work(case.root, case.works[role], case.owner).revision,
            outcome="cancelled",
            basis=f"Synthetic {role} is not needed",
        ),
        case.owner,
    )


def _complete_ab(case: Case) -> ArtifactRef:
    """Run A and B, confirm their obligations and return B's exact result."""

    root, space, owner, _activity, _parent, works = case
    _issue(case, "a")
    _confirm(
        case, "checked", _result(root, space, owner, works["a"], "checked", b"synthetic check")
    )
    _issue(case, "b")
    summary = _result(root, space, owner, works["b"], "final", b"synthetic summary")
    _confirm(case, "final", summary)
    return summary


def _acceptance_pending(case: Case) -> tuple[StatusReason, ...]:
    return (StatusReason(code="acceptance_pending", record_id=case.parent),)


def _applicability_pending(case: Case) -> StatusReason:
    return StatusReason(code="applicability_pending", key=ART, name=ART, record_id=case.parent)


def _applicability_stale(choice: DecisionRef) -> StatusReason:
    return StatusReason(
        code="applicability_stale",
        key=ART,
        name=ART,
        record_id=choice.decision_id,
        revision=choice.revision,
    )


def _conflict(
    *choices: DecisionRef, key: str | None = ART, name: str = ART
) -> tuple[StatusReason, ...]:
    return tuple(
        StatusReason(
            code="decision_conflict",
            key=key,
            name=name,
            record_id=choice.decision_id,
            revision=choice.revision,
        )
        for choice in sorted(choices, key=lambda item: str(item.decision_id))
    )


def _issue_pending(case: Case, role: str) -> StatusReason:
    return StatusReason(code="issue_pending", role=role, record_id=case.works[role])


def _statuses_in_new_process(case: Case, works: dict[str, UUID]) -> dict[str, object]:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, sys; from pathlib import Path; from uuid import UUID; "
            "from zaratustra.foundation import authorize_local, read_execution; "
            "p=Path(sys.argv[1]); o=authorize_local(p, actor='owner', source_ref='restart'); "
            "works=json.loads(sys.argv[2]); "
            "print(json.dumps({name: read_execution(p, UUID(work), o).model_dump(mode='json', "
            "include={'status', 'composition'}) for name, work in works.items()}))",
            str(case.root),
            json.dumps({name: str(work) for name, work in works.items()}),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return dict(json.loads(result.stdout))


def _statuses(case: Case, works: dict[str, UUID]) -> dict[str, object]:
    return {
        name: read_execution(case.root, work, case.owner).model_dump(
            mode="json", include={"status", "composition"}
        )
        for name, work in works.items()
    }


def _stored_payload(case: Case, key: str, revision: int) -> bytes:
    with closing(sqlite3.connect(case.root / ".zara-core" / "core.sqlite3")) as connection:
        row = connection.execute(
            "SELECT payload FROM work_obligation_revisions "
            "WHERE parent_id = ? AND key = ? AND revision = ?",
            (str(case.parent), key, revision),
        ).fetchone()
    assert row is not None
    return bytes(row[0])


def test_conditional_obligation_starts_unresolved_and_resolves_inactive_by_choice(
    tmp_path: Path,
) -> None:
    case = _composite(_space(tmp_path))
    root, _space_id, owner, _activity, parent, works = case
    materialized = [read_obligation(root, parent, key, owner) for key in ("checked", "final", ART)]
    assert [(item.applicability, item.status, item.choice) for item in materialized] == [
        ("active", "open", None),
        ("active", "open", None),
        ("unresolved", "open", None),
    ]
    # An unconditional instance keeps its earlier canonical bytes: no applicability address.
    assert b'"choice"' not in _stored_payload(case, "checked", 1)
    assert b'"applicability":"unresolved"' in _stored_payload(case, ART, 1)
    initial = read_work_status(root, parent, owner)
    assert initial.status == "ready"
    assert initial.reasons == (
        _issue_pending(case, "a"),
        _issue_pending(case, "art"),
        _applicability_pending(case),
    )

    summary = _complete_ab(case)
    apply_operation(root, _link_request(case, summary), owner)
    # Both unconditional obligations hold; the conditional one is neither due nor excused.
    _refused(case, "obligation_unresolved", _accept_request(case))
    _refused(case, "obligation_unresolved", _confirm_request(case, ART, summary))
    unresolved = read_work_status(root, parent, owner)
    assert unresolved.status == "ready"
    assert unresolved.reasons == (_issue_pending(case, "art"), _applicability_pending(case))

    choice = _choose(case, "not_required", _work_scope(case))
    request = _resolve_request(case, choice, basis="Synthetic packet has no artwork")
    receipt = apply_operation(root, request, owner)
    assert receipt.result == {
        "work_id": str(parent),
        "key": ART,
        "revision": 2,
        "applicability": "inactive",
        "choice": {"decision_id": str(choice.decision_id), "revision": 1},
    }
    assert "no artwork" not in json.dumps(receipt.model_dump(mode="json"))
    assert apply_operation(root, request, owner) == receipt
    # History: the exact instance revisions and the audit name the Decision address.
    resolved = read_obligation(root, parent, ART, owner)
    assert (resolved.revision, resolved.applicability, resolved.status) == (2, "inactive", "open")
    assert resolved.choice == choice and resolved.basis == "Synthetic packet has no artwork"
    assert read_obligation(root, parent, ART, owner, revision=1).applicability == "unresolved"
    audit = read_operation_audit(root, receipt.operation_id, owner)
    assert AuditReference(record_id=choice.decision_id, revision=1) in audit.target_refs
    decision = read_decision(root, choice.decision_id, owner, revision=1)
    assert isinstance(decision.state, ChoiceState) and decision.state.value == "not_required"

    _refused(case, "stale_obligation", request.model_copy(update={"operation_id": uuid4()}))
    again = request.model_copy(update={"operation_id": uuid4(), "expected_obligation_revision": 2})
    _refused(case, "applicability_resolved", again)
    _refused(case, "obligation_inactive", _confirm_request(case, ART, summary))

    pending = read_work_status(root, parent, owner)
    assert pending.status == "ready" and pending.reasons == _acceptance_pending(case)
    composition = read_execution(root, parent, owner).composition
    assert composition is not None
    progress = {item.key: item for item in composition.obligations}
    assert (progress[ART].applicability, progress[ART].choice) == ("inactive", choice)
    assert _statuses_in_new_process(case, {"parent": parent, **works}) == _statuses(
        case, {"parent": parent, **works}
    )
    apply_operation(root, _accept_request(case), owner)
    assert read_work_status(root, parent, owner).status == "succeeded"
    assert read_work(root, works["art"], owner).state.status == "proposed"


def test_different_values_conflict_until_one_choice_is_revoked(tmp_path: Path) -> None:
    case = _composite(_space(tmp_path))
    required = _choose(case, "required", _work_scope(case))
    not_required = _choose(case, "not_required", _work_scope(case))
    refused = _refused(case, "decision_conflict", _resolve_request(case, not_required))
    assert str(required.decision_id) in refused.detail
    assert str(not_required.decision_id) in refused.detail
    assert read_obligation(case.root, case.parent, ART, case.owner).revision == 1
    blocked = read_work_status(case.root, case.parent, case.owner)
    assert blocked.status == "blocked"
    assert blocked.reasons == _conflict(required, not_required)

    _revoke(case, required)
    assert _resolve(case, not_required).result["applicability"] == "inactive"
    assert read_work_status(case.root, case.parent, case.owner).reasons == (
        _issue_pending(case, "a"),
        _issue_pending(case, "art"),
    )


def test_overlapping_scopes_conflict_and_the_local_choice_does_not_win(tmp_path: Path) -> None:
    case = _composite(_space(tmp_path))
    general = _choose(case, "required", _activity_scope(case))
    local = _choose(case, "not_required", _work_scope(case))
    for choice in (local, general):
        refused = _refused(case, "decision_conflict", _resolve_request(case, choice))
        assert str(general.decision_id) in refused.detail
        assert str(local.decision_id) in refused.detail
    # A choice for another Work does not cover this parent and never takes part.
    child_only = _choose(case, "required", DecisionScope(kind="work", record_id=case.works["a"]))
    _refused(case, "choice_mismatch", _resolve_request(case, child_only))
    _revoke(case, general)
    assert _resolve(case, local).result["applicability"] == "inactive"


def test_opposite_choice_after_inactive_resolution_blocks_integration_until_revoked(
    tmp_path: Path,
) -> None:
    case = _composite(_space(tmp_path))
    root, space, owner, activity, parent, works = case
    local = _choose(case, "not_required", _work_scope(case))
    _resolve(case, local)
    # A node that runs only while the review is not required, added before any issue.
    note = _child(activity, "note", "note", readiness=_value(local, "not_required"))
    current = read_work_plan(root, parent, owner)
    _apply(
        root,
        space,
        owner,
        ReviseWorkPlanRequest,
        work_id=parent,
        expected_plan_revision=current.revision,
        plan=current.plan.model_copy(
            update={"children": (*current.plan.children, note), "rationale": "Add a note"}
        ),
    )
    works["note"] = note.work_id
    summary = _complete_ab(case)

    general = _choose(case, "required", _activity_scope(case))
    refusing: tuple[DomainRequest, ...] = (
        _link_request(case, summary),
        _issue_request(case, "note"),
        _accept_request(case),
    )
    for request in refusing:
        refused = _refused(case, "decision_conflict", request)
        assert str(local.decision_id) in refused.detail
        assert str(general.decision_id) in refused.detail
    # The recorded resolution is not rewritten; the derived states name both addresses.
    assert read_obligation(root, parent, ART, owner).applicability == "inactive"
    blocked = read_work_status(root, parent, owner)
    assert blocked.status == "blocked" and blocked.reasons == _conflict(local, general)
    note_status = read_work_status(root, works["note"], owner)
    assert note_status.status == "blocked"
    assert note_status.reasons == _conflict(local, general, key=None)
    checked = {"parent": parent, "note": works["note"]}
    assert _statuses_in_new_process(case, checked) == _statuses(case, checked)

    # Revoking the opposite choice restores the earlier resolution.
    _revoke(case, general)
    apply_operation(root, _link_request(case, summary), owner)
    _issue(case, "note")
    assert read_work_status(root, parent, owner).reasons == _acceptance_pending(case)

    # Revoking the referenced choice needs a new resolution; nothing switches silently.
    _revoke(case, local)
    stale = read_work_status(root, parent, owner)
    assert stale.status == "ready"
    assert stale.reasons == (_issue_pending(case, "art"), _applicability_stale(local))
    _refused(case, "stale_basis", _accept_request(case))
    assert read_work_status(root, works["note"], owner).reasons == (
        StatusReason(code="stale_basis", record_id=local.decision_id, revision=1, name=ART),
    )
    # The exact choice leaf is a premise of the note: it can be closed as stale.
    apply_operation(
        root,
        CloseWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=works["note"],
            expected_revision=read_work(root, works["note"], owner).revision,
            outcome="stale",
            basis="The choice the note relied on was revoked",
            decision_premises=(local,),
        ),
        owner,
    )
    renewed = _choose(case, "not_required", _work_scope(case))
    assert _resolve(case, renewed).result == {
        "work_id": str(parent),
        "key": ART,
        "revision": 3,
        "applicability": "inactive",
        "choice": {"decision_id": str(renewed.decision_id), "revision": 1},
    }
    apply_operation(root, _accept_request(case), owner)
    assert read_work_status(root, parent, owner).status == "succeeded"


def test_opposite_choice_after_active_resolution_blocks_confirmation(tmp_path: Path) -> None:
    case = _composite(_space(tmp_path))
    root, space, owner, _activity, parent, works = case
    local = _choose(case, "required", _work_scope(case))
    assert _resolve(case, local).result["applicability"] == "active"
    active = read_obligation(root, parent, ART, owner)
    assert (active.applicability, active.status, active.choice) == ("active", "open", local)
    summary = _complete_ab(case)
    apply_operation(root, _link_request(case, summary), owner)
    _issue(case, "art")
    review = _result(root, space, owner, works["art"], "reviewed", b"synthetic art review")
    due = read_work_status(root, parent, owner)
    assert due.reasons == (StatusReason(code="confirmation_pending", role="art", record_id=parent),)
    _refused(case, "obligation_open", _accept_request(case))

    general = _choose(case, "not_required", _activity_scope(case))
    refusing: tuple[DomainRequest, ...] = (
        _confirm_request(case, ART, review),
        _accept_request(case),
    )
    for request in refusing:
        refused = _refused(case, "decision_conflict", request)
        assert str(local.decision_id) in refused.detail
        assert str(general.decision_id) in refused.detail
    blocked = read_work_status(root, parent, owner)
    assert blocked.status == "blocked" and blocked.reasons == _conflict(local, general)

    _revoke(case, general)
    _confirm(case, ART, review)
    confirmed = read_obligation(root, parent, ART, owner)
    assert (confirmed.applicability, confirmed.status, confirmed.choice) == (
        "active",
        "satisfied",
        local,
    )
    apply_operation(root, _accept_request(case), owner)
    assert read_work_status(root, parent, owner).status == "succeeded"


def test_revised_referenced_choice_reads_stale_until_resolved_again(tmp_path: Path) -> None:
    case = _composite(_space(tmp_path))
    root, _space_id, owner, _activity, parent, _works = case
    choice = _choose(case, "not_required", _work_scope(case))
    _resolve(case, choice)
    apply_operation(root, _link_request(case, _complete_ab(case)), owner)
    assert read_work_status(root, parent, owner).reasons == _acceptance_pending(case)

    revised = _revise_choice(case, choice)
    composition = read_execution(root, parent, owner).composition
    assert composition is not None
    progress = {item.key: item for item in composition.obligations}
    assert (progress[ART].applicability, progress[ART].choice) == ("applicability_stale", choice)
    assert read_work_status(root, parent, owner).reasons == (
        _issue_pending(case, "art"),
        _applicability_stale(choice),
    )
    recorded = read_obligation(root, parent, ART, owner)
    assert (recorded.revision, recorded.applicability, recorded.choice) == (2, "inactive", choice)
    _refused(case, "stale_basis", _accept_request(case))
    _refused(case, "stale_basis", _resolve_request(case, choice))
    assert _resolve(case, revised).result["applicability"] == "inactive"
    apply_operation(root, _accept_request(case), owner)
    assert read_work_status(root, parent, owner).status == "succeeded"


def test_decision_value_leaf_closes_on_another_exact_value(tmp_path: Path) -> None:
    setup = _space(tmp_path)
    general = _choose(setup, "not_required", _activity_scope(setup))
    skip = _child(setup.activity, "skip", "note", readiness=_value(general, "not_required"))
    case = _composite(setup, art_readiness=_value(general, "required"), extra=(skip,))
    root, _space_id, owner, _activity, parent, works = case
    refused = _refused(case, "dependency_closed", _issue_request(case, "art"))
    assert f"{general.decision_id}@1" in refused.detail
    art = read_work_status(root, works["art"], owner)
    assert art.status == "blocked"
    assert art.reasons == (
        StatusReason(code="dependency_closed", record_id=general.decision_id, revision=1, name=ART),
    )
    _issue(case, "skip")
    # The review is not required, so the parent completes without the closed branch.
    assert _resolve(case, general).result["applicability"] == "inactive"
    apply_operation(root, _link_request(case, _complete_ab(case)), owner)
    assert read_work_status(root, parent, owner).reasons == _acceptance_pending(case)
    apply_operation(root, _accept_request(case), owner)
    assert read_work_status(root, parent, owner).status == "succeeded"


def test_formal_conflict_keeps_its_code_through_composite_conditions(tmp_path: Path) -> None:
    setup = _space(tmp_path)
    required = _choose(setup, "required", _activity_scope(setup))
    # One alternative is closed for good by its exact value; the other holds unless a
    # covering choice disagrees with it.
    either = PlanCondition(
        kind="any", members=(_value(required, "required"), _value(required, "not_required"))
    )
    source = PlanCondition(kind="artifact_current", artifact=setup.source)
    a_done = PlanCondition(kind="work_succeeded", role="a")
    dropped_done = PlanCondition(kind="work_succeeded", role="dropped")

    def node(role: str, *members: PlanCondition, kind: Literal["all", "any"]) -> PlanChild:
        readiness = PlanCondition(kind=kind, members=members)
        return _child(setup.activity, role, "note", readiness=readiness)

    case = _composite(
        setup,
        art_readiness=either,
        extra=(
            node("nested_all", either, source, kind="all"),
            node("nested_any", either, dropped_done, kind="any"),
            node("behind_open", a_done, _value(required, "required"), kind="all"),
            node("behind_closed", dropped_done, _value(required, "required"), kind="all"),
            node("open_alternative", _value(required, "required"), a_done, kind="any"),
            node("true_alternative", _value(required, "required"), source, kind="any"),
            _child(setup.activity, "dropped", "note"),
        ),
    )
    root, _space_id, owner, _activity, _parent, works = case
    _cancel(case, "dropped")
    opposite = _choose(case, "not_required", _work_scope(case))

    conflicted = _conflict(required, opposite, key=None)
    waiting_for_a = StatusReason(code="dependency_open", role="a", record_id=works["a"])
    dropped = StatusReason(code="dependency_closed", role="dropped", record_id=works["dropped"])
    derived = {
        "art": conflicted,
        "nested_all": conflicted,
        "nested_any": conflicted,
        "behind_open": (waiting_for_a, *conflicted),
        "behind_closed": (dropped, *conflicted),
        "open_alternative": (*conflicted, waiting_for_a),
    }
    for role, reasons in derived.items():
        status = read_work_status(root, works[role], owner)
        assert (status.status, status.reasons) == ("blocked", reasons)
        assert read_execution(root, works[role], owner).status == status
    checked = {role: works[role] for role in derived}
    assert _statuses_in_new_process(case, checked) == _statuses(case, checked)

    # The operation names the same addressed conflict through every composite, even
    # behind an open member of all, and writes nothing.
    for role in ("art", "nested_all", "nested_any", "behind_open"):
        refused = _refused(case, "decision_conflict", _issue_request(case, role))
        assert str(required.decision_id) in refused.detail
        assert str(opposite.decision_id) in refused.detail
    # A closed member keeps all closed for good; an alternative that may still become true
    # by progress keeps dependency_open; an alternative that holds is not blocked by the
    # conflict of another one.
    _refused(case, "dependency_closed", _issue_request(case, "behind_closed"))
    _refused(case, "dependency_open", _issue_request(case, "open_alternative"))
    _issue(case, "true_alternative")
    assert read_work_status(root, works["true_alternative"], owner).status == "ready"

    _revoke(case, opposite)
    for role in ("art", "nested_all", "nested_any"):
        _issue(case, role)
        assert read_work_status(root, works[role], owner).status == "ready"
    # With the conflict lifted, the open member of all is the only gap again.
    _refused(case, "dependency_open", _issue_request(case, "behind_open"))
    assert read_work_status(root, works["behind_open"], owner).reasons == (waiting_for_a,)


def test_formal_conflict_in_a_nested_completion_refuses_acceptance(tmp_path: Path) -> None:
    setup = _space(tmp_path)
    formal = _choose(setup, "formal", _activity_scope(setup), name="tone")
    completion = PlanCondition(
        kind="any",
        members=(
            PlanCondition(kind="work_succeeded", role="dropped"),
            PlanCondition(
                kind="all",
                members=(
                    PlanCondition(kind="work_succeeded", role="b"),
                    _value(formal, "formal", name="tone"),
                ),
            ),
        ),
    )
    case = _composite(
        setup, extra=(_child(setup.activity, "dropped", "note"),), completion=completion
    )
    root, _space_id, owner, _activity, parent, works = case
    _resolve(case, _choose(case, "not_required", _work_scope(case)))
    apply_operation(root, _link_request(case, _complete_ab(case)), owner)
    _cancel(case, "dropped")
    review = StatusReason(code="branch_review", role="dropped", record_id=works["dropped"])
    assert read_work_status(root, parent, owner).reasons == (*_acceptance_pending(case), review)

    casual = _choose(case, "casual", _work_scope(case), name="tone")
    refused = _refused(case, "decision_conflict", _accept_request(case))
    assert str(formal.decision_id) in refused.detail
    assert str(casual.decision_id) in refused.detail
    blocked = read_work_status(root, parent, owner)
    assert blocked.status == "blocked"
    assert blocked.reasons == (*_conflict(formal, casual, key=None, name="tone"), review)
    assert read_execution(root, parent, owner).status == blocked
    assert _statuses_in_new_process(case, {"parent": parent}) == _statuses(case, {"parent": parent})

    _revoke(case, casual)
    apply_operation(root, _accept_request(case), owner)
    assert read_work_status(root, parent, owner).status == "succeeded"


def test_unsupported_applicability_and_condition_kinds_fail_validation(tmp_path: Path) -> None:
    obligation = {
        "key": "tone",
        "source": "synthetic",
        "role": "art",
        "slot": "reviewed",
        "media_type": "text/plain",
    }
    for applicability in (
        "sometimes",
        {"kind": "expression", "choice": ART, "active": ["required"]},
        {"kind": "choice", "choice": ART, "active": ["required"], "inactive": ["required"]},
        {"kind": "choice", "choice": ART},
        {"kind": "choice", "choice": "Art Review", "active": ["required"]},
    ):
        with pytest.raises(ValidationError):
            MethodObligation.model_validate({**obligation, "applicability": applicability})
    leaf = {"decision_id": str(uuid4()), "decision_revision": 1}
    for condition in (
        {"kind": "predicate", **leaf},
        {"kind": "decision_value", **leaf, "name": ART},
        {"kind": "decision_value", **leaf, "value": "required"},
        {"kind": "decision_active", **leaf, "name": ART, "value": "required"},
        {"kind": "decision_value", "role": "a", "name": ART, "value": "required"},
    ):
        with pytest.raises(ValidationError):
            PlanCondition.model_validate(condition)
    with pytest.raises(ValidationError):
        ChoiceState.model_validate(
            {"statement": "No scope", "name": ART, "value": "required", "scope": {"kind": "space"}}
        )

    # A structurally valid leaf must still name an existing exact choice with its name.
    setup = _space(tmp_path)
    method = _method(setup)
    rule = uuid4()
    _apply(
        setup.root,
        setup.space,
        setup.owner,
        CreateDecisionRequest,
        decision_id=rule,
        state=DecisionState(
            statement="Synthetic reads need a Grant",
            effect="require_grant",
            actions=("record.read",),
        ),
    )
    other_name = _choose(setup, "required", _activity_scope(setup), name="tone_review")
    for readiness in (
        _value(DecisionRef(decision_id=rule, revision=1), "required"),
        _value(other_name, "required"),
        _value(DecisionRef(decision_id=uuid4(), revision=1), "required"),
    ):
        _refused(setup, "invalid_plan", _composite_request(setup, method, art_readiness=readiness))


def test_schema_6_refuses_every_new_applicability_payload(tmp_path: Path) -> None:
    setup = _space(tmp_path, schema=6)
    root, space, owner, activity, _source, seeded = setup
    root_rule = next(
        item.record_id for item in inspect_space(root, owner).records if item.kind == "decision"
    )
    choice = CreateDecisionRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        decision_id=uuid4(),
        state=ChoiceState(
            statement="Too early",
            name=ART,
            value="required",
            scope=DecisionScope(kind="activity", record_id=activity),
        ),
    )
    method = CreateMethodVersionRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        method_id=uuid4(),
        version=1,
        definition=_definition(),
    )
    refusing: tuple[DomainRequest, ...] = (
        choice,
        method,
        ResolveObligationApplicabilityRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=seeded,
            key="checked",
            expected_plan_revision=1,
            expected_obligation_revision=1,
            choice=DecisionRef(decision_id=root_rule, revision=1),
            basis="Too early",
        ),
        ReviseDecisionRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            decision_id=root_rule,
            expected_revision=1,
            state=choice.state,
        ),
    )
    for request in refusing:
        _refused(setup, "unsupported_schema", request)
    assert isinstance(read_decision(root, root_rule, owner).state, DecisionState)

    # After the explicit upgrade the refused intents apply once; nothing was left behind.
    assert upgrade_plan_revision_space(root, owner).schema_version == 7
    assert apply_operation(root, choice, owner).result["revision"] == 1
    assert apply_operation(root, method, owner).result["version"] == 1


def test_access_checks_ignore_choices_and_variants_stay_fixed(tmp_path: Path) -> None:
    case = _composite(_space(tmp_path))
    root, space, owner, _activity, parent, _works = case
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest,
        grant_id=uuid4(),
        state=GrantState(grantee="reader", actions=("record.read",)),
    )
    reader = authorize_local(root, actor="reader", source_ref="fictional-reader")

    def audited_rules() -> list[AuditReference]:
        artifact = _apply(
            root,
            space,
            owner,
            CreateArtifactRequest,
            artifact_id=uuid4(),
            media_type="text/plain",
            content=b"synthetic note",
        )
        return list(read_operation_audit(root, artifact.operation_id, owner).decision_refs)

    rules_before = audited_rules()
    readable = read_work(root, parent, reader)
    # Choices named after an action, in every scope: none of them is an access rule.
    for value, scope in (("deny", _activity_scope(case)), ("require_grant", _work_scope(case))):
        _choose(case, value, scope, name="record-read")
    assert audited_rules() == rules_before
    assert read_work(root, parent, reader) == readable

    deny = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateDecisionRequest,
        decision_id=deny,
        state=DecisionState(
            statement="The synthetic reader may not read now",
            effect="deny",
            actions=("record.read",),
            subjects=("reader",),
        ),
    )
    with pytest.raises(FoundationError, match="decision_denied"):
        read_work(root, parent, reader)
    # A rule never becomes a choice (that would silently drop it), nor a choice a rule.
    choice = _choose(case, "required", _activity_scope(case))
    variants: tuple[DomainRequest, ...] = (
        ReviseDecisionRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            decision_id=deny,
            expected_revision=1,
            state=ChoiceState(
                statement="Not a rule any more",
                name=ART,
                value="required",
                scope=_activity_scope(case),
            ),
        ),
        ReviseDecisionRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            decision_id=choice.decision_id,
            expected_revision=1,
            state=DecisionState(statement="Deny", effect="deny", actions=("record.read",)),
        ),
    )
    for request in variants:
        _refused(case, "invalid_request", request)
    with pytest.raises(FoundationError, match="decision_denied"):
        read_work(root, parent, reader)


def test_choice_scope_exists_and_keeps_its_name_and_scope(tmp_path: Path) -> None:
    case = _composite(_space(tmp_path))
    root, space, owner, activity, parent, works = case
    missing = CreateDecisionRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        decision_id=uuid4(),
        state=ChoiceState(
            statement="For nothing",
            name=ART,
            value="required",
            scope=DecisionScope(kind="work", record_id=uuid4()),
        ),
    )
    _refused(case, "not_found", missing)
    wrong_kind = missing.model_copy(
        update={
            "operation_id": uuid4(),
            "state": missing.state.model_copy(
                update={"scope": DecisionScope(kind="activity", record_id=parent)}
            ),
        }
    )
    _refused(case, "not_found", wrong_kind)
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest,
        grant_id=uuid4(),
        state=GrantState(grantee="worker", actions=("work.write", "method.use", "record.read")),
    )
    worker = authorize_local(root, actor="worker", source_ref="fictional-worker")
    by_worker = missing.model_copy(
        update={
            "operation_id": uuid4(),
            "actor": "worker",
            "state": missing.state.model_copy(update={"scope": _work_scope(case)}),
        }
    )
    before = read_space(root)
    with pytest.raises(FoundationError, match="permission_denied"):
        apply_operation(root, by_worker, worker)
    assert read_space(root) == before

    choice = _choose(case, "required", _work_scope(case))
    current = read_decision(root, choice.decision_id, owner)
    assert isinstance(current.state, ChoiceState)
    for change in (
        {"name": "tone_review"},
        {"scope": DecisionScope(kind="activity", record_id=activity)},
        {"scope": DecisionScope(kind="work", record_id=works["a"])},
    ):
        _refused(
            case,
            "invalid_request",
            ReviseDecisionRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                decision_id=choice.decision_id,
                expected_revision=1,
                state=current.state.model_copy(update=change),
            ),
        )
    _apply(
        root,
        space,
        owner,
        ReviseDecisionRequest,
        decision_id=choice.decision_id,
        expected_revision=1,
        state=current.state.model_copy(update={"value": "not_required"}),
    )
    first = read_decision(root, choice.decision_id, owner, revision=1)
    second = read_decision(root, choice.decision_id, owner)
    assert isinstance(first.state, ChoiceState) and isinstance(second.state, ChoiceState)
    assert (first.state.value, second.state.value, second.revision) == (
        "required",
        "not_required",
        2,
    )
    with pytest.raises(FoundationError, match="not_found"):
        read_decision(root, choice.decision_id, owner, revision=3)


def test_resolution_refusals_name_the_reason_and_write_nothing(tmp_path: Path) -> None:
    case = _composite(_space(tmp_path))
    root, space, owner, _activity, parent, works = case
    rule = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateDecisionRequest,
        decision_id=rule,
        state=DecisionState(
            statement="Synthetic writes need a Grant",
            effect="require_grant",
            actions=("work.write",),
        ),
    )
    valid = _choose(case, "not_required", _work_scope(case))
    other_name = _choose(case, "required", _work_scope(case), name="tone_review")
    other_work = _choose(case, "required", DecisionScope(kind="work", record_id=works["b"]))
    refusals: tuple[tuple[str, ResolveObligationApplicabilityRequest], ...] = (
        ("unconditional_obligation", _resolve_request(case, valid, key="checked")),
        ("not_found", _resolve_request(case, valid, key="missing", obligation_revision=1)),
        ("choice_required", _resolve_request(case, DecisionRef(decision_id=rule, revision=1))),
        ("choice_mismatch", _resolve_request(case, other_name)),
        ("choice_mismatch", _resolve_request(case, other_work)),
        (
            "not_found",
            _resolve_request(case, DecisionRef(decision_id=valid.decision_id, revision=9)),
        ),
        (
            "stale_plan",
            _resolve_request(case, valid).model_copy(update={"expected_plan_revision": 2}),
        ),
        ("stale_obligation", _resolve_request(case, valid, obligation_revision=2)),
    )
    for code, request in refusals:
        _refused(case, code, request)
    unlisted = _choose(case, "maybe", _work_scope(case))
    _refused(case, "choice_mismatch", _resolve_request(case, unlisted))
    _revoke(case, unlisted)
    revoked = _choose(case, "required", _work_scope(case))
    for reference in (revoked, _revoke(case, revoked)):
        _refused(case, "stale_basis", _resolve_request(case, reference))

    # Rights: work.write and method.use, both current, for the parent.
    grants: tuple[tuple[str, tuple[Action, ...]], ...] = (
        ("writer", ("work.write", "record.read")),
        ("user", ("method.use", "record.read")),
    )
    for grantee, actions in grants:
        _apply(
            root,
            space,
            owner,
            CreateGrantRequest,
            grant_id=uuid4(),
            state=GrantState(grantee=grantee, actions=actions),
        )
        actor = authorize_local(root, actor=grantee, source_ref=f"fictional-{grantee}")
        request = _resolve_request(case, valid).model_copy(update={"actor": grantee})
        before = read_space(root)
        with pytest.raises(FoundationError, match="permission_denied"):
            apply_operation(root, request, actor)
        assert read_space(root) == before
    assert read_obligation(root, parent, ART, owner).revision == 1
    assert _resolve(case, valid).result["applicability"] == "inactive"


def test_applicability_history_survives_restore_and_goes_with_its_parent(
    tmp_path: Path,
) -> None:
    case = _composite(_space(tmp_path))
    root, space, owner, _activity, parent, works = case
    choice = _choose(case, "not_required", _work_scope(case))
    marker = f"Synthetic applicability basis {uuid4()}"
    request = _resolve_request(case, choice, basis=marker)
    receipt = apply_operation(root, request, owner)
    backup = create_backup(root, uuid4(), owner)

    restored_root = tmp_path / "restored"
    restored_root.mkdir()
    restored = restore_backup(
        backup.package, restored_root, authorize_recovery(actor="owner", source_ref="restore")
    )
    assert restored.schema_version == 7 and restored.recovery_state == "quarantined"
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
    reopened = authorize_local(restored_root, actor="owner", source_ref="new-epoch")
    first = read_obligation(restored_root, parent, ART, reopened, revision=1)
    assert first.applicability == "unresolved"
    history = read_obligation(restored_root, parent, ART, reopened, revision=2)
    assert (history.applicability, history.choice, history.basis) == ("inactive", choice, marker)
    assert read_decision(restored_root, choice.decision_id, reopened) == read_decision(
        root, choice.decision_id, owner
    )
    assert read_work_status(restored_root, parent, reopened) == read_work_status(
        root, parent, owner
    )

    # Deleting the role's child retires the copied basis; the addressed choice stays.
    for role in ("art", "b", "a"):
        _apply(root, space, owner, DeleteWorkRequest, work_id=works[role], expected_revision=1)
    retained = read_obligation(root, parent, ART, owner)
    assert (retained.revision, retained.applicability, retained.choice, retained.basis) == (
        3,
        "inactive",
        choice,
        None,
    )
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_obligation(root, parent, ART, owner, revision=2)
    with pytest.raises(FoundationError, match="history_unavailable"):
        apply_operation(root, request, owner)
    assert complete_deletions(root, owner).live_store_sanitized
    assert not backup.package.exists()
    assert not _sqlite_contains(root / ".zara-core", marker)

    _apply(
        root,
        space,
        owner,
        DeleteWorkRequest,
        work_id=parent,
        expected_revision=read_work(root, parent, owner).revision,
    )
    assert complete_deletions(root, owner).live_store_sanitized
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_obligation(root, parent, ART, owner)
    with pytest.raises(FoundationError, match="not_found"):
        read_receipt(root, receipt.operation_id, owner)
    assert not _sqlite_contains(create_backup(root, uuid4(), owner).package, marker)
    # There is no Decision deletion operation: the choice stays an ordinary record.
    assert read_decision(root, choice.decision_id, owner).revision == 1
