"""Addressed, transient observation of existing Core process boundaries."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from zaratustra.foundation import (
    FoundationError,
    current_conversation_action,
    read_activity_setup,
    read_attempt_response,
    read_execution,
    read_space,
    read_workflow_run,
)

type BoundaryKind = Literal[
    "running", "question", "result", "paused", "cancelled", "attention", "stopped"
]


class ProcessTarget(BaseModel):
    """Stable target captured by a native lifecycle tool, never UI selection."""

    model_config = {"extra": "forbid", "frozen": True}
    kind: Literal["setup", "workflow", "procedure"]
    id: UUID


class ProcessBoundary(BaseModel):
    """A derived tool return, not stored workflow state or delivery authority."""

    model_config = {"extra": "forbid", "frozen": True}
    kind: BoundaryKind
    target: ProcessTarget
    revision: int = Field(ge=1)
    details: dict[str, Any]
    action: dict[str, Any] | None = None
    execution: dict[str, Any]
    lease_token: UUID | None = None


@dataclass(frozen=True)
class ObservationLease:
    target: ProcessTarget
    generation: int
    branch_id: str
    token: UUID
    controller: Any
    thread: Any


def _controller(bridge: Any, target: ProcessTarget) -> Any:
    return getattr(bridge, target.kind + "_controller")


def _runtime(bridge: Any, target: ProcessTarget, work_id: UUID | None = None) -> dict[str, Any]:
    controller = _controller(bridge, target)
    expected = work_id if target.kind == "procedure" else target.id
    owned = controller is not None and controller.active == expected
    thread = controller.thread if owned else None
    alive = thread is not None and thread.is_alive()
    stopping = owned and controller.stop.is_set()
    return {"owned": owned, "alive": alive, "stop_requested": bool(stopping)}


def _execution_facts(snapshot: Any) -> dict[str, Any]:
    return {
        "work_id": str(snapshot.work.work_id),
        "work_revision": snapshot.work.revision,
        "assignments": [item.model_dump(mode="json") for item in snapshot.assignments],
        "unresolved_invocations": [
            str(item.invocation_id)
            for item in snapshot.invocations
            if item.status in ("admitted", "sent", "unknown")
        ],
        "unknown": any(item.status == "unknown" for item in snapshot.invocations)
        or any(item.status == "unknown" for item in snapshot.assignments),
    }


def read_process_boundary(bridge: Any, target: ProcessTarget) -> ProcessBoundary:
    """Read current rights and saved effects without holding a runtime lock."""
    action_subject = target.id
    kind: BoundaryKind
    waits: list[dict[str, Any]] = []
    facts: dict[str, Any] = {}
    if target.kind == "setup":
        # Observe executor liveness first. A completed executor has already
        # committed its effects; the following Core read sees that boundary.
        runtime = _runtime(bridge, target)
        current = read_activity_setup(bridge.path, target.id, bridge.authority)
        state = current.state
        revision = current.revision
        details = current.model_dump(mode="json")
        if state.stages:
            snapshot = read_execution(bridge.path, state.stages[-1].work_id, bridge.authority)
            facts = _execution_facts(snapshot)
            facts["response"] = read_attempt_response(
                bridge.path, state.stages[-1].work_id, bridge.authority
            ).model_dump(mode="json")
            waits.extend(
                item.model_dump(mode="json") for item in snapshot.waits if item.status == "open"
            )
        if state.root_work_id is not None:
            view = read_workflow_run(bridge.path, state.root_work_id, bridge.authority)
            waits.extend(item.model_dump(mode="json") for item in view.waits)
        if state.question is not None:
            waits.insert(0, {"question": state.question, "setup_id": str(target.id)})
        kind = (
            "result"
            if state.phase == "ready"
            else "cancelled"
            if state.phase == "cancelled"
            else "paused"
            if state.phase == "paused"
            else "attention"
            if state.phase == "needs_attention"
            else "question"
            if waits
            else "running"
        )
        # A collecting setup has no executing stage and needs an explicit submit.
        if kind == "running" and state.phase == "collecting" and not runtime["alive"]:
            kind = "stopped"
            runtime["reason"] = "setup_collecting"
    elif target.kind == "workflow":
        runtime = _runtime(bridge, target)
        view = read_workflow_run(bridge.path, target.id, bridge.authority)
        revision = view.revision
        details = view.model_dump(mode="json")
        waits = [item.model_dump(mode="json") for item in view.waits]
        snapshot = read_execution(bridge.path, target.id, bridge.authority)
        for node in view.nodes:
            if not node.retired and node.output is None:
                node_snapshot = read_execution(bridge.path, node.work_id, bridge.authority)
                node_facts = _execution_facts(node_snapshot)
                node_facts["response"] = read_attempt_response(
                    bridge.path, node.work_id, bridge.authority
                ).model_dump(mode="json")
                if node_facts["unknown"] or node_facts["unresolved_invocations"]:
                    facts.setdefault("nodes", []).append(node_facts)
                elif node_facts["response"]["outcome"] in ("recoverable", "attention"):
                    facts.setdefault("nodes", []).append(node_facts)
        kind = (
            "cancelled"
            if view.control == "cancelled"
            else "paused"
            if view.control == "paused"
            else "question"
            if waits
            else "attention"
            if view.next_action in ("attention", "owner_action")
            else "result"
            if view.next_action == "closed" and snapshot.work.state.linked_outputs
            else "stopped"
            if view.next_action == "closed"
            else "running"
        )
    else:
        from .procedures import procedure_view

        details = procedure_view(bridge.path, bridge.authority, target.id)
        work_id = UUID(details["work_id"])
        action_subject = work_id
        snapshot = read_execution(bridge.path, work_id, bridge.authority)
        revision = snapshot.work.revision
        details.update(work_revision=revision, work=snapshot.work.state.model_dump(mode="json"))
        runtime = _runtime(bridge, target, work_id)
        facts = _execution_facts(snapshot)
        waits = [item.model_dump(mode="json") for item in snapshot.waits if item.status == "open"]
        kind = (
            "question"
            if waits
            else "result"
            if snapshot.work.state.linked_outputs
            else "cancelled"
            if snapshot.work.state.status == "cancelled"
            else "stopped"
            if snapshot.work.state.status != "proposed"
            else "running"
        )
    details["questions"] = waits
    runtime.update(facts)
    if kind == "running" and (
        facts.get("unknown") or any(item["unknown"] for item in facts.get("nodes", []))
    ):
        kind = "attention"
        runtime["reason"] = "unresolved_execution"
    if kind == "running" and not runtime["alive"]:
        unresolved = facts.get("unresolved_invocations") or any(
            item["unresolved_invocations"] for item in facts.get("nodes", [])
        )
        kind = "attention" if unresolved or facts.get("unknown") else "stopped"
        runtime["reason"] = "unresolved_execution" if kind == "attention" else "executor_absent"
    action = (
        current_conversation_action(bridge.path, action_subject, bridge.authority)
        if read_space(bridge.path).schema_version >= 17
        else None
    )
    return ProcessBoundary(
        kind=kind,
        target=target,
        revision=revision,
        details=details,
        action=action.model_dump(mode="json") if action is not None else None,
        execution=runtime,
    )


def process_boundary(bridge: Any, session_id: UUID, raw: dict[str, Any]) -> dict[str, Any]:
    """Bounded native observation/cancel with branch and executor fencing."""
    bridge._session(session_id)
    if bridge.assigned_attempt_id is not None:
        raise FoundationError("permission_denied", "Assigned nodes cannot observe owner processes")
    target = ProcessTarget.model_validate(raw["target"])
    generation = int(raw["generation"])
    key = str(raw["operation_key"])
    timeout = float(raw.get("timeout_seconds", 0))
    if not key or not 0 <= timeout <= 20:
        raise FoundationError("invalid_request", "Use a native operation and a bounded observation")
    mode = raw.get("mode", "observe")
    if mode not in ("observe", "pause"):
        raise FoundationError("invalid_request", "Unknown native observation action")
    host = bridge.conversation_hosts.get(session_id)
    if host is None or int(host.get("generation", -1)) != generation:
        raise FoundationError("stale_session", "Native process observation branch changed")
    with bridge.lock:
        lease = bridge.process_observations.get((session_id, key))
        if lease is None:
            if mode != "observe":
                raise FoundationError(
                    "stale_session", "Pause requires a captured process observation"
                )
            controller = _controller(bridge, target)
            lease = ObservationLease(
                target,
                generation,
                host["branch_id"],
                uuid4(),
                controller,
                controller.thread if controller is not None else None,
            )
            bridge.process_observations[session_id, key] = lease
        if (lease.target, lease.generation, lease.branch_id) != (
            target,
            generation,
            host["branch_id"],
        ):
            raise FoundationError("stale_session", "Observation belongs to a different process")
        if raw.get("lease_token") is not None and str(raw["lease_token"]) != str(lease.token):
            raise FoundationError("stale_session", "Observation executor identity changed")
    if mode == "pause":
        if raw.get("lease_token") is None:
            raise FoundationError("invalid_request", "Pause requires its exact observation lease")
        controller = _controller(bridge, target)
        if controller is not lease.controller or (
            controller is not None
            and controller.thread is not None
            and controller.thread is not lease.thread
        ):
            raise FoundationError("stale_session", "A later execution owns this process")
        if controller is not None:
            controller.request_pause(target.id, expected_thread=lease.thread)
    deadline = time.monotonic() + timeout
    while True:
        current_host = bridge.conversation_hosts.get(session_id)
        if current_host != host:
            raise FoundationError("stale_session", "Native process observation was replaced")
        boundary = read_process_boundary(bridge, target)
        if mode == "pause" or boundary.kind != "running" or time.monotonic() >= deadline:
            return boundary.model_copy(update={"lease_token": lease.token}).model_dump(mode="json")
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))
