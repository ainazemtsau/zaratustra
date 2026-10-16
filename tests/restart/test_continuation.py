"""Package B finite continuation matrix, observed through API and physical tables."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app import Coordinator, Driver, Pi
from zaratustra_core import Core, CoreError

from .support import PROFILE, Provider, Receiver, ingest, inspect, pi_cli
from .test_contract import prepared
from .test_crashes import child


def proof(root: Path, core: Core, case: str, receiver: Receiver | None = None) -> None:
    observed = {
        "case": case,
        "tables": {
            name: inspect(core, name)
            for name in (
                "works",
                "attempts",
                "actions",
                "observations",
                "results",
                "waits",
                "tool_calls",
                "conversations",
                "intents",
                "acceptance",
            )
        },
        "receiver_actions": receiver.actions if receiver else [],
        "processes": (core.root / "b-processes.jsonl").read_text(encoding="utf-8").splitlines()
        if (core.root / "b-processes.jsonl").exists()
        else [],
        "receiver_log_base64": base64.b64encode(
            (core.root / "receiver-effects.jsonl").read_bytes()
        ).decode()
        if (core.root / "receiver-effects.jsonl").exists()
        else None,
    }
    (root / "b-observation.json").write_text(json.dumps(observed, indent=2), encoding="utf-8")


def process_proof(core: Core, result: subprocess.CompletedProcess[str], phase: str) -> None:
    with (core.root / "b-processes.jsonl").open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(
                {
                    "phase": phase,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
            + chr(10)
        )


def control(client: Any, action: str) -> dict[str, Any]:
    state = Coordinator(client).snapshot()
    work = state["works"][0]
    return dict(
        client.call(
            "control_work",
            {"work_id": work["id"], "revision": work["revision"], "action": action},
            action + ":" + str(work["revision"]),
        )
    )


def reconcile(client: Any, state: str) -> None:
    client.call(
        "observe_attempt",
        {
            "attempt_id": "A1",
            "event_id": "proof-" + state,
            "kind": "reconcile",
            "evidence": {
                "action_id": "A1:action",
                "state": state,
                "receiver_ref": "fictional-receiver/physical-log#1",
            },
        },
        "proof-" + state,
    )


def reopen_recover(core: Core, token: str, attempt: str, pi: bool = False) -> dict[str, Any]:
    script = """
