"""An obligation is waived only by an exact addressed exception, never by a Grant.

Part 3.4 of Stage 6 pass 3, model-free through public Core operations.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from tests.zaratustra.foundation.test_applicability import (
    ART,
    Case,
    Space,
    _accept_request,
    _activity_scope,
    _child,
    _choose,
    _confirm,
    _confirm_request,
    _definition,
    _issue,
    _issue_request,
    _link_request,
    _method,
    _refused,
    _resolve,
    _revise_choice,
    _revoke,
    _space,
    _statuses,
    _statuses_in_new_process,
    _stored_payload,
    _work_scope,
)
from tests.zaratustra.foundation.test_composition import _apply, _result, _sqlite_contains
from zaratustra.foundation import (
    Action,
    ArtifactRef,
    AuditReference,
    CloseWorkRequest,
    CreateArtifactRequest,
    CreateCompositeWorkRequest,
    CreateDecisionRequest,
    CreateGrantRequest,
    DecisionRef,
    DecisionState,
    DeleteWorkRequest,
    DomainRequest,
    ExceptionState,
    FoundationError,
    GrantState,
    MethodRef,
    NamedInput,
    ObligationProgress,
    ObligationTarget,
    PlanChild,
    PlanCondition,
    PlanOutputBinding,
    RecoverRequest,
    ReviseDecisionRequest,
    StatusReason,
    WaivedObligation,
    WaiveObligationRequest,
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
    read_space,
    read_work,
    read_work_plan,
    read_work_status,
    restore_backup,
)


def _case(setup: Space, *, extra: tuple[PlanChild, ...] = ()) -> Case:
    """A needs no predecessor and B needs no A, so a failed A leaves B's path open."""

    activity, source = setup.activity, setup.source
    request = CreateCompositeWorkRequest(
        operation_id=uuid4(),
        space_id=setup.space,
        actor="owner",
        work_id=uuid4(),
        state=WorkState(
            activity_id=activity,
            goal="Prepare the synthetic packet",
            inputs=(source,),
            expected_outputs=_definition().named_outputs,
            method=_method(setup),
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
                _child(activity, "b", "final"),
                _child(activity, "art", "reviewed"),
                *extra,
            ),
            completion=PlanCondition(kind="work_succeeded", role="b"),
            basis=(source,),
            rationale="Synthetic plan whose check may be waived",
            source_ref="fictional-owner-plan",
        ),
    )
    apply_operation(setup.root, request, setup.owner)
    return Case(
        setup.root,
        setup.space,
        setup.owner,
        activity,
        request.work_id,
        {child.role: child.work_id for child in request.plan.children},
    )


def _root_rule(case: Case | Space) -> UUID:
    """The bootstrap access rule, selected by its variant rather than by listing order."""

    return next(
        item.record_id
        for item in inspect_space(case.root, case.owner).records
        if item.kind == "decision"
        and isinstance(read_decision(case.root, item.record_id, case.owner).state, DecisionState)
    )


def _pinned(case: Case) -> MethodRef:
    method = read_work(case.root, case.parent, case.owner).state.method
    assert isinstance(method, MethodRef)
    return method


def _except(
    case: Case,
    key: str = "checked",
    *,
    work: UUID | None = None,
    methods: tuple[MethodRef, ...] | None = None,
    statement: str = "Synthetic exception: the check may be skipped for this packet",
) -> DecisionRef:
    decision = uuid4()
    _apply(
        case.root,
        case.space,
        case.owner,
        CreateDecisionRequest,
        decision_id=decision,
        state=ExceptionState(
            statement=statement,
            target=ObligationTarget(work_id=work or case.parent, key=key),
            methods=methods or (_pinned(case),),
        ),
    )
    return DecisionRef(decision_id=decision, revision=1)


def _revise_exception(
    case: Case, exception: DecisionRef, *, status: Literal["active", "revoked"] = "active"
) -> DecisionRef:
    current = read_decision(case.root, exception.decision_id, case.owner)
    assert isinstance(current.state, ExceptionState) and current.revision == exception.revision
    _apply(
        case.root,
        case.space,
        case.owner,
        ReviseDecisionRequest,
        decision_id=exception.decision_id,
        expected_revision=exception.revision,
        state=current.state.model_copy(
            update={"statement": f"{current.state.statement} (revised)", "status": status}
        ),
    )
    return DecisionRef(decision_id=exception.decision_id, revision=exception.revision + 1)


