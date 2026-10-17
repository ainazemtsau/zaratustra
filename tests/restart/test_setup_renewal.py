"""Independent renewal/race observations on disposable Core, no inference."""

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app import Coordinator
from zaratustra_core import Core, CoreError

from .support import inspect


def setup(root: Path, *, limit: int | None = None) -> tuple[Any, Any, Any]:
    core, token = Core.initialize(root)
    owner = core.connect(token)
    executor = core.connect(
        core.grant(
            token,
            "setup",
            [
                "read",
                "prepare_attempt",
                "claim_dispatch",
                "observe_attempt",
                "commit_outcome",
                "renew_setup",
                "apply_changes",
                "open_work",
                "reserve_tool",
                "control_work",
            ],
            origin="host",
        )
    )
    owner.call(
        "apply_changes",
        {
            "changes": [
                {"id": "method", "kind": "method", "key": "setup", "body": "A small useful step"},
                {
                    "id": "profile",
                    "kind": "profile",
                    "key": "setup",
                    "body": {"setup_admission": "native-setup/v1"},
                },
            ]
        },
        "seed",
        expected_heads={"method": 0, "profile": 0},
    )
    owner.call(
        "open_work",
        {
            "id": "creation",
            "conversation": "creation",
            "goal": "Create useful fictional Activity",
            "method_ref": {"id": "method", "revision": 1},
            "call_limit": limit,
            "continuation_policy": "durable",
            "execution_policy": "setup-final-only/v1",
        },
        "open",
    )
    coordinator = Coordinator(executor)
    coordinator.prepare("creation", "first", {"id": "profile", "revision": 1})
    executor.call(
        "claim_dispatch",
        {
            "attempt_id": "first",
            "generation": 1,
            "resource_upper": None if limit is None else 1,
        },
        "claim",
        action_id="first-action",
    )
    return core, owner, executor


def renewal() -> dict[str, Any]:
    return {"attempt_id": "first", "generation": 1, "work_revision": 2}


def terminal(executor: Any) -> dict[str, Any]:
    return dict(
        executor.call(
            "observe_attempt",
            {
                "attempt_id": "first",
                "event_id": "terminal",
                "kind": "terminal",
                "raw_base64": base64.b64encode(b"retained actual terminal").decode(),
            },
            "terminal",
        )
    )


def test_unknown_renewal_preserves_action_usage_and_fences_late_reply(tmp_path: Path) -> None:
    core, _, executor = setup(tmp_path / "core", limit=3)
    executor.call(
        "observe_attempt",
        {
            "attempt_id": "first",
            "event_id": "lost",
            "kind": "unknown",
        },
        "lost",
    )
    before = inspect(core, "actions")
    receipt = executor.call("renew_setup", renewal(), "renew")
    assert receipt == executor.call("renew_setup", renewal(), "renew")
    assert inspect(core, "actions") == before
    work = inspect(core, "works")[0]
    assert (work["generation"], work["reserved"], work["status"]) == (2, 1, "ready")
    Coordinator(executor).prepare("creation", "second", {"id": "profile", "revision": 1})
    late = terminal(executor)
    assert late["late"] is True
    with pytest.raises(CoreError, match="generation"):
        executor.call(
            "commit_outcome",
            {
                "attempt_id": "first",
                "generation": 1,
                "terminal_event": "terminal",
                "original_cursor": 0,
                "processed_cutoff": 0,
                "state": "completed",
                "text": "old",
            },
            "old-commit",
        )
    assert inspect(core, "results") == []
    assert inspect(core, "attempts")[0]["status"] == "superseded"


def test_terminal_vs_renewal_has_one_winner(tmp_path: Path) -> None:
    core, _, executor = setup(tmp_path / "core")

    def race(operation: str) -> Any:
        try:
            return (
                terminal(executor)
                if operation == "terminal"
                else executor.call("renew_setup", renewal(), "renew")
            )
        except CoreError as error:
            return error.field

    with ThreadPoolExecutor(max_workers=2) as pool:
        observed, renewed = list(pool.map(race, ["terminal", "renew"]))
    if isinstance(renewed, dict):
        assert observed["late"] is True
        assert inspect(core, "works")[0]["generation"] == 2
    else:
        assert renewed == "setup.recover_terminal"
        assert observed["late"] is False
        executor.call(
            "commit_outcome",
            {
                "attempt_id": "first",
                "generation": 1,
                "terminal_event": "terminal",
                "original_cursor": 0,
                "processed_cutoff": 0,
                "state": "completed",
                "text": "saved",
            },
            "commit",
        )
        assert len(inspect(core, "results")) == 1


def test_final_only_and_cancel_and_stale_guards(tmp_path: Path) -> None:
    core, _, executor = setup(tmp_path / "core")
    with pytest.raises(CoreError, match="final_only"):
        executor.call(
            "reserve_tool",
            {
                "attempt_id": "first",
                "generation": 1,
                "native_id": "write",
                "command_id": "write",
            },
            "reserve",
        )
    with pytest.raises(CoreError, match="setup.work"):
        executor.call("renew_setup", renewal() | {"work_revision": 1}, "stale")
    executor.call(
        "control_work",
        {
            "work_id": "creation",
            "revision": 2,
            "action": "cancel",
        },
        "cancel",
    )
    with pytest.raises(CoreError):
        executor.call("renew_setup", renewal(), "cancelled")
    assert inspect(core, "works")[0]["status"] == "cancelled"


def test_old_profile_cannot_get_renewal(tmp_path: Path) -> None:
    core, owner, executor = setup(tmp_path / "core")
    # A standard Work with otherwise identical host identity has no renewal authority.
    owner.call("control_work", {"work_id": "creation", "revision": 2, "action": "cancel"}, "end")
    owner.call(
        "open_work",
        {
            "id": "ordinary",
            "conversation": "ordinary",
            "goal": "Ordinary coding",
            "method_ref": {"id": "method", "revision": 1},
            "continuation_policy": "durable",
        },
        "ordinary",
    )
    Coordinator(executor).prepare("ordinary", "ordinary-attempt", {"id": "profile", "revision": 1})
    with pytest.raises(CoreError, match="setup.policy"):
        executor.call(
            "renew_setup",
            {
                "attempt_id": "ordinary-attempt",
                "generation": 1,
                "work_revision": 2,
            },
            "ordinary-renew",
        )
    assert (
        json.loads(inspect(core, "works")[0]["body"])["execution_policy"] == "setup-final-only/v1"
    )
