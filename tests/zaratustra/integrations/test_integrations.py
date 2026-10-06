"""Typed technical operations without hardcoded service names or user topics."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from tests.zaratustra.foundation.test_binding import _apply, _ready
from zaratustra.foundation import (
    ActivityState,
    CreateGrantRequest,
    CreateKnowledgeRequest,
    CreateWorkRequest,
    FoundationError,
    GrantState,
    HandoffState,
    KnowledgeRef,
    OutputContract,
    ReviseActivityRequest,
    SourceState,
    WorkState,
    authorize_local,
    read_activity,
    read_knowledge,
    read_space,
    read_work,
    upgrade_knowledge_space,
)
from zaratustra.integrations import (
    IntegrationRegistry,
    IntegrationResult,
    ManualExchange,
    Operation,
    Parameters,
    installed_integrations,
)
from zaratustra.pi_adapter import Bridge


def invoke(
    registry: IntegrationRegistry,
    operation: str,
    arguments: dict[str, Any],
    operation_id: UUID | None = None,
) -> dict[str, object]:
    return registry.execute(
        operation_id or uuid4(), "manual", operation, arguments, contract_version=1
    ).output


def test_another_adapter_uses_its_own_typed_operations() -> None:
    class Echo(Parameters):
        value: int

    calls: list[int] = []

    def echo(_operation_id: UUID, args: BaseModel) -> IntegrationResult:
        value = cast(Echo, args).value
        calls.append(value)
        return IntegrationResult({"echo": value})

    registry = IntegrationRegistry(
        {"fictional-local": {"echo": Operation("Echo a value", "read only", Echo, echo)}}
    )
    contract = registry.contract("fictional-local", "echo")
    schema = cast(dict[str, Any], contract["schema"])
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["value"]
    assert registry.execute(
        uuid4(), "fictional-local", "echo", {"value": 9}, contract_version=1
    ).output == {"echo": 9}
    for adapter, operation, arguments, version, error in (
        ("not-installed", "echo", {"value": 1}, 1, "unsupported_operation"),
        ("fictional-local", "send", {"value": 1}, 1, "unsupported_operation"),
        ("fictional-local", "echo", {"value": 1}, 2, "unsupported_contract"),
        ("fictional-local", "echo", {"value": 1}, True, "unsupported_contract"),
        ("fictional-local", "echo", {"value": "invalid"}, 1, "invalid_request"),
        ("fictional-local", "echo", {"value": 1, "actor": "owner"}, 1, "invalid_request"),
    ):
        with pytest.raises(FoundationError, match=error):
            registry.execute(uuid4(), adapter, operation, arguments, contract_version=version)
    assert calls == [9]


def test_custom_setup_context_and_unstructured_return_survive_reopening(tmp_path: Path) -> None:
    root, space, owner, activity, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    work = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=work,
        state=WorkState(
            activity_id=activity,
            goal="A fictional broad research task",
            expected_outputs=(OutputContract(slot="note", media_type="text/plain"),),
        ),
    )
    registry = installed_integrations(root, owner)
    context = invoke(
        registry,
        "retain_text",
        {
            "activity_id": str(activity),
            "origin": "Fictional article",
            "content_text": "Exact context for a freely chosen subject.",
        },
    )
    context_ref = KnowledgeRef(record_id=UUID(str(context["record_id"])), revision=1)
    document = "Discuss any fictional garden idea.\nAsk for missing observations.\n"
    arguments: dict[str, Any] = {
        "activity_id": str(activity),
        "work_id": str(work),
        "external_tool": "A previously unknown service",
        "document_text": document,
        "expected_return": "The person's chosen discussion result",
        "context": [context_ref.model_dump(mode="json")],
    }
    operation = uuid4()
    prepared = invoke(registry, "prepare_document", arguments, operation)
    assert prepared == invoke(registry, "prepare_document", arguments, operation)
    handoff_id = UUID(str(prepared["record_id"]))
    state = read_knowledge(root, handoff_id, owner).state
    assert isinstance(state, HandoffState)
    assert state.document == document.encode()
    assert state.included[-1] == context_ref
    assert state.status == "prepared" and state.transfer_source is None
    with pytest.raises(FoundationError, match="operation_conflict"):
        invoke(registry, "prepare_document", {**arguments, "document_text": "Changed"}, operation)

    # A malformed external package is data, not an invalid internal operation.
    original = "\ufeff  No header, no date. {broken JSON!\r\nПредложение 🙂\n"
    returned = invoke(
        registry,
        "retain_text",
        {
            "activity_id": str(activity),
            "work_id": str(work),
            "origin": "A previously unknown service",
            "content_text": original,
            "reply_to": {"record_id": str(handoff_id), "revision": 1},
        },
    )
    assert "content_text" not in returned
    source_id = UUID(str(returned["record_id"]))
    saved = read_knowledge(root, source_id, owner).state
    assert isinstance(saved, SourceState) and saved.content == original.encode()
    assert saved.derived_from == (KnowledgeRef(record_id=handoff_id, revision=1),)
    registry = installed_integrations(root, owner)
    offset = 0
    parts: list[str] = []
    while True:
        page = invoke(
            registry,
            "read_document",
            {
                "record_id": str(source_id),
                "revision": 1,
                "offset": offset,
                "max_bytes": 11,
            },
        )
        parts.append(str(page["content_text"]))
        assert "content_base64" not in page
        assert len(parts[-1].encode()) <= 11
        if page["next_offset"] is None:
            break
        offset = int(str(page["next_offset"]))
    assert "".join(parts) == original
    assert returned["sha256"] == hashlib.sha256(original.encode()).hexdigest().upper()
    assert read_work(root, work, owner).state.acceptance is None
    assert read_work(root, work, owner).state.linked_outputs == ()


def test_reply_accepts_source_evidence_but_not_foreign_activity_or_work(tmp_path: Path) -> None:
    root, space, owner, activity, other = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    exchange = ManualExchange(root, owner)
    own_source = exchange.receive(uuid4(), activity, origin="Article", content=b"Context")
    foreign_source = exchange.receive(uuid4(), other, origin="Article", content=b"Other context")
    work = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=work,
        state=WorkState(
            activity_id=activity,
            goal="Another Work",
            expected_outputs=(OutputContract(slot="note", media_type="text/plain"),),
        ),
    )
    for ref, allowed in (
        (KnowledgeRef(record_id=UUID(str(own_source["record_id"])), revision=1), True),
        (KnowledgeRef(record_id=UUID(str(foreign_source["record_id"])), revision=1), False),
        (KnowledgeRef(record_id=other, revision=1), False),
        (KnowledgeRef(record_id=work, revision=1), False),
    ):
        handoff_id = uuid4()
        _apply(
            root,
            space,
            owner,
            CreateKnowledgeRequest,
            record_id=handoff_id,
            state=HandoffState(
                subject="Existing Core handoff",
                document=b"Discuss the supplied material",
                media_type="text/plain",
                expected_return="A discussion",
                included=(KnowledgeRef(record_id=activity, revision=1), ref),
                status="prepared",
                basis_state_revision=read_space(root).state_revision,
            ),
        )
        reply_to = KnowledgeRef(record_id=handoff_id, revision=1)
        if allowed:
            result = exchange.receive(
                uuid4(), activity, origin="Chat", content=b"Reply", reply_to=reply_to
            )
            saved = read_knowledge(root, UUID(str(result["record_id"])), owner).state
            assert isinstance(saved, SourceState) and saved.derived_from == (reply_to,)
        else:
            with pytest.raises(FoundationError, match="wrong_work"):
                exchange.receive(
                    uuid4(), activity, origin="Chat", content=b"Reply", reply_to=reply_to
                )


def test_document_replay_keeps_original_activity_basis(tmp_path: Path) -> None:
    root, space, owner, activity, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    registry = installed_integrations(root, owner)
    arguments = {
        "activity_id": str(activity),
        "external_tool": "Chat",
        "document_text": "My chosen instructions",
        "expected_return": "A result",
    }
    operation = uuid4()
    initial = invoke(registry, "prepare_document", arguments, operation)
    previous = read_activity(root, activity, owner)
    _apply(
        root,
        space,
        owner,
        ReviseActivityRequest,
        activity_id=activity,
        expected_revision=previous.revision,
        state=ActivityState(title=previous.state.title, goal="A revised goal"),
    )
    replayed = invoke(registry, "prepare_document", arguments, operation)
    assert replayed["record_id"] == initial["record_id"]
    assert replayed["stale"] is True
    retained = read_knowledge(root, UUID(str(initial["record_id"])), owner).state
    assert isinstance(retained, HandoffState) and retained.included[0].revision == 1


@pytest.mark.parametrize("legacy_first", [True, False])
def test_legacy_and_tailored_prepare_do_not_share_an_operation_intent(
    tmp_path: Path, legacy_first: bool
) -> None:
    root, _, owner, activity, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    exchange = ManualExchange(root, owner)
    operation_id = uuid4()

    def legacy() -> dict[str, object]:
        return exchange.prepare(operation_id, activity, external_tool="Chat")

    def tailored() -> dict[str, object]:
        return exchange.prepare_document(
            operation_id,
            activity,
            external_tool="Chat",
            document_text="Specific instructions",
            expected_return="A result",
        )

    first, second = (legacy, tailored) if legacy_first else (tailored, legacy)
    result = first()
    with pytest.raises(FoundationError, match="operation_conflict"):
        second()
    assert first()["record_id"] == result["record_id"]


def test_catalog_is_not_a_write_grant(tmp_path: Path) -> None:
    root, space, owner, activity, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest,
        grant_id=uuid4(),
        state=GrantState(
            grantee="reader",
            actions=("record.read",),
            resource_type="space",
            status="active",
        ),
    )
    reader = authorize_local(root, actor="reader", source_ref="fictional-reader")
    registry = installed_integrations(root, reader)
    assert registry.catalog()["adapters"]
    assert registry.contract("manual", "retain_text")["schema"]
    with pytest.raises(FoundationError, match="permission_denied"):
        invoke(
            registry,
            "retain_text",
            {
                "activity_id": str(activity),
                "origin": "Chat",
                "content_text": "No write grant",
            },
        )


def test_bridge_result_exposure_and_bounded_read(tmp_path: Path) -> None:
    root, _, owner, activity, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    bridge = Bridge(root, owner, tmp_path)
    session = uuid4()
    bridge.connect(session)
    request: dict[str, Any] = {
        "mode": "apply",
        "adapter": "manual",
        "operation": "retain_text",
        "contract_version": 1,
        "operation_key": "same-tool-call",
        "arguments": {"activity_id": str(activity), "origin": "Chat", "content_text": "x" * 90000},
    }
    retained = bridge.integration(session, request)
    assert bridge.integration(session, request) == retained
    ref = KnowledgeRef(record_id=UUID(str(retained["record_id"])), revision=1)
    assert ref not in bridge.exposed_refs.get(session, set())
    page = bridge.integration(
        session,
        {
            **request,
            "operation": "read_document",
            "operation_key": "read-call",
            "arguments": {"record_id": retained["record_id"], "revision": 1},
        },
    )
    assert page["next_offset"] == 16384
    assert len(str(page["content_text"])) == 16384
    assert ref in bridge.exposed_refs[session]
    bridge.assigned_attempt_id = uuid4()
    with pytest.raises(FoundationError, match="interactive only"):
        bridge.integration(session, {"mode": "catalog"})


def test_shipped_context_read_is_exact_and_has_no_core_effect(tmp_path: Path) -> None:
    root, _, owner, _, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    before = read_space(root).state_revision
    registry = installed_integrations(root, owner)
    first = invoke(registry, "product_context", {})
    second = invoke(installed_integrations(root, owner), "product_context", {})
    assert first == second
    content = str(first["content_text"]).encode()
    assert first["bytes"] == len(content)
    assert first["sha256"] == hashlib.sha256(content).hexdigest().upper()
    assert read_space(root).state_revision == before
