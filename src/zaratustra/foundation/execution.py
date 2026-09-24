"""Additive interactive execution state owned by the foundation SQLite space."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from .composition import composite_execution_ready
from .models import (
    Action,
    AdmitInvocationRequest,
    AnswerWaitRequest,
    ArtifactRef,
    AssignAttemptRequest,
    AssignmentRecord,
    AttemptRecord,
    ClaimAttemptLaunchRequest,
    CreateResourceRequest,
    ExecutionSnapshot,
    FinishInvocationRequest,
    InvocationRecord,
    OpenWaitRequest,
    OutboxRecord,
    PrepareInvocationRequest,
    PublishAttemptOutputRequest,
    RecordAttemptStopRequest,
    RequestAttemptStopRequest,
    ResourceRevision,
    ResourceState,
    ReviseResourceRequest,
    SendInvocationRequest,
    SpaceInfo,
    StartAttemptRequest,
    StopAttemptRequest,
    WaitRecord,
    WorkState,
)
from .operations import (
    LocalAuthority,
    _authorize,
    _authorize_artifact_ref,
    _local_space,
    read_activity,
    read_artifact,
    read_work,
)
from .storage import (
    CONTINUATION_SCHEMA_NAME,
    CONTINUATION_SCHEMA_SHA256,
    CONTINUATION_SCHEMA_STATEMENTS,
    EXECUTION_SCHEMA_NAME,
    EXECUTION_SCHEMA_SHA256,
    EXECUTION_SCHEMA_STATEMENTS,
    FoundationError,
    canonical_json,
    read_space,
    space_connection,
    utc_now,
)
from .work_status import composition_view, work_status

type ExecutionRequest = (
    CreateResourceRequest
    | ReviseResourceRequest
    | StartAttemptRequest
    | AssignAttemptRequest
    | StopAttemptRequest
    | PrepareInvocationRequest
    | AdmitInvocationRequest
    | SendInvocationRequest
    | FinishInvocationRequest
    | PublishAttemptOutputRequest
)
type ContinuationRequest = (
    ClaimAttemptLaunchRequest
    | OpenWaitRequest
    | AnswerWaitRequest
    | RequestAttemptStopRequest
    | RecordAttemptStopRequest
)


def _event(
    connection: object,
    request: ExecutionRequest | ContinuationRequest,
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
        raise FoundationError(
            "work_closed", f"{state.status.title()} Work cannot receive a new execution"
        )
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
    allowed_assignment_statuses: tuple[str, ...] = ("assigned", "ready"),
) -> ResourceState:
    _no_pending_deletion(connection)
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
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 4:  # type: ignore[attr-defined]
        assignment = connection.execute(  # type: ignore[attr-defined]
            "SELECT status FROM execution_assignments WHERE attempt_id = ?",
            (str(attempt_id),),
        ).fetchone()
        if assignment is not None and assignment[0] not in allowed_assignment_statuses:
            raise FoundationError("attempt_not_ready", "Assigned Attempt cannot send a new effect")
    return resource


def _no_pending_deletion(connection: object) -> None:
    pending = connection.execute(  # type: ignore[attr-defined]
        "SELECT 1 FROM deletion_jobs WHERE status = 'pending' "
        "UNION ALL SELECT 1 FROM subject_deletion_jobs WHERE status = 'pending' LIMIT 1"
    ).fetchone()
    if pending is not None:
        raise FoundationError("deletion_pending", "Finish managed deletion before model execution")


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
    elif isinstance(request, (StartAttemptRequest, AssignAttemptRequest)):
        _no_pending_deletion(connection)
        revision, work_state = _work(connection, request.work_id)
        if revision != request.expected_work_revision:
            raise FoundationError("stale_work", "Work revision changed")
        _current_inputs(connection, work_state, actor=request.actor, epoch=epoch)
        resource = _available_resource(
            connection, request.resource_id, request.work_id, request.expected_resource_revision
        )
        if connection.execute(  # type: ignore[attr-defined]
            "SELECT 1 FROM execution_attempts WHERE attempt_id = ?",
            (str(request.attempt_id),),
        ).fetchone():
            raise FoundationError("record_exists", "Attempt id is already used")
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
        assigned_schema = int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 4  # type: ignore[attr-defined]
        if prior is not None and assigned_schema:
            previous_assignment = connection.execute(  # type: ignore[attr-defined]
                "SELECT status FROM execution_assignments WHERE attempt_id = ?",
                (prior[0],),
            ).fetchone()
            if previous_assignment == ("unknown",):
                raise FoundationError(
                    "resource_busy", "Unknown assigned Attempt still owns the resource"
                )
        busy_query = (
            "SELECT 1 FROM execution_attempts a JOIN execution_resources r "
            "ON r.resource_id = a.resource_id "
            "LEFT JOIN execution_assignments s ON s.attempt_id = a.attempt_id "
            "WHERE (a.status = 'active' OR s.status = 'unknown') "
            "AND r.resource_id != ? AND json_extract(r.state_json, '$.root') = ? LIMIT 1"
            if assigned_schema
            else "SELECT 1 FROM execution_attempts a JOIN execution_resources r "
            "ON r.resource_id = a.resource_id WHERE a.status = 'active' "
            "AND r.resource_id != ? AND json_extract(r.state_json, '$.root') = ? LIMIT 1"
        )
        if (
            resource.mode == "exclusive"
            and connection.execute(  # type: ignore[attr-defined]
                busy_query,
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
        if isinstance(request, AssignAttemptRequest):
            connection.execute(  # type: ignore[attr-defined]
                "INSERT INTO execution_assignments(attempt_id, work_id, revision, "
                "executor_version, status, created_at, updated_at) "
                "VALUES (?, ?, 1, ?, 'assigned', ?, ?)",
                (
                    str(request.attempt_id),
                    str(request.work_id),
                    request.executor_version,
                    now,
                    now,
                ),
            )
            connection.execute(  # type: ignore[attr-defined]
                "INSERT INTO execution_outbox(outbox_id, attempt_id, work_id, wait_id, "
                "execution_epoch, generation, kind, status, created_at) "
                "VALUES (?, ?, ?, NULL, ?, ?, 'launch', 'pending', ?)",
                (
                    str(uuid5(request.attempt_id, "launch")),
                    str(request.attempt_id),
                    str(request.work_id),
                    epoch,
                    generation,
                    now,
                ),
            )
        work_id, target_id = request.work_id, request.attempt_id
        result = {"attempt_id": str(target_id), "generation": generation, "revision": 1}
    elif isinstance(request, StopAttemptRequest):
        if (
            int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 4  # type: ignore[attr-defined]
            and connection.execute(  # type: ignore[attr-defined]
                "SELECT 1 FROM execution_assignments WHERE attempt_id = ?",
                (str(request.attempt_id),),
            ).fetchone()
        ):
            raise FoundationError("assigned_attempt", "Use addressed stop for assigned Attempt")
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


def upgrade_continuation_space(path: Path, authority: LocalAuthority) -> SpaceInfo:
    """Explicit additive schema 3 to 4 upgrade; ordinary reads never upgrade."""

    with space_connection(path, writable=True) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active" or info.schema_version < 3:
            raise FoundationError("unsupported_schema", "Upgrade execution before continuation")
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.backup",
            epoch=info.execution_epoch,
        )
        if info.schema_version == 3:
            for statement in CONTINUATION_SCHEMA_STATEMENTS:
                connection.execute(statement)
            now = utc_now().isoformat()
            connection.execute(
                "INSERT INTO schema_migrations(version, name, sha256, applied_at) "
                "VALUES (4, ?, ?, ?)",
                (CONTINUATION_SCHEMA_NAME, CONTINUATION_SCHEMA_SHA256, now),
            )
            connection.execute("PRAGMA user_version = 4")
            connection.execute(
                "UPDATE spaces SET state_revision = state_revision + 1 WHERE singleton = 1"
            )
            connection.execute(
                "INSERT INTO maintenance_events(event_id, kind, occurred_at, detail_json) "
                "VALUES (?, 'schema_upgrade', ?, ?)",
                (str(uuid4()), now, canonical_json({"from": 3, "to": 4})),
            )
    return read_space(path)


def _assignment(
    connection: object,
    attempt_id: UUID,
    work_id: UUID,
    session_id: UUID,
    epoch: int,
    *,
    active: bool = True,
) -> tuple[int, str, int]:
    _, _, _, generation = _attempt(
        connection, attempt_id, work_id, session_id, epoch, active=active
    )
    row = connection.execute(  # type: ignore[attr-defined]
        "SELECT revision, status FROM execution_assignments WHERE attempt_id = ? AND work_id = ?",
        (str(attempt_id), str(work_id)),
    ).fetchone()
    if row is None:
        raise FoundationError("stale_attempt", "Attempt has no durable assignment")
    return int(row[0]), str(row[1]), generation


def _restored_unknown_stop_assignment(
    connection: object,
    request: RecordAttemptStopRequest,
    epoch: int,
) -> tuple[int, str, int]:
    """Let the current recovery owner confirm only an old unknown stop."""

    row = connection.execute(  # type: ignore[attr-defined]
        "SELECT s.revision, s.status, a.generation, a.status, a.execution_epoch, "
        "a.session_id FROM execution_assignments s JOIN execution_attempts a "
        "ON a.attempt_id = s.attempt_id AND a.work_id = s.work_id "
        "WHERE s.attempt_id = ? AND s.work_id = ?",
        (str(request.attempt_id), str(request.work_id)),
    ).fetchone()
    if row is None or row[5] != str(request.session_id):
        raise FoundationError("stale_attempt", "Attempt is not owned by this session")
    if int(row[4]) >= epoch or row[3] != "interrupted" or row[1] != "unknown":
        raise FoundationError("stale_attempt", "Attempt is not a restored unknown stop")
    recovery = connection.execute(  # type: ignore[attr-defined]
        "SELECT actor FROM operations WHERE kind = 'recover' ORDER BY state_revision DESC LIMIT 1"
    ).fetchone()
    if recovery is None or recovery[0] != request.actor:
        raise FoundationError(
            "permission_denied", "Only the current recovery owner can confirm stop"
        )
    return int(row[0]), str(row[1]), int(row[2])


def apply_continuation_change(
    connection: object,
    request: ContinuationRequest,
    *,
    now: str,
    epoch: int,
    authority_source: str,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Apply one addressed continuation change inside the receipt transaction."""

    if isinstance(request, ClaimAttemptLaunchRequest):
        _check_attempt_basis(
            connection,
            request.attempt_id,
            request.work_id,
            request.session_id,
            epoch,
            actor=request.actor,
            allowed_assignment_statuses=("assigned",),
        )
        revision, status, _ = _assignment(
            connection, request.attempt_id, request.work_id, request.session_id, epoch
        )
        if revision != request.expected_assignment_revision or status != "assigned":
            raise FoundationError("stale_assignment", "Assignment changed before launch")
        result = {"attempt_id": str(request.attempt_id), "launch_claimed": True}
        targets = [{"record_id": str(request.attempt_id), "revision": revision}]
    elif isinstance(request, OpenWaitRequest):
        _check_attempt_basis(
            connection,
            request.attempt_id,
            request.work_id,
            request.session_id,
            epoch,
            actor=request.actor,
        )
        revision, status, _ = _assignment(
            connection, request.attempt_id, request.work_id, request.session_id, epoch
        )
        if revision != request.expected_assignment_revision or status not in ("assigned", "ready"):
            raise FoundationError("stale_assignment", "Assignment changed or cannot ask")
        if connection.execute(  # type: ignore[attr-defined]
            "SELECT 1 FROM execution_waits WHERE wait_id = ?",
            (str(request.wait_id),),
        ).fetchone():
            raise FoundationError("record_exists", "Wait id is already used")
        if connection.execute(  # type: ignore[attr-defined]
            "SELECT 1 FROM execution_waits WHERE attempt_id = ? AND status = 'open'",
            (str(request.attempt_id),),
        ).fetchone():
            raise FoundationError("wait_open", "This Attempt already has an open wait")
        for reference in request.partial_refs:
            _authorize_artifact_ref(
                connection,
                reference,
                actor=request.actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            )
        connection.execute(  # type: ignore[attr-defined]
            "INSERT INTO execution_waits(wait_id, attempt_id, work_id, revision, status, "
            "question, expected_actor, remainder, partial_refs_json, created_at, updated_at) "
            "VALUES (?, ?, ?, 1, 'open', ?, ?, ?, ?, ?, ?)",
            (
                str(request.wait_id),
                str(request.attempt_id),
                str(request.work_id),
                request.question.encode("utf-8"),
                request.expected_actor,
                request.remainder.encode("utf-8"),
                canonical_json([ref.model_dump(mode="json") for ref in request.partial_refs]),
                now,
                now,
            ),
        )
        connection.execute(  # type: ignore[attr-defined]
            "UPDATE execution_assignments SET revision = revision + 1, "
            "status = 'waiting', updated_at = ? WHERE attempt_id = ?",
            (now, str(request.attempt_id)),
        )
        result = {"wait_id": str(request.wait_id), "status": "open", "revision": 1}
        targets = [{"record_id": str(request.wait_id), "revision": 1}]
    elif isinstance(request, AnswerWaitRequest):
        _check_attempt_basis(
            connection,
            request.attempt_id,
            request.work_id,
            request.session_id,
            epoch,
            actor=request.actor,
            allowed_assignment_statuses=("waiting",),
        )
        _, assignment_status, generation = _assignment(
            connection, request.attempt_id, request.work_id, request.session_id, epoch
        )
        row = connection.execute(  # type: ignore[attr-defined]
            "SELECT revision, status, expected_actor FROM execution_waits "
            "WHERE wait_id = ? AND attempt_id = ? AND work_id = ?",
            (str(request.wait_id), str(request.attempt_id), str(request.work_id)),
        ).fetchone()
        if row is None or int(row[0]) != request.expected_wait_revision or row[1] != "open":
            raise FoundationError("stale_wait", "Wait changed or is closed")
        if assignment_status != "waiting" or row[2] != request.actor:
            raise FoundationError("permission_denied", "Answer is not from the expected actor")
        connection.execute(  # type: ignore[attr-defined]
            "UPDATE execution_waits SET revision = revision + 1, status = 'answered', "
            "answer = ?, answer_source = ?, updated_at = ? WHERE wait_id = ?",
            (request.answer.encode("utf-8"), authority_source, now, str(request.wait_id)),
        )
        connection.execute(  # type: ignore[attr-defined]
            "UPDATE execution_assignments SET revision = revision + 1, "
            "status = 'ready', updated_at = ? WHERE attempt_id = ?",
            (now, str(request.attempt_id)),
        )
        outbox_id = uuid5(request.wait_id, "answer-continuation")
        connection.execute(  # type: ignore[attr-defined]
            "INSERT INTO execution_outbox(outbox_id, attempt_id, work_id, wait_id, "
            "execution_epoch, generation, kind, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'resume', 'pending', ?)",
            (
                str(outbox_id),
                str(request.attempt_id),
                str(request.work_id),
                str(request.wait_id),
                epoch,
                generation,
                now,
            ),
        )
        result = {
            "wait_id": str(request.wait_id),
            "status": "answered",
            "outbox_id": str(outbox_id),
        }
        targets = [
            {"record_id": str(request.wait_id), "revision": request.expected_wait_revision + 1},
            {"record_id": str(outbox_id), "revision": 1},
        ]
    elif isinstance(request, RequestAttemptStopRequest):
        revision, status, _ = _assignment(
            connection, request.attempt_id, request.work_id, request.session_id, epoch
        )
        if revision != request.expected_assignment_revision or status not in (
            "assigned",
            "waiting",
            "ready",
        ):
            raise FoundationError("stale_assignment", "Assignment changed or is stopping")
        connection.execute(  # type: ignore[attr-defined]
            "UPDATE execution_assignments SET revision = revision + 1, "
            "status = 'stop_requested', stop_reason = ?, updated_at = ? WHERE attempt_id = ?",
            (request.reason.encode("utf-8"), now, str(request.attempt_id)),
        )
        connection.execute(  # type: ignore[attr-defined]
            "UPDATE execution_outbox SET status = 'cancelled' "
            "WHERE attempt_id = ? AND status = 'pending'",
            (str(request.attempt_id),),
        )
        result = {"attempt_id": str(request.attempt_id), "status": "stop_requested"}
        targets = [{"record_id": str(request.attempt_id), "revision": revision + 1}]
    else:
        assert isinstance(request, RecordAttemptStopRequest)
        if request.outcome == "stopped":
            attempt = connection.execute(  # type: ignore[attr-defined]
                "SELECT execution_epoch FROM execution_attempts WHERE attempt_id = ? "
                "AND work_id = ?",
                (str(request.attempt_id), str(request.work_id)),
            ).fetchone()
            if attempt is not None and int(attempt[0]) < epoch:
                revision, status, _ = _restored_unknown_stop_assignment(connection, request, epoch)
            else:
                revision, status, _ = _assignment(
                    connection, request.attempt_id, request.work_id, request.session_id, epoch
                )
        else:
            revision, status, _ = _assignment(
                connection, request.attempt_id, request.work_id, request.session_id, epoch
            )
        if revision != request.expected_assignment_revision or status not in (
            "stop_requested",
            "unknown",
        ):
            raise FoundationError("stale_assignment", "No matching stop request")
        if status == "unknown" and request.outcome != "stopped":
            raise FoundationError(
                "stale_assignment", "Unknown stop can only be resolved as stopped"
            )
        connection.execute(  # type: ignore[attr-defined]
            "UPDATE execution_assignments SET revision = revision + 1, status = ?, "
            "updated_at = ? WHERE attempt_id = ?",
            (request.outcome, now, str(request.attempt_id)),
        )
        if request.outcome == "stopped":
            connection.execute(  # type: ignore[attr-defined]
                "UPDATE execution_waits SET status = 'closed', revision = revision + 1, "
                "updated_at = ? WHERE attempt_id = ? AND status = 'open'",
                (now, str(request.attempt_id)),
            )
            connection.execute(  # type: ignore[attr-defined]
                "UPDATE execution_invocations SET status = 'unknown', revision = revision + 1, "
                "updated_at = ? WHERE attempt_id = ? AND status IN ('admitted', 'sent')",
                (now, str(request.attempt_id)),
            )
            connection.execute(  # type: ignore[attr-defined]
                "UPDATE execution_attempts SET status = 'interrupted', revision = revision + 1, "
                "updated_at = ? WHERE attempt_id = ? AND status = 'active'",
                (now, str(request.attempt_id)),
            )
        result = {"attempt_id": str(request.attempt_id), "status": request.outcome}
        targets = [{"record_id": str(request.attempt_id), "revision": revision + 1}]
    _event(connection, request, request.work_id, now, attempt_id=request.attempt_id)
    return result, targets


