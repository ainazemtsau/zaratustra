from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import pytest

import zaratustra.foundation.operations as operation_module
from zaratustra.foundation import (
    BackupInfo,
    BootstrapRequest,
    CreateArtifactRequest,
    DeleteArtifactRequest,
    FoundationError,
    LocalAuthority,
    RecoverRequest,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    initialize_space,
    inspect_recovery,
    inspect_space,
    read_artifact,
    read_receipt,
    restore_backup,
)
from zaratustra.foundation.storage import (
    backup_database as prepare_backup_database,
)
from zaratustra.foundation.storage import (
    load_backup as load_backup_package,
)


def ready_space(tmp_path: Path) -> tuple[Path, UUID, LocalAuthority]:
    root = tmp_path / "space"
    root.mkdir()
    info = initialize_space(root)
    owner = authorize_local(root, actor="owner", source_ref="synthetic-owner")
    apply_operation(
        root,
        BootstrapRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        owner,
    )
    return root, info.space_id, owner


def test_backup_restore_is_verified_quarantined_and_requires_fresh_epoch(tmp_path: Path) -> None:
    root, space_id, owner = ready_space(tmp_path)
    artifact_id = uuid4()
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            artifact_id=artifact_id,
            media_type="text/plain",
            content=b"backup payload",
        ),
        owner,
    )
    backup = create_backup(root, uuid4(), owner)
    restored = tmp_path / "restored"
    restored.mkdir()
    recovery = authorize_recovery(actor="owner", source_ref="fresh-recovery-confirmation")

    quarantined = restore_backup(backup.package, restored, recovery)

    assert quarantined.recovery_state == "quarantined"
    assert quarantined.execution_epoch == 2
    assert inspect_recovery(restored, recovery)["space_id"] == str(space_id)
    with pytest.raises(FoundationError) as inherited:
        read_artifact(restored, artifact_id, owner)

    apply_operation(
        restored,
        RecoverRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        recovery,
    )
    restored_owner = authorize_local(
        restored, actor="owner", source_ref="post-restore-owner-confirmation"
    )

    assert inherited.value.code == "permission_denied"
    assert read_artifact(restored, artifact_id, restored_owner).content == b"backup payload"


def test_backup_hash_mismatch_is_refused_without_destination_change(tmp_path: Path) -> None:
    root, _, owner = ready_space(tmp_path)
    backup = create_backup(root, uuid4(), owner)
    database = backup.package / "core.sqlite3"
    database.write_bytes(database.read_bytes() + b"tampered")
    restored = tmp_path / "restored"
    restored.mkdir()
    recovery = authorize_recovery(actor="owner", source_ref="fresh-recovery-confirmation")

    with pytest.raises(FoundationError) as refusal:
        restore_backup(backup.package, restored, recovery)

    assert refusal.value.code == "invalid_backup"
    assert list(restored.iterdir()) == []


def test_delete_blocks_all_revisions_and_sanitizes_live_and_managed_backups(
    tmp_path: Path,
) -> None:
    root, space_id, owner = ready_space(tmp_path)
    sentinel = b"UNIQUE-MANAGED-PAYLOAD-TO-REMOVE-92A7"
    artifact_id = uuid4()
    create = CreateArtifactRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        artifact_id=artifact_id,
        media_type="application/octet-stream",
        content=sentinel,
    )
    apply_operation(root, create, owner)
    backup = create_backup(root, uuid4(), owner)
    delete = DeleteArtifactRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor="owner",
        artifact_id=artifact_id,
        expected_revision=1,
    )
    apply_operation(root, delete, owner)

    with pytest.raises(FoundationError) as historical:
        read_artifact(root, artifact_id, owner, revision=1)
    with pytest.raises(FoundationError) as removed_receipt:
        read_receipt(root, create.operation_id, owner)
    with pytest.raises(FoundationError) as removed_intent:
        apply_operation(root, create, owner)
    before = inspect_space(root, owner)
    completed = complete_deletions(root, owner)
    files = [
        entry
        for entry in (root / ".zara-core").iterdir()
        if entry.is_file() and entry.name.startswith("core.sqlite3")
    ]

    assert historical.value.code == "content_unavailable"
    assert removed_receipt.value.code == "not_found"
    assert removed_intent.value.code == "history_unavailable"
    assert before.pending_deletions == 1 and before.contaminated_backups == 1
    assert completed.live_store_sanitized and completed.pending_jobs == 0
    assert not backup.package.exists()
    assert all(sentinel not in entry.read_bytes() for entry in files)
    assert inspect_space(root, owner).contaminated_backups == 0


