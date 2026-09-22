from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest

import zaratustra.foundation.operations as operation_module
from zaratustra.foundation import (
    BootstrapRequest,
    CreateArtifactRequest,
    CreateDecisionRequest,
    CreateGrantRequest,
    DecisionState,
    DeleteArtifactRequest,
    FoundationError,
    GrantState,
    LocalAuthority,
    OperationReceipt,
    ProvenanceRef,
    ReviseArtifactRequest,
    ReviseDecisionRequest,
    RevokeGrantRequest,
    apply_operation,
    authorize_local,
    initialize_space,
    inspect_space,
    read_artifact,
    read_receipt,
)


def ready_space(tmp_path: Path) -> tuple[Path, UUID, LocalAuthority]:
    root = tmp_path / "space"
    root.mkdir()
    info = initialize_space(root)
    owner = authorize_local(root, actor="owner", source_ref="synthetic-owner")
    apply_operation(
        root,
        BootstrapRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        owner,
    )
    return root, info.space_id, owner


def create_artifact(
    root: Path,
    space_id: UUID,
    owner: LocalAuthority,
    content: bytes = b"first",
) -> tuple[CreateArtifactRequest, OperationReceipt]:
    request = CreateArtifactRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor=owner.actor,
        artifact_id=uuid4(),
        media_type="application/octet-stream",
        content=content,
        provenance=(ProvenanceRef(relation="observed-at", external_ref="synthetic:input"),),
    )
    receipt = apply_operation(root, request, owner)
    return request, receipt


def test_exact_text_and_binary_revisions_keep_history_and_provenance(tmp_path: Path) -> None:
    root, space_id, owner = ready_space(tmp_path)
    first_request, _ = create_artifact(root, space_id, owner, "первая версия".encode())
    second = ReviseArtifactRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        artifact_id=first_request.artifact_id,
        expected_revision=1,
        media_type="application/octet-stream",
        content=b"\x00second\xff",
        provenance=(
            ProvenanceRef(relation="revises", record_id=first_request.artifact_id, revision=1),
        ),
    )
    apply_operation(root, second, owner)

    current = read_artifact(root, first_request.artifact_id, owner)
    historical = read_artifact(root, first_request.artifact_id, owner, revision=1)

    assert current.revision == 2 and current.content == b"\x00second\xff"
    assert historical.revision == 1 and historical.content == "первая версия".encode()
    assert current.provenance[0].record_id == first_request.artifact_id
    assert current.content_sha256 != historical.content_sha256


def test_exact_replay_returns_receipt_and_changed_intent_conflicts(tmp_path: Path) -> None:
    root, space_id, owner = ready_space(tmp_path)
    request, first = create_artifact(root, space_id, owner)

    replay = apply_operation(root, request, owner)
    changed = request.model_copy(update={"content": b"different"})
    with pytest.raises(FoundationError) as conflict:
        apply_operation(root, changed, owner)

    assert replay == first
    assert conflict.value.code == "operation_conflict"
    assert read_artifact(root, request.artifact_id, owner).revision == 1


def test_stale_revision_is_honest_and_does_not_replace_current_bytes(tmp_path: Path) -> None:
    root, space_id, owner = ready_space(tmp_path)
    created, _ = create_artifact(root, space_id, owner)
    current = ReviseArtifactRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        artifact_id=created.artifact_id,
        expected_revision=1,
        media_type="text/plain",
        content=b"current",
    )
    apply_operation(root, current, owner)
    stale = current.model_copy(update={"operation_id": uuid4(), "content": b"stale"})

    with pytest.raises(FoundationError) as refusal:
        apply_operation(root, stale, owner)

    assert refusal.value.code == "stale_revision"
    assert read_artifact(root, created.artifact_id, owner).content == b"current"


def test_deleted_artifact_is_terminal_even_at_its_exact_current_revision(tmp_path: Path) -> None:
    root, space_id, owner = ready_space(tmp_path)
    created, _ = create_artifact(root, space_id, owner)
    apply_operation(
        root,
        DeleteArtifactRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            artifact_id=created.artifact_id,
            expected_revision=1,
        ),
        owner,
    )
    revise = ReviseArtifactRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        artifact_id=created.artifact_id,
        expected_revision=2,
        media_type="text/plain",
        content=b"must not return",
    )
    delete_again = DeleteArtifactRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        artifact_id=created.artifact_id,
        expected_revision=2,
    )

    with pytest.raises(FoundationError) as revise_refusal:
        apply_operation(root, revise, owner)
    with pytest.raises(FoundationError) as delete_refusal:
        apply_operation(root, delete_again, owner)
    with pytest.raises(FoundationError) as read_refusal:
        read_artifact(root, created.artifact_id, owner)

    assert revise_refusal.value.code == "content_unavailable"
    assert delete_refusal.value.code == "content_unavailable"
    assert read_refusal.value.code == "content_unavailable"
    assert len(inspect_space(root, owner).records) == 3


