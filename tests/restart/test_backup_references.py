"""Rehashed corruption must not break the retained typed reference graph."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app import Coordinator, Driver, Sleep
from zaratustra_core import Core, CoreError

from .sleep_support import PROFILE as SLEEP_PROFILE
from .sleep_support import MechanicalSleepReceiver, seed
from .support import PROFILE, Receiver, fixture
from .test_contract import prepared


def rehash(backup: Path) -> None:
    raw = (backup / "core.sqlite3").read_bytes()
    manifest = json.loads((backup / "manifest.json").read_bytes())
    manifest.update(database_sha256=hashlib.sha256(raw).hexdigest(), database_size=len(raw))
    (backup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_pinned_json_boolean_is_not_integer(tmp_path: Path) -> None:
    core, owner, executor = fixture(tmp_path)
    old = owner.call("read_exact", PROFILE, "profile")
    owner.call(
        "apply_changes",
        {
            "changes": [
                {"id": "profile", "kind": "profile", "key": old["key"], "body": {"flag": True}}
            ]
        },
        "advance",
        expected_heads={"profile": 1},
    )
    Coordinator(executor).prepare("work", "A1", {"id": "profile", "revision": 2})
    core.backup(owner.token, tmp_path / "backup")
    with sqlite3.connect(tmp_path / "backup/core.sqlite3") as db:
        body = json.loads(db.execute("SELECT body FROM attempts").fetchone()[0])
        body["profile"]["body"]["value"]["flag"] = 1
        db.execute("UPDATE attempts SET body=?", (json.dumps(body),))
    rehash(tmp_path / "backup")
    with pytest.raises(CoreError, match="backup.reference_closure"):
        Core.restore_quarantined(tmp_path / "backup", tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


@pytest.mark.parametrize(
    "damage",
    [
        "profile_ref",
        "wrong_profile_ref",
        "method",
        "method_bytes",
        "profile",
        "inputs",
        "catalog",
        "work_method",
        "work_inputs",
        "manifest_sequence",
        "manifest_hash",
        "message_bytes",
        "message_range",
        "receipt_result",
        "result_ref",
    ],
)
def test_rehashed_pinned_reference_corruption_refused(tmp_path: Path, damage: str) -> None:
    core, owner, _, _ = prepared(tmp_path)
    backup = tmp_path / "backup"
    core.backup(owner.token, backup)
    with sqlite3.connect(backup / "core.sqlite3") as db:
        body = json.loads(db.execute("SELECT body FROM attempts").fetchone()[0])
        if damage == "profile_ref":
            body["profile_ref"] = {"id": "missing", "revision": 999}
        elif damage == "wrong_profile_ref":
            body["profile_ref"] = {"id": "method", "revision": 1}
        elif damage in {"method", "profile", "inputs", "catalog"}:
            item = body[damage][0] if isinstance(body[damage], list) else body[damage]
            item["id"], item["revision"] = "missing", 999
        elif damage == "method_bytes":
            body["method"]["body"]["value"] = "changed pinned bytes"
        elif damage == "work_method":
            body["work"]["method_ref"] = {"id": "missing", "revision": 999}
        elif damage == "work_inputs":
            body["work"]["inputs"] = [{"id": "missing", "revision": 999}]
        elif damage == "manifest_sequence":
            body["manifest"][0]["sequence"] = 999
        elif damage == "manifest_hash":
            body["manifest"][0]["sha256"] = "0" * 64
        elif damage == "message_bytes":
            body["messages"][0]["raw"] = base64.b64encode(b"different input").decode()
        elif damage == "message_range":
            body["messages"] = body["messages"][1:]
        elif damage == "receipt_result":
            receipt = db.execute("SELECT command,response FROM receipts LIMIT 1").fetchone()
            response = json.loads(receipt[1])
            response["result"] = {"different": "saved result"}
            db.execute(
                "UPDATE receipts SET response=? WHERE command=?", (json.dumps(response), receipt[0])
            )
        else:
            event = db.execute(
                "SELECT seq,body FROM events WHERE kind='apply_changes' LIMIT 1"
            ).fetchone()
            result = json.loads(event[1])
            result["refs"] = [{"id": "missing", "revision": 999}]
            db.execute("UPDATE events SET body=? WHERE seq=?", (json.dumps(result), event[0]))
        db.execute("UPDATE attempts SET body=?", (json.dumps(body),))
    rehash(backup)
    with pytest.raises(CoreError, match="backup.*closure"):
        Core.restore_quarantined(backup, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_historical_pins_remain_restorable(tmp_path: Path) -> None:
    core, owner, _, _ = prepared(tmp_path)
    changes: list[dict[str, Any]] = [
        {"id": "method", "kind": "method", "key": "conversation", "body": "new method"},
        {"id": "profile", "kind": "profile", "key": "local", "body": "new profile"},
    ]
    # Preserve established identities, while advancing heads beyond the pinned versions.
    for change in changes:
        old = owner.call("read_exact", {"id": change["id"], "revision": 1}, "old-" + change["id"])
        change["key"] = old["key"]
        owner.call(
            "apply_changes",
            {"changes": [change]},
            "advance-" + change["id"],
            expected_heads={change["id"]: 1},
        )
    core.backup(owner.token, tmp_path / "backup")
    restored, token = Core.restore_quarantined(tmp_path / "backup", tmp_path / "restored")
    snapshot = restored.connect(token).call("read_snapshot", {}, "history")
    assert snapshot["attempts"][0]["status"] == "fenced"
    pinned = json.loads(snapshot["attempts"][0]["body"])
    assert pinned["method"]["revision"] == pinned["profile"]["revision"] == 1


@pytest.mark.parametrize(
    "damage",
    [
        None,
        "prior_messages",
        "prior_results",
        "prior_waits",
        "tool_ledger",
        "result_outputs",
        "observation_identity",
        "intent",
        "acceptance",
    ],
)
def test_continued_context_reference_graph(tmp_path: Path, damage: str | None) -> None:
    core, owner, _, coordinator = prepared(tmp_path)
    coordinator.dispatch("A1", 1, Driver(Receiver()))
    coordinator.recover("A1")
    with sqlite3.connect(core.path) as db:
        fingerprint = db.execute("SELECT fingerprint FROM results WHERE attempt='A1'").fetchone()[0]
    core.accept_result(owner.token, "A1", fingerprint)
    owner.call(
        "ingest_message",
        {
            "conversation": "conversation",
            "event_id": "answer",
            "raw_base64": "eA==",
            "reply_to": {"id": "W7", "revision": 1},
        },
        "answer",
    )
    coordinator.prepare("work", "A2", PROFILE)
    core.backup(owner.token, tmp_path / "backup")
    if damage:
        with sqlite3.connect(tmp_path / "backup/core.sqlite3") as db:
            body = json.loads(db.execute("SELECT body FROM attempts WHERE id='A2'").fetchone()[0])
            if damage == "prior_messages":
                body[damage][0]["raw"] = "eA=="
            elif damage == "prior_results":
                body[damage][0]["attempt"] = "missing"
            elif damage == "prior_waits":
                body[damage][0]["id"] = "missing"
            elif damage == "tool_ledger":
                body[damage][0]["command"] = "missing"
            elif damage == "result_outputs":
                result = json.loads(db.execute("SELECT body FROM results LIMIT 1").fetchone()[0])
                result["outputs"] = [{"id": "missing", "revision": 999}]
                db.execute("UPDATE results SET body=?", (json.dumps(result),))
            elif damage == "observation_identity":
                result = json.loads(
                    db.execute("SELECT body FROM observations LIMIT 1").fetchone()[0]
                )
                result["attempt_id"] = "missing"
                db.execute("UPDATE observations SET body=?", (json.dumps(result),))
            elif damage == "intent":
                db.execute("UPDATE intents SET subject='missing'")
            else:
                db.execute("UPDATE acceptance SET result_hash=?", ("0" * 64,))
            db.execute("UPDATE attempts SET body=? WHERE id='A2'", (json.dumps(body),))
        rehash(tmp_path / "backup")
        with pytest.raises(CoreError, match="backup.*closure"):
            Core.restore_quarantined(tmp_path / "backup", tmp_path / "restored")
        assert not (tmp_path / "restored").exists()
    else:
        restored, token = Core.restore_quarantined(tmp_path / "backup", tmp_path / "restored")
        assert (
            restored.connect(token).call("export_diagnostics", {}, "diag")["mode"] == "quarantined"
        )


@pytest.mark.parametrize(
    "damage",
    [
        None,
        "method_ref",
        "analysis_result_refs",
        "selected_source_refs",
        "delivered_manifest_refs",
        "applied_receipts",
        "unresolved_calls",
        "wrong_delivery",
        "wrong_receipt",
        "wrong_action",
    ],
)
def test_sleep_reference_graph(tmp_path: Path, damage: str | None) -> None:
    core, owner, client = seed(tmp_path)
    owner.call(
        "open_work",
        {
            "id": "other",
            "conversation": "other",
            "goal": "other lineage",
            "method_ref": {"id": "practice", "revision": 1},
            "inputs": [],
            "call_limit": 2,
            "continuation_policy": "durable",
        },
        "other-open",
    )
    Coordinator(client).prepare("other", "other-attempt", SLEEP_PROFILE)
    client.call(
        "claim_dispatch",
        {"attempt_id": "other-attempt", "generation": 1},
        "other-claim",
        action_id="other-action",
    )
    sleep = Sleep(client)
    sleep.start(work_id="sleep", call_limit=4, portion=100)
    sleep.run("sleep", SLEEP_PROFILE, Driver(MechanicalSleepReceiver()))
    core.backup(owner.token, tmp_path / "backup")
    if damage:
        with sqlite3.connect(tmp_path / "backup/core.sqlite3") as db:
            row = db.execute(
                "SELECT id,revision,body FROM records WHERE key='sleep-progress:sleep' "
                "ORDER BY revision DESC LIMIT 1"
            ).fetchone()
            wrapper = json.loads(row[2])
            value = wrapper["value"]
            if damage == "method_ref":
                value[damage] = {"id": "missing", "revision": 999}
            elif damage == "analysis_result_refs":
                value[damage] = [{"id": "missing", "revision": 999}]
            elif damage == "selected_source_refs":
                value[damage] = [{"sequence": 999999, "index": 0, "sha256": "0" * 64}]
            elif damage == "delivered_manifest_refs":
                value[damage] = [{"attempt_id": "missing", "sha256": "0" * 64}]
            elif damage == "wrong_delivery":
                value["delivered_manifest_refs"] = [
                    {"attempt_id": "other-attempt", "sha256": hashlib.sha256(b"[]").hexdigest()}
                ]
            elif damage == "wrong_receipt":
                value["applied_receipts"] = ["other-open"]
            elif damage == "wrong_action":
                value["unresolved_calls"] = ["other-action"]
            else:
                value[damage] = ["missing"]
            db.execute(
                "UPDATE records SET body=? WHERE id=? AND revision=?",
                (json.dumps(wrapper), row[0], row[1]),
            )
        rehash(tmp_path / "backup")
        with pytest.raises(CoreError, match="backup.*closure"):
            Core.restore_quarantined(tmp_path / "backup", tmp_path / "restored")
        assert not (tmp_path / "restored").exists()
    else:
        restored, token = Core.restore_quarantined(tmp_path / "backup", tmp_path / "restored")
        assert (
            restored.connect(token).call("export_diagnostics", {}, "diag")["mode"] == "quarantined"
        )
