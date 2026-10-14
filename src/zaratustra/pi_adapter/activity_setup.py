"""Finite Activity setup over the existing assigned Pi/DBOS executor."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4, uuid5

from zaratustra.foundation import (
    ActivitySetupRequest,
    AssignAttemptRequest,
    CreateResourceRequest,
    FoundationError,
    RequestAttemptStopRequest,
    ResourceState,
    WorkflowModel,
    apply_operation,
    authorize_local,
    read_activity_setup,
    read_execution,
    read_space,
    read_workflow_node_for_work,
)

from .assigned import EXECUTOR_VERSION, AssignedConfig, run_assigned
from .response_recovery import missing_executor, recover_response

if TYPE_CHECKING:
    from .bridge import Bridge

INSTRUCTIONS = {
    "draft": (
        "Prepare the whole initial Activity setup from the supplied exact user sources. Ask "
        "about goals/workflow, never implementation. Prefer a simple usable foundation, "
        "originals/history, clear Work results, continuation and later Sleep. Return the "
        "ActivitySetupDraft JSON matching result_schema as your final text; retain "
        "unresolved necessary user questions in open_questions. Do not invent implemented "
        "capabilities. Method Works need a complete typed composite plan; plain Works need "
        "declared outputs. No trial is required."
        " For contract_version 2, design the entire first workflow: planning horizon, intake, "
        "facts versus intentions, use, review and adaptation. Ask about meaningful periods. "
        "Declare only needed finite typed formats, reusable procedures and working sets. "
        "Use only exact names from supported_operations in operations; put step descriptions "
        "in process/instructions. Reuse supplied answers, including forwarded originals; ask "
        "only missing user decisions. A minimal foundation must support a useful first action. "
        "Distinguish blocking questions from deferred extensions. Explain decisions and sources. "
        "Do not require Health, journals or calendar templates."
        " The person works through an assistant, not by reading or repairing files. "
        "Distinguish confirmed decisions, suggested defaults and unknowns. A question "
        "needed for a later procedure may be that procedure's first step, without "
        "blocking a usable initial foundation. Present all proposed questions for "
        "whole-structure review; do not confuse missing subject measurements with "
        "permission to create an Activity. Never require the user to repeat known facts."
    ),
    "correction": (
        "Correct the whole current ActivitySetupDraft using the complete review and original "
        "user sources. Fix causes and look for similar manifestations across all parts. "
        "Preserve supported capabilities, history and extensibility. Return the complete "
        "replacement draft matching result_schema, not a patch. Retain optional improvements "
        "for later; do not expand the owner's task."
    ),
    "review": (
        "Review the WHOLE current draft against the original user sources, not only earlier "
        "findings or a diff. Independently check every area in result_schema: goal, "
        "workflow, history, continuation, extension, capabilities and consistency. Name "
        "concrete material obstacles with causes; distinguish optional improvements and "
        "required user choices. Return ActivitySetupReview JSON matching result_schema, "
        "exact draft_ref and input_version. A structural review is not real-use evidence or "
        "owner acceptance. Do not run a fictional trial."
        " For contract_version 2, inspect the whole activation_manifest and initial draft; "
        "return exact manifest_ref. Give reasoned coverage for each area with existing component "
        "keys (process, first_path, formats.<key>, procedures.<key>, etc.). Verify event identity, "
        "corrections, periods, incomplete intake, current working sets and useful first path. "
        "Never mistake a list of seven area names for evidence."
        " Check every proposed question's blocking scope against the first useful "
        "path. Reject inconsistent claims that recording may start while activation "
        "is blocked by data needed only for later planning. Correct the whole design "
        "when such a question is misplaced. Genuine missing setup decisions remain "
        "questions for the owner; never invent their answers."
    ),
}


def _observe(function: Any, *args: Any, **kwargs: Any) -> Any:
    """Retry only known local lock contention; never a provider send."""
    for number in range(3):
        try:
            return function(*args, **kwargs)
        except FoundationError as error:
            contention = error.code == "busy" or (
                error.code == "storage"
                and any(
                    marker in error.detail.casefold()
                    for marker in ("sqlite_busy", "sqlite_locked", "locked")
                )
            )
            if number == 2 or not contention:
                raise
            time.sleep(0.05 * (number + 1))


class SetupCoordinator:
    """One window-owned coordinator; Core is its entire durable authority."""

    def __init__(self, bridge: Bridge, config: AssignedConfig) -> None:
        self.bridge = bridge
        self.config = config
        self.thread: threading.Thread | None = None
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.control_lock = threading.Lock()
        self.active: UUID | None = None
        self.selection: dict[str, Any] = {
            "id": config.model_id,
            "provider": config.provider_id,
            "thinking": config.thinking or "off",
        }

    def update_model(self, model: dict[str, Any]) -> None:
        if not model.get("id") or model.get("provider") != self.config.provider_id:
            raise FoundationError("unsupported_provider", "Use the admitted selected provider")
        with self.lock:
            self.selection = dict(model)

    def _step(self, identifier: UUID, action: str, **fields: Any) -> None:
        current = _observe(
            read_activity_setup, self.config.space, identifier, self.bridge.authority
        )
        _observe(
            apply_operation,
            self.config.space,
            ActivitySetupRequest(
                operation_id=uuid4(),
                space_id=self.bridge.authority.space_id,
                actor=self.bridge.authority.actor,
                setup_id=identifier,
                activity_id=current.state.activity_id,
                expected_revision=current.revision,
                action=cast(Any, action),
                **fields,
            ),
            self.bridge.authority,
        )

    def start(self, identifier: UUID, model: dict[str, Any]) -> None:
        with self.control_lock:
            self._start(identifier, model)

    def _start(self, identifier: UUID, model: dict[str, Any]) -> None:
        if not model.get("id") or model.get("provider") != self.config.provider_id:
            raise FoundationError(
                "unsupported_provider", "Setup must use the selected admitted Pi provider/model"
            )
        self.update_model(model)
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                if self.active == identifier:
                    return
                raise FoundationError(
                    "setup_running", "Another setup already runs in this Pi window"
                )
            self.config = replace(
                self.config,
                model_id=str(model["id"]),
                thinking=model.get("thinking"),
                disable_tools=False,
                restricted_tools=("zara_workflow", "zara_memory"),
                pi_tools=(),
            )
            self.stop.clear()
            self.active = identifier
            self.thread = threading.Thread(target=self._run, args=(identifier,), daemon=True)
            self.thread.start()

    def _run(self, identifier: UUID) -> None:
        try:
            while not self.stop.is_set():
                state = _observe(
                    read_activity_setup, self.config.space, identifier, self.bridge.authority
                ).state
                if state.phase in (
                    "needs_input",
                    "needs_attention",
                    "cancelled",
                    "ready",
                    "paused",
                ):
                    return
                if state.phase == "activating":
                    self._step(identifier, "finish")
                    return
                if (
                    not state.stages
                    or state.stages[-1].output is not None
                    or state.stages[-1].retired
                ):
                    kind = (
                        state.stages[-1].kind
                        if state.stages
                        and state.stages[-1].rejection
                        and state.stages[-1].input_version == state.input_version
                        else "draft"
                        if state.draft is None
                        else "correction"
                        if state.review is not None
                        else "review"
                    )
                    self._step(
                        identifier,
                        "start_stage",
                        stage_kind=kind,
                        stage_instruction=INSTRUCTIONS[kind]
                        + (
                            " Correct the rejected raw result using its typed diagnostics and "
                            "supported_operations. Return the whole result matching result_schema. "
                            "For review, inspect the whole current package again."
                            if state.stages and state.stages[-1].rejection
                            else ""
                        ),
                    )
                    state = _observe(
                        read_activity_setup, self.config.space, identifier, self.bridge.authority
                    ).state
                stage = state.stages[-1]
                snapshot = _observe(
                    read_execution, self.config.space, stage.work_id, self.bridge.authority
                )
                if not snapshot.outputs:
                    self._execute_stage(identifier, stage.work_id)
                if self.stop.is_set():
                    return
                snapshot = _observe(
                    read_execution, self.config.space, stage.work_id, self.bridge.authority
                )
                if not snapshot.outputs:
                    raise FoundationError(
                        "setup_output_missing", "Assigned setup stage did not retain an Artifact"
                    )
                output = snapshot.work.state.linked_outputs[0].artifact
                self._step(identifier, "complete_stage", output=output)
        except Exception as error:
            if not self.stop.is_set():
                try:
                    self._step(identifier, "attention", text=str(error)[:4096])
                except FoundationError:
                    # Losing authority/content cannot be repaired by another model send.
                    return

    def _execute_stage(self, setup_id: UUID, work_id: UUID) -> None:
        if self.stop.is_set():
            return
        authority = self.bridge.authority
        config = self.config
        setup = _observe(read_activity_setup, config.space, setup_id, authority)
        response = recover_response(config.space, work_id, authority)
        if response.outcome == "applied":
            return
        if response.outcome == "running":
            if setup.state.root_work_id is None:
                # A live legacy stage is already owned by its calling setup thread.
                # Reopening cannot recreate an unobserved RPC process.
                raise missing_executor(response)
            from .workflows import WorkflowCoordinator

            executor = WorkflowCoordinator(self.bridge, config)
            executor.stop = self.stop
            executor._execute_work(setup.state.root_work_id, work_id, config)
            return
        stage = next(item for item in reversed(setup.state.stages) if item.work_id == work_id)
        if stage.model is None and read_space(config.space).schema_version >= 16:
            with self.lock:
                selection = dict(self.selection)
            pinned = WorkflowModel(
                provider=str(selection["provider"]),
                model_id=str(selection["id"]),
                profile=config.provider_profile,
                reasoning=str(selection.get("thinking") or config.thinking or "off"),
            )
            self._step(setup_id, "bind_model", stage_model=pinned)
            setup = _observe(read_activity_setup, config.space, setup_id, authority)
            stage = next(item for item in reversed(setup.state.stages) if item.work_id == work_id)
        if stage.model is not None:
            if (stage.model.profile, stage.model.provider) != (
                config.provider_profile,
                config.provider_id,
            ):
                raise FoundationError(
                    "unsupported_provider", "Stored stage model differs from admission"
                )
            config = replace(config, model_id=stage.model.model_id, thinking=stage.model.reasoning)
        if setup.state.root_work_id is not None:
            from .workflows import WorkflowCoordinator

            node = read_workflow_node_for_work(config.space, work_id, authority)
            if node is None:
                raise FoundationError(
                    "wrong_work", "Setup stage is absent from its actual workflow"
                )
            executor = WorkflowCoordinator(self.bridge, config)
            executor.stop = self.stop
            executor._execute_node(setup.state.root_work_id, node)
            return
        snapshot = _observe(read_execution, self.config.space, work_id, authority)
        resource_id = uuid5(work_id, "setup-resource")
        if not snapshot.resources:
            apply_operation(
                self.config.space,
                CreateResourceRequest(
                    operation_id=uuid5(work_id, "create-resource"),
                    space_id=authority.space_id,
                    actor=authority.actor,
                    resource_id=resource_id,
                    work_id=work_id,
                    state=ResourceState(
                        label="Activity setup",
                        root=config.workspace,
                        limit_units=config.limit_units,
                    ),
                ),
                authority,
            )
            snapshot = _observe(read_execution, self.config.space, work_id, authority)
        if snapshot.assignments and snapshot.assignments[-1].status in (
            "assigned",
            "waiting",
            "ready",
            "stop_requested",
        ):
            attempt_id = snapshot.assignments[-1].attempt_id
        else:
            attempt_id = uuid4()
            apply_operation(
                self.config.space,
                AssignAttemptRequest(
                    operation_id=uuid5(attempt_id, "assign"),
                    space_id=authority.space_id,
                    actor=authority.actor,
                    attempt_id=attempt_id,
                    work_id=work_id,
                    expected_work_revision=snapshot.work.revision,
                    resource_id=resource_id,
                    expected_resource_revision=snapshot.resources[0].revision,
                    session_id=uuid4(),
                    previous_attempt_id=snapshot.attempts[-1].attempt_id
                    if snapshot.attempts
                    else None,
                    executor_version=EXECUTOR_VERSION,
                ),
                authority,
            )
        payload = {
            "config": {
                key: str(value) if isinstance(value, Path) else value
                for key, value in asdict(config).items()
            },
            "actor": authority.actor,
            "setup_id": str(setup_id),
            "attempt_id": str(attempt_id),
        }
        # A child process isolates DBOS globals and still uses the ordinary executor.
        environment = os.environ.copy()
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        if self.stop.is_set():
            self._stop_stage(work_id)
            return
        process = subprocess.Popen(
            [sys.executable, "-X", "utf8", "-m", "zaratustra.pi_adapter.activity_setup"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            creationflags=creationflags,
        )
        assert process.stdin is not None
        process.stdin.write(json.dumps(payload).encode("utf-8"))
        process.stdin.close()
        process.stdin = None
        # Drain continuously, retaining a bounded diagnostic tail, never provider bodies.
        tails = [bytearray(), bytearray()]

        def drain(stream: Any, tail: bytearray) -> None:
            for chunk in iter(lambda: stream.read(4096), b""):
                tail.extend(chunk)
                if len(tail) > 16384:
                    del tail[:-16384]

        readers = [
            threading.Thread(target=drain, args=(stream, tail), daemon=True)
            for stream, tail in zip((process.stdout, process.stderr), tails, strict=True)
        ]
        for reader in readers:
            reader.start()
        while process.poll() is None:
            if self.stop.wait(0.2):
                self._stop_stage(work_id)
            snapshot = _observe(read_execution, self.config.space, work_id, authority)
            opened = next((item for item in snapshot.waits if item.status == "open"), None)
            state = _observe(read_activity_setup, self.config.space, setup_id, authority).state
            if opened is not None and state.question != opened.question:
                self._step(setup_id, "question", text=opened.question)
        for reader in readers:
            reader.join(timeout=2)
        if process.returncode and not self.stop.is_set():
            detail = tails[1].decode("utf-8", errors="replace")[-4096:]
            raise FoundationError(
                "setup_executor", detail or f"Setup runner exited {process.returncode}"
            )

    def _stop_stage(self, work_id: UUID) -> None:
        authority = self.bridge.authority
        snapshot = _observe(read_execution, self.config.space, work_id, authority)
        for assignment in snapshot.assignments:
            if assignment.status not in ("assigned", "waiting", "ready"):
                continue
            attempt = next(
                item for item in snapshot.attempts if item.attempt_id == assignment.attempt_id
            )
            apply_operation(
                self.config.space,
                RequestAttemptStopRequest(
                    operation_id=uuid5(assignment.attempt_id, "setup-window-stop"),
                    space_id=authority.space_id,
                    actor=authority.actor,
                    work_id=work_id,
                    attempt_id=assignment.attempt_id,
                    session_id=attempt.session_id,
                    expected_assignment_revision=assignment.revision,
                    reason="Activity setup window closed or paused",
                ),
                authority,
            )

    def request_pause(self, setup_id: UUID | None = None, *, expected_thread: Any = ...) -> None:
        with self.control_lock:
            if expected_thread is not ... and self.thread not in (None, expected_thread):
                raise FoundationError("stale_session", "A later executor owns this setup")
            self._request_pause(setup_id)

    def _request_pause(self, setup_id: UUID | None = None) -> None:
        """Persist an addressed stop request without joining a live RPC worker."""
        with self.lock:
            if setup_id is not None and self.active != setup_id:
                return
            identifier = self.active
        try:
            if identifier is not None:
                state = _observe(
                    read_activity_setup, self.config.space, identifier, self.bridge.authority
                ).state
                if state.phase not in (
                    "ready",
                    "cancelled",
                    "needs_attention",
                    "needs_input",
                    "paused",
                ):
                    # Core stores the pause and exact assignment stops together.
                    # A separate snapshot-based stop can race its live executor
                    # and prevent this durable pause from ever being requested.
                    self._step(
                        identifier,
                        "pause",
                        text="Pi window closed; retained continuation",
                        auto_resume=True,
                    )
        finally:
            # Local teardown follows the saved Core intent. Even a refused pause
            # stops future dispatch, but its refusal remains visible to callers.
            self.stop.set()

    def close(self, setup_id: UUID | None = None) -> None:
        try:
            self.request_pause(setup_id)
        finally:
            with self.lock:
                thread = self.thread if setup_id is None or self.active == setup_id else None
            if thread is not None:
                thread.join(timeout=15)


def worker() -> int:
    """Internal parent-started worker; never an interactive public entry point."""
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
    fields["pi_tools"] = tuple(fields.get("pi_tools", ()))
    fields["restricted_tools"] = tuple(fields.get("restricted_tools", ()))
    config = AssignedConfig(**fields)
    if (
        not config.disable_tools and config.restricted_tools != ("zara_workflow", "zara_memory")
    ) or config.provider_profile not in (
        "codex-sse",
        "local-completions",
    ):
        raise FoundationError("permission_denied", "Internal setup worker has a restricted profile")
    authority = authorize_local(
        config.space, actor=str(raw["actor"]), source_ref=f"activity-setup-worker:{raw['setup_id']}"
    )
    setup = read_activity_setup(config.space, UUID(raw["setup_id"]), authority)
    attempt = UUID(raw["attempt_id"])
    if setup.state.owner != authority.actor or not setup.state.stages:
        raise FoundationError("permission_denied", "Worker does not belong to this setup")
    snapshot = _observe(read_execution, config.space, setup.state.stages[-1].work_id, authority)
    if not any(item.attempt_id == attempt for item in snapshot.assignments):
        raise FoundationError("wrong_work", "Worker Attempt belongs to another Work")
    run_assigned(config, authority, attempt)
    return 0


if __name__ == "__main__":
    raise SystemExit(worker())