import json,sys
from pathlib import Path
from zaratustra_core import Core
from zaratustra_app import Coordinator
p=json.load(sys.stdin)
print(json.dumps(Coordinator(Core(Path(p['root'])).connect(p['token'])).recover(
    p['attempt'],pi=p['pi'])))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", script],
        input=json.dumps({"root": str(core.root), "token": token, "attempt": attempt, "pi": pi}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    process_proof(core, result, "reopen-recover-" + attempt)
    assert result.returncode == 0, result.stdout + result.stderr
    return dict(json.loads(result.stdout))


@pytest.mark.parametrize("stage", ["ready", "prepared", "claimed", "waiting", "blocked"])
@pytest.mark.parametrize("action", ["pause", "cancel"])
def test_control_fences_every_supported_stage(tmp_path: Path, stage: str, action: str) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    if stage == "ready":
        control(owner, "refresh")
    elif stage in {"claimed", "blocked"}:
        executor.call(
            "claim_dispatch", {"attempt_id": "A1", "generation": 1}, "claim", action_id="A1:action"
        )
        if stage == "blocked":
            executor.call(
                "observe_attempt",
                {"attempt_id": "A1", "event_id": "lost", "kind": "unknown"},
                "lost",
            )
    elif stage == "waiting":
        coordinator.dispatch("A1", 1, Driver(Receiver()))
        coordinator.recover("A1")
    before = inspect(core, "works")[0]
    result = control(owner, action)
    work = inspect(core, "works")[0]
    assert result["status"] == ("paused" if action == "pause" else "cancelled")
    assert work["generation"] == before["generation"] + 1
    assert work["reserved"] == before["reserved"]
    assert not any(
        i["kind"] in {"prepare", "dispatch", "observe"} for i in inspect(core, "intents")
    )
    if stage in {"claimed", "blocked", "waiting"}:
        late = executor.call(
            "observe_attempt",
            {"attempt_id": "A1", "event_id": "late", "kind": "terminal", "raw_base64": "e30="},
            "late",
        )
        assert late["late"] is True
        assert inspect(core, "works")[0] == work
    if action == "cancel":
        with pytest.raises(CoreError, match="stale_basis"):
            control(owner, "resume")
    proof(tmp_path, core, action + "-" + stage)


@pytest.mark.parametrize("known", ["not_received", "running", "terminal"])
def test_unknown_proven_continuation_without_resend(tmp_path: Path, known: str) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    executor.call(
        "claim_dispatch", {"attempt_id": "A1", "generation": 1}, "claim", action_id="A1:action"
    )
    receiver = Receiver()
    raw = receiver({}, "A1:action") if known != "not_received" else b""
    executor.call(
        "observe_attempt", {"attempt_id": "A1", "event_id": "lost", "kind": "unknown"}, "lost"
    )
    with pytest.raises(CoreError, match="outcome_unknown"):
        control(owner, "resume")
    reconcile(executor, known)
    control(owner, "resume")
    if known == "not_received":
        fresh = Coordinator(Core(core.root).connect(executor.token)).prepare("work", "A2", PROFILE)
        coordinator.dispatch("A2", fresh["generation"], Driver(receiver))
        assert receiver.actions == ["A2:action"]
        assert inspect(core, "works")[0]["reserved"] == 3
    else:
        assert [i["subject"] for i in inspect(core, "intents") if i["kind"] == "observe"] == ["A1"]
        with pytest.raises(CoreError, match="outcome_unknown"):
            coordinator.dispatch("A1", 1, Driver(receiver))
        executor.call(
            "observe_attempt",
            {
                "attempt_id": "A1",
                "event_id": "terminal",
                "kind": "terminal",
                "raw_base64": base64.b64encode(raw).decode(),
            },
            "retain",
        )
        assert reopen_recover(core, executor.token, "A1")["state"] == "waiting"
        assert receiver.actions == ["A1:action"]
    assert inspect(core, "acceptance") == []
    proof(tmp_path, core, "unknown-" + known, receiver)


def test_resume_current_basis_and_explicit_correction(tmp_path: Path) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    control(owner, "pause")
    owner.call(
        "apply_changes",
        {"changes": [{"id": "memory", "kind": "memory", "key": "preference", "body": "corrected"}]},
        "correction",
        expected_heads={"memory": 1},
    )
    before = inspect(core, "works")
    with pytest.raises(CoreError, match="stale_basis"):
        control(owner, "resume")
    assert inspect(core, "works") == before
    coordinator.refresh_basis("work")
    fresh = coordinator.prepare("work", "A2", PROFILE)
    assert fresh["pinned"]["inputs"][0]["revision"] == 2
    assert fresh["generation"] == 3
    assert inspect(core, "conversations")[0]["cursor"] == 0
    proof(tmp_path, core, "explicit-current-correction")


def test_resume_preserves_exhausted_reserve(tmp_path: Path) -> None:
    core, owner, executor, _ = prepared(tmp_path)
    executor.call(
        "claim_dispatch",
        {"attempt_id": "A1", "generation": 1, "resource_upper": 4},
        "claim",
        action_id="A1:action",
    )
    control(owner, "pause")
    reconcile(executor, "not_received")
    with pytest.raises(CoreError, match="resource_exhausted"):
        control(owner, "resume")
    with pytest.raises(CoreError, match="resource_exhausted"):
        control(owner, "refresh")
    assert inspect(core, "works")[0]["status"] == "paused"
    assert inspect(core, "works")[0]["reserved"] == 4
    proof(tmp_path, core, "exhausted-resume")


def test_resume_rechecks_authority(tmp_path: Path) -> None:
    core, owner, executor, _ = prepared(tmp_path)
    control(owner, "pause")
    core.revoke(owner.token, "executor")
    with pytest.raises(CoreError, match="denied"):
        executor.call(
            "control_work", {"work_id": "work", "revision": 3, "action": "resume"}, "revoked"
        )
    assert inspect(core, "works")[0]["status"] == "paused"
    proof(tmp_path, core, "revoked-resume")


def test_pause_unknown_requires_terminal_proof(tmp_path: Path) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    executor.call(
        "claim_dispatch", {"attempt_id": "A1", "generation": 1}, "claim", action_id="A1:action"
    )
    control(owner, "pause")
    with pytest.raises(CoreError, match="outcome_unknown"):
        control(owner, "resume")
    with pytest.raises(CoreError, match="outcome_unknown"):
        control(owner, "refresh")
    reconcile(executor, "running")
    with pytest.raises(CoreError, match="outcome_unknown"):
        control(owner, "resume")
    reconcile(executor, "terminal")
    control(owner, "resume")
    fresh = coordinator.prepare("work", "A2", PROFILE)
    assert fresh["generation"] == 2
    assert inspect(core, "attempts")[0]["status"] == "fenced"
    assert inspect(core, "works")[0]["reserved"] == 1
    assert len(inspect(core, "actions")) == 1
    proof(tmp_path, core, "paused-running-terminal-proof")


@pytest.mark.parametrize("state", ["waiting", "cancelled", "completed"])
def test_refresh_cannot_bypass_terminal_or_question(tmp_path: Path, state: str) -> None:
    core, owner, _, coordinator = prepared(tmp_path)
    if state == "cancelled":
        control(owner, "cancel")
    else:
        receiver = Receiver()
        if state == "completed":
            receiver.outputs = [{"state": "completed", "text": "bounded result"}]
        coordinator.dispatch("A1", 1, Driver(receiver))
        coordinator.recover("A1")
    before = {table: inspect(core, table) for table in ("works", "attempts", "waits", "intents")}
    with pytest.raises(CoreError, match="stale_basis"):
        coordinator.refresh_basis("work")
    assert before == {table: inspect(core, table) for table in before}
    proof(tmp_path, core, "refresh-denied-" + state)


def test_refresh_cannot_install_non_method(tmp_path: Path) -> None:
    core, owner, _, _ = prepared(tmp_path)
    control(owner, "pause")
    with pytest.raises(CoreError, match="invalid_request"):
        owner.call(
            "control_work",
            {
                "work_id": "work",
                "revision": 3,
                "action": "refresh",
                "method_ref": {"id": "memory", "revision": 1},
            },
            "wrong-method",
        )
    assert inspect(core, "works")[0]["status"] == "paused"
    proof(tmp_path, core, "refresh-method-kind")


def test_tool_receipt_survives_crash_before_terminal(tmp_path: Path) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    executor.call(
        "claim_dispatch", {"attempt_id": "A1", "generation": 1}, "claim", action_id="A1:action"
    )
    script = """
import json,os,sys
from pathlib import Path
from zaratustra_core import Core
p=json.load(sys.stdin)
c=Core(Path(p['root'])).connect(p['token'])
c.call('reserve_tool',{'attempt_id':'A1','generation':1,'native_id':'t',
    'command_id':'durable-tool'},'reserve')
c.call('apply_changes',{'changes':[{'id':'effect','kind':'data','key':'effect',
    'body':'retained exact effect'}],'tool':{'attempt_id':'A1','generation':1,'native_id':'t'}},
    'durable-tool',expected_heads={'effect':0})
os._exit(91)
"""
    crashed = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", script],
        input=json.dumps({"root": str(core.root), "token": executor.token}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    process_proof(core, crashed, "tool-committed-before-terminal")
    assert crashed.returncode == 91, crashed.stderr
    assert inspect(core, "observations") == []
    assert inspect(core, "tool_calls")[0]["receipt"] == "durable-tool"
    saved = (
        Core(core.root)
        .connect(executor.token)
        .call("lookup_receipt", {"command_id": "durable-tool"}, "lookup-saved")
    )
    assert saved["command_id"] == "durable-tool"
    executor.call(
        "observe_attempt", {"attempt_id": "A1", "event_id": "lost", "kind": "unknown"}, "lost"
    )
    reconcile(executor, "terminal")
    control(owner, "resume")
    raw = json.dumps({"state": "ready", "text": "continue from saved tool receipt"}).encode()
    executor.call(
        "observe_attempt",
        {
            "attempt_id": "A1",
            "event_id": "terminal",
            "kind": "terminal",
            "raw_base64": base64.b64encode(raw).decode(),
        },
        "retain",
    )
    assert reopen_recover(core, executor.token, "A1")["state"] == "ready"
    pinned = coordinator.prepare("work", "A2", PROFILE)["pinned"]
    assert pinned["tool_ledger"][0]["receipt"] == "durable-tool"
    assert len([r for r in inspect(core, "records") if r["id"] == "effect"]) == 1
    assert len(inspect(core, "actions")) == 1
    assert inspect(core, "acceptance") == []
    proof(tmp_path, core, "tool-receipt-crash-before-terminal")


@pytest.mark.parametrize("phase", ["claim_before_send", "claim_after_receiver"])
def test_crash_reopen_reconciliation_allows_safe_progress(tmp_path: Path, phase: str) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    crashed = child({"root": str(core.root), "token": executor.token, "phase": phase})
    process_proof(core, crashed, phase)
    assert crashed.returncode == 91, crashed.stderr
    effects = core.root / "receiver-effects.jsonl"
    count = len(effects.read_bytes().splitlines()) if effects.exists() else 0
    assert count == (1 if phase == "claim_after_receiver" else 0)
    executor.call(
        "observe_attempt", {"attempt_id": "A1", "event_id": "lost", "kind": "unknown"}, "lost"
    )
    receiver = Receiver()
    with pytest.raises(CoreError, match="stale_basis"):
        coordinator.dispatch("A1", 1, Driver(receiver))
    known = "terminal" if count else "not_received"
    reconcile(executor, known)
    control(owner, "resume")
    if count:
        raw = json.dumps({"state": "completed", "text": "receiver-confirmed result"}).encode()
        executor.call(
            "observe_attempt",
            {
                "attempt_id": "A1",
                "event_id": "terminal",
                "kind": "terminal",
                "raw_base64": base64.b64encode(raw).decode(),
            },
            "retained",
        )
        assert reopen_recover(core, executor.token, "A1")["state"] == "completed"
        assert len(effects.read_bytes().splitlines()) == 1
        assert receiver.actions == []
    else:
        fresh = coordinator.prepare("work", "A2", PROFILE)
        coordinator.dispatch("A2", fresh["generation"], Driver(receiver))
        assert reopen_recover(core, executor.token, "A2")["state"] == "waiting"
        assert receiver.actions == ["A2:action"]
    assert len(inspect(core, "results")) == 1
    assert inspect(core, "acceptance") == []
    proof(tmp_path, core, phase, receiver)


@pytest.mark.parametrize("adapter", ["driver", "pi"])
def test_pause_reopen_retained_question_and_correction(tmp_path: Path, adapter: str) -> None:
    import threading

    core, owner, executor, coordinator = prepared(tmp_path)
    control(owner, "pause")
    control(owner, "resume")
    fresh = coordinator.prepare("work", "A2", PROFILE)
    receiver = Receiver()
    provider = Provider(receiver)
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    try:
        port = provider.server_port
        engine = (
            Pi(pi_cli(), tmp_path / "pi", f"http://127.0.0.1:{port}/v1")
            if adapter == "pi"
            else Driver(receiver)
        )
        coordinator.dispatch("A2", fresh["generation"], engine)
        first = reopen_recover(core, executor.token, "A2", pi=adapter == "pi")
        assert reopen_recover(core, executor.token, "A2", pi=adapter == "pi") == first
        assert receiver.actions == ["A2:action"]
        assert first["state"] == "waiting"
        ingest(owner, "correction", "Corrected duration and topic")
        assert inspect(core, "works")[0]["status"] == "waiting"
        ingest(owner, "answer", "Exact current answer", {"id": "W7", "revision": 1})
        next_attempt = coordinator.prepare("work", "A3", PROFILE)
        ledger = next_attempt["pinned"]["tool_ledger"]
        assert len(ledger) == 1 and ledger[0]["receipt"] == "A2:tool:create-activity"
        assert [m["seq"] for m in next_attempt["pinned"]["messages"]] == [21, 22]
        coordinator.dispatch("A3", next_attempt["generation"], engine)
        assert (
            reopen_recover(core, executor.token, "A3", pi=adapter == "pi")["state"] == "completed"
        )
        assert receiver.actions == ["A2:action", "A3:action"]
        assert len(inspect(core, "results")) == 2
        assert len([r for r in inspect(core, "records") if r["id"] == "activity"]) == 1
        assert inspect(core, "works")[0]["reserved"] == 4
        assert inspect(core, "acceptance") == []
        proof(tmp_path, core, "pause-reopen-" + adapter, receiver)
    finally:
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=5)
