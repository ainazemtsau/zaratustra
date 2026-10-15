"""Conversation evidence: actual Core setup/Work, delivery, recovery and sanitation."""

from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_activity_setup import (
    Case,
    _case,
    _complete,
    _draft,
    _review,
    _step,
)
from tests.zaratustra.foundation.test_child_execution import (
    _claim as _claim_assigned,
)
from tests.zaratustra.foundation.test_child_execution import (
    _invocation as _assigned_invocation,
)
from tests.zaratustra.foundation.test_child_execution import (
    _stop as _stop_assigned,
)
from zaratustra.foundation import (
    AcceptWorkRequest,
    ActivityState,
    AdmitInvocationRequest,
    ArtifactRef,
    AssignAttemptRequest,
    ContextState,
    ConversationActionView,
    ConversationDeliveryRequest,
    ConversationResponseProblem,
    ConversationTerminalObservation,
    CreateActivityRequest,
    CreateArtifactRequest,
    CreateDecisionRequest,
    CreateKnowledgeRequest,
    CreateResourceRequest,
    CreateWorkRequest,
    DecisionState,
    DeleteKnowledgeRequest,
    FinishInvocationRequest,
    FoundationError,
    IssueChildWorkRequest,
    KnowledgeRef,
    LinkedOutput,
    LinkWorkOutputRequest,
    MemoryMetadata,
    NativeSelectionObservation,
    OpenWaitRequest,
    OrdinarySelectionTransition,
    OutputContract,
    PrepareInvocationRequest,
    RecordContextDeliveryRequest,
    RecoverRequest,
    ResourceState,
    ReviseKnowledgeRequest,
    SelectionTarget,
    SendInvocationRequest,
    SourceState,
    StartAttemptRequest,
    StopAttemptRequest,
    WorkState,
    apply_operation,
    authorize_local,
    authorize_recovery,
    create_backup,
    list_conversation_actions,
    list_conversation_deliveries,
    read_activity_setup,
    read_conversation_action,
    read_conversation_actions_page,
    read_conversation_delivery,
    read_execution,
    read_knowledge,
    read_operation_audit,
    read_ordinary_final_proof,
    read_receipt,
    read_space,
    read_work,
    read_work_plan,
    restore_backup,
    upgrade_conversation_space,
    upgrade_delivery_correlation_space,
    upgrade_structures_space,
    upgrade_workflow_space,
    validate_conversation_answer,
)


def _upgrade(case: Case) -> None:
    for upgrade in (upgrade_structures_space, upgrade_workflow_space, upgrade_conversation_space):
        upgrade(case[0], case[2])


def _apply(case: Case, kind: type[Any], **fields: Any) -> Any:
    return apply_operation(
        case[0], kind(operation_id=uuid4(), space_id=case[1], actor="owner", **fields), case[2]
    )


def _question(tmp_path: Path) -> tuple[Case, Any]:
    case = _case(tmp_path)
    _step(case, "question", text="Which cadence do you prefer?")
    _upgrade(case)
    actions = list_conversation_actions(case[0], case[2], activity_id=case[4])
    action = next(item for item in actions if item.subject_id == case[3])
    assert action.kind == "question" and action.answer_target is not None
    assert action.answer_target.subject_id == case[3]
    return case, action


def _claim(case: Case, action: Any, *, host: str = "host-one") -> dict[str, Any]:
    fields = {
        "delivery_id": uuid4(),
        "action_ref": action.ref,
        "host_id": host,
        "session_id": uuid4(),
        "branch_id": "main",
    }
    receipt = _apply(case, ConversationDeliveryRequest, action="claim", **fields)
    assert receipt.result["status"] == "claimed"
    return fields


def _invocation(
    case: Case, action: Any, fields: dict[str, Any], stage: str = "prepared"
) -> tuple[KnowledgeRef, UUID]:
    identifier, invocation = uuid4(), uuid4()
    manifest = KnowledgeRef(record_id=identifier, revision=1)
    _apply(
        case,
        CreateKnowledgeRequest,
        record_id=identifier,
        state=ContextState(
            purpose="Explain the saved continuation",
            session_id=fields["session_id"],
            mandatory=action.bases,
            conversation_actions=(action.ref,),
        ),
    )
    _apply(
        case,
        RecordContextDeliveryRequest,
        invocation_id=invocation,
        manifest=manifest,
        stage="prepared",
    )
    _apply(
        case,
        ConversationDeliveryRequest,
        action="include",
        manifest=manifest,
        invocation_id=invocation,
        **fields,
    )
    if stage != "prepared":
        _apply(
            case,
            RecordContextDeliveryRequest,
            invocation_id=invocation,
            manifest=manifest,
            stage="sent",
            request_sha256="A" * 64,
            request_bytes=100,
        )
    if stage == "answered":
        _apply(
            case,
            RecordContextDeliveryRequest,
            invocation_id=invocation,
            manifest=manifest,
            stage="answered",
            usage_units=0,
        )
    return manifest, invocation


def _assistant(
    case: Case,
    fields: dict[str, Any],
    manifest: KnowledgeRef,
    *,
    final: bool,
    channel: Literal[
        "conversation_assistant", "document", "tool_result"
    ] = "conversation_assistant",
) -> KnowledgeRef:
    identifier = uuid4()
    _apply(
        case,
        CreateKnowledgeRequest,
        record_id=identifier,
        state=SourceState(
            channel=channel,
            connection="fictional-pi",
            profile_revision=1,
            sender="pi-assistant",
            conversation_id=str(fields["session_id"]),
            source_event_id=f"{fields['session_id']}:{'final-entry' if final else 'tool-entry'}",
            media_type="text/plain",
            capture="full",
            content=b"Here is the next useful step.",
            derived_from=(manifest,),
            conversation_final=final,
        ),
    )
    return KnowledgeRef(record_id=identifier, revision=1)


def test_schema_upgrade_preserves_old_payloads_and_ready_setup_first_work(tmp_path: Path) -> None:
    case = _case(tmp_path)
    _step(case, "start_stage", stage_kind="draft", stage_instruction="Prepare complete setup")
    draft = _complete(case, _draft(case))
    _step(case, "start_stage", stage_kind="review", stage_instruction="Review complete setup")
    _complete(case, _review(case, draft))
    _step(case, "finish")
    before = read_activity_setup(case[0], case[3], case[2])
    work_id = before.state.activated_works[0]
    work_before = read_work(case[0], work_id, case[2])
    _upgrade(case)
    assert read_space(case[0]).schema_version == 17
    assert read_activity_setup(case[0], case[3], case[2]) == before
    assert read_work(case[0], work_id, case[2]) == work_before
    actions = list_conversation_actions(case[0], case[2], activity_id=case[4])
    ready = next(item for item in actions if item.subject_id == case[3])
    assert ready.kind == "ready" and ready.work_id == work_id
    assert any(item.work_id == work_id and item.kind == "available_work" for item in actions)
    assert work_before.state.acceptance is None
    output = uuid4()
    _apply(
        case,
        CreateArtifactRequest,
        artifact_id=output,
        media_type="text/plain",
        content=b"First actual result",
    )
    child = read_work_plan(case[0], work_id, case[2]).plan.children[0].work_id
    _apply(
        case,
        IssueChildWorkRequest,
        parent_work_id=work_id,
        work_id=child,
        expected_plan_revision=1,
        expected_work_revision=1,
    )
    _apply(
        case,
        LinkWorkOutputRequest,
        work_id=child,
        expected_revision=read_work(case[0], child, case[2]).revision,
        output=LinkedOutput(slot="report", artifact=ArtifactRef(artifact_id=output, revision=1)),
    )
    _apply(
        case,
        AcceptWorkRequest,
        work_id=child,
        expected_revision=read_work(case[0], child, case[2]).revision,
        basis="Owner accepts this fictional child result",
    )
    # Publishing the composite result changes its Work revision, not the setup event.
    _apply(
        case,
        LinkWorkOutputRequest,
        work_id=work_id,
        expected_revision=read_work(case[0], work_id, case[2]).revision,
        output=LinkedOutput(slot="report", artifact=ArtifactRef(artifact_id=output, revision=1)),
    )
    after = read_conversation_action(case[0], ready.ref, case[2])
    assert after.ref == ready.ref and after.bases == ready.bases
    fields = _claim(case, after)
    manifest, _ = _invocation(case, after, fields)
    assert manifest.record_id != work_id
    assert read_work(case[0], work_id, case[2]).state.acceptance is None
    assert "conversation_actions" not in ContextState(
        purpose="Historical context", session_id=uuid4()
    ).model_dump(mode="json")
    assert "conversation_final" not in SourceState(
        channel="document",
        connection="fixture",
        profile_revision=1,
        capture="full",
        content=b"original",
        media_type="text/plain",
    ).model_dump(mode="json")


