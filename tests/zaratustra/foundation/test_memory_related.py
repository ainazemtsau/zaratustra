"""Exact related materials survive selection composition, caching and reopening."""

import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

import pytest

from tests.zaratustra.foundation.test_activity_structures import (
    _activate,
    _proposal,
    _structured_case,
)
from tests.zaratustra.foundation.test_memory import ready
from zaratustra.foundation import (
    ActivityState,
    ChoiceState,
    ClaimState,
    ContextState,
    CreateActivityRequest,
    CreateArtifactRequest,
    CreateDecisionRequest,
    CreateGrantRequest,
    CreateKnowledgeRequest,
    CreateWorkRequest,
    DataEntryState,
    DataField,
    DecisionScope,
    DeleteArtifactRequest,
    FoundationError,
    GrantState,
    HandoffState,
    KnowledgeRef,
    MemorySelector,
    MemoryViewState,
    OutputContract,
    RecordContextDeliveryRequest,
    ReviseArtifactRequest,
    RevokeGrantRequest,
    SetupFormatTemplate,
    SourceState,
    WorkState,
    apply_operation,
    authorize_local,
    create_entry,
    open_memory_selection,
    prepare_memory_cache,
    read_activity_setup,
    read_development,
    read_knowledge,
    read_space,
)
from zaratustra.foundation.storage import canonical_json, space_connection


def _case(tmp_path: Path) -> tuple[Any, ...]:
    case = _structured_case(tmp_path)
    draft = _proposal()
    format_template = draft.formats[0]
    definition = format_template.definition.model_copy(
        update={
            "fields": format_template.definition.fields
            + (DataField(key="related", meaning="Exact supporting material", type="ref"),)
        }
    )
    draft = draft.model_copy(
        update={"formats": (SetupFormatTemplate(key="observation", definition=definition),)}
    )
    described = _activate(case, draft)
    root, space, owner, setup, activity, *_ = case
    source = read_activity_setup(root, setup, owner).state.sources[0]
    format_ref = KnowledgeRef.model_validate(described["state"]["formats"]["observation"])
    return root, space, owner, activity, source, format_ref


def _artifact(case: tuple[Any, ...], content: bytes) -> KnowledgeRef:
    root, space, owner, *_ = case
    identifier = uuid4()
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            artifact_id=identifier,
            media_type="text/plain",
            content=content,
        ),
        owner,
    )
    return KnowledgeRef(record_id=identifier, revision=1)


def _entry(case: tuple[Any, ...], related: KnowledgeRef) -> KnowledgeRef:
    root, _, owner, activity, source, format_ref = case
    receipt = create_entry(
        root,
        owner,
        DataEntryState(
            scope_activity_id=activity,
            format_ref=format_ref,
            role="event",
            values={
                "day": "2026-01-01",
                "value": "1.25",
                "related": {"record_id": str(related.record_id), "revision": related.revision},
            },
            bases=(source,),
        ),
    )
    return KnowledgeRef(record_id=UUID(str(receipt.result["record_id"])), revision=1)


def test_exact_artifact_relation_is_readable_cached_and_reopened(tmp_path: Path) -> None:
    case = _case(tmp_path)
    root, _, owner, _, _, format_ref = case
    original = _artifact(case, b"Exact retained artifact input")
    entry = _entry(case, original)
    selectors = (MemorySelector(format_refs=(format_ref,)),)
    first = prepare_memory_cache(root, owner, selectors)
    assert "Exact retained artifact input" in str(first["content_text"])
    selection_id = UUID(str(first["selection_id"]))
    saved = read_knowledge(root, selection_id, owner)
    assert isinstance(saved.state, MemoryViewState) and saved.state.selection is not None
    assert original in saved.state.selection.members and entry in saved.state.selection.members
    before = read_space(root)
    assert prepare_memory_cache(root, owner, selectors)["selection_id"] == str(selection_id)
    reopened = open_memory_selection(root, selection_id, owner)
    assert reopened["current"] is True and "Exact retained artifact input" in str(
        reopened["content_text"]
    )
    assert read_space(root) == before


