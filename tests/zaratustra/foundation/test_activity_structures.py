"""Real Core boundaries: reviewed definitions, exact data and legacy history."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_activity_setup import Case, _case, _complete, _step
from zaratustra.foundation import (
    ActivitySetupDraftV2,
    ActivitySetupReviewV2,
    CreateKnowledgeRequest,
    DataEntryState,
    DataField,
    DataFormatState,
    FoundationError,
    KnowledgeRef,
    SetupAreaEvidence,
    SetupDecisionBasis,
    SetupFormatTemplate,
    SetupOutputTemplate,
    SetupProcedureTemplate,
    apply_operation,
    describe_structure,
    read_activity_setup,
    read_space,
    upgrade_structures_space,
)

SetupArea = Literal[
    "goal", "workflow", "history", "continuation", "extension", "capabilities", "consistency"
]
AREAS: tuple[SetupArea, ...] = (
    "goal",
    "workflow",
    "history",
    "continuation",
    "extension",
    "capabilities",
    "consistency",
)


def _structured_case(tmp_path: Path) -> Case:
    case = _case(tmp_path)
    root, space, owner, *_ = case
    upgrade_structures_space(root, owner)
    # The existing schema-14 interview is kept; v2 is a distinct new setup.
    from zaratustra.foundation import ActivitySetupRequest

    setup, activity = uuid4(), uuid4()
    request = ActivitySetupRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        action="begin",
        setup_id=setup,
        activity_id=activity,
        title="Fictional observations",
        text="Record dated measurements and analyse chosen periods",
        contract_version=2,
    )
    receipt = apply_operation(root, request, owner)
    return root, space, owner, setup, activity, request, receipt


def _proposal() -> ActivitySetupDraftV2:
    return ActivitySetupDraftV2(
        title="Fictional observations",
        goal="Record and compare measurements",
        instructions="Keep originals; corrections revise an event, new dates are new events",
        process="Import observations, select an explicit period, analyse, then propose changes",
        first_action="Provide the first dated observation",
        first_path="User input → retained Source → typed entry → period analysis",
        formats=(
            SetupFormatTemplate(
                key="observation",
                definition=DataFormatState(
                    title="Observation",
                    role="event",
                    fields=(
                        DataField(key="day", meaning="Event day", type="date", indexed=True),
                        DataField(
                            key="value",
                            meaning="Measured value",
                            type="decimal",
                            precision=2,
                            unit="fictional_unit",
                            unknown_allowed=True,
                            indexed=True,
                        ),
                    ),
                    time_field="day",
                ),
            ),
        ),
        procedures=(
            SetupProcedureTemplate(
                key="observe",
                purpose="Record a dated observation",
                goal="Retain and structure the supplied observation",
                operations=("ingest_batch",),
                outputs=(
                    SetupOutputTemplate(
                        slot="result", media_type="application/json", format_key="observation"
                    ),
                ),
            ),
        ),
        decisions=(
            SetupDecisionBasis(
                subject="Period", status="confirmed", explanation="Chosen per request"
            ),
        ),
    )


def _activate(
    case: Case, draft: ActivitySetupDraftV2 | None = None, *, finish: bool = True
) -> dict[str, Any]:
    root, _, owner, setup, *_ = case
    _step(
        case, "start_stage", stage_kind="draft", stage_instruction="Design the complete structure"
    )
    ref = _complete(case, draft or _proposal())
    current = read_activity_setup(root, setup, owner)
    assert current.state.manifest is not None
    _step(case, "start_stage", stage_kind="review", stage_instruction="Review the entire package")
    report = ActivitySetupReviewV2(
        draft=ref,
        manifest=current.state.manifest,
        input_version=current.state.input_version,
        checked=AREAS,
        coverage=tuple(
            SetupAreaEvidence(
                area=area,
                explanation="The complete process preserves dated originals "
                "and versioned continuation",
                components=("process", "formats.observation", "procedures.observe"),
            )
            for area in AREAS
        ),
        conclusion="No blocking obstacle",
    )
    _complete(case, report)
    if finish:
        _step(case, "finish")
    return describe_structure(root, case[4], owner)


def test_composite_procedure_child_retains_snapshot_and_typed_output(tmp_path: Path) -> None:
    """Risk: assigned children lose the procedure input or publish untyped parent results."""
    from zaratustra.foundation import (
        AcceptWorkRequest,
        ArtifactRef,
        CreateArtifactRequest,
        DataOutputEnvelope,
        IssueChildWorkRequest,
        LinkedOutput,
        LinkWorkOutputRequest,
        MethodDefinition,
        MethodObligation,
        NamedInput,
        OutputContract,
        PlanChild,
        PlanCondition,
        PlanOutputBinding,
        SetupMethodTemplate,
        WorkPlan,
        WorkState,
        create_entry,
        procedure_for_work,
        read_work,
        read_work_plan,
        start_procedure,
    )

    case = _structured_case(tmp_path)
    root, space, owner, setup, activity, *_ = case
    placeholder = uuid4()
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            artifact_id=placeholder,
            media_type="application/json",
            content=b"{}",
        ),
        owner,
    )
    output = OutputContract(slot="result", media_type="application/json")
    original = ArtifactRef(artifact_id=placeholder, revision=1)
    definition = MethodDefinition(
        instruction="Retain typed observations",
        source_ref="fictional",
        named_inputs=(OutputContract(slot="input", media_type="application/json"),),
        named_outputs=(output,),
        obligations=(
            MethodObligation(
                key="record",
                source="fictional",
                role="prepare",
                slot="result",
                media_type="application/json",
            ),
        ),
    )
    plan = WorkPlan(
        named_inputs=(NamedInput(slot="input", artifact=original),),
        children=(
            PlanChild(
                role="prepare",
                work_id=uuid4(),
                state=WorkState(
                    activity_id=activity,
                    goal="Record observation",
                    inputs=(original,),
                    expected_outputs=(output,),
                ),
            ),
        ),
        output_bindings=(
            PlanOutputBinding(
                parent_slot="result",
                role="prepare",
                child_slot="result",
                media_type="application/json",
            ),
        ),
        completion=PlanCondition(kind="work_succeeded", role="prepare"),
        rationale="One assigned preparation",
        source_ref="fictional",
    )
    draft = _proposal()
    draft = draft.model_copy(
        update={
            "methods": (
                SetupMethodTemplate(
                    key="record", definition=definition, output_formats={"result": "observation"}
                ),
            ),
            "procedures": (
                draft.procedures[0].model_copy(
                    update={"method_key": "record", "input_slot": "input", "plan": plan}
                ),
            ),
        }
    )
    described = _activate(case, draft)
    run = start_procedure(root, owner, activity, "observe", "composite")
    parent = UUID(str(run["work_id"]))
    child = read_work_plan(root, parent, owner).plan.children[0].work_id
    parent_state = read_work(root, parent, owner).state
    child_state = read_work(root, child, owner).state
    assert child_state.inputs == parent_state.inputs and original not in child_state.inputs
    assert child_state.structure == parent_state.structure
    saved = procedure_for_work(root, owner, child)
    assert saved is not None and saved["run_id"] == str(run["run_id"])
    snapshot = KnowledgeRef.model_validate(saved["snapshot"])
    apply_operation(
        root,
        IssueChildWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            parent_work_id=parent,
            work_id=child,
            expected_plan_revision=1,
            expected_work_revision=1,
        ),
        owner,
    )
    entry = create_entry(
        root,
        owner,
        DataEntryState(
            scope_activity_id=activity,
            format_ref=KnowledgeRef.model_validate(described["state"]["formats"]["observation"]),
            structure=parent_state.structure,
            role="event",
            work_id=child,
            selection=snapshot,
            values={"day": "2026-01-01", "value": "1.25"},
            bases=(read_activity_setup(root, setup, owner).state.sources[0],),
        ),
    )
    ref = KnowledgeRef(
        record_id=UUID(str(entry.result["record_id"])), revision=cast(int, entry.result["revision"])
    )
    artifact = uuid4()
    envelope = DataOutputEnvelope(
        entries=(ref,), basis_snapshot=snapshot, complete=True, result="A typed observation"
    )
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            artifact_id=artifact,
            media_type="application/json",
            content=envelope.model_dump_json().encode(),
        ),
        owner,
    )
    linked = apply_operation(
        root,
        LinkWorkOutputRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=child,
            expected_revision=2,
            output=LinkedOutput(
                slot="result", artifact=ArtifactRef(artifact_id=artifact, revision=1)
            ),
        ),
        owner,
    )
    assert read_work(root, child, owner).state.acceptance is None
    apply_operation(
        root,
        AcceptWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=child,
            expected_revision=cast(int, linked.result["revision"]),
            basis="Owner checked entry",
        ),
        owner,
    )
    assert read_work(root, child, owner).state.status == "succeeded"
    assert read_work(root, parent, owner).state.acceptance is None


def test_schema_upgrade_and_reviewed_format_admission(tmp_path: Path) -> None:
    """Risk: upgrade loses old setup, or an arbitrary format bypasses reviewed structure."""
    case = _structured_case(tmp_path)
    root, space, owner, setup, activity, *_ = case
    assert read_space(root).schema_version == 15
    result = _activate(case)
    assert read_activity_setup(root, setup, owner).state.phase == "ready"
    assert (
        result["state"]["procedures"][0]["outputs"][0]["format_ref"]
        == result["state"]["formats"]["observation"]
    )
    source = read_activity_setup(root, setup, owner).state.sources[0]
    ref = KnowledgeRef.model_validate(result["state"]["formats"]["observation"])
    record_id = uuid4()
    receipt = apply_operation(
        root,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=record_id,
            state=DataEntryState(
                scope_activity_id=activity,
                format_ref=ref,
                role="event",
                values={"day": "2026-01-01", "value": "0.00"},
                bases=(source,),
            ),
        ),
        owner,
    )

    assert receipt.result["revision"] == 1
    with pytest.raises(FoundationError, match="precision"):
        apply_operation(
            root,
            CreateKnowledgeRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                record_id=uuid4(),
                state=DataEntryState(
                    scope_activity_id=activity,
                    format_ref=ref,
                    role="event",
                    values={"day": "2026-01-02", "value": "0.001"},
                    bases=(source,),
                ),
            ),
            owner,
        )


def test_intake_corrections_cache_and_exact_calculation(tmp_path: Path) -> None:
    """Risk: repeat imports duplicate events, partial input vanishes, or cache hides new data."""
    from zaratustra.foundation import (
        DataMutation,
        IngestDataRequest,
        IntakeElement,
        MemorySelector,
        SourceState,
        aggregate_entries,
        ingest_batch,
        memory_catalog,
        query_entries,
        read_entry,
    )

    case = _structured_case(tmp_path)
    root, space, owner, _, activity, *_ = case
    described = _activate(case)
    format_ref = KnowledgeRef.model_validate(described["state"]["formats"]["observation"])
    source_id, entry_id = uuid4(), uuid4()
    apply_operation(
        root,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=source_id,
            state=SourceState(
                channel="document",
                connection="fictional",
                profile_revision=1,
                scope_activity_id=activity,
                media_type="text/plain",
                capture="full",
                content=b"2026-01-01 value 0; 2026-01-02 value unknown",
            ),
        ),
        owner,
    )
    source = KnowledgeRef(record_id=source_id, revision=1)
    entry = DataEntryState(
        scope_activity_id=activity,
        format_ref=format_ref,
        role="event",
        values={"day": "2026-01-01", "value": "0"},
        bases=(source,),
        external_namespace="fictional",
        external_key="one",
    )
    request = IngestDataRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        source=source,
        delivery_key="first",
        elements=(
            IntakeElement(
                key="one", status="saved", mutation=DataMutation(record_id=entry_id, state=entry)
            ),
            IntakeElement(key="two", status="deferred", reason="Original has an unresolved value"),
        ),
        complete=False,
    )
    result = ingest_batch(root, request, owner)
    assert result.result["deferred"] == 1
    assert ingest_batch(root, request.model_copy(update={"operation_id": uuid4()}), owner).result[
        "repeated"
    ]
    intake = memory_catalog(
        root,
        owner,
        selectors=(
            MemorySelector(
                activity_ids=(activity,), record_ids=(source_id,), material_roles=("intake",)
            ),
        ),
    )
    assert len(cast(list[Any], intake["items"])) == 1
    selectors = (MemorySelector(activity_ids=(activity,), format_refs=(format_ref,)),)
    cached = query_entries(root, owner, selectors, cache=True)
    assert (
        query_entries(root, owner, selectors, cache=True)["selection_id"] == cached["selection_id"]
    )
    sum_result = aggregate_entries(
        root,
        KnowledgeRef(record_id=UUID(str(cached["selection_id"])), revision=1),
        owner,
        field="value",
        operation="sum",
        precision=2,
    )
    assert sum_result["groups"][0]["value"] == "0.00"
    assert sum_result["groups"][0]["known"] == 1
    corrected = entry.model_copy(update={"values": {"day": "2026-01-01", "value": "1.25"}})
    from zaratustra.foundation import correct_entry

    correct_entry(root, owner, entry_id, 1, corrected)
    assert (
        query_entries(root, owner, selectors, cache=True)["selection_id"] != cached["selection_id"]
    )
    assert (
        read_entry(root, owner, KnowledgeRef(record_id=entry_id, revision=1))["state"]["values"][
            "value"
        ]
        == "0.00"
    )
    with pytest.raises(FoundationError, match="explicit correction"):
        ingest_batch(
            root,
            request.model_copy(
                update={
                    "operation_id": uuid4(),
                    "delivery_key": "conflicting",
                    "elements": (
                        IntakeElement(
                            key="one",
                            status="saved",
                            mutation=DataMutation(record_id=entry_id, state=corrected),
                        ),
                    ),
                }
            ),
            owner,
        )


def test_procedure_intent_survives_new_session_and_period(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Risk: resuming a saved request creates another Work or silently shifts its period."""
    from zaratustra.foundation import (
        MemorySelector,
        StartProcedureRequest,
        prepare_memory_cache,
        procedure_status,
        read_work,
        start_procedure,
    )

    case = _structured_case(tmp_path)
    root, space, owner, _, activity, *_ = case
    draft = _proposal()
    procedure = draft.procedures[0].model_copy(
        update={
            "trigger": "period",
            "period": "week",
            "timezone": "UTC",
            "parameters": (DataField(key="label", meaning="Observation label", type="text"),),
        }
    )
    _activate(case, draft.model_copy(update={"procedures": (procedure,)}))
    import zaratustra.foundation.data as implementation

    def interrupted(*args: Any, **kwargs: Any) -> None:
        raise FoundationError("interrupted", "Interrupted before selecting inputs")

    with monkeypatch.context() as patch:
        patch.setattr(implementation, "prepare_memory_cache", interrupted)
        with pytest.raises(FoundationError, match="interrupted"):
            start_procedure(
                root,
                owner,
                activity,
                "observe",
                "saved-intent",
                parameters={"label": "original"},
                when=datetime(2026, 1, 4, tzinfo=UTC),
            )
    selected = prepare_memory_cache(
        root, owner, (MemorySelector(activity_ids=(activity,), kinds=("data_entry",)),), cache=False
    )
    with pytest.raises(FoundationError, match="procedure_conflict"):
        apply_operation(
            root,
            StartProcedureRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                activity_id=activity,
                procedure="observe",
                request_key="saved-intent",
                structure=KnowledgeRef.model_validate(
                    describe_structure(root, activity, owner)["structure"]
                ),
                parameters={"label": "changed"},
                snapshot=KnowledgeRef(record_id=UUID(str(selected["selection_id"])), revision=1),
            ),
            owner,
        )
    first = start_procedure(
        root, owner, activity, "observe", "saved-intent", when=datetime(2026, 2, 10, tzinfo=UTC)
    )
    from zaratustra.foundation import authorize_local

    fresh = authorize_local(root, actor="owner", source_ref="fictional-new-session")
    repeat = start_procedure(
        root, fresh, activity, "observe", "saved-intent", when=datetime(2026, 2, 10, tzinfo=UTC)
    )
    assert repeat["work_id"] == first["work_id"]
    status = procedure_status(root, fresh, UUID(str(first["run_id"])))
    assert status["parameters"] == {"label": "original"}
    assert status["period_from"] == "2025-12-29" and status["period_until"] == "2026-01-05"
    assert read_work(root, UUID(str(first["work_id"])), fresh).state.acceptance is None
    assert status["parameters"] == {"label": "original"}


