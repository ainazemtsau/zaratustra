"""Explicit cancellation ends a pass; a new owner request creates fresh analysis."""

import base64
import copy
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from zaratustra_app import Sleep
from zaratustra_app.native_sleep import NativeSleep
from zaratustra_core import Core, CoreError

from .sleep_support import save


def seed(tmp_path: Path) -> tuple[Any, str, NativeSleep]:
    core, token = Core.initialize(tmp_path / "core")
    save(
        core.connect(token),
        {"id": "source", "kind": "data", "key": "source", "body": "Fictional retained source"},
    )
    return core, token, NativeSleep(core, token, "space")


def cancel(helper: NativeSleep, work_id: str) -> None:
    work = helper.coordinator.rows("works", work=work_id)[0]
    helper.client.call(
        "control_work",
        {
            "work_id": work_id,
            "revision": work["revision"],
            "action": "cancel",
            "reason": "Explicit owner cancellation",
        },
        uuid4().hex,
    )


def terminal(helper: NativeSleep, mapping: dict[str, Any], state: str = "completed") -> None:
    helper.client.call(
        "observe_attempt",
        {
            "attempt_id": mapping["attempt"],
            "event_id": "terminal",
            "kind": "terminal",
            "raw_base64": base64.b64encode(
                json.dumps(
                    {"state": state, "text": "No finding established; remaining sources retained"}
                ).encode()
            ).decode(),
        },
        uuid4().hex,
    )
    helper.coordinator.recover(mapping["attempt"])
    helper.checkpoint(mapping["work"], mapping["attempt"])


@pytest.mark.parametrize("state", ["unclaimed", "claimed", "unknown", "ready"])
def test_cancelled_initial_pass_fresh_history_preserves_old_facts(
    tmp_path: Path, state: str
) -> None:
    core, token, helper = seed(tmp_path)
    if state == "unclaimed":
        helper.sleep.start(work_id="old", method_id="native-sleep-method:space")
    else:
        old = helper.start("old", {"model": "fictional"})
        if state == "unknown":
            helper.client.call(
                "observe_attempt",
                {"attempt_id": old["attempt"], "event_id": "lost", "kind": "unknown"},
                "lost",
            )
        elif state == "ready":
            terminal(helper, old, "ready")
    cancel(helper, "old")
    assert helper.verified_cancelled_work("old") is True
    before = {
        table: helper.coordinator.rows(table, work="old")
        for table in ("works", "attempts", "actions", "results", "tool_calls", "observations")
    }
    old_progress = helper.sleep.progress("old")
    fresh = NativeSleep(Core(core.root), token, "space").follow({"model": "new"})
    value = helper.sleep.progress(fresh["work"])["body"]["value"]
    assert fresh["work"] != "old" and value["format"] == "sleep-progress/v1"
    assert "predecessor_ref" not in value and not value["analysis_result_refs"]
    assert value["source_high_watermark"] > old_progress["body"]["value"]["source_high_watermark"]
    ctx = helper.context(fresh)
    assert "continuation" not in ctx["work"]
    assert ctx["work"]["conversation"] != before["works"][0]["conversation"]
    assert "fresh pass after explicit cancellation" in ctx["instructions"]
    first = helper.client.call(
        "read_history",
        {"scope": "space", "limit": 1, "high_watermark": value["source_high_watermark"]},
        uuid4().hex,
    )["sources"][0]
    assert value["enumerated_source_refs"][0] == first["source_ref"]
    for table, rows in before.items():
        assert helper.coordinator.rows(table, work="old") == rows
    assert helper.sleep.progress("old") == old_progress


def test_completed_parent_cancelled_child_retires_whole_component(tmp_path: Path) -> None:
    _, _, helper = seed(tmp_path)
    parent = helper.follow({"model": "first"})
    terminal(helper, parent)
    child = helper.follow({"model": "child"})
    assert helper.context(child)["work"]["continuation"]["parent_work_id"] == parent["work"]
    cancel(helper, child["work"])
    saved = {
        table: helper.coordinator.rows(table)
        for table in ("works", "attempts", "actions", "results")
    }
    fresh = helper.follow({"model": "fresh"})
    assert "continuation" not in helper.context(fresh)["work"]
    assert helper.sleep.progress(fresh["work"])["body"]["value"]["format"] == "sleep-progress/v1"
    terminal(helper, fresh)
    next_pass = helper.follow({"model": "successor"})
    assert helper.context(next_pass)["work"]["continuation"]["parent_work_id"] == fresh["work"]
    for table, rows in saved.items():
        current = helper.coordinator.rows(table)
        assert all(row in current for row in rows)


