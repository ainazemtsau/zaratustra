"""Disposable process fault windows; never imported by product code."""

import os
import sys
from pathlib import Path
from typing import Any

from zaratustra_app.native_session import NativeSession
from zaratustra_core import Core

from tests.restart.test_activity_setup import PROFILE, route


def main() -> None:
    root, mode = Path(sys.argv[1]), sys.argv[2]
    core, token = Core.initialize(root)
    (root / "fictional-owner").write_text(token, encoding="utf-8")
    native = NativeSession(core, token, "killed-pi")
    native.profile = PROFILE
    if mode == "claim-before-mapping":
        native._save = lambda *_: os._exit(73)  # type: ignore[method-assign]
        native.input("human", "Create a fictional Activity")
        raise AssertionError("Kill window was not reached")
    native.input("human", "Create a fictional Activity")
    origin = route(native)["current"]
    native.tool(
        "result",
        "stage",
        {
            "outputs": [{"id": "fictional", "revision": 1}],
            "changes": [
                {
                    "id": "checkpoint",
                    "kind": "data",
                    "key": "checkpoint",
                    "scope": "fictional",
                    "body": "A useful durable step",
                }
            ],
            "expected_heads": {"checkpoint": 0},
            "next_work": {"goal": "Continue from the checkpoint", "inputs": []},
        },
        origin,
    )
    if mode == "during-commit":
        original = core._changes

        def kill_changes(*args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            if any(c["id"] == "checkpoint" for c in args[1]):
                os._exit(73)  # SQL writes executed, transaction not committed.
            return result

        core._changes = kill_changes  # type: ignore[method-assign]
    elif mode == "terminal-before-commit":
        native.coordinator.recover = lambda *_a, **_k: os._exit(73)  # type: ignore[method-assign]
    elif mode == "result-before-display":
        original_save = native._save

        def kill_save(revision: int, value: dict[str, Any]) -> None:
            if value.get("managed_setup") and not value.get("attempt"):
                os._exit(73)  # Result + child committed, mapping/UI not updated.
            original_save(revision, value)

        native._save = kill_save  # type: ignore[method-assign]
    native.settled("actual-terminal", "A useful durable step is ready.", False, origin=origin)
    raise AssertionError("Kill window was not reached")


if __name__ == "__main__":
    main()
