"""Native selection choices use the existing guarded ordinary Attempt stop."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid5

from zaratustra.foundation import (
    CreateKnowledgeRequest,
    FoundationError,
    KnowledgeRef,
    NativeSelectionObservation,
    OrdinarySelectionTransition,
    SelectionTarget,
    SourceState,
    StopAttemptRequest,
    apply_operation,
    read_execution,
    read_knowledge,
    read_work,
)
from zaratustra.workspace import select_work_project


def work_target(bridge: Any, identifier: UUID, mode: str = "ordinary") -> SelectionTarget:
    work = read_work(bridge.path, identifier, bridge.authority)
    if work.state.status != "proposed":
        raise FoundationError("closed_work", "Select only a proposed Work")
    return SelectionTarget.model_validate(
        {"mode": mode, "work_id": identifier, "work_revision": work.revision}
    )


def _host(bridge: Any, session: UUID, raw: dict[str, Any]) -> None:
    registered = bridge.conversation_hosts.get(session)
    if not registered or any(
        str(raw.get(key)) != str(registered[key]) for key in ("host_id", "branch_id", "generation")
    ):
        raise FoundationError("stale_session", "Native selection branch changed")


def _target(bridge: Any, value: Any) -> SelectionTarget:
    target = SelectionTarget.model_validate(value)
    if target.work_id is not None:
        current = read_work(bridge.path, target.work_id, bridge.authority)
        if current.revision != target.work_revision or current.state.status != "proposed":
            raise FoundationError("stale_work", "The selected target Work changed")
        if target.mode == "ordinary":
            execution = read_execution(bridge.path, target.work_id, bridge.authority)
            if execution.composition or any(
                item.status in ("assigned", "waiting", "ready", "stop_requested", "unknown")
                for item in execution.assignments
            ):
                raise FoundationError("wrong_work", "Assigned execution uses its coordinator")
    if target.root is not None:
        root = target.root.resolve()
        config = bridge._workspace_configuration()
        if config is None:
            if root != bridge.workspace:
                raise FoundationError("resource_unavailable", "Project must be registered locally")
        else:
            config.project_name(root)
        if not root.is_dir():
            raise FoundationError("resource_unavailable", "Selected project is unavailable")
        target = target.model_copy(update={"root": root})
    return target


def _original(
    bridge: Any, session: UUID, target: SelectionTarget, handoff: dict[str, Any], *, continued: bool
) -> tuple[KnowledgeRef, SourceState]:
    identifier = UUID(str(handoff["operation_id"]))
    departing = handoff.get("departing")
    historical_session = UUID(str(departing["session_id"])) if departing else session
    native = handoff.get("boundary")
    event = str(native["source_event_id"]) if native else f"selection:{identifier}"
    source_id = uuid5(bridge.authority.space_id, f"pi:{historical_session}:{event}")
    try:
        existing = read_knowledge(bridge.path, source_id, bridge.authority, revision=1)
    except FoundationError as error:
        if error.code != "not_found":
            raise
    else:
        state = existing.state
        if not isinstance(state, SourceState) or state.native_selection is None:
            raise FoundationError("invalid_selection_proof", "Native choice original is absent")
        if state.native_selection.target != target:
            raise FoundationError("operation_conflict", "Native choice names another target")
        return KnowledgeRef(record_id=source_id, revision=1), state
    if continued:
        raise FoundationError("selection_proof_missing", "Saved choice lacks native proof")
    observation: dict[str, Any] = {
        key: handoff[key] for key in ("origin", "host_id", "branch_id", "generation")
    }
    observation["target"] = target.model_dump(mode="json")
    if handoff["origin"] == "owner_tool":
        owner, _ = bridge._fresh_user_source(session, handoff.get("owner_source"))
        observation.update(
            owner_source=owner.model_dump(mode="json"),
            **{key: handoff[key] for key in ("tool_call_id", "tool_name", "arguments_json")},
        )
        if native is None:
            raise FoundationError("selection_proof_missing", "Tool choice needs native response")
        result = bridge.capture_source(
            historical_session,
            channel="conversation_assistant",
            content=str(native["content"]),
            source_event_id=event,
            input_source="pi-event",
            conversation_terminal=native["conversation_terminal"],
            native_selection=observation,
            retain_empty=True,
        )
        reference = KnowledgeRef.model_validate(result["source_ref"])
        retained = read_knowledge(bridge.path, reference.record_id, bridge.authority, revision=1)
        assert isinstance(retained.state, SourceState)
        return reference, retained.state
    bases = (
        (KnowledgeRef(record_id=target.work_id, revision=target.work_revision),)
        if target.work_id is not None and target.work_revision is not None
        else ()
    )
    state = SourceState(
        channel="core_operation",
        connection="ordinary-pi-selection",
        profile_revision=1,
        conversation_id=str(historical_session),
        source_event_id=f"{historical_session}:{event}",
        sender=bridge.authority.actor,
        media_type="application/json",
        capture="full",
        content=json.dumps(handoff.get("choice", {}), ensure_ascii=False).encode(),
        derived_from=bases,
        native_selection=NativeSelectionObservation.model_validate(observation),
    )
    apply_operation(
        bridge.path,
        CreateKnowledgeRequest(
            operation_id=uuid5(source_id, "capture"),
            space_id=bridge.authority.space_id,
            actor=bridge.authority.actor,
            record_id=source_id,
            state=state,
        ),
        bridge.authority,
    )
    return KnowledgeRef(record_id=source_id, revision=1), state


def transition(
    bridge: Any,
    session: UUID,
    target_value: Any,
    raw: dict[str, Any],
    *,
    continued: bool = False,
) -> dict[str, Any]:
    """Stop the departing ordinary pin before committing any new selection."""
    # Native branch registration and origin binding use this same admission
    # lock. They cannot supersede the checked host before Core commits its stop.
    # No executor launch, process observation or cleanup wait occurs here.
    with bridge.lock:
        return _transition_locked(bridge, session, target_value, raw, continued=continued)


def _transition_locked(
    bridge: Any,
    session: UUID,
    target_value: Any,
    raw: dict[str, Any],
    *,
    continued: bool,
) -> dict[str, Any]:
    if bridge.assigned_attempt_id is not None or session in bridge.response_only:
        raise FoundationError("permission_denied", "This execution cannot change selection")
    target = _target(bridge, target_value)
    selected = bridge._session(session)
    handoff = raw.get("selection_handoff")
    current = read_execution(bridge.path, selected.work_id, bridge.authority) if selected else None
    active = [item for item in current.attempts if item.status == "active"] if current else []
    if target.mode == "ordinary" and target.work_id is not None:
        destination = read_execution(bridge.path, target.work_id, bridge.authority)
        if any(
            item.status == "active"
            and (
                selected is None or selected.work_id != target.work_id or item.session_id != session
            )
            for item in destination.attempts
        ):
            raise FoundationError("recovery_required", "Inspect the target's existing execution")
    same_work = selected is not None and target.work_id == selected.work_id
    actual_root = bridge.workspace
    if same_work and current is not None:
        actual_resources = [item for item in current.resources if item.state.status == "active"]
        if len(actual_resources) > 1:
            raise FoundationError("resource_unavailable", "Selection needs one actual resource")
        if actual_resources:
            actual_root = actual_resources[0].state.root.resolve()
            config = bridge._workspace_configuration()
            if config is not None:
                config.project_name(actual_root)
    if same_work and active:
        assert current is not None
        resources = [item for item in current.resources if item.state.status == "active"]
        if len(resources) != 1:
            raise FoundationError("resource_unavailable", "Selection needs one actual resource")
        resource = resources[0]
        if (
            any(
                item.resource_id != resource.resource_id
                or item.resource_revision != resource.revision
                for item in active
            )
            or resource.state.root.resolve() != bridge.workspace
        ):
            raise FoundationError("stale_resource", "The departing resource pin changed")
    if (
        selected
        and target.mode == "ordinary"
        and target.work_id == selected.work_id
        and actual_root == bridge.workspace
        and (target.root is None or target.root.resolve() == bridge.workspace)
    ):
        return {
            "selection": _selection_json(selected),
            "changed": False,
            "preserve_attempt": bool(active),
        }
    if (
        target.mode == "project"
        and target.root == bridge.workspace
        and actual_root == bridge.workspace
    ):
        return {
            "selection": _selection_json(selected),
            "changed": False,
            "preserve_attempt": bool(active),
        }
    if handoff is None:
        if active:
            raise FoundationError("selection_proof_required", "Retain the native choice boundary")
        if target.mode == "assigned":
            bridge.sessions[session] = None
            return {"selection": None, "changed": selected is not None}
    else:
        _host(bridge, session, raw.get("current_host", handoff))
        if active and handoff.get("departing") is None:
            raise FoundationError("selection_proof_required", "The departing pin was not retained")
        if not continued and handoff.get("departing"):
            old = handoff["departing"]
            if not selected or str(selected.work_id) != str(old["work_id"]):
                raise FoundationError("stale_selection", "Departing selection changed")
        observation, original = _original(bridge, session, target, handoff, continued=continued)
        bridge.pending_selections[session] = {
            "handoff": handoff,
            "target": target.model_dump(mode="json"),
        }
        old = handoff.get("departing")
        receipt = None
        if old is not None:
            metadata = original.native_selection
            assert metadata is not None
            owner = metadata.owner_source if metadata.origin == "owner_tool" else observation
            assert owner is not None
            proof = OrdinarySelectionTransition(
                **{
                    key: old[key]
                    for key in (
                        "execution_epoch",
                        "work_revision",
                        "attempt_revision",
                        "resource_id",
                        "resource_revision",
                    )
                },
                owner_source=owner,
                observation=observation,
                boundary_source=observation
                if metadata.origin == "owner_tool"
                else handoff.get("boundary_source"),
                target=target,
            )
            receipt = apply_operation(
                bridge.path,
                StopAttemptRequest(
                    operation_id=uuid5(UUID(handoff["operation_id"]), "selection-stop"),
                    space_id=bridge.authority.space_id,
                    actor=bridge.authority.actor,
                    work_id=UUID(old["work_id"]),
                    attempt_id=UUID(old["attempt_id"]),
                    session_id=UUID(old["session_id"]),
                    outcome="interrupted",
                    selection_transition=proof,
                ),
                bridge.authority,
            )
            bridge.sessions[session] = None
        bridge.selection_barriers[session] = str(handoff["operation_id"])
        # The pending choice survives a target/config refusal after committed stop.
    # Core checked this target with its stop. A separately admitted writer may
    # have changed it since that receipt; never commit a different target version.
    target = _target(bridge, target)
    if target.mode == "assigned":
        bridge.sessions[session] = None
    elif target.mode == "ordinary":
        assert target.work_id is not None
        work = read_work(bridge.path, target.work_id, bridge.authority)
        bridge.select(session, work.state.activity_id, target.work_id)
    else:
        assert target.root is not None
        config = bridge._workspace_configuration()
        if config is not None and target.work_id is not None:
            select_work_project(
                config,
                bridge.authority,
                target.work_id,
                config.project_name(target.root),
                operation_id=uuid5(UUID(handoff["operation_id"]), "project-selection")
                if handoff
                else None,
            )
        bridge.workspace = target.root.resolve()
        if target.work_id is not None:
            work = read_work(bridge.path, target.work_id, bridge.authority)
            bridge.select(session, work.state.activity_id, target.work_id)
    bridge.pending_selections.pop(session, None)
    return {
        "selection": _selection_json(bridge._session(session)),
        "changed": True,
        "preserve_attempt": False,
        "target": target.model_dump(mode="json"),
        **(
            {
                "observation": observation.model_dump(mode="json"),
                "receipt": receipt.model_dump(mode="json") if receipt else None,
            }
            if handoff is not None
            else {}
        ),
    }


def _selection_json(selected: Any) -> dict[str, str] | None:
    return (
        {"activity_id": str(selected.activity_id), "work_id": str(selected.work_id)}
        if selected
        else None
    )


def assigned_transition(bridge: Any, session: UUID, work: UUID, raw: dict[str, Any]) -> None:
    result = transition(bridge, session, work_target(bridge, work, "assigned"), raw)
    bridge.selection_results[session] = result


def unchanged(bridge: Any, session: UUID, raw: dict[str, Any]) -> dict[str, Any]:
    """An interview answer without an executor wake does not select another Work."""
    with bridge.lock:
        _host(bridge, session, raw["selection_handoff"])
        selected = bridge._session(session)
        current = (
            read_execution(bridge.path, selected.work_id, bridge.authority) if selected else None
        )
        return {
            "selection": _selection_json(selected),
            "changed": False,
            "preserve_attempt": bool(
                current and any(item.status == "active" for item in current.attempts)
            ),
        }


def pending_mode(bridge: Any, session: UUID, raw: dict[str, Any]) -> dict[str, Any]:
    with bridge.lock:
        return _pending_locked(bridge, session, raw)


def _pending_locked(bridge: Any, session: UUID, raw: dict[str, Any]) -> dict[str, Any]:
    _host(bridge, session, raw)
    mode = raw["mode"]
    if mode == "selection_recovery":
        old = raw["departing"]
        work = UUID(str(old["work_id"]))
        current = read_execution(bridge.path, work, bridge.authority)
        surviving = any(
            str(item.attempt_id) == str(old["attempt_id"])
            and str(item.session_id) == str(old["session_id"])
            and item.status == "active"
            for item in current.attempts
        )
        if surviving:
            bridge.recovery_obstacles[session] = work
        elif bridge.recovery_obstacles.get(session) == work:
            bridge.recovery_obstacles.pop(session, None)
        return {"recovery_obstacle": old if surviving else None}
    if mode == "selection_restore":
        pending = dict(raw["pending"])
        previous = bridge.pending_selections.get(session)
        if previous is not None and previous["handoff"] == pending["handoff"]:
            pending = {**pending, **previous}
        bridge.pending_selections[session] = pending
        bridge.sessions[session] = None
        bridge.selection_barriers[session] = str(pending["handoff"]["operation_id"])
        native = pending["handoff"].get("boundary")
        observation = None
        if native is not None:
            old = pending["handoff"].get("departing")
            historical_session = UUID(old["session_id"]) if old else session
            source_id = uuid5(
                bridge.authority.space_id, f"pi:{historical_session}:{native['source_event_id']}"
            )
            try:
                original = read_knowledge(bridge.path, source_id, bridge.authority, revision=1)
            except FoundationError as error:
                if error.code != "not_found":
                    raise
            else:
                if isinstance(original.state, SourceState) and original.state.native_selection:
                    observation = KnowledgeRef(record_id=source_id, revision=1).model_dump(
                        mode="json"
                    )
                    pending["target"] = original.state.native_selection.target.model_dump(
                        mode="json"
                    )
                    pending["observation"] = observation
        return {"pending": True, "selection": None, "observation": observation}
    bridge._fresh_user_source(session, raw.get("answer_source"))
    pending = bridge.pending_selections.get(session)
    if pending is None or str(raw["pending_id"]) != str(pending["handoff"]["operation_id"]):
        raise FoundationError("stale_selection", "The saved native choice changed")
    if mode == "cancel_selection":
        old = pending["handoff"].get("departing")
        recovery = None
        if old is not None:
            recovery = _pending_locked(
                bridge, session, {**raw, "mode": "selection_recovery", "departing": old}
            )["recovery_obstacle"]
        bridge.pending_selections.pop(session, None)
        bridge.selection_barriers.pop(session, None)
        return {
            "selection": None,
            "changed": True,
            "preserve_attempt": False,
            "cancelled": True,
            "accepted": False,
            "departing": old,
            "recovery_obstacle": recovery,
        }
    handoff = pending["handoff"]
    target = pending.get("target")
    if target is None:
        old = handoff.get("departing")
        native = handoff.get("boundary")
        historical_session = UUID(old["session_id"]) if old else session
        event = native["source_event_id"] if native else f"selection:{handoff['operation_id']}"
        ref = uuid5(bridge.authority.space_id, f"pi:{historical_session}:{event}")
        original = read_knowledge(bridge.path, ref, bridge.authority, revision=1)
        if not isinstance(original.state, SourceState) or original.state.native_selection is None:
            raise FoundationError("selection_proof_missing", "Native target is unavailable")
        target = original.state.native_selection.target
    return transition(
        bridge, session, target, {"selection_handoff": handoff, "current_host": raw}, continued=True
    )
