from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_composition import _delete_after_upgrade
from zaratustra.foundation import (
    ALL_ACTIONS,
    AcceptWorkRequest,
    Action,
    ActivityState,
    ArtifactRef,
    BootstrapRequest,
    CreateActivityRequest,
    CreateArtifactRequest,
    CreateGrantRequest,
    CreateWorkRequest,
    DeleteActivityRequest,
    DeleteArtifactRequest,
    DeleteWorkRequest,
    FoundationError,
    GrantState,
    LinkedOutput,
    LinkWorkOutputRequest,
    LocalAuthority,
    OutputContract,
    RecoverRequest,
    RevokeGrantRequest,
    WorkState,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    initialize_space,
    inspect_space,
    read_activity,
    read_artifact,
    read_operation_audit,
    read_receipt,
    read_work,
    restore_backup,
    upgrade_space,
)
from zaratustra.foundation.storage import space_connection


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
    assert upgrade_space(root, owner).schema_version == 2
    return root, info.space_id, owner


def artifact(root: Path, space_id: UUID, owner: LocalAuthority, media_type: str) -> UUID:
    artifact_id = uuid4()
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            artifact_id=artifact_id,
            media_type=media_type,
            content=b"fictional content",
        ),
        owner,
    )
    return artifact_id


def activity(root: Path, space_id: UUID, owner: LocalAuthority) -> UUID:
    activity_id = uuid4()
    apply_operation(
        root,
        CreateActivityRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            activity_id=activity_id,
            state=ActivityState(title="Fictional development", goal="Continue development"),
        ),
        owner,
    )
    return activity_id


def work(
    root: Path,
    space_id: UUID,
    owner: LocalAuthority,
    activity_id: UUID,
    input_id: UUID,
) -> UUID:
    work_id = uuid4()
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            work_id=work_id,
            state=WorkState(
                activity_id=activity_id,
                goal="Produce one checked fictional report",
                inputs=(ArtifactRef(artifact_id=input_id, revision=1),),
                constraints=("Synthetic content only",),
                expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    return work_id


def link(
    root: Path,
    space_id: UUID,
    owner: LocalAuthority,
    work_id: UUID,
    result_id: UUID,
) -> LinkWorkOutputRequest:
    request = LinkWorkOutputRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor=owner.actor,
        work_id=work_id,
        expected_revision=1,
        output=LinkedOutput(slot="report", artifact=ArtifactRef(artifact_id=result_id, revision=1)),
    )
    apply_operation(root, request, owner)
    return request


def test_explicit_acceptance_keeps_activity_ongoing_and_exact_history(tmp_path: Path) -> None:
    root, space_id, owner = ready_space(tmp_path)
    input_id = artifact(root, space_id, owner, "text/plain")
    result_id = artifact(root, space_id, owner, "text/plain")
    activity_id = activity(root, space_id, owner)
    work_id = work(root, space_id, owner, activity_id, input_id)

    with pytest.raises(FoundationError, match="output_incomplete"):
        apply_operation(
            root,
            AcceptWorkRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor=owner.actor,
                work_id=work_id,
                expected_revision=1,
                basis="Checked",
            ),
            owner,
        )
    assert read_work(root, work_id, owner).state.status == "proposed"
    linked = link(root, space_id, owner, work_id, result_id)
    assert read_work(root, work_id, owner).state.status == "proposed"
    assert read_work(root, work_id, owner, revision=1).state.linked_outputs == ()
    accepted = AcceptWorkRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor=owner.actor,
        work_id=work_id,
        expected_revision=2,
        basis="Exact named result checked against the output contract",
    )
    receipt = apply_operation(root, accepted, owner)
    assert apply_operation(root, accepted, owner) == receipt
    assert read_receipt(root, accepted.operation_id, owner) == receipt
    audit = read_operation_audit(root, accepted.operation_id, owner)
    assert audit.authority_source == "synthetic-owner"
    assert audit.target_refs[0].record_id == work_id
    assert audit.target_refs[0].revision == 3
    assert {item.record_id for item in audit.target_refs[1:]} == {input_id, result_id}
    assert audit.grant_refs
    current = read_work(root, work_id, owner)
    assert current.revision == 3
    assert current.state.status == "succeeded"
    assert current.state.acceptance is not None
    assert current.state.acceptance.operation_id == accepted.operation_id
    assert current.state.acceptance.authority_source == "synthetic-owner"
    assert current.state.linked_outputs[0].artifact.artifact_id == result_id
    assert current.unavailable_refs == ()
    assert read_activity(root, activity_id, owner).state.status == "ongoing"
    assert read_work(root, work_id, owner, revision=2).state.status == "proposed"
    assert linked.output.slot == "report"

    with pytest.raises(FoundationError, match="stale_revision"):
        apply_operation(
            root,
            AcceptWorkRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor=owner.actor,
                work_id=work_id,
                expected_revision=2,
                basis="Stale",
            ),
            owner,
        )


