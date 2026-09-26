"""Pi capture keeps derivative provenance for addressed source deletion."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from tests.zaratustra.foundation.test_binding import _ready
from zaratustra.foundation import (
    DeleteKnowledgeRequest,
    SourceState,
    apply_operation,
    complete_deletions,
    read_knowledge,
    search_knowledge,
    upgrade_knowledge_space,
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
