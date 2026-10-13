"""Durable accounting pins use exact public context/execution evidence only."""

import sqlite3
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_activity_setup import Case, _case
from tests.zaratustra.foundation.test_conversations import _apply, _upgrade
from zaratustra import foundation as core


def _ordinary(case: Case, tmp_path: Path) -> tuple[UUID, UUID, UUID, UUID]:
    activity, work, resource, attempt, session = (uuid4() for _ in range(5))
    workdir = tmp_path / str(work)
    workdir.mkdir()
    _apply(
        case,
        core.CreateActivityRequest,
        activity_id=activity,
        state=core.ActivityState(title="Fictional audit", goal="Keep exact accounting"),
    )
    _apply(
        case,
        core.CreateWorkRequest,
        work_id=work,
        state=core.WorkState(
            activity_id=activity,
            goal="Ordinary work",
            expected_outputs=(core.OutputContract(slot="report", media_type="text/plain"),),
        ),
    )
    _apply(
        case,
        core.CreateResourceRequest,
        work_id=work,
        resource_id=resource,
        state=core.ResourceState(label="Fictional resource", root=workdir),
    )
    _apply(
        case,
        core.StartAttemptRequest,
        work_id=work,
        attempt_id=attempt,
        resource_id=resource,
        session_id=session,
        expected_work_revision=1,
        expected_resource_revision=1,
    )
    return work, resource, attempt, session


def _manifest(
    case: Case, work: UUID | None, attempt: UUID | None, session: UUID
) -> core.KnowledgeRef:
    ref = core.KnowledgeRef(record_id=uuid4(), revision=1)
    _apply(
        case,
        core.CreateKnowledgeRequest,
        record_id=ref.record_id,
        state=core.ContextState(
            purpose="Exact ordinary accounting",
            work_id=work,
            attempt_id=attempt,
            session_id=session,
            mandatory=(core.KnowledgeRef(record_id=work, revision=1),) if work else (),
        ),
    )
    return ref


def _delivery(
    case: Case, manifest: core.KnowledgeRef, *, sent: bool = True, invocation: UUID | None = None
) -> UUID:
    invocation = invocation or uuid4()
    _apply(
        case,
        core.RecordContextDeliveryRequest,
        invocation_id=invocation,
        manifest=manifest,
        stage="prepared",
    )
    if sent:
        _apply(
            case,
            core.RecordContextDeliveryRequest,
            invocation_id=invocation,
            manifest=manifest,
            stage="sent",
            request_sha256="A" * 64,
            request_bytes=3,
        )
    return invocation


def _stop(case: Case, work: UUID, attempt: UUID, session: UUID, *, guarded: bool = True) -> None:
    _apply(
        case,
        core.StopAttemptRequest,
        work_id=work,
        attempt_id=attempt,
        session_id=session,
        outcome="interrupted",
        no_send_only=guarded,
    )


def _execution(
    case: Case,
    work: UUID,
    attempt: UUID,
    session: UUID,
    invocation: UUID,
) -> core.PrepareInvocationRequest:
    request = core.PrepareInvocationRequest(
        operation_id=uuid4(),
        space_id=case[1],
        actor="owner",
        work_id=work,
        attempt_id=attempt,
        session_id=session,
        invocation_id=invocation,
        purpose="content",
        provider="fictional",
        model="fictional",
        transport="local",
        request_sha256="A" * 64,
        request_bytes=3,
        reserve_units=1,
    )
    core.apply_operation(case[0], request, case[2])
    return request


