"""Exact reply recovery leaves execution history truthful and services its dependencies."""

from pathlib import Path
from uuid import UUID, uuid4, uuid5

import pytest

import zaratustra.foundation as core
from tests.zaratustra.pi_adapter.test_response_recovery import _assign, _capture, _target


def _saved(
    tmp_path: Path, raw: str = "Broken JSON: данные"
) -> tuple[Path, UUID, core.LocalAuthority, UUID, core.RecoverAttemptOutputRequest]:
    case, _, work, _, _ = _target(tmp_path, "setup")
    attempt, session = _assign(case, work)
    source, invocation = _capture(case, work, attempt, session, raw, "setup_json")
    root, space, owner, *_ = case
    view = core.read_attempt_response(root, work, owner)
    assert view.outcome == "recoverable"
    request = core.RecoverAttemptOutputRequest(
        operation_id=uuid5(invocation, "recover-output:report"),
        space_id=space,
        actor=owner.actor,
        work_id=work,
        expected_work_revision=view.work_revision,
        attempt_id=attempt,
        session_id=session,
        slot="report",
        assistant_source=source,
        invocation_id=invocation,
    )
    return root, space, owner, work, request


@pytest.mark.parametrize("raw", ["Broken JSON: данные", "", " \n "])
def test_exact_recovery_is_idempotent_without_success_or_publication(
    tmp_path: Path, raw: str
) -> None:
    root, _, owner, work, request = _saved(tmp_path, raw)
    before = core.read_execution(root, work, owner)
    receipt = core.apply_operation(root, request, owner)
    assert core.apply_operation(root, request, owner) == receipt
    view = core.read_attempt_response(root, work, owner)
    assert view.outcome == "applied" and view.artifact is not None
    artifact = core.read_artifact(root, view.artifact.artifact_id, owner)
    assert artifact.content == raw.encode("utf-8")
    assert artifact.provenance == ()
    proof = core.read_artifact_recovery_proof(root, view.artifact, owner)
    assert proof is not None and proof.assistant_source == request.assistant_source
    assert (
        proof.invocation_id == request.invocation_id and proof.operation_id == request.operation_id
    )
    after = core.read_execution(root, work, owner)
    assert after.attempts == before.attempts
    assert after.invocations == before.invocations
    assert after.work.state.status == "proposed" and after.work.state.acceptance is None
    events = core.read_execution_events(root, work, 0, owner)
    assert sum(event["kind"] == "recover_attempt_output" for event in events) == 1
    assert not any(event["kind"] == "publish_attempt_output" for event in events)
    conflicting = request.model_copy(
        update={
            "operation_id": uuid4(),
            "assistant_source": core.KnowledgeRef(record_id=uuid4(), revision=1),
        }
    )
    with pytest.raises(core.FoundationError):
        core.apply_operation(root, conflicting, owner)
    assert core.read_execution(root, work, owner) == after


def test_fresh_assignment_cannot_bypass_saved_answer(tmp_path: Path) -> None:
    root, space, owner, work, request = _saved(tmp_path)
    execution = core.read_execution(root, work, owner)
    before = core.read_space(root).state_revision
    with pytest.raises(core.FoundationError, match="response_pending"):
        core.apply_operation(
            root,
            core.AssignAttemptRequest(
                operation_id=uuid4(),
                space_id=space,
                actor=owner.actor,
                work_id=work,
                attempt_id=uuid4(),
                expected_work_revision=execution.work.revision,
                resource_id=execution.resources[0].resource_id,
                expected_resource_revision=execution.resources[0].revision,
                session_id=uuid4(),
                executor_version="fictional",
                previous_attempt_id=request.attempt_id,
            ),
            owner,
        )
    assert core.read_space(root).state_revision == before
    assert core.read_execution(root, work, owner) == execution


