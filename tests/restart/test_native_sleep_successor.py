"""Verified completed Sleep successors over disposable fictional public Core data."""

import base64
import copy
import json
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from zaratustra_app import Coordinator, Sleep
from zaratustra_app.native_session import NativeSession
from zaratustra_core import Core, CoreError


def seed(tmp_path: Path) -> tuple[Any, str]:
    core, token = Core.initialize(tmp_path / "core")
    changes = [{"id": "subject", "kind": "activity", "key": "subject", "body": "Fictional task"}]
    changes += [
        {
            "id": "source-" + str(n),
            "kind": "data",
            "key": "source-" + str(n),
            "scope": "subject",
            "body": "Fictional observation " + str(n),
        }
        for n in range(5)
    ]
    core.connect(token).call(
        "apply_changes", {"changes": changes}, "seed", expected_heads={c["id"]: 0 for c in changes}
    )
    return core, token


def complete(session: NativeSession, *, analysed: bool = False) -> dict[str, Any]:
    ctx = session.context()
    mapping = ctx["current"]
    metadata: dict[str, Any] = {"outputs": [{"id": "subject", "revision": 1}]}
    if analysed:
        progress = next(
            r for r in ctx["sleep"]["inputs"] if r["id"] == mapping["work"] + ":progress"
        )
        body = copy.deepcopy(progress["body"]["value"])
        analysis = mapping["attempt"] + ":analysis"
        body["remaining_refs"] = []
        body["delivered_manifest_refs"].append(ctx["sleep"]["sleep_delivery_manifest"])
        body["analysis_result_refs"].append({"id": analysis, "revision": 1})
        body["consumed_resource"] = ctx["sleep"]["resource_state"]["consumed_resource"]
        body["unresolved_calls"] = []
        body["stop_reason"] = "bounded_portion_ended"
        body["continuation"] = "No finding; uncertainty remains"
        metadata.update(
            {
                "changes": [
                    {
                        "id": analysis,
                        "kind": "data",
                        "key": analysis,
                        "scope": "subject",
                        "body": {
                            "format": "sleep-analysis/v1",
                            "sources": body["selected_source_refs"],
                            "content": "Synthetic structural analysis; no useful finding claimed",
                        },
                    },
                    {
                        "id": progress["id"],
                        "kind": "data",
                        "key": progress["key"],
                        "scope": "subject",
                        "body": body,
                    },
                ],
                "expected_heads": {analysis: 0, progress["id"]: progress["revision"]},
            }
        )
    session.tool("result", "stage-" + uuid4().hex, metadata)
    result = session.settled(
        "final-" + uuid4().hex, "No finding established; unknowns remain.", False
    )
    assert result["state"] == "completed" and result["accepted"] is False
    return cast(dict[str, Any], mapping)


def ordinary_turn(session: NativeSession) -> None:
    session.input("ordinary-input", "Help with the same fictional task")
    session.tool(
        "route",
        "route",
        {
            "outputs": [{"id": "subject", "revision": 1}],
            "next_work": {"scope": "subject", "goal": "Ordinary work", "inputs": []},
        },
    )
    session.tool("result", "ordinary-stage", {"outputs": [{"id": "subject", "revision": 1}]})
    session.settled("ordinary-final", "An ordinary useful reply.", False)


def test_completed_backlog_successor_preserves_parent_and_old_cutoff(tmp_path: Path) -> None:
    core, token = seed(tmp_path)
    first = NativeSession(core, token, "first")
    first.start_sleep("subject", portion=2)
    parent = complete(first)
    sleep = Sleep(core.connect(token))
    predecessor = sleep.progress(parent["work"])
    co = Coordinator(core.connect(token))
    parent_row = co.rows("works", work=parent["work"])[0]
    parent_result = co.rows("results", work=parent["work"])[0]
    ordinary_turn(NativeSession(core, token, "ordinary"))
    method = core.connect(token).call(
        "read_exact", {"id": "native-sleep-method:subject", "revision": 1}, "read-old-method"
    )
    core.connect(token).call(
        "apply_changes",
        {
            "changes": [
                {
                    "id": method["id"],
                    "kind": "method",
                    "key": method["key"],
                    "scope": "subject",
                    "body": "Fictional current Sleep instructions",
                }
            ]
        },
        "method-revision",
        expected_heads={method["id"]: 1},
    )
    second = NativeSession(core, token, "second")
    ctx = second.start_sleep("subject", portion=2)
    child = ctx["current"]
    progress = sleep.progress(child["work"])["body"]["value"]
    old = predecessor["body"]["value"]
    assert child["work"] != parent["work"]
    assert progress["format"] == "sleep-progress/v2" and progress["transition"] == "same_window"
    assert progress["predecessor_ref"] == {
        "id": predecessor["id"],
        "revision": predecessor["revision"],
        "role": "exact",
    }
    assert progress["source_high_watermark"] == old["source_high_watermark"]
    assert progress["enumerated_source_refs"] == old["enumerated_source_refs"]
    assert progress["remaining_refs"] == old["remaining_refs"]
    assert not progress["analysis_result_refs"] and not progress["delivered_manifest_refs"]
    assert progress["unexplored_coverage_position"] == old["unexplored_coverage_position"]
    assert ctx["sleep"]["method"]["revision"] == 2 and old["method_ref"]["revision"] == 1
    assert co.rows("works", work=parent["work"])[0] == parent_row
    assert co.rows("results", work=parent["work"])[0] == parent_result
    assert sleep.progress(parent["work"]) == predecessor


