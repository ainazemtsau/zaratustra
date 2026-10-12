"""Workflow scheduler risks: native Method gates and reuse of retained results."""

import io
import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

import zaratustra.pi_adapter.workflows as workflow_host
from tests.zaratustra.foundation import test_activity_setup as setup_cases
from tests.zaratustra.foundation import test_workflows as core_cases
from tests.zaratustra.foundation.test_binding import _ready as original_case
from tests.zaratustra.foundation.test_execution import invocation
from zaratustra.foundation import (
    AcceptWorkRequest,
    AdmitInvocationRequest,
    ArtifactRef,
    AssignAttemptRequest,
    CreateArtifactRequest,
    CreateMethodVersionRequest,
    CreateResourceRequest,
    FinishInvocationRequest,
    FoundationError,
    LinkedOutput,
    LinkWorkOutputRequest,
    MethodDefinition,
    MethodRef,
    NamedInput,
    OutputContract,
    ParentOutputSlot,
    PlanChild,
    PlanCondition,
    RecordAttemptStopRequest,
    ResourceState,
    SendInvocationRequest,
    WorkflowDefinition,
    WorkflowModel,
    WorkflowNode,
    WorkflowRequest,
    WorkPlan,
    WorkState,
    method_checksum,
    read_execution,
    read_work,
    read_workflow,
    read_workflow_method_tasks,
    read_workflow_run,
)
from zaratustra.pi_adapter import Bridge
from zaratustra.pi_adapter.assigned import EXECUTOR_VERSION, AssignedConfig
from zaratustra.pi_adapter.workflows import WorkflowCoordinator, workflow_work_ids


