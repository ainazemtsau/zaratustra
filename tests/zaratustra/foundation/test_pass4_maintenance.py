"""Process-death boundaries for a schema 8 Core/DBOS/Pi backup package."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from zaratustra.foundation import (
    CreateArtifactRequest,
    FoundationError,
    RecoverRequest,
    apply_operation,
    authorize_local,
    authorize_recovery,
    inspect_space,
    read_artifact,
    read_execution,
    read_receipt,
    restore_backup,
)
from zaratustra.foundation.storage import load_backup as load_backup_package
from zaratustra.pi_adapter.assigned import create_assigned_backup

# isort: split
import sqlite3

_KILL_BACKUP = """
import os
import sys
from pathlib import Path
from uuid import UUID
import zaratustra.foundation.operations as operations
import zaratustra.foundation.storage as storage
from zaratustra.foundation import authorize_local
from zaratustra.pi_adapter.assigned import create_assigned_backup

root, backup_id, phase = Path(sys.argv[1]), UUID(sys.argv[2]), sys.argv[3]
def stop(code):
    os._exit(code)
if phase == 'closed_handles':
    operations.backup_database = lambda *_args: stop(70)
elif phase in ('core_snapshot', 'dbos_snapshot'):
    original = storage.file_sha256
    def after_digest(path):
        result = original(path)
        if path.parent.name == f'.{backup_id}.partial' and path.name == (
            'core.sqlite3' if phase == 'core_snapshot' else 'executor.sqlite3'
        ):
            stop(71 if phase == 'core_snapshot' else 72)
        return result
    storage.file_sha256 = after_digest
elif phase == 'pi_copy':
    original = storage.shutil.copy2
    def after_copy(source, destination, *args, **kwargs):
        result = original(source, destination, *args, **kwargs)
        if 'pi-rpc-home' in Path(source).parts:
            stop(73)
        return result
    storage.shutil.copy2 = after_copy
elif phase == 'format2_manifest':
    original = Path.write_text
    def after_write(path, data, *args, **kwargs):
        result = original(path, data, *args, **kwargs)
        if path.name == 'manifest.json' and '"format_version": 2' in data:
            stop(74)
        return result
    Path.write_text = after_write
elif phase == 'rename':
    original = Path.rename
    def after_rename(path, target):
        result = original(path, target)
        if path.name == f'.{backup_id}.partial':
            stop(75)
        return result
    Path.rename = after_rename
elif phase == 'marker':
    original = Path.replace
    def after_marker(path, target):
        result = original(path, target)
        if path.name == '.complete.partial':
            stop(76)
        return result
    Path.replace = after_marker
elif phase == 'inventory_complete':
    def after_inventory(path):
        stop(77)
    operations.load_backup = after_inventory
else:
    raise AssertionError(phase)
