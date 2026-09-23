"""The sole domain mutation path and current Decision/Grant enforcement."""

from __future__ import annotations

import hashlib
import json
import shutil
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4, uuid5

from pydantic import JsonValue, TypeAdapter, ValidationError

from .models import (
    ALL_ACTIONS,
    AcceptWorkRequest,
    Action,
    ActivityRevision,
    ActivityState,
    AdmitInvocationRequest,
    ArtifactRef,
    ArtifactRevision,
    BackupInfo,
    BootstrapRequest,
    CreateActivityRequest,
    CreateArtifactRequest,
    CreateDecisionRequest,
    CreateGrantRequest,
    CreateResourceRequest,
    CreateWorkRequest,
    DecisionState,
    DeleteActivityRequest,
    DeleteArtifactRequest,
    DeleteWorkRequest,
    DeletionStatus,
    DomainRequest,
    FinishInvocationRequest,
    GrantState,
    LinkedOutput,
    LinkWorkOutputRequest,
    OperationAuditEntry,
    OperationReceipt,
    PrepareInvocationRequest,
    ProvenanceRef,
    PublishAttemptOutputRequest,
    RecordSummary,
    RecoverRequest,
    ReviseActivityRequest,
    ReviseArtifactRequest,
    ReviseDecisionRequest,
    ReviseResourceRequest,
    RevokeGrantRequest,
    SendInvocationRequest,
    SpaceInfo,
    SpaceInspection,
    StartAttemptRequest,
    StopAttemptRequest,
    WorkAcceptance,
    WorkRevision,
    WorkState,
)
from .storage import (
    DATABASE_NAME,
    SUBJECT_SCHEMA_NAME,
    SUBJECT_SCHEMA_SHA256,
    SUBJECT_SCHEMA_STATEMENTS,
    FoundationError,
    backup_database,
    canonical_json,
    initialize_space,
    layout,
    load_backup,
    read_space,
    restore_database,
    sanitize_database,
    space_connection,
    utc_now,
)


@dataclass(frozen=True)
class LocalAuthority:
    """Trusted local adapter value, never parsed from operation/model payload."""

    actor: str
    source_ref: str
    established_at: datetime
    space_root: Path
    space_id: UUID
    execution_epoch: int


@dataclass(frozen=True)
class RecoveryAuthority:
    """Fresh trusted-local recovery source that is not restored from a backup."""

    actor: str
    source_ref: str
    established_at: datetime


type Authority = LocalAuthority | RecoveryAuthority
REQUEST_ADAPTER: TypeAdapter[DomainRequest] = TypeAdapter(DomainRequest)


def authorize_local(path: Path, *, actor: str, source_ref: str) -> LocalAuthority:
    """Trusted adapter seam; call only after actual local permission is established."""

    if not actor.strip() or not source_ref.strip():
        raise FoundationError("permission_denied", "Trusted authority needs actor and source")
    info = read_space(path)
    if info.recovery_state != "active":
        raise FoundationError("permission_denied", "Quarantined space needs recovery authority")
    return LocalAuthority(
        actor=actor,
        source_ref=source_ref,
        established_at=utc_now(),
        space_root=info.root,
        space_id=info.space_id,
        execution_epoch=info.execution_epoch,
    )


def authorize_recovery(*, actor: str, source_ref: str) -> RecoveryAuthority:
    """Trusted recovery seam; backed-up fields never create this value."""

    if not actor.strip() or not source_ref.strip():
        raise FoundationError("permission_denied", "Recovery needs a fresh trusted source")
    return RecoveryAuthority(actor=actor, source_ref=source_ref, established_at=utc_now())


def fingerprint(request: DomainRequest) -> str:
    body = canonical_json(request.model_dump(mode="json"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest().upper()


def _validated_request(request: DomainRequest) -> DomainRequest:
    try:
        return REQUEST_ADAPTER.validate_python(request.model_dump(mode="python"))
    except (AttributeError, ValidationError) as error:
        raise FoundationError("invalid_request", str(error)) from error


def _authority_actor(request: DomainRequest, authority: Authority) -> None:
    if authority.actor != request.actor:
        raise FoundationError("permission_denied", "Authority is not the request actor")


def _local_space(authority: LocalAuthority, info: SpaceInfo) -> None:
    if (
        authority.space_root != info.root
        or authority.space_id != info.space_id
        or authority.execution_epoch != info.execution_epoch
    ):
        raise FoundationError("permission_denied", "Authority belongs to another space or epoch")


def _current_bodies(connection: object, kind: str) -> list[tuple[str, int, str]]:
    rows = connection.execute(  # type: ignore[attr-defined]
        "SELECT r.record_id, r.current_revision, v.body_json "
        "FROM records r JOIN record_revisions v "
        "ON v.record_id = r.record_id AND v.revision = r.current_revision "
        "WHERE r.kind = ? ORDER BY r.record_id",
        (kind,),
    ).fetchall()
    return cast(list[tuple[str, int, str]], rows)


def _authorize(
    connection: object,
    *,
    actor: str,
    action: Action,
    epoch: int,
    resource_type: str = "space",
    resource_id: UUID | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    decisions: list[dict[str, object]] = []
    for record_id, revision, raw in _current_bodies(connection, "decision"):
        decision_state = DecisionState.model_validate_json(raw)
        if decision_state.status != "active" or action not in decision_state.actions:
            continue
        if "*" not in decision_state.subjects and actor not in decision_state.subjects:
            continue
        reference = {"record_id": record_id, "revision": revision}
        decisions.append(reference)
        if decision_state.effect == "deny":
            raise FoundationError(
                "decision_denied", f"Active Decision {record_id}@{revision} denies {action}"
            )

    grants: list[dict[str, object]] = []
    for record_id, revision, raw in _current_bodies(connection, "grant"):
        body = json.loads(raw)
        grant_state = GrantState.model_validate(body["state"])
        if int(body["epoch"]) != epoch or grant_state.status != "active":
            continue
        if grant_state.grantee != actor or action not in grant_state.actions:
            continue
        scoped = grant_state.resource_type == "space" or (
            grant_state.resource_type == resource_type and grant_state.resource_id == resource_id
        )
        if scoped:
            grants.append({"record_id": record_id, "revision": revision})
    if not grants:
        raise FoundationError(
            "permission_denied", f"No current Grant permits {actor} to perform {action}"
        )
    return grants, decisions


def _receipt_from_row(raw: str) -> OperationReceipt:
    try:
        return OperationReceipt.model_validate_json(raw)
    except ValidationError as error:
        raise FoundationError("corrupt_space", f"Invalid receipt: {error}") from error


def _saved_receipt(connection: object, operation_id: UUID) -> tuple[str, str] | None:
    row = connection.execute(  # type: ignore[attr-defined]
        "SELECT fingerprint, receipt_json FROM receipts WHERE operation_id = ?",
        (str(operation_id),),
    ).fetchone()
    return cast(tuple[str, str] | None, row)


def _current_revision(
    connection: object, record_id: UUID, expected_kind: str
) -> tuple[int, str, str]:
    row = connection.execute(  # type: ignore[attr-defined]
        "SELECT current_revision, kind, status FROM records WHERE record_id = ?",
        (str(record_id),),
    ).fetchone()
    if row is None or row[1] != expected_kind:
        raise FoundationError("not_found", f"No {expected_kind} record {record_id}")
    return int(row[0]), str(row[1]), str(row[2])


def _expect_absent(connection: object, record_id: UUID) -> None:
    row = connection.execute(  # type: ignore[attr-defined]
        "SELECT 1 FROM records WHERE record_id = ?", (str(record_id),)
    ).fetchone()
    if row is not None:
        raise FoundationError("record_exists", f"Record already exists: {record_id}")
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])  # type: ignore[attr-defined]
    if version == 2:
        row = connection.execute(  # type: ignore[attr-defined]
            "SELECT 1 FROM subject_records WHERE record_id = ?", (str(record_id),)
        ).fetchone()
        if row is not None:
            raise FoundationError("record_exists", f"Record already exists: {record_id}")


def _expect_revision(
    connection: object,
    record_id: UUID,
    kind: str,
    expected: int,
    *,
    required_status: str | None = None,
) -> None:
    current, _, status = _current_revision(connection, record_id, kind)
    if current != expected:
        raise FoundationError(
            "stale_revision", f"Expected {record_id}@{expected}; current revision is {current}"
        )
    if required_status is not None and status != required_status:
        raise FoundationError(
            "content_unavailable",
            f"{kind.title()} {record_id} is {status}; it cannot be changed",
        )


def _insert_record(
    connection: object,
    *,
    record_id: UUID,
    kind: str,
    operation_id: UUID,
    actor: str,
    now: str,
    status: str,
    body: dict[str, object],
    revision: int = 1,
) -> None:
    if revision == 1:
        connection.execute(  # type: ignore[attr-defined]
            "INSERT INTO records("
            "record_id, kind, current_revision, status, created_at, updated_at) "
            "VALUES (?, ?, 1, ?, ?, ?)",
            (str(record_id), kind, status, now, now),
        )
    else:
        connection.execute(  # type: ignore[attr-defined]
            "UPDATE records SET current_revision = ?, status = ?, updated_at = ? "
            "WHERE record_id = ?",
            (revision, status, now, str(record_id)),
        )
    connection.execute(  # type: ignore[attr-defined]
        "INSERT INTO record_revisions(record_id, revision, operation_id, created_at, actor, "
        "status, body_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            str(record_id),
            revision,
            str(operation_id),
            now,
            actor,
            status,
            canonical_json(body),
        ),
    )


