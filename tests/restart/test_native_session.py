"""Native Pi lifecycle using real disposable Core, without a model."""

import base64
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app.pi_host import handle
from zaratustra_core import CoreError


def test_native_plaintext_scoped_completion(tmp_path: Path) -> None:
    root = tmp_path / "data"

    def send(command: str, **fields: Any) -> dict[str, Any]:
        return handle(
            {
                "data_root": str(root),
                "session_id": "fictional-session",
                "command": command,
                **fields,
            }
        )

    send("attach")
    send("input", event_id="fictional-input", text="Help with fictional arithmetic")
    routed = send(
        "tool",
        name="route",
        call_id="route-1",
        payload={
            "changes": [
                {
                    "id": "arithmetic",
                    "kind": "activity",
                    "key": "arithmetic",
                    "body": "Fictional arithmetic practice",
                }
            ],
            "expected_heads": {"arithmetic": 0},
            "outputs": [{"id": "arithmetic", "revision": 1}],
            "next_work": {"scope": "arithmetic", "goal": "Practice arithmetic", "inputs": []},
        },
    )
    assert routed["current"]["scope"] == "arithmetic"
    staged = send(
        "tool",
        name="result",
        call_id="result-1",
        payload={"outputs": [{"id": "arithmetic", "revision": 1}]},
    )
    assert staged["completed"] is False
    send(
        "observation",
        event_id="builtin-1",
        value={"tool": "bash", "result": "fictional observed output"},
    )
    final = send(
        "settled", event_id="assistant-entry-1", text="Two plus two is four.", aborted=False
    )
    assert final["state"] == "completed"
    reopened = send("reopen")
    assert reopened["current"] == {}
    messages = send(
        "tool",
        name="read",
        call_id="read-1",
        payload={"operation": "read_page", "arguments": {"table": "messages"}},
    )["rows"]
    assert base64.b64decode(messages[0]["raw"]).decode() == "Help with fictional arithmetic"
    assert any("Two plus two is four." in row["body"] for row in reopened["core"]["results"])


def test_abort_preserves_open_attempt_and_blocks_replay(tmp_path: Path) -> None:
    base = {"data_root": str(tmp_path / "data"), "session_id": "abort-session"}
    handle(base | {"command": "input", "event_id": "input-1", "text": "Fictional request"})
    result = handle(
        base | {"command": "settled", "event_id": "aborted", "text": "", "aborted": True}
    )
    assert result["state"] == "incomplete"
    assert handle(base | {"command": "reopen"})["current"]["attempt"]
    with pytest.raises(CoreError):
        handle(base | {"command": "input", "event_id": "input-2", "text": "New request"})


def test_cross_session_wait_reply_and_actual_profile(tmp_path: Path) -> None:
    from zaratustra_app.native_session import NativeSession
    from zaratustra_core import Core

    core, token = Core.initialize(tmp_path / "core")
    first = NativeSession(core, token, "pi-session-a")
    first.profile = {"model": "fictional-a", "provider": "fictional"}
    first.input("question-input", "Practice a fictional subject")
    first.tool(
        "route",
        "route",
        {
            "changes": [
                {"id": "subject", "kind": "activity", "key": "subject", "body": "Fictional subject"}
            ],
            "expected_heads": {"subject": 0},
            "outputs": [{"id": "subject", "revision": 1}],
            "next_work": {"scope": "subject", "goal": "Practice", "inputs": []},
        },
    )
    first.tool(
        "result",
        "result",
        {
            "state": "waiting",
            "wait": {"id": "question", "question": "Which fictional example?"},
            "outputs": [{"id": "subject", "revision": 1}],
        },
    )
    assert first.settled("assistant-a", "Which fictional example?", False)["state"] == "waiting"
    reopened = NativeSession(core, token, "pi-session-b")
    reopened.profile = {"model": "fictional-b", "provider": "fictional"}
    context = reopened.context()
    assert context["current"]["scope"] == "subject"
    wait = {k: context["waiting"][0][k] for k in ("id", "revision")}
    with pytest.raises(CoreError, match="addressed_reply_required"):
        reopened.input("free-input", "Not an addressed reply")
    continued = reopened.reply("reply-input", "The blue fictional example", wait)
    assert continued["current"]["profile"]["model"] == "fictional-b"
    assert continued["current"]["session_id"] == "pi-session-b"
    assert continued["current"]["attempt"] != context["current"]["attempt"]
    reopened.verify_profile()
    reopened.profile = {"model": "fictional-c", "provider": "fictional"}
    with pytest.raises(CoreError, match="actual_profile"):
        reopened.verify_profile()
    snapshot = reopened.coordinator.snapshot()
    profiles = [h for h in snapshot["heads"] if h["kind"] == "profile"]
    values = [
        reopened.owner.call(
            "read_exact", {"id": h["id"], "revision": h["revision"]}, h["id"] + ":read"
        )["body"]["value"]
        for h in profiles
    ]
    assert {v["model"] for v in values} == {"fictional-a", "fictional-b"}
    assert {v["session_id"] for v in values} == {"pi-session-a", "pi-session-b"}