def test_live_wait_lease_is_shared_reused_and_released_only_on_its_process_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A native wait cannot admit a third Pi; closing one controller preserves the other."""
    case, _, config = _method_case(tmp_path, monkeypatch)
    root, _, owner, *_ = case
    bridge = Bridge(root, owner, config.workspace)
    first = WorkflowCoordinator(bridge, config)
    other = WorkflowCoordinator(bridge, config)
    wait_work, side_work, third_work = uuid4(), uuid4(), uuid4()
    queued = threading.Event()
    third_started = threading.Event()
    spawned: list[subprocess.Popen[bytes]] = []
    acquired: list[str] = []
    original_acquire = first.executors.acquire

    def acquire(*args: Any, **kwargs: Any) -> bool:
        acquired.append(threading.current_thread().name)
        if threading.current_thread().name == "queued-third":
            queued.set()
        return bool(original_acquire(*args, **kwargs))

    monkeypatch.setattr(first.executors, "acquire", acquire)

    def dispatch(controller: WorkflowCoordinator, identifier: UUID, work: UUID, data: Any) -> bool:
        if work in controller.processes:
            return False
        process = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.stdin.buffer.readline()"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        spawned.append(process)
        reader = threading.Thread(target=lambda: None)
        reader.start()
        executor = workflow_host._Executor(process, reader, bytearray())
        with controller.pool.lock:
            controller.processes[work] = executor
            controller._watch_executor_exit(work, executor)
        if work == third_work:
            third_started.set()
        return False

    monkeypatch.setattr(WorkflowCoordinator, "_dispatch_work", dispatch)
    stopped: list[UUID] = []

    def stop(controller: WorkflowCoordinator, work: UUID) -> None:
        stopped.append(work)
        process = controller.processes[work].process
        assert process.stdin is not None
        process.stdin.write(b"exit\n")
        process.stdin.flush()

    monkeypatch.setattr(WorkflowCoordinator, "_stop_node", stop)
    pending = threading.Thread(
        target=other._execute_work, args=(uuid4(), third_work, config), name="queued-third"
    )
    try:
        assert first.pool is other.pool
        assert first._execute_work(uuid4(), wait_work, config) is False
        assert other._execute_work(uuid4(), side_work, config) is False
        assert len(first.pool.leases) == 2
        before = len(acquired)
        assert first._execute_work(uuid4(), wait_work, config) is False
        assert len(acquired) == before and len(spawned) == 2
        pending.start()
        assert queued.wait(5) and not third_started.is_set()
        # The actual wait process exits while another caller is blocked acquiring
        # a lease. Its asynchronous observer must unblock that caller directly.
        first.close()
        assert third_started.wait(5)
        pending.join(timeout=5)
        assert not pending.is_alive()
        assert stopped == [wait_work]
        assert other.processes[side_work].process.poll() is None
        assert other.processes[third_work].process.poll() is None
        assert len(other.pool.leases) == 2
        other.close()
        assert len(other.pool.leases) == 0
        assert set(stopped) == {wait_work, side_work, third_work}
    finally:
        for process in spawned:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)
        pending.join(timeout=5) if pending.ident is not None else None


def _method_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    provider_id: str = "fictional",
    model_id: str = "chosen-model",
    reasoning: str = "high",
) -> tuple[Any, Any, AssignedConfig]:
    method_id = uuid4()
    method = MethodDefinition(
        instruction="Review exact observations and synthesize an addressed report",
        named_inputs=(OutputContract(slot="context", media_type="application/json"),),
        named_outputs=(OutputContract(slot="report", media_type="text/plain"),),
        source_ref="fictional-reviewed-method",
    )
    reference = MethodRef(method_id=method_id, version=1, checksum=method_checksum(method))

    def with_method(path: Path) -> Any:
        case = original_case(path)
        root, space, owner, *_ = case
        core_cases._op(
            root,
            space,
            owner,
            CreateMethodVersionRequest,
            method_id=method_id,
            version=1,
            definition=method,
        )
        return case

    # Register through the existing schema-9 operation before the fixture's
    # explicit upgrade. The test exercises reuse of an existing exact Method.
    monkeypatch.setattr(setup_cases, "_ready", with_method)
    plan = WorkPlan(
        named_inputs=(
            NamedInput(slot="context", artifact=ArtifactRef(artifact_id=uuid4(), revision=1)),
        ),
        parent_outputs=(ParentOutputSlot(slot="report", media_type="text/plain"),),
        children=(
            PlanChild(
                role="analyse",
                work_id=uuid4(),
                state=WorkState(
                    activity_id=uuid4(),
                    goal="Analyse observations",
                    expected_outputs=(
                        OutputContract(slot="observations", media_type="text/plain"),
                    ),
                ),
            ),
        ),
        completion=PlanCondition(kind="work_succeeded", role="analyse"),
        rationale="One native role followed by parent synthesis",
        source_ref="fictional-plan",
    )
    case = core_cases._setup(
        tmp_path,
        (
            WorkflowNode(
                key="review",
                kind="model",
                instruction="Execute the reviewed Method",
                method=reference,
                plan=plan,
                input_slot="context",
            ),
        ),
    )
    root, space, owner, _, _, identifier = case
    core_cases._step(
        case,
        "bind_node",
        node_key="review",
        model=WorkflowModel(
            provider=provider_id,
            model_id=model_id,
            profile="local-completions",
            reasoning=reasoning,
        ),
    )
    node = read_workflow_run(root, identifier, owner).nodes[0]
    config = AssignedConfig(
        space=root,
        workspace=root,
        pi_cli=tmp_path / "unused.js",
        pi_runtime=tmp_path,
        node="node",
        provider_profile="local-completions",
        provider_base_url="http://127.0.0.1:1/v1",
        provider_id="fictional",
        model_id="startup-default",
        context_window=4096,
        max_tokens=512,
        reserve_units=10,
        limit_units=None,
    )
    return case, node, config


def test_method_roles_execute_before_own_attempt_and_keep_owner_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A native Method role is issued once; its proposal never becomes automatic acceptance."""
    case, node, config = _method_case(tmp_path, monkeypatch)
    root, space, owner, _, _, identifier = case
    bridge = Bridge(root, owner, root)
    session = uuid4()
    bridge.connect(session)
    coordinator = WorkflowCoordinator(bridge, config)
    dispatched: list[tuple[UUID, AssignedConfig]] = []

    def retain_role(_root: UUID, work_id: UUID, chosen: AssignedConfig) -> bool:
        dispatched.append((work_id, chosen))
        if work_id == node.work_id:
            # Stop at the actual parent dispatch boundary; publication is covered
            # by installed Pi and Core's parent producer proof tests.
            return False
        state = read_work(root, work_id, owner)
        artifact = uuid4()
        core_cases._op(
            root,
            space,
            owner,
            CreateArtifactRequest,
            artifact_id=artifact,
            media_type="text/plain",
            content=b"Observed fictional result",
        )
        core_cases._op(
            root,
            space,
            owner,
            LinkWorkOutputRequest,
            work_id=work_id,
            expected_revision=state.revision,
            output=LinkedOutput(
                slot="observations", artifact=ArtifactRef(artifact_id=artifact, revision=1)
            ),
        )
        return True

    monkeypatch.setattr(coordinator, "_execute_work", retain_role)
    assert coordinator._execute_node(identifier, node) is False
    tasks = read_workflow_method_tasks(root, node.work_id, owner)
    child = UUID(tasks["children"][0]["work_id"])
    assert tasks["children"][0]["issued"] and not tasks["parent_ready"]
    assert read_work(root, child, owner).state.acceptance is None
    assert read_workflow_run(root, identifier, owner).next_action == "owner_action"
    visible = bridge.workflow(
        session,
        {"mode": "method_tasks", "root_work_id": str(identifier), "work_id": str(node.work_id)},
    )
    assert visible["children"][0]["outputs"] and visible["owner_waiting"]
    assert child in workflow_work_ids(root, identifier, owner)
    assert len(dispatched) == 1 and dispatched[0][0] == child
    assert dispatched[0][1].model_id == "chosen-model" and dispatched[0][1].thinking == "high"
    assert dispatched[0][1].result_protocol is None
    assert coordinator._execute_node(identifier, node) is False and len(dispatched) == 1
    core_cases._op(
        root,
        space,
        owner,
        AcceptWorkRequest,
        work_id=child,
        expected_revision=read_work(root, child, owner).revision,
        basis="Owner checked this result",
    )
    assert coordinator._execute_node(identifier, node) is False
    assert dispatched[-1][0] == node.work_id and len(dispatched) == 2
    assert dispatched[-1][1].result_protocol == "workflow_json"
    assert read_work(root, node.work_id, owner).state.acceptance is None


