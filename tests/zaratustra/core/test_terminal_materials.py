"""Schema-8 compatibility, terminal Result and Process-owned material behavior."""

from __future__ import annotations

import hashlib
import sqlite3
import zipfile
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from zaratustra.core import (
    ArtifactError,
    ArtifactReference,
    Event,
    LocalAuthorization,
    MutationError,
    MutationRequest,
    NextWork,
    Process,
    ProcessMaterialQuery,
    ProcessMaterialRequest,
    ProcessMaterialSubmission,
    ProcessReceiptQuery,
    ProcessStateQuery,
    ReceiptQuery,
    ResultSubmission,
    TerminalResultSubmission,
    Work,
    WorkspaceError,
    authorize_local,
    migrate_workspace,
    prepare_authorization,
    read_handoffs,
    read_history,
    read_process_material,
    read_process_receipt,
    read_process_state,
    read_records,
    read_result,
    read_workspace,
    save_process_material,
    submit_result,
)

ExactQuery = ReceiptQuery | ProcessStateQuery | ProcessMaterialQuery | ProcessReceiptQuery


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    archive = Path(__file__).resolve().parents[3] / "docs/work6/evidence/retained-trial.zip"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(
            tmp_path / "selected",
            [name for name in bundle.namelist() if name.startswith("workspace/")],
        )
    selected = tmp_path / "selected/workspace"
    migrate_workspace(selected, target_version=6)
    return selected


def confirm(
    path: Path, value: MutationRequest | ProcessMaterialRequest | ExactQuery
) -> LocalAuthorization:
    return authorize_local(
        prepare_authorization(path, value),
        channel="local-chat",
        actor="fictional-terminal-test-adapter",
        source_ref="public-onboarding-r2-t1:simulated-prior-permission",
    )


def source(path: Path) -> tuple[UUID, Work, tuple[UUID, ...], ArtifactReference]:
    snapshot = read_records(path)
    initial = next(record for record in snapshot.records if isinstance(record, Event))
    work = next(
        record
        for record in snapshot.records
        if isinstance(record, Work) and record.id == initial.work_id
    )
    accepted = read_handoffs(path)
    return (
        snapshot.workspace_id,
        work,
        tuple(row.handoff.handoff_id for row in accepted),
        accepted[0].handoff.result,
    )


def result_request(path: Path, *, terminal: bool) -> MutationRequest:
    snapshot = read_records(path)
    workspace_id, work, acceptance_ids, result = source(path)
    continuation = None
    if not terminal:
        continuation = NextWork(
            work_id=uuid4(),
            artifact_id=uuid4(),
            goal="Compare two fictional lunar notes",
            expected_result="One concise fictional comparison",
            acceptance=("Retain both fictional observations",),
            boundaries=("No external action",),
            budget="One bounded local test",
            executor_requirements=(),
            artifact_title="Fictional comparison",
            authority_scope="work_metadata",
        )
    return MutationRequest(
        version=6 if terminal else 4,
        operation_id=uuid4(),
        workspace_id=workspace_id,
        work_id=work.id,
        expected_revision=snapshot.state_revision,
        operation="submit_result",
        provenance="Exact fictional terminal-result fixture",
        references=(result,),
        submission=(
            ResultSubmission(
                source_revision=snapshot.state_revision,
                result=result,
                acceptance_ids=acceptance_ids,
                next_work=continuation,
            )
            if continuation is not None
            else None
        ),
        terminal_submission=(
            TerminalResultSubmission(
                source_revision=snapshot.state_revision,
                result=result,
                acceptance_ids=acceptance_ids,
            )
            if terminal
            else None
        ),
    )


def raw_result_rows(
    path: Path,
) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    database = read_workspace(path).database
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        return (
            connection.execute("SELECT * FROM work_results ORDER BY operation_id").fetchall(),
            connection.execute("SELECT * FROM mutation_events ORDER BY state_revision").fetchall(),
            connection.execute("SELECT * FROM mutation_receipts ORDER BY operation_id").fetchall(),
        )


def test_schema8_preserves_released_result_next_rows_and_restart(workspace: Path) -> None:
    request = result_request(workspace, terminal=False)
    receipt = submit_result(workspace, request, confirm(workspace, request))
    released_rows = raw_result_rows(workspace)
    released_history = read_history(workspace)
    assert read_workspace(workspace).schema_version == 6

    assert migrate_workspace(workspace, target_version=8).schema_version == 8
    assert raw_result_rows(workspace) == released_rows
    assert read_history(workspace) == released_history
    query = ReceiptQuery(
        workspace_id=request.workspace_id,
        work_id=request.work_id,
        operation_id=request.operation_id,
    )
    saved = read_result(workspace, query, confirm(workspace, query))
    assert saved.receipt == receipt
    assert request.submission is not None and request.submission.next_work is not None
    assert saved.next_work_id == request.submission.next_work.work_id
    assert read_records(workspace).current_work is not None


