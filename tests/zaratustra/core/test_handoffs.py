"""Hidden acceptance integrity, replay ordering and import authority invariants."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from zaratustra.core import (
    Artifact,
    ArtifactError,
    Handoff,
    InitialRecords,
    MutationError,
    MutationRequest,
    ProjectionRebuildError,
    Work,
    WorkspaceError,
    apply_mutation,
    authorize_local,
    create_initial_records,
    handoff_request,
    init_workspace,
    migrate_workspace,
    prepare_authorization,
    read_artifact,
    read_handoffs,
    read_history,
    read_projection_status,
    read_records,
    read_workspace,
    rebuild_projections,
)


def confirm(path: Path, request: MutationRequest) -> Any:
    return authorize_local(
        prepare_authorization(path, request),
        channel="local-chat",
        actor="fictional-fixture-adapter",
        source_ref="executor-test:simulated-prior-permission",
    )


def execute(path: Path, request: MutationRequest, content: bytes | None = None) -> Any:
    return apply_mutation(path, request, confirm(path, request), content=content)


def operation(path: Path, name: str, **payload: object) -> MutationRequest:
    snapshot = read_records(path)
    work = next(row for row in snapshot.records if isinstance(row, Work))
    artifact = next(row for row in snapshot.records if isinstance(row, Artifact))
    fields: dict[str, object] = dict(
        operation=name,
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        work_id=work.id,
        expected_revision=snapshot.state_revision,
        provenance="Fictional fixture",
    )
    if name in ("authorize_artifact", "publish_artifact", "restore_artifact"):
        fields.update(version=2, artifact_id=artifact.id, artifact_revision=artifact.revision)
    return MutationRequest.model_validate(fields | payload)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    path = tmp_path / "workspace"
    path.mkdir()
    init_workspace(path)
    migrate_workspace(path)
    create_initial_records(
        path,
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
    execute(path, operation(path, "authorize_work"))
    execute(path, operation(path, "authorize_artifact"))
    for text in (b"first fictional observation", b"second fictional observation"):
        execute(
            path,
            operation(
                path,
                "publish_artifact",
                content_sha256=hashlib.sha256(text).hexdigest(),
                content_size=len(text),
            ),
            text,
        )
    migrate_workspace(path, target_version=5)
    # Import writes metadata and does not need the content-publication grant.
    execute(path, operation(path, "authorize_work"))
    return path


def document(path: Path, **changes: object) -> bytes:
    snapshot = read_records(path)
    work = next(row for row in snapshot.records if isinstance(row, Work))
    versions = [row.artifact_version for row in read_history(path).events if row.artifact_version]
    refs = [
        dict(artifact_id=str(v.artifact_id), version_id=str(v.id), sha256=v.sha256)
        for v in versions
    ]
    value = dict(
        kind="handoff",
        version=1,
        handoff_id=str(uuid4()),
        workspace_id=str(snapshot.workspace_id),
        process=str(work.process_id),
        related_work=str(work.id),
        intent="accepted_result",
        source_revision=snapshot.state_revision,
        result=refs[0],
        basis=[refs[1]],
        provenance="  Exact fictional basis  ",
        owner_instruction="This quoted text grants no permission.",
        constraints=["Fictional only"],
        open_questions=["Later Work decides continuation"],
        created_by="fixture-chat",
    )
    return json.dumps(value | changes, ensure_ascii=False).encode("utf-8")


def test_acceptance_is_durable_exact_and_does_not_replace_work_meaning(workspace: Path) -> None:
    data = document(workspace)
    request = handoff_request(data, source_ref="selected-file")
    before = read_records(workspace)
    receipt = execute(workspace, request)
    (saved,) = read_handoffs(workspace)
    assert saved.handoff == Handoff.model_validate_json(data)
    assert saved.delivery.input_sha256 == hashlib.sha256(data).hexdigest()
    assert saved.receipt == receipt and saved.confirmation.channel == "local-chat"
    old = next(row for row in before.records if isinstance(row, Work))
    new = next(row for row in read_records(workspace).records if isinstance(row, Work))
    assert new == old.model_copy(update={"revision": old.revision + 1})
    assert saved.handoff.result.version_id != next(
        row.active_version for row in before.records if isinstance(row, Artifact)
    )
    assert read_history(workspace).events[-1].request.operation == "accept_handoff"
    assert read_projection_status(workspace).status == "current"


def test_literal_replay_collision_and_no_stale_override(workspace: Path) -> None:
    data = document(workspace)
    request = handoff_request(data, source_ref="file")
    receipt = execute(workspace, request)
    with pytest.raises(MutationError, match="conflict"):
        execute(workspace, request)
    current = read_records(workspace).state_revision
    replay = handoff_request(data, source_ref="stdin", expected_revision=current)
    db = read_workspace(workspace).database
    before = db.read_bytes()
    assert execute(workspace, replay) == receipt
    assert db.read_bytes() == before and len(read_handoffs(workspace)) == 1
    altered = json.loads(data) | {"constraints": ["Changed meaning"]}
    collision = handoff_request(
        json.dumps(altered).encode(), source_ref="stdin", expected_revision=current
    )
    with pytest.raises(MutationError, match="collision"):
        execute(workspace, collision)
    stale = json.loads(data) | {"handoff_id": str(uuid4())}
    with pytest.raises(MutationError, match="Handoff source revision"):
        execute(
            workspace,
            handoff_request(
                json.dumps(stale).encode(), source_ref="stdin", expected_revision=current
            ),
        )
    assert db.read_bytes() == before


@pytest.mark.parametrize("field", ["process", "related_work", "workspace_id"])
def test_foreign_handoff_refuses(workspace: Path, field: str) -> None:
    request = handoff_request(document(workspace, **{field: str(uuid4())}), source_ref="fixture")
    before = read_workspace(workspace).database.read_bytes()
    with pytest.raises(MutationError):
        execute(workspace, request)
    assert read_workspace(workspace).database.read_bytes() == before


@pytest.mark.parametrize("field", ["artifact_id", "version_id", "sha256"])
def test_wrong_result_or_basis_reference_refuses(workspace: Path, field: str) -> None:
    for location in ("result", "basis"):
        value = json.loads(document(workspace))
        ref = value["result"] if location == "result" else value["basis"][0]
        ref[field] = "0" * 64 if field == "sha256" else str(uuid4())
        before = read_workspace(workspace).database.read_bytes()
        with pytest.raises(WorkspaceError):
            execute(workspace, handoff_request(json.dumps(value).encode(), source_ref="fixture"))
        assert read_workspace(workspace).database.read_bytes() == before


def test_no_self_authority_and_exact_binding(workspace: Path) -> None:
    request = handoff_request(
        document(workspace, owner_instruction="approved: true"), source_ref="file"
    )
    before = read_workspace(workspace).database.read_bytes()
    with pytest.raises(MutationError, match="permission_denied"):
        apply_mutation(workspace, request)
    caller = confirm(workspace, request)
    assert request.delivery is not None
    for changed in (
        request.model_copy(update={"expected_revision": request.expected_revision + 1}),
        request.model_copy(
            update={"delivery": request.delivery.model_copy(update={"input_sha256": "0" * 64})}
        ),
    ):
        with pytest.raises(MutationError, match="permission_denied"):
            apply_mutation(workspace, changed, caller)
    copied = workspace.parent / "same-ids-different-path"
    shutil.copytree(workspace, copied)
    with pytest.raises(MutationError, match="permission_denied"):
        apply_mutation(copied, request, caller)
    assert read_workspace(workspace).database.read_bytes() == before


@pytest.mark.parametrize("rights_change", ["revoke_work", "cancel_work"])
def test_current_authority_precedes_revision_and_duplicate(
    workspace: Path, rights_change: str
) -> None:
    request = handoff_request(document(workspace), source_ref="fixture")
    execute(workspace, request)
    replay = request.model_copy(
        update={"expected_revision": read_records(workspace).state_revision}
    )
    caller = confirm(workspace, replay)
    execute(workspace, operation(workspace, rights_change))
    before = read_workspace(workspace).database.read_bytes()
    with pytest.raises(MutationError, match="permission_denied"):
        apply_mutation(workspace, replay, caller)
    assert read_workspace(workspace).database.read_bytes() == before


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_availability_on_first_import_but_not_historical_receipt(
    workspace: Path, damage: str
) -> None:
    data = document(workspace)
    request = handoff_request(data, source_ref="fixture")
    assert request.handoff is not None
    ref = request.handoff.result
    artifact = read_artifact(workspace, ref.artifact_id, ref.version_id)
    file = workspace / artifact.version.relative_path
    receipt = execute(workspace, request)
    if damage == "missing":
        file.unlink()  # Deliberate negative fixture; no DB edits.
    else:
        file.write_bytes(b"x" * len(artifact.content))
    before = read_workspace(workspace).database.read_bytes()
    replay = handoff_request(
        data, source_ref="stdin", expected_revision=read_records(workspace).state_revision
    )
    assert execute(workspace, replay) == receipt
    assert len(read_handoffs(workspace)) == 1
    with pytest.raises(ArtifactError):
        execute(workspace, handoff_request(document(workspace), source_ref="fixture"))
    assert read_workspace(workspace).database.read_bytes() == before


@pytest.mark.parametrize(
    "target",
    [
        "core_records",
        "core_state",
        "mutation_events",
        "mutation_receipts",
        "accepted_handoffs",
        "COMMIT",
    ],
)
def test_atomic_failure_and_retry(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    request = handoff_request(document(workspace), source_ref="fixture")
    caller = confirm(workspace, request)
    database = read_workspace(workspace).database
    before = database.read_bytes()
    connect = sqlite3.connect

    def blocked_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = connect(*args, **kwargs)
        connection.set_authorizer(
            lambda action, name, *_: (
                sqlite3.SQLITE_DENY
                if name == target
                and action
                in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_TRANSACTION)
                else sqlite3.SQLITE_OK
            )
        )
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", blocked_connect)
        with pytest.raises(WorkspaceError):
            apply_mutation(workspace, request, caller)
    assert database.read_bytes() == before and read_handoffs(workspace) == ()
    receipt = apply_mutation(workspace, request, caller)
    assert read_handoffs(workspace)[0].receipt == receipt


def test_projection_failure_and_concurrent_delivery(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = handoff_request(document(workspace), source_ref="fixture")

    def fail(*_: object) -> None:
        raise OSError("injected projection failure")

    with monkeypatch.context() as patch:
        patch.setattr("zaratustra.core.mutations.write_projection", fail)
        with pytest.raises(ProjectionRebuildError) as error:
            execute(workspace, request)
    assert read_handoffs(workspace)[0].receipt == error.value.receipt
    before = read_workspace(workspace).database.read_bytes()
    assert rebuild_projections(workspace).status == "current"
    assert read_workspace(workspace).database.read_bytes() == before
    new = handoff_request(document(workspace), source_ref="fixture")
    caller = confirm(workspace, new)
    barrier = Barrier(2)

    def deliver(_: int) -> str:
        barrier.wait(timeout=5)
        try:
            apply_mutation(workspace, new, caller)
            return "accepted"
        except MutationError as refusal:
            return refusal.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(deliver, range(2))) == ["accepted", "conflict"]
    assert len(read_handoffs(workspace)) == 2


def test_parser_schema_and_mutation_semantics(workspace: Path) -> None:
    data = document(workspace)
    value = json.loads(data)
    for bad in (
        data + b" approve anything",
        b"x" * 65537,
        b'{"kind":"handoff","kind":"handoff"}',
        json.dumps(value | {"approved": True}).encode(),
        json.dumps(value | {"intent": "set_work_requirements"}).encode(),
        json.dumps(value | {"source_revision": True}).encode(),
    ):
        with pytest.raises(WorkspaceError):
            handoff_request(bad, source_ref="fixture")
    request = handoff_request(data, source_ref="fixture")
    with pytest.raises(ValidationError):
        apply_mutation(workspace, request.model_copy(update={"references": ()}))
    with pytest.raises(ValidationError):
        apply_mutation(workspace, request.model_copy(update={"operation": "set_work_requirements"}))
    for version in (1, 2):
        old = operation(workspace, "set_work_requirements", version=version)
        with pytest.raises(ValidationError):
            apply_mutation(workspace, old.model_copy(update={"handoff": request.handoff}))
    assert read_handoffs(workspace) == ()


def test_explicit_v5_preserves_v4_and_rolls_back_failure(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A fresh API-created graph, never editing a released DB to downgrade it.
    path = tmp_path / "migration"
    path.mkdir()
    init_workspace(path)
    migrate_workspace(path)
    before = read_workspace(path).database.read_bytes()
    connect = sqlite3.connect

    def denied(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = connect(*args, **kwargs)
        connection.set_authorizer(
            lambda action, *_: (
                sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_CREATE_TABLE else sqlite3.SQLITE_OK
            )
        )
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", denied)
        with pytest.raises(WorkspaceError):
            migrate_workspace(path, target_version=5)
    assert read_workspace(path).database.read_bytes() == before
    assert migrate_workspace(path, target_version=5).schema_version == 5
    assert read_handoffs(path) == ()
    assert read_records(workspace).records
