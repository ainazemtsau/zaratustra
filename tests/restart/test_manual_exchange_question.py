"""Pending exchange questions finish a step without a new wait lifecycle."""

import json
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app.native_session import NativeSession
from zaratustra_core import Core, CoreError, outcome_metadata_contract


@pytest.fixture
def exchange(tmp_path: Path) -> NativeSession:
    core, token = Core.initialize(tmp_path / "core")
    session = NativeSession(core, token, "pending-question")
    session.input("request", "Configure fictional paper notes; direction is unknown.")
    session.tool("exchange", "begin", {"operation": "begin"})
    return session


@pytest.mark.parametrize(
    ("metadata", "field"),
    [
        (
            {"state": "waiting", "wait": {"id": "direction", "question": "Which direction?"}},
            "state",
        ),
        ({"state": "ready"}, "state"),
        ({"wait": {"id": "direction", "question": "Which direction?"}}, "wait"),
    ],
)
def test_exchange_metadata_rejection_clears_stage_before_any_outcome(
    exchange: NativeSession, metadata: dict[str, Any], field: str
) -> None:
    session = exchange
    session.tool("result", "old-stage", {"outputs": []})
    before = {
        table: session.coordinator.rows(table)
        for table in ("observations", "results", "waits", "works")
    }
    subject_heads = [h for h in session.coordinator.rows("heads") if h["id"] != session.mapping_id]
    rejection = session.tool("result", "bad-metadata", {"outputs": [], **metadata})
    assert rejection["state"] == "rejected" and rejection["staged"] is False
    assert rejection["previous_metadata_cleared"] is True
    assert rejection["rejection"]["field"] == "exchange.result_" + field
    assert "completed" in rejection["text"] and "pending" in rejection["text"]
    assert session._load()[1]["staged"] == {}
    assert {table: session.coordinator.rows(table) for table in before} == before
    assert [
        h for h in session.coordinator.rows("heads") if h["id"] != session.mapping_id
    ] == subject_heads
    session.tool("result", "corrected", {"outputs": [], "state": "completed"})
    assert (
        session.settled("actual-final", "Which direction? Setup remains pending.", False)["state"]
        == "completed"
    )
    assert not session.coordinator.rows("waits")
    result = session.coordinator.rows("results")[-1]
    assert json.loads(result["body"])["text"] == "Which direction? Setup remains pending."


@pytest.mark.parametrize("kind", ["change", "route", "result-change", "expected-heads"])
def test_subject_denial_is_not_metadata_feedback(exchange: NativeSession, kind: str) -> None:
    change = {"id": "forbidden", "kind": "activity", "key": "forbidden", "body": "No"}
    payload: dict[str, Any] = {"outputs": [], "state": "waiting"}
    name = kind if kind in {"route", "change"} else "result"
    payload.update(
        {"expected_heads": {"forbidden": 0}} if kind == "expected-heads" else {"changes": [change]}
    )
    before = exchange._load()
    with pytest.raises(CoreError, match="exchange.confirmed_changes_only"):
        exchange.tool(name, "forbidden", payload)
    assert exchange._load() == before
    assert not any(h["id"] == "forbidden" for h in exchange.coordinator.rows("heads"))


def test_exchange_contract_is_specific_without_changing_shared_core_contract(
    exchange: NativeSession,
) -> None:
    contract = exchange.context()["outcome_metadata_contract"]
    properties = contract["metadata_schema"]["properties"]
    assert properties["state"]["enum"] == ["completed"]
    assert "wait" not in properties and "changes" not in properties
    assert (
        "waiting" in outcome_metadata_contract()["metadata_schema"]["properties"]["state"]["enum"]
    )


def test_exchange_cleanup_cas_failure_remains_fatal(
    exchange: NativeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    exchange.tool("result", "old-stage", {"outputs": []})

    def fail_save(revision: int, value: dict[str, Any]) -> None:
        raise CoreError("stale_basis", "fictional.cleanup_cas")

    monkeypatch.setattr(exchange, "_save", fail_save)
    with pytest.raises(CoreError, match="fictional.cleanup_cas"):
        exchange.tool("result", "bad", {"outputs": [], "state": "waiting"})
