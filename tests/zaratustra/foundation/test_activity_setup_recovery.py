"""Raw response regressions: durable repair, bounded sends and retained originals."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_activity_setup import Case, _step
from tests.zaratustra.foundation.test_activity_structures import AREAS, _proposal, _structured_case
from tests.zaratustra.foundation.test_child_execution import _assign, _claim, _invocation, _stop
from tests.zaratustra.foundation.test_execution import InvocationFields, invocation, start
from zaratustra.foundation import (
    ActivitySetupRequest,
    AdmitInvocationRequest,
    ArtifactRef,
    AssignAttemptRequest,
    CreateArtifactRequest,
    CreateKnowledgeRequest,
    CreateResourceRequest,
    DeleteKnowledgeRequest,
    FinishInvocationRequest,
    FoundationError,
    KnowledgeRef,
    LinkedOutput,
    LinkWorkOutputRequest,
    MemorySelector,
    OutputContract,
    ProcedureOperation,
    PublishAttemptOutputRequest,
    RecoverRequest,
    ResourceState,
    SendInvocationRequest,
    SetupStage,
    SetupWorkTemplate,
    SourceState,
    WorkingSet,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    read_activity_setup,
    read_artifact,
    read_execution,
    read_knowledge,
    read_setup_stage,
    read_work,
    read_work_plan,
    read_workflow_run,
    restore_backup,
    upgrade_workflow_space,
)
from zaratustra.integrations import installed_integrations


def _recovery_case(tmp_path: Path, schema: int) -> Case:
    case = _structured_case(tmp_path)
    if schema == 16:
        upgrade_workflow_space(case[0], case[2])
        _step(case, "migrate_workflow")
    return case


def _raw(case: Case, text: str, *, complete: bool = True) -> ArtifactRef:
    root, space, owner, setup, *_ = case
    stage = read_activity_setup(root, setup, owner).state.stages[-1]
    ref = ArtifactRef(artifact_id=uuid4(), revision=1)
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            artifact_id=ref.artifact_id,
            media_type="text/plain",
            content=text.encode("utf-8"),
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
    if complete:
        _step(case, "complete_stage", output=ref)
    return ref


def _start(case: Case, kind: str = "draft") -> dict[str, Any]:
    _step(case, "start_stage", stage_kind=kind, stage_instruction="Use the whole exact packet")
    state = read_activity_setup(case[0], case[3], case[2]).state
    content = read_artifact(case[0], state.stages[-1].packet.artifact_id, case[2]).content
    assert content is not None
    return cast(dict[str, Any], json.loads(content))


def _report(case: Case, blocking: bool = False) -> str:
    state = read_activity_setup(case[0], case[3], case[2]).state
    assert state.draft is not None and state.manifest is not None
    return json.dumps(
        {
            "contract_version": 2,
            "draft": state.draft.model_dump(mode="json"),
            "manifest": state.manifest.model_dump(mode="json"),
            "input_version": state.input_version,
            "checked": AREAS,
            "coverage": [
                {
                    "area": area,
                    "explanation": "The whole workflow has been examined",
                    "components": ["process", "first_path", "procedures.observe"],
                }
                for area in AREAS
            ],
            "findings": [
                {
                    "area": "workflow",
                    "problem": "Unclear event date",
                    "cause": "Dates conflated",
                    "blocking": True,
                }
            ]
            if blocking
            else [],
            "conclusion": "Whole review",
        }
    )


def _setup_source(case: Case, text: str = "Additional original observations") -> KnowledgeRef:
    record = uuid4()
    apply_operation(
        case[0],
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=case[1],
            actor="owner",
            record_id=record,
            state=SourceState(
                channel="document",
                connection="fictional-test",
                profile_revision=1,
                source_event_id=str(record),
                media_type="text/plain",
                capture="full",
                content=text.encode("utf-8"),
            ),
        ),
        case[2],
    )
    return KnowledgeRef(record_id=record, revision=1)


def _assigned_setup_stage(case: Case) -> tuple[SetupStage, UUID, UUID]:
    root, space, owner, setup, *_ = case
    stage = read_activity_setup(root, setup, owner).state.stages[-1]
    resource = uuid4()
    apply_operation(
        root,
        CreateResourceRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=stage.work_id,
            resource_id=resource,
            state=ResourceState(label="Fictional setup resource", root=root, mode="shared"),
        ),
        owner,
    )
    attempt, session, _, _ = _assign(root, space, owner, stage.work_id, resource)
    _claim(root, space, owner, stage.work_id, attempt, session)
    return stage, attempt, session


@pytest.mark.parametrize("schema", (15, 16))
def test_paused_stopped_stage_accepts_new_sources_and_preserves_raw_history(
    tmp_path: Path, schema: int
) -> None:
    """A stopped unfinished correction must not permanently reject new user originals."""
    case = _recovery_case(tmp_path, schema)
    _start(case)
    _raw(case, _proposal().model_dump_json())
    _start(case, "review")
    _raw(case, _report(case, blocking=True))
    _start(case, "correction")
    raw = _raw(case, '{"unfinished":', complete=False)
    stage, attempt, session = _assigned_setup_stage(case)
    _step(case, "pause")
    _stop(case[0], case[1], case[2], stage.work_id, attempt, session)
    before = read_activity_setup(case[0], case[3], case[2])
    work_before = read_work(case[0], stage.work_id, case[2])
    source = _setup_source(case, "New known facts Шаг")
    request = ActivitySetupRequest(
        operation_id=uuid4(),
        space_id=case[1],
        actor="owner",
        setup_id=case[3],
        activity_id=case[4],
        action="attach_sources",
        expected_revision=before.revision,
        source_refs=(source,),
    )
    receipt = apply_operation(case[0], request, case[2])
    assert apply_operation(case[0], request, case[2]) == receipt
    current = read_activity_setup(case[0], case[3], case[2])
    assert current.state.phase == "paused" and current.state.stages[-1].retired
    assert current.state.input_version == before.state.input_version + 1
    assert current.state.sources[:-1] == before.state.sources
    assert current.state.sources[-1] == source
    assert current.state.reviews_started == before.state.reviews_started == 1
    assert current.state.draft is current.state.review is current.state.manifest is None
    if schema == 16:
        closed = read_work(case[0], stage.work_id, case[2])
        assert closed.state.status == "cancelled" and closed.state.acceptance is None
        assert closed.state.linked_outputs == work_before.state.linked_outputs
        assert (
            read_work(case[0], stage.work_id, case[2], revision=work_before.revision) == work_before
        )
    else:
        assert read_work(case[0], stage.work_id, case[2]) == work_before
    assert read_artifact(case[0], raw.artifact_id, case[2]).content == b'{"unfinished":'
    assert (
        read_activity_setup(
            case[0], case[3], authorize_local(case[0], actor="owner", source_ref="reopened")
        )
        == current
    )
    _step(case, "resume")
    packet = _start(case)
    assert [item["ref"] for item in packet["sources"]] == [
        ref.model_dump(mode="json") for ref in current.state.sources
    ]
    assert read_activity_setup(case[0], case[3], case[2]).state.stages[-1].work_id != stage.work_id
    if schema == 16:
        parent = read_activity_setup(case[0], case[3], case[2]).state.root_work_id
        assert parent is not None
        assert stage.work_id not in {
            child.work_id for child in read_work_plan(case[0], parent, case[2]).plan.children
        }
        old_plan = read_work_plan(case[0], parent, case[2], revision=4)
        assert stage.work_id in {child.work_id for child in old_plan.plan.children}
        assert next(
            node
            for node in read_workflow_run(case[0], parent, case[2]).nodes
            if node.work_id == stage.work_id
        ).retired
    _raw(case, _proposal().model_dump_json())
    _start(case, "review")
    _raw(case, _report(case))
    assert read_activity_setup(case[0], case[3], case[2]).state.reviews_started == 2
    _step(case, "finish")
    assert read_activity_setup(case[0], case[3], case[2]).state.phase == "ready"


@pytest.mark.parametrize("schema", (15, 16))
def test_pause_does_not_claim_executor_stopped_before_new_input_changes(
    tmp_path: Path, schema: int
) -> None:
    """A pause receipt fences sends but cannot stand in for observed Attempt shutdown."""
    case = _recovery_case(tmp_path, schema)
    _start(case)
    stage, attempt, session = _assigned_setup_stage(case)
    source = _setup_source(case)
    with pytest.raises(FoundationError, match="setup_running"):
        _step(case, "attach_sources", source_refs=(source,))
    _step(case, "pause")
    before = read_activity_setup(case[0], case[3], case[2])
    assert (
        read_execution(case[0], stage.work_id, case[2]).assignments[-1].status == "stop_requested"
    )
    for action in ("attach_sources", "resume", "retry"):
        with pytest.raises(FoundationError, match="setup_stopping"):
            _step(
                case, action, **({"source_refs": (source,)} if action == "attach_sources" else {})
            )
        assert read_activity_setup(case[0], case[3], case[2]) == before
    _stop(case[0], case[1], case[2], stage.work_id, attempt, session)
    _step(case, "attach_sources", source_refs=(source,))
    assert read_activity_setup(case[0], case[3], case[2]).state.stages[-1].retired


@pytest.mark.parametrize("schema", (15, 16))
@pytest.mark.parametrize("outcome", ("admitted", "sent", "unknown"))
def test_paused_unknown_saves_inputs_without_implicit_send_or_same_work_replay(
    tmp_path: Path, schema: int, outcome: str
) -> None:
    """Changed inputs plus explicit retry permit a fresh read-only stage, never request replay."""
    case = _recovery_case(tmp_path, schema)
    original_packet = _start(case)
    stage, attempt, session = _assigned_setup_stage(case)
    invocation_id, _ = invocation(case[0], case[1], stage.work_id, attempt, session, case[2], 7)
    common: InvocationFields = dict(
        invocation_id=invocation_id, attempt_id=attempt, work_id=stage.work_id, session_id=session
    )
    apply_operation(
        case[0],
        AdmitInvocationRequest(operation_id=uuid4(), space_id=case[1], actor="owner", **common),
        case[2],
    )
    if outcome != "admitted":
        apply_operation(
            case[0],
            SendInvocationRequest(operation_id=uuid4(), space_id=case[1], actor="owner", **common),
            case[2],
        )
    if outcome == "unknown":
        apply_operation(
            case[0],
            FinishInvocationRequest(
                operation_id=uuid4(), space_id=case[1], actor="owner", outcome="unknown", **common
            ),
            case[2],
        )
    _step(case, "pause")
    with pytest.raises(FoundationError, match="unknown_effect"):
        _step(case, "retry")
    source = _setup_source(case)
    _step(case, "attach_sources", source_refs=(source,))
    current = read_activity_setup(case[0], case[3], case[2])
    assert current.state.phase == "paused" and not current.state.stages[-1].retired
    assert current.state.input_version == stage.input_version + 1
    assert current.state.result and "saved" in current.state.result
    assert (
        read_artifact(case[0], stage.packet.artifact_id, case[2]).content
        == json.dumps(
            original_packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    )
    snapshot = read_execution(case[0], stage.work_id, case[2])
    assert (
        snapshot.invocations[-1].status == outcome and snapshot.invocations[-1].reserve_units == 7
    )
    for action in ("resume", "retry", "start_stage", "answer"):
        fields = (
            {"stage_kind": "draft", "stage_instruction": "Forbidden replay"}
            if action == "start_stage"
            else {"text": "Do not answer for owner"}
            if action == "answer"
            else {}
        )
        with pytest.raises(FoundationError, match="unknown_effect"):
            _step(case, action, **fields)
        assert read_activity_setup(case[0], case[3], case[2]) == current
        assert read_execution(case[0], stage.work_id, case[2]) == snapshot
    _stop(case[0], case[1], case[2], stage.work_id, attempt, session)
    stopped = read_execution(case[0], stage.work_id, case[2])
    assert stopped.assignments[-1].status == "stopped"
    assert (
        stopped.invocations[-1].status == "unknown" and stopped.invocations[-1].usage_units is None
    )
    reopened = authorize_local(case[0], actor="owner", source_ref="reopened")
    assert read_activity_setup(case[0], case[3], reopened) == current
    with pytest.raises(FoundationError, match="unknown_effect"):
        _step(case, "resume")
    _step(case, "retry")
    packet = _start(case)
    assert packet["sources"][:-1] == original_packet["sources"]
    assert packet["sources"][-1]["ref"] == source.model_dump(mode="json")
    historical = read_execution(case[0], stage.work_id, reopened)
    assert historical.attempts == stopped.attempts
    assert historical.assignments == stopped.assignments
    assert historical.invocations == stopped.invocations
    if schema == 16:
        assert historical.work.state.status == "cancelled"
        assert historical.work.state.acceptance is None
        assert (
            read_work(case[0], stage.work_id, reopened, revision=stopped.work.revision)
            == stopped.work
        )
    final = read_activity_setup(case[0], case[3], reopened)
    assert final.state.stages[-2].retired and final.state.stages[-1].work_id != stage.work_id
    resource = stopped.resources[0]
    with pytest.raises(FoundationError, match="setup_pending"):
        apply_operation(
            case[0],
            AssignAttemptRequest(
                operation_id=uuid4(),
                space_id=case[1],
                actor="owner",
                attempt_id=uuid4(),
                work_id=stage.work_id,
                expected_work_revision=stopped.work.revision,
                resource_id=resource.resource_id,
                expected_resource_revision=resource.revision,
                session_id=uuid4(),
                previous_attempt_id=attempt,
                executor_version="fictional-setup",
            ),
            reopened,
        )


@pytest.mark.parametrize("schema", (15, 16))
def test_unknown_retry_requires_new_inputs_even_after_observed_stop(
    tmp_path: Path, schema: int
) -> None:
    """Explicit retry is not permission to duplicate an unknown request with the same packet."""
    case = _recovery_case(tmp_path, schema)
    _start(case)
    stage, attempt, session = _assigned_setup_stage(case)
    _invocation(case[0], case[1], case[2], stage.work_id, attempt, session, finish=False)
    _step(case, "pause")
    _stop(case[0], case[1], case[2], stage.work_id, attempt, session)
    before = read_activity_setup(case[0], case[3], case[2])
    with pytest.raises(FoundationError, match="unknown_effect"):
        _step(case, "retry")
    assert read_activity_setup(case[0], case[3], case[2]) == before


def test_paused_unknown_question_keeps_actual_answer_without_native_continuation(
    tmp_path: Path,
) -> None:
    """A real owner answer must not be lost or implicitly restart an unknown request."""
    case = _recovery_case(tmp_path, 16)
    original = _start(case)
    stage, attempt, session = _assigned_setup_stage(case)
    _invocation(case[0], case[1], case[2], stage.work_id, attempt, session, finish=False)
    _step(case, "question", text="Which period should the ordinary process use?")
    _step(case, "pause")
    before = read_execution(case[0], stage.work_id, case[2])
    _step(case, "answer", text="Use a month; this is my original answer")
    current = read_activity_setup(case[0], case[3], case[2])
    assert current.state.question is None and current.state.phase == "paused"
    assert not current.state.stages[-1].retired
    assert current.state.input_version == stage.input_version + 1
    pair = current.state.interactions[-1]
    assert (
        pair.question == "Which period should the ordinary process use?" and pair.answer is not None
    )
    answer = read_knowledge(case[0], pair.answer.record_id, case[2])
    assert isinstance(answer.state, SourceState)
    assert answer.state.content == b"Use a month; this is my original answer"
    assert read_execution(case[0], stage.work_id, case[2]) == before
    with pytest.raises(FoundationError, match="unknown_effect"):
        _step(case, "resume")
    with pytest.raises(FoundationError, match="unknown_effect"):
        _step(case, "retry")
    _stop(case[0], case[1], case[2], stage.work_id, attempt, session)
    _step(case, "retry")
    packet = _start(case)
    assert packet["sources"][:-1] == original["sources"]
    assert (
        packet["interactions"][-1]["answer"]["state"]["text"]
        == "Use a month; this is my original answer"
    )
    assert packet["interactions"][-1]["question"] == pair.question
    assert read_execution(case[0], stage.work_id, case[2]).invocations[-1].status == "unknown"


@pytest.mark.parametrize(
    "text",
    [
        "I want to improve",
        "Keep dated observations, compare a chosen period, and preserve corrections",
        "Forwarded prior answers: daily observations; review period unknown",
        "I know my goal; I do not know the schedule yet",
    ],
)
@pytest.mark.parametrize("schema", (15, 16))
def test_input_forms_keep_originals_and_saved_question(
    tmp_path: Path, text: str, schema: int
) -> None:
    """Risk: forwarded/partial answers disappear or restart duplicates the Activity."""
    case = _recovery_case(tmp_path, schema)
    _step(case, "answer", text=text)
    _step(case, "question", text="Which review period is useful?")
    saved = read_activity_setup(case[0], case[3], case[2])
    reopened = authorize_local(case[0], actor="owner", source_ref="reopened")
    assert read_activity_setup(case[0], case[3], reopened) == saved
    _step(case, "answer", text="Weekly")
    packet = _start(case)
    assert text in json.dumps(packet, ensure_ascii=False)
    assert packet["activity_id"] == str(saved.state.activity_id)
    assert read_activity_setup(case[0], case[3], reopened).state.question is None


@pytest.mark.parametrize("original", ['{"contract_version":2,', " ", ""])
@pytest.mark.parametrize("schema", (15, 16))
def test_raw_failures_repair_after_reopen_and_compile_working_set(
    tmp_path: Path, original: str, schema: int
) -> None:
    """Risk: malformed JSON/operation prose locks setup or working_set is rejected."""
    case = _recovery_case(tmp_path, schema)
    packet = _start(case)
    assert "working_set" in {item["operation"] for item in packet["supported_operations"]}
    first = _raw(case, original)
    state = read_activity_setup(case[0], case[3], case[2]).state
    assert state.draft is None and state.manifest is None
    assert state.stages[-1].rejection is not None
    assert state.stages[-1].rejection.artifact == first
    assert read_artifact(case[0], first.artifact_id, case[2]).content == original.encode()
    reopened = authorize_local(case[0], actor="owner", source_ref="new-session")
    assert read_activity_setup(case[0], case[3], reopened).state == state
    repair = _start(case)
    assert repair["rejected_result"]["content_text"] == original
    assert repair["sources"] == packet["sources"]
    bad = json.loads(_proposal().model_dump_json())
    bad["procedures"][0]["operations"] = ["Preserve the original separately"]
    _raw(case, json.dumps(bad))
    rejection = read_activity_setup(case[0], case[3], reopened).state.stages[-1].rejection
    assert rejection is not None
    assert rejection.issues[0].path == ("procedures", 0, "operations", 0)
    assert "working_set" in rejection.issues[0].allowed_values
    _start(case)
    good = _proposal().model_copy(
        update={
            "procedures": (
                _proposal()
                .procedures[0]
                .model_copy(update={"operations": (ProcedureOperation.WORKING_SET,)}),
            ),
            "working_sets": (
                WorkingSet(
                    key="current",
                    purpose="Current observations",
                    selectors=(
                        MemorySelector(current_activity=True, format_keys=("observation",)),
                    ),
                ),
            ),
        }
    )
    _raw(case, good.model_dump_json())
    _start(case, "review")
    _raw(case, _report(case))
    _step(case, "finish")
    current = read_activity_setup(case[0], case[3], reopened)
    assert current.state.phase == "ready" and current.state.reviews_started == 1
    result = installed_integrations(case[0], reopened).execute(
        uuid4(),
        "data",
        "working_set",
        {"activity_id": str(case[4]), "key": "current"},
        contract_version=1,
    )
    assert result.output


@pytest.mark.parametrize("kind", ["correction", "review"])
def test_invalid_result_repeats_same_kind_with_whole_package(tmp_path: Path, kind: str) -> None:
    """Risk: a broken report becomes success or correction loses the reviewed whole."""
    case = _structured_case(tmp_path)
    _start(case)
    _raw(case, _proposal().model_dump_json())
    if kind == "correction":
        _start(case, "review")
        _raw(case, _report(case, blocking=True))
    original = _start(case, kind)
    _raw(case, "{broken")
    packet = _start(case, kind)
    assert packet["draft"] == original["draft"]
    assert packet["activation_manifest"] == original["activation_manifest"]
    assert packet["rejected_result"]["stage_kind"] == kind
    current = read_activity_setup(case[0], case[3], case[2]).state
    assert current.stages[-1].repair_number == 1
    assert current.reviews_started == (2 if kind == "review" else 1)


@pytest.mark.parametrize("schema", (15, 16))
def test_review_component_contract_and_repair_use_same_exact_catalog(
    tmp_path: Path, schema: int
) -> None:
    """Risk: real keyed components are rejected or review has to guess valid addresses."""
    case = _recovery_case(tmp_path, schema)
    proposal = _proposal().model_copy(
        update={
            "working_sets": tuple(
                WorkingSet(
                    key=key,
                    purpose="Selected observations",
                    selectors=(MemorySelector(current_activity=True),),
                )
                for key in ("foundation", "period_events", "period_plans", "reviews")
            ),
            "works": tuple(
                SetupWorkTemplate(
                    key=key,
                    goal="Record the first observation",
                    expected_outputs=(OutputContract(slot="result", media_type="text/plain"),),
                )
                for key in ("foundation_and_first_event", "first_personal_program")
            ),
        }
    )
    _start(case)
    _raw(case, proposal.model_dump_json())
    packet = _start(case, "review")
    components = [
        "first_action",
        "working_sets.foundation",
        "working_sets.period_events",
        "working_sets.period_plans",
        "working_sets.reviews",
        "works.foundation_and_first_event",
        "works.first_personal_program",
    ]
    catalog = packet["review_components"]
    component_schema = packet["result_schema"]["$defs"]["SetupAreaEvidence"]["properties"][
        "components"
    ]["items"]
    assert component_schema == {"type": "string", "enum": catalog}
    assert set(components).issubset(catalog)
    assert {"first_path", "working_sets", "initial_works"}.issubset(catalog)
    assert "initial_works.first_personal_program" in catalog
    report = json.loads(_report(case))
    for item in report["coverage"]:
        item["components"] = components
    report["coverage"][1]["components"] = ["working_sets.absent"]
    original = json.dumps(report)
    rejected = _raw(case, original)
    state = read_activity_setup(case[0], case[3], case[2]).state
    rejection = state.stages[-1].rejection
    assert rejection is not None and rejection.artifact == rejected
    assert rejection.issues[0].code == "unsupported_review_component"
    assert rejection.issues[0].path == ("coverage", 1, "components", 0)
    assert list(rejection.issues[0].allowed_values) == catalog
    assert "working_sets.absent" not in rejection.issues[0].allowed_values
    repair = _start(case, "review")
    assert repair["review_components"] == catalog
    assert repair["result_schema"] == packet["result_schema"]
    assert repair["rejected_result"]["content_text"] == original
    assert repair["activation_manifest"] == packet["activation_manifest"]
    report["coverage"][1]["components"] = components
    _raw(case, json.dumps(report))
    _step(case, "finish")
    state = read_activity_setup(case[0], case[3], case[2]).state
    assert state.phase == "ready" and state.reviews_started == 2
    assert read_artifact(case[0], rejected.artifact_id, case[2]).content == original.encode()


def test_setup_source_packet_keeps_received_and_event_times_distinct(tmp_path: Path) -> None:
    """Risk: an old event is presented as current or a relative report loses receipt time."""
    case = _recovery_case(tmp_path, 16)
    source_id = uuid4()
    event_at = datetime(2024, 1, 5, 12, tzinfo=UTC)
    source = SourceState(
        channel="conversation_user",
        connection="fictional-test",
        profile_revision=1,
        source_event_id="original-message",
        event_at=event_at,
        event_time_basis="An exact supplied event timestamp",
        media_type="text/plain",
        capture="full",
        content=b"Today I reported an earlier observation",
    )
    apply_operation(
        case[0],
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=case[1],
            actor="owner",
            record_id=source_id,
            state=source,
        ),
        case[2],
    )
    saved = read_knowledge(case[0], source_id, case[2])
    ref = {"record_id": str(source_id), "revision": 1, "start": None, "end": None}
    _step(case, "attach_sources", source_refs=(ref,))
    packet = _start(case)
    basis = next(item for item in packet["sources"] if item["ref"]["record_id"] == str(source_id))
    assert datetime.fromisoformat(basis["state"]["received_at"]) == saved.received_at
    assert datetime.fromisoformat(basis["state"]["event_at"].replace("Z", "+00:00")) == event_at
    assert saved.received_at != event_at
    assert basis["state"]["channel"] == source.channel
    assert basis["state"]["connection"] == source.connection
    assert basis["state"]["source_event_id"] == source.source_event_id
    assert read_knowledge(case[0], source_id, case[2]) == saved


@pytest.mark.parametrize("repeat", [True, False])
@pytest.mark.parametrize("schema", (15, 16))
def test_repair_boundaries_survive_reopen_and_receipt_replay(
    tmp_path: Path, repeat: bool, schema: int
) -> None:
    """Risk: restart/replay silently resets limits or retries the same bad response forever."""
    case = _recovery_case(tmp_path, schema)
    _start(case)
    _raw(case, "{broken")
    _start(case)
    _raw(case, "{broken" if repeat else '{"different":1}')
    if not repeat:
        _start(case)
        _raw(case, '{"another":1}')
    current = read_activity_setup(case[0], case[3], case[2])
    assert current.state.phase == "needs_attention"
    reopened = authorize_local(case[0], actor="owner", source_ref="reopened")
    assert read_activity_setup(case[0], case[3], reopened) == current
    with pytest.raises(FoundationError, match="setup_result_exhausted"):
        _step(case, "resume")
    request = ActivitySetupRequest(
        operation_id=uuid4(),
        space_id=case[1],
        actor="owner",
        setup_id=case[3],
        activity_id=case[4],
        expected_revision=current.revision,
        action="retry",
    )
    receipt = apply_operation(case[0], request, reopened)
    assert apply_operation(case[0], request, reopened) == receipt
    _start(case)
    assert read_activity_setup(case[0], case[3], reopened).state.stages[-1].repair_number == 0


@pytest.mark.parametrize("schema", (15, 16))
def test_bad_fifth_review_cannot_start_sixth(tmp_path: Path, schema: int) -> None:
    """Risk: format repair bypasses the five started full-review limit."""
    case = _recovery_case(tmp_path, schema)
    _start(case)
    _raw(case, _proposal().model_dump_json())
    for _ in range(4):
        _start(case, "review")
        _raw(case, _report(case, blocking=True))
        _start(case, "correction")
        _raw(case, _proposal().model_dump_json())
    _start(case, "review")
    _raw(case, "{broken")
    current = read_activity_setup(case[0], case[3], case[2]).state
    assert current.reviews_started == 5 and current.phase == "needs_attention"
    with pytest.raises(FoundationError):
        _start(case, "review")
    assert read_activity_setup(case[0], case[3], case[2]).state == current


@pytest.mark.parametrize("schema", (15, 16))
def test_rejected_original_is_backed_up_and_sanitized_with_basis(
    tmp_path: Path, schema: int
) -> None:
    """Risk: rejected content/diagnostics survive deletion or disappear from recovery."""
    case = _recovery_case(tmp_path, schema)
    _start(case)
    ref = _raw(case, "{broken private fictional value")
    state = read_activity_setup(case[0], case[3], case[2]).state
    backup = create_backup(case[0], uuid4(), case[2])
    destination = tmp_path / "restored"
    destination.mkdir()
    recovery = authorize_recovery(actor="owner", source_ref="recovery")
    restore_backup(backup.package, destination, recovery)
    apply_operation(
        destination,
        RecoverRequest(
            operation_id=uuid4(),
            space_id=case[1],
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        recovery,
    )
    restored = authorize_local(destination, actor="owner", source_ref="restored")
    assert read_activity_setup(destination, case[3], restored).state == state
    source = state.sources[0]
    apply_operation(
        case[0],
        DeleteKnowledgeRequest(
            operation_id=uuid4(),
            space_id=case[1],
            actor="owner",
            record_id=source.record_id,
            expected_revision=source.revision,
        ),
        case[2],
    )
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_artifact(case[0], ref.artifact_id, case[2])
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_activity_setup(case[0], case[3], case[2])
    assert complete_deletions(case[0], case[2]).live_store_sanitized


def test_protocol_defaults_preserve_legacy_stage_bytes(tmp_path: Path) -> None:
    """Risk: adding protocol metadata changes old serialized pins/checksums."""
    case = _structured_case(tmp_path)
    _start(case)
    stage = read_setup_stage(
        case[0], read_activity_setup(case[0], case[3], case[2]).state.stages[-1].work_id, case[2]
    )
    assert stage is not None
    assert stage.result_protocol == "setup_json"
    legacy = stage.model_dump(exclude={"result_protocol"})
    old = type(stage).model_validate(legacy)
    assert old.result_protocol is None
    assert old.model_dump() == legacy


def test_empty_attempt_result_reaches_saved_json_rejection(tmp_path: Path) -> None:
    """Risk: the publication request rejects empty bytes before durable diagnostics."""
    case = _structured_case(tmp_path)
    _start(case)
    root, space, owner, setup, *_ = case
    stage = read_activity_setup(root, setup, owner).state.stages[-1]
    resource = uuid4()
    working = tmp_path / "assigned"
    working.mkdir()
    apply_operation(
        root,
        CreateResourceRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            work_id=stage.work_id,
            resource_id=resource,
            state=ResourceState(label="Fictional stage", root=working),
        ),
        owner,
    )
    attempt, session = start(root, space, stage.work_id, resource, owner)
    invocation_id, _ = invocation(root, space, stage.work_id, attempt, session, owner, 1)
    common: InvocationFields = dict(
        invocation_id=invocation_id, attempt_id=attempt, work_id=stage.work_id, session_id=session
    )
    for request in (
        AdmitInvocationRequest(operation_id=uuid4(), space_id=space, actor=owner.actor, **common),
        SendInvocationRequest(operation_id=uuid4(), space_id=space, actor=owner.actor, **common),
        FinishInvocationRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            outcome="answered",
            usage_units=0,
            **common,
        ),
    ):
        apply_operation(
            root,
            request,
            owner,
        )
    receipt = apply_operation(
        root,
        PublishAttemptOutputRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            attempt_id=attempt,
            work_id=stage.work_id,
            session_id=session,
            slot="report",
            media_type="text/plain",
            content=b"",
        ),
        owner,
    )
    result = read_work(root, stage.work_id, owner).state.linked_outputs[0].artifact
    assert read_artifact(root, result.artifact_id, owner).content == b""
    _step(case, "complete_stage", output=result)
    rejection = read_activity_setup(root, setup, owner).state.stages[-1].rejection
    assert rejection is not None and rejection.artifact == result
    assert rejection.issues[0].code == "json_invalid" and receipt.kind == "publish_attempt_output"


def test_out_of_scope_result_is_not_sent_for_model_repair(tmp_path: Path) -> None:
    """Risk: a scope refusal becomes authority to retry an unauthorized effect."""
    case = _structured_case(tmp_path)
    _start(case)
    invalid = json.loads(_proposal().model_dump_json())
    invalid["formats"][0]["definition"]["scope_activity_id"] = str(uuid4())
    with pytest.raises(FoundationError, match="out_of_scope"):
        _raw(case, json.dumps(invalid))
    current = read_activity_setup(case[0], case[3], case[2]).state
    assert current.draft is None and current.stages[-1].rejection is None


def test_corrupt_saved_manifest_is_not_a_bad_model_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Risk: an internal manifest failure is hidden by automatic model corrections."""
    from zaratustra.foundation import activity_setup

    case = _structured_case(tmp_path)
    _start(case)
    _raw(case, _proposal().model_dump_json())
    _start(case, "review")
    output = _raw(case, _report(case), complete=False)
    before = read_activity_setup(case[0], case[3], case[2])
    original = activity_setup._artifact

    def corrupt(connection: Any, ref: ArtifactRef, actor: str, epoch: int, **kwargs: Any) -> bytes:
        return (
            b"{broken"
            if ref == before.state.manifest
            else original(connection, ref, actor, epoch, **kwargs)
        )

    monkeypatch.setattr(activity_setup, "_artifact", corrupt)
    with pytest.raises(FoundationError, match="corrupt_space"):
        _step(case, "complete_stage", output=output)
    assert read_activity_setup(case[0], case[3], case[2]) == before
