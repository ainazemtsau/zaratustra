"""Additive interactive execution state owned by the foundation SQLite space."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

from .models import (
    Action,
    AdmitInvocationRequest,
    ArtifactRef,
    AttemptRecord,
    CreateResourceRequest,
    ExecutionSnapshot,
    FinishInvocationRequest,
    InvocationRecord,
    PrepareInvocationRequest,
    ResourceRevision,
    ResourceState,
    ReviseResourceRequest,
    SendInvocationRequest,
    SpaceInfo,
    StartAttemptRequest,
    StopAttemptRequest,
    WorkState,
)
from .operations import (
    LocalAuthority,
    _authorize,
    _local_space,
    read_activity,
    read_artifact,
    read_work,
)
from .storage import (
    EXECUTION_SCHEMA_NAME,
    EXECUTION_SCHEMA_SHA256,
    EXECUTION_SCHEMA_STATEMENTS,
    FoundationError,
    canonical_json,
    read_space,
    space_connection,
    utc_now,
)

type ExecutionRequest = (
    CreateResourceRequest
    | ReviseResourceRequest
    | StartAttemptRequest
    | StopAttemptRequest
    | PrepareInvocationRequest
    | AdmitInvocationRequest
    | SendInvocationRequest
    | FinishInvocationRequest
)


def _event(
    connection: object,
    request: ExecutionRequest,
    work_id: UUID,
    now: str,
    *,
    attempt_id: UUID | None = None,
    invocation_id: UUID | None = None,
) -> None:
    connection.execute(  # type: ignore[attr-defined]
        "INSERT INTO execution_events(operation_id, work_id, attempt_id, invocation_id, "
        "kind, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            str(request.operation_id),
            str(work_id),
            str(attempt_id) if attempt_id else None,
            str(invocation_id) if invocation_id else None,
            request.kind,
            now,
        ),
    )


def _work(connection: object, work_id: UUID) -> tuple[int, WorkState]:
    row = connection.execute(  # type: ignore[attr-defined]
        "SELECT s.current_revision, s.status, c.payload FROM subject_records s "
        "JOIN subject_content c ON c.record_id = s.record_id "
        "AND c.revision = s.current_revision "
        "WHERE s.record_id = ? AND s.kind = 'work'",
        (str(work_id),),
    ).fetchone()
    if row is None or row[1] == "deleted":
        raise FoundationError("not_found", "Named Work is unavailable")
    state = WorkState.model_validate_json(bytes(row[2]))
    if state.status != "proposed":
        raise FoundationError("work_closed", "Accepted Work cannot receive a new execution")
    return int(row[0]), state


def _current_inputs(connection: object, state: WorkState, *, actor: str, epoch: int) -> None:
    for reference in state.inputs:
        row = connection.execute(  # type: ignore[attr-defined]
            "SELECT r.current_revision, r.status, c.payload, c.sha256 FROM records r "
            "JOIN managed_content c ON c.record_id = r.record_id "
            "AND c.revision = r.current_revision "
            "WHERE r.record_id = ? AND r.kind = 'artifact'",
            (str(reference.artifact_id),),
        ).fetchone()
        if row is None or row[1] != "active" or int(row[0]) != reference.revision:
            raise FoundationError("stale_input", "A required Artifact changed or is unavailable")
        if hashlib.sha256(bytes(row[2])).hexdigest().upper() != row[3]:
            raise FoundationError("corrupt_space", "Required Artifact bytes failed verification")
        _authorize(
            connection,
            actor=actor,
            action="record.read",
            epoch=epoch,
            resource_type="artifact",
            resource_id=reference.artifact_id,
        )


def _resource(connection: object, resource_id: UUID) -> tuple[UUID, int, ResourceState]:
    row = connection.execute(  # type: ignore[attr-defined]
        "SELECT work_id, current_revision, state_json FROM execution_resources "
        "WHERE resource_id = ?",
        (str(resource_id),),
    ).fetchone()
    if row is None:
        raise FoundationError("not_found", "Named resource is unavailable")
    state = ResourceState.model_validate_json(row[2])
    return UUID(row[0]), int(row[1]), state


def _available_resource(
    connection: object, resource_id: UUID, work_id: UUID, revision: int
) -> ResourceState:
    owner, current, state = _resource(connection, resource_id)
    if owner != work_id or current != revision or state.status != "active":
        raise FoundationError("stale_resource", "Selected resource changed or was revoked")
    root = state.root.expanduser().resolve()
    if not root.is_dir() or root != state.root:
        raise FoundationError("resource_unavailable", "Selected working directory is unavailable")
    return state


def _attempt(
    connection: object,
    attempt_id: UUID,
    work_id: UUID,
    session_id: UUID,
    epoch: int,
    *,
    active: bool = True,
) -> tuple[int, UUID, int, int]:
    row = connection.execute(  # type: ignore[attr-defined]
        "SELECT work_revision, resource_id, resource_revision, generation, status, "
        "session_id, execution_epoch FROM execution_attempts WHERE attempt_id = ? AND work_id = ?",
        (str(attempt_id), str(work_id)),
    ).fetchone()
    if row is None or row[5] != str(session_id) or int(row[6]) != epoch:
        raise FoundationError("stale_attempt", "Attempt is not owned by this session and epoch")
    if active and row[4] != "active":
        raise FoundationError("stale_attempt", "Attempt is no longer active")
    return int(row[0]), UUID(row[1]), int(row[2]), int(row[3])


def _check_attempt_basis(
    connection: object,
    attempt_id: UUID,
    work_id: UUID,
    session_id: UUID,
    epoch: int,
    *,
    actor: str,
) -> ResourceState:
    work_revision, resource_id, resource_revision, generation = _attempt(
        connection, attempt_id, work_id, session_id, epoch
    )
    current_revision, state = _work(connection, work_id)
    if current_revision != work_revision:
        raise FoundationError("stale_work", "Work changed after Attempt started")
    _current_inputs(connection, state, actor=actor, epoch=epoch)
    resource = _available_resource(connection, resource_id, work_id, resource_revision)
    owner = connection.execute(  # type: ignore[attr-defined]
        "SELECT attempt_id FROM execution_attempts WHERE work_id = ? AND generation = ? "
        "AND status = 'active'",
        (str(work_id), generation),
    ).fetchone()
    if owner != (str(attempt_id),):
        raise FoundationError("stale_attempt", "Attempt generation lost ownership")
    return resource


def _used_units(connection: object, work_id: UUID) -> tuple[int, int]:
    row = connection.execute(  # type: ignore[attr-defined]
        "SELECT COALESCE(SUM(CASE WHEN status = 'answered' THEN usage_units ELSE 0 END), 0), "
        "COALESCE(SUM(CASE WHEN status IN ('admitted', 'sent', 'unknown') "
        "THEN reserve_units ELSE 0 END), 0) "
        "FROM execution_invocations WHERE work_id = ?",
        (str(work_id),),
    ).fetchone()
    return int(row[0]), int(row[1])


def _invocation(
    connection: object, invocation_id: UUID, attempt_id: UUID, work_id: UUID, session_id: UUID
) -> str:
    row = connection.execute(  # type: ignore[attr-defined]
        "SELECT status FROM execution_invocations WHERE invocation_id = ? "
        "AND attempt_id = ? AND work_id = ? AND session_id = ?",
        (str(invocation_id), str(attempt_id), str(work_id), str(session_id)),
    ).fetchone()
    if row is None:
        raise FoundationError("not_found", "Named invocation is unavailable")
    return str(row[0])


def apply_execution_change(
    connection: object, request: ExecutionRequest, *, now: str, epoch: int
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Run inside the existing operation/audit/receipt transaction."""

    if isinstance(request, CreateResourceRequest):
        _work(connection, request.work_id)
        if connection.execute(  # type: ignore[attr-defined]
            "SELECT 1 FROM execution_resources WHERE resource_id = ?", (str(request.resource_id),)
        ).fetchone():
            raise FoundationError("record_exists", "Resource id is already used")
        root = request.state.root.expanduser().resolve()
        if not root.is_dir():
            raise FoundationError("resource_unavailable", "Working directory does not exist")
        state = request.state.model_copy(update={"root": root})
        body = state.model_dump_json()
        connection.execute(  # type: ignore[attr-defined]
            "INSERT INTO execution_resources(resource_id, work_id, current_revision, status, "
            "state_json) VALUES (?, ?, 1, ?, ?)",
            (str(request.resource_id), str(request.work_id), state.status, body),
        )
        connection.execute(  # type: ignore[attr-defined]
            "INSERT INTO execution_resource_revisions(resource_id, revision, operation_id, "
            "state_json) VALUES (?, 1, ?, ?)",
            (str(request.resource_id), str(request.operation_id), body),
        )
        work_id, target_id, revision = request.work_id, request.resource_id, 1
        result: dict[str, object] = {"resource_id": str(target_id), "revision": revision}
    elif isinstance(request, ReviseResourceRequest):
        work_id, current, _ = _resource(connection, request.resource_id)
        if work_id != request.work_id:
            raise FoundationError("wrong_work", "Resource belongs to another Work")
        if current != request.expected_revision:
            raise FoundationError("stale_resource", "Resource revision changed")
        root = request.state.root.expanduser().resolve()
        if request.state.status == "active" and not root.is_dir():
            raise FoundationError("resource_unavailable", "Working directory does not exist")
        state = request.state.model_copy(update={"root": root})
        revision = current + 1
        connection.execute(  # type: ignore[attr-defined]
            "UPDATE execution_resources SET current_revision = ?, status = ?, state_json = ? "
            "WHERE resource_id = ?",
            (revision, state.status, state.model_dump_json(), str(request.resource_id)),
        )
        connection.execute(  # type: ignore[attr-defined]
            "INSERT INTO execution_resource_revisions(resource_id, revision, operation_id, "
            "state_json) VALUES (?, ?, ?, ?)",
            (
                str(request.resource_id),
                revision,
                str(request.operation_id),
                state.model_dump_json(),
            ),
        )
        target_id = request.resource_id
        result = {"resource_id": str(target_id), "revision": revision}
    elif isinstance(request, StartAttemptRequest):
        revision, work_state = _work(connection, request.work_id)
        if revision != request.expected_work_revision:
            raise FoundationError("stale_work", "Work revision changed")
        _current_inputs(connection, work_state, actor=request.actor, epoch=epoch)
        resource = _available_resource(
            connection, request.resource_id, request.work_id, request.expected_resource_revision
        )
        prior = connection.execute(  # type: ignore[attr-defined]
            "SELECT attempt_id, generation, status FROM execution_attempts "
            "WHERE work_id = ? ORDER BY generation DESC LIMIT 1",
            (str(request.work_id),),
        ).fetchone()
        if prior is None and request.previous_attempt_id is not None:
            raise FoundationError("stale_attempt", "No previous Attempt exists")
        if prior is not None and (
            prior[2] == "active" or request.previous_attempt_id != UUID(prior[0])
        ):
            raise FoundationError("stale_attempt", "Prior Attempt is active or not linked exactly")
        if (
            resource.mode == "exclusive"
            and connection.execute(  # type: ignore[attr-defined]
                "SELECT 1 FROM execution_attempts a JOIN execution_resources r "
                "ON r.resource_id = a.resource_id WHERE a.status = 'active' "
                "AND r.resource_id != ? AND json_extract(r.state_json, '$.root') = ? LIMIT 1",
                (str(request.resource_id), str(resource.root)),
            ).fetchone()
        ):
            raise FoundationError("resource_busy", "Exclusive working directory is assigned")
        generation = 1 if prior is None else int(prior[1]) + 1
        connection.execute(  # type: ignore[attr-defined]
            "INSERT INTO execution_attempts(attempt_id, revision, work_id, work_revision, "
            "resource_id, resource_revision, session_id, previous_attempt_id, execution_epoch, "
            "generation, input_refs_json, status, created_at, updated_at) "
            "VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)",
            (
                str(request.attempt_id),
                str(request.work_id),
                revision,
                str(request.resource_id),
                request.expected_resource_revision,
                str(request.session_id),
                str(request.previous_attempt_id) if request.previous_attempt_id else None,
                epoch,
                generation,
                canonical_json([item.model_dump(mode="json") for item in work_state.inputs]),
                now,
                now,
            ),
        )
        work_id, target_id = request.work_id, request.attempt_id
        result = {"attempt_id": str(target_id), "generation": generation, "revision": 1}
    elif isinstance(request, StopAttemptRequest):
        _attempt(connection, request.attempt_id, request.work_id, request.session_id, epoch)
        connection.execute(  # type: ignore[attr-defined]
            "UPDATE execution_invocations SET status = 'unknown', revision = revision + 1, "
            "updated_at = ? WHERE attempt_id = ? AND status IN ('admitted', 'sent')",
            (now, str(request.attempt_id)),
        )
        connection.execute(  # type: ignore[attr-defined]
            "UPDATE execution_attempts SET status = ?, revision = revision + 1, updated_at = ? "
            "WHERE attempt_id = ?",
            (request.outcome, now, str(request.attempt_id)),
        )
        work_id, target_id = request.work_id, request.attempt_id
        result = {"attempt_id": str(target_id), "status": request.outcome}
    elif isinstance(request, PrepareInvocationRequest):
        _check_attempt_basis(
            connection,
            request.attempt_id,
            request.work_id,
            request.session_id,
            epoch,
            actor=request.actor,
        )
        if connection.execute(  # type: ignore[attr-defined]
            "SELECT 1 FROM execution_invocations WHERE invocation_id = ?",
            (str(request.invocation_id),),
        ).fetchone():
            raise FoundationError("record_exists", "Invocation id is already used")
        connection.execute(  # type: ignore[attr-defined]
            "INSERT INTO execution_invocations(invocation_id, revision, attempt_id, work_id, "
            "session_id, purpose, provider, model, transport, request_sha256, request_bytes, "
            "reserve_units, status, created_at, updated_at) "
            "VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'prepared', ?, ?)",
            (
                str(request.invocation_id),
                str(request.attempt_id),
                str(request.work_id),
                str(request.session_id),
                request.purpose,
                request.provider,
                request.model,
                request.transport,
                request.request_sha256.upper(),
                request.request_bytes,
                request.reserve_units,
                now,
                now,
            ),
        )
        work_id, target_id = request.work_id, request.invocation_id
        result = {"invocation_id": str(target_id), "status": "prepared", "revision": 1}
    elif isinstance(request, (AdmitInvocationRequest, SendInvocationRequest)):
        resource = _check_attempt_basis(
            connection,
            request.attempt_id,
            request.work_id,
            request.session_id,
            epoch,
            actor=request.actor,
        )
        invocation_status = _invocation(
            connection,
            request.invocation_id,
            request.attempt_id,
            request.work_id,
            request.session_id,
        )
        expected = "prepared" if isinstance(request, AdmitInvocationRequest) else "admitted"
        if invocation_status != expected:
            raise FoundationError("stale_invocation", f"Invocation is not {expected}")
        if isinstance(request, AdmitInvocationRequest):
            committed, held = _used_units(connection, request.work_id)
            reserve = int(
                connection.execute(  # type: ignore[attr-defined]
                    "SELECT reserve_units FROM execution_invocations WHERE invocation_id = ?",
                    (str(request.invocation_id),),
                ).fetchone()[0]
            )
            if committed + held + reserve > resource.limit_units:
                raise FoundationError("budget_exhausted", "Model reserve exceeds Work limit")
        next_status = "admitted" if isinstance(request, AdmitInvocationRequest) else "sent"
        connection.execute(  # type: ignore[attr-defined]
            "UPDATE execution_invocations SET status = ?, revision = revision + 1, "
            "updated_at = ? WHERE invocation_id = ?",
            (next_status, now, str(request.invocation_id)),
        )
        work_id, target_id = request.work_id, request.invocation_id
        result = {"invocation_id": str(target_id), "status": next_status}
    elif isinstance(request, FinishInvocationRequest):
        _attempt(
            connection, request.attempt_id, request.work_id, request.session_id, epoch, active=False
        )
        invocation_status = _invocation(
            connection,
            request.invocation_id,
            request.attempt_id,
            request.work_id,
            request.session_id,
        )
        if invocation_status != "sent":
            raise FoundationError(
                "stale_invocation", "Only a sent invocation can record an outcome"
            )
        connection.execute(  # type: ignore[attr-defined]
            "UPDATE execution_invocations SET status = ?, usage_units = ?, http_status = ?, "
            "revision = revision + 1, updated_at = ? WHERE invocation_id = ?",
            (
                request.outcome,
                request.usage_units,
                request.http_status,
                now,
                str(request.invocation_id),
            ),
        )
        work_id, target_id = request.work_id, request.invocation_id
        result = {"invocation_id": str(target_id), "status": request.outcome}
    else:
        raise FoundationError("invalid_request", "Unsupported execution operation")

    attempt_id = request.attempt_id if hasattr(request, "attempt_id") else None
    invocation_id = request.invocation_id if hasattr(request, "invocation_id") else None
    _event(connection, request, work_id, now, attempt_id=attempt_id, invocation_id=invocation_id)
    return result, [{"record_id": str(target_id), "revision": result.get("revision", 1)}]