def _change(case: Case) -> Case:
    from zaratustra.foundation import ActivitySetupRequest

    root, space, owner, _, activity, *_ = case
    setup = uuid4()
    request = ActivitySetupRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        action="begin",
        setup_id=setup,
        activity_id=activity,
        mode="change_structure",
        contract_version=2,
        title="Updated observations",
        text="Use a monthly review",
    )
    receipt = apply_operation(root, request, owner)
    return root, space, owner, setup, activity, request, receipt


def test_change_preserves_old_work_and_deletion_preserves_old_structure(tmp_path: Path) -> None:
    """Risk: adopting or deleting a new setup rewrites Development's existing history."""
    from zaratustra.foundation import (
        CreateWorkRequest,
        DeleteKnowledgeRequest,
        OutputContract,
        WorkState,
        read_activity,
        read_knowledge,
        read_work,
    )

    case = _structured_case(tmp_path)
    root, space, owner, old_setup, activity, *_ = case
    old_structure = _activate(case)
    old_activity = read_activity(root, activity, owner)
    work_id = uuid4()
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=work_id,
            state=WorkState(
                activity_id=activity,
                goal="Existing Development task",
                expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    before = read_work(root, work_id, owner)
    changed = _change(case)
    draft = _proposal().model_copy(
        update={"process": "Import daily; review by month", "title": "Monthly observations"}
    )
    current = _activate(changed, draft)
    assert current["structure"]["revision"] == 2
    assert read_work(root, work_id, owner) == before
    assert read_activity(root, activity, owner) == old_activity
    assert (
        describe_structure(root, activity, owner, work_id=work_id)["structure"]
        == old_structure["structure"]
    )
    original = read_activity_setup(root, changed[3], owner).state.sources[0]
    apply_operation(
        root,
        DeleteKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=original.record_id,
            expected_revision=original.revision,
        ),
        owner,
    )
    assert read_activity(root, activity, owner) == old_activity
    assert read_work(root, work_id, owner) == before
    assert (
        read_knowledge(
            root, old_structure["structure"]["record_id"], owner, revision=1
        ).availability
        == "available"
    )
    assert read_activity_setup(root, old_setup, owner).state.phase == "ready"
    assert (
        describe_structure(root, activity, owner, work_id=work_id)["structure"]
        == (old_structure["structure"])
    )


