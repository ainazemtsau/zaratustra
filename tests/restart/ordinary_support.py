"""Explicit fictional Activity choices; never used by product code or live G14."""

from __future__ import annotations

import json
from typing import Any

from .support import Receiver


def routing(context: dict[str, Any], activity: str = "activity") -> dict[str, Any]:
    old = next((r for r in context["catalog"] if r["id"] == activity), None)
    revision = old["revision"] if old else 0
    return {
        "state": "completed",
        "text": "",
        "changes": [
            {
                "id": activity,
                "kind": "activity",
                "key": "practice" if activity == "activity" else activity,
                "body": {"agreement": context["raw_messages"][-1]},
            }
        ],
        "expected_heads": {activity: revision},
        "outputs": [{"id": activity, "revision": revision + 1}],
        "next_work": {
            "scope": activity,
            "goal": "Carry out the exact fictional request",
            "inputs": [],
        },
    }


class OrdinaryReceiver(Receiver):
    def __init__(self) -> None:
        super().__init__()
        self.useful = 0

    def __call__(self, context: dict[str, Any], action_id: str) -> bytes:
        self.received.append(context)
        self.actions.append(action_id)
        if context["response_contract"]["version"] == "ordinary-routing/1":
            return json.dumps(routing(context), ensure_ascii=False).encode()
        output = dict(self.outputs[self.useful])
        self.useful += 1
        activity = next(r for r in context["catalog"] if r["id"] == context["work"]["scope"])
        revision = activity["revision"]
        if output.get("tool_changes"):
            for change in output["tool_changes"]:
                if change["id"] == activity["id"]:
                    output["expected_heads"][change["id"]] = revision
                    revision += 1
        output["outputs"] = [{"id": activity["id"], "revision": revision}]
        # The controlled Pi upstream's tool-return leg reads this exact terminal.
        self.outputs[self.useful - 1] = output
        return json.dumps(output, ensure_ascii=False).encode()
