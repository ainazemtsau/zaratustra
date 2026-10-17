"""Whole-source query bounds apply before durable history read responses are copied."""

from __future__ import annotations

import base64
import copy
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from zaratustra_core import Core, CoreError, wire

from .support import fixture, inspect
from .test_contract import prepared


def seeded(root: Path, values: list[str]) -> tuple[Core, Any]:
    core, token = Core.initialize(root / "core")
    owner = core.connect(token)
    for index, value in enumerate(values):
        owner.call(
            "apply_changes",
            {
                "changes": [
                    {
                        "id": f"record-{index}",
                        "kind": "data",
                        "key": f"record-{index}",
                        "body": value,
                    }
                ]
            },
            f"record-{index}",
            expected_heads={f"record-{index}": 0},
        )
    return core, owner


def assert_prefix(
    result: dict[str, Any], full: list[dict[str, Any]], after: list[int], budget: int
) -> None:
    assert len(wire(result)) <= budget
    assert result["sources"] == full[: len(result["sources"])]
    assert result["query_coverage"]["returned"] == len(result["sources"])
    if result["has_more"]:
        expected = (
            [
                full[len(result["sources"]) - 1]["source_ref"]["sequence"],
                full[len(result["sources"]) - 1]["source_ref"]["index"],
            ]
            if result["sources"]
            else after
        )
        assert result["cursor"] == expected
        withheld = full[len(result["sources"])]
        assert result["query_coverage"]["first_withheld_source_ref"] == withheld["source_ref"]
        assert result["query_coverage"]["first_withheld_source_bytes"] == len(wire(withheld))
    else:
        assert result["cursor"] == [result["high_watermark"], 2147483647]


def test_absent_null_legacy_result_and_cached_commands_are_unchanged(tmp_path: Path) -> None:
    _, owner = seeded(tmp_path, ["first", "second"])
    old = owner.call("read_history", {}, "old-command")
    high = old["high_watermark"]
    assert set(old) == {"sources", "cursor", "has_more", "high_watermark"}
    assert owner.call("read_history", {"high_watermark": high, "byte_limit": None}, "null") == old
    assert owner.call("read_history", {}, "old-command") == old
    assert owner.call("read_history", {"high_watermark": high}, "same-default") == old
    bounded = owner.call("read_history", {"high_watermark": high, "byte_limit": 2000}, "bounded")
    assert bounded["sources"] == old["sources"]
    assert (
        owner.call("read_history", {"high_watermark": high, "byte_limit": 2000}, "bounded")
        == bounded
    )
    with pytest.raises(CoreError, match="idempotency_conflict"):
        owner.call("read_history", {"high_watermark": high, "byte_limit": 2001}, "bounded")
    with pytest.raises(CoreError, match="idempotency_conflict"):
        owner.call("read_history", {"byte_limit": 2000}, "old-command")


def test_count_and_bytes_page_exact_sources_without_gaps_or_cursor_skips(tmp_path: Path) -> None:
    _, owner = seeded(tmp_path, ["data-" + str(n) + "x" * 500 for n in range(9)])
    full = owner.call("read_history", {"limit": 100}, "full")
    after = [0, 0]
    combined: list[dict[str, Any]] = []
    for index in range(10):
        result = owner.call(
            "read_history",
            {
                "high_watermark": full["high_watermark"],
                "limit": 2,
                "after_sequence": after[0],
                "after_index": after[1],
                "byte_limit": 2200,
            },
            f"page-{index}",
        )
        assert_prefix(result, full["sources"][len(combined) :], after, 2200)
        combined.extend(result["sources"])
        if index == 0:
            owner.call(
                "apply_changes",
                {
                    "changes": [
                        {
                            "id": "record-0",
                            "kind": "data",
                            "key": "record-0",
                            "body": "Later revision outside the frozen cutoff",
                        }
                    ]
                },
                "later-revision",
                expected_heads={"record-0": 1},
            )
        if not result["has_more"]:
            break
        assert result["sources"]
        after = result["cursor"]
    assert combined == full["sources"]


def test_entire_utf8_escaped_result_and_final_withheld_metadata_fit(tmp_path: Path) -> None:
    _, owner = seeded(
        tmp_path,
        [("雪🙂" + chr(34) + chr(92) + chr(10)) * 100, ("Ω" + chr(34) + chr(92)) * 200, "tail"],
    )
    full = owner.call("read_history", {}, "full")
    for budget in (500, 1500, 2000, 2500, 4000, 10_000):
        result = owner.call(
            "read_history",
            {"high_watermark": full["high_watermark"], "byte_limit": budget},
            f"bytes-{budget}",
        )
        assert_prefix(result, full["sources"], [0, 0], budget)
    # A result that fits a budget exactly remains legal including metadata.
    result = owner.call(
        "read_history", {"high_watermark": full["high_watermark"], "byte_limit": 4000}, "boundary"
    )
    exact = len(wire(result))
    replay = owner.call(
        "read_history", {"high_watermark": full["high_watermark"], "byte_limit": exact}, "exact"
    )
    assert len(wire(replay)) <= exact
    assert len(wire(result)) > len(json.dumps(result, ensure_ascii=False))