def _validate_provenance(connection: object, provenance: tuple[ProvenanceRef, ...]) -> None:
    for source in provenance:
        if source.record_id is None:
            continue
        row = connection.execute(  # type: ignore[attr-defined]
            "SELECT 1 FROM record_revisions WHERE record_id = ? AND revision = ?",
            (str(source.record_id), source.revision),
        ).fetchone()
        if row is None:
            raise FoundationError(
                "invalid_provenance",
                f"Missing exact source {source.record_id}@{source.revision}",
            )


def _write_artifact(
    connection: object,
    request: CreateArtifactRequest | ReviseArtifactRequest,
    now: str,
    revision: int,
) -> None:
    _validate_provenance(connection, request.provenance)
    _insert_record(
        connection,
        record_id=request.artifact_id,
        kind="artifact",
        operation_id=request.operation_id,
        actor=request.actor,
        now=now,
        status="active",
        body={"status": "active"},
        revision=revision,
    )
    digest = hashlib.sha256(request.content).hexdigest().upper()
    connection.execute(  # type: ignore[attr-defined]
        "INSERT INTO managed_content(record_id, revision, media_type, payload, sha256) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(request.artifact_id), revision, request.media_type, request.content, digest),
    )
    for ordinal, source in enumerate(request.provenance):
        connection.execute(  # type: ignore[attr-defined]
            "INSERT INTO revision_provenance(record_id, revision, ordinal, relation, "
            "source_record_id, source_revision, external_ref) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(request.artifact_id),
                revision,
                ordinal,
                source.relation,
                str(source.record_id) if source.record_id else None,
                source.revision,
                source.external_ref,
            ),
        )


def _root_decision() -> DecisionState:
    return DecisionState(
        statement="Every controlled foundation action requires a current matching Grant.",
        effect="require_grant",
        actions=ALL_ACTIONS,
        subjects=("*",),
    )


def _write_root(
    connection: object,
    request: BootstrapRequest | RecoverRequest,
    now: str,
    epoch: int,
) -> list[dict[str, object]]:
    for record_id in (request.decision_id, request.grant_id):
        _expect_absent(connection, record_id)
    decision = _root_decision()
    grant = GrantState(grantee=request.actor, actions=ALL_ACTIONS)
    _insert_record(
        connection,
        record_id=request.decision_id,
        kind="decision",
        operation_id=request.operation_id,
        actor=request.actor,
        now=now,
        status=decision.status,
        body=cast(dict[str, object], decision.model_dump(mode="json")),
    )
    _insert_record(
        connection,
        record_id=request.grant_id,
        kind="grant",
        operation_id=request.operation_id,
        actor=request.actor,
        now=now,
        status=grant.status,
        body={"epoch": epoch, "state": grant.model_dump(mode="json")},
    )
    if (
        isinstance(request, RecoverRequest)
        and int(connection.execute("PRAGMA user_version").fetchone()[0])  # type: ignore[attr-defined]
        >= 3
    ):
        connection.execute(  # type: ignore[attr-defined]
            "UPDATE execution_invocations SET status = 'unknown', revision = revision + 1, "
            "updated_at = ? WHERE status IN ('admitted', 'sent')",
            (now,),
        )
        connection.execute(  # type: ignore[attr-defined]
            "UPDATE execution_attempts SET status = 'interrupted', revision = revision + 1, "
            "updated_at = ? WHERE status = 'active'",
            (now,),
        )
    return [
        {"record_id": str(request.decision_id), "revision": 1},
        {"record_id": str(request.grant_id), "revision": 1},
    ]


def _operation_action(request: DomainRequest) -> tuple[Action, str, UUID | None]:
    if isinstance(request, (CreateResourceRequest, ReviseResourceRequest)):
        return "resource.write", "work", request.work_id
    if isinstance(request, (StartAttemptRequest, StopAttemptRequest)):
        return "work.execute", "work", request.work_id
    if isinstance(
        request,
        (
            PrepareInvocationRequest,
            AdmitInvocationRequest,
            SendInvocationRequest,
            FinishInvocationRequest,
        ),
    ):
        return "model.invoke", "work", request.work_id
    if isinstance(request, (CreateArtifactRequest, ReviseArtifactRequest, DeleteArtifactRequest)):
        return "artifact.write", "artifact", request.artifact_id
    if isinstance(request, (CreateDecisionRequest, ReviseDecisionRequest)):
        return "decision.write", "space", None
    if isinstance(request, (CreateGrantRequest, RevokeGrantRequest)):
        return "grant.write", "space", None
    if isinstance(request, CreateActivityRequest):
        return "activity.write", "space", None
    if isinstance(request, (ReviseActivityRequest, DeleteActivityRequest)):
        return "activity.write", "activity", request.activity_id
    if isinstance(request, CreateWorkRequest):
        return "work.write", "activity", request.state.activity_id
    if isinstance(request, (LinkWorkOutputRequest, PublishAttemptOutputRequest, DeleteWorkRequest)):
        return "work.write", "work", request.work_id
    if isinstance(request, AcceptWorkRequest):
        return "work.accept", "work", request.work_id
    raise FoundationError("invalid_request", f"No ordinary action for {request.kind}")


def _subject_current(connection: object, record_id: UUID, kind: str) -> tuple[int, str, str | None]:
    row = connection.execute(  # type: ignore[attr-defined]
        "SELECT current_revision, status, parent_id FROM subject_records "
        "WHERE record_id = ? AND kind = ?",
        (str(record_id), kind),
    ).fetchone()
    if row is None:
        raise FoundationError("not_found", f"No {kind} record {record_id}")
    return int(row[0]), str(row[1]), str(row[2]) if row[2] else None


def _subject_state(connection: object, record_id: UUID, revision: int) -> dict[str, object]:
    row = connection.execute(  # type: ignore[attr-defined]
        "SELECT c.payload, c.sha256 FROM subject_revisions r LEFT JOIN subject_content c "
        "ON c.record_id = r.record_id AND c.revision = r.revision "
        "WHERE r.record_id = ? AND r.revision = ?",
        (str(record_id), revision),
    ).fetchone()
    if row is None:
        raise FoundationError("not_found", f"No exact subject revision {record_id}@{revision}")
    if row[0] is None:
        raise FoundationError("content_unavailable", f"Subject content is unavailable: {record_id}")
    payload = bytes(row[0])
    if hashlib.sha256(payload).hexdigest().upper() != row[1]:
        raise FoundationError("corrupt_space", f"Subject content digest mismatch: {record_id}")
    return cast(dict[str, object], json.loads(payload))


