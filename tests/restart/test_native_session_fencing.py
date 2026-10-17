"""A stale Pi process must never address another session's newly claimed Work."""

from pathlib import Path
from typing import Any

import pytest
from zaratustra_app.pi_host import handle
from zaratustra_core import CoreError


@pytest.mark.parametrize("late", ["result", "observation", "settled"])
def test_old_pi_session_cannot_write_replacement_attempt(tmp_path: Path, late: str) -> None:
    root = str(tmp_path / "data")
    old = {"data_root": root, "session_id": "old-pi"}
    new = {"data_root": root, "session_id": "new-pi"}
    handle(old | {"command": "input", "event_id": "first", "text": "First fictional request"})
    handle(new | {"command": "cancel"})
    handle(new | {"command": "input", "event_id": "second", "text": "Replacement request"})
    routed = handle(
        new
        | {
            "command": "tool",
            "name": "route",
            "call_id": "route",
            "payload": {
                "changes": [
                    {"id": "activity", "kind": "activity", "key": "activity", "body": "Fictional"}
                ],
                "expected_heads": {"activity": 0},
                "outputs": [{"id": "activity", "revision": 1}],
                "next_work": {"scope": "activity", "goal": "Replacement work", "inputs": []},
            },
        }
    )
    handle(
        new
        | {
            "command": "tool",
            "name": "result",
            "call_id": "new-stage",
            "payload": {"outputs": [{"id": "activity", "revision": 1}]},
        }
    )
    packets: dict[str, dict[str, Any]] = {
        "result": {
            "command": "tool",
            "name": "result",
            "call_id": "old-stage",
            "payload": {
                "outputs": [{"id": "activity", "revision": 1}],
                "state": "waiting",
                "wait": {"id": "stale-wait", "question": "Stale question"},
            },
        },
        "observation": {
            "command": "observation",
            "event_id": "old-tool",
            "value": {"toolCallId": "old"},
        },
        "settled": {
            "command": "settled",
            "event_id": "old-final",
            "text": "Stale final",
            "aborted": False,
            "terminal": {"stop_reason": "stop"},
        },
    }
    packet = packets[late]
    with pytest.raises(CoreError, match="native.session"):
        handle(old | packet)
    current = handle(new | {"command": "context"})
    assert current["current"]["attempt"] == routed["current"]["attempt"]
    assert current["current"]["staged"]["outputs"] == [{"id": "activity", "revision": 1}]
    result = handle(
        new
        | {
            "command": "settled",
            "event_id": "new-final",
            "text": "Actual new final",
            "aborted": False,
            "terminal": {"stop_reason": "stop"},
        }
    )
    assert result["state"] == "completed" and result["text"] == "Actual new final"
