"""Pulse reads changed Core addresses without mutating or deciding their outcome."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from tests.zaratustra.foundation.test_binding import _ready
from zaratustra.foundation import (
    CreateKnowledgeRequest,
    SourceState,
    apply_operation,
    pulse_space,
    read_space,
    upgrade_knowledge_space,
)


def test_pulse_checkpoint_and_prior_address(tmp_path: Path) -> None:
    root, space, owner, _, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    before = read_space(root).state_revision
    source_id = uuid4()
    apply_operation(
        root,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            record_id=source_id,
            state=SourceState(
                channel="conversation_user",
                connection="pulse-test",
                profile_revision=1,
                source_event_id="source-after-checkpoint",
                media_type="text/plain",
                capture="full",
                content=b"Fictional new material",
            ),
        ),
        owner,
    )
    first = pulse_space(root, owner, checkpoint=before)
    assert source_id in first.checked_records
    assert first.findings == ()
    assert first.through_revision == read_space(root).state_revision
    second = pulse_space(
        root, owner, checkpoint=first.through_revision, previous_addresses=(source_id,)
    )
    assert source_id in second.checked_records
    assert second.findings == ()
    assert second.through_revision == first.through_revision
