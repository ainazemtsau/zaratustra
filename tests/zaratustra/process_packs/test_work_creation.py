"""Truthful Process resume and explicit Pack-compatible ordinary Work admission."""

from __future__ import annotations

import hashlib
import sqlite3
import zipfile
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from zaratustra.core import (
    AmbiguousCurrentWorkError,
    Artifact,
    ArtifactReference,
    Handoff,
    LocalAuthorization,
    MutationError,
    MutationRequest,
    NextWork,
    PackReference,
    Process,
    ProcessMaterialRequest,
    ProcessMaterialSubmission,
    ProcessReceiptQuery,
    ProcessStateQuery,
    TerminalResultSubmission,
    Work,
    WorkCreationRequest,
    WorkspaceError,
    apply_mutation,
    authorize_local,
    create_work,
    handoff_request,
    migrate_workspace,
    prepare_authorization,
    read_handoffs,
    read_history,
    read_process_receipt,
    read_process_state,
    read_records,
    read_workspace,
    save_process_material,
    submit_result,
)
from zaratustra.process_packs import (
    PackError,
    PackRegistration,
    PackRegistry,
    binding_request,
    create_later_work,
    work_creation_request,
)

ExactRequest = (
    MutationRequest
    | ProcessMaterialRequest
    | WorkCreationRequest
    | ProcessStateQuery
    | ProcessReceiptQuery
)


class NoFollowingRule:
    def next_work(
        self,
        work: Work,
        accepted_result: bytes,
        work_id: UUID,
        artifact_id: UUID,
    ) -> NextWork | None:
        del work, accepted_result, work_id, artifact_id
        return None


REFERENCE = PackReference(
    pack_id="fictional.resume",
    pack_version="1.0.0",
    process_type="fictional_resume",
    contract_version=1,
    state_version=1,
)
REGISTRATION = PackRegistration(reference=REFERENCE, rule=NoFollowingRule())
REGISTRY = PackRegistry((REGISTRATION,))


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    archive = Path(__file__).resolve().parents[3] / "docs/work6/evidence/retained-trial.zip"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(
            tmp_path / "selected",
            [name for name in bundle.namelist() if name.startswith("workspace/")],
        )
    selected = tmp_path / "selected/workspace"
    migrate_workspace(selected, target_version=8)
    bind_current(selected)
    finish_current(selected)
    return selected


@pytest.fixture
def unbound_workspace(tmp_path: Path) -> Path:
    archive = Path(__file__).resolve().parents[3] / "docs/work6/evidence/retained-trial.zip"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(
            tmp_path / "unbound",
            [name for name in bundle.namelist() if name.startswith("workspace/")],
        )
    selected = tmp_path / "unbound/workspace"
    migrate_workspace(selected, target_version=8)
    finish_current(selected)
    migrate_workspace(selected, target_version=9)
    return selected


def confirm(path: Path, value: ExactRequest) -> LocalAuthorization:
    return authorize_local(
        prepare_authorization(path, value),
        channel="local-chat",
        actor="fictional-resume-test-adapter",
        source_ref="public-onboarding-r2-t2:simulated-prior-permission",
    )


def process_and_current(path: Path) -> tuple[Process, Work | None]:
    snapshot = read_records(path)
    process = next(record for record in snapshot.records if isinstance(record, Process))
    return process, snapshot.current_work


def bind_current(path: Path) -> None:
    snapshot = read_records(path)
    current = snapshot.current_work
    assert current is not None
    request = binding_request(
        REGISTRY,
        REFERENCE,
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        work_id=current.id,
        expected_revision=snapshot.state_revision,
        provenance="Bind exact fictional resume Pack",
    )
    apply_mutation(path, request, confirm(path, request))


def finish_current(path: Path) -> None:
    snapshot = read_records(path)
    current = snapshot.current_work
    assert current is not None
    accepted = tuple(row for row in read_handoffs(path) if row.handoff.related_work == current.id)
    assert accepted
    result = accepted[-1].handoff.result
    request = MutationRequest(
        version=6,
        operation="submit_result",
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        work_id=current.id,
        expected_revision=snapshot.state_revision,
        provenance="Finish exact fictional Work without a continuation",
        references=(result,),
        terminal_submission=TerminalResultSubmission(
            source_revision=snapshot.state_revision,
            result=result,
            acceptance_ids=tuple(row.handoff.handoff_id for row in accepted),
        ),
    )
    submit_result(path, request, confirm(path, request))


