"""Window-owned coordination of Core workflow Work through ordinary Pi/DBOS."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, Field, ValidationError

from zaratustra.foundation import (
    AssignAttemptRequest,
    CreateResourceRequest,
    FoundationError,
    IssueChildWorkRequest,
    LocalAuthority,
    RequestAttemptStopRequest,
    ResourceState,
    ReviseResourceRequest,
    WorkflowModel,
    WorkflowNodeView,
    WorkflowRequest,
    apply_operation,
    authorize_local,
    read_attempt_response,
    read_execution,
    read_workflow,
    read_workflow_method_tasks,
    read_workflow_run,
)

from .activity_setup import _observe
from .assigned import EXECUTOR_VERSION, AssignedConfig, read_assignment_refusal, run_assigned
from .response_recovery import missing_executor, recover_response

if TYPE_CHECKING:
    from .bridge import Bridge


READ_TOOLS = ("zara_workflow", "zara_memory")
WORKER_ERROR_PREFIX = "ZARATUSTRA_WORKFLOW_WORKER_ERROR "


class WorkerFailureRecord(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}
    protocol: Literal["zara.pi.worker-error.v1"] = "zara.pi.worker-error.v1"
    work_id: UUID
    attempt_id: UUID
    code: str = Field(min_length=1, max_length=100)
    detail: str = Field(min_length=1, max_length=500)


def _read_worker_failure(
    tail: bytearray, work_id: UUID, attempt_id: UUID
) -> FoundationError | None:
    for line in reversed(tail.decode("utf-8", errors="replace").splitlines()):
        if not line.startswith(WORKER_ERROR_PREFIX):
            continue
        try:
            record = WorkerFailureRecord.model_validate_json(line[len(WORKER_ERROR_PREFIX) :])
        except ValidationError:
            continue
        if record.work_id == work_id and record.attempt_id == attempt_id:
            return FoundationError(record.code, record.detail)
    return None


def node_tools(actions: tuple[str, ...]) -> tuple[str, ...]:
    tools = list(READ_TOOLS)
    for action, names in (
        ("project_read", ("read",)),
        ("project_write", ("write", "edit")),
        ("project_command", ("bash",)),
    ):
        if action in actions:
            tools.extend(names)
    return tuple(tools)


def method_work_ids(path: Path, parent: UUID, authority: LocalAuthority) -> set[UUID]:
    """Read one issued native Method family without duplicating its graph."""
    works: set[UUID] = set()

    def visit(work: UUID) -> None:
        if work in works:
            return
        works.add(work)
        try:
            tasks = read_workflow_method_tasks(path, work, authority)
        except FoundationError as error:
            if error.code == "wrong_kind":
                return
            raise
        for child in tasks["children"]:
            if child["issued"]:
                visit(UUID(child["work_id"]))

    visit(parent)
    return works


def workflow_work_ids(path: Path, root: UUID, authority: LocalAuthority) -> set[UUID]:
    """Read the Core-owned node and issued Method families for worker fencing."""
    works: set[UUID] = {root}
    for node in read_workflow_run(path, root, authority).nodes:
        works.update(method_work_ids(path, node.work_id, authority))
    return works


def workflow_view(path: Path, root: UUID, authority: LocalAuthority) -> dict[str, Any]:
    """Project native questions already derived by Core, without a second status."""
    current = read_workflow_run(path, root, authority)
    view = current.model_dump(mode="json")
    view["native_waits"] = [wait for wait in view["waits"] if wait.get("native")]
    definition = read_workflow(path, current.workflow, authority)
    model_nodes = {node.key for node in definition.nodes if node.kind == "model"}
    for node in view["nodes"]:
        if node["key"] in model_nodes and node["output"] is None and not node["retired"]:
            node["response"] = read_attempt_response(
                path, UUID(node["work_id"]), authority
            ).model_dump(mode="json")
    return view


@dataclass
class _Executor:
    process: subprocess.Popen[bytes]
    reader: threading.Thread
    tail: bytearray
    attempt_id: UUID
    lease_token: object | None = None


class _ExecutorPool:
    """Window-local leases follow actual subprocess lifetimes, including RPC waits."""

    def __init__(self) -> None:
        self.slots = threading.BoundedSemaphore(2)
        self.lock = threading.Lock()
        self.leases: dict[UUID, object] = {}
        self.processes: dict[UUID, _Executor] = {}

    def release(self, work_id: UUID, token: object | None) -> None:
        with self.lock:
            if token is not None and self.leases.get(work_id) is token:
                self.leases.pop(work_id)
                self.slots.release()


class WorkflowCoordinator:
    """Schedules only admitted nodes; all execution evidence remains in Core."""

    def __init__(self, bridge: Bridge, config: AssignedConfig) -> None:
        self.bridge = bridge
        self.config = config
        self.thread: threading.Thread | None = None
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.lock = threading.Lock()
        self.control_lock = threading.Lock()
        with bridge.lock:
            if bridge.workflow_executor_pool is None:
                bridge.workflow_executor_pool = _ExecutorPool()
            self.pool: _ExecutorPool = bridge.workflow_executor_pool
        self.executors = self.pool.slots
        self.active: UUID | None = None
        self.selection: dict[str, Any] = {
            "id": config.model_id,
            "provider": config.provider_id,
            "thinking": config.thinking or "off",
        }
        self.processes = self.pool.processes
        self.owned_processes: set[UUID] = set()

    def update_model(self, model: dict[str, Any]) -> None:
        if not model.get("id") or model.get("provider") != self.config.provider_id:
            raise FoundationError("unsupported_provider", "Use the admitted selected provider")
        with self.lock:
            self.selection = dict(model)

    def start(self, identifier: UUID, model: dict[str, Any]) -> dict[str, Any]:
        with self.control_lock:
            return self._start(identifier, model)

    def _start(self, identifier: UUID, model: dict[str, Any]) -> dict[str, Any]:
        self.update_model(model)
        current = read_workflow_run(self.config.space, identifier, self.bridge.authority)
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                if self.active != identifier:
                    raise FoundationError("workflow_running", "Another workflow is executing")
                self.wake.set()
                return current.model_dump(mode="json")
            self.active = identifier
            self.stop.clear()
            self.wake.clear()
            self.thread = threading.Thread(target=self._drive, args=(identifier,), daemon=True)
            self.thread.start()
        return current.model_dump(mode="json")

    def _drive(self, identifier: UUID) -> None:
        while not self.stop.is_set():
            self._run(identifier)
            with self.lock:
                if self.wake.is_set() and not self.stop.is_set():
                    self.wake.clear()
                    continue
                self.thread = None
                return

    def _resource_policy(self, spec: Any) -> tuple[Path, bool]:
        root = self.config.workspace
        if self.config.workspace_config is not None:
            from zaratustra.workspace import read_config

            config = read_config(self.config.workspace_config)
            root = config.project_root(spec.project if spec.resource == "project" else "personal")
        exclusive = any(
            action in ("project_write", "project_command") for action in spec.allowed_actions
        )
        return root.resolve(), exclusive

    def _resource_available(
        self, identifier: UUID, node: WorkflowNodeView, policy: tuple[Path, bool]
    ) -> bool:
        own_family = method_work_ids(self.config.space, node.work_id, self.bridge.authority)
        for work in (
            workflow_work_ids(self.config.space, identifier, self.bridge.authority) - own_family
        ):
            snapshot = read_execution(self.config.space, work, self.bridge.authority)
            active = {
                attempt.resource_id
                for attempt in snapshot.attempts
                if attempt.status == "active"
                or any(
                    assignment.attempt_id == attempt.attempt_id and assignment.status == "unknown"
                    for assignment in snapshot.assignments
                )
            }
            if any(
                resource.resource_id in active
                and resource.state.root.resolve() == policy[0]
                and (policy[1] or resource.state.mode == "exclusive")
                for resource in snapshot.resources
            ):
                return False
        return True

    def _step(self, identifier: UUID, action: str, **fields: Any) -> Any:
        current = _observe(read_workflow_run, self.config.space, identifier, self.bridge.authority)
        request = WorkflowRequest.model_validate(
            {
                "space_id": self.bridge.authority.space_id,
                "actor": self.bridge.authority.actor,
                "root_work_id": identifier,
                "expected_revision": current.revision,
                "action": action,
                **fields,
                "operation_id": uuid5(
                    identifier,
                    f"host:{action}:{current.revision}:"
                    + json.dumps(fields, sort_keys=True, default=str),
                ),
            }
        )
        return _observe(apply_operation, self.config.space, request, self.bridge.authority)

    def _run(self, identifier: UUID) -> None:
        try:
            while not self.stop.is_set():
                state = _observe(
                    read_workflow_run, self.config.space, identifier, self.bridge.authority
                )
                available = workflow_view(self.config.space, identifier, self.bridge.authority)
                if state.next_action in ("answer", "owner_action", "resume", "attention", "closed"):
                    return
                if state.next_action == "finish":
                    self._step(identifier, "finish")
                    return
                definition = read_workflow(self.config.space, state.workflow, self.bridge.authority)
                specs = {node.key: node for node in definition.nodes}
                nodes: list[WorkflowNodeView] = []
                resource_policies: list[tuple[Path, bool]] = []
                progressed = False
                for key in available["ready_nodes"]:
                    current = read_workflow_run(
                        self.config.space, identifier, self.bridge.authority
                    )
                    node = next(item for item in reversed(current.nodes) if item.key == key)
                    if node.output is not None:
                        self._step(identifier, "advance", node_key=key, iteration=node.iteration)
                        progressed = True
                        break
                    if specs[key].kind != "model":
                        receipt = self._step(
                            identifier, "advance", node_key=key, iteration=node.iteration
                        )
                        progressed = True
                        nested = receipt.result.get("nested_root_work_id")
                        if nested is not None:
                            nested_id = UUID(str(nested))
                            self._run(nested_id)
                            snapshot = read_execution(
                                self.config.space, nested_id, self.bridge.authority
                            )
                            if not snapshot.work.state.linked_outputs:
                                return
                            self._step(
                                identifier, "advance", node_key=key, iteration=node.iteration
                            )
                        break
                    policy = self._resource_policy(specs[key])
                    if not self._resource_available(identifier, node, policy) or any(
                        policy[0] == other[0] and (policy[1] or other[1])
                        for other in resource_policies
                    ):
                        continue
                    if node.model is None:
                        with self.lock:
                            selection = dict(self.selection)
                        pinned = WorkflowModel(
                            provider=str(selection["provider"]),
                            model_id=str(selection["id"]),
                            profile=self.config.provider_profile,
                            reasoning=str(
                                selection.get("thinking") or self.config.thinking or "off"
                            ),
                        )
                        self._step(
                            identifier,
                            "bind_node",
                            node_key=key,
                            model=pinned.model_dump(mode="json"),
                        )
                        current = read_workflow_run(
                            self.config.space, identifier, self.bridge.authority
                        )
                        node = next(item for item in reversed(current.nodes) if item.key == key)
                    nodes.append(node)
                    resource_policies.append(policy)
                    if len(nodes) == 2:
                        break
                if not nodes:
                    if progressed:
                        continue
                    if not available["ready_nodes"] and available["native_waits"]:
                        return
                    if not state.ready_nodes:
                        raise FoundationError(
                            "workflow_no_progress", "No eligible node or retained continuation"
                        )
                    return
                waiting_for_owner = False
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(self._execute_node, identifier, node) for node in nodes]
                    for node, future in zip(nodes, futures, strict=True):
                        finished = future.result()
                        if not finished:
                            waiting_for_owner = True
                            continue
                        if self.stop.is_set():
                            return
                        snapshot = read_execution(
                            self.config.space, node.work_id, self.bridge.authority
                        )
                        if not snapshot.work.state.linked_outputs:
                            raise FoundationError(
                                "workflow_output_missing", "Node did not retain its raw Artifact"
                            )
                        output = snapshot.work.state.linked_outputs[0].artifact
                        self._step(
                            identifier,
                            "validate_output",
                            node_key=node.key,
                            iteration=node.iteration,
                            output=output.model_dump(mode="json"),
                        )
                        current = read_workflow_run(
                            self.config.space, identifier, self.bridge.authority
                        )
                        checked = next(
                            item for item in reversed(current.nodes) if item.key == node.key
                        )
                        if checked.validation_id is not None or checked.issues:
                            self._step(
                                identifier, "advance", node_key=node.key, iteration=node.iteration
                            )
                if waiting_for_owner:
                    pending = workflow_view(self.config.space, identifier, self.bridge.authority)
                    if not pending["ready_nodes"]:
                        return
        except Exception as error:
            if not self.stop.is_set():
                try:
                    self._step(
                        identifier,
                        "attention",
                        text=str(error)[:4096],
                        code=error.code
                        if isinstance(error, FoundationError)
                        else "workflow_executor",
                    )
                except FoundationError:
                    # Losing authority never authorizes another send or an invented repair.
                    return

    def _execute_node(self, identifier: UUID, node: WorkflowNodeView) -> bool:
        authority = self.bridge.authority
        config = self.config
        run = read_workflow_run(config.space, identifier, authority)
        definition = read_workflow(config.space, run.workflow, authority)
        spec = next(item for item in definition.nodes if item.key == node.key)
        if spec.method is None:
            response = recover_response(config.space, node.work_id, authority)
            if response.outcome == "applied":
                return True
            if response.outcome == "running":
                return self._execute_work(identifier, node.work_id, config)
        pinned = node.model
        if pinned is None or (pinned.profile, pinned.provider) != (
            config.provider_profile,
            config.provider_id,
        ):
            raise FoundationError(
                "unsupported_provider", "Node model/profile does not match admission"
            )
        config = replace(
            config,
            model_id=pinned.model_id,
            thinking=pinned.reasoning,
            disable_tools=False,
            restricted_tools=READ_TOOLS,
            pi_tools=(),
        )
        config = replace(
            config,
            restricted_tools=node_tools(spec.allowed_actions),
            workflow_project_tools=any(
                action.startswith("project_") for action in spec.allowed_actions
            ),
            result_protocol="setup_json"
            if spec.result_protocol in ("setup_draft", "setup_review")
            else "workflow_json",
        )
        if config.workspace_config is not None:
            from zaratustra.workspace import read_config, select_work_project

            workspace = read_config(config.workspace_config)
            selected = spec.project if spec.resource == "project" else "personal"
            if selected is None:
                raise FoundationError("resource_unavailable", "Node project is unspecified")
            config = replace(
                config, workspace=select_work_project(workspace, authority, node.work_id, selected)
            )
        elif spec.resource == "project":
            raise FoundationError("resource_unavailable", "Node project must be registered")
        if spec.method is not None:
            return self._execute_method_work(identifier, node.work_id, config)
        return self._execute_work(identifier, node.work_id, config)

    def _execute_work(self, identifier: UUID, work_id: UUID, config: AssignedConfig) -> bool:
        while not self.stop.is_set():
            with self.pool.lock:
                token = self.pool.leases.get(work_id)
            retained = token is not None
            if retained or self.executors.acquire(timeout=0.2):
                if not retained:
                    with self.pool.lock:
                        if work_id in self.pool.leases:
                            self.executors.release()
                            token = self.pool.leases[work_id]
                        else:
                            token = object()
                            self.pool.leases[work_id] = token
                try:
                    with self.lock:
                        self.owned_processes.add(work_id)
                    return self._dispatch_work(identifier, work_id, config)
                finally:
                    with self.pool.lock:
                        executor = self.processes.get(work_id)
                    if executor is None or executor.process.poll() is not None:
                        self.pool.release(work_id, token)
        return False

    def _watch_executor_exit(self, work_id: UUID, executor: _Executor) -> None:
        token = self.pool.leases.get(work_id)
        executor.lease_token = token

        def observe() -> None:
            executor.process.wait()
            self.pool.release(work_id, token)

        threading.Thread(target=observe, daemon=True).start()

    def _execute_method_work(self, identifier: UUID, work_id: UUID, config: AssignedConfig) -> bool:
        """Issue native roles and preserve their ordinary acceptance requirements."""
        authority = self.bridge.authority
        while not self.stop.is_set():
            tasks = read_workflow_method_tasks(config.space, work_id, authority)
            children = [child for child in tasks["children"] if child["ready"]]
            if children:
                executable = []
                maximum = (
                    1
                    if any(tool in config.restricted_tools for tool in ("write", "edit", "bash"))
                    else 2
                )
                for child in children[:maximum]:
                    child_id = UUID(child["work_id"])
                    if not child["issued"]:
                        apply_operation(
                            config.space,
                            IssueChildWorkRequest(
                                operation_id=uuid5(
                                    child_id, f"workflow-issue:{tasks['plan_revision']}"
                                ),
                                space_id=authority.space_id,
                                actor=authority.actor,
                                parent_work_id=work_id,
                                work_id=child_id,
                                expected_plan_revision=tasks["plan_revision"],
                                expected_work_revision=child["work_revision"],
                            ),
                            authority,
                        )
                    executable.append((child_id, child["method"]))
                role_config = replace(config, result_protocol=None)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [
                        pool.submit(
                            self._execute_method_work if method != "none" else self._execute_work,
                            identifier,
                            child_id,
                            role_config,
                        )
                        for child_id, method in executable
                    ]
                    finished = [future.result() for future in futures]
                if not all(finished):
                    return False
                continue
            if not tasks["own_output_pending"]:
                return True
            if tasks["parent_ready"]:
                return self._execute_work(identifier, work_id, config)
            # Proposed outputs and obligations remain available for the owner;
            # publishing them is never an acceptance operation.
            return False
        return False

    def _dispatch_work(self, identifier: UUID, work_id: UUID, config: AssignedConfig) -> bool:
        authority = self.bridge.authority
        snapshot = read_execution(config.space, work_id, authority)
        if any(wait.status == "open" for wait in snapshot.waits):
            return False
        with self.pool.lock:
            active_process = self.processes.get(work_id)
        response = recover_response(config.space, work_id, authority)
        if response.outcome == "applied":
            return True
        if response.outcome == "running":
            if active_process is None:
                raise missing_executor(response)
            return self._await_executor(work_id, active_process, config)
        resource_id = uuid5(work_id, "workflow-resource")
        if not snapshot.resources:
            apply_operation(
                config.space,
                CreateResourceRequest(
                    operation_id=uuid5(resource_id, "create"),
                    space_id=authority.space_id,
                    actor=authority.actor,
                    resource_id=resource_id,
                    work_id=work_id,
                    state=ResourceState(
                        label="Workflow node",
                        root=config.workspace,
                        mode="exclusive"
                        if any(
                            tool in config.restricted_tools for tool in ("write", "edit", "bash")
                        )
                        else "shared",
                        limit_units=config.limit_units,
                    ),
                ),
                authority,
            )
            snapshot = read_execution(config.space, work_id, authority)
        resources = [item for item in snapshot.resources if item.state.status == "active"]
        if len(resources) != 1:
            raise FoundationError("resource_unavailable", "Node needs one active resource")
        required_mode = (
            "exclusive"
            if any(tool in config.restricted_tools for tool in ("write", "edit", "bash"))
            else "shared"
        )
        if resources[0].state.mode != required_mode:
            if any(attempt.status == "active" for attempt in snapshot.attempts):
                raise FoundationError("resource_busy", "Active resource policy cannot change")
            resource = resources[0]
            apply_operation(
                config.space,
                ReviseResourceRequest(
                    operation_id=uuid5(
                        resource.resource_id, f"workflow-mode:{resource.revision}:{required_mode}"
                    ),
                    space_id=authority.space_id,
                    actor=authority.actor,
                    work_id=work_id,
                    resource_id=resource.resource_id,
                    expected_revision=resource.revision,
                    state=resource.state.model_copy(update={"mode": required_mode}),
                ),
                authority,
            )
            snapshot = read_execution(config.space, work_id, authority)
            resources = [item for item in snapshot.resources if item.state.status == "active"]
        config = replace(config, workspace=resources[0].state.root)
        if snapshot.assignments and snapshot.assignments[-1].status in ("assigned", "ready"):
            attempt_id = snapshot.assignments[-1].attempt_id
        else:
            attempt_id = uuid5(work_id, f"attempt:{len(snapshot.attempts) + 1}")
            apply_operation(
                config.space,
                AssignAttemptRequest(
                    ordinary_handoff=response.handoff_operation_id,
                    operation_id=uuid5(attempt_id, "assign"),
                    space_id=authority.space_id,
                    actor=authority.actor,
                    work_id=work_id,
                    attempt_id=attempt_id,
                    expected_work_revision=snapshot.work.revision,
                    resource_id=resources[0].resource_id,
                    expected_resource_revision=resources[0].revision,
                    session_id=uuid5(attempt_id, "session"),
                    executor_version=EXECUTOR_VERSION,
                    previous_attempt_id=snapshot.attempts[-1].attempt_id
                    if snapshot.attempts
                    else None,
                ),
                authority,
            )
        payload = {
            "config": {
                key: str(value) if isinstance(value, Path) else value
                for key, value in asdict(config).items()
            },
            "actor": authority.actor,
            "root_work_id": str(identifier),
            "attempt_id": str(attempt_id),
            "work_id": str(work_id),
        }
        with self.pool.lock:
            executor = self.processes.get(work_id)
            if executor is None:
                process = subprocess.Popen(
                    [sys.executable, "-X", "utf8", "-m", "zaratustra.pi_adapter.workflows"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                assert process.stdin is not None
                process.stdin.write(json.dumps(payload).encode("utf-8"))
                process.stdin.close()
                tail = bytearray()

                def drain() -> None:
                    stream = process.stderr
                    assert stream is not None
                    for chunk in iter(lambda: stream.read(4096), b""):
                        tail.extend(chunk)
                        if len(tail) > 16384:
                            del tail[:-16384]

                reader = threading.Thread(target=drain, daemon=True)
                reader.start()
                executor = _Executor(process, reader, tail, attempt_id)
                self.processes[work_id] = executor
                self._watch_executor_exit(work_id, executor)
        return self._await_executor(work_id, executor, config)

    def _await_executor(self, work_id: UUID, executor: _Executor, config: AssignedConfig) -> bool:
        authority = self.bridge.authority
        attempt_id = executor.attempt_id
        process = executor.process
        while process.poll() is None:
            if self.stop.wait(0.2):
                self._stop_node(work_id)
            elif any(
                wait.status == "open"
                for wait in _observe(read_execution, config.space, work_id, authority).waits
            ):
                # Keep the actual assigned RPC/DBOS process; an addressed answer
                # wakes this same Attempt through its durable Core outbox.
                return False
        executor.reader.join(timeout=2)
        with self.pool.lock:
            self.processes.pop(work_id, None)
        if not self.stop.is_set():
            response = recover_response(config.space, work_id, authority)
            if response.outcome == "applied":
                return True
            if response.outcome == "running":
                raise missing_executor(response)
        if process.returncode and not self.stop.is_set():
            saved_refusal = _observe(
                read_assignment_refusal, config.space, work_id, attempt_id, authority
            )
            if saved_refusal is not None:
                raise saved_refusal
            worker_failure = _read_worker_failure(executor.tail, work_id, attempt_id)
            if worker_failure is not None:
                raise worker_failure
            raise FoundationError(
                "workflow_executor",
                executor.tail.decode("utf-8", errors="replace")[-4096:]
                or f"Node executor exited {process.returncode}",
            )
        return bool(read_execution(config.space, work_id, authority).work.state.linked_outputs)

    def _stop_node(self, work_id: UUID) -> None:
        authority = self.bridge.authority
        snapshot = read_execution(self.config.space, work_id, authority)
        for assignment in snapshot.assignments:
            if assignment.status not in ("assigned", "waiting", "ready"):
                continue
            attempt = next(
                item for item in snapshot.attempts if item.attempt_id == assignment.attempt_id
            )
            apply_operation(
                self.config.space,
                RequestAttemptStopRequest(
                    operation_id=uuid5(assignment.attempt_id, "workflow-window-stop"),
                    space_id=authority.space_id,
                    actor=authority.actor,
                    work_id=work_id,
                    attempt_id=assignment.attempt_id,
                    session_id=attempt.session_id,
                    expected_assignment_revision=assignment.revision,
                    reason="Workflow window closed or paused",
                ),
                authority,
            )

    def request_pause(self, root_id: UUID | None = None, *, expected_thread: Any = ...) -> None:
        with self.control_lock:
            if expected_thread is not ... and self.thread not in (None, expected_thread):
                raise FoundationError("stale_session", "A later executor owns this workflow")
            self._request_pause(root_id)

    def _request_pause(self, root_id: UUID | None = None) -> None:
        """Request Core stops promptly; cleanup waits belong only to close."""
        if root_id is not None and self.active != root_id:
            return
        try:
            if self.active is not None:
                current = read_workflow_run(self.config.space, self.active, self.bridge.authority)
                if current.control == "running" and current.next_action != "closed":
                    # Core pauses the current family and requests its stops in
                    # one transaction, before orphaned local processes are read.
                    self._step(self.active, "pause")
        finally:
            self.stop.set()
        with self.lock:
            owned = set(self.owned_processes)
        for work in owned:
            self._stop_node(work)

    def close(self) -> None:
        try:
            self.request_pause()
        finally:
            self._close_owned()

    def _close_owned(self) -> None:
        """Drain owned processes even when current Core admission refuses pause."""
        with self.lock:
            owned = set(self.owned_processes)
        thread = self.thread
        if thread is not None:
            thread.join(timeout=15)
        with self.pool.lock:
            owned_executors = [
                (work, self.processes[work]) for work in owned if work in self.processes
            ]
        for work, executor in owned_executors:
            try:
                executor.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                # Core retains the stop/unknown evidence. Never claim a stop by
                # destroying an unobserved model process.
                continue
            executor.reader.join(timeout=2)
            self.pool.release(work, executor.lease_token)
        with self.pool.lock:
            for work, executor in owned_executors:
                if self.processes.get(work) is executor and executor.process.poll() is not None:
                    self.processes.pop(work, None)


def worker() -> int:
    """Run one already admitted node in the existing assigned executor."""
    raw = json.loads(sys.stdin.buffer.read())
    fields = raw["config"]
    for key in (
        "space",
        "workspace",
        "pi_cli",
        "pi_runtime",
        "subscription_agent_dir",
        "workspace_config",
    ):
        if fields.get(key) is not None:
            fields[key] = Path(fields[key])
    for key in ("pi_tools", "restricted_tools"):
        fields[key] = tuple(fields.get(key, ()))
    config = AssignedConfig(**fields)
    if config.provider_profile not in ("codex-sse", "local-completions"):
        raise FoundationError(
            "permission_denied", "Workflow worker requires the restricted node profile"
        )
    authority = authorize_local(
        config.space, actor=str(raw["actor"]), source_ref="workflow-node-worker"
    )
    root = UUID(raw["root_work_id"])
    attempt = UUID(raw["attempt_id"])
    members = workflow_work_ids(config.space, root, authority)
    if not any(
        any(
            item.attempt_id == attempt
            for item in read_execution(config.space, work_id, authority).assignments
        )
        for work_id in members
    ):
        raise FoundationError("wrong_work", "Attempt is not a node of this workflow")
    work = UUID(raw["work_id"])
    current = read_workflow_run(config.space, root, authority)
    node = next(
        (
            item
            for item in current.nodes
            if work in method_work_ids(config.space, item.work_id, authority)
        ),
        None,
    )
    if node is None or node.model is None:
        raise FoundationError("wrong_work", "Attempt has no pinned workflow node")
    spec = next(
        item
        for item in read_workflow(config.space, current.workflow, authority).nodes
        if item.key == node.key
    )
    if config.restricted_tools != node_tools(spec.allowed_actions) or (
        config.provider_id,
        config.model_id,
        config.provider_profile,
        config.thinking,
    ) != (node.model.provider, node.model.model_id, node.model.profile, node.model.reasoning):
        raise FoundationError(
            "permission_denied", "Worker policy or model differs from its exact node pin"
        )
    if config.workflow_project_tools != any(
        action.startswith("project_") for action in spec.allowed_actions
    ):
        raise FoundationError(
            "permission_denied", "Worker resource fence differs from declared actions"
        )
    try:
        run_assigned(config, authority, attempt)
    except FoundationError as error:
        print(
            WORKER_ERROR_PREFIX
            + WorkerFailureRecord(
                work_id=work, attempt_id=attempt, code=error.code, detail=error.detail[:500]
            ).model_dump_json(),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(worker())