def test_snapshot_late_arrival_and_deleted_procedure_input(tmp_path: Path) -> None:
    """Risk: exact analysis pretends to be current, or removed bases survive in input copies."""
    from zaratustra.foundation import (
        DeleteKnowledgeRequest,
        MemorySelector,
        aggregate_entries,
        create_entry,
        procedure_status,
        read_artifact,
        read_entry,
        read_work,
        start_procedure,
    )

    case = _structured_case(tmp_path)
    root, space, owner, setup, activity, *_ = case
    draft = _proposal()
    draft = draft.model_copy(
        update={
            "procedures": (
                draft.procedures[0].model_copy(
                    update={
                        "inputs": (
                            MemorySelector(current_activity=True, format_keys=("observation",)),
                        )
                    }
                ),
            )
        }
    )
    described = _activate(case, draft)
    format_ref = KnowledgeRef.model_validate(described["state"]["formats"]["observation"])
    source = read_activity_setup(root, setup, owner).state.sources[0]
    entry = DataEntryState(
        scope_activity_id=activity,
        format_ref=format_ref,
        role="event",
        values={"day": "2026-01-01", "value": "1.25"},
        bases=(source,),
    )
    created = create_entry(root, owner, entry)
    run = start_procedure(root, owner, activity, "observe", "one")
    snapshot = KnowledgeRef.model_validate(
        procedure_status(root, owner, UUID(str(run["run_id"])))["snapshot"]
    )
    assert aggregate_entries(root, snapshot, owner, field="value", operation="sum")["current"]
    create_entry(
        root, owner, entry.model_copy(update={"values": {"day": "2026-01-02", "value": "2"}})
    )
    summary = aggregate_entries(root, snapshot, owner, field="value", operation="sum")
    assert summary["groups"][0]["value"] == "1.250000" and not summary["current"]
    inputs = read_work(root, UUID(str(run["work_id"])), owner).state.inputs
    apply_operation(
        root,
        DeleteKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=UUID(str(created.result["record_id"])),
            expected_revision=1,
        ),
        owner,
    )
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_artifact(root, inputs[0].artifact_id, owner)
    assert (
        read_entry(
            root, owner, KnowledgeRef(record_id=UUID(str(created.result["record_id"])), revision=1)
        )["availability"]
        != "available"
    )


