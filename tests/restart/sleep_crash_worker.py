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
        result = send(self, request)
        phase = packet["phase"]
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
        ):
            os._exit(91)
        return result

    type.__setattr__(Client, "send", crash)
    sleep = Sleep(client)
    if packet["phase"].startswith("outcome:"):
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
