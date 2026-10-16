"""Semantic prose keeps exact bytes; identity slots retain their own limits."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app import Coordinator, Driver
from zaratustra_core import Core, CoreError

from .ordinary_support import routing
from .support import METHOD, PROFILE, fixture, inspect
from .test_work_handoff import commit, routed

LONG = "Arbitrary prose / Произвольный текст 🌊\n" * 20


@pytest.mark.parametrize("operation", ["open_work", "apply_changes"])
def test_long_goal_shared_admission_preserves_bytes(tmp_path: Path, operation: str) -> None:
    core, owner, _ = fixture(tmp_path)
    work = {
        "id": "long-work",
        "conversation": "other",
        "goal": LONG,
        "method_ref": METHOD,
        "inputs": [],
        "call_limit": 2,
        "continuation_policy": "durable",
    }
    if operation == "apply_changes":
        owner.call(
            operation,
            {
                "changes": [
                    {"id": "activity", "kind": "activity", "key": "long", "body": "fixture"}
                ],
                "initial_work": work,
            },
            "long",
            expected_heads={"activity": 0},
        )
    else:
        owner.call(operation, work, "long")
    saved = next(w for w in inspect(core, "works") if w["id"] == "long-work")
    assert json.loads(saved["body"])["goal"].encode() == LONG.encode()
    core.backup(owner.token, tmp_path / "backup")
    restored, token = Core.restore_quarantined(tmp_path / "backup", tmp_path / "restored")
    state = restored.connect(token).call("read_snapshot", {}, "check")
    assert (
        json.loads(next(w for w in state["works"] if w["id"] == "long-work")["body"])[
            "goal"
        ].encode()
        == LONG.encode()
    )


def test_long_goal_c8_handoff_keeps_exact_prose(tmp_path: Path) -> None:
    core, owner, client, _, payload = routed(tmp_path)
    payload["next_work"]["goal"] = LONG
    try:
        result: Any = commit(client, payload)
    except CoreError as error:
        result = error
    assert isinstance(result, dict), "C8 must admit nonempty prose beyond the identity length cap"
    child = next(w for w in inspect(core, "works") if w["id"] == result["next_work_id"])
    assert json.loads(child["body"])["goal"].encode() == LONG.encode()
    assert inspect(core, "conversations")[0]["cursor"] == 0
    assert child["reserved"] == 0 and json.loads(child["body"])["call_limit"] == 2
    core.backup(owner.token, tmp_path / "backup")


def test_long_wait_question_is_prose_and_replay_is_send_free(tmp_path: Path) -> None:
    core, _, client = fixture(tmp_path)
    coordinator = Coordinator(client)
    coordinator.prepare("work", "attempt", PROFILE)
    calls: list[str] = []
    raw = json.dumps(
        {"state": "waiting", "text": "question", "wait": {"id": "wait", "question": LONG}}
    ).encode()

    def receive(_: Any, action: str) -> bytes:
        calls.append(action)
        return raw

    coordinator.dispatch("attempt", 1, Driver(receive))
    try:
        result: Any = coordinator.recover("attempt")
    except CoreError as error:
        result = error
    assert isinstance(result, dict), "A valid long addressed question must commit atomically"
    assert json.loads(inspect(core, "waits")[0]["body"])["question"].encode() == LONG.encode()
    assert Coordinator(Core(core.root).connect(client.token)).recover("attempt") == result
    assert len(calls) == 1 and inspect(core, "works")[0]["reserved"] == 2


@pytest.mark.parametrize("field", ["id", "scope", "method_ref.id"])
def test_long_prose_does_not_relax_identity_limits(tmp_path: Path, field: str) -> None:
    core, owner, _ = fixture(tmp_path)
    work = {
        "id": "long-work",
        "conversation": "other",
        "goal": LONG,
        "method_ref": METHOD,
        "inputs": [],
        "call_limit": 2,
        "continuation_policy": "durable",
    }
    if field == "method_ref.id":
        work["method_ref"] = {"id": "x" * 241, "revision": 1}
    else:
        work[field] = "x" * 241
    with pytest.raises(CoreError) as error:
        owner.call("open_work", work, "invalid")
    assert error.value.field == field and len(inspect(core, "works")) == 1


@pytest.mark.parametrize("goal", ["", None, 7, True, []])
def test_goal_remains_nonempty_strict_text(tmp_path: Path, goal: Any) -> None:
    core, _, client, _, payload = routed(tmp_path)
    payload["next_work"]["goal"] = goal
    with pytest.raises(CoreError) as error:
        commit(client, payload)
    assert error.value.field == "next_work.goal" and not inspect(core, "results")
    assert not any(h["id"] == "activity" for h in inspect(core, "heads"))


def test_cli_known_invalid_retains_terminal_without_resend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    from zaratustra_app import cli

    core, token = Core.initialize(tmp_path / "space")
    (core.root / "owner.credential").write_text(token)
    profile = tmp_path / "profile.json"
    profile.write_text(
        json.dumps(
            {
                "pi_cli": "fictional",
                "endpoint": "https://api.openai.com/v1",
                "model": "gpt-6-luna",
                "credential_env": "FICTIONAL",
                "max_tokens": 64,
            }
        )
    )
    calls: list[dict[str, Any]] = []
    raw = b"PRIVATE_SENTINEL malformed JSON"

    def receive(context: dict[str, Any], _: str) -> bytes:
        calls.append(context)
        return raw

    class FakePi(Driver):
        def __init__(self, *_: Any, **__: Any):
            super().__init__(receive)

    monkeypatch.setattr(cli, "Pi", FakePi)
    args = [
        "entry",
        "--data-root",
        str(core.root),
        "chat",
        "--profile-file",
        str(profile),
        "--call-limit",
        "8",
    ]
    for suffix in [["--message", "fictional input"], []]:
        monkeypatch.setattr("sys.argv", args + suffix)
        try:
            status: Any = cli.main()
        except CoreError as error:
            status = error
        assert status == 1, "Known Core refusal must return a CLI failure instead of escaping"
        captured = capsys.readouterr()
        assert json.loads(captured.err)["error"]["code"] == "invalid_request"
        assert "Traceback" not in captured.err and "PRIVATE_SENTINEL" not in captured.err
    assert len(calls) == 1 and len(inspect(core, "actions")) == 1
    assert inspect(core, "works")[0]["reserved"] == 2
    assert inspect(core, "conversations")[0]["cursor"] == 0 and not inspect(core, "results")
    observation = json.loads(inspect(core, "observations")[0]["body"])
    assert base64.b64decode(observation["raw_base64"]) == raw


def test_cli_valid_path_unchanged_and_developer_errors_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    from zaratustra_app import cli

    core, token = Core.initialize(tmp_path / "space")
    (core.root / "owner.credential").write_text(token)
    profile = tmp_path / "profile.json"
    profile.write_text(
        json.dumps(
            {
                "pi_cli": "fictional",
                "endpoint": "https://api.openai.com/v1",
                "model": "gpt-6-luna",
                "credential_env": "FICTIONAL",
                "max_tokens": 64,
            }
        )
    )
    calls: list[dict[str, Any]] = []

    def receive(context: dict[str, Any], _: str) -> bytes:
        calls.append(context)
        if context["response_contract"]["version"] == "ordinary-routing/1":
            return json.dumps(routing(context)).encode()
        activity = next(r for r in context["catalog"] if r["id"] == context["work"]["scope"])
        return json.dumps(
            {
                "state": "completed",
                "text": "useful fixture result",
                "outputs": [{"id": activity["id"], "revision": activity["revision"]}],
            }
        ).encode()

    class FakePi(Driver):
        def __init__(self, *_: Any, **__: Any):
            super().__init__(receive)

    monkeypatch.setattr(cli, "Pi", FakePi)
    monkeypatch.setattr(
        "sys.argv",
        [
            "entry",
            "--data-root",
            str(core.root),
            "chat",
            "--profile-file",
            str(profile),
            "--call-limit",
            "8",
            "--message",
            "fictional input",
        ],
    )
    assert cli.main() == 0
    output = capsys.readouterr()
    assert output.out == "useful fixture result\n" and not output.err
    assert len(calls) == 2

    def broken() -> int:
        raise RuntimeError("developer error")

    monkeypatch.setattr(cli, "_main", broken)
    with pytest.raises(RuntimeError, match="developer error"):
        cli.main()
