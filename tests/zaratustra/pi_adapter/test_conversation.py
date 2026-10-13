"""Consumed native origin and continuation effects through public Core."""

from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

import zaratustra.foundation as core
from zaratustra.pi_adapter import Bridge
from zaratustra.pi_adapter.__main__ import _prepare_space
from zaratustra.pi_adapter.conversation import conversation


def _case(tmp_path: Path) -> tuple[Bridge, UUID, UUID, UUID]:
    root = tmp_path / "space"
    root.mkdir()
    owner = _prepare_space(root, "owner", create=True)
    activity, work = uuid4(), uuid4()
    for request in (
        core.CreateActivityRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor=owner.actor,
            activity_id=activity,
            state=core.ActivityState(title="Fictional activity", goal="Keep observations"),
        ),
        core.CreateWorkRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor=owner.actor,
            work_id=work,
            state=core.WorkState(
                activity_id=activity,
                goal="First useful observation",
                expected_outputs=(core.OutputContract(slot="result", media_type="text/plain"),),
            ),
        ),
    ):
        core.apply_operation(root, request, owner)
    bridge = Bridge(root, owner, tmp_path)
    session = uuid4()
    bridge.connect(session)
    return bridge, session, activity, work


def test_queued_receipt_cannot_replace_consumed_owner_origin(tmp_path: Path) -> None:
    bridge, session, _, _ = _case(tmp_path)
    consumed = bridge.capture_source(
        session,
        channel="conversation_user",
        content="Actual answer",
        source_event_id="native:delivered",
        input_source="interactive",
    )["source_ref"]
    bridge.bind_request_origin(session, {"origin": "owner", "sources": [consumed]})
    bridge.capture_source(
        session,
        channel="conversation_user",
        content="Queued later request",
        source_event_id="queued",
        input_source="received-interactive",
    )
    assert bridge._fresh_user_source(session)[1] == "Actual answer"
    packet = cast(dict[str, Any], bridge.prepare_context(session)["packet"])
    assert packet["request_origin"]["sources"] == [consumed]
    assert "Queued later request" not in str(packet)
    bridge.bind_request_origin(session, {"origin": "host", "sources": []})
    with pytest.raises(core.FoundationError, match="delivered owner"):
        bridge._fresh_user_source(session)


def test_several_consumed_sources_need_addressed_choice(tmp_path: Path) -> None:
    bridge, session, _, _ = _case(tmp_path)
    sources = cast(
        list[dict[str, Any]],
        [
            bridge.capture_source(
                session,
                channel="conversation_user",
                content=text,
                source_event_id=f"native:{uuid4()}",
                input_source="interactive",
            )["source_ref"]
            for text in ("One actual message", "Another actual message")
        ],
    )
    bridge.bind_request_origin(session, {"origin": "owner", "sources": sources})
    with pytest.raises(core.FoundationError, match="delivered owner"):
        bridge._fresh_user_source(session)
    assert bridge._fresh_user_source(session, sources[0])[1] == "One actual message"
    assert bridge._fresh_user_source(session, sources[1])[1] == "Another actual message"


def test_existing_work_selection_neither_duplicates_nor_accepts(tmp_path: Path) -> None:
    bridge, session, activity, work = _case(tmp_path)
    view = next(
        item
        for item in cast(
            list[dict[str, Any]], conversation(bridge, session, {"mode": "catalog"})["items"]
        )
        if item["work_id"] == str(work)
    )
    source = bridge.capture_source(
        session,
        channel="conversation_user",
        content="Start that work",
        source_event_id="native:choose",
        input_source="interactive",
    )["source_ref"]
    bridge.bind_request_origin(session, {"origin": "owner", "sources": [source]})
    before = core.read_work(bridge.path, work, bridge.authority)
    selected = conversation(
        bridge, session, {"mode": "use_existing_work", "action_ref": view["ref"]}
    )
    assert selected["selection"] == {"activity_id": str(activity), "work_id": str(work)}
    assert selected["accepted"] is False
    assert core.read_work(bridge.path, work, bridge.authority) == before
    assert (
        len(
            [
                item
                for item in core.inspect_space(bridge.path, bridge.authority).records
                if item.kind == "work"
            ]
        )
        == 1
    )


