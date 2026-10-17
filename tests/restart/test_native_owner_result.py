"""Review and owner acceptance stay distinct, linked to the exact same delivery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from zaratustra_app import Coordinator, Driver
from zaratustra_app.conversation import pin_profile
from zaratustra_app.native_session import NativeSession
from zaratustra_app.native_verdict import delivery, record
from zaratustra_core import CoreError

from .test_native_review import delivered


def test_human_verdict_pins_exact_result_and_replays_without_duplicate(tmp_path: Path) -> None:
    core, token, attempt = delivered(tmp_path)
    shown = delivery(core, token)
    assert shown["attempt_id"] == attempt and shown["review"] is None
    with pytest.raises(CoreError, match="stale_basis"):
        record(core, token, attempt, "wrong", "accepted", "Explicit fictional owner verdict")
    revised = record(core, token, attempt, shown["result_hash"], "revised", "Нужна одна правка")
    assert revised["owner_words"] == "Нужна одна правка"
    session = NativeSession(core, token, "owner-ui")
    assert not session.coordinator.snapshot()["acceptance"]
    accepted = record(
        core, token, attempt, shown["result_hash"], "accepted", "Принимаю этот результат"
    )
    assert (
        record(core, token, attempt, shown["result_hash"], "accepted", "Принимаю этот результат")
        == accepted
    )
    state = session.coordinator.snapshot()
    assert len(state["acceptance"]) == 1
    heads = [h for h in state["heads"] if h["id"].startswith("owner-verdict:")]
    assert len(heads) == 2 and all(h["scope"] == "subject" for h in heads)


def test_fresh_native_review_retains_report_without_mutation_or_acceptance(tmp_path: Path) -> None:
    core, token, builder = delivered(tmp_path)
    reviewer = NativeSession(core, token, "fresh-review-Pi")
    reviewer.profile = {"model": "fictional-reviewer", "provider": "fictional"}
    context = reviewer.start_review("subject", builder)
    assert context["current"]["mode"] == "review"
    assert context["review"]["inputs"]
    with pytest.raises(CoreError, match="read_only_review"):
        reviewer.tool("result", "forbidden", {"changes": [{"id": "bad"}]})
    with pytest.raises(CoreError, match="read_only_review"):
        reviewer.tool("change", "write", {"changes": []})
    reviewer.tool("result", "review-result", {"outputs": [{"id": "subject", "revision": 1}]})
    result = reviewer.settled("review-final-entry", "Finding: actual evidence is limited.", False)
    assert result["state"] == "completed" and not result["accepted"]
    shown = delivery(core, token)
    assert shown["attempt_id"] == builder
    assert shown["review"]["text"] == "Finding: actual evidence is limited."
    assert not reviewer.coordinator.snapshot()["acceptance"]
    owner = core.connect(token)
    owner.call(
        "apply_changes",
        {
            "changes": [
                {
                    "id": "sleep-method",
                    "kind": "method",
                    "key": "sleep",
                    "scope": "subject",
                    "body": "Inspect retained outcomes",
                }
            ]
        },
        "sleep-method",
        expected_heads={"sleep-method": 0},
    )
    coordinator = Coordinator(owner)
    coordinator.open_work(
        {
            "id": "sleep-report",
            "conversation": "separate-sleep",
            "goal": "Sleep",
            "method_ref": {"id": "sleep-method", "revision": 1},
            "call_limit": None,
            "continuation_policy": "durable",
        },
        scope="subject",
    )
    profile = pin_profile(owner, "sleep-profile", {"model": "fictional"})
    prepared = coordinator.prepare("sleep-report", "sleep-report-attempt", profile)
    coordinator.dispatch(
        "sleep-report-attempt",
        prepared["generation"],
        Driver(
            lambda *_: json.dumps(
                {
                    "state": "completed",
                    "text": "Retained Sleep report",
                    "outputs": [{"id": "subject", "revision": 1}],
                }
            ).encode()
        ),
    )
    coordinator.recover("sleep-report-attempt")
    fresh = NativeSession(core, token, "entirely-fresh-pi")
    latest = fresh.context()["latest_delivery"]
    assert latest["attempt_id"] == builder
    pointer = latest["review_ref"]
    rows = fresh.tool("read", "review-discovery", pointer["read"])["rows"]
    row = next(r for r in rows if r["attempt"] == pointer["attempt_id"])
    assert row["fingerprint"] == pointer["result_hash"]
    assert json.loads(row["body"])["text"] == "Finding: actual evidence is limited."
    sleep_pointer = next(r for r in latest["related_results"] if r["goal"] == "Sleep")
    sleep_rows = fresh.tool("read", "sleep-discovery", sleep_pointer["read"])["rows"]
    assert any(json.loads(r["body"])["text"] == "Retained Sleep report" for r in sleep_rows)
    assert latest["related_coverage"]["total"] >= 3