def state_query(path: Path) -> ProcessStateQuery:
    snapshot = read_records(path)
    process, _ = process_and_current(path)
    return ProcessStateQuery(
        workspace_id=snapshot.workspace_id,
        process_id=process.id,
        expected_revision=snapshot.state_revision,
    )


def later_spec(*, work_id: UUID | None = None, artifact_id: UUID | None = None) -> NextWork:
    return NextWork(
        work_id=work_id or uuid4(),
        artifact_id=artifact_id or uuid4(),
        goal="Compare the retained fictional observatory notes",
        expected_result="One verified fictional comparison",
        acceptance=("Name both retained fictional observations",),
        boundaries=("No external action or real personal data",),
        budget="One bounded local test",
        executor_requirements=(),
        artifact_title="Fictional comparison",
        authority_scope="work_metadata",
    )


def later_request(
    path: Path,
    *,
    operation_id: UUID | None = None,
    work_id: UUID | None = None,
    artifact_id: UUID | None = None,
) -> WorkCreationRequest:
    snapshot = read_records(path)
    process, _ = process_and_current(path)
    assert process.pack_binding is not None
    return work_creation_request(
        REGISTRY,
        process.pack_binding,
        operation_id=operation_id or uuid4(),
        workspace_id=snapshot.workspace_id,
        process_id=process.id,
        expected_revision=snapshot.state_revision,
        provenance="Explicit fictional request for one ordinary Work",
        work=later_spec(work_id=work_id, artifact_id=artifact_id),
    )


def material(path: Path, content: bytes) -> None:
    snapshot = read_records(path)
    process, _ = process_and_current(path)
    request = ProcessMaterialRequest(
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        process_id=process.id,
        expected_revision=snapshot.state_revision,
        provenance="Exact fictional material before a later Work",
        material=ProcessMaterialSubmission(
            material_id=uuid4(),
            title="Fictional retained note",
            media_type="text/plain; charset=utf-8",
            content_sha256=hashlib.sha256(content).hexdigest(),
            content_size=len(content),
        ),
    )
    save_process_material(path, request, confirm(path, request), content=content)


def raw_domain_rows(path: Path) -> tuple[list[tuple[Any, ...]], ...]:
    database = read_workspace(path).database
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        return tuple(
            connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
            for table in (
                "core_records",
                "mutation_events",
                "mutation_receipts",
                "artifact_versions",
                "accepted_handoffs",
                "work_results",
                "process_materials",
            )
        )


def durable_workspace_bytes(path: Path) -> dict[str, bytes]:
    return {
        file.relative_to(path).as_posix(): file.read_bytes()
        for directory in (path / ".zara", path / "artifacts", path / "projections")
        for file in sorted(directory.rglob("*"))
        if file.is_file()
    }


def mutate_work(path: Path, work_id: UUID, operation: str, **changes: Any) -> MutationRequest:
    snapshot = read_records(path)
    return MutationRequest.model_validate(
        dict(
            version=2 if operation in ("authorize_artifact", "publish_artifact") else 1,
            operation_id=uuid4(),
            workspace_id=snapshot.workspace_id,
            work_id=work_id,
            expected_revision=snapshot.state_revision,
            operation=operation,
            provenance="Explicit fictional later-Work evidence",
        )
        | changes
    )


def accept_later_result(path: Path, work: Work, artifact: Artifact, content: bytes) -> None:
    authorize = mutate_work(
        path,
        work.id,
        "authorize_artifact",
        artifact_id=artifact.id,
        artifact_revision=artifact.revision,
    )
    apply_mutation(path, authorize, confirm(path, authorize))
    digest = hashlib.sha256(content).hexdigest()
    publish = mutate_work(
        path,
        work.id,
        "publish_artifact",
        artifact_id=artifact.id,
        artifact_revision=artifact.revision,
        content_sha256=digest,
        content_size=len(content),
    )
    apply_mutation(path, publish, confirm(path, publish), content=content)
    snapshot = read_records(path)
    handoff = Handoff(
        kind="handoff",
        version=1,
        handoff_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        process=work.process_id,
        related_work=work.id,
        intent="accepted_result",
        source_revision=snapshot.state_revision,
        result=ArtifactReference(
            artifact_id=artifact.id,
            version_id=publish.operation_id,
            sha256=digest,
        ),
        provenance="Accepted fictional later-Work comparison",
        created_by="fictional-resume-test-adapter",
    )
    request = handoff_request(handoff.model_dump_json().encode(), source_ref="fictional-result")
    apply_mutation(path, request, confirm(path, request))