def test_native_session_sleep_settles_exact_pinned_sources(tmp_path: Path) -> None:
    import json

    from zaratustra_app.native_session import NativeSession

    from .sleep_support import MechanicalSleepReceiver, seed

    core, owner, _ = seed(tmp_path)
    session = NativeSession(core, owner.token, "native-pi")
    session.profile = {"provider": "fictional", "model": "fictional-model"}
    context = session.start_sleep("space", portion=100)
    output = json.loads(MechanicalSleepReceiver()(context["sleep"], "fictional-action"))
    session.tool("result", "result-call", {k: v for k, v in output.items() if k != "text"})
    settled = session.settled("actual-final", output["text"], False)
    assert settled["state"] == "completed"
    reopened = NativeSession(core, owner.token, "fresh-pi")
    assert reopened.context()["current"] == {}


def test_new_pi_session_reopens_unknown_without_new_action(tmp_path: Path) -> None:
    base = {"data_root": str(tmp_path / "data"), "session_id": "old-pi"}
    first = handle(
        base | {"command": "input", "event_id": "lost-input", "text": "Fictional unknown task"}
    )
    handle(base | {"command": "settled", "event_id": "lost-terminal", "text": "", "aborted": True})
    reopened = handle(base | {"session_id": "fresh-pi", "command": "reopen"})
    assert reopened["current"]["attempt"] == first["current"]["attempt"]
    assert len(reopened["core"]["actions"]) == 1
    assert not reopened["core"]["results"]


def test_cancel_unknown_then_fresh_request_keeps_activity(tmp_path: Path) -> None:
    from zaratustra_app.native_session import NativeSession
    from zaratustra_core import Core

    core, token = Core.initialize(tmp_path / "core")
    first = NativeSession(core, token, "old-pi")
    first.input("old-input", "Fictional task")
    first.tool(
        "route",
        "route",
        {
            "changes": [
                {
                    "id": "kept",
                    "kind": "activity",
                    "key": "kept",
                    "body": "Keep this fictional activity",
                }
            ],
            "expected_heads": {"kept": 0},
            "outputs": [{"id": "kept", "revision": 1}],
            "next_work": {"scope": "kept", "goal": "Practice", "inputs": []},
        },
    )
    first.settled("lost", "", True)
    fresh = NativeSession(core, token, "fresh-pi")
    assert fresh.context()["current"]["scope"] == "kept"
    retained_before = {a["id"] for a in fresh.coordinator.rows("actions")}
    assert len(retained_before) == 2
    (core.root / "owner.credential").write_text(token, encoding="utf-8")
    cancelled = handle({"data_root": str(core.root), "session_id": "fresh-pi", "command": "cancel"})
    assert cancelled["state"] == "cancelled"
    next_turn = fresh.input("new-input", "A new fictional task")
    assert any(h["id"] == "kept" for h in next_turn["core"]["heads"])
    assert len(next_turn["core"]["actions"]) == 1
    retained_after = {a["id"] for a in fresh.coordinator.rows("actions")}
    assert len(retained_after) == 3 and retained_before < retained_after
    assert next_turn["projection"]["attempts_actions_work"] == next_turn["current"]["work"]
    assert any(w["status"] == "cancelled" for w in next_turn["core"]["works"])


