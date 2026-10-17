"""Synthetic native Sleep transport checks, never semantic evaluation."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from zaratustra_app.native_sleep import NativeSleep
from zaratustra_core import Core, CoreError

from .sleep_support import MechanicalSleepReceiver, seed
from .support import inspect


def test_native_sleep_pins_and_commits_actual_terminal(tmp_path: Path) -> None:
    core, owner, _ = seed(tmp_path)
    owner.call(
        "ingest_message",
        {
            "conversation": "human",
            "event_id": "human-1",
            "raw_base64": base64.b64encode(b"An ordinary useful conversation").decode(),
        },
        "human",
    )
    helper = NativeSleep(core, owner.token, "space")
    profile = {"provider": "fictional", "model": "native-pi", "session_id": "native-test"}
    mapping = helper.start("native-sleep", profile, portion=100)
    context = helper.context(mapping)
    assert mapping["mode"] == "sleep" and mapping["profile"] == profile
    assert context["resource_state"]["call_limit"] is None
    assert context["sleep_sources"] and context["sleep_delivery_manifest"]
    assert inspect(core, "works")[0]["reserved"] == 0
    receiver = MechanicalSleepReceiver()
    output = json.loads(receiver(context, mapping["attempt"] + ":action"))
    envelope = {"native_event_id": "settled", "assistant_text": output["text"], "outcome": output}
    helper.client.call(
        "observe_attempt",
        {
            "attempt_id": mapping["attempt"],
            "event_id": "terminal",
            "kind": "terminal",
            "raw_base64": base64.b64encode(json.dumps(envelope).encode()).decode(),
        },
        "native-terminal",
    )
    # Reopen after retention, before C8: no model call or replacement output.
    reopened = NativeSleep(Core(core.root), owner.token, "space")
    result = reopened.coordinator.recover(
        mapping["attempt"], decoder=lambda raw: json.loads(raw)["outcome"]
    )
    reopened.checkpoint(mapping["work"], mapping["attempt"])
    assert result["state"] == "completed" and result["accepted"] is False
    with pytest.raises(CoreError, match="not_ready"):
        reopened.resume(mapping["work"], profile)
    assert len(receiver.received) == 1
    progress = reopened.sleep.progress(mapping["work"])["body"]["value"]
    assert progress["analysis_result_refs"] and not progress["remaining_refs"]
    reopened.sleep.open_work(
        {
            "id": "next",
            "conversation": "next",
            "goal": "Try current",
            "method_ref": {"id": "practice", "revision": 1},
            "call_limit": None,
            "continuation_policy": "durable",
        }
    )
    next_mapping = reopened.coordinator.prepare(
        "next", "next-attempt", {"id": "profile", "revision": 1}
    )
    assert next_mapping["pinned"]["method"]["revision"] == 2
    assert next(m for m in next_mapping["pinned"]["inputs"] if m["id"] == "memory")["revision"] == 2
    core.backup(owner.token, tmp_path / "backup")
    assert (tmp_path / "backup" / "manifest.json").exists()


def test_native_sleep_unknown_reopen_never_dispatches(tmp_path: Path) -> None:
    core, owner, _ = seed(tmp_path)
    helper = NativeSleep(core, owner.token, "space")
    mapping = helper.start("sleep", {"model": "fictional"})
    helper.client.call(
        "observe_attempt",
        {"attempt_id": mapping["attempt"], "event_id": "lost", "kind": "unknown"},
        "lost",
    )
    reopened = NativeSleep(Core(core.root), owner.token, "space")
    with pytest.raises(CoreError, match="outcome_unknown"):
        reopened.start("sleep", {"model": "fictional"})
    with pytest.raises(CoreError, match="outcome_unknown"):
        reopened.resume("sleep", {"model": "fictional"})
    assert len(inspect(core, "attempts")) == len(inspect(core, "actions")) == 1
    assert not inspect(core, "results")


def test_native_sleep_ready_resumes_same_cutoff_with_new_attempt(tmp_path: Path) -> None:
    core, owner, _ = seed(tmp_path)
    helper = NativeSleep(core, owner.token, "space")
    mapping = helper.start("sleep", {"model": "first"}, portion=2)
    before = helper.sleep.progress("sleep")["body"]["value"]
    context = helper.context(mapping)
    output = json.loads(MechanicalSleepReceiver(state="ready")(context, "synthetic-action"))
    helper.client.call(
        "observe_attempt",
        {
            "attempt_id": mapping["attempt"],
            "event_id": "terminal",
            "kind": "terminal",
            "raw_base64": base64.b64encode(json.dumps({"outcome": output}).encode()).decode(),
        },
        "terminal",
    )
    helper.coordinator.recover(mapping["attempt"], decoder=lambda raw: json.loads(raw)["outcome"])
    # Resume also repairs the checkpoint window before preparing the next portion.
    resumed = NativeSleep(Core(core.root), owner.token, "space")
    next_mapping = resumed.resume("sleep", {"model": "second"}, portion=2)
    after = resumed.sleep.progress("sleep")["body"]["value"]
    assert next_mapping["work"] == mapping["work"]
    assert next_mapping["attempt"] != mapping["attempt"]
    assert next_mapping["profile"]["model"] == "second"
    assert after["source_high_watermark"] == before["source_high_watermark"]
    assert after["enumerated_source_refs"][:2] == before["enumerated_source_refs"]
    assert len(after["enumerated_source_refs"]) == 4
    assert after["analysis_result_refs"] == [{"id": "sleep:analysis", "revision": 1}]
    assert after["delivered_manifest_refs"] == [context["sleep_delivery_manifest"]]
    assert (
        next(h for h in resumed.coordinator.snapshot()["heads"] if h["id"] == "memory")["revision"]
        == 2
    )
    with pytest.raises(CoreError, match="outcome_unknown"):
        resumed.resume("sleep", {"model": "third"})