@pytest.mark.parametrize("owner_kind", ["process_material", "work_creation"])
def test_work_mutation_rejects_each_process_receipt_identity_without_effect(
    workspace: Path, owner_kind: str
) -> None:
    migrate_workspace(workspace, target_version=9)
    process_operation_id = uuid4()
    content: bytes | None = None
    process, _ = process_and_current(workspace)
    if owner_kind == "process_material":
        content = b"Exact fictional cross-kind identity note.\n"
        snapshot = read_records(workspace)
        process_request: ProcessMaterialRequest | WorkCreationRequest = ProcessMaterialRequest(
            operation_id=process_operation_id,
            workspace_id=snapshot.workspace_id,
            process_id=process.id,
            expected_revision=snapshot.state_revision,
            provenance="Retain one exact fictional cross-kind identity",
            material=ProcessMaterialSubmission(
                material_id=uuid4(),
                title="Fictional cross-kind identity note",
                media_type="text/plain; charset=utf-8",
                content_sha256=hashlib.sha256(content).hexdigest(),
                content_size=len(content),
            ),
        )
        process_receipt = apply_mutation(
            workspace,
            process_request,
            confirm(workspace, process_request),
            content=content,
        )
        work_request = later_request(workspace)
        create_later_work(workspace, work_request, confirm(workspace, work_request), REGISTRY)
    else:
        process_request = later_request(workspace, operation_id=process_operation_id)
        process_receipt = create_later_work(
            workspace,
            process_request,
            confirm(workspace, process_request),
            REGISTRY,
        )

    snapshot = read_records(workspace)
    work = snapshot.current_work
    assert work is not None
    artifact = next(
        record
        for record in snapshot.records
        if isinstance(record, Artifact) and record.work_id == work.id
    )
    changed_intent = mutate_work(
        workspace,
        work.id,
        "authorize_artifact",
        artifact_id=artifact.id,
        artifact_revision=artifact.revision,
    ).model_copy(update={"operation_id": process_operation_id})
    before = durable_workspace_bytes(workspace)
    with pytest.raises(MutationError, match="collision") as collision:
        apply_mutation(workspace, changed_intent, confirm(workspace, changed_intent))
    assert collision.value.code == "collision"
    assert durable_workspace_bytes(workspace) == before

    refreshed = process_request.model_copy(update={"expected_revision": snapshot.state_revision})
    assert (
        apply_mutation(workspace, refreshed, confirm(workspace, refreshed), content=content)
        == process_receipt
    )
    assert durable_workspace_bytes(workspace) == before


@pytest.mark.parametrize("process_kind", ["process_material", "work_creation"])
def test_process_mutation_rejects_work_receipt_identity_without_effect(
    workspace: Path, process_kind: str
) -> None:
    migrate_workspace(workspace, target_version=9)
    work_request = later_request(workspace)
    create_later_work(workspace, work_request, confirm(workspace, work_request), REGISTRY)
    snapshot = read_records(workspace)
    work = snapshot.current_work
    assert work is not None
    artifact = next(
        record
        for record in snapshot.records
        if isinstance(record, Artifact) and record.work_id == work.id
    )
    work_mutation = mutate_work(
        workspace,
        work.id,
        "authorize_artifact",
        artifact_id=artifact.id,
        artifact_revision=artifact.revision,
    )
    work_receipt = apply_mutation(workspace, work_mutation, confirm(workspace, work_mutation))
    committed = read_records(workspace)
    process, _ = process_and_current(workspace)
    content: bytes | None = None
    if process_kind == "process_material":
        content = b"Rejected fictional reverse-kind identity note.\n"
        process_request: ProcessMaterialRequest | WorkCreationRequest = ProcessMaterialRequest(
            operation_id=work_mutation.operation_id,
            workspace_id=committed.workspace_id,
            process_id=process.id,
            expected_revision=committed.state_revision,
            provenance="Attempt to reuse one exact Work identity for Process material",
            material=ProcessMaterialSubmission(
                material_id=uuid4(),
                title="Rejected reverse-kind identity note",
                media_type="text/plain; charset=utf-8",
                content_sha256=hashlib.sha256(content).hexdigest(),
                content_size=len(content),
            ),
        )
    else:
        assert process.pack_binding is not None
        process_request = work_creation_request(
            REGISTRY,
            process.pack_binding,
            operation_id=work_mutation.operation_id,
            workspace_id=committed.workspace_id,
            process_id=process.id,
            expected_revision=committed.state_revision,
            provenance="Attempt to reuse one exact Work identity for Work creation",
            work=later_spec(),
        )
    before = durable_workspace_bytes(workspace)
    with pytest.raises(MutationError, match="collision") as collision:
        apply_mutation(
            workspace,
            process_request,
            confirm(workspace, process_request),
            content=content,
        )
    assert collision.value.code == "collision"
    assert durable_workspace_bytes(workspace) == before

    refreshed = work_mutation.model_copy(update={"expected_revision": committed.state_revision})
    assert apply_mutation(workspace, refreshed, confirm(workspace, refreshed)) == work_receipt
    assert durable_workspace_bytes(workspace) == before