def test_one_global_claim_final_source_and_multiple_invocations(tmp_path: Path) -> None:
    case, action = _question(tmp_path)
    fields = _claim(case, action)
    with pytest.raises(FoundationError, match="conversation_delivery_claimed"):
        _claim(case, action, host="other-window")
    manifest, invocation = _invocation(case, action, fields, "answered")
    tool_source = _assistant(case, fields, manifest, final=False)
    with pytest.raises(FoundationError, match="invalid_conversation_response"):
        _apply(
            case,
            ConversationDeliveryRequest,
            action="respond",
            manifest=manifest,
            invocation_id=invocation,
            assistant_source=tool_source,
            assistant_entry_id="final-entry",
            **fields,
        )
    assert read_conversation_delivery(case[0], fields["delivery_id"], case[2]).status == "included"
    manifest, invocation = _invocation(case, action, fields, "answered")
    final_source = _assistant(case, fields, manifest, final=True)
    request = ConversationDeliveryRequest(
        operation_id=uuid4(),
        space_id=case[1],
        actor="owner",
        action="respond",
        manifest=manifest,
        invocation_id=invocation,
        assistant_source=final_source,
        assistant_entry_id="final-entry",
        **fields,
    )
    receipt = apply_operation(case[0], request, case[2])
    assert apply_operation(case[0], request, case[2]) == receipt
    assert read_conversation_delivery(case[0], fields["delivery_id"], case[2]).status == "responded"
    assert read_conversation_action(case[0], action.ref, case[2]) == action
    assert action in list_conversation_actions(case[0], case[2], activity_id=case[4])
    with pytest.raises(FoundationError, match="conversation_delivery_claimed"):
        _claim(case, action, host="new-session")


@pytest.mark.parametrize("channel", ("document", "tool_result"))
def test_delivery_final_proof_requires_assistant_channel(
    tmp_path: Path, channel: Literal["document", "tool_result"]
) -> None:
    case, action = _question(tmp_path)
    fields = _claim(case, action)
    manifest, invocation = _invocation(case, action, fields, "answered")
    original = _assistant(case, fields, manifest, final=True, channel=channel)
    with pytest.raises(FoundationError, match="invalid_conversation_response"):
        _apply(
            case,
            ConversationDeliveryRequest,
            action="respond",
            manifest=manifest,
            invocation_id=invocation,
            assistant_source=original,
            assistant_entry_id="final-entry",
            **fields,
        )
    assert read_conversation_delivery(case[0], fields["delivery_id"], case[2]).status == "included"


def test_unsent_release_requires_fence_and_unknown_send_cannot_retry(tmp_path: Path) -> None:
    case, action = _question(tmp_path)
    fields = _claim(case, action)
    with pytest.raises(FoundationError, match="explicit host fencing"):
        _apply(case, ConversationDeliveryRequest, action="abandon", **fields)
    _apply(case, ConversationDeliveryRequest, action="abandon", fenced=True, **fields)
    fields = _claim(case, action, host="second-window")
    manifest, invocation = _invocation(case, action, fields, "sent")
    with pytest.raises(FoundationError, match="unknown_conversation_delivery"):
        _apply(case, ConversationDeliveryRequest, action="abandon", fenced=True, **fields)
    _apply(
        case,
        ConversationDeliveryRequest,
        action="unknown",
        manifest=manifest,
        invocation_id=invocation,
        **fields,
    )
    assert read_conversation_delivery(case[0], fields["delivery_id"], case[2]).status == "unknown"
    with pytest.raises(FoundationError, match="conversation_delivery_claimed"):
        _claim(case, action, host="third-window")


def test_changed_question_refused_before_actual_send_and_old_evidence_readable(
    tmp_path: Path,
) -> None:
    case, action = _question(tmp_path)
    fields = _claim(case, action)
    manifest, invocation = _invocation(case, action, fields)
    _step(case, "answer", text="Weekly, with a monthly overview")
    with pytest.raises(FoundationError, match="stale_conversation_action"):
        read_conversation_action(case[0], action.ref, case[2])
    with pytest.raises(FoundationError, match="stale_conversation_action"):
        _apply(
            case,
            RecordContextDeliveryRequest,
            invocation_id=invocation,
            manifest=manifest,
            stage="sent",
            request_sha256="A" * 64,
            request_bytes=100,
        )
    assert read_conversation_delivery(case[0], fields["delivery_id"], case[2]).status == "included"
    assert read_activity_setup(case[0], case[3], case[2]).state.phase == "collecting"
    request = ConversationDeliveryRequest(
        operation_id=uuid4(),
        space_id=case[1],
        actor="owner",
        action="abandon",
        fenced=True,
        **fields,
    )
    receipt = apply_operation(case[0], request, case[2])
    assert apply_operation(case[0], request, case[2]) == receipt
    assert read_conversation_delivery(case[0], fields["delivery_id"], case[2]).status == "abandoned"