def _subject_expect(connection: object, record_id: UUID, kind: str, expected: int) -> None:
    revision, status, _ = _subject_current(connection, record_id, kind)
    if revision != expected:
        raise FoundationError(
            "stale_revision", f"Expected {record_id}@{expected}; current revision is {revision}"
        )
    if status == "deleted":
        raise FoundationError("content_unavailable", f"{kind.title()} {record_id} was deleted")


def _write_subject(
    connection: object,
    *,
    record_id: UUID,
    kind: str,
    parent_id: UUID | None,
    operation_id: UUID,
    actor: str,
    now: str,
    status: str,
    state: ActivityState | WorkState,
    revision: int,
) -> None:
    if revision == 1:
        _expect_absent(connection, record_id)
        connection.execute(  # type: ignore[attr-defined]
            "INSERT INTO subject_records(record_id, kind, parent_id, current_revision, "
            "status, created_at, updated_at) VALUES (?, ?, ?, 1, ?, ?, ?)",
            (str(record_id), kind, str(parent_id) if parent_id else None, status, now, now),
        )
    else:
        connection.execute(  # type: ignore[attr-defined]
            "UPDATE subject_records SET current_revision = ?, status = ?, updated_at = ? "
            "WHERE record_id = ?",
            (revision, status, now, str(record_id)),
        )
    connection.execute(  # type: ignore[attr-defined]
        "INSERT INTO subject_revisions(record_id, revision, operation_id, created_at, "
        "actor, status) VALUES (?, ?, ?, ?, ?, ?)",
        (str(record_id), revision, str(operation_id), now, actor, status),
    )
    payload = canonical_json(state.model_dump(mode="json")).encode("utf-8")
    connection.execute(  # type: ignore[attr-defined]
        "INSERT INTO subject_content(record_id, revision, payload, sha256) VALUES (?, ?, ?, ?)",
        (str(record_id), revision, payload, hashlib.sha256(payload).hexdigest().upper()),
    )


def _artifact_reference(
    connection: object,
    reference: ArtifactRef,
    *,
    media_type: str | None = None,
) -> None:
    row = connection.execute(  # type: ignore[attr-defined]
        "SELECT r.status, c.media_type FROM records r "
        "JOIN managed_content c ON c.record_id = r.record_id "
        "WHERE r.record_id = ? AND r.kind = 'artifact' AND c.revision = ?",
        (str(reference.artifact_id), reference.revision),
    ).fetchone()
    if row is None or row[0] != "active":
        raise FoundationError(
            "content_unavailable",
            f"Artifact {reference.artifact_id}@{reference.revision} is unavailable",
        )
    if media_type is not None and row[1] != media_type:
        raise FoundationError("output_mismatch", "Artifact media type differs from output contract")


def _authorize_artifact_ref(
    connection: object,
    reference: ArtifactRef,
    *,
    actor: str,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
    media_type: str | None = None,
) -> None:
    extra_grants, extra_decisions = _authorize(
        connection,
        actor=actor,
        action="record.read",
        epoch=epoch,
        resource_type="artifact",
        resource_id=reference.artifact_id,
    )
    grants.extend(reference for reference in extra_grants if reference not in grants)
    decisions.extend(reference for reference in extra_decisions if reference not in decisions)
    _artifact_reference(connection, reference, media_type=media_type)


