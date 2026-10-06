"""Risks: mixed scopes, stale membership, disclosure, partial exports and persistence."""

from __future__ import annotations

import base64
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_binding import _apply, _ready
from zaratustra.foundation import (
    AnalysisState,
    ClaimState,
    ContextState,
    CreateGrantRequest,
    CreateKnowledgeRequest,
    DeleteKnowledgeRequest,
    FoundationError,
    GrantState,
    KnowledgeRef,
    LocalAuthority,
    MemoryMetadata,
    MemorySelector,
    MemoryViewState,
    RecordContextDeliveryRequest,
    ReviseKnowledgeRequest,
    RevokeGrantRequest,
    SourceState,
    apply_operation,
    authorize_local,
    complete_deletions,
    create_backup,
    export_memory_selection,
    memory_catalog,
    memory_history,
    open_knowledge,
    open_memory_selection,
    prepare_memory_cache,
    read_current_rights,
    read_knowledge,
    read_memory_batch,
    read_space,
    search_knowledge,
    upgrade_change_package_space,
    upgrade_development_space,
    upgrade_knowledge_space,
    upgrade_memory_space,
)
from zaratustra.foundation.storage import space_connection


def ready(tmp_path: Path) -> tuple[Path, UUID, LocalAuthority, UUID, UUID]:
    root, space, owner, activity, other = _ready(tmp_path)
    for upgrade in (
        upgrade_knowledge_space,
        upgrade_development_space,
        upgrade_change_package_space,
        upgrade_memory_space,
    ):
        upgrade(root, owner)
    return root, space, owner, activity, other


def note(
    root: Path,
    space: UUID,
    owner: LocalAuthority,
    text: str,
    *,
    activity: UUID | None = None,
    topic: str = "equipment",
) -> UUID:
    identifier = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=identifier,
        state=SourceState(
            channel="document",
            connection="fictional",
            profile_revision=1,
            media_type="text/plain",
            capture="full",
            content=text.encode(),
            scope_activity_id=activity,
            memory=MemoryMetadata(title=text[:40], activity_id=activity, topics=(topic,)),
        ),
    )
    return identifier


def fact(
    root: Path, space: UUID, owner: LocalAuthority, source: UUID, text: str, activity: UUID
) -> UUID:
    identifier = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=identifier,
        state=ClaimState(
            proposition=text,
            epistemic_kind="reported",
            status="current",
            scope_activity_id=activity,
            evidence=(KnowledgeRef(record_id=source, revision=1),),
            interpretation_basis="Fictional report",
            memory=MemoryMetadata(title=text, activity_id=activity, topics=("equipment",)),
        ),
    )
    return identifier


def test_batch_union_history_and_original_scope(tmp_path: Path) -> None:
    """Overlapping selectors return each revision once; corrections retain their original."""
    root, space, owner, activity, other = ready(tmp_path)
    common = note(root, space, owner, "Fictional device")
    initial_source = note(root, space, owner, "Measurement on day one", activity=activity)
    first = fact(root, space, owner, initial_source, "Measurement on day one", activity)
    second = note(root, space, owner, "Measurement on day two", activity=other)
    original = read_knowledge(root, first, owner)
    assert isinstance(original.state, ClaimState)
    correction = note(root, space, owner, "Corrected report on day one", activity=activity)
    _apply(
        root,
        space,
        owner,
        ReviseKnowledgeRequest,
        record_id=first,
        expected_revision=1,
        state=original.state.model_copy(
            update={
                "proposition": "Corrected measurement on day one",
                "evidence": (KnowledgeRef(record_id=correction, revision=1),),
            }
        ),
    )
    selection = read_memory_batch(
        root,
        owner,
        (
            MemorySelector(activity_ids=(activity, other), common=True, full=True),
            MemorySelector(record_ids=(first, common)),
        ),
    )
    assert selection["content_complete"] is True
    saved = read_knowledge(root, UUID(str(selection["selection_id"])), owner)
    assert isinstance(saved.state, MemoryViewState) and saved.state.selection is not None
    assert {(ref.record_id, ref.revision) for ref in saved.state.selection.members} == {
        (common, 1),
        (initial_source, 1),
        (correction, 1),
        (first, 1),
        (first, 2),
        (second, 1),
    }
    assert read_knowledge(root, first, owner, revision=1).state == original.state
    revised = read_knowledge(root, first, owner).state
    assert isinstance(revised, ClaimState) and revised.scope_activity_id == activity
    assert len(cast(list[object], memory_history(root, first, owner)["items"])) == 2