def test_nested_entry_relation_uses_the_exact_historical_artifact(tmp_path: Path) -> None:
    case = _case(tmp_path)
    root, space, owner, *_ = case
    original = _artifact(case, b"Historical supporting material")
    first = _entry(case, original)
    second = _entry(case, first)
    apply_operation(
        root,
        ReviseArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            artifact_id=original.record_id,
            expected_revision=1,
            media_type="text/plain",
            content=b"New unrelated replacement body",
        ),
        owner,
    )
    selected = prepare_memory_cache(root, owner, (MemorySelector(record_ids=(second.record_id,)),))
    assert "Historical supporting material" in str(selected["content_text"])
    assert "New unrelated replacement body" not in str(selected["content_text"])
    saved = read_knowledge(root, UUID(str(selected["selection_id"])), owner)
    assert isinstance(saved.state, MemoryViewState) and saved.state.selection is not None
    assert {original, first, second}.issubset(saved.state.selection.members)
    assert original.model_copy(update={"revision": 2}) not in saved.state.selection.members


def test_deleted_artifact_cannot_be_ignored_or_read_from_cached_parts(tmp_path: Path) -> None:
    case = _case(tmp_path)
    root, space, owner, *_ = case
    original = _artifact(case, b"Material scheduled for deletion")
    entry = _entry(case, original)
    selected = prepare_memory_cache(root, owner, (MemorySelector(record_ids=(entry.record_id,)),))
    apply_operation(
        root,
        DeleteArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            artifact_id=original.record_id,
            expected_revision=1,
        ),
        owner,
    )
    with pytest.raises(FoundationError, match="content_unavailable"):
        open_memory_selection(root, UUID(str(selected["selection_id"])), owner)
    with pytest.raises(FoundationError, match="content_unavailable"):
        prepare_memory_cache(root, owner, (MemorySelector(record_ids=(entry.record_id,)),))


def test_revoked_related_artifact_rights_fence_saved_selection(tmp_path: Path) -> None:
    case = _case(tmp_path)
    root, space, owner, activity, _, format_ref = case
    original = _artifact(case, b"Related material requiring an exact grant")
    entry = _entry(case, original)
    reader = authorize_local(root, actor="fictional-reader", source_ref="fixture")
    artifact_grant = uuid4()
    apply_operation(
        root,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            grant_id=artifact_grant,
            state=GrantState(grantee=reader.actor, actions=("record.read",), resource_type="space"),
        ),
        owner,
    )
    # Preparation uses the caller's own write grant; saved views cannot lend
    # authority to an original after the read grant is revoked.
    apply_operation(
        root,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            grant_id=uuid4(),
            state=GrantState(
                grantee=reader.actor, actions=("artifact.write",), resource_type="space"
            ),
        ),
        owner,
    )
    selected = prepare_memory_cache(root, reader, (MemorySelector(record_ids=(entry.record_id,)),))
    saved = read_knowledge(root, UUID(str(selected["selection_id"])), reader)
    assert isinstance(saved.state, MemoryViewState) and saved.state.selection is not None
    for ref in (
        KnowledgeRef(record_id=saved.record_id, revision=1),
        *saved.state.selection.parts,
        *saved.state.selection.members,
    ):
        if ref == original:
            continue
        apply_operation(
            root,
            CreateGrantRequest(
                operation_id=uuid4(),
                space_id=space,
                actor=owner.actor,
                grant_id=uuid4(),
                state=GrantState(
                    grantee=reader.actor,
                    actions=("record.read",),
                    resource_type="artifact",
                    resource_id=ref.record_id,
                ),
            ),
            owner,
        )
    apply_operation(
        root,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            grant_id=uuid4(),
            state=GrantState(
                grantee=reader.actor,
                actions=("record.read",),
                resource_type="activity",
                resource_id=activity,
            ),
        ),
        owner,
    )
    apply_operation(
        root,
        RevokeGrantRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            grant_id=artifact_grant,
            expected_revision=1,
        ),
        owner,
    )
    assert format_ref in saved.state.selection.members
    with pytest.raises(FoundationError, match="permission_denied"):
        open_memory_selection(root, saved.record_id, reader)