def _subject_delete(
    connection: object,
    *,
    record_id: UUID,
    kind: str,
    expected_revision: int,
    operation_id: UUID,
    actor: str,
    now: str,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    _subject_expect(connection, record_id, kind, expected_revision)
    if kind == "activity":
        active_work = connection.execute(  # type: ignore[attr-defined]
            "SELECT 1 FROM subject_records WHERE kind = 'work' AND parent_id = ? "
            "AND status != 'deleted' LIMIT 1",
            (str(record_id),),
        ).fetchone()
        if active_work is not None:
            raise FoundationError("dependent_work", "Delete the Activity's Works first")
    prior_operations = [
        row[0]
        for row in connection.execute(  # type: ignore[attr-defined]
            "SELECT operation_id FROM subject_revisions WHERE record_id = ?",
            (str(record_id),),
        ).fetchall()
    ]
    connection.executemany(  # type: ignore[attr-defined]
        "DELETE FROM receipts WHERE operation_id = ?",
        ((prior_id,) for prior_id in prior_operations),
    )
    connection.executemany(  # type: ignore[attr-defined]
        "UPDATE operations SET fingerprint = 'DELETED' WHERE operation_id = ?",
        ((prior_id,) for prior_id in prior_operations),
    )
    revision = expected_revision + 1
    connection.execute(  # type: ignore[attr-defined]
        "UPDATE subject_records SET current_revision = ?, status = 'deleted', "
        "updated_at = ? WHERE record_id = ?",
        (revision, now, str(record_id)),
    )
    connection.execute(  # type: ignore[attr-defined]
        "INSERT INTO subject_revisions(record_id, revision, operation_id, created_at, "
        "actor, status) VALUES (?, ?, ?, ?, ?, 'deleted')",
        (str(record_id), revision, str(operation_id), now, actor),
    )
    connection.execute(  # type: ignore[attr-defined]
        "DELETE FROM subject_content WHERE record_id = ?", (str(record_id),)
    )
    if kind == "work" and int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 3:  # type: ignore[attr-defined]
        execution_operations = [
            row[0]
            for row in connection.execute(  # type: ignore[attr-defined]
                "SELECT operation_id FROM execution_events WHERE work_id = ?", (str(record_id),)
            ).fetchall()
        ]
        connection.executemany(  # type: ignore[attr-defined]
            "DELETE FROM receipts WHERE operation_id = ?",
            ((saved_id,) for saved_id in execution_operations),
        )
        connection.executemany(  # type: ignore[attr-defined]
            "UPDATE operations SET fingerprint = 'DELETED' WHERE operation_id = ?",
            ((saved_id,) for saved_id in execution_operations),
        )
        connection.execute("DELETE FROM execution_events WHERE work_id = ?", (str(record_id),))  # type: ignore[attr-defined]
        connection.execute("DELETE FROM execution_invocations WHERE work_id = ?", (str(record_id),))  # type: ignore[attr-defined]
        connection.execute("DELETE FROM execution_attempts WHERE work_id = ?", (str(record_id),))  # type: ignore[attr-defined]
        connection.execute(  # type: ignore[attr-defined]
            "DELETE FROM execution_resource_revisions WHERE resource_id IN "
            "(SELECT resource_id FROM execution_resources WHERE work_id = ?)",
            (str(record_id),),
        )
        connection.execute("DELETE FROM execution_resources WHERE work_id = ?", (str(record_id),))  # type: ignore[attr-defined]
    connection.execute(  # type: ignore[attr-defined]
        "INSERT INTO subject_deletion_jobs(operation_id, record_id, status, created_at) "
        "VALUES (?, ?, 'pending', ?)",
        (str(operation_id), str(record_id), now),
    )
    connection.execute(  # type: ignore[attr-defined]
        "UPDATE backup_inventory SET status = 'contaminated' "
        "WHERE status IN ('planned', 'failed') OR (status = 'complete' AND backup_id IN "
        "(SELECT backup_id FROM backup_subjects WHERE record_id = ?))",
        (str(record_id),),
    )
    return (
        {"record_id": str(record_id), "revision": revision, "content": "unavailable"},
        [{"record_id": str(record_id), "revision": revision}],
    )


def _apply_subject_change(
    connection: object,
    request: (
        CreateActivityRequest
        | ReviseActivityRequest
        | DeleteActivityRequest
        | CreateWorkRequest
        | LinkWorkOutputRequest
        | AcceptWorkRequest
        | DeleteWorkRequest
    ),
    *,
    now: str,
    epoch: int,
    authority: LocalAuthority,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if isinstance(request, CreateActivityRequest):
        _write_subject(
            connection,
            record_id=request.activity_id,
            kind="activity",
            parent_id=None,
            operation_id=request.operation_id,
            actor=request.actor,
            now=now,
            status=request.state.status,
            state=request.state,
            revision=1,
        )
        return {"record_id": str(request.activity_id), "revision": 1}, [
            {"record_id": str(request.activity_id), "revision": 1}
        ]
    if isinstance(request, ReviseActivityRequest):
        _subject_expect(connection, request.activity_id, "activity", request.expected_revision)
        if request.state.status == "completed":
            active = connection.execute(  # type: ignore[attr-defined]
                "SELECT 1 FROM subject_records WHERE parent_id = ? AND kind = 'work' "
                "AND status NOT IN ('succeeded', 'deleted') LIMIT 1",
                (str(request.activity_id),),
            ).fetchone()
            if active is not None:
                raise FoundationError("dependent_work", "Activity still has open Work")
        revision = request.expected_revision + 1
        _write_subject(
            connection,
            record_id=request.activity_id,
            kind="activity",
            parent_id=None,
            operation_id=request.operation_id,
            actor=request.actor,
            now=now,
            status=request.state.status,
            state=request.state,
            revision=revision,
        )
        return {"record_id": str(request.activity_id), "revision": revision}, [
            {"record_id": str(request.activity_id), "revision": revision}
        ]
    if isinstance(request, DeleteActivityRequest):
        return _subject_delete(
            connection,
            record_id=request.activity_id,
            kind="activity",
            expected_revision=request.expected_revision,
            operation_id=request.operation_id,
            actor=request.actor,
            now=now,
        )
    if isinstance(request, CreateWorkRequest):
        activity_revision, activity_status, _ = _subject_current(
            connection, request.state.activity_id, "activity"
        )
        if activity_status != "ongoing":
            raise FoundationError("activity_not_ongoing", "Work needs an ongoing Activity")
        _subject_state(connection, request.state.activity_id, activity_revision)
        for reference in request.state.inputs:
            _authorize_artifact_ref(
                connection,
                reference,
                actor=request.actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            )
        _write_subject(
            connection,
            record_id=request.work_id,
            kind="work",
            parent_id=request.state.activity_id,
            operation_id=request.operation_id,
            actor=request.actor,
            now=now,
            status="proposed",
            state=request.state,
            revision=1,
        )
        return {"record_id": str(request.work_id), "revision": 1}, [
            {"record_id": str(request.work_id), "revision": 1},
            {"record_id": str(request.state.activity_id), "revision": activity_revision},
        ]
    if isinstance(request, DeleteWorkRequest):
        return _subject_delete(
            connection,
            record_id=request.work_id,
            kind="work",
            expected_revision=request.expected_revision,
            operation_id=request.operation_id,
            actor=request.actor,
            now=now,
        )
    _subject_expect(connection, request.work_id, "work", request.expected_revision)
    state = WorkState.model_validate(
        _subject_state(connection, request.work_id, request.expected_revision)
    )
    if state.status != "proposed":
        raise FoundationError("work_closed", "Accepted Work cannot be changed")
    if isinstance(request, LinkWorkOutputRequest):
        contract = next(
            (item for item in state.expected_outputs if item.slot == request.output.slot), None
        )
        if contract is None:
            raise FoundationError("output_mismatch", "No declared output slot")
        _authorize_artifact_ref(
            connection,
            request.output.artifact,
            actor=request.actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
            media_type=contract.media_type,
        )
        linked = tuple(
            item for item in state.linked_outputs if item.slot != request.output.slot
        ) + (request.output,)
        next_state = state.model_copy(update={"linked_outputs": linked})
    else:
        assert isinstance(request, AcceptWorkRequest)
        declared = {item.slot: item.media_type for item in state.expected_outputs}
        linked_by_slot = {item.slot: item.artifact for item in state.linked_outputs}
        if set(declared) != set(linked_by_slot):
            raise FoundationError("output_incomplete", "Every declared output must be linked")
        for slot, reference in linked_by_slot.items():
            _authorize_artifact_ref(
                connection,
                reference,
                actor=request.actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
                media_type=declared[slot],
            )
        for reference in state.inputs:
            _authorize_artifact_ref(
                connection,
                reference,
                actor=request.actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            )
        next_state = state.model_copy(
            update={
                "status": "succeeded",
                "acceptance": WorkAcceptance(
                    operation_id=request.operation_id,
                    basis=request.basis,
                    authority_source=authority.source_ref,
                    accepted_at=datetime.fromisoformat(now),
                ),
            }
        )
    revision = request.expected_revision + 1
    _write_subject(
        connection,
        record_id=request.work_id,
        kind="work",
        parent_id=state.activity_id,
        operation_id=request.operation_id,
        actor=request.actor,
        now=now,
        status=next_state.status,
        state=next_state,
        revision=revision,
    )
    targets: list[dict[str, object]] = [{"record_id": str(request.work_id), "revision": revision}]
    references = (
        (request.output.artifact,)
        if isinstance(request, LinkWorkOutputRequest)
        else state.inputs + tuple(item.artifact for item in state.linked_outputs)
    )
    targets.extend(
        {"record_id": str(reference.artifact_id), "revision": reference.revision}
        for reference in references
    )
    return (
        {"record_id": str(request.work_id), "revision": revision, "status": next_state.status},
        targets,
    )


def _apply_change(
    connection: object,
    request: DomainRequest,
    *,
    now: str,
    epoch: int,
    authority: LocalAuthority,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if isinstance(request, PublishAttemptOutputRequest):
        from .execution import _check_attempt_basis, _event, _work

        if int(connection.execute("PRAGMA user_version").fetchone()[0]) != 3:  # type: ignore[attr-defined]
            raise FoundationError("unsupported_schema", "Attempt publication requires schema 3")
        _check_attempt_basis(
            connection,
            request.attempt_id,
            request.work_id,
            request.session_id,
            epoch,
            actor=request.actor,
        )
        answered = connection.execute(  # type: ignore[attr-defined]
            "SELECT 1 FROM execution_invocations WHERE attempt_id = ? "
            "AND status = 'answered' LIMIT 1",
            (str(request.attempt_id),),
        ).fetchone()
        if answered is None:
            raise FoundationError("no_answer", "No answered model invocation belongs to Attempt")
        revision, state = _work(connection, request.work_id)
        declared = {item.slot: item.media_type for item in state.expected_outputs}
        if declared.get(request.slot) != request.media_type:
            raise FoundationError("wrong_output", "Slot or media type is not declared by Work")
        if any(item.slot == request.slot for item in state.linked_outputs):
            raise FoundationError("stale_work", "Output slot was linked after Attempt started")
        artifact_id = uuid5(request.attempt_id, f"artifact:{request.slot}")
        artifact_grants, artifact_decisions = _authorize(
            connection,
            actor=request.actor,
            action="artifact.write",
            epoch=epoch,
            resource_type="artifact",
            resource_id=artifact_id,
        )
        grants.extend(artifact_grants)
        decisions.extend(artifact_decisions)
        _expect_absent(connection, artifact_id)
        artifact = CreateArtifactRequest(
            operation_id=request.operation_id,
            space_id=request.space_id,
            actor=request.actor,
            artifact_id=artifact_id,
            media_type=request.media_type,
            content=request.content,
            provenance=(
                ProvenanceRef(
                    relation="produced_by_attempt", external_ref=f"attempt:{request.attempt_id}"
                ),
            ),
        )
        _write_artifact(connection, artifact, now, 1)
        linked = (
            *state.linked_outputs,
            LinkedOutput(
                slot=request.slot, artifact=ArtifactRef(artifact_id=artifact_id, revision=1)
            ),
        )
        _write_subject(
            connection,
            record_id=request.work_id,
            kind="work",
            parent_id=state.activity_id,
            operation_id=request.operation_id,
            actor=request.actor,
            now=now,
            status=state.status,
            state=state.model_copy(update={"linked_outputs": linked}),
            revision=revision + 1,
        )
        _event(connection, request, request.work_id, now, attempt_id=request.attempt_id)
        return {
            "artifact_id": str(artifact_id),
            "work_id": str(request.work_id),
            "revision": revision + 1,
        }, [
            {"record_id": str(artifact_id), "revision": 1},
            {"record_id": str(request.work_id), "revision": revision + 1},
        ]
    if isinstance(
        request,
        (
            CreateResourceRequest,
            ReviseResourceRequest,
            StartAttemptRequest,
            StopAttemptRequest,
            PrepareInvocationRequest,
            AdmitInvocationRequest,
            SendInvocationRequest,
            FinishInvocationRequest,
        ),
    ):
        from .execution import apply_execution_change

        if int(connection.execute("PRAGMA user_version").fetchone()[0]) != 3:  # type: ignore[attr-defined]
            raise FoundationError("unsupported_schema", "Interactive execution requires schema 3")
        return apply_execution_change(connection, request, now=now, epoch=epoch)
    if isinstance(
        request,
        (
            CreateActivityRequest,
            ReviseActivityRequest,
            DeleteActivityRequest,
            CreateWorkRequest,
            LinkWorkOutputRequest,
            AcceptWorkRequest,
            DeleteWorkRequest,
        ),
    ):
        if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 2:  # type: ignore[attr-defined]
            raise FoundationError("unsupported_schema", "Activity/Work requires schema 2")
        return _apply_subject_change(
            connection,
            request,
            now=now,
            epoch=epoch,
            authority=authority,
            grants=grants,
            decisions=decisions,
        )
    if isinstance(request, CreateArtifactRequest):
        _expect_absent(connection, request.artifact_id)
        _write_artifact(connection, request, now, 1)
        return {"record_id": str(request.artifact_id), "revision": 1}, [
            {"record_id": str(request.artifact_id), "revision": 1}
        ]
    if isinstance(request, ReviseArtifactRequest):
        _expect_revision(
            connection,
            request.artifact_id,
            "artifact",
            request.expected_revision,
            required_status="active",
        )
        revision = request.expected_revision + 1
        _write_artifact(connection, request, now, revision)
        return {"record_id": str(request.artifact_id), "revision": revision}, [
            {"record_id": str(request.artifact_id), "revision": revision}
        ]
    if isinstance(request, DeleteArtifactRequest):
        _expect_revision(
            connection,
            request.artifact_id,
            "artifact",
            request.expected_revision,
            required_status="active",
        )
        prior_operations = [
            row[0]
            for row in connection.execute(  # type: ignore[attr-defined]
                "SELECT operation_id FROM record_revisions WHERE record_id = ?",
                (str(request.artifact_id),),
            ).fetchall()
        ]
        connection.executemany(  # type: ignore[attr-defined]
            "DELETE FROM receipts WHERE operation_id = ?",
            ((operation_id,) for operation_id in prior_operations),
        )
        connection.executemany(  # type: ignore[attr-defined]
            "UPDATE operations SET fingerprint = 'DELETED' WHERE operation_id = ?",
            ((operation_id,) for operation_id in prior_operations),
        )
        revision = request.expected_revision + 1
        _insert_record(
            connection,
            record_id=request.artifact_id,
            kind="artifact",
            operation_id=request.operation_id,
            actor=request.actor,
            now=now,
            status="deleted",
            body={"status": "deleted"},
            revision=revision,
        )
        connection.execute(  # type: ignore[attr-defined]
            "DELETE FROM revision_provenance WHERE record_id = ?", (str(request.artifact_id),)
        )
        connection.execute(  # type: ignore[attr-defined]
            "DELETE FROM managed_content WHERE record_id = ?", (str(request.artifact_id),)
        )
        if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 3:  # type: ignore[attr-defined]
            affected = connection.execute(  # type: ignore[attr-defined]
                "SELECT e.operation_id FROM execution_events e "
                "JOIN execution_invocations i ON i.invocation_id = e.invocation_id "
                "JOIN execution_attempts a ON a.attempt_id = i.attempt_id "
                "JOIN json_each(a.input_refs_json) j "
                "WHERE e.kind = 'prepare_invocation' "
                "AND json_extract(j.value, '$.artifact_id') = ?",
                (str(request.artifact_id),),
            ).fetchall()
            connection.executemany(  # type: ignore[attr-defined]
                "DELETE FROM receipts WHERE operation_id = ?", affected
            )
            connection.executemany(  # type: ignore[attr-defined]
                "UPDATE operations SET fingerprint = 'DELETED' WHERE operation_id = ?",
                affected,
            )
            connection.execute(  # type: ignore[attr-defined]
                "UPDATE execution_invocations SET request_sha256 = NULL "
                "WHERE attempt_id IN (SELECT a.attempt_id FROM execution_attempts a "
                "JOIN json_each(a.input_refs_json) j "
                "WHERE json_extract(j.value, '$.artifact_id') = ?)",
                (str(request.artifact_id),),
            )
        connection.execute(  # type: ignore[attr-defined]
            "INSERT INTO deletion_jobs(operation_id, record_id, status, created_at) "
            "VALUES (?, ?, 'pending', ?)",
            (str(request.operation_id), str(request.artifact_id), now),
        )
        connection.execute(  # type: ignore[attr-defined]
            "UPDATE backup_inventory SET status = 'contaminated' "
            "WHERE status IN ('planned', 'failed') OR (status = 'complete' AND backup_id IN "
            "(SELECT backup_id FROM backup_records WHERE record_id = ?))",
            (str(request.artifact_id),),
        )
        return {
            "record_id": str(request.artifact_id),
            "revision": revision,
            "content": "unavailable",
            "deletion": "pending",
        }, [{"record_id": str(request.artifact_id), "revision": revision}]
    if isinstance(request, CreateDecisionRequest):
        _expect_absent(connection, request.decision_id)
        _insert_record(
            connection,
            record_id=request.decision_id,
            kind="decision",
            operation_id=request.operation_id,
            actor=request.actor,
            now=now,
            status=request.state.status,
            body=cast(dict[str, object], request.state.model_dump(mode="json")),
        )
        return {"record_id": str(request.decision_id), "revision": 1}, [
            {"record_id": str(request.decision_id), "revision": 1}
        ]
    if isinstance(request, ReviseDecisionRequest):
        _expect_revision(connection, request.decision_id, "decision", request.expected_revision)
        revision = request.expected_revision + 1
        _insert_record(
            connection,
            record_id=request.decision_id,
            kind="decision",
            operation_id=request.operation_id,
            actor=request.actor,
            now=now,
            status=request.state.status,
            body=cast(dict[str, object], request.state.model_dump(mode="json")),
            revision=revision,
        )
        return {"record_id": str(request.decision_id), "revision": revision}, [
            {"record_id": str(request.decision_id), "revision": revision}
        ]
    if isinstance(request, CreateGrantRequest):
        _expect_absent(connection, request.grant_id)
        _insert_record(
            connection,
            record_id=request.grant_id,
            kind="grant",
            operation_id=request.operation_id,
            actor=request.actor,
            now=now,
            status=request.state.status,
            body={"epoch": epoch, "state": request.state.model_dump(mode="json")},
        )
        return {"record_id": str(request.grant_id), "revision": 1}, [
            {"record_id": str(request.grant_id), "revision": 1}
        ]
    if isinstance(request, RevokeGrantRequest):
        _expect_revision(connection, request.grant_id, "grant", request.expected_revision)
        row = connection.execute(  # type: ignore[attr-defined]
            "SELECT body_json FROM record_revisions WHERE record_id = ? AND revision = ?",
            (str(request.grant_id), request.expected_revision),
        ).fetchone()
        if row is None:
            raise FoundationError("corrupt_space", "Current Grant revision is missing")
        previous = json.loads(row[0])
        previous_state = GrantState.model_validate(previous["state"])
        revoked = previous_state.model_copy(update={"status": "revoked"})
        revision = request.expected_revision + 1
        _insert_record(
            connection,
            record_id=request.grant_id,
            kind="grant",
            operation_id=request.operation_id,
            actor=request.actor,
            now=now,
            status="revoked",
            body={"epoch": int(previous["epoch"]), "state": revoked.model_dump(mode="json")},
            revision=revision,
        )
        return {"record_id": str(request.grant_id), "revision": revision}, [
            {"record_id": str(request.grant_id), "revision": revision}
        ]
    raise FoundationError("invalid_request", f"Unsupported operation: {request.kind}")


def _write_receipt(connection: object, receipt: OperationReceipt) -> None:
    """Single fault-injection seam used to verify transaction rollback."""

    connection.execute(  # type: ignore[attr-defined]
        "INSERT INTO receipts(operation_id, fingerprint, receipt_json) VALUES (?, ?, ?)",
        (str(receipt.operation_id), receipt.fingerprint, receipt.model_dump_json()),
    )


def apply_operation(path: Path, request: DomainRequest, authority: Authority) -> OperationReceipt:
    """Apply one exact domain operation with audit and receipt in the same commit."""

    request = _validated_request(request)
    _authority_actor(request, authority)
    request_fingerprint = fingerprint(request)
    with space_connection(path, writable=True) as (connection, info):
        if request.space_id != info.space_id:
            raise FoundationError("wrong_space", "Operation names another space")
        if type(authority) is LocalAuthority:
            _local_space(authority, info)

        saved = _saved_receipt(connection, request.operation_id)
        if saved is not None:
            _authorize(
                connection,
                actor=request.actor,
                action="receipt.read",
                epoch=info.execution_epoch,
            )
            saved_fingerprint, raw = saved
            if saved_fingerprint != request_fingerprint:
                raise FoundationError(
                    "operation_conflict", "Operation id already has a different exact intent"
                )
            return _receipt_from_row(raw)
        prior_operation = connection.execute(
            "SELECT fingerprint FROM operations WHERE operation_id = ?",
            (str(request.operation_id),),
        ).fetchone()
        if prior_operation is not None:
            _authorize(
                connection,
                actor=request.actor,
                action="receipt.read",
                epoch=info.execution_epoch,
            )
            raise FoundationError(
                "history_unavailable",
                "Operation history was retained without the deleted intent/receipt",
            )

        now = utc_now()
        now_text = now.isoformat()
        grants: list[dict[str, object]] = []
        decisions: list[dict[str, object]] = []

        if isinstance(request, BootstrapRequest):
            if type(authority) is not LocalAuthority:
                raise FoundationError(
                    "permission_denied", "Bootstrap needs trusted local authority"
                )
            count = int(connection.execute("SELECT count(*) FROM records").fetchone()[0])
            if info.recovery_state != "active" or info.state_revision != 0 or count != 0:
                raise FoundationError("bootstrap_closed", "Bootstrap is only for a new empty space")
        elif isinstance(request, RecoverRequest):
            if type(authority) is not RecoveryAuthority or info.recovery_state != "quarantined":
                raise FoundationError(
                    "permission_denied", "Recovery needs fresh authority in quarantine"
                )
        else:
            if type(authority) is not LocalAuthority or info.recovery_state != "active":
                raise FoundationError(
                    "permission_denied", "Ordinary operations require active space"
                )
            action, resource_type, resource_id = _operation_action(request)
            grants, decisions = _authorize(
                connection,
                actor=request.actor,
                action=action,
                epoch=info.execution_epoch,
                resource_type=resource_type,
                resource_id=resource_id,
            )

        state_revision = info.state_revision + 1
        updated = connection.execute(
            "UPDATE spaces SET state_revision = ?, recovery_state = ? "
            "WHERE singleton = 1 AND state_revision = ?",
            (
                state_revision,
                "active" if isinstance(request, RecoverRequest) else info.recovery_state,
                info.state_revision,
            ),
        )
        if updated.rowcount != 1:
            raise FoundationError("stale_space", "Space revision changed during operation")
        connection.execute(
            "INSERT INTO operations(operation_id, fingerprint, kind, actor, committed_at, "
            "state_revision) VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(request.operation_id),
                request_fingerprint,
                request.kind,
                request.actor,
                now_text,
                state_revision,
            ),
        )

        if isinstance(request, (BootstrapRequest, RecoverRequest)):
            targets = _write_root(connection, request, now_text, info.execution_epoch)
            result: dict[str, object] = {
                "decision_id": str(request.decision_id),
                "grant_id": str(request.grant_id),
                "execution_epoch": info.execution_epoch,
            }
        else:
            result, targets = _apply_change(
                connection,
                request,
                now=now_text,
                epoch=info.execution_epoch,
                authority=cast(LocalAuthority, authority),
                grants=grants,
                decisions=decisions,
            )

        connection.execute(
            "INSERT INTO operation_audit(operation_id, authority_source, target_refs_json, "
            "grant_refs_json, decision_refs_json) VALUES (?, ?, ?, ?, ?)",
            (
                str(request.operation_id),
                authority.source_ref,
                canonical_json(targets),
                canonical_json(grants),
                canonical_json(decisions),
            ),
        )
        receipt = OperationReceipt(
            operation_id=request.operation_id,
            fingerprint=request_fingerprint,
            kind=request.kind,
            state_revision=state_revision,
            committed_at=now,
            result=cast(dict[str, JsonValue], result),
        )
        _write_receipt(connection, receipt)
        return receipt


def read_receipt(path: Path, operation_id: UUID, authority: LocalAuthority) -> OperationReceipt:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active":
            raise FoundationError("permission_denied", "Quarantined spaces disclose no receipts")
        _authorize(
            connection,
            actor=authority.actor,
            action="receipt.read",
            epoch=info.execution_epoch,
        )
        saved = _saved_receipt(connection, operation_id)
        if saved is None:
            raise FoundationError("not_found", f"No receipt for operation {operation_id}")
        return _receipt_from_row(saved[1])


def read_operation_audit(
    path: Path, operation_id: UUID, authority: LocalAuthority
) -> OperationAuditEntry:
    """Read the exact content-free authorization and target references."""

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active":
            raise FoundationError("permission_denied", "Quarantined spaces disclose no audit")
        _authorize(
            connection,
            actor=authority.actor,
            action="receipt.read",
            epoch=info.execution_epoch,
        )
        row = connection.execute(
            "SELECT authority_source, target_refs_json, grant_refs_json, "
            "decision_refs_json FROM operation_audit WHERE operation_id = ?",
            (str(operation_id),),
        ).fetchone()
        if row is None:
            raise FoundationError("not_found", f"No audit for operation {operation_id}")
        return OperationAuditEntry(
            operation_id=operation_id,
            authority_source=row[0],
            target_refs=json.loads(row[1]),
            grant_refs=json.loads(row[2]),
            decision_refs=json.loads(row[3]),
        )


def _provenance(connection: object, record_id: UUID, revision: int) -> tuple[ProvenanceRef, ...]:
    rows = connection.execute(  # type: ignore[attr-defined]
        "SELECT relation, source_record_id, source_revision, external_ref "
        "FROM revision_provenance WHERE record_id = ? AND revision = ? ORDER BY ordinal",
        (str(record_id), revision),
    ).fetchall()
    return tuple(
        ProvenanceRef(
            relation=row[0],
            record_id=UUID(row[1]) if row[1] else None,
            revision=row[2],
            external_ref=row[3],
        )
        for row in rows
    )


def read_artifact(
    path: Path,
    artifact_id: UUID,
    authority: LocalAuthority,
    *,
    revision: int | None = None,
) -> ArtifactRevision:
    """Read current or exact historical bytes; unavailable content never falls forward."""

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active":
            raise FoundationError("permission_denied", "Quarantined spaces disclose no content")
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="artifact",
            resource_id=artifact_id,
        )
        if revision is None:
            current, _, _ = _current_revision(connection, artifact_id, "artifact")
            selected = current
        else:
            selected = revision
        row = connection.execute(
            "SELECT v.operation_id, v.created_at, v.actor, v.status, c.media_type, c.payload, "
            "c.sha256 FROM record_revisions v LEFT JOIN managed_content c "
            "ON c.record_id = v.record_id AND c.revision = v.revision "
            "WHERE v.record_id = ? AND v.revision = ?",
            (str(artifact_id), selected),
        ).fetchone()
        if row is None:
            raise FoundationError("not_found", f"No exact revision {artifact_id}@{selected}")
        if row[5] is None:
            raise FoundationError(
                "content_unavailable",
                f"Managed content is unavailable for {artifact_id}@{selected}",
            )
        return ArtifactRevision(
            artifact_id=artifact_id,
            revision=selected,
            operation_id=UUID(row[0]),
            created_at=datetime.fromisoformat(row[1]),
            actor=row[2],
            media_type=row[4],
            content=bytes(row[5]),
            content_sha256=row[6],
            status=row[3],
            provenance=_provenance(connection, artifact_id, selected),
        )


def upgrade_space(path: Path, authority: LocalAuthority) -> SpaceInfo:
    """Explicit additive schema upgrade; an old space remains usable before it."""

    with space_connection(path, writable=True) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active":
            raise FoundationError("permission_denied", "Quarantined spaces cannot upgrade")
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.backup",
            epoch=info.execution_epoch,
        )
        if info.schema_version == 1:
            for statement in SUBJECT_SCHEMA_STATEMENTS:
                connection.execute(statement)
            now = utc_now().isoformat()
            connection.execute(
                "INSERT INTO schema_migrations(version, name, sha256, applied_at) "
                "VALUES (2, ?, ?, ?)",
                (SUBJECT_SCHEMA_NAME, SUBJECT_SCHEMA_SHA256, now),
            )
            connection.execute("PRAGMA user_version = 2")
            connection.execute(
                "UPDATE spaces SET state_revision = state_revision + 1 WHERE singleton = 1"
            )
            connection.execute(
                "INSERT INTO maintenance_events(event_id, kind, occurred_at, detail_json) "
                "VALUES (?, 'schema_upgrade', ?, ?)",
                (str(uuid4()), now, canonical_json({"from": 1, "to": 2})),
            )
    return read_space(path)