def test_explicit_rerun_requires_basis_and_cannot_change_saved_work_pin(tmp_path: Path) -> None:
    """Risk: retry silently creates another chain or a Work acquires a later structure."""
    from zaratustra.foundation import read_work, start_procedure

    case = _structured_case(tmp_path)
    root, space, owner, setup, activity, *_ = case
    _activate(case)
    first = start_procedure(root, owner, activity, "observe", "one")
    alias = start_procedure(root, owner, activity, "observe", "same-inputs")
    assert alias["work_id"] == first["work_id"]
    with pytest.raises(FoundationError, match="invalid_rerun"):
        start_procedure(
            root, owner, activity, "observe", "bad-rerun", rerun_of=UUID(str(first["run_id"]))
        )
    source = read_activity_setup(root, setup, owner).state.sources[0]
    rerun = start_procedure(
        root,
        owner,
        activity,
        "observe",
        "explicit-rerun",
        rerun_of=UUID(str(first["run_id"])),
        request_basis=(source,),
    )
    assert rerun["work_id"] != first["work_id"]
    old = read_work(root, UUID(str(first["work_id"])), owner)
    head = _activate(_change(case))
    assert old.state.structure != KnowledgeRef.model_validate(head["structure"])
    assert read_work(root, old.work_id, owner) == old


