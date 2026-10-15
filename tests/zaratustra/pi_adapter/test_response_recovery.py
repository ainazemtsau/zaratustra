"""Interrupted assigned answers resume through exact Core output recovery, not replay."""

import io
import json
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID, uuid4, uuid5

import pytest

from tests.zaratustra.foundation.test_activity_setup import _step
from tests.zaratustra.foundation.test_activity_setup_recovery import _recovery_case, _start
from tests.zaratustra.foundation.test_activity_structures import (
    _activate,
    _proposal,
    _structured_case,
)
from tests.zaratustra.foundation.test_child_execution import _claim, _invocation, _stop
from tests.zaratustra.foundation.test_workflows import _op, _setup
from tests.zaratustra.pi_adapter.test_child_assigned import _config
from tests.zaratustra.workspace.test_workspace import configuration
from zaratustra.foundation import (
    AdmitInvocationRequest,
    AssignAttemptRequest,
    ContextState,
    ConversationTerminalObservation,
    CreateKnowledgeRequest,
    CreateResourceRequest,
    CreateWorkRequest,
    DataEntryState,
    FinishInvocationRequest,
    FoundationError,
    KnowledgeRef,
    OutputContract,
    PrepareInvocationRequest,
    PublishAttemptOutputRequest,
    RecordContextDeliveryRequest,
    ResourceState,
    ReviseResourceRequest,
    SendInvocationRequest,
    SourceState,
    StartAttemptRequest,
    StopAttemptRequest,
    WorkflowModel,
    WorkflowNode,
    WorkflowRequest,
    WorkState,
    authorize_local,
    create_entry,
    read_activity_setup,
    read_artifact,
    read_execution,
    read_knowledge,
    read_ordinary_final_proof,
    read_space,
    read_work,
    read_workflow_run,
    start_procedure,
)
from zaratustra.pi_adapter import Bridge
from zaratustra.pi_adapter import workflows as workflow_host
from zaratustra.pi_adapter.__main__ import _prepare_space
from zaratustra.pi_adapter.activity_setup import SetupCoordinator
from zaratustra.pi_adapter.assigned import EXECUTOR_VERSION
from zaratustra.pi_adapter.procedures import ProcedureCoordinator, procedure_view
from zaratustra.pi_adapter.response_recovery import recover_response
from zaratustra.pi_adapter.workflows import WorkflowCoordinator, workflow_view
from zaratustra.workspace import select_work_project

Target = Literal["setup", "workflow", "procedure"]


@pytest.mark.parametrize("ambiguous", (False, True))
def test_legacy_setup_refuses_unselected_resources_without_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ambiguous: bool
) -> None:
    """A revoked history or two active choices cannot silently supply an Attempt."""
    case, identifier, work, bridge, controller = _target(tmp_path, "setup")
    root, space, owner, *_ = case
    _step(
        case,
        "bind_model",
        stage_model=WorkflowModel(
            provider=controller.config.provider_id,
            model_id=controller.config.model_id,
            profile=controller.config.provider_profile,
            reasoning="off",
        ),
    )
    _op(
        root,
        space,
        owner,
        CreateResourceRequest,
        resource_id=UUID(int=1),
        work_id=work,
        state=ResourceState(label="Saved choice", root=root),
    )
    if ambiguous:
        _op(
            root,
            space,
            owner,
            CreateResourceRequest,
            resource_id=UUID(int=2),
            work_id=work,
            state=ResourceState(label="Other choice", root=root),
        )
    else:
        _op(
            root,
            space,
            owner,
            ReviseResourceRequest,
            resource_id=UUID(int=1),
            work_id=work,
            expected_revision=1,
            state=ResourceState(label="Saved choice", root=root, status="revoked"),
        )
    before, stable = read_execution(root, work, owner), read_space(root)
    monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: pytest.fail("Unexpected executor"))
    with pytest.raises(FoundationError, match="Setup needs one active resource"):
        controller._execute_stage(identifier, work)
    assert read_execution(root, work, owner) == before
    assert read_space(root) == stable


