"""An accepted child result whose premise changed integrates only after an exact recheck.

Part 3.5 of Stage 6 pass 3, model-free through public Core operations.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Literal, NamedTuple
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_applicability import (
    Case,
    Space,
    _activity_scope,
    _child,
    _choose,
    _conflict,
    _refused,
    _revoke,
    _space,
    _statuses,
    _statuses_in_new_process,
    _value,
    _work_scope,
)
from tests.zaratustra.foundation.test_composition import _apply, _result, _sqlite_contains
from zaratustra.foundation import (
    AcceptWorkRequest,
    Action,
    ArtifactRef,
    AuditReference,
    ChoiceState,
    CloseWorkRequest,
    ConfirmObligationRequest,
    CreateArtifactRequest,
    CreateCompositeWorkRequest,
    CreateGrantRequest,
    CreateMethodVersionRequest,
    DeleteArtifactRequest,
    DeleteWorkRequest,
    DomainRequest,
    FoundationError,
    GrantState,
    IssueChildWorkRequest,
    LinkedOutput,
    LinkWorkOutputRequest,
    MethodDefinition,
    MethodObligation,
    MethodRef,
    NamedInput,
    OperationReceipt,
    OutputContract,
    PlanChild,
    PlanCondition,
    PlanOutputBinding,
    PremiseChange,
    RecoverRequest,
    RevalidateResultRequest,
    ReviseArtifactRequest,
    ReviseDecisionRequest,
    StatusReason,
    WorkPlan,
    WorkState,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    read_artifact,
    read_decision,
    read_execution,
    read_obligation,
    read_operation_audit,
    read_receipt,
    read_revalidation,
    read_space,
    read_work,
    read_work_plan,
    read_work_status,
    restore_backup,
)


class Premised(NamedTuple):
    case: Case
    premise: ArtifactRef


def _definition() -> MethodDefinition:
    def obligation(key: str, role: str) -> MethodObligation:
        return MethodObligation(
            key=key,
            source="synthetic recheck contract",
            role=role,
            slot=key,
            media_type="text/plain",
        )

    return MethodDefinition(
        instruction="Check the synthetic premise, then write the summary from the check.",
        named_inputs=(OutputContract(slot="source", media_type="text/plain"),),
        named_outputs=(
            OutputContract(slot="checked", media_type="text/plain"),
            OutputContract(slot="final", media_type="text/plain"),
        ),
        obligations=(obligation("checked", "a"), obligation("final", "b")),
        source_ref="synthetic-recheck-method",
    )


def _artifact(setup: Space | Case, content: bytes, *, revisions: int = 1) -> ArtifactRef:
    """A synthetic Artifact revised until it reaches the requested revision."""

    artifact = uuid4()
    _apply(
        setup.root,
        setup.space,
        setup.owner,
        CreateArtifactRequest,
        artifact_id=artifact,
        media_type="text/plain",
        content=content,
    )
    for revision in range(1, revisions):
        _apply(
            setup.root,
            setup.space,
            setup.owner,
            ReviseArtifactRequest,
            artifact_id=artifact,
            expected_revision=revision,
            media_type="text/plain",
            content=content + f" r{revision + 1}".encode(),
        )
    return ArtifactRef(artifact_id=artifact, revision=revisions)


def _case(
    setup: Space,
    *,
    premise_revisions: int = 1,
    a_readiness: PlanCondition | None = None,
    a_inputs: tuple[ArtifactRef, ...] = (),
    extra: tuple[PlanChild, ...] = (),
) -> Premised:
    """A rests on its own premise only; B needs A's result and C needs A's success."""

    premise = _artifact(setup, b"synthetic premise", revisions=premise_revisions)
    created = _apply(
        setup.root,
        setup.space,
        setup.owner,
        CreateMethodVersionRequest,
        method_id=(method := uuid4()),
        version=1,
        definition=_definition(),
    )
    activity, source = setup.activity, setup.source
    accepted_a = PlanCondition(
        kind="accepted_output", role="a", slot="checked", media_type="text/plain"
    )
    request = CreateCompositeWorkRequest(
        operation_id=uuid4(),
        space_id=setup.space,
        actor="owner",
        work_id=uuid4(),
        state=WorkState(
            activity_id=activity,
            goal="Integrate a synthetic check",
            inputs=(source,),
            expected_outputs=_definition().named_outputs,
            method=MethodRef(method_id=method, version=1, checksum=str(created.result["checksum"])),
        ),
        plan=WorkPlan(
            named_inputs=(NamedInput(slot="source", artifact=source),),
            output_bindings=(
                PlanOutputBinding(
                    parent_slot="checked", role="a", child_slot="checked", media_type="text/plain"
                ),
                PlanOutputBinding(
                    parent_slot="final", role="b", child_slot="final", media_type="text/plain"
                ),
            ),
            children=(
                _child(
                    activity, "a", "checked", inputs=(premise, *a_inputs), readiness=a_readiness
                ),
                _child(activity, "b", "final", readiness=accepted_a),
                _child(
                    activity, "c", "note", readiness=PlanCondition(kind="work_succeeded", role="a")
                ),
                *extra,
            ),
            completion=PlanCondition(
                kind="all",
                members=(
                    PlanCondition(kind="work_succeeded", role="b"),
                    PlanCondition(kind="work_succeeded", role="c"),
                ),
            ),
            basis=(source,),
            rationale="Synthetic plan integrating one check",
            source_ref="fictional-owner-plan",
        ),
    )
    apply_operation(setup.root, request, setup.owner)
    case = Case(
        setup.root,
        setup.space,
        setup.owner,
        activity,
        request.work_id,
        {child.role: child.work_id for child in request.plan.children},
    )
    return Premised(case, premise)


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


def _link_request(case: Case, slot: str, artifact: ArtifactRef) -> LinkWorkOutputRequest:
    return LinkWorkOutputRequest(
        operation_id=uuid4(),
        space_id=case.space,
        actor="owner",
        work_id=case.parent,
        expected_revision=read_work(case.root, case.parent, case.owner).revision,
        output=LinkedOutput(slot=slot, artifact=artifact),
    )


def _accept_request(case: Case) -> AcceptWorkRequest:
    return AcceptWorkRequest(
        operation_id=uuid4(),
        space_id=case.space,
        actor="owner",
        work_id=case.parent,
        expected_revision=read_work(case.root, case.parent, case.owner).revision,
        basis="Synthetic parent acceptance",
    )


def _recheck_request(
    case: Case,
    premises: tuple[PremiseChange, ...],
    *,
    role: str = "a",
    work: UUID | None = None,
    outputs: tuple[LinkedOutput, ...] | None = None,
    basis: str = "Synthetic recheck: the check still holds on the revised premise",
) -> RevalidateResultRequest:
    child = work or case.works[role]
    return RevalidateResultRequest(
        operation_id=uuid4(),
        space_id=case.space,
        actor="owner",
        parent_work_id=case.parent,
        role=role,
        work_id=child,
        outputs=outputs
        if outputs is not None
        else read_work(case.root, child, case.owner).state.linked_outputs,
        expected_plan_revision=read_work_plan(case.root, case.parent, case.owner).revision,
        premises=premises,
        basis=basis,
    )


def _apply_all(case: Case, *requests: DomainRequest) -> list[OperationReceipt]:
    return [apply_operation(case.root, request, case.owner) for request in requests]


def _revise(case: Case, artifact: ArtifactRef, content: bytes) -> ArtifactRef:
    _apply(
        case.root,
        case.space,
        case.owner,
        ReviseArtifactRequest,
        artifact_id=artifact.artifact_id,
        expected_revision=artifact.revision,
        media_type="text/plain",
        content=content,
    )
    return ArtifactRef(artifact_id=artifact.artifact_id, revision=artifact.revision + 1)


def _changed(
    record: UUID,
    revision: int,
    current: int | None,
    kind: Literal["artifact", "decision"] = "artifact",
) -> PremiseChange:
    return PremiseChange(kind=kind, record_id=record, revision=revision, current=current)


def _premise_reason(case: Case, change: PremiseChange, role: str = "a") -> StatusReason:
    return StatusReason(
        code="premise_changed", role=role, record_id=case.works[role], premise=change
    )


def _addressed(refused: FoundationError, case: Case, change: PremiseChange) -> None:
    current = "unavailable" if change.current is None else f"@{change.current}"
    assert str(case.works["a"]) in refused.detail
    assert f"{change.record_id}@{change.revision} -> {current}" in refused.detail


def _run_a(case: Case) -> ArtifactRef:
    apply_operation(case.root, _issue_request(case, "a"), case.owner)
    return _result(
        case.root, case.space, case.owner, case.works["a"], "checked", b"synthetic check"
    )


def test_changed_premise_refuses_integration_until_an_exact_recheck(tmp_path: Path) -> None:
    case, premise = _case(_space(tmp_path))
    root, space, owner, _activity, parent, works = case
    check = _run_a(case)
    second = _revise(case, premise, b"synthetic premise revised")
    change = _changed(premise.artifact_id, 1, 2)

    # The result stays a really performed action: succeeded, and its Artifact reads.
    assert read_work(root, works["a"], owner).state.status == "succeeded"
    assert read_artifact(root, check.artifact_id, owner, revision=1).content == b"synthetic check"
    refusing: tuple[DomainRequest, ...] = (
        _issue_request(case, "b"),
        _issue_request(case, "c"),
        _confirm_request(case, "checked", check),
        _link_request(case, "checked", check),
    )
    for request in refusing:
        _addressed(_refused(case, "premise_changed", request), case, change)
    a_status = read_work_status(root, works["a"], owner)
    assert (a_status.status, a_status.reasons) == ("succeeded", (_premise_reason(case, change),))
    blocked = read_work_status(root, parent, owner)
    assert (blocked.status, blocked.reasons) == ("blocked", (_premise_reason(case, change),))
    for role in ("b", "c"):
        dependent = read_work_status(root, works[role], owner)
        assert (dependent.status, dependent.reasons) == (
            "blocked",
            (_premise_reason(case, change),),
        )
    everything = {"parent": parent, **works}
    assert _statuses_in_new_process(case, everything) == _statuses(case, everything)

    # A recheck names exactly the changed premises and their current revisions.
    source = read_work(root, parent, owner).state.inputs[0]
    other = _artifact(case, b"synthetic unrelated artifact")
    refusals: tuple[tuple[str, RevalidateResultRequest], ...] = (
        ("premise_mismatch", _recheck_request(case, (_changed(source.artifact_id, 1, 2),))),
        ("premise_mismatch", _recheck_request(case, (change, _changed(source.artifact_id, 1, 2)))),
        ("premise_mismatch", _recheck_request(case, (_changed(premise.artifact_id, 2, 3),))),
        ("stale_basis", _recheck_request(case, (_changed(premise.artifact_id, 1, 3),))),
        (
            "wrong_work",
            _recheck_request(
                case,
                (change,),
                role="a",
                work=works["b"],
                outputs=(LinkedOutput(slot="checked", artifact=check),),
            ),
        ),
        ("wrong_work", _recheck_request(case, (change,), role="b", work=works["a"])),
        (
            "dependency_open",
            _recheck_request(
                case, (change,), role="b", outputs=(LinkedOutput(slot="final", artifact=check),)
            ),
        ),
        (
            "output_mismatch",
            _recheck_request(
                case, (change,), outputs=(LinkedOutput(slot="checked", artifact=other),)
            ),
        ),
        (
            "stale_plan",
            _recheck_request(case, (change,)).model_copy(update={"expected_plan_revision": 2}),
        ),
    )
    for code, request in refusals:
        _refused(case, code, request)

    marker = f"Synthetic recheck basis {uuid4()}"
    request = _recheck_request(case, (change,), basis=marker)
    receipt = apply_operation(root, request, owner)
    assert receipt.result == {
        "parent_work_id": str(parent),
        "role": "a",
        "work_id": str(works["a"]),
        "revision": 1,
        "premises": [change.model_dump(mode="json")],
    }
    assert marker not in json.dumps(receipt.model_dump(mode="json"))
    assert apply_operation(root, request, owner) == receipt
    audit = read_operation_audit(root, receipt.operation_id, owner)
    assert AuditReference(record_id=premise.artifact_id, revision=2) in audit.target_refs
    recorded = read_revalidation(root, parent, works["a"], owner)
    assert (recorded.revision, recorded.premises, recorded.basis) == (1, (change,), marker)
    assert recorded.outputs == (LinkedOutput(slot="checked", artifact=check),)
    assert read_revalidation(root, parent, works["a"], owner, revision=1) == recorded
    assert read_work_status(root, works["a"], owner).reasons == ()
    composition = read_execution(root, parent, owner).composition
    assert composition is not None
    assert {child.role: child.revalidation for child in composition.children} == {
        "a": 1,
        "b": None,
        "c": None,
    }

    # The same exact result now integrates: B gets it as its exact input.
    _apply_all(
        case,
        _issue_request(case, "b"),
        _confirm_request(case, "checked", check),
        _link_request(case, "checked", check),
    )
    assert read_work(root, works["b"], owner).state.inputs == (check,)
    assert read_obligation(root, parent, "checked", owner).evidence == check

    # The next change needs a new recheck; the earlier one permits nothing any more.
    _revise(case, second, b"synthetic premise revised again")
    later = _changed(premise.artifact_id, 1, 3)
    _addressed(_refused(case, "premise_changed", _issue_request(case, "c")), case, later)
    _addressed(
        _refused(case, "premise_changed", _link_request(case, "checked", check)), case, later
    )
    b_status = read_work_status(root, works["b"], owner)
    assert (b_status.status, b_status.reasons) == ("blocked", (_premise_reason(case, later),))
    assert _statuses_in_new_process(case, everything) == _statuses(case, everything)
    assert apply_operation(root, _recheck_request(case, (later,)), owner).result["revision"] == 2
    apply_operation(root, _issue_request(case, "c"), owner)
    assert read_work_status(root, works["b"], owner).status == "ready"


def test_acceptance_refuses_premise_changed_and_keeps_the_satisfied_obligation(
    tmp_path: Path,
) -> None:
    case, premise = _case(_space(tmp_path))
    root, space, owner, _activity, parent, works = case
    check = _run_a(case)
    _apply_all(
        case, _confirm_request(case, "checked", check), _link_request(case, "checked", check)
    )
    apply_operation(root, _issue_request(case, "b"), owner)
    summary = _result(root, space, owner, works["b"], "final", b"synthetic summary")
    _apply_all(
        case, _confirm_request(case, "final", summary), _link_request(case, "final", summary)
    )
    apply_operation(root, _issue_request(case, "c"), owner)
    _result(root, space, owner, works["c"], "note", b"synthetic note")
    pending = read_work_status(root, parent, owner)
    assert pending.reasons == (StatusReason(code="acceptance_pending", record_id=parent),)

    _revise(case, premise, b"synthetic premise revised")
    change = _changed(premise.artifact_id, 1, 2)
    _addressed(_refused(case, "premise_changed", _accept_request(case)), case, change)
    # The satisfied obligation is not reopened silently: it keeps its exact evidence.
    confirmed = read_obligation(root, parent, "checked", owner)
    assert (confirmed.revision, confirmed.status, confirmed.evidence) == (2, "satisfied", check)
    blocked = read_work_status(root, parent, owner)
    assert (blocked.status, blocked.reasons) == ("blocked", (_premise_reason(case, change),))
    # Results resting only on the unchanged result of A are not premise-changed themselves.
    assert read_work_status(root, works["b"], owner).reasons == ()

    apply_operation(root, _recheck_request(case, (change,)), owner)
    assert read_work_status(root, parent, owner).reasons == pending.reasons
    apply_operation(root, _accept_request(case), owner)
    assert read_work_status(root, parent, owner).status == "succeeded"
    # Once the parent is accepted, later changes are history, not a pending recheck.
    _revise(case, ArtifactRef(artifact_id=premise.artifact_id, revision=2), b"synthetic r3")
    assert read_work_status(root, works["a"], owner).reasons == ()


def test_result_accepted_on_c7_integrates_only_after_a_recheck(tmp_path: Path) -> None:
    """The W22 example: accepted on C@7, then C@8."""

    case, c7 = _case(_space(tmp_path), premise_revisions=7)
    root, _space_id, owner, _activity, _parent, works = case
    assert c7.revision == 7
    check = _run_a(case)
    _revise(case, c7, b"synthetic C revised to 8")
    change = _changed(c7.artifact_id, 7, 8)
    _addressed(_refused(case, "premise_changed", _issue_request(case, "b")), case, change)
    assert read_work(root, works["a"], owner).state.inputs == (c7,)
    apply_operation(root, _recheck_request(case, (change,)), owner)
    apply_operation(root, _issue_request(case, "b"), owner)
    assert read_work(root, works["b"], owner).state.inputs == (check,)


def test_changed_decision_premise_is_rechecked_only_to_an_active_revision(tmp_path: Path) -> None:
    setup = _space(tmp_path)
    tone = _choose(setup, "formal", _activity_scope(setup), name="tone")
    case, _premise = _case(setup, a_readiness=_value(tone, "formal", name="tone"))
    root, space, owner, _activity, _parent, works = case
    _run_a(case)
    current = read_decision(root, tone.decision_id, owner)
    assert isinstance(current.state, ChoiceState)
    _apply(
        root,
        space,
        owner,
        ReviseDecisionRequest,
        decision_id=tone.decision_id,
        expected_revision=1,
        state=current.state.model_copy(update={"statement": "Synthetic tone, restated"}),
    )
    change = _changed(tone.decision_id, 1, 2, kind="decision")
    _addressed(_refused(case, "premise_changed", _issue_request(case, "b")), case, change)
    apply_operation(root, _recheck_request(case, (change,)), owner)
    apply_operation(root, _issue_request(case, "c"), owner)

    _apply(
        root,
        space,
        owner,
        ReviseDecisionRequest,
        decision_id=tone.decision_id,
        expected_revision=2,
        state=current.state.model_copy(update={"status": "revoked"}),
    )
    revoked = _changed(tone.decision_id, 1, 3, kind="decision")
    _addressed(_refused(case, "premise_changed", _issue_request(case, "b")), case, revoked)
    # A revoked revision is no premise to recheck onto.
    refused = _refused(case, "stale_basis", _recheck_request(case, (revoked,)))
    assert f"{tone.decision_id}@1" in refused.detail
    assert read_work_status(root, works["a"], owner).reasons == (_premise_reason(case, revoked),)


def test_recheck_refusals_rights_and_schema(tmp_path: Path) -> None:
    case, premise = _case(_space(tmp_path))
    root, space, owner, _activity, parent, works = case
    _run_a(case)
    _revise(case, premise, b"synthetic premise revised")
    change = _changed(premise.artifact_id, 1, 2)

    # Rights: work.accept and method.use, both current, for the parent.
    grants: tuple[tuple[str, tuple[Action, ...]], ...] = (
        ("acceptor", ("work.accept", "record.read")),
        ("user", ("method.use", "record.read", "work.write", "decision.write")),
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
        request = _recheck_request(case, (change,)).model_copy(update={"actor": grantee})
        before = read_space(root)
        with pytest.raises(FoundationError, match="permission_denied"):
            apply_operation(root, request, actor)
        assert read_space(root) == before

    # A closed parent takes no recheck; nothing is written.
    for role in ("b", "c"):
        apply_operation(
            root,
            CloseWorkRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                work_id=works[role],
                expected_revision=read_work(root, works[role], owner).revision,
                outcome="cancelled",
                basis=f"Synthetic {role} is not needed",
            ),
            owner,
        )
    apply_operation(
        root,
        CloseWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=parent,
            expected_revision=read_work(root, parent, owner).revision,
            outcome="cancelled",
            basis="Synthetic packet is not needed",
        ),
        owner,
    )
    _refused(case, "work_closed", _recheck_request(case, (change,)))
    with pytest.raises(FoundationError, match="not_found"):
        read_revalidation(root, parent, works["a"], owner)

    # Schema 6 has neither the operation nor its table.
    (tmp_path / "old").mkdir()
    old = _space(tmp_path / "old", schema=6)
    old_method = read_work(old.root, old.seeded, old.owner).state.method
    assert isinstance(old_method, MethodRef)
    request = RevalidateResultRequest(
        operation_id=uuid4(),
        space_id=old.space,
        actor="owner",
        parent_work_id=old.seeded,
        role="a",
        work_id=uuid4(),
        outputs=(LinkedOutput(slot="checked", artifact=old.source),),
        expected_plan_revision=1,
        premises=(_changed(old.source.artifact_id, 1, 2),),
        basis="Too early",
    )
    _refused(old, "unsupported_schema", request)
    with pytest.raises(FoundationError, match="unsupported_schema"):
        read_revalidation(old.root, old.seeded, uuid4(), old.owner)
    invalid_requests: tuple[dict[str, object], ...] = (
        {"premises": [change.model_dump(mode="json") | {"current": None}]},
        {"premises": [change.model_dump(mode="json")] * 2},
        {"premises": []},
    )
    for invalid in invalid_requests:
        with pytest.raises(ValueError):
            RevalidateResultRequest.model_validate(request.model_dump(mode="json") | invalid)
    with pytest.raises(ValueError):
        PremiseChange(kind="artifact", record_id=premise.artifact_id, revision=2, current=2)


@pytest.mark.parametrize("deleted", ["premise", "output", "child"])
def test_recheck_history_survives_restore_and_deletion_removes_its_basis(
    tmp_path: Path, deleted: str
) -> None:
    case, premise = _case(_space(tmp_path))
    root, space, owner, _activity, parent, works = case
    check = _run_a(case)
    second = _revise(case, premise, b"synthetic premise revised")
    change = _changed(premise.artifact_id, 1, 2)
    marker = f"Synthetic recheck basis {uuid4()}"
    request = _recheck_request(case, (change,), basis=marker)
    apply_operation(root, request, owner)
    apply_operation(root, _issue_request(case, "b"), owner)
    backup = create_backup(root, uuid4(), owner)

    restored_root = tmp_path / "restored"
    restored_root.mkdir()
    restore_backup(
        backup.package, restored_root, authorize_recovery(actor="owner", source_ref="restore")
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
    reopened = authorize_local(restored_root, actor="owner", source_ref="new-epoch")
    kept = read_revalidation(restored_root, parent, works["a"], reopened)
    assert kept == read_revalidation(root, parent, works["a"], owner)
    assert kept.basis == marker
    assert read_work_status(restored_root, works["b"], reopened) == read_work_status(
        root, works["b"], owner
    )

    # Deleting the child, its output or a named premise removes the recheck basis; the
    # addresses stay, its receipt leaves replay and nothing integrates on it any more.
    if deleted == "premise":
        _apply(
            root,
            space,
            owner,
            DeleteArtifactRequest,
            artifact_id=second.artifact_id,
            expected_revision=2,
        )
    elif deleted == "output":
        _apply(
            root,
            space,
            owner,
            DeleteArtifactRequest,
            artifact_id=check.artifact_id,
            expected_revision=1,
        )
    else:
        for role in ("b", "a"):
            _apply(
                root,
                space,
                owner,
                DeleteWorkRequest,
                work_id=works[role],
                expected_revision=read_work(root, works[role], owner).revision,
            )
    retained = read_revalidation(root, parent, works["a"], owner)
    assert retained.basis is None
    assert retained.model_copy(update={"basis": marker}) == kept
    with pytest.raises(FoundationError, match="history_unavailable"):
        apply_operation(root, request, owner)
    assert complete_deletions(root, owner).live_store_sanitized
    assert not backup.package.exists()
    assert not _sqlite_contains(root / ".zara-core", marker)
    if deleted != "child":
        with pytest.raises(FoundationError, match="premise_changed|content_unavailable"):
            apply_operation(root, _confirm_request(case, "checked", check), owner)
    checked = {"parent": parent, "a": works["a"]} if deleted != "child" else {"parent": parent}
    assert _statuses_in_new_process(case, checked) == _statuses(case, checked)

    # Deleting the parent after its children clears every recheck record.
    for role in ("c", "b", "a"):
        if _exists(case, works[role]):
            _apply(
                root,
                space,
                owner,
                DeleteWorkRequest,
                work_id=works[role],
                expected_revision=read_work(root, works[role], owner).revision,
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
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_revalidation(root, parent, works["a"], owner)
    assert not _sqlite_contains(create_backup(root, uuid4(), owner).package, marker)
    assert not _sqlite_contains(root / ".zara-core", marker)


def _exists(case: Case, work: UUID) -> bool:
    try:
        read_work(case.root, work, case.owner)
    except FoundationError as error:
        assert error.code == "content_unavailable"
        return False
    return True


def _basis_in_new_process(case: Case, work: UUID) -> str | None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, sys; from pathlib import Path; from uuid import UUID; "
            "from zaratustra.foundation import authorize_local, read_revalidation; "
            "p=Path(sys.argv[1]); o=authorize_local(p, actor='owner', source_ref='restart'); "
            "r=read_revalidation(p, UUID(sys.argv[2]), UUID(sys.argv[3]), o); "
            "print(json.dumps(r.basis))",
            str(case.root),
            str(case.parent),
            str(work),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    basis = json.loads(result.stdout)
    assert basis is None or isinstance(basis, str)
    return basis


def _delete_in_new_process(case: Case, kind: str, record: UUID) -> None:
    """Delete one Artifact or Work and finish maintenance in a separate Python process."""

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; from uuid import UUID, uuid4; "
            "from zaratustra.foundation import DeleteArtifactRequest, DeleteWorkRequest, "
            "apply_operation, authorize_local, complete_deletions, read_artifact, read_work; "
            "p=Path(sys.argv[1]); o=authorize_local(p, actor='owner', source_ref='restart'); "
            "s, r = UUID(sys.argv[2]), UUID(sys.argv[4]); "
            "q = DeleteWorkRequest(operation_id=uuid4(), space_id=s, actor='owner', work_id=r, "
            "expected_revision=read_work(p, r, o).revision) if sys.argv[3] == 'work' else "
            "DeleteArtifactRequest(operation_id=uuid4(), space_id=s, actor='owner', "
            "artifact_id=r, expected_revision=read_artifact(p, r, o).revision); "
            "apply_operation(p, q, o); print(complete_deletions(p, o).live_store_sanitized)",
            str(case.root),
            str(case.space),
            kind,
            str(record),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


def _assert_basis_gone(
    case: Case, work: UUID, request: RevalidateResultRequest, receipt: OperationReceipt, marker: str
) -> None:
    """The recheck keeps its addresses and audit; its basis, receipt and replay are gone."""

    retained = read_revalidation(case.root, case.parent, work, case.owner)
    assert retained.basis is None
    assert (retained.premises, retained.outputs) == (request.premises, request.outputs)
    assert _basis_in_new_process(case, work) is None
    with pytest.raises(FoundationError, match="history_unavailable"):
        apply_operation(case.root, request, case.owner)
    with pytest.raises(FoundationError, match="not_found"):
        read_receipt(case.root, receipt.operation_id, case.owner)
    audit = read_operation_audit(case.root, receipt.operation_id, case.owner)
    assert {item.record_id for item in audit.target_refs} >= {work, case.parent}
    assert not _sqlite_contains(case.root / ".zara-core", marker)


@pytest.mark.parametrize("quoted", ["readiness", "plan_basis", "unchanged_input"])
def test_recheck_basis_goes_with_any_premise_it_quotes(tmp_path: Path, quoted: str) -> None:
    """Codex review of c11d54f (P1): the basis may quote premises that did not change."""

    setup = _space(tmp_path)
    marker = f"synthetic quoted premise {uuid4()}"
    quoted_artifact = _artifact(setup, f"synthetic Y {marker}".encode())
    if quoted == "readiness":
        premised = _case(
            setup, a_readiness=PlanCondition(kind="artifact_current", artifact=quoted_artifact)
        )
    elif quoted == "plan_basis":
        # The common input of the parent and the basis of its plan.
        premised = _case(setup._replace(source=quoted_artifact))
    else:
        premised = _case(setup, a_inputs=(quoted_artifact,))
    case, premise = premised
    root, space, owner, _activity, _parent, works = case
    _run_a(case)
    _revise(case, premise, b"synthetic premise revised")
    request = _recheck_request(
        case, (_changed(premise.artifact_id, 1, 2),), basis=f"Still holds: Y says {marker}"
    )
    receipt = apply_operation(root, request, owner)
    assert _basis_in_new_process(case, works["a"]) == request.basis
    old_backup = create_backup(root, uuid4(), owner)

    _apply(
        root,
        space,
        owner,
        DeleteArtifactRequest,
        artifact_id=quoted_artifact.artifact_id,
        expected_revision=1,
    )
    assert complete_deletions(root, owner).live_store_sanitized
    assert not old_backup.package.exists()
    _assert_basis_gone(case, works["a"], request, receipt, marker)
    assert not _sqlite_contains(create_backup(root, uuid4(), owner).package, marker)
    # The outcome stays: A is still the accepted Work it was.
    assert read_work(root, works["a"], owner).state.status == "succeeded"


@pytest.mark.parametrize("deleted", ["upstream_artifact", "upstream_child"])
def test_recheck_of_a_downstream_result_goes_with_its_upstream(
    tmp_path: Path, deleted: str
) -> None:
    setup = _space(tmp_path)
    marker = f"synthetic upstream quote {uuid4()}"
    upstream = _artifact(setup, b"synthetic Y")
    case, _premise = _case(
        setup, a_readiness=PlanCondition(kind="artifact_current", artifact=upstream)
    )
    root, space, owner, _activity, _parent, works = case
    check = _run_a(case)
    apply_operation(root, _issue_request(case, "b"), owner)
    _result(root, space, owner, works["b"], "final", b"synthetic summary")
    # B rests on A's exact result; a new revision of that result changes B's premise.
    _revise(case, check, b"synthetic check restated")
    request = _recheck_request(
        case,
        (_changed(check.artifact_id, 1, 2),),
        role="b",
        basis=f"The summary still holds; A was ready on Y: {marker}",
    )
    receipt = apply_operation(root, request, owner)
    if deleted == "upstream_artifact":
        _apply(
            root,
            space,
            owner,
            DeleteArtifactRequest,
            artifact_id=upstream.artifact_id,
            expected_revision=1,
        )
    else:
        _apply(
            root,
            space,
            owner,
            DeleteWorkRequest,
            work_id=works["a"],
            expected_revision=read_work(root, works["a"], owner).revision,
        )
    assert complete_deletions(root, owner).live_store_sanitized
    _assert_basis_gone(case, works["b"], request, receipt, marker)
    assert read_work(root, works["b"], owner).state.status == "succeeded"


def _independent_case(setup: Space) -> tuple[Case, dict[str, ArtifactRef], dict[str, str]]:
    """A and B rest on their own inputs and readiness Artifacts; neither needs the other."""

    markers = {name: f"synthetic {name} marker {uuid4()}" for name in ("ya", "yb")}
    premises = {
        "xa": _artifact(setup, b"synthetic premise of a"),
        "xb": _artifact(setup, b"synthetic premise of b"),
        "ya": _artifact(setup, f"synthetic Y of a {markers['ya']}".encode()),
        "yb": _artifact(setup, f"synthetic Y of b {markers['yb']}".encode()),
    }
    created = _apply(
        setup.root,
        setup.space,
        setup.owner,
        CreateMethodVersionRequest,
        method_id=(method := uuid4()),
        version=1,
        definition=_definition(),
    )

    def ready(name: str) -> PlanCondition:
        return PlanCondition(kind="artifact_current", artifact=premises[name])

    request = CreateCompositeWorkRequest(
        operation_id=uuid4(),
        space_id=setup.space,
        actor="owner",
        work_id=uuid4(),
        state=WorkState(
            activity_id=setup.activity,
            goal="Integrate two independent synthetic checks",
            inputs=(setup.source,),
            expected_outputs=_definition().named_outputs,
            method=MethodRef(method_id=method, version=1, checksum=str(created.result["checksum"])),
        ),
        plan=WorkPlan(
            named_inputs=(NamedInput(slot="source", artifact=setup.source),),
            output_bindings=(
                PlanOutputBinding(
                    parent_slot="checked", role="a", child_slot="checked", media_type="text/plain"
                ),
                PlanOutputBinding(
                    parent_slot="final", role="b", child_slot="final", media_type="text/plain"
                ),
            ),
            children=(
                _child(
                    setup.activity, "a", "checked", inputs=(premises["xa"],), readiness=ready("ya")
                ),
                _child(
                    setup.activity, "b", "final", inputs=(premises["xb"],), readiness=ready("yb")
                ),
            ),
            completion=PlanCondition(
                kind="all",
                members=(
                    PlanCondition(kind="work_succeeded", role="a"),
                    PlanCondition(kind="work_succeeded", role="b"),
                ),
            ),
            basis=(setup.source,),
            rationale="Two independent synthetic checks",
            source_ref="fictional-owner-plan",
        ),
    )
    apply_operation(setup.root, request, setup.owner)
    case = Case(
        setup.root,
        setup.space,
        setup.owner,
        setup.activity,
        request.work_id,
        {child.role: child.work_id for child in request.plan.children},
    )
    return case, premises, markers


def test_recheck_bases_follow_sequential_deletions_after_restart(tmp_path: Path) -> None:
    case, named, quoted = _independent_case(_space(tmp_path))
    root, space, owner, _activity, parent, works = case
    markers = {"a": quoted["ya"], "b": quoted["yb"]}
    requests: dict[str, RevalidateResultRequest] = {}
    receipts: dict[str, OperationReceipt] = {}
    for role, premise in (("a", named["xa"]), ("b", named["xb"])):
        apply_operation(root, _issue_request(case, role), owner)
        slot = "checked" if role == "a" else "final"
        _result(root, space, owner, works[role], slot, f"synthetic {role} result".encode())
        _revise(case, premise, f"synthetic premise of {role} revised".encode())
        requests[role] = _recheck_request(
            case,
            (_changed(premise.artifact_id, 1, 2),),
            role=role,
            basis=f"Still holds on {markers[role]}",
        )
        receipts[role] = apply_operation(root, requests[role], owner)
    first_backup = create_backup(root, uuid4(), owner)

    # Deleting A's readiness Artifact retires A's recheck basis; B's record is independent.
    ya, yb = named["ya"], named["yb"]
    _apply(
        root, space, owner, DeleteArtifactRequest, artifact_id=ya.artifact_id, expected_revision=1
    )
    assert complete_deletions(root, owner).live_store_sanitized
    assert not first_backup.package.exists()
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_work_plan(root, parent, owner)
    _assert_basis_gone(case, works["a"], requests["a"], receipts["a"], markers["a"])
    kept = read_revalidation(root, parent, works["b"], owner)
    assert kept.basis == requests["b"].basis
    assert _basis_in_new_process(case, works["b"]) == requests["b"].basis
    assert apply_operation(root, requests["b"], owner) == receipts["b"]
    assert read_receipt(root, receipts["b"].operation_id, owner) == receipts["b"]
    second_backup = create_backup(root, uuid4(), owner)
    assert _sqlite_contains(second_backup.package, markers["b"])

    # A new process deletes B's readiness Artifact; the plan is known only by its index.
    _delete_in_new_process(case, "artifact", yb.artifact_id)
    assert not second_backup.package.exists()
    _assert_basis_gone(case, works["b"], requests["b"], receipts["b"], markers["b"])
    assert read_revalidation(root, parent, works["a"], owner).basis is None
    assert [read_work(root, works[role], owner).state.status for role in ("a", "b")] == [
        "succeeded",
        "succeeded",
    ]
    fresh = create_backup(root, uuid4(), owner).package
    assert not any(_sqlite_contains(fresh, marker) for marker in markers.values())


def test_premise_changed_keeps_its_code_through_composite_conditions(tmp_path: Path) -> None:
    """Owner refinement after the Codex review of c11d54f.

    A changed premise of an accepted result is a blocking reason, like a formal conflict:
    it keeps its addressed code through nested all/any. A true alternative still passes,
    a member that is really waiting keeps dependency_open, and closed members keep
    dependency_closed. A formal conflict is named before it; stale_basis is unchanged.
    """

    setup = _space(tmp_path)
    tone = _choose(setup, "formal", _activity_scope(setup), name="tone")
    stale_source = _artifact(setup, b"synthetic Z")
    a_out = PlanCondition(kind="accepted_output", role="a", slot="checked", media_type="text/plain")
    a_done = PlanCondition(kind="work_succeeded", role="a")
    b_done = PlanCondition(kind="work_succeeded", role="b")
    dropped_done = PlanCondition(kind="work_succeeded", role="dropped")
    source_ok = PlanCondition(kind="artifact_current", artifact=setup.source)
    z_ok = PlanCondition(kind="artifact_current", artifact=stale_source)
    formal = _value(tone, "formal", name="tone")

    def any_of(*members: PlanCondition) -> PlanCondition:
        return PlanCondition(kind="any", members=members)

    def all_of(*members: PlanCondition) -> PlanCondition:
        return PlanCondition(kind="all", members=members)

    readiness = {
        "closed_other": any_of(a_out, dropped_done),
        "waiting_other": any_of(a_out, b_done),
        "true_other": any_of(a_out, source_ok),
        "behind_open": all_of(b_done, a_done),
        "behind_closed": all_of(dropped_done, a_out),
        "nested_all": all_of(any_of(a_out, dropped_done), source_ok),
        "nested_any": any_of(all_of(a_done, source_ok), dropped_done),
        "any_conflict": any_of(formal, a_out),
        "all_conflict": all_of(a_out, formal),
        "stale_closed": any_of(z_ok, dropped_done),
        "stale_changed": any_of(z_ok, a_out),
        "stale_first": all_of(z_ok, b_done),
        "stale_then_changed": all_of(z_ok, a_out),
    }
    extra = (
        _child(setup.activity, "dropped", "note"),
        *(_child(setup.activity, role, "note", readiness=item) for role, item in readiness.items()),
    )
    case, premise = _case(setup, extra=extra)
    root, space, owner, _activity, parent, works = case
    _run_a(case)
    apply_operation(
        root,
        CloseWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=works["dropped"],
            expected_revision=1,
            outcome="cancelled",
            basis="Synthetic branch is not needed",
        ),
        owner,
    )
    casual = _choose(case, "casual", _work_scope(case), name="tone")
    _revise(case, premise, b"synthetic premise revised")
    _revise(case, stale_source, b"synthetic Z revised")

    change = _changed(premise.artifact_id, 1, 2)
    changed = _premise_reason(case, change)
    closed = StatusReason(code="dependency_closed", role="dropped", record_id=works["dropped"])
    waiting = StatusReason(code="dependency_open", role="b", record_id=works["b"])
    stale = StatusReason(code="stale_basis", record_id=stale_source.artifact_id, revision=1)
    conflicted = _conflict(tone, casual, key=None, name="tone")
    derived: dict[str, tuple[StatusReason, ...]] = {
        "closed_other": (changed,),
        "waiting_other": (changed, waiting),
        "behind_open": (waiting, changed),
        "behind_closed": (closed, changed),
        "nested_all": (changed,),
        "nested_any": (changed,),
        "any_conflict": (*conflicted, changed),
        "all_conflict": (changed, *conflicted),
        "stale_closed": (stale,),
        "stale_changed": (stale, changed),
        "stale_first": (stale, waiting),
        "stale_then_changed": (stale, changed),
    }
    for role, reasons in derived.items():
        status = read_work_status(root, works[role], owner)
        assert (role, status.status, status.reasons) == (role, "blocked", reasons)
        assert read_execution(root, works[role], owner).status == status
    checked = {role: works[role] for role in derived}
    assert _statuses_in_new_process(case, checked) == _statuses(case, checked)

    operations = {
        "closed_other": "premise_changed",
        "waiting_other": "dependency_open",
        "behind_open": "premise_changed",
        "behind_closed": "dependency_closed",
        "nested_all": "premise_changed",
        "nested_any": "premise_changed",
        "any_conflict": "decision_conflict",
        "all_conflict": "decision_conflict",
        # stale_basis keeps its earlier semantics: a waiting member of any, the first
        # refusal of all without a closed member, a conflict or a changed premise.
        "stale_closed": "dependency_open",
        "stale_changed": "dependency_open",
        "stale_first": "stale_basis",
        # Beside a stale member, all names the changed premise, as it names a conflict.
        "stale_then_changed": "premise_changed",
    }
    for role, code in operations.items():
        refused = _refused(case, code, _issue_request(case, role))
        assert (role, refused.code) == (role, code)
        if code == "premise_changed":
            _addressed(refused, case, change)
        if code == "decision_conflict":
            assert str(tone.decision_id) in refused.detail
            assert str(casual.decision_id) in refused.detail
    # A true alternative is not blocked by the changed premise of another one.
    apply_operation(root, _issue_request(case, "true_other"), owner)
    assert read_work_status(root, works["true_other"], owner).status == "ready"

    # Lifting the conflict leaves the changed premise as the only blocking reason.
    _revoke(case, casual)
    apply_operation(root, _issue_request(case, "any_conflict"), owner)
    _addressed(
        _refused(case, "premise_changed", _issue_request(case, "all_conflict")), case, change
    )

    # The recheck lifts it; really waiting, closed and stale members keep their codes.
    apply_operation(root, _recheck_request(case, (change,)), owner)
    for role in ("closed_other", "waiting_other", "nested_all", "nested_any", "all_conflict"):
        apply_operation(root, _issue_request(case, role), owner)
        assert read_work_status(root, works[role], owner).status == "ready"
    apply_operation(root, _issue_request(case, "stale_changed"), owner)
    for role, code in (
        ("behind_open", "dependency_open"),
        ("behind_closed", "dependency_closed"),
        ("stale_closed", "dependency_open"),
        ("stale_first", "stale_basis"),
        ("stale_then_changed", "stale_basis"),
    ):
        _refused(case, code, _issue_request(case, role))
    assert read_work_status(root, works["behind_open"], owner).reasons == (waiting,)
    assert read_work(root, parent, owner).state.status == "proposed"