def _waive_request(
    case: Case,
    exception: DecisionRef,
    *,
    key: str = "checked",
    basis: str = "Synthetic waiver of the check",
    obligation_revision: int | None = None,
) -> WaiveObligationRequest:
    return WaiveObligationRequest(
        operation_id=uuid4(),
        space_id=case.space,
        actor="owner",
        work_id=case.parent,
        key=key,
        expected_plan_revision=read_work_plan(case.root, case.parent, case.owner).revision,
        expected_obligation_revision=obligation_revision
        or read_obligation(case.root, case.parent, key, case.owner).revision,
        exception=exception,
        basis=basis,
    )


def _fail(case: Case, role: str) -> None:
    apply_operation(
        case.root,
        CloseWorkRequest(
            operation_id=uuid4(),
            space_id=case.space,
            actor="owner",
            work_id=case.works[role],
            expected_revision=read_work(case.root, case.works[role], case.owner).revision,
            outcome="failed",
            basis=f"Synthetic {role} could not be done",
        ),
        case.owner,
    )


def _finish_b(case: Case) -> ArtifactRef:
    """Run B, confirm its obligation and link its exact result to the parent."""

    _issue(case, "b")
    summary = _result(
        case.root, case.space, case.owner, case.works["b"], "final", b"synthetic summary"
    )
    _confirm(case, "final", summary)
    apply_operation(case.root, _link_request(case, summary), case.owner)
    return summary


def _progress(case: Case) -> dict[str, ObligationProgress]:
    composition = read_execution(case.root, case.parent, case.owner).composition
    assert composition is not None
    return {item.key: item for item in composition.obligations}


def _waived(exception: DecisionRef, key: str = "checked") -> StatusReason:
    return StatusReason(
        code="waived", key=key, record_id=exception.decision_id, revision=exception.revision
    )


def _stored_work(case: Case, work: UUID, revision: int) -> bytes:
    with closing(sqlite3.connect(case.root / ".zara-core" / "core.sqlite3")) as connection:
        row = connection.execute(
            "SELECT payload FROM subject_content WHERE record_id = ? AND revision = ?",
            (str(work), revision),
        ).fetchone()
    assert row is not None
    return bytes(row[0])


