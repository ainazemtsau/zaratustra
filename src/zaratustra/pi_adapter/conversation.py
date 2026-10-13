"""Native conversation effects over the public Core delivery contract."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4

from zaratustra.foundation import (
    ConversationActionRef,
    ConversationDeliveryRequest,
    FoundationError,
    StopAttemptRequest,
    apply_operation,
    current_conversation_action,
    read_conversation_action,
    read_conversation_actions_page,
    read_execution,
    read_ordinary_final_proof,
    read_space,
    read_work,
)


def conversation(bridge: Any, session_id: UUID, raw: dict[str, Any]) -> dict[str, object]:
    """Only the native host can claim/deliver; model tools can discover/select."""
    bridge._session(session_id)
    if bridge.assigned_attempt_id is not None:
        raise FoundationError("permission_denied", "Assigned nodes cannot drive owner conversation")
    mode = str(raw.get("mode", "catalog"))
    if read_space(bridge.path).schema_version < 17:
        if mode == "catalog":
            return {"items": [], "upgrade_required": True}
        raise FoundationError("upgrade_required", "Conversation continuation needs schema 17")
    if mode == "catalog":
        limit, offset = int(raw.get("limit", 20)), int(raw.get("offset", 0))
        page = read_conversation_actions_page(
            bridge.path, bridge.authority, limit=limit, offset=offset
        )
        return {
            "items": [item.model_dump(mode="json") for item in page.actions],
            "next_offset": page.next_offset,
            "scanned": page.scanned,
        }
    if mode == "current":
        action = current_conversation_action(
            bridge.path, UUID(str(raw["subject_id"])), bridge.authority
        )
        return {"item": action.model_dump(mode="json") if action is not None else None}
    if mode == "host":
        host = {key: str(raw[key]) for key in ("host_id", "branch_id")}
        bridge.conversation_hosts[session_id] = host
        return {"registered": True}
    if mode == "restore":
        work_id = UUID(str(raw["work_id"]))
        selected = bridge._selection(session_id)
        if selected.work_id != work_id:
            raise FoundationError("wrong_work", "Restore only the saved selected Work")
        execution = read_execution(bridge.path, work_id, bridge.authority)
        active = [item for item in execution.attempts if item.status == "active"]
        if not active:
            return {
                "selection": {"activity_id": str(selected.activity_id), "work_id": str(work_id)},
                "completed_observed": False,
            }
        for attempt in active:
            proof = read_ordinary_final_proof(
                bridge.path, work_id, bridge.authority, attempt_id=attempt.attempt_id
            )
            if proof is None:
                bridge.sessions[session_id] = None
                bridge.recovery_obstacles[session_id] = work_id
                return {
                    "selection": None,
                    "completed_observed": False,
                    "obstacle": "Saved execution needs inspection; conversation remains available",
                }
            from uuid import uuid5

            apply_operation(
                bridge.path,
                StopAttemptRequest(
                    operation_id=uuid5(
                        attempt.attempt_id, "native-final:" + str(proof.assistant_source)
                    ),
                    space_id=bridge.authority.space_id,
                    actor=bridge.authority.actor,
                    attempt_id=attempt.attempt_id,
                    work_id=work_id,
                    session_id=attempt.session_id,
                    outcome="completed",
                    observed_final=proof,
                ),
                bridge.authority,
            )
        return {
            "selection": {"activity_id": str(selected.activity_id), "work_id": str(work_id)},
            "completed_observed": True,
        }
    ref = ConversationActionRef.model_validate(raw["action_ref"])
    if mode in ("read", "use_existing_work", "interrupt_execution"):
        action = read_conversation_action(bridge.path, ref, bridge.authority)
        if mode == "read":
            return action.model_dump(mode="json")
        bridge._fresh_user_source(session_id, raw.get("answer_source"))
        if action.work_id is None:
            raise FoundationError("invalid_request", "This action has no ordinary Work to select")
        work = read_work(bridge.path, action.work_id, bridge.authority)
        if work.state.status != "proposed":
            raise FoundationError("closed_work", "Select only an existing proposed Work")
        execution = read_execution(bridge.path, action.work_id, bridge.authority)
        active = [item for item in execution.attempts if item.status == "active"]
        if mode == "interrupt_execution":
            if raw.get("confirmed") is not True:
                raise FoundationError(
                    "permission_denied", "Interrupt needs native owner confirmation"
                )
            if execution.assignments or execution.composition:
                raise FoundationError(
                    "wrong_work", "Assigned/composite execution uses its coordinator"
                )
            from uuid import uuid5

            source, _ = bridge._fresh_user_source(session_id, raw.get("answer_source"))
            for attempt in active:
                apply_operation(
                    bridge.path,
                    StopAttemptRequest(
                        operation_id=uuid5(
                            source.record_id, "interrupt:" + str(attempt.attempt_id)
                        ),
                        space_id=bridge.authority.space_id,
                        actor=bridge.authority.actor,
                        attempt_id=attempt.attempt_id,
                        work_id=action.work_id,
                        session_id=attempt.session_id,
                        outcome="interrupted",
                    ),
                    bridge.authority,
                )
            bridge.recovery_obstacles.pop(session_id, None)
            return {"interrupted": [str(item.attempt_id) for item in active], "accepted": False}
        if active:
            raise FoundationError(
                "recovery_required",
                "Old execution remains active; inspect or interrupt it before selection",
            )
        snapshot = bridge.select(session_id, action.activity_id, action.work_id)
        return {
            "selection": {"activity_id": str(action.activity_id), "work_id": str(action.work_id)},
            "snapshot": snapshot,
            "accepted": False,
        }
    host = bridge.conversation_hosts.get(session_id)
    if host is None or any(str(raw.get(key)) != host[key] for key in host):
        raise FoundationError("stale_session", "Conversation native branch changed")
    fields = {
        key: raw[key]
        for key in ("manifest", "invocation_id", "assistant_source", "assistant_entry_id", "fenced")
        if raw.get(key) is not None
    }
    receipt = apply_operation(
        bridge.path,
        ConversationDeliveryRequest(
            operation_id=UUID(str(raw.get("operation_id", uuid4()))),
            space_id=bridge.authority.space_id,
            actor=bridge.authority.actor,
            action=cast(Any, mode),
            delivery_id=UUID(str(raw["delivery_id"])),
            action_ref=ref,
            session_id=session_id,
            **host,
            **fields,
        ),
        bridge.authority,
    )
    if mode == "claim":
        bridge.conversation_actions[session_id] = ref
    elif mode in ("respond", "unknown", "abandon"):
        bridge.conversation_actions.pop(session_id, None)
    return cast(dict[str, object], receipt.model_dump(mode="json"))