@pytest.mark.parametrize("revoked_history", (False, True))
def test_legacy_setup_binds_actual_resource_identity_and_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, revoked_history: bool
) -> None:
    """An existing resource need not have the setup factory's deterministic ID."""
    case, identifier, work, bridge, controller = _target(tmp_path, "setup")
    root, space, owner, *_ = case
    if revoked_history:
        _op(
            root,
            space,
            owner,
            CreateResourceRequest,
            resource_id=UUID(int=1),
            work_id=work,
            state=ResourceState(label="Historical resource", root=root),
        )
        _op(
            root,
            space,
            owner,
            ReviseResourceRequest,
            resource_id=UUID(int=1),
            work_id=work,
            expected_revision=1,
            state=ResourceState(label="Historical resource", root=root, status="revoked"),
        )
    selected = UUID(int=2)
    _op(
        root,
        space,
        owner,
        CreateResourceRequest,
        resource_id=selected,
        work_id=work,
        state=ResourceState(label="Explicitly selected resource", root=root),
    )
    before = read_execution(root, work, owner)

    class ExecutorBoundaryReached(RuntimeError):
        pass

    def observe_spawn(*args: Any, **kwargs: Any) -> None:
        raise ExecutorBoundaryReached("Resource binding reached the native executor boundary")

    monkeypatch.setattr("subprocess.Popen", observe_spawn)
    with pytest.raises(ExecutorBoundaryReached):
        controller._execute_stage(identifier, work)
    after = read_execution(root, work, owner)
    assert after.resources == before.resources
    assert len(after.attempts) == len(after.assignments) == 1
    assert after.attempts[0].resource_id == selected
    assert after.attempts[0].resource_revision == 1
    assert after.work == before.work and after.work.state.acceptance is None
    assert not after.invocations


@pytest.mark.parametrize("project", ("personal", "code"))
@pytest.mark.parametrize("preselected", (False, True))
def test_configured_procedure_assigns_the_committed_project_resource_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: str, preselected: bool
) -> None:
    """Real launch selection must not be followed by a stale-snapshot second resource."""
    case = _structured_case(tmp_path)
    root, space, owner, _, activity, *_ = case
    proposal = _proposal()
    if project != "personal":
        procedure = proposal.procedures[0].model_copy(
            update={"resource": "project", "project": project}
        )
        proposal = proposal.model_copy(update={"procedures": (procedure,)})
    _activate(case, proposal)
    _prepare_space(root, owner.actor, create=False, upgrade_existing=True)
    launch = tmp_path / "launch"
    launch.mkdir()
    config_path, launch_config = configuration(launch, root, space)
    run = start_procedure(root, owner, activity, "observe", "configured-first-action")
    identifier, work = UUID(str(run["run_id"])), UUID(str(run["work_id"]))
    bridge = Bridge(root, owner, launch_config.workspace, workspace_config=config_path)
    assigned = replace(
        _config(root, launch_config.workspace, tmp_path / "executor-runtime"),
        workspace_config=config_path,
    )
    controller = ProcedureCoordinator(bridge, assigned)
    if preselected:
        select_work_project(launch_config, owner, work, project)
    before = read_execution(root, work, owner)
    entered, release = threading.Event(), threading.Event()

    def observe_dispatch(attempt: UUID) -> None:
        assert read_execution(root, work, owner).attempts[-1].attempt_id == attempt
        entered.set()
        release.wait(10)

    # Stop at the native executor boundary; resource/assignment effects are real Core calls.
    monkeypatch.setattr(controller, "_run", observe_dispatch)
    model = {"provider": "synthetic", "id": "synthetic", "thinking": "off"}
    try:
        result = controller.start(identifier, model)
        assert result["execution"] == "assigned" and entered.wait(5)
        current = read_execution(root, work, owner)
        assert len(current.resources) == 1
        resource = current.resources[0]
        assert resource.state.status == "active"
        assert resource.state.root == launch_config.project_root(project)
        assert controller.config.workspace == resource.state.root
        assert current.attempts[0].resource_id == resource.resource_id
        assert current.attempts[0].resource_revision == resource.revision
        assert len(current.attempts) == len(current.assignments) == 1
        if preselected:
            assert current.resources == before.resources
        assert controller.start(identifier, model)["execution"] == "running"
        assert read_execution(root, work, owner) == current
        assert current.work == before.work and current.work.state.acceptance is None
        assert not current.invocations
    finally:
        release.set()
        if controller.thread is not None:
            controller.thread.join(timeout=5)