def test_source_deletion_retires_recovered_copies_and_independent_artifact_survives(
    tmp_path: Path,
) -> None:
    root, space, owner, work, request = _saved(tmp_path)
    core.apply_operation(root, request, owner)
    view = core.read_attempt_response(root, work, owner)
    assert view.artifact is not None
    independent = uuid4()
    core.apply_operation(
        root,
        core.CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            artifact_id=independent,
            content=b"Independent observation",
            media_type="text/plain",
        ),
        owner,
    )
    core.apply_operation(
        root,
        core.DeleteKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            record_id=request.assistant_source.record_id,
            expected_revision=request.assistant_source.revision,
        ),
        owner,
    )
    with pytest.raises(core.FoundationError, match="content_unavailable"):
        core.read_artifact(root, view.artifact.artifact_id, owner)
    with pytest.raises(core.FoundationError):
        core.apply_operation(root, request, owner)
    assert core.read_artifact(root, independent, owner).content == b"Independent observation"


def test_old_terminal_optional_protocol_does_not_change_canonical_bytes() -> None:
    terminal = core.ConversationTerminalObservation(
        invocation_id=uuid4(),
        manifest=core.KnowledgeRef(record_id=uuid4(), revision=1),
        assistant_entry_id="native-entry",
        native_outcome="completed",
        stop_reason="stop",
    )
    assert "result_protocol" not in terminal.model_dump(mode="json")
    assert (
        core.ConversationTerminalObservation.model_validate_json(terminal.model_dump_json())
        == terminal
    )


@pytest.mark.parametrize("outcome", ["sent", "unknown"])
def test_existing_output_cannot_mask_newer_unresolved_invocation(
    tmp_path: Path, outcome: str
) -> None:
    case, identifier, work, _, controller = _target(tmp_path, "setup")
    root, space, owner, *_ = case
    artifact = uuid4()
    core.apply_operation(
        root,
        core.CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            artifact_id=artifact,
            content=b"Earlier proposed output",
            media_type="text/plain",
        ),
        owner,
    )
    state = core.read_work(root, work, owner)
    core.apply_operation(
        root,
        core.LinkWorkOutputRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            work_id=work,
            expected_revision=state.revision,
            output=core.LinkedOutput(
                slot=state.state.expected_outputs[0].slot,
                artifact=core.ArtifactRef(artifact_id=artifact, revision=1),
            ),
        ),
        owner,
    )
    attempt, session = _assign(case, work)
    _capture(case, work, attempt, session, "New unresolved answer", "setup_json", outcome=outcome)
    before = core.read_space(root).state_revision
    view = core.read_attempt_response(root, work, owner)
    assert view.outcome == ("running" if outcome == "sent" else "unknown")
    with pytest.raises(core.FoundationError):
        controller._execute_stage(identifier, work)
    assert core.read_space(root).state_revision == before


def test_later_no_send_attempt_does_not_hide_earlier_saved_assigned_answer(tmp_path: Path) -> None:
    root, space, owner, work, request = _saved(tmp_path)
    execution = core.read_execution(root, work, owner)
    core.apply_operation(
        root,
        core.StartAttemptRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            work_id=work,
            expected_work_revision=execution.work.revision,
            resource_id=execution.resources[0].resource_id,
            expected_resource_revision=1,
            attempt_id=uuid4(),
            session_id=uuid4(),
            previous_attempt_id=request.attempt_id,
        ),
        owner,
    )
    view = core.read_attempt_response(root, work, owner)
    assert view.outcome == "attention"
    assert view.diagnostics[0].code == "previous_response_pending"
    assert view.invocation_id == request.invocation_id


