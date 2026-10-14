"""Native conversation effects over the public Core delivery contract."""

from __future__ import annotations

import json
from typing import Any, cast
from uuid import UUID, uuid4, uuid5

from zaratustra.foundation import (
    ConversationActionRef,
    ConversationDeliveryRequest,
    FoundationError,
    StopAttemptRequest,
    apply_operation,
    current_conversation_action,
    list_conversation_deliveries,
    read_conversation_action,
    read_conversation_actions_page,
    read_conversation_delivery,
    read_execution,
    read_ordinary_final_proof,
    read_space,
    read_work,
)


def delivery_summaries(bridge: Any, actions: list[Any]) -> list[dict[str, object]]:
    """Bounded exact-current delivery facts, without loading their original bodies."""
    summaries = []
    for action in actions:
        deliveries = list_conversation_deliveries(
            bridge.path, bridge.authority, action_id=action.ref.action_id, limit=1
        )
        if deliveries and deliveries[0].action_ref == action.ref:
            summaries.append(deliveries[0].model_dump(mode="json"))
    return summaries


def conversation(bridge: Any, session_id: UUID, raw: dict[str, Any]) -> dict[str, object]:
    """Only the native host can claim/deliver; model tools can discover/select."""
    bridge._session(session_id)
    if bridge.assigned_attempt_id is not None:
        raise FoundationError("permission_denied", "Assigned nodes cannot drive owner conversation")
    mode = str(raw.get("mode", "catalog"))
    if mode == "host":
        native_host = {key: str(raw[key]) for key in ("host_id", "branch_id")}
        native_host["generation"] = str(int(raw.get("generation", 0)))
        previous = bridge.conversation_hosts.get(session_id)
        if previous is not None and previous != native_host:
            with bridge.lock:
                bridge.response_only.pop(session_id, None)
                bridge.request_origins[session_id] = "history"
                bridge.request_sources[session_id] = ()
        bridge.conversation_hosts[session_id] = native_host
        return {"registered": True}
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
            "delivery_outcomes": delivery_summaries(bridge, list(page.actions)),
        }
    if mode == "current":
        action = current_conversation_action(
            bridge.path, UUID(str(raw["subject_id"])), bridge.authority
        )
        return {
            "item": action.model_dump(mode="json") if action is not None else None,
            "delivery_outcomes": delivery_summaries(bridge, [action]) if action is not None else [],
        }
    if mode == "delivery":
        delivery = read_conversation_delivery(
            bridge.path, UUID(str(raw["delivery_id"])), bridge.authority
        )
        return delivery.model_dump(mode="json")
    if mode in ("terminal", "response_only"):
        return cast(dict[str, object], bridge.native_response_mode(session_id, raw))
    if mode == "restore":
        work_id = UUID(str(raw["work_id"]))
        selected = bridge._selection(session_id)
        if selected.work_id != work_id:
            raise FoundationError("wrong_work", "Restore only the saved selected Work")
        execution = read_execution(bridge.path, work_id, bridge.authority)
        active = [item for item in execution.attempts if item.status == "active"]
        cleanup_unsent = raw.get("cleanup_unsent") is True
        addressed = UUID(str(raw["attempt_id"])) if raw.get("attempt_id") else None
        if cleanup_unsent and addressed is None:
            raise FoundationError("invalid_request", "Cleanup requires the exact current Attempt")
        if (
            addressed is not None
            and active
            and all(item.attempt_id != addressed for item in active)
        ):
            raise FoundationError("stale_attempt", "Another Attempt is active")
        if addressed is not None:
            active = [item for item in active if item.attempt_id == addressed]
        if not active:
            return {
                "selection": {"activity_id": str(selected.activity_id), "work_id": str(work_id)},
                "completed_observed": False,
            }
        interrupted_unsent = False
        for attempt in active:
            proof = read_ordinary_final_proof(
                bridge.path, work_id, bridge.authority, attempt_id=attempt.attempt_id
            )
            if proof is None:
                if cleanup_unsent:
                    try:
                        apply_operation(
                            bridge.path,
                            StopAttemptRequest(
                                operation_id=uuid5(attempt.attempt_id, "native-unsent-cleanup"),
                                space_id=bridge.authority.space_id,
                                actor=bridge.authority.actor,
                                attempt_id=attempt.attempt_id,
                                work_id=work_id,
                                session_id=session_id,
                                outcome="interrupted",
                                no_send_only=True,
                            ),
                            bridge.authority,
                        )
                        interrupted_unsent = True
                        continue
                    except FoundationError as error:
                        if error.code != "attempt_send_observed":
                            raise
                bridge.sessions[session_id] = None
                bridge.recovery_obstacles[session_id] = work_id
                return {
                    "selection": None,
                    "completed_observed": False,
                    "obstacle": "Saved execution needs inspection; conversation remains available",
                }
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
            "completed_observed": not interrupted_unsent,
            "interrupted_unsent": interrupted_unsent,
        }
    ref = ConversationActionRef.model_validate(raw["action_ref"])
    if mode in ("read", "use_existing_work", "interrupt_execution"):
        action = read_conversation_action(bridge.path, ref, bridge.authority)
        if mode == "read":
            return {
                **action.model_dump(mode="json"),
                "delivery_outcomes": delivery_summaries(bridge, [action]),
            }
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
    registered = bridge.conversation_hosts.get(session_id)
    host = {key: registered[key] for key in ("host_id", "branch_id")} if registered else None
    if host is None or any(str(raw.get(key)) != host[key] for key in host):
        raise FoundationError("stale_session", "Conversation native branch changed")
    fields = {
        key: raw[key]
        for key in (
            "manifest",
            "invocation_id",
            "assistant_source",
            "assistant_entry_id",
            "fenced",
            "response_problem",
        )
        if raw.get(key) is not None
    }
    operation_id = UUID(str(raw["operation_id"])) if raw.get("operation_id") else uuid4()
    if not raw.get("operation_id") and mode in (
        "observe_terminal",
        "repair_response",
        "respond",
        "response_attention",
    ):
        current_delivery = read_conversation_delivery(
            bridge.path, UUID(str(raw["delivery_id"])), bridge.authority
        )
        identity = json.dumps(
            {
                "action": mode,
                "invocation": raw.get("invocation_id") or str(current_delivery.invocation_id),
                "source": raw.get("assistant_source"),
                "entry": raw.get("assistant_entry_id"),
                "problem": raw.get("response_problem"),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        operation_id = uuid5(current_delivery.delivery_id, identity)
    receipt = apply_operation(
        bridge.path,
        ConversationDeliveryRequest(
            operation_id=operation_id,
            space_id=bridge.authority.space_id,
            actor=bridge.authority.actor,
            action=cast(Any, mode),
            delivery_id=UUID(str(raw["delivery_id"])),
            action_ref=ref,
            session_id=session_id,
            host_id=host["host_id"],
            branch_id=host["branch_id"],
            **fields,
        ),
        bridge.authority,
    )
    if mode == "claim":
        bridge.conversation_actions[session_id] = ref
    elif mode in ("respond", "unknown", "abandon", "response_attention") or (
        mode == "observe_terminal" and receipt.result.get("status") == "unknown"
    ):
        bridge.conversation_actions.pop(session_id, None)
    return cast(dict[str, object], receipt.model_dump(mode="json"))