def test_exact_exception_waives_a_failed_branch_and_acceptance_names_it(tmp_path: Path) -> None:
    setup = _space(tmp_path)
    after_a = PlanCondition(
        kind="accepted_output", role="a", slot="checked", media_type="text/plain"
    )
    case = _case(setup, extra=(_child(setup.activity, "d", "note", readiness=after_a),))
    root, _space_id, owner, _activity, parent, works = case
    _fail(case, "a")
    summary = _finish_b(case)
    _resolve(case, _choose(case, "not_required", _work_scope(case)))
    # The failed branch can never satisfy its requirement: acceptance names it.
    refused = _refused(case, "dependency_closed", _accept_request(case))
    assert str(works["a"]) in refused.detail

    exception = _except(case)
    marker = f"Synthetic waiver basis {uuid4()}"
    request = _waive_request(case, exception, basis=marker)
    receipt = apply_operation(root, request, owner)
    assert receipt.result == {
        "work_id": str(parent),
        "key": "checked",
        "revision": 2,
        "status": "waived",
        "exception": {"decision_id": str(exception.decision_id), "revision": 1},
    }
    assert marker not in json.dumps(receipt.model_dump(mode="json"))
    assert apply_operation(root, request, owner) == receipt
    _refused(case, "stale_obligation", request.model_copy(update={"operation_id": uuid4()}))
    _refused(case, "stale_obligation", _confirm_request(case, "checked", summary))
    # A waiver is not a result: a dependency on the role's output stays closed.
    closed = _refused(case, "dependency_closed", _issue_request(case, "d"))
    assert str(works["a"]) in closed.detail
    assert read_work_status(root, works["d"], owner).reasons == (
        StatusReason(code="dependency_closed", role="a", record_id=works["a"]),
    )
    audit = read_operation_audit(root, receipt.operation_id, owner)
    assert AuditReference(record_id=exception.decision_id, revision=1) in audit.target_refs

    # Kept apart from satisfied: the exact exception address and no evidence.
    waived = read_obligation(root, parent, "checked", owner)
    assert (waived.revision, waived.status, waived.evidence) == (2, "waived", None)
    assert (waived.exception, waived.basis) == (exception, marker)
    assert read_obligation(root, parent, "checked", owner, revision=1).status == "open"
    assert b'"exception"' not in _stored_payload(case, "final", 2)
    progress = _progress(case)
    assert (progress["checked"].status, progress["checked"].exception) == ("waived", exception)
    assert (progress["final"].status, progress["final"].exception) == ("satisfied", None)
    pending = read_work_status(root, parent, owner)
    assert pending.status == "ready"
    assert pending.reasons == (
        StatusReason(code="acceptance_pending", record_id=parent),
        _waived(exception),
        StatusReason(code="branch_review", role="a", record_id=works["a"]),
    )
    everything = {"parent": parent, **works}
    assert _statuses_in_new_process(case, everything) == _statuses(case, everything)

    accepted = apply_operation(root, _accept_request(case), owner)
    listed = [
        {"key": "checked", "exception": {"decision_id": str(exception.decision_id), "revision": 1}}
    ]
    assert accepted.result["waived"] == listed
    work = read_work(root, parent, owner)
    assert work.state.status == "succeeded" and work.state.acceptance is not None
    assert work.state.acceptance.waived == (WaivedObligation(key="checked", exception=exception),)
    done = read_work_status(root, parent, owner)
    assert (done.status, done.reasons) == ("succeeded", (_waived(exception),))
    assert _progress(case)["checked"].status == "waived"
    assert _statuses_in_new_process(case, everything) == _statuses(case, everything)
    # An acceptance without waivers keeps its earlier canonical form.
    b_revision = read_work(root, works["b"], owner).revision
    assert b'"waived"' not in _stored_work(case, works["b"], b_revision)
    assert b'"waived"' in _stored_work(case, parent, work.revision)


def test_waiver_refusals_name_the_reason_and_write_nothing(tmp_path: Path) -> None:
    setup = _space(tmp_path)
    case = _case(setup)
    root, space, owner, _activity, parent, works = case
    _fail(case, "a")
    # A broad Grant and any other Decision variant never replace an addressed exception.
    root_rule = _root_rule(case)
    choice = _choose(case, "required", _activity_scope(case), name="tone_review")
    other_key = _except(case, "final")
    other_work = _except(case, work=setup.seeded)
    other_version = _except(case, methods=(_pinned(case).model_copy(update={"version": 2}),))
    revoked = _except(case)
    exact = _except(case)
    refusals: tuple[tuple[str, DomainRequest], ...] = (
        (
            "exception_required",
            _waive_request(case, DecisionRef(decision_id=root_rule, revision=1)),
        ),
        ("exception_required", _waive_request(case, choice)),
        ("exception_mismatch", _waive_request(case, other_key)),
        ("exception_mismatch", _waive_request(case, other_work)),
        ("exception_mismatch", _waive_request(case, other_version)),
        ("stale_basis", _waive_request(case, _revise_exception(case, revoked, status="revoked"))),
        ("stale_basis", _waive_request(case, revoked)),
        ("not_found", _waive_request(case, DecisionRef(decision_id=exact.decision_id, revision=7))),
        ("not_found", _waive_request(case, exact, key="missing", obligation_revision=1)),
        ("stale_obligation", _waive_request(case, exact, obligation_revision=2)),
        (
            "stale_plan",
            _waive_request(case, exact).model_copy(update={"expected_plan_revision": 2}),
        ),
    )
    for code, request in refusals:
        _refused(case, code, request)

    # The instance state decides first: an unresolved or inactive requirement is not due.
    art_exception = _except(case, ART)
    _refused(case, "obligation_unresolved", _waive_request(case, art_exception, key=ART))
    _resolve(case, _choose(case, "not_required", _work_scope(case)))
    _refused(case, "obligation_inactive", _waive_request(case, art_exception, key=ART))

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
        request = _waive_request(case, exact).model_copy(update={"actor": grantee})
        before = read_space(root)
        with pytest.raises(FoundationError, match="permission_denied"):
            apply_operation(root, request, actor)
        assert read_space(root) == before
    assert read_obligation(root, parent, "checked", owner).revision == 1
    assert apply_operation(root, _waive_request(case, exact), owner).result["status"] == "waived"
    assert read_work(root, works["a"], owner).state.status == "failed"


