"""Setup contracts: exact review, bounded continuation and isolated adoption."""

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_binding import _ready
from zaratustra.foundation import (
    ActivitySetupDraft,
    ActivitySetupRequest,
    ActivitySetupReview,
    ArtifactRef,
    CreateArtifactRequest,
    FoundationError,
    LinkedOutput,
    LinkWorkOutputRequest,
    LocalAuthority,
    MethodDefinition,
    MethodObligation,
    OperationReceipt,
    OutputContract,
    SetupMethodTemplate,
    SetupWorkTemplate,
    WorkPlan,
    WorkState,
    apply_operation,
    read_activity_setup,
    read_work,
    upgrade_activity_setup_space,
    upgrade_change_package_space,
    upgrade_development_space,
    upgrade_knowledge_space,
    upgrade_memory_space,
)
from zaratustra.foundation.models import PlanChild, PlanCondition, PlanOutputBinding

Case = tuple[Path, UUID, LocalAuthority, UUID, UUID, ActivitySetupRequest, OperationReceipt]


def _case(tmp_path: Path) -> Case:
    root, space, owner, activity, _ = _ready(tmp_path)
    for upgrade in (
        upgrade_knowledge_space,
        upgrade_development_space,
        upgrade_change_package_space,
        upgrade_memory_space,
        upgrade_activity_setup_space,
    ):
        upgrade(root, owner)
    setup, activity = uuid4(), uuid4()
    request = ActivitySetupRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        action="begin",
        setup_id=setup,
        activity_id=activity,
        title="Fictional workshop",
        text="Keep project notes and prepare weekly summaries",
    )
    receipt = apply_operation(root, request, owner)
    return root, space, owner, setup, activity, request, receipt


def _step(case: Case, action: Any, **fields: Any) -> OperationReceipt:
    root, space, owner, setup, activity, *_ = case
    current = read_activity_setup(root, setup, owner)
    return apply_operation(
        root,
        ActivitySetupRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            setup_id=setup,
            activity_id=activity,
            action=action,
            expected_revision=current.revision,
            **fields,
        ),
        owner,
    )


def _complete(case: Case, content: ActivitySetupDraft | ActivitySetupReview) -> ArtifactRef:
    root, space, owner, setup, *_ = case
    stage = read_activity_setup(root, setup, owner).state.stages[-1]
    identifier = uuid4()
    ref = ArtifactRef(artifact_id=identifier, revision=1)
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            artifact_id=identifier,
            media_type="text/plain",
            content=content.model_dump_json().encode(),
        ),
        owner,
    )
    work = read_work(root, stage.work_id, owner)
    apply_operation(
        root,
        LinkWorkOutputRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=stage.work_id,
            expected_revision=work.revision,
            output=LinkedOutput(slot="report", artifact=ref),
        ),
        owner,
    )
    _step(case, "complete_stage", output=ref)
    return ref


def _draft(case: Case) -> ActivitySetupDraft:
    activity = case[4]
    output = OutputContract(slot="report", media_type="text/plain")
    definition = MethodDefinition(
        instruction="Keep original project notes and write a versioned summary",
        named_outputs=(output,),
        obligations=(
            MethodObligation(
                key="summary",
                source="fictional",
                role="prepare",
                slot="report",
                media_type="text/plain",
            ),
        ),
        source_ref="fictional:setup",
    )
    plan = WorkPlan(
        children=(
            PlanChild(
                role="prepare",
                work_id=uuid4(),
                state=WorkState(
                    activity_id=activity, goal="Prepare summary", expected_outputs=(output,)
                ),
            ),
        ),
        output_bindings=(
            PlanOutputBinding(
                parent_slot="report", role="prepare", child_slot="report", media_type="text/plain"
            ),
        ),
        completion=PlanCondition(kind="work_succeeded", role="prepare"),
        rationale="First summary",
        source_ref="fictional:setup",
    )
    return ActivitySetupDraft(
        title="Fictional workshop",
        goal="Keep notes",
        instructions=(
            "Preserve originals, update conclusions with history; use Sleep for observed "
            "difficulties"
        ),
        methods=(SetupMethodTemplate(key="summary", definition=definition),),
        works=(
            SetupWorkTemplate(
                key="weekly", goal="Prepare first summary", method_key="summary", plan=plan
            ),
        ),
        first_action="Bring your first project note",
    )


def _review(case: Case, ref: ArtifactRef) -> ActivitySetupReview:
    state = read_activity_setup(case[0], case[3], case[2]).state
    return ActivitySetupReview(
        draft=ref,
        input_version=state.input_version,
        checked=(
            "goal",
            "workflow",
            "history",
            "continuation",
            "extension",
            "capabilities",
            "consistency",
        ),
        conclusion="No material obstacle in the fictional setup",
    )


