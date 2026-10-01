"""Sleep continuation and the admitted Method change retain exact Core history."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_binding import _accepted, _new_definition, _ready
from zaratustra.foundation import (
    ApplyCandidateRequest,
    BindingChange,
    ChangeCandidateState,
    ChangeDecisionState,
    ClaimState,
    CreateBindingVersionRequest,
    CreateCompositeWorkRequest,
    CreateDecisionRequest,
    CreateDevelopmentRequest,
    CreateKnowledgeRequest,
    CreateMethodVersionRequest,
    DeleteKnowledgeRequest,
    FireBindingRequest,
    FoundationError,
    KnowledgeRef,
    LocalAuthority,
    MethodDefinition,
    MethodRef,
    OperationReceipt,
    OutputContract,
    RecordChangeOutcomeRequest,
    RecoverRequest,
    RecoveryAuthority,
    RestoreCandidateRequest,
    ReviseDevelopmentRequest,
    SleepState,
    StopCandidateRequest,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    initial_sleep_method,
    initial_sleep_ref,
    list_sleep_sources,
    read_binding_version,
    read_change_application,
    read_development,
    read_space,
    restore_backup,
    sleep_work_template,
    upgrade_development_space,
    upgrade_knowledge_space,
)
from zaratustra.foundation.models import (
    MethodChange,
    SleepEffect,
    SleepRemainder,
    SleepSelection,
    ValidationCriterion,
    ValidationPlanState,
    ValidationResultState,
)


def _operation(
    root: Path,
    space: UUID,
    owner: LocalAuthority | RecoveryAuthority,
    kind: type[Any],
    **fields: object,
) -> OperationReceipt:
    return apply_operation(
        root,
        kind(operation_id=uuid4(), space_id=space, actor="owner", **fields),
        owner,
    )


def test_sleep_enumeration_persists_cursor_across_two_pages(tmp_path: Path) -> None:
    root, space, owner, activity_id, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    upgrade_development_space(root, owner)
    for number in range(3):
        _operation(
            root,
            space,
            owner,
            CreateKnowledgeRequest,
            record_id=uuid4(),
            state={
                "kind": "source",
                "channel": "conversation_user",
                "connection": "test-pi",
                "profile_revision": 1,
                "source_event_id": f"pagination-{number}",
                "media_type": "text/plain",
                "capture": "full",
                "content": f"Observation {number}".encode(),
            },
        )
    seed = initial_sleep_ref(space)
    _operation(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=seed.method_id,
        version=1,
        definition=initial_sleep_method(),
    )
    work_id, sleep_id = uuid4(), uuid4()
    work, plan = sleep_work_template(
        activity_id=activity_id,
        method=seed,
        work_id=work_id,
        consolidation_id=uuid4(),
        exploration_id=uuid4(),
        scope="fictional experience",
    )
    _operation(
        root, space, owner, CreateCompositeWorkRequest, work_id=work_id, state=work, plan=plan
    )
    state = SleepState(
        work_id=work_id,
        method=seed,
        scope_activity_ids=(),
        intake_cutoff_revision=read_space(root).state_revision,
        resource_limit_units=100,
    )
    _operation(root, space, owner, CreateDevelopmentRequest, record_id=sleep_id, state=state)

    first = list_sleep_sources(root, sleep_id, owner, purpose="consolidation", limit=2)
    first_items = cast(list[dict[str, object]], first["items"])
    assert len(first_items) == 2
    assert first["exhausted"] is False
    state = state.model_copy(
        update={
            "enumeration_cursor_revision": first["next_cursor_revision"],
            "enumeration_cursor_id": UUID(str(first["next_cursor_id"])),
        }
    )
    _operation(
        root,
        space,
        owner,
        ReviseDevelopmentRequest,
        record_id=sleep_id,
        expected_revision=1,
        state=state,
    )
    second = list_sleep_sources(root, sleep_id, owner, purpose="consolidation", limit=2)
    second_items = cast(list[dict[str, object]], second["items"])
    assert len(second_items) == 1
    assert second["exhausted"] is True
    assert {item["record_id"] for item in first_items}.isdisjoint(
        item["record_id"] for item in second_items
    )


def test_sleep_progress_candidate_apply_stop_and_restore(tmp_path: Path) -> None:
    root, space, owner, activity_id, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    assert upgrade_development_space(root, owner).schema_version == 11
    source_id = uuid4()
    source_receipt = _operation(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=source_id,
        state={
            "kind": "source",
            "channel": "conversation_user",
            "connection": "test-pi",
            "profile_revision": 1,
            "source_event_id": "owner-observation-1",
            "media_type": "text/plain",
            "capture": "full",
            "content": b"A useful observation",
        },
    )
    assert source_receipt.result["revision"] == 1
    seed = initial_sleep_ref(space)
    _operation(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=seed.method_id,
        version=1,
        definition=initial_sleep_method(),
    )
    work_id, sleep_id = uuid4(), uuid4()
    work, plan = sleep_work_template(
        activity_id=activity_id,
        method=seed,
        work_id=work_id,
        consolidation_id=uuid4(),
        exploration_id=uuid4(),
        scope="fictional experience",
    )
    _operation(
        root, space, owner, CreateCompositeWorkRequest, work_id=work_id, state=work, plan=plan
    )
    cutoff = read_space(root).state_revision
    initial = SleepState(
        work_id=work_id,
        method=seed,
        scope_activity_ids=(),
        intake_cutoff_revision=cutoff,
        resource_limit_units=100,
        remainder=(SleepRemainder(kind="new_intake", description="Review the next source"),),
    )
    _operation(root, space, owner, CreateDevelopmentRequest, record_id=sleep_id, state=initial)
    assert list_sleep_sources(root, sleep_id, owner, purpose="consolidation")["items"]
    source_ref = KnowledgeRef(record_id=source_id, revision=1)
    partial = initial.model_copy(
        update={
            "selected": (SleepSelection(source=source_ref, purpose="consolidation"),),
            "enumeration_cursor_revision": cutoff,
            "enumeration_cursor_id": source_id,
            "consolidation": "partial",
        }
    )
    _operation(
        root,
        space,
        owner,
        ReviseDevelopmentRequest,
        record_id=sleep_id,
        expected_revision=1,
        state=partial,
    )
    assert read_development(root, sleep_id, owner).revision == 2
    effect_id, effect_operation = uuid4(), uuid4()
    apply_operation(
        root,
        CreateKnowledgeRequest(
            operation_id=effect_operation,
            space_id=space,
            actor="owner",
            record_id=effect_id,
            state=ClaimState(
                proposition="This fictional observation may help later work",
                epistemic_kind="hypothesis",
                status="current",
                scope_global=True,
                evidence=(source_ref,),
                interpretation_basis="Observed in one synthetic case",
            ),
        ),
        owner,
    )
    resumed = partial.model_copy(
        update={
            "effects": (
                SleepEffect(
                    operation_id=effect_operation,
                    result=KnowledgeRef(record_id=effect_id, revision=1),
                ),
            ),
            "remainder": (SleepRemainder(kind="question", description="Explore another period"),),
        }
    )
    _operation(
        root,
        space,
        owner,
        ReviseDevelopmentRequest,
        record_id=sleep_id,
        expected_revision=2,
        state=resumed,
    )
    assert read_development(root, sleep_id, owner).state == resumed
    with pytest.raises(FoundationError, match="resource_mismatch"):
        _operation(
            root,
            space,
            owner,
            ReviseDevelopmentRequest,
            record_id=sleep_id,
            expected_revision=3,
            state=resumed.model_copy(update={"spent_units": 1}),
        )

    target_definition = initial_sleep_method().model_copy(
        update={
            "instruction": initial_sleep_method().instruction
            + " Preserve the exact negative result."
        }
    )
    candidate_id, decision_id = uuid4(), uuid4()
    result_id = uuid4()
    candidate = ChangeCandidateState(
        target=MethodChange(
            method_id=seed.method_id,
            from_version=1,
            from_checksum=seed.checksum,
            to_version=2,
            definition=target_definition,
        ),
        proposal="Preserve a negative exploratory result in the next Sleep Method",
        evidence=(source_ref,),
        expected_outcome="Next Work receives the revised instruction",
        scope_activity_ids=(activity_id,),
        exclusions="Other Activities are excluded",
        impact="New Work in the selected Activity; existing Work stays pinned",
        unknowns="Behavioral usefulness remains unknown",
        validation_plan=ValidationPlanState(
            baseline="Method version 1",
            environment="Synthetic local Core",
            criteria=(
                ValidationCriterion(
                    key="exact",
                    question="Is version 2 exact?",
                    pass_condition="New Work pins version 2",
                    basis=(source_ref,),
                ),
            ),
            cases="Next fictional Work",
            method="Inspect exact Core revisions",
            sufficiency="Structural behavior is directly observable",
            limits="One Activity and no external effect",
            stop_and_restore="Stop new use then select version 1",
            decision_condition="Exact version and current rights",
            follow_up="Observe later Work result",
        ),
        results=(
            ValidationResultState(
                result_id=result_id,
                criterion="exact",
                outcome="met",
                evidence=(source_ref,),
                actual_input="Method 1 and proposed Method 2",
                environment="Local Core",
            ),
        ),
        restore_plan="Stop new selection and return to version 1",
        irreversible_effects="Started Work and external effects require separate review",
    )
    _operation(
        root, space, owner, CreateDevelopmentRequest, record_id=candidate_id, state=candidate
    )
    _operation(
        root,
        space,
        owner,
        CreateDecisionRequest,
        decision_id=decision_id,
        state=ChangeDecisionState(
            statement="Admit the checked exact version in this Activity",
            candidate_id=candidate_id,
            candidate_revision=1,
            mode="regular",
            use="recommended",
            scope_activity_id=activity_id,
            validation_result_ids=(result_id,),
            review_condition="Review after next Work",
        ),
    )
    application_id = uuid4()
    applied = apply_operation(
        root,
        ApplyCandidateRequest(
            operation_id=application_id,
            space_id=space,
            actor="owner",
            candidate_id=candidate_id,
            candidate_revision=1,
            decision_id=decision_id,
            decision_revision=1,
            mode="regular",
        ),
        owner,
    )
    assert applied.result["version"] == 2
    from zaratustra.foundation.composition import method_checksum
    from zaratustra.foundation.models import MethodRef

    new_ref = MethodRef(
        method_id=seed.method_id, version=2, checksum=method_checksum(target_definition)
    )
    next_work, next_plan = sleep_work_template(
        activity_id=activity_id,
        method=new_ref,
        work_id=uuid4(),
        consolidation_id=uuid4(),
        exploration_id=uuid4(),
        scope="next fictional case",
    )
    _operation(
        root,
        space,
        owner,
        CreateCompositeWorkRequest,
        work_id=uuid4(),
        state=next_work,
        plan=next_plan,
    )
    stop = _operation(
        root,
        space,
        owner,
        StopCandidateRequest,
        application_id=application_id,
        expected_revision=1,
        reason="Observed reason to pause",
        started_works="Keep pinned Work for review",
        external_effects="No external effect observed",
    )
    assert stop.result["status"] == "stopped"
    with pytest.raises(FoundationError, match="change_stopped"):
        _operation(
            root,
            space,
            owner,
            CreateCompositeWorkRequest,
            work_id=uuid4(),
            state=next_work,
            plan=next_plan,
        )
    restored = _operation(
        root,
        space,
        owner,
        RestoreCandidateRequest,
        application_id=application_id,
        expected_revision=2,
        reason="Return to prior selection",
        data_restoration="No data changed",
        external_effects="Review any begun Work independently",
    )
    assert restored.result["status"] == "restored"
    application, history = read_change_application(root, application_id, owner)
    assert application.status == "restored"
    assert [entry["kind"] for entry in history] == ["apply", "stop", "restore"]
    late_id = uuid4()
    _operation(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=late_id,
        state={
            "kind": "source",
            "channel": "document",
            "connection": "fixture",
            "profile_revision": 1,
            "media_type": "text/plain",
            "capture": "full",
            "content": b"Fictional later counterexample",
        },
    )
    _operation(
        root,
        space,
        owner,
        RecordChangeOutcomeRequest,
        application_id=application_id,
        expected_revision=3,
        outcome="negative",
        evidence=(KnowledgeRef(record_id=late_id, revision=1),),
        observation="The fictional later result contradicted expected usefulness",
    )
    _operation(root, space, owner, DeleteKnowledgeRequest, record_id=late_id, expected_revision=1)
    _, history = read_change_application(root, application_id, owner)
    assert history[-1]["kind"] == "outcome" and history[-1]["detail"] == {}
    assert read_development(root, candidate_id, owner).availability == "available"


def test_binding_trial_limit_backup_and_deleted_basis(tmp_path: Path) -> None:
    root, space, owner, producer, consumer = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    clean_backup = create_backup(root, uuid4(), owner)
    source_id = uuid4()
    _operation(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=source_id,
        state={
            "kind": "source",
            "channel": "document",
            "connection": "fixture",
            "profile_revision": 1,
            "media_type": "text/plain",
            "capture": "full",
            "content": b"Fictional checked transfer",
        },
    )
    source_ref = KnowledgeRef(record_id=source_id, revision=1)
    method_id = uuid4()
    method_receipt = _operation(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=method_id,
        version=1,
        definition=MethodDefinition(
            instruction="Plan from the accepted fictional result",
            named_inputs=(OutputContract(slot="source", media_type="text/plain"),),
            named_outputs=(OutputContract(slot="plan", media_type="text/plain"),),
            source_ref="fictional-trial-method",
        ),
    )
    method = MethodRef(
        method_id=method_id, version=1, checksum=str(method_receipt.result["checksum"])
    )
    upgrade_development_space(root, owner)
    with pytest.raises(FoundationError, match="candidate_required"):
        _operation(
            root,
            space,
            owner,
            CreateBindingVersionRequest,
            binding_id=uuid4(),
            version=1,
            definition=_new_definition(producer, consumer, method, goal="Unadmitted transfer"),
        )
    binding_id, candidate_id, decision_id, result_id = (uuid4() for _ in range(4))
    definition = _new_definition(producer, consumer, method, goal="Fictional bounded transfer")
    candidate = ChangeCandidateState(
        target=BindingChange(binding_id=binding_id, to_version=1, definition=definition),
        proposal="Trial one accepted result transfer",
        evidence=(source_ref,),
        expected_outcome="One target Work can be created",
        scope_activity_ids=(consumer,),
        exclusions="All other Activities excluded",
        impact="One new Work in the consumer Activity",
        unknowns="Further repetitions are untested",
        validation_plan=ValidationPlanState(
            baseline="No Binding",
            environment="Synthetic local Core",
            criteria=(
                ValidationCriterion(
                    key="shape",
                    question="Is the exact Binding well formed?",
                    pass_condition="Source and target contracts match",
                    basis=(source_ref,),
                ),
            ),
            cases="One fictional accepted producer result",
            method="Compare typed slots and exact Method",
            sufficiency="One bounded trial after structural check",
            limits="One consumer Work",
            stop_and_restore="Pause the Binding and keep created Work",
            decision_condition="Current Decision and Grant",
            follow_up="Review the created Work separately",
        ),
        results=(
            ValidationResultState(
                result_id=result_id,
                criterion="shape",
                outcome="met",
                evidence=(source_ref,),
                actual_input="Typed fictional Binding definition",
                environment="Synthetic local Core",
            ),
        ),
        restore_plan="Pause new transfer; no prior version exists",
        irreversible_effects="The first created Work remains addressed",
    )
    _operation(
        root, space, owner, CreateDevelopmentRequest, record_id=candidate_id, state=candidate
    )
    _operation(
        root,
        space,
        owner,
        CreateDecisionRequest,
        decision_id=decision_id,
        state=ChangeDecisionState(
            statement="Admit one bounded Binding trial",
            candidate_id=candidate_id,
            candidate_revision=1,
            mode="trial",
            trial_use_limit=1,
            use="permitted",
            scope_activity_id=consumer,
            validation_result_ids=(result_id,),
            review_condition="Review after one created Work",
        ),
    )
    application_id = uuid4()
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
    )
    assert read_binding_version(root, binding_id, 1, owner).state == "trial"
    first_work, _, first_accept = _accepted(root, space, owner, producer)
    first_fire = _operation(
        root,
        space,
        owner,
        FireBindingRequest,
        binding_id=binding_id,
        version=1,
        producer_work_id=first_work,
        accepted_work_revision=3,
    )
    assert first_fire.result["outcome"] == "created"
    second_work, _, _ = _accepted(root, space, owner, producer)
    with pytest.raises(FoundationError, match="change_stopped"):
        _operation(
            root,
            space,
            owner,
            FireBindingRequest,
            binding_id=binding_id,
            version=1,
            producer_work_id=second_work,
            accepted_work_revision=3,
        )
    backup = create_backup(root, uuid4(), owner)
    assert backup.manifest.schema_version == 11
    restored = tmp_path / "restored"
    restored.mkdir()
    recovery = authorize_recovery(actor="owner", source_ref="synthetic-recovery")
    assert restore_backup(backup.package, restored, recovery).recovery_state == "quarantined"
    _operation(restored, space, recovery, RecoverRequest, decision_id=uuid4(), grant_id=uuid4())
    reopened = authorize_local(restored, actor="owner", source_ref="synthetic-reopened")
    assert read_change_application(restored, application_id, reopened)[0].status == "active"
    assert read_binding_version(restored, binding_id, 1, reopened).state == "trial"
    with pytest.raises(FoundationError, match="change_stopped"):
        _operation(
            restored,
            space,
            reopened,
            FireBindingRequest,
            binding_id=binding_id,
            version=1,
            producer_work_id=second_work,
            accepted_work_revision=3,
        )
    _operation(root, space, owner, DeleteKnowledgeRequest, record_id=source_id, expected_revision=1)
    assert read_development(root, candidate_id, owner).availability == "unavailable"
    application, history = read_change_application(root, application_id, owner)
    assert application.status == "partial"
    assert history[0]["detail"] == {}
    assert complete_deletions(root, owner).live_store_sanitized
    assert not backup.package.exists()
    assert clean_backup.package.is_dir()