def test_no_current_read_is_stable_then_material_migration_and_later_work_replay(
    workspace: Path,
) -> None:
    query = state_query(workspace)
    caller = confirm(workspace, query)
    database = read_workspace(workspace).database
    before_read = database.read_bytes()
    state = read_process_state(workspace, query, caller)
    assert state.resume_state == "no_current_work" and state.current_work is None
    assert read_process_state(workspace, query, caller) == state
    assert database.read_bytes() == before_read

    material(workspace, b"The fictional silver rim remains visible at sunset.\n")
    pre_migration = raw_domain_rows(workspace)
    material_revision = read_records(workspace).state_revision
    assert migrate_workspace(workspace, target_version=9).schema_version == 9
    assert raw_domain_rows(workspace) == pre_migration

    request = later_request(workspace)
    denied_before = read_records(workspace)
    with pytest.raises(MutationError, match="permission_denied"):
        create_later_work(workspace, request, None, REGISTRY)
    assert read_records(workspace) == denied_before
    with pytest.raises(PackError, match="missing_pack"):
        create_later_work(workspace, request, confirm(workspace, request), PackRegistry())
    incompatible = PackRegistry(
        (
            PackRegistration(
                reference=REFERENCE.model_copy(update={"state_version": 2}),
                rule=NoFollowingRule(),
            ),
        )
    )
    with pytest.raises(PackError, match="incompatible_pack"):
        create_later_work(workspace, request, confirm(workspace, request), incompatible)
    assert read_records(workspace) == denied_before

    receipt = create_later_work(workspace, request, confirm(workspace, request), REGISTRY)
    created = read_records(workspace)
    assert receipt.previous_revision == material_revision
    assert created.state_revision == material_revision + 1
    assert created.current_work is not None
    assert created.current_work.id == request.work.work_id
    assert created.current_work.pack_binding == request.pack_binding
    assert created.current_work.status == "ready"
    receipt_query = ProcessReceiptQuery(
        workspace_id=created.workspace_id,
        process_id=request.process_id,
        operation_id=request.operation_id,
        expected_revision=created.state_revision,
    )
    assert (
        read_process_receipt(workspace, receipt_query, confirm(workspace, receipt_query)) == receipt
    )
    state = read_process_state(
        workspace, state_query(workspace), confirm(workspace, state_query(workspace))
    )
    assert state.resume_state == "current_work" and state.current_work == created.current_work

    replay = request.model_copy(update={"expected_revision": created.state_revision})
    assert create_later_work(workspace, replay, confirm(workspace, replay), REGISTRY) == receipt
    assert read_records(workspace) == created
    collision = replay.model_copy(
        update={"work": replay.work.model_copy(update={"goal": "Changed intent"})}
    )
    with pytest.raises(MutationError, match="collision"):
        create_later_work(workspace, collision, confirm(workspace, collision), REGISTRY)
    fresh = later_request(workspace)
    with pytest.raises(MutationError, match="current_work_exists"):
        create_later_work(workspace, fresh, confirm(workspace, fresh), REGISTRY)
    assert read_records(workspace) == created


