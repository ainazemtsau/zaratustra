"""Mixed exact materials retain rights, byte bounds and honest exposure."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_activity_structures import _structured_case
from tests.zaratustra.foundation.test_binding import _ready
from zaratustra.foundation import (
    ContextState,
    CreateArtifactRequest,
    CreateDecisionRequest,
    CreateGrantRequest,
    CreateKnowledgeRequest,
    DecisionState,
    DeleteArtifactRequest,
    DeleteKnowledgeRequest,
    FoundationError,
    GrantState,
    HandoffState,
    KnowledgeRef,
    LocalAuthority,
    ProvenanceRef,
    ReviseArtifactRequest,
    RevokeGrantRequest,
    SourceState,
    apply_operation,
    authorize_local,
    read_space,
    upgrade_knowledge_space,
)
from zaratustra.foundation.materials import describe_material_reference, open_material


def _fixture(tmp_path: Path) -> tuple[Path, UUID, LocalAuthority]:
    root, space, owner, _, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    return root, space, owner


def _material(
    root: Path,
    space: UUID,
    owner: LocalAuthority,
    content: bytes,
    *,
    source: bool,
    media_type: str = "text/plain",
) -> KnowledgeRef:
    record_id = uuid4()
    request = (
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            record_id=record_id,
            state=SourceState(
                channel="document",
                connection="fictional-input",
                profile_revision=1,
                capture="full",
                media_type=media_type,
                content=content,
            ),
        )
        if source
        else CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            artifact_id=record_id,
            media_type=media_type,
            content=content,
        )
    )
    apply_operation(root, request, owner)
    return KnowledgeRef(record_id=record_id, revision=1)


def test_mixed_exact_materials_have_body_free_navigation_and_actual_windows(tmp_path: Path) -> None:
    root, space, owner = _fixture(tmp_path)
    body = "Пример: only the selected bytes. Остальное.".encode()
    for source in (True, False):
        ref = _material(root, space, owner, body, source=source)
        before = read_space(root)
        navigation = describe_material_reference(root, ref, owner)
        assert navigation["record_kind"] == ("source" if source else "artifact")
        assert navigation["reader"] == "material"
        assert navigation["total_bytes"] == len(body)
        assert "content_base64" not in navigation and "content_text" not in navigation
        assert "state" not in navigation and "exposed" not in navigation
        opened = open_material(root, ref, owner, max_bytes=7)
        chunk = base64.b64decode(str(opened["content_base64"]))
        assert chunk == "При".encode()
        assert opened["returned_bytes"] == 6 and opened["next_offset"] == 6
        assert opened["content_text"] == "При"
        assert opened["content_complete"] is False
        assert opened["chunk_sha256"] == hashlib.sha256(chunk).hexdigest().upper()
        assert opened["content_sha256"] == hashlib.sha256(body).hexdigest().upper()
        assert opened["exposed"] == [
            ref.model_copy(update={"start": 0, "end": 6}).model_dump(mode="json")
        ]
        assert read_space(root) == before


@pytest.mark.parametrize("source", [False, True])
def test_fragment_relative_continuation_cannot_escape_selected_bounds(
    tmp_path: Path, source: bool
) -> None:
    root, space, owner = _fixture(tmp_path)
    body = "outside Привет 🌍 outside".encode()
    ref = _material(root, space, owner, body, source=source)
    start, end = len(b"outside "), len("outside Привет 🌍".encode())
    selected = ref.model_copy(update={"start": start, "end": end})
    offset = 0
    chunks: list[bytes] = []
    while True:
        opened = open_material(root, selected, owner, offset=offset, max_bytes=5)
        chunk = base64.b64decode(str(opened["content_base64"]))
        chunks.append(chunk)
        assert len(chunk) <= 5 and opened["total_bytes"] == end - start
        assert opened["original_total_bytes"] == len(body)
        assert opened["exposed"] == [
            ref.model_copy(
                update={"start": start + offset, "end": start + offset + len(chunk)}
            ).model_dump(mode="json")
        ]
        next_offset = opened["next_offset"]
        if next_offset is None:
            break
        assert isinstance(next_offset, int) and next_offset > offset
        offset = next_offset
    assert b"".join(chunks) == "Привет 🌍".encode()
    assert opened["content_complete"] is False
    assert open_material(root, selected, owner)["content_complete"] is True
    with pytest.raises(FoundationError, match="invalid_request"):
        open_material(root, selected, owner, offset=end - start + 1)
    with pytest.raises(FoundationError, match="invalid_fragment"):
        open_material(root, ref.model_copy(update={"start": 0, "end": len(body) + 1}), owner)
    with pytest.raises(FoundationError, match="UTF-8"):
        open_material(root, selected, owner, offset=1)
    with pytest.raises(FoundationError, match="UTF-8"):
        open_material(root, selected, owner, max_bytes=1)


def test_old_artifact_revision_never_falls_forward(tmp_path: Path) -> None:
    root, space, owner = _fixture(tmp_path)
    ref = _material(root, space, owner, b"old exact input", source=False)
    apply_operation(
        root,
        ReviseArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            artifact_id=ref.record_id,
            expected_revision=1,
            media_type="text/plain",
            content=b"new incompatible input",
        ),
        owner,
    )
    assert open_material(root, ref, owner)["content_text"] == "old exact input"
    assert describe_material_reference(root, ref, owner)["stale"] is True
    assert open_material(root, ref.model_copy(update={"revision": 2}), owner)["content_text"] == (
        "new incompatible input"
    )
    with pytest.raises(FoundationError, match="not_found"):
        open_material(root, ref.model_copy(update={"revision": 3}), owner)


@pytest.mark.parametrize("source", [False, True])
def test_permissions_and_revocation_never_fall_back_to_disclosing_kind(
    tmp_path: Path, source: bool
) -> None:
    root, space, owner = _fixture(tmp_path)
    ref = _material(root, space, owner, b"private exact body", source=source)
    reader = authorize_local(root, actor="fictional-reader", source_ref="fixture")
    with pytest.raises(FoundationError) as denied:
        describe_material_reference(root, ref, reader)
    assert denied.value.code == "permission_denied"
    grant_id = uuid4()
    apply_operation(
        root,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            grant_id=grant_id,
            state=GrantState(
                grantee=reader.actor,
                actions=("record.read",),
                resource_type="artifact",
                resource_id=ref.record_id,
            ),
        ),
        owner,
    )
    assert open_material(root, ref, reader)["content_text"] == "private exact body"
    apply_operation(
        root,
        RevokeGrantRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            grant_id=grant_id,
            expected_revision=1,
        ),
        owner,
    )
    with pytest.raises(FoundationError) as revoked:
        open_material(root, ref, reader)
    assert revoked.value.code == "permission_denied"


def test_context_and_handoff_read_their_supported_body_without_metadata_copy(
    tmp_path: Path,
) -> None:
    root, space, owner = _fixture(tmp_path)
    source = _material(root, space, owner, b"exact original", source=True)
    context_id, handoff_id = uuid4(), uuid4()
    for record_id, state in (
        (
            context_id,
            ContextState(
                purpose="Fictional diagnostic context",
                session_id=uuid4(),
                mandatory=(source,),
            ),
        ),
        (
            handoff_id,
            HandoffState(
                subject="Fictional handoff",
                document="Прочитать выбранное".encode(),
                media_type="text/plain",
                included=(source,),
                expected_return="Review",
                status="prepared",
                basis_state_revision=read_space(root).state_revision,
            ),
        ),
    ):
        apply_operation(
            root,
            CreateKnowledgeRequest(
                operation_id=uuid4(),
                space_id=space,
                actor=owner.actor,
                record_id=record_id,
                state=state,
            ),
            owner,
        )
    context_ref = KnowledgeRef(record_id=context_id, revision=1)
    context = open_material(root, context_ref, owner)
    assert context["record_kind"] == "context" and context["field"] == "structured_data"
    assert json.loads(str(context["content_text"]))["mandatory"] == [source.model_dump(mode="json")]
    assert "purpose" not in describe_material_reference(root, context_ref, owner)
    handoff = open_material(root, KnowledgeRef(record_id=handoff_id, revision=1), owner)
    assert handoff["field"] == "document" and handoff["content_text"] == "Прочитать выбранное"
    assert "subject" not in handoff and "state" not in handoff


def test_actual_material_windows_can_be_retained_as_exact_context_exposure(tmp_path: Path) -> None:
    root, space, owner = _fixture(tmp_path)
    originals = [
        _material(root, space, owner, b"source packet original", source=True),
        _material(root, space, owner, b"artifact packet original", source=False),
    ]
    context_id = uuid4()
    apply_operation(
        root,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            record_id=context_id,
            state=ContextState(
                purpose="Addressed packet diagnostics",
                session_id=uuid4(),
                mandatory=(originals[0],),
            ),
        ),
        owner,
    )
    originals.append(KnowledgeRef(record_id=context_id, revision=1))
    exposed: list[KnowledgeRef] = []
    for ref in originals:
        result = open_material(root, ref, owner, offset=2, max_bytes=7)
        addresses = result["exposed"]
        assert isinstance(addresses, list) and len(addresses) == 1
        actual = KnowledgeRef.model_validate(addresses[0])
        assert actual.start == 2 and actual.end == 9
        exposed.append(actual)
        assert open_material(root, actual, owner)["content_base64"] == result["content_base64"]
    retained = apply_operation(
        root,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            record_id=uuid4(),
            state=ContextState(
                purpose="Only actually delivered windows",
                session_id=uuid4(),
                mandatory=tuple(exposed),
            ),
        ),
        owner,
    )
    assert retained.result["revision"] == 1
    for ref in originals:
        bad = ref.model_copy(update={"start": 0, "end": 65536})
        with pytest.raises(FoundationError, match="invalid_fragment"):
            apply_operation(
                root,
                CreateKnowledgeRequest(
                    operation_id=uuid4(),
                    space_id=space,
                    actor=owner.actor,
                    record_id=uuid4(),
                    state=ContextState(
                        purpose="Invalid exposure", session_id=uuid4(), mandatory=(bad,)
                    ),
                ),
                owner,
            )


def test_derived_artifact_rechecks_basis_rights_before_navigation_or_bytes(tmp_path: Path) -> None:
    root, space, owner, *_ = _structured_case(tmp_path)
    source = _material(root, space, owner, b"restricted basis", source=False)
    artifact_id = uuid4()
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            artifact_id=artifact_id,
            media_type="text/plain",
            content=b"derived restricted material",
            provenance=(ProvenanceRef(relation="basis", record_id=source.record_id, revision=1),),
        ),
        owner,
    )
    reader = authorize_local(root, actor="fictional-reader", source_ref="fixture")
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
                resource_id=artifact_id,
            ),
        ),
        owner,
    )
    ref = KnowledgeRef(record_id=artifact_id, revision=1)
    for read in (describe_material_reference, open_material):
        with pytest.raises(FoundationError) as denied:
            read(root, ref, reader)
        assert denied.value.code == "permission_denied"


def test_deleted_wrong_kind_and_unavailable_material_are_not_missing_bytes(tmp_path: Path) -> None:
    root, space, owner = _fixture(tmp_path)
    source = _material(root, space, owner, b"retired source", source=True)
    artifact = _material(root, space, owner, b"retired artifact", source=False)
    for request in (
        DeleteKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            record_id=source.record_id,
            expected_revision=1,
        ),
        DeleteArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            artifact_id=artifact.record_id,
            expected_revision=1,
        ),
    ):
        apply_operation(root, request, owner)
    deleted = open_material(root, source, owner)
    assert deleted["availability"] == "deleted"
    assert deleted["content"] is None and deleted["exposed"] == []
    assert deleted["returned_bytes"] == 0 and deleted["content_complete"] is False
    deleted_artifact = open_material(root, artifact, owner)
    assert deleted_artifact["record_kind"] == "artifact"
    assert deleted_artifact["availability"] == "deleted"
    assert deleted_artifact["content"] is None and deleted_artifact["exposed"] == []
    with pytest.raises(FoundationError, match="not_found"):
        open_material(root, KnowledgeRef(record_id=uuid4(), revision=1), owner)
    decision_id = uuid4()
    apply_operation(
        root,
        CreateDecisionRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            decision_id=decision_id,
            state=DecisionState(
                statement="Fictional read authority contract",
                effect="require_grant",
                actions=("record.read",),
            ),
        ),
        owner,
    )
    with pytest.raises(FoundationError, match="wrong_kind"):
        open_material(root, KnowledgeRef(record_id=decision_id, revision=1), owner)
    reference_id = uuid4()
    apply_operation(
        root,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            record_id=reference_id,
            state=SourceState(
                channel="document",
                connection="fictional-reference",
                profile_revision=1,
                capture="reference",
                media_type="text/plain",
                locator="fixture://not-retained",
            ),
        ),
        owner,
    )
    unavailable = open_material(root, KnowledgeRef(record_id=reference_id, revision=1), owner)
    assert unavailable["availability"] == "unavailable" and unavailable["exposed"] == []
    assert "locator" not in unavailable


@pytest.mark.parametrize("source", [False, True])
@pytest.mark.parametrize("body", [b"", b"\xff\xfe\x80abc", b"a\xffz", b"\x00\x01\x02"])
def test_empty_binary_and_invalid_utf8_windows_remain_bounded_and_byte_exact(
    tmp_path: Path, source: bool, body: bytes
) -> None:
    root, space, owner = _fixture(tmp_path)
    ref = _material(
        root,
        space,
        owner,
        body,
        source=source,
        media_type="application/octet-stream" if source else "text/plain",
    )
    offset = 0
    chunks: list[bytes] = []
    while True:
        opened = open_material(root, ref, owner, offset=offset, max_bytes=1)
        chunk = base64.b64decode(str(opened["content_base64"]))
        chunks.append(chunk)
        assert len(chunk) <= 1 and opened["returned_bytes"] == len(chunk)
        assert bool(opened["exposed"]) == bool(chunk)
        next_offset = opened["next_offset"]
        if next_offset is None:
            break
        assert isinstance(next_offset, int) and next_offset > offset
        offset = next_offset
    assert b"".join(chunks) == body
    assert open_material(root, ref, owner, offset=len(body))["exposed"] == []


@pytest.mark.parametrize("offset,budget", [(-1, 8), (0, 0), (0, 65537)])
def test_invalid_window_is_rejected_without_reading(
    tmp_path: Path, offset: int, budget: int
) -> None:
    root, _, owner = _fixture(tmp_path)
    with pytest.raises(FoundationError, match="invalid_request"):
        open_material(
            root,
            KnowledgeRef(record_id=uuid4(), revision=1),
            owner,
            offset=offset,
            max_bytes=budget,
        )