def test_old_goal_cannot_answer_question_opened_by_same_tool_chain(tmp_path: Path) -> None:
    bridge, session, _, _ = _case(tmp_path)
    original = bridge.capture_source(
        session,
        channel="conversation_user",
        content="Make an activity",
        source_event_id="native:goal",
        input_source="interactive",
    )["source_ref"]
    bridge.bind_request_origin(session, {"origin": "owner", "sources": [original]})
    setup, activity = uuid4(), uuid4()
    bridge.activity_setup(
        session,
        {
            "action": "begin",
            "setup_id": str(setup),
            "activity_id": str(activity),
            "title": "Second activity",
            "goal": "Keep notes",
        },
    )
    bridge.activity_setup(
        session, {"action": "question", "setup_id": str(setup), "question": "Which period?"}
    )
    with pytest.raises(core.FoundationError, match="before|after|question"):
        bridge.activity_setup(session, {"action": "answer", "setup_id": str(setup)})
    assert (
        core.read_activity_setup(bridge.path, setup, bridge.authority).state.phase == "needs_input"
    )


def test_discovery_does_not_load_unrelated_large_original(tmp_path: Path) -> None:
    bridge, session, activity, _ = _case(tmp_path)
    artifact, work = uuid4(), uuid4()
    core.apply_operation(
        bridge.path,
        core.CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=bridge.authority.space_id,
            actor=bridge.authority.actor,
            artifact_id=artifact,
            media_type="text/plain",
            content=b"unrelated original " * 100000,
        ),
        bridge.authority,
    )
    core.apply_operation(
        bridge.path,
        core.CreateWorkRequest(
            operation_id=uuid4(),
            space_id=bridge.authority.space_id,
            actor=bridge.authority.actor,
            work_id=work,
            state=core.WorkState(
                activity_id=activity,
                goal="Other project",
                inputs=(core.ArtifactRef(artifact_id=artifact, revision=1),),
                expected_outputs=(core.OutputContract(slot="result", media_type="text/plain"),),
            ),
        ),
        bridge.authority,
    )
    source = bridge.capture_source(
        session,
        channel="conversation_user",
        content="What next?",
        source_event_id="native:status",
        input_source="interactive",
    )["source_ref"]
    bridge.bind_request_origin(session, {"origin": "owner", "sources": [source]})
    bridge.context_max_bytes = 12000
    packet = bridge.prepare_context(session)
    assert cast(int, packet["byte_count"]) < 12000
    assert "unrelated original " not in str(packet)


def test_host_event_cannot_create_work_under_owner_grant(tmp_path: Path) -> None:
    bridge, session, activity, _ = _case(tmp_path)
    request = core.CreateWorkRequest(
        operation_id=uuid4(),
        space_id=bridge.authority.space_id,
        actor=bridge.authority.actor,
        work_id=uuid4(),
        state=core.WorkState(
            activity_id=activity,
            goal="Forbidden host duplicate",
            expected_outputs=(core.OutputContract(slot="result", media_type="text/plain"),),
        ),
    )
    bridge.bind_request_origin(session, {"origin": "host", "sources": []})
    with pytest.raises(core.FoundationError, match="read-only"):
        bridge.development_operation(session, request.model_dump(mode="json"))
    owner = bridge.capture_source(
        session,
        channel="conversation_user",
        content="Create an ordinary Work",
        source_event_id="native:allow",
        input_source="interactive",
    )["source_ref"]
    bridge.bind_request_origin(session, {"origin": "owner", "sources": [owner]})
    bridge.development_operation(session, request.model_dump(mode="json"))
    assert (
        core.read_work(bridge.path, request.work_id, bridge.authority).state.goal
        == "Forbidden host duplicate"
    )


@pytest.mark.parametrize("kind", ["create_knowledge", "revise_knowledge"])
@pytest.mark.parametrize("marker", ["conversation_final", "conversation_terminal"])
def test_model_memory_cannot_forge_native_final_proof(
    tmp_path: Path, kind: str, marker: str
) -> None:
    bridge, session, _, _ = _case(tmp_path)
    owner = bridge.capture_source(
        session,
        channel="conversation_user",
        content="Keep a note",
        source_event_id="native:note",
        input_source="interactive",
    )["source_ref"]
    bridge.bind_request_origin(session, {"origin": "owner", "sources": [owner]})
    with pytest.raises(core.FoundationError, match="Native final proof"):
        bridge.knowledge_operation(
            session,
            {
                "kind": kind,
                "record_id": str(uuid4()),
                "state": {"kind": "source", "sender": "pi-assistant", marker: True},
            },
        )


