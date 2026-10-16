"""Atomic scoped continuation, observed through Core and physical state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from zaratustra_app import Coordinator, Driver
from zaratustra_core import CoreError

from .support import MEMORY, METHOD, PROFILE, fixture, ingest, inspect


def routed(root: Path, upper: int = 2) -> tuple[Any, Any, Any, Any, dict[str, Any]]:
    core, owner, client = fixture(root)
    coordinator = Coordinator(client)
    coordinator.prepare("work", "route-attempt", PROFILE)
    driver = Driver(lambda *_: b'{"state":"completed","text":"routing only"}')
    driver.resource_upper = upper
    coordinator.dispatch("route-attempt", 1, driver)
    payload = {
        "attempt_id": "route-attempt",
        "generation": 1,
        "terminal_event": "terminal",
        "original_cursor": 0,
        "processed_cutoff": 0,
        "state": "completed",
        "text": "",
        "changes": [
            {"id": "activity", "kind": "activity", "key": "practice", "body": "Agreed practice"}
        ],
        "outputs": [{"id": "activity", "revision": 1}],
        "next_work": {
            "id": "scoped-work",
            "conversation": "conversation",
            "goal": "Perform the agreed practice",
            "scope": "activity",
            "method_ref": METHOD,
            "inputs": [{"id": "activity", "revision": 1}, MEMORY],
            "call_limit": 4 - upper,
            "continuation_policy": "durable",
        },
    }
    return core, owner, client, coordinator, payload


def commit(client: Any, payload: dict[str, Any], command: str = "handoff") -> dict[str, Any]:
    return cast(
        dict[str, Any],
        client.call("commit_outcome", payload, command, expected_heads={"activity": 0}),
    )


def test_handoff_preserves_raw_input_then_scoped_result(tmp_path: Path) -> None:
    core, owner, client, coordinator, payload = routed(tmp_path)
    result = commit(client, payload)
    assert result["cutoff"] == 0 and result["delivered_cutoff"] == 20
    assert result["next_work_id"] == "scoped-work"
    assert inspect(core, "conversations")[0]["cursor"] == 0
    works = {w["id"]: w for w in inspect(core, "works")}
    assert works["work"]["status"] == "completed" and works["scoped-work"]["status"] == "ready"
    assert len([w for w in works.values() if w["status"] not in {"completed", "cancelled"}]) == 1
    pending = [i for i in inspect(core, "intents") if i["kind"] == "input"]
    assert json.loads(pending[0]["body"])["after"] == 0
    try:
        replay: Any = commit(client, payload, "same-terminal-other-command")
    except CoreError as error:
        replay = error
    assert replay == result, "The retained final result must replay without executing a new handoff"
    assert len(inspect(core, "works")) == 2
    ingest(owner, "21", "A late correction remains pending")
    prepared = coordinator.prepare("scoped-work", "useful-attempt", PROFILE)
    assert prepared["pinned"]["messages"][-1]["seq"] == 21
    assert prepared["pinned"]["work"]["scope"] == "activity"
    assert len(prepared["pinned"]["messages"]) == 21
    driver = Driver(lambda *_: b'{"state":"completed","text":"actual useful response"}')
    coordinator.dispatch("useful-attempt", 1, driver)
    useful = coordinator.recover("useful-attempt")
    assert useful["text"] == "actual useful response" and useful["cutoff"] == 21
    assert inspect(core, "conversations")[0]["cursor"] == 21
    core.backup(owner.token, tmp_path / "backup")


@pytest.mark.parametrize("upper", [3, 4])
def test_exhausted_continuation_is_paused_not_lost(tmp_path: Path, upper: int) -> None:
    core, _, client, coordinator, payload = routed(tmp_path, upper)
    result = commit(client, payload)
    child = next(w for w in inspect(core, "works") if w["id"] == result["next_work_id"])
    assert child["status"] == "paused" and child["reserved"] == 0
    assert json.loads(child["body"])["call_limit"] == 4 - upper
    assert json.loads(child["body"])["continuation"]["resource_upper"] == upper
    assert not any(
        i["kind"] == "prepare" and i["subject"] == child["id"] for i in inspect(core, "intents")
    )
    assert inspect(core, "conversations")[0]["cursor"] == 0
    with pytest.raises(CoreError):
        coordinator.prepare(child["id"], "must-not-prepare", PROFILE)
    assert len(inspect(core, "attempts")) == 1


@pytest.mark.parametrize("damage", ["budget", "scope", "conversation", "wait", "partial", "upper"])
def test_bad_handoff_rolls_back_every_boundary(tmp_path: Path, damage: str) -> None:
    core, _, client, _, payload = routed(tmp_path)
    if damage == "budget":
        payload["next_work"]["call_limit"] = 3
    elif damage == "scope":
        payload["next_work"]["scope"] = "missing"
    elif damage == "conversation":
        payload["next_work"]["conversation"] = "other"
    elif damage == "wait":
        payload["state"] = "waiting"
        payload["wait"] = {"id": "wait", "question": "bad combination"}
    elif damage == "upper":
        payload["next_work"]["resource_upper"] = 1
    else:
        payload["processed_cutoff"] = 10
    with pytest.raises(CoreError):
        commit(client, payload)
    assert len(inspect(core, "works")) == 1
    assert not inspect(core, "results")
    assert not any(h["id"] == "activity" for h in inspect(core, "heads"))
    assert inspect(core, "conversations")[0]["cursor"] == 0
    assert not any(r["command"] == "handoff" for r in inspect(core, "receipts"))


def test_preserved_cursor_without_next_work_is_refused(tmp_path: Path) -> None:
    core, _, client, _, payload = routed(tmp_path)
    payload.pop("next_work")
    with pytest.raises(CoreError, match="stale_basis"):
        commit(client, payload)
    assert not inspect(core, "results") and inspect(core, "conversations")[0]["cursor"] == 0


def test_refresh_can_drop_inputs_without_losing_historical_activity(tmp_path: Path) -> None:
    core, owner, client, _, payload = routed(tmp_path)
    commit(client, payload)
    owner.call(
        "control_work",
        {"work_id": "scoped-work", "revision": 1, "action": "refresh", "inputs": []},
        "refresh-inputs",
    )
    child = next(w for w in inspect(core, "works") if w["id"] == "scoped-work")
    body = json.loads(child["body"])
    assert body["inputs"] == []
    assert body["continuation"]["activity_ref"] == {"id": "activity", "revision": 1}
    core.backup(owner.token, tmp_path / "refreshed-backup")
    from zaratustra_core import Core

    Core.restore_quarantined(tmp_path / "refreshed-backup", tmp_path / "restored")
    assert (tmp_path / "restored/core.sqlite3").is_file()


@pytest.mark.parametrize(
    "damage",
    [
        "parent",
        "scope",
        "activity",
        "delivered_bool",
        "processed_bool",
        "reserve_bool",
        "upper_bool",
        "budget",
        "reverse",
    ],
)
def test_rehashed_handoff_reference_corruption_is_refused(tmp_path: Path, damage: str) -> None:
    import sqlite3

    from zaratustra_core import Core

    from .test_backup_references import rehash

    core, owner, client, _, payload = routed(tmp_path)
    commit(client, payload)
    backup = tmp_path / "backup"
    core.backup(owner.token, backup)
    with sqlite3.connect(backup / "core.sqlite3") as db:
        body = json.loads(db.execute("SELECT body FROM works WHERE id='scoped-work'").fetchone()[0])
        link = body["continuation"]
        if damage == "parent":
            link["attempt_id"] = "missing"
        elif damage == "scope":
            body["scope"] = "different-activity"
        elif damage == "activity":
            link["activity_ref"] = MEMORY
        elif damage.endswith("_bool"):
            field = {
                "delivered": "delivered_cutoff",
                "processed": "processed_cutoff",
                "reserve": "parent_reserved",
                "upper": "resource_upper",
            }[damage.removesuffix("_bool")]
            link[field] = bool(link[field])
        elif damage == "budget":
            body["call_limit"] = 99
        else:
            result = json.loads(db.execute("SELECT body FROM results").fetchone()[0])
            result["next_work_id"] = "missing"
            db.execute("UPDATE results SET body=?", (json.dumps(result),))
        db.execute("UPDATE works SET body=? WHERE id='scoped-work'", (json.dumps(body),))
    rehash(backup)
    with pytest.raises(CoreError, match="backup.reference_closure"):
        Core.restore_quarantined(backup, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_physical_loss_inside_child_creation_rolls_back_handoff(tmp_path: Path) -> None:
    import subprocess
    import sys

    import zaratustra_app
    import zaratustra_core
    from zaratustra_core import Core

    sources = [
        str(Path(zaratustra_core.__file__).parents[1]),
        str(Path(zaratustra_app.__file__).parents[1]),
        str(Path(__file__).resolve().parents[2]),
    ]
    script = (
        "import sys;sys.path[:0]="
        + repr(sources)
        + ";"
        + """