def upgrade_execution_space(path: Path, authority: LocalAuthority) -> SpaceInfo:
    """Explicit schema 2 to 3 upgrade. Stage 2 to 3 remains a separate choice."""

    with space_connection(path, writable=True) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active" or info.schema_version < 2:
            raise FoundationError("unsupported_schema", "Upgrade Activity/Work before execution")
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.backup",
            epoch=info.execution_epoch,
        )
        if info.schema_version == 2:
            for statement in EXECUTION_SCHEMA_STATEMENTS:
                connection.execute(statement)
            now = utc_now().isoformat()
            connection.execute(
                "INSERT INTO schema_migrations(version, name, sha256, applied_at) "
                "VALUES (3, ?, ?, ?)",
                (EXECUTION_SCHEMA_NAME, EXECUTION_SCHEMA_SHA256, now),
            )
            connection.execute("PRAGMA user_version = 3")
            connection.execute(
                "UPDATE spaces SET state_revision = state_revision + 1 WHERE singleton = 1"
            )
            connection.execute(
                "INSERT INTO maintenance_events(event_id, kind, occurred_at, detail_json) "
                "VALUES (?, 'schema_upgrade', ?, ?)",
                (str(uuid4()), now, canonical_json({"from": 2, "to": 3})),
            )
    return read_space(path)


