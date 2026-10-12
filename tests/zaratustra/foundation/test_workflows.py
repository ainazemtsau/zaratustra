"""Workflow risks: exact internal evidence, durable interactions and Work authority."""

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_activity_structures import _structured_case
from zaratustra.foundation import (
    ActivitySetupRequest,
    ActivityState,
    ApplyCandidateRequest,
    ArtifactRef,
    ChangeCandidateState,
    ChangeDecisionState,
    CreateActivityRequest,
    CreateArtifactRequest,
    CreateDecisionRequest,
    CreateDevelopmentRequest,
    CreateKnowledgeRequest,
    FoundationError,
    KnowledgeRef,
    LinkedOutput,
    LinkWorkOutputRequest,
    LocalAuthority,
    OutputContract,
    SourceState,
    ValidationCriterion,
    ValidationPlanState,
    ValidationResultState,
    WorkflowChange,
    WorkflowDefinition,
    WorkflowModel,
    WorkflowNode,
    WorkflowNodeResult,
    WorkflowRef,
    WorkflowRequest,
    apply_operation,
    read_activity_setup,
    read_work,
    read_work_plan,
    read_workflow_run,
    upgrade_workflow_space,
)


def _op(root: Path, space: UUID, owner: LocalAuthority, kind: type[Any], **fields: Any) -> Any:
    return apply_operation(
        root, kind(operation_id=uuid4(), space_id=space, actor="owner", **fields), owner
    )


def _setup(
    tmp_path: Path, nodes: tuple[WorkflowNode, ...]
) -> tuple[Path, UUID, LocalAuthority, UUID, WorkflowRef, UUID]:
    root, space, owner, *_ = _structured_case(tmp_path)
    assert upgrade_workflow_space(root, owner).schema_version == 16
    activity = uuid4()
    _op(
        root,
        space,
        owner,
        CreateActivityRequest,
        activity_id=activity,
        state=ActivityState(title="Fictional workspace", goal="Keep dated observations"),
    )
    source = uuid4()
    _op(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=source,
        state=SourceState(
            channel="conversation_user",
            connection="fictional-pi",
            profile_revision=1,
            sender="owner",
            media_type="text/plain",
            capture="full",
            content=b"Analyse my observations",
        ),
    )
    source_ref = KnowledgeRef(record_id=source, revision=1)
    definition = WorkflowDefinition(
        title="Fictional review",
        purpose="Review dated observations",
        nodes=nodes,
        entry_nodes=(nodes[0].key,),
        outputs=(OutputContract(slot="report", media_type="text/plain"),),
    )
    ref = _adopt_workflow(root, space, owner, activity, source_ref, definition)
    run = uuid4()
    _op(
        root,
        space,
        owner,
        WorkflowRequest,
        action="start",
        workflow=ref,
        root_work_id=run,
        activity_id=activity,
        source_refs=(source_ref,),
    )
    return root, space, owner, activity, ref, run


def _adopt_workflow(
    root: Path,
    space: UUID,
    owner: LocalAuthority,
    activity: UUID,
    source_ref: KnowledgeRef,
    definition: WorkflowDefinition,
    *,
    identifier: UUID | None = None,
    from_version: int | None = None,
) -> WorkflowRef:
    identifier = identifier or uuid4()
    saved = _op(
        root,
        space,
        owner,
        WorkflowRequest,
        action="create_definition",
        workflow_id=identifier,
        definition=definition,
        version=(from_version or 0) + 1,
    )
    ref = WorkflowRef.model_validate(saved.result["workflow"])
    candidate_id, decision_id, result_id = uuid4(), uuid4(), uuid4()
    candidate = ChangeCandidateState(
        target=WorkflowChange(
            workflow_id=identifier,
            from_version=from_version,
            to_version=(from_version or 0) + 1,
            definition=definition,
        ),
        proposal="A reviewed finite process",
        evidence=(source_ref,),
        expected_outcome="Process continues after an interruption",
        scope_activity_ids=(activity,),
        exclusions="Other Activities",
        impact="Only this process",
        unknowns="Semantic usefulness",
        restore_plan="Stop new starts",
        irreversible_effects="Preserve observed results",
        validation_plan=ValidationPlanState(
            baseline="No workflow",
            environment="Fictional local Core",
            criteria=(
                ValidationCriterion(
                    key="exact",
                    question="Is the graph coherent?",
                    pass_condition="Declared nodes connect",
                    basis=(source_ref,),
                ),
            ),
            cases="One fictional workflow",
            method="Exact review",
            sufficiency="Structural evidence",
            limits="No model",
            stop_and_restore="Stop use",
            decision_condition="Exact validation",
            follow_up="Observe use",
        ),
        results=(
            ValidationResultState(
                result_id=result_id,
                criterion="exact",
                outcome="met",
                evidence=(source_ref,),
                actual_input="Whole definition",
                environment="Local Core",
            ),
        ),
    )
    _op(root, space, owner, CreateDevelopmentRequest, record_id=candidate_id, state=candidate)
    _op(
        root,
        space,
        owner,
        CreateDecisionRequest,
        decision_id=decision_id,
        state=ChangeDecisionState(
            statement="Adopt exact workflow",
            candidate_id=candidate_id,
            candidate_revision=1,
            mode="regular",
            use="recommended",
            scope_activity_id=activity,
            validation_result_ids=(result_id,),
            review_condition="Review future use",
        ),
    )
    _op(
        root,
        space,
        owner,
        ApplyCandidateRequest,
        candidate_id=candidate_id,
        candidate_revision=1,
        decision_id=decision_id,
        decision_revision=1,
        mode="regular",
    )
    return ref


def _step(case: tuple[Any, ...], action: str, **fields: Any) -> Any:
    root, space, owner, _, _, run = case
    current = read_workflow_run(root, run, owner)
    return _op(
        root,
        space,
        owner,
        WorkflowRequest,
        action=action,
        root_work_id=run,
        expected_revision=current.revision,
        **fields,
    )