def test_plain_link_is_a_proposed_output_but_does_not_authorize_repeated_dispatch(
    tmp_path: Path,
) -> None:
    root, space, owner, work, request = _saved(tmp_path)
    artifact = uuid4()
    core.apply_operation(
        root,
        core.CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            artifact_id=artifact,
            content=b"Explicitly provided alternative",
            media_type="text/plain",
        ),
        owner,
    )
    state = core.read_work(root, work, owner)
    core.apply_operation(
        root,
        core.LinkWorkOutputRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            work_id=work,
            expected_revision=state.revision,
            output=core.LinkedOutput(
                slot="report", artifact=core.ArtifactRef(artifact_id=artifact, revision=1)
            ),
        ),
        owner,
    )
    assert core.read_attempt_response(root, work, owner).outcome == "applied"
    # Public Core linking remains a valid proposed output. It cannot prove that
    # the older assigned response was consumed, or authorize generating it again.
    execution = core.read_execution(root, work, owner)
    before = core.read_space(root).state_revision
    with pytest.raises(core.FoundationError, match="response_pending"):
        core.apply_operation(
            root,
            core.AssignAttemptRequest(
                operation_id=uuid4(),
                space_id=space,
                actor=owner.actor,
                work_id=work,
                expected_work_revision=execution.work.revision,
                attempt_id=uuid4(),
                session_id=uuid4(),
                previous_attempt_id=request.attempt_id,
                executor_version="fictional",
                resource_id=execution.resources[0].resource_id,
                expected_resource_revision=1,
            ),
            owner,
        )
    assert core.read_space(root).state_revision == before


@pytest.mark.parametrize("fault", ["ambiguous", "resource"])
def test_recovery_refuses_changed_or_ambiguous_proof_without_effects(
    tmp_path: Path, fault: str
) -> None:
    root, space, owner, work, request = _saved(tmp_path)
    if fault == "resource":
        resource = core.read_execution(root, work, owner).resources[0]
        core.apply_operation(
            root,
            core.ReviseResourceRequest(
                operation_id=uuid4(),
                space_id=space,
                actor=owner.actor,
                resource_id=resource.resource_id,
                work_id=work,
                expected_revision=resource.revision,
                state=resource.state.model_copy(update={"status": "revoked"}),
            ),
            owner,
        )
    else:
        source = core.read_knowledge(root, request.assistant_source.record_id, owner).state
        assert isinstance(source, core.SourceState) and source.conversation_terminal is not None
        entry = str(uuid4())
        core.apply_operation(
            root,
            core.CreateKnowledgeRequest(
                operation_id=uuid4(),
                space_id=space,
                actor=owner.actor,
                record_id=uuid4(),
                state=source.model_copy(
                    update={
                        "source_event_id": f"{request.session_id}:{entry}",
                        "content": b"Conflicting retained original",
                        "conversation_terminal": source.conversation_terminal.model_copy(
                            update={"assistant_entry_id": entry}
                        ),
                    }
                ),
            ),
            owner,
        )
    before = core.read_execution(root, work, owner)
    revision = core.read_space(root).state_revision
    with pytest.raises(core.FoundationError):
        core.apply_operation(root, request, owner)
    assert core.read_execution(root, work, owner) == before
    assert core.read_space(root).state_revision == revision


def test_reply_protocol_must_match_the_pinned_stage_before_recovery(tmp_path: Path) -> None:
    case, _, work, _, _ = _target(tmp_path, "setup")
    attempt, session = _assign(case, work)
    source, invocation = _capture(case, work, attempt, session, "{}", "workflow_json")
    root, space, owner, *_ = case
    view = core.read_attempt_response(root, work, owner)
    assert view.outcome == "attention" and view.diagnostics[0].code == "response_protocol_changed"
    before = core.read_space(root).state_revision
    with pytest.raises(core.FoundationError, match="response_protocol_changed"):
        core.apply_operation(
            root,
            core.RecoverAttemptOutputRequest(
                operation_id=uuid4(),
                space_id=space,
                actor=owner.actor,
                work_id=work,
                expected_work_revision=view.work_revision,
                attempt_id=attempt,
                session_id=session,
                slot="report",
                assistant_source=source,
                invocation_id=invocation,
            ),
            owner,
        )
    assert core.read_space(root).state_revision == before


