"""G12/G13 mechanical guarantees. Text meaning requires separately authorized live evaluation."""

from __future__ import annotations

import base64
import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import zaratustra_app
import zaratustra_core
from zaratustra_app import Coordinator, Driver, Sleep
from zaratustra_core import Core, CoreError

from .sleep_support import PROFILE, MechanicalSleepReceiver, adaptation_trace, save, seed
from .support import inspect


def crash_sleep(core: Any, client: Any, phase: str) -> subprocess.CompletedProcess[str]:
    sources = [
        str(Path(zaratustra_core.__file__).parents[1]),
        str(Path(zaratustra_app.__file__).parents[1]),
        str(Path(__file__).resolve().parents[2]),
    ]
    script = (
        "import sys;sys.path[:0]="
        + repr(sources)
        + ";from tests.restart.sleep_crash_worker import main;main()"
    )
    return subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", script],
        input=json.dumps({"root": str(core.root), "token": client.token, "phase": phase}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


@pytest.mark.parametrize("phase", ["method", "work", "progress", "bound"])
def test_sleep_start_recovers_each_commit_window(tmp_path: Path, phase: str) -> None:
    core, _, client = seed(tmp_path)
    killed = crash_sleep(core, client, phase)
    assert killed.returncode == 91, killed.stderr
    sleep = Sleep(Core(core.root).connect(client.token))
    first = sleep.start(work_id="s", call_limit=4)
    assert sleep.start(work_id="s", call_limit=4) == first
    assert len(inspect(core, "works")) == 1
    assert len([h for h in inspect(core, "heads") if h["key"] == "sleep-progress:s"]) == 1
    assert len([h for h in inspect(core, "heads") if h["key"] == "sleep"]) == 1
    assert json.loads(inspect(core, "works")[0]["body"])["inputs"] == [
        first["progress_ref"] | {"role": "must_be_current"}
    ]


def test_sleep_run_recovers_retained_terminal_without_inference(tmp_path: Path) -> None:
    core, _, client = seed(tmp_path)
    Sleep(client).start(work_id="s", call_limit=4)
    killed = crash_sleep(core, client, "terminal")
    assert killed.returncode == 91, killed.stderr
    assert inspect(core, "results") == []
    receiver = MechanicalSleepReceiver()
    sleep = Sleep(Core(core.root).connect(client.token))
    try:
        result = sleep.run("s", PROFILE, Driver(receiver))
    except CoreError as error:
        raise AssertionError(
            "retained terminal must recover without inference: " + error.code
        ) from error
    assert receiver.actions == []
    assert result["state"] == "completed"
    assert sleep.run("s", PROFILE, Driver(receiver)) == result
    assert receiver.actions == [] and len(inspect(core, "results")) == 1
    assert inspect(core, "works")[0]["reserved"] == 2


@pytest.mark.parametrize("mode", ["driver", "pi"])
def test_sleep_adaptation_trace(tmp_path: Path, mode: str) -> None:
    result = adaptation_trace(tmp_path, mode)
    assert len(result["received"]) == 2


def progress_change(sleep: Sleep, work_id: str) -> tuple[dict[str, Any], int]:
    record = sleep.progress(work_id)
    return {
        "id": record["id"],
        "kind": record["kind"],
        "key": record["key"],
        "scope": record["scope"],
        "body": copy.deepcopy(record["body"]["value"]),
    }, record["revision"]


def test_history_cutoff_enumeration_not_analysis(tmp_path: Path) -> None:
    _, owner, client = seed(tmp_path)
    sleep = Sleep(client)
    sleep.start(work_id="s", call_limit=4, portion=2)
    record = sleep.progress("s")
    body = record["body"]["value"]
    high = body["source_high_watermark"]
    assert len(body["enumerated_source_refs"]) == 2
    assert not body["analysis_result_refs"] and not body["delivered_manifest_refs"]
    save(
        owner, {"id": "late", "kind": "data", "key": "late", "body": "Late arrival about old event"}
    )
    sleep.continue_portion("s", portion=100)
    continued = sleep.progress("s")["body"]["value"]
    assert continued["source_high_watermark"] == high
    assert len(continued["enumerated_source_refs"]) == 7
    assert continued["enumeration_cursor"][0] == high
    assert continued["analysis_result_refs"] == continued["delivered_manifest_refs"] == []
    assert continued["unexplored_coverage_position"] == body["unexplored_coverage_position"]
    newer = client.call("read_history", {}, uuid4().hex)
    assert any(s["material"].get("record", {}).get("id") == "late" for s in newer["sources"])


@pytest.mark.parametrize(
    "defect", ["selection", "remainder", "resource", "scope", "receipt", "deselected"]
)
def test_progress_rejects_false_claims(tmp_path: Path, defect: str) -> None:
    core, owner, client = seed(tmp_path)
    sleep = Sleep(client)
    sleep.start(work_id="s", call_limit=4)
    change, revision = progress_change(sleep, "s")
    body = change["body"]
    if defect == "selection":
        body["selected_source_refs"] = [{"sequence": 999999, "index": 0, "sha256": "0" * 64}]
    elif defect == "remainder":
        body["remaining_refs"] = []
    elif defect == "deselected":
        body["selected_source_refs"] = body["remaining_refs"] = []
    elif defect == "resource":
        body["consumed_resource"] = 999
    elif defect == "scope":
        change["scope"] = body["scope"] = "other"
    elif defect == "receipt":
        body["applied_receipts"] = ["unrelated-read"]
        owner.call("read_snapshot", {}, "unrelated-read")
    before = inspect(core, "records")
    with pytest.raises(CoreError):
        save(owner, change, revision)
    assert inspect(core, "records") == before


@pytest.mark.parametrize("phase", ["prepared", "unknown"])
def test_prepared_unknown_is_not_delivered(tmp_path: Path, phase: str) -> None:
    _, owner, client = seed(tmp_path)
    sleep = Sleep(client)
    sleep.start(work_id="s", call_limit=4)
    prepared = Coordinator(client).prepare("s", "a", PROFILE)
    if phase == "unknown":
        client.call(
            "claim_dispatch",
            {"attempt_id": "a", "generation": prepared["generation"]},
            "claim",
            action_id="a:action",
        )
        client.call(
            "observe_attempt",
            {"attempt_id": "a", "event_id": "unknown", "kind": "unknown"},
            "unknown",
        )
    change, revision = progress_change(sleep, "s")
    change["body"]["delivered_manifest_refs"] = [prepared["pinned"]["sleep_delivery_manifest"]]
    if phase == "unknown":
        change["body"]["consumed_resource"] = 1
        change["body"]["unresolved_calls"] = ["a:action"]
    with pytest.raises(CoreError, match="unobserved_delivery"):
        save(owner, change, revision)


def test_unknown_reservation_survives_reopen(tmp_path: Path) -> None:
    core, _, client = seed(tmp_path)
    sleep = Sleep(client)
    sleep.start(work_id="s", call_limit=2)
    coordinator = Coordinator(client)
    prepared = coordinator.prepare("s", "a", PROFILE)

    def lost(context: Any, action: str) -> bytes:
        raise OSError("receiver accepted; response/usage lost")

    with pytest.raises(OSError):
        coordinator.dispatch("a", prepared["generation"], Driver(lost))
    reopened = Core(core.root).connect(client.token)
    change, revision = progress_change(Sleep(reopened), "s")
    change["body"]["consumed_resource"] = 2
    change["body"]["unresolved_calls"] = ["a:action"]
    change["body"]["stop_reason"] = "unknown_usage_and_outcome"
    save(reopened, change, revision)
    row = inspect(core, "works")[0]
    assert row["reserved"] == 2 and row["status"] == "blocked"
    with pytest.raises(CoreError, match="outcome_unknown"):
        Sleep(reopened).run("s", PROFILE, Driver(MechanicalSleepReceiver()))
    assert inspect(core, "works")[0]["reserved"] == 2
    reopened.call(
        "observe_attempt",
        {
            "attempt_id": "a",
            "event_id": "not-received",
            "kind": "reconcile",
            "evidence": {
                "action_id": "a:action",
                "state": "not_received",
                "receiver_ref": "synthetic-receiver-check",
            },
        },
        uuid4().hex,
    )
    with pytest.raises(CoreError, match="resource_exhausted"):
        reopened.call(
            "control_work",
            {"work_id": "s", "revision": row["revision"], "action": "refresh"},
            uuid4().hex,
        )
    assert inspect(core, "works")[0]["reserved"] == 2


@pytest.mark.parametrize(
    "kind,scope", [("memory", "space"), ("method", "other"), ("grant", "space")]
)
def test_delegated_scope_does_not_expand(tmp_path: Path, kind: str, scope: str) -> None:
    core, owner, _ = seed(tmp_path)
    token = core.grant(owner.token, "limited", ["read", "apply_changes", "write:method:space"])
    limited = core.connect(token)
    before = inspect(core, "records")
    with pytest.raises(CoreError, match="denied"):
        limited.call(
            "apply_changes",
            {
                "changes": [
                    {"id": "harmless", "kind": "data", "key": "harmless", "body": "atomic"},
                    {
                        "id": "forbidden",
                        "kind": kind,
                        "key": "forbidden",
                        "scope": scope,
                        "body": "new power",
                    },
                ]
            },
            uuid4().hex,
            expected_heads={"harmless": 0, "forbidden": 0},
        )
    assert inspect(core, "records") == before


def test_text_memory_remains_free(tmp_path: Path) -> None:
    _, owner, _ = seed(tmp_path)
    arbitrary = "Not a grammar: observations? maybe. Alternative and counterexample are prose."
    ref = save(owner, {"id": "free", "kind": "memory", "key": "free", "body": arbitrary})
    assert owner.call("read_exact", ref, uuid4().hex)["body"]["value"] == arbitrary


def test_method_delivery_refuses_stale_current(tmp_path: Path) -> None:
    core, owner, client = seed(tmp_path)
    sleep = Sleep(client)
    sleep.open_work(
        {
            "id": "next",
            "conversation": "next",
            "goal": "ordinary",
            "method_ref": {"id": "practice", "revision": 1},
            "call_limit": 2,
            "continuation_policy": "durable",
        }
    )
    save(owner, {"id": "practice", "kind": "method", "key": "practice", "body": "v2"}, 1)
    with pytest.raises(CoreError, match="stale_basis"):
        Coordinator(client).prepare("next", "a", PROFILE)
    assert inspect(core, "attempts") == []


def test_next_call_beyond_remaining_is_rejected(tmp_path: Path) -> None:
    core, _, client = seed(tmp_path)
    sleep = Sleep(client)
    sleep.start(work_id="s", call_limit=3)
    sleep.run("s", PROFILE, Driver(MechanicalSleepReceiver(state="ready")))
    assert inspect(core, "works")[0]["reserved"] == 2
    receiver = MechanicalSleepReceiver()
    with pytest.raises(CoreError, match="resource_exhausted"):
        sleep.run("s", PROFILE, Driver(receiver))
    assert receiver.actions == []
    assert inspect(core, "works")[0]["reserved"] == 2
    assert inspect(core, "works")[0]["status"] == "paused"
    assert sleep.progress("s")["body"]["value"]["stop_reason"] == "resource_exhausted"


def test_proposal_is_not_an_applied_memory_or_method(tmp_path: Path) -> None:
    _, owner, client = seed(tmp_path)
    save(
        owner,
        {
            "id": "proposed",
            "kind": "memory",
            "key": "proposal",
            "body": "Free proposal",
            "application": "proposal",
        },
    )
    save(
        owner,
        {
            "id": "proposed-method",
            "kind": "method",
            "key": "proposal",
            "body": "Free proposal",
            "application": "proposal",
        },
    )
    sleep = Sleep(client)
    sleep.open_work(
        {
            "id": "next",
            "conversation": "next",
            "goal": "ordinary",
            "method_ref": {"id": "practice", "revision": 1},
            "call_limit": 2,
            "continuation_policy": "durable",
        }
    )
    pinned = Coordinator(client).prepare("next", "a", PROFILE)["pinned"]
    assert "proposed" not in {r["id"] for r in pinned["inputs"]}
    with pytest.raises(CoreError, match="inactive_method"):
        client.call(
            "open_work",
            {
                "id": "bad",
                "conversation": "bad",
                "goal": "ordinary",
                "method_ref": {"id": "proposed-method", "revision": 1},
                "call_limit": 2,
                "continuation_policy": "durable",
            },
            "bad:open",
        )


def test_sleep_history_includes_raw_input_and_unknown_attempt(tmp_path: Path) -> None:
    _, owner, client = seed(tmp_path)
    original = "Only in raw input: trial has three unverified buds.\nKeep uncertainty."
    owner.call(
        "ingest_message",
        {
            "conversation": "lab",
            "event_id": "fact",
            "scope": "lab",
            "raw_base64": base64.b64encode(original.encode()).decode(),
        },
        "raw-fact",
    )
    Coordinator(client).open_work(
        {
            "id": "lab-work",
            "conversation": "lab",
            "goal": "Examine trial",
            "method_ref": {"id": "practice", "revision": 1},
            "call_limit": 2,
            "continuation_policy": "durable",
        },
        scope="lab",
    )
    coordinator = Coordinator(client)
    prepared = coordinator.prepare("lab-work", "unknown-attempt", PROFILE)

    def lost(context: Any, action: str) -> bytes:
        raise OSError("No terminal or usage received")

    with pytest.raises(OSError):
        coordinator.dispatch("unknown-attempt", prepared["generation"], Driver(lost))
    sleep = Sleep(owner)
    sleep.start(work_id="lab-sleep", scope="lab", method_id="lab-sleep-method", call_limit=2)
    sleep_prepared = Coordinator(owner).prepare("lab-sleep", "sleep-attempt", PROFILE)
    materials = [s["material"] for s in sleep_prepared["pinned"]["sleep_sources"]]
    assert all(m["scope"] == "lab" for m in materials)
    direct = next(m["message"] for m in materials if "message" in m)
    assert base64.b64decode(direct["raw"]).decode() == original
    observed = next(m for m in materials if m.get("observation", {}).get("kind") == "unknown")
    assert observed["observation"]["attempt_id"] == "unknown-attempt"
    assert base64.b64decode(observed["messages"][0]["raw"]).decode() == original
    assert observed["resource_reservation"] == 2
    assert observed["method"]["id"] == "practice"


def test_invalid_known_terminal_is_retained_without_regeneration(tmp_path: Path) -> None:
    core, _, client = seed(tmp_path)
    sleep = Sleep(client)
    sleep.start(work_id="s", call_limit=3)

    class InvalidExecutor:
        resource_upper = 1
        tool_handler: Any = None
        sends = 0

        def run(self, context: Any, action: str) -> bytes:
            self.sends += 1
            return b"known exact terminal with invalid JSON"

    executor = InvalidExecutor()
    for _ in range(2):
        with pytest.raises(CoreError, match="retained_outcome_format"):
            sleep.run("s", PROFILE, executor)
    assert executor.sends == 1
    assert inspect(core, "actions")[0]["state"] == "terminal"
    observation = json.loads(inspect(core, "observations")[0]["body"])
    assert base64.b64decode(observation["raw_base64"]) == b"known exact terminal with invalid JSON"
    assert inspect(core, "works")[0]["reserved"] == 1
    # Explicit new basis is a NEW Attempt, retaining the invalid response and its reservation.
    sleep.coordinator.refresh_basis("s")
    result = sleep.run("s", PROFILE, Driver(MechanicalSleepReceiver()))
    assert result["state"] == "completed"
    assert len(inspect(core, "attempts")) == 2 and inspect(core, "works")[0]["reserved"] == 3


@pytest.mark.parametrize("transition", ["open", "refresh"])
@pytest.mark.parametrize("restriction", ["scope", "proposal", "withdrawn", "tombstone"])
def test_core_method_application_guards(tmp_path: Path, transition: str, restriction: str) -> None:
    core, owner, client = seed(tmp_path)
    change: dict[str, Any] = {
        "id": "restricted",
        "kind": "method",
        "key": "restricted",
        "scope": "lab" if restriction == "scope" else "space",
        "body": "Free method",
    }
    if restriction in {"proposal", "withdrawn"}:
        change["application"] = restriction
    elif restriction == "tombstone":
        change["tombstone"] = True
    save(owner, change)
    payload = {
        "id": "ordinary-work",
        "conversation": "ordinary-work",
        "goal": "Task",
        "method_ref": {"id": "restricted", "revision": 1, "role": "exact"},
        "scope": "other",
        "call_limit": 2,
        "continuation_policy": "durable",
    }
    before = inspect(core, "works")
    if transition == "open":
        operation, request = "open_work", payload
    else:
        client.call(
            "open_work", payload | {"method_ref": {"id": "practice", "revision": 1}}, "open-valid"
        )
        before = inspect(core, "works")
        operation, request = (
            "control_work",
            {
                "work_id": payload["id"],
                "revision": before[0]["revision"],
                "action": "refresh",
                "method_ref": payload["method_ref"],
            },
        )
    with pytest.raises(CoreError, match="method.scope|inactive_method"):
        client.call(operation, request, uuid4().hex)
    assert inspect(core, "works") == before and inspect(core, "attempts") == []


def test_exhausted_ready_outcome_persists_paused(tmp_path: Path) -> None:
    core, _, client = seed(tmp_path)
    sleep = Sleep(client)
    sleep.start(work_id="s", call_limit=2)
    result = sleep.run("s", PROFILE, Driver(MechanicalSleepReceiver(state="ready")))
    assert result["state"] == "paused"
    assert inspect(core, "works")[0]["status"] == "paused"
    progress = sleep.progress("s")["body"]["value"]
    assert progress["stop_reason"] == "resource_exhausted" and progress["consumed_resource"] == 2
    assert progress["remaining_refs"] == []
    assert any(
        i["kind"] == "resource" and json.loads(i["body"])["reason"] == "resource_exhausted"
        for i in inspect(core, "intents")
    )


@pytest.mark.parametrize("state,limit", [("completed", 2), ("ready", 2), ("ready", 4)])
def test_post_c8_crash_registers_delivery_and_changes(
    tmp_path: Path, state: str, limit: int
) -> None:
    core, _, client = seed(tmp_path)
    sleep = Sleep(client)
    sleep.start(work_id="s", call_limit=limit)
    killed = crash_sleep(core, client, "outcome:" + state)
    assert killed.returncode == 91, killed.stderr
    assert any(h["id"] == "learned" for h in inspect(core, "heads"))
    assert sleep.progress("s")["body"]["value"]["delivered_manifest_refs"] == []

    class NeverInfer:
        resource_upper = 2
        tool_handler: Any = None
        sends = 0

        def run(self, context: Any, action: str) -> bytes:
            self.sends += 1
            raise AssertionError("New inference before mechanical recovery observation")

    receiver = NeverInfer()
    reopened = Sleep(Core(core.root).connect(client.token))
    if state == "ready" and limit == 4:
        # Retain ready as stopped while testing projection recovery independently of more execution.
        work = inspect(core, "works")[0]
        client.call(
            "control_work",
            {"work_id": "s", "revision": work["revision"], "action": "pause"},
            uuid4().hex,
        )
    for _ in range(2):
        try:
            reopened.run("s", PROFILE, receiver)
        except CoreError as error:
            assert error.code in {"stale_basis", "resource_exhausted"}
    progress = reopened.progress("s")["body"]["value"]
    assert progress["delivered_manifest_refs"]
    assert any(r.endswith(":outcome") for r in progress["applied_receipts"])
    assert progress["analysis_result_refs"] == []
    assert progress["remaining_refs"] == progress["enumerated_source_refs"]
    assert receiver.sends == 0 and inspect(core, "works")[0]["reserved"] == 2


def test_sleep_run_does_not_resume_unstarted_owner_pause(tmp_path: Path) -> None:
    core, _, client = seed(tmp_path)
    sleep = Sleep(client)
    sleep.start(work_id="s", call_limit=4)
    work = inspect(core, "works")[0]
    client.call(
        "control_work",
        {"work_id": "s", "revision": work["revision"], "action": "pause"},
        uuid4().hex,
    )
    receiver = MechanicalSleepReceiver()
    with pytest.raises(CoreError, match="sleep.paused"):
        sleep.run("s", PROFILE, Driver(receiver))
    assert receiver.actions == [] and inspect(core, "works")[0]["status"] == "paused"


@pytest.mark.parametrize("phase", ["before-pause", "after-pause", "after-projection"])
def test_resource_pause_crash_recovers_authoritative_cause(tmp_path: Path, phase: str) -> None:
    core, _, client = seed(tmp_path)
    sleep = Sleep(client)
    sleep.start(work_id="s", call_limit=3)

    class Returned:
        resource_upper = 1
        tool_handler: Any = None

        def run(self, context: Any, action: str) -> bytes:
            return json.dumps(
                {
                    "state": "ready",
                    "text": "Actual bounded result with honest remainder",
                    "changes": [
                        {
                            "id": "learned",
                            "kind": "memory",
                            "key": "learned",
                            "body": "Actual correction",
                        }
                    ],
                    "expected_heads": {"learned": 0},
                }
            ).encode()

    class CannotFit:
        resource_upper = 3
        tool_handler: Any = None
        sends = 0

        def run(self, context: Any, action: str) -> bytes:
            self.sends += 1
            raise AssertionError("New inference must not fit remaining resource")

    sleep.run("s", PROFILE, Returned())
    initial = sleep.progress("s")["body"]["value"]
    killed = crash_sleep(core, client, "resource-" + phase)
    assert killed.returncode == 91, killed.stderr
    if phase == "after-pause":
        assert inspect(core, "works")[0]["status"] == "paused"
        assert sleep.progress("s")["body"]["value"]["stop_reason"] == "terminal_received"
    receiver = CannotFit()
    previous = None
    for _ in range(2):
        reopened = Sleep(Core(core.root).connect(client.token))
        with pytest.raises(CoreError, match="resource_exhausted"):
            reopened.run("s", PROFILE, receiver)
        progress = reopened.progress("s")
        value = progress["body"]["value"]
        assert value["stop_reason"] == "resource_exhausted"
        assert value["consumed_resource"] == 1 and value["unresolved_calls"] == []
        for field in [
            "remaining_refs",
            "delivered_manifest_refs",
            "applied_receipts",
            "analysis_result_refs",
        ]:
            assert value[field] == initial[field]
        assert value["remaining_refs"] and value["applied_receipts"]
        if previous:
            assert progress == previous
        previous = progress
    assert receiver.sends == 0 and inspect(core, "works")[0]["reserved"] == 1


@pytest.mark.parametrize("continuation", ["resume", "refresh"])
@pytest.mark.parametrize("reason", [None, "owner_review"])
def test_owner_pause_replaces_previous_resource_cause(
    tmp_path: Path, continuation: str, reason: str | None
) -> None:
    core, _, client = seed(tmp_path)
    sleep = Sleep(client)
    sleep.start(work_id="s", call_limit=4)
    work = inspect(core, "works")[0]
    client.call(
        "control_work",
        {
            "work_id": "s",
            "revision": work["revision"],
            "action": "pause",
            "reason": "resource_exhausted",
        },
        uuid4().hex,
    )
    work = inspect(core, "works")[0]
    client.call(
        "control_work",
        {"work_id": "s", "revision": work["revision"], "action": continuation},
        uuid4().hex,
    )
    assert not any(i["kind"] == "control" for i in inspect(core, "intents"))
    work = inspect(core, "works")[0]
    client.call(
        "control_work",
        {"work_id": "s", "revision": work["revision"], "action": "pause", "reason": reason},
        uuid4().hex,
    )
    receiver = MechanicalSleepReceiver()
    for _ in range(2):
        with pytest.raises(CoreError, match="sleep.paused"):
            Sleep(Core(core.root).connect(client.token)).run("s", PROFILE, Driver(receiver))
    assert receiver.actions == []
    assert sleep.progress("s")["body"]["value"]["stop_reason"] == "not_started"
    control = next(i for i in inspect(core, "intents") if i["kind"] == "control")
    assert json.loads(control["body"]) == {"action": "pause", "reason": reason}


def test_enumeration_cannot_skip_to_finished_cursor(tmp_path: Path) -> None:
    core, owner, client = seed(tmp_path)
    sleep = Sleep(client)
    sleep.start(work_id="s", call_limit=4, portion=1)
    change, revision = progress_change(sleep, "s")
    change["body"]["enumeration_cursor"] = [change["body"]["source_high_watermark"], 2147483647]
    before = inspect(core, "records")
    with pytest.raises(CoreError, match="enumeration_prefix"):
        save(owner, change, revision)
    assert inspect(core, "records") == before
    assert Sleep(Core(core.root).connect(client.token)).start(work_id="s", call_limit=4, portion=1)[
        "has_more"
    ]


def test_enumeration_sparse_scopes_batch_members_and_late_arrival(tmp_path: Path) -> None:
    _, owner, _ = seed(tmp_path)
    changes = [
        {"id": name, "kind": "data", "key": name, "scope": scope, "body": name}
        for name, scope in [("a", "lab"), ("b", "other"), ("c", "lab"), ("d", "lab")]
    ]
    owner.call(
        "apply_changes",
        {"changes": changes},
        "same-event",
        expected_heads={c["id"]: 0 for c in changes},
    )
    for i in range(3):
        owner.call("read_snapshot", {}, "sourceless-event-" + str(i))
    sleep = Sleep(owner)
    sleep.start(work_id="s", scope="lab", method_id="lab-method", call_limit=4, portion=1)
    first = sleep.progress("s")["body"]["value"]
    assert first["enumerated_source_refs"][0]["index"] == 0
    high = first["source_high_watermark"]
    save(
        owner,
        {"id": "late-lab", "kind": "data", "key": "late-lab", "scope": "lab", "body": "later"},
    )
    sleep.continue_portion("s", portion=1)
    second = sleep.progress("s")["body"]["value"]
    assert second["enumerated_source_refs"][1]["index"] == 2
    assert (
        second["enumerated_source_refs"][1]["sequence"]
        == first["enumerated_source_refs"][0]["sequence"]
    )
    # Selection may be empty without falsifying mechanical enumeration or claiming analysis.
    change, revision = progress_change(sleep, "s")
    change["body"]["selected_source_refs"] = []
    save(owner, change, revision)
    sleep.continue_portion("s", portion=100)
    final = sleep.progress("s")["body"]["value"]
    bounded = owner.call(
        "read_history", {"scope": "lab", "high_watermark": high, "limit": 100}, "bounded-history"
    )
    assert final["enumerated_source_refs"] == [s["source_ref"] for s in bounded["sources"]]
    assert final["source_high_watermark"] == high
    assert final["analysis_result_refs"] == final["delivered_manifest_refs"] == []
    assert final["remaining_refs"] == final["enumerated_source_refs"]
    assert "late-lab" not in {s["material"]["record"]["id"] for s in bounded["sources"]}