def _owner_source(case: tuple[Any, ...], text: bytes) -> KnowledgeRef:
    root, space, owner, *_ = case
    identifier = uuid4()
    _op(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=identifier,
        state=SourceState(
            channel="conversation_user",
            connection="fictional-pi",
            profile_revision=1,
            sender="owner",
            media_type="text/plain",
            capture="full",
            content=text,
        ),
    )
    return KnowledgeRef(record_id=identifier, revision=1)


def _raw_node_result(case: tuple[Any, ...], key: str, raw: bytes) -> ArtifactRef:
    root, space, owner, _, _, run = case
    _step(
        case,
        "bind_node",
        node_key=key,
        model=WorkflowModel(
            provider="fictional", model_id="fictional", profile="local", reasoning="medium"
        ),
    )
    node = next(
        item
        for item in reversed(read_workflow_run(root, run, owner).nodes)
        if item.key == key and not item.retired
    )
    identifier = uuid4()
    _op(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=identifier,
        media_type="text/plain",
        content=raw,
    )
    ref = ArtifactRef(artifact_id=identifier, revision=1)
    _op(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=node.work_id,
        expected_revision=read_work(root, node.work_id, owner).revision,
        output=LinkedOutput(slot="report", artifact=ref),
    )
    _step(case, "validate_output", node_key=key, output=ref)
    return ref


def test_answer_correction_retires_dependent_work_and_keeps_original(tmp_path: Path) -> None:
    case = _setup(
        tmp_path,
        (
            WorkflowNode(
                key="period", kind="question", instruction="Choose period", successors=("analyse",)
            ),
            WorkflowNode(
                key="analyse", kind="model", instruction="Analyse period", dependencies=("period",)
            ),
        ),
    )
    root, _, owner, _, _, run = case
    _step(case, "ask", node_key="period", question="Which period?", purpose="Choose period")
    wait = read_workflow_run(root, run, owner).waits[0]
    first = _owner_source(case, b"Weekly")
    _step(case, "answer", wait_id=wait.wait_id, expected_wait_revision=wait.revision, answer=first)
    _step(case, "advance", node_key="period")
    _step(case, "advance", node_key="period")
    before = read_workflow_run(root, run, owner)
    assert "analyse" in before.ready_nodes
    corrected = _owner_source(case, b"Monthly")
    _step(case, "correct_answer", wait_id=wait.wait_id, expected_wait_revision=2, answer=corrected)
    after = read_workflow_run(root, run, owner)
    assert all(
        item.retired
        for item in after.nodes
        if item.work_id in {entry.work_id for entry in before.nodes}
    )
    assert after.ready_nodes == ("period",)
    _step(case, "advance", node_key="period")
    _step(case, "advance", node_key="period")
    from zaratustra.foundation import read_workflow_packet, read_workflow_wait

    latest = read_workflow_run(root, run, owner).nodes[-1]
    packet = read_workflow_packet(root, run, latest.packet, owner)
    assert b"Monthly" in packet and b"Weekly" in packet
    assert read_workflow_wait(root, run, wait.wait_id, owner).answer == corrected


def test_version_transfer_needs_explicit_mapping_and_preserves_kept_result(tmp_path: Path) -> None:
    case = _setup(
        tmp_path,
        (
            WorkflowNode(
                key="analyse", kind="model", instruction="Analyse inputs", successors=("review",)
            ),
            WorkflowNode(
                key="review", kind="model", instruction="Review result", dependencies=("analyse",)
            ),
        ),
    )
    root, space, owner, activity, ref, run = case
    output = _raw_node_result(
        case, "analyse", b'{"outcome":"result","values":{},"next_nodes":["review"]}'
    )
    _step(case, "advance", node_key="analyse")
    from zaratustra.foundation import read_workflow

    original = read_workflow(root, ref, owner)
    replacement = original.model_copy(
        update={
            "nodes": (
                original.nodes[0],
                original.nodes[1].model_copy(
                    update={"instruction": "Review whole current package"}
                ),
            )
        }
    )
    target = _adopt_workflow(
        root,
        space,
        owner,
        activity,
        _owner_source(case, b"Improve review"),
        replacement,
        identifier=ref.workflow_id,
        from_version=1,
    )
    with pytest.raises(FoundationError, match="mapping_incomplete"):
        _step(case, "migrate", workflow=target)
    _step(
        case,
        "migrate",
        workflow=target,
        node_mapping={"analyse": "analyse", "review": "review"},
        node_dispositions={"analyse": "keep", "review": "replace"},
    )
    state = read_workflow_run(root, run, owner)
    assert state.workflow == target
    kept = next(item for item in state.nodes if item.key == "analyse")
    assert kept.output == output and not kept.retired
    reviews = tuple(item for item in state.nodes if item.key == "review")
    assert reviews[0].retired and not reviews[1].retired
    assert read_work(root, kept.work_id, owner).state.acceptance is None


def test_raw_rejection_limits_survive_reopening_and_explicit_retry(tmp_path: Path) -> None:
    case = _setup(
        tmp_path, (WorkflowNode(key="analyse", kind="model", instruction="Analyse inputs"),)
    )
    root, _, owner, _, _, run = case
    first = _raw_node_result(case, "analyse", b'{"outcome":')
    _step(case, "advance", node_key="analyse")
    second = _raw_node_result(case, "analyse", b'{"outcome":')
    _step(case, "advance", node_key="analyse")
    stopped = read_workflow_run(root, run, owner)
    assert stopped.next_action == "attention" and len(stopped.nodes) == 2
    assert {item.output for item in stopped.nodes} == {first, second}
    assert read_workflow_run(root, run, owner) == stopped
    _step(
        case,
        "retry",
        node_key="analyse",
        answer=_owner_source(case, b"Retry the technical correction"),
    )
    assert read_workflow_run(root, run, owner).ready_nodes == ("analyse",)
    _raw_node_result(case, "analyse", b'{"outcome":"result","values":{}}')
    _step(case, "finish")
    assert read_workflow_run(root, run, owner).next_action == "closed"