def test_answered_ordinary_assessment_requires_owner_interruption_before_procedure_handoff(
    tmp_path: Path,
) -> None:
    """A published proposal without final proof keeps its resource until an addressed stop."""
    case = _structured_case(tmp_path)
    root, space, owner, _, activity, *_ = case
    _activate(case)
    _prepare_space(root, owner.actor, create=False, upgrade_existing=True)
    launch = tmp_path / "launch"
    launch.mkdir()
    _, config = configuration(launch, root, space)
    assessment, attempt, session = uuid4(), uuid4(), uuid4()
    _op(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=assessment,
        state=WorkState(
            activity_id=activity,
            goal="Retain the fictional ordinary assessment before beginning its procedure",
            expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
        ),
    )
    select_work_project(config, owner, assessment, "personal")
    resource = read_execution(root, assessment, owner).resources[0]
    assert resource.state.mode == "exclusive"
    _op(
        root,
        space,
        owner,
        StartAttemptRequest,
        work_id=assessment,
        attempt_id=attempt,
        session_id=session,
        expected_work_revision=1,
        resource_id=resource.resource_id,
        expected_resource_revision=resource.revision,
    )
    invocation = _invocation(root, space, owner, assessment, attempt, session)
    _op(
        root,
        space,
        owner,
        PublishAttemptOutputRequest,
        work_id=assessment,
        attempt_id=attempt,
        session_id=session,
        slot="report",
        media_type="text/plain",
        content=b"Fictional proposed assessment; owner acceptance remains separate",
    )
    answered = read_execution(root, assessment, owner)
    output = answered.work.state.linked_outputs[0].artifact
    original = read_artifact(root, output.artifact_id, owner, revision=output.revision)
    assert answered.attempts[0].status == "active" and not answered.assignments
    assert answered.invocations[0].invocation_id == invocation
    assert answered.invocations[0].status == "answered" and answered.committed_units == 3
    assert answered.held_units == 0
    assert answered.work.state.status == "proposed" and answered.work.state.acceptance is None
    reopened = authorize_local(root, actor=owner.actor, source_ref="fictional-reopened-session")
    assert read_ordinary_final_proof(root, assessment, reopened, attempt_id=attempt) is None
    assert read_execution(root, assessment, reopened) == answered

    run = start_procedure(root, reopened, activity, "observe", "ordinary-assessment-handoff")
    procedure = UUID(str(run["work_id"]))
    select_work_project(config, reopened, procedure, "personal")
    pending = read_execution(root, procedure, reopened)
    selected = pending.resources[0]
    assert selected.state.root == resource.state.root and selected.state.mode == "exclusive"
    successor, successor_session = uuid4(), uuid4()
    fields = dict(
        work_id=procedure,
        attempt_id=successor,
        session_id=successor_session,
        expected_work_revision=pending.work.revision,
        resource_id=selected.resource_id,
        expected_resource_revision=selected.revision,
        executor_version=EXECUTOR_VERSION,
    )
    before_refusal = read_space(root)
    with pytest.raises(FoundationError) as refusal:
        _op(root, space, reopened, AssignAttemptRequest, **fields)
    assert refusal.value.code == "resource_busy"
    assert read_space(root) == before_refusal
    assert read_execution(root, assessment, reopened) == answered
    assert read_execution(root, procedure, reopened) == pending

    _op(
        root,
        space,
        reopened,
        StopAttemptRequest,
        work_id=assessment,
        attempt_id=attempt,
        session_id=session,
        outcome="interrupted",
    )
    interrupted = read_execution(root, assessment, reopened)
    assert interrupted.attempts[0].status == "interrupted"
    assert interrupted.work == answered.work and interrupted.resources == answered.resources
    assert interrupted.invocations == answered.invocations
    assert interrupted.committed_units == answered.committed_units and interrupted.held_units == 0
    assert read_artifact(root, output.artifact_id, reopened, revision=output.revision) == original
    _op(root, space, reopened, AssignAttemptRequest, **fields)
    assigned = read_execution(root, procedure, reopened)
    assert len(assigned.attempts) == len(assigned.assignments) == 1
    assert assigned.attempts[0].attempt_id == successor
    assert assigned.attempts[0].status == "active" and assigned.assignments[0].status == "assigned"
    assert assigned.work == pending.work and assigned.work.state.acceptance is None
    assert not assigned.invocations
    assert read_execution(root, assessment, reopened) == interrupted


