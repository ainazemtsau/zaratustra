"""The one post-bootstrap domain mutation path, in literal plan §5 order."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Literal
from uuid import uuid4

from .protocol import (
    Confirmation,
    MutationEvent,
    MutationHistory,
    MutationReceipt,
    MutationRequest,
    ReceiptQuery,
    authorization_digest,
    event_receipt,
    evolve_work,
    fingerprint,
)
from .records import RecordModel, RecordsSnapshot, Text, Work, _read_records
from .workspace import WorkspaceError, workspace_connection


class MutationError(WorkspaceError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


class AuthorizationPrompt(RecordModel):
    workspace_path: Text
    current: RecordsSnapshot
    request: MutationRequest | ReceiptQuery
    request_sha256: Text


@dataclass(frozen=True)
class LocalAuthorization:
    """Trusted adapter value, never parsed from JSON/CLI/model output.

    The local application's Python code is trusted. This is not a sandbox against
    arbitrary Python or other processes of the same OS user (owner W21 decision).
    """

    confirmation: Confirmation


def _work(snapshot: RecordsSnapshot) -> Work:
    for record in snapshot.records:
        if isinstance(record, Work):
            return record
    raise MutationError("invalid_work", "Create initial draft records first")


def prepare_authorization(
    path: Path, request: MutationRequest | ReceiptQuery
) -> AuthorizationPrompt:
    """Owner-local preview only; no permission issued and no mutation performed."""
    request = type(request).model_validate(request.model_dump())
    with workspace_connection(path) as (connection, info):
        if info.schema_version != 3:
            raise MutationError("schema", "Mutation protocol requires explicit migration to 3")
        snapshot = _read_records(connection, info.workspace_id)
        if request.workspace_id != info.workspace_id or request.work_id != _work(snapshot).id:
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
    request: MutationRequest | ReceiptQuery,
    caller: LocalAuthorization | None,
    snapshot: RecordsSnapshot,
) -> Confirmation:
    if type(caller) is not LocalAuthorization:
        raise MutationError("permission_denied", "Separate trusted local authorization required")
    confirmation = Confirmation.model_validate(caller.confirmation.model_dump())
    if (
        request.workspace_id != snapshot.workspace_id
        or request.work_id != _work(snapshot).id
        or confirmation.workspace_path != path.as_posix()
        or confirmation.request_sha256 != authorization_digest(path.as_posix(), request)
    ):
        raise MutationError("permission_denied", "Authorization is not for this exact request")
    return confirmation


def _history(connection: sqlite3.Connection, snapshot: RecordsSnapshot) -> MutationHistory:
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
    previous: Work | None = None
    ordered_receipts = []
    for revision, event in enumerate(events, start=2):
        if event.state_revision != revision or event.request.workspace_id != snapshot.workspace_id:
            raise WorkspaceError("Mutation history workspace/revision mismatch")
        if previous is None:
            if event.before.revision != 1 or event.before.status != "draft":
                raise WorkspaceError("Mutation history must start from initial draft")
        elif event.before != previous:
            raise WorkspaceError("Broken mutation before/after chain")
        retained = receipts.get(event.id)
        if retained is None or retained != event_receipt(event):
            raise WorkspaceError("Receipt does not describe the committed event")
        ordered_receipts.append(retained)
        previous = event.after
    if previous is not None and previous != _work(snapshot):
        raise WorkspaceError("Mutation history does not reconstruct current Work")
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
        if info.schema_version == 3:
            _history(connection, snapshot)
        elif snapshot.state_revision not in (0, 1):
            raise WorkspaceError("Schema 2 only supports initial records")
        return snapshot


def read_history(path: Path) -> MutationHistory:
    """Owner-local audit. Not a Work-scoped context/receipt-disclosure endpoint."""
    with workspace_connection(path) as (connection, info):
        if info.schema_version != 3:
            raise MutationError("schema", "History requires explicit migration to 3")
        return _history(connection, _read_records(connection, info.workspace_id))


def read_receipt(
    path: Path, query: ReceiptQuery, caller: LocalAuthorization | None = None
) -> MutationReceipt:
    query = ReceiptQuery.model_validate(query.model_dump())
    with workspace_connection(path) as (connection, info):
        if info.schema_version != 3:
            raise MutationError("schema", "Receipt requires explicit migration to 3")
        snapshot = _read_records(connection, info.workspace_id)
        _caller(info.workspace, query, caller, snapshot)
        if _work(snapshot).authority_scope != "work_metadata":
            raise MutationError("permission_denied", "Current Work has no receipt-read permission")
        history = _history(connection, snapshot)
        for receipt in history.receipts:
            if receipt.operation_id == query.operation_id and receipt.work_id == query.work_id:
                return receipt
        raise MutationError("not_found", "No committed operation in this Work")


def apply_mutation(
    path: Path, request: MutationRequest, caller: LocalAuthorization | None = None
) -> MutationReceipt:
    # 1. Input schema. Revalidate even a model constructed by trusted Python code.
    request = MutationRequest.model_validate(request.model_dump())
    with workspace_connection(path, write=True) as (connection, info):
        if info.schema_version != 3:
            raise MutationError("schema", "Mutation requires explicit migration to 3")
        # 2. Current Work + authority, in the same write transaction as the effect.
        snapshot = _read_records(connection, info.workspace_id)
        confirmation = _caller(info.workspace, request, caller, snapshot)
        before = _work(snapshot)
        try:
            after = evolve_work(before, request)
        except ValueError as error:
            raise MutationError("permission_denied", str(error)) from error
        # 3. Expected global revision. Never look up a duplicate before this check.
        if request.expected_revision != snapshot.state_revision:
            raise MutationError("conflict", "Expected revision is not the current state revision")
        # 4. Duplicate identity + intent, with authorized disclosure only.
        history = _history(connection, snapshot)
        intent = fingerprint(request)
        for stored in history.receipts:
            if stored.operation_id == request.operation_id:
                if stored.fingerprint != intent:
                    raise MutationError(
                        "collision", "Operation id already belongs to another intent"
                    )
                return stored
        # 5. No content publication exists yet: reject every unsupported reference.
        if request.artifact_references:
            raise MutationError("unsupported_artifacts", "Content references require Work 4")
        # 6. Narrow DB change; goal/acceptance/bounds/budget/membership stay immutable.
        connection.execute(
            "UPDATE core_records SET revision = ?, body = ? WHERE id = ?",
            (after.revision, after.model_dump_json(), str(after.id)),
        )
        connection.execute(
            "UPDATE core_state SET revision = ? WHERE singleton = 1", (after.revision,)
        )
        # 7. Event and receipt commit with the mutation, including exact provenance.
        event = MutationEvent(
            id=uuid4(),
            state_revision=after.revision,
            recorded_at=datetime.now(UTC),
            product_version=version("zaratustra"),
            request=request,
            confirmation=confirmation,
            fingerprint=intent,
            before=before,
            after=after,
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
        _history(connection, _read_records(connection, info.workspace_id))
    # 8. Context manager has committed before any response escapes.
    # 9. The admitted DB-only operations have no implemented affected projections.
    # The persisted empty set is explicit; Work 4 must add actual rebuild behavior.
    return receipt
