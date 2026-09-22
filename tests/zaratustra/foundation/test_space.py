from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from zaratustra.foundation import (
    BootstrapRequest,
    FoundationError,
    LocalAuthority,
    OperationReceipt,
    SpaceInfo,
    apply_operation,
    authorize_local,
    initialize_space,
    inspect_space,
    read_space,
)


def bootstrap(
    root: Path, actor: str = "owner-local"
) -> tuple[SpaceInfo, LocalAuthority, OperationReceipt]:
    info = initialize_space(root)
    authority = authorize_local(root, actor=actor, source_ref="synthetic-owner-confirmation")
    receipt = apply_operation(
        root,
        BootstrapRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=actor,
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        authority,
    )
    return info, authority, receipt


def test_empty_space_has_own_identity_and_reopens_without_domain_state(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    created = initialize_space(root)
    reopened = read_space(root)

    assert reopened == created
    assert reopened.state_revision == 0
    assert reopened.database == root / ".zara-core" / "core.sqlite3"
    assert list((root / ".zara-core" / "backups").iterdir()) == []


def test_initialization_refuses_legacy_or_nonempty_directory_without_change(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    legacy = root / ".zara" / "state.sqlite3"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"legacy sentinel")

    with pytest.raises(FoundationError, match="empty") as refusal:
        initialize_space(root)

    assert refusal.value.code == "layout"
    assert legacy.read_bytes() == b"legacy sentinel"
    assert not (root / ".zara-core").exists()


def test_unknown_schema_is_refused_without_replacement_or_migration(tmp_path: Path) -> None:
    root = tmp_path / "space"
    root.mkdir()
    created = initialize_space(root)
    with sqlite3.connect(created.database) as connection:
        connection.execute("PRAGMA user_version = 99")
    before = {
        path.name: path.read_bytes()
        for path in created.database.parent.iterdir()
        if path.is_file()
        and path.name.startswith("core.sqlite3")
        and not path.name.endswith("-shm")
    }

    with pytest.raises(FoundationError) as refusal:
        read_space(root)
    after = {
        path.name: path.read_bytes()
        for path in created.database.parent.iterdir()
        if path.is_file()
        and path.name.startswith("core.sqlite3")
        and not path.name.endswith("-shm")
    }

    assert refusal.value.code == "unsupported_schema"
    assert after == before
    with sqlite3.connect(created.database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (99,)


def test_model_free_inspection_sees_bootstrap_records_and_no_payload(tmp_path: Path) -> None:
    root = tmp_path / "space"
    root.mkdir()
    _, authority, receipt = bootstrap(root)

    inspection = inspect_space(root, authority)

    assert inspection.operation_count == 1
    assert inspection.audit_count == 1
    assert inspection.receipt_count == 1
    assert {record.kind for record in inspection.records} == {"decision", "grant"}
    assert receipt.state_revision == inspection.space.state_revision


def test_import_refuses_unfixed_sqlite_runtime_in_a_fresh_process() -> None:
    environment = os.environ.copy()
    environment.pop("ZARATUSTRA_SQLITE_DLL", None)
    result = subprocess.run(
        [sys.executable, "-c", "import zaratustra.foundation"],
        check=False,
        capture_output=True,
        encoding="utf-8",
        env=environment,
    )

    assert result.returncode != 0
    assert "Unsupported SQLite runtime" in result.stderr