def test_workflow_uses_common_stop_and_restore_without_rewriting_run(tmp_path: Path) -> None:
    from zaratustra.foundation import (
        RestoreCandidateRequest,
        StopCandidateRequest,
        list_change_applications,
        read_change_application,
    )

    case = _setup(
        tmp_path, (WorkflowNode(key="analyse", kind="model", instruction="Analyse inputs"),)
    )
    root, space, owner, activity, ref, run = case
    application = next(
        item for item in list_change_applications(root, owner) if item.target_id == ref.workflow_id
    )
    _op(
        root,
        space,
        owner,
        StopCandidateRequest,
        application_id=application.application_id,
        expected_revision=application.revision,
        reason="Stop new starts",
        started_works="Keep current run",
        external_effects="None",
    )
    assert read_workflow_run(root, run, owner).workflow == ref
    with pytest.raises(FoundationError, match="workflow_not_adopted"):
        _op(
            root,
            space,
            owner,
            WorkflowRequest,
            action="start",
            root_work_id=uuid4(),
            workflow=ref,
            activity_id=activity,
            source_refs=(_owner_source(case, b"Another request"),),
        )
    _op(
        root,
        space,
        owner,
        RestoreCandidateRequest,
        application_id=application.application_id,
        expected_revision=2,
        reason="Restore former absence",
        data_restoration="Keep history",
        external_effects="None",
    )
    current, history = read_change_application(root, application.application_id, owner)
    assert current.status == "restored" and tuple(item["kind"] for item in history) == (
        "apply",
        "stop",
        "restore",
    )


def test_definition_without_run_is_sanitized_with_deleted_basis_and_backup(tmp_path: Path) -> None:
    from zaratustra.foundation import (
        DeleteKnowledgeRequest,
        RecoverRequest,
        authorize_local,
        authorize_recovery,
        complete_deletions,
        create_backup,
        read_workflow,
        restore_backup,
    )
    from zaratustra.foundation.storage import space_connection

    root, space, owner, *_ = _structured_case(tmp_path)
    upgrade_workflow_space(root, owner)
    activity, source = uuid4(), uuid4()
    _op(
        root,
        space,
        owner,
        CreateActivityRequest,
        activity_id=activity,
        state=ActivityState(title="Fictional process", goal="Track observations"),
    )
    _op(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=source,
        state=SourceState(
            channel="conversation_user",
            connection="fictional-pi",
            profile_revision=1,
            sender="owner",
            media_type="text/plain",
            capture="full",
            content=b"Private basis marker",
        ),
    )
    ref = _adopt_workflow(
        root,
        space,
        owner,
        activity,
        KnowledgeRef(record_id=source, revision=1),
        WorkflowDefinition(
            title="Fictional process",
            purpose="Private basis marker",
            nodes=(WorkflowNode(key="analyse", kind="model", instruction="Private basis marker"),),
            entry_nodes=("analyse",),
        ),
    )
    backup = create_backup(root, uuid4(), owner)
    restored = tmp_path / "restored-workflow"
    restored.mkdir()
    recovery = authorize_recovery(actor="owner", source_ref="fictional-recovery")
    assert restore_backup(backup.package, restored, recovery).schema_version == 16
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
    assert read_workflow(restored, ref, reopened).purpose == "Private basis marker"
    _op(root, space, owner, DeleteKnowledgeRequest, record_id=source, expected_revision=1)
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_workflow(root, ref, owner)
    with space_connection(root) as (connection, _):
        assert (
            connection.execute(
                "SELECT payload FROM workflow_versions WHERE workflow_id=?", (str(ref.workflow_id),)
            ).fetchone()[0]
            is None
        )
        assert all(
            "Private basis marker" not in row[0]
            for row in connection.execute(
                "SELECT detail_json FROM change_package_parts WHERE target_kind='workflow'"
            )
        )
    assert complete_deletions(root, owner).live_store_sanitized
    assert not backup.package.exists()