def test_unproven_old_attempt_restores_free_conversation_before_selection(tmp_path: Path) -> None:
    bridge, session, activity, work = _case(tmp_path)
    bridge.select(session, activity, work)
    started = bridge.start_attempt(session, interrupt_previous=False)
    restored = conversation(bridge, session, {"mode": "restore", "work_id": str(work)})
    assert restored["selection"] is None and restored["completed_observed"] is False
    source = bridge.capture_source(
        session,
        channel="conversation_user",
        content="What next?",
        source_event_id="native:next",
        input_source="interactive",
    )["source_ref"]
    bridge.bind_request_origin(session, {"origin": "owner", "sources": [source]})
    packet = cast(dict[str, Any], bridge.prepare_context(session)["packet"])
    assert packet["recovery_obstacle"]["work_id"] == str(work)
    assert "work" not in packet
    action = next(
        item
        for item in cast(
            list[dict[str, Any]], conversation(bridge, session, {"mode": "catalog"})["items"]
        )
        if item["work_id"] == str(work)
    )
    with pytest.raises(core.FoundationError, match="Old execution remains active"):
        conversation(bridge, session, {"mode": "use_existing_work", "action_ref": action["ref"]})
    assert bridge._session(session) is None
    assert any(
        item.status == "active" and str(item.attempt_id) == started["attempt_id"]
        for item in core.read_execution(bridge.path, work, bridge.authority).attempts
    )


@pytest.mark.parametrize("variant", ["valid", "tool", "unknown"])
def test_native_completion_uses_core_final_proof(tmp_path: Path, variant: str) -> None:
    from tests.zaratustra.foundation.test_conversations import _ordinary_final_case

    case, work_id, attempt_id, session_id = _ordinary_final_case(tmp_path, variant)
    work = core.read_work(case[0], work_id, case[2])
    bridge = Bridge(case[0], case[2], tmp_path)
    bridge.connect(session_id)
    bridge.select(session_id, work.state.activity_id, work_id)
    outcome = conversation(bridge, session_id, {"mode": "restore", "work_id": str(work_id)})
    attempt = next(
        item
        for item in core.read_execution(case[0], work_id, case[2]).attempts
        if item.attempt_id == attempt_id
    )
    if variant == "valid":
        assert outcome["completed_observed"] is True
        assert attempt.status == "completed" and bridge._session(session_id) is not None
    else:
        assert outcome["completed_observed"] is False and outcome["selection"] is None
        assert attempt.status == "active" and bridge._session(session_id) is None
    assert core.read_work(case[0], work_id, case[2]) == work


@pytest.mark.parametrize("text", ["", "\u0085 \n", "Visible final response"])
def test_native_terminal_capture_preserves_exact_visible_bytes(tmp_path: Path, text: str) -> None:
    bridge, session, activity, work = _case(tmp_path)
    bridge.select(session, activity, work)
    manifest = bridge.prepare_context(session)
    reference = core.KnowledgeRef(record_id=UUID(str(manifest["manifest_id"])), revision=1)
    captured = bridge.capture_source(
        session,
        channel="conversation_assistant",
        content=text,
        source_event_id="native-final",
        final_manifest=reference,
        conversation_terminal={
            "invocation_id": str(uuid4()),
            "manifest": reference.model_dump(mode="json"),
            "assistant_entry_id": "native-final",
            "native_outcome": "completed",
            "stop_reason": "stop",
        },
    )
    source_ref = core.KnowledgeRef.model_validate(captured["source_ref"])
    source = core.read_knowledge(bridge.path, source_ref.record_id, bridge.authority).state
    assert isinstance(source, core.SourceState)
    assert source.capture == "full" and source.content == text.encode("utf-8")
    assert source.conversation_final == bool(text.strip())
    assert source.conversation_terminal is not None
    assert source.conversation_terminal.manifest == reference


def test_duplicate_native_terminal_callbacks_reuse_receipts_and_repair_permission(
    tmp_path: Path,
) -> None:
    from tests.zaratustra.foundation.test_conversations import (
        _claim,
        _invocation,
        _question,
        _terminal_original,
    )

    case, action = _question(tmp_path)
    fields = _claim(case, action)
    manifest, invocation = _invocation(case, action, fields, "answered")
    source, entry = _terminal_original(case, fields, manifest, invocation, b"")
    bridge = Bridge(case[0], case[2], tmp_path)
    session = fields["session_id"]
    bridge.connect(session)
    conversation(bridge, session, {"mode": "host", "host_id": "host-one", "branch_id": "main"})
    identity = {
        "delivery_id": str(fields["delivery_id"]),
        "action_ref": action.ref.model_dump(mode="json"),
        "host_id": "host-one",
        "branch_id": "main",
    }
    observed = {
        **identity,
        "mode": "observe_terminal",
        "manifest": manifest.model_dump(mode="json"),
        "invocation_id": str(invocation),
        "assistant_source": source.model_dump(mode="json"),
        "assistant_entry_id": entry,
    }
    first = conversation(bridge, session, observed)
    assert conversation(bridge, session, observed) == first
    repair = {**identity, "mode": "repair_response"}
    permission = conversation(bridge, session, repair)
    assert conversation(bridge, session, repair) == permission
    assert (
        core.read_conversation_delivery(case[0], fields["delivery_id"], case[2]).repair_count == 1
    )