def test_delete_invalidates_backup_prepared_concurrently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, space_id, owner = ready_space(tmp_path)
    sentinel = b"CONCURRENT-BACKUP-DELETE-SENTINEL-440C"
    artifact_id = uuid4()
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            artifact_id=artifact_id,
            media_type="application/octet-stream",
            content=sentinel,
        ),
        owner,
    )
    backup_id = uuid4()
    prepared = Event()
    resume = Event()
    observed_package: list[Path] = []

    def pause_after_prepare(path: Path, identity: UUID, created_at: datetime) -> BackupInfo:
        backup = prepare_backup_database(path, identity, created_at)
        observed_package.append(backup.package)
        prepared.set()
        assert resume.wait(timeout=10)
        return backup

    monkeypatch.setattr(operation_module, "backup_database", pause_after_prepare)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(create_backup, root, backup_id, owner)
        assert prepared.wait(timeout=10)
        partial = observed_package[0]
        assert partial.name == f".{backup_id}.partial"
        assert sentinel in (partial / "core.sqlite3").read_bytes()
        with pytest.raises(FoundationError) as unpublished:
            restore_backup(
                partial,
                tmp_path / "never-restored",
                authorize_recovery(actor="owner", source_ref="fresh-recovery"),
            )
        apply_operation(
            root,
            DeleteArtifactRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor="owner",
                artifact_id=artifact_id,
                expected_revision=1,
            ),
            owner,
        )
        resume.set()
        with pytest.raises(FoundationError) as invalidated:
            future.result(timeout=10)

    completed = complete_deletions(root, owner)

    assert unpublished.value.code == "invalid_backup"
    assert invalidated.value.code == "backup_invalidated"
    assert completed.purged_backups == 1
    assert not partial.exists()
    assert not (partial.parent / str(backup_id)).exists()
    assert inspect_space(root, owner).contaminated_backups == 0


def test_backup_publication_is_honest_on_both_sides_of_inventory_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, owner = ready_space(tmp_path)
    backup_id = uuid4()
    published = Event()
    allow_commit = Event()
    committed = Event()
    allow_return = Event()
    original_rename = Path.rename

    def pause_after_publish(source: Path, target: Path) -> Path:
        result = original_rename(source, target)
        if source.name == f".{backup_id}.partial":
            published.set()
            assert allow_commit.wait(timeout=10)
        return result

    def pause_after_commit(package: Path) -> BackupInfo:
        committed.set()
        assert allow_return.wait(timeout=10)
        return load_backup_package(package)

    monkeypatch.setattr(Path, "rename", pause_after_publish)
    monkeypatch.setattr("zaratustra.foundation.operations.load_backup", pause_after_commit)
    final_package = root / ".zara-core" / "backups" / str(backup_id)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(create_backup, root, backup_id, owner)
        assert published.wait(timeout=10)
        assert final_package.is_dir()
        with pytest.raises(FoundationError) as precommit:
            load_backup_package(final_package)
        allow_commit.set()
        assert committed.wait(timeout=10)
        verified = load_backup_package(final_package)
        allow_return.set()
        completed = future.result(timeout=10)

    assert precommit.value.code == "invalid_backup"
    assert verified.manifest.backup_id == backup_id
    assert completed == verified
    assert inspect_space(root, owner).completed_backups == 1