def _read_subject(
    path: Path,
    record_id: UUID,
    kind: str,
    authority: LocalAuthority,
    revision: int | None,
) -> tuple[int, UUID, datetime, str, dict[str, object], tuple[ArtifactRef, ...]]:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active" or info.schema_version < 2:
            raise FoundationError(
                "permission_denied", "Subject records require an active schema 2 space"
            )
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type=kind,
            resource_id=record_id,
        )
        current, status, _ = _subject_current(connection, record_id, kind)
        if status == "deleted":
            raise FoundationError("content_unavailable", f"{kind.title()} {record_id} was deleted")
        selected = current if revision is None else revision
        row = connection.execute(
            "SELECT operation_id, created_at, actor FROM subject_revisions "
            "WHERE record_id = ? AND revision = ?",
            (str(record_id), selected),
        ).fetchone()
        if row is None:
            raise FoundationError("not_found", f"No exact subject revision {record_id}@{selected}")
        body = _subject_state(connection, record_id, selected)
        unavailable: list[ArtifactRef] = []
        if kind == "work":
            state = WorkState.model_validate(body)
            references = list(state.inputs) + [output.artifact for output in state.linked_outputs]
            for reference in references:
                try:
                    _artifact_reference(connection, reference)
                except FoundationError as error:
                    if error.code != "content_unavailable":
                        raise
                    unavailable.append(reference)
        return (
            selected,
            UUID(row[0]),
            datetime.fromisoformat(row[1]),
            str(row[2]),
            body,
            tuple(unavailable),
        )