def test_unknown_terminal_clears_host_task_before_an_independent_owner_topic(
    tmp_path: Path,
) -> None:
    from tests.zaratustra.foundation.test_conversations import (
        _apply,
        _claim,
        _invocation,
        _question,
        _terminal_original,
    )

    case, action = _question(tmp_path)
    fields = _claim(case, action)
    manifest, invocation = _invocation(case, action, fields, "sent")
    _apply(
        case,
        core.RecordContextDeliveryRequest,
        invocation_id=invocation,
        manifest=manifest,
        stage="unknown",
    )
    source, entry = _terminal_original(
        case, fields, manifest, invocation, b"", outcome="error", stop_reason="error"
    )
    bridge = Bridge(case[0], case[2], tmp_path)
    session = fields["session_id"]
    bridge.connect(session)
    conversation(bridge, session, {"mode": "host", "host_id": "host-one", "branch_id": "main"})
    bridge.conversation_actions[session] = action.ref
    bridge.bind_request_origin(session, {"origin": "host", "sources": []})
    receipt = conversation(
        bridge,
        session,
        {
            "mode": "observe_terminal",
            "delivery_id": str(fields["delivery_id"]),
            "action_ref": action.ref.model_dump(mode="json"),
            "host_id": "host-one",
            "branch_id": "main",
            "manifest": manifest.model_dump(mode="json"),
            "invocation_id": str(invocation),
            "assistant_source": source.model_dump(mode="json"),
            "assistant_entry_id": entry,
        },
    )
    assert cast(dict[str, Any], receipt["result"])["status"] == "unknown"
    assert session not in bridge.conversation_actions
    # A stale host cache cannot inject a terminal task even on a host-origin read.
    bridge.conversation_actions[session] = action.ref
    packet = cast(dict[str, Any], bridge.prepare_context(session)["packet"])
    assert "conversation_event" not in packet and "conversation_task" not in packet
    original = bridge.capture_source(
        session,
        channel="conversation_user",
        content="Different topic",
        source_event_id="native:other-topic",
        input_source="interactive",
    )["source_ref"]
    bridge.bind_request_origin(session, {"origin": "owner", "sources": [original]})
    packet = cast(dict[str, Any], bridge.prepare_context(session)["packet"])
    assert packet["request_origin"]["kind"] == "owner"
    assert "conversation_event" not in packet and "conversation_task" not in packet
    assert packet["conversation_delivery_outcomes"][0]["response_outcome"] == "unknown"


@pytest.mark.parametrize("variant", ["valid", "tool", "unknown"])
def test_cleanup_rechecks_saved_final_or_preserves_observed_execution(
    tmp_path: Path,
    variant: str,
) -> None:
    from tests.zaratustra.foundation.test_conversations import _ordinary_final_case

    case, work, attempt, session = _ordinary_final_case(tmp_path, variant)
    core.upgrade_delivery_correlation_space(case[0], case[2])
    before = core.read_work(case[0], work, case[2])
    bridge = Bridge(case[0], case[2], tmp_path)
    bridge.connect(session)
    bridge.select(session, before.state.activity_id, work)
    restored = conversation(
        bridge,
        session,
        {
            "mode": "restore",
            "work_id": str(work),
            "attempt_id": str(attempt),
            "cleanup_unsent": True,
        },
    )
    execution = core.read_execution(case[0], work, case[2])
    saved = next(item for item in execution.attempts if item.attempt_id == attempt)
    assert core.read_work(case[0], work, case[2]) == before
    if variant == "valid":
        assert saved.status == "completed" and restored["completed_observed"] is True
    else:
        assert saved.status == "active" and restored["selection"] is None
        assert restored["completed_observed"] is False


def test_cleanup_can_interrupt_only_the_exact_attempt_with_no_provider_send(tmp_path: Path) -> None:
    bridge, session, activity, work = _case(tmp_path)
    bridge.select(session, activity, work)
    started = bridge.start_attempt(session, interrupt_previous=False)
    with pytest.raises(core.FoundationError, match="exact current Attempt"):
        conversation(
            bridge, session, {"mode": "restore", "work_id": str(work), "cleanup_unsent": True}
        )
    restored = conversation(
        bridge,
        session,
        {
            "mode": "restore",
            "work_id": str(work),
            "attempt_id": started["attempt_id"],
            "cleanup_unsent": True,
        },
    )
    assert restored["interrupted_unsent"] is True and restored["completed_observed"] is False
    attempt = core.read_execution(bridge.path, work, bridge.authority).attempts[-1]
    assert attempt.status == "interrupted"
    assert core.read_work(bridge.path, work, bridge.authority).state.acceptance is None