@pytest.mark.parametrize("fresh_limit", [None, 2])
def test_fresh_policy_is_not_cancelled_budget_and_old_unknown_is_not_resolved(
    tmp_path: Path, fresh_limit: int | None
) -> None:
    _, _, helper = seed(tmp_path)
    old = helper.start("old", {"model": "old"}, call_limit=5)
    helper.client.call(
        "observe_attempt",
        {"attempt_id": old["attempt"], "event_id": "unknown", "kind": "unknown"},
        "unknown",
    )
    cancel(helper, "old")
    old_action = helper.coordinator.rows("actions", work="old")[0]
    assert old_action["state"] not in {"terminal", "not_received"}
    fresh = helper.follow({"model": "fresh"}, call_limit=fresh_limit)
    ctx = helper.context(fresh)
    assert ctx["work"]["call_limit"] == fresh_limit
    assert ctx["resource_state"]["call_limit"] == fresh_limit
    assert ctx["work"].get("continuation") is None
    assert helper.coordinator.rows("actions", work="old")[0] == old_action
    old_work = helper.coordinator.rows("works", work="old")[0]
    assert old_work["reserved"] == 1 and json.loads(old_work["body"])["call_limit"] == 5
    late = helper.client.call(
        "observe_attempt",
        {
            "attempt_id": old["attempt"],
            "event_id": "late",
            "kind": "terminal",
            "raw_base64": base64.b64encode(b'{"state":"completed","text":"late"}').decode(),
        },
        "late",
    )
    assert late["late"] is True
    with pytest.raises(CoreError):
        helper.coordinator.recover(old["attempt"])
    assert helper.coordinator.rows("actions", work="old")[0] == old_action
    assert not helper.coordinator.rows("results", work="old")


def test_fresh_memory_is_mandatory_beyond_catalog_and_other_inputs_survive_binding(
    tmp_path: Path,
) -> None:
    core, token, helper = seed(tmp_path)
    owner = core.connect(token)
    for offset in range(0, 105, 32):
        changes = [
            {"id": "filler-" + str(n), "kind": "data", "key": "filler-" + str(n), "body": "Fixture"}
            for n in range(offset, min(105, offset + 32))
        ]
        owner.call(
            "apply_changes",
            {"changes": changes},
            "fill-" + str(offset),
            expected_heads={c["id"]: 0 for c in changes},
        )
    save(
        owner,
        {"id": "memory", "kind": "memory", "key": "memory", "body": "Successful retained memory"},
    )
    old = helper.follow({"model": "old"})
    cancel(helper, old["work"])
    save(
        owner,
        {"id": "memory", "kind": "memory", "key": "memory", "body": "Current successful memory"},
        1,
    )
    fresh = helper.follow({"model": "fresh"})
    ctx = helper.context(fresh)
    assert not any(r["id"] == "memory" for r in ctx["catalog"])
    assert next(r for r in ctx["inputs"] if r["id"] == "memory")["revision"] == 2
    # A separate unclaimed Work exercises binding without altering a claimed Attempt.
    sleep = Sleep(owner)
    started = sleep.start(work_id="binding", method_id="native-sleep-method:space")
    extra = save(
        owner, {"id": "mandatory", "kind": "data", "key": "mandatory", "body": "Required input"}
    )
    work = helper.coordinator.rows("works", work="binding")[0]
    inputs = json.loads(work["body"])["inputs"] + [extra | {"role": "exact"}]
    owner.call(
        "control_work",
        {"work_id": "binding", "revision": work["revision"], "action": "refresh", "inputs": inputs},
        uuid4().hex,
    )
    sleep._bind_progress("binding", started["progress_ref"])
    bound = json.loads(helper.coordinator.rows("works", work="binding")[0]["body"])["inputs"]
    assert extra | {"role": "exact"} in bound
    assert {"id": "memory", "revision": 2, "role": "must_be_current"} in bound
    assert started["progress_ref"] | {"role": "must_be_current"} in bound


