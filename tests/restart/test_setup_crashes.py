"""Actual abrupt process exits at durable setup boundaries; recovery uses public API."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from zaratustra_core import Core

from .support import inspect
from .test_activity_setup import session


@pytest.mark.parametrize(
    "window",
    [
        "claim-before-mapping",
        "during-commit",
        "terminal-before-commit",
        "result-before-display",
    ],
)
def test_setup_process_kill(tmp_path: Path, window: str) -> None:
    root = tmp_path / "core"
    result = subprocess.run(
        [sys.executable, "-m", "tests.restart.setup_crash_worker", str(root), window],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=30,
    )
    assert result.returncode == 73, result.stderr
    core = Core(root)
    token = (root / "fictional-owner").read_text(encoding="utf-8")
    before = inspect(core, "results")
    if window == "during-commit":
        assert not any(r["id"] == "checkpoint" for r in inspect(core, "records"))
        assert len(before) == 1
    if window == "result-before-display":
        assert len(before) == 2
    recovered = session(core, token, "fresh-process-pi").reopen()
    assert recovered["current"]["managed_setup"] is True
    assert recovered["current"]["attempt"]
    if window == "claim-before-mapping":
        assert inspect(core, "records") and not any(
            r["kind"] == "activity" for r in inspect(core, "records")
        )
        assert len(inspect(core, "works")) == 1
    else:
        assert len([r for r in inspect(core, "records") if r["id"] == "checkpoint"]) == 1
        assert len(inspect(core, "results")) == 2
        assert recovered["current"]["work"] != json.loads(before[0]["body"])["next_work_id"]
    assert (
        len([w for w in inspect(core, "works") if w["status"] not in {"completed", "cancelled"}])
        == 1
    )
