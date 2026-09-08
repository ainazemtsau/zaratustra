"""Persistence, integrity and refusal checks for invisible initial-record state."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from zaratustra.core import (
    Artifact,
    Event,
    InitialRecords,
    Work,
    WorkspaceError,
    create_initial_records,
    init_workspace,
    migrate_workspace,
    read_records,
    read_workspace,
)
from zaratustra.core.migration_v2 import V2_NAME, V2_SHA256


@pytest.fixture
def draft() -> InitialRecords:
    return InitialRecords(
        process_title="Fictional observatory",
        goal="Describe an imaginary moon",
        expected_result="A short fictional observation",
        acceptance=("The observation is saved",),
        boundaries=("Fictional data only",),
        budget="One short local session",
        artifact_title="Observation draft",
    )


def test_explicit_migration_preserves_bootstrap_and_repeat_bytes(tmp_path: Path) -> None:
    original = init_workspace(tmp_path)
    before = original.database.read_bytes()
    with pytest.raises(WorkspaceError, match="migrate explicitly"):
        read_records(tmp_path)
    assert original.database.read_bytes() == before
    upgraded = migrate_workspace(tmp_path)
    assert upgraded.workspace_id == original.workspace_id
    assert upgraded.created_at == original.created_at
    assert upgraded.schema_version == 2
    with closing(sqlite3.connect(original.database)) as connection:
        assert connection.execute(
            "SELECT version, name, sha256 FROM schema_migrations WHERE version = 2"
        ).fetchone() == (2, V2_NAME, V2_SHA256)
    migrated_bytes = original.database.read_bytes()
    assert migrate_workspace(tmp_path) == upgraded
    assert init_workspace(tmp_path) == upgraded
    assert read_records(tmp_path).records == ()
    assert read_records(tmp_path).state_revision == 0
    assert original.database.read_bytes() == migrated_bytes


def test_records_restart_preserves_all_fields_revisions_and_links(
    tmp_path: Path, draft: InitialRecords
) -> None:
    info = init_workspace(tmp_path)
    migrate_workspace(tmp_path)
    created = create_initial_records(tmp_path, draft)
    before = info.database.read_bytes()
    reopened = read_records(tmp_path)
    assert created == reopened
    assert reopened.workspace_id == info.workspace_id
    assert reopened.state_revision == 1
    assert {record.kind for record in reopened.records} == {"process", "work", "artifact", "event"}
    assert {record.revision for record in reopened.records} == {1}
    work = next(record for record in reopened.records if isinstance(record, Work))
    artifact = next(record for record in reopened.records if isinstance(record, Artifact))
    event = next(record for record in reopened.records if isinstance(record, Event))
    assert work.goal == draft.goal and work.acceptance == draft.acceptance
    assert work.authority_scope == "none" and work.status == "draft"
    assert artifact.active_version is None and artifact.work_id == work.id
    assert event.affected_ids == (work.process_id, work.id, artifact.id)
    assert event.product_version == "0.2.0"
    with pytest.raises(WorkspaceError, match="already exist"):
        create_initial_records(tmp_path, draft)
    assert info.database.read_bytes() == before
    assert list((tmp_path / "artifacts").iterdir()) == []
    assert list((tmp_path / "projections").iterdir()) == []


def test_initial_records_refuse_schema_one_without_mutation(
    tmp_path: Path, draft: InitialRecords
) -> None:
    info = init_workspace(tmp_path)
    before = info.database.read_bytes()
    with pytest.raises(WorkspaceError, match="migrate explicitly"):
        create_initial_records(tmp_path, draft)
    assert info.database.read_bytes() == before


def test_bootstrap_inputs_cannot_self_grant_or_supply_state(draft: InitialRecords) -> None:
    for field in ("approved", "actor", "authority_scope", "id", "revision", "active_version"):
        with pytest.raises(ValidationError):
            InitialRecords.model_validate({**draft.model_dump(), field: "owner"})
    with pytest.raises(ValidationError):
        InitialRecords.model_validate({**draft.model_dump(), "goal": "  "})


def test_migration_failure_leaves_original_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    info = init_workspace(tmp_path)
    before = info.database.read_bytes()
    connect = sqlite3.connect

    def failing_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = connect(*args, **kwargs)

        def deny_state(action: int, table: str | None, *_: object) -> int:
            return (
                sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_INSERT and table == "core_state"
                else sqlite3.SQLITE_OK
            )

        connection.set_authorizer(deny_state)
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", failing_connect)
        with pytest.raises(WorkspaceError):
            migrate_workspace(tmp_path)
    assert read_workspace(tmp_path) == info
    assert info.database.read_bytes() == before
    assert migrate_workspace(tmp_path).schema_version == 2


def test_event_insert_failure_rolls_back_records_and_revision(
    tmp_path: Path, draft: InitialRecords, monkeypatch: pytest.MonkeyPatch
) -> None:
    info = init_workspace(tmp_path)
    migrate_workspace(tmp_path)
    before = info.database.read_bytes()
    connect = sqlite3.connect

    def failing_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = connect(*args, **kwargs)
        connection.execute(
            "CREATE TEMP TRIGGER fail_event BEFORE INSERT ON core_records "
            "WHEN NEW.kind = 'event' BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
        )
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", failing_connect)
        with pytest.raises(WorkspaceError, match="injected failure"):
            create_initial_records(tmp_path, draft)
    assert read_records(tmp_path).state_revision == 0
    assert read_records(tmp_path).records == ()
    assert info.database.read_bytes() == before
    assert create_initial_records(tmp_path, draft).state_revision == 1


@pytest.mark.parametrize("damage", ["foreign-process", "missing-event", "revision", "migration"])
def test_invalid_stored_records_are_refused_without_repair(
    tmp_path: Path, draft: InitialRecords, damage: str
) -> None:
    info = init_workspace(tmp_path)
    migrate_workspace(tmp_path)
    create_initial_records(tmp_path, draft)
    # Deliberately corrupt disposable fixtures; never repair the passing runtime trial.
    with closing(sqlite3.connect(info.database, autocommit=True)) as connection:
        if damage == "foreign-process":
            body = json.loads(
                connection.execute(
                    "SELECT body FROM core_records WHERE kind = 'artifact'"
                ).fetchone()[0]
            )
            body["process_id"] = str(uuid4())
            connection.execute(
                "UPDATE core_records SET body = ? WHERE kind = 'artifact'", (json.dumps(body),)
            )
        elif damage == "missing-event":
            connection.execute("DELETE FROM core_records WHERE kind = 'event'")
        elif damage == "revision":
            connection.execute("UPDATE core_records SET revision = 2 WHERE kind = 'work'")
        else:
            connection.execute("UPDATE schema_migrations SET sha256 = 'wrong' WHERE version = 2")
    before = info.database.read_bytes()
    with pytest.raises(WorkspaceError):
        read_records(tmp_path)
    with pytest.raises(WorkspaceError):
        create_initial_records(tmp_path, draft)
    assert info.database.read_bytes() == before
