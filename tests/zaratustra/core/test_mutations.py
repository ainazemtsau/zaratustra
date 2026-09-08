"""Hidden-state checks for literal ordering, authority, audit and DB consistency."""

from __future__ import annotations

import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from zaratustra.core import (
    InitialRecords,
    LocalAuthorization,
    MutationError,
    MutationRequest,
    ReceiptQuery,
    Work,
    WorkspaceError,
    apply_mutation,
    authorize_local,
    create_initial_records,
    init_workspace,
    migrate_workspace,
    prepare_authorization,
    read_history,
    read_receipt,
    read_records,
    read_workspace,
)
from zaratustra.core.migration_v3 import V3_NAME, V3_SHA256


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    init_workspace(tmp_path)
    migrate_workspace(tmp_path, target_version=2)
    create_initial_records(
        tmp_path,
        InitialRecords(
            process_title="Fictional observatory",
            goal="Describe an imaginary moon",
            expected_result="One fictional note",
            acceptance=("Preserve the observation",),
            boundaries=("Fictional internal changes only",),
            budget="One local trial",
            artifact_title="Observation draft",
        ),
    )
    return tmp_path


def request_for(
    path: Path, operation: str = "authorize_work", **changes: object
) -> MutationRequest:
    snapshot = read_records(path)
    work = next(record for record in snapshot.records if isinstance(record, Work))
    return MutationRequest.model_validate(
        dict(
            operation_id=uuid4(),
            workspace_id=snapshot.workspace_id,
            work_id=work.id,
            expected_revision=snapshot.state_revision,
            operation=operation,
            provenance="Fictional failure fixture; simulated prior owner permission",
        )
        | changes
    )


def confirm(path: Path, request: MutationRequest | ReceiptQuery) -> LocalAuthorization:
    # Trusted adapter simulation only; the installed probe separately exercises console delivery.
    return authorize_local(
        prepare_authorization(path, request),
        channel="local-chat",
        actor="fictional-trusted-adapter",
        source_ref="fixture:explicit-simulated-owner-instruction",
    )


def execute(path: Path, request: MutationRequest) -> None:
    apply_mutation(path, request, confirm(path, request))


def ready(path: Path) -> None:
    migrate_workspace(path, target_version=3)
    execute(path, request_for(path))


def test_explicit_v3_migration_preserves_v2_and_grants_nothing(workspace: Path) -> None:
    original = read_workspace(workspace)
    snapshot = read_records(workspace)
    before = original.database.read_bytes()
    with pytest.raises(MutationError, match="migration"):
        apply_mutation(workspace, request_for(workspace))
    assert original.database.read_bytes() == before
    upgraded = migrate_workspace(workspace, target_version=3)
    assert upgraded.schema_version == 3
    assert (upgraded.workspace_id, upgraded.created_at) == (
        original.workspace_id,
        original.created_at,
    )
    assert read_records(workspace) == snapshot
    assert read_history(workspace).events == ()
    with closing(sqlite3.connect(original.database)) as connection:
        assert connection.execute(
            "SELECT version, name, sha256 FROM schema_migrations WHERE version = 3"
        ).fetchone() == (3, V3_NAME, V3_SHA256)
    migrated = original.database.read_bytes()
    assert migrate_workspace(workspace, target_version=3) == upgraded
    with pytest.raises(WorkspaceError, match="downgrade"):
        migrate_workspace(workspace, target_version=2)
    assert original.database.read_bytes() == migrated


def test_one_effect_replay_collision_and_saved_audit(workspace: Path) -> None:
    ready(workspace)
    request = request_for(workspace, "set_work_requirements", requirements=("reasoning",))
    caller = confirm(workspace, request)
    receipt = apply_mutation(workspace, request, caller)
    info = read_workspace(workspace)
    before = info.database.read_bytes()
    with pytest.raises(MutationError, match="conflict"):
        apply_mutation(workspace, request, caller)
    refreshed = request.model_copy(update={"expected_revision": receipt.new_revision})
    assert apply_mutation(workspace, refreshed, confirm(workspace, refreshed)) == receipt
    collision = refreshed.model_copy(update={"requirements": ("different",)})
    with pytest.raises(MutationError, match="collision"):
        apply_mutation(workspace, collision, confirm(workspace, collision))
    history = read_history(workspace)
    event = history.events[-1]
    assert len(history.events) == 2 and len(history.receipts) == 2
    assert event.request == request
    assert event.confirmation == caller.confirmation
    assert event.confirmation.actor == "fictional-trusted-adapter"
    assert event.before.executor_requirements == ()
    assert event.after.executor_requirements == ("reasoning",)
    assert event.before.revision == receipt.previous_revision == 2
    assert event.after.revision == receipt.new_revision == 3
    assert event.id == receipt.event_id
    assert event.affected_projections == receipt.affected_projections == ()
    assert info.database.read_bytes() == before


