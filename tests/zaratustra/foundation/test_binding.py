"""Accepted results cross Activities through durable exact Binding versions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from zaratustra.foundation import (
    AcceptWorkRequest,
    ActivityState,
    ArtifactRef,
    BindingChildTemplate,
    BindingCondition,
    BindingDefinition,
    BindingNewWork,
    BindingOfferWork,
    BootstrapRequest,
    ChoiceState,
    CreateActivityRequest,
    CreateArtifactRequest,
    CreateBindingVersionRequest,
    CreateDecisionRequest,
    CreateGrantRequest,
    CreateMethodVersionRequest,
    CreateResourceRequest,
    CreateWorkRequest,
    DecisionRef,
    DecisionScope,
    DeleteArtifactRequest,
    DeleteMethodVersionRequest,
    DeleteWorkRequest,
    FireBindingRequest,
    FoundationError,
    GrantState,
    LinkedOutput,
    LinkWorkOutputRequest,
    LocalAuthority,
    MethodDefinition,
    MethodRef,
    NamedInput,
    OperationReceipt,
    OutputContract,
    PlanCondition,
    PlanOutputBinding,
    RecoverRequest,
    RecoveryAuthority,
    ResolveBindingOfferRequest,
    ResourceState,
    ReviseDecisionRequest,
    SetBindingStateRequest,
    StartAttemptRequest,
    WorkState,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    initialize_space,
    read_binding_firings,
    read_binding_input_history,
    read_binding_offer,
    read_binding_version,
    read_execution,
    read_space,
    read_work,
    read_work_plan,
    restore_backup,
    upgrade_binding_space,
    upgrade_child_execution_space,
    upgrade_composition_space,
    upgrade_continuation_space,
    upgrade_execution_space,
    upgrade_parent_execution_space,
    upgrade_plan_revision_space,
    upgrade_space,
)


def _apply(
    root: Path,
    space: UUID,
    owner: LocalAuthority | RecoveryAuthority,
    kind: type[Any],
    **fields: object,
) -> OperationReceipt:
    return apply_operation(
        root, kind(operation_id=uuid4(), space_id=space, actor="owner", **fields), owner
    )


def _binding_result(receipt: OperationReceipt) -> dict[str, object]:
    return cast(list[dict[str, object]], receipt.result["bindings"])[0]


def _ready(tmp_path: Path) -> tuple[Path, UUID, LocalAuthority, UUID, UUID]:
    root = tmp_path / "space"
    root.mkdir()
    info = initialize_space(root)
    owner = authorize_local(root, actor="owner", source_ref="fictional-owner")
    _apply(root, info.space_id, owner, BootstrapRequest, decision_id=uuid4(), grant_id=uuid4())
    for upgrade in (
        upgrade_space,
        upgrade_execution_space,
        upgrade_continuation_space,
        upgrade_composition_space,
        upgrade_child_execution_space,
        upgrade_plan_revision_space,
        upgrade_parent_execution_space,
        upgrade_binding_space,
    ):
        upgrade(root, owner)
    assert read_space(root).schema_version == 9
    producer, consumer = uuid4(), uuid4()
    _apply(
        root,
        info.space_id,
        owner,
        CreateActivityRequest,
        activity_id=producer,
        state=ActivityState(title="Fictional design", goal="Publish a checked design"),
    )
    _apply(
        root,
        info.space_id,
        owner,
        CreateActivityRequest,
        activity_id=consumer,
        state=ActivityState(title="Fictional planning", goal="Use accepted designs"),
    )
    return root, info.space_id, owner, producer, consumer


def _accepted(
    root: Path,
    space: UUID,
    owner: LocalAuthority,
    activity_id: UUID,
) -> tuple[UUID, UUID, OperationReceipt]:
    artifact_id, work_id = uuid4(), uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=artifact_id,
        media_type="text/plain",
        content=b"fictional accepted result",
    )
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=work_id,
        state=WorkState(
            activity_id=activity_id,
            goal="Produce fictional design",
            expected_outputs=(OutputContract(slot="design", media_type="text/plain"),),
        ),
    )
    _apply(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=work_id,
        expected_revision=1,
        output=LinkedOutput(
            slot="design", artifact=ArtifactRef(artifact_id=artifact_id, revision=1)
        ),
    )
    accepted = _apply(
        root,
        space,
        owner,
        AcceptWorkRequest,
        work_id=work_id,
        expected_revision=2,
        basis="Fictional design checked",
    )
    return work_id, artifact_id, accepted


def _new_definition(
    producer: UUID,
    consumer: UUID,
    method: MethodRef,
    fixed: ArtifactRef | None = None,
    *,
    goal: str,
) -> BindingDefinition:
    return BindingDefinition(
        source_activity_id=producer,
        source_slot="design",
        media_type="text/plain",
        target=BindingNewWork(
            activity_id=consumer,
            method=method,
            goal=goal,
            named_inputs=("source",),
            fixed_inputs=(NamedInput(slot="context", artifact=fixed),) if fixed else (),
            expected_outputs=(OutputContract(slot="plan", media_type="text/plain"),),
            children=(
                BindingChildTemplate(
                    role="draft",
                    goal="Draft a plan from design",
                    consume_source=True,
                    expected_outputs=(OutputContract(slot="plan", media_type="text/plain"),),
                ),
            ),
            output_bindings=(
                PlanOutputBinding(
                    parent_slot="plan", role="draft", child_slot="plan", media_type="text/plain"
                ),
            ),
            completion=PlanCondition(kind="work_succeeded", role="draft"),
            rationale="Continue accepted designs in planning",
            source_ref="fictional-owner-plan",
        ),
        basis="Fictional owner-approved recurring transfer",
    )


def test_binding_creates_once_then_survives_restart_version_and_restore(tmp_path: Path) -> None:
    root, space, owner, producer, consumer = _ready(tmp_path)
    fixed_id = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=fixed_id,
        media_type="text/markdown",
        content=b"fictional planning context",
    )
    fixed = ArtifactRef(artifact_id=fixed_id, revision=1)
    method_id = uuid4()
    method = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=method_id,
        version=1,
        definition=MethodDefinition(
            instruction="Plan from the accepted design",
            named_inputs=(
                OutputContract(slot="source", media_type="text/plain"),
                OutputContract(slot="context", media_type="text/markdown"),
            ),
            named_outputs=(OutputContract(slot="plan", media_type="text/plain"),),
            source_ref="fictional-method",
        ),
    )
    ref = MethodRef(method_id=method_id, version=1, checksum=cast(str, method.result["checksum"]))
    binding_id = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateBindingVersionRequest,
        binding_id=binding_id,
        version=1,
        definition=_new_definition(producer, consumer, ref, fixed, goal="Plan the first design"),
    )
    with pytest.raises(FoundationError, match="method_in_use"):
        _apply(
            root,
            space,
            owner,
            DeleteMethodVersionRequest,
            method_id=method_id,
            version=1,
            checksum=ref.checksum,
        )
    _apply(
        root,
        space,
        owner,
        SetBindingStateRequest,
        binding_id=binding_id,
        version=1,
        expected_state_revision=1,
        state="enabled",
    )
    work_id, artifact_id, accepted = _accepted(root, space, owner, producer)
    assert _binding_result(accepted)["outcome"] == "created", accepted.result
    first = read_binding_firings(root, binding_id, owner)
    assert len(first) == 1
    target_id = cast(UUID, first[0].consumer_work_id)
    reopened = authorize_local(root, actor="owner", source_ref="fictional-restart")
    target = read_work(root, target_id, reopened)
    assert target.state.activity_id == consumer
    assert target.state.inputs == (ArtifactRef(artifact_id=artifact_id, revision=1), fixed)
    assert read_work_plan(root, target_id, reopened).plan.children[0].state.inputs == (
        ArtifactRef(artifact_id=artifact_id, revision=1),
    )
    assert read_binding_version(root, binding_id, 1, reopened).state == "enabled"
    repeated = _apply(
        root,
        space,
        reopened,
        FireBindingRequest,
        binding_id=binding_id,
        version=1,
        producer_work_id=work_id,
        accepted_work_revision=3,
    )
    assert repeated.result["outcome"] == "repeated"
    assert len(read_binding_firings(root, binding_id, reopened)) == 1
    _apply(
        root,
        space,
        reopened,
        CreateBindingVersionRequest,
        binding_id=binding_id,
        version=2,
        definition=_new_definition(producer, consumer, ref, fixed, goal="Plan later designs"),
    )
    assert read_binding_version(root, binding_id, 1, reopened).state == "retired"
    _apply(
        root,
        space,
        reopened,
        SetBindingStateRequest,
        binding_id=binding_id,
        version=2,
        expected_state_revision=1,
        state="enabled",
    )
    _accepted(root, space, reopened, producer)
    assert len(read_binding_firings(root, binding_id, reopened)) == 2
    _apply(
        root,
        space,
        reopened,
        SetBindingStateRequest,
        binding_id=binding_id,
        version=2,
        expected_state_revision=2,
        state="paused",
    )
    held_work, _held_artifact, _held = _accepted(root, space, reopened, producer)
    assert len(read_binding_firings(root, binding_id, reopened)) == 2
    with pytest.raises(FoundationError, match="binding_inactive"):
        _apply(
            root,
            space,
            reopened,
            FireBindingRequest,
            binding_id=binding_id,
            version=2,
            producer_work_id=held_work,
            accepted_work_revision=3,
        )
    _apply(
        root,
        space,
        reopened,
        SetBindingStateRequest,
        binding_id=binding_id,
        version=2,
        expected_state_revision=3,
        state="enabled",
    )
    assert (
        _apply(
            root,
            space,
            reopened,
            FireBindingRequest,
            binding_id=binding_id,
            version=2,
            producer_work_id=held_work,
            accepted_work_revision=3,
        ).result["outcome"]
        == "created"
    )
    with pytest.raises(FoundationError, match="event_before_version"):
        _apply(
            root,
            space,
            reopened,
            FireBindingRequest,
            binding_id=binding_id,
            version=2,
            producer_work_id=work_id,
            accepted_work_revision=3,
        )
    assert (
        _apply(
            root,
            space,
            reopened,
            FireBindingRequest,
            binding_id=binding_id,
            version=2,
            producer_work_id=work_id,
            accepted_work_revision=3,
            backfill=True,
            basis="Explicitly include the accepted earlier design",
        ).result["outcome"]
        == "created"
    )
    assert len(read_binding_firings(root, binding_id, reopened)) == 4
    assert any(
        item.basis == "Explicitly include the accepted earlier design"
        for item in read_binding_firings(root, binding_id, reopened)
    )
    backup = create_backup(root, uuid4(), reopened)
    restored = tmp_path / "restored"
    restored.mkdir()
    recovery = authorize_recovery(actor="owner", source_ref="fictional-recovery")
    assert restore_backup(backup.package, restored, recovery).recovery_state == "quarantined"
    _apply(restored, space, recovery, RecoverRequest, decision_id=uuid4(), grant_id=uuid4())
    restored_owner = authorize_local(restored, actor="owner", source_ref="fictional-restored")
    assert len(read_binding_firings(restored, binding_id, restored_owner)) == 4
    assert read_work(restored, target_id, restored_owner).state.inputs == target.state.inputs
    _apply(root, space, reopened, DeleteArtifactRequest, artifact_id=fixed_id, expected_revision=1)
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_binding_version(root, binding_id, 2, reopened)
    assert all(
        item.basis is None
        for item in read_binding_firings(root, binding_id, reopened)
        if item.version == 2
    )


def test_binding_offer_requires_explicit_resolution(tmp_path: Path) -> None:
    root, space, owner, producer, consumer = _ready(tmp_path)
    target_id = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=target_id,
        state=WorkState(
            activity_id=consumer,
            goal="Review an offered design",
            expected_outputs=(OutputContract(slot="review", media_type="text/plain"),),
        ),
    )
    binding_id = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateBindingVersionRequest,
        binding_id=binding_id,
        version=1,
        definition=BindingDefinition(
            source_activity_id=producer,
            source_slot="design",
            media_type="text/plain",
            basis="Fictional transfer",
            target=BindingOfferWork(work_id=target_id, input_slot="design"),
        ),
    )
    _apply(
        root,
        space,
        owner,
        SetBindingStateRequest,
        binding_id=binding_id,
        version=1,
        expected_state_revision=1,
        state="enabled",
    )
    _producer, artifact_id, receipt = _accepted(root, space, owner, producer)
    offer_id = UUID(str(_binding_result(receipt)["offer_id"]))
    assert read_binding_offer(root, offer_id, owner).status == "open"
    assert read_work(root, target_id, owner).state.inputs == ()
    workspace = tmp_path / "consumer-workspace"
    workspace.mkdir()
    resource_id, attempt_id = uuid4(), uuid4()
    _apply(
        root,
        space,
        owner,
        CreateResourceRequest,
        resource_id=resource_id,
        work_id=target_id,
        state=ResourceState(label="Fictional consumer resource", root=workspace, limit_units=100),
    )
    _apply(
        root,
        space,
        owner,
        StartAttemptRequest,
        attempt_id=attempt_id,
        work_id=target_id,
        expected_work_revision=1,
        resource_id=resource_id,
        expected_resource_revision=1,
        session_id=uuid4(),
    )
    assert read_execution(root, target_id, owner).attempts[-1].status == "active"
    _apply(
        root,
        space,
        owner,
        ResolveBindingOfferRequest,
        offer_id=offer_id,
        expected_consumer_revision=1,
        decision="accept",
        basis="Use in the next review",
    )
    resolved = read_binding_offer(root, offer_id, owner)
    assert resolved.status == "accepted" and resolved.resolution_basis == "Use in the next review"
    assert read_execution(root, target_id, owner).attempts[-1].status == "interrupted"
    assert read_work(root, target_id, owner).state.inputs == (
        ArtifactRef(artifact_id=artifact_id, revision=1),
    )
    assert read_binding_input_history(root, target_id, owner)[0].input_slot == "design"
    with pytest.raises(FoundationError, match="offer_unavailable"):
        _apply(
            root,
            space,
            owner,
            ResolveBindingOfferRequest,
            offer_id=offer_id,
            expected_consumer_revision=1,
            decision="accept",
            basis="Repeat",
        )
    _next_producer, next_artifact, next_receipt = _accepted(root, space, owner, producer)
    next_offer = UUID(str(_binding_result(next_receipt)["offer_id"]))
    _apply(
        root,
        space,
        owner,
        ResolveBindingOfferRequest,
        offer_id=next_offer,
        expected_consumer_revision=2,
        decision="accept",
        basis="Use newer design",
    )
    assert read_work(root, target_id, owner).state.inputs == (
        ArtifactRef(artifact_id=next_artifact, revision=1),
    )
    assert [item.revision for item in read_binding_input_history(root, target_id, owner)] == [2, 3]
    _third_producer, third_artifact, third_receipt = _accepted(root, space, owner, producer)
    third_offer = UUID(str(_binding_result(third_receipt)["offer_id"]))
    _apply(
        root, space, owner, DeleteArtifactRequest, artifact_id=third_artifact, expected_revision=1
    )
    assert read_binding_offer(root, third_offer, owner).status == "unavailable"
    with pytest.raises(FoundationError, match="offer_unavailable"):
        _apply(
            root,
            space,
            owner,
            ResolveBindingOfferRequest,
            offer_id=third_offer,
            expected_consumer_revision=3,
            decision="accept",
            basis="Deleted result",
        )
    _apply(root, space, owner, DeleteWorkRequest, work_id=target_id, expected_revision=3)
    complete_deletions(root, owner)
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_binding_version(root, binding_id, 1, owner)
    assert read_binding_offer(root, offer_id, owner).resolution_basis is None
    assert read_binding_input_history(root, target_id, owner) == ()


def test_binding_uses_exact_active_source_choice_and_keeps_blocked_history(tmp_path: Path) -> None:
    root, space, owner, producer, consumer = _ready(tmp_path)
    target_id, decision_id, binding_id = uuid4(), uuid4(), uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=target_id,
        state=WorkState(
            activity_id=consumer,
            goal="Review approved design",
            expected_outputs=(OutputContract(slot="review", media_type="text/plain"),),
        ),
    )
    choice = ChoiceState(
        statement="Fictional owner approval",
        name="transfer",
        value="approved",
        scope=DecisionScope(kind="activity", record_id=producer),
    )
    _apply(root, space, owner, CreateDecisionRequest, decision_id=decision_id, state=choice)
    _apply(
        root,
        space,
        owner,
        CreateBindingVersionRequest,
        binding_id=binding_id,
        version=1,
        definition=BindingDefinition(
            source_activity_id=producer,
            source_slot="design",
            media_type="text/plain",
            target=BindingOfferWork(work_id=target_id, input_slot="design"),
            condition=BindingCondition(
                choice=DecisionRef(decision_id=decision_id, revision=1),
                name="transfer",
                value="approved",
            ),
            basis="Transfer only under the exact active choice",
        ),
    )
    _apply(
        root,
        space,
        owner,
        SetBindingStateRequest,
        binding_id=binding_id,
        version=1,
        expected_state_revision=1,
        state="enabled",
    )
    _accepted(root, space, owner, producer)
    assert read_binding_firings(root, binding_id, owner)[0].outcome == "offered"
    _apply(
        root,
        space,
        owner,
        ReviseDecisionRequest,
        decision_id=decision_id,
        expected_revision=1,
        state=choice.model_copy(update={"status": "revoked"}),
    )
    _, _, receipt = _accepted(root, space, owner, producer)
    assert _binding_result(receipt)["reason"] == "stale_decision"
    firings = read_binding_firings(root, binding_id, owner)
    assert [item.outcome for item in firings] == ["offered", "blocked"]
    assert firings[1].reason == "stale_decision"


def test_binding_fire_checks_current_consumer_right(tmp_path: Path) -> None:
    root, space, owner, producer, consumer = _ready(tmp_path)
    target_id, binding_id = uuid4(), uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=target_id,
        state=WorkState(
            activity_id=consumer,
            goal="Review transferred design",
            expected_outputs=(OutputContract(slot="review", media_type="text/plain"),),
        ),
    )
    _apply(
        root,
        space,
        owner,
        CreateBindingVersionRequest,
        binding_id=binding_id,
        version=1,
        definition=BindingDefinition(
            source_activity_id=producer,
            source_slot="design",
            media_type="text/plain",
            target=BindingOfferWork(work_id=target_id, input_slot="design"),
            basis="Trial transfer with current rights",
        ),
    )
    producer_work, _, _ = _accepted(root, space, owner, producer)
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest,
        grant_id=uuid4(),
        state=GrantState(grantee="worker", actions=("record.read",)),
    )
    worker = authorize_local(root, actor="worker", source_ref="fictional-worker")
    with pytest.raises(FoundationError, match="permission_denied"):
        apply_operation(
            root,
            FireBindingRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="worker",
                binding_id=binding_id,
                version=1,
                producer_work_id=producer_work,
                accepted_work_revision=3,
            ),
            worker,
        )
    assert read_binding_firings(root, binding_id, owner) == ()


def test_offer_to_composite_work_revises_its_plan_and_exact_input(tmp_path: Path) -> None:
    root, space, owner, producer, consumer = _ready(tmp_path)
    method_id, create_binding_id, offer_binding_id = uuid4(), uuid4(), uuid4()
    method = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=method_id,
        version=1,
        definition=MethodDefinition(
            instruction="Plan from the accepted design",
            named_inputs=(OutputContract(slot="source", media_type="text/plain"),),
            named_outputs=(OutputContract(slot="plan", media_type="text/plain"),),
            source_ref="fictional-composite-method",
        ),
    )
    ref = MethodRef(method_id=method_id, version=1, checksum=cast(str, method.result["checksum"]))
    _apply(
        root,
        space,
        owner,
        CreateBindingVersionRequest,
        binding_id=create_binding_id,
        version=1,
        definition=_new_definition(producer, consumer, ref, goal="Plan one design"),
    )
    _apply(
        root,
        space,
        owner,
        SetBindingStateRequest,
        binding_id=create_binding_id,
        version=1,
        expected_state_revision=1,
        state="enabled",
    )
    _, first_artifact, _ = _accepted(root, space, owner, producer)
    target_id = cast(UUID, read_binding_firings(root, create_binding_id, owner)[0].consumer_work_id)
    _apply(
        root,
        space,
        owner,
        CreateBindingVersionRequest,
        binding_id=offer_binding_id,
        version=1,
        definition=BindingDefinition(
            source_activity_id=producer,
            source_slot="design",
            media_type="text/plain",
            target=BindingOfferWork(work_id=target_id, input_slot="additional_design"),
            basis="Offer later accepted designs to this plan",
        ),
    )
    _apply(
        root,
        space,
        owner,
        SetBindingStateRequest,
        binding_id=offer_binding_id,
        version=1,
        expected_state_revision=1,
        state="enabled",
    )
    _, second_artifact, _ = _accepted(root, space, owner, producer)
    offer_id = cast(UUID, read_binding_firings(root, offer_binding_id, owner)[0].offer_id)
    assert read_work_plan(root, target_id, owner).revision == 1
    receipt = _apply(
        root,
        space,
        owner,
        ResolveBindingOfferRequest,
        offer_id=offer_id,
        expected_consumer_revision=1,
        decision="accept",
        basis="Use the later design",
    )
    assert receipt.result["plan_revision"] == 2
    assert read_work_plan(root, target_id, owner).plan.basis == (
        ArtifactRef(artifact_id=first_artifact, revision=1),
        ArtifactRef(artifact_id=second_artifact, revision=1),
    )
    assert (
        read_work(root, target_id, owner).state.inputs
        == read_work_plan(root, target_id, owner).plan.basis
    )
    assert read_binding_input_history(root, target_id, owner)[0].plan_revision == 2
