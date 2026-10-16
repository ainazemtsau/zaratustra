"""Historical typed-reference closure; never interpret arbitrary record prose."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .formats import value_references
from .shapes import Ref, SleepProgress
from .types import CoreError, digest


def verify_references(db: sqlite3.Connection, path: Path) -> None:
    # Local import avoids an API/maintenance import cycle; these helpers only read db.
    from .api import Core

    core = Core(path.parent)

    def require(condition: bool) -> None:
        if not condition:
            raise CoreError("invalid_request", "backup.reference_closure")

    def table(name: str) -> list[dict[str, Any]]:
        return [dict(row) for row in db.execute("SELECT * FROM " + name)]

    records = {(r["id"], r["revision"]): r for r in table("records")}
    works = {r["id"]: r for r in table("works")}
    attempts = {r["id"]: r for r in table("attempts")}
    attempt_order = [r[0] for r in db.execute("SELECT id FROM attempts ORDER BY rowid")]
    messages = {(r["conversation"], r["seq"]): r for r in table("messages")}
    results = {(r["attempt"], r["slot"]): r for r in table("results")}
    waits = {r["id"]: r for r in table("waits")}
    tools = {(r["attempt"], r["native_id"]): r for r in table("tool_calls")}
    receipts = {r["command"]: r for r in table("receipts")}
    actions = {r["id"]: r for r in table("actions")}
    events = {r["seq"]: r for r in table("events")}

    def equal(left: Any, right: Any) -> bool:
        # Python equality conflates JSON booleans and integers; wire/v1 does not.
        return digest(left) == digest(right)

    def record(ref: dict[str, Any], kind: str | None = None) -> dict[str, Any]:
        Ref.model_validate(ref)
        row = records.get((ref["id"], ref["revision"]))
        require(row is not None)
        assert row is not None
        require(kind is None or row["kind"] == kind)
        return row | {"body": json.loads(row["body"])}

    def snapshot(saved: dict[str, Any]) -> dict[str, Any]:
        actual = record({"id": saved["id"], "revision": saved["revision"]})
        normalized = saved | {
            "body": json.loads(saved["body"]) if isinstance(saved["body"], str) else saved["body"]
        }
        require(equal(normalized, actual))
        return actual

    def work_refs(body: dict[str, Any]) -> None:
        method = record(body["method_ref"], "method")
        require(method["scope"] in {"space", body.get("scope", "space")})
        for ref in body.get("inputs", []):
            record(ref)
        if "continuation" in body:
            link = body["continuation"]
            require(
                set(link) - {"activity_ref"}
                == {
                    "attempt_id",
                    "delivered_cutoff",
                    "processed_cutoff",
                    "parent_reserved",
                    "resource_upper",
                }
            )
            parent_attempt = attempts.get(link["attempt_id"])
            require(parent_attempt is not None)
            assert parent_attempt is not None
            parent = works[parent_attempt["work"]]
            parent_result = results.get((parent_attempt["id"], "final"))
            require(parent_result is not None)
            assert parent_result is not None
            result_body = json.loads(parent_result["body"])
            require(
                all(
                    type(link[k]) is int
                    for k in (
                        "delivered_cutoff",
                        "processed_cutoff",
                        "parent_reserved",
                        "resource_upper",
                    )
                )
                and 0 <= link["processed_cutoff"] <= link["delivered_cutoff"]
                and link["resource_upper"] > 0
            )
            require(
                result_body.get("next_work_id") == body["id"]
                and parent["conversation"] == body["conversation"]
                and link["delivered_cutoff"] == parent_attempt["cutoff"]
                and link["processed_cutoff"] == result_body["cutoff"]
            )
            parent_actions = [a for a in actions.values() if a["attempt"] == parent_attempt["id"]]
            require(len(parent_actions) == 1)
            require(link["resource_upper"] == parent_actions[0]["reserve"])
            # Reservations at the historical handoff, not the parent's later total.
            parent_order = attempt_order.index(parent_attempt["id"])
            prefix = set(attempt_order[: parent_order + 1])
            reserved = sum(
                a["reserve"]
                for a in actions.values()
                if a["attempt"] in prefix and attempts[a["attempt"]]["work"] == parent["id"]
            )
            require(type(link["parent_reserved"]) is int and link["parent_reserved"] == reserved)
            require(
                type(body["call_limit"]) is int
                and 0 <= body["call_limit"] <= json.loads(parent["body"])["call_limit"] - reserved
            )
            scope = body.get("scope", "space")
            if "activity_ref" in link:
                record(link["activity_ref"], "activity")
                require(link["activity_ref"]["id"] == scope)
            if scope != "space":
                require(link.get("activity_ref", {}).get("id") == scope)

    def result_refs(body: dict[str, Any]) -> None:
        for ref in body.get("refs", []) + body.get("outputs", []):
            record(ref)
        if "next_work_id" in body:
            child = works.get(body["next_work_id"])
            require(child is not None)
            assert child is not None
            require(
                json.loads(child["body"]).get("continuation", {}).get("attempt_id")
                == body["attempt_id"]
            )

    def source(ref: dict[str, Any]) -> dict[str, Any]:
        return core._source(db, ref)

    try:
        for work in works.values():
            work_refs(json.loads(work["body"]))
        for result in results.values():
            saved_result = json.loads(result["body"])
            require(saved_result["attempt_id"] == result["attempt"])
            require(type(saved_result.get("cutoff")) is int and saved_result["cutoff"] >= 0)
            result_refs(saved_result)
        for event in events.values():
            receipt = receipts.get(event["subject"])
            require(receipt is not None)
            assert receipt is not None
            response = json.loads(receipt["response"])
            require(type(response["sequence"]) is int and response["sequence"] == event["seq"])
            require(response["command_id"] == response["receipt_id"] == receipt["command"])
            require(equal(response["result"], json.loads(event["body"])))
            if event["kind"] in {"apply_changes", "commit_outcome"}:
                result_refs(response["result"])
            if event["kind"] in {"prepare_attempt", "claim_dispatch"}:
                result = response["result"]
                saved_pin = dict(result["pinned"])
                resource = saved_pin.pop("resource_state", None)
                if event["kind"] == "claim_dispatch":
                    action = actions[result["action_id"]]
                    attempt_id = action["attempt"]
                    require(resource is not None)
                    require(
                        all(
                            key in actions
                            and attempts[actions[key]["attempt"]]["work"]
                            == attempts[attempt_id]["work"]
                            for key in resource["unresolved_calls"]
                        )
                    )
                else:
                    attempt_id = result["attempt_id"]
                require(equal(saved_pin, json.loads(attempts[attempt_id]["body"])))
        for receipt in receipts.values():
            response = json.loads(receipt["response"])
            receipt_event = events.get(response["sequence"])
            require(receipt_event is not None and receipt_event["subject"] == receipt["command"])
        for tool in tools.values():
            if tool["receipt"] is not None:
                require(tool["receipt"] == tool["command"] and tool["receipt"] in receipts)
        for acceptance in table("acceptance"):
            accepted_result = results.get((acceptance["attempt"], acceptance["slot"]))
            require(
                accepted_result is not None
                and accepted_result["fingerprint"] == acceptance["result_hash"]
            )
        conversations = {r["id"] for r in table("conversations")}
        targets: dict[str, Any] = {
            "input": conversations,
            "prepare": works,
            "control": works,
            "dispatch": attempts,
            "observe": attempts,
            "resource": works,
        }
        for intent in table("intents"):
            require(intent["kind"] in targets and intent["subject"] in targets[intent["kind"]])
            saved_intent = json.loads(intent["body"])
            if "reply_to" in saved_intent:
                reply = saved_intent["reply_to"]
                reply_wait = waits.get(reply["id"])
                require(reply_wait is not None and reply_wait["work"] == intent["subject"])
                require(reply_wait is not None and 1 <= reply["revision"] <= reply_wait["revision"])
            if intent["kind"] == "observe" and "event_id" in saved_intent:
                require(
                    db.execute(
                        "SELECT 1 FROM observations WHERE attempt=? AND event=?",
                        (intent["subject"], saved_intent["event_id"]),
                    ).fetchone()
                    is not None
                )
        for action in actions.values():
            if action["correlation"] is not None:
                require(json.loads(action["correlation"])["action_id"] == action["id"])
        for wait in waits.values():
            bound = attempts.get(json.loads(wait["body"])["attempt_id"])
            require(bound is not None and bound["work"] == wait["work"])
            require(bound is not None and bound["conversation"] == wait["conversation"])
        for message in messages.values():
            reply = json.loads(message["reply"])
            if reply:
                reply_wait = waits.get(reply["id"])
                require(
                    reply_wait is not None and reply_wait["conversation"] == message["conversation"]
                )
                require(reply_wait is not None and 1 <= reply["revision"] <= reply_wait["revision"])
        for observation in table("observations"):
            saved_observation = json.loads(observation["body"])
            require(saved_observation["attempt_id"] == observation["attempt"])
            require(saved_observation["event_id"] == observation["event"])
            evidence = saved_observation.get("evidence")
            if evidence:
                observed_action = actions.get(evidence["action_id"])
                require(
                    observed_action is not None
                    and observed_action["attempt"] == observation["attempt"]
                )
        for attempt in attempts.values():
            body = json.loads(attempt["body"])
            work_refs(body["work"])
            require(body["work"]["id"] == attempt["work"])
            require(body["work"]["conversation"] == attempt["conversation"])
            require(works[attempt["work"]]["conversation"] == attempt["conversation"])
            require(snapshot(body["method"]) == record(body["work"]["method_ref"], "method"))
            require(snapshot(body["profile"]) == record(body["profile_ref"], "profile"))
            require(
                equal(
                    [snapshot(r) for r in body["inputs"]],
                    [record(r) for r in body["work"].get("inputs", [])],
                )
            )
            for saved in body["catalog"]:
                snapshot(saved)
            conversation = attempt["conversation"]
            start, cutoff = attempt["original_cursor"], attempt["cutoff"]
            require(type(start) is int and type(cutoff) is int and 0 <= start <= cutoff)
            current = sorted(
                (
                    m
                    for m in messages.values()
                    if m["conversation"] == conversation and start < m["seq"] <= cutoff
                ),
                key=lambda m: m["seq"],
            )
            require(len(current) == cutoff - start)
            require(all(m["seq"] == start + i + 1 for i, m in enumerate(current)))
            require(equal(body["messages"], current))
            prior = sorted(
                (
                    m
                    for m in messages.values()
                    if m["conversation"] == conversation and m["seq"] <= start
                ),
                key=lambda m: m["seq"],
            )
            require(equal(body["prior_messages"], prior))
            require(
                equal(
                    body["manifest"],
                    [
                        {
                            "sequence": m["seq"],
                            "sha256": hashlib.sha256(
                                base64.b64decode(m["raw"], validate=True)
                            ).hexdigest(),
                        }
                        for m in body["messages"]
                    ],
                )
            )
            for saved in body["prior_results"]:
                require(equal(results.get((saved["attempt"], saved["slot"])), saved))
                require(attempts[saved["attempt"]]["conversation"] == conversation)
            for saved in body["prior_waits"]:
                saved_wait = waits.get(saved["id"])
                require(saved_wait is not None and saved_wait["body"] == saved["body"])
                require(
                    saved_wait is not None
                    and saved_wait["work"] == saved["work"]
                    and saved_wait["conversation"] == saved["conversation"] == conversation
                )
                require(
                    saved_wait is not None
                    and type(saved["revision"]) is int
                    and 1 <= saved["revision"] <= saved_wait["revision"]
                )
            for saved in body["tool_ledger"]:
                saved_tool = tools.get((saved["attempt"], saved["native_id"]))
                require(
                    saved_tool is not None
                    and all(
                        saved_tool[k] == saved[k]
                        for k in ("attempt", "native_id", "command", "action")
                    )
                )
                require(
                    saved_tool is not None
                    and (saved["receipt"] is None or saved_tool["receipt"] == saved["receipt"])
                )
                require(attempts[saved["attempt"]]["work"] == attempt["work"])
            for saved in body.get("sleep_sources", []):
                require(equal(source(saved["source_ref"]), saved["material"]))
            if "sleep_delivery_manifest" in body:
                require(
                    body["sleep_delivery_manifest"]
                    == {"attempt_id": attempt["id"], "sha256": digest(body["sleep_sources"])}
                )
        for row in records.values():
            wrapper = json.loads(row["body"])
            value = wrapper["value"]
            if wrapper.get("schema_ref"):
                schema = record(wrapper["schema_ref"])["body"]["value"]
                for ref in value_references(value, schema):
                    record(ref)
            if not isinstance(value, dict) or value.get("format") != "sleep-progress/v1":
                continue
            SleepProgress.model_validate(value)
            require(value["work_id"] in works)
            record(value["method_ref"], "method")
            high, cursor = value["source_high_watermark"], value["enumeration_cursor"]
            require(0 <= cursor[0] <= high <= max(events, default=0))
            for key in ("enumerated_source_refs", "selected_source_refs", "remaining_refs"):
                for ref in value[key]:
                    source(ref)
                    require(ref["sequence"] <= high and [ref["sequence"], ref["index"]] <= cursor)
            require(
                all(
                    any(equal(ref, enumerated) for enumerated in value["enumerated_source_refs"])
                    for ref in value["selected_source_refs"] + value["remaining_refs"]
                )
            )
            for delivery in value["delivered_manifest_refs"]:
                require(delivery["attempt_id"] in attempts)
                require(attempts[delivery["attempt_id"]]["work"] == value["work_id"])
                pinned = json.loads(attempts[delivery["attempt_id"]]["body"])
                require(delivery["sha256"] == digest(pinned.get("sleep_sources", [])))
            for ref in value["analysis_result_refs"]:
                analysis = record(ref)["body"]["value"]
                require(
                    isinstance(analysis, dict) and analysis.get("format") == "sleep-analysis/v1"
                )
                for ref in analysis["sources"]:
                    source(ref)
            for key in value["applied_receipts"]:
                require(key in receipts)
                applied = events[json.loads(receipts[key]["response"])["sequence"]]
                result = json.loads(applied["body"])
                outcome_work = (
                    attempts[result["attempt_id"]]["work"]
                    if applied["kind"] == "commit_outcome"
                    else None
                )
                tool_works = {
                    attempts[t["attempt"]]["work"] for t in tools.values() if t["receipt"] == key
                }
                require(outcome_work == value["work_id"] or value["work_id"] in tool_works)
            for key in value["unresolved_calls"]:
                require(
                    key in actions and attempts[actions[key]["attempt"]]["work"] == value["work_id"]
                )
    except (KeyError, TypeError, ValueError, CoreError) as error:
        raise CoreError("invalid_request", "backup.reference_closure") from error