def test_output_type_and_separate_accept_right_are_enforced(tmp_path: Path) -> None:
    root, space_id, owner = ready_space(tmp_path)
    input_id = artifact(root, space_id, owner, "text/plain")
    wrong_id = artifact(root, space_id, owner, "application/json")
    result_id = artifact(root, space_id, owner, "text/plain")
    activity_id = activity(root, space_id, owner)
    work_id = work(root, space_id, owner, activity_id, input_id)
    with pytest.raises(FoundationError, match="output_mismatch"):
        link(root, space_id, owner, work_id, wrong_id)

    scoped_rights: tuple[tuple[Action, Literal["work", "artifact"], UUID], ...] = (
        ("work.write", "work", work_id),
        ("record.read", "artifact", result_id),
        ("record.read", "artifact", input_id),
    )
    for action, resource_type, resource_id in scoped_rights:
        apply_operation(
            root,
            CreateGrantRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor="owner",
                grant_id=uuid4(),
                state=GrantState(
                    grantee="worker",
                    actions=(action,),
                    resource_type=resource_type,
                    resource_id=resource_id,
                ),
            ),
            owner,
        )
    worker = authorize_local(root, actor="worker", source_ref="synthetic-worker")
    link(root, space_id, worker, work_id, result_id)
    with pytest.raises(FoundationError) as read_refusal:
        read_work(root, work_id, worker)
    assert read_refusal.value.code == "permission_denied"
    with pytest.raises(FoundationError) as refusal:
        apply_operation(
            root,
            AcceptWorkRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor="worker",
                work_id=work_id,
                expected_revision=2,
                basis="Checked",
            ),
            worker,
        )
    assert refusal.value.code == "permission_denied"
    assert read_work(root, work_id, owner).state.status == "proposed"


def test_existing_stage2_grant_does_not_silently_gain_new_actions(tmp_path: Path) -> None:
    root = tmp_path / "space"
    root.mkdir()
    info = initialize_space(root)
    owner = authorize_local(root, actor="owner", source_ref="synthetic-owner")
    root_grant_id = uuid4()
    apply_operation(
        root,
        BootstrapRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="owner",
            decision_id=uuid4(),
            grant_id=root_grant_id,
        ),
        owner,
    )
    stage2_actions: tuple[Action, ...] = tuple(
        action
        for action in ALL_ACTIONS
        if action not in {"activity.write", "work.write", "work.accept"}
    )
    apply_operation(
        root,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="owner",
            grant_id=uuid4(),
            state=GrantState(grantee="owner", actions=stage2_actions),
        ),
        owner,
    )
    apply_operation(
        root,
        RevokeGrantRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="owner",
            grant_id=root_grant_id,
            expected_revision=1,
        ),
        owner,
    )
    assert upgrade_space(root, owner).schema_version == 2
    request = CreateActivityRequest(
        operation_id=uuid4(),
        space_id=info.space_id,
        actor="owner",
        activity_id=uuid4(),
        state=ActivityState(title="Fictional", goal="Fictional goal"),
    )
    with pytest.raises(FoundationError) as refusal:
        apply_operation(root, request, owner)
    assert refusal.value.code == "permission_denied"
    apply_operation(
        root,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="owner",
            grant_id=uuid4(),
            state=GrantState(
                grantee="owner",
                actions=("activity.write", "work.write", "work.accept"),
            ),
        ),
        owner,
    )
    apply_operation(root, request, owner)
    assert read_activity(root, request.activity_id, owner).state.title == "Fictional"