def test_cache_reuses_then_updates_membership_without_unrelated_changes(tmp_path: Path) -> None:
    """A new matching record must invalidate a cache even though all old versions match."""
    root, space, owner, activity, other = ready(tmp_path)
    original_source = note(root, space, owner, "Device report", activity=activity, topic="basis")
    first = fact(root, space, owner, original_source, "Device", activity)
    selectors = (MemorySelector(activity_ids=(activity,), topics=("equipment",)),)
    cached = prepare_memory_cache(root, owner, selectors)
    revision = read_space(root).state_revision
    assert prepare_memory_cache(root, owner, selectors)["selection_id"] == cached["selection_id"]
    assert read_space(root).state_revision == revision
    note(root, space, owner, "Other device", activity=other)
    assert prepare_memory_cache(root, owner, selectors)["selection_id"] == cached["selection_id"]
    note(root, space, owner, "Second device", activity=activity)
    changed = prepare_memory_cache(root, owner, selectors)
    assert changed["selection_id"] != cached["selection_id"] and changed["members"] == 2
    assert open_memory_selection(root, UUID(str(cached["selection_id"])), owner)["current"] is False
    old = read_knowledge(root, first, owner)
    assert isinstance(old.state, ClaimState)
    _apply(
        root,
        space,
        owner,
        ReviseKnowledgeRequest,
        record_id=first,
        expected_revision=1,
        state=old.state.model_copy(
            update={
                "memory": MemoryMetadata(
                    title="Moved category",
                    activity_id=activity,
                    topics=("other",),
                )
            }
        ),
    )
    assert prepare_memory_cache(root, owner, selectors)["members"] == 1


def test_revoked_source_access_is_not_bypassed_by_saved_selection(tmp_path: Path) -> None:
    """Having access to a derived view does not grant access to a now-denied original."""
    root, space, owner, _, _ = ready(tmp_path)
    identifier = note(root, space, owner, "Private fictional material")
    selected = read_memory_batch(root, owner, (MemorySelector(record_ids=(identifier,)),))
    initial_grants = cast(list[dict[str, Any]], read_current_rights(root, owner)["grants"])
    saved = read_knowledge(root, UUID(str(selected["selection_id"])), owner)
    assert isinstance(saved.state, MemoryViewState) and saved.state.selection is not None
    prompt = note(root, space, owner, "Continue the saved chat", topic="request")
    context_id = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=context_id,
        state=ContextState(
            purpose="Continue a fictional saved chat",
            session_id=uuid4(),
            mandatory=(KnowledgeRef(record_id=prompt, revision=1),),
            historical_memory=(KnowledgeRef(record_id=saved.record_id, revision=1),),
        ),
    )
    for readable in (
        prompt,
        context_id,
        UUID(str(selected["selection_id"])),
        *(p.record_id for p in saved.state.selection.parts),
    ):
        _apply(
            root,
            space,
            owner,
            CreateGrantRequest,
            grant_id=uuid4(),
            state=GrantState(
                grantee="owner",
                actions=("record.read",),
                resource_type="artifact",
                resource_id=readable,
            ),
        )
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest,
        grant_id=uuid4(),
        state=GrantState(grantee="owner", actions=("model.invoke",), resource_type="space"),
    )
    for grant in initial_grants:
        _apply(
            root,
            space,
            owner,
            RevokeGrantRequest,
            grant_id=UUID(grant["record_id"]),
            expected_revision=grant["revision"],
        )
    visible = cast(list[dict[str, Any]], memory_catalog(root, owner)["items"])
    assert [item["record_id"] for item in visible] == [str(prompt)]
    with pytest.raises(FoundationError, match="permission_denied"):
        open_memory_selection(root, UUID(str(selected["selection_id"])), owner)
    with pytest.raises(FoundationError, match="permission_denied"):
        export_memory_selection(
            root, UUID(str(selected["selection_id"])), owner, tmp_path / "copy.md"
        )
    assert not (tmp_path / "copy.md").exists()
    with pytest.raises(FoundationError, match="permission_denied"):
        open_knowledge(root, saved.state.selection.parts[0].record_id, owner)
    with pytest.raises(FoundationError, match="permission_denied"):
        apply_operation(
            root,
            RecordContextDeliveryRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                invocation_id=uuid4(),
                manifest=KnowledgeRef(record_id=context_id, revision=1),
                stage="prepared",
                free_call=True,
                reserve_units=1,
            ),
            owner,
        )


