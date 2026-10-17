"""Permanent-use compatibility and two-root single-active-instance protocol."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
import zaratustra_core
from zaratustra_core import Core, CoreError

from .support import inspect
from .test_contract import prepared


def setup_restore(tmp_path: Path) -> tuple[Core, str, Core, str]:
    source, token = Core.initialize(tmp_path / "source")
    source.connect(token).call(
        "apply_changes",
        {
            "changes": [
                {"id": "activity", "key": "kept", "kind": "activity", "body": "Owner content"}
            ]
        },
        "record",
        expected_heads={"activity": 0},
    )
    source.backup(token, tmp_path / "backup")
    restored, new_token = Core.restore_quarantined(tmp_path / "backup", tmp_path / "restored")
    return source, token, restored, new_token


def rows(core: Core, table: str) -> list[dict[str, Any]]:
    with sqlite3.connect(core.path) as db:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute("SELECT * FROM " + table)]


def test_update_preserves_exact_domain_and_identifiers(tmp_path: Path) -> None:
    source, token, _, _ = setup_restore(tmp_path)
    before = {
        table: rows(source, table) for table in ("records", "meta", "events", "receipts", "heads")
    }
    report = source.prepare_update(token, tmp_path / "pre-update")
    assert report["status"] == "compatible"
    assert report["compatibility"]["schema"] == "restart/v1"
    assert before == {table: rows(source, table) for table in before}
    reopened = Core(source.root).connect(token)
    assert (
        reopened.call("read_exact", {"id": "activity", "revision": 1}, "exact")["body"]["value"]
        == "Owner content"
    )
    assert (
        json.loads((tmp_path / "pre-update" / "manifest.json").read_text())["compatibility"]
        == report["compatibility"]
    )


@pytest.mark.parametrize("mutation", ["PRAGMA user_version=999", "CREATE TABLE alien(value TEXT)"])
def test_unknown_schema_fails_before_backup_or_data_change(tmp_path: Path, mutation: str) -> None:
    source, token = Core.initialize(tmp_path / "source")
    with sqlite3.connect(source.path) as db:
        db.execute(mutation)
    before = source.path.read_bytes()
    with pytest.raises(CoreError, match="maintenance.schema"):
        source.prepare_update(token, tmp_path / "not-created")
    with pytest.raises(CoreError, match="maintenance.schema"):
        Core(source.root)
    assert source.path.read_bytes() == before
    assert not (tmp_path / "not-created").exists()


def test_activation_retires_old_clients_and_replay_keeps_single_event(tmp_path: Path) -> None:
    source, token, restored, new_token = setup_restore(tmp_path)
    old_client = source.connect(token)
    evidence = restored.activate_restored(new_token, source, token)
    assert evidence["status"] == "active"
    assert rows(source, "lifecycle") == [{"mode": "retired"}]
    assert rows(restored, "lifecycle") == [{"mode": "active"}]
    assert restored.activate_restored(new_token, Core(source.root), token) == evidence
    assert len([e for e in rows(restored, "events") if e["kind"] == "restore_activated"]) == 1
    assert rows(source, "meta")[0]["epoch"] == evidence["source"]["epoch"] + 1
    with pytest.raises(CoreError):
        old_client.call(
            "ingest_message",
            {"conversation": "chat", "event_id": "e", "raw_base64": "c3RhbGU="},
            "old",
        )
    with pytest.raises(CoreError, match="quarantined"):
        source.grant(token, "rogue", ["*"])
    with pytest.raises(CoreError, match="quarantined"):
        source.revoke(token, "owner")
    restored.connect(new_token).call(
        "ingest_message", {"conversation": "chat", "event_id": "e", "raw_base64": "bmV3"}, "new"
    )
    restored.backup(new_token, tmp_path / "activated-backup")


def test_other_instance_and_wrong_credentials_leave_both_unchanged(tmp_path: Path) -> None:
    source, token, restored, new_token = setup_restore(tmp_path)
    other, other_token = Core.initialize(tmp_path / "other")
    with pytest.raises(CoreError, match="restore.source"):
        restored.activate_restored(new_token, other, other_token)
    with pytest.raises(CoreError, match="credential"):
        restored.activate_restored(new_token, source, "not-owner")
    assert rows(source, "lifecycle") == rows(other, "lifecycle") == [{"mode": "active"}]
    assert rows(restored, "lifecycle") == [{"mode": "quarantined"}]
    with pytest.raises(CoreError, match="wrong_instance"):
        restored.activate_restored(new_token, Core(tmp_path / "absent"), token)


def test_competing_restores_cannot_both_activate(tmp_path: Path) -> None:
    source, token, first, first_token = setup_restore(tmp_path)
    second, second_token = Core.restore_quarantined(tmp_path / "backup", tmp_path / "second")

    def run(core: Core, credential: str) -> str:
        try:
            core.activate_restored(credential, source, token)
            return "active"
        except CoreError:
            return "denied"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda pair: run(*pair), [(first, first_token), (second, second_token)])
        )
    assert sorted(results) == ["active", "denied"]
    assert sorted([rows(first, "lifecycle")[0]["mode"], rows(second, "lifecycle")[0]["mode"]]) == [
        "active",
        "quarantined",
    ]


@pytest.mark.parametrize("phase", ["restore_retired", "restore_activated"])
def test_process_crash_before_and_after_retirement_recovers(tmp_path: Path, phase: str) -> None:
    source, token, restored, new_token = setup_restore(tmp_path)
    script = """import os,sys