def read_activity(
    path: Path,
    activity_id: UUID,
    authority: LocalAuthority,
    *,
    revision: int | None = None,
) -> ActivityRevision:
    selected, operation_id, created_at, actor, body, _ = _read_subject(
        path, activity_id, "activity", authority, revision
    )
    return ActivityRevision(
        activity_id=activity_id,
        revision=selected,
        operation_id=operation_id,
        created_at=created_at,
        actor=actor,
        state=ActivityState.model_validate(body),
    )


def read_work(
    path: Path,
    work_id: UUID,
    authority: LocalAuthority,
    *,
    revision: int | None = None,
) -> WorkRevision:
    selected, operation_id, created_at, actor, body, unavailable = _read_subject(
        path, work_id, "work", authority, revision
    )
    return WorkRevision(
        work_id=work_id,
        revision=selected,
        operation_id=operation_id,
        created_at=created_at,
        actor=actor,
        state=WorkState.model_validate(body),
        unavailable_refs=unavailable,
    )


def inspect_space(path: Path, authority: LocalAuthority) -> SpaceInspection:
    """Return bounded metadata only; this does not disclose managed payload."""

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active":
            raise FoundationError("permission_denied", "Use recovery inspection for quarantine")
        _authorize(
            connection,
            actor=authority.actor,
            action="space.inspect",
            epoch=info.execution_epoch,
        )
        rows = connection.execute(
            "SELECT record_id, kind, current_revision, status, created_at, updated_at "
            "FROM records ORDER BY kind, record_id"
        ).fetchall()
        records = tuple(
            RecordSummary(
                record_id=UUID(row[0]),
                kind=row[1],
                current_revision=row[2],
                status=row[3],
                created_at=datetime.fromisoformat(row[4]),
                updated_at=datetime.fromisoformat(row[5]),
            )
            for row in rows
        )
        if info.schema_version >= 2:
            subject_rows = connection.execute(
                "SELECT record_id, kind, current_revision, status, created_at, updated_at "
                "FROM subject_records ORDER BY kind, record_id"
            ).fetchall()
            records += tuple(
                RecordSummary(
                    record_id=UUID(row[0]),
                    kind=row[1],
                    current_revision=row[2],
                    status=row[3],
                    created_at=datetime.fromisoformat(row[4]),
                    updated_at=datetime.fromisoformat(row[5]),
                )
                for row in subject_rows
            )
        operation_count = int(connection.execute("SELECT count(*) FROM operations").fetchone()[0])
        audit_count = int(connection.execute("SELECT count(*) FROM operation_audit").fetchone()[0])
        receipt_count = int(connection.execute("SELECT count(*) FROM receipts").fetchone()[0])
        pending = int(
            connection.execute(
                "SELECT count(*) FROM deletion_jobs WHERE status = 'pending'"
            ).fetchone()[0]
        )
        if info.schema_version >= 2:
            pending += int(
                connection.execute(
                    "SELECT count(*) FROM subject_deletion_jobs WHERE status = 'pending'"
                ).fetchone()[0]
            )
        complete_backups = int(
            connection.execute(
                "SELECT count(*) FROM backup_inventory WHERE status = 'complete'"
            ).fetchone()[0]
        )
        contaminated = int(
            connection.execute(
                "SELECT count(*) FROM backup_inventory WHERE status = 'contaminated'"
            ).fetchone()[0]
        )
        return SpaceInspection(
            space=info,
            records=records,
            operation_count=operation_count,
            audit_count=audit_count,
            receipt_count=receipt_count,
            pending_deletions=pending,
            completed_backups=complete_backups,
            contaminated_backups=contaminated,
        )