owner = authorize_local(root, actor='owner', source_ref='synthetic-backup-child')
create_assigned_backup(root, backup_id, owner)
raise AssertionError('injection did not fire')
"""


@pytest.mark.parametrize(
    ("phase", "exit_code", "renamed", "marked", "complete"),
    [
        ("closed_handles", 70, False, False, False),
        ("core_snapshot", 71, False, False, False),
        ("dbos_snapshot", 72, False, False, False),
        ("pi_copy", 73, False, False, False),
        ("format2_manifest", 74, False, False, False),
        ("rename", 75, True, False, False),
        ("marker", 76, True, True, False),
        ("inventory_complete", 77, True, True, True),
    ],
)
def test_schema8_backup_process_death_and_quarantined_restore(
    tmp_path: Path, phase: str, exit_code: int, renamed: bool, marked: bool, complete: bool
) -> None:
    from tests.zaratustra.foundation.test_parent_execution import _own_parent

    root, space, owner, _parent, _, _ = _own_parent(tmp_path)
    marker = f"fictional-backup-{uuid4()}"
    artifact = uuid4()
    created = CreateArtifactRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        artifact_id=artifact,
        media_type="text/plain",
        content=marker.encode(),
    )

    receipt = apply_operation(root, created, owner)
    technical = root / ".zara-core"
    with sqlite3.connect(technical / "executor.sqlite3") as connection:
        connection.execute("CREATE TABLE synthetic (value TEXT NOT NULL)")
        connection.execute("INSERT INTO synthetic VALUES ('fictional DBOS snapshot')")
    pi_file = technical / "pi-rpc-home" / "fictional" / "session.jsonl"
    pi_file.parent.mkdir(parents=True)
    pi_file.write_text('{"event":"fictional Pi state"}\n', encoding="utf-8")
    before = inspect_space(root, owner)
    interrupted_id = uuid4()
    crashed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-c",
            _KILL_BACKUP,
            str(root),
            str(interrupted_id),
            phase,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert crashed.returncode == exit_code, crashed.stderr
    backups = technical / "backups"
    interrupted = backups / str(interrupted_id)
    partial = backups / f".{interrupted_id}.partial"
    assert interrupted.is_dir() == renamed
    assert partial.is_dir() == (not renamed and phase != "closed_handles")
    assert (interrupted / "complete.json").is_file() == marked
    assert inspect_space(root, owner).completed_backups == int(complete)
    if complete:
        assert load_backup_package(interrupted).manifest.schema_version == 8
    else:
        with pytest.raises(FoundationError, match="invalid_backup"):
            load_backup_package(interrupted if renamed else partial)
        refused = tmp_path / "refused"
        refused.mkdir()
        with pytest.raises(FoundationError, match="invalid_backup"):
            restore_backup(
                interrupted if renamed else partial,
                refused,
                authorize_recovery(actor="owner", source_ref="synthetic-recovery"),
            )
        assert list(refused.iterdir()) == []
    assert read_receipt(root, created.operation_id, owner) == receipt
    assert apply_operation(root, created, owner) == receipt
    assert read_artifact(root, artifact, owner).content == marker.encode()
    published = create_assigned_backup(root, uuid4(), owner)
    manifest = published.manifest
    assert manifest.format_version == 2 and manifest.schema_version == 8
    assert manifest.execution_epoch == 1 and manifest.maintenance_boundary == "exclusive-managed"
    assert (
        manifest.executor_sha256
        == hashlib.sha256((published.package / "executor.sqlite3").read_bytes()).hexdigest().upper()
    )
    assert manifest.pi_rpc_home_files == {
        "fictional/session.jsonl": hashlib.sha256(
            (published.package / "pi-rpc-home" / "fictional" / "session.jsonl").read_bytes()
        )
        .hexdigest()
        .upper()
    }
    assert (
        manifest.database_sha256
        == hashlib.sha256((published.package / "core.sqlite3").read_bytes()).hexdigest().upper()
    )
    assert load_backup_package(published.package) == published
    for target in ("core.sqlite3", "executor.sqlite3", "pi-rpc-home/fictional/session.jsonl"):
        corrupted = tmp_path / f"corrupt-{target.replace('/', '-')}" / str(manifest.backup_id)
        shutil.copytree(published.package, corrupted)
        victim = corrupted.joinpath(*target.split("/"))
        victim.write_bytes(victim.read_bytes() + b"corrupt")
        with pytest.raises(FoundationError, match="invalid_backup"):
            load_backup_package(corrupted)
        refused_corrupt = tmp_path / f"refused-{target.replace('/', '-')}"
        refused_corrupt.mkdir()
        with pytest.raises(FoundationError, match="invalid_backup"):
            restore_backup(
                corrupted,
                refused_corrupt,
                authorize_recovery(actor="owner", source_ref="synthetic-recovery"),
            )
        assert list(refused_corrupt.iterdir()) == []
    restored_root = tmp_path / "restored"
    restored_root.mkdir()
    recovery = authorize_recovery(actor="owner", source_ref="synthetic-recovery")
    quarantined = restore_backup(published.package, restored_root, recovery)
    assert quarantined.execution_epoch == 2 and quarantined.recovery_state == "quarantined"
    assert not (restored_root / ".zara-core" / "executor.sqlite3").exists()
    assert not (restored_root / ".zara-core" / "pi-rpc-home").exists()
    assert (restored_root / ".zara-core" / "executor-restored.sqlite3").is_file()
    assert (restored_root / ".zara-core" / "pi-rpc-home-restored").is_dir()
    with pytest.raises(FoundationError, match="permission_denied"):
        read_artifact(restored_root, artifact, owner)
    apply_operation(
        restored_root,
        RecoverRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        recovery,
    )
    restored_owner = authorize_local(restored_root, actor="owner", source_ref="new-epoch")
    assert read_artifact(restored_root, artifact, restored_owner).content == marker.encode()
    assert read_receipt(restored_root, created.operation_id, restored_owner) == receipt
    assert before.completed_backups == 0
    print(
        json.dumps(
            {
                "phase": phase,
                "exit": crashed.returncode,
                "before_completed": before.completed_backups,
                "after_completed": inspect_space(root, owner).completed_backups,
                "partial": partial.is_dir(),
                "renamed": interrupted.is_dir(),
                "marker": marked,
                "original_valid": complete,
                "schema": manifest.schema_version,
                "format": manifest.format_version,
                "restored_epoch": quarantined.execution_epoch,
                "http": 0,
                "replay_equal": True,
            },
            sort_keys=True,
        )
    )


def test_quarantine_keeps_sent_own_parent_unknown_and_fences_old_epoch(tmp_path: Path) -> None:
    from tests.zaratustra.foundation.test_child_execution import (
        _assign,
        _claim,
        _invocation,
        _issue,
        _resource,
    )
    from tests.zaratustra.foundation.test_composition import _result
    from tests.zaratustra.foundation.test_parent_execution import _own_parent

    root, space, owner, parent, a, b = _own_parent(tmp_path)
    for child in (a, b):
        _issue(root, space, owner, parent, child)
        _result(root, space, owner, child, "result", b"fictional independent result")
    resource = _resource(root, space, owner, parent, "workspace-parent")
    attempt, session, request, receipt = _assign(root, space, owner, parent, resource)
    _claim(root, space, owner, parent, attempt, session)
    invocation = _invocation(root, space, owner, parent, attempt, session, finish=False)
    before = read_execution(root, parent, owner)
    assert before.invocations[0].status == "sent" and before.held_units > 0
    technical = root / ".zara-core"
    with sqlite3.connect(technical / "executor.sqlite3") as connection:
        connection.execute("CREATE TABLE synthetic (value TEXT NOT NULL)")
        connection.execute("INSERT INTO synthetic VALUES ('fictional sent Attempt')")
    pi_file = technical / "pi-rpc-home" / str(attempt) / "session.jsonl"
    pi_file.parent.mkdir(parents=True)
    pi_file.write_text('{"phase":"sent"}\n', encoding="utf-8")
    backup = create_assigned_backup(root, uuid4(), owner)
    assert backup.manifest.executor_sha256 is not None
    assert len(backup.manifest.pi_rpc_home_files) == 1
    destination = tmp_path / "restored"
    destination.mkdir()
    recovery = authorize_recovery(actor="owner", source_ref="fictional-own-recovery")
    quarantined = restore_backup(backup.package, destination, recovery)
    assert quarantined.execution_epoch == 2 and quarantined.recovery_state == "quarantined"
    with pytest.raises(FoundationError, match="permission_denied"):
        read_execution(destination, parent, owner)
    with pytest.raises(FoundationError, match="permission_denied"):
        apply_operation(destination, request, owner)
    apply_operation(
        destination,
        RecoverRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        recovery,
    )
    new_owner = authorize_local(destination, actor="owner", source_ref="new-epoch")
    after = read_execution(destination, parent, new_owner)
    assert after.invocations[0].invocation_id == invocation
    assert after.invocations[0].status == "unknown"
    assert after.assignments[0].status == "interrupted"
    assert after.held_units == before.held_units
    assert read_receipt(destination, request.operation_id, new_owner) == receipt
    assert not (destination / ".zara-core" / "executor.sqlite3").exists()
    assert (destination / ".zara-core" / "executor-restored.sqlite3").is_file()
    assert (destination / ".zara-core" / "pi-rpc-home-restored").is_dir()
    fresh = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-c",
            "import json,sys; from pathlib import Path; from uuid import UUID; "
            "from zaratustra.foundation import authorize_local,read_execution,read_receipt; "
            "p=Path(sys.argv[1]); o=authorize_local(p,actor='owner',source_ref='fresh'); "
            "e=read_execution(p,UUID(sys.argv[2]),o); "
            "r=read_receipt(p,UUID(sys.argv[3]),o); "
            "print(json.dumps({'assignment':e.assignments[0].status,"
            "'invocation':e.invocations[0].status,'held':e.held_units,"
            "'receipt':str(r.operation_id)}))",
            str(destination),
            str(parent),
            str(request.operation_id),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert fresh.returncode == 0, fresh.stderr
    assert json.loads(fresh.stdout.strip()) == {
        "assignment": "interrupted",
        "invocation": "unknown",
        "held": before.held_units,
        "receipt": str(receipt.operation_id),
    }
    print(
        json.dumps(
            {
                "phase": "sent-own-parent-restore",
                "before_assignment": before.assignments[0].status,
                "after_assignment": after.assignments[0].status,
                "before_invocation": before.invocations[0].status,
                "after_invocation": after.invocations[0].status,
                "held_units": after.held_units,
                "restored_epoch": quarantined.execution_epoch,
                "http": 0,
                "receipt_equal": True,
            },
            sort_keys=True,
        )
    )
