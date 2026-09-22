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
from uuid import UUID

from pydantic import JsonValue, TypeAdapter, ValidationError

from .models import (
    ALL_ACTIONS,
    Action,
    ArtifactRevision,
    BackupInfo,
    BootstrapRequest,
    CreateArtifactRequest,
    CreateDecisionRequest,
    CreateGrantRequest,
    DecisionState,
    DeleteArtifactRequest,
    DeletionStatus,
    DomainRequest,
    GrantState,
    OperationReceipt,
    ProvenanceRef,
    RecordSummary,
    RecoverRequest,
    ReviseArtifactRequest,
    ReviseDecisionRequest,
    RevokeGrantRequest,
    SpaceInfo,
    SpaceInspection,
)
from .storage import (
    DATABASE_NAME,
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
        scoped = grant_state.resource_type == "space" or grant_state.resource_id == resource_id
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


def _expect_revision(connection: object, record_id: UUID, kind: str, expected: int) -> None:
    current, _, _ = _current_revision(connection, record_id, kind)
    if current != expected:
        raise FoundationError(
            "stale_revision", f"Expected {record_id}@{expected}; current revision is {current}"
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
    return [
        {"record_id": str(request.decision_id), "revision": 1},
        {"record_id": str(request.grant_id), "revision": 1},
    ]


def _operation_action(request: DomainRequest) -> tuple[Action, UUID | None]:
    if isinstance(request, (CreateArtifactRequest, ReviseArtifactRequest, DeleteArtifactRequest)):
        return "artifact.write", request.artifact_id
    if isinstance(request, (CreateDecisionRequest, ReviseDecisionRequest)):
        return "decision.write", None
    if isinstance(request, (CreateGrantRequest, RevokeGrantRequest)):
        return "grant.write", None
    raise FoundationError("invalid_request", f"No ordinary action for {request.kind}")


def _apply_change(
    connection: object,
    request: DomainRequest,
    *,
    now: str,
    epoch: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if isinstance(request, CreateArtifactRequest):
        _expect_absent(connection, request.artifact_id)
        _write_artifact(connection, request, now, 1)
        return {"record_id": str(request.artifact_id), "revision": 1}, [
            {"record_id": str(request.artifact_id), "revision": 1}
        ]
    if isinstance(request, ReviseArtifactRequest):
        _expect_revision(connection, request.artifact_id, "artifact", request.expected_revision)
        revision = request.expected_revision + 1
        _write_artifact(connection, request, now, revision)
        return {"record_id": str(request.artifact_id), "revision": revision}, [
            {"record_id": str(request.artifact_id), "revision": revision}
        ]
    if isinstance(request, DeleteArtifactRequest):
        _expect_revision(connection, request.artifact_id, "artifact", request.expected_revision)
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
        connection.execute(  # type: ignore[attr-defined]
            "INSERT INTO deletion_jobs(operation_id, record_id, status, created_at) "
            "VALUES (?, ?, 'pending', ?)",
            (str(request.operation_id), str(request.artifact_id), now),
        )
        connection.execute(  # type: ignore[attr-defined]
            "UPDATE backup_inventory SET status = 'contaminated' "
            "WHERE backup_id IN (SELECT backup_id FROM backup_records WHERE record_id = ?) "
            "AND status = 'complete'",
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
            action, resource_id = _operation_action(request)
            grants, decisions = _authorize(
                connection,
                actor=request.actor,
                action=action,
                epoch=info.execution_epoch,
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
                connection, request, now=now_text, epoch=info.execution_epoch
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
        operation_count = int(connection.execute("SELECT count(*) FROM operations").fetchone()[0])
        audit_count = int(connection.execute("SELECT count(*) FROM operation_audit").fetchone()[0])
        receipt_count = int(connection.execute("SELECT count(*) FROM receipts").fetchone()[0])
        pending = int(
            connection.execute(
                "SELECT count(*) FROM deletion_jobs WHERE status = 'pending'"
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
        backup = backup_database(path, backup_id, created_at)
        snapshot_database = backup.package / DATABASE_NAME
        import sqlite3

        with closing(sqlite3.connect(snapshot_database)) as snapshot:
            record_ids = [
                row[0]
                for row in snapshot.execute(
                    "SELECT DISTINCT record_id FROM managed_content ORDER BY record_id"
                ).fetchall()
            ]
        with space_connection(path, writable=True) as (connection, info):
            _local_space(authority, info)
            _authorize(
                connection,
                actor=authority.actor,
                action="maintenance.backup",
                epoch=info.execution_epoch,
            )
            connection.execute(
                "UPDATE backup_inventory SET state_revision = ?, database_sha256 = ?, "
                "status = 'complete' WHERE backup_id = ? AND status = 'planned'",
                (
                    backup.manifest.state_revision,
                    backup.manifest.database_sha256,
                    str(backup_id),
                ),
            )
            connection.executemany(
                "INSERT INTO backup_records(backup_id, record_id) VALUES (?, ?)",
                ((str(backup_id), record_id) for record_id in record_ids),
            )
        return backup
    except BaseException:
        try:
            with space_connection(path, writable=True) as (connection, _):
                connection.execute(
                    "UPDATE backup_inventory SET status = 'failed' "
                    "WHERE backup_id = ? AND status = 'planned'",
                    (str(backup_id),),
                )
        except BaseException:
            pass
        raise


def restore_backup(package: Path, destination: Path, authority: RecoveryAuthority) -> SpaceInfo:
    if not authority.actor.strip() or not authority.source_ref.strip():
        raise FoundationError("permission_denied", "Restore needs fresh trusted authority")
    load_backup(package)
    return restore_database(package, destination)


def complete_deletions(path: Path, authority: LocalAuthority) -> DeletionStatus:
    """Purge affected managed backups, then close/checkpoint/VACUUM the live store."""

    root, _, backups = layout(path)
    with space_connection(root, writable=True) as (connection, info):
        _local_space(authority, info)
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.delete",
            epoch=info.execution_epoch,
        )
        pending = int(
            connection.execute(
                "SELECT count(*) FROM deletion_jobs WHERE status = 'pending'"
            ).fetchone()[0]
        )
        contaminated = [
            UUID(row[0])
            for row in connection.execute(
                "SELECT backup_id FROM backup_inventory WHERE status = 'contaminated'"
            ).fetchall()
        ]
    if pending == 0:
        complete = 0
        with space_connection(root) as (connection, _):
            complete = int(
                connection.execute(
                    "SELECT count(*) FROM deletion_jobs WHERE status = 'complete'"
                ).fetchone()[0]
            )
        return DeletionStatus(
            pending_jobs=0,
            completed_jobs=complete,
            purged_backups=0,
            live_store_sanitized=True,
            completed_at=utc_now(),
        )

    purged = 0
    for backup_id in contaminated:
        package = (backups / str(backup_id)).resolve()
        if package.parent != backups.resolve():
            raise FoundationError("layout", "Backup inventory escaped managed directory")
        if package.exists():
            shutil.rmtree(package)
        purged += 1

    sanitize_database(root)
    completed_at = utc_now()
    with space_connection(root, writable=True) as (connection, info):
        _local_space(authority, info)
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.delete",
            epoch=info.execution_epoch,
        )
        connection.execute(
            "UPDATE backup_inventory SET status = 'purged', database_sha256 = NULL "
            "WHERE status = 'contaminated'"
        )
        connection.execute(
            "UPDATE deletion_jobs SET status = 'complete', completed_at = ? "
            "WHERE status = 'pending'",
            (completed_at.isoformat(),),
        )
        completed = int(
            connection.execute(
                "SELECT count(*) FROM deletion_jobs WHERE status = 'complete'"
            ).fetchone()[0]
        )
    sanitize_database(root)
    return DeletionStatus(
        pending_jobs=0,
        completed_jobs=completed,
        purged_backups=purged,
        live_store_sanitized=True,
        completed_at=completed_at,
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
    "read_receipt",
    "read_space",
    "restore_backup",
]
