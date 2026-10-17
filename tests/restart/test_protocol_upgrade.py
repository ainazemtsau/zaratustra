"""Actual frozen old wheel refusal and preserving protocol-generation update."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import zaratustra_core
from zaratustra_core import Core, CoreError

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "delivery/zaratustra-pi-0.2.0-32b096a/wheels/zaratustra_core-0.2.0-py3-none-any.whl"


def old_root(tmp_path: Path) -> tuple[Core, str]:
    script = (
        "import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
        "from zaratustra_core import Core;c,t=Core.initialize(Path(sys.argv[2]));"
        "print(json.dumps({'token':t}))"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(OLD), str(tmp_path / "space")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    token = json.loads(result.stdout)["token"]
    core = Core(tmp_path / "space")
    core.connect(token).call(
        "apply_changes",
        {
            "changes": [
                {
                    "id": "activity",
                    "kind": "activity",
                    "key": "activity",
                    "body": "Fictional retained activity",
                }
            ]
        },
        "save",
        expected_heads={"activity": 0},
    )
    return core, token


def domain(core: Core) -> dict[str, Any]:
    with sqlite3.connect(core.path) as db:
        return {
            table: list(db.execute("SELECT * FROM " + table))
            for table in (
                "meta",
                "credentials",
                "rights",
                "records",
                "heads",
                "works",
                "attempts",
                "messages",
                "results",
                "actions",
                "tool_calls",
            )
        }


def test_frozen_02_wheel_refuses_upgraded_data_before_mutation(tmp_path: Path) -> None:
    core, token = old_root(tmp_path)
    assert core.data_protocol == 0
    before = domain(core)
    update = core.prepare_update(token, tmp_path / "snapshot")
    assert update["upgrade"]["from"] == 0 and update["upgrade"]["to"] == 1
    assert update["compatibility"]["required_protocol"] == 1
    assert "required_protocol" not in update["manifest"]["compatibility"]
    assert domain(core) == before
    assert core.prepare_update(token, tmp_path / "snapshot") == update
    assert core.data_protocol == 1
    protected = hashlib.sha256(core.path.read_bytes()).hexdigest()
    script = (
        "import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
        "from zaratustra_core import Core,CoreError\ntry: Core(Path(sys.argv[2]))\n"
        "except CoreError as e:\n print(e.code,e.field);sys.exit(37)\nsys.exit(99)"
    )
    old = subprocess.run(
        [sys.executable, "-I", "-c", script, str(OLD), str(core.root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert old.returncode == 37, old.stdout + old.stderr
    assert "maintenance.schema" in old.stdout
    assert hashlib.sha256(core.path.read_bytes()).hexdigest() == protected
    assert domain(core) == before
    core.backup(token, tmp_path / "new-snapshot")


@pytest.mark.parametrize("phase", ["before_commit", "after_commit"])
def test_upgrade_crash_recovers_exact_snapshot(tmp_path: Path, phase: str) -> None:
    core, token = old_root(tmp_path)
    before = domain(core)
    script = """import os,sys
from contextlib import contextmanager
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from zaratustra_core import Core,lifecycle
core=Core(Path(sys.argv[2]))
original_event=lifecycle.event
def event(db,kind,subject,body):
 if kind=='protocol_upgrade' and sys.argv[5]=='before_commit':os._exit(91)
 return original_event(db,kind,subject,body)
lifecycle.event=event
original=core._locked_transaction
@contextmanager
def transaction():
 with original() as db:
  yield db
  upgraded=db.execute('PRAGMA user_version').fetchone()[0]==1
 if upgraded and sys.argv[5]=='after_commit':os._exit(91)