def test_new_matching_input_fences_prepared_context(tmp_path: Path) -> None:
    """An addition outside the old ref list is detected before provider admission."""
    root, space, owner, activity, _ = ready(tmp_path)
    original = note(root, space, owner, "Original device", activity=activity)
    cached = prepare_memory_cache(root, owner, (MemorySelector(activity_ids=(activity,)),))
    context_id = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=context_id,
        state=ContextState(
            purpose="Fictional request",
            session_id=uuid4(),
            mandatory=(KnowledgeRef(record_id=UUID(str(cached["selection_id"])), revision=1),),
        ),
    )
    note(root, space, owner, "New device", activity=activity)
    historical_id = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=historical_id,
        state=ContextState(
            purpose="Explain the exact historical snapshot",
            session_id=uuid4(),
            mandatory=(KnowledgeRef(record_id=original, revision=1),),
            historical_memory=(
                KnowledgeRef(record_id=UUID(str(cached["selection_id"])), revision=1),
            ),
        ),
    )
    # Historical snapshots remain readable after additions; only current caches fence them.
    apply_operation(
        root,
        RecordContextDeliveryRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            invocation_id=uuid4(),
            manifest=KnowledgeRef(record_id=historical_id, revision=1),
            stage="prepared",
            free_call=True,
            reserve_units=1,
        ),
        owner,
    )
    with pytest.raises(FoundationError, match="stale_context"):
        apply_operation(
            root,
            RecordContextDeliveryRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                invocation_id=uuid4(),
                manifest=KnowledgeRef(record_id=context_id, revision=1),
                stage="prepared",
                free_call=True,
                reserve_units=1,
            ),
            owner,
        )