def test_fully_processed_successor_enumerates_only_after_verified_boundary(tmp_path: Path) -> None:
    core, token = seed(tmp_path)
    first = NativeSession(core, token, "first")
    first.start_sleep("subject", portion=100)
    parent = complete(first, analysed=True)
    old = Sleep(core.connect(token)).progress(parent["work"])["body"]["value"]
    assert not old["remaining_refs"] and old["enumeration_cursor"][1] == 2147483647
    core.connect(token).call(
        "apply_changes",
        {
            "changes": [
                {
                    "id": "new-arrival",
                    "kind": "data",
                    "key": "new-arrival",
                    "scope": "subject",
                    "body": "Later fictional observation",
                }
            ]
        },
        "new-arrival",
        expected_heads={"new-arrival": 0},
    )
    ctx = NativeSession(core, token, "second").start_sleep("subject", portion=100)
    value = Sleep(core.connect(token)).progress(ctx["current"]["work"])["body"]["value"]
    assert value["transition"] == "new_window"
    assert value["range_start"] == [old["source_high_watermark"], 2147483647]
    assert all(
        r["sequence"] > old["source_high_watermark"] for r in value["enumerated_source_refs"]
    )
    assert any(
        s["material"].get("record", {}).get("id") == "new-arrival"
        for s in ctx["sleep"]["sleep_sources"]
    )
    assert not value["analysis_result_refs"] and not value["applied_receipts"]


