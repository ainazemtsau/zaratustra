"""Window-owned execution of one saved procedure through ordinary assigned Pi/DBOS."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

from zaratustra.foundation import (
    AssignAttemptRequest,
    CreateKnowledgeRequest,
    CreateResourceRequest,
    FoundationError,
    MemoryMetadata,
    RequestAttemptStopRequest,
    ResourceState,
    SourceState,
    apply_operation,
    authorize_local,
    describe_structure,
    procedure_status,
    read_execution,
)
from zaratustra.workspace import read_config, select_work_project

from .assigned import EXECUTOR_VERSION, AssignedConfig, run_assigned
from .bridge import Bridge


class ProcedureCoordinator:
    """No separate queue or model loop; all execution state belongs to Core."""

    def __init__(self, bridge: Bridge, config: AssignedConfig):
        self.bridge, self.config = bridge, replace(config, disable_tools=False)
        self.thread: threading.Thread | None = None
        self.active: UUID | None = None
        self.stop = threading.Event()
        self.lock = threading.Lock()

    def update_model(self, model: dict[str, Any]) -> None:
        if model.get("provider") != self.config.provider_id or not model.get("id"):
            raise FoundationError("unsupported_provider", "Use the admitted selected provider")
        with self.lock:
            self.config = replace(
                self.config, model_id=str(model["id"]), thinking=model.get("thinking")
            )

    def start(self, run_id: UUID, model: dict[str, Any]) -> dict[str, Any]:
        if model.get("provider") != self.config.provider_id or not model.get("id"):
            raise FoundationError(
                "unsupported_provider", "Use the selected admitted subscription/model"
            )
        status = procedure_status(self.config.space, self.bridge.authority, run_id)
        work = UUID(status["work_id"])
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                if self.active == work:
                    return {**status, "execution": "running"}
                raise FoundationError(
                    "procedure_running", "Another procedure runs in this Pi window"
                )
            snapshot = read_execution(self.config.space, work, self.bridge.authority)
            if snapshot.work.state.linked_outputs or snapshot.work.state.status != "proposed":
                return {**status, "execution": "result_available"}
            if any(item.status in ("sent", "unknown") for item in snapshot.invocations):
                return {**status, "execution": "unknown", "requires_resolution": True}
            if snapshot.assignments and snapshot.assignments[-1].status in ("unknown", "waiting"):
                return {**status, "execution": snapshot.assignments[-1].status}
            definition = describe_structure(
                self.config.space, UUID(status["activity_id"]), self.bridge.authority, work_id=work
            )["state"]
            procedure = next(
                item for item in definition["procedures"] if item["key"] == status["procedure"]
            )
            config = replace(self.config, model_id=str(model["id"]), thinking=model.get("thinking"))
            if config.workspace_config is not None:
                workspace = read_config(config.workspace_config)
                project = procedure["project"] if procedure["resource"] == "project" else "personal"
                config = replace(
                    config,
                    workspace=select_work_project(workspace, self.bridge.authority, work, project),
                )
            elif procedure["resource"] == "project":
                raise FoundationError("resource_unavailable", "Project must be registered locally")
            if not snapshot.resources:
                resource = uuid5(work, "procedure-resource")
                apply_operation(
                    config.space,
                    CreateResourceRequest(
                        operation_id=uuid5(resource, "create"),
                        space_id=self.bridge.authority.space_id,
                        actor=self.bridge.authority.actor,
                        work_id=work,
                        resource_id=resource,
                        state=ResourceState(
                            label="Procedure", root=config.workspace, limit_units=config.limit_units
                        ),
                    ),
                    self.bridge.authority,
                )
            snapshot = read_execution(config.space, work, self.bridge.authority)
            resources = [item for item in snapshot.resources if item.state.status == "active"]
            if len(resources) != 1:
                raise FoundationError("resource_unavailable", "Procedure needs one active resource")
            config = replace(config, workspace=resources[0].state.root)
            if snapshot.assignments and snapshot.assignments[-1].status in ("assigned", "ready"):
                attempt = snapshot.assignments[-1].attempt_id
            else:
                attempt = uuid4()
                apply_operation(
                    config.space,
                    AssignAttemptRequest(
                        operation_id=uuid5(attempt, "assign"),
                        space_id=self.bridge.authority.space_id,
                        actor=self.bridge.authority.actor,
                        work_id=work,
                        attempt_id=attempt,
                        expected_work_revision=snapshot.work.revision,
                        resource_id=resources[0].resource_id,
                        expected_resource_revision=resources[0].revision,
                        session_id=uuid4(),
                        executor_version=EXECUTOR_VERSION,
                        previous_attempt_id=snapshot.attempts[-1].attempt_id
                        if snapshot.attempts
                        else None,
                    ),
                    self.bridge.authority,
                )
            self.active, self.config = work, config
            self.stop.clear()
            self.thread = threading.Thread(target=self._run, args=(attempt,), daemon=True)
            self.thread.start()
            return {**status, "execution": "assigned", "attempt_id": str(attempt)}

    def _run(self, attempt: UUID) -> None:
        payload = {
            "config": {
                key: str(value) if isinstance(value, Path) else value
                for key, value in asdict(self.config).items()
            },
            "actor": self.bridge.authority.actor,
            "attempt_id": str(attempt),
        }
        process = subprocess.Popen(
            [sys.executable, "-X", "utf8", "-m", "zaratustra.pi_adapter.procedures"],
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
                del tail[:-16384]

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        while process.poll() is None:
            if self.stop.wait(0.2):
                self._request_stop()
        reader.join(timeout=2)
        if process.returncode and self.active is not None:
            snapshot = read_execution(self.config.space, self.active, self.bridge.authority)
            apply_operation(
                self.config.space,
                CreateKnowledgeRequest(
                    operation_id=uuid5(attempt, "procedure-executor-failure"),
                    space_id=self.bridge.authority.space_id,
                    actor=self.bridge.authority.actor,
                    record_id=uuid5(attempt, "procedure-executor-diagnostic"),
                    state=SourceState(
                        channel="tool_result",
                        connection="procedure-executor",
                        profile_revision=1,
                        sender="local-executor",
                        capture="full",
                        media_type="text/plain",
                        scope_activity_id=snapshot.work.state.activity_id,
                        scope_work_id=self.active,
                        content=bytes(tail) or f"Executor exited {process.returncode}".encode(),
                        memory=MemoryMetadata(
                            title="Procedure execution error", material_role="execution"
                        ),
                    ),
                ),
                self.bridge.authority,
            )

    def _request_stop(self) -> None:
        if self.active is None:
            return
        snapshot = read_execution(self.config.space, self.active, self.bridge.authority)
        for item in snapshot.assignments:
            if item.status not in ("assigned", "ready", "waiting"):
                continue
            attempt = next(
                value for value in snapshot.attempts if value.attempt_id == item.attempt_id
            )
            apply_operation(
                self.config.space,
                RequestAttemptStopRequest(
                    operation_id=uuid5(item.attempt_id, "procedure-window-stop"),
                    space_id=self.bridge.authority.space_id,
                    actor=self.bridge.authority.actor,
                    work_id=self.active,
                    attempt_id=item.attempt_id,
                    session_id=attempt.session_id,
                    expected_assignment_revision=item.revision,
                    reason="Procedure Pi window closed",
                ),
                self.bridge.authority,
            )

    def close(self) -> None:
        self.stop.set()
        self._request_stop()
        if self.thread:
            self.thread.join(timeout=5)


def worker() -> None:
    raw = json.loads(sys.stdin.buffer.read())
    fields = dict(raw["config"])
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
    fields["pi_tools"] = tuple(fields.get("pi_tools", ()))
    config = AssignedConfig(**fields)
    authority = authorize_local(config.space, actor=raw["actor"], source_ref="procedure-worker")
    run_assigned(config, authority, UUID(raw["attempt_id"]))


if __name__ == "__main__":
    worker()