def test_current_rights_terminal_state_and_receipt_disclosure(workspace: Path) -> None:
    ready(workspace)
    request = request_for(workspace, "set_work_requirements", requirements=("coding",))
    execute(workspace, request)
    query = ReceiptQuery(
        workspace_id=request.workspace_id,
        work_id=request.work_id,
        operation_id=request.operation_id,
    )
    query_caller = confirm(workspace, query)
    assert read_receipt(workspace, query, query_caller).new_revision == 3
    cancel = request_for(workspace, "cancel_work")
    execute(workspace, cancel)
    assert read_receipt(workspace, query, query_caller).new_revision == 3
    for operation in ("authorize_work", "cancel_work", "set_work_requirements"):
        terminal = request_for(workspace, operation)
        with pytest.raises(MutationError, match="permission_denied"):
            execute(workspace, terminal)
    execute(workspace, request_for(workspace, "revoke_work"))
    after = read_workspace(workspace).database.read_bytes()
    with pytest.raises(MutationError, match="permission_denied"):
        read_receipt(workspace, query, query_caller)
    with pytest.raises(MutationError, match="permission_denied"):
        apply_mutation(workspace, request, confirm(workspace, request))
    assert read_workspace(workspace).database.read_bytes() == after


def test_ungranted_work_and_exact_authorization_binding(workspace: Path) -> None:
    migrate_workspace(workspace, target_version=3)
    request = request_for(workspace, "set_work_requirements", requirements=("reasoning",))
    before = read_workspace(workspace).database.read_bytes()
    with pytest.raises(MutationError, match="permission_denied"):
        apply_mutation(workspace, request, confirm(workspace, request))
    grant = request_for(workspace)
    with pytest.raises(MutationError, match="permission_denied"):
        apply_mutation(workspace, grant)
    caller = confirm(workspace, grant)
    copied = workspace.parent / (workspace.name + "-copy")
    shutil.copytree(workspace, copied)
    with pytest.raises(MutationError, match="permission_denied"):
        apply_mutation(copied, grant, caller)
    assert read_workspace(copied).database.read_bytes() == before
    for field, value in (
        ("provenance", "Altered after confirmation"),
        ("work_id", uuid4()),
        ("workspace_id", uuid4()),
        ("operation_id", uuid4()),
        ("expected_revision", 99),
    ):
        with pytest.raises(MutationError, match="permission_denied"):
            apply_mutation(workspace, grant.model_copy(update={field: value}), caller)
    assert read_workspace(workspace).database.read_bytes() == before


