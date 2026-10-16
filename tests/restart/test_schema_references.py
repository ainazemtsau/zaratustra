"""Declared reference fields share C3/C8 atomic admission and backup closure."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from zaratustra_core import Core, CoreError

from .test_backup_references import rehash
from .test_binding_findings import domain
from .test_contract import outcome, prepared

SCHEMA = {
    "type": "object",
    "fields": [
        {"name": "refs", "type": "list", "items": {"type": "exact-ref"}},
        {"name": "optional", "type": "exact-ref", "nullable": True},
        {"name": "text", "type": "text"},
    ],
}


def setup(tmp_path: Path, operation: str) -> tuple[Any, Any, Any]:
    core, owner, executor, _ = prepared(tmp_path)
    owner.call(
        "apply_changes",
        {"changes": [{"id": "schema", "kind": "data", "key": "schema", "body": SCHEMA}]},
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
    return core, owner, executor


@pytest.mark.parametrize("operation", ["apply_changes", "commit_outcome"])
@pytest.mark.parametrize("location", ["refs", "optional"])
def test_dangling_schema_ref_rejects_entire_bundle(
    tmp_path: Path, operation: str, location: str
) -> None:
    core, _, executor = setup(tmp_path, operation)
    missing = {"id": "missing", "revision": 999}
    value = {location: [missing] if location == "refs" else missing}
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
    with pytest.raises(CoreError, match="missing_ref"):
        executor.call(operation, payload, "dangling", expected_heads={"first": 0, "entry": 0})
    assert domain(core) == before


@pytest.mark.parametrize("operation", ["apply_changes", "commit_outcome"])
def test_schema_historical_optional_and_prior_batch_refs(tmp_path: Path, operation: str) -> None:
    core, owner, executor = setup(tmp_path, operation)
    owner.call(
        "apply_changes",
        {"changes": [{"id": "target", "kind": "data", "key": "target", "body": "historical"}]},
        "target",
        expected_heads={"target": 0},
    )
    owner.call(
        "apply_changes",
        {"changes": [{"id": "target", "kind": "data", "key": "target", "body": "new revision"}]},
        "advance",
        expected_heads={"target": 1},
    )
    changes = [
        {
            "id": "first",
            "kind": "data",
            "key": "first",
            "body": {"id": "not-a-declared-ref", "revision": 999},
        },
        {
            "id": "entry",
            "kind": "data",
            "key": "entry",
            "body": {
                "refs": [
                    {"id": "target", "revision": 1, "role": "must_be_current"},
                    {"id": "first", "revision": 1},
                ],
                "optional": None,
                "text": "missing/999 is ordinary text",
            },
            "schema_ref": {"id": "schema", "revision": 1},
        },
        {
            "id": "empty",
            "kind": "data",
            "key": "empty",
            "body": {},
            "schema_ref": {"id": "schema", "revision": 1},
        },
    ]
    payload = (
        {"changes": changes} if operation == "apply_changes" else outcome() | {"changes": changes}
    )
    executor.call(operation, payload, "valid", expected_heads={"first": 0, "entry": 0, "empty": 0})
    core.backup(owner.token, tmp_path / "backup")
    restored, token = Core.restore_quarantined(tmp_path / "backup", tmp_path / "restored")
    saved = restored.connect(token).call("read_exact", {"id": "entry", "revision": 1}, "entry")
    assert saved["body"]["value"]["refs"][0]["revision"] == 1


def test_rehashed_schema_value_ref_is_closed(tmp_path: Path) -> None:
    core, owner, _ = setup(tmp_path, "apply_changes")
    owner.call(
        "apply_changes",
        {
            "changes": [
                {
                    "id": "entry",
                    "kind": "data",
                    "key": "entry",
                    "body": {"refs": [{"id": "memory", "revision": 1}]},
                    "schema_ref": {"id": "schema", "revision": 1},
                }
            ]
        },
        "entry",
        expected_heads={"entry": 0},
    )
    core.backup(owner.token, tmp_path / "backup")
    with sqlite3.connect(tmp_path / "backup/core.sqlite3") as db:
        body = json.loads(db.execute("SELECT body FROM records WHERE id='entry'").fetchone()[0])
        body["value"]["refs"] = [{"id": "missing", "revision": 999}]
        db.execute("UPDATE records SET body=? WHERE id='entry'", (json.dumps(body),))
    rehash(tmp_path / "backup")
    with pytest.raises(CoreError, match="backup.reference_closure"):
        Core.restore_quarantined(tmp_path / "backup", tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_observation_evidence_keeps_local_action_identity(tmp_path: Path) -> None:
    core, owner, executor, _ = prepared(tmp_path)
    executor.call(
        "claim_dispatch", {"attempt_id": "A1", "generation": 1}, "claim", action_id="action"
    )
    payload: dict[str, Any] = {
        "attempt_id": "A1",
        "event_id": "progress",
        "kind": "progress",
        "evidence": {
            "action_id": "missing",
            "state": "running",
            "receiver_ref": "external opaque receiver token",
        },
    }
    before = domain(core)
    with pytest.raises(CoreError, match="evidence.action_id"):
        executor.call("observe_attempt", payload, "wrong-action")
    assert domain(core) == before
    payload["evidence"]["action_id"] = "action"
    result = executor.call("observe_attempt", payload, "correct-action")
    assert not result.get("verified", False)
    core.backup(owner.token, tmp_path / "backup")
    restored, token = Core.restore_quarantined(tmp_path / "backup", tmp_path / "restored")
    assert restored.connect(token).call("export_diagnostics", {}, "diag")["mode"] == "quarantined"