import json,os
from pathlib import Path
from zaratustra_core import Core
from tests.restart.test_work_handoff import routed,commit
root=Path(sys.argv[1]);core,owner,client,coord,payload=routed(root)
(root/'payload.json').write_text(json.dumps(payload))
(root/'test-token').write_text(owner.token)
original=Core._work
def crash(self,*args,**kwargs):
    result=original(self,*args,**kwargs)
    if kwargs.get('continuation') is not None:os._exit(77)
    return result
Core._work=crash
commit(client,payload)
"""
    )
    run = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script, str(tmp_path)], capture_output=True, timeout=30
    )
    if b"MUTANT_REACHED" in run.stdout:
        print(run.stdout.decode())
    assert run.returncode == 77, run.stdout + run.stderr
    core = Core(tmp_path / "space")
    assert not any(h["id"] == "activity" for h in inspect(core, "heads"))
    assert len(inspect(core, "works")) == 1 and not inspect(core, "results")
    assert inspect(core, "conversations")[0]["cursor"] == 0
    token = (tmp_path / "test-token").read_text().strip()
    payload = json.loads((tmp_path / "payload.json").read_bytes())
    commit(core.connect(token), payload)
    assert len(inspect(core, "works")) == 2
    assert inspect(core, "conversations")[0]["cursor"] == 0