def test_schema_authority_revision_duplicate_artifact_order(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ready(workspace)
    request = request_for(workspace)
    stale = request.model_copy(update={"expected_revision": 1, "artifact_references": (uuid4(),)})
    stale_caller = confirm(workspace, stale)
    connect = sqlite3.connect

    def guarded_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = connect(*args, **kwargs)

        def deny_journal(action: int, table: str | None, *_: object) -> int:
            return (
                sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_READ and table == "mutation_receipts"
                else sqlite3.SQLITE_OK
            )

        # Metadata's LIMIT 0 read names receipt columns, so use a trace callback
        # to install the denial after metadata and the initial record snapshot.
        def trace(sql: str) -> None:
            if sql.startswith("SELECT id, kind, revision, body FROM core_records ORDER"):
                connection.set_authorizer(deny_journal)

        connection.set_trace_callback(trace)
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", guarded_connect)
        with pytest.raises(ValidationError):
            apply_mutation(workspace, request.model_copy(update={"expected_revision": True}))
        with pytest.raises(MutationError, match="permission_denied"):
            apply_mutation(workspace, stale)
        with pytest.raises(MutationError, match="conflict"):
            apply_mutation(workspace, stale, stale_caller)
    unsupported = request.model_copy(update={"artifact_references": (uuid4(),)})
    with pytest.raises(MutationError, match="unsupported_artifacts"):
        execute(workspace, unsupported)
    execute(workspace, request)
    collision = unsupported.model_copy(update={"expected_revision": 3})
    with pytest.raises(MutationError, match="collision"):
        execute(workspace, collision)
    assert len(read_history(workspace).events) == 2


@pytest.mark.parametrize(
    "field", ["approved", "actor", "authority_scope", "exact_text", "goal", "budget"]
)
def test_payload_cannot_expand_scope_or_attest_authority(workspace: Path, field: str) -> None:
    with pytest.raises(ValidationError):
        MutationRequest.model_validate({**request_for(workspace).model_dump(), field: "owner"})


@pytest.mark.parametrize("stage", ["state", "event", "receipt", "commit"])
def test_db_failure_rolls_back_change_event_and_receipt(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    ready(workspace)
    request = request_for(workspace, "set_work_requirements", requirements=("reasoning",))
    caller = confirm(workspace, request)
    database = read_workspace(workspace).database
    before = database.read_bytes()
    connect = sqlite3.connect

    def failing_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = connect(*args, **kwargs)

        def fail(action: int, target: str | None, *_: object) -> int:
            blocked = {
                "state": (sqlite3.SQLITE_UPDATE, "core_state"),
                "event": (sqlite3.SQLITE_INSERT, "mutation_events"),
                "receipt": (sqlite3.SQLITE_INSERT, "mutation_receipts"),
                "commit": (sqlite3.SQLITE_TRANSACTION, "COMMIT"),
            }[stage]
            return sqlite3.SQLITE_DENY if (action, target) == blocked else sqlite3.SQLITE_OK

        connection.set_authorizer(fail)
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", failing_connect)
        with pytest.raises(WorkspaceError):
            apply_mutation(workspace, request, caller)
    assert database.read_bytes() == before
    assert read_records(workspace).state_revision == 2
    assert len(read_history(workspace).events) == len(read_history(workspace).receipts) == 1
    assert apply_mutation(workspace, request, caller).new_revision == 3


def test_v3_migration_failure_retains_v2(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    before = read_workspace(workspace).database.read_bytes()
    connect = sqlite3.connect

    def failing_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = connect(*args, **kwargs)
        connection.set_authorizer(
            lambda action, table, *_: (
                sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_INSERT and table == "schema_migrations"
                else sqlite3.SQLITE_OK
            )
        )
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", failing_connect)
        with pytest.raises(WorkspaceError):
            migrate_workspace(workspace, target_version=3)
    assert read_workspace(workspace).schema_version == 2
    assert read_workspace(workspace).database.read_bytes() == before
    assert migrate_workspace(workspace, target_version=3).schema_version == 3


@pytest.mark.parametrize("same_id", [False, True])
def test_concurrent_requests_have_one_effect(workspace: Path, same_id: bool) -> None:
    migrate_workspace(workspace, target_version=3)
    first = request_for(workspace)
    second = first if same_id else request_for(workspace)
    callers = [confirm(workspace, request) for request in (first, second)]
    barrier = Barrier(2)

    def run(index: int) -> str:
        barrier.wait()
        try:
            apply_mutation(workspace, (first, second)[index], callers[index])
            return "committed"
        except MutationError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(run, range(2)))
    assert sorted(outcomes) == ["committed", "conflict"]
    assert read_records(workspace).state_revision == 2
    assert len(read_history(workspace).events) == len(read_history(workspace).receipts) == 1


def test_authority_revoked_between_preview_and_mutation(workspace: Path) -> None:
    ready(workspace)
    request = request_for(workspace, "set_work_requirements", requirements=("reasoning",))
    caller = confirm(workspace, request)
    execute(workspace, request_for(workspace, "revoke_work"))
    before = read_workspace(workspace).database.read_bytes()
    with pytest.raises(MutationError, match="permission_denied"):
        apply_mutation(workspace, request, caller)
    assert read_workspace(workspace).database.read_bytes() == before


def test_audit_inconsistency_is_refused_without_repair(workspace: Path) -> None:
    ready(workspace)
    database = read_workspace(workspace).database
    # Deliberately damaged negative fixture, not a successful trial or DB repair.
    with closing(sqlite3.connect(database, autocommit=True)) as connection:
        connection.execute("DELETE FROM mutation_receipts")
    before = database.read_bytes()
    with pytest.raises(WorkspaceError, match="Incomplete"):
        read_records(workspace)
    with pytest.raises(WorkspaceError, match="Incomplete"):
        read_history(workspace)
    assert database.read_bytes() == before