def test_exact_method_deletion_retires_only_dependent_workflow_versions(tmp_path: Path) -> None:
    """A Method version retires its exact templates/consumers and preserves another version."""
    from tests.zaratustra.foundation.test_binding import _ready
    from zaratustra.foundation import (
        CreateMethodVersionRequest,
        DeleteMethodVersionRequest,
        MethodDefinition,
        MethodRef,
        ParentOutputSlot,
        PlanChild,
        WorkPlan,
        WorkState,
        complete_deletions,
        create_backup,
        list_change_applications,
        method_checksum,
        read_artifact,
        read_change_application,
        read_development,
        read_knowledge,
        read_method_version,
        read_receipt,
        read_workflow,
        upgrade_activity_setup_space,
        upgrade_change_package_space,
        upgrade_development_space,
        upgrade_knowledge_space,
        upgrade_memory_space,
        upgrade_structures_space,
    )
    from zaratustra.foundation.storage import space_connection

    root, space, owner, activity, _ = _ready(tmp_path)
    identifier = uuid4()
    methods: list[MethodRef] = []
    for version in (1, 2):
        method_definition = MethodDefinition(
            instruction=f"Fictional Method {version}",
            named_outputs=(OutputContract(slot="report", media_type="text/plain"),),
            source_ref="fictional-version-cleanup",
        )
        _op(
            root,
            space,
            owner,
            CreateMethodVersionRequest,
            method_id=identifier,
            version=version,
            definition=method_definition,
        )
        methods.append(
            MethodRef(
                method_id=identifier, version=version, checksum=method_checksum(method_definition)
            )
        )
    for upgrade in (
        upgrade_knowledge_space,
        upgrade_development_space,
        upgrade_change_package_space,
        upgrade_memory_space,
        upgrade_activity_setup_space,
        upgrade_structures_space,
        upgrade_workflow_space,
    ):
        upgrade(root, owner)
    source = _owner_source((root, space, owner), b"Keep this independent original")
    refs: list[WorkflowRef] = []
    for version, method in enumerate(methods, 1):
        plan = WorkPlan(
            parent_outputs=(ParentOutputSlot(slot="report", media_type="text/plain"),),
            children=(
                PlanChild(
                    role="observe",
                    work_id=uuid4(),
                    state=WorkState(
                        activity_id=activity,
                        goal="Prepare observation",
                        expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
                    ),
                ),
            ),
            rationale="Keep one observation",
            source_ref="fictional-plan",
        )
        definition = WorkflowDefinition(
            title=f"Versioned process {version}",
            purpose=f"Fictional process version {version}",
            nodes=(
                WorkflowNode(
                    key="choose",
                    kind="question",
                    instruction="Choose period",
                    successors=("analyse",),
                ),
                WorkflowNode(
                    key="analyse",
                    kind="model",
                    instruction="Analyse observations",
                    method=method,
                    plan=plan,
                    dependencies=("choose",),
                ),
            ),
            entry_nodes=("choose",),
        )
        refs.append(
            _adopt_workflow(
                root,
                space,
                owner,
                activity,
                source,
                definition,
                identifier=refs[0].workflow_id if refs else None,
                from_version=1 if refs else None,
            )
        )
    consumers = tuple(
        _adopt_workflow(
            root,
            space,
            owner,
            activity,
            source,
            WorkflowDefinition(
                title=f"Exact consumer {index}",
                purpose="Use only the exact selected workflow",
                nodes=(
                    WorkflowNode(
                        key="delegate",
                        kind="nested",
                        instruction="Continue exact workflow",
                        workflow=ref,
                    ),
                ),
                entry_nodes=("delegate",),
            ),
        )
        for index, ref in enumerate(refs, 1)
    )
    applications = list_change_applications(root, owner)
    retired = tuple(
        next(
            item
            for item in applications
            if item.target_id == ref.workflow_id and item.version == ref.version
        )
        for ref in (refs[0], consumers[0])
    )
    receipts = tuple(
        UUID(str(read_change_application(root, item.application_id, owner)[1][0]["operation_id"]))
        for item in retired
    )
    run = uuid4()
    _op(
        root,
        space,
        owner,
        WorkflowRequest,
        action="start",
        workflow=refs[0],
        root_work_id=run,
        activity_id=activity,
        source_refs=(source,),
    )
    case = root, space, owner, activity, refs[0], run
    _step(case, "advance", node_key="choose")
    packet = read_workflow_run(root, run, owner).nodes[0].packet
    backup = create_backup(root, uuid4(), owner)
    _op(
        root,
        space,
        owner,
        DeleteMethodVersionRequest,
        method_id=identifier,
        version=1,
        checksum=methods[0].checksum,
    )
    for ref in (refs[0], consumers[0]):
        with pytest.raises(FoundationError, match="content_unavailable"):
            read_workflow(root, ref, owner)
    for item, operation in zip(retired, receipts, strict=True):
        assert read_development(root, item.candidate_id, owner).availability == "unavailable"
        assert read_change_application(root, item.application_id, owner)[0].status == "partial"
        with pytest.raises(FoundationError, match="not_found"):
            read_receipt(root, operation, owner)
    assert read_workflow(root, refs[1], owner).nodes[1].method == methods[1]
    assert read_workflow(root, consumers[1], owner).nodes[0].workflow == refs[1]
    assert (
        read_method_version(root, methods[1], owner).definition.instruction == "Fictional Method 2"
    )
    assert read_knowledge(root, source.record_id, owner).availability == "available"
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_artifact(root, packet.artifact_id, owner)
    with space_connection(root) as (connection, _):
        assert connection.execute(
            "SELECT control,sources FROM workflow_runs WHERE root_work_id=?", (str(run),)
        ).fetchone() == ("paused", None)
        assert (
            connection.execute(
                "SELECT question FROM workflow_waits WHERE root_work_id=?", (str(run),)
            ).fetchone()[0]
            is None
        )
        assert all(
            row[0] == "{}"
            for row in connection.execute(
                "SELECT detail_json FROM change_package_parts WHERE application_id IN (?,?)",
                tuple(str(item.application_id) for item in retired),
            )
        )
    assert complete_deletions(root, owner).live_store_sanitized
    assert not backup.package.exists()