def _target(tmp_path: Path, target: Target) -> tuple[Any, UUID, UUID, Bridge, Any]:
    case: Any
    if target == "workflow":
        case = _setup(
            tmp_path,
            (WorkflowNode(key="summary", kind="model", instruction="Summarize observations"),),
        )
        root, _, owner, _, _, identifier = case
        _prepare_space(root, owner.actor, create=False, upgrade_existing=True)
        current = read_workflow_run(root, identifier, owner)
        _op(
            root,
            case[1],
            owner,
            WorkflowRequest,
            action="bind_node",
            root_work_id=identifier,
            expected_revision=current.revision,
            node_key="summary",
            model=WorkflowModel(
                provider="synthetic",
                model_id="synthetic",
                profile="local-completions",
                reasoning="off",
            ),
        )
        work = read_workflow_run(root, identifier, owner).nodes[0].work_id
    elif target == "setup":
        case = _recovery_case(tmp_path, 15)
        root, _, owner, identifier, *_ = case
        _prepare_space(root, owner.actor, create=False, upgrade_existing=True)
        _start(case)
        state = read_activity_setup(root, identifier, owner).state
        assert state.root_work_id is None
        work = state.stages[-1].work_id
    else:
        case = _structured_case(tmp_path)
        root, _, owner, _, activity, *_ = case
        _activate(case)
        _prepare_space(root, owner.actor, create=False, upgrade_existing=True)
        run = start_procedure(root, owner, activity, "observe", "fictional-recovery")
        identifier, work = UUID(str(run["run_id"])), UUID(str(run["work_id"]))
    bridge = Bridge(root, owner, root)
    config = _config(root, root, tmp_path / "runtime")
    controller = (
        SetupCoordinator(bridge, config)
        if target == "setup"
        else WorkflowCoordinator(bridge, config)
        if target == "workflow"
        else ProcedureCoordinator(bridge, config)
    )
    return case, identifier, work, bridge, controller


def test_procedure_executor_failure_retains_scoped_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case, _, work, bridge, controller = _target(tmp_path, "procedure")
    root, _, owner, *_ = case
    attempt, _ = _assign(case, work)
    controller.active = work
    before = read_execution(root, work, owner)

    class FailedExecutor:
        stdin = io.BytesIO()
        stderr = io.BytesIO(b"Fictional executor transport failed")
        returncode = 1

        def poll(self) -> int:
            return self.returncode

    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: FailedExecutor())
    controller._run(attempt)
    original = read_knowledge(root, uuid5(attempt, "procedure-executor-diagnostic"), owner)
    assert isinstance(original.state, SourceState)
    assert original.state.content == b"Fictional executor transport failed"
    assert original.state.scope_work_id == work
    assert original.state.memory is not None
    assert original.state.memory.activity_id == before.work.state.activity_id
    assert read_execution(root, work, owner) == before
    assert bridge.authority == owner


def _assign(case: Any, work: UUID) -> tuple[UUID, UUID]:
    root, space, owner, *_ = case
    resource, attempt, session = uuid4(), uuid4(), uuid4()
    _op(
        root,
        space,
        owner,
        CreateResourceRequest,
        resource_id=resource,
        work_id=work,
        state=ResourceState(label="Fictional response resource", root=root, mode="shared"),
    )
    _op(
        root,
        space,
        owner,
        AssignAttemptRequest,
        work_id=work,
        attempt_id=attempt,
        expected_work_revision=read_work(root, work, owner).revision,
        resource_id=resource,
        expected_resource_revision=1,
        session_id=session,
        executor_version=EXECUTOR_VERSION,
    )
    _claim(root, space, owner, work, attempt, session)
    return attempt, session


