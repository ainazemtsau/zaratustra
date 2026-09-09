"""The one post-bootstrap domain mutation path, in literal plan §5 order."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from .artifacts import (
    ArtifactContent,
    ArtifactInspection,
    current_artifact,
    inspect_files,
    publish_bytes,
    read_versions,
    resolve_version,
    validate_bytes,
    verified_content,
)
from .handoffs import AcceptedHandoff
from .projections import (
    ProjectionStatus,
    projection_status,
    render_overview,
    write_projection,
)
from .protocol import (
    ARTIFACT_OPERATIONS,
    ArtifactReference,
    ArtifactVersion,
    Confirmation,
    ContextQuery,
    MutationEvent,
    MutationHistory,
    MutationReceipt,
    MutationRequest,
    ProcessQuery,
    ReceiptQuery,
    SavedResult,
    authorization_digest,
    event_receipt,
    evolve_artifact,
    evolve_process,
    evolve_work,
    fingerprint,
    next_records,
)
from .records import (
    Artifact,
    Event,
    Process,
    RecordModel,
    RecordsSnapshot,
    Text,
    Work,
    _read_records,
)
from .results import result_basis
from .workspace import WorkspaceError, WorkspaceInfo, workspace_connection


class MutationError(WorkspaceError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


class ProjectionRebuildError(MutationError):
    def __init__(self, receipt: MutationReceipt, detail: str) -> None:
        self.receipt = receipt
        super().__init__("rebuild_required", f"Mutation committed; {detail}")


class AuthorizationPrompt(RecordModel):
    workspace_path: Text
    current: RecordsSnapshot
    request: MutationRequest | ReceiptQuery | ContextQuery | ProcessQuery
    request_sha256: Text


@dataclass(frozen=True)
class LocalAuthorization:
    """Trusted adapter value, never parsed from JSON/CLI/model output.

    The local application's Python code is trusted. This is not a sandbox against
    arbitrary Python or other processes of the same OS user (owner W21 decision).
    """

    confirmation: Confirmation


def _work(snapshot: RecordsSnapshot, work_id: UUID | None = None) -> Work:
    for record in snapshot.records:
        if isinstance(record, Work) and (work_id is None or record.id == work_id):
            return record
    raise MutationError("invalid_work", "Create initial draft records first")


def prepare_authorization(
    path: Path, request: MutationRequest | ReceiptQuery | ContextQuery | ProcessQuery
) -> AuthorizationPrompt:
    """Owner-local preview only; no permission issued and no mutation performed."""
    request = type(request).model_validate(request.model_dump())
    with workspace_connection(path) as (connection, info):
        if info.schema_version < 3:
            raise MutationError("schema", "Mutation protocol requires explicit migration to 3")
        snapshot = _read_records(connection, info.workspace_id)
        if request.workspace_id != info.workspace_id or request.work_id not in {
            r.id for r in snapshot.records if isinstance(r, Work)
        }:
            raise MutationError("invalid_work", "Request does not name this workspace and Work")
        resolved = info.workspace.as_posix()
        return AuthorizationPrompt(
            workspace_path=resolved,
            current=snapshot,
            request=request,
            request_sha256=authorization_digest(resolved, request),
        )


def authorize_local(
    prompt: AuthorizationPrompt,
    *,
    channel: Literal["local-console", "local-chat"],
    actor: str,
    source_ref: str,
) -> LocalAuthorization:
    """Trusted adapter seam: call ONLY after actual owner permission was received.

    The console adapter supplies this after exact interactive confirmation. A
    trusted local-chat adapter with actual prior permission may call directly;
    no second identity check is required. Untrusted input is not such an adapter.
    No CLI flag, file reader or model-response importer invokes this function.
    """
    prompt = AuthorizationPrompt.model_validate(prompt.model_dump())
    digest = authorization_digest(prompt.workspace_path, prompt.request)
    if prompt.request_sha256 != digest:
        raise MutationError("permission_denied", "Changed authorization preview")
    return LocalAuthorization(
        Confirmation(
            channel=channel,
            actor=actor,
            source_ref=source_ref,
            confirmed_at=datetime.now(UTC),
            workspace_path=prompt.workspace_path,
            request_sha256=digest,
        )
    )


def _caller(
    path: Path,
    request: MutationRequest | ReceiptQuery | ContextQuery | ProcessQuery,
    caller: LocalAuthorization | None,
    snapshot: RecordsSnapshot,
) -> Confirmation:
    if type(caller) is not LocalAuthorization:
        raise MutationError("permission_denied", "Separate trusted local authorization required")
    confirmation = Confirmation.model_validate(caller.confirmation.model_dump())
    if (
        request.workspace_id != snapshot.workspace_id
        or request.work_id not in {r.id for r in snapshot.records if isinstance(r, Work)}
        or confirmation.workspace_path != path.as_posix()
        or confirmation.request_sha256 != authorization_digest(path.as_posix(), request)
    ):
        raise MutationError("permission_denied", "Authorization is not for this exact request")
    return confirmation


def _history(
    connection: sqlite3.Connection, snapshot: RecordsSnapshot, *, artifacts_enabled: bool = False
) -> MutationHistory:
    events = []
    for identity, revision, body in connection.execute(
        "SELECT id, state_revision, body FROM mutation_events ORDER BY state_revision"
    ):
        event = MutationEvent.model_validate_json(body)
        if (str(event.id), event.state_revision) != (identity, revision):
            raise WorkspaceError("Mutation event metadata mismatch")
        events.append(event)
    receipts = {}
    for operation_id, event_id, intent, body in connection.execute(
        "SELECT operation_id, event_id, fingerprint, body FROM mutation_receipts"
    ):
        receipt = MutationReceipt.model_validate_json(body)
        if (str(receipt.operation_id), str(receipt.event_id), receipt.fingerprint) != (
            operation_id,
            event_id,
            intent,
        ):
            raise WorkspaceError("Mutation receipt metadata mismatch")
        receipts[receipt.event_id] = receipt
    if len(events) != max(0, snapshot.state_revision - 1) or len(receipts) != len(events):
        raise WorkspaceError("Incomplete mutation/event/receipt history")
    schema = connection.execute("PRAGMA user_version").fetchone()[0]
    versions = read_versions(connection) if artifacts_enabled else ()
    current = {r.id: r for r in snapshot.records}
    reconstructed: dict[UUID, Process | Event | Work | Artifact] = {}
    if snapshot.records:
        initial_event = next(r for r in snapshot.records if isinstance(r, Event))
        initial_work = _work(snapshot, initial_event.work_id)
        initial_artifact = current_artifact(snapshot, initial_work.id)
        beginning = events[0].before if events else initial_work
        if (
            beginning.id != initial_work.id
            or beginning.revision != 1
            or beginning.status != "draft"
        ):
            raise WorkspaceError("Mutation history must start from initial draft")
        reconstructed = {r.id: r for r in snapshot.records if isinstance(r, (Process, Event))}
        process = next(r for r in snapshot.records if isinstance(r, Process))
        reconstructed[process.id] = Process.model_validate(
            process.model_dump() | dict(revision=1, pack_binding=None)
        )
        reconstructed[beginning.id] = beginning
        reconstructed[initial_artifact.id] = Artifact.model_validate(
            {
                **initial_artifact.model_dump(),
                "revision": 1,
                "status": "declared",
                "active_version": None,
            }
        )
    published: dict[UUID, ArtifactVersion] = {}
    ordered_receipts = []
    previous_events: list[MutationEvent] = []
    for revision, event in enumerate(events, start=2):
        request = event.request
        if (
            event.state_revision != revision
            or request.expected_revision != revision - 1
            or request.workspace_id != snapshot.workspace_id
        ):
            raise WorkspaceError("Mutation history workspace/revision mismatch")
        if reconstructed.get(event.before.id) != event.before:
            raise WorkspaceError("Broken mutation before/after chain")
        retained = receipts.get(event.id)
        if retained is None or retained != event_receipt(event):
            raise WorkspaceError("Receipt does not describe the committed event")
        ordered_receipts.append(retained)
        prior = RecordsSnapshot(
            workspace_id=snapshot.workspace_id,
            state_revision=revision - 1,
            records=tuple(reconstructed.values()),
        )
        artifact = current_artifact(prior, request.work_id)
        if request.operation == "bind_pack":
            if (
                schema < 7
                or event.process_before is None
                or event.process_after is None
                or reconstructed.get(event.process_before.id) != event.process_before
            ):
                raise WorkspaceError("Pack binding requires schema7 and exact Process history")
            reconstructed[event.process_after.id] = event.process_after
        if request.operation in ARTIFACT_OPERATIONS and (
            request.artifact_id != artifact.id or request.artifact_revision != artifact.revision
        ):
            raise WorkspaceError("Artifact event target/revision mismatch")
        for reference in request.references:
            descriptor = resolve_version(tuple(published.values()), artifact, reference.version_id)
            if (reference.artifact_id, reference.sha256) != (
                descriptor.artifact_id,
                descriptor.sha256,
            ):
                raise WorkspaceError("Historical artifact reference mismatch")
        if request.operation == "restore_artifact":
            restored = resolve_version(tuple(published.values()), artifact, request.restore_version)
            if (restored.sha256, restored.size) != (request.content_sha256, request.content_size):
                raise WorkspaceError("Historical restore descriptor mismatch")
        if event.artifact_version is not None:
            if event.artifact_before != artifact or event.artifact_after is None:
                raise WorkspaceError("Broken Artifact before/after chain")
            published[event.artifact_version.id] = event.artifact_version
            reconstructed[artifact.id] = event.artifact_after
        if request.submission is not None:
            if schema < 6 or event.result_artifact != artifact:
                raise WorkspaceError("Result requires schema6 and exact source Artifact")
            closure = result_basis(
                request, prior, tuple(previous_events), tuple(published.values())
            )
            if (
                closure != event.result_references
                or event.next_work is None
                or event.next_artifact is None
            ):
                raise WorkspaceError("Result does not preserve the complete historical grounds")
            reconstructed[event.next_work.id] = event.next_work
            reconstructed[event.next_artifact.id] = event.next_artifact
        reconstructed[event.after.id] = event.after
        previous_events.append(event)
    if reconstructed != current:
        raise WorkspaceError("Mutation history does not reconstruct current records")
    if artifacts_enabled:
        if published != {descriptor.id: descriptor for descriptor in versions}:
            raise WorkspaceError("Version registrations do not match committed publications")
    elif any(event.request.version != 1 for event in events) or (
        snapshot.records and current_artifact(snapshot).active_version is not None
    ):
        raise WorkspaceError("Artifact lifecycle requires schema 4")
    results = {
        str(e.request.operation_id): (
            str(e.before.id),
            str(e.next_work.id),
            SavedResult(event=e, receipt=event_receipt(e)),
        )
        for e in events
        if e.next_work is not None
    }
    if schema >= 6:
        saved_results = {
            op: (work, next_work, SavedResult.model_validate_json(body))
            for op, work, next_work, body in connection.execute(
                "SELECT operation_id, work_id, next_work_id, body FROM work_results"
            )
        }
        if results != saved_results:
            raise WorkspaceError("Result records do not match the committed history")
    elif results:
        raise WorkspaceError("Result storage requires schema 6")
    imported = {
        str(event.request.operation_id): (
            str(event.id),
            AcceptedHandoff(
                handoff=event.request.handoff,
                delivery=event.request.delivery,
                confirmation=event.confirmation,
                receipt=event_receipt(event),
            ),
        )
        for event in events
        if event.request.handoff is not None and event.request.delivery is not None
    }
    if connection.execute("PRAGMA user_version").fetchone()[0] >= 5:
        saved = {
            identity: (event_id, AcceptedHandoff.model_validate_json(body))
            for identity, event_id, body in connection.execute(
                "SELECT id, event_id, body FROM accepted_handoffs"
            )
        }
        if saved != imported:
            raise WorkspaceError("Accepted Handoff records do not match the committed history")
    elif imported:
        raise WorkspaceError("Handoff import requires schema 5")
    return MutationHistory(
        workspace_id=snapshot.workspace_id,
        state_revision=snapshot.state_revision,
        events=tuple(events),
        receipts=tuple(ordered_receipts),
    )


def read_records(path: Path) -> RecordsSnapshot:
    """Owner-local consistent record read, including v3 journal integrity checks."""
    with workspace_connection(path) as (connection, info):
        if info.schema_version < 2:
            raise WorkspaceError("Records require schema 2 or later; run zara migrate explicitly.")
        snapshot = _read_records(connection, info.workspace_id)
        if info.schema_version >= 3:
            _history(connection, snapshot, artifacts_enabled=info.schema_version >= 4)
        elif snapshot.state_revision not in (0, 1):
            raise WorkspaceError("Schema 2 only supports initial records")
        return snapshot


def read_history(path: Path) -> MutationHistory:
    """Owner-local audit. Not a Work-scoped context/receipt-disclosure endpoint."""
    with workspace_connection(path) as (connection, info):
        if info.schema_version < 3:
            raise MutationError("schema", "History requires explicit migration to 3")
        return _history(
            connection,
            _read_records(connection, info.workspace_id),
            artifacts_enabled=info.schema_version >= 4,
        )


def read_receipt(
    path: Path, query: ReceiptQuery, caller: LocalAuthorization | None = None
) -> MutationReceipt:
    query = ReceiptQuery.model_validate(query.model_dump())
    with workspace_connection(path) as (connection, info):
        if info.schema_version < 3:
            raise MutationError("schema", "Receipt requires explicit migration to 3")
        snapshot = _read_records(connection, info.workspace_id)
        _caller(info.workspace, query, caller, snapshot)
        if _work(snapshot, query.work_id).authority_scope not in (
            "work_metadata",
            "work_metadata_and_artifact",
        ):
            raise MutationError("permission_denied", "Current Work has no receipt-read permission")
        history = _history(connection, snapshot, artifacts_enabled=info.schema_version >= 4)
        for receipt in history.receipts:
            if receipt.operation_id == query.operation_id and receipt.work_id == query.work_id:
                return receipt
        raise MutationError("not_found", "No committed operation in this Work")


def read_handoffs(path: Path) -> tuple[AcceptedHandoff, ...]:
    """Owner-local saved acceptance inspection, not a scoped Work context package."""
    with workspace_connection(path) as (connection, info):
        if info.schema_version < 5:
            raise MutationError("schema", "Handoff storage requires explicit migration to 5")
        history = _history(
            connection, _read_records(connection, info.workspace_id), artifacts_enabled=True
        )
        return tuple(
            AcceptedHandoff(
                handoff=event.request.handoff,
                delivery=event.request.delivery,
                confirmation=event.confirmation,
                receipt=event_receipt(event),
            )
            for event in history.events
            if event.request.handoff is not None and event.request.delivery is not None
        )


def _mutate(
    connection: sqlite3.Connection,
    info: WorkspaceInfo,
    request: MutationRequest,
    caller: LocalAuthorization | None,
    content: bytes | None,
) -> MutationReceipt:
    if info.schema_version < 3 or (request.version == 2 and info.schema_version < 4):
        raise MutationError("schema", "Mutation requires explicit migration to 3/4")
    if request.version == 3 and info.schema_version < 5:
        raise MutationError("schema", "Handoff import requires explicit migration to 5")
    if request.version == 4 and info.schema_version < 6:
        raise MutationError("schema", "Result requires explicit migration to 6")
    if request.version == 5 and info.schema_version < 7:
        raise MutationError("schema", "Pack binding requires explicit migration to 7")
    # 2. Current Work + authority, in the same write transaction as the effect.
    snapshot = _read_records(connection, info.workspace_id)
    confirmation = _caller(info.workspace, request, caller, snapshot)
    before = _work(snapshot, request.work_id)
    artifact = current_artifact(snapshot, request.work_id)
    try:
        after = evolve_work(before, request)
        if request.operation in ARTIFACT_OPERATIONS and request.artifact_id != artifact.id:
            raise ValueError("The scope permits only this Work's declared Artifact")
    except ValueError as error:
        raise MutationError("permission_denied", str(error)) from error
    # 3. Global revision first, including refreshed duplicates.
    if request.expected_revision != snapshot.state_revision:
        raise MutationError("conflict", "Expected revision is not the current state revision")
    # 4. Saved identity and intent. Do not check physical bytes on duplicate delivery.
    enabled = info.schema_version >= 4
    history = _history(connection, snapshot, artifacts_enabled=enabled)
    intent = fingerprint(request)
    for stored in history.receipts:
        if stored.operation_id == request.operation_id:
            if stored.fingerprint != intent:
                raise MutationError("collision", "Operation id already belongs to another intent")
            return stored
    process_before = None
    process_after = None
    if request.operation == "bind_pack":
        process_before = next(
            row
            for row in snapshot.records
            if isinstance(row, Process) and row.id == before.process_id
        )
        try:
            process_after = evolve_process(process_before, request)
        except ValueError as error:
            raise MutationError("pack_bound", str(error)) from error
    # 5. Exact scoped references and bytes, before any DB/domain effect.
    if request.handoff is not None and request.handoff.source_revision != snapshot.state_revision:
        raise MutationError("conflict", "Handoff source revision is not current")
    if request.artifact_references:
        raise MutationError("unsupported_artifacts", "Use version 2 exact version/hash references")
    versions = read_versions(connection) if enabled else ()
    closure: tuple[ArtifactReference, ...] = ()
    if request.submission is not None:
        if request.submission.source_revision != snapshot.state_revision:
            raise MutationError("conflict", "Result source revision is not current")
        try:
            closure = result_basis(request, snapshot, history.events, versions)
        except (ValueError, KeyError) as error:
            raise MutationError("invalid_result", str(error)) from error
        by_version = {v.id: v for v in versions}
        for ref in closure:
            verified_content(info.workspace, by_version[ref.version_id])
    for reference in request.references:
        if reference.artifact_id != artifact.id:
            raise MutationError("invalid_artifact", "Reference is outside this Work")
        descriptor = resolve_version(versions, artifact, reference.version_id)
        if reference.sha256 != descriptor.sha256:
            raise MutationError("invalid_artifact", "Reference hash does not match registration")
        verified_content(info.workspace, descriptor)
    if request.operation in ARTIFACT_OPERATIONS and request.artifact_revision != artifact.revision:
        raise MutationError("conflict", "Expected Artifact revision is not current")
    now = datetime.now(UTC)
    published: ArtifactVersion | None = None
    artifact_after: Artifact | None = None
    if request.operation in ("publish_artifact", "restore_artifact"):
        checked = validate_bytes(content, request.content_sha256, request.content_size)
        if request.operation == "restore_artifact":
            descriptor = resolve_version(versions, artifact, request.restore_version)
            if (descriptor.sha256, descriptor.size) != (
                request.content_sha256,
                request.content_size,
            ):
                raise MutationError("invalid_artifact", "Repair must match the registered version")
            publish_bytes(info.workspace, descriptor, checked, restore=True)
        else:
            assert request.content_sha256 is not None and request.content_size is not None
            published = ArtifactVersion(
                id=request.operation_id,
                artifact_id=artifact.id,
                work_id=before.id,
                process_id=before.process_id,
                artifact_revision=artifact.revision + 1,
                sha256=request.content_sha256,
                size=request.content_size,
                created_at=now,
                state_revision=after.revision,
            )
            publish_bytes(info.workspace, published, checked)
            artifact_after = evolve_artifact(artifact, published)
    elif content is not None:
        raise MutationError("invalid_artifact", "This operation does not accept content")
    continuation_work = None
    continuation_artifact = None
    if request.submission is not None:
        continuation_work, continuation_artifact = next_records(
            request, now, before.process_id, before.pack_binding
        )
        for record in (continuation_work, continuation_artifact):
            connection.execute(
                "INSERT INTO core_records (id, kind, revision, body) VALUES (?, ?, ?, ?)",
                (str(record.id), record.kind, record.revision, record.model_dump_json()),
            )
    # 6. Complete file already exists. Registration + active switch commit with Work.
    if published is not None and artifact_after is not None:
        connection.execute(
            "INSERT INTO artifact_versions VALUES (?, ?, ?)",
            (str(published.id), str(artifact.id), published.model_dump_json()),
        )
        connection.execute(
            "UPDATE core_records SET revision = ?, body = ? WHERE id = ?",
            (artifact_after.revision, artifact_after.model_dump_json(), str(artifact.id)),
        )
    connection.execute(
        "UPDATE core_records SET revision = ?, body = ? WHERE id = ?",
        (after.revision, after.model_dump_json(), str(after.id)),
    )
    if process_after is not None:
        connection.execute(
            "UPDATE core_records SET revision = ?, body = ? WHERE id = ?",
            (process_after.revision, process_after.model_dump_json(), str(process_after.id)),
        )
    connection.execute("UPDATE core_state SET revision = ? WHERE singleton = 1", (after.revision,))
    # 7. One immutable event and receipt, including old/new Artifact and exact descriptor.
    event = MutationEvent(
        id=uuid4(),
        state_revision=after.revision,
        recorded_at=now,
        product_version=version("zaratustra"),
        request=request,
        confirmation=confirmation,
        fingerprint=intent,
        before=before,
        after=after,
        affected_projections=("overview.md",) if enabled else (),
        artifact_before=artifact if published is not None else None,
        artifact_after=artifact_after,
        artifact_version=published,
        next_work=continuation_work,
        next_artifact=continuation_artifact,
        result_artifact=artifact if request.submission is not None else None,
        result_references=closure,
        process_before=process_before,
        process_after=process_after,
    )
    connection.execute(
        "INSERT INTO mutation_events VALUES (?, ?, ?)",
        (str(event.id), event.state_revision, event.model_dump_json()),
    )
    receipt = event_receipt(event)
    connection.execute(
        "INSERT INTO mutation_receipts VALUES (?, ?, ?, ?)",
        (str(request.operation_id), str(event.id), intent, receipt.model_dump_json()),
    )
    if request.handoff is not None and request.delivery is not None:
        accepted = AcceptedHandoff(
            handoff=request.handoff,
            delivery=request.delivery,
            confirmation=confirmation,
            receipt=receipt,
        )
        connection.execute(
            "INSERT INTO accepted_handoffs VALUES (?, ?, ?)",
            (str(request.operation_id), str(event.id), accepted.model_dump_json()),
        )
    if continuation_work is not None:
        saved_result = SavedResult(event=event, receipt=receipt)
        connection.execute(
            "INSERT INTO work_results VALUES (?, ?, ?, ?)",
            (
                str(request.operation_id),
                str(before.id),
                str(continuation_work.id),
                saved_result.model_dump_json(),
            ),
        )
    _history(connection, _read_records(connection, info.workspace_id), artifacts_enabled=enabled)
    return receipt


def apply_mutation(
    path: Path,
    request: MutationRequest,
    caller: LocalAuthorization | None = None,
    *,
    content: bytes | None = None,
) -> MutationReceipt:
    # 1. Input schema, even for an already constructed Python value.
    request = MutationRequest.model_validate(request.model_dump())
    with workspace_connection(path, write=True) as (connection, info):
        receipt = _mutate(connection, info, request, caller, content)
    # 8. The receipt is durable. No post-commit file error may imply a rollback.
    # 9. Rebuild latest DB state, including when an authorized duplicate was delivered.
    if info.schema_version >= 4:
        try:
            rebuild_projections(path)
        except (WorkspaceError, OSError, ValueError) as error:
            raise ProjectionRebuildError(receipt, str(error)) from error
    return receipt


def _artifact_snapshot(
    connection: sqlite3.Connection, info: WorkspaceInfo
) -> tuple[RecordsSnapshot, MutationHistory, tuple[ArtifactVersion, ...]]:
    if info.schema_version < 4:
        raise MutationError("schema", "Artifacts/projections require explicit migration to 4")
    snapshot = _read_records(connection, info.workspace_id)
    history = _history(connection, snapshot, artifacts_enabled=True)
    return snapshot, history, read_versions(connection)


def read_artifact(path: Path, artifact_id: UUID, version_id: UUID | None = None) -> ArtifactContent:
    """Owner-local content inspection; every read verifies the returned immutable bytes."""
    with workspace_connection(path) as (connection, info):
        snapshot, _, versions = _artifact_snapshot(connection, info)
        artifact = next(
            (r for r in snapshot.records if isinstance(r, Artifact) and r.id == artifact_id), None
        )
        if artifact is None:
            raise MutationError("invalid_artifact", "Artifact is outside this Work")
        return verified_content(info.workspace, resolve_version(versions, artifact, version_id))


def inspect_artifacts(path: Path) -> ArtifactInspection:
    """Owner-local diagnosis. Never register, remove, repair or activate files."""
    with workspace_connection(path) as (connection, info):
        snapshot, _, versions = _artifact_snapshot(connection, info)
        return inspect_files(info.workspace, snapshot, versions)


def read_projection_status(path: Path) -> ProjectionStatus:
    with workspace_connection(path) as (connection, info):
        snapshot, history, versions = _artifact_snapshot(connection, info)
        content, timestamp = render_overview(snapshot, history, versions, info.created_at)
        return projection_status(info.workspace, content, snapshot.state_revision, timestamp)


def rebuild_projections(path: Path) -> ProjectionStatus:
    """Serialize writers, rebuild latest authoritative snapshot, change no DB state."""
    with workspace_connection(path, write=True) as (connection, info):
        snapshot, history, versions = _artifact_snapshot(connection, info)
        content, timestamp = render_overview(snapshot, history, versions, info.created_at)
        write_projection(info.workspace, content)
        return projection_status(info.workspace, content, snapshot.state_revision, timestamp)


def submit_result(
    path: Path, request: MutationRequest, caller: LocalAuthorization | None = None
) -> MutationReceipt:
    """Submit one exact Result through the one Mutation API."""
    request = MutationRequest.model_validate(request.model_dump())
    if request.operation != "submit_result":
        raise MutationError("invalid_result", "Expected submit_result request")
    return apply_mutation(path, request, caller)


def read_result(
    path: Path, query: ReceiptQuery, caller: LocalAuthorization | None = None
) -> SavedResult:
    """Discover durable outcome under current rights, including completed Work."""
    query = ReceiptQuery.model_validate(query.model_dump())
    with workspace_connection(path) as (connection, info):
        if info.schema_version < 6:
            raise MutationError("schema", "Result requires explicit migration to 6")
        snapshot = _read_records(connection, info.workspace_id)
        _caller(info.workspace, query, caller, snapshot)
        if _work(snapshot, query.work_id).authority_scope not in (
            "work_metadata",
            "work_metadata_and_artifact",
        ):
            raise MutationError("permission_denied", "Current Work has no Result-read permission")
        history = _history(connection, snapshot, artifacts_enabled=True)
        for event in history.events:
            if (
                event.request.operation_id == query.operation_id
                and event.before.id == query.work_id
                and event.next_work is not None
            ):
                return SavedResult(event=event, receipt=event_receipt(event))
        raise MutationError("not_found", "No committed Result in this Work")