def test_terminal_result_has_no_hidden_current_and_survives_restart(workspace: Path) -> None:
    migrate_workspace(workspace, target_version=8)
    before = read_records(workspace)
    request = result_request(workspace, terminal=True)
    receipt = submit_result(workspace, request, confirm(workspace, request))
    after = read_records(workspace)
    assert len(after.records) == len(before.records)
    assert after.state_revision == before.state_revision + 1
    assert after.current_work is None
    work = next(record for record in after.records if isinstance(record, Work))
    assert work.status == "done" and work.completion_id == request.operation_id

    query = ReceiptQuery(
        workspace_id=request.workspace_id,
        work_id=request.work_id,
        operation_id=request.operation_id,
    )
    saved = read_result(workspace, query, confirm(workspace, query))
    assert saved.receipt == receipt and saved.next_work_id is None
    process = next(record for record in after.records if isinstance(record, Process))
    state_query = ProcessStateQuery(
        workspace_id=after.workspace_id,
        process_id=process.id,
        expected_revision=after.state_revision,
    )
    process_state = read_process_state(workspace, state_query, confirm(workspace, state_query))
    assert process_state.current_work is None
    assert process_state.process.id == process.id
    assert tuple(row.event.request.operation_id for row in process_state.results) == (
        request.operation_id,
    )


def material_request(
    path: Path,
    content: bytes,
    *,
    operation_id: UUID | None = None,
    material_id: UUID | None = None,
) -> ProcessMaterialRequest:
    snapshot = read_records(path)
    process = next(record for record in snapshot.records if isinstance(record, Process))
    return ProcessMaterialRequest(
        operation_id=operation_id or uuid4(),
        workspace_id=snapshot.workspace_id,
        process_id=process.id,
        expected_revision=snapshot.state_revision,
        provenance="Fictional Process note, explicitly retained",
        material=ProcessMaterialSubmission(
            material_id=material_id or uuid4(),
            title="Fictional post-terminal note",
            media_type="text/plain; charset=utf-8",
            content_sha256=hashlib.sha256(content).hexdigest(),
            content_size=len(content),
        ),
    )


def terminal_workspace(path: Path) -> None:
    migrate_workspace(path, target_version=8)
    request = result_request(path, terminal=True)
    submit_result(path, request, confirm(path, request))


def test_process_material_post_terminal_exact_read_replay_collision_and_denial(
    workspace: Path,
) -> None:
    terminal_workspace(workspace)
    before = read_records(workspace)
    works_before = tuple(record for record in before.records if isinstance(record, Work))
    content = b"The fictional observatory keeps the silver rim note.\n"
    request = material_request(workspace, content)

    with pytest.raises(MutationError, match="permission_denied"):
        save_process_material(workspace, request, content=content)
    assert read_records(workspace) == before
    with pytest.raises(ArtifactError, match="content_changed"):
        save_process_material(workspace, request, confirm(workspace, request), content=b"changed")
    assert read_records(workspace) == before

    receipt = save_process_material(
        workspace, request, confirm(workspace, request), content=content
    )
    saved = read_records(workspace)
    assert saved.state_revision == before.state_revision + 1 and saved.current_work is None
    assert tuple(record for record in saved.records if isinstance(record, Work)) == works_before
    assert receipt.process_id == request.process_id

    replay = request.model_copy(update={"expected_revision": saved.state_revision})
    assert (
        save_process_material(workspace, replay, confirm(workspace, replay), content=content)
        == receipt
    )
    assert read_records(workspace) == saved

    assert request.material is not None and request.process_id is not None
    collision = replay.model_copy(
        update={"material": request.material.model_copy(update={"title": "Different intent"})}
    )
    with pytest.raises(MutationError, match="collision"):
        save_process_material(workspace, collision, confirm(workspace, collision), content=content)
    wrong_process = replay.model_copy(update={"process_id": uuid4()})
    with pytest.raises(MutationError, match="permission_denied"):
        save_process_material(workspace, wrong_process, confirm(workspace, replay), content=content)
    stale = material_request(workspace, content).model_copy(
        update={"expected_revision": before.state_revision}
    )
    with pytest.raises(MutationError, match="conflict"):
        save_process_material(workspace, stale, confirm(workspace, stale), content=content)
    reused_material = material_request(workspace, content, material_id=request.material.material_id)
    with pytest.raises(MutationError, match="collision"):
        save_process_material(
            workspace,
            reused_material,
            confirm(workspace, reused_material),
            content=content,
        )
    assert read_records(workspace) == saved

    material_query = ProcessMaterialQuery(
        workspace_id=saved.workspace_id,
        process_id=request.process_id,
        material_id=request.material.material_id,
        expected_revision=saved.state_revision,
    )
    with pytest.raises(MutationError, match="permission_denied"):
        read_process_material(workspace, material_query)
    retained = read_process_material(workspace, material_query, confirm(workspace, material_query))
    assert retained.content == content and retained.material.id == request.material.material_id
    receipt_query = ProcessReceiptQuery(
        workspace_id=saved.workspace_id,
        process_id=request.process_id,
        operation_id=request.operation_id,
        expected_revision=saved.state_revision,
    )
    assert (
        read_process_receipt(workspace, receipt_query, confirm(workspace, receipt_query)) == receipt
    )


def test_material_transaction_failure_leaves_no_record_event_or_receipt(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    terminal_workspace(workspace)
    content = b"Atomic fictional note\n"
    request = material_request(workspace, content)
    caller = confirm(workspace, request)
    before = read_records(workspace)
    history = read_history(workspace)
    connect = sqlite3.connect

    def fail(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = connect(*args, **kwargs)

        def deny(
            action: int,
            table: str | None,
            _column: str | None,
            _database: str | None,
            _trigger: str | None,
        ) -> int:
            if action == sqlite3.SQLITE_INSERT and table == "process_materials":
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(deny)
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", fail)
        with pytest.raises(WorkspaceError):
            save_process_material(workspace, request, caller, content=content)
    assert read_records(workspace) == before
    assert read_history(workspace) == history
