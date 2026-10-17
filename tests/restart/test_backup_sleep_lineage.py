"""Mixed Sleep generations retain exact attribution through verified late links."""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app import Coordinator, Driver, Sleep
from zaratustra_core import Core, CoreError

from .sleep_support import PROFILE, MechanicalSleepReceiver, seed
from .test_backup_references import rehash


def lineage(root: Path, complete: bool = False) -> tuple[Core, Any, dict[str, Any], dict[str, Any]]:
    core, owner, client = seed(root)
    sleep = Sleep(client)
    sleep.start(work_id="parent", portion=100)
    receiver = (
        MechanicalSleepReceiver()
        if complete
        else (
            lambda _context, _action: b'{"state":"completed","text":"Unexamined sources retained"}'
        )
    )
    sleep.run("parent", PROFILE, Driver(receiver))
    predecessor = sleep.progress("parent")
    coordinator = Coordinator(owner)
    parent = coordinator.rows("works", work="parent")[0]
    result = coordinator.rows("results", work="parent")[0]
    attempt = coordinator.rows("attempts", work="parent")[-1]
    original_result = dict(result)
    original_pin = attempt["body"]
    core.prepare_update(owner.token, root / "internal-pre-update")
    basis = {
        "id": predecessor["id"],
        "revision": predecessor["revision"],
        "role": "must_be_current",
    }
    method = json.loads(parent["body"])["method_ref"]
    child = {
        "id": "child",
        "conversation": parent["conversation"],
        "goal": "Sleep",
        "scope": "space",
        "method_ref": method,
        "inputs": [],
        "call_limit": None,
        "continuation_policy": "durable",
        "continuation_from": {
            "attempt_id": attempt["id"],
            "result_hash": result["fingerprint"],
            "work_revision": parent["revision"],
            "basis_refs": [basis],
        },
    }
    admitted = owner.call("open_work", child, "late-child")
    assert admitted["continuation"]["result_hash"] == result["fingerprint"]
    body = copy.deepcopy(predecessor["body"]["value"])
    body.update(
        format="sleep-progress/v2",
        work_id="child",
        predecessor_ref=basis | {"role": "exact"},
        transition="new_window" if complete else "same_window",
        range_start=[0, 0],
        delivered_manifest_refs=[],
        analysis_result_refs=[],
        applied_receipts=[],
        consumed_resource=0,
        unresolved_calls=[],
        stop_reason="not_started",
    )
    if complete:
        old_high = body["source_high_watermark"]
        history = owner.call(
            "read_history",
            {"after_sequence": old_high, "after_index": 2147483647, "limit": 100},
            "new-window-history",
        )
        refs = [item["source_ref"] for item in history["sources"]]
        body.update(
            range_start=[old_high, 2147483647],
            source_high_watermark=history["high_watermark"],
            enumeration_cursor=history["cursor"],
            enumerated_source_refs=refs,
            selected_source_refs=refs,
            remaining_refs=refs,
        )
    change = {"id": "child-progress", "kind": "data", "key": "sleep-progress:child", "body": body}
    owner.call(
        "apply_changes",
        {"changes": [change]},
        "child-progress",
        expected_heads={"child-progress": 0},
    )
    Sleep(owner)._bind_progress("child", {"id": "child-progress", "revision": 1})
    assert coordinator.rows("results", work="parent")[0] == original_result
    assert coordinator.rows("attempts", work="parent")[-1]["body"] == original_pin
    assert (
        owner.call(
            "read_exact",
            {"id": predecessor["id"], "revision": predecessor["revision"]},
            "unchanged-predecessor",
        )
        == predecessor
    )
    return core, owner, body, predecessor


@pytest.mark.parametrize("complete", [False, True])
def test_mixed_v1_v2_late_history_passes_backup_and_update(tmp_path: Path, complete: bool) -> None:
    core, owner, progress, predecessor = lineage(tmp_path, complete)
    assert progress["delivered_manifest_refs"] == progress["analysis_result_refs"] == []
    assert (
        progress["unexplored_coverage_position"]
        == predecessor["body"]["value"]["unexplored_coverage_position"]
    )
    core.backup(owner.token, tmp_path / "mixed-backup")
    assert core.prepare_update(owner.token, tmp_path / "mixed-pre-update")["status"] == "compatible"
    restored, token = Core.restore_quarantined(tmp_path / "mixed-backup", tmp_path / "restored")
    assert (
        restored.connect(token).call(
            "read_exact", {"id": "child-progress", "revision": 1}, "exact-child"
        )["body"]["value"]
        == progress
    )


