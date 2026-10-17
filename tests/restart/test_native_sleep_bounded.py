"""Whole-source Sleep admission under the unchanged Core context byte boundary."""

import base64
import copy
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from zaratustra_app import Coordinator
from zaratustra_app.native_session import NativeSession
from zaratustra_app.native_sleep import NativeSleep
from zaratustra_core import Core, CoreError


def seed_large(root: Path, size: int = 500_000) -> tuple[Any, str]:
    core, token = Core.initialize(root / "core")
    owner = core.connect(token)
    owner.call(
        "apply_changes",
        {
            "changes": [
                {"id": "subject", "kind": "activity", "key": "subject", "body": "Fictional task"},
                {
                    "id": "method",
                    "kind": "method",
                    "key": "method",
                    "scope": "subject",
                    "body": "Inspect",
                },
                {
                    "id": "profile",
                    "kind": "profile",
                    "key": "profile",
                    "body": {"model": "fictional"},
                },
            ]
        },
        "seed",
        expected_heads={"subject": 0, "method": 0, "profile": 0},
    )
    co = Coordinator(owner)
    co.open_work(
        {
            "id": "ordinary",
            "conversation": "ordinary",
            "goal": "Inspect",
            "method_ref": {"id": "method", "revision": 1},
            "call_limit": None,
            "continuation_policy": "durable",
        },
        scope="subject",
    )
    prepared = co.prepare("ordinary", "ordinary-attempt", {"id": "profile", "revision": 1})
    owner.call(
        "claim_dispatch",
        {
            "attempt_id": "ordinary-attempt",
            "generation": prepared["generation"],
            "resource_upper": None,
        },
        "claim",
        action_id="ordinary-action",
    )
    for n in range(2):
        owner.call(
            "observe_attempt",
            {
                "attempt_id": "ordinary-attempt",
                "event_id": "tool-" + str(n),
                "kind": "progress",
                "raw_base64": base64.b64encode(b"x" * size).decode(),
            },
            "observe-" + str(n),
        )
    return core, token


def finish_ready(helper: NativeSleep, mapping: dict[str, Any]) -> None:
    ctx = helper.context(mapping)
    record = helper.sleep.progress(mapping["work"])
    body = copy.deepcopy(record["body"]["value"])
    selected = body["selected_source_refs"]
    analysis = mapping["attempt"] + ":analysis"
    body["remaining_refs"] = [r for r in body["remaining_refs"] if r not in selected]
    body["delivered_manifest_refs"].append(ctx["sleep_delivery_manifest"])
    body["analysis_result_refs"].append({"id": analysis, "revision": 1})
    body["stop_reason"] = "bounded_portion_ended"
    body["continuation"] = "Inspect remaining complete sources"
    body["unresolved_calls"] = []
    output = {
        "state": "ready",
        "text": "Synthetic analysis; unknowns remain",
        "changes": [
            {
                "id": analysis,
                "kind": "data",
                "key": analysis,
                "scope": "subject",
                "body": {
                    "format": "sleep-analysis/v1",
                    "sources": selected,
                    "content": "Synthetic test only",
                },
            },
            {
                "id": record["id"],
                "kind": "data",
                "key": record["key"],
                "scope": "subject",
                "body": body,
            },
        ],
        "expected_heads": {analysis: 0, record["id"]: record["revision"]},
    }
    helper.client.call(
        "observe_attempt",
        {
            "attempt_id": mapping["attempt"],
            "event_id": "terminal",
            "kind": "terminal",
            "raw_base64": base64.b64encode(json.dumps(output).encode()).decode(),
        },
        uuid4().hex,
    )
    helper.coordinator.recover(mapping["attempt"])