def test_period_aggregate_roots_missing_unknown_and_zero(tmp_path: Path) -> None:
    """Risk: related entries are counted twice, or missing/unknown measurements become zero."""
    from zaratustra.foundation import MemorySelector, aggregate_entries, create_entry, query_entries

    case = _structured_case(tmp_path)
    root, _, owner, setup, activity, *_ = case
    proposal = _proposal()
    fields = (
        proposal.formats[0].definition.fields[0],
        proposal.formats[0].definition.fields[1].model_copy(update={"required": False}),
        DataField(key="related", meaning="Related observation", type="ref", required=False),
    )
    formatted = proposal.formats[0].model_copy(
        update={"definition": proposal.formats[0].definition.model_copy(update={"fields": fields})}
    )
    head = _activate(case, proposal.model_copy(update={"formats": (formatted,)}))
    ref = KnowledgeRef.model_validate(head["state"]["formats"]["observation"])
    basis = read_activity_setup(root, setup, owner).state.sources[0]
    identifiers: list[UUID] = []
    for day, value in (("2026-01-01", "0"), ("2026-01-02", None), ("2026-01-03", "missing")):
        values: dict[str, Any] = {"day": day}
        if value != "missing":
            values["value"] = value
        if identifiers:
            values["related"] = {"record_id": str(identifiers[0]), "revision": 1, "mode": "exact"}
        result = create_entry(
            root,
            owner,
            DataEntryState(
                scope_activity_id=activity,
                format_ref=ref,
                role="event",
                values=values,
                bases=(basis,),
            ),
        )
        identifiers.append(UUID(str(result.result["record_id"])))
    chosen = query_entries(
        root, owner, (MemorySelector(format_refs=(ref,), record_ids=tuple(identifiers[1:])),)
    )
    snapshot = KnowledgeRef(record_id=UUID(str(chosen["selection_id"])), revision=1)
    aggregated = aggregate_entries(
        root, snapshot, owner, field="value", operation="mean", group_period="week"
    )
    assert aggregated["groups"][0]["records"] == 2
    assert aggregated["groups"][0]["known"] == 0
    assert aggregated["groups"][0]["unknown"] == 1 and aggregated["groups"][0]["missing"] == 1
    assert aggregated["groups"][0]["value"] is None
    all_entries = query_entries(root, owner, (MemorySelector(format_refs=(ref,)),))
    complete = aggregate_entries(
        root,
        KnowledgeRef(record_id=UUID(str(all_entries["selection_id"])), revision=1),
        owner,
        field="value",
        operation="sum",
    )
    assert complete["groups"][0]["value"] == "0.000000" and complete["groups"][0]["known"] == 1