@pytest.mark.parametrize(
    "damage",
    [
        "result_hash",
        "parent_revision",
        "basis_revision",
        "late_receipt",
        "fork",
        "cycle",
        "predecessor",
        "wrong_scope",
        "cutoff",
        "cursor",
        "source_sha",
        "drop_remainder",
        "foreign_delivery",
        "foreign_receipt",
        "new_window_unfinished",
        "marker_zero",
        "child_budget_zero",
    ],
)
def test_rehashed_late_lineage_or_inherited_proof_corruption_is_rejected(
    tmp_path: Path, damage: str
) -> None:
    core, owner, _, predecessor = lineage(tmp_path)
    backup = tmp_path / "backup"
    core.backup(owner.token, backup)
    with sqlite3.connect(backup / "core.sqlite3") as db:
        child = json.loads(db.execute("SELECT body FROM works WHERE id='child'").fetchone()[0])
        wrapper = json.loads(
            db.execute("SELECT body FROM records WHERE id='child-progress'").fetchone()[0]
        )
        progress = wrapper["value"]
        link = child["continuation"]
        if damage == "result_hash":
            link["result_hash"] = "0" * 64
        elif damage == "parent_revision":
            link["parent_work_revision"] = True
        elif damage == "basis_revision":
            link["basis_refs"][0]["revision"] = 1
            progress["predecessor_ref"]["revision"] = 1
        elif damage == "late_receipt":
            link["receipt_id"] = "missing"
        elif damage == "fork":
            fork = dict(child, id="fork")
            db.execute(
                "INSERT INTO works VALUES('fork',1,?,'ready',1,?,0)",
                (child["conversation"], json.dumps(fork)),
            )
        elif damage == "cycle":
            parent = json.loads(
                db.execute("SELECT body FROM works WHERE id='parent'").fetchone()[0]
            )
            parent["continuation"] = dict(link)
            db.execute("UPDATE works SET body=? WHERE id='parent'", (json.dumps(parent),))
        elif damage == "predecessor":
            progress["predecessor_ref"]["id"] = "missing"
        elif damage == "wrong_scope":
            progress["scope"] = "foreign"
        elif damage == "cutoff":
            progress["source_high_watermark"] += 1
        elif damage == "cursor":
            progress["enumeration_cursor"] = [0, 0]
        elif damage == "source_sha":
            progress["enumerated_source_refs"][0]["sha256"] = "0" * 64
        elif damage == "drop_remainder":
            progress["remaining_refs"] = []
        elif damage == "foreign_delivery":
            progress["delivered_manifest_refs"] = predecessor["body"]["value"][
                "delivered_manifest_refs"
            ]
        elif damage == "foreign_receipt":
            progress["applied_receipts"] = ["late-child"]
        elif damage == "new_window_unfinished":
            progress["transition"] = "new_window"
            progress["range_start"] = [progress["source_high_watermark"], 2147483647]
        elif damage == "child_budget_zero":
            child["call_limit"] = 0
        else:
            db.execute("PRAGMA user_version=0")
        db.execute("UPDATE works SET body=? WHERE id='child'", (json.dumps(child),))
        db.execute("UPDATE records SET body=? WHERE id='child-progress'", (json.dumps(wrapper),))
        if damage in {"result_hash", "parent_revision", "basis_revision"}:
            response = json.loads(
                db.execute("SELECT response FROM receipts WHERE command='late-child'").fetchone()[0]
            )
            response["result"]["continuation"] = link
            db.execute(
                "UPDATE receipts SET response=? WHERE command='late-child'", (json.dumps(response),)
            )
            db.execute(
                "UPDATE events SET body=? WHERE subject='late-child'",
                (json.dumps(response["result"]),),
            )
    rehash(backup)
    with pytest.raises(CoreError):
        Core.restore_quarantined(backup, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


@pytest.mark.parametrize(
    "family", ["delivered_manifest_refs", "analysis_result_refs", "applied_receipts"]
)
def test_valid_parent_evidence_cannot_be_relabelled_as_child_owned(
    tmp_path: Path, family: str
) -> None:
    core, owner, _, predecessor = lineage(tmp_path, complete=True)
    evidence = predecessor["body"]["value"][family]
    assert evidence
    backup = tmp_path / "backup"
    core.backup(owner.token, backup)
    with sqlite3.connect(backup / "core.sqlite3") as db:
        wrapper = json.loads(
            db.execute("SELECT body FROM records WHERE id='child-progress'").fetchone()[0]
        )
        wrapper["value"][family] = evidence
        db.execute("UPDATE records SET body=? WHERE id='child-progress'", (json.dumps(wrapper),))
    rehash(backup)
    with pytest.raises(CoreError, match="backup.reference_closure"):
        Core.restore_quarantined(backup, tmp_path / "restored")