def inspect_recovery(path: Path, authority: RecoveryAuthority) -> dict[str, object]:
    """Inspect only recovery metadata; no record or receipt content is returned."""

    info = read_space(path)
    if info.recovery_state != "quarantined" or not authority.source_ref:
        raise FoundationError("permission_denied", "Space is not in trusted recovery quarantine")
    return {
        "space_id": str(info.space_id),
        "schema_version": info.schema_version,
        "state_revision": info.state_revision,
        "execution_epoch": info.execution_epoch,
        "recovery_state": info.recovery_state,
    }


def create_backup(path: Path, backup_id: UUID, authority: LocalAuthority) -> BackupInfo:
    created_at = utc_now()
    prepared: BackupInfo | None = None
    final_package: Path | None = None
    try:
        with space_connection(path, writable=True) as (connection, info):
            _local_space(authority, info)
            if info.recovery_state != "active":
                raise FoundationError("permission_denied", "Quarantined spaces cannot back up")
            _authorize(
                connection,
                actor=authority.actor,
                action="maintenance.backup",
                epoch=info.execution_epoch,
            )
            connection.execute(
                "INSERT INTO backup_inventory(backup_id, package_name, created_at, "
                "state_revision, status) VALUES (?, ?, ?, ?, 'planned')",
                (str(backup_id), str(backup_id), created_at.isoformat(), info.state_revision),
            )
        prepared = backup_database(path, backup_id, created_at)
        final_package = prepared.package.parent / str(backup_id)
        snapshot_database = prepared.package / DATABASE_NAME
        import sqlite3

        with closing(sqlite3.connect(snapshot_database)) as snapshot:
            record_ids = [
                row[0]
                for row in snapshot.execute(
                    "SELECT DISTINCT record_id FROM managed_content ORDER BY record_id"
                ).fetchall()
            ]
            subject_ids = (
                [
                    row[0]
                    for row in snapshot.execute(
                        "SELECT DISTINCT record_id FROM subject_content ORDER BY record_id"
                    ).fetchall()
                ]
                if prepared.manifest.schema_version >= 2
                else []
            )
        with space_connection(path, writable=True) as (connection, info):
            _local_space(authority, info)
            _authorize(
                connection,
                actor=authority.actor,
                action="maintenance.backup",
                epoch=info.execution_epoch,
            )
            row = connection.execute(
                "SELECT status FROM backup_inventory WHERE backup_id = ?",
                (str(backup_id),),
            ).fetchone()
            if row != ("planned",) or info.state_revision != prepared.manifest.state_revision:
                raise FoundationError(
                    "backup_invalidated", "Space changed while the backup was being prepared"
                )
            connection.executemany(
                "INSERT INTO backup_records(backup_id, record_id) VALUES (?, ?)",
                ((str(backup_id), record_id) for record_id in record_ids),
            )
            if info.schema_version >= 2:
                connection.executemany(
                    "INSERT INTO backup_subjects(backup_id, record_id) VALUES (?, ?)",
                    ((str(backup_id), record_id) for record_id in subject_ids),
                )
            prepared.package.rename(final_package)
            updated = connection.execute(
                "UPDATE backup_inventory SET state_revision = ?, database_sha256 = ?, "
                "status = 'complete' WHERE backup_id = ? AND status = 'planned'",
                (
                    prepared.manifest.state_revision,
                    prepared.manifest.database_sha256,
                    str(backup_id),
                ),
            )
            if updated.rowcount != 1:
                raise FoundationError("backup_invalidated", "Backup inventory changed")
        return load_backup(final_package)
    except BaseException as error:
        for package in (
            prepared.package if prepared is not None else None,
            final_package,
        ):
            if package is not None and package.exists():
                shutil.rmtree(package)
        try:
            with space_connection(path, writable=True) as (connection, _):
                connection.execute(
                    "UPDATE backup_inventory SET status = 'failed' "
                    "WHERE backup_id = ? AND status IN ('planned', 'complete')",
                    (str(backup_id),),
                )
        except BaseException:
            pass
        if isinstance(error, FoundationError):
            raise
        raise FoundationError("backup_failed", str(error)) from error


