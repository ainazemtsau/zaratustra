"""Pi capture keeps derivative provenance for addressed source deletion."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_binding import _ready
from tests.zaratustra.foundation.test_composition import _seed
from tests.zaratustra.foundation.test_continuation import assign
from tests.zaratustra.foundation.test_execution import ready, start
from zaratustra.foundation import (
    ContextState,
    CreateKnowledgeRequest,
    CreateResourceRequest,
    CreateWorkRequest,
    DeleteKnowledgeRequest,
    FoundationError,
    OutputContract,
    ResourceState,
    SourceState,
    WorkState,
    apply_operation,
    complete_deletions,
    read_execution,
    read_knowledge,
    read_work,
    search_knowledge,
    upgrade_binding_space,
    upgrade_child_execution_space,
    upgrade_composition_space,
    upgrade_continuation_space,
    upgrade_knowledge_space,
    upgrade_parent_execution_space,
    upgrade_plan_revision_space,
)
from zaratustra.pi_adapter import Bridge


def test_assigned_memory_writer_cannot_delete_owner_knowledge(tmp_path: Path) -> None:
    root, space, owner, activity_id, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    work_id, resource_id = uuid4(), uuid4()
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            work_id=work_id,
            state=WorkState(
                activity_id=activity_id,
                goal="Write a fictional memory note",
                expected_outputs=(OutputContract(slot="note", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    apply_operation(
        root,
        CreateResourceRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            work_id=work_id,
            resource_id=resource_id,
            state=ResourceState(label="Synthetic writer", root=tmp_path, limit_units=100),
        ),
        owner,
    )
    attempt_id, session_id, _ = assign(root, space, work_id, resource_id)
    writer = Bridge(
        root, owner, tmp_path, 100, assigned_attempt_id=attempt_id, assigned_session_id=session_id
    )
    writer.connect(session_id)
    writer.select(session_id, activity_id, work_id)
    source_id = uuid4()
    source = CreateKnowledgeRequest(
        operation_id=uuid4(),
        space_id=space,
        actor=owner.actor,
        record_id=source_id,
        state=SourceState(
            channel="document",
            connection="synthetic-writer",
            profile_revision=1,
            source_event_id="written-note",
            media_type="text/plain",
            capture="full",
            content=b"Fictional memory note",
        ),
    )
    writer.knowledge_operation(session_id, source.model_dump(mode="json"))
    deletion = DeleteKnowledgeRequest(
        operation_id=uuid4(),
        space_id=space,
        actor=owner.actor,
        record_id=source_id,
        expected_revision=1,
    )
    with pytest.raises(FoundationError, match="interactive owner path"):
        writer.knowledge_operation(session_id, deletion.model_dump(mode="json"))
    assert read_knowledge(root, source_id, owner).availability == "available"
    interactive = Bridge(root, owner, tmp_path, 100)
    owner_session = uuid4()
    interactive.connect(owner_session)
    interactive.knowledge_operation(owner_session, deletion.model_dump(mode="json"))
    assert read_knowledge(root, source_id, owner).availability == "deleted"


def test_captured_answer_depends_on_received_user_source(tmp_path: Path) -> None:
    root, space, owner, _, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    bridge = Bridge(root, owner, tmp_path, 1000)
    session_id = uuid4()
    bridge.connect(session_id)
    received = bridge.capture_source(
        session_id,
        channel="conversation_user",
        content="Private fictional phrase",
        source_event_id="user-one",
    )
    answer = bridge.capture_source(
        session_id,
        channel="conversation_assistant",
        content="Private fictional phrase repeated",
        source_event_id="answer-one",
    )
    received_id = UUID(str(cast(dict[str, object], received["result"])["record_id"]))
    answer_id = UUID(str(cast(dict[str, object], answer["result"])["record_id"]))
    applied = read_knowledge(root, answer_id, owner)
    assert isinstance(applied.state, SourceState)
    assert received_id in {ref.record_id for ref in applied.state.derived_from}
    apply_operation(
        root,
        DeleteKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=received_id,
            expected_revision=1,
        ),
        owner,
    )
    assert read_knowledge(root, answer_id, owner).availability == "unavailable"
    assert search_knowledge(root, owner, "Private fictional phrase")["items"] == []
    assert complete_deletions(root, owner).live_store_sanitized
    with pytest.raises(FoundationError, match="content_unavailable"):
        bridge.capture_source(
            session_id,
            channel="conversation_assistant",
            content="The old context still saw deleted text",
            source_event_id="blocked-answer",
        )
    clean_session = uuid4()
    bridge.connect(clean_session)
    bridge.capture_source(
        clean_session,
        channel="conversation_user",
        content="Begin a clean fictional conversation",
        source_event_id="clean-user",
    )
    clean_answer = bridge.capture_source(
        clean_session,
        channel="conversation_assistant",
        content="A new answer from the clean context",
        source_event_id="clean-answer",
    )
    clean_id = UUID(str(cast(dict[str, object], clean_answer["result"])["record_id"]))
    clean_state = read_knowledge(root, clean_id, owner).state
    assert isinstance(clean_state, SourceState)
    assert received_id not in {ref.record_id for ref in clean_state.derived_from}


def test_selected_work_compaction_keeps_exact_work_method_and_plan(tmp_path: Path) -> None:
    root, _, owner, activity_id, _, method, work_id, *_ = _seed(tmp_path)
    for upgrade in (
        upgrade_child_execution_space,
        upgrade_plan_revision_space,
        upgrade_parent_execution_space,
        upgrade_binding_space,
        upgrade_knowledge_space,
    ):
        upgrade(root, owner)
    bridge = Bridge(root, owner, tmp_path, 1000)
    session_id = uuid4()
    bridge.connect(session_id)
    bridge.select(session_id, activity_id, work_id)
    bridge.capture_source(
        session_id,
        channel="conversation_user",
        content="Continue the fictional packet",
        source_event_id="user-one",
    )
    bridge.prepare_context(session_id)
    compact = bridge.prepare_context(session_id, purpose="compaction-summary")
    packet = cast(dict[str, object], compact["packet"])
    current = read_execution(root, work_id, owner)
    assert current.composition is not None
    assert packet["work_address"] == f"{work_id}@{current.work.revision}"
    assert packet["activity_address"] == f"{activity_id}@{current.activity.revision}"
    assert packet["method_address"] == method.model_dump(mode="json")
    assert packet["plan_address"] == {
        "work_id": str(current.composition.parent_work_id),
        "revision": current.composition.plan_revision,
        "method": current.composition.method.model_dump(mode="json"),
    }
    manifest = read_knowledge(root, UUID(cast(str, compact["manifest_id"])), owner)
    assert isinstance(manifest.state, ContextState)
    assert manifest.state.work_id == work_id
    assert manifest.state.method == method
    assert manifest.state.plan_revision == current.composition.plan_revision
    assert any(
        ref.record_id == work_id and ref.revision == current.work.revision
        for ref in manifest.state.mandatory
    )
    assert any(
        ref.record_id == activity_id and ref.revision == current.activity.revision
        for ref in manifest.state.mandatory
    )
    delivery = bridge.context_delivery(
        session_id,
        {
            "invocation_id": str(uuid4()),
            "manifest_id": compact["manifest_id"],
            "manifest_revision": compact["manifest_revision"],
            "stage": "prepared",
        },
    )
    assert cast(dict[str, object], delivery["result"])["stage"] == "prepared"


def test_trial_send_cap_survives_bridge_restart_and_assigned_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, working, space_id, _, work_id, resource_id, owner = ready(tmp_path)
    for upgrade in (
        upgrade_continuation_space,
        upgrade_composition_space,
        upgrade_child_execution_space,
        upgrade_plan_revision_space,
        upgrade_parent_execution_space,
        upgrade_binding_space,
        upgrade_knowledge_space,
    ):
        upgrade(root, owner)
    monkeypatch.setenv("ZARA_TRIAL_MAX_TOTAL_SENDS", "2")
    activity_id = read_work(root, work_id, owner).state.activity_id

    for _ in range(2):
        bridge = Bridge(root, owner, working, 100)
        session_id = uuid4()
        bridge.connect(session_id)
        bridge.select(session_id, activity_id, work_id)
        manifest = bridge.prepare_context(session_id)
        bridge.context_delivery(
            session_id,
            {
                "invocation_id": str(uuid4()),
                "manifest_id": manifest["manifest_id"],
                "manifest_revision": manifest["manifest_revision"],
                "stage": "prepared",
            },
        )

    attempt_id, assigned_session_id = start(root, space_id, work_id, resource_id, owner)
    assigned = Bridge(
        root,
        owner,
        working,
        100,
        assigned_attempt_id=attempt_id,
        assigned_session_id=assigned_session_id,
    )
    assigned.connect(assigned_session_id)
    assigned.select(assigned_session_id, activity_id, work_id)
    manifest = assigned.prepare_context(assigned_session_id)
    with pytest.raises(FoundationError, match="trial_send_limit"):
        assigned.context_delivery(
            assigned_session_id,
            {
                "invocation_id": str(uuid4()),
                "manifest_id": manifest["manifest_id"],
                "manifest_revision": manifest["manifest_revision"],
                "stage": "prepared",
            },
        )


def test_large_context_keeps_full_source_and_reuses_exact_manifest(tmp_path: Path) -> None:
    root, _, owner, _, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    bridge = Bridge(root, owner, tmp_path)
    session_id = uuid4()
    bridge.connect(session_id)
    text = "Полный исходный материал. " * 5000
    captured = bridge.capture_source(
        session_id, channel="conversation_user", content=text, source_event_id="large-source"
    )
    first = bridge.prepare_context(session_id)
    assert cast(dict[str, object], first["packet"])["prompt_text"] == text
    assert bridge.prepare_context(session_id)["manifest_id"] == first["manifest_id"]
    source_id = UUID(str(cast(dict[str, object], captured["result"])["record_id"]))
    retained = read_knowledge(root, source_id, owner)
    assert isinstance(retained.state, SourceState)
    assert retained.state.content == text.encode()
    bridge.capture_source(
        session_id, channel="conversation_user", content="New exact source", source_event_id="next"
    )
    assert bridge.prepare_context(session_id)["manifest_id"] != first["manifest_id"]


def test_unlimited_conversation_keeps_usage_across_bridge_restart(tmp_path: Path) -> None:
    root, _, owner, _, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    for index in range(2):
        bridge = Bridge(root, owner, tmp_path)
        session_id = uuid4()
        bridge.connect(session_id)
        bridge.capture_source(
            session_id, channel="conversation_user", content="Continue", source_event_id=str(index)
        )
        manifest = bridge.prepare_context(session_id)
        common = {
            "invocation_id": str(uuid4()),
            "manifest_id": manifest["manifest_id"],
            "manifest_revision": manifest["manifest_revision"],
        }
        prepared = bridge.context_delivery(
            session_id, {**common, "stage": "prepared", "reserve_units": 30}
        )
        assert prepared["result"]
        bridge.context_delivery(
            session_id,
            {**common, "stage": "sent", "request_sha256": "A" * 64, "request_bytes": 123},
        )
        answered = bridge.context_delivery(
            session_id, {**common, "stage": "answered", "usage_units": 20000000}
        )
        assert answered["result"]


def test_saved_user_message_restores_manifest_without_duplicate_source(tmp_path: Path) -> None:
    root, _, owner, _, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    native_session = uuid4()
    restored = []
    for _ in range(2):
        bridge = Bridge(root, owner, tmp_path)
        session_id = uuid4()
        bridge.connect(session_id)
        receipt = bridge.capture_source(
            session_id,
            channel="conversation_user",
            content="Retained fictional user message",
            source_event_id="resume:saved-entry",
            input_source="session-resume",
            replay_session_id=native_session,
            limitations=("Restored from a saved Pi user message; not a new owner request",),
        )
        source_id = UUID(str(cast(dict[str, object], receipt["result"])["record_id"]))
        restored.append(source_id)
        manifest = bridge.prepare_context(session_id, purpose="compaction-summary")
        assert (
            cast(dict[str, object], manifest["packet"])["prompt_text"]
            == "Retained fictional user message"
        )
        source = read_knowledge(root, source_id, owner)
        assert isinstance(source.state, SourceState)
        assert source.state.sender == "pi-session-history"
        assert source.state.conversation_id == str(native_session)
    assert restored[0] == restored[1]
    items = cast(
        list[dict[str, object]],
        search_knowledge(root, owner, "Retained fictional user message")["items"],
    )
    assert len(items) == 1


def test_saved_message_replay_does_not_recreate_deleted_source(tmp_path: Path) -> None:
    root, space, owner, _, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    native_session = uuid4()
    bridge = Bridge(root, owner, tmp_path)
    session_id = uuid4()
    bridge.connect(session_id)
    captured = bridge.capture_source(
        session_id,
        channel="conversation_user",
        content="Fictional replay to be deleted",
        source_event_id="resume:saved-entry",
        input_source="session-resume",
        replay_session_id=native_session,
    )
    source_id = UUID(str(cast(dict[str, object], captured["result"])["record_id"]))
    apply_operation(
        root,
        DeleteKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            record_id=source_id,
            expected_revision=1,
        ),
        owner,
    )
    assert complete_deletions(root, owner).live_store_sanitized
    reopened = Bridge(root, owner, tmp_path)
    resumed = uuid4()
    reopened.connect(resumed)
    with pytest.raises(FoundationError, match="history_unavailable"):
        reopened.capture_source(
            resumed,
            channel="conversation_user",
            content="Fictional replay to be deleted",
            source_event_id="resume:saved-entry",
            input_source="session-resume",
            replay_session_id=native_session,
        )
    assert read_knowledge(root, source_id, owner).availability == "deleted"
    assert search_knowledge(root, owner, "Fictional replay to be deleted")["items"] == []