def read_assigned_control(
    path: Path, work_id: UUID, attempt_id: UUID, authority: LocalAuthority
) -> bool:
    """Read one claimed Attempt's current stop gate without loading Work payload."""

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 4 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Assigned control needs active schema 4")
        for action in ("record.read", "work.execute", "model.invoke"):
            _authorize(
                connection,
                actor=authority.actor,
                action=action,
                epoch=info.execution_epoch,
                resource_type="work",
                resource_id=work_id,
            )
        if not composite_execution_ready(
            connection, work_id, attempt_id, actor=authority.actor, epoch=info.execution_epoch
        ):
            return False
        row = connection.execute(
            "SELECT assignment.status, attempt.status, attempt.execution_epoch "
            "FROM execution_assignments AS assignment "
            "JOIN execution_attempts AS attempt ON attempt.attempt_id = assignment.attempt_id "
            "WHERE assignment.work_id = ? AND assignment.attempt_id = ?",
            (str(work_id), str(attempt_id)),
        ).fetchone()
        return bool(
            row is not None
            and row[0] in ("assigned", "waiting", "ready")
            and row[1] == "active"
            and row[2] == info.execution_epoch
        )


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
        if info.schema_version < 3 or info.recovery_state != "active":
            raise FoundationError(
                "unsupported_schema", "Execution snapshot requires active execution schema"
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
        assignments: tuple[AssignmentRecord, ...] = ()
        waits: tuple[WaitRecord, ...] = ()
        outbox: tuple[OutboxRecord, ...] = ()
        if info.schema_version >= 4:
            assignment_rows = connection.execute(
                "SELECT attempt_id, revision, executor_version, status, stop_reason "
                "FROM execution_assignments WHERE work_id = ? ORDER BY created_at, attempt_id",
                (str(work_id),),
            ).fetchall()
            assignments = tuple(
                AssignmentRecord(
                    attempt_id=UUID(row[0]),
                    work_id=work_id,
                    revision=row[1],
                    executor_version=row[2],
                    status=row[3],
                    stop_reason=bytes(row[4]).decode("utf-8") if row[4] is not None else None,
                )
                for row in assignment_rows
            )
            wait_rows = connection.execute(
                "SELECT wait_id, attempt_id, revision, status, question, expected_actor, "
                "remainder, partial_refs_json, answer, answer_source "
                "FROM execution_waits WHERE work_id = ? ORDER BY created_at, wait_id",
                (str(work_id),),
            ).fetchall()
            waits = tuple(
                WaitRecord(
                    wait_id=UUID(row[0]),
                    attempt_id=UUID(row[1]),
                    work_id=work_id,
                    revision=row[2],
                    status=row[3],
                    question=bytes(row[4]).decode("utf-8") if row[4] is not None else None,
                    expected_actor=row[5],
                    remainder=bytes(row[6]).decode("utf-8") if row[6] is not None else None,
                    partial_refs=tuple(
                        ArtifactRef.model_validate(item) for item in json.loads(row[7])
                    ),
                    answer=bytes(row[8]).decode("utf-8") if row[8] is not None else None,
                    answer_source=row[9],
                )
                for row in wait_rows
            )
            outbox_rows = connection.execute(
                "SELECT outbox_id, attempt_id, wait_id, execution_epoch, generation, "
                "kind, status FROM execution_outbox WHERE work_id = ? "
                "ORDER BY created_at, outbox_id",
                (str(work_id),),
            ).fetchall()
            outbox = tuple(
                OutboxRecord(
                    outbox_id=UUID(row[0]),
                    attempt_id=UUID(row[1]),
                    work_id=work_id,
                    wait_id=UUID(row[2]) if row[2] else None,
                    execution_epoch=row[3],
                    generation=row[4],
                    kind=row[5],
                    status=row[6],
                )
                for row in outbox_rows
            )
        committed, held = _used_units(connection, work_id)
        status = work_status(connection, work_id)
        composition = composition_view(connection, work_id)
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
            assignments=assignments,
            waits=waits,
            outbox=outbox,
            work_rights=tuple(current_rights),
            limit_units=limit,
            committed_units=committed,
            held_units=held,
            remaining_units=None if limit is None else limit - committed - held,
            status=status,
            composition=composition,
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
        if info.schema_version < 3:
            raise FoundationError("unsupported_schema", "Events require execution schema")
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