def restore_backup(package: Path, destination: Path, authority: RecoveryAuthority) -> SpaceInfo:
    if not authority.actor.strip() or not authority.source_ref.strip():
        raise FoundationError("permission_denied", "Restore needs fresh trusted authority")
    load_backup(package)
    return restore_database(package, destination)


def _subject_deletion_count(connection: object, schema_version: int, status: str) -> int:
    if schema_version < 2:
        return 0
    return int(
        connection.execute(  # type: ignore[attr-defined]
            "SELECT count(*) FROM subject_deletion_jobs WHERE status = ?", (status,)
        ).fetchone()[0]
    )


def complete_deletions(path: Path, authority: LocalAuthority) -> DeletionStatus:
    """Purge affected managed backups, then close/checkpoint/VACUUM the live store."""

    from .history import managed_pi_lock

    with managed_pi_lock(path):
        return _complete_deletions_locked(path, authority)


def _complete_deletions_locked(path: Path, authority: LocalAuthority) -> DeletionStatus:
    from .history import purge_managed_pi_sessions

    root, _, backups = layout(path)
    with space_connection(root, writable=True) as (connection, info):
        _local_space(authority, info)
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.delete",
            epoch=info.execution_epoch,
        )
        pending_jobs = [
            str(row[0])
            for row in connection.execute(
                "SELECT operation_id FROM deletion_jobs WHERE status = 'pending' "
                "ORDER BY operation_id"
            ).fetchall()
        ]
        subject_jobs = (
            [
                str(row[0])
                for row in connection.execute(
                    "SELECT operation_id FROM subject_deletion_jobs WHERE status = 'pending' "
                    "ORDER BY operation_id"
                ).fetchall()
            ]
            if info.schema_version >= 2
            else []
        )
        contaminated = [
            UUID(row[0])
            for row in connection.execute(
                "SELECT backup_id FROM backup_inventory WHERE status = 'contaminated' "
                "ORDER BY backup_id"
            ).fetchall()
        ]
    if not pending_jobs and not subject_jobs and not contaminated:
        sanitize_database(root)
        with space_connection(root) as (connection, current):
            pending = int(
                connection.execute(
                    "SELECT count(*) FROM deletion_jobs WHERE status = 'pending'"
                ).fetchone()[0]
            )
            pending += _subject_deletion_count(connection, current.schema_version, "pending")
            complete = int(
                connection.execute(
                    "SELECT count(*) FROM deletion_jobs WHERE status = 'complete'"
                ).fetchone()[0]
            )
            complete += _subject_deletion_count(connection, current.schema_version, "complete")
            remaining_backups = int(
                connection.execute(
                    "SELECT count(*) FROM backup_inventory WHERE status = 'contaminated'"
                ).fetchone()[0]
            )
        finished = pending == 0 and remaining_backups == 0
        return DeletionStatus(
            pending_jobs=pending,
            completed_jobs=complete,
            purged_backups=0,
            live_store_sanitized=finished,
            completed_at=utc_now() if finished else None,
        )

    if pending_jobs or subject_jobs:
        purge_managed_pi_sessions(root, authority.space_id)

    for backup_id in contaminated:
        packages = (
            (backups / f".{backup_id}.partial").resolve(),
            (backups / str(backup_id)).resolve(),
        )
        for package in packages:
            if package.parent != backups.resolve():
                raise FoundationError("layout", "Backup inventory escaped managed directory")
            if package.exists():
                shutil.rmtree(package)

    sanitize_database(root)
    completed_at = utc_now()
    purged = 0
    with space_connection(root, writable=True) as (connection, info):
        _local_space(authority, info)
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.delete",
            epoch=info.execution_epoch,
        )
        for backup_id in contaminated:
            updated = connection.execute(
                "UPDATE backup_inventory SET status = 'purged', database_sha256 = NULL "
                "WHERE backup_id = ? AND status = 'contaminated'",
                (str(backup_id),),
            )
            purged += updated.rowcount
        for operation_id in pending_jobs:
            connection.execute(
                "UPDATE deletion_jobs SET status = 'complete', completed_at = ? "
                "WHERE operation_id = ? AND status = 'pending'",
                (completed_at.isoformat(), operation_id),
            )
        if info.schema_version >= 2:
            for operation_id in subject_jobs:
                connection.execute(
                    "UPDATE subject_deletion_jobs SET status = 'complete', completed_at = ? "
                    "WHERE operation_id = ? AND status = 'pending'",
                    (completed_at.isoformat(), operation_id),
                )
    sanitize_database(root)
    with space_connection(root) as (connection, current):
        pending = int(
            connection.execute(
                "SELECT count(*) FROM deletion_jobs WHERE status = 'pending'"
            ).fetchone()[0]
        )
        pending += _subject_deletion_count(connection, current.schema_version, "pending")
        completed = int(
            connection.execute(
                "SELECT count(*) FROM deletion_jobs WHERE status = 'complete'"
            ).fetchone()[0]
        )
        completed += _subject_deletion_count(connection, current.schema_version, "complete")
        remaining_backups = int(
            connection.execute(
                "SELECT count(*) FROM backup_inventory WHERE status = 'contaminated'"
            ).fetchone()[0]
        )
    finished = pending == 0 and remaining_backups == 0
    return DeletionStatus(
        pending_jobs=pending,
        completed_jobs=completed,
        purged_backups=purged,
        live_store_sanitized=finished,
        completed_at=completed_at if finished else None,
    )


__all__ = [
    "FoundationError",
    "LocalAuthority",
    "RecoveryAuthority",
    "apply_operation",
    "authorize_local",
    "authorize_recovery",
    "complete_deletions",
    "create_backup",
    "fingerprint",
    "initialize_space",
    "inspect_recovery",
    "inspect_space",
    "read_artifact",
    "read_activity",
    "read_operation_audit",
    "read_work",
    "read_receipt",
    "read_space",
    "restore_backup",
    "upgrade_space",
]
