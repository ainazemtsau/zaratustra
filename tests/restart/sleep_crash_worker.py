"""Kill after real committed public operations; no direct subject repair."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from zaratustra_app import Driver, Sleep
from zaratustra_core import Client, Core, Request

from .sleep_support import PROFILE, MechanicalSleepReceiver


def main() -> None:
    packet = json.load(sys.stdin)
    client = Core(Path(packet["root"])).connect(packet["token"])
    send = Client.send

    def crash(self: Client, request: Request) -> dict[str, Any]:
        phase = packet["phase"]
        resource_pause = (
            request.operation == "control_work"
            and request.payload.get("action") == "pause"
            and request.payload.get("reason") == "resource_exhausted"
        )
        if phase == "resource-before-pause" and resource_pause:
            os._exit(91)
        result = send(self, request)
        changes = request.payload.get("changes", [])
        if (
            (phase == "method" and request.command_id == "sleep:install:sleep-method")
            or (phase == "work" and request.operation == "open_work")
            or (phase == "progress" and any(c["id"] == "s:progress" for c in changes))
            or (phase == "bound" and request.operation == "control_work")
            or (
                phase == "terminal"
                and request.operation == "observe_attempt"
                and request.payload["kind"] == "terminal"
            )
            or (phase.startswith("outcome:") and request.operation == "commit_outcome")
            or (phase == "resource-after-pause" and resource_pause)
            or (
                phase == "resource-after-projection"
                and any(
                    c["id"] == "s:progress"
                    and c.get("body", {}).get("stop_reason") == "resource_exhausted"
                    for c in changes
                )
            )
        ):
            os._exit(91)
        return result

    type.__setattr__(Client, "send", crash)
    sleep = Sleep(client)
    if packet["phase"].startswith("resource-"):

        class CannotFit:
            resource_upper = 3
            tool_handler: Any = None

            def run(self, context: Any, action: str) -> bytes:
                raise AssertionError("Resource admission must reject before sending")

        sleep.run("s", PROFILE, CannotFit())
    elif packet["phase"].startswith("outcome:"):
        state = packet["phase"].split(":")[1]

        def receiver(context: Any, action: str) -> bytes:
            return json.dumps(
                {
                    "state": state,
                    "text": "Actual retained bounded result",
                    "changes": [
                        {
                            "id": "learned",
                            "kind": "memory",
                            "key": "learned",
                            "body": "Actual permitted correction",
                        }
                    ],
                    "expected_heads": {"learned": 0},
                }
            ).encode()

        sleep.run("s", PROFILE, Driver(receiver))
    elif packet["phase"] == "terminal":
        sleep.run("s", PROFILE, Driver(MechanicalSleepReceiver()))
    else:
        sleep.start(work_id="s", call_limit=4)