def test_later_work_can_finish_with_an_ordinary_result_and_identities_stay_immutable(
    workspace: Path,
) -> None:
    migrate_workspace(workspace, target_version=9)
    request = later_request(workspace)
    create_later_work(workspace, request, confirm(workspace, request), REGISTRY)
    snapshot = read_records(workspace)
    work = snapshot.current_work
    assert work is not None
    artifact = next(
        record
        for record in snapshot.records
        if isinstance(record, Artifact) and record.work_id == work.id
    )
    accept_later_result(workspace, work, artifact, b"Both fictional notes retain the silver rim.\n")
    finish_current(workspace)
    finished = read_records(workspace)
    assert finished.current_work is None
    historical = next(record for record in finished.records if record.id == work.id)
    assert isinstance(historical, Work)
    assert historical.status == "done" and historical.id == request.work.work_id
    state = read_process_state(
        workspace, state_query(workspace), confirm(workspace, state_query(workspace))
    )
    assert state.resume_state == "no_current_work"
    assert len(state.results) == 2
    assert len(read_history(workspace).work_creation_events) == 1

    reused = later_request(
        workspace,
        work_id=request.work.work_id,
        artifact_id=request.work.artifact_id,
    )
    with pytest.raises(MutationError, match="collision"):
        create_later_work(workspace, reused, confirm(workspace, reused), REGISTRY)
    assert read_records(workspace) == finished


def test_stale_wrong_binding_and_transaction_failure_change_nothing(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrate_workspace(workspace, target_version=9)
    current = read_records(workspace)
    request = later_request(workspace)
    stale = request.model_copy(update={"expected_revision": current.state_revision - 1})
    with pytest.raises(MutationError, match="conflict"):
        create_later_work(workspace, stale, confirm(workspace, stale), REGISTRY)
    wrong_process = request.model_copy(update={"process_id": uuid4()})
    with pytest.raises(MutationError, match="permission_denied"):
        create_later_work(workspace, wrong_process, confirm(workspace, request), REGISTRY)
    changed_reference = REFERENCE.model_copy(update={"pack_version": "2.0.0"})
    wrong_binding = request.model_copy(update={"pack_binding": changed_reference})
    with pytest.raises(MutationError, match="incompatible_pack"):
        create_work(workspace, wrong_binding, confirm(workspace, wrong_binding))
    assert read_records(workspace) == current

    caller = confirm(workspace, request)
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
            if action == sqlite3.SQLITE_INSERT and table == "core_records":
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(deny)
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", fail)
        with pytest.raises(WorkspaceError):
            create_later_work(workspace, request, caller, REGISTRY)
    assert read_records(workspace) == current
    assert not read_history(workspace).work_creation_events


def test_unbound_process_cannot_bypass_pack_compatibility(unbound_workspace: Path) -> None:
    snapshot = read_records(unbound_workspace)
    process, current = process_and_current(unbound_workspace)
    assert current is None and process.pack_binding is None
    request = WorkCreationRequest(
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        process_id=process.id,
        expected_revision=snapshot.state_revision,
        provenance="Attempted fictional unbound Work",
        pack_binding=REFERENCE,
        work=later_spec(),
    )
    with pytest.raises(MutationError, match="unbound_pack"):
        create_work(unbound_workspace, request, confirm(unbound_workspace, request))
    assert read_records(unbound_workspace) == snapshot


def test_ambiguous_many_is_explicit_and_read_does_not_repair(workspace: Path) -> None:
    migrate_workspace(workspace, target_version=9)
    snapshot = read_records(workspace)
    process, _ = process_and_current(workspace)
    query = state_query(workspace)
    caller = confirm(workspace, query)
    now = process.created_at
    database = read_workspace(workspace).database
    with sqlite3.connect(database) as connection:
        for index in range(2):
            work = Work(
                id=uuid4(),
                revision=snapshot.state_revision,
                created_at=now,
                process_id=process.id,
                goal=f"Corrupt fictional candidate {index}",
                expected_result="Nothing selectable",
                acceptance=("Never selected",),
                boundaries=("Corruption fixture only",),
                budget="No execution",
                status="ready",
                authority_scope="work_metadata",
                pack_binding=process.pack_binding,
            )
            artifact = Artifact(
                id=uuid4(),
                revision=1,
                created_at=now,
                process_id=process.id,
                work_id=work.id,
                title=f"Corrupt artifact {index}",
            )
            for record in (work, artifact):
                connection.execute(
                    "INSERT INTO core_records (id, kind, revision, body) VALUES (?, ?, ?, ?)",
                    (str(record.id), record.kind, record.revision, record.model_dump_json()),
                )
    corrupted = database.read_bytes()
    with pytest.raises(AmbiguousCurrentWorkError, match="ambiguous_current_work") as error:
        read_process_state(workspace, query, caller)
    assert error.value.code == "ambiguous_current_work"
    assert database.read_bytes() == corrupted