def test_owner_wait_in_one_method_branch_does_not_stop_other_ready_nodes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """More than one batch advances while a proposed native role waits for its owner."""
    case, _, config = _method_case(tmp_path, monkeypatch)
    root, space, owner, activity, ref, _ = case
    original = read_workflow(root, ref, owner).nodes[0]
    definition = WorkflowDefinition(
        title="Independent review branches",
        purpose="Keep independent progress",
        entry_nodes=("route",),
        nodes=(
            WorkflowNode(
                key="route",
                kind="model",
                instruction="Start all checks",
                successors=("review", "side1", "side2"),
            ),
            original.model_copy(update={"dependencies": ("route",)}),
            WorkflowNode(
                key="side1", kind="model", instruction="Check dates", dependencies=("route",)
            ),
            WorkflowNode(
                key="side2", kind="model", instruction="Check originals", dependencies=("route",)
            ),
        ),
    )
    source = core_cases._owner_source(case, b"Proceed with the independent checks")
    adopted = core_cases._adopt_workflow(root, space, owner, activity, source, definition)
    identifier = uuid4()
    core_cases._op(
        root,
        space,
        owner,
        WorkflowRequest,
        action="start",
        workflow=adopted,
        root_work_id=identifier,
        activity_id=activity,
        source_refs=(source,),
    )
    coordinator = WorkflowCoordinator(Bridge(root, owner, root), config)
    dispatched: list[str] = []

    def retain(_root: UUID, work_id: UUID, chosen: AssignedConfig) -> bool:
        state = read_work(root, work_id, owner)
        run = read_workflow_run(root, identifier, owner)
        current = next((entry for entry in run.nodes if entry.work_id == work_id), None)
        key = current.key if current else "analyse"
        dispatched.append(key)
        content = (
            json.dumps(
                {
                    "outcome": "result",
                    "values": {"checked": key},
                    "next_nodes": ["review", "side1", "side2"] if key == "route" else [],
                }
            ).encode()
            if chosen.result_protocol == "workflow_json"
            else b"Observed original"
        )
        artifact = uuid4()
        core_cases._op(
            root,
            space,
            owner,
            CreateArtifactRequest,
            artifact_id=artifact,
            media_type="text/plain",
            content=content,
        )
        core_cases._op(
            root,
            space,
            owner,
            LinkWorkOutputRequest,
            work_id=work_id,
            expected_revision=state.revision,
            output=LinkedOutput(
                slot=state.state.expected_outputs[0].slot,
                artifact=ArtifactRef(artifact_id=artifact, revision=1),
            ),
        )
        return True

    monkeypatch.setattr(coordinator, "_execute_work", retain)
    coordinator._run(identifier)
    assert set(dispatched) == {"route", "analyse", "side1", "side2"}
    state = read_workflow_run(root, identifier, owner)
    assert state.next_action == "owner_action"
    assert all(node.validation_id for node in state.nodes if node.key.startswith("side"))
    method_node = next(node for node in state.nodes if node.key == "review")
    native = read_workflow_method_tasks(root, method_node.work_id, owner)
    assert native["owner_waiting"] and not native["parent_ready"]


