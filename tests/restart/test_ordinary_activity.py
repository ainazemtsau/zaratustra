"""General Activity lifecycle mechanics with explicit fictional executor choices."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app import Conversation, Driver
from zaratustra_core import Core, CoreError

from .ordinary_support import OrdinaryReceiver, routing
from .support import inspect


def test_multi_activity_correction_and_reopen(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "space")
    selected = ["first-activity", "first-activity", "other-activity"]
    calls: list[dict[str, Any]] = []
    phases: list[str] = []

    def receive(context: dict[str, Any], _: str) -> bytes:
        calls.append(context)
        phase = context["response_contract"]["version"]
        phases.append(phase)
        if phase == "ordinary-routing/1":
            result = routing(context, selected.pop(0))
        else:
            scope = context["work"]["scope"]
            activity = next(r for r in context["catalog"] if r["id"] == scope)
            data_id = scope + ":result"
            old = next((r for r in context["catalog"] if r["id"] == data_id), None)
            revision = old["revision"] if old else 0
            result = {
                "state": "completed",
                "text": "Useful result: " + context["raw_messages"][-1],
                "changes": [
                    {
                        "id": data_id,
                        "kind": "data",
                        "key": "result",
                        "scope": scope,
                        "body": context["raw_messages"][-1],
                    }
                ],
                "expected_heads": {data_id: revision},
                "outputs": [
                    {"id": scope, "revision": activity["revision"]},
                    {"id": data_id, "revision": revision + 1},
                ],
            }
        return json.dumps(result).encode()

    driver = Driver(receive)
    for text in ["fictional first task", "fictional correction", "different fictional task"]:
        session = Conversation(Core(core.root), token)
        session.submit(text)
        result = session.run(driver, {"profile": "fictional"}, 8)
        assert result["text"] == "Useful result: " + text
        before = len(calls)
        assert (
            Conversation(Core(core.root), token).run(driver, {"profile": "fictional"}, 8)["state"]
            == "idle"
        )
        assert len(calls) == before
    assert phases == ["ordinary-routing/1", "ordinary-execution/2"] * 3
    heads = inspect(core, "heads")
    assert {r["id"] for r in heads if r["kind"] == "activity"} == {
        "first-activity",
        "other-activity",
    }
    assert next(r for r in heads if r["id"] == "first-activity")["revision"] == 2
    for context in calls:
        if context["response_contract"]["version"] == "ordinary-execution/2":
            assert context["work"]["scope"] in {"first-activity", "other-activity"}
            assert context["raw_messages"]  # Original pending bytes, not copied prior text.
    assert inspect(core, "conversations")[0]["cursor"] == 3
    assert not inspect(core, "acceptance")


def test_addressed_reply_stays_in_existing_scoped_work(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "space")
    receiver = OrdinaryReceiver()
    driver = Driver(receiver)
    session = Conversation(core, token)
    session.submit("fictional practice")
    first = session.run(driver, {"profile": "fictional"}, 8)
    assert first["state"] == "waiting" and len(receiver.actions) == 2
    waiting = next(w for w in inspect(core, "works") if w["status"] == "waiting")
    session.submit("free correction")
    assert session.run(driver, {"profile": "fictional"}, 8)["reply_to"] == first["reply_to"]
    assert len(receiver.actions) == 2
    session.submit("addressed answer", first["reply_to"])
    result = session.run(driver, {"profile": "fictional"}, 8)
    assert result["state"] == "completed" and len(receiver.actions) == 3
    assert receiver.received[-1]["work"]["id"] == waiting["id"]
    assert receiver.received[-1]["response_contract"]["version"] == "ordinary-execution/2"
    assert len(inspect(core, "works")) == 2
    before = len(receiver.actions)
    assert (
        Conversation(Core(core.root), token).run(driver, {"profile": "fictional"}, 8)["state"]
        == "idle"
    )
    assert len(receiver.actions) == before


@pytest.mark.parametrize("when", ["before", "after"])
def test_handoff_reopen_uses_retained_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, when: str
) -> None:
    core, token = Core.initialize(tmp_path / "space")
    receiver = OrdinaryReceiver()
    receiver.outputs = [{"state": "completed", "text": "actual result"}]
    driver = Driver(receiver)
    session = Conversation(core, token)
    session.submit("fictional pending input")
    recover = session.coordinator.recover

    def crash(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if when == "before":
            raise RuntimeError("simulated host loss after retained raw terminal")
        recover(*args, **kwargs)
        raise RuntimeError("simulated host loss after atomic handoff")

    monkeypatch.setattr(session.coordinator, "recover", crash)
    with pytest.raises(RuntimeError, match="simulated host loss"):
        session.run(driver, {"profile": "fictional"}, 8)
    assert len(receiver.actions) == 1
    assert inspect(core, "conversations")[0]["cursor"] == 0
    reopened = Conversation(Core(core.root), token)
    try:
        result: Any = reopened.run(driver, {"profile": "fictional"}, 8)
    except CoreError as error:
        result = error
    assert isinstance(result, dict), "Reopen must continue the existing child without rediscovery"
    assert result["text"] == "actual result" and len(receiver.actions) == 2
    assert len(inspect(core, "works")) == 2
    assert inspect(core, "conversations")[0]["cursor"] == 1


def test_discovery_tool_cannot_publish_orphan_activity(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "space")
    calls = []

    def receive(context: dict[str, Any], _: str) -> bytes:
        calls.append(context)
        try:
            driver.tool_handler(
                "early-publication",
                {
                    "changes": [
                        {"id": "orphan", "kind": "activity", "key": "orphan", "body": "fictional"}
                    ],
                    "expected_heads": {"orphan": 0},
                },
            )
        except CoreError as error:
            assert error.field == "ordinary.routing_atomic_handoff"
        raise RuntimeError("fictional provider failure before handoff")

    driver = Driver(receive)
    session = Conversation(core, token)
    session.submit("fictional task")
    with pytest.raises(RuntimeError):
        session.run(driver, {"profile": "fictional"}, 8)
    assert len(calls) == 1
    assert not any(r["kind"] == "activity" for r in inspect(core, "heads"))
    assert not inspect(core, "tool_calls") and not inspect(core, "results")
    assert len(inspect(core, "works")) == 1 and inspect(core, "works")[0]["status"] == "blocked"


def test_scoped_execution_pins_only_applicable_memory(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "space")
    session = Conversation(core, token)
    changes = [
        {"id": key, "kind": "memory", "key": key, "scope": scope, "body": key}
        for key, scope in [("global", "space"), ("local", "activity"), ("foreign", "other")]
    ]
    session.owner.call(
        "apply_changes",
        {"changes": changes},
        "memory",
        expected_heads={c["id"]: 0 for c in changes},
    )
    receiver = OrdinaryReceiver()
    receiver.outputs = [{"state": "completed", "text": "useful"}]
    session.submit("fictional task")
    session.run(Driver(receiver), {"profile": "fictional"}, 8)
    inputs = {r["id"] for r in receiver.received[-1]["inputs"]}
    assert {"activity", "global", "local"} <= inputs and "foreign" not in inputs
    assert "local" not in {r["id"] for r in receiver.received[0]["inputs"]}


@pytest.mark.parametrize("damage", ["json", "list", "state", "output", "role", "input", "goal"])
def test_malformed_terminal_is_retained_without_resend(tmp_path: Path, damage: str) -> None:
    core, token = Core.initialize(tmp_path / "space")
    calls = []

    def receive(context: dict[str, Any], _: str) -> bytes:
        calls.append(context)
        value: Any = routing(context)
        if damage == "json":
            return b"{unfinished"
        if damage == "list":
            value = []
        elif damage == "state":
            value["state"] = []
        elif damage == "output":
            value["outputs"] = ["bad"]
        elif damage == "role":
            value["outputs"][0]["role"] = []
        elif damage == "input":
            value["next_work"]["inputs"] = [None]
        elif damage == "goal":
            value["next_work"].pop("goal")
        return json.dumps(value).encode()

    driver = Driver(receive)
    session = Conversation(core, token)
    session.submit("fictional task")
    for current in [session, Conversation(Core(core.root), token)]:
        with pytest.raises(CoreError, match="invalid_request"):
            current.run(driver, {"profile": "fictional"}, 8)
    assert len(calls) == 1
    observations = [json.loads(o["body"]) for o in inspect(core, "observations")]
    assert [o["kind"] for o in observations] == ["terminal"]
    assert not inspect(core, "results")
    assert not any(r["kind"] == "activity" for r in inspect(core, "heads"))


@pytest.mark.parametrize("cap", [1, 15])
def test_native_cap_below_sdk_floor_refused_before_runtime(tmp_path: Path, cap: int) -> None:
    from zaratustra_app import LiveProfile

    with pytest.raises(CoreError, match="unsupported_capability"):
        LiveProfile(
            endpoint="https://api.openai.com/v1",
            model="gpt-6-luna",
            auth_mode="pi-chatgpt",
            auth_path=str(tmp_path / "unused-auth.json"),
            max_tokens=cap,
            context_window=8192,
        )
    assert not list(tmp_path.iterdir())


def test_late_input_reroutes_before_first_dependent_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core, token = Core.initialize(tmp_path / "space")
    session = Conversation(core, token)
    calls: list[dict[str, Any]] = []
    choices = ["old-activity", "new-activity"]

    def receive(context: dict[str, Any], _: str) -> bytes:
        calls.append(context)
        if context["response_contract"]["version"] == "ordinary-routing/1":
            return json.dumps(routing(context, choices.pop(0))).encode()
        activity = next(r for r in context["catalog"] if r["id"] == context["work"]["scope"])
        return json.dumps(
            {
                "state": "completed",
                "text": "useful corrected result",
                "outputs": [{"id": activity["id"], "revision": activity["revision"]}],
            }
        ).encode()

    recover = session.coordinator.recover
    injected = False

    def late(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal injected
        result = recover(*args, **kwargs)
        if not injected and "next_work_id" in result:
            injected = True
            session.submit("late change before dependent dispatch")
        return result

    monkeypatch.setattr(session.coordinator, "recover", late)
    session.submit("initial request")
    result = session.run(Driver(receive), {"profile": "fictional"}, 8)
    assert result["text"] == "useful corrected result"
    assert [c["response_contract"]["version"] for c in calls] == [
        "ordinary-routing/1",
        "ordinary-routing/1",
        "ordinary-execution/2",
    ]
    assert calls[-1]["work"]["scope"] == "new-activity"
    assert calls[-1]["raw_messages"] == ["initial request", "late change before dependent dispatch"]
    assert calls[1]["work"]["scope"] == "old-activity"  # Old scope/history was not relabelled.
    assert sum(a["reserve"] for a in inspect(core, "actions")) == 6
    assert inspect(core, "conversations")[0]["cursor"] == 2
    core.backup(token, tmp_path / "backup")


def test_existing_method_adaptation_and_history_are_not_overwritten(tmp_path: Path) -> None:
    from zaratustra_app.conversation import CONVERSATION_METHOD

    core, token = Core.initialize(tmp_path / "space")
    owner = core.connect(token)
    owner.call(
        "apply_changes",
        {
            "changes": [
                {
                    "id": "conversation-method",
                    "kind": "method",
                    "key": "conversation/1",
                    "body": CONVERSATION_METHOD,
                }
            ]
        },
        "legacy",
        expected_heads={"conversation-method": 0},
    )
    receiver = OrdinaryReceiver()
    receiver.outputs = [{"state": "completed", "text": "useful"}]
    session = Conversation(core, token)
    session.submit("new fictional request")
    session.run(Driver(receiver), {"profile": "fictional"}, 8)
    legacy = owner.call("read_exact", {"id": "conversation-method", "revision": 1}, "read-legacy")
    assert legacy["body"]["value"] == CONVERSATION_METHOD
    assert (
        next(h for h in inspect(core, "heads") if h["id"] == "conversation-method")["revision"] == 1
    )


def test_scoped_execution_tool_cannot_reset_chain_budget(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "space")
    seen: list[dict[str, Any]] = []
    admissions: list[Any] = []

    def receive(context: dict[str, Any], _: str) -> bytes:
        seen.append(context)
        if context["response_contract"]["version"] == "ordinary-routing/1":
            return json.dumps(routing(context)).encode()
        activity = next(r for r in context["catalog"] if r["id"] == context["work"]["scope"])
        change = {
            "id": "forbidden-effect",
            "kind": "data",
            "key": "effect",
            "scope": activity["id"],
            "body": "fictional",
        }
        child = {
            "id": "independent-budget",
            "conversation": context["work"]["conversation"],
            "scope": activity["id"],
            "goal": "unrequested",
            "method_ref": context["work"]["method_ref"],
            "inputs": [{"id": activity["id"], "revision": activity["revision"]}],
            "call_limit": 1000,
            "continuation_policy": "durable",
        }
        try:
            admissions.append(
                driver.tool_handler(
                    "extra",
                    {
                        "changes": [change],
                        "expected_heads": {"forbidden-effect": 0},
                        "initial_work": child,
                    },
                )
            )
        except CoreError as error:
            admissions.append(error)
        return json.dumps(
            {
                "state": "completed",
                "text": "useful result",
                "outputs": [{"id": activity["id"], "revision": activity["revision"]}],
            }
        ).encode()

    driver = Driver(receive)
    session = Conversation(core, token)
    session.submit("fictional finite request")
    assert session.run(driver, {"profile": "fictional"}, 4)["text"] == "useful result"
    assert (
        isinstance(admissions[0], CoreError) and admissions[0].field == "native_tool.initial_work"
    )
    assert (
        Conversation(Core(core.root), token).run(driver, {"profile": "fictional"}, 4)["state"]
        == "idle"
    )
    assert len(seen) == 2 and all(c["raw_messages"] for c in seen)
    assert len(inspect(core, "works")) == 2
    assert sum(w["reserved"] for w in inspect(core, "works")) == 4
    assert not any(h["id"] == "forbidden-effect" for h in inspect(core, "heads"))
    assert not any(t["native_id"] == "extra" for t in inspect(core, "tool_calls"))
