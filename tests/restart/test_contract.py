"""Behavioral invariants observed independently of production admission helpers."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app import Coordinator, Driver
from zaratustra_core import Core, CoreError, Request, wire

from .support import CORRECTION, PROFILE, Receiver, fixture, ingest, inspect


def prepared(root: Path) -> tuple[Any, Any, Any, Any]:
    core, owner, executor = fixture(root)
    coordinator = Coordinator(executor)
    coordinator.prepare("work", "A1", PROFILE)
    return core, owner, executor, coordinator


def outcome() -> dict[str, Any]:
    return {
        "attempt_id": "A1",
        "generation": 1,
        "terminal_event": "terminal",
        "original_cursor": 0,
        "processed_cutoff": 20,
        "state": "completed",
        "text": "retained",
    }


def test_wire_vectors() -> None:
    value = {"z": ["é", "é", "line" + chr(10), "decimal:1.00"], "a": 20}
    expected = '{"a":20,"z":["é","é","line' + chr(92) + 'n","decimal:1.00"]}'
    assert wire(value) == expected.encode()
    with pytest.raises(ValueError):
        wire({"bad": float("nan")})
    with pytest.raises(ValueError):
        wire({"bad": 1.2})
    with pytest.raises(ValueError):
        Request(
            instance_id="i",
            space_id="s",
            recovery_epoch=True,
            command_id="c",
            operation="x",
            payload={},
        )


def test_cas_identity_exact(tmp_path: Path) -> None:
    core, owner, executor = fixture(tmp_path)
    old = owner.call("read_exact", {"id": "memory", "revision": 1}, "read-old")
    change = {"id": "memory", "kind": "memory", "key": "preference", "body": "Changed preference"}
    owner.call("apply_changes", {"changes": [change]}, "write-win", expected_heads={"memory": 1})
    with pytest.raises(CoreError, match="stale_basis"):
        executor.call(
            "apply_changes",
            {"changes": [change | {"body": "stale loser"}]},
            "write-lose",
            expected_heads={"memory": 1},
        )
    historical = (
        Core(core.root)
        .connect(owner.token)
        .call("read_exact", {"id": "memory", "revision": 1}, "reopen-old")
    )
    assert historical == old
    assert json.loads(inspect(core, "records")[-1]["body"])["value"] == "Changed preference"
    with pytest.raises(CoreError, match="identity_conflict"):
        owner.call(
            "apply_changes",
            {"changes": [change | {"id": "duplicate"}]},
            "duplicate-key",
            expected_heads={"duplicate": 0},
        )
    assert len([h for h in inspect(core, "heads") if h["key"] == "preference"]) == 1


def test_ingest_idempotency_intent(tmp_path: Path) -> None:
    core, owner, _ = fixture(tmp_path)
    receipt = ingest(owner, "21", CORRECTION)
    assert ingest(owner, "21", CORRECTION) == receipt
    with pytest.raises(CoreError, match="idempotency_conflict"):
        ingest(owner, "21", "Changed command payload")
    assert len(inspect(core, "messages")) == 21
    assert any(
        i["kind"] == "input" and i["subject"] == "conversation" for i in inspect(core, "intents")
    )
    assert any(r["command"] == "input:21" for r in inspect(core, "receipts"))


def test_contiguous_and_current_input(tmp_path: Path) -> None:
    _, owner, executor = fixture(tmp_path)
    change = {"id": "memory", "kind": "memory", "key": "preference", "body": "new current"}
    owner.call("apply_changes", {"changes": [change]}, "new-memory", expected_heads={"memory": 1})
    with pytest.raises(CoreError, match="stale_basis"):
        Coordinator(executor).prepare("work", "A1", PROFILE)


def test_claim_rechecks_late_input(tmp_path: Path) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    ingest(owner, "21", CORRECTION)
    with pytest.raises(CoreError, match="stale_basis"):
        coordinator.dispatch("A1", 1, Driver(Receiver()))
    assert inspect(core, "actions") == []


def test_no_blind_resend_after_claim(tmp_path: Path) -> None:
    core, _, executor, coordinator = prepared(tmp_path)
    executor.call(
        "claim_dispatch",
        {"attempt_id": "A1", "generation": 1, "resource_upper": 2},
        "A1:claim",
        action_id="A1:action",
    )
    receiver = Receiver()
    receiver({"accepted_before_observer_crash": True}, "A1:action")
    code = None
    try:
        Coordinator(Core(core.root).connect(executor.token)).dispatch("A1", 1, Driver(receiver))
    except CoreError as error:
        code = error.code
    assert receiver.actions == ["A1:action"], "unsafe replay produced duplicate receiver effects"
    assert code == "outcome_unknown"
    assert inspect(core, "works")[0]["reserved"] == 2


def test_reconcile_blocked_without_resend(tmp_path: Path) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    executor.call(
        "claim_dispatch", {"attempt_id": "A1", "generation": 1}, "claim", action_id="A1:action"
    )
    receiver = Receiver()
    # Receiver accepted, process vanished before observing it.
    raw = receiver({"external": "accepted"}, "A1:action")
    executor.call(
        "observe_attempt", {"attempt_id": "A1", "event_id": "unknown", "kind": "unknown"}, "unknown"
    )
    with pytest.raises(CoreError, match="outcome_unknown"):
        owner.call(
            "control_work", {"work_id": "work", "revision": 2, "action": "resume"}, "unsafe-resume"
        )
    executor.call(
        "observe_attempt",
        {
            "attempt_id": "A1",
            "event_id": "reconcile",
            "kind": "reconcile",
            "evidence": {
                "action_id": "A1:action",
                "state": "terminal",
                "receiver_ref": "receiver-log/v1#1",
            },
        },
        "reconcile",
    )
    owner.call("control_work", {"work_id": "work", "revision": 2, "action": "resume"}, "resume")
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
    result = Coordinator(Core(core.root).connect(executor.token)).recover("A1")
    assert result["state"] == "waiting"
    assert receiver.actions == ["A1:action"]
    assert inspect(core, "works")[0]["reserved"] == 1


def test_revocation_and_foreign_receipt(tmp_path: Path) -> None:
    core, owner, executor = fixture(tmp_path)
    with pytest.raises(CoreError, match="denied"):
        executor.call("lookup_receipt", {"command_id": "seed"}, "foreign")
    core.revoke(owner.token, "executor")
    with pytest.raises(CoreError, match="denied"):
        executor.call("read_exact", {"id": "memory", "revision": 1}, "revoked-read")
    with pytest.raises(CoreError, match="denied"):
        executor.call("open_work", {"id": "forged"}, "revoked-write")
    assert len(inspect(core, "works")) == 1


@pytest.mark.parametrize("path", ["apply_changes", "commit_outcome"])
def test_forbidden_delta_atomic(tmp_path: Path, path: str) -> None:
    core, _, executor, coordinator = prepared(tmp_path)
    coordinator.dispatch("A1", 1, Driver(Receiver()))
    changes = [
        {"id": "good", "kind": "data", "key": "good", "body": "allowed"},
        {"id": "bad", "kind": "grant", "key": "owner", "body": "*"},
    ]
    payload = {"changes": changes} if path == "apply_changes" else outcome() | {"changes": changes}
    with pytest.raises(CoreError, match="denied"):
        executor.call(path, payload, "forbidden:" + path, expected_heads={"good": 0, "bad": 0})
    assert not any(h["id"] == "good" for h in inspect(core, "heads"))
    assert inspect(core, "results") == []
    assert inspect(core, "conversations")[0]["cursor"] == 0


def test_late_fencing(tmp_path: Path) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    coordinator.dispatch("A1", 1, Driver(Receiver()))
    owner.call("control_work", {"work_id": "work", "revision": 2, "action": "pause"}, "pause")
    late = executor.call(
        "observe_attempt",
        {"attempt_id": "A1", "event_id": "late", "kind": "terminal", "raw_base64": "e30="},
        "late",
    )
    assert late["late"] is True
    with pytest.raises(CoreError, match="stale_basis"):
        executor.call("commit_outcome", outcome(), "late-outcome")
    assert inspect(core, "results") == []
    assert inspect(core, "works")[0]["status"] == "paused"


def test_exact_question_no_acceptance(tmp_path: Path) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    coordinator.dispatch("A1", 1, Driver(Receiver()))
    coordinator.recover("A1")
    with pytest.raises(CoreError, match="stale_basis"):
        ingest(owner, "wrong", "Answer", {"id": "W7", "revision": 2})
    ingest(owner, "free", "Unaddressed answer")
    assert inspect(core, "waits")[0]["status"] == "waiting"
    with pytest.raises(CoreError, match="denied"):
        core.accept_result(executor.token, "A1", inspect(core, "results")[0]["fingerprint"])
    assert inspect(core, "acceptance") == []


def test_retained_terminal_bytes(tmp_path: Path) -> None:
    core, _, _, coordinator = prepared(tmp_path)
    receiver = Receiver()
    raw = coordinator.dispatch("A1", 1, Driver(receiver))
    terminal = json.loads(inspect(core, "observations")[0]["body"])
    assert base64.b64decode(terminal["raw_base64"]) == raw
    coordinator.recover("A1")
    coordinator.recover("A1")
    assert receiver.actions == ["A1:action"]
    assert len(inspect(core, "results")) == 1


def test_tool_before_terminal_recovery(tmp_path: Path) -> None:
    core, _, executor, coordinator = prepared(tmp_path)
    executor.call(
        "claim_dispatch", {"attempt_id": "A1", "generation": 1}, "claim", action_id="A1:action"
    )
    executor.call(
        "reserve_tool",
        {"attempt_id": "A1", "generation": 1, "native_id": "tool1", "command_id": "tool1:command"},
        "tool1:reserve",
    )
    change = {"id": "tool-record", "kind": "data", "key": "effect", "body": "exact saved bytes"}
    request = executor.request(
        "apply_changes",
        {"changes": [change], "tool": {"attempt_id": "A1", "generation": 1, "native_id": "tool1"}},
        "tool1:command",
        expected_heads={"tool-record": 0},
    )
    receipt = executor.send(request)
    assert Core(core.root).connect(executor.token).send(request) == receipt
    assert len([r for r in inspect(core, "records") if r["id"] == "tool-record"]) == 1
    assert inspect(core, "tool_calls")[0]["receipt"] == "tool1:command"


def test_cursor_gap_and_conflicting_final(tmp_path: Path) -> None:
    core, _, executor, coordinator = prepared(tmp_path)
    coordinator.dispatch("A1", 1, Driver(Receiver()))
    with pytest.raises(CoreError, match="stale_basis"):
        executor.call("commit_outcome", outcome() | {"processed_cutoff": 19}, "skip-cutoff")
    assert inspect(core, "conversations")[0]["cursor"] == 0
    executor.call("commit_outcome", outcome(), "correct-final")
    with pytest.raises(CoreError, match="idempotency_conflict"):
        executor.call("commit_outcome", outcome() | {"text": "other"}, "duplicate-final")
    assert len(inspect(core, "results")) == 1


@pytest.mark.parametrize("field", ["key", "scope", "id"])
@pytest.mark.parametrize("value", [None, "", True, 1])
def test_declared_identity_strict(tmp_path: Path, field: str, value: Any) -> None:
    core, owner, _ = fixture(tmp_path)
    change = {"id": "valid", "kind": "data", "key": "valid", "body": "value"}
    with pytest.raises(CoreError, match="invalid_request"):
        owner.call(
            "apply_changes",
            {"changes": [change, change | {"id": "invalid", field: value}]},
            "invalid-identity",
            expected_heads={"valid": 0, "invalid": 0},
        )
    assert not any(h["id"] == "valid" for h in inspect(core, "heads"))


def test_prepared_refresh_without_repair(tmp_path: Path) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    ingest(owner, "21", CORRECTION)
    with pytest.raises(CoreError, match="stale_basis"):
        coordinator.dispatch("A1", 1, Driver(Receiver()))
    assert inspect(core, "works")[0]["status"] == "ready"
    fresh = Coordinator(executor).prepare("work", "A2", PROFILE)
    assert fresh["generation"] == 2
    assert fresh["pinned"]["messages"][-1]["seq"] == 21
    assert inspect(core, "actions") == []


def test_stale_method_on_claim(tmp_path: Path) -> None:
    core, owner, executor = fixture(tmp_path)
    owner.call(
        "open_work",
        {
            "id": "method-work",
            "conversation": "other",
            "goal": "pinned method",
            "method_ref": {"id": "method", "revision": 1, "role": "must_be_current"},
            "inputs": [],
            "call_limit": 2,
            "continuation_policy": "durable",
        },
        "method-work:create",
    )
    Coordinator(executor).prepare("method-work", "A1", PROFILE)
    owner.call(
        "apply_changes",
        {"changes": [{"id": "method", "kind": "method", "key": "conversation", "body": "updated"}]},
        "method-update",
        expected_heads={"method": 1},
    )
    with pytest.raises(CoreError, match="stale_basis"):
        Coordinator(executor).dispatch("A1", 1, Driver(Receiver()))
    assert inspect(core, "actions") == []


def test_stale_current_on_outcome_retains_terminal(tmp_path: Path) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    raw = coordinator.dispatch("A1", 1, Driver(Receiver()))
    owner.call(
        "apply_changes",
        {
            "changes": [
                {"id": "memory", "kind": "memory", "key": "preference", "body": "new preference"}
            ]
        },
        "memory-update",
        expected_heads={"memory": 1},
    )
    with pytest.raises(CoreError, match="stale_basis"):
        coordinator.recover("A1")
    assert inspect(core, "results") == []
    assert inspect(core, "conversations")[0]["cursor"] == 0
    assert (
        base64.b64decode(json.loads(inspect(core, "observations")[0]["body"])["raw_base64"]) == raw
    )


@pytest.mark.parametrize("kind", ["unknown", "progress", "terminal"])
def test_late_callback_cannot_resurrect(tmp_path: Path, kind: str) -> None:
    core, _, executor, coordinator = prepared(tmp_path)
    coordinator.dispatch("A1", 1, Driver(Receiver()))
    executor.call("commit_outcome", outcome(), "finish")
    before = {
        table: inspect(core, table)
        for table in ("works", "attempts", "results", "conversations", "intents")
    }
    result = executor.call(
        "observe_attempt",
        {"attempt_id": "A1", "event_id": "late-" + kind, "kind": kind, "raw_base64": "e30="},
        "late-" + kind,
    )
    assert result["late"] is True
    assert before == {table: inspect(core, table) for table in before}


def test_missing_m19_cannot_prepare_cutoff20(tmp_path: Path) -> None:
    core, owner, executor = fixture(tmp_path)
    snapshot = Coordinator(owner).snapshot()
    messages = [m for m in snapshot["messages"] if m["seq"] != 19]
    payload = {
        "id": "A1",
        "work_id": "work",
        "work_revision": 1,
        "original_cursor": 0,
        "cutoff": 20,
        "profile_ref": PROFILE,
        "message_sequences": [m["seq"] for m in messages],
        "manifest": [
            {
                "sequence": m["seq"],
                "sha256": __import__("hashlib").sha256(base64.b64decode(m["raw"])).hexdigest(),
            }
            for m in messages
        ],
    }
    with pytest.raises(CoreError, match="stale_basis"):
        executor.call("prepare_attempt", payload, "gap")
    assert inspect(core, "attempts") == []
    assert inspect(core, "works")[0]["status"] == "ready"


def test_old_generation_cannot_publish_current(tmp_path: Path) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    coordinator.dispatch("A1", 1, Driver(Receiver()))
    owner.call("control_work", {"work_id": "work", "revision": 2, "action": "pause"}, "pause")
    with pytest.raises(CoreError, match="stale_basis"):
        executor.call("commit_outcome", outcome(), "old-generation-final")
    assert inspect(core, "results") == []
    assert inspect(core, "conversations")[0]["cursor"] == 0
    assert inspect(core, "works")[0]["status"] == "paused"


def test_stale_basis_can_form_new_explicit_intent(tmp_path: Path) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    coordinator.dispatch("A1", 1, Driver(Receiver()))
    owner.call(
        "apply_changes",
        {
            "changes": [
                {
                    "id": "memory",
                    "kind": "memory",
                    "key": "preference",
                    "body": "new bounded preference",
                }
            ]
        },
        "new-memory",
        expected_heads={"memory": 1},
    )
    with pytest.raises(CoreError, match="stale_basis"):
        coordinator.recover("A1")
    coordinator.refresh_basis("work")
    next_attempt = coordinator.prepare("work", "A2", PROFILE)
    assert next_attempt["generation"] == 2
    assert next_attempt["pinned"]["inputs"][0]["revision"] == 2
    assert next_attempt["pinned"]["messages"][-1]["seq"] == 20
    assert inspect(core, "attempts")[0]["status"] == "superseded"
    assert inspect(core, "observations") != []
    assert inspect(core, "results") == []


def test_atomic_activity_initial_work(tmp_path: Path) -> None:
    core, owner, _ = fixture(tmp_path)
    change = {"id": "activity", "kind": "activity", "key": "practice", "body": "Practice"}
    work = {
        "id": "practice",
        "conversation": "practice",
        "goal": "begin",
        "method_ref": {"id": "method", "revision": 1},
        "inputs": [],
        "call_limit": 1,
        "continuation_policy": "durable",
    }
    with pytest.raises(CoreError, match="invalid_request"):
        owner.call(
            "apply_changes",
            {
                "changes": [change],
                "initial_work": work | {"method_ref": {"id": "missing", "revision": 1}},
            },
            "atomic-fail",
            expected_heads={"activity": 0},
        )
    assert not any(h["id"] == "activity" for h in inspect(core, "heads"))
    owner.call(
        "apply_changes",
        {"changes": [change], "initial_work": work},
        "atomic-success",
        expected_heads={"activity": 0},
    )
    assert any(h["id"] == "activity" for h in inspect(core, "heads"))
    assert any(w["id"] == "practice" for w in inspect(core, "works"))
    assert any(
        i["subject"] == "practice" and i["kind"] == "prepare" for i in inspect(core, "intents")
    )


def test_resume_does_not_unfence_old_attempt(tmp_path: Path) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    coordinator.dispatch("A1", 1, Driver(Receiver()))
    owner.call("control_work", {"work_id": "work", "revision": 2, "action": "pause"}, "pause")
    owner.call("control_work", {"work_id": "work", "revision": 3, "action": "resume"}, "resume")
    assert inspect(core, "works")[0]["status"] == "ready"
    assert inspect(core, "attempts")[0]["status"] == "fenced"
    with pytest.raises(CoreError, match="stale_basis"):
        executor.call("commit_outcome", outcome(), "fenced-after-resume")
    assert inspect(core, "results") == []
    prepared2 = coordinator.prepare("work", "A2", PROFILE)
    assert prepared2["generation"] == 2


def test_epoch_and_single_active_slots(tmp_path: Path) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    request = executor.request(
        "claim_dispatch",
        {"attempt_id": "A1", "generation": 1},
        "wrong-epoch",
        action_id="A1:action",
    )
    with pytest.raises(CoreError, match="stale_epoch"):
        executor.send(request.model_copy(update={"recovery_epoch": request.recovery_epoch + 1}))
    assert inspect(core, "actions") == []
    owner.call(
        "open_work",
        {
            "id": "parallel",
            "conversation": "conversation",
            "goal": "another turn",
            "method_ref": {"id": "method", "revision": 1},
            "inputs": [],
            "call_limit": 2,
            "continuation_policy": "durable",
        },
        "parallel:create",
    )
    with pytest.raises(CoreError, match="identity_conflict"):
        coordinator.prepare("parallel", "A2", PROFILE)
    assert len(inspect(core, "attempts")) == 1


def test_confirmation_is_explicitly_unsupported(tmp_path: Path) -> None:
    core, owner, _ = fixture(tmp_path)
    request = owner.request(
        "apply_changes",
        {"changes": [{"id": "unconfirmed", "kind": "data", "key": "unconfirmed", "body": "value"}]},
        "unconfirmed",
        expected_heads={"unconfirmed": 0},
    )
    with pytest.raises(CoreError, match="unsupported_capability"):
        owner.send(request.model_copy(update={"confirmation_ref": "invented-confirmation"}))
    assert not any(h["id"] == "unconfirmed" for h in inspect(core, "heads"))
