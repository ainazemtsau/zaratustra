"""Ordinary runtime reads preserve material kinds, fragments and selection boundaries."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_activity_structures import _activate, _structured_case
from tests.zaratustra.foundation.test_memory import note, ready
from zaratustra.foundation import (
    ContextState,
    CreateArtifactRequest,
    CreateGrantRequest,
    CreateKnowledgeRequest,
    FoundationError,
    GrantState,
    KnowledgeRef,
    MemoryMetadata,
    SourceState,
    apply_operation,
    authorize_local,
    read_knowledge,
    read_space,
    start_procedure,
)
from zaratustra.pi_adapter import Bridge


def materials(tmp_path: Path) -> tuple[Bridge, UUID, KnowledgeRef, KnowledgeRef]:
    root, space, owner, activity, *_ = ready(tmp_path)
    source = note(root, space, owner, "prefix абв source suffix", activity=activity)
    artifact = uuid4()
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            artifact_id=artifact,
            media_type="text/plain",
            content="prefix 🙂 artifact suffix".encode(),
        ),
        owner,
    )

    bridge = Bridge(root, owner, root)
    session = uuid4()
    bridge.connect(session)
    return (
        bridge,
        session,
        KnowledgeRef(record_id=source, revision=1),
        KnowledgeRef(record_id=artifact, revision=1),
    )


def test_revisionless_source_open_returns_utf8_and_empty_eof_without_false_exposure(
    tmp_path: Path,
) -> None:
    bridge, session, source, _ = materials(tmp_path)
    first = bridge.knowledge_read(
        session,
        {
            "mode": "open",
            "record_id": str(source.record_id),
            "max_bytes": 9,
        },
    )
    assert first["content_text"] == "prefix а"
    assert first["next_offset"] == 9
    assert KnowledgeRef.model_validate(cast(list[Any], first["exposed"])[0]) == source.model_copy(
        update={"start": 0, "end": 9}
    )
    full = bridge.knowledge_read(session, {"mode": "open", "record_id": str(source.record_id)})
    assert full["content_text"] == "prefix абв source suffix"
    assert full["exposed"] == [source.model_dump(mode="json")]
    end = bridge.knowledge_read(
        session,
        {
            "mode": "open",
            "record_id": str(source.record_id),
            "offset": full["total_bytes"],
        },
    )
    assert end["content_text"] == "" and end["exposed"] == []
    assert end["next_offset"] is None


@pytest.mark.parametrize("index", [0, 1])
def test_native_exact_open_keeps_kind_fragment_and_only_returned_exposure(
    tmp_path: Path, index: int
) -> None:
    bridge, session, source, artifact = materials(tmp_path)
    ref = (source, artifact)[index].model_copy(update={"start": 7, "end": 16 if index == 0 else 20})
    before = read_space(bridge.path)
    output = bridge.knowledge_read(
        session, {"mode": "open", **ref.model_dump(mode="json"), "max_bytes": 5}
    )
    chunk = base64.b64decode(str(output["content_base64"]))
    assert output["record_kind"] == ("source" if index == 0 else "artifact")
    assert output["reader"] == "material" and output["returned_bytes"] == len(chunk) <= 5
    exposed = KnowledgeRef.model_validate(cast(list[Any], output["exposed"])[0])
    assert (
        exposed.record_id == ref.record_id and exposed.start == 7 and exposed.end == 7 + len(chunk)
    )
    assert ref not in bridge.exposed_refs[session]
    assert ref.model_copy(update={"start": None, "end": None}) not in bridge.exposed_refs[session]
    assert read_space(bridge.path) == before
    # Native retained assistant provenance uses only the exact read fragments.
    # This exercises Core reference validation for both material families.
    retained = bridge.capture_source(
        session,
        channel="conversation_assistant",
        content="Used the returned fragment",
        source_event_id="read-fragments-assistant",
    )
    retained_ref = KnowledgeRef.model_validate(retained["source_ref"])
    saved = read_knowledge(bridge.path, retained_ref.record_id, bridge.authority).state
    assert isinstance(saved, SourceState) and exposed in saved.derived_from
    assert ref not in saved.derived_from
    bridge.capture_source(
        session,
        channel="conversation_user",
        content="Continue from read fragments",
        source_event_id="read-fragments-owner",
        input_source="interactive",
    )
    context = bridge.prepare_context(session)
    manifest = read_knowledge(
        bridge.path, UUID(str(context["manifest_id"])), bridge.authority
    ).state
    assert isinstance(manifest, ContextState)
    assert ref not in manifest.mandatory and ref not in manifest.historical_memory


def test_native_mixed_batch_pages_share_budget_without_retained_selection(tmp_path: Path) -> None:
    bridge, session, source, artifact = materials(tmp_path)
    refs = (
        source.model_copy(update={"start": 7, "end": 17}),
        artifact.model_copy(update={"start": 7, "end": 21}),
    )
    arguments = {
        "mode": "read_batch",
        "material_refs": [ref.model_dump(mode="json") for ref in refs],
        "max_bytes": 8,
    }
    before = read_space(bridge.path)
    bodies = [bytearray(), bytearray()]
    index, offset, pages = 0, 0, 0
    while True:
        output = bridge.knowledge_read(
            session, {**arguments, "material_index": index, "offset": offset}
        )
        assert output["kind"] == "material_batch" and "selection_id" not in output
        assert cast(int, output["returned_bytes"]) <= 8
        for item in cast(list[dict[str, Any]], output["items"]):
            position = 0 if item["record_id"] == str(source.record_id) else 1
            bodies[position].extend(base64.b64decode(item["content_base64"]))
        pages += 1
        assert pages <= 8
        if output["next_material_index"] is None:
            assert output["end_of_batch"]
            break
        index, offset = cast(int, output["next_material_index"]), cast(int, output["next_offset"])
    assert bytes(bodies[0]) == "абв sou".encode()
    assert bytes(bodies[1]) == "🙂 artifact ".encode()
    assert not bridge.memory_snapshots.get(session)
    assert read_space(bridge.path) == before
    with pytest.raises(FoundationError, match="invalid_request"):
        bridge.knowledge_read(session, {**arguments, "selectors": [{"common": True}]})
    with pytest.raises(FoundationError, match="invalid_request"):
        bridge.knowledge_read(session, {"mode": "read_batch", "material_refs": []})
    assert read_space(bridge.path) == before


@pytest.mark.parametrize("mode", ["catalog", "read_batch", "prepare_cache", "open"])
def test_native_wrong_family_is_precise_and_rights_checked_first(tmp_path: Path, mode: str) -> None:
    bridge, session, _, artifact = materials(tmp_path)
    arguments = (
        {"mode": mode, "record_id": str(artifact.record_id)}
        if mode == "open"
        else {"mode": mode, "selectors": [{"record_ids": [str(artifact.record_id)]}]}
    )
    before = read_space(bridge.path)
    with pytest.raises(FoundationError) as caught:
        bridge.knowledge_read(session, arguments)
    assert caught.value.code == "wrong_kind" and "exact revision 1" in caught.value.detail
    assert read_space(bridge.path) == before
    apply_operation(
        bridge.path,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=bridge.authority.space_id,
            actor=bridge.authority.actor,
            grant_id=uuid4(),
            state=GrantState(grantee="outsider", actions=("space.inspect",)),
        ),
        bridge.authority,
    )
    outsider = Bridge(
        bridge.path,
        authorize_local(bridge.path, actor="outsider", source_ref="fictional-read-test"),
        bridge.path,
    )
    outsider_session = uuid4()
    outsider.connect(outsider_session)
    with pytest.raises(FoundationError) as refused:
        outsider.knowledge_read(outsider_session, arguments)
    assert refused.value.code == "permission_denied" and "Artifact" not in refused.value.detail


def test_native_runtime_selector_and_literal_search_are_the_same_advertised_contract(
    tmp_path: Path,
) -> None:
    bridge, session, _, _ = materials(tmp_path)
    schema = cast(dict[str, Any], bridge.connect(session)["runtime_selector_schema"])
    assert not {"current_activity", "format_keys", "use_period"}.intersection(schema["properties"])
    before = read_space(bridge.path)
    for key, value in (
        ("current_activity", True),
        ("format_keys", ["entry"]),
        ("use_period", True),
    ):
        with pytest.raises(FoundationError) as caught:
            bridge.knowledge_read(session, {"mode": "read_batch", "selectors": [{key: value}]})
        assert (
            caught.value.code == "invalid_request" and f"selectors.0.{key}" in caught.value.detail
        )
    for text in ("Pacific/Chatham", "2026-01-16", "[term]", "OR"):
        result = bridge.knowledge_read(session, {"mode": "search", "query": text})
        assert result["query_mode"] == "text" and result["index_coverage"]
    assert read_space(bridge.path) == before


def test_native_procedure_packet_navigation_keeps_exact_input_and_request_basis(
    tmp_path: Path,
) -> None:
    case = _structured_case(tmp_path)
    root, space, owner, _, activity, *_ = case
    _activate(case)
    source = note(root, space, owner, "Use the supplied fictional observations", activity=activity)
    original = KnowledgeRef(record_id=source, revision=1)
    run = start_procedure(
        root, owner, activity, "observe", "addressed-material-navigation", request_basis=(original,)
    )
    bridge = Bridge(root, owner, root)
    session = uuid4()
    bridge.connect(session)
    bridge.select(session, activity, UUID(str(run["work_id"])))
    bridge.start_attempt(session, interrupt_previous=False)
    packet = cast(dict[str, Any], bridge.prepare_context(session)["packet"])
    inputs = cast(list[dict[str, Any]], packet["inputs"])
    assert all(item["material"]["record_kind"] == "artifact" for item in inputs)
    navigation = packet["procedure"]["request_basis"][0]
    assert navigation["record_id"] == str(source) and navigation["revision"] == 1
    assert navigation["reader"] == "material" and navigation["record_kind"] == "source"
    assert "content_text" not in navigation and "content_base64" not in navigation


def test_context_catalog_and_material_navigation_do_not_expose_unread_originals(
    tmp_path: Path,
) -> None:
    case = _structured_case(tmp_path)
    root, space, owner, _, activity, *_ = case
    _activate(case)
    original_id = uuid4()
    apply_operation(
        root,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            record_id=original_id,
            state=SourceState(
                channel="document",
                connection="fictional",
                profile_revision=1,
                media_type="text/plain",
                capture="full",
                scope_activity_id=activity,
                content=b"Unread original body requires explicit open",
                memory=MemoryMetadata(
                    title="Unread intake", activity_id=activity, material_role="intake"
                ),
            ),
        ),
        owner,
    )
    original = KnowledgeRef(record_id=original_id, revision=1)
    run = start_procedure(root, owner, activity, "observe", "metadata-only-intake")
    bridge = Bridge(root, owner, root)
    session = uuid4()
    bridge.connect(session)
    bridge.select(session, activity, UUID(str(run["work_id"])))
    bridge.start_attempt(session, interrupt_previous=False)
    context = bridge.prepare_context(session)
    packet = cast(dict[str, Any], context["packet"])
    assert any(item["record_id"] == str(original_id) for item in packet["memory_intake"]["items"])
    manifest = read_knowledge(root, UUID(str(context["manifest_id"])), owner).state
    assert isinstance(manifest, ContextState) and original in manifest.mandatory
    assert original not in bridge.exposed_refs.get(session, set())
    with pytest.raises(FoundationError, match="permission_denied"):
        bridge._exposed_sources(session, {"source_refs": [original.model_dump(mode="json")]})
    window = bridge.knowledge_read(
        session, {"mode": "open", **original.model_dump(mode="json"), "max_bytes": 7}
    )
    exact = KnowledgeRef.model_validate(cast(list[Any], window["exposed"])[0])
    assert exact.start == 0 and exact.end == 7
    assert bridge._exposed_sources(session, {"source_refs": [exact.model_dump(mode="json")]}) == (
        exact,
    )
    with pytest.raises(FoundationError, match="permission_denied"):
        bridge._exposed_sources(session, {"source_refs": [original.model_dump(mode="json")]})