def test_setup_reopens_interview_and_admits_exact_methods_without_accepting_work(
    tmp_path: Path,
) -> None:
    """Risk: duplicate setup after restart or fabricated Work acceptance."""
    case = _case(tmp_path)
    root, _, owner, setup, _, request, receipt = case
    assert apply_operation(root, request, owner) == receipt
    _step(case, "question", text="How do you normally bring project notes?")
    _step(case, "answer", text="One plain text note at the end of each day")
    reopened = read_activity_setup(root, setup, owner)
    assert reopened.state.input_version == 2 and len(reopened.state.sources) == 2
    _step(case, "start_stage", stage_kind="draft", stage_instruction="Prepare the complete setup")
    draft = _complete(case, _draft(case))
    _step(case, "start_stage", stage_kind="review", stage_instruction="Review the whole setup")
    _complete(case, _review(case, draft))
    _step(case, "finish")
    result = read_activity_setup(root, setup, owner).state
    assert result.phase == "ready" and len(result.activated_methods) == 1
    work = read_work(root, result.activated_works[0], owner)
    assert work.state.method == result.activated_methods[0]
    assert work.state.acceptance is None and work.state.status == "proposed"


def test_changed_answers_cannot_activate_previous_whole_review(tmp_path: Path) -> None:
    """Risk: a successful review survives a changed interview."""
    case = _case(tmp_path)
    _step(case, "start_stage", stage_kind="draft", stage_instruction="Prepare complete setup")
    draft = _complete(case, _draft(case))
    _step(case, "start_stage", stage_kind="review", stage_instruction="Review complete setup")
    _complete(case, _review(case, draft))
    _step(case, "answer", text="I changed my workflow: retain two independent original versions")
    with pytest.raises(FoundationError, match="setup_not_reviewed"):
        _step(case, "finish")
    assert read_activity_setup(case[0], case[3], case[2]).state.activated_methods == ()


def test_whole_correction_and_five_passes_survive_reopen(tmp_path: Path) -> None:
    """Risk: reviewing only a patch, or resetting the review cap after a restart."""
    import json

    from zaratustra.foundation import SetupFinding, read_artifact

    case = _case(tmp_path)
    _step(case, "start_stage", stage_kind="draft", stage_instruction="Prepare whole draft")
    draft = _complete(case, _draft(case))
    for number in range(1, 6):
        _step(case, "start_stage", stage_kind="review", stage_instruction="Review whole package")
        state = read_activity_setup(case[0], case[3], case[2]).state
        assert state.reviews_started == number
        report = _review(case, draft).model_copy(
            update={
                "findings": (
                    SetupFinding(
                        area="history",
                        problem="Preservation rule incomplete",
                        blocking=True,
                        cause="Both intake and summary rely on an incomplete rule",
                    ),
                )
            }
        )
        _complete(case, report)
        if number < 5:
            _step(case, "start_stage", stage_kind="correction", stage_instruction="Correct causes")
            changed = _draft(case).model_copy(
                update={"instructions": "Preserve both intake and summary originals"}
            )
            draft = _complete(case, changed)
    state = read_activity_setup(case[0], case[3], case[2]).state
    assert state.phase == "needs_attention" and state.reviews_completed == 5
    with pytest.raises(FoundationError, match="setup_review_exhausted"):
        _step(case, "resume")
    _step(case, "retry")
    _step(case, "start_stage", stage_kind="correction", stage_instruction="Correct causes")
    packet = read_artifact(
        case[0],
        read_activity_setup(case[0], case[3], case[2]).state.stages[-1].packet.artifact_id,
        case[2],
    )
    assert packet.content is not None
    whole = json.loads(packet.content)
    assert whole["draft"]["methods"] and whole["draft"]["works"] and whole["sources"]
    assert whole["previous_review"]["findings"]
    _step(case, "attention", text="Repeated local transport failure; no blind repeat")
    stopped = read_activity_setup(case[0], case[3], case[2]).state
    assert stopped.phase == "needs_attention" and stopped.reviews_started == 5
    assert stopped.repair_work is not None
    with pytest.raises(FoundationError, match="invalid_transition"):
        _step(case, "start_stage", stage_kind="review", stage_instruction="No send allowed")


