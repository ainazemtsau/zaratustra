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