def test_revoked_exception_reads_waiver_stale_until_confirmed(tmp_path: Path) -> None:
    case = _case(_space(tmp_path))
    root, space, owner, _activity, parent, works = case
    _resolve(case, _choose(case, "not_required", _work_scope(case)))
    _issue(case, "a")
    check = _result(root, space, owner, works["a"], "checked", b"synthetic late check")
    exception = _except(case)
    apply_operation(root, _waive_request(case, exception), owner)
    _finish_b(case)
    assert read_work_status(root, parent, owner).reasons == (
        StatusReason(code="acceptance_pending", record_id=parent),
        _waived(exception),
    )

    revoked = _revise_exception(case, exception, status="revoked")
    assert revoked.revision == 2
    # The recorded waiver is not rewritten; it reads stale and acceptance refuses.
    assert read_obligation(root, parent, "checked", owner).status == "waived"
    assert _progress(case)["checked"].status == "waiver_stale"
    stale = read_work_status(root, parent, owner)
    assert stale.status == "ready"
    assert stale.reasons == (
        StatusReason(code="issue_pending", role="art", record_id=works["art"]),
        StatusReason(code="confirmation_pending", role="a", record_id=parent),
        StatusReason(
            code="waiver_stale", key="checked", record_id=exception.decision_id, revision=1
        ),
    )
    refused = _refused(case, "stale_basis", _accept_request(case))
    assert "checked" in refused.detail
    _refused(case, "stale_basis", _waive_request(case, revoked))

    # The exact accepted result restores the path; the waiver is not kept beside it.
    _confirm(case, "checked", check)
    confirmed = read_obligation(root, parent, "checked", owner)
    assert (confirmed.revision, confirmed.status, confirmed.evidence) == (3, "satisfied", check)
    assert confirmed.exception is None
    assert read_obligation(root, parent, "checked", owner, revision=2).exception == exception
    accepted = apply_operation(root, _accept_request(case), owner)
    assert "waived" not in accepted.result
    assert read_work_status(root, parent, owner).reasons == ()


def test_revised_or_revoked_exception_needs_a_new_waiver(tmp_path: Path) -> None:
    case = _case(_space(tmp_path))
    root, _space_id, owner, _activity, _parent, _works = case
    _resolve(case, _choose(case, "not_required", _work_scope(case)))
    _fail(case, "a")
    exception = _except(case)
    apply_operation(root, _waive_request(case, exception), owner)
    _finish_b(case)
    revised = _revise_exception(case, exception)
    assert _progress(case)["checked"].status == "waiver_stale"
    _refused(case, "stale_basis", _accept_request(case))
    # The next revision waives it again by the exact current exception revision.
    receipt = apply_operation(root, _waive_request(case, revised), owner)
    assert receipt.result["revision"] == 3
    assert _progress(case)["checked"].status == "waived"

    # After revocation only another exception, waived anew, restores the path.
    _revise_exception(case, revised, status="revoked")
    assert _progress(case)["checked"].status == "waiver_stale"
    _refused(case, "stale_basis", _accept_request(case))
    replacement = _except(case, statement="Synthetic replacement exception for the check")
    assert apply_operation(root, _waive_request(case, replacement), owner).result["revision"] == 4
    accepted = apply_operation(root, _accept_request(case), owner)
    assert accepted.result["waived"] == [
        {
            "key": "checked",
            "exception": {"decision_id": str(replacement.decision_id), "revision": 1},
        }
    ]


