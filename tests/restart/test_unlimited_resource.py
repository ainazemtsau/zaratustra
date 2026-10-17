"""Production has explicit unbounded resources; finite evaluation bounds remain real."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app import Coordinator, Driver
from zaratustra_core import CoreError

from .support import METHOD, PROFILE, fixture, inspect


def test_unlimited_ready_work_continues_beyond_eight_without_hidden_sentinel(
    tmp_path: Path,
) -> None:
    core, owner, client = fixture(tmp_path)
    coordinator = Coordinator(client)
    coordinator.open_work(
        {
            "id": "unlimited",
            "conversation": "production",
            "goal": "Continue",
            "method_ref": METHOD,
            "call_limit": None,
            "continuation_policy": "durable",
        }
    )
    contexts: list[dict[str, Any]] = []

    def answer(context: dict[str, Any], action: str) -> bytes:
        contexts.append(context)
        return b'{"state":"ready","text":"Retained ordinary progress"}'

    executor = Driver(answer)
    executor.resource_upper = None
    for index in range(12):
        identity = "unlimited:" + str(index)
        prepared = coordinator.prepare("unlimited", identity, PROFILE)
        coordinator.dispatch(identity, prepared["generation"], executor)
        assert coordinator.recover(identity)["state"] == "ready"
    work = next(w for w in inspect(core, "works") if w["id"] == "unlimited")
    assert json.loads(work["body"])["call_limit"] is None
    assert work["status"] == "ready" and work["reserved"] == 0
    assert len(contexts) == 12
    assert all(c["resource_state"]["mode"] == "unlimited" for c in contexts)
    assert all(c["resource_state"]["reservation_upper"] is None for c in contexts)
    core.backup(owner.token, tmp_path / "verified-unlimited-backup")


def test_finite_work_cannot_admit_an_unbounded_attempt(tmp_path: Path) -> None:
    core, _, client = fixture(tmp_path)
    coordinator = Coordinator(client)
    coordinator.prepare("work", "finite-attempt", PROFILE)
    executor = Driver(lambda *_: b'{"state":"completed","text":"not sent"}')
    executor.resource_upper = None
    with pytest.raises(CoreError, match="resource_upper"):
        coordinator.dispatch("finite-attempt", 1, executor)
    assert not inspect(core, "actions")


def test_unlimited_continuation_preserves_policy_and_backup(tmp_path: Path) -> None:
    from zaratustra_app import Conversation

    from .ordinary_support import OrdinaryReceiver

    core, owner, _ = fixture(tmp_path)
    session = Conversation(core, owner.token, "unlimited-native-parity")
    receiver = OrdinaryReceiver()
    receiver.outputs = [{"state": "completed", "text": "Useful retained result"}]
    executor = Driver(receiver)
    executor.resource_upper = None
    session.submit("An ordinary unbounded request")
    assert session.run(executor, {"mode": "unlimited"})["state"] == "completed"
    works = [w for w in inspect(core, "works") if w["conversation"] == "unlimited-native-parity"]
    assert len(works) == 2
    assert all(json.loads(w["body"])["call_limit"] is None for w in works)
    assert all(w["reserved"] == 0 for w in works)
    core.backup(owner.token, tmp_path / "continuation-backup")