def test_stranded_sleep_reuses_work_and_drains_complete_remaining_sources(tmp_path: Path) -> None:
    core, token = seed_large(tmp_path)
    helper = NativeSleep(core, token, "subject")
    helper.sleep.start(
        work_id="stranded", scope="subject", portion=16, method_id="native-sleep-method:subject"
    )
    before = helper.sleep.progress("stranded")["body"]["value"]
    history = helper.client.call(
        "read_history",
        {"scope": "subject", "limit": 16, "high_watermark": before["source_high_watermark"]},
        "measure-fixture",
    )
    source_sizes = [len(json.dumps(s).encode()) for s in history["sources"]]
    assert max(source_sizes) < 1048576 < sum(source_sizes)
    session = NativeSession(core, token, "fresh-native")
    ctx = session.start_sleep("subject", portion=16)
    mapping = ctx["current"]
    assert mapping["work"] == "stranded"
    assert (
        len(
            [
                w
                for w in helper.coordinator.rows("works")
                if json.loads(w["body"])["goal"] == "Sleep"
            ]
        )
        == 1
    )
    pinned = ctx["sleep"]
    selected = [s["source_ref"] for s in pinned["sleep_sources"]]
    assert selected and len(selected) < len(before["selected_source_refs"])
    after = helper.sleep.progress("stranded")["body"]["value"]
    assert after["remaining_refs"] == before["remaining_refs"]
    assert after["enumerated_source_refs"] == before["enumerated_source_refs"]
    assert after["source_high_watermark"] == before["source_high_watermark"]
    assert after["enumeration_cursor"] == before["enumeration_cursor"]
    finish_ready(helper, mapping)
    next_mapping = helper.resume("stranded", {"model": "fictional-next"}, portion=16)
    next_ctx = helper.context(next_mapping)
    assert all(s["source_ref"] not in selected for s in next_ctx["sleep_sources"])
    assert (
        helper.sleep.progress("stranded")["body"]["value"]["source_high_watermark"]
        == before["source_high_watermark"]
    )


def test_single_oversized_source_stops_without_claim_or_empty_delivery(tmp_path: Path) -> None:
    core, token = seed_large(tmp_path, size=900_000)
    helper = NativeSleep(core, token, "subject")
    helper.sleep.start(
        work_id="oversized", scope="subject", portion=16, method_id="native-sleep-method:subject"
    )
    history = helper.client.call("read_history", {"scope": "subject", "limit": 16}, "find-large")
    source = next(s for s in history["sources"] if "observation" in s["material"])
    helper.sleep.select_sources("oversized", [source["source_ref"]])
    with pytest.raises(CoreError, match="context.max_bytes"):
        helper.start("oversized", {"model": "fictional"}, portion=16)
    assert not helper.coordinator.rows("attempts", work="oversized")
    progress = helper.sleep.progress("oversized")["body"]["value"]
    assert progress["remaining_refs"]
    assert progress["stop_reason"] == "context_max_bytes"


def test_unmapped_attempted_sleep_is_not_replaced(tmp_path: Path) -> None:
    core, token = seed_large(tmp_path, size=10)
    helper = NativeSleep(core, token, "subject")
    helper.start("unknown", {"model": "fictional"})
    session = NativeSession(core, token, "fresh")
    with pytest.raises(CoreError, match="outcome_unknown"):
        session.start_sleep("subject")
    assert (
        len(
            [
                w
                for w in helper.coordinator.rows("works")
                if json.loads(w["body"])["goal"] == "Sleep"
            ]
        )
        == 1
    )


def test_unclaimed_sleep_ambiguity_and_stale_selection_do_not_choose(tmp_path: Path) -> None:
    core, token = seed_large(tmp_path, size=10)
    helper = NativeSleep(core, token, "subject")
    for work_id in ("one", "two"):
        helper.sleep.start(
            work_id=work_id, scope="subject", method_id="native-sleep-method:subject"
        )
    record = helper.sleep.progress("one")
    refs = record["body"]["value"]["remaining_refs"]
    helper.sleep.select_sources("one", refs[:1], expected_revision=record["revision"])
    with pytest.raises(CoreError, match="progress_revision"):
        helper.sleep.select_sources("one", refs, expected_revision=record["revision"])
    session = NativeSession(core, token, "fresh")
    with pytest.raises(CoreError, match="ambiguous_unclaimed_sleep"):
        session.start_sleep("subject")
    assert not helper.coordinator.rows("attempts", work="one")
    assert not helper.coordinator.rows("attempts", work="two")