def test_sleep_analysis_adopts_workflow_without_changing_sleep_progress(tmp_path: Path) -> None:
    """Workflow is a common Candidate target; the existing Sleep Work retains its boundary."""
    from tests.zaratustra.foundation.test_child_execution import (
        _assign,
        _claim,
        _invocation,
        _resource,
        _stop,
    )
    from zaratustra.foundation import (
        AnalysisState,
        CreateCompositeWorkRequest,
        CreateMethodVersionRequest,
        IssueChildWorkRequest,
        SleepRemainder,
        SleepSelection,
        SleepState,
        initial_sleep_method,
        initial_sleep_ref,
        list_sleep_sources,
        list_workflow_runs,
        read_development,
        read_sleep_for_work,
        read_space,
        read_workflow,
        sleep_work_template,
    )

    case = _setup(
        tmp_path, (WorkflowNode(key="choose", kind="question", instruction="Choose period"),)
    )
    root, space, owner, activity, _, _ = case
    source = _owner_source(case, b"Dated observations need an explicit review process")
    seed = initial_sleep_ref(space)
    _op(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=seed.method_id,
        version=1,
        definition=initial_sleep_method(),
    )
    work, child, sibling, sleep = (uuid4() for _ in range(4))
    state, plan = sleep_work_template(
        activity_id=activity,
        method=seed,
        work_id=work,
        consolidation_id=child,
        exploration_id=sibling,
        scope="Fictional observations",
    )
    _op(root, space, owner, CreateCompositeWorkRequest, work_id=work, state=state, plan=plan)
    _op(
        root,
        space,
        owner,
        IssueChildWorkRequest,
        parent_work_id=work,
        work_id=child,
        expected_plan_revision=1,
        expected_work_revision=1,
    )
    resource = _resource(root, space, owner, child, "fictional-sleep-child")
    attempt, session, _, _ = _assign(root, space, owner, child, resource)
    _claim(root, space, owner, child, attempt, session)
    _invocation(root, space, owner, child, attempt, session)
    _stop(root, space, owner, child, attempt, session)
    cutoff = read_space(root).state_revision
    analysis = KnowledgeRef(record_id=uuid4(), revision=1)
    _op(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=analysis.record_id,
        state=AnalysisState(
            task="Compare the observation process",
            inputs=(source,),
            executor="fictional-analysis",
            status="result",
            conclusion="Propose a finite period review workflow through common Candidate admission",
        ),
    )
    saved = SleepState(
        work_id=work,
        method=seed,
        scope_activity_ids=(activity,),
        intake_cutoff_revision=cutoff,
        enumeration_cursor_revision=cutoff,
        enumeration_cursor_id=source.record_id,
        exploration_cursor_revision=cutoff,
        exploration_cursor_id=source.record_id,
        selected=(SleepSelection(source=source, purpose="consolidation"),),
        analyses=(analysis,),
        remainder=(SleepRemainder(kind="question", description="Choose the next review period"),),
        spent_units=3,
        resource_limit_units=100,
        consolidation="partial",
        exploration="partial",
    )
    _op(root, space, owner, CreateDevelopmentRequest, record_id=sleep, state=saved)
    before = read_development(root, sleep, owner)
    runs = list_workflow_runs(root, owner)
    ref = _adopt_workflow(
        root,
        space,
        owner,
        activity,
        analysis,
        WorkflowDefinition(
            title="Reviewed observation process",
            purpose="Review a chosen period",
            nodes=(
                WorkflowNode(
                    key="review", kind="model", instruction="Review exact dated observations"
                ),
            ),
            entry_nodes=("review",),
        ),
    )
    assert read_workflow(root, ref, owner).title == "Reviewed observation process"
    assert read_development(root, sleep, owner) == before
    assert read_sleep_for_work(root, child, owner) == before
    assert list_workflow_runs(root, owner) == runs
    listed = list_sleep_sources(root, sleep, owner, purpose="consolidation")
    assert listed["cutoff_revision"] == cutoff
    assert read_work(root, work, owner).state.method == seed


def test_setup_fragment_packet_delivers_only_selected_utf8_bytes(tmp_path: Path) -> None:
    from tests.zaratustra.foundation.test_activity_setup import _step as setup_step
    from tests.zaratustra.foundation.test_activity_setup_recovery import _start

    case = _structured_case(tmp_path)
    root, space, owner, *_ = case
    upgrade_workflow_space(root, owner)
    setup_step(case, "migrate_workflow")
    source = _owner_source((root, space, owner), "Before Шаг After".encode())
    selected = source.model_copy(
        update={"start": len(b"Before "), "end": len(b"Before ") + len("Шаг".encode())}
    )
    setup_step(case, "attach_sources", source_refs=(selected,))
    with pytest.raises(FoundationError, match="invalid_fragment"):
        setup_step(
            case, "attach_sources", source_refs=(source.model_copy(update={"start": 8, "end": 9}),)
        )
    packet = _start(case)
    assert (
        next(item for item in packet["sources"] if item["ref"] == selected.model_dump(mode="json"))[
            "state"
        ]["text"]
        == "Шаг"
    )
    assert "Before Шаг After" not in str(packet)


def test_legacy_migration_preserves_processed_rejection_and_review_counter(tmp_path: Path) -> None:
    from tests.zaratustra.foundation.test_activity_setup import _step as setup_step
    from tests.zaratustra.foundation.test_activity_setup_recovery import _raw, _report, _start
    from tests.zaratustra.foundation.test_activity_structures import _proposal

    case = _structured_case(tmp_path)
    root, _, owner, setup, *_ = case
    _start(case)
    _raw(case, _proposal().model_dump_json())
    _start(case, "review")
    rejected = _raw(case, "{broken legacy review")
    original = read_activity_setup(root, setup, owner)
    old_works = tuple(item.work_id for item in original.state.stages)
    upgrade_workflow_space(root, owner)
    setup_step(case, "migrate_workflow")
    state = read_activity_setup(root, setup, owner).state
    assert state.stages[-1].rejection is not None
    assert state.reviews_started == 1 and state.stages[-1].rejection.artifact == rejected
    assert tuple(item.work_id for item in state.stages) == old_works
    assert state.root_work_id is not None
    assert not set(old_works).intersection(
        child.work_id for child in read_work_plan(root, state.root_work_id, owner).plan.children
    )
    packet = _start(case, "review")
    assert packet["rejected_result"]["content_text"] == "{broken legacy review"
    _raw(case, _report(case))
    setup_step(case, "finish")
    assert read_activity_setup(root, setup, owner).state.phase == "ready"
    assert read_activity_setup(root, setup, owner).state.reviews_started == 2


def test_finished_legacy_review_activates_without_new_send_or_cloned_work(tmp_path: Path) -> None:
    from tests.zaratustra.foundation.test_activity_setup import _step as setup_step
    from tests.zaratustra.foundation.test_activity_setup_recovery import _raw, _report, _start
    from tests.zaratustra.foundation.test_activity_structures import _proposal
    from zaratustra.foundation.storage import space_connection

    case = _structured_case(tmp_path)
    root, _, owner, setup, *_ = case
    _start(case)
    _raw(case, _proposal().model_dump_json())
    _start(case, "review")
    _raw(case, _report(case))
    before = read_activity_setup(root, setup, owner).state
    assert before.phase == "activating" and before.root_work_id is None
    with space_connection(root) as (connection, _):
        sends = connection.execute("SELECT COUNT(*) FROM execution_invocations").fetchone()[0]
    upgrade_workflow_space(root, owner)
    setup_step(case, "finish")
    after = read_activity_setup(root, setup, owner).state
    assert after.phase == "ready" and after.stages == before.stages
    assert after.root_work_id is None and after.reviews_started == before.reviews_started
    with space_connection(root) as (connection, _):
        assert (
            connection.execute("SELECT COUNT(*) FROM execution_invocations").fetchone()[0] == sends
        )
        assert connection.execute("SELECT COUNT(*) FROM workflow_runs").fetchone()[0] == 0