def test_partial_assembly_replay_and_unicode_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Interrupted assembly has no ready root; replay and UTF-8 byte windows stay exact."""
    from zaratustra.foundation import memory

    root, space, owner, activity, _ = ready(tmp_path)
    text = "Вымышленный документ 🧭\n" * 2500
    identifier = note(root, space, owner, text, activity=activity)
    selectors = (MemorySelector(record_ids=(identifier,)),)
    original_apply = apply_operation

    def interrupt(path: Path, request: Any, authority: Any) -> Any:
        if request.state.selection is not None:
            raise OSError("Fictional interruption before root publication")
        return original_apply(path, request, authority)

    operation_id = uuid4()
    monkeypatch.setattr(memory, "apply_operation", interrupt)
    with pytest.raises(OSError, match="interruption"):
        read_memory_batch(root, owner, selectors, operation_id=operation_id)
    monkeypatch.setattr(memory, "apply_operation", original_apply)
    selected = read_memory_batch(root, owner, selectors, operation_id=operation_id, max_bytes=127)
    chunks = [str(selected["content_text"])]
    while selected["next_part"] is not None:
        selected = open_memory_selection(
            root,
            UUID(str(selected["selection_id"])),
            owner,
            part=int(str(selected["next_part"])),
            offset=int(str(selected["next_offset"])),
            max_bytes=127,
        )
        chunks.append(str(selected["content_text"]))
    assert text in "".join(chunks)
    assert selected["end_of_selection"] is True and selected["content_complete"] is False
    assert selected["returned_bytes"] == len(chunks[-1].encode("utf-8"))
    assert selected["total_bytes"] == len("".join(chunks).encode("utf-8"))
    destination = tmp_path / "export.md"
    exported = export_memory_selection(
        root, UUID(str(selected["selection_id"])), owner, destination
    )
    assert exported["complete"] is True and text in destination.read_text(encoding="utf-8")
    with pytest.raises(FoundationError, match="file_exists"):
        export_memory_selection(root, UUID(str(selected["selection_id"])), owner, destination)
    concurrent = tmp_path / "concurrent.md"
    original_link = os.link

    def publish_concurrent(source: Any, target: Any) -> None:
        Path(target).write_text("Another completed delivery", encoding="utf-8")
        original_link(source, target)

    monkeypatch.setattr(os, "link", publish_concurrent)
    with pytest.raises(FoundationError, match="file_exists"):
        export_memory_selection(root, UUID(str(selected["selection_id"])), owner, concurrent)
    assert concurrent.read_text(encoding="utf-8") == "Another completed delivery"
    assert not list(tmp_path.glob("*.pending"))
    # Binary originals are opaque bytes; a text export must retain them losslessly.
    foreign_encoding = uuid4()
    original_bytes = "Вымышленный оригинал".encode("utf-16")
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=foreign_encoding,
        state=SourceState(
            channel="document",
            connection="fictional",
            profile_revision=1,
            media_type="application/octet-stream",
            capture="full",
            content=original_bytes,
        ),
    )
    retained = read_memory_batch(root, owner, (MemorySelector(record_ids=(foreign_encoding,)),))
    assert base64.b64encode(original_bytes).decode("ascii") in str(retained["content_text"])


def test_filtered_read_does_not_decode_unrelated_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A small selected context does not grow with unrelated matching prose or old revisions."""
    from zaratustra.foundation import knowledge

    root, space, owner, activity, other = ready(tmp_path)
    wanted = note(root, space, owner, "Target equipment", activity=activity)
    for number in range(40):
        note(root, space, owner, f"UNRELATED_PAYLOAD {number}", activity=other)
    adapter = knowledge.BODY_ADAPTER

    class CheckedAdapter:
        def validate_json(self, payload: bytes) -> Any:
            assert b"UNRELATED_PAYLOAD" not in payload
            return adapter.validate_json(payload)

    monkeypatch.setattr(knowledge, "BODY_ADAPTER", CheckedAdapter())
    selected = read_memory_batch(root, owner, (MemorySelector(activity_ids=(activity,)),))
    assert selected["members"] == 1 and str(wanted) in str(selected["content_text"])
    from zaratustra.foundation import memory

    original_connection = space_connection
    consumed = {"catalog": 0, "search": 0}

    @contextmanager
    def bounded_rows(path: Path) -> Any:
        with original_connection(path) as (connection, info):

            def row_factory(_cursor: Any, values: Any) -> Any:
                key = (
                    "catalog"
                    if len(values) == 11 and "UNRELATED_PAYLOAD" in str(values[5])
                    else "search"
                    if len(values) == 4 and "UNRELATED_PAYLOAD" in str(values[3])
                    else None
                )
                if key:
                    consumed[key] += 1
                    assert consumed[key] <= 3, "Small pages must not materialize all 40 matches"
                return values

            connection.row_factory = row_factory
            yield connection, info

    monkeypatch.setattr(knowledge, "space_connection", bounded_rows)
    monkeypatch.setattr(memory, "space_connection", bounded_rows)
    catalog = memory_catalog(
        root, owner, selectors=(MemorySelector(activity_ids=(other,)),), limit=2
    )
    found = search_knowledge(root, owner, '"UNRELATED_PAYLOAD"', limit=2)
    assert len(cast(list[object], catalog["items"])) == len(cast(list[object], found["items"])) == 2
    assert (
        catalog["next_cursor"] and found["next_cursor"] and consumed == {"catalog": 3, "search": 3}
    )


def test_deletion_purges_derived_selection_and_contaminated_backup(tmp_path: Path) -> None:
    """New caches and their text parts participate in existing transitive sanitation."""
    root, space, owner, _, _ = ready(tmp_path)
    source = note(root, space, owner, "Fictional removable material")
    selected = prepare_memory_cache(root, owner, (MemorySelector(record_ids=(source,)),))
    saved = read_knowledge(root, UUID(str(selected["selection_id"])), owner)
    assert isinstance(saved.state, MemoryViewState) and saved.state.selection is not None
    backup = create_backup(root, uuid4(), owner)
    _apply(root, space, owner, DeleteKnowledgeRequest, record_id=source, expected_revision=1)
    result = complete_deletions(root, owner)
    assert result.live_store_sanitized and not backup.package.exists()
    for ref in saved.state.selection.parts:
        assert read_knowledge(root, ref.record_id, owner).state is None
    assert read_knowledge(root, UUID(str(selected["selection_id"])), owner).state is None
    assert memory_catalog(root, owner)["items"] == []