@pytest.mark.parametrize("window", ["open", "progress", "binding", "claim"])
def test_fresh_launch_crashes_recover_one_unclaimed_work_or_fence_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window: str
) -> None:
    _, _, helper = seed(tmp_path)
    old = helper.follow({"model": "old"})
    cancel(helper, old["work"])
    original_progress = Sleep._start_progress
    original_bind = Sleep._bind_progress
    original_claim = NativeSleep._claim

    def stop_progress(self: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("after open")

    def stop_bind(self: Any, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("after progress")

    def stop_claim(self: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if window == "claim":
            original_claim(self, *args, **kwargs)
        raise RuntimeError("after binding/claim")

    if window == "open":
        monkeypatch.setattr(Sleep, "_start_progress", stop_progress)
    elif window == "progress":
        monkeypatch.setattr(Sleep, "_bind_progress", stop_bind)
    else:
        monkeypatch.setattr(NativeSleep, "_claim", stop_claim)
    with pytest.raises(RuntimeError):
        helper.follow({"model": "interrupted"})
    monkeypatch.setattr(Sleep, "_start_progress", original_progress)
    monkeypatch.setattr(Sleep, "_bind_progress", original_bind)
    monkeypatch.setattr(NativeSleep, "_claim", original_claim)
    before = helper.coordinator.rows("works")
    if window == "claim":
        with pytest.raises(CoreError, match="outcome_unknown"):
            helper.follow({"model": "reopened"})
    else:
        fresh = helper.follow({"model": "reopened"})
        assert len(helper.coordinator.rows("attempts", work=fresh["work"])) == 1
    assert len(helper.coordinator.rows("works")) == len(before) == 2


@pytest.mark.parametrize(
    "corruption",
    [
        "missing",
        "wrong_result",
        "fork",
        "cycle",
        "cancel_fact",
        "foreign_basis",
        "empty_basis",
        "missing_basis",
        "wrong_revision",
        "cancel_generation",
    ],
)
def test_invalid_lineage_projection_never_becomes_fresh_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corruption: str
) -> None:
    _, _, helper = seed(tmp_path)
    parent = helper.follow({"model": "parent"})
    terminal(helper, parent)
    child = helper.follow({"model": "child"})
    cancel(helper, child["work"])
    read = helper.coordinator.rows

    def projected(table: str, **filters: Any) -> list[dict[str, Any]]:
        rows = copy.deepcopy(read(table, **filters))
        if table == "works" and not filters:
            if corruption == "missing":
                return [r for r in rows if r["id"] != parent["work"]]
            for row in rows:
                if row["id"] == child["work"]:
                    body = json.loads(row["body"])
                    if corruption == "wrong_result":
                        body["continuation"]["result_hash"] = "0" * 64
                    elif corruption == "cycle":
                        body["continuation"]["parent_work_id"] = child["work"]
                    elif corruption == "foreign_basis":
                        body["continuation"]["basis_refs"] = [
                            {"id": "source", "revision": 1, "role": "exact"}
                        ]
                    elif corruption == "empty_basis":
                        body["continuation"]["basis_refs"] = []
                    elif corruption == "missing_basis":
                        body["continuation"]["basis_refs"] = [
                            {"id": "missing", "revision": 1, "role": "exact"}
                        ]
                    elif corruption == "wrong_revision":
                        body["continuation"]["parent_work_revision"] += 1
                    elif corruption == "cancel_generation":
                        row["generation"] = 1
                    row["body"] = json.dumps(body)
                    if corruption == "fork":
                        sibling = copy.deepcopy(row)
                        sibling["id"] = "forged-sibling"
                        rows.append(sibling)
                        break
        if table == "intents" and corruption == "cancel_fact":
            rows = [
                r for r in rows if not (r["kind"] == "control" and r["subject"] == child["work"])
            ]
        return rows

    # App reader boundary fault injection; underlying Core is never patched/corrupted.
    monkeypatch.setattr(helper.coordinator, "rows", projected)
    with pytest.raises(CoreError):
        helper.follow({"model": "forbidden"})
    assert len(read("works")) == 2


def test_non_cancelled_unknown_and_ambiguous_components_remain_blockers(tmp_path: Path) -> None:
    _, _, helper = seed(tmp_path)
    active = helper.follow({"model": "active"})
    assert helper.verified_cancelled_work(active["work"]) is False
    with pytest.raises(CoreError, match="outcome_unknown"):
        helper.follow({"model": "not fresh"})
    terminal(helper, active)
    unrelated = helper.start("unrelated", {"model": "unrelated"})
    terminal(helper, unrelated)
    with pytest.raises(CoreError, match="ambiguous_unclaimed_sleep"):
        helper.follow({"model": "no arbitrary choice"})