def test_unknown_legacy_stage_prevents_migration_and_repeat(tmp_path: Path) -> None:
    from tests.zaratustra.foundation.test_activity_setup import _step as setup_step
    from tests.zaratustra.foundation.test_activity_setup_recovery import _start
    from tests.zaratustra.foundation.test_child_execution import (
        _assign,
        _assignment_revision,
        _claim,
        _invocation,
        _request_stop,
        _resource,
    )
    from zaratustra.foundation import RecordAttemptStopRequest, read_execution

    case = _structured_case(tmp_path)
    root, space, owner, setup, *_ = case
    _start(case)
    work = read_activity_setup(root, setup, owner).state.stages[-1].work_id
    resource = _resource(root, space, owner, work, "fictional-legacy-stage")
    attempt, session, _, _ = _assign(root, space, owner, work, resource)
    _claim(root, space, owner, work, attempt, session)
    _invocation(root, space, owner, work, attempt, session, finish=False)
    _request_stop(root, space, owner, work, attempt, session)
    _op(
        root,
        space,
        owner,
        RecordAttemptStopRequest,
        work_id=work,
        attempt_id=attempt,
        session_id=session,
        expected_assignment_revision=_assignment_revision(root, owner, work, attempt),
        outcome="unknown",
    )
    before = read_activity_setup(root, setup, owner)
    upgrade_workflow_space(root, owner)
    with pytest.raises(FoundationError, match="unknown_outcome"):
        setup_step(case, "migrate_workflow")
    assert read_activity_setup(root, setup, owner) == before
    assert read_execution(root, work, owner).assignments[-1].status == "unknown"


def test_internal_transition_does_not_accept_work(tmp_path: Path) -> None:
    """A validated service output unblocks its exact child without owner acceptance."""
    case = _setup(
        tmp_path,
        (
            WorkflowNode(
                key="analyse",
                kind="model",
                instruction="Analyse exact inputs",
                successors=("review",),
            ),
            WorkflowNode(
                key="review",
                kind="model",
                instruction="Review the whole result",
                dependencies=("analyse",),
            ),
        ),
    )
    root, space, owner, _, _, run = case
    _step(
        case,
        "bind_node",
        node_key="analyse",
        model=WorkflowModel(
            provider="fictional", model_id="fictional", profile="local", reasoning="medium"
        ),
    )
    node = read_workflow_run(root, run, owner).nodes[0]
    output = uuid4()
    _op(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=output,
        media_type="text/plain",
        content=WorkflowNodeResult(outcome="result", next_nodes=("review",))
        .model_dump_json()
        .encode(),
    )
    _op(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=node.work_id,
        expected_revision=read_work(root, node.work_id, owner).revision,
        output=LinkedOutput(slot="report", artifact=ArtifactRef(artifact_id=output, revision=1)),
    )
    _step(
        case,
        "validate_output",
        node_key="analyse",
        output=ArtifactRef(artifact_id=output, revision=1),
    )
    _step(case, "advance", next_nodes=("review",))
    state = read_workflow_run(root, run, owner)
    assert len(state.nodes) == 2 and state.ready_nodes == ("review",)
    assert read_work(root, node.work_id, owner).state.acceptance is None
    readiness = read_work_plan(root, run, owner).plan.children[1].readiness
    assert readiness is not None and readiness.kind == "all"
    _step(
        case,
        "bind_node",
        node_key="review",
        model=WorkflowModel(
            provider="fictional", model_id="fictional", profile="local", reasoning="medium"
        ),
    )
    assert read_work(root, run, owner).state.acceptance is None
    node = state.nodes[-1]
    output = uuid4()
    _op(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=output,
        media_type="text/plain",
        content=WorkflowNodeResult(outcome="result").model_dump_json().encode(),
    )
    _op(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=node.work_id,
        expected_revision=read_work(root, node.work_id, owner).revision,
        output=LinkedOutput(slot="report", artifact=ArtifactRef(artifact_id=output, revision=1)),
    )
    _step(
        case,
        "validate_output",
        node_key="review",
        output=ArtifactRef(artifact_id=output, revision=1),
    )
    _step(case, "finish")
    parent = read_work(root, run, owner)
    assert parent.state.acceptance is None and parent.state.linked_outputs
    from zaratustra.foundation import read_parent_output_proof

    proof = read_parent_output_proof(
        root, parent.state.linked_outputs[0].artifact.artifact_id, owner
    )
    assert proof is not None and proof.work_id == run


def test_host_wait_survives_reopening_and_rejects_non_owner_source(tmp_path: Path) -> None:
    """A question needs no fake Pi session and has an addressed actual owner answer."""
    case = _setup(
        tmp_path, (WorkflowNode(key="question", kind="question", instruction="Which period?"),)
    )
    root, space, owner, _, _, run = case
    _step(
        case,
        "ask",
        node_key="question",
        question="Which period?",
        purpose="Choose the analysis period",
    )
    state = read_workflow_run(root, run, owner)
    assert state.next_action == "answer" and state.waits[0].question == "Which period?"
    assert read_workflow_run(root, run, owner) == state
    source = uuid4()
    _op(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=source,
        state=SourceState(
            channel="conversation_assistant",
            connection="fictional-pi",
            profile_revision=1,
            sender="assistant",
            media_type="text/plain",
            capture="full",
            content=b"Weekly",
        ),
    )
    with pytest.raises(FoundationError, match="invalid_answer_source"):
        _step(
            case,
            "answer",
            wait_id=state.waits[0].wait_id,
            expected_wait_revision=1,
            answer=KnowledgeRef(record_id=source, revision=1),
        )
    assert read_workflow_run(root, run, owner).waits == state.waits
    source = uuid4()
    _op(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=source,
        state=SourceState(
            channel="conversation_user",
            connection="fictional-pi",
            profile_revision=1,
            sender="owner",
            media_type="text/plain",
            capture="full",
            content=b"Monthly",
        ),
    )
    _step(
        case,
        "answer",
        wait_id=state.waits[0].wait_id,
        expected_wait_revision=1,
        answer=KnowledgeRef(record_id=source, revision=1),
    )
    _step(case, "advance", node_key="question")
    node = read_workflow_run(root, run, owner).nodes[0]
    assert node.validation_id is not None
    _step(case, "finish")
    assert read_workflow_run(root, run, owner).next_action == "closed"


