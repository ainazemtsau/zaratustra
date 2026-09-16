"""Standalone bootstrap, material history and preservation of released data."""

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from zaratustra.core import (
    Event,
    InitialProcess,
    Process,
    ProcessMaterialQuery,
    ProcessMaterialRequest,
    ProcessMaterialSubmission,
    Work,
    WorkspaceError,
    authorize_local,
    create_process,
    init_workspace,
    migrate_workspace,
    prepare_authorization,
    read_history,
    read_process_material,
    read_records,
    save_process_material,
)


def test_standalone_material_survives_reopen_and_exact_retry(tmp_path: Path) -> None:
    init_workspace(tmp_path)
    migrate_workspace(tmp_path, target_version=10)
    initial = InitialProcess(
        title="Учебные заметки", purpose="Собирать материалы", operation_id=uuid4()
    )
    snapshot = create_process(tmp_path, initial)
    process = next(row for row in snapshot.records if isinstance(row, Process))
    assert len(snapshot.records) == 2
    assert not any(isinstance(row, Work) for row in snapshot.records)
    assert next(row for row in snapshot.records if isinstance(row, Event)).work_id is None
    content = "Исходный материал".encode()
    request = ProcessMaterialRequest(
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        process_id=process.id,
        expected_revision=1,
        provenance="owner: save this material",
        material=ProcessMaterialSubmission(
            material_id=uuid4(),
            title="Источник",
            media_type="text/plain",
            content_sha256=hashlib.sha256(content).hexdigest(),
            content_size=len(content),
        ),
    )
    permission = authorize_local(
        prepare_authorization(tmp_path, request),
        channel="local-chat",
        actor="test host",
        source_ref="explicit fictional instruction",
    )
    receipt = save_process_material(tmp_path, request, permission, content=content)
    reopened = read_records(tmp_path)
    assert reopened.state_revision == 2
    assert create_process(tmp_path, initial) == reopened
    assert not any(isinstance(row, Work) for row in reopened.records)
    query = ProcessMaterialQuery(
        workspace_id=snapshot.workspace_id,
        process_id=process.id,
        expected_revision=2,
        material_id=request.material.material_id,
    )
    read_permission = authorize_local(
        prepare_authorization(tmp_path, query),
        channel="local-chat",
        actor="new test host",
        source_ref="explicit fictional read",
    )
    assert read_process_material(tmp_path, query, read_permission).content == content
    assert len(read_history(tmp_path).process_events) == 1
    assert receipt.new_revision == 2
    with pytest.raises(WorkspaceError, match="intent differs"):
        create_process(tmp_path, initial.model_copy(update={"purpose": "Changed"}))


def test_standalone_requires_explicit_migration(tmp_path: Path) -> None:
    init_workspace(tmp_path)
    migrate_workspace(tmp_path, target_version=9)
    before = (tmp_path / ".zara" / "state.sqlite3").read_bytes()
    with pytest.raises(WorkspaceError, match="schema 10"):
        create_process(
            tmp_path, InitialProcess(title="Notes", purpose="Collect", operation_id=uuid4())
        )
    assert (tmp_path / ".zara" / "state.sqlite3").read_bytes() == before