@pytest.mark.parametrize("crash_window", ["input_claim", "route_child_claim"])
def test_process_kill_before_mapping_save_requires_cancel(
    tmp_path: Path, crash_window: str
) -> None:
    import json
    import subprocess
    import sys

    root = tmp_path / "data"
    handle({"data_root": str(root), "session_id": "setup", "command": "attach"})
    script = """
import os, sys
from zaratustra_app.native_session import NativeSession
from zaratustra_app.pi_host import handle
root, window = sys.argv[1:]
base = {"data_root": root, "session_id": "killed-pi"}
def die_before_mapping(self, revision, value):
    os._exit(91)
if window == "input_claim":
    NativeSession._save = die_before_mapping
handle(base | {"command": "input", "event_id": "durable-input",
               "text": "Exact fictional input before process kill"})
NativeSession._save = die_before_mapping
handle(base | {"command": "tool", "name": "route", "call_id": "route-before-kill", "payload": {
    "changes": [{"id": "durable-activity", "kind": "activity",
                 "key": "durable-activity", "body": "Fictional retained Activity"}],
    "expected_heads": {"durable-activity": 0},
    "outputs": [{"id": "durable-activity", "revision": 1}],
    "next_work": {"scope": "durable-activity", "goal": "Fictional useful work", "inputs": []}}})
"""
    process = subprocess.run(
        [sys.executable, "-c", script, str(root), crash_window],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert process.returncode == 91, process.stderr
    fresh = {"data_root": str(root), "session_id": "fresh-pi"}
    reopened = handle(fresh | {"command": "reopen"})
    expected_actions = 1 if crash_window == "input_claim" else 2

    def retained_actions() -> set[str]:
        page = handle(
            fresh
            | {
                "command": "tool",
                "name": "read",
                "call_id": "inspect-actions",
                "payload": {"operation": "read_page", "arguments": {"table": "actions"}},
            }
        )
        assert not page["has_more"]
        return {a["id"] for a in page["rows"]}

    retained_before = retained_actions()
    assert len(retained_before) == expected_actions
    assert len(reopened["core"]["actions"]) == (0 if crash_window == "input_claim" else 1)
    if crash_window == "input_claim":
        assert reopened["unmapped_work"]
    else:
        assert reopened["current"]["incomplete"] is True
        assert reopened["current"]["scope"] == "durable-activity"
        with pytest.raises(CoreError, match="recovered_claim"):
            handle(
                fresh
                | {"command": "tool", "name": "result", "call_id": "unsafe-replay", "payload": {}}
            )
    assert handle(fresh | {"command": "cancel"})["state"] == "cancelled"
    new = handle(
        fresh
        | {"command": "input", "event_id": "new-input", "text": "Explicit new fictional request"}
    )
    assert len(new["core"]["actions"]) == 1
    retained_after = retained_actions()
    assert len(retained_after) == expected_actions + 1 and retained_before < retained_after
    messages = handle(
        fresh
        | {
            "command": "tool",
            "name": "read",
            "call_id": "inspect-input",
            "payload": {"operation": "read_page", "arguments": {"table": "messages"}},
        }
    )["rows"]
    assert (
        base64.b64decode(messages[0]["raw"]).decode() == "Exact fictional input before process kill"
    )
    if crash_window == "route_child_claim":
        assert any(h["id"] == "durable-activity" for h in new["core"]["heads"])
    assert json.loads(new["core"]["works"][-1]["body"])["call_limit"] is None