def test_waiver_recomputes_applicable_choices_in_its_transaction(tmp_path: Path) -> None:
    case = _case(_space(tmp_path))
    root, _space_id, owner, _activity, parent, _works = case
    local = _choose(case, "required", _work_scope(case))
    _resolve(case, local)
    exception = _except(case, ART)
    general = _choose(case, "not_required", _activity_scope(case))
    refused = _refused(case, "decision_conflict", _waive_request(case, exception, key=ART))
    assert str(local.decision_id) in refused.detail
    assert str(general.decision_id) in refused.detail
    _revoke(case, general)
    # A revised referenced choice needs a new resolution before anything is waived.
    revised = _revise_choice(case, local)
    _refused(case, "stale_basis", _waive_request(case, exception, key=ART))
    _resolve(case, revised)
    receipt = apply_operation(root, _waive_request(case, exception, key=ART), owner)
    assert receipt.result["status"] == "waived"
    waived = read_obligation(root, parent, ART, owner)
    assert (waived.applicability, waived.choice, waived.exception) == ("active", revised, exception)


def test_exception_is_never_an_access_rule_and_keeps_its_target(tmp_path: Path) -> None:
    setup = _space(tmp_path)
    case = _case(setup)
    root, space, owner, _activity, parent, works = case
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
    exception = _except(case)
    assert audited_rules() == rules_before
    assert read_work(root, parent, reader) == readable
    stored = read_decision(root, exception.decision_id, owner)
    assert isinstance(stored.state, ExceptionState)
    assert stored.state.target == ObligationTarget(work_id=parent, key="checked")

    missing = CreateDecisionRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        decision_id=uuid4(),
        state=ExceptionState(
            statement="For nothing",
            target=ObligationTarget(work_id=uuid4(), key="checked"),
            methods=(_pinned(case),),
        ),
    )
    _refused(case, "not_found", missing)
    # A Grant without decision.write cannot write an exception, however it is meant.
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest,
        grant_id=uuid4(),
        state=GrantState(grantee="worker", actions=("work.accept", "method.use", "record.read")),
    )
    worker = authorize_local(root, actor="worker", source_ref="fictional-worker")
    by_worker = missing.model_copy(
        update={
            "operation_id": uuid4(),
            "actor": "worker",
            "state": missing.state.model_copy(
                update={"target": ObligationTarget(work_id=parent, key="checked")}
            ),
        }
    )
    before = read_space(root)
    with pytest.raises(FoundationError, match="permission_denied"):
        apply_operation(root, by_worker, worker)
    assert read_space(root) == before

    # An exception keeps its target and variant; its limits and reason may be revised.
    assert isinstance(stored.state, ExceptionState)
    changes: tuple[ExceptionState | DecisionState, ...] = (
        stored.state.model_copy(update={"target": ObligationTarget(work_id=parent, key="final")}),
        stored.state.model_copy(
            update={"target": ObligationTarget(work_id=works["a"], key="checked")}
        ),
        DecisionState(statement="Deny", effect="deny", actions=("record.read",)),
    )
    for state in changes:
        _refused(
            case,
            "invalid_request",
            ReviseDecisionRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                decision_id=exception.decision_id,
                expected_revision=1,
                state=state,
            ),
        )
    root_rule = _root_rule(case)
    _refused(
        case,
        "invalid_request",
        ReviseDecisionRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            decision_id=root_rule,
            expected_revision=1,
            state=stored.state,
        ),
    )
    seeded_method = read_work(root, setup.seeded, owner).state.method
    assert isinstance(seeded_method, MethodRef)
    wider = stored.state.model_copy(
        update={
            "methods": (*stored.state.methods, seeded_method),
            "statement": "Synthetic exception with a revised reason and wider limits",
        }
    )
    _apply(
        root,
        space,
        owner,
        ReviseDecisionRequest,
        decision_id=exception.decision_id,
        expected_revision=1,
        state=wider,
    )
    assert read_decision(root, exception.decision_id, owner, revision=1) == stored
    assert read_decision(root, exception.decision_id, owner).state == wider
    invalid_states: tuple[dict[str, object], ...] = (
        {"methods": []},
        {"methods": [stored.state.methods[0], stored.state.methods[0]]},
        {"target": {"work_id": str(parent), "key": "Not A Key"}},
    )
    for invalid in invalid_states:
        with pytest.raises(ValidationError):
            ExceptionState.model_validate(stored.state.model_dump(mode="json") | invalid)