@pytest.mark.parametrize("family", ["source", "artifact", "handoff"])
def test_full_history_retains_cross_family_exact_fragments_without_widening(
    tmp_path: Path, family: str
) -> None:
    case = _case(tmp_path)
    root, space, owner, *_ = case
    body = b"private-before selected material private-after"
    if family == "artifact":
        original = _artifact(case, body)
    else:
        original = KnowledgeRef(record_id=uuid4(), revision=1)
        state = (
            HandoffState(
                subject="Fictional retained handoff",
                document=body,
                media_type="text/plain",
                expected_return="A source-backed observation",
                status="prepared",
                basis_state_revision=read_space(root).state_revision,
            )
            if family == "handoff"
            else SourceState(
                channel="document",
                connection="fictional",
                profile_revision=1,
                capture="full",
                media_type="text/plain",
                content=body,
            )
        )
        apply_operation(
            root,
            CreateKnowledgeRequest(
                operation_id=uuid4(),
                space_id=space,
                actor=owner.actor,
                record_id=original.record_id,
                state=state,
            ),
            owner,
        )
    fragment = original.model_copy(update={"start": 15, "end": 32})
    second_fragment = original.model_copy(update={"start": 15, "end": 23})
    claim_id = uuid4()
    apply_operation(
        root,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            record_id=claim_id,
            state=ClaimState(
                proposition="Selected material establishes the claim",
                epistemic_kind="reported",
                status="current",
                scope_global=True,
                evidence=(fragment, second_fragment),
                interpretation_basis="Exact fragment",
            ),
        ),
        owner,
    )
    selected = prepare_memory_cache(
        root, owner, (MemorySelector(record_ids=(claim_id,), full=True),)
    )
    saved = read_knowledge(root, UUID(str(selected["selection_id"])), owner)
    assert isinstance(saved.state, MemoryViewState) and saved.state.selection is not None
    assert (
        fragment in saved.state.selection.members and original not in saved.state.selection.members
    )
    assert second_fragment in saved.state.selection.members
    assert "selected material" in str(selected["content_text"])
    assert "private-before" not in str(selected["content_text"])
    assert "private-after" not in str(selected["content_text"])
    assert open_memory_selection(root, saved.record_id, owner)["current"] is True


def _structural_anchor(case: tuple[Any, ...], kind: str) -> tuple[KnowledgeRef, str]:
    root, space, owner, activity, *_ = case
    identifier = uuid4()
    marker = f"Private structural {kind} prose"
    request: CreateWorkRequest | CreateActivityRequest | CreateDecisionRequest | CreateGrantRequest
    if kind == "work":
        request = CreateWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            work_id=identifier,
            state=WorkState(
                activity_id=activity,
                goal=marker,
                expected_outputs=(OutputContract(slot="result", media_type="text/plain"),),
            ),
        )
    elif kind == "activity":
        request = CreateActivityRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            activity_id=identifier,
            state=ActivityState(title=marker, goal=marker),
        )
    elif kind == "decision":
        request = CreateDecisionRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            decision_id=identifier,
            state=ChoiceState(
                statement=marker,
                name="basis",
                value="chosen",
                scope=DecisionScope(kind="activity", record_id=activity),
            ),
        )
    elif kind == "grant":
        request = CreateGrantRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            grant_id=identifier,
            state=GrantState(grantee=marker, actions=("record.read",), resource_type="space"),
        )
    else:
        with space_connection(root) as (connection, _):
            row = connection.execute(
                "SELECT record_id,current_revision FROM development_records "
                "WHERE kind='candidate' AND status='active' ORDER BY record_id LIMIT 1"
            ).fetchone()
        assert row is not None
        ref = KnowledgeRef(record_id=UUID(row[0]), revision=row[1])
        development = read_development(root, ref.record_id, owner, ref.revision)
        assert development.state is not None and development.state.kind == "candidate"
        return ref, development.state.proposal
    apply_operation(root, request, owner)
    return KnowledgeRef(record_id=identifier, revision=1), marker