def test_schema16_setup_stages_are_actual_root_children(tmp_path: Path) -> None:
    """Creation has one graph, paired answers and reviewed proposals before blocking."""
    from tests.zaratustra.foundation.test_activity_setup import _step as setup_step
    from tests.zaratustra.foundation.test_activity_setup_recovery import _raw, _report, _start
    from tests.zaratustra.foundation.test_activity_structures import _proposal
    from zaratustra.foundation import SetupQuestion

    old = _structured_case(tmp_path)
    root, space, owner, *_ = old
    upgrade_workflow_space(root, owner)
    setup, activity = uuid4(), uuid4()
    request = ActivitySetupRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        action="begin",
        setup_id=setup,
        activity_id=activity,
        title="Fictional observations",
        text="Keep dated observations",
        contract_version=2,
    )
    receipt = apply_operation(root, request, owner)
    case = root, space, owner, setup, activity, request, receipt
    saved = read_activity_setup(root, setup, owner)
    assert saved.state.root_work_id is not None
    setup_step(case, "question", text="Which analysis period?")
    setup_step(case, "answer", text="Monthly")
    packet = _start(case)
    assert packet["interactions"][0]["question"] == "Which analysis period?"
    assert packet["interactions"][0]["answer"]["state"]["text"] == "Monthly"
    workflow = WorkflowDefinition(
        title="Observation review",
        purpose="Review exact recorded facts",
        nodes=(
            WorkflowNode(
                key="analyse", kind="model", instruction="Analyse an explicit dated period"
            ),
        ),
        entry_nodes=("analyse",),
    )
    draft = _proposal().model_copy(
        update={
            "questions": (
                SetupQuestion(
                    text="Fresh value before a personal plan",
                    blocking=True,
                    scope="procedure",
                    procedure_key="observe",
                ),
            ),
            "workflows": (workflow,),
        }
    )
    _raw(case, draft.model_dump_json())
    assert read_activity_setup(root, setup, owner).state.phase == "drafting"
    _start(case, "review")
    _raw(case, _report(case))
    state = read_activity_setup(root, setup, owner).state
    assert state.root_work_id is not None
    plan = read_work_plan(root, state.root_work_id, owner)
    assert {child.work_id for child in plan.plan.children}.issuperset(
        stage.work_id for stage in state.stages
    )
    setup_step(case, "finish")
    current = read_activity_setup(root, setup, owner)
    assert current.state.phase == "ready"
    assert current.state.root_work_id is not None
    assert read_work(root, current.state.root_work_id, owner).state.linked_outputs
    from zaratustra.foundation import describe_structure, read_workflow

    structure = describe_structure(root, activity, owner)
    ref = WorkflowRef.model_validate(structure["state"]["workflows"][0])
    assert read_workflow(root, ref, owner) == workflow


def _method_case(tmp_path: Path) -> tuple[tuple[Any, ...], UUID]:
    import json

    from zaratustra.foundation import (
        IssueChildWorkRequest,
        ParentOutputSlot,
        PlanChild,
        PlanCondition,
        WorkPlan,
        WorkState,
        read_workflow_method_tasks,
        read_workflow_packet,
    )

    case = _setup(
        tmp_path, (WorkflowNode(key="seed", kind="model", instruction="Prepare a result"),)
    )
    root, space, owner, activity, _, seed_run = case
    source = KnowledgeRef.model_validate(
        json.loads(
            read_workflow_packet(
                root, seed_run, read_workflow_run(root, seed_run, owner).nodes[0].packet, owner
            )
        )["sources"][0]["ref"]
    )
    method = read_work(root, seed_run, owner).state.method
    assert method != "none"
    plan = WorkPlan(
        parent_outputs=(ParentOutputSlot(slot="report", media_type="text/plain"),),
        children=(
            PlanChild(
                role="observe",
                work_id=uuid4(),
                state=WorkState(
                    activity_id=activity,
                    goal="Prepare a checked observation",
                    expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
                ),
            ),
        ),
        completion=PlanCondition(kind="work_succeeded", role="observe"),
        rationale="Use separately accepted observation",
        source_ref="fictional-method-plan",
    )
    definition = WorkflowDefinition(
        title="Method workflow",
        purpose="Preserve ordinary Method authority",
        nodes=(
            WorkflowNode(
                key="analyse",
                kind="model",
                instruction="Analyse the accepted observation",
                method=method,
                plan=plan,
            ),
        ),
        entry_nodes=("analyse",),
    )
    ref = _adopt_workflow(root, space, owner, activity, source, definition)
    run = uuid4()
    _op(
        root,
        space,
        owner,
        WorkflowRequest,
        action="start",
        workflow=ref,
        root_work_id=run,
        activity_id=activity,
        source_refs=(source,),
    )
    view = read_workflow_run(root, run, owner)
    node = view.nodes[0]
    assert read_work(root, node.work_id, owner).state.method == method
    tasks = read_workflow_method_tasks(root, node.work_id, owner)
    assert tasks["children"][0]["ready"] and not tasks["parent_ready"]
    _step(
        (root, space, owner, activity, ref, run),
        "bind_node",
        node_key="analyse",
        model=WorkflowModel(
            provider="fictional", model_id="fictional", profile="local", reasoning="medium"
        ),
    )
    child = tasks["children"][0]
    child_id = UUID(child["work_id"])
    _op(
        root,
        space,
        owner,
        IssueChildWorkRequest,
        parent_work_id=node.work_id,
        work_id=child_id,
        expected_plan_revision=tasks["plan_revision"],
        expected_work_revision=child["work_revision"],
    )
    return (root, space, owner, activity, ref, run), child_id