def _capture(
    case: Any,
    work: UUID,
    attempt: UUID,
    session: UUID,
    raw: str,
    protocol: Literal["setup_json", "workflow_json", "zara_envelope"],
    *,
    proof: bool = True,
    outcome: str = "answered",
) -> tuple[KnowledgeRef, UUID]:
    root, space, owner, *_ = case
    current = read_work(root, work, owner)
    manifest = KnowledgeRef(record_id=uuid4(), revision=1)
    _op(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=manifest.record_id,
        state=ContextState(
            purpose="Fictional assigned recovery",
            work_id=work,
            attempt_id=attempt,
            session_id=session,
            mandatory=(KnowledgeRef(record_id=work, revision=current.revision),)
            + tuple(
                KnowledgeRef(record_id=item.artifact_id, revision=item.revision)
                for item in current.state.inputs
            ),
        ),
    )
    invocation = uuid4()
    common = dict(work_id=work, attempt_id=attempt, session_id=session, invocation_id=invocation)
    _op(
        root,
        space,
        owner,
        PrepareInvocationRequest,
        purpose="content",
        provider="synthetic",
        model="synthetic",
        transport="http-sse",
        request_sha256="A" * 64,
        request_bytes=10,
        reserve_units=5,
        **common,
    )
    _op(
        root,
        space,
        owner,
        RecordContextDeliveryRequest,
        invocation_id=invocation,
        manifest=manifest,
        stage="prepared",
    )
    _op(root, space, owner, AdmitInvocationRequest, **common)
    _op(root, space, owner, SendInvocationRequest, **common)
    _op(
        root,
        space,
        owner,
        RecordContextDeliveryRequest,
        invocation_id=invocation,
        manifest=manifest,
        stage="sent",
        request_sha256="A" * 64,
        request_bytes=10,
    )
    if outcome != "sent":
        _op(
            root,
            space,
            owner,
            FinishInvocationRequest,
            outcome=outcome,
            usage_units=3 if outcome == "answered" else None,
            **common,
        )
        _op(
            root,
            space,
            owner,
            RecordContextDeliveryRequest,
            invocation_id=invocation,
            manifest=manifest,
            stage=outcome,
            usage_units=3 if outcome == "answered" else None,
        )
    source = KnowledgeRef(record_id=uuid4(), revision=1)
    entry = str(uuid4())
    _op(
        root,
        space,
        owner,
        CreateKnowledgeRequest,
        record_id=source.record_id,
        state=SourceState(
            channel="conversation_assistant",
            connection="ordinary-pi",
            profile_revision=1,
            sender="pi-assistant",
            conversation_id=str(session),
            source_event_id=f"{session}:{entry}",
            scope_activity_id=current.state.activity_id,
            scope_work_id=work,
            media_type="text/plain",
            capture="full",
            content=raw.encode("utf-8"),
            derived_from=(manifest,),
            conversation_final=bool(raw.strip()),
            conversation_terminal=ConversationTerminalObservation(
                invocation_id=invocation,
                manifest=manifest,
                assistant_entry_id=entry,
                native_outcome="completed",
                stop_reason="stop",
                result_protocol=protocol,
            )
            if proof
            else None,
        ),
    )
    if outcome != "sent":
        _stop(root, space, owner, work, attempt, session)
    return source, invocation


def _dispatch(target: Target, identifier: UUID, work: UUID, controller: Any) -> Any:
    if target == "setup":
        return controller._execute_stage(identifier, work)
    if target == "workflow":
        return controller._dispatch_work(identifier, work, controller.config)
    return controller._start(identifier, {"provider": "synthetic", "id": "synthetic"})


@pytest.mark.parametrize("raw_kind", ("valid", "malformed", "whitespace"))
def test_setup_retained_raw_reply_uses_normal_validation_without_second_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw_kind: str
) -> None:
    case, identifier, work, bridge, controller = _target(tmp_path, "setup")
    attempt, session = _assign(case, work)
    raw = {
        "valid": _proposal().model_dump_json(),
        "malformed": '{"broken":',
        "whitespace": " \t\r\n",
    }[raw_kind]
    malformed = raw_kind != "valid"
    source, _ = _capture(case, work, attempt, session, raw, "setup_json")
    _step(case, "pause")
    _step(case, "resume")
    before = read_execution(bridge.path, work, bridge.authority)
    monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: pytest.fail("Unexpected model launch"))
    _dispatch("setup", identifier, work, controller)
    recovered = read_execution(bridge.path, work, bridge.authority)
    assert len(recovered.attempts) == len(before.attempts) == 1
    assert recovered.attempts == before.attempts and recovered.assignments == before.assignments
    assert recovered.invocations == before.invocations
    artifact = recovered.work.state.linked_outputs[0].artifact
    assert (
        read_artifact(bridge.path, artifact.artifact_id, bridge.authority).content == raw.encode()
    )
    _step(case, "complete_stage", output=artifact)
    stage = read_activity_setup(bridge.path, identifier, bridge.authority).state.stages[-1]
    assert (stage.rejection is not None) is malformed
    if malformed:
        assert stage.output is None and stage.retired
        assert stage.rejection is not None and stage.rejection.artifact == artifact
    else:
        assert stage.output == artifact
    original = read_knowledge(bridge.path, source.record_id, bridge.authority).state
    assert isinstance(original, SourceState) and original.content == raw.encode()
    assert recovered.work.state.acceptance is None
    stable = read_space(bridge.path)
    assert recover_response(bridge.path, work, bridge.authority).outcome == "applied"
    assert read_space(bridge.path) == stable