def test_upgrade_retains_old_bytes_and_cache_reopens(tmp_path: Path) -> None:
    """Explicit migration preserves originals; a fresh authority can reuse the saved selection."""
    root, space, owner, activity, _ = _ready(tmp_path)
    for upgrade in (
        upgrade_knowledge_space,
        upgrade_development_space,
        upgrade_change_package_space,
    ):
        upgrade(root, owner)
    identifier = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=identifier,
        state=SourceState(
            channel="document",
            connection="fictional",
            profile_revision=1,
            media_type="text/plain",
            capture="full",
            content=b"Original retained bytes",
            scope_activity_id=activity,
        ),
    )
    original = read_knowledge(root, identifier, owner)
    with pytest.raises(FoundationError, match="unsupported_schema"):
        memory_catalog(root, owner)
    upgrade_memory_space(root, owner)
    assert read_knowledge(root, identifier, owner).sha256 == original.sha256
    selected = prepare_memory_cache(root, owner, (MemorySelector(activity_ids=(activity,)),))
    fresh = authorize_local(root, actor="owner", source_ref="fictional-new-session")
    assert (
        prepare_memory_cache(root, fresh, (MemorySelector(activity_ids=(activity,)),))[
            "selection_id"
        ]
        == selected["selection_id"]
    )


def test_source_organization_preserves_capture_and_processed_intake(tmp_path: Path) -> None:
    """Classification retains raw bytes/event identity; explicit interpretation clears intake."""
    root, space, owner, activity, _ = ready(tmp_path)
    source = uuid4()
    raw = SourceState(
        channel="conversation_user",
        connection="fictional",
        profile_revision=1,
        source_event_id="fictional-event",
        media_type="text/plain",
        capture="full",
        content=b"Fictional unchanged report",
        scope_activity_id=activity,
    )
    _apply(root, space, owner, CreateKnowledgeRequest, record_id=source, state=raw)
    assert memory_catalog(root, owner, unprocessed_only=True)["items"]
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=uuid4(),
        state=AnalysisState(
            task="Inspect the report later",
            inputs=(KnowledgeRef(record_id=source, revision=1),),
            executor="fictional",
            status="pending",
        ),
    )
    assert memory_catalog(root, owner, unprocessed_only=True)["items"]
    interpreted = fact(root, space, owner, source, "Fictional interpretation", activity)
    assert memory_catalog(root, owner, unprocessed_only=True)["items"] == []
    assert str(source) not in str(memory_catalog(root, owner)["items"])
    assert str(source) in str(memory_catalog(root, owner, full=True)["items"])
    assert memory_history(root, interpreted, owner)["items"]
    tagged = raw.model_copy(update={"memory": MemoryMetadata(title="Report", activity_id=activity)})
    _apply(
        root,
        space,
        owner,
        ReviseKnowledgeRequest,
        record_id=source,
        expected_revision=1,
        state=tagged,
    )
    assert read_knowledge(root, source, owner, revision=1).state == raw
    assert read_knowledge(root, source, owner).state == tagged
    with pytest.raises(FoundationError, match="source_immutable"):
        _apply(
            root,
            space,
            owner,
            ReviseKnowledgeRequest,
            record_id=source,
            expected_revision=2,
            state=tagged.model_copy(update={"content": b"Rewritten"}),
        )
    with pytest.raises(FoundationError, match="not_found"):
        read_memory_batch(root, owner, (MemorySelector(record_ids=(uuid4(),), full=True),))
    selected = prepare_memory_cache(root, owner, (MemorySelector(record_ids=(source,)),))
    compiled = read_knowledge(root, UUID(str(selected["selection_id"])), owner).state
    assert isinstance(compiled, MemoryViewState)
    with pytest.raises(FoundationError, match="selection compiler"):
        _apply(root, space, owner, CreateKnowledgeRequest, record_id=uuid4(), state=compiled)
