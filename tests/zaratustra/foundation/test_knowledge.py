"""Source-backed knowledge keeps exact revisions, access and deletion boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_binding import _ready
from zaratustra.foundation import (
    ClaimState,
    CreateArtifactRequest,
    CreateGrantRequest,
    CreateKnowledgeRequest,
    DeleteKnowledgeRequest,
    FoundationError,
    GrantState,
    HandoffState,
    KnowledgeRef,
    LocalAuthority,
    MemoryLinkState,
    MemoryViewState,
    OperationReceipt,
    ReviseArtifactRequest,
    ReviseKnowledgeRequest,
    SourceState,
    apply_operation,
    authorize_local,
    complete_deletions,
    create_backup,
    list_knowledge,
    read_knowledge,
    read_knowledge_neighbors,
    read_space,
    search_knowledge,
    upgrade_knowledge_space,
)


def _apply(
    root: Path,
    space: UUID,
    authority: LocalAuthority,
    request: CreateKnowledgeRequest
    | ReviseKnowledgeRequest
    | DeleteKnowledgeRequest
    | CreateGrantRequest,
) -> OperationReceipt:
    assert request.space_id == space
    return apply_operation(root, request, authority)


def _source(text: str, *, event_id: str = "message-1") -> SourceState:
    return SourceState(
        channel="conversation_user",
        connection="pi-chat",
        profile_revision=1,
        source_event_id=event_id,
        conversation_id="conversation-a",
        sender="owner",
        media_type="text/plain; charset=utf-8",
        capture="full",
        content=text.encode(),
    )


def test_source_claim_revision_search_and_current_rights(tmp_path: Path) -> None:
    root, space, owner, _, _ = _ready(tmp_path)
    assert upgrade_knowledge_space(root, owner).schema_version == 10
    source_id, claim_id = uuid4(), uuid4()
    source = CreateKnowledgeRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        record_id=source_id,
        state=_source("A calibration result arrived late."),
    )
    _apply(root, space, owner, source)
    assert _apply(root, space, owner, source).operation_id == source.operation_id
    assert read_knowledge(root, source_id, owner).state == source.state
    matches = cast(list[dict[str, object]], search_knowledge(root, owner, "calibration")["items"])
    sources = cast(list[dict[str, object]], list_knowledge(root, owner, kind="source")["items"])
    assert matches[0]["record_id"] == str(source_id)
    assert sources[0]["record_id"] == str(source_id)
    claim = CreateKnowledgeRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        record_id=claim_id,
        state=ClaimState(
            proposition="The calibration is current",
            epistemic_kind="reported",
            status="current",
            scope_global=True,
            evidence=(KnowledgeRef(record_id=source_id, revision=1),),
            interpretation_basis="The owner reported this in the selected conversation.",
        ),
    )
    _apply(root, space, owner, claim)
    correction_id = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=correction_id,
            state=_source("The calibration was superseded.", event_id="message-2"),
        ),
    )
    revised = ReviseKnowledgeRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        record_id=claim_id,
        expected_revision=1,
        state=ClaimState(
            proposition="The calibration may be outdated",
            epistemic_kind="reported",
            status="contested",
            scope_global=True,
            evidence=(KnowledgeRef(record_id=source_id, revision=1),),
            counter_evidence=(KnowledgeRef(record_id=correction_id, revision=1),),
            interpretation_basis="Later owner correction contests the original report.",
        ),
    )
    _apply(root, space, owner, revised)
    assert read_knowledge(root, claim_id, owner).revision == 2
    claim_hits = cast(list[dict[str, object]], search_knowledge(root, owner, "outdated")["items"])
    assert claim_hits[0]["record_id"] == str(claim_id)
    reader = authorize_local(root, actor="reader", source_ref="reader-console")
    with pytest.raises(FoundationError, match="permission_denied"):
        read_knowledge(root, source_id, reader)
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            grant_id=uuid4(),
            state=GrantState(
                grantee="reader",
                actions=("record.read",),
                resource_type="artifact",
                resource_id=source_id,
            ),
        ),
    )
    assert read_knowledge(root, source_id, reader).state == source.state
    assert list_knowledge(root, reader, kind="claim")["items"] == []
    assert list_knowledge(root, reader, kind="claim")["restricted"] is True
    hidden = search_knowledge(root, reader, "outdated")
    unrelated = search_knowledge(root, reader, "impossiblefixtureterm")
    assert hidden["items"] == unrelated["items"] == []
    assert hidden["restricted"] == unrelated["restricted"] is True


def test_handoff_return_and_deletion_retire_derived_bytes(tmp_path: Path) -> None:
    root, space, owner, _, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    source_id, handoff_id = uuid4(), uuid4()
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=source_id,
            state=_source("A design source for the external reviewer."),
        ),
    )
    initial = HandoffState(
        subject="Review design",
        document=b"Please review the enclosed design.",
        media_type="text/plain",
        included=(KnowledgeRef(record_id=source_id, revision=1),),
        expected_return="Text report",
        status="prepared",
        basis_state_revision=read_space(root).state_revision,
    )
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=handoff_id,
            state=initial,
        ),
    )
    transfer_id, return_id = uuid4(), uuid4()
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=transfer_id,
            state=SourceState(
                channel="external_report",
                connection="owner-report",
                profile_revision=1,
                media_type="text/plain",
                capture="full",
                content=b"I sent the document.",
                sender="owner",
            ),
        ),
    )
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=return_id,
            state=SourceState(
                channel="document",
                connection="manual-return",
                profile_revision=1,
                media_type="text/plain",
                capture="full",
                content=b"External review result",
                sender="owner",
                claimed_author="reviewer",
            ),
        ),
    )
    sent = initial.model_copy(
        update={
            "status": "reported_sent",
            "transfer_source": KnowledgeRef(record_id=transfer_id, revision=1),
        }
    )
    returned = initial.model_copy(
        update={
            "status": "returned",
            "transfer_source": KnowledgeRef(record_id=transfer_id, revision=1),
            "return_source": KnowledgeRef(record_id=return_id, revision=1),
        }
    )
    _apply(
        root,
        space,
        owner,
        ReviseKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=handoff_id,
            expected_revision=1,
            state=sent,
        ),
    )
    _apply(
        root,
        space,
        owner,
        ReviseKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=handoff_id,
            expected_revision=2,
            state=returned,
        ),
    )
    backup = create_backup(root, uuid4(), owner)
    _apply(
        root,
        space,
        owner,
        DeleteKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=source_id,
            expected_revision=1,
        ),
    )
    assert read_knowledge(root, source_id, owner).availability == "deleted"
    assert read_knowledge(root, handoff_id, owner).availability == "unavailable"
    assert search_knowledge(root, owner, "design")["items"] == []
    assert complete_deletions(root, owner).live_store_sanitized
    assert not backup.package.exists()


def test_current_view_marks_new_in_scope_source_without_unrelated_invalidation(
    tmp_path: Path,
) -> None:
    root, space, owner, activity, other_activity = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    source_id, view_id = uuid4(), uuid4()
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=source_id,
            state=_source("Initial note").model_copy(update={"scope_activity_id": activity}),
        ),
    )
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=view_id,
            state=MemoryViewState(
                purpose="Current overview",
                scope="Fictional design",
                scope_kind="activity",
                scope_id=str(activity),
                generation_method="Owner summary",
                mode="current",
                sources=(
                    KnowledgeRef(record_id=activity, revision=1),
                    KnowledgeRef(record_id=source_id, revision=1),
                ),
                text="Initial note received",
                coverage_state_revision=read_space(root).state_revision,
            ),
        ),
    )
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=uuid4(),
            state=_source("Unrelated note", event_id="other").model_copy(
                update={"scope_activity_id": other_activity}
            ),
        ),
    )
    assert read_knowledge(root, view_id, owner).stale is False
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=uuid4(),
            state=_source("Relevant late note", event_id="late").model_copy(
                update={"scope_activity_id": activity}
            ),
        ),
    )
    assert read_knowledge(root, view_id, owner).stale is True


def test_late_handoff_return_cannot_match_revised_artifact(tmp_path: Path) -> None:
    root, space, owner, _, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    artifact_id, handoff_id, report_id, return_id = uuid4(), uuid4(), uuid4(), uuid4()
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            artifact_id=artifact_id,
            media_type="text/plain",
            content=b"First basis",
        ),
        owner,
    )
    for record_id, text in ((report_id, "Sent"), (return_id, "Returned")):
        _apply(
            root,
            space,
            owner,
            CreateKnowledgeRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                record_id=record_id,
                state=_source(text, event_id=str(record_id)),
            ),
        )

    base = HandoffState(
        subject="Check exact Artifact",
        document=b"Please review first basis",
        media_type="text/plain",
        included=(KnowledgeRef(record_id=artifact_id, revision=1),),
        expected_return="Text note",
        status="prepared",
        basis_state_revision=read_space(root).state_revision,
    )
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=handoff_id,
            state=base,
        ),
    )
    sent = base.model_copy(
        update={
            "status": "reported_sent",
            "transfer_source": KnowledgeRef(record_id=report_id, revision=1),
        }
    )
    returned = sent.model_copy(
        update={
            "status": "returned",
            "return_source": KnowledgeRef(record_id=return_id, revision=1),
        }
    )
    _apply(
        root,
        space,
        owner,
        ReviseKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=handoff_id,
            expected_revision=1,
            state=sent,
        ),
    )
    _apply(
        root,
        space,
        owner,
        ReviseKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=handoff_id,
            expected_revision=2,
            state=returned,
        ),
    )
    apply_operation(
        root,
        ReviseArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            artifact_id=artifact_id,
            expected_revision=1,
            media_type="text/plain",
            content=b"Changed basis",
        ),
        owner,
    )
    with pytest.raises(FoundationError, match="stale_basis"):
        _apply(
            root,
            space,
            owner,
            ReviseKnowledgeRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                record_id=handoff_id,
                expected_revision=3,
                state=returned.model_copy(
                    update={"status": "matched", "match_basis": "Same document"}
                ),
            ),
        )


def test_current_link_resolves_latest_target_without_rewriting_its_basis(tmp_path: Path) -> None:
    root, space, owner, _, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    source_id, artifact_id, link_id = uuid4(), uuid4(), uuid4()
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=source_id,
            state=_source("Link basis"),
        ),
    )
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            artifact_id=artifact_id,
            media_type="text/plain",
            content=b"Target one",
        ),
        owner,
    )
    _apply(
        root,
        space,
        owner,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=link_id,
            state=MemoryLinkState(
                source=KnowledgeRef(record_id=source_id, revision=1),
                target=KnowledgeRef(record_id=artifact_id, revision=1),
                target_mode="current",
                relation="navigates_to",
                basis=(KnowledgeRef(record_id=source_id, revision=1),),
                explanation="Owner linked this material to the evolving Artifact",
            ),
        ),
    )
    apply_operation(
        root,
        ReviseArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            artifact_id=artifact_id,
            expected_revision=1,
            media_type="text/plain",
            content=b"Target two",
        ),
        owner,
    )
    assert read_knowledge(root, link_id, owner).stale is False
    edges = cast(list[dict[str, object]], read_knowledge_neighbors(root, link_id, owner)["items"])
    assert any(
        edge["to"] == f"{artifact_id}@2" and edge["pinned_target"] == f"{artifact_id}@1"
        for edge in edges
    )
    reverse = cast(
        list[dict[str, object]], read_knowledge_neighbors(root, artifact_id, owner)["items"]
    )
    assert any(edge["from"] == f"{link_id}@1" for edge in reverse)
    first_page = read_knowledge_neighbors(root, link_id, owner, limit=1)
    assert isinstance(first_page["next_cursor"], str)
    second_page = read_knowledge_neighbors(
        root, link_id, owner, limit=1, cursor=first_page["next_cursor"]
    )
    assert second_page["items"]