def test_backup_restore_epoch_and_dependent_source_sanitation(tmp_path: Path) -> None:
    case, action = _question(tmp_path)
    fields = _claim(case, action)
    manifest, invocation = _invocation(case, action, fields, "sent")
    _apply(
        case,
        ConversationDeliveryRequest,
        action="unknown",
        manifest=manifest,
        invocation_id=invocation,
        **fields,
    )
    backup = create_backup(case[0], uuid4(), case[2])
    restored = tmp_path / "restored"
    restored.mkdir()
    recovery = authorize_recovery(actor="owner", source_ref="fixture-recovery")
    restore_backup(backup.package, restored, recovery)
    assert read_space(restored).schema_version == 17
    apply_operation(
        restored,
        RecoverRequest(
            operation_id=uuid4(),
            space_id=case[1],
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        recovery,
    )
    reopened = authorize_local(restored, actor="owner", source_ref="fixture-reopened")
    restored_delivery = read_conversation_delivery(restored, fields["delivery_id"], reopened)
    assert (
        restored_delivery.status == "unknown" and restored_delivery.epoch < reopened.execution_epoch
    )
    with pytest.raises(FoundationError, match="terminal"):
        apply_operation(
            restored,
            ConversationDeliveryRequest(
                operation_id=uuid4(),
                space_id=case[1],
                actor="owner",
                action="abandon",
                fenced=True,
                **fields,
            ),
            reopened,
        )
    with pytest.raises(FoundationError, match="conversation_delivery_claimed"):
        apply_operation(
            restored,
            ConversationDeliveryRequest(
                operation_id=uuid4(),
                space_id=case[1],
                actor="owner",
                action="claim",
                delivery_id=uuid4(),
                action_ref=action.ref,
                host_id="after-recovery",
                session_id=uuid4(),
                branch_id="main",
            ),
            reopened,
        )
    source = next(ref for ref in action.bases if ref.record_id != case[4])
    original = read_knowledge(case[0], source.record_id, case[2])
    _apply(
        case,
        DeleteKnowledgeRequest,
        record_id=source.record_id,
        expected_revision=original.revision,
    )
    assert list_conversation_deliveries(case[0], case[2], action_id=action.ref.action_id) == ()
    assert read_space(restored).recovery_state == "active"
    old_authority = authorize_local(case[0], actor="owner", source_ref="fixture-owner")
    assert old_authority.execution_epoch == case[2].execution_epoch


def test_owner_source_must_follow_question_and_rights_are_rechecked(tmp_path: Path) -> None:
    case, action = _question(tmp_path)
    old_source = read_activity_setup(case[0], case[3], case[2]).state.sources[0]
    with pytest.raises(FoundationError, match="predates"):
        validate_conversation_answer(case[0], case[2], old_source, kind="setup", subject_id=case[3])
    identifier = uuid4()
    _apply(
        case,
        CreateKnowledgeRequest,
        record_id=identifier,
        state=SourceState(
            channel="conversation_user",
            connection="ordinary-pi",
            profile_revision=1,
            sender="owner",
            capture="full",
            content=b"Weekly",
            media_type="text/plain",
        ),
    )
    validate_conversation_answer(
        case[0],
        case[2],
        KnowledgeRef(record_id=identifier, revision=1),
        kind="setup",
        subject_id=case[3],
    )
    fields = _claim(case, action)
    manifest, invocation = _invocation(case, action, fields)
    _apply(
        case,
        CreateDecisionRequest,
        decision_id=uuid4(),
        state=DecisionState(
            statement="Deny reading this Activity",
            effect="deny",
            actions=("record.read",),
            subjects=("owner",),
        ),
    )
    assert list_conversation_actions(case[0], case[2]) == ()
    with pytest.raises(FoundationError, match="decision_denied"):
        read_conversation_action(case[0], action.ref, case[2])
    with pytest.raises(FoundationError, match="decision_denied"):
        _apply(
            case,
            RecordContextDeliveryRequest,
            invocation_id=invocation,
            manifest=manifest,
            stage="sent",
            request_sha256="A" * 64,
            request_bytes=100,
        )


def test_cursor_keeps_scanning_hidden_children_and_composite_wait_is_addressed(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    _step(case, "start_stage", stage_kind="draft", stage_instruction="Prepare complete setup")
    draft = _complete(case, _draft(case))
    _step(case, "start_stage", stage_kind="review", stage_instruction="Review complete setup")
    _complete(case, _review(case, draft))
    _step(case, "finish")
    _upgrade(case)
    all_actions: list[ConversationActionView] = []
    offset = 0
    while True:
        page = read_conversation_actions_page(
            case[0], case[2], limit=1, offset=offset, scan_limit=1
        )
        all_actions.extend(page.actions)
        if page.next_offset is None:
            break
        assert page.next_offset > offset
        offset = page.next_offset
    parent = read_activity_setup(case[0], case[3], case[2]).state.activated_works[0]
    assert any(item.work_id == parent and item.kind == "available_work" for item in all_actions)
    child = read_work_plan(case[0], parent, case[2]).plan.children[0].work_id
    _apply(
        case,
        IssueChildWorkRequest,
        parent_work_id=parent,
        work_id=child,
        expected_plan_revision=1,
        expected_work_revision=1,
    )
    resource, attempt, session, wait = uuid4(), uuid4(), uuid4(), uuid4()
    workdir = tmp_path / "resource"
    workdir.mkdir()
    _apply(
        case,
        CreateResourceRequest,
        work_id=child,
        resource_id=resource,
        state=ResourceState(label="Fictional resource", root=workdir),
    )
    _apply(
        case,
        AssignAttemptRequest,
        work_id=child,
        attempt_id=attempt,
        resource_id=resource,
        expected_work_revision=read_work(case[0], child, case[2]).revision,
        expected_resource_revision=1,
        session_id=session,
        executor_version="fixture-1",
    )
    _apply(
        case,
        OpenWaitRequest,
        work_id=child,
        attempt_id=attempt,
        wait_id=wait,
        session_id=session,
        expected_assignment_revision=1,
        question="Which observation?",
        expected_actor="owner",
        remainder="Await actual observation",
    )
    action = next(
        item for item in list_conversation_actions(case[0], case[2]) if item.subject_id == parent
    )
    assert action.kind == "question" and action.explanation == "Which observation?"
    assert action.answer_target is not None
    assert action.answer_target.subject_id == child and action.answer_target.wait_id == wait
    source = uuid4()
    _apply(
        case,
        CreateKnowledgeRequest,
        record_id=source,
        state=SourceState(
            channel="conversation_user",
            connection="ordinary-pi",
            profile_revision=1,
            sender="owner",
            capture="full",
            content=b"The latest one",
            media_type="text/plain",
        ),
    )
    validate_conversation_answer(
        case[0],
        case[2],
        KnowledgeRef(record_id=source, revision=1),
        kind="work",
        subject_id=child,
        wait_id=wait,
    )
    assert read_work(case[0], parent, case[2]).state.acceptance is None


def _ordinary_final_case(tmp_path: Path, variant: str) -> tuple[Case, UUID, UUID, UUID]:
    case = _case(tmp_path)
    _upgrade(case)
    activity, work, resource, attempt, session, invocation = (uuid4() for _ in range(6))
    workdir = tmp_path / "ordinary-work"
    workdir.mkdir()
    _apply(
        case,
        CreateActivityRequest,
        activity_id=activity,
        state=ActivityState(title="Fictional conversation", goal="Continue after close"),
    )
    _apply(
        case,
        CreateWorkRequest,
        work_id=work,
        state=WorkState(
            activity_id=activity,
            goal="Explain current state",
            expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
        ),
    )
    _apply(
        case,
        CreateResourceRequest,
        resource_id=resource,
        work_id=work,
        state=ResourceState(label="Ordinary resource", root=workdir),
    )
    _apply(
        case,
        StartAttemptRequest,
        work_id=work,
        attempt_id=attempt,
        resource_id=resource,
        expected_work_revision=1,
        expected_resource_revision=1,
        session_id=session,
    )
    manifest = KnowledgeRef(record_id=uuid4(), revision=1)
    _apply(
        case,
        CreateKnowledgeRequest,
        record_id=manifest.record_id,
        state=ContextState(
            purpose="Ordinary conversation",
            session_id=session,
            work_id=work,
            attempt_id=attempt,
            mandatory=(KnowledgeRef(record_id=work, revision=1),),
        ),
    )
    _apply(
        case,
        PrepareInvocationRequest,
        work_id=work,
        attempt_id=attempt,
        session_id=session,
        invocation_id=invocation,
        purpose="content",
        provider="fictional",
        model="fictional",
        transport="local",
        request_sha256="A" * 64,
        request_bytes=100,
        reserve_units=1,
    )
    _apply(
        case,
        RecordContextDeliveryRequest,
        invocation_id=invocation,
        manifest=manifest,
        stage="prepared",
    )
    common = dict(work_id=work, attempt_id=attempt, session_id=session, invocation_id=invocation)
    _apply(case, AdmitInvocationRequest, **common)
    _apply(case, SendInvocationRequest, **common)
    _apply(
        case,
        RecordContextDeliveryRequest,
        invocation_id=invocation,
        manifest=manifest,
        stage="sent",
        request_sha256="A" * 64,
        request_bytes=100,
    )
    outcome = "unknown" if variant == "unknown" else "answered"
    _apply(
        case,
        FinishInvocationRequest,
        outcome=outcome,
        usage_units=0 if outcome == "answered" else None,
        **common,
    )
    _apply(
        case,
        RecordContextDeliveryRequest,
        invocation_id=invocation,
        manifest=manifest,
        stage=outcome,
        usage_units=0 if outcome == "answered" else None,
    )
    source_session = uuid4() if variant == "other_session" else session
    _apply(
        case,
        CreateKnowledgeRequest,
        record_id=uuid4(),
        state=SourceState(
            channel="conversation_assistant",
            connection="ordinary-pi",
            profile_revision=1,
            conversation_id=str(source_session),
            source_event_id=f"{source_session}:native-final",
            sender="pi-assistant",
            scope_work_id=work,
            capture="full",
            content=b" \t\r\n" if variant == "whitespace" else b"Saved final reply",
            media_type="text/plain",
            conversation_final=variant != "tool",
            derived_from=(manifest,),
        ),
    )
    return case, work, attempt, session


@pytest.mark.parametrize("variant", ("valid", "tool", "unknown", "other_session", "whitespace"))
def test_ordinary_final_recovery_requires_exact_saved_final_proof(
    tmp_path: Path,
    variant: str,
) -> None:
    case, work, attempt, session = _ordinary_final_case(tmp_path, variant)
    proof = read_ordinary_final_proof(case[0], work, case[2], attempt_id=attempt)
    if variant == "valid":
        assert proof is not None and proof.session_id == session
        assert proof.assistant_entry_id == "native-final" and proof.attempt_id == attempt
        _apply(
            case,
            StopAttemptRequest,
            work_id=work,
            attempt_id=attempt,
            session_id=session,
            outcome="completed",
            observed_final=proof,
        )
        assert read_execution(case[0], work, case[2]).attempts[-1].status == "completed"
    else:
        assert proof is None
        assert read_execution(case[0], work, case[2]).attempts[-1].status == "active"
    assert read_work(case[0], work, case[2]).state.acceptance is None


def _selection_transition_case(
    tmp_path: Path,
    *,
    native_ui: bool = False,
    assigned: bool = False,
    target_mode: Literal["ordinary", "assigned", "project"] = "ordinary",
    same_work: bool = False,
    complete_output: bool = False,
    prior_assignment: bool = False,
) -> tuple[Case, StopAttemptRequest, KnowledgeRef, UUID | None]:
    case = _case(tmp_path)
    _upgrade(case)
    upgrade_delivery_correlation_space(case[0], case[2])
    work, target, resource, attempt, session = (uuid4() for _ in range(5))
    activity = uuid4()
    _apply(
        case,
        CreateActivityRequest,
        activity_id=activity,
        state=ActivityState(
            title="Fictional selection",
            goal="Continue between saved works",
        ),
    )
    directory = tmp_path / "selection-root"
    directory.mkdir()
    for identifier in (work, target):
        _apply(
            case,
            CreateWorkRequest,
            work_id=identifier,
            state=WorkState(
                activity_id=activity,
                goal="Fictional selected work",
                expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
            ),
        )
    if complete_output:
        artifact = uuid4()
        _apply(
            case,
            CreateArtifactRequest,
            artifact_id=artifact,
            media_type="text/plain",
            content=b"Complete retained output",
        )
        _apply(
            case,
            LinkWorkOutputRequest,
            work_id=work,
            expected_revision=1,
            output=LinkedOutput(
                slot="report", artifact=ArtifactRef(artifact_id=artifact, revision=1)
            ),
        )
    work_revision = read_work(case[0], work, case[2]).revision
    _apply(
        case,
        CreateResourceRequest,
        resource_id=resource,
        work_id=work,
        state=ResourceState(label="Selection root", root=directory),
    )
    previous_attempt = None
    if prior_assignment:
        previous_attempt, previous_session = uuid4(), uuid4()
        _apply(
            case,
            AssignAttemptRequest,
            work_id=work,
            attempt_id=previous_attempt,
            resource_id=resource,
            expected_work_revision=work_revision,
            expected_resource_revision=1,
            session_id=previous_session,
            executor_version="fictional",
        )
        _claim_assigned(case[0], case[1], case[2], work, previous_attempt, previous_session)
        _assigned_invocation(case[0], case[1], case[2], work, previous_attempt, previous_session)
        _stop_assigned(case[0], case[1], case[2], work, previous_attempt, previous_session)
    _apply(
        case,
        AssignAttemptRequest if assigned else StartAttemptRequest,
        work_id=work,
        attempt_id=attempt,
        resource_id=resource,
        expected_work_revision=work_revision,
        expected_resource_revision=1,
        session_id=session,
        previous_attempt_id=previous_attempt,
        **({"executor_version": "fictional"} if assigned else {}),
    )
    project = tmp_path / "next-project"
    if target_mode == "project":
        project.mkdir()
    selected = SelectionTarget(
        mode=target_mode,
        work_id=work if same_work else target,
        work_revision=work_revision if same_work else 1,
        root=project if target_mode == "project" else None,
    )
    owner_source = KnowledgeRef(record_id=uuid4(), revision=1)
    observation = owner_source if native_ui else KnowledgeRef(record_id=uuid4(), revision=1)
    manifest = KnowledgeRef(record_id=uuid4(), revision=1)
    invocation = None if native_ui else uuid4()
    if not native_ui:
        _apply(
            case,
            CreateKnowledgeRequest,
            record_id=owner_source.record_id,
            state=SourceState(
                channel="conversation_user",
                connection="ordinary-pi",
                profile_revision=1,
                sender="owner",
                conversation_id=str(session),
                source_event_id=f"{session}:user",
                capture="full",
                content=b"Continue the other work",
                media_type="text/plain",
            ),
        )
        _apply(
            case,
            CreateKnowledgeRequest,
            record_id=manifest.record_id,
            state=ContextState(
                purpose="Choose another saved work",
                session_id=session,
                work_id=work,
                attempt_id=attempt,
                mandatory=(KnowledgeRef(record_id=work, revision=work_revision), owner_source),
            ),
        )
        common = dict(
            work_id=work, attempt_id=attempt, session_id=session, invocation_id=invocation
        )
        _apply(
            case,
            PrepareInvocationRequest,
            purpose="content",
            provider="fictional",
            model="fictional",
            transport="local",
            request_sha256="A" * 64,
            request_bytes=100,
            reserve_units=1,
            **common,
        )
        _apply(
            case,
            RecordContextDeliveryRequest,
            invocation_id=invocation,
            manifest=manifest,
            stage="prepared",
        )
        _apply(case, AdmitInvocationRequest, **common)
        _apply(case, SendInvocationRequest, **common)
        _apply(
            case,
            RecordContextDeliveryRequest,
            invocation_id=invocation,
            manifest=manifest,
            stage="sent",
            request_sha256="A" * 64,
            request_bytes=100,
        )
        _apply(case, FinishInvocationRequest, outcome="answered", usage_units=0, **common)
        _apply(
            case,
            RecordContextDeliveryRequest,
            invocation_id=invocation,
            manifest=manifest,
            stage="answered",
            usage_units=0,
        )
    metadata = NativeSelectionObservation(
        origin="native_ui" if native_ui else "owner_tool",
        target=selected,
        owner_source=None if native_ui else owner_source,
        host_id="fictional-host",
        branch_id="main",
        generation=1,
        tool_call_id=None if native_ui else "native-call",
        tool_name=None if native_ui else "zara_conversation",
        arguments_json=None if native_ui else '{"mode":"use_existing_work"}',
    )
    bases: tuple[KnowledgeRef, ...] = (
        KnowledgeRef(
            record_id=work if same_work else target, revision=work_revision if same_work else 1
        ),
    )
    if not native_ui:
        bases += (owner_source, manifest)
    boundary = None
    if not native_ui:
        assert invocation is not None
        boundary = ConversationTerminalObservation(
            invocation_id=invocation,
            manifest=manifest,
            assistant_entry_id="native-choice",
            native_outcome="tool_call",
            stop_reason="toolUse",
        )
    _apply(
        case,
        CreateKnowledgeRequest,
        record_id=observation.record_id,
        state=SourceState(
            channel="core_operation" if native_ui else "conversation_assistant",
            connection="ordinary-pi",
            profile_revision=1,
            sender="owner" if native_ui else "pi-assistant",
            conversation_id=str(session),
            source_event_id=f"{session}:native-choice",
            scope_work_id=work,
            capture="full",
            content=b"/zara-work choice" if native_ui else b"",
            media_type="text/plain",
            derived_from=bases,
            native_selection=metadata,
            conversation_terminal=boundary,
        ),
    )
    request = StopAttemptRequest(
        operation_id=uuid4(),
        space_id=case[1],
        actor="owner",
        work_id=work,
        attempt_id=attempt,
        session_id=session,
        outcome="interrupted",
        selection_transition=OrdinarySelectionTransition(
            execution_epoch=case[2].execution_epoch,
            work_revision=work_revision,
            attempt_revision=1,
            resource_id=resource,
            resource_revision=1,
            owner_source=owner_source,
            observation=observation,
            boundary_source=None if native_ui else observation,
            target=selected,
        ),
    )
    return case, request, manifest, invocation


@pytest.mark.parametrize("native_ui", (False, True))
def test_guarded_selection_interrupts_exact_attempt_without_final_or_acceptance(
    tmp_path: Path, native_ui: bool
) -> None:
    case, request, _, _ = _selection_transition_case(tmp_path, native_ui=native_ui)
    before = read_execution(case[0], request.work_id, case[2])
    receipt = apply_operation(case[0], request, case[2])
    assert apply_operation(case[0], request, case[2]) == receipt
    after = read_execution(case[0], request.work_id, case[2])
    assert after.attempts[-1].status == "interrupted"
    assert after.invocations == before.invocations and after.work == before.work
    assert after.work.state.acceptance is None
    proof = request.selection_transition
    assert proof is not None and receipt.result["selection_transition"] == proof.model_dump(
        mode="json"
    )
    targets = read_operation_audit(case[0], request.operation_id, case[2]).target_refs
    assert any(item.record_id == proof.observation.record_id for item in targets)
    assert any(item.record_id == proof.target.work_id for item in targets)
    assert "selection_transition" not in request.model_copy(
        update={"selection_transition": None}
    ).model_dump(mode="json")


@pytest.mark.parametrize(
    "changed", ("session", "epoch", "attempt", "resource", "target", "owner", "rights")
)
def test_guarded_selection_rechecks_current_pins_and_authority(
    tmp_path: Path, changed: str
) -> None:
    case, request, _, _ = _selection_transition_case(tmp_path)
    proof = request.selection_transition
    assert proof is not None
    if changed == "session":
        request = request.model_copy(update={"session_id": uuid4()})
    elif changed == "rights":
        _apply(
            case,
            CreateDecisionRequest,
            decision_id=uuid4(),
            state=DecisionState(
                statement="Revoke execution",
                effect="deny",
                actions=("work.execute",),
                subjects=("owner",),
            ),
        )
    else:
        updates: dict[str, dict[str, Any]] = {
            "epoch": {"execution_epoch": proof.execution_epoch + 1},
            "attempt": {"attempt_revision": proof.attempt_revision + 1},
            "resource": {"resource_revision": proof.resource_revision + 1},
            "target": {"target": proof.target.model_copy(update={"work_revision": 2})},
            "owner": {"owner_source": KnowledgeRef(record_id=uuid4(), revision=1)},
        }
        update = updates[changed]
        request = request.model_copy(
            update={"selection_transition": proof.model_copy(update=update)}
        )
    before = read_execution(case[0], request.work_id, case[2])
    with pytest.raises(FoundationError):
        apply_operation(case[0], request, case[2])
    assert read_execution(case[0], request.work_id, case[2]) == before


@pytest.mark.parametrize("deleted_manifest", (False, True))
def test_guarded_selection_fences_delivery_race_even_without_execution_invocation(
    tmp_path: Path, deleted_manifest: bool
) -> None:
    case, request, manifest, _ = _selection_transition_case(tmp_path)
    late = uuid4()
    _apply(
        case, RecordContextDeliveryRequest, invocation_id=late, manifest=manifest, stage="prepared"
    )
    _apply(
        case,
        RecordContextDeliveryRequest,
        invocation_id=late,
        manifest=manifest,
        stage="sent",
        request_sha256="B" * 64,
        request_bytes=123,
    )
    if deleted_manifest:
        _apply(case, DeleteKnowledgeRequest, record_id=manifest.record_id, expected_revision=1)
    before = read_execution(case[0], request.work_id, case[2])
    with pytest.raises(FoundationError, match="response_outcome_unknown"):
        apply_operation(case[0], request, case[2])
    assert read_execution(case[0], request.work_id, case[2]) == before


def test_complete_output_precedes_ordinary_assignment_handoff(tmp_path: Path) -> None:
    """A handoff is not permission to regenerate an already published result."""
    from zaratustra.foundation import read_attempt_response

    case, request, _, _ = _selection_transition_case(
        tmp_path, target_mode="assigned", same_work=True, complete_output=True
    )
    apply_operation(case[0], request, case[2])
    before = read_execution(case[0], request.work_id, case[2])
    view = read_attempt_response(case[0], request.work_id, case[2])
    assert view.outcome == "applied" and view.handoff_operation_id is None
    assert view.artifact == before.work.state.linked_outputs[0].artifact
    assert read_execution(case[0], request.work_id, case[2]) == before
    assert not before.assignments and before.work.state.acceptance is None
    assert before.attempts[-1].status == "interrupted"


def test_guarded_selection_receipt_deletion_and_restore_preserve_truthful_history(
    tmp_path: Path,
) -> None:
    case, request, _, _ = _selection_transition_case(tmp_path)
    receipt = apply_operation(case[0], request, case[2])
    backup = create_backup(case[0], uuid4(), case[2])
    restored = tmp_path / "restored-transition"
    restored.mkdir()
    recovery = authorize_recovery(actor="owner", source_ref="fictional-restore")
    restored_info = restore_backup(backup.package, restored, recovery)
    apply_operation(
        restored,
        RecoverRequest(
            operation_id=uuid4(),
            space_id=case[1],
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        recovery,
    )
    restored_owner = authorize_local(restored, actor="owner", source_ref="restored-owner")
    assert restored_info.execution_epoch == case[2].execution_epoch + 1
    assert (
        read_execution(restored, request.work_id, restored_owner).attempts[-1].status
        == "interrupted"
    )
    assert read_receipt(restored, request.operation_id, restored_owner) == receipt
    proof = request.selection_transition
    assert proof is not None
    _apply(
        case, DeleteKnowledgeRequest, record_id=proof.owner_source.record_id, expected_revision=1
    )
    with pytest.raises(FoundationError, match="history_unavailable"):
        apply_operation(case[0], request, case[2])
    assert read_execution(case[0], request.work_id, case[2]).attempts[-1].status == "interrupted"
    assert proof.target.work_id is not None
    assert read_work(case[0], proof.target.work_id, case[2]).state.acceptance is None


@pytest.mark.parametrize("mode", ("ordinary", "assigned", "project"))
def test_guarded_selection_distinguishes_same_work_execution_ownership(
    tmp_path: Path, mode: Literal["ordinary", "assigned", "project"]
) -> None:
    case, request, _, _ = _selection_transition_case(
        tmp_path, native_ui=True, target_mode=mode, same_work=True
    )
    if mode == "ordinary":
        with pytest.raises(FoundationError, match="selection_unchanged"):
            apply_operation(case[0], request, case[2])
        assert read_execution(case[0], request.work_id, case[2]).attempts[-1].status == "active"
    else:
        apply_operation(case[0], request, case[2])
        assert (
            read_execution(case[0], request.work_id, case[2]).attempts[-1].status == "interrupted"
        )


def test_guarded_selection_refuses_assigned_ownership(tmp_path: Path) -> None:
    case, request, _, _ = _selection_transition_case(tmp_path, native_ui=True, assigned=True)
    before = read_execution(case[0], request.work_id, case[2])
    with pytest.raises(FoundationError, match="assigned_attempt"):
        apply_operation(case[0], request, case[2])
    assert read_execution(case[0], request.work_id, case[2]) == before


@pytest.mark.parametrize("status", ("admitted", "sent", "unknown"))
def test_guarded_selection_refuses_new_execution_send_after_observation(
    tmp_path: Path, status: str
) -> None:
    case, request, _, _ = _selection_transition_case(tmp_path)
    common = dict(
        work_id=request.work_id,
        attempt_id=request.attempt_id,
        session_id=request.session_id,
        invocation_id=uuid4(),
    )
    _apply(
        case,
        PrepareInvocationRequest,
        purpose="other",
        provider="fictional",
        model="fictional",
        transport="local",
        request_sha256="B" * 64,
        request_bytes=100,
        reserve_units=1,
        **common,
    )
    _apply(case, AdmitInvocationRequest, **common)
    if status != "admitted":
        _apply(case, SendInvocationRequest, **common)
    if status == "unknown":
        _apply(case, FinishInvocationRequest, outcome="unknown", **common)
    before = read_execution(case[0], request.work_id, case[2])
    with pytest.raises(FoundationError, match="response_outcome_unknown"):
        apply_operation(case[0], request, case[2])
    assert read_execution(case[0], request.work_id, case[2]) == before


@pytest.mark.parametrize("change", ("invocation", "source"))
def test_observed_final_stop_rechecks_proof_in_its_mutation_transaction(
    tmp_path: Path,
    change: str,
) -> None:
    case, work, attempt, session = _ordinary_final_case(tmp_path, "valid")
    proof = read_ordinary_final_proof(case[0], work, case[2], attempt_id=attempt)
    assert proof is not None
    if change == "invocation":
        _apply(
            case,
            PrepareInvocationRequest,
            work_id=work,
            attempt_id=attempt,
            session_id=session,
            invocation_id=uuid4(),
            purpose="other",
            provider="fictional",
            model="fictional",
            transport="local",
            request_sha256="B" * 64,
            request_bytes=100,
            reserve_units=1,
        )
    else:
        source = read_knowledge(case[0], proof.assistant_source.record_id, case[2])
        assert isinstance(source.state, SourceState)
        _apply(
            case,
            ReviseKnowledgeRequest,
            record_id=source.record_id,
            expected_revision=source.revision,
            state=source.state.model_copy(
                update={"memory": MemoryMetadata(title="Retained native final reply")}
            ),
        )
    with pytest.raises(FoundationError, match="stale_final_response"):
        _apply(
            case,
            StopAttemptRequest,
            work_id=work,
            attempt_id=attempt,
            session_id=session,
            outcome="completed",
            observed_final=proof,
        )
    assert read_execution(case[0], work, case[2]).attempts[-1].status == "active"
    assert "observed_final" not in StopAttemptRequest(
        operation_id=uuid4(),
        space_id=case[1],
        actor="owner",
        work_id=work,
        attempt_id=attempt,
        session_id=session,
        outcome="interrupted",
    ).model_dump(mode="json")


def _terminal_original(
    case: Case,
    fields: dict[str, Any],
    manifest: KnowledgeRef,
    invocation: UUID,
    content: bytes,
    *,
    stop_reason: str = "stop",
    outcome: Literal["completed", "tool_call", "aborted", "error", "unknown"] = "completed",
) -> tuple[KnowledgeRef, str]:
    source, entry = uuid4(), str(uuid4())
    _apply(
        case,
        CreateKnowledgeRequest,
        record_id=source,
        state=SourceState(
            channel="conversation_assistant",
            connection="ordinary-pi",
            profile_revision=1,
            sender="pi-assistant",
            conversation_id=str(fields["session_id"]),
            source_event_id=f"{fields['session_id']}:{entry}",
            media_type="text/plain",
            capture="full",
            content=content,
            derived_from=(manifest,),
            conversation_final=True,
            conversation_terminal=ConversationTerminalObservation(
                invocation_id=invocation,
                manifest=manifest,
                assistant_entry_id=entry,
                native_outcome=outcome,
                stop_reason=stop_reason,
            ),
        ),
    )
    return KnowledgeRef(record_id=source, revision=1), entry


@pytest.mark.parametrize(
    "content,reason,expected",
    (
        (b"", "stop", "empty"),
        (b" \t\r\n", "stop", "empty"),
        ("\u00a0\u3000".encode(), "stop", "empty"),
        ("Готово".encode(), "stop", "visible"),
        (b"", "length", "attention"),
        (b"", "toolUse", "unproven"),
    ),
)
def test_native_terminal_original_is_retained_before_response_classification(
    tmp_path: Path,
    content: bytes,
    reason: str,
    expected: str,
) -> None:
    case, action = _question(tmp_path)
    fields = _claim(case, action)
    manifest, invocation = _invocation(case, action, fields, "answered")
    source, entry = _terminal_original(
        case, fields, manifest, invocation, content, stop_reason=reason
    )
    original = read_knowledge(case[0], source.record_id, case[2])
    assert isinstance(original.state, SourceState) and original.state.content == content
    _apply(
        case,
        ConversationDeliveryRequest,
        action="observe_terminal",
        manifest=manifest,
        invocation_id=invocation,
        assistant_source=source,
        assistant_entry_id=entry,
        **fields,
    )
    view = read_conversation_delivery(case[0], fields["delivery_id"], case[2])
    assert view.response_outcome == expected and view.repair_count == 0
    assert view.response_source == source and view.status == "included"
    if expected == "empty":
        with pytest.raises(FoundationError, match="invalid_conversation_response"):
            _apply(
                case,
                ConversationDeliveryRequest,
                action="respond",
                manifest=manifest,
                invocation_id=invocation,
                assistant_source=source,
                assistant_entry_id=entry,
                **fields,
            )
        with pytest.raises(FoundationError, match="response_repair_required"):
            _invocation(case, action, fields)
    elif expected in ("attention", "unproven"):
        with pytest.raises(FoundationError, match="response_repair_unavailable"):
            _apply(case, ConversationDeliveryRequest, action="repair_response", **fields)


def test_response_repairs_are_persistent_bounded_and_observation_is_idempotent(
    tmp_path: Path,
) -> None:
    case, action = _question(tmp_path)
    fields = _claim(case, action)
    for number in range(3):
        manifest, invocation = _invocation(case, action, fields, "answered")
        source, entry = _terminal_original(case, fields, manifest, invocation, b"")
        request = ConversationDeliveryRequest(
            operation_id=uuid4(),
            space_id=case[1],
            actor="owner",
            action="observe_terminal",
            manifest=manifest,
            invocation_id=invocation,
            assistant_source=source,
            assistant_entry_id=entry,
            **fields,
        )
        receipt = apply_operation(case[0], request, case[2])
        assert apply_operation(case[0], request, case[2]) == receipt
        view = read_conversation_delivery(case[0], fields["delivery_id"], case[2])
        assert view.repair_count == number and view.status == "included"
        if number < 2:
            first = _apply(case, ConversationDeliveryRequest, action="repair_response", **fields)
            duplicate = _apply(
                case, ConversationDeliveryRequest, action="repair_response", **fields
            )
            assert first.result == duplicate.result and first.result["repair_number"] == number + 1
            _apply(
                case,
                ConversationDeliveryRequest,
                action="observe_terminal",
                manifest=manifest,
                invocation_id=invocation,
                assistant_source=source,
                assistant_entry_id=entry,
                **fields,
            )
            assert (
                read_conversation_delivery(case[0], fields["delivery_id"], case[2]).response_outcome
                == "empty"
            )
        else:
            assert view.response_outcome == "attention"
            assert view.diagnostics[0].code == "response_repair_exhausted"
            with pytest.raises(FoundationError, match="response_repair_unavailable"):
                _apply(case, ConversationDeliveryRequest, action="repair_response", **fields)
    reopened = authorize_local(case[0], actor="owner", source_ref="reopened-console")
    assert read_conversation_delivery(case[0], fields["delivery_id"], reopened).repair_count == 2
    with pytest.raises(FoundationError, match="stale_conversation_delivery"):
        _apply(
            case,
            ConversationDeliveryRequest,
            action="repair_response",
            **{**fields, "branch_id": "another-branch"},
        )
    assert read_activity_setup(case[0], case[3], case[2]).state.phase == "needs_input"


def test_unknown_or_missing_native_evidence_never_authorizes_response_repair(
    tmp_path: Path,
) -> None:
    case, action = _question(tmp_path)
    fields = _claim(case, action)
    manifest, invocation = _invocation(case, action, fields, "answered")
    with pytest.raises(FoundationError, match="response_repair_unavailable"):
        _apply(case, ConversationDeliveryRequest, action="repair_response", **fields)
    _apply(
        case,
        ConversationDeliveryRequest,
        action="response_attention",
        response_problem=ConversationResponseProblem(
            code="native_capture_failed", message="Original could not be retained"
        ),
        **fields,
    )
    view = read_conversation_delivery(case[0], fields["delivery_id"], case[2])
    assert view.response_outcome == "attention" and view.response_source is None
    _apply(
        case,
        ConversationDeliveryRequest,
        action="unknown",
        manifest=manifest,
        invocation_id=invocation,
        **fields,
    )
    assert (
        read_conversation_delivery(case[0], fields["delivery_id"], case[2]).response_outcome
        == "unproven"
    )
    with pytest.raises(FoundationError, match="terminal"):
        _apply(case, ConversationDeliveryRequest, action="repair_response", **fields)


def test_invalid_utf8_capture_cannot_become_empty_or_retry_permission(tmp_path: Path) -> None:
    case, action = _question(tmp_path)
    fields = _claim(case, action)
    manifest, invocation = _invocation(case, action, fields, "answered")
    with pytest.raises(FoundationError, match="invalid_content"):
        _terminal_original(case, fields, manifest, invocation, b"\xff")
    view = read_conversation_delivery(case[0], fields["delivery_id"], case[2])
    assert view.response_source is None and view.response_outcome == "unproven"
    _apply(
        case,
        ConversationDeliveryRequest,
        action="response_attention",
        response_problem=ConversationResponseProblem(
            code="native_capture_invalid_utf8", message="Text capture rejected invalid UTF-8"
        ),
        **fields,
    )
    with pytest.raises(FoundationError, match="response_repair_unavailable"):
        _apply(case, ConversationDeliveryRequest, action="repair_response", **fields)


def test_terminal_source_budget_restore_and_fragment_proof_refusal(tmp_path: Path) -> None:
    case, action = _question(tmp_path)
    fields = _claim(case, action)
    manifest, invocation = _invocation(case, action, fields, "answered")
    source, entry = _terminal_original(case, fields, manifest, invocation, b" ")
    fragment = source.model_copy(update={"start": 0, "end": 1})
    with pytest.raises(FoundationError, match="whole Source"):
        _apply(
            case,
            ConversationDeliveryRequest,
            action="observe_terminal",
            manifest=manifest,
            invocation_id=invocation,
            assistant_source=fragment,
            assistant_entry_id=entry,
            **fields,
        )
    _apply(
        case,
        ConversationDeliveryRequest,
        action="observe_terminal",
        manifest=manifest,
        invocation_id=invocation,
        assistant_source=source,
        assistant_entry_id=entry,
        **fields,
    )
    _apply(case, ConversationDeliveryRequest, action="repair_response", **fields)
    backup = create_backup(case[0], uuid4(), case[2])
    restored = tmp_path / "restored-response"
    restored.mkdir()
    recovery = authorize_recovery(actor="owner", source_ref="fictional-recovery")
    restore_backup(backup.package, restored, recovery)
    apply_operation(
        restored,
        RecoverRequest(
            operation_id=uuid4(),
            space_id=case[1],
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        recovery,
    )
    owner = authorize_local(restored, actor="owner", source_ref="fictional-reopened")
    recovered = read_conversation_delivery(restored, fields["delivery_id"], owner)
    assert recovered.repair_count == 1 and recovered.response_source == source
    with pytest.raises(FoundationError, match="stale_conversation_delivery"):
        apply_operation(
            restored,
            ConversationDeliveryRequest(
                operation_id=uuid4(),
                space_id=case[1],
                actor="owner",
                action="repair_response",
                **fields,
            ),
            owner,
        )
    _apply(case, DeleteKnowledgeRequest, record_id=source.record_id, expected_revision=1)
    assert (
        list_conversation_deliveries(case[0], case[2], action_id=action.ref.action_id)[0].status
        == "stale"
    )
    original = read_knowledge(restored, source.record_id, owner)
    assert isinstance(original.state, SourceState) and original.state.content == b" "


def test_duplicate_response_receipts_follow_source_deletion_without_spending_budget(
    tmp_path: Path,
) -> None:
    case, action = _question(tmp_path)
    fields = _claim(case, action)
    manifest, invocation = _invocation(case, action, fields, "answered")
    source, entry = _terminal_original(case, fields, manifest, invocation, b"")
    observed = _apply(
        case,
        ConversationDeliveryRequest,
        action="observe_terminal",
        manifest=manifest,
        invocation_id=invocation,
        assistant_source=source,
        assistant_entry_id=entry,
        **fields,
    )
    repair = _apply(case, ConversationDeliveryRequest, action="repair_response", **fields)
    alias_observed = _apply(
        case,
        ConversationDeliveryRequest,
        action="observe_terminal",
        manifest=manifest,
        invocation_id=invocation,
        assistant_source=source,
        assistant_entry_id=entry,
        **fields,
    )
    alias_repair = _apply(case, ConversationDeliveryRequest, action="repair_response", **fields)
    assert observed.result == alias_observed.result and repair.result == alias_repair.result
    view = read_conversation_delivery(case[0], fields["delivery_id"], case[2])
    assert view.repair_count == 1 and view.response_outcome == "empty"
    _apply(case, DeleteKnowledgeRequest, record_id=source.record_id, expected_revision=1)
    for receipt in (observed, repair, alias_observed, alias_repair):
        with pytest.raises(FoundationError, match="not_found"):
            read_receipt(case[0], receipt.operation_id, case[2])
    assert read_conversation_delivery(case[0], fields["delivery_id"], case[2]).status == "stale"


def test_visible_observed_reply_cannot_be_hidden_by_another_invocation(tmp_path: Path) -> None:
    case, action = _question(tmp_path)
    fields = _claim(case, action)
    manifest, invocation = _invocation(case, action, fields, "answered")
    source, entry = _terminal_original(case, fields, manifest, invocation, b"Ready to continue")
    _apply(
        case,
        ConversationDeliveryRequest,
        action="observe_terminal",
        manifest=manifest,
        invocation_id=invocation,
        assistant_source=source,
        assistant_entry_id=entry,
        **fields,
    )
    with pytest.raises(FoundationError, match="response_already_visible"):
        _invocation(case, action, fields)
    view = read_conversation_delivery(case[0], fields["delivery_id"], case[2])
    assert view.response_source == source and view.response_outcome == "visible"
    _apply(
        case,
        ConversationDeliveryRequest,
        action="respond",
        manifest=manifest,
        invocation_id=invocation,
        assistant_source=source,
        assistant_entry_id=entry,
        **fields,
    )
    assert read_conversation_delivery(case[0], fields["delivery_id"], case[2]).status == "responded"


def test_native_original_before_final_accounting_remains_pending_then_can_be_observed(
    tmp_path: Path,
) -> None:
    case, action = _question(tmp_path)
    fields = _claim(case, action)
    manifest, invocation = _invocation(case, action, fields, "sent")
    source, entry = _terminal_original(case, fields, manifest, invocation, b"")
    request = ConversationDeliveryRequest(
        operation_id=uuid4(),
        space_id=case[1],
        actor="owner",
        action="observe_terminal",
        manifest=manifest,
        invocation_id=invocation,
        assistant_source=source,
        assistant_entry_id=entry,
        **fields,
    )
    with pytest.raises(FoundationError, match="response_accounting_pending"):
        apply_operation(case[0], request, case[2])
    pending = read_conversation_delivery(case[0], fields["delivery_id"], case[2])
    assert pending.status == "included" and pending.response_outcome == "unproven"
    _apply(
        case,
        RecordContextDeliveryRequest,
        invocation_id=invocation,
        manifest=manifest,
        stage="answered",
        usage_units=0,
    )
    receipt = apply_operation(case[0], request, case[2])
    assert receipt.result["response_outcome"] == "empty"
    observed = read_conversation_delivery(case[0], fields["delivery_id"], case[2])
    assert observed.status == "included" and observed.response_source == source


@pytest.mark.parametrize("stage", ("prepared", "sent", "answered", "unknown"))
@pytest.mark.parametrize("manifest_deleted", (False, True))
def test_no_send_cleanup_checks_pinned_knowledge_accounting_without_execution_send(
    tmp_path: Path,
    stage: str,
    manifest_deleted: bool,
) -> None:
    case = _case(tmp_path)
    _upgrade(case)
    upgrade_delivery_correlation_space(case[0], case[2])
    activity, work, resource, attempt, session, invocation = (uuid4() for _ in range(6))
    workdir = tmp_path / "unsent-work"
    workdir.mkdir()
    _apply(
        case,
        CreateActivityRequest,
        activity_id=activity,
        state=ActivityState(title="Fictional cleanup", goal="Preserve send accounting"),
    )
    _apply(
        case,
        CreateWorkRequest,
        work_id=work,
        state=WorkState(
            activity_id=activity,
            goal="Ordinary preflight",
            expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
        ),
    )
    _apply(
        case,
        CreateResourceRequest,
        resource_id=resource,
        work_id=work,
        state=ResourceState(label="Preflight resource", root=workdir),
    )
    _apply(
        case,
        StartAttemptRequest,
        work_id=work,
        attempt_id=attempt,
        resource_id=resource,
        expected_work_revision=1,
        expected_resource_revision=1,
        session_id=session,
    )
    manifest = KnowledgeRef(record_id=uuid4(), revision=1)
    _apply(
        case,
        CreateKnowledgeRequest,
        record_id=manifest.record_id,
        state=ContextState(
            purpose="Pinned ordinary preflight",
            session_id=session,
            work_id=work,
            attempt_id=attempt,
            mandatory=(KnowledgeRef(record_id=work, revision=1),),
        ),
    )
    _apply(
        case,
        RecordContextDeliveryRequest,
        invocation_id=invocation,
        manifest=manifest,
        stage="prepared",
    )
    if stage != "prepared":
        _apply(
            case,
            RecordContextDeliveryRequest,
            invocation_id=invocation,
            manifest=manifest,
            stage="sent",
            request_sha256="A" * 64,
            request_bytes=100,
        )
    if stage in ("answered", "unknown"):
        _apply(
            case,
            RecordContextDeliveryRequest,
            invocation_id=invocation,
            manifest=manifest,
            stage=stage,
            usage_units=0 if stage == "answered" else None,
        )
    if manifest_deleted:
        _apply(case, DeleteKnowledgeRequest, record_id=manifest.record_id, expected_revision=1)
    before = read_execution(case[0], work, case[2])
    assert before.invocations == ()
    if stage == "prepared" and not manifest_deleted:
        _apply(
            case,
            StopAttemptRequest,
            work_id=work,
            attempt_id=attempt,
            session_id=session,
            outcome="interrupted",
            no_send_only=True,
        )
        assert read_execution(case[0], work, case[2]).attempts[-1].status == "interrupted"
    else:
        with pytest.raises(FoundationError, match="attempt_send_observed"):
            _apply(
                case,
                StopAttemptRequest,
                work_id=work,
                attempt_id=attempt,
                session_id=session,
                outcome="interrupted",
                no_send_only=True,
            )
        assert read_execution(case[0], work, case[2]) == before
    assert read_work(case[0], work, case[2]).state.acceptance is None
