"""Fresh public API reproductions for the three independent review findings."""

from pathlib import Path

import pytest
from zaratustra_app import Coordinator, Driver
from zaratustra_core import Client, CoreError, Request

from .support import PROFILE, Receiver, fixture, inspect
from .test_contract import outcome, prepared


def tool_request(client: Client, command: str = "tool-change") -> Request:
    return client.request(
        "apply_changes",
        {
            "changes": [
                {"id": "effect", "kind": "data", "key": "effect", "body": "forbidden effect"}
            ],
            "tool": {"attempt_id": "A1", "generation": 1, "native_id": "tool"},
        },
        command,
        expected_heads={"effect": 0},
    )


def test_correlated_tool_requires_claim(tmp_path: Path) -> None:
    core, _, executor, _ = prepared(tmp_path)
    with pytest.raises(CoreError, match="denied"):
        executor.call(
            "reserve_tool",
            {"attempt_id": "A1", "generation": 1, "native_id": "tool", "command_id": "tool-change"},
            "reserve",
        )
    with pytest.raises(CoreError, match="denied"):
        executor.send(tool_request(executor))
    assert inspect(core, "actions") == inspect(core, "tool_calls") == []
    assert not any(h["id"] == "effect" for h in inspect(core, "heads"))


def test_correlated_tool_requires_live_attempt(tmp_path: Path) -> None:
    core, _, executor, coordinator = prepared(tmp_path)
    coordinator.dispatch("A1", 1, Driver(Receiver()))
    coordinator.recover("A1")
    with pytest.raises(CoreError, match="stale_basis"):
        executor.call(
            "reserve_tool",
            {"attempt_id": "A1", "generation": 1, "native_id": "late", "command_id": "late-change"},
            "late-reserve",
        )
    with pytest.raises(CoreError, match="stale_basis"):
        executor.send(tool_request(executor, "late-change"))
    assert not any(h["id"] == "effect" for h in inspect(core, "heads"))
    assert inspect(core, "works")[0]["status"] == "waiting"


def test_correlated_tool_requires_claimed_executor(tmp_path: Path) -> None:
    core, owner, executor, _ = prepared(tmp_path)
    executor.call(
        "claim_dispatch", {"attempt_id": "A1", "generation": 1}, "claim", action_id="A1:action"
    )
    other = core.connect(
        core.grant(owner.token, "other", ["read", "reserve_tool", "apply_changes"], origin="host")
    )
    with pytest.raises(CoreError, match="denied"):
        other.call(
            "reserve_tool",
            {"attempt_id": "A1", "generation": 1, "native_id": "tool", "command_id": "tool-change"},
            "other-reserve",
        )
    with pytest.raises(CoreError, match="denied"):
        other.send(tool_request(other))
    assert inspect(core, "tool_calls") == []
    assert not any(h["id"] == "effect" for h in inspect(core, "heads"))


@pytest.mark.parametrize(
    "subject,kind,key",
    [
        ("memory", "memory", "preference"),
        ("method", "method", "conversation"),
        ("profile", "profile", "local-scripted"),
    ],
)
def test_correlated_tool_rechecks_basis_at_effect(
    tmp_path: Path, subject: str, kind: str, key: str
) -> None:
    core, owner, executor = fixture(tmp_path)
    owner.call(
        "open_work",
        {
            "id": "basis-work",
            "conversation": "basis",
            "goal": "check exact current basis",
            "method_ref": {"id": "method", "revision": 1, "role": "must_be_current"},
            "inputs": [{"id": "memory", "revision": 1, "role": "must_be_current"}],
            "call_limit": 2,
            "continuation_policy": "durable",
        },
        "basis-work",
    )
    Coordinator(executor).prepare("basis-work", "A1", PROFILE | {"role": "must_be_current"})
    executor.call(
        "claim_dispatch", {"attempt_id": "A1", "generation": 1}, "claim", action_id="A1:action"
    )
    executor.call(
        "reserve_tool",
        {"attempt_id": "A1", "generation": 1, "native_id": "tool", "command_id": "tool-change"},
        "reserve",
    )
    owner.call(
        "apply_changes",
        {
            "changes": [
                {
                    "id": subject,
                    "kind": kind,
                    "key": key,
                    "body": "new required basis",
                }
            ]
        },
        "memory-update",
        expected_heads={subject: 1},
    )
    with pytest.raises(CoreError, match="stale_basis"):
        executor.send(tool_request(executor))
    with pytest.raises(CoreError, match="stale_basis"):
        executor.call(
            "reserve_tool",
            {"attempt_id": "A1", "generation": 1, "native_id": "new", "command_id": "new-change"},
            "new-reserve",
        )
    assert not any(h["id"] == "effect" for h in inspect(core, "heads"))
    assert inspect(core, "tool_calls")[0]["receipt"] is None


def test_initial_work_cannot_bypass_authority(tmp_path: Path) -> None:
    core, owner, _ = fixture(tmp_path)
    actor = core.connect(core.grant(owner.token, "records-only", ["read", "apply_changes"]))
    initial = {
        "id": "nested",
        "conversation": "nested",
        "goal": "nested",
        "method_ref": {"id": "method", "revision": 1},
        "inputs": [],
        "call_limit": 1,
        "continuation_policy": "durable",
    }
    with pytest.raises(CoreError, match="denied"):
        actor.call("open_work", initial, "direct")
    with pytest.raises(CoreError, match="denied"):
        actor.call(
            "apply_changes",
            {
                "changes": [
                    {"id": "new-activity", "kind": "activity", "key": "new", "body": "activity"}
                ],
                "initial_work": initial,
            },
            "nested",
            expected_heads={"new-activity": 0},
        )
    assert not any(w["id"] == "nested" for w in inspect(core, "works"))
    assert not any(h["id"] == "new-activity" for h in inspect(core, "heads"))


def test_outcome_changes_cannot_bypass_authority(tmp_path: Path) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    coordinator.dispatch("A1", 1, Driver(Receiver()))
    actor = core.connect(
        core.grant(owner.token, "outcome-only", ["read", "commit_outcome"], origin="host")
    )
    with pytest.raises(CoreError, match="denied"):
        actor.call(
            "commit_outcome",
            outcome()
            | {
                "changes": [
                    {"id": "nested", "kind": "memory", "key": "nested", "body": "unauthorized"}
                ]
            },
            "nested",
            expected_heads={"nested": 0},
        )
    assert not any(h["id"] == "nested" for h in inspect(core, "heads"))
    assert inspect(core, "results") == []
    assert inspect(core, "conversations")[0]["cursor"] == 0