@pytest.mark.parametrize("kind", ["work", "activity", "decision", "grant", "development"])
def test_full_history_structural_anchor_has_no_imported_body(tmp_path: Path, kind: str) -> None:
    case = _case(tmp_path)
    root, space, owner, *_ = case
    ref, marker = _structural_anchor(case, kind)
    claim_id = uuid4()
    apply_operation(
        root,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            record_id=claim_id,
            state=ClaimState(
                proposition="The addressed structural record supports this claim",
                epistemic_kind="reported",
                status="current",
                scope_global=True,
                evidence=(ref,),
                interpretation_basis="Exact structural anchor",
            ),
        ),
        owner,
    )
    selected = prepare_memory_cache(
        root, owner, (MemorySelector(record_ids=(claim_id,), full=True),)
    )
    saved = read_knowledge(root, UUID(str(selected["selection_id"])), owner)
    assert isinstance(saved.state, MemoryViewState) and saved.state.selection is not None
    assert ref in saved.state.selection.members
    assert marker not in str(selected["content_text"])
    assert f'"reader":"{kind}"' in str(selected["content_text"])
    assert '"content_included":false' in str(selected["content_text"])
    assert open_memory_selection(root, saved.record_id, owner)["current"] is True


def test_previous_partial_full_snapshot_remains_historical_without_rewriting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Model the old compiler's knowledge-only JOIN using normal retained operations."""
    from zaratustra.foundation import memory

    case = _case(tmp_path)
    root, space, owner, *_ = case
    ref, marker = _structural_anchor(case, "work")
    claim_id = uuid4()
    apply_operation(
        root,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            record_id=claim_id,
            state=ClaimState(
                proposition="Historical partial closure",
                epistemic_kind="reported",
                status="current",
                scope_global=True,
                evidence=(ref,),
                interpretation_basis="An exact structural anchor",
            ),
        ),
        owner,
    )
    selectors = (MemorySelector(record_ids=(claim_id,), full=True),)
    # The old JOIN found no knowledge row for the Work and omitted that edge.
    with monkeypatch.context() as legacy:
        legacy.setattr(memory, "_full_bases", lambda _connection, _reader, _root: iter(()))
        previous = prepare_memory_cache(root, owner, selectors)
    identifier = UUID(str(previous["selection_id"]))
    saved = read_knowledge(root, identifier, owner)
    assert isinstance(saved.state, MemoryViewState) and saved.state.selection is not None
    before_payload, before_hash = saved.state.model_dump_json(), saved.sha256
    assert ref not in saved.state.selection.members
    reopened = open_memory_selection(root, identifier, owner)
    assert reopened["current"] is False and "Historical partial closure" in str(
        reopened["content_text"]
    )
    corrected = prepare_memory_cache(root, owner, selectors)
    assert corrected["selection_id"] != previous["selection_id"] and corrected["current"] is True
    assert marker not in str(corrected["content_text"])
    unchanged = read_knowledge(root, identifier, owner)
    assert unchanged.state is not None
    assert unchanged.state.model_dump_json() == before_payload and unchanged.sha256 == before_hash