def test_out_of_scope_activation_is_atomic_and_ordinary_work_is_fenced(tmp_path: Path) -> None:
    """Risk: a reviewed proposal affects another Activity or admits ordinary work early."""
    from zaratustra.foundation import CreateWorkRequest, StartAttemptRequest, read_activity

    case = _case(tmp_path)
    root, space, owner, setup, activity, *_ = case
    ordinary = uuid4()
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=ordinary,
            state=WorkState(
                activity_id=activity,
                goal="Ordinary work",
                expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    with pytest.raises(FoundationError, match="setup_pending"):
        apply_operation(
            root,
            StartAttemptRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                attempt_id=uuid4(),
                work_id=ordinary,
                expected_work_revision=1,
                session_id=uuid4(),
                resource_id=uuid4(),
                expected_resource_revision=1,
            ),
            owner,
        )
    _step(case, "start_stage", stage_kind="draft", stage_instruction="Prepare whole draft")
    proposal = _draft(case)
    template = proposal.works[0]
    assert template.plan is not None
    child = template.plan.children[0].model_copy(
        update={
            "state": template.plan.children[0].state.model_copy(update={"activity_id": uuid4()})
        }
    )
    proposal = proposal.model_copy(
        update={
            "works": (
                template.model_copy(
                    update={"plan": template.plan.model_copy(update={"children": (child,)})}
                ),
            )
        }
    )
    draft = _complete(case, proposal)
    _step(case, "start_stage", stage_kind="review", stage_instruction="Review whole package")
    _complete(case, _review(case, draft))
    before = read_activity(root, activity, owner)
    with pytest.raises(FoundationError, match="out_of_scope"):
        _step(case, "finish")
    assert read_activity(root, activity, owner) == before
    assert read_activity_setup(root, setup, owner).state.activated_methods == ()


def test_setup_backup_and_deletion_remove_copied_basis(tmp_path: Path) -> None:
    """Risk: deleting a source leaves interview/proposal text in durable copies or backup."""
    from zaratustra.foundation import (
        DeleteKnowledgeRequest,
        complete_deletions,
        create_backup,
        read_artifact,
        read_knowledge,
    )

    case = _case(tmp_path)
    root, space, owner, setup, *_ = case
    _step(case, "start_stage", stage_kind="draft", stage_instruction="Prepare whole draft")
    draft = _complete(case, _draft(case))
    _step(case, "start_stage", stage_kind="review", stage_instruction="Review whole package")
    _complete(case, _review(case, draft))
    _step(case, "finish")
    state = read_activity_setup(root, setup, owner).state
    backup = create_backup(root, uuid4(), owner)
    assert backup.package.exists()
    from zaratustra.foundation import (
        RecoverRequest,
        authorize_local,
        authorize_recovery,
        restore_backup,
    )

    recovery = authorize_recovery(actor="owner", source_ref="fictional-recovery")
    restored = tmp_path / "restored"
    restored.mkdir()
    assert restore_backup(backup.package, restored, recovery).schema_version == 14
    apply_operation(
        restored,
        RecoverRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        recovery,
    )
    reopened = authorize_local(restored, actor="owner", source_ref="fictional-reopened")
    assert read_activity_setup(restored, setup, reopened).state == state
    source = state.sources[0]
    apply_operation(
        root,
        DeleteKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=source.record_id,
            expected_revision=source.revision,
        ),
        owner,
    )
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_activity_setup(root, setup, owner)
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_artifact(root, draft.artifact_id, owner)
    assert read_knowledge(root, source.record_id, owner).availability == "deleted"
    assert complete_deletions(root, owner).live_store_sanitized
    assert not backup.package.exists()


def test_derived_packet_rechecks_source_access(tmp_path: Path) -> None:
    """Risk: granting a packet reveals originals whose rights were not granted."""
    from zaratustra.foundation import CreateGrantRequest, GrantState, authorize_local, read_artifact

    case = _case(tmp_path)
    root, space, owner, setup, activity, *_ = case
    _step(case, "start_stage", stage_kind="draft", stage_instruction="Prepare whole draft")
    packet = read_activity_setup(root, setup, owner).state.stages[-1].packet
    reader = authorize_local(root, actor="fictional-reader", source_ref="fictional-access")
    for resource_type, resource_id in (("activity", activity), ("artifact", packet.artifact_id)):
        apply_operation(
            root,
            CreateGrantRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                grant_id=uuid4(),
                state=GrantState(
                    grantee="fictional-reader",
                    actions=("record.read",),
                    resource_type="activity" if resource_type == "activity" else "artifact",
                    resource_id=resource_id,
                ),
            ),
            owner,
        )
    with pytest.raises(FoundationError, match="permission_denied"):
        read_artifact(root, packet.artifact_id, reader)
    with pytest.raises(FoundationError, match="permission_denied"):
        read_activity_setup(root, setup, reader)


