"""Public-API-only coordination; durable core state is the continuation authority."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any
from uuid import uuid4

from zaratustra_core import Client, CoreError

from .executor_port import Executor, Pi


class Coordinator:
    def __init__(self, client: Client):
        self.client = client

    def snapshot(self) -> dict[str, Any]:
        return self.client.call("read_snapshot", {}, str(uuid4()))

    def prepare(self, work_id: str, attempt_id: str, profile_ref: dict[str, Any]) -> dict[str, Any]:
        snapshot = self.snapshot()
        work = next(w for w in snapshot["works"] if w["id"] == work_id)
        cursor = next(
            c["cursor"] for c in snapshot["conversations"] if c["id"] == work["conversation"]
        )
        messages = sorted(
            (
                m
                for m in snapshot["messages"]
                if m["conversation"] == work["conversation"] and m["seq"] > cursor
            ),
            key=lambda m: m["seq"],
        )
        cutoff = messages[-1]["seq"] if messages else cursor
        manifest = [
            {"sequence": m["seq"], "sha256": hashlib.sha256(base64.b64decode(m["raw"])).hexdigest()}
            for m in messages
        ]
        return self.client.call(
            "prepare_attempt",
            {
                "work_id": work_id,
                "work_revision": work["revision"],
                "id": attempt_id,
                "profile_ref": profile_ref,
                "original_cursor": cursor,
                "cutoff": cutoff,
                "message_sequences": [m["seq"] for m in messages],
                "manifest": manifest,
            },
            attempt_id + ":prepare",
        )

    def refresh_basis(self, work_id: str) -> dict[str, Any]:
        """Explicit new intent over freshly read current refs; old terminal remains evidence."""
        snapshot = self.snapshot()
        work = next(w for w in snapshot["works"] if w["id"] == work_id)
        body = json.loads(work["body"])
        heads = {h["id"]: h["revision"] for h in snapshot["heads"]}

        def fresh(ref: dict[str, Any]) -> dict[str, Any]:
            if ref.get("role") == "must_be_current":
                return ref | {"revision": heads[ref["id"]]}
            return ref

        return self.client.call(
            "control_work",
            {
                "work_id": work_id,
                "revision": work["revision"],
                "action": "refresh",
                "inputs": [fresh(r) for r in body.get("inputs", [])],
                "method_ref": fresh(body["method_ref"]),
            },
            str(uuid4()),
        )

    def dispatch(self, attempt_id: str, generation: int, executor: Executor) -> bytes:
        action_id = attempt_id + ":action"
        try:
            pinned = self.client.call(
                "claim_dispatch",
                {
                    "attempt_id": attempt_id,
                    "generation": generation,
                    "resource_upper": getattr(executor, "resource_upper", 1),
                },
                attempt_id + ":claim:" + str(uuid4()),
                action_id=action_id,
            )["pinned"]
        except CoreError as exc:
            if exc.code == "stale_basis" and exc.field == "new_input":
                state = self.snapshot()
                attempt = next(a for a in state["attempts"] if a["id"] == attempt_id)
                work = next(w for w in state["works"] if w["id"] == attempt["work"])
                self.client.call(
                    "control_work",
                    {"work_id": work["id"], "revision": work["revision"], "action": "refresh"},
                    attempt_id + ":refresh",
                )
            raise
        # A replayed claim is potentially sent; a receipt never proves send safety.
        snapshot = self.snapshot()
        action = next(a for a in snapshot["actions"] if a["id"] == action_id)
        observations = [o for o in snapshot["observations"] if o["attempt"] == attempt_id]
        if observations or action["state"] != "claimed":
            raise CoreError("outcome_unknown", "existing_dispatch", "reconcile")
        context = dict(pinned)
        context["raw_messages"] = [
            base64.b64decode(m["raw"]).decode("utf-8") for m in pinned["messages"]
        ]

        def tool_handler(native_id: str, intent: dict[str, Any]) -> dict[str, Any]:
            if set(intent) - {"changes", "expected_heads", "initial_work"}:
                raise CoreError("invalid_request", "native_tool.intent")
            command_id = attempt_id + ":tool:" + native_id
            self.client.call(
                "reserve_tool",
                {
                    "attempt_id": attempt_id,
                    "generation": generation,
                    "native_id": native_id,
                    "command_id": command_id,
                },
                command_id + ":reserve",
            )
            change_payload = {
                "changes": intent["changes"],
                "tool": {
                    "attempt_id": attempt_id,
                    "generation": generation,
                    "native_id": native_id,
                },
            }
            if "initial_work" in intent:
                change_payload["initial_work"] = intent["initial_work"]
            request = self.client.request(
                "apply_changes", change_payload, command_id, expected_heads=intent["expected_heads"]
            )
            return self.client.send(request)

        executor.tool_handler = tool_handler
        try:
            raw = executor.run(context, action_id)
        except BaseException:
            self.client.call(
                "observe_attempt",
                {"attempt_id": attempt_id, "event_id": "unknown", "kind": "unknown"},
                attempt_id + ":unknown",
            )
            raise
        self.client.call(
            "observe_attempt",
            {
                "attempt_id": attempt_id,
                "event_id": "terminal",
                "kind": "terminal",
                "raw_base64": base64.b64encode(raw).decode(),
            },
            attempt_id + ":retain",
        )
        return raw

    def recover(self, attempt_id: str, *, pi: bool = False) -> dict[str, Any]:
        snapshot = self.snapshot()
        attempt = next(a for a in snapshot["attempts"] if a["id"] == attempt_id)
        observations = [
            json.loads(o["body"]) for o in snapshot["observations"] if o["attempt"] == attempt_id
        ]
        terminal = next(
            (o for o in observations if o["kind"] == "terminal" and not o["late"]), None
        )
        if terminal is None:
            if any(a["attempt"] == attempt_id for a in snapshot["actions"]):
                raise CoreError("outcome_unknown", "retained_claim", "reconcile")
            raise CoreError("invalid_request", "no_terminal")
        raw = base64.b64decode(terminal["raw_base64"])
        output = Pi.decode(raw) if pi else json.loads(raw)
        payload = {
            "attempt_id": attempt_id,
            "generation": attempt["generation"],
            "terminal_event": terminal["event_id"],
            "original_cursor": attempt["original_cursor"],
            "processed_cutoff": attempt["cutoff"],
            "state": output["state"],
            "text": output["text"],
            "outputs": output.get("outputs", []),
        }
        if output.get("wait"):
            payload["wait"] = output["wait"]
        return self.client.call("commit_outcome", payload, attempt_id + ":outcome")
