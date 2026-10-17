"""Historical explicit context selections remain exact and backup-compatible."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app import Coordinator, Driver
from zaratustra_core import Core, CoreError

from .support import PROFILE, Receiver, fixture, ingest
from .test_backup_references import rehash


def selected_history(root: Path, empty: bool = False) -> tuple[Core, Any, dict[str, Any]]:
    core, owner, executor = fixture(root)
    coordinator = Coordinator(executor)
    coordinator.prepare("work", "A1", PROFILE)
    coordinator.dispatch("A1", 1, Driver(Receiver()))
    coordinator.recover("A1")
    ingest(owner, "reply", "Exact addressed reply", {"id": "W7", "revision": 1})
    coordinator.prepare("work", "A2", PROFILE)
    second = Driver(lambda _context, _action: b'{"state":"ready","text":"Second retained portion"}')
    second.resource_upper = 1
    coordinator.dispatch("A2", 1, second)
    coordinator.recover("A2")
    ingest(owner, "next", "Exact mandatory current input")
    selection = (
        {}
        if empty
        else {
            "catalog_refs": [{"id": "memory", "revision": 1}, {"id": "method", "revision": 1}],
            "prior_message_sequences": [3, 1],
            "prior_result_attempts": ["A2", "A1"],
            "prior_wait_ids": ["W7"],
        }
    )
    pinned = coordinator.prepare("work", "A3", PROFILE, context_selection=selection)["pinned"]
    return core, owner, pinned


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("operation", ["backup", "prepare_update"])
def test_public_update_and_backup_accept_exact_explicit_prior_selection(
    tmp_path: Path, empty: bool, operation: str
) -> None:
    core, owner, pinned = selected_history(tmp_path / "data", empty)
    assert len(pinned["messages"]) == 1
    assert pinned["messages"][0]["seq"] == 22
    assert pinned["inputs"][0]["body"]["value"] == "Keep practice brief."
    destination = tmp_path / "backup"
    original_bytes = core.path.read_bytes()
    if operation == "backup":
        core.backup(owner.token, destination)
    else:
        assert core.prepare_update(owner.token, destination)["status"] == "compatible"
    restored, token = Core.restore_quarantined(destination, tmp_path / "restored")
    saved = Coordinator(restored.connect(token)).rows("attempts", work="work")
    assert json.loads(next(row for row in saved if row["id"] == "A3")["body"]) == pinned
    assert core.path.read_bytes() == original_bytes


def test_historical_catalog_and_counts_survive_later_heads(tmp_path: Path) -> None:
    core, owner, pinned = selected_history(tmp_path / "data")
    owner.call(
        "apply_changes",
        {
            "changes": [
                {"id": "memory", "kind": "memory", "key": "preference", "body": "Later memory"},
                {"id": "later", "kind": "data", "key": "later", "body": "Later catalog entry"},
            ]
        },
        "later-heads",
        expected_heads={"memory": 1, "later": 0},
    )
    coordinator = Coordinator(owner)
    # The stale mandatory memory stops a claim until explicit refresh; this does
    # not invalidate the historically valid preparation or its frozen coverage.
    core.prepare_update(owner.token, tmp_path / "backup")
    restored, token = Core.restore_quarantined(tmp_path / "backup", tmp_path / "restored")
    saved = Coordinator(restored.connect(token)).rows("attempts", work="work")
    assert json.loads(next(row for row in saved if row["id"] == "A3")["body"]) == pinned
    assert coordinator.rows("heads")[-1]["id"] == "later"


def test_selected_wait_snapshot_remains_valid_after_addressed_reply(tmp_path: Path) -> None:
    core, owner, executor = fixture(tmp_path / "data")
    coordinator = Coordinator(executor)
    coordinator.prepare("work", "A1", PROFILE)
    coordinator.dispatch("A1", 1, Driver(Receiver()))
    coordinator.recover("A1")
    owner.call(
        "open_work",
        {
            "id": "other",
            "conversation": "conversation",
            "goal": "Exact other work",
            "method_ref": {"id": "method", "revision": 1},
            "inputs": [],
            "call_limit": 2,
            "continuation_policy": "durable",
        },
        "other-open",
    )
    saved = coordinator.prepare(
        "other", "other-attempt", PROFILE, context_selection={"prior_wait_ids": ["W7"]}
    )["pinned"]
    assert saved["prior_waits"][0]["revision"] == 1
    terminal = Driver(lambda _context, _action: b'{"state":"completed","text":"Exact empty turn"}')
    terminal.resource_upper = 1
    coordinator.dispatch("other-attempt", 1, terminal)
    coordinator.recover("other-attempt")
    ingest(owner, "answer", "Exact addressed reply", {"id": "W7", "revision": 1})
    assert coordinator.rows("waits")[0]["revision"] == 2
    core.backup(owner.token, tmp_path / "backup")


def rewrite_pin(db: sqlite3.Connection, pinned: dict[str, Any]) -> None:
    """Keep event/receipt alignment so deeper structural guards must reject damage."""
    db.execute("UPDATE attempts SET body=? WHERE id='A3'", (json.dumps(pinned),))
    for seq, subject, text in db.execute(
        "SELECT seq,subject,body FROM events WHERE kind='prepare_attempt'"
    ).fetchall():
        result = json.loads(text)
        if result["attempt_id"] != "A3":
            continue
        result["pinned"] = pinned
        db.execute("UPDATE events SET body=? WHERE seq=?", (json.dumps(result), seq))
        response = json.loads(
            db.execute("SELECT response FROM receipts WHERE command=?", (subject,)).fetchone()[0]
        )
        response["result"] = result
        db.execute(
            "UPDATE receipts SET response=? WHERE command=?", (json.dumps(response), subject)
        )


@pytest.mark.parametrize(
    "damage",
    [
        "missing_message",
        "undeclared_message",
        "missing_sequence",
        "duplicate_sequence",
        "forged_message",
        "future_message",
        "wrong_conversation",
        "message_order",
        "catalog_order",
        "catalog_declaration",
        "catalog_missing",
        "catalog_duplicate",
        "catalog_type",
        "missing_result",
        "result_order",
        "result_declaration",
        "result_duplicate",
        "result_foreign",
        "wait_declaration",
        "wait_duplicate",
        "wait_foreign",
        "forged_wait",
        "missing_coverage",
        "mode",
        "count",
        "count_boolean",
        "total_count",
        "selection_boolean",
        "mandatory_current",
        "mandatory_memory",
    ],
)
def test_coherently_rehashed_selected_context_corruption_is_rejected(
    tmp_path: Path, damage: str
) -> None:
    core, owner, _ = selected_history(tmp_path / "data")
    foreign_results: list[dict[str, Any]] = []
    foreign_waits: list[dict[str, Any]] = []
    if damage in {"result_foreign", "wait_foreign"}:
        coordinator = Coordinator(owner)
        owner.call(
            "open_work",
            {
                "id": "foreign-work",
                "conversation": "foreign",
                "goal": "Foreign work",
                "method_ref": {"id": "method", "revision": 1},
                "inputs": [],
                "call_limit": 2,
                "continuation_policy": "durable",
            },
            "foreign-open",
        )
        coordinator.prepare("foreign-work", "foreign-attempt", PROFILE)
        terminal = Driver(
            lambda _context, _action: (
                b'{"state":"waiting","text":"Foreign question",'
                b'"wait":{"id":"foreign-wait","question":"Foreign?"}}'
            )
        )
        terminal.resource_upper = 1
        coordinator.dispatch("foreign-attempt", 1, terminal)
        coordinator.recover("foreign-attempt")
        foreign_results = coordinator.rows("results", work="foreign-work")
        foreign_waits = coordinator.rows("waits", work="foreign-work")
    backup = tmp_path / "backup"
    core.backup(owner.token, backup)
    with sqlite3.connect(backup / "core.sqlite3") as db:
        pinned = json.loads(db.execute("SELECT body FROM attempts WHERE id='A3'").fetchone()[0])
        coverage = pinned["context_coverage"]
        if damage == "missing_message":
            pinned["prior_messages"].pop()
        elif damage == "undeclared_message":
            pinned["prior_messages"].append(pinned["prior_messages"][0])
            coverage["selected_rows"]["prior_messages"] += 1
        elif damage == "missing_sequence":
            coverage["selection"]["prior_message_sequences"] = [999]
        elif damage == "duplicate_sequence":
            coverage["selection"]["prior_message_sequences"] = [3, 3]
            pinned["prior_messages"][1] = pinned["prior_messages"][0]
        elif damage == "forged_message":
            pinned["prior_messages"][0]["raw"] = "Zm9yZ2Vk"
        elif damage == "future_message":
            coverage["selection"]["prior_message_sequences"] = [22]
            pinned["prior_messages"] = list(pinned["messages"])
            coverage["selected_rows"]["prior_messages"] = 1
        elif damage == "wrong_conversation":
            pinned["prior_messages"][0]["conversation"] = "other"
        elif damage == "message_order":
            pinned["prior_messages"].reverse()
        elif damage == "catalog_order":
            pinned["catalog"].reverse()
        elif damage == "catalog_declaration":
            coverage["selection"]["catalog_refs"].reverse()
        elif damage == "catalog_missing":
            coverage["selection"]["catalog_refs"][0]["id"] = "missing"
        elif damage == "catalog_duplicate":
            coverage["selection"]["catalog_refs"][1] = coverage["selection"]["catalog_refs"][0]
            pinned["catalog"][1] = pinned["catalog"][0]
        elif damage == "catalog_type":
            coverage["selection"]["catalog_refs"][0]["revision"] = True
        elif damage == "missing_result":
            pinned["prior_results"].pop()
        elif damage == "result_order":
            pinned["prior_results"].reverse()
        elif damage == "result_declaration":
            coverage["selection"]["prior_result_attempts"] = ["A3"]
        elif damage == "result_duplicate":
            coverage["selection"]["prior_result_attempts"] = ["A1", "A1"]
        elif damage == "result_foreign":
            coverage["selection"]["prior_result_attempts"] = ["foreign-attempt"]
            pinned["prior_results"] = foreign_results
            coverage["selected_rows"]["prior_results"] = len(foreign_results)
        elif damage == "wait_declaration":
            coverage["selection"]["prior_wait_ids"] = []
        elif damage == "wait_duplicate":
            coverage["selection"]["prior_wait_ids"] = ["W7", "W7"]
        elif damage == "wait_foreign":
            coverage["selection"]["prior_wait_ids"] = ["foreign-wait"]
            pinned["prior_waits"] = foreign_waits
        elif damage == "forged_wait":
            pinned["prior_waits"][0]["body"] = "{}"
        elif damage == "missing_coverage":
            pinned.pop("context_coverage")
        elif damage == "mode":
            coverage["mode"] = "automatic"
        elif damage == "count":
            coverage["selected_rows"]["catalog"] += 1
        elif damage == "count_boolean":
            coverage["selected_rows"]["prior_waits"] = True
        elif damage == "total_count":
            coverage["total_rows"]["catalog"] += 1
        elif damage == "selection_boolean":
            coverage["selection"]["prior_message_sequences"] = [True]
        elif damage == "mandatory_current":
            pinned["messages"] = []
        else:
            pinned["inputs"] = []
        rewrite_pin(db, pinned)
    rehash(backup)
    with pytest.raises(CoreError, match="backup.reference_closure"):
        Core.restore_quarantined(backup, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()