def test_workflow_recovery_has_internal_validation_without_acceptance_or_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case, identifier, work, bridge, controller = _target(tmp_path, "workflow")
    attempt, session = _assign(case, work)
    raw = '{"outcome":"result","values":{"observations":"1.25"}}'
    source, _ = _capture(case, work, attempt, session, raw, "workflow_json")
    before = read_execution(bridge.path, work, bridge.authority)
    stable = read_space(bridge.path)
    observed = workflow_view(bridge.path, identifier, bridge.authority)
    response = observed["nodes"][0]["response"]
    assert response["outcome"] == "recoverable"
    assert response["assistant_source"]["record_id"] == str(source.record_id)
    assert read_space(bridge.path) == stable
    monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: pytest.fail("Unexpected model launch"))
    existing = read_workflow_run(bridge.path, identifier, bridge.authority).nodes[0]
    assert existing.model is not None
    controller.config = replace(controller.config, provider_id="unavailable")
    assert controller._execute_node(identifier, existing) is True
    recovered = read_execution(bridge.path, work, bridge.authority)
    output = recovered.work.state.linked_outputs[0].artifact
    controller._step(identifier, "validate_output", node_key="summary", iteration=1, output=output)
    node = read_workflow_run(bridge.path, identifier, bridge.authority).nodes[0]
    assert node.output == output and node.validation_id is not None
    assert recovered.attempts == before.attempts and recovered.invocations == before.invocations
    assert recovered.work.state.acceptance is None
    original = read_knowledge(bridge.path, source.record_id, bridge.authority).state
    assert isinstance(original, SourceState) and original.content == raw.encode()


@pytest.mark.parametrize("live_executor", (False, True))
def test_running_workflow_awaits_exact_existing_executor_or_stops_without_relaunch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, live_executor: bool
) -> None:
    case, identifier, work, bridge, controller = _target(tmp_path, "workflow")
    attempt, session = _assign(case, work)
    raw = '{"outcome":"result","values":{"observations":"1.25"}}'
    source, invocation = _capture(
        case, work, attempt, session, raw, "workflow_json", outcome="sent"
    )
    before = read_execution(bridge.path, work, bridge.authority)
    stable = read_space(bridge.path)
    response = workflow_view(bridge.path, identifier, bridge.authority)["nodes"][0]["response"]
    assert response["outcome"] == "running"
    assert read_space(bridge.path) == stable
    monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: pytest.fail("Unexpected model launch"))

    class Executor:
        returncode: int | None = None
        polled = False

        def poll(self) -> int | None:
            if not self.polled:
                self.polled = True
                return None
            if self.returncode is None:
                current = read_knowledge(bridge.path, source.record_id, bridge.authority).state
                assert (
                    isinstance(current, SourceState) and current.conversation_terminal is not None
                )
                _op(
                    bridge.path,
                    case[1],
                    bridge.authority,
                    FinishInvocationRequest,
                    work_id=work,
                    attempt_id=attempt,
                    session_id=session,
                    invocation_id=invocation,
                    outcome="answered",
                    usage_units=3,
                )
                _op(
                    bridge.path,
                    case[1],
                    bridge.authority,
                    RecordContextDeliveryRequest,
                    invocation_id=invocation,
                    manifest=current.conversation_terminal.manifest,
                    stage="answered",
                    usage_units=3,
                )
                _stop(bridge.path, case[1], bridge.authority, work, attempt, session)
                self.returncode = 1
            return self.returncode

    if not live_executor:
        with pytest.raises(FoundationError, match="response_execution_unavailable"):
            _dispatch("workflow", identifier, work, controller)
        assert read_execution(bridge.path, work, bridge.authority) == before
        return
    reader = threading.Thread(target=lambda: None)
    reader.start()
    reader.join(timeout=1)
    controller.processes[work] = workflow_host._Executor(
        cast(Any, Executor()), reader, bytearray(), attempt
    )
    assert _dispatch("workflow", identifier, work, controller) is True
    after = read_execution(bridge.path, work, bridge.authority)
    assert len(after.attempts) == len(before.attempts) == 1
    assert len(after.invocations) == len(before.invocations) == 1
    assert after.invocations[0].status == "answered"
    assert after.attempts[0].status == "interrupted"
    assert after.work.state.linked_outputs and after.work.state.acceptance is None
    assert not controller.processes