def test_grant_revoke_and_receipt_read_are_current_separate_rights(tmp_path: Path) -> None:
    root, space_id, owner = ready_space(tmp_path)
    grant_id = uuid4()
    grant = CreateGrantRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        grant_id=grant_id,
        state=GrantState(grantee="worker", actions=("artifact.write",)),
    )
    apply_operation(root, grant, owner)
    worker = authorize_local(root, actor="worker", source_ref="synthetic-delegation")
    request = CreateArtifactRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="worker",
        artifact_id=uuid4(),
        media_type="text/plain",
        content=b"worker result",
    )
    receipt = apply_operation(root, request, worker)

    with pytest.raises(FoundationError) as hidden:
        read_receipt(root, receipt.operation_id, worker)

    apply_operation(
        root,
        RevokeGrantRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            grant_id=grant_id,
            expected_revision=1,
        ),
        owner,
    )
    denied = request.model_copy(update={"operation_id": uuid4(), "artifact_id": uuid4()})
    with pytest.raises(FoundationError) as revoked:
        apply_operation(root, denied, worker)

    assert hidden.value.code == "permission_denied"
    assert revoked.value.code == "permission_denied"


def test_active_decision_denies_then_revocation_reopens_granted_action(tmp_path: Path) -> None:
    root, space_id, owner = ready_space(tmp_path)
    decision_id = uuid4()
    create = CreateDecisionRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        decision_id=decision_id,
        state=DecisionState(
            statement="Pause artifact mutation while the source is reviewed.",
            effect="deny",
            actions=("artifact.write",),
        ),
    )
    apply_operation(root, create, owner)
    request = CreateArtifactRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        artifact_id=uuid4(),
        media_type="text/plain",
        content=b"blocked",
    )

    with pytest.raises(FoundationError) as denied:
        apply_operation(root, request, owner)

    apply_operation(
        root,
        ReviseDecisionRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            decision_id=decision_id,
            expected_revision=1,
            state=create.state.model_copy(update={"status": "revoked"}),
        ),
        owner,
    )
    receipt = apply_operation(root, request, owner)

    assert denied.value.code == "decision_denied"
    assert receipt.result["revision"] == 1


def test_receipt_write_failure_rolls_back_record_audit_and_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, space_id, owner = ready_space(tmp_path)
    before = inspect_space(root, owner)
    request = CreateArtifactRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        artifact_id=uuid4(),
        media_type="text/plain",
        content=b"must roll back",
    )

    def fail_receipt(connection: object, receipt: OperationReceipt) -> None:
        raise sqlite3.OperationalError("synthetic receipt failure")

    monkeypatch.setattr(operation_module, "_write_receipt", fail_receipt)
    with pytest.raises(FoundationError) as failure:
        apply_operation(root, request, owner)
    after = inspect_space(root, owner)

    assert failure.value.code == "storage"
    assert after.space.state_revision == before.space.state_revision
    assert after.operation_count == before.operation_count
    assert after.audit_count == before.audit_count
    assert after.receipt_count == before.receipt_count
    assert request.artifact_id not in {record.record_id for record in after.records}


def test_lost_response_is_recovered_by_authorized_receipt_read(tmp_path: Path) -> None:
    root, space_id, owner = ready_space(tmp_path)
    request, committed = create_artifact(root, space_id, owner, b"committed once")

    recovered = read_receipt(root, request.operation_id, owner)

    assert recovered == committed
    assert read_artifact(root, request.artifact_id, owner).content == b"committed once"


def test_concurrent_revisions_have_one_winner_and_one_stale_refusal(tmp_path: Path) -> None:
    root, space_id, owner = ready_space(tmp_path)
    created, _ = create_artifact(root, space_id, owner)
    barrier = Barrier(2)

    def revise(content: bytes) -> str:
        request = ReviseArtifactRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            artifact_id=created.artifact_id,
            expected_revision=1,
            media_type="text/plain",
            content=content,
        )
        barrier.wait()
        try:
            return apply_operation(root, request, owner).kind
        except FoundationError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(revise, (b"left", b"right")))

    assert sorted(outcomes) == ["revise_artifact", "stale_revision"]
    assert read_artifact(root, created.artifact_id, owner).revision == 2


def test_concurrent_exact_duplicate_has_one_effect_and_one_receipt(tmp_path: Path) -> None:
    root, space_id, owner = ready_space(tmp_path)
    request = CreateArtifactRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        artifact_id=uuid4(),
        media_type="text/plain",
        content=b"same operation",
    )
    barrier = Barrier(2)

    def apply_same(_index: int) -> OperationReceipt:
        barrier.wait()
        return apply_operation(root, request, owner)

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(apply_same, (1, 2)))

    assert receipts[0] == receipts[1]
    assert read_artifact(root, request.artifact_id, owner).revision == 1
