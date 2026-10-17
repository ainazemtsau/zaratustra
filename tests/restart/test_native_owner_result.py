"""Review and owner acceptance stay distinct, linked to the exact same delivery."""

from __future__ import annotations

from pathlib import Path

import pytest
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