@pytest.mark.parametrize("first", ("knowledge", "execution"))
@pytest.mark.parametrize("context", ("matching", "other_attempt", "not_attempt"))
def test_both_registration_orders_require_the_same_exact_invocation_pin(
    tmp_path: Path,
    first: Literal["knowledge", "execution"],
    context: Literal["matching", "other_attempt", "not_attempt"],
) -> None:
    case = _case(tmp_path)
    _upgrade(case)
    core.upgrade_delivery_correlation_space(case[0], case[2])
    work, _, attempt, session = _ordinary(case, tmp_path)
    context_work, context_attempt, context_session = work, attempt, session
    if context == "other_attempt":
        context_work, _, context_attempt, context_session = _ordinary(case, tmp_path)
    manifest = _manifest(
        case, context_work, None if context == "not_attempt" else context_attempt, context_session
    )
    invocation = uuid4()
    execution_request = None
    if first == "knowledge":
        _delivery(case, manifest, sent=False, invocation=invocation)
    else:
        execution_request = _execution(case, work, attempt, session, invocation)
    before_space = core.read_space(case[0])
    before_execution = core.read_execution(case[0], work, case[2])
    if context == "matching":
        if first == "knowledge":
            execution_request = _execution(case, work, attempt, session, invocation)
        else:
            _delivery(case, manifest, sent=False, invocation=invocation)
        assert execution_request is not None
        receipt = core.apply_operation(case[0], execution_request, case[2])
        assert core.apply_operation(case[0], execution_request, case[2]) == receipt
        _apply(
            case,
            core.RecordContextDeliveryRequest,
            invocation_id=invocation,
            manifest=manifest,
            stage="sent",
            request_sha256="A" * 64,
            request_bytes=3,
        )
        delivery = core.read_context_delivery(case[0], invocation, case[2])
        assert delivery["stage"] == "sent" and delivery["context_attempt_id"] == str(attempt)
        assert len(core.read_execution(case[0], work, case[2]).invocations) == 1
    else:
        with pytest.raises(core.FoundationError, match="delivery_correlation_conflict"):
            if first == "knowledge":
                _execution(case, work, attempt, session, invocation)
            else:
                _delivery(case, manifest, sent=False, invocation=invocation)
        assert core.read_space(case[0]) == before_space
        assert core.read_execution(case[0], work, case[2]) == before_execution
        if first == "knowledge":
            assert core.read_context_delivery(case[0], invocation, case[2])["stage"] == "prepared"
        else:
            with pytest.raises(core.FoundationError, match="not_found"):
                core.read_context_delivery(case[0], invocation, case[2])
    assert core.read_work(case[0], work, case[2]).state.acceptance is None