def read_execution(path: Path, work_id: UUID, authority: LocalAuthority) -> ExecutionSnapshot:
    """Read the current Work, exact bytes, execution ledger and remaining reserve."""

    work = read_work(path, work_id, authority)
    activity = read_activity(path, work.state.activity_id, authority)
    inputs = tuple(
        read_artifact(path, ref.artifact_id, authority, revision=ref.revision)
        for ref in work.state.inputs
        if ref not in work.unavailable_refs
    )
    outputs = tuple(
        read_artifact(path, item.artifact.artifact_id, authority, revision=item.artifact.revision)
        for item in work.state.linked_outputs
        if item.artifact not in work.unavailable_refs
    )
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version != 3 or info.recovery_state != "active":
            raise FoundationError(
                "unsupported_schema", "Execution snapshot requires active schema 3"
            )
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="work",
            resource_id=work_id,
        )
        current_rights: list[Action] = []
        for action in (
            "record.read",
            "work.write",
            "work.accept",
            "work.execute",
            "resource.write",
            "model.invoke",
        ):
            try:
                _authorize(
                    connection,
                    actor=authority.actor,
                    action=action,
                    epoch=info.execution_epoch,
                    resource_type="work",
                    resource_id=work_id,
                )
            except FoundationError as error:
                if error.code not in {"permission_denied", "decision_denied"}:
                    raise
            else:
                current_rights.append(action)
        resource_rows = connection.execute(
            "SELECT resource_id, current_revision, state_json FROM execution_resources "
            "WHERE work_id = ? ORDER BY resource_id",
            (str(work_id),),
        ).fetchall()
        resources = tuple(
            ResourceRevision(
                resource_id=UUID(row[0]),
                work_id=work_id,
                revision=row[1],
                state=ResourceState.model_validate_json(row[2]),
            )
            for row in resource_rows
        )
        attempt_rows = connection.execute(
            "SELECT attempt_id, revision, work_revision, resource_id, resource_revision, "
            "session_id, previous_attempt_id, execution_epoch, generation, input_refs_json, status "
            "FROM execution_attempts WHERE work_id = ? ORDER BY generation",
            (str(work_id),),
        ).fetchall()
        attempts = tuple(
            AttemptRecord(
                attempt_id=UUID(row[0]),
                revision=row[1],
                work_id=work_id,
                work_revision=row[2],
                resource_id=UUID(row[3]),
                resource_revision=row[4],
                session_id=UUID(row[5]),
                previous_attempt_id=UUID(row[6]) if row[6] else None,
                execution_epoch=row[7],
                generation=row[8],
                input_refs=tuple(ArtifactRef.model_validate(item) for item in json.loads(row[9])),
                status=row[10],
            )
            for row in attempt_rows
        )
        invocation_rows = connection.execute(
            "SELECT invocation_id, revision, attempt_id, purpose, provider, model, transport, "
            "request_sha256, request_bytes, reserve_units, usage_units, status, http_status "
            "FROM execution_invocations WHERE work_id = ? ORDER BY created_at, invocation_id",
            (str(work_id),),
        ).fetchall()
        invocations = tuple(
            InvocationRecord(
                invocation_id=UUID(row[0]),
                revision=row[1],
                attempt_id=UUID(row[2]),
                purpose=row[3],
                provider=row[4],
                model=row[5],
                transport=row[6],
                request_sha256=row[7],
                request_bytes=row[8],
                reserve_units=row[9],
                usage_units=row[10],
                status=row[11],
                http_status=row[12],
            )
            for row in invocation_rows
        )
        committed, held = _used_units(connection, work_id)
        limit = min(
            (
                resource.state.limit_units
                for resource in resources
                if resource.state.status == "active"
            ),
            default=None,
        )
        return ExecutionSnapshot(
            space_id=info.space_id,
            execution_epoch=info.execution_epoch,
            activity=activity,
            work=work,
            inputs=inputs,
            outputs=outputs,
            resources=resources,
            attempts=attempts,
            invocations=invocations,
            work_rights=tuple(current_rights),
            limit_units=limit,
            committed_units=committed,
            held_units=held,
            remaining_units=None if limit is None else limit - committed - held,
        )


def read_execution_events(
    path: Path, work_id: UUID, cursor: int, authority: LocalAuthority
) -> tuple[dict[str, object], ...]:
    """Read addressed metadata events; waiting belongs outside the SQLite transaction."""

    if cursor < 0:
        raise FoundationError("invalid_request", "Event cursor must be nonnegative")
    read_work(path, work_id, authority)
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version != 3:
            raise FoundationError("unsupported_schema", "Events require schema 3")
        rows = connection.execute(
            "SELECT sequence, operation_id, attempt_id, invocation_id, kind, created_at "
            "FROM execution_events WHERE work_id = ? AND sequence > ? "
            "ORDER BY sequence LIMIT 100",
            (str(work_id), cursor),
        ).fetchall()
        return tuple(
            {
                "sequence": row[0],
                "operation_id": row[1],
                "attempt_id": row[2],
                "invocation_id": row[3],
                "kind": row[4],
                "created_at": row[5],
            }
            for row in rows
        )