core._locked_transaction=transaction
core.prepare_update(sys.argv[3],Path(sys.argv[4]))
"""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            script,
            str(Path(zaratustra_core.__file__).parents[1]),
            str(core.root),
            token,
            str(tmp_path / "snapshot"),
            phase,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 91, result.stderr
    reopened = Core(core.root)
    assert reopened.data_protocol == (0 if phase == "before_commit" else 1)
    assert domain(reopened) == before
    report = reopened.prepare_update(token, tmp_path / "snapshot")
    assert report["upgrade"]["from"] == 0 and reopened.data_protocol == 1
    assert domain(reopened) == before
    assert (
        len(
            [
                r
                for r in sqlite3.connect(reopened.path).execute(
                    "SELECT kind FROM events WHERE kind='protocol_upgrade'"
                )
            ]
        )
        == 1
    )


def test_missing_protocol_evidence_fails_closed(tmp_path: Path) -> None:
    core, _ = Core.initialize(tmp_path / "space")
    with sqlite3.connect(core.path) as db:
        db.execute("DELETE FROM events WHERE kind='protocol_initialized'")
    before = core.path.read_bytes()
    with pytest.raises(CoreError, match="protocol_evidence"):
        Core(core.root)
    assert core.path.read_bytes() == before


def protocol_one(tmp_path: Path, upgraded: bool) -> tuple[Core, str]:
    if upgraded:
        core, token = old_root(tmp_path)
        core.grant(token, "delegated", ["read"], origin="host")
        core.prepare_update(token, tmp_path / "generation-zero-snapshot")
    else:
        core, token = Core.initialize(tmp_path / "space")
        core.connect(token).call(
            "apply_changes",
            {
                "changes": [
                    {
                        "id": "activity",
                        "kind": "activity",
                        "key": "activity",
                        "body": "Fictional unchanged subject",
                    }
                ]
            },
            "seed",
            expected_heads={"activity": 0},
        )
    if not upgraded:
        core.grant(token, "delegated", ["read"], origin="host")
    return core, token


@pytest.mark.parametrize("upgraded", [False, True])
def test_protocol_one_unchanged_update_reentry_preserves_source_and_snapshot(
    tmp_path: Path, upgraded: bool
) -> None:
    core, token = protocol_one(tmp_path, upgraded)
    source_before = core.path.read_bytes()
    snapshot = tmp_path / "normal-update"
    first = core.prepare_update(token, snapshot)
    assert first["upgrade"] == {"from": 1, "to": 1}
    snapshot_before = (snapshot / "core.sqlite3").read_bytes()
    assert Core(core.root).prepare_update(token, snapshot) == first
    assert core.path.read_bytes() == source_before
    assert (snapshot / "core.sqlite3").read_bytes() == snapshot_before
    assert (
        core.connect(token).call("read_exact", {"id": "activity", "revision": 1}, "retained")["id"]
        == "activity"
    )


@pytest.mark.parametrize("change", ["activity", "rights", "credentials", "history"])
@pytest.mark.parametrize("snapshot_kind", ["normal", "initial_upgrade"])
def test_protocol_one_changed_source_refuses_old_snapshot(
    tmp_path: Path, change: str, snapshot_kind: str
) -> None:
    core, token = protocol_one(tmp_path, True)
    snapshot = tmp_path / (
        "normal-update" if snapshot_kind == "normal" else "generation-zero-snapshot"
    )
    if snapshot_kind == "normal":
        core.prepare_update(token, snapshot)
    snapshot_before = (snapshot / "core.sqlite3").read_bytes()
    if change == "activity":
        core.connect(token).call(
            "apply_changes",
            {
                "changes": [
                    {
                        "id": "activity",
                        "kind": "activity",
                        "key": "activity",
                        "body": "New fictional revision",
                    }
                ]
            },
            "new-revision",
            expected_heads={"activity": 1},
        )
    elif change == "rights":
        core.revoke(token, "delegated")
    elif change == "history":
        # Synthetic corruption: unchanged domain rows must not hide altered lineage receipts.
        with sqlite3.connect(core.path) as db:
            db.execute("UPDATE receipts SET fingerprint=? WHERE command='save'", ("f" * 64,))
    else:
        # Adds a credential while the same principal's rights remain exactly unchanged.
        core.grant(token, "delegated", ["read"], origin="host")
    source_before = core.path.read_bytes()
    with pytest.raises(CoreError, match="maintenance.update_snapshot"):
        core.prepare_update(token, snapshot)
    assert core.path.read_bytes() == source_before
    assert (snapshot / "core.sqlite3").read_bytes() == snapshot_before


def test_protocol_one_foreign_snapshot_and_stale_upgrade_snapshot_refused(tmp_path: Path) -> None:
    core, token = protocol_one(tmp_path, True)
    foreign, foreign_token = Core.initialize(tmp_path / "foreign")
    snapshot = tmp_path / "foreign-snapshot"
    foreign.prepare_update(foreign_token, snapshot)
    source_before = core.path.read_bytes()
    with pytest.raises(CoreError, match="maintenance.update_snapshot"):
        core.prepare_update(token, snapshot)
    assert core.path.read_bytes() == source_before
    # A prior valid generation0->1 audit must not waive later source-state changes.
    core.grant(token, "new-after-upgrade", ["read"], origin="host")
    source_before = core.path.read_bytes()
    with pytest.raises(CoreError, match="maintenance.update_snapshot"):
        core.prepare_update(token, tmp_path / "generation-zero-snapshot")
    assert core.path.read_bytes() == source_before


@pytest.mark.parametrize("upgraded", [False, True])
def test_protocol_one_process_interruption_after_snapshot_reenters_normally(
    tmp_path: Path, upgraded: bool
) -> None:
    core, token = protocol_one(tmp_path, upgraded)
    source_before = core.path.read_bytes()
    snapshot = tmp_path / "interrupted-normal-update"
    script = """import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from zaratustra_core import Core,maintenance
original=maintenance.backup_locked
def interrupted(core,token,destination):
 original(core,token,destination)
 os._exit(91)
maintenance.backup_locked=interrupted
Core(Path(sys.argv[2])).prepare_update(sys.argv[3],Path(sys.argv[4]))
"""
    process = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            script,
            str(Path(zaratustra_core.__file__).parents[1]),
            str(core.root),
            token,
            str(snapshot),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert process.returncode == 91, process.stdout + process.stderr
    assert (snapshot / "manifest.json").is_file()
    snapshot_before = (snapshot / "core.sqlite3").read_bytes()
    reopen = """import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from zaratustra_core import Core
result=Core(Path(sys.argv[2])).prepare_update(sys.argv[3],Path(sys.argv[4]))
print(json.dumps({"status":result["status"],"upgrade":result["upgrade"]}))
"""
    resumed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            reopen,
            str(Path(zaratustra_core.__file__).parents[1]),
            str(core.root),
            token,
            str(snapshot),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    assert json.loads(resumed.stdout) == {"status": "compatible", "upgrade": {"from": 1, "to": 1}}
    assert core.path.read_bytes() == source_before
    assert (snapshot / "core.sqlite3").read_bytes() == snapshot_before


def test_protocol_one_reentry_allows_only_additional_read_receipts(tmp_path: Path) -> None:
    core, token = protocol_one(tmp_path, False)
    snapshot = tmp_path / "normal-update"
    first = core.prepare_update(token, snapshot)
    core.connect(token).call("read_exact", {"id": "activity", "revision": 1}, "read-after-snapshot")
    source_before = core.path.read_bytes()
    assert core.prepare_update(token, snapshot) == first
    assert core.path.read_bytes() == source_before
