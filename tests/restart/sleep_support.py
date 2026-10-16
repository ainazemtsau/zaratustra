"""Fictional mechanical Sleep trace; scripted analysis is NOT semantic evidence."""

from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from zaratustra_app import Coordinator, Driver, Pi, Sleep
from zaratustra_core import Core

from .support import Provider, Receiver, inspect, pi_cli

PROFILE = {"id": "profile", "revision": 1}


def save(client: Any, change: dict[str, Any], revision: int = 0) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        client.call(
            "apply_changes",
            {"changes": [change]},
            uuid4().hex,
            expected_heads={change["id"]: revision},
        )["refs"][0],
    )


def seed(root: Path) -> tuple[Any, Any, Any]:
    core, token = Core.initialize(root / "space")
    owner = core.connect(token)
    permissions = [
        "read",
        "apply_changes",
        "open_work",
        "prepare_attempt",
        "claim_dispatch",
        "observe_attempt",
        "commit_outcome",
        "control_work",
        "reserve_tool",
        "write:method:space",
        "write:memory:space",
    ]
    executor = core.connect(core.grant(token, "sleep-executor", permissions, origin="host"))
    changes: list[dict[str, Any]] = [
        {"id": "profile", "kind": "profile", "key": "transport", "body": {"mode": "scripted"}},
        {"id": "practice", "kind": "method", "key": "practice", "body": "Original bounded method"},
        {"id": "memory", "kind": "memory", "key": "known", "body": "Earlier uncertain note"},
        {"id": "ordinary", "kind": "data", "key": "ordinary", "body": "Routine work; no complaint"},
        {"id": "success", "kind": "data", "key": "success", "body": "Observed successful attempt"},
        {
            "id": "error",
            "kind": "data",
            "key": "error",
            "body": "Observed failed attempt, unresolved cause",
        },
    ]
    for change in changes:
        save(owner, change)
    return core, owner, executor


class MechanicalSleepReceiver(Receiver):
    def __init__(self, *, rollback: bool = False, state: str = "completed"):
        super().__init__()
        self.rollback, self.state = rollback, state

    def __call__(self, context: dict[str, Any], action_id: str) -> bytes:
        self.received.append(copy.deepcopy(context))
        self.actions.append(action_id)
        progress = next(
            m
            for m in context["inputs"]
            if isinstance(m["body"]["value"], dict)
            and m["body"]["value"].get("format") == "sleep-progress/v1"
        )
        body = copy.deepcopy(progress["body"]["value"])
        analysis_id = context["work"]["id"] + ":analysis"
        body["delivered_manifest_refs"].append(context["sleep_delivery_manifest"])
        body["analysis_result_refs"].append({"id": analysis_id, "revision": 1})
        body["remaining_refs"] = []
        body["consumed_resource"] = context["resource_state"]["consumed_resource"]
        body["unresolved_calls"] = []
        body["unexplored_coverage_position"] = {
            "attempted": "bounded comparison outside known links",
            "unknown": "Other material remains unexplored",
        }
        body["stop_reason"] = "bounded_portion_ended"
        body["continuation"] = "Check actual later outcomes, not summary count"
        heads = {h["id"]: h for h in context["catalog"]}
        changes = [
            {
                "id": analysis_id,
                "kind": "data",
                "key": analysis_id,
                "body": {
                    "format": "sleep-analysis/v1",
                    "sources": body["selected_source_refs"],
                    "content": {
                        "observation": "Fictional source observations",
                        "hypothesis": "Unproven improvement",
                        "alternatives": ["Different cause"],
                        "counterexamples": ["Success"],
                        "negative_attempts": ["Prior unsuccessful approach"],
                        "question": "Chosen without a complaint",
                    },
                },
            },
            {
                "id": "memory",
                "kind": "memory",
                "key": "known",
                "body": "Corrected bounded note",
                "source_refs": [{"id": analysis_id, "revision": 1}],
            },
            {
                "id": "practice",
                "kind": "method",
                "key": "practice",
                "body": "Original bounded method" if self.rollback else "Revised bounded method",
                "source_refs": [{"id": analysis_id, "revision": 1}],
            },
            {
                "id": progress["id"],
                "kind": "data",
                "key": progress["key"],
                "scope": progress["scope"],
                "body": body,
            },
        ]
        output = {
            "state": self.state,
            "text": "Mechanical bounded pass; unexplored material remains",
            "changes": changes,
            "expected_heads": {
                c["id"]: heads[c["id"]]["revision"] if c["id"] in heads else 0 for c in changes
            },
        }
        return json.dumps(output, ensure_ascii=False).encode()


