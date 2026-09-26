"""Pi capture keeps derivative provenance for addressed source deletion."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from tests.zaratustra.foundation.test_binding import _ready
from tests.zaratustra.foundation.test_composition import _seed
from zaratustra.foundation import (
    ContextState,
    DeleteKnowledgeRequest,
    SourceState,
    apply_operation,
    complete_deletions,
    read_execution,
    read_knowledge,
    search_knowledge,
    upgrade_binding_space,
    upgrade_child_execution_space,
    upgrade_knowledge_space,
    upgrade_parent_execution_space,
    upgrade_plan_revision_space,
)
from zaratustra.pi_adapter import Bridge


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
