"""Versioned ordinary Activity protocol; meaning stays with the executor."""

from __future__ import annotations

import json
from typing import Any

from zaratustra_core import CoreError, digest

ROUTING_ID = "conversation-routing-method"
EXECUTION_ID = "conversation-execution-method"

ROUTING_METHOD = """conversation-routing/1
Choose the Activity for the exact pending human request and corrections in
raw_messages. Read the catalog and retained conversation before choosing.
Reuse an existing Activity only when it is the same work; preserve its identity,
kind/key/scope and exact current revision. A different request may need another
Activity in the same conversation. You choose all subject meaning and useful
organization; no domain router, compulsory interview or fixed project template.
Create or update a meaningful minimal Activity holding the actual agreed goal,
constraints and working arrangement. Internal durable bookkeeping does not mean
asking the person to create cards or delaying their requested practice.
Return typed changes and expected_heads, plus exact outputs containing the chosen
Activity ref. New IDs use expected_heads[id]=0; updates use the catalog revision.
Change shape: {id,kind,key,scope,body,source_refs?}. Body is the actual free text or
object, not a record wrapper. Allowed kinds activity/data; memory and Method need
explicit delegation. source_refs are subject record refs, never Work/message IDs.
Return one JSON object with state completed, text empty, changes, expected_heads,
outputs and next_work:{scope:chosen_activity_id,goal:the actual requested useful
work,inputs:[exact subject refs needed for that work]}. The host supplies identity,
conversation, finite remaining budget and the pinned execution Method. Do not
start the useful work or call zara_change in this discovery phase. Core atomically
publishes Activity + scoped continuation; the original human input stays pending
for that Work. This intermediate result is not a user response or acceptance.
"""

EXECUTION_METHOD = """conversation/2
Help with the original human request and corrections in raw_messages now, using
the Activity pinned in inputs and this Work's scope. Read applicable memory,
catalog, prior results/messages and exact versions. Choose the smallest useful
organization; do not impose an interview, setup project, planning document or
fixed template. Ask only questions needed for the requested result.
Preserve the Activity's stable identity and retain its actual current agreement,
constraints, progress and useful results in versioned Activity/data where needed
for continuation. A bare card with the real work only in chat is insufficient.
You choose the meaning and free text/object structure; no prescribed subject
fields or number of sections. The scoped final itself is also retained by Core.
Use zara_change for intermediate changes only when needed, or include changes
atomically with the terminal response. Allowed kinds activity/data; memory and
Method require explicit delegation. New IDs use expected_heads[id]=0; existing
IDs use their catalog revision, identical kind/key/scope, and a new body value.
Change shape: {id,kind,key,scope,body,source_refs?}; never record wrappers as body
or Work/message IDs as source_refs. Never mutate rights or execution status.
Return exactly one JSON object (no Markdown fences): state completed, text the
actual useful response, changes, expected_heads and outputs. Outputs must include
the exact chosen Activity revision and any useful subject data refs. For a needed
addressed question use state waiting and wait:{id:unique_id,question:text}, still
retaining the Activity/output refs. completed ends this bounded Work; it is not
owner acceptance, proof of truth or completion of the whole Activity.
"""


def response_contract(routing: bool) -> dict[str, Any]:
    return {
        "version": "ordinary-routing/1" if routing else "ordinary-execution/2",
        "terminal": (
            "JSON: state completed, text empty, changes, expected_heads, outputs, "
            "next_work:{scope:Activity ID,goal:text,inputs:[exact record refs]}"
            if routing
            else "JSON: state completed/waiting, useful text, changes, expected_heads, "
            "outputs:[chosen Activity ref and any data refs], optional wait"
        ),
        "changes": "C3 Change: id,kind,key,scope,body (value only), optional source_refs",
        "expected_heads": "each changed ID maps to its old revision; zero for a new ID",
        "identity": "the model chooses subject meaning; Core checks refs, scope, CAS and rights",
    }


