"""Manual exchange retains exact scope, originals and versions without acceptance."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_binding import _ready
from zaratustra.foundation import (
    CreateWorkRequest,
    DeleteKnowledgeRequest,
    FoundationError,
    HandoffState,
    KnowledgeRef,
    OutputContract,
    SourceState,
    WorkState,
    apply_operation,
    read_knowledge,
    read_work,
    upgrade_knowledge_space,
)
from zaratustra.pi_adapter import Bridge, ManualExchange


def test_exchange_for_two_activities_retains_exact_return_versions(tmp_path: Path) -> None:
    root, space, owner, activity, other = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    work_id = uuid4()
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            work_id=work_id,
            state=WorkState(
                activity_id=activity,
                goal="Review a fictional pump",
                expected_outputs=(OutputContract(slot="review", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    exchange = ManualExchange(root, owner)
    operation_id = uuid4()
    first = exchange.prepare(operation_id, activity, work_id=work_id, external_tool="Chat A")
    repeated = exchange.prepare(operation_id, activity, work_id=work_id, external_tool="Chat A")
    assert repeated == first
    handoff = read_knowledge(root, UUID(str(first["record_id"])), owner, revision=1)
    assert isinstance(handoff.state, HandoffState)
    assert {ref.record_id for ref in handoff.state.included} == {activity, work_id}
    assert handoff.state.status == "prepared"
    other_document = exchange.prepare(uuid4(), other, external_tool="Chat B")
    other_handoff = read_knowledge(root, UUID(str(other_document["record_id"])), owner)
    assert isinstance(other_handoff.state, HandoffState)
    assert {ref.record_id for ref in other_handoff.state.included} == {other}
    assert str(work_id) not in str(other_document["content_text"])

    original = "\ufeff  Неполный свободный ответ: fictional pump\r\n".encode()
    returned = exchange.receive(
        uuid4(),
        activity,
        work_id=work_id,
        origin="Chat A",
        content=original,
        reply_to=KnowledgeRef(record_id=handoff.record_id, revision=1),
        sender="external-model",
    )
    source_id = UUID(str(returned["record_id"]))
    revision_id = uuid4()
    revised = exchange.receive(
        revision_id,
        activity,
        work_id=work_id,
        origin="Chat A",
        content=b"New proposal",
        previous_source=KnowledgeRef(record_id=source_id, revision=1),
    )
    reopened = ManualExchange(root, owner)
    old = read_knowledge(root, source_id, owner, revision=1)
    revised_id = UUID(str(revised["record_id"]))
    current = read_knowledge(root, revised_id, owner, revision=1)
    assert isinstance(old.state, SourceState) and old.state.content == original
    assert isinstance(current.state, SourceState) and current.state.content == b"New proposal"
    assert revised_id != source_id
    assert current.state.sender is None
    assert current.state.derived_from == (KnowledgeRef(record_id=source_id, revision=1),)
    assert str(reopened.read(source_id, revision=1)["content_text"]).encode() == original
    assert reopened.read(revised_id, revision=1) == revised
    assert (
        reopened.receive(
            revision_id,
            activity,
            work_id=work_id,
            origin="Chat A",
            content=b"New proposal",
            previous_source=KnowledgeRef(record_id=source_id, revision=1),
        )
        == revised
    )
    work = read_work(root, work_id, owner)
    assert work.state.status == "proposed" and work.state.acceptance is None
    assert work.state.linked_outputs == ()


def test_exchange_rejects_wrong_scope_and_keeps_original_source(tmp_path: Path) -> None:
    root, _, owner, activity, other = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    exchange = ManualExchange(root, owner)
    document = exchange.prepare(uuid4(), activity, external_tool="Fictional chat")
    with pytest.raises(FoundationError, match="outside this Activity"):
        exchange.receive(
            uuid4(),
            other,
            origin="Fictional chat",
            content=b"Other reply",
            reply_to=KnowledgeRef(record_id=UUID(str(document["record_id"])), revision=1),
        )
    original = exchange.receive(uuid4(), activity, origin="Fictional chat", content=b"First")
    source_id = UUID(str(original["record_id"]))
    second = exchange.receive(
        uuid4(),
        activity,
        origin="Fictional chat",
        content=b"Second",
        previous_source=KnowledgeRef(record_id=source_id, revision=1),
    )
    with pytest.raises(FoundationError, match="different origin or scope"):
        exchange.receive(
            uuid4(),
            other,
            origin="Fictional chat",
            content=b"Moved",
            previous_source=KnowledgeRef(record_id=source_id, revision=1),
        )
    assert exchange.read(source_id, revision=1)["content_text"] == "First"
    assert exchange.read(UUID(str(second["record_id"])), revision=1)["content_text"] == "Second"


def test_bridge_activity_exchange_and_read_need_no_work_selection(tmp_path: Path) -> None:
    root, _, owner, activity, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    bridge = Bridge(root, owner, tmp_path)
    session = uuid4()
    bridge.connect(session)
    request: dict[str, object] = {
        "mode": "prepare",
        "activity_id": str(activity),
        "external_tool": "Fictional chat",
        "operation_key": "stable-tool-call",
    }
    first = bridge.manual_exchange(session, request)
    assert bridge.manual_exchange(session, request) == first
    with pytest.raises(FoundationError, match="Explicit Work also needs its Activity"):
        bridge.manual_exchange(session, {**request, "activity_id": None, "work_id": str(uuid4())})
    incoming: dict[str, object] = {
        "mode": "import",
        "activity_id": str(activity),
        "origin": "Fictional chat",
        "operation_key": "stable-import",
        "content_base64": "RnJlZSB0ZXh0",
    }
    source = bridge.manual_exchange(session, incoming)
    assert bridge.manual_exchange(session, incoming) == source
    reopened = uuid4()
    bridge.connect(reopened)
    saved = bridge.manual_exchange(
        reopened, {"mode": "read", "record_id": source["record_id"], "revision": 1}
    )
    assert saved == source and saved["content_text"] == "Free text"


def test_exchange_read_keeps_answer_provenance_and_deletion_dependency(tmp_path: Path) -> None:
    root, space, owner, activity, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    bridge = Bridge(root, owner, tmp_path)
    session = uuid4()
    bridge.connect(session)
    original = bridge.manual_exchange(
        session,
        {
            "mode": "import",
            "activity_id": str(activity),
            "origin": "Fictional chat",
            "content_base64": "UHJpdmF0ZSBmaWN0aW9uYWwgcHJvcG9zYWw=",
            "operation_key": "import-file",
        },
    )
    source_id = UUID(str(original["record_id"]))
    acknowledgement = bridge.capture_source(
        session,
        channel="conversation_assistant",
        content="Saved the file",
        source_event_id="import-acknowledgement",
    )
    acknowledgement_id = UUID(str(cast(dict[str, object], acknowledgement["result"])["record_id"]))
    saved_ack = read_knowledge(root, acknowledgement_id, owner)
    assert isinstance(saved_ack.state, SourceState) and saved_ack.state.derived_from == ()
    bridge.manual_exchange(session, {"mode": "read", "record_id": str(source_id), "revision": 1})
    captured = bridge.capture_source(
        session,
        channel="conversation_assistant",
        content="An answer based on the private fictional proposal",
        source_event_id="exchange-answer",
    )
    answer_id = UUID(str(cast(dict[str, object], captured["result"])["record_id"]))
    answer = read_knowledge(root, answer_id, owner)
    assert isinstance(answer.state, SourceState)
    assert KnowledgeRef(record_id=source_id, revision=1) in answer.state.derived_from
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
    assert read_knowledge(root, answer_id, owner).availability == "unavailable"
    assert read_knowledge(root, acknowledgement_id, owner).availability == "available"