def test_interrupted_review_wait_continues_same_pass_with_saved_answer(tmp_path: Path) -> None:
    """Risk: closing Pi loses an answer or spends a new review pass on the same Work."""
    import json

    from pydantic import TypeAdapter

    from zaratustra.foundation import DomainRequest, read_artifact, read_execution

    case = _case(tmp_path)
    root, space, owner, setup, *_ = case
    _step(case, "start_stage", stage_kind="draft", stage_instruction="Prepare whole draft")
    draft = _complete(case, _draft(case))
    _step(case, "start_stage", stage_kind="review", stage_instruction="Review whole draft")
    stage = read_activity_setup(root, setup, owner).state.stages[-1]
    adapter: TypeAdapter[DomainRequest] = TypeAdapter(DomainRequest)

    def effect(kind: str, **fields: Any) -> OperationReceipt:
        return apply_operation(
            root,
            adapter.validate_python(
                dict(kind=kind, operation_id=uuid4(), actor="owner", space_id=space, **fields)
            ),
            owner,
        )

    resource, attempt, session, wait = uuid4(), uuid4(), uuid4(), uuid4()
    effect(
        "create_resource",
        resource_id=resource,
        work_id=stage.work_id,
        state=dict(label="Fictional resource", root=tmp_path),
    )
    effect(
        "assign_attempt",
        attempt_id=attempt,
        work_id=stage.work_id,
        session_id=session,
        resource_id=resource,
        expected_resource_revision=1,
        expected_work_revision=1,
        executor_version="fictional-setup-1",
    )
    effect(
        "open_wait",
        wait_id=wait,
        attempt_id=attempt,
        work_id=stage.work_id,
        session_id=session,
        expected_assignment_revision=1,
        question="Choose the intake frequency",
        expected_actor="owner",
        remainder="Continue the full review after this answer",
    )
    _step(case, "question", text="Choose the intake frequency")
    assignment = read_execution(root, stage.work_id, owner).assignments[-1]
    effect(
        "request_attempt_stop",
        attempt_id=attempt,
        work_id=stage.work_id,
        session_id=session,
        expected_assignment_revision=assignment.revision,
        reason="Fictional window closed",
    )
    assignment = read_execution(root, stage.work_id, owner).assignments[-1]
    effect(
        "record_attempt_stop",
        attempt_id=attempt,
        work_id=stage.work_id,
        session_id=session,
        expected_assignment_revision=assignment.revision,
        outcome="stopped",
    )
    _step(case, "answer", text="Daily notes")
    state = read_activity_setup(root, setup, owner).state
    assert state.reviews_started == 1 and state.stages[-1].work_id == stage.work_id
    assert not state.stages[-1].retired and state.stages[-1].packet != stage.packet
    packet = read_artifact(root, state.stages[-1].packet.artifact_id, owner)
    assert packet.content is not None
    sources = json.loads(packet.content)["sources"]
    assert sources[-1]["state"]["text"] == "Daily notes"
    assert read_execution(root, stage.work_id, owner).work.state.inputs == (
        state.stages[-1].packet,
    )
    _complete(case, _review(case, draft))
    _step(case, "pause")
    _step(case, "resume")
    assert read_activity_setup(root, setup, owner).state.phase == "activating"
    _step(case, "finish")
    assert read_activity_setup(root, setup, owner).state.phase == "ready"


def test_setup_deletion_preserves_selected_original_from_other_activity(tmp_path: Path) -> None:
    """Risk: a selected original of another setup is incorrectly treated as an owned copy."""
    from zaratustra.foundation import DeleteKnowledgeRequest, list_activity_setups, read_knowledge

    case = _case(tmp_path)
    root, space, owner, setup, _, *_ = case
    original = read_activity_setup(root, setup, owner).state.sources[0]
    other_setup, other_activity = uuid4(), uuid4()
    apply_operation(
        root,
        ActivitySetupRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            setup_id=other_setup,
            activity_id=other_activity,
            action="begin",
            title="Another direction",
            text="Reuse one selected original without taking ownership",
            source_refs=(original,),
        ),
        owner,
    )
    new_source = read_activity_setup(root, other_setup, owner).state.sources[0]
    apply_operation(
        root,
        DeleteKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=new_source.record_id,
            expected_revision=1,
        ),
        owner,
    )
    assert read_knowledge(root, original.record_id, owner).availability == "available"
    assert read_activity_setup(root, setup, owner).state.phase == "collecting"
    pending = list_activity_setups(root, owner, pending_only=True, limit=1)
    assert len(pending) == 1 and pending[0].setup_id == setup