def test_schema_6_refuses_exceptions_and_waivers(tmp_path: Path) -> None:
    setup = _space(tmp_path, schema=6)
    root, space, owner, _activity, _source, seeded = setup
    method = read_work(root, seeded, owner).state.method
    assert isinstance(method, MethodRef)
    root_rule = _root_rule(setup)
    exception = CreateDecisionRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        decision_id=uuid4(),
        state=ExceptionState(
            statement="Too early",
            target=ObligationTarget(work_id=seeded, key="checked"),
            methods=(method,),
        ),
    )
    refusing: tuple[DomainRequest, ...] = (
        exception,
        ReviseDecisionRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            decision_id=root_rule,
            expected_revision=1,
            state=exception.state,
        ),
        WaiveObligationRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=seeded,
            key="checked",
            expected_plan_revision=1,
            expected_obligation_revision=1,
            exception=DecisionRef(decision_id=root_rule, revision=1),
            basis="Too early",
        ),
    )
    for request in refusing:
        _refused(setup, "unsupported_schema", request)
    assert isinstance(read_decision(root, root_rule, owner).state, DecisionState)


def test_waiver_history_survives_restore_and_deletion_takes_the_waiver_off(
    tmp_path: Path,
) -> None:
    case = _case(_space(tmp_path))
    root, space, owner, _activity, parent, works = case
    # The review applies by an addressed choice; it is then waived as well.
    required = _choose(case, "required", _work_scope(case))
    _resolve(case, required)
    art_exception = _except(case, ART)
    art_marker = f"Synthetic art waiver basis {uuid4()}"
    apply_operation(root, _waive_request(case, art_exception, key=ART, basis=art_marker), owner)
    _fail(case, "a")
    exception = _except(case)
    marker = f"Synthetic waiver basis {uuid4()}"
    request = _waive_request(case, exception, basis=marker)
    apply_operation(root, request, owner)
    _finish_b(case)
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
    history = read_obligation(restored_root, parent, "checked", reopened, revision=2)
    assert (history.status, history.exception, history.basis) == ("waived", exception, marker)
    assert read_decision(restored_root, exception.decision_id, reopened) == read_decision(
        root, exception.decision_id, owner
    )
    assert read_work_status(restored_root, parent, reopened) == read_work_status(
        root, parent, owner
    )

    # Deleting the role's child takes the waiver off and removes its copied basis; the
    # independent obligation keeps its exact history.
    final_history = [
        read_obligation(root, parent, "final", owner, revision=revision) for revision in (1, 2)
    ]
    _apply(
        root,
        space,
        owner,
        DeleteWorkRequest,
        work_id=works["a"],
        expected_revision=read_work(root, works["a"], owner).revision,
    )
    reopened_instance = read_obligation(root, parent, "checked", owner)
    assert (
        reopened_instance.revision,
        reopened_instance.status,
        reopened_instance.exception,
        reopened_instance.basis,
    ) == (3, "open", None, None)
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_obligation(root, parent, "checked", owner, revision=2)
    with pytest.raises(FoundationError, match="history_unavailable"):
        apply_operation(root, request, owner)
    assert [
        read_obligation(root, parent, "final", owner, revision=revision) for revision in (1, 2)
    ] == final_history
    assert complete_deletions(root, owner).live_store_sanitized
    assert not backup.package.exists()
    assert not _sqlite_contains(root / ".zara-core", marker)
    checked = {"parent": parent}
    assert _statuses_in_new_process(case, checked) == _statuses(case, checked)

    # Deleting the art child takes that waiver off too; the addressed applicability stays.
    _apply(root, space, owner, DeleteWorkRequest, work_id=works["art"], expected_revision=1)
    art = read_obligation(root, parent, ART, owner)
    assert (art.revision, art.applicability, art.choice, art.status, art.exception) == (
        4,
        "active",
        required,
        "open",
        None,
    )
    assert complete_deletions(root, owner).live_store_sanitized
    assert not _sqlite_contains(root / ".zara-core", art_marker)
    _apply(
        root,
        space,
        owner,
        DeleteWorkRequest,
        work_id=works["b"],
        expected_revision=read_work(root, works["b"], owner).revision,
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
        read_obligation(root, parent, "checked", owner)
    fresh_backup = create_backup(root, uuid4(), owner).package
    for text in (marker, art_marker):
        assert not _sqlite_contains(fresh_backup, text)
        assert not _sqlite_contains(root / ".zara-core", text)
    # There is no Decision deletion operation: the exception stays an ordinary record.
    assert read_decision(root, exception.decision_id, owner).revision == 1
