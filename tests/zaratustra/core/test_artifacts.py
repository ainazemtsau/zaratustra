"""Hidden consistency at file publication, DB commit, content read and rebuild."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier, Event
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from zaratustra.core import (
    Artifact,
    ArtifactError,
    ArtifactReference,
    InitialRecords,
    MutationError,
    MutationRequest,
    ProjectionRebuildError,
    Work,
    WorkspaceError,
    apply_mutation,
    authorize_local,
    create_initial_records,
    init_workspace,
    inspect_artifacts,
    migrate_workspace,
    prepare_authorization,
    read_artifact,
    read_history,
    read_projection_status,
    read_records,
    read_workspace,
    rebuild_projections,
)


def request_for(path: Path, operation: str, **changes: object) -> MutationRequest:
    snapshot = read_records(path)
    work = next(record for record in snapshot.records if isinstance(record, Work))
    artifact = next(record for record in snapshot.records if isinstance(record, Artifact))
    fields: dict[str, object] = dict(
        version=2,
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        work_id=work.id,
        expected_revision=snapshot.state_revision,
        operation=operation,
        provenance="Fictional Work 4 fixture; simulated prior owner permission",
    )
    if operation in ("authorize_artifact", "publish_artifact", "restore_artifact"):
        fields.update(artifact_id=artifact.id, artifact_revision=artifact.revision)
    return MutationRequest.model_validate(fields | changes)


def confirm(path: Path, request: MutationRequest) -> Any:
    return authorize_local(
        prepare_authorization(path, request),
        channel="local-chat",
        actor="fictional-adapter",
        source_ref="fixture:prior-owner-permission",
    )


def execute(path: Path, request: MutationRequest, content: bytes | None = None) -> Any:
    return apply_mutation(path, request, confirm(path, request), content=content)


def publication(path: Path, content: bytes, **changes: object) -> MutationRequest:
    return request_for(
        path,
        "publish_artifact",
        content_sha256=hashlib.sha256(content).hexdigest(),
        content_size=len(content),
        **changes,
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    init_workspace(tmp_path)
    migrate_workspace(tmp_path)
    create_initial_records(
        tmp_path,
        InitialRecords(
            process_title="Fictional observatory",
            goal="Describe an imaginary moon",
            expected_result="A fictional note",
            acceptance=("Saved observation",),
            boundaries=("Fictional only",),
            budget="One local trial",
            artifact_title="Observation",
        ),
    )
    execute(tmp_path, request_for(tmp_path, "authorize_work"))
    execute(tmp_path, request_for(tmp_path, "authorize_artifact"))
    return tmp_path


def test_v4_migration_preserves_v3_history_and_grants_nothing(tmp_path: Path) -> None:
    init_workspace(tmp_path)
    migrate_workspace(tmp_path, target_version=3)
    create_initial_records(
        tmp_path,
        InitialRecords(
            process_title="Fictional observatory",
            goal="Describe an imaginary moon",
            expected_result="A note",
            acceptance=("Saved",),
            boundaries=("Fictional",),
            budget="Local trial",
            artifact_title="Note",
        ),
    )
    v1 = request_for(tmp_path, "authorize_work", version=1)
    execute(tmp_path, v1)
    snapshot = read_records(tmp_path)
    history = read_history(tmp_path)
    db = read_workspace(tmp_path).database
    with closing(sqlite3.connect(db)) as connection:
        before = connection.execute("SELECT * FROM mutation_events").fetchall()
        migrations = connection.execute("SELECT * FROM schema_migrations").fetchall()
    assert migrate_workspace(tmp_path).schema_version == 4
    assert read_records(tmp_path) == snapshot and read_history(tmp_path) == history
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT * FROM mutation_events").fetchall() == before
        assert (
            connection.execute("SELECT * FROM schema_migrations WHERE version < 4").fetchall()
            == migrations
        )
    with pytest.raises(MutationError, match="permission_denied"):
        execute(tmp_path, publication(tmp_path, b"note"), b"note")
    migrated = db.read_bytes()
    migrate_workspace(tmp_path)
    assert db.read_bytes() == migrated


def test_versions_verified_reads_replay_and_registration_audit(workspace: Path) -> None:
    first = publication(workspace, b"first")
    receipt = execute(workspace, first, b"first")
    assert first.artifact_id is not None
    content = read_artifact(workspace, first.artifact_id)
    original_path = workspace / content.version.relative_path
    assert content.content == b"first" and content.version.id == first.operation_id
    assert receipt.affected_projections == ("overview.md",)
    with pytest.raises(MutationError, match="conflict"):
        execute(workspace, first, b"first")
    refreshed = first.model_copy(update={"expected_revision": receipt.new_revision})
    assert execute(workspace, refreshed) == receipt
    with pytest.raises(MutationError, match="collision"):
        execute(workspace, refreshed.model_copy(update={"provenance": "different intent"}))
    second = publication(workspace, b"second")
    execute(workspace, second, b"second")
    assert read_artifact(workspace, first.artifact_id).content == b"second"
    assert read_artifact(workspace, first.artifact_id, first.operation_id).content == b"first"
    assert original_path.read_bytes() == b"first"
    history = read_history(workspace)
    assert len(history.events) == len(history.receipts) == 4
    assert history.events[-1].artifact_before == history.events[-2].artifact_after
    assert len(inspect_artifacts(workspace).versions) == 2
    assert read_projection_status(workspace).status == "current"


@pytest.mark.parametrize(
    "stage",
    ["flush", "publish", "registration", "artifact", "work", "state", "event", "receipt", "commit"],
)
def test_failure_retains_db_and_retry_publishes_once(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    request = publication(workspace, b"retained file")
    caller = confirm(workspace, request)
    db = read_workspace(workspace).database
    before = db.read_bytes()
    snapshot = read_records(workspace)
    connect = sqlite3.connect

    def failing_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = connect(*args, **kwargs)

        def block(action: int, target: str | None, *_: object) -> int:
            blocked = {
                "registration": (sqlite3.SQLITE_INSERT, "artifact_versions"),
                "state": (sqlite3.SQLITE_UPDATE, "core_state"),
                "event": (sqlite3.SQLITE_INSERT, "mutation_events"),
                "receipt": (sqlite3.SQLITE_INSERT, "mutation_receipts"),
                "commit": (sqlite3.SQLITE_TRANSACTION, "COMMIT"),
            }.get(stage)
            if (action, target) == blocked:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(block)
        return connection

    class FailingConnection(sqlite3.Connection):
        count = 0

        def execute(self, sql: str, parameters: Any = (), /) -> sqlite3.Cursor:
            if sql.startswith("UPDATE core_records"):
                self.count += 1
                if (stage, self.count) in (("artifact", 1), ("work", 2)):
                    raise sqlite3.OperationalError("injected record write failure")
            return super().execute(sql, parameters)

    def fail_io(*_: object) -> None:
        raise OSError("injected file failure")

    with monkeypatch.context() as patch:
        if stage in ("flush", "publish"):
            patch.setattr(os, "fsync" if stage == "flush" else "link", fail_io)
        elif stage in ("artifact", "work"):
            patch.setattr(
                sqlite3, "connect", lambda *a, **k: connect(*a, factory=FailingConnection, **k)
            )
        else:
            patch.setattr(sqlite3, "connect", failing_connect)
        with pytest.raises(WorkspaceError):
            apply_mutation(workspace, request, caller, content=b"retained file")
    assert db.read_bytes() == before and read_records(workspace) == snapshot
    assert inspect_artifacts(workspace).versions == ()
    assert request.artifact_id is not None
    with pytest.raises(ArtifactError, match="registered"):
        read_artifact(workspace, request.artifact_id)
    receipt = apply_mutation(workspace, request, caller, content=b"retained file")
    assert receipt.new_revision == snapshot.state_revision + 1
    assert read_artifact(workspace, request.artifact_id).content == b"retained file"
    assert len(inspect_artifacts(workspace).versions) == 1


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_unavailable_content_refused_and_explicit_restore_audited(
    workspace: Path, damage: str
) -> None:
    original = publication(workspace, b"registered bytes")
    execute(workspace, original, b"registered bytes")
    assert original.artifact_id is not None
    descriptor = read_artifact(workspace, original.artifact_id).version
    file = workspace / descriptor.relative_path
    if damage == "missing":
        file.unlink()  # Negative file-loss fixture; recovery must use Core.
    else:
        file.write_bytes(b"damaged bytes")
    db = read_workspace(workspace).database
    before = db.read_bytes()
    with pytest.raises(ArtifactError):
        read_artifact(workspace, original.artifact_id)
    assert db.read_bytes() == before
    refreshed = original.model_copy(
        update={"expected_revision": read_records(workspace).state_revision}
    )
    assert execute(workspace, refreshed).operation_id == original.operation_id
    with pytest.raises(ArtifactError):
        read_artifact(workspace, original.artifact_id)
    repair = request_for(
        workspace,
        "restore_artifact",
        restore_version=descriptor.id,
        content_sha256=descriptor.sha256,
        content_size=descriptor.size,
    )
    with pytest.raises(ArtifactError, match="content_changed"):
        execute(workspace, repair, b"incorrect")
    execute(workspace, repair, b"registered bytes")
    assert read_artifact(workspace, original.artifact_id).version == descriptor
    assert read_artifact(workspace, original.artifact_id).content == b"registered bytes"
    inspection = inspect_artifacts(workspace)
    assert len(inspection.versions) == 1 and inspection.versions[0].status == "verified"
    if damage == "changed":
        assert len(inspection.unregistered_files) == 1
        assert (workspace / inspection.unregistered_files[0]).read_bytes() == b"damaged bytes"
    assert read_history(workspace).events[-1].request.operation == "restore_artifact"


def test_projection_failure_is_committed_and_rebuild_changes_no_db(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = publication(workspace, b"committed")
    previous = (workspace / "projections/overview.md").read_bytes()

    def fail(*_: object) -> None:
        raise OSError("injected replace failure")

    with monkeypatch.context() as patch:
        patch.setattr("zaratustra.core.projections.os.replace", fail)
        with pytest.raises(ProjectionRebuildError) as error:
            execute(workspace, request, b"committed")
    assert error.value.receipt.operation_id == request.operation_id
    assert (workspace / "projections/overview.md").read_bytes() == previous
    assert read_projection_status(workspace).status == "stale_or_changed"
    db = read_workspace(workspace).database
    before = db.read_bytes()
    assert rebuild_projections(workspace).status == "current"
    generated = (workspace / "projections/overview.md").read_bytes()
    assert rebuild_projections(workspace).status == "current"
    assert (workspace / "projections/overview.md").read_bytes() == generated
    (workspace / "projections/overview.md").unlink()
    assert read_projection_status(workspace).status == "missing"
    rebuild_projections(workspace)
    assert (workspace / "projections/overview.md").read_bytes() == generated
    assert db.read_bytes() == before


def test_exact_refs_bytes_and_current_scope_before_files(workspace: Path) -> None:
    request = publication(workspace, b"note")
    caller = confirm(workspace, request)
    db = read_workspace(workspace).database
    before = db.read_bytes()
    with pytest.raises(ArtifactError, match="content_changed"):
        apply_mutation(workspace, request, caller, content=b"altered")
    foreign = request.model_copy(update={"artifact_id": uuid4()})
    with pytest.raises(MutationError, match="permission_denied"):
        execute(workspace, foreign, b"note")
    assert db.read_bytes() == before
    execute(workspace, request, b"note")
    assert request.artifact_id is not None
    ref = ArtifactReference(
        artifact_id=request.artifact_id,
        version_id=request.operation_id,
        sha256=hashlib.sha256(b"note").hexdigest(),
    )
    good = request_for(
        workspace, "set_work_requirements", references=(ref,), requirements=("coding",)
    )
    execute(workspace, good)
    bad = request_for(
        workspace,
        "set_work_requirements",
        references=(ref.model_copy(update={"sha256": "0" * 64}),),
    )
    with pytest.raises(MutationError, match="invalid_artifact"):
        execute(workspace, bad)
    pending = publication(workspace, b"later")
    authorization = confirm(workspace, pending)
    execute(workspace, request_for(workspace, "revoke_work"))
    revoked = db.read_bytes()
    with pytest.raises(MutationError, match="permission_denied"):
        apply_mutation(workspace, pending, authorization, content=b"later")
    assert db.read_bytes() == revoked


def test_concurrent_publications_and_delayed_rebuild_use_latest_state(workspace: Path) -> None:
    barrier = Barrier(2)
    requests = [publication(workspace, content) for content in (b"a", b"b")]
    callers = [confirm(workspace, request) for request in requests]

    def run(index: int) -> str:
        barrier.wait()
        try:
            apply_mutation(workspace, requests[index], callers[index], content=(b"a", b"b")[index])
            return "committed"
        except MutationError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, range(2))) == ["committed", "conflict"]
    assert len(inspect_artifacts(workspace).versions) == 1
    assert read_projection_status(workspace).status == "current"


def test_delayed_rebuild_cannot_overwrite_newer_projection(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import zaratustra.core.mutations as mutations

    entered, resume = Event(), Event()
    original = mutations.rebuild_projections
    first_request = publication(workspace, b"first")

    def delayed(path: Path) -> Any:
        entered.set()
        if not resume.wait(5):
            raise RuntimeError("test synchronization timeout")
        return original(path)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with monkeypatch.context() as patch:
            patch.setattr(mutations, "rebuild_projections", delayed)
            future = pool.submit(execute, workspace, first_request, b"first")
            assert entered.wait(5)
        second = publication(workspace, b"second")
        execute(workspace, second, b"second")
        latest = (workspace / "projections/overview.md").read_bytes()
        resume.set()
        future.result()
    assert (workspace / "projections/overview.md").read_bytes() == latest
    assert (
        read_projection_status(workspace).generated_from_revision
        == read_records(workspace).state_revision
    )


def test_v1_cannot_smuggle_artifact_fields_and_v2_rejects_paths(workspace: Path) -> None:
    request = publication(workspace, b"data")
    with pytest.raises(ValidationError):
        MutationRequest.model_validate({**request.model_dump(), "version": 1})
    with pytest.raises(ValidationError):
        MutationRequest.model_validate({**request.model_dump(), "path": "outside"})
    old = request_for(workspace, "set_work_requirements", version=1)
    with pytest.raises(ValidationError):
        execute(workspace, old.model_copy(update={"content_size": 42}))
    assert inspect_artifacts(workspace).versions == ()


def test_rebuild_and_content_repair_after_directory_loss(workspace: Path) -> None:
    request = publication(workspace, b"lost file")
    execute(workspace, request, b"lost file")
    assert request.artifact_id is not None
    descriptor = read_artifact(workspace, request.artifact_id).version
    projection = workspace / "projections/overview.md"
    generated = projection.read_bytes()
    projection.unlink()
    projection.parent.rmdir()
    before = read_workspace(workspace).database.read_bytes()
    assert read_records(workspace).state_revision == 4
    assert rebuild_projections(workspace).status == "current"
    assert projection.read_bytes() == generated
    assert read_workspace(workspace).database.read_bytes() == before
    content = workspace / descriptor.relative_path
    content.unlink()
    content.parent.rmdir()
    content.parent.parent.rmdir()
    assert read_history(workspace).state_revision == 4
    with pytest.raises(ArtifactError, match="content_unavailable"):
        read_artifact(workspace, request.artifact_id)
    repair = request_for(
        workspace,
        "restore_artifact",
        restore_version=descriptor.id,
        content_sha256=descriptor.sha256,
        content_size=descriptor.size,
    )
    execute(workspace, repair, b"lost file")
    assert read_artifact(workspace, request.artifact_id).content == b"lost file"


def test_v4_migration_failure_retains_exact_v3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_workspace(tmp_path)
    migrate_workspace(tmp_path, target_version=3)
    database = read_workspace(tmp_path).database
    before = database.read_bytes()
    connect = sqlite3.connect

    def failing_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = connect(*args, **kwargs)
        connection.set_authorizer(
            lambda action, table, *_: (
                sqlite3.SQLITE_DENY
                if (action, table) == (sqlite3.SQLITE_INSERT, "schema_migrations")
                else sqlite3.SQLITE_OK
            )
        )
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", failing_connect)
        with pytest.raises(WorkspaceError):
            migrate_workspace(tmp_path)
    assert database.read_bytes() == before and read_workspace(tmp_path).schema_version == 3
    assert migrate_workspace(tmp_path).schema_version == 4


def test_missing_reference_and_terminal_work_refuse_without_files(workspace: Path) -> None:
    original = publication(workspace, b"reference")
    execute(workspace, original, b"reference")
    assert original.artifact_id is not None
    descriptor = read_artifact(workspace, original.artifact_id).version
    (workspace / descriptor.relative_path).unlink()
    reference = ArtifactReference(
        artifact_id=descriptor.artifact_id, version_id=descriptor.id, sha256=descriptor.sha256
    )
    request = publication(workspace, b"dependent", references=(reference,))
    before = read_workspace(workspace).database.read_bytes()
    with pytest.raises(ArtifactError, match="content_unavailable"):
        execute(workspace, request, b"dependent")
    assert read_workspace(workspace).database.read_bytes() == before
    execute(workspace, request_for(workspace, "cancel_work"))
    cancelled = read_workspace(workspace).database.read_bytes()
    for operation in ("authorize_work", "authorize_artifact", "publish_artifact"):
        terminal = (
            publication(workspace, b"new")
            if operation == "publish_artifact"
            else request_for(workspace, operation)
        )
        with pytest.raises(MutationError, match="permission_denied"):
            execute(workspace, terminal, b"new" if operation == "publish_artifact" else None)
    assert read_workspace(workspace).database.read_bytes() == cancelled


def test_cli_returns_committed_receipt_on_rebuild_failure(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from zaratustra.cli import main

    request = request_for(workspace, "set_work_requirements", requirements=("coding",))
    caller = confirm(workspace, request)
    monkeypatch.setattr("zaratustra.cli.confirm_on_console", lambda _: caller)

    def fail(*_: object) -> None:
        raise OSError("injected projection failure")

    monkeypatch.setattr("zaratustra.core.mutations.write_projection", fail)
    assert main(["mutate", str(workspace), request.model_dump_json()]) == 2
    delivered = json.loads(capsys.readouterr().out)
    assert delivered["status"] == "rebuild_required"
    assert delivered["receipt"] == read_history(workspace).receipts[-1].model_dump(mode="json")
    assert read_records(workspace).state_revision == request.expected_revision + 1


def test_interrupted_restore_retains_damage_and_retries_without_active_switch(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = publication(workspace, b"original")
    execute(workspace, original, b"original")
    assert original.artifact_id is not None
    descriptor = read_artifact(workspace, original.artifact_id).version
    (workspace / descriptor.relative_path).write_bytes(b"damage")
    repair = request_for(
        workspace,
        "restore_artifact",
        restore_version=descriptor.id,
        content_sha256=descriptor.sha256,
        content_size=descriptor.size,
    )
    db = read_workspace(workspace).database
    before = db.read_bytes()

    def fail(*_: object) -> None:
        raise OSError("interrupted repair publication")

    with monkeypatch.context() as patch:
        patch.setattr(os, "link", fail)
        with pytest.raises(ArtifactError, match="publication_failed"):
            execute(workspace, repair, b"original")
    assert db.read_bytes() == before
    retained = inspect_artifacts(workspace).unregistered_files
    assert any((workspace / name).read_bytes() == b"damage" for name in retained)
    execute(workspace, repair, b"original")
    assert read_artifact(workspace, original.artifact_id).version == descriptor
    assert read_artifact(workspace, original.artifact_id).content == b"original"