@pytest.mark.parametrize("busy_count", [1, 3])
def test_busy_model_free_poll_reopens_read_without_relaunching_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, busy_count: int
) -> None:
    """A transient identity read retries the read; the existing executor sends only once."""
    case = core_cases._setup(
        tmp_path, (WorkflowNode(key="inspect", kind="model", instruction="Read exact originals"),)
    )
    root, space, owner, _, _, identifier = case
    core_cases._step(
        case,
        "bind_node",
        node_key="inspect",
        model=WorkflowModel(
            provider="fictional", model_id="fictional", profile="local-completions", reasoning="off"
        ),
    )
    work = read_workflow_run(root, identifier, owner).nodes[0].work_id
    config = AssignedConfig(
        space=root,
        workspace=root,
        pi_cli=tmp_path / "unused.js",
        pi_runtime=tmp_path,
        node="node",
        provider_profile="local-completions",
        provider_base_url="http://127.0.0.1:1/v1",
        provider_id="fictional",
        model_id="fictional",
        context_window=4096,
        max_tokens=512,
        reserve_units=10,
        limit_units=None,
    )
    coordinator = WorkflowCoordinator(Bridge(root, owner, root), config)
    launches: list[Any] = []
    busy_reads: list[str] = []
    model_sends: list[UUID] = []
    actual_read = read_execution

    class Executor:
        stdin = io.BytesIO()
        stderr = io.BytesIO()
        returncode: int | None = None
        polling = False
        exited = threading.Event()

        def wait(self, timeout: float | None = None) -> int:
            if not self.exited.wait(timeout):
                assert timeout is not None
                raise subprocess.TimeoutExpired("fictional executor", timeout)
            assert self.returncode is not None
            return self.returncode

        def poll(self) -> int | None:
            if not self.polling:
                self.polling = True
                return None
            if self.returncode is None:
                snapshot = read_execution(root, work, owner)
                attempt = snapshot.attempts[-1]
                sent, _ = invocation(
                    root, space, work, attempt.attempt_id, attempt.session_id, owner, 1
                )
                model_sends.append(sent)
                for kind in (AdmitInvocationRequest, SendInvocationRequest):
                    core_cases._op(
                        root,
                        space,
                        owner,
                        kind,
                        invocation_id=sent,
                        attempt_id=attempt.attempt_id,
                        work_id=work,
                        session_id=attempt.session_id,
                    )
                core_cases._op(
                    root,
                    space,
                    owner,
                    FinishInvocationRequest,
                    invocation_id=sent,
                    attempt_id=attempt.attempt_id,
                    work_id=work,
                    session_id=attempt.session_id,
                    outcome="answered",
                    usage_units=1,
                )
                artifact = uuid4()
                core_cases._op(
                    root,
                    space,
                    owner,
                    CreateArtifactRequest,
                    artifact_id=artifact,
                    media_type="text/plain",
                    content=b"{}",
                )
                core_cases._op(
                    root,
                    space,
                    owner,
                    LinkWorkOutputRequest,
                    work_id=work,
                    expected_revision=read_work(root, work, owner).revision,
                    output=LinkedOutput(
                        slot="report", artifact=ArtifactRef(artifact_id=artifact, revision=1)
                    ),
                )
                self.returncode = 0
                self.exited.set()
            return self.returncode

    process = Executor()

    def launch(*arguments: Any, **options: Any) -> Executor:
        launches.append(arguments)
        return process

    def read(path: Path, work_id: UUID, authority: Any) -> Any:
        if process.polling and process.returncode is None and len(busy_reads) < busy_count:
            busy_reads.append("application_id")
            raise FoundationError(
                "storage",
                "SQLite identity failed at application_id (SQLITE_BUSY): database is locked",
            )
        return actual_read(path, work_id, authority)

    monkeypatch.setattr("zaratustra.pi_adapter.workflows.subprocess.Popen", launch)
    monkeypatch.setattr(workflow_host, "read_execution", read)
    if busy_count == 3:
        with pytest.raises(FoundationError) as error:
            coordinator._dispatch_work(identifier, work, config)
        assert error.value.code == "storage"
    else:
        assert coordinator._dispatch_work(identifier, work, config)
    snapshot = read_execution(root, work, owner)
    assert busy_reads == ["application_id"] * busy_count and len(launches) == 1
    assert len(snapshot.assignments) == len(snapshot.attempts) == 1
    if busy_count == 3:
        assert not snapshot.invocations and not model_sends
        assert work in coordinator.processes and not snapshot.work.state.linked_outputs
    else:
        assert len(snapshot.invocations) == len(model_sends) == 1
        assert snapshot.invocations[0].status == "answered"
        assert snapshot.work.state.linked_outputs and not coordinator.processes
    if process.returncode is None:
        process.returncode = 1
        process.exited.set()