def test_corrupt_execution_correlation_refuses_delivery_advance_without_mutation(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    _upgrade(case)
    core.upgrade_delivery_correlation_space(case[0], case[2])
    work, _, attempt, session = _ordinary(case, tmp_path)
    manifest = _manifest(case, work, attempt, session)
    invocation = _delivery(case, manifest, sent=False)
    _execution(case, work, attempt, session, invocation)
    wrong_session = str(uuid4())
    # Fault injection in a fictional fixture: corrupt one immutable accounting pin.
    # No accepted result or successful state is fabricated by this test.
    with sqlite3.connect(core.read_space(case[0]).database) as connection:
        connection.execute(
            "UPDATE execution_invocations SET session_id=? WHERE invocation_id=?",
            (wrong_session, str(invocation)),
        )
    before_space = core.read_space(case[0])
    before_delivery = core.read_context_delivery(case[0], invocation, case[2])
    before_execution = core.read_execution(case[0], work, case[2])
    with pytest.raises(core.FoundationError, match="delivery_correlation_conflict"):
        _apply(
            case,
            core.RecordContextDeliveryRequest,
            invocation_id=invocation,
            manifest=manifest,
            stage="sent",
            request_sha256="A" * 64,
            request_bytes=3,
        )
    assert core.read_space(case[0]) == before_space
    assert core.read_context_delivery(case[0], invocation, case[2]) == before_delivery
    assert core.read_execution(case[0], work, case[2]) == before_execution
    with sqlite3.connect(core.read_space(case[0]).database) as connection:
        assert connection.execute(
            "SELECT session_id FROM execution_invocations WHERE invocation_id=?", (str(invocation),)
        ).fetchone() == (wrong_session,)


@pytest.mark.parametrize("deleted", (False, True))
def test_upgrade_pins_exact_manifest_or_same_invocation_and_is_idempotent(
    tmp_path: Path,
    deleted: bool,
) -> None:
    case = _case(tmp_path)
    _upgrade(case)
    work, _, attempt, session = _ordinary(case, tmp_path)
    manifest = _manifest(case, work, attempt, session)
    original = core.read_knowledge(case[0], manifest.record_id, case[2], revision=1)
    invocation = _delivery(case, manifest)
    if deleted:
        _execution(case, work, attempt, session, invocation)
        _apply(case, core.DeleteKnowledgeRequest, record_id=manifest.record_id, expected_revision=1)
    info = core.upgrade_delivery_correlation_space(case[0], case[2])
    assert info.schema_version == 18
    assert core.upgrade_delivery_correlation_space(case[0], case[2]) == info
    delivery = core.read_context_delivery(case[0], invocation, case[2])
    assert (
        delivery["context_work_id"],
        delivery["context_attempt_id"],
        delivery["context_session_id"],
        delivery["correlation_state"],
    ) == (str(work), str(attempt), str(session), "exact")
    assert (
        not core.read_execution(case[0], work, case[2])
        .attempts[-1]
        .legacy_delivery_correlation_uncertain
    )
    with pytest.raises(core.FoundationError, match="attempt_send_observed"):
        _stop(case, work, attempt, session)
    if not deleted:
        assert core.read_knowledge(case[0], manifest.record_id, case[2], revision=1) == original
    assert "legacy_delivery_correlation_uncertain" not in core.read_execution(
        case[0], work, case[2]
    ).attempts[-1].model_dump(mode="json")


def test_not_attempt_delivery_never_blocks_an_unrelated_attempt(tmp_path: Path) -> None:
    case = _case(tmp_path)
    _upgrade(case)
    work, _, attempt, session = _ordinary(case, tmp_path)
    manifest = _manifest(case, work, None, session)
    invocation = _delivery(case, manifest)
    core.upgrade_delivery_correlation_space(case[0], case[2])
    pin = core.read_context_delivery(case[0], invocation, case[2])
    assert pin["correlation_state"] == "not_attempt" and pin["context_attempt_id"] is None
    _stop(case, work, attempt, session)
    assert core.read_execution(case[0], work, case[2]).attempts[-1].status == "interrupted"


def test_unresolved_legacy_marks_only_then_active_attempts_and_manual_stop_remains_available(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    _upgrade(case)
    work, _, attempt, session = _ordinary(case, tmp_path)
    manifest = _manifest(case, work, attempt, session)
    invocation = _delivery(case, manifest)
    _apply(case, core.DeleteKnowledgeRequest, record_id=manifest.record_id, expected_revision=1)
    core.upgrade_delivery_correlation_space(case[0], case[2])
    pin = core.read_context_delivery(case[0], invocation, case[2])
    assert (
        pin["correlation_state"],
        pin["context_work_id"],
        pin["context_attempt_id"],
        pin["context_session_id"],
    ) == ("unresolved_legacy", None, None, None)
    before = core.read_execution(case[0], work, case[2])
    assert before.attempts[-1].legacy_delivery_correlation_uncertain
    with pytest.raises(core.FoundationError, match=f"uncorrelated_delivery_history.*{attempt}"):
        _stop(case, work, attempt, session)
    assert core.read_execution(case[0], work, case[2]) == before
    _stop(case, work, attempt, session, guarded=False)
    new_work, _, new_attempt, new_session = _ordinary(case, tmp_path)
    assert (
        not core.read_execution(case[0], new_work, case[2])
        .attempts[-1]
        .legacy_delivery_correlation_uncertain
    )
    _stop(case, new_work, new_attempt, new_session)


@pytest.mark.parametrize("conflict", ("work", "attempt", "session"))
def test_contradictory_exact_evidence_aborts_upgrade_and_all_ddl_atomically(
    tmp_path: Path,
    conflict: Literal["work", "attempt", "session"],
) -> None:
    case = _case(tmp_path)
    _upgrade(case)
    work, _, attempt, session = _ordinary(case, tmp_path)
    context_work, context_attempt, context_session = work, attempt, session
    if conflict == "session":
        context_session = uuid4()
    else:
        other_work, _, other_attempt, _ = _ordinary(case, tmp_path)
        if conflict == "work":
            context_work = other_work
        else:
            context_attempt = other_attempt
    manifest = _manifest(case, context_work, context_attempt, context_session)
    invocation = _delivery(case, manifest)
    _execution(case, work, attempt, session, invocation)
    before = core.read_space(case[0])
    delivery = core.read_context_delivery(case[0], invocation, case[2])
    with pytest.raises(core.FoundationError, match="delivery_correlation_conflict"):
        core.upgrade_delivery_correlation_space(case[0], case[2])
    assert core.read_space(case[0]) == before and before.schema_version == 17
    assert core.read_context_delivery(case[0], invocation, case[2]) == delivery
    with pytest.raises(core.FoundationError, match="upgrade_required.*18"):
        _stop(case, work, attempt, session)
    _stop(case, work, attempt, session, guarded=False)


def test_new_delivery_validates_exact_attempt_and_keeps_pin_through_stages_and_deletion(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    _upgrade(case)
    core.upgrade_delivery_correlation_space(case[0], case[2])
    work, _, attempt, session = _ordinary(case, tmp_path)
    wrong_manifest = _manifest(case, work, attempt, uuid4())
    invocation = uuid4()
    before = core.read_space(case[0])
    with pytest.raises(core.FoundationError, match="invalid_delivery_correlation"):
        _delivery(case, wrong_manifest, invocation=invocation)
    assert core.read_space(case[0]) == before
    with pytest.raises(core.FoundationError, match="not_found"):
        core.read_context_delivery(case[0], invocation, case[2])
    manifest = _manifest(case, work, attempt, session)
    _delivery(case, manifest, invocation=invocation)
    pin = core.read_context_delivery(case[0], invocation, case[2])
    request = core.RecordContextDeliveryRequest(
        operation_id=uuid4(),
        space_id=case[1],
        actor="owner",
        invocation_id=invocation,
        manifest=manifest,
        stage="answered",
        usage_units=0,
    )
    receipt = core.apply_operation(case[0], request, case[2])
    assert core.apply_operation(case[0], request, case[2]) == receipt
    answered = core.read_context_delivery(case[0], invocation, case[2])
    for field in (
        "context_work_id",
        "context_attempt_id",
        "context_session_id",
        "correlation_state",
    ):
        assert answered[field] == pin[field]
    _apply(case, core.DeleteKnowledgeRequest, record_id=manifest.record_id, expected_revision=1)
    deleted = core.read_context_delivery(case[0], invocation, case[2])
    assert deleted["stage"] == "unknown"
    for field in (
        "context_work_id",
        "context_attempt_id",
        "context_session_id",
        "correlation_state",
    ):
        assert deleted[field] == pin[field]
    with pytest.raises(core.FoundationError, match="attempt_send_observed"):
        _stop(case, work, attempt, session)


def test_backup_restores_schema18_pins_and_uncertainty_without_new_epoch_completion(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    _upgrade(case)
    work, _, attempt, session = _ordinary(case, tmp_path)
    manifest = _manifest(case, work, attempt, session)
    invocation = _delivery(case, manifest)
    _apply(case, core.DeleteKnowledgeRequest, record_id=manifest.record_id, expected_revision=1)
    core.upgrade_delivery_correlation_space(case[0], case[2])
    before = core.read_context_delivery(case[0], invocation, case[2])
    backup = core.create_backup(case[0], uuid4(), case[2])
    assert backup.manifest.schema_version == 18
    restored = tmp_path / "restored"
    restored.mkdir()
    recovery = core.authorize_recovery(actor="owner", source_ref="fictional recovery")
    core.restore_backup(backup.package, restored, recovery)
    core.apply_operation(
        restored,
        core.RecoverRequest(
            operation_id=uuid4(),
            space_id=case[1],
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        recovery,
    )
    authority = core.authorize_local(restored, actor="owner", source_ref="fictional reopened")
    assert core.read_space(restored).schema_version == 18
    assert core.read_context_delivery(restored, invocation, authority) == before
    restored_attempt = core.read_execution(restored, work, authority).attempts[-1]
    assert restored_attempt.legacy_delivery_correlation_uncertain
    assert restored_attempt.execution_epoch < authority.execution_epoch
    with pytest.raises(core.FoundationError, match="stale_epoch|stale_attempt"):
        core.apply_operation(
            restored,
            core.StopAttemptRequest(
                operation_id=uuid4(),
                space_id=case[1],
                actor="owner",
                work_id=work,
                attempt_id=attempt,
                session_id=session,
                outcome="interrupted",
                no_send_only=True,
            ),
            authority,
        )


@pytest.mark.parametrize("stage", ("prepared", "sent"))
def test_legacy_missing_attempt_uses_same_execution_pin_without_rewriting_context(
    tmp_path: Path,
    stage: Literal["prepared", "sent"],
) -> None:
    case = _case(tmp_path)
    _upgrade(case)
    work, _, attempt, session = _ordinary(case, tmp_path)
    manifest = _manifest(case, work, None, session)
    original = core.read_knowledge(case[0], manifest.record_id, case[2], revision=1)
    assert isinstance(original.state, core.ContextState)
    assert original.state.attempt_id is None
    original_receipt = core.read_receipt(case[0], original.operation_id, case[2])
    invocation = _delivery(case, manifest, sent=stage == "sent")
    _execution(case, work, attempt, session, invocation)
    core.upgrade_delivery_correlation_space(case[0], case[2])
    migrated = core.read_context_delivery(case[0], invocation, case[2])
    assert (
        migrated["context_work_id"],
        migrated["context_attempt_id"],
        migrated["context_session_id"],
        migrated["correlation_state"],
    ) == (str(work), str(attempt), str(session), "exact")
    assert core.read_knowledge(case[0], manifest.record_id, case[2], revision=1) == original
    assert core.read_receipt(case[0], original.operation_id, case[2]) == original_receipt
    if stage == "prepared":
        _apply(
            case,
            core.RecordContextDeliveryRequest,
            invocation_id=invocation,
            manifest=manifest,
            stage="sent",
            request_sha256="A" * 64,
            request_bytes=3,
        )
    _apply(
        case,
        core.RecordContextDeliveryRequest,
        invocation_id=invocation,
        manifest=manifest,
        stage="answered",
        usage_units=0,
    )
    answered = core.read_context_delivery(case[0], invocation, case[2])
    assert answered["stage"] == "answered" and answered["context_attempt_id"] == str(attempt)
    _apply(case, core.DeleteKnowledgeRequest, record_id=manifest.record_id, expected_revision=1)
    deleted = core.read_context_delivery(case[0], invocation, case[2])
    assert deleted["stage"] == "unknown" and deleted["context_attempt_id"] == str(attempt)
    backup = core.create_backup(case[0], uuid4(), case[2])
    restored = tmp_path / "legacy-restored"
    restored.mkdir()
    recovery = core.authorize_recovery(actor="owner", source_ref="fictional compatibility restore")
    core.restore_backup(backup.package, restored, recovery)
    core.apply_operation(
        restored,
        core.RecoverRequest(
            operation_id=uuid4(),
            space_id=case[1],
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        recovery,
    )
    authority = core.authorize_local(restored, actor="owner", source_ref="fictional compatibility")
    assert core.read_context_delivery(restored, invocation, authority) == deleted
    assert (
        not core.read_execution(restored, work, authority)
        .attempts[-1]
        .legacy_delivery_correlation_uncertain
    )
