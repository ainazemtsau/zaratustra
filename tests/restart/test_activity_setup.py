"""Saved AI-selected steps, durable wait and origin fencing through public App/Core."""

import json
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app.native_session import NativeSession
from zaratustra_core import Core, CoreError

from .support import inspect

PROFILE = {
    "adapter": "ordinary-native-pi",
    "model": "fictional",
    "setup_admission": "native-setup/v1",
}


def session(core: Core, token: str, identity: str) -> NativeSession:
    value = NativeSession(core, token, identity)
    value.profile = PROFILE
    return value


def route(native: NativeSession) -> dict[str, Any]:
    origin = native.context()["current"]
    return native.tool(
        "route",
        "route",
        {
            "changes": [
                {
                    "id": "fictional",
                    "kind": "activity",
                    "key": "fictional",
                    "body": "A fictional observation journal, chosen by the model.",
                }
            ],
            "expected_heads": {"fictional": 0},
            "outputs": [{"id": "fictional", "revision": 1}],
            "next_work": {
                "scope": "fictional",
                "goal": "Build a useful first journal",
                "inputs": [],
                "setup": True,
            },
        },
        origin,
    )


def test_checkpoint_lost_mapping_reopen_then_natural_wait_reply(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "core")
    native = session(core, token, "pi-one")
    native.input("human", "Help me create a fictional bird observation journal")
    origin = route(native)["current"]
    payload = {
        "changes": [
            {
                "id": "journal",
                "kind": "data",
                "key": "journal",
                "scope": "fictional",
                "body": "Initial useful journal checkpoint",
            }
        ],
        "expected_heads": {"journal": 0},
        "outputs": [{"id": "fictional", "revision": 1}, {"id": "journal", "revision": 1}],
        "next_work": {
            "goal": "Ask only the needed location",
            "inputs": [{"id": "journal", "revision": 1}],
        },
    }
    native.tool("result", "stage", payload, origin)
    result = native.settled(
        "shown-one", "The first journal is saved; next choose a location.", False, origin=origin
    )
    assert result["next_work_id"]
    assert len(inspect(core, "results")) == 2  # Routing + actual saved step.
    # Lose the adapter pointer through its ordinary public host write, no SQL repair.
    revision, _ = native._load()
    native._save(revision, {})
    fresh = session(core, token, "pi-two")
    reopened = fresh.reopen()
    assert reopened["current"]["work"] == result["next_work_id"]
    assert reopened["current"]["scope"] == "fictional"
    assert "Initial useful journal checkpoint" in json.dumps(reopened["pinned"]["inputs"])
    assert result["text"] in json.dumps(reopened["pinned"]["prior_results"])
    origin2 = reopened["current"]
    fresh.tool(
        "result",
        "question",
        {
            "state": "waiting",
            "wait": {"id": "location", "question": "Which location?"},
            "outputs": [{"id": "fictional", "revision": 1}],
        },
        origin2,
    )
    fresh.settled("shown-two", "Which location?", False, origin=origin2)
    third = session(core, token, "pi-three")
    assert third.reopen()["waiting"][0]["question"] == "Which location?"
    answered = third.input("answer", "The fictional lake")
    assert answered["waiting"] == []
    assert answered["current"]["work"] == origin2["work"]
    assert len([r for r in inspect(core, "records") if r["kind"] == "activity"]) == 1


def test_claim_before_mapping_and_late_callbacks_never_use_new_attempt(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "core")
    first = session(core, token, "one")
    first.input("human", "Create a fictional working Activity")
    old = route(first)["current"]
    revision, _ = first._load()
    first._save(revision, {})
    second = session(core, token, "two")
    current = second.reopen()["current"]
    assert current["work"] == old["work"] and current["attempt"] != old["attempt"]
    assert second.observation("late-tool", {"tool": "fictional-read"}, old)["late"] is True
    assert second.settled("late-final", "Late old answer", False, origin=old)["state"] == "late"
    assert second.context()["current"]["attempt"] == current["attempt"]
    with pytest.raises(CoreError, match="native.origin"):
        second.tool("result", "old-call", {"outputs": []}, old)
    with pytest.raises(CoreError, match="final_only"):
        second.tool("change", "write", {"changes": [], "expected_heads": {}}, current)
    assert not any("Late old answer" in r["body"] for r in inspect(core, "results"))


