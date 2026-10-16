"""G15 independent byte, crash, quarantine and writer exclusion observations."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast

import pytest
import zaratustra_core
from zaratustra_core import Core, CoreError, storage

from .support import inspect
from .test_contract import prepared
from .test_crashes import child as crash_child

ROOT = Path(__file__).resolve().parents[2]
RAW = bytes(range(256)) * 257 + b"complete trailing bytes"
SHA = hashlib.sha256(RAW).hexdigest()


def stage(client: Any) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        client.call(
            "stage_artifact",
            {
                "sha256": SHA,
                "raw_base64": base64.b64encode(RAW).decode(),
                "content_type": "application/octet-stream",
            },
            "stage",
        ),
    )


def launch(packet: dict[str, Any]) -> subprocess.Popen[str]:
    script = (
        "import sys;sys.path[:0]="
        + repr([str(Path(zaratustra_core.__file__).parents[1]), str(ROOT)])
        + ";from tests.restart.maintenance_worker import main;main()"
    )
    process = subprocess.Popen(
        [sys.executable, "-I", "-X", "utf8", "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    assert process.stdin is not None
    process.stdin.write(json.dumps(packet))
    process.stdin.close()
    process.stdin = None
    return process


def test_artifact_bytes_refs_and_diagnostics(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "space")
    owner = core.connect(token)
    assert stage(owner) == {"sha256": SHA, "size": len(RAW)}
    assert (core.root / "artifacts" / SHA).is_file()
    assert (core.root / "artifacts" / SHA).read_bytes() == RAW
    owner.call(
        "apply_changes",
        {
            "changes": [
                {
                    "id": "a",
                    "kind": "data",
                    "key": "a",
                    "body": "PRIVATE CONVERSATION AND SECRET VALUE",
                    "artifact_refs": [SHA],
                }
            ]
        },
        "publish",
        expected_heads={"a": 0},
    )
    record = owner.call("read_exact", {"id": "a", "revision": 1}, "record")
    assert record["body"]["artifact_refs"] == [SHA]
    assert (
        base64.b64decode(owner.call("read_artifact", {"sha256": SHA}, "bytes")["raw_base64"]) == RAW
    )
    with pytest.raises(CoreError, match="artifact.missing"):
        owner.call(
            "apply_changes",
            {
                "changes": [
                    {
                        "id": "bad",
                        "kind": "data",
                        "key": "bad",
                        "body": "bad",
                        "artifact_refs": ["0" * 64],
                    }
                ]
            },
            "broken",
            expected_heads={"bad": 0},
        )
    assert not any(h["id"] == "bad" for h in inspect(core, "heads"))
    diagnostics = owner.call("export_diagnostics", {}, "diagnostics")
    encoded = json.dumps(diagnostics)
    assert (
        "PRIVATE CONVERSATION" not in encoded
        and token not in encoded
        and str(core.root) not in encoded
    )
    assert diagnostics["preview"] and not diagnostics["transmitted"]
    assert diagnostics["integrity"] == "ok" and diagnostics["foreign_key_violations"] == 0


@pytest.mark.parametrize("phase", ["stage_sync", "stage_replace", "stage_committed"])
def test_staging_physical_crash(tmp_path: Path, phase: str) -> None:
    core, token = Core.initialize(tmp_path / "space")
    child = launch(
        {
            "root": str(core.root),
            "token": token,
            "phase": phase,
            "raw_base64": base64.b64encode(RAW).decode(),
        }
    )
    out, err = child.communicate(timeout=20)
    if "MUTANT_REACHED" in out:
        print(out)
    assert child.returncode == 91, out + err
    rows = inspect(core, "artifacts")
    if phase == "stage_committed":
        assert rows == [
            {"sha256": SHA, "size": len(RAW), "content_type": "application/octet-stream"}
        ]
        reader = launch({"root": str(core.root), "token": token, "phase": "read", "sha256": SHA})
        raw, error = reader.communicate(timeout=20)
        assert reader.returncode == 0, error
        assert base64.b64decode(json.loads(raw)["raw_base64"]) == RAW
    else:
        assert rows == []
    assert stage(core.connect(token))["sha256"] == SHA
    assert (core.root / "artifacts" / SHA).read_bytes() == RAW


def test_backup_complete_new_epoch_quarantine(tmp_path: Path) -> None:
    core, owner, executor, _ = prepared(tmp_path)
    crashed = crash_child(
        {"root": str(core.root), "token": executor.token, "phase": "claim_after_receiver"}
    )
    assert crashed.returncode == 91, crashed.stderr
    assert len((core.root / "receiver-effects.jsonl").read_bytes().splitlines()) == 1
    stage(owner)
    owner.call(
        "apply_changes",
        {
            "changes": [
                {
                    "id": "attached",
                    "kind": "data",
                    "key": "bytes",
                    "body": "held",
                    "artifact_refs": [SHA],
                }
            ]
        },
        "attach",
        expected_heads={"attached": 0},
    )
    manifest = core.backup(owner.token, tmp_path / "backup")
    assert manifest["artifacts"] == [
        {"sha256": SHA, "size": len(RAW), "content_type": "application/octet-stream"}
    ]
    assert (tmp_path / "backup" / "artifacts" / SHA).read_bytes() == RAW
    restorer = launch(
        {
            "root": str(core.root),
            "phase": "restore",
            "backup": str(tmp_path / "backup"),
            "destination": str(tmp_path / "restored"),
        }
    )
    output, error = restorer.communicate(timeout=20)
    if "MUTANT_REACHED" in output:
        print(output)
    assert restorer.returncode == 0, output + error
    restored = Core(tmp_path / "restored")
    token = (restored.root / "owner.credential").read_text(encoding="utf-8")
    client = restored.connect(token)
    assert client.meta["epoch"] == owner.meta["epoch"] + 1
    assert (
        client.meta["instance"] != owner.meta["instance"]
        and client.meta["space"] != owner.meta["space"]
    )
    for old in (owner.token, executor.token):
        with pytest.raises(CoreError, match="credential"):
            restored.connect(old)
    with pytest.raises(CoreError, match="wrong_instance"):
        client.send(owner.request("describe_contract", {}, "old-request"))
    stale = client.request("describe_contract", {}, "stale").model_copy(
        update={"recovery_epoch": owner.meta["epoch"]}
    )
    with pytest.raises(CoreError, match="stale_epoch"):
        client.send(stale)
    with pytest.raises(CoreError, match="quarantined"):
        client.call(
            "ingest_message",
            {"conversation": "new", "event_id": "noexec", "raw_base64": "bm9leGVj"},
            "quarantine-write",
        )
    with pytest.raises(CoreError, match="quarantined"):
        client.call(
            "control_work", {"work_id": "work", "revision": 3, "action": "resume"}, "resume"
        )
    assert inspect(restored, "intents") == []
    assert inspect(restored, "attempts")[0]["status"] == "fenced"
    assert inspect(restored, "works")[0]["status"] == "paused"
    assert inspect(restored, "works")[0]["reserved"] == 1
    assert inspect(restored, "actions")[0]["state"] == "claimed"
    assert client.call("export_diagnostics", {}, "diagnose")["mode"] == "quarantined"
    assert (
        base64.b64decode(client.call("read_artifact", {"sha256": SHA}, "bytes")["raw_base64"])
        == RAW
    )
    assert inspect(core, "attempts")[0]["status"] == "claimed"


@pytest.mark.parametrize("damage", ["orphan_head", "orphan_artifact_ref"])
def test_rehashed_incoherent_backup_refused(tmp_path: Path, damage: str) -> None:
    core, token = Core.initialize(tmp_path / "space")
    owner = core.connect(token)
    stage(owner)
    owner.call(
        "apply_changes",
        {
            "changes": [
                {"id": "a", "kind": "data", "key": "a", "body": "held", "artifact_refs": [SHA]}
            ]
        },
        "a",
        expected_heads={"a": 0},
    )
    backup = tmp_path / "backup"
    core.backup(token, backup)
    database = backup / "core.sqlite3"
    with sqlite3.connect(database) as db:
        if damage == "orphan_head":
            db.execute("UPDATE heads SET revision=99")
        else:
            body = json.loads(db.execute("SELECT body FROM records").fetchone()[0])
            body["artifact_refs"] = ["0" * 64]
            db.execute("UPDATE records SET body=?", (json.dumps(body),))
    db.close()
    manifest = json.loads((backup / "manifest.json").read_bytes())
    raw = database.read_bytes()
    manifest.update(database_sha256=hashlib.sha256(raw).hexdigest(), database_size=len(raw))
    (backup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CoreError, match="backup.(integrity|reference_closure)"):
        Core.restore_quarantined(backup, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


@pytest.mark.parametrize(
    "damage", ["database", "valid_database_change", "bytes", "missing", "manifest", "partial"]
)
def test_corrupt_partial_backups_refused(tmp_path: Path, damage: str) -> None:
    core, token = Core.initialize(tmp_path / "space")
    stage(core.connect(token))
    core.backup(token, tmp_path / "backup")
    source = tmp_path / "damaged"
    shutil.copytree(tmp_path / "backup", source)
    if damage == "database":
        (source / "core.sqlite3").write_bytes(b"corrupt")
    elif damage == "valid_database_change":
        with sqlite3.connect(source / "core.sqlite3") as db:
            # Change valid SQLite bytes without breaking event/reference closure:
            # this fixture isolates the manifest SHA guard from logical integrity.
            db.execute("PRAGMA user_version=17")
        db.close()
    elif damage == "bytes":
        (source / "artifacts" / SHA).write_bytes(RAW[:-1])
    elif damage == "missing":
        (source / "artifacts" / SHA).unlink()
    elif damage == "partial":
        (source / "manifest.json").unlink()
    else:
        manifest = json.loads((source / "manifest.json").read_bytes())
        manifest["artifacts"] = []
        (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CoreError, match="invalid_request"):
        Core.restore_quarantined(source, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


@pytest.mark.parametrize("phase", ["backup_hold", "backup_hold_inventory"])
def test_backup_crash_and_maintenance_excludes_writer(tmp_path: Path, phase: str) -> None:
    core, token = Core.initialize(tmp_path / "space")
    owner = core.connect(token)
    stage(owner)
    # An idle live client owns neither a transaction nor a snapshot.
    with sqlite3.connect(core.path, timeout=0) as independent:
        independent.execute("BEGIN EXCLUSIVE")
        independent.rollback()
    common = {"root": str(core.root), "token": token, "destination": str(tmp_path / "backup")}
    crashed = launch(common | {"phase": "backup_partial"})
    out, err = crashed.communicate(timeout=20)
    if "MUTANT_REACHED" in out:
        print(out)
    assert crashed.returncode == 91, out + err
    assert not (tmp_path / "backup").exists()
    partial = next(tmp_path.glob("backup.partial-*"))
    with pytest.raises(CoreError, match="backup.invalid"):
        Core.restore_quarantined(partial, tmp_path / "restored")
    ready, release = tmp_path / "ready", tmp_path / "release"
    held = launch(common | {"phase": phase, "ready": str(ready), "release": str(release)})
    deadline = time.monotonic() + 15
    try:
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists()
        with pytest.raises(CoreError, match="maintenance"):
            owner.call(
                "ingest_message",
                {"conversation": "c", "event_id": "blocked", "raw_base64": "YmxvY2tlZA=="},
                "blocked",
            )
    finally:
        release.write_text("release", encoding="utf-8")
        out, err = held.communicate(timeout=20)
        if "MUTANT_REACHED" in out:
            print(out)
    assert held.returncode == 0, out + err
    assert inspect(core, "messages") == []
    owner.call(
        "ingest_message",
        {"conversation": "c", "event_id": "after", "raw_base64": "YWZ0ZXI="},
        "after",
    )
    assert inspect(core, "messages")[0]["event"] == "after"


@pytest.mark.parametrize("release", [True, False])
def test_atomic_publish_windows_sharing_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, release: bool
) -> None:
    staging, destination = tmp_path / "partial", tmp_path / "published"
    staging.mkdir()
    (staging / "held.bin").write_bytes(RAW)
    if os.name != "nt":
        storage.publish_directory(staging, destination)
        assert (destination / "held.bin").read_bytes() == RAW
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    # A file reader which withholds FILE_SHARE_DELETE blocks ancestor publication.
    handle = kernel.CreateFileW(str(staging / "held.bin"), 0x80000000, 3, None, 3, 0, None)
    assert handle != ctypes.c_void_p(-1).value
    closed = False
    try:
        with pytest.raises(PermissionError) as observed:
            os.replace(staging, destination)
        assert observed.value.winerror in {5, 32, 33} and not destination.exists()
        if release:

            def release_reader(_: float) -> None:
                nonlocal closed
                assert kernel.CloseHandle(handle)
                closed = True

            monkeypatch.setattr(time, "sleep", release_reader)
            storage.publish_directory(staging, destination)
            assert not staging.exists() and (destination / "held.bin").read_bytes() == RAW
        else:
            started = time.monotonic()
            with pytest.raises(PermissionError):
                storage.publish_directory(staging, destination)
            assert 2 <= time.monotonic() - started < 4
            assert not destination.exists() and (staging / "held.bin").read_bytes() == RAW
    finally:
        if not closed:
            assert kernel.CloseHandle(handle)


def test_atomic_publish_unrelated_error_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, Path]] = []
    error = OSError("unrelated publication failure")

    def fail(source: Path, destination: Path) -> None:
        calls.append((source, destination))
        raise error

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError) as observed:
        storage.publish_directory(tmp_path / "partial", tmp_path / "published")
    assert observed.value is error
    assert calls == [(tmp_path / "partial", tmp_path / "published")]


def test_atomic_publish_preserves_existing_destination(tmp_path: Path) -> None:
    staging, destination = tmp_path / "partial", tmp_path / "published"
    staging.mkdir()
    destination.mkdir()
    (staging / "new.bin").write_bytes(RAW)
    (destination / "sentinel.bin").write_bytes(b"existing destination")
    with pytest.raises(OSError):
        storage.publish_directory(staging, destination)
    assert (staging / "new.bin").read_bytes() == RAW
    assert (destination / "sentinel.bin").read_bytes() == b"existing destination"
    assert not (destination / "new.bin").exists()


def test_failed_backup_cleanup_preserves_publication_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zaratustra_core import maintenance

    core, token = Core.initialize(tmp_path / "space")
    publication_error = PermissionError("publication denied")

    def fail_publish(source: Path, destination: Path) -> None:
        assert source.is_dir() and not destination.exists()
        raise publication_error

    def failed_cleanup(source: Path, *, ignore_errors: bool = False) -> None:
        assert source.is_dir() and ignore_errors
        # Emulate rmtree's ignore_errors contract with an unremovable staging tree.

    monkeypatch.setattr(maintenance, "publish_directory", fail_publish)
    monkeypatch.setattr(shutil, "rmtree", failed_cleanup)
    with pytest.raises(PermissionError) as observed:
        core.backup(token, tmp_path / "backup")
    assert observed.value is publication_error
    assert not (tmp_path / "backup").exists()