def test_context_delivery_checks_mixed_originals_before_provider_admission(tmp_path: Path) -> None:
    case = _case(tmp_path)
    root, space, owner, *_ = case
    original = _artifact(case, b"Original admitted with the typed entry")
    entry = _entry(case, original)
    selected = prepare_memory_cache(root, owner, (MemorySelector(record_ids=(entry.record_id,)),))
    context_id = uuid4()
    apply_operation(
        root,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            record_id=context_id,
            state=ContextState(
                purpose="Continue after reading the exact mixed selection",
                session_id=uuid4(),
                mandatory=(
                    KnowledgeRef(record_id=UUID(str(selected["selection_id"])), revision=1),
                ),
            ),
        ),
        owner,
    )
    receipt = apply_operation(
        root,
        RecordContextDeliveryRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            invocation_id=uuid4(),
            manifest=KnowledgeRef(record_id=context_id, revision=1),
            stage="prepared",
            free_call=True,
            reserve_units=1,
        ),
        owner,
    )
    assert receipt.result["stage"] == "prepared"
    assert (
        open_memory_selection(root, UUID(str(selected["selection_id"])), owner)["current"] is True
    )


def test_schema13_knowledge_only_identity_and_bytes_stay_compatible(tmp_path: Path) -> None:
    root, space, owner, *_ = ready(tmp_path)
    source_id, claim_id = uuid4(), uuid4()
    apply_operation(
        root,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            record_id=source_id,
            state=SourceState(
                channel="document",
                connection="fictional",
                profile_revision=1,
                capture="full",
                media_type="text/plain",
                content=b"Exact old source",
            ),
        ),
        owner,
    )
    apply_operation(
        root,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            record_id=claim_id,
            state=ClaimState(
                proposition="Old knowledge-only claim",
                epistemic_kind="reported",
                status="current",
                scope_global=True,
                evidence=(KnowledgeRef(record_id=source_id, revision=1),),
                interpretation_basis="Exact source",
            ),
        ),
        owner,
    )
    selectors = (MemorySelector(record_ids=(claim_id,), full=True),)
    # Schema-13's established v1 identity: row + exact knowledge payload hashes.
    digest = hashlib.sha256(b"unrestricted")
    with space_connection(root) as (connection, info):
        row = connection.execute(
            "SELECT * FROM memory_index WHERE record_id=?", (str(claim_id),)
        ).fetchone()
        assert row is not None
        digest.update(canonical_json(list(row)).encode())
        for identifier in (claim_id, source_id):
            checksum = connection.execute(
                "SELECT sha256 FROM knowledge_revisions WHERE record_id=? AND revision=1",
                (str(identifier),),
            ).fetchone()[0]
            digest.update(f"{identifier}:1:{checksum}".encode())
    expected_fingerprint = digest.hexdigest()
    identity = canonical_json(
        {
            "actor": owner.actor,
            "epoch": info.execution_epoch,
            "selectors": [selector.model_dump(mode="json") for selector in selectors],
            "fingerprint": expected_fingerprint,
            "rule": 1,
        }
    )
    expected_id = uuid5(UUID("e27bf85c-ec92-456b-bbd7-769843ae6848"), identity)
    selected = prepare_memory_cache(root, owner, selectors)
    assert selected["selection_id"] == str(expected_id)
    saved = read_knowledge(root, expected_id, owner)
    assert isinstance(saved.state, MemoryViewState) and saved.state.selection is not None
    assert saved.state.selection.fingerprint == expected_fingerprint
    assert "Exact old source" in str(selected["content_text"])
    before = read_space(root)
    assert before.schema_version == 13
    assert prepare_memory_cache(root, owner, selectors)["selection_id"] == str(expected_id)
    assert open_memory_selection(root, expected_id, owner)["current"] is True
    assert read_space(root) == before


def test_current_data_relation_does_not_silently_expand_to_artifact_family(tmp_path: Path) -> None:
    case = _case(tmp_path)
    root, _, owner, activity, source, format_ref = case
    original = _artifact(case, b"An Artifact has exact data references only")
    before = read_space(root)
    with pytest.raises(FoundationError, match="not_found"):
        create_entry(
            root,
            owner,
            DataEntryState(
                scope_activity_id=activity,
                format_ref=format_ref,
                role="event",
                values={
                    "day": "2026-01-01",
                    "value": "1.25",
                    "related": {"record_id": str(original.record_id), "mode": "current"},
                },
                bases=(source,),
            ),
        )
    assert read_space(root) == before