def test_deleted_subject_redacts_old_receipts_but_replays_its_delete(
    tmp_path: Path,
) -> None:
    root, space_id, owner = ready_space(tmp_path)
    input_id = artifact(root, space_id, owner, "text/plain")
    result_id = artifact(root, space_id, owner, "text/plain")
    unaffected_operation = read_artifact(root, result_id, owner).operation_id
    activity_id = uuid4()
    create_activity = CreateActivityRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        activity_id=activity_id,
        state=ActivityState(title="Fictional", goal="Continue"),
    )
    apply_operation(root, create_activity, owner)
    work_id = uuid4()
    create_work = CreateWorkRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        work_id=work_id,
        state=WorkState(
            activity_id=activity_id,
            goal="Make one fictional result",
            inputs=(ArtifactRef(artifact_id=input_id, revision=1),),
            expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
        ),
    )
    apply_operation(root, create_work, owner)
    linked = link(root, space_id, owner, work_id, result_id)
    accepted = AcceptWorkRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        work_id=work_id,
        expected_revision=2,
        basis="Exact fictional output checked",
    )
    apply_operation(root, accepted, owner)
    delete_work = DeleteWorkRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        work_id=work_id,
        expected_revision=3,
    )
    deletion_receipt = apply_operation(root, delete_work, owner)
    assert apply_operation(root, delete_work, owner) == deletion_receipt
    assert read_receipt(root, delete_work.operation_id, owner) == deletion_receipt
    for previous in (create_work, linked, accepted):
        with pytest.raises(FoundationError) as replay:
            apply_operation(root, previous, owner)
        assert replay.value.code == "history_unavailable"
        with pytest.raises(FoundationError) as missing:
            read_receipt(root, previous.operation_id, owner)
        assert missing.value.code == "not_found"
        assert read_operation_audit(root, previous.operation_id, owner).authority_source
    with space_connection(root) as (connection, _):
        old_fingerprints = [
            connection.execute(
                "SELECT fingerprint FROM operations WHERE operation_id = ?",
                (str(previous.operation_id),),
            ).fetchone()[0]
            for previous in (create_work, linked, accepted)
        ]
        delete_fingerprint = connection.execute(
            "SELECT fingerprint FROM operations WHERE operation_id = ?",
            (str(delete_work.operation_id),),
        ).fetchone()[0]
    assert old_fingerprints == ["DELETED", "DELETED", "DELETED"]
    assert delete_fingerprint == deletion_receipt.fingerprint
    assert read_receipt(root, unaffected_operation, owner).kind == "create_artifact"
    assert read_artifact(root, result_id, owner).content == b"fictional content"

    delete_activity = DeleteActivityRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        activity_id=activity_id,
        expected_revision=1,
    )
    activity_deletion = apply_operation(root, delete_activity, owner)
    assert apply_operation(root, delete_activity, owner) == activity_deletion
    with pytest.raises(FoundationError) as replay:
        apply_operation(root, create_activity, owner)
    assert replay.value.code == "history_unavailable"
    with pytest.raises(FoundationError) as missing:
        read_receipt(root, create_activity.operation_id, owner)
    assert missing.value.code == "not_found"
    assert read_receipt(root, unaffected_operation, owner).kind == "create_artifact"

    root_grant_id = next(
        record.record_id
        for record in inspect_space(root, owner).records
        if record.kind == "grant" and record.status == "active"
    )
    apply_operation(
        root,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            grant_id=uuid4(),
            state=GrantState(grantee="owner", actions=("grant.write",)),
        ),
        owner,
    )
    apply_operation(
        root,
        RevokeGrantRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            grant_id=root_grant_id,
            expected_revision=1,
        ),
        owner,
    )
    with pytest.raises(FoundationError) as denied:
        apply_operation(root, create_work, owner)
    assert denied.value.code == "permission_denied"
    with pytest.raises(FoundationError) as denied_delete:
        apply_operation(root, delete_work, owner)
    assert denied_delete.value.code == "permission_denied"


