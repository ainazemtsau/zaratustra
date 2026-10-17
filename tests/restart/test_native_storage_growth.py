"""Ordinary native reads must not retain copies of unrelated raw tool history."""

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app import Coordinator
from zaratustra_app.native_session import NativeSession
from zaratustra_core import Client, Core

from .support import inspect
from .test_native_review import delivered


def test_fresh_result_discovery_does_not_copy_unrelated_pinned_bodies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core, token, builder = delivered(tmp_path)
    owner = core.connect(token)
    marker = "foreign-retained-context-" + "X" * 250_000
    owner.call(
        "apply_changes",
        {
            "changes": [
                {"id": "foreign-data", "kind": "data", "key": "foreign-data", "body": marker},
                {
                    "id": "foreign-method",
                    "kind": "method",
                    "key": "foreign-method",
                    "body": "Retained Method",
                },
                {
                    "id": "foreign-profile",
                    "kind": "profile",
                    "key": "foreign-profile",
                    "body": {"model": "fictional"},
                },
            ]
        },
        "foreign-records",
        expected_heads={"foreign-data": 0, "foreign-method": 0, "foreign-profile": 0},
    )
    coordinator = Coordinator(owner)
    coordinator.open_work(
        {
            "id": "foreign-work",
            "conversation": "foreign-conversation",
            "goal": "Foreign retained work",
            "method_ref": {"id": "foreign-method", "revision": 1},
            "inputs": [{"id": "foreign-data", "revision": 1}],
            "call_limit": None,
            "continuation_policy": "durable",
        }
    )
    coordinator.prepare("foreign-work", "foreign-attempt", {"id": "foreign-profile", "revision": 1})
    assert (
        marker in next(a for a in inspect(core, "attempts") if a["id"] == "foreign-attempt")["body"]
    )
    original = Client.call
    responses = []

    def tracked(
        self: Client, operation: str, payload: dict[str, Any], command: str, **kwargs: Any
    ) -> Any:
        result = original(self, operation, payload, command, **kwargs)
        responses.append(json.dumps(result))
        return result

    monkeypatch.setattr(Client, "call", tracked)
    context = NativeSession(core, token, "fresh-discovery").context()
    assert context["latest_delivery"]["attempt_id"] == builder
    assert responses and not any(marker in response for response in responses)


def test_equal_native_cycles_preserve_evidence_without_snapshot_amplification(
    tmp_path: Path,
) -> None:
    core, token = Core.initialize(tmp_path / "core")
    session = NativeSession(core, token, "growth-session")
    session.profile = {"model": "fictional", "provider": "localhost"}
    tool_text = "A realistic fictional source line with observable tool output.\n" * 256
    sizes = []
    attempts = []
    for index in range(6):
        suffix = str(index)
        text = "Inspect the fictional source, cycle " + suffix
        session.input("input-" + suffix, text)
        session.tool(
            "route",
            "route-" + suffix,
            {
                "changes": (
                    [
                        {
                            "id": "activity",
                            "kind": "activity",
                            "key": "practice",
                            "body": "Fictional practice",
                        }
                    ]
                    if index == 0
                    else []
                ),
                "expected_heads": ({"activity": 0} if index == 0 else {}),
                "outputs": [{"id": "activity", "revision": 1}],
                "next_work": {"scope": "activity", "goal": "Inspect source", "inputs": []},
            },
        )
        attempts.append(session.context()["current"]["attempt"])
        session.observation(
            "tool-" + suffix,
            {"toolCallId": "read-" + suffix, "toolName": "read", "result": tool_text},
        )
        session.verify_profile()
        session.tool("result", "result-" + suffix, {"outputs": [{"id": "activity", "revision": 1}]})
        session.settled(
            "final-" + suffix,
            "Observed fictional source, cycle " + suffix,
            False,
            {"stop_reason": "stop", "error_message": None},
        )
        session.context()
        sizes.append((core.root / "core.sqlite3").stat().st_size)
    # Equal repeated work may add context/catalog metadata. It must not copy raw
    # historical observations into every read event and its durable receipt.
    early_growth = sizes[2] - sizes[0]
    late_growth = sizes[5] - sizes[3]
    assert late_growth < early_growth * 3
    assert sizes[-1] < len(tool_text.encode()) * 6 * 128
    events = inspect(core, "events")
    assert not any(e["kind"] == "read_snapshot" for e in events)
    observations = inspect(core, "observations")
    messages = inspect(core, "messages")
    for index, attempt in enumerate(attempts):
        suffix = str(index)
        message = next(m for m in messages if m["event"] == "input-" + suffix)
        assert (
            base64.b64decode(message["raw"]).decode()
            == "Inspect the fictional source, cycle " + suffix
        )
        tool = next(
            o for o in observations if o["attempt"] == attempt and o["event"] == "tool-" + suffix
        )
        raw = json.loads(base64.b64decode(json.loads(tool["body"])["raw_base64"]))
        assert raw == {"toolCallId": "read-" + suffix, "toolName": "read", "result": tool_text}
        terminal = next(
            o for o in observations if o["attempt"] == attempt and o["event"] == "terminal"
        )
        assert (
            json.loads(base64.b64decode(json.loads(terminal["body"])["raw_base64"]))[
                "native_event_id"
            ]
            == "final-" + suffix
        )
    owner = core.connect(token)
    before = owner.call("lookup_receipt", {"command_id": "native-input:input-0"}, "receipt-before")
    replay = owner.call(
        "ingest_message",
        {
            "conversation": session.mapping_id,
            "event_id": "input-0",
            "raw_base64": base64.b64encode(b"Inspect the fictional source, cycle 0").decode(),
        },
        "native-input:input-0",
    )
    after = owner.call("lookup_receipt", {"command_id": "native-input:input-0"}, "receipt-after")
    assert before == after and replay == before["result"]