@pytest.mark.parametrize("target", ("setup", "workflow", "procedure"))
@pytest.mark.parametrize("outcome", ("answered", "unknown"))
def test_missing_proof_or_unknown_send_never_creates_another_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: Target, outcome: str
) -> None:
    case, identifier, work, bridge, controller = _target(tmp_path, target)
    attempt, session = _assign(case, work)
    protocol: Literal["setup_json", "workflow_json", "zara_envelope"] = (
        "setup_json"
        if target == "setup"
        else "workflow_json"
        if target == "workflow"
        else "zara_envelope"
    )
    source, _ = _capture(case, work, attempt, session, "{}", protocol, proof=False, outcome=outcome)
    before = read_execution(bridge.path, work, bridge.authority)
    stable = read_space(bridge.path)
    if target == "workflow":
        response = workflow_view(bridge.path, identifier, bridge.authority)["nodes"][0]["response"]
        assert response["outcome"] == ("attention" if outcome == "answered" else "unknown")
        assert response["diagnostics"]
    elif target == "procedure":
        response = procedure_view(bridge.path, bridge.authority, identifier)["response"]
        assert response["outcome"] == ("attention" if outcome == "answered" else "unknown")
        assert response["diagnostics"]
    assert read_space(bridge.path) == stable
    monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: pytest.fail("Unexpected model launch"))
    with pytest.raises(FoundationError):
        _dispatch(target, identifier, work, controller)
    assert read_execution(bridge.path, work, bridge.authority) == before
    original = read_knowledge(bridge.path, source.record_id, bridge.authority).state
    assert isinstance(original, SourceState) and original.content == b"{}"
    assert not before.work.state.linked_outputs and before.work.state.acceptance is None


@pytest.mark.parametrize("wrong_snapshot", (False, True))
def test_procedure_recovery_checks_actual_entries_and_exact_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wrong_snapshot: bool
) -> None:
    case, identifier, work, bridge, controller = _target(tmp_path, "procedure")
    root, _, owner, _, activity, *_ = case
    attempt, session = _assign(case, work)
    status = start_procedure(root, owner, activity, "observe", "fictional-recovery")
    snapshot = KnowledgeRef.model_validate(status["snapshot"])
    contract = read_work(root, work, owner).state
    assert contract.expected_outputs[0].format_ref is not None
    entry = create_entry(
        root,
        owner,
        DataEntryState(
            scope_activity_id=activity,
            format_ref=contract.expected_outputs[0].format_ref,
            structure=contract.structure,
            role="event",
            work_id=work,
            attempt_id=attempt,
            session_id=session,
            selection=snapshot,
            values={"day": "2026-01-01", "value": "1.25"},
            bases=read_activity_setup(root, case[3], owner).state.sources,
        ),
    )
    inner = json.dumps(
        {
            "entries": [{"record_id": entry.result["record_id"], "revision": 1}],
            "basis_snapshot": {"record_id": str(uuid4()), "revision": 1}
            if wrong_snapshot
            else snapshot.model_dump(mode="json"),
            "complete": True,
            "result": "A retained observation",
        }
    )
    raw = json.dumps({"zara": "final", "text": inner})
    source, _ = _capture(case, work, attempt, session, raw, "zara_envelope")
    before = read_execution(root, work, owner)
    stable = read_space(root)
    observed = procedure_view(root, owner, identifier)
    assert observed["response"]["outcome"] == "recoverable"
    assert observed["response"]["assistant_source"]["record_id"] == str(source.record_id)
    assert read_space(root) == stable
    monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: pytest.fail("Unexpected model launch"))
    if wrong_snapshot:
        with pytest.raises(FoundationError, match="invalid_output"):
            _dispatch("procedure", identifier, work, controller)
        assert read_execution(root, work, owner) == before
    else:
        result = _dispatch("procedure", identifier, work, controller)
        assert result["execution"] == "result_available" and result["work"]["linked_outputs"]
        assert result["response"]["outcome"] == "applied"
        after = read_execution(root, work, owner)
        assert after.attempts == before.attempts and after.invocations == before.invocations
        output = after.work.state.linked_outputs[0].artifact
        assert read_artifact(root, output.artifact_id, owner).content == inner.encode()
        assert after.work.state.acceptance is None
    original = read_knowledge(root, source.record_id, owner).state
    assert isinstance(original, SourceState) and original.content == raw.encode()