def test_method_node_pins_real_composite_and_waits_for_owner(tmp_path: Path) -> None:
    """A Method's ordinary acceptance cannot be replaced by service validation."""
    from zaratustra.foundation import read_workflow_method_tasks, read_workflow_packet

    case, child_id = _method_case(tmp_path)
    root, space, owner, _, _, run = case
    node = read_workflow_run(root, run, owner).nodes[0]
    output = uuid4()
    _op(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=output,
        media_type="text/plain",
        content=b"A dated fictional observation",
    )
    _op(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=child_id,
        expected_revision=read_work(root, child_id, owner).revision,
        output=LinkedOutput(slot="report", artifact=ArtifactRef(artifact_id=output, revision=1)),
    )
    pending = read_workflow_run(root, run, owner)
    assert pending.next_action == "owner_action"
    assert read_work(root, child_id, owner).state.acceptance is None
    assert not read_workflow_method_tasks(root, node.work_id, owner)["parent_ready"]
    assert (
        read_workflow_packet(root, run, ArtifactRef(artifact_id=output, revision=1), owner)
        == b"A dated fictional observation"
    )


@pytest.mark.parametrize("interrupted", (False, True))
def test_native_method_wait_retains_addressed_answer_after_pause(
    tmp_path: Path, interrupted: bool
) -> None:
    from tests.zaratustra.foundation.test_child_execution import (
        _assign,
        _claim,
        _invocation,
        _resource,
        _stop,
    )
    from zaratustra.foundation import (
        OpenWaitRequest,
        read_execution,
        read_workflow_continuation_for_work,
        read_workflow_packet,
    )

    case, work = _method_case(tmp_path)
    root, space, owner, _, _, run = case
    resource = _resource(root, space, owner, work, "fictional-native-work")
    attempt, session, _, _ = _assign(root, space, owner, work, resource)
    _claim(root, space, owner, work, attempt, session)
    _invocation(root, space, owner, work, attempt, session)
    wait = uuid4()
    _op(
        root,
        space,
        owner,
        OpenWaitRequest,
        wait_id=wait,
        attempt_id=attempt,
        work_id=work,
        session_id=session,
        expected_actor="owner",
        expected_assignment_revision=read_execution(root, work, owner).assignments[-1].revision,
        question="Which observations should I use?",
        remainder="Keep the checked observation and continue",
        partial_refs=(),
    )
    before = read_workflow_run(root, run, owner)
    assert before.next_action == "answer" and before.waits[0].native
    if interrupted:
        _step(case, "pause")
        assert read_execution(root, work, owner).assignments[-1].status == "stop_requested"
        _stop(root, space, owner, work, attempt, session)
    current = read_workflow_run(root, run, owner)
    assert current.waits[0].wait_id == wait
    receipt = _step(
        case,
        "answer",
        wait_id=wait,
        expected_wait_revision=current.waits[0].revision,
        answer=_owner_source(case, b"Use this month's observations"),
    )
    packet = read_workflow_continuation_for_work(root, work, owner)
    assert packet is not None and b"this month's" in read_workflow_packet(root, run, packet, owner)
    assert ("outbox_id" in receipt.result) != interrupted
    if interrupted:
        snapshot = read_execution(root, work, owner)
        assert all(item.status != "pending" for item in snapshot.outbox)
        assert snapshot.waits[-1].status == "closed"
        assert read_work(root, work, owner).state.acceptance is None
        _step(case, "resume")
        assert read_workflow_run(root, run, owner).next_action == "run"


def test_nested_workflow_wait_is_addressed_through_parent(tmp_path: Path) -> None:
    """A nested question survives parent navigation and never creates fake Pi sessions."""
    import json

    from zaratustra.foundation import read_workflow_packet

    case = _setup(
        tmp_path, (WorkflowNode(key="question", kind="question", instruction="Which period?"),)
    )
    root, space, owner, activity, nested_ref, seed_run = case
    source = KnowledgeRef.model_validate(
        json.loads(
            read_workflow_packet(
                root, seed_run, read_workflow_run(root, seed_run, owner).nodes[0].packet, owner
            )
        )["sources"][0]["ref"]
    )
    definition = WorkflowDefinition(
        title="Parent process",
        purpose="Coordinate an addressed nested interview",
        nodes=(
            WorkflowNode(
                key="interview",
                kind="nested",
                instruction="Obtain the chosen period",
                workflow=nested_ref,
            ),
        ),
        entry_nodes=("interview",),
    )
    ref = _adopt_workflow(root, space, owner, activity, source, definition)
    run = uuid4()
    _op(
        root,
        space,
        owner,
        WorkflowRequest,
        action="start",
        workflow=ref,
        root_work_id=run,
        activity_id=activity,
        source_refs=(source,),
    )
    parent_case = root, space, owner, activity, ref, run
    created = _step(parent_case, "advance", node_key="interview")
    nested_run = UUID(created.result["nested_root_work_id"])
    nested_case = root, space, owner, activity, nested_ref, nested_run
    _step(nested_case, "advance", node_key="question")
    parent = read_workflow_run(root, run, owner)
    assert parent.next_action == "answer" and parent.waits[0].root_work_id == nested_run
    answer = uuid4()
    _op(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=answer,
        state=SourceState(
            channel="conversation_user",
            connection="fictional-pi",
            profile_revision=1,
            sender="owner",
            media_type="text/plain",
            capture="full",
            content=b"Monthly",
        ),
    )
    _step(
        parent_case,
        "answer",
        wait_id=parent.waits[0].wait_id,
        expected_wait_revision=1,
        answer=KnowledgeRef(record_id=answer, revision=1),
    )
    _step(nested_case, "advance", node_key="question")
    _step(nested_case, "finish")
    _step(parent_case, "advance", node_key="interview")
    _step(parent_case, "finish")
    assert read_workflow_run(root, run, owner).next_action == "closed"