def test_route_same_message_result_is_not_child_result(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "core")
    native = session(core, token, "one")
    old = native.input("human", "Create a fictional Activity")["current"]
    route(native)
    with pytest.raises(CoreError, match="native.origin"):
        native.tool(
            "result", "sibling-result", {"outputs": [{"id": "fictional", "revision": 1}]}, old
        )
    assert len(inspect(core, "results")) == 1


@pytest.mark.parametrize("flag", [None, False])
def test_new_activity_cannot_opt_out_of_setup(tmp_path: Path, flag: bool | None) -> None:
    core, token = Core.initialize(tmp_path / "core")
    native = session(core, token, "pi")
    origin = native.input("new", "Create a fictional Activity")["current"]
    child: dict[str, Any] = {"scope": "new", "goal": "Create a useful journal", "inputs": []}
    if flag is not None:
        child["setup"] = flag
    result = native.tool(
        "route",
        "route",
        {
            "changes": [{"id": "new", "kind": "activity", "key": "new", "body": "Actual goal"}],
            "expected_heads": {"new": 0},
            "outputs": [{"id": "new", "revision": 1}],
            "next_work": child,
        },
        origin,
    )
    assert result["current"]["managed_setup"] is True
    assert result["pinned"]["work"]["execution_policy"] == "setup-final-only/v1"


def test_existing_activity_keeps_ordinary_tools_profile(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "core")
    native = session(core, token, "pi")
    native.owner.call(
        "apply_changes",
        {
            "changes": [
                {
                    "id": "existing",
                    "kind": "activity",
                    "key": "existing",
                    "body": "Established work",
                }
            ]
        },
        "seed-existing",
        expected_heads={"existing": 0},
    )
    origin = native.input("new", "Continue ordinary fictional coding")["current"]
    result = native.tool(
        "route",
        "route",
        {
            "changes": [],
            "expected_heads": {},
            "outputs": [{"id": "existing", "revision": 1}],
            "next_work": {
                "scope": "existing",
                "goal": "Ordinary coding",
                "inputs": [],
                "setup": False,
            },
        },
        origin,
    )
    assert not result["current"].get("managed_setup")
    assert result["pinned"]["work"]["execution_policy"] == "standard"


def test_route_batch_cannot_create_another_activity_outside_selected_scope(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "core")
    native = session(core, token, "pi")
    origin = native.input("human", "Create a fictional Activity")["current"]
    with pytest.raises(CoreError, match="activity_scope"):
        native.tool(
            "route",
            "route",
            {
                "changes": [
                    {"id": identity, "kind": "activity", "key": identity, "body": "Fictional"}
                    for identity in ("selected", "bypass")
                ],
                "expected_heads": {"selected": 0, "bypass": 0},
                "outputs": [{"id": "selected", "revision": 1}],
                "next_work": {"scope": "selected", "goal": "Create", "inputs": []},
            },
            origin,
        )
    assert not any(r["kind"] == "activity" for r in inspect(core, "records"))
    assert inspect(core, "results") == []


def test_duplicate_terminal_and_cancel_do_not_repeat_saved_step(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "core")
    native = session(core, token, "pi")
    native.input("human", "Create a fictional Activity")
    origin = route(native)["current"]
    native.tool("result", "stage", {"outputs": [{"id": "fictional", "revision": 1}]}, origin)
    result = native.settled("actual", "The useful step.", False, origin=origin)
    from zaratustra_app.native_verdict import delivery

    shown = delivery(core, token, "fictional")
    assert shown["attempt_id"] == origin["attempt"] and shown["review"] is None
    assert shown["result"]["text"] == "The useful step."
    assert native.settled("actual", "The useful step.", False, origin=origin) == result
    with pytest.raises(CoreError, match="native.terminal"):
        native.settled("different", "Replacement text", False, origin=origin)
    assert len(inspect(core, "results")) == 2
    native.input("another", "Create another fictional Activity")
    _, current = native._load()
    work = next(w for w in inspect(core, "works") if w["id"] == current["work"])
    native.owner.call(
        "control_work",
        {"work_id": work["id"], "revision": work["revision"], "action": "cancel"},
        "cancel",
    )
    assert session(core, token, "fresh").reopen()["current"] == {}
    assert len(inspect(core, "attempts")) == 3