def adaptation_trace(root: Path, mode: str) -> dict[str, Any]:
    core, owner, client = seed(root)
    receiver = MechanicalSleepReceiver()
    provider = Provider(receiver) if mode == "pi" else None
    thread = threading.Thread(target=provider.serve_forever, daemon=True) if provider else None
    if thread:
        thread.start()
    executor = (
        Pi(pi_cli(), root / "pi-home", f"http://127.0.0.1:{provider.server_port}/v1")
        if provider
        else Driver(receiver)
    )
    try:
        original_method = next(r for r in inspect(core, "records") if r["id"] == "practice")
        sleep = Sleep(client)
        sleep.start(work_id="sleep-one", call_limit=6, portion=100)
        before = sleep.progress("sleep-one")["body"]["value"]
        assert before["analysis_result_refs"] == before["delivered_manifest_refs"] == []
        assert before["remaining_refs"] == before["selected_source_refs"]
        first = sleep.run("sleep-one", PROFILE, executor)
        assert first["state"] == "completed" and first["accepted"] is False
        context = receiver.received[0]
        assert context["work"]["goal"] == "Sleep" and context["raw_messages"] == []
        assert {s["material"]["record"]["id"] for s in context["sleep_sources"]} >= {
            "ordinary",
            "success",
            "error",
        }
        progress = sleep.progress("sleep-one")["body"]["value"]
        assert progress["consumed_resource"] == 2
        assert progress["analysis_result_refs"] and progress["delivered_manifest_refs"]
        # Next actual Work receives CURRENT versions, then produces a real negative outcome.
        sleep.open_work(
            {
                "id": "next",
                "conversation": "next",
                "goal": "Try revised method",
                "method_ref": {"id": "practice", "revision": 1},
                "call_limit": 2,
                "continuation_policy": "durable",
            }
        )
        received: list[dict[str, Any]] = []

        def negative(ctx: dict[str, Any], action: str) -> bytes:
            received.append(ctx)
            return json.dumps(
                {"state": "completed", "text": "Actual negative outcome: result failed"}
            ).encode()

        coordinator = Coordinator(client)
        prepared = coordinator.prepare("next", "next-attempt", PROFILE)
        coordinator.dispatch("next-attempt", prepared["generation"], Driver(negative))
        coordinator.recover("next-attempt")
        assert received[0]["method"]["revision"] == 2
        assert {m["id"]: m["revision"] for m in received[0]["inputs"]}.get("memory") == 2
        assert next(m for m in received[0]["inputs"] if m["id"] == "memory")["revision"] == 2
        receiver.rollback = True
        sleep = Sleep(Core(core.root).connect(client.token))
        sleep.start(work_id="sleep-two", call_limit=4, portion=100)
        sleep.run("sleep-two", PROFILE, executor)
        feedback = [
            s["material"]
            for s in receiver.received[1]["sleep_sources"]
            if "outcome" in s["material"]
        ]
        actual = next(s for s in feedback if s["outcome"]["attempt_id"] == "next-attempt")
        assert actual["method"]["revision"] == 2
        assert next(m for m in actual["inputs"] if m["id"] == "memory")["revision"] == 2
        assert "negative" in actual["outcome"]["text"]
        rows = [r for r in inspect(core, "records") if r["id"] == "practice"]
        assert [r["revision"] for r in rows] == [1, 2, 3]
        assert rows[0] == original_method
        assert json.loads(rows[0]["body"])["value"] == json.loads(rows[2]["body"])["value"]
        assert rows[0]["scope"] == rows[1]["scope"] == rows[2]["scope"] == "space"
        assert inspect(core, "acceptance") == []
        evidence = {
            "mode": mode,
            "received": receiver.received,
            "next_work_received": received,
            "physical": {
                t: inspect(core, t)
                for t in (
                    "records",
                    "heads",
                    "works",
                    "attempts",
                    "actions",
                    "observations",
                    "results",
                )
            },
            "native_events": executor.events if isinstance(executor, Pi) else [],
            "provider_packets": provider.packets if provider else [],
        }
        destination = os.environ.get("ZARA_RESTART_EVIDENCE")
        if destination:
            path = Path(destination)
            path.mkdir(parents=True, exist_ok=True)
            (path / ("sleep-" + mode + ".json")).write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return evidence
    finally:
        if provider:
            provider.shutdown()
            provider.server_close()
        if thread:
            thread.join(timeout=2)
