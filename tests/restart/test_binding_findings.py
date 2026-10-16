"""Independent state oracles for binding review F1/F2 and their neighboring cases."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from zaratustra_core import Client, Core, CoreError

from .support import PROFILE, inspect
from .test_contract import outcome, prepared

INVALID_DECLARATIONS: list[tuple[dict[str, Any], Any]] = [
    ({"type": "list", "items": {"type": []}}, []),
    ({"type": "list", "items": {"type": {}}}, []),
    ({"type": "list", "items": {"type": "unknown"}}, []),
    ({"type": "list", "items": {"type": "unknown"}, "nullable": True}, None),
    (
        {"type": "object", "fields": [{"name": "x", "type": "list", "items": {"type": "unknown"}}]},
        {},
    ),
    ({"type": "object", "nullable": True, "fields": [{"name": "x", "type": "unknown"}]}, None),
    ({"type": "list", "items": {"type": "text", "nullable": "true"}}, []),
    ({"type": "list", "items": {"type": "integer", "min": True}}, []),
    ({"type": "list", "items": {"type": "enum", "values": ["x", "x"]}}, []),
    ({"type": "object", "fields": [{"name": "x", "type": "list"}]}, {}),
]


def domain(core: Core) -> dict[str, Any]:
    return {
        table: inspect(core, table)
        for table in (
            "records",
            "heads",
            "receipts",
            "events",
            "works",
            "attempts",
            "results",
            "waits",
            "messages",
            "conversations",
            "intents",
        )
    }


@pytest.mark.parametrize("operation", ["apply_changes", "commit_outcome"])
@pytest.mark.parametrize("schema,value", INVALID_DECLARATIONS)
def test_declaration_rejected_atomically(
    tmp_path: Path, operation: str, schema: dict[str, Any], value: Any
) -> None:
    core, owner, executor, _ = prepared(tmp_path)
    owner.call(
        "apply_changes",
        {"changes": [{"id": "schema", "kind": "data", "key": "schema", "body": schema}]},
        "schema",
        expected_heads={"schema": 0},
    )
    if operation == "commit_outcome":
        executor.call(
            "claim_dispatch", {"attempt_id": "A1", "generation": 1}, "claim", action_id="action"
        )
        executor.call(
            "observe_attempt",
            {"attempt_id": "A1", "event_id": "terminal", "kind": "terminal", "raw_base64": "e30="},
            "retain",
        )
    changes = [
        {"id": "first", "kind": "data", "key": "first", "body": "must roll back"},
        {
            "id": "entry",
            "kind": "data",
            "key": "entry",
            "body": value,
            "schema_ref": {"id": "schema", "revision": 1},
        },
    ]
    payload = (
        {"changes": changes} if operation == "apply_changes" else outcome() | {"changes": changes}
    )
    before = domain(core)
    with pytest.raises(CoreError, match="invalid_request"):
        executor.call(operation, payload, "rejected", expected_heads={"first": 0, "entry": 0})
    assert domain(core) == before, "invalid declaration left a partial C3/C8 bundle"


@pytest.mark.parametrize("value", [{}, {"x": []}, {"x": None}, {"x": [1, 2]}])
def test_valid_optional_empty_nullable_and_plain_text(tmp_path: Path, value: Any) -> None:
    core, owner, _, _ = prepared(tmp_path)
    schema = {
        "type": "object",
        "fields": [{"name": "x", "type": "list", "nullable": True, "items": {"type": "integer"}}],
    }
    owner.call(
        "apply_changes",
        {"changes": [{"id": "schema", "kind": "data", "key": "schema", "body": schema}]},
        "schema",
        expected_heads={"schema": 0},
    )
    owner.call(
        "apply_changes",
        {
            "changes": [
                {
                    "id": "entry",
                    "kind": "data",
                    "key": "entry",
                    "body": value,
                    "schema_ref": {"id": "schema", "revision": 1},
                },
                {
                    "id": "plain",
                    "kind": "data",
                    "key": "plain",
                    "body": "The moon is made of cheese.",
                },
            ]
        },
        "valid",
        expected_heads={"entry": 0, "plain": 0},
    )
    assert {h["id"] for h in inspect(core, "heads")} >= {"entry", "plain"}


def wait_outcome(host: Client, attempt: str, generation: int, cursor: int, question: str) -> None:
    host.call(
        "claim_dispatch",
        {"attempt_id": attempt, "generation": generation},
        "claim:" + attempt,
        action_id="action:" + attempt,
    )
    host.call(
        "observe_attempt",
        {"attempt_id": attempt, "event_id": "terminal", "kind": "terminal", "raw_base64": "e30="},
        "retain:" + attempt,
    )
    host.call(
        "commit_outcome",
        {
            "attempt_id": attempt,
            "generation": generation,
            "terminal_event": "terminal",
            "original_cursor": cursor,
            "processed_cutoff": 20,
            "state": "waiting",
            "text": question,
            "wait": {"id": question, "question": question},
        },
        "outcome:" + attempt,
    )


def answer(owner: Client, question: str, event: str) -> dict[str, Any]:
    return owner.call(
        "ingest_message",
        {
            "conversation": "conversation",
            "event_id": event,
            "raw_base64": base64.b64encode(b"exact answer").decode(),
            "reply_to": {"id": question, "revision": 1},
        },
        event,
    )


def test_old_wait_cannot_unblock_current_question(tmp_path: Path) -> None:
    core, owner, host, coordinator = prepared(tmp_path)
    wait_outcome(host, "A1", 1, 0, "Q1")
    owner.call("control_work", {"work_id": "work", "revision": 3, "action": "pause"}, "pause")
    owner.call("control_work", {"work_id": "work", "revision": 4, "action": "resume"}, "resume")
    coordinator.prepare("work", "A2", PROFILE)
    wait_outcome(host, "A2", 2, 20, "Q2")
    before = domain(core)
    try:
        answer(owner, "Q1", "old-answer")
    except CoreError as error:
        assert error.code == "stale_basis"
        assert domain(core) == before, "rejected old reply changed the state bundle"
    assert inspect(core, "works")[0]["status"] == "waiting", "old reply released unanswered Q2"
    assert next(w for w in inspect(core, "waits") if w["id"] == "Q2")["status"] == "waiting"
    with pytest.raises(CoreError, match="stale_basis"):
        coordinator.prepare("work", "A3", PROFILE)
    assert inspect(core, "works")[0]["status"] == "waiting"
    first = answer(owner, "Q2", "current-answer")
    after = domain(core)
    assert answer(owner, "Q2", "current-answer") == first
    assert domain(core) == after, "receipt replay changed current state"
    assert inspect(core, "works")[0]["status"] == "ready"
    assert next(w for w in inspect(core, "waits") if w["id"] == "Q2")["status"] == "answered"
    coordinator.prepare("work", "A3", PROFILE)


@pytest.mark.parametrize("control", ["pause", "cancel"])
def test_fenced_question_does_not_create_continuation(tmp_path: Path, control: str) -> None:
    core, owner, host, _ = prepared(tmp_path)
    wait_outcome(host, "A1", 1, 0, "Q1")
    owner.call("control_work", {"work_id": "work", "revision": 3, "action": control}, "control")
    before = domain(core)
    with pytest.raises(CoreError, match="stale_basis"):
        answer(owner, "Q1", "fenced-answer")
    assert domain(core) == before