def test_stop_restore_then_new_adoption_keeps_revision_history(tmp_path: Path) -> None:
    """Risk: restoration makes the next adoption reuse an existing revision or reset old Works."""
    from uuid import UUID

    from zaratustra.foundation import (
        RestoreCandidateRequest,
        StopCandidateRequest,
        read_change_application,
        start_procedure,
    )

    case = _structured_case(tmp_path)
    root, space, owner, _, activity, *_ = case
    first = _activate(case)
    changed = _change(case)
    _activate(changed, finish=False)
    finished = _step(changed, "finish")
    application = finished.operation_id
    app = read_change_application(root, application, owner)[0]
    apply_operation(
        root,
        StopCandidateRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            application_id=application,
            expected_revision=app.revision,
            reason="Restore the prior process",
            started_works="None",
            external_effects="None",
        ),
        owner,
    )
    with pytest.raises(FoundationError, match="structure_stopped"):
        start_procedure(root, owner, activity, "observe", "stopped")
    app = read_change_application(root, application, owner)[0]
    apply_operation(
        root,
        RestoreCandidateRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            application_id=application,
            expected_revision=app.revision,
            reason="Return to prior process",
            data_restoration="Keep all entries and historical revisions",
            external_effects="None",
        ),
        owner,
    )
    assert describe_structure(root, activity, owner)["structure"] == first["structure"]
    next_head = _activate(_change(case))
    assert next_head["structure"]["record_id"] == str(UUID(first["structure"]["record_id"]))
    assert next_head["structure"]["revision"] == 3