@pytest.mark.parametrize("window", ["after_open", "after_progress", "after_bind"])
def test_successor_reopen_recovers_single_unclaimed_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window: str
) -> None:
    core, token = seed(tmp_path)
    first = NativeSession(core, token, "first")
    first.start_sleep("subject", portion=2)
    parent = complete(first)
    original_init = Sleep.initialize_successor
    original_bind = Sleep._bind_progress
    from zaratustra_app.native_sleep import NativeSleep

    original_claim = NativeSleep._claim

    def interrupted_init(self: Sleep, work_id: str, *, portion: int = 16) -> dict[str, Any]:
        raise RuntimeError("after open")

    def interrupted_bind(self: Sleep, work_id: str, progress: dict[str, Any]) -> None:
        if work_id != parent["work"]:
            raise RuntimeError("after progress")
        original_bind(self, work_id, progress)

    def interrupted_claim(self: Any, work_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("after bind")

    if window == "after_open":
        monkeypatch.setattr(Sleep, "initialize_successor", interrupted_init)
    elif window == "after_progress":
        monkeypatch.setattr(Sleep, "_bind_progress", interrupted_bind)
    else:
        monkeypatch.setattr(NativeSleep, "_claim", interrupted_claim)
    with pytest.raises(RuntimeError):
        NativeSession(core, token, "interrupted").start_sleep("subject")
    monkeypatch.setattr(Sleep, "initialize_successor", original_init)
    monkeypatch.setattr(Sleep, "_bind_progress", original_bind)
    monkeypatch.setattr(NativeSleep, "_claim", original_claim)
    ctx = NativeSession(core, token, "reopened").start_sleep("subject")
    co = Coordinator(core.connect(token))
    works = [w for w in co.rows("works") if json.loads(w["body"])["goal"] == "Sleep"]
    assert len(works) == 2
    assert len(co.rows("attempts", work=ctx["current"]["work"])) == 1
    with pytest.raises(CoreError, match="outcome_unknown"):
        NativeSession(core, token, "another").start_sleep("subject")


def test_finite_exhaustion_has_no_successor_or_send(tmp_path: Path) -> None:
    core, token = seed(tmp_path)
    sleep = Sleep(core.connect(token))
    sleep.start(
        work_id="finite", scope="subject", call_limit=1, method_id="native-sleep-method:subject"
    )
    session = NativeSession(core, token, "finite")
    ctx = session.start_sleep("subject")
    assert ctx["sleep"]["resource_state"]["call_limit"] == 1
    complete(session)
    with pytest.raises(CoreError, match="continuation.calls"):
        NativeSession(core, token, "next").start_sleep("subject")
    assert (
        len(
            [
                w
                for w in Coordinator(core.connect(token)).rows("works")
                if json.loads(w["body"])["goal"] == "Sleep"
            ]
        )
        == 1
    )


def test_claim_before_native_mapping_is_unknown_not_redispatched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core, token = seed(tmp_path)
    first = NativeSession(core, token, "first")
    first.start_sleep("subject", portion=2)
    parent = complete(first)
    original_save = NativeSession._save

    def interrupted(self: Any, revision: int, value: dict[str, Any]) -> None:
        raise RuntimeError("claim retained before mapping")

    monkeypatch.setattr(NativeSession, "_save", interrupted)
    with pytest.raises(RuntimeError):
        NativeSession(core, token, "interrupted").start_sleep("subject")
    monkeypatch.setattr(NativeSession, "_save", original_save)
    co = Coordinator(core.connect(token))
    child = next(
        w
        for w in co.rows("works")
        if json.loads(w["body"]).get("continuation", {}).get("parent_work_id") == parent["work"]
    )
    attempts = co.rows("attempts", work=child["id"])
    with pytest.raises(CoreError, match="outcome_unknown"):
        NativeSession(core, token, "reopened").start_sleep("subject")
    assert co.rows("attempts", work=child["id"]) == attempts


def test_finite_successor_inherits_only_unspent_allowance(tmp_path: Path) -> None:
    core, token = seed(tmp_path)
    sleep = Sleep(core.connect(token))
    sleep.start(
        work_id="finite", scope="subject", call_limit=3, method_id="native-sleep-method:subject"
    )
    first = NativeSession(core, token, "finite-first")
    first.start_sleep("subject")
    complete(first)
    child = NativeSession(core, token, "finite-second").start_sleep("subject")
    state = child["sleep"]["resource_state"]
    assert state["mode"] == "finite" and state["call_limit"] == 2
    assert state["reservation_upper"] == state["consumed_resource"] == 1


def test_unavailable_established_progress_never_restarts_at_zero(tmp_path: Path) -> None:
    core, token = seed(tmp_path)
    first = NativeSession(core, token, "first")
    first.start_sleep("subject", portion=2)
    parent = complete(first)
    sleep = Sleep(core.connect(token))
    record = sleep.progress(parent["work"])
    core.connect(token).call(
        "apply_changes",
        {
            "changes": [
                {
                    "id": record["id"],
                    "kind": "data",
                    "key": record["key"],
                    "scope": "subject",
                    "body": "Explicit fictional unavailable checkpoint",
                }
            ]
        },
        "invalidate-checkpoint",
        expected_heads={record["id"]: record["revision"]},
    )
    with pytest.raises(CoreError, match="progress_unavailable"):
        NativeSession(core, token, "next").start_sleep("subject")
    assert (
        len(
            [
                w
                for w in Coordinator(core.connect(token)).rows("works")
                if json.loads(w["body"])["goal"] == "Sleep"
            ]
        )
        == 1
    )


def completed_root(
    helper: Any, work_id: str, *, portion: int = 2, selected_size: int | None = None
) -> dict[str, Any]:
    if selected_size is not None:
        helper.sleep.start(
            work_id=work_id,
            scope="subject",
            portion=portion,
            method_id="native-sleep-method:subject",
        )
        refs = helper.sleep.progress(work_id)["body"]["value"]["remaining_refs"]
        helper.sleep.select_sources(work_id, refs[:selected_size])
    mapping = helper.start(work_id, {"model": "fictional"}, portion=portion)
    helper.client.call(
        "observe_attempt",
        {
            "attempt_id": mapping["attempt"],
            "event_id": "terminal",
            "kind": "terminal",
            "raw_base64": base64.b64encode(
                json.dumps(
                    {"state": "completed", "text": "No finding; remaining sources retained"}
                ).encode()
            ).decode(),
        },
        uuid4().hex,
    )
    helper.coordinator.recover(mapping["attempt"])
    helper.checkpoint(work_id, mapping["attempt"])
    return cast(dict[str, Any], mapping)


def cancel_root(helper: Any, work_id: str) -> None:
    work = helper.coordinator.rows("works", work=work_id)[0]
    helper.client.call(
        "control_work",
        {
            "work_id": work_id,
            "revision": work["revision"],
            "action": "cancel",
            "reason": "Explicit fictional owner cancellation",
        },
        uuid4().hex,
    )


def test_cancelled_roots_are_retained_without_becoming_analysed_boundaries(tmp_path: Path) -> None:
    from zaratustra_app.native_sleep import NativeSleep

    core, token = seed(tmp_path)
    helper = NativeSleep(core, token, "subject")
    extras = [
        {
            "id": "extra-" + str(n),
            "kind": "data",
            "key": "extra-" + str(n),
            "scope": "subject",
            "body": "Fictional later source " + str(n),
        }
        for n in range(81)
    ]
    for offset in range(0, len(extras), 32):
        batch = extras[offset : offset + 32]
        helper.client.call(
            "apply_changes",
            {"changes": batch},
            "extra-batch-" + str(offset),
            expected_heads={c["id"]: 0 for c in batch},
        )
    helper.sleep.start(
        work_id="cancelled69", scope="subject", method_id="native-sleep-method:subject"
    )
    cancel_root(helper, "cancelled69")
    unknown = helper.start("cancelled-cdf", {"model": "fictional"})
    helper.client.call(
        "observe_attempt",
        {"attempt_id": unknown["attempt"], "event_id": "lost", "kind": "unknown"},
        "lost",
    )
    cancel_root(helper, "cancelled-cdf")
    retained_actions = helper.coordinator.rows("actions", work="cancelled-cdf")
    retained_attempts = helper.coordinator.rows("attempts", work="cancelled-cdf")
    completed_root(helper, "completed0169", portion=16, selected_size=4)
    old = helper.sleep.progress("completed0169")["body"]["value"]
    assert len(old["selected_source_refs"]) == 4 and len(old["remaining_refs"]) == 16
    assert not old["analysis_result_refs"] and len(old["delivered_manifest_refs"]) == 1
    history = helper.client.call(
        "read_history",
        {"scope": "subject", "limit": 100, "high_watermark": old["source_high_watermark"]},
        "all-old-sources",
    )
    assert len(history["sources"]) - len(old["enumerated_source_refs"]) == 74
    assert all(ref in old["remaining_refs"] for ref in old["selected_source_refs"])
    ctx = NativeSession(core, token, "next").start_sleep("subject")
    new = helper.sleep.progress(ctx["current"]["work"])["body"]["value"]
    assert {w["work_id"] for w in ctx["sleep"]["cancelled_history"]} == {
        "cancelled69",
        "cancelled-cdf",
    }
    assert all(w["analysed_boundary_credit"] is False for w in ctx["sleep"]["cancelled_history"])
    assert new["predecessor_ref"]["id"] == "completed0169:progress"
    assert new["range_start"] == [0, 0]
    assert new["source_high_watermark"] == old["source_high_watermark"]
    assert new["remaining_refs"] == old["remaining_refs"]
    assert all(ref in new["remaining_refs"] for ref in old["selected_source_refs"])
    assert helper.coordinator.rows("actions", work="cancelled-cdf") == retained_actions
    assert helper.coordinator.rows("attempts", work="cancelled-cdf") == retained_attempts
    assert helper.coordinator.rows("works", work="cancelled69")[0]["status"] == "cancelled"
    assert helper.coordinator.rows("works", work="cancelled-cdf")[0]["status"] == "cancelled"


def test_two_eligible_completed_roots_require_choice(tmp_path: Path) -> None:
    from zaratustra_app.native_sleep import NativeSleep

    core, token = seed(tmp_path)
    helper = NativeSleep(core, token, "subject")
    completed_root(helper, "one")
    completed_root(helper, "two")
    with pytest.raises(CoreError, match="ambiguous_unclaimed_sleep"):
        NativeSession(core, token, "next").start_sleep("subject")
    assert (
        len(
            [
                w
                for w in helper.coordinator.rows("works")
                if json.loads(w["body"])["goal"] == "Sleep"
            ]
        )
        == 2
    )


def test_new_explicit_sleep_after_cancel_starts_fresh_without_old_queue(tmp_path: Path) -> None:
    from zaratustra_app.native_sleep import NativeSleep

    core, token = seed(tmp_path)
    helper = NativeSleep(core, token, "subject")
    helper.sleep.start(
        work_id="cancelled", scope="subject", method_id="native-sleep-method:subject"
    )
    cancel_root(helper, "cancelled")
    old = helper.coordinator.rows("works", work="cancelled")
    fresh = NativeSession(core, token, "next").start_sleep("subject")
    assert fresh["current"]["work"] != "cancelled"
    assert "continuation" not in fresh["sleep"]["work"]
    assert (
        helper.sleep.progress(fresh["current"]["work"])["body"]["value"]["format"]
        == "sleep-progress/v1"
    )
    assert helper.coordinator.rows("works", work="cancelled") == old
    assert not helper.coordinator.rows("attempts", work="cancelled")