@pytest.mark.parametrize("linked", [False, True])
def test_older_unknown_send_fences_a_later_no_send_generation(tmp_path: Path, linked: bool) -> None:
    case, _, work, _, _ = _target(tmp_path, "setup")
    root, space, owner, *_ = case
    attempt, session = _assign(case, work)
    _, invocation = _capture(case, work, attempt, session, "", "setup_json", outcome="unknown")
    execution = core.read_execution(root, work, owner)
    if linked:
        artifact = uuid4()
        core.apply_operation(
            root,
            core.CreateArtifactRequest(
                operation_id=uuid4(),
                space_id=space,
                actor=owner.actor,
                artifact_id=artifact,
                content=b"Earlier output",
                media_type="text/plain",
            ),
            owner,
        )
        core.apply_operation(
            root,
            core.LinkWorkOutputRequest(
                operation_id=uuid4(),
                space_id=space,
                actor=owner.actor,
                work_id=work,
                expected_revision=execution.work.revision,
                output=core.LinkedOutput(
                    slot="report", artifact=core.ArtifactRef(artifact_id=artifact, revision=1)
                ),
            ),
            owner,
        )
    newer, newer_session = uuid4(), uuid4()
    current = core.read_work(root, work, owner)
    core.apply_operation(
        root,
        core.StartAttemptRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            work_id=work,
            expected_work_revision=current.revision,
            attempt_id=newer,
            resource_id=execution.resources[0].resource_id,
            expected_resource_revision=1,
            session_id=newer_session,
            previous_attempt_id=attempt,
        ),
        owner,
    )
    view = core.read_attempt_response(root, work, owner)
    assert view.outcome == "unknown" and view.invocation_id == invocation
    core.apply_operation(
        root,
        core.StopAttemptRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            work_id=work,
            attempt_id=newer,
            session_id=newer_session,
            outcome="interrupted",
            no_send_only=True,
        ),
        owner,
    )
    before = core.read_space(root).state_revision
    with pytest.raises(core.FoundationError, match="response_outcome_unknown"):
        core.apply_operation(
            root,
            core.AssignAttemptRequest(
                operation_id=uuid4(),
                space_id=space,
                actor=owner.actor,
                work_id=work,
                expected_work_revision=current.revision,
                attempt_id=uuid4(),
                session_id=uuid4(),
                executor_version="fictional",
                resource_id=execution.resources[0].resource_id,
                expected_resource_revision=1,
                previous_attempt_id=newer,
            ),
            owner,
        )
    assert core.read_space(root).state_revision == before


@pytest.mark.parametrize("already_recovered", [False, True])
def test_backup_restore_preserves_reply_history_and_never_regenerates_it(
    tmp_path: Path, already_recovered: bool
) -> None:
    root, space, owner, work, request = _saved(tmp_path)
    if already_recovered:
        core.apply_operation(root, request, owner)
    before = core.read_execution(root, work, owner)
    backup = core.create_backup(root, uuid4(), owner)
    restored = tmp_path / "restored"
    restored.mkdir()
    recovery = core.authorize_recovery(actor="owner", source_ref="fictional restore")
    core.restore_backup(backup.package, restored, recovery)
    core.apply_operation(
        restored,
        core.RecoverRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        recovery,
    )
    reopened = core.authorize_local(restored, actor="owner", source_ref="fictional reopened")
    after = core.read_execution(restored, work, reopened)
    assert after.attempts == before.attempts and after.invocations == before.invocations
    source = core.read_knowledge(restored, request.assistant_source.record_id, reopened)
    assert isinstance(source.state, core.SourceState) and source.state.content
    view = core.read_attempt_response(restored, work, reopened)
    if already_recovered:
        assert view.outcome == "applied" and view.artifact is not None
        assert (
            core.read_artifact(restored, view.artifact.artifact_id, reopened).content
            == source.state.content
        )
        proof = core.read_artifact_recovery_proof(restored, view.artifact, reopened)
        assert proof is not None and proof.invocation_id == request.invocation_id
    else:
        assert view.outcome == "attention" and view.diagnostics[0].code == "stale_response_basis"
        with pytest.raises(core.FoundationError):
            core.apply_operation(restored, request, reopened)
        assert core.read_execution(restored, work, reopened) == after
