"""Current conversation caches refresh before sends, without changing pinned Work inputs."""

from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_binding import _apply
from tests.zaratustra.foundation.test_memory import note, ready
from zaratustra.foundation import (
    ClaimState,
    CreateKnowledgeRequest,
    CreateWorkRequest,
    FoundationError,
    KnowledgeRef,
    MemoryMetadata,
    OutputContract,
    ReviseKnowledgeRequest,
    SourceState,
    WorkState,
    read_knowledge,
)
from zaratustra.pi_adapter import Bridge


def test_conversation_refreshes_cached_membership_and_fences_old_manifest(tmp_path: Path) -> None:
    """A tool cache can become stale between reading and HTTP, even without a selected Work."""
    root, space, owner, activity, other = ready(tmp_path)
    note(root, space, owner, "First selected fact", activity=activity)
    bridge = Bridge(root, owner, tmp_path)
    session = uuid4()
    bridge.connect(session)
    bridge.capture_source(
        session,
        channel="conversation_user",
        content="Read selected facts",
        source_event_id="fictional-request",
    )
    cached = bridge.knowledge_read(
        session,
        {
            "mode": "prepare_cache",
            "selectors": [
                {"activity_ids": [str(activity)], "topics": ["equipment"]},
            ],
        },
    )
    old = bridge.prepare_context(session)
    note(root, space, owner, "New selected fact", activity=activity)
    with pytest.raises(FoundationError, match="stale_context"):
        bridge.context_delivery(
            session,
            {
                "invocation_id": str(uuid4()),
                "manifest_id": old["manifest_id"],
                "manifest_revision": 1,
                "stage": "prepared",
                "reserve_units": 1,
            },
        )
    fresh = bridge.prepare_context(session)
    packet = cast(dict[str, Any], fresh["packet"])
    selected = packet["conversation_memory"][0]
    assert selected["selection_id"] != cached["selection_id"]
    assert "New selected fact" in selected["content_text"] and selected["content_complete"]
    note(root, space, owner, "An unrelated fact", activity=other)
    next_packet = cast(dict[str, Any], bridge.prepare_context(session)["packet"])
    assert next_packet["conversation_memory"][0]["selection_id"] == selected["selection_id"]
    manifest = read_knowledge(root, UUID(str(fresh["manifest_id"])), owner)
    assert manifest.availability == "available"
    reopened = Bridge(root, owner, tmp_path)
    new_session = uuid4()
    reopened.connect(new_session)
    reopened.capture_source(
        new_session,
        channel="conversation_user",
        content="Continue the saved conversation",
        source_event_id="fictional-resumed-request",
    )
    resumed = reopened.prepare_context(
        new_session,
        historical_memory=(KnowledgeRef(record_id=UUID(str(cached["selection_id"])), revision=1),),
    )
    resumed_packet = cast(dict[str, Any], resumed["packet"])
    assert resumed_packet["conversation_memory"][0]["selection_id"] == selected["selection_id"]
    assert "New selected fact" in resumed_packet["conversation_memory"][0]["content_text"]


def test_required_memory_scope_and_legacy_claim_delivery(tmp_path: Path) -> None:
    """Deliver common conditions and legacy claims without importing foreign conditions."""
    root, space, owner, activity, other = ready(tmp_path)
    required_ids = []
    for scope in (None, other):
        identifier = note(
            root, space, owner, "Fictional condition", activity=scope, topic="condition"
        )
        old = read_knowledge(root, identifier, owner).state
        assert isinstance(old, SourceState)
        _apply(
            root,
            space,
            owner,
            ReviseKnowledgeRequest,
            record_id=identifier,
            expected_revision=1,
            state=old.model_copy(
                update={
                    "memory": MemoryMetadata(
                        title="Condition", activity_id=scope, context_role="required"
                    )
                }
            ),
        )
        required_ids.append(identifier)
    legacy_id = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=legacy_id,
        state=ClaimState(
            proposition="Fictional legacy constraint",
            epistemic_kind="hypothesis",
            status="unsupported",
            scope_activity_id=activity,
            interpretation_basis="Fictional legacy classification",
        ),
    )
    work_id = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=work_id,
        state=WorkState(
            activity_id=activity,
            goal="Use applicable constraints",
            expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
        ),
    )
    bridge = Bridge(root, owner, tmp_path)
    session = uuid4()
    bridge.connect(session)
    bridge.select(session, activity, work_id)
    bridge.capture_source(
        session,
        channel="conversation_user",
        content="Continue the fictional Work",
        source_event_id="fictional-constraint-request",
    )
    packet = cast(dict[str, Any], bridge.prepare_context(session)["packet"])
    assert [entry["record_id"] for entry in packet["memory_constraints"]] == [str(required_ids[0])]
    assert [entry["record_id"] for entry in packet["claims"]] == [str(legacy_id)]
    assert str(required_ids[1]) not in str(packet["memory_constraints"])