@pytest.mark.parametrize("close_window", [False, True])
def test_native_method_question_is_visible_and_answer_uses_actual_user_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, close_window: bool
) -> None:
    """A role question stays addressed to that role, without accepting its output."""
    case, node, config = _method_case(tmp_path, monkeypatch)
    root, space, owner, activity, _, identifier = case
    bridge = Bridge(root, owner, root)
    coordinator = WorkflowCoordinator(bridge, config)
    bridge.workflow_controller = coordinator
    wait_id, attempt_id, assigned_session = uuid4(), uuid4(), uuid4()

    def ask(_root: UUID, work: UUID, _config: AssignedConfig) -> bool:
        resource = uuid4()
        core_cases._op(
            root,
            space,
            owner,
            CreateResourceRequest,
            resource_id=resource,
            work_id=work,
            state=ResourceState(label="Role resource", root=root, mode="shared"),
        )
        core_cases._op(
            root,
            space,
            owner,
            AssignAttemptRequest,
            work_id=work,
            attempt_id=attempt_id,
            expected_work_revision=read_work(root, work, owner).revision,
            resource_id=resource,
            expected_resource_revision=1,
            session_id=assigned_session,
            executor_version=EXECUTOR_VERSION,
        )
        rpc = Bridge(
            root, owner, root, assigned_attempt_id=attempt_id, assigned_session_id=assigned_session
        )
        rpc.connect(assigned_session)
        rpc.select(assigned_session, activity, work)
        rpc.open_wait(
            assigned_session,
            attempt_id,
            wait_id,
            "Known observations",
            "Which observations should I compare?",
            "Compare the addressed period",
        )
        return False

    monkeypatch.setattr(coordinator, "_execute_work", ask)
    assert not coordinator._execute_node(identifier, node)
    child = UUID(read_workflow_method_tasks(root, node.work_id, owner)["children"][0]["work_id"])
    if close_window:
        coordinator.active = identifier
        coordinator.close()
        assignment = read_execution(root, child, owner).assignments[-1]
        core_cases._op(
            root,
            space,
            owner,
            RecordAttemptStopRequest,
            work_id=child,
            attempt_id=attempt_id,
            session_id=assigned_session,
            expected_assignment_revision=assignment.revision,
            outcome="stopped",
        )
        bridge = Bridge(root, owner, root)
        coordinator = WorkflowCoordinator(bridge, config)
        bridge.workflow_controller = coordinator
    session = uuid4()
    bridge.connect(session)
    state = bridge.workflow(session, {"mode": "status", "root_work_id": str(identifier)})
    assert state["next_action"] == ("resume" if close_window else "answer")
    assert state["native_waits"][0]["question"] == "Which observations should I compare?"
    work_id = UUID(state["native_waits"][0]["work_id"])
    restarted: list[UUID] = []

    def restart(work: UUID, model: dict[str, Any]) -> dict[str, Any]:
        restarted.append(work)
        return {}

    monkeypatch.setattr(coordinator, "start", restart)
    bridge.capture_source(
        session,
        channel="conversation_user",
        content="Previous complete month",
        source_event_id="actual-owner-answer",
        input_source="rpc",
    )
    original = bridge.last_sources[session]
    raw = {
        "mode": "answer",
        "root_work_id": str(identifier),
        "wait_id": str(wait_id),
        "expected_wait_revision": state["native_waits"][0]["revision"],
        "operation_key": "addressed-answer",
    }
    bridge.workflow(session, raw)
    wait = read_execution(root, work_id, owner).waits[0]
    assert wait.status == ("closed" if close_window else "answered")
    if not close_window:
        assert wait.answer == "Previous complete month"
    interaction = bridge.workflow(
        session, {"mode": "interaction", "root_work_id": str(identifier), "wait_id": str(wait_id)}
    )
    assert interaction["answer"] == original.model_dump(mode="json")
    assert read_work(root, work_id, owner).state.acceptance is None
    assert restarted == [identifier]
    bridge.workflow(session, raw)
    assert restarted == [identifier]
    bridge.select(session, activity, work_id)
    packet = bridge.prepare_context(session)["packet"]
    assert isinstance(packet, dict)
    continuation = packet["workflow_continuation"]
    assert '"Previous complete month"' in continuation["content_text"]
    assert continuation["partials"]
    if close_window:
        assert read_workflow_run(root, identifier, owner).next_action == "resume"
        assert all(item.kind != "resume" for item in read_execution(root, child, owner).outbox)
        bridge.workflow(
            session,
            {
                "mode": "resume",
                "root_work_id": str(identifier),
                "operation_key": "resume-after-addressed-answer",
            },
        )
        assert read_workflow_run(root, identifier, owner).next_action == "run"