def test_provenance_copy_does_not_bypass_original_access_or_deletion(tmp_path: Path) -> None:
    """Risk: an ordinary Artifact copy conceals denied/deleted typed procedure bases."""
    from zaratustra.foundation import (
        CreateArtifactRequest,
        CreateGrantRequest,
        DeleteKnowledgeRequest,
        GrantState,
        ProvenanceRef,
        authorize_local,
        create_entry,
        read_artifact,
        read_entry,
        read_work,
        start_procedure,
    )

    case = _structured_case(tmp_path)
    root, space, owner, setup, activity, *_ = case
    head = _activate(case)
    source = read_activity_setup(root, setup, owner).state.sources[0]
    run = start_procedure(root, owner, activity, "observe", "one", request_basis=(source,))
    work = read_work(root, UUID(str(run["work_id"])), owner)
    input_ref = work.state.inputs[0]
    original_content = read_artifact(root, input_ref.artifact_id, owner).content
    assert original_content is not None
    copy_id = uuid4()
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            artifact_id=copy_id,
            media_type="application/json",
            content=original_content,
            provenance=(
                ProvenanceRef(relation="copy", record_id=input_ref.artifact_id, revision=1),
            ),
        ),
        owner,
    )
    entry = create_entry(
        root,
        owner,
        DataEntryState(
            scope_activity_id=activity,
            format_ref=KnowledgeRef.model_validate(head["state"]["formats"]["observation"]),
            role="event",
            values={"day": "2026-01-01", "value": "2"},
            bases=(KnowledgeRef(record_id=copy_id, revision=1),),
        ),
    )
    ref = KnowledgeRef(record_id=UUID(str(entry.result["record_id"])), revision=1)
    # Grant the copy and entry alone: no permission to its original is implied.
    for identifier in (copy_id, ref.record_id):
        apply_operation(
            root,
            CreateGrantRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                grant_id=uuid4(),
                state=GrantState(
                    grantee="viewer",
                    actions=("record.read",),
                    resource_type="artifact",
                    resource_id=identifier,
                ),
            ),
            owner,
        )
    apply_operation(
        root,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            grant_id=uuid4(),
            state=GrantState(
                grantee="viewer",
                actions=("record.read",),
                resource_type="activity",
                resource_id=activity,
            ),
        ),
        owner,
    )
    viewer = authorize_local(root, actor="viewer", source_ref="fictional-limited-reader")
    with pytest.raises(FoundationError, match="permission_denied"):
        read_artifact(root, copy_id, viewer)
    with pytest.raises(FoundationError, match="permission_denied"):
        read_entry(root, viewer, ref)
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
        read_artifact(root, copy_id, owner)
    assert read_entry(root, owner, ref)["availability"] != "available"