def test_subject_delete_contaminates_backup_and_keeps_stage2_artifact(
    tmp_path: Path,
) -> None:
    root, space_id, owner = ready_space(tmp_path)
    input_id = artifact(root, space_id, owner, "text/plain")
    activity_id = activity(root, space_id, owner)
    work_id = work(root, space_id, owner, activity_id, input_id)
    backup = create_backup(root, uuid4(), owner)
    with pytest.raises(FoundationError, match="dependent_work"):
        apply_operation(
            root,
            DeleteActivityRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor="owner",
                activity_id=activity_id,
                expected_revision=1,
            ),
            owner,
        )
    apply_operation(
        root,
        DeleteWorkRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            expected_revision=1,
        ),
        owner,
    )
    with pytest.raises(FoundationError) as refusal:
        read_work(root, work_id, owner)
    assert refusal.value.code == "content_unavailable"
    restored = tmp_path / "refused-restore"
    restored.mkdir()
    recovery = authorize_recovery(actor="owner", source_ref="fresh-synthetic")
    with pytest.raises(FoundationError, match="invalid_backup"):
        restore_backup(backup.package, restored, recovery)
    assert complete_deletions(root, owner).live_store_sanitized
    assert not backup.package.exists()
    apply_operation(
        root,
        DeleteActivityRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            activity_id=activity_id,
            expected_revision=1,
        ),
        owner,
    )
    assert complete_deletions(root, owner).live_store_sanitized
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_activity(root, activity_id, owner)
    assert read_artifact(root, input_id, owner).content == b"fictional content"
    assert inspect_space(root, owner).pending_deletions == 0


def test_schema2_backup_restores_quarantined_and_deleted_result_is_unavailable(
    tmp_path: Path,
) -> None:
    root, space_id, owner = ready_space(tmp_path)
    input_id = artifact(root, space_id, owner, "text/plain")
    result_id = artifact(root, space_id, owner, "text/plain")
    activity_id = activity(root, space_id, owner)
    work_id = work(root, space_id, owner, activity_id, input_id)
    link(root, space_id, owner, work_id, result_id)
    apply_operation(
        root,
        AcceptWorkRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            work_id=work_id,
            expected_revision=2,
            basis="Synthetic accepted result",
        ),
        owner,
    )
    backup = create_backup(root, uuid4(), owner)
    destination = tmp_path / "restored"
    destination.mkdir()
    recovery = authorize_recovery(actor="owner", source_ref="fresh-synthetic")
    restored = restore_backup(backup.package, destination, recovery)
    assert restored.schema_version == 2 and restored.recovery_state == "quarantined"
    with pytest.raises(FoundationError, match="permission_denied"):
        read_work(destination, work_id, owner)
    apply_operation(
        destination,
        RecoverRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        recovery,
    )
    new_owner = authorize_local(destination, actor="owner", source_ref="restored-synthetic")
    assert read_work(destination, work_id, new_owner).state.status == "succeeded"
    assert read_activity(destination, activity_id, new_owner).state.status == "ongoing"
    # The acceptance basis depends on the result: schema 2 needs the explicit upgrade first.
    _delete_after_upgrade(
        root,
        space_id,
        owner,
        DeleteArtifactRequest,
        artifact_id=result_id,
        expected_revision=1,
    )
    current = read_work(root, work_id, owner)
    assert current.state.status == "succeeded"
    assert current.state.acceptance is not None and current.state.acceptance.basis is None
    assert current.unavailable_refs == (ArtifactRef(artifact_id=result_id, revision=1),)
    assert complete_deletions(root, owner).live_store_sanitized