sys.path.insert(0,sys.argv[1])
from pathlib import Path
from zaratustra_core import Core
from zaratustra_core import lifecycle
original=lifecycle.event
def crash(db,kind,subject,body):
    if kind == sys.argv[6]: os._exit(91)
    original(db,kind,subject,body)
lifecycle.event=crash
Core(Path(sys.argv[2])).activate_restored(sys.argv[3],Core(Path(sys.argv[4])),sys.argv[5])
"""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            script,
            str(Path(zaratustra_core.__file__).parents[1]),
            str(restored.root),
            new_token,
            str(source.root),
            token,
            phase,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert result.returncode == 91, result.stderr
    assert rows(restored, "lifecycle") == [{"mode": "quarantined"}]
    assert rows(source, "lifecycle") == [
        {"mode": "active" if phase == "restore_retired" else "retired"}
    ]
    Core(restored.root).activate_restored(new_token, Core(source.root), token)
    assert rows(restored, "lifecycle") == [{"mode": "active"}]
    assert rows(source, "lifecycle") == [{"mode": "retired"}]


def test_unknown_external_effect_remains_a_resume_fence(tmp_path: Path) -> None:
    source, owner, executor, _ = prepared(tmp_path)
    executor.call(
        "claim_dispatch",
        {"attempt_id": "A1", "generation": 1},
        "claim",
        action_id="external-action",
    )
    executor.call(
        "observe_attempt", {"attempt_id": "A1", "event_id": "unknown", "kind": "unknown"}, "unknown"
    )
    source.backup(owner.token, tmp_path / "backup")
    restored, token = Core.restore_quarantined(tmp_path / "backup", tmp_path / "restored")
    restored.activate_restored(token, source, owner.token)
    assert inspect(restored, "attempts")[0]["status"] == "fenced"
    assert inspect(restored, "actions")[0]["state"] == "claimed"
    with pytest.raises(CoreError, match="outcome_unknown"):
        restored.connect(token).call(
            "control_work",
            {
                "work_id": "work",
                "revision": rows(restored, "works")[0]["revision"],
                "action": "resume",
            },
            "resume",
        )


def test_dispatch_after_backup_blocks_activation(tmp_path: Path) -> None:
    source, owner, executor, _ = prepared(tmp_path)
    source.backup(owner.token, tmp_path / "backup")
    executor.call(
        "claim_dispatch", {"attempt_id": "A1", "generation": 1}, "claim", action_id="late-action"
    )
    restored, token = Core.restore_quarantined(tmp_path / "backup", tmp_path / "restored")
    with pytest.raises(CoreError, match="restore.source_effects"):
        restored.activate_restored(token, source, owner.token)
    assert rows(source, "lifecycle") == [{"mode": "active"}]
    assert rows(restored, "lifecycle") == [{"mode": "quarantined"}]


def test_corrupt_backup_never_publishes_restore(tmp_path: Path) -> None:
    setup_restore(tmp_path)
    path = tmp_path / "backup" / "core.sqlite3"
    path.write_bytes(path.read_bytes() + b"bad")
    with pytest.raises(CoreError):
        Core.restore_quarantined(tmp_path / "backup", tmp_path / "corrupt")
    assert not (tmp_path / "corrupt").exists()


def test_external_tool_reserved_after_backup_blocks_activation(tmp_path: Path) -> None:
    source, owner, executor, _ = prepared(tmp_path)
    executor.call(
        "claim_dispatch", {"attempt_id": "A1", "generation": 1}, "claim", action_id="dispatch"
    )
    source.backup(owner.token, tmp_path / "backup")
    executor.call(
        "reserve_tool",
        {"attempt_id": "A1", "generation": 1, "native_id": "external", "command_id": "effect"},
        "reserve",
    )
    restored, token = Core.restore_quarantined(tmp_path / "backup", tmp_path / "restored")
    with pytest.raises(CoreError, match="restore.source_effects"):
        restored.activate_restored(token, source, owner.token)
    assert rows(source, "lifecycle") == [{"mode": "active"}]
    assert rows(restored, "lifecycle") == [{"mode": "quarantined"}]


def test_compatible_prior_backup_without_metadata_is_still_admitted(tmp_path: Path) -> None:
    source, token, _, _ = setup_restore(tmp_path)
    manifest_path = tmp_path / "backup" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.pop("compatibility")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    restored, credential = Core.restore_quarantined(tmp_path / "backup", tmp_path / "prior")
    restored.activate_restored(credential, source, token)
    assert rows(restored, "records") == rows(source, "records")


def test_incompatible_backup_metadata_fails_without_publishing(tmp_path: Path) -> None:
    setup_restore(tmp_path)
    manifest_path = tmp_path / "backup" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["compatibility"]["schema"] = "future/v999"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CoreError, match="backup.compatibility"):
        Core.restore_quarantined(tmp_path / "backup", tmp_path / "future")
    assert not (tmp_path / "future").exists()