def test_oversized_first_source_reports_exact_ref_size_and_does_not_advance(tmp_path: Path) -> None:
    _, owner = seeded(tmp_path, ["large" * 30_000, "later"])
    full = owner.call("read_history", {}, "full")
    result = owner.call(
        "read_history", {"high_watermark": full["high_watermark"], "byte_limit": 1000}, "small"
    )
    assert_prefix(result, full["sources"], [0, 0], 1000)
    assert result["sources"] == []
    assert result["state"] == "NOT_DELIVERED"
    assert result["reason"] == "single_source_too_large"
    assert result["has_more"] is True
    assert result["query_coverage"]["byte_limited"] is True
    moved = copy.deepcopy(result)
    moved["cursor"] = [full["high_watermark"], 2147483647]
    with pytest.raises(AssertionError):
        assert_prefix(moved, full["sources"], [0, 0], 1000)
    with pytest.raises(AssertionError):
        assert len(wire(full)) <= 1000  # The old unbounded behavior fails this control.


@pytest.mark.parametrize("budget", [1, 0, -1, True, False, "1000", 1.5, [], {}])
def test_bad_or_metadata_unfit_budgets_have_no_events_or_receipts(
    tmp_path: Path, budget: Any
) -> None:
    core, owner = seeded(tmp_path, ["exact"])
    before = {name: inspect(core, name) for name in ("events", "receipts")}
    with pytest.raises(CoreError) as rejected:
        owner.call("read_history", {"byte_limit": budget}, "bad-budget")
    if type(budget) is int and budget == 1:
        assert rejected.value.code == "invalid_request"
        assert rejected.value.field == "history.byte_limit"
    assert before == {name: inspect(core, name) for name in before}


def test_permissions_high_cursor_scope_and_capability_remain_enforced(tmp_path: Path) -> None:
    core, owner, _ = fixture(tmp_path)
    denied = core.connect(core.grant(owner.token, "no-read", ["read"], origin="host"))
    core.revoke(owner.token, "no-read")
    with pytest.raises(CoreError, match="denied"):
        denied.call("read_history", {"byte_limit": 1000}, "denied")
    full = owner.call("read_history", {}, "high")
    for payload in (
        {"high_watermark": full["high_watermark"] + 1000},
        {"high_watermark": 0, "after_sequence": 1},
    ):
        with pytest.raises(CoreError):
            owner.call("read_history", payload | {"byte_limit": 1000}, "bad-range")
    empty = owner.call("read_history", {"scope": "foreign", "byte_limit": 1000}, "foreign")
    assert empty["sources"] == [] and empty["has_more"] is False
    discovery = owner.call("describe_contract", {}, "discovery")["read_history"]
    assert discovery["byte_limit_optional"] is True
    assert "entire canonical" in discovery["byte_limit_scope"]


def test_repeated_large_fictional_observations_persist_bounded_query_results(
    tmp_path: Path,
) -> None:
    core, owner, _, _ = prepared(tmp_path)
    owner.call("claim_dispatch", {"attempt_id": "A1", "generation": 1}, "claim", action_id="action")
    boundary = owner.call("read_history", {"limit": 1}, "before-observations")["high_watermark"]
    for index in range(90):
        size = 111_000 if index % 15 == 0 else 626_000 if index % 15 == 1 else 500
        raw = base64.b64encode(
            json.dumps({"tool": "fictional-read", "output": "x" * size}).encode()
        ).decode()
        owner.call(
            "observe_attempt",
            {
                "attempt_id": "A1",
                "event_id": f"observed-{index}",
                "kind": "progress",
                "raw_base64": raw,
            },
            f"observe-{index}",
        )
    request = {"limit": 100, "after_sequence": boundary, "after_index": 2147483647}
    unbounded = owner.call("read_history", request, "unbounded-large")
    assert len(unbounded["sources"]) == 90
    request["high_watermark"] = unbounded["high_watermark"]
    for cycle in range(8):
        bounded = owner.call("read_history", request | {"byte_limit": 51_200}, f"bounded-{cycle}")
        assert_prefix(bounded, unbounded["sources"], [boundary, 2147483647], 51_200)
        assert bounded["state"] == "NOT_DELIVERED"
    with sqlite3.connect(core.path) as db:
        events = dict(
            db.execute(
                "SELECT subject,length(CAST(body AS BLOB)) FROM events "
                "WHERE subject='unbounded-large' OR subject LIKE 'bounded-%'"
            )
        )
        receipts = dict(
            db.execute(
                "SELECT command,length(CAST(response AS BLOB)) FROM receipts "
                "WHERE command='unbounded-large' OR command LIKE 'bounded-%'"
            )
        )
    assert events["unbounded-large"] > 5_000_000
    assert all(events[f"bounded-{n}"] <= 51_200 for n in range(8))
    assert all(receipts[f"bounded-{n}"] < 52_000 for n in range(8))
    assert len(inspect(core, "observations")) == 90
    print(
        json.dumps(
            {
                "unbounded_event_bytes": events["unbounded-large"],
                "unbounded_receipt_bytes": receipts["unbounded-large"],
                "eight_bounded_event_bytes": sum(events[f"bounded-{n}"] for n in range(8)),
                "eight_bounded_receipt_bytes": sum(receipts[f"bounded-{n}"] for n in range(8)),
            }
        )
    )
