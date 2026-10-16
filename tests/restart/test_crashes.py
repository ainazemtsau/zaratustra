"""Crash and concurrent-writer behavior through fresh interpreter processes."""

from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
import zaratustra_app
import zaratustra_core
from zaratustra_app import Coordinator, Driver
from zaratustra_core import CoreError

from .support import Receiver, fixture, ingest, inspect
from .test_contract import outcome, prepared

ROOT = Path(__file__).resolve().parents[2]


def child(packet: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    sources = [
        str(Path(zaratustra_core.__file__).parents[1]),
        str(Path(zaratustra_app.__file__).parents[1]),
        str(ROOT),
    ]
    script = (
        "import sys;sys.path[:0]="
        + repr(sources)
        + ";from tests.restart.crash_worker import main;main()"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", script],
        input=json.dumps(packet),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        cwd=ROOT,
    )
    if "MUTANT_REACHED" in result.stdout:
        print(result.stdout)
    return result


@pytest.mark.parametrize("phase", ["ingest_mid", "ingest_committed"])
def test_ingest_crash_atomic(tmp_path: Path, phase: str) -> None:
    core, owner, _ = fixture(tmp_path)
    before = {t: inspect(core, t) for t in ("messages", "intents", "receipts")}
    result = child({"root": str(core.root), "token": owner.token, "phase": phase})
    assert result.returncode == 91, result.stderr
    independent = child({"root": str(core.root), "phase": "oracle"})
    assert independent.returncode == 0, independent.stderr
    assert json.loads(independent.stdout)["conversations"] == inspect(core, "conversations")
    if phase == "ingest_mid":
        assert before == {t: inspect(core, t) for t in before}
    else:
        assert len(inspect(core, "messages")) == 21
        assert any(r["command"] == "input:21" for r in inspect(core, "receipts"))
        assert any(i["kind"] == "input" and "21" in i["body"] for i in inspect(core, "intents"))


@pytest.mark.parametrize("phase", ["outcome_mid", "outcome_after_final", "outcome_committed"])
def test_outcome_crash_atomic(tmp_path: Path, phase: str) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    coordinator.dispatch("A1", 1, Driver(Receiver()))
    ingest(owner, "21", "Now five minutes")
    payload = outcome() | {
        "changes": [{"id": "delivered", "kind": "data", "key": "result", "body": "saved result"}]
    }
    result = child(
        {
            "root": str(core.root),
            "token": executor.token,
            "phase": phase,
            "payload": payload,
            "heads": {"delivered": 0},
        }
    )
    assert result.returncode == 91, result.stderr
    independent = child({"root": str(core.root), "phase": "oracle"})
    assert independent.returncode == 0, independent.stderr
    assert json.loads(independent.stdout)["conversations"] == inspect(core, "conversations")
    if phase != "outcome_committed":
        assert inspect(core, "results") == []
        assert inspect(core, "conversations")[0]["cursor"] == 0
        assert not any(h["id"] == "delivered" for h in inspect(core, "heads"))
    else:
        assert len(inspect(core, "results")) == 1
        assert inspect(core, "conversations")[0]["cursor"] == 20
        assert any(h["id"] == "delivered" for h in inspect(core, "heads"))
        assert any(i["kind"] == "input" for i in inspect(core, "intents"))
        assert any(r["command"] == "crash-outcome" for r in inspect(core, "receipts"))


@pytest.mark.parametrize("phase", ["claim_before_send", "claim_after_receiver"])
def test_claim_crash_never_resends(tmp_path: Path, phase: str) -> None:
    core, _, executor, _ = prepared(tmp_path)
    result = child({"root": str(core.root), "token": executor.token, "phase": phase})
    assert result.returncode == 91, result.stderr
    independent = child({"root": str(core.root), "phase": "oracle"})
    assert independent.returncode == 0, independent.stderr
    assert json.loads(independent.stdout)["conversations"] == inspect(core, "conversations")
    receiver = Receiver()
    with pytest.raises(CoreError, match="outcome_unknown"):
        Coordinator(executor).dispatch("A1", 1, Driver(receiver))
    assert receiver.actions == []
    expected = 1 if phase == "claim_after_receiver" else 0
    effects = core.root / "receiver-effects.jsonl"
    actual = len(effects.read_bytes().splitlines()) if effects.exists() else 0
    assert actual == expected
    assert len(inspect(core, "actions")) == 1
    assert inspect(core, "works")[0]["reserved"] == 1


def test_fresh_process_retained_replay(tmp_path: Path) -> None:
    core, _, executor, coordinator = prepared(tmp_path)
    receiver = Receiver()
    coordinator.dispatch("A1", 1, Driver(receiver))
    packet = {"root": str(core.root), "token": executor.token, "phase": "recover"}
    first, second = child(packet), child(packet)
    assert first.returncode == second.returncode == 0, first.stderr + second.stderr
    assert json.loads(first.stdout) == json.loads(second.stdout)
    assert receiver.actions == ["A1:action"]
    assert len(inspect(core, "results")) == 1


def test_competing_outcomes_one_final(tmp_path: Path) -> None:
    core, _, executor, coordinator = prepared(tmp_path)
    coordinator.dispatch("A1", 1, Driver(Receiver()))

    def finish(n: int) -> str:
        try:
            executor.call("commit_outcome", outcome() | {"text": str(n)}, "final-" + str(n))
            return "committed"
        except CoreError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(finish, (1, 2)))
    assert sorted(results) == ["committed", "idempotency_conflict"]
    assert len(inspect(core, "results")) == 1
    assert inspect(core, "conversations")[0]["cursor"] == 20