def outcome(
    output: dict[str, Any],
    attempt: dict[str, Any],
    work: dict[str, Any],
    inputs: Any,
) -> dict[str, Any]:
    """Normalize trusted identity/budget; never invent Activity or subject content."""
    body = json.loads(work["body"])
    if body["method_ref"]["id"] not in {ROUTING_ID, EXECUTION_ID}:
        return output  # Historical/custom Work keeps its original contract.

    def invalid() -> None:
        raise CoreError("invalid_request", "ordinary.outcome_shape", "after_refresh")

    def refs(value: Any) -> bool:
        return isinstance(value, list) and all(
            isinstance(r, dict)
            and isinstance(r.get("id"), str)
            and bool(r["id"])
            and type(r.get("revision")) is int
            and r["revision"] > 0
            and not set(r) - {"id", "revision", "role"}
            and isinstance(r.get("role", "exact"), str)
            and r.get("role", "exact") in {"exact", "must_be_current"}
            for r in value
        )

    if (
        not isinstance(output, dict)
        or set(output)
        - {"state", "text", "changes", "expected_heads", "outputs", "wait", "next_work"}
        or not isinstance(output.get("state"), str)
        or output.get("state") not in {"completed", "ready", "waiting"}
        or not isinstance(output.get("text"), str)
        or not refs(output.get("outputs", []))
        or not isinstance(output.get("changes", []), list)
        or not all(isinstance(c, dict) for c in output.get("changes", []))
        or not isinstance(output.get("expected_heads", {}), dict)
        or not all(
            isinstance(k, str) and type(v) is int and v >= 0
            for k, v in output.get("expected_heads", {}).items()
        )
    ):
        invalid()
    routing = body["method_ref"]["id"] == ROUTING_ID
    scope = body.get("scope", "space")
    if routing:
        child = output.get("next_work")
        if (
            output.get("state") != "completed"
            or not isinstance(child, dict)
            or set(child) - {"scope", "goal", "inputs"}
            or not isinstance(child.get("scope"), str)
            or not child.get("scope")
            or child.get("scope") == "space"
            or not isinstance(child.get("goal"), str)
            or not child.get("goal")
            or not refs(child.get("inputs", []))
        ):
            raise CoreError("invalid_request", "ordinary.routing_outcome", "after_refresh")
        scope = child["scope"]
    elif output.get("next_work") is not None:
        raise CoreError("invalid_request", "ordinary.unexpected_continuation", "after_refresh")
    if not routing:
        subject_scope(output.get("changes", []), scope)
    selected = next((r for r in output.get("outputs", []) if r.get("id") == scope), None)
    if selected is None:
        raise CoreError("invalid_request", "ordinary.activity_output", "after_refresh")
    if routing:
        assert isinstance(child, dict)
        pinned = json.loads(attempt["body"])
        method = next((r for r in pinned["catalog"] if r["id"] == EXECUTION_ID), None)
        if method is None:
            raise CoreError("invalid_request", "ordinary.execution_method", "after_refresh")
        requested = [r for r in child.get("inputs", []) if r["id"] != scope]
        # Subject versions are immutable inputs; mutations use their own CAS.
        # Requiring this head to remain current would reject our own typed tool
        # updating the Activity before the final outcome.
        requested.append(selected | {"role": "exact"})
        output = output | {
            "text": "",
            "processed_cutoff": attempt["original_cursor"],
            "next_work": {
                "id": "continued:" + digest(attempt["id"]),
                "conversation": body["conversation"],
                "scope": scope,
                "goal": child["goal"],
                "inputs": inputs(scope, requested),
                "method_ref": {
                    "id": method["id"],
                    "revision": method["revision"],
                    "role": "must_be_current",
                },
                "call_limit": (
                    None
                    if body["call_limit"] is None
                    else max(0, body["call_limit"] - work["reserved"])
                ),
                "continuation_policy": "durable",
            },
        }
    return output


def subject_scope(changes: Any, scope: str) -> None:
    if not isinstance(changes, list) or any(not isinstance(c, dict) for c in changes):
        raise CoreError("invalid_request", "ordinary.changes")
    if any(
        (c.get("kind") == "activity" and c.get("id") != scope)
        or (c.get("kind") == "data" and c.get("scope", "space") != scope)
        for c in changes
    ):
        raise CoreError("denied", "ordinary.activity_scope")
