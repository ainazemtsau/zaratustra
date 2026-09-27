"""An Activity split or merge keeps exact Work history and commits as one operation."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from tests.zaratustra.foundation.test_binding import _ready
from zaratustra.foundation import (
    ActivityChange,
    ActivityCreation,
    ActivityRevisionChange,
    ActivityState,
    ApplyCandidateRequest,
    ChangeCandidateState,
    ChangeDecisionState,
    CreateActivityRequest,
    CreateDecisionRequest,
    CreateDevelopmentRequest,
    CreateKnowledgeRequest,
    CreateWorkRequest,
    FoundationError,
    KnowledgeRef,
    OutputContract,
    ReorganizeActivitiesRequest,
    RestoreCandidateRequest,
    SourceState,
    StopCandidateRequest,
    ValidationCriterion,
    ValidationPlanState,
    ValidationResultState,
    WorkActivityMove,
    WorkState,
    apply_operation,
    pulse_space,
    read_activity,
    read_work,
    upgrade_change_package_space,
    upgrade_development_space,
    upgrade_knowledge_space,
)


def test_split_and_merge_preserve_started_work_and_history(tmp_path: Path) -> None:
    root, space, owner, original, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    upgrade_development_space(root, owner)
    existing, new = uuid4(), uuid4()
    apply_operation(
        root,
        CreateActivityRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            activity_id=existing,
            state=ActivityState(title="Existing project", goal="Continue the existing project"),
        ),
        owner,
    )
    works = (uuid4(), uuid4())
    for work_id in works:
        apply_operation(
            root,
            CreateWorkRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                work_id=work_id,
                state=WorkState(
                    activity_id=original,
                    goal="Keep a partial fictional result",
                    expected_outputs=(OutputContract(slot="result", media_type="text/plain"),),
                ),
            ),
            owner,
        )
    request = ReorganizeActivitiesRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        creations=(
            ActivityCreation(
                activity_id=new,
                state=ActivityState(title="Split project", goal="Continue the split project"),
            ),
        ),
        revisions=(
            ActivityRevisionChange(
                activity_id=original,
                expected_revision=1,
                state=ActivityState(
                    title="Original project",
                    goal="All current Work transferred",
                    status="completed",
                ),
            ),
        ),
        moves=(
            WorkActivityMove(
                work_id=works[0],
                expected_revision=1,
                from_activity_id=original,
                to_activity_id=new,
            ),
            WorkActivityMove(
                work_id=works[1],
                expected_revision=1,
                from_activity_id=original,
                to_activity_id=existing,
            ),
        ),
        rationale="Exact current membership was reviewed",
        binding_disposition="No scoped Binding is carried to either destination",
        decision_disposition="No scoped Decision is copied",
        grant_disposition="No Grant is copied",
        event_boundary="Future Work uses the new current membership",
    )
    receipt = apply_operation(root, request, owner)
    assert receipt.result["moved"] == [str(work_id) for work_id in works]
    assert apply_operation(root, request, owner) == receipt
    assert read_activity(root, original, owner).state.status == "completed"
    for work_id, destination in zip(works, (new, existing), strict=True):
        assert read_work(root, work_id, owner).state.activity_id == destination
        assert read_work(root, work_id, owner, revision=1).state.activity_id == original
        assert read_work(root, work_id, owner).state.status == "proposed"


def test_stale_member_rolls_back_entire_reorganization(tmp_path: Path) -> None:
    root, space, owner, original, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    upgrade_development_space(root, owner)
    new, work_id = uuid4(), uuid4()
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=work_id,
            state=WorkState(
                activity_id=original,
                goal="Keep a fictional result",
                expected_outputs=(OutputContract(slot="result", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    with pytest.raises(FoundationError, match="Work membership changed"):
        apply_operation(
            root,
            ReorganizeActivitiesRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                creations=(
                    ActivityCreation(
                        activity_id=new,
                        state=ActivityState(title="New project", goal="Keep work"),
                    ),
                ),
                moves=(
                    WorkActivityMove(
                        work_id=work_id,
                        expected_revision=2,
                        from_activity_id=original,
                        to_activity_id=new,
                    ),
                ),
                rationale="Proposed exact transfer",
                binding_disposition="No Binding transfer",
                decision_disposition="No Decision transfer",
                grant_disposition="No Grant transfer",
                event_boundary="Future events after transfer",
            ),
            owner,
        )
    assert read_work(root, work_id, owner).state.activity_id == original
    with pytest.raises(FoundationError, match="No activity record"):
        read_activity(root, new, owner)


def test_admitted_activity_split_stop_and_exact_restore(tmp_path: Path) -> None:
    root, space, owner, original, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    upgrade_development_space(root, owner)
    upgrade_change_package_space(root, owner)
    work_id, destination, candidate_id, decision_id, result_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=work_id,
            state=WorkState(
                activity_id=original,
                goal="Continue a fictional work item",
                expected_outputs=(OutputContract(slot="result", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    evidence_id = uuid4()
    apply_operation(
        root,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=evidence_id,
            state=SourceState(
                channel="tool_result",
                connection="local-test",
                profile_revision=1,
                source_event_id="activity-membership-check",
                media_type="text/plain",
                capture="full",
                content=b"Current Work and Activity revisions inspected",
            ),
        ),
        owner,
    )
    target = ActivityChange(
        change_id=uuid4(),
        creations=(
            ActivityCreation(
                activity_id=destination,
                state=ActivityState(title="Focused project", goal="Continue focused Work"),
            ),
        ),
        revisions=(
            ActivityRevisionChange(
                activity_id=original,
                expected_revision=1,
                state=ActivityState(
                    title="Original project", goal="Transferred current Work", status="completed"
                ),
            ),
        ),
        moves=(
            WorkActivityMove(
                work_id=work_id,
                expected_revision=1,
                from_activity_id=original,
                to_activity_id=destination,
            ),
        ),
        rationale="Split the independently continuing Work",
        binding_disposition="No Binding scope is copied",
        decision_disposition="No Decision scope is copied",
        grant_disposition="No Grant scope is copied",
        event_boundary="Future Work uses the new current membership",
    )
    candidate = ChangeCandidateState(
        target=target,
        proposal="Admit an exact Activity split",
        expected_outcome="One Work belongs to the new Activity",
        scope_activity_ids=(original,),
        exclusions="All other Work stays in place",
        impact="One current Work and two Activity addresses",
        affected_work_ids=(work_id,),
        unknowns="Future usefulness is unknown",
        validation_plan=ValidationPlanState(
            baseline="Work belongs to the original Activity",
            environment="Local fictional Core space",
            criteria=(
                ValidationCriterion(
                    key="membership",
                    question="Are current addresses and revisions exact?",
                    pass_condition="Work and Activity have the reviewed current revisions",
                ),
            ),
            cases="One exact local Work",
            method="Read current Work and Activity revisions",
            sufficiency="Exact revisions are directly observable",
            limits="No claim of semantic benefit",
            stop_and_restore="Stop and reverse exact current membership",
            decision_condition="Current authority and saved validation",
            follow_up="Observe future use of the split Activity",
        ),
        results=(
            ValidationResultState(
                result_id=result_id,
                criterion="membership",
                outcome="met",
                evidence=(KnowledgeRef(record_id=evidence_id, revision=1),),
                actual_input="Original Activity and Work at revision one",
                environment="Local fictional Core space",
                limitations="Application rechecks current revisions",
            ),
        ),
        restore_plan="Reverse only when exact current revisions remain unchanged",
        irreversible_effects="No external effect is reversed",
    )
    apply_operation(
        root,
        CreateDevelopmentRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=candidate_id,
            state=candidate,
        ),
        owner,
    )
    apply_operation(
        root,
        CreateDecisionRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            decision_id=decision_id,
            state=ChangeDecisionState(
                statement="Admit the bounded Activity split",
                candidate_id=candidate_id,
                candidate_revision=1,
                mode="trial",
                trial_use_limit=1,
                use="permitted",
                scope_activity_id=original,
                validation_result_ids=(result_id,),
                review_condition="Stop after observing the first moved Work",
            ),
        ),
        owner,
    )
    application_id = uuid4()
    assert (
        apply_operation(
            root,
            ApplyCandidateRequest(
                operation_id=application_id,
                space_id=space,
                actor="owner",
                candidate_id=candidate_id,
                candidate_revision=1,
                decision_id=decision_id,
                decision_revision=1,
                mode="trial",
            ),
            owner,
        ).result["status"]
        == "active"
    )
    assert read_work(root, work_id, owner).state.activity_id == destination
    assert read_activity(root, original, owner).state.status == "completed"
    apply_operation(
        root,
        StopCandidateRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            application_id=application_id,
            expected_revision=1,
            reason="Return to the original organization",
            started_works="No new Work started in the destination",
            external_effects="No external effects are known",
        ),
        owner,
    )
    assert (
        apply_operation(
            root,
            RestoreCandidateRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                application_id=application_id,
                expected_revision=2,
                reason="Reverse exact current membership",
                data_restoration="Retire the created Activity, retain its history",
                external_effects="No external effect is reversed",
            ),
            owner,
        ).result["status"]
        == "restored"
    )
    assert read_work(root, work_id, owner).state.activity_id == original
    assert read_work(root, work_id, owner, revision=2).state.activity_id == destination
    assert read_activity(root, original, owner).state.status == "ongoing"
    assert read_activity(root, destination, owner).state.status == "completed"
    assert pulse_space(root, owner).findings == ()
