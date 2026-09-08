"""Versioned DB-only operation values and deterministic intent/receipt semantics."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .records import RecordModel, Text, Work

Revision = Annotated[int, Field(strict=True, ge=1)]
Digest = Annotated[str, Field(strict=True, pattern="^[0-9a-f]{64}$")]
Operation = Literal["authorize_work", "revoke_work", "set_work_requirements", "cancel_work"]


class MutationRequest(RecordModel):
    version: Annotated[int, Field(strict=True, ge=1, le=1)] = 1
    operation_id: UUID
    workspace_id: UUID
    work_id: UUID
    expected_revision: Revision
    operation: Operation
    requirements: tuple[Text, ...] = ()
    artifact_references: tuple[UUID, ...] = ()
    provenance: Annotated[Text, Field(max_length=4096)]

    @model_validator(mode="after")
    def operation_payload(self) -> Self:
        if self.operation != "set_work_requirements" and self.requirements:
            raise ValueError("Only set_work_requirements accepts requirements")
        return self


class ReceiptQuery(RecordModel):
    version: Annotated[int, Field(strict=True, ge=1, le=1)] = 1
    workspace_id: UUID
    work_id: UUID
    operation_id: UUID


def canonical(value: RecordModel, *, exclude: set[str] | None = None) -> str:
    return json.dumps(
        value.model_dump(mode="json", exclude=exclude),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def fingerprint(request: MutationRequest) -> str:
    return hashlib.sha256(
        canonical(request, exclude={"operation_id", "expected_revision"}).encode("utf-8")
    ).hexdigest()


def authorization_digest(path: str, request: MutationRequest | ReceiptQuery) -> str:
    envelope = json.dumps(
        [path, type(request).__name__, canonical(request)], ensure_ascii=True, separators=(",", ":")
    )
    return hashlib.sha256(envelope.encode("utf-8")).hexdigest()


class Confirmation(RecordModel):
    channel: Literal["local-console", "local-chat"]
    actor: Text
    source_ref: Text
    confirmed_at: AwareDatetime
    workspace_path: Text
    request_sha256: Digest


def evolve_work(work: Work, request: MutationRequest) -> Work:
    """Narrow state transition, also used to validate retained journal before/after images."""
    if request.work_id != work.id:
        raise ValueError("Wrong Work")
    change: dict[str, object] = {"revision": work.revision + 1}
    if request.operation == "revoke_work":
        change["authority_scope"] = "none"
    elif request.operation == "authorize_work":
        if work.status == "cancelled":
            raise ValueError("Terminal Work cannot be authorized")
        change.update(status="ready", authority_scope="work_metadata")
    else:
        if work.status != "ready" or work.authority_scope != "work_metadata":
            raise ValueError("Work is not ready or has no current permission")
        if request.operation == "set_work_requirements":
            change["executor_requirements"] = request.requirements
        else:
            change["status"] = "cancelled"
    return Work.model_validate({**work.model_dump(), **change})


class MutationEvent(RecordModel):
    id: UUID
    state_revision: Revision
    recorded_at: AwareDatetime
    product_version: Text
    request: MutationRequest
    confirmation: Confirmation
    fingerprint: Digest
    before: Work
    after: Work
    affected_projections: tuple[()] = ()

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.fingerprint != fingerprint(self.request):
            raise ValueError("Event intent fingerprint mismatch")
        if self.confirmation.request_sha256 != authorization_digest(
            self.confirmation.workspace_path, self.request
        ):
            raise ValueError("Event authorization binding mismatch")
        if self.request.expected_revision != self.before.revision:
            raise ValueError("Event expected revision mismatch")
        if self.state_revision != self.after.revision:
            raise ValueError("Event state revision mismatch")
        if self.request.artifact_references or evolve_work(self.before, self.request) != self.after:
            raise ValueError("Event does not describe an admitted change")
        return self


class MutationReceipt(RecordModel):
    operation_id: UUID
    event_id: UUID
    workspace_id: UUID
    work_id: UUID
    previous_revision: Revision
    new_revision: Revision
    fingerprint: Digest
    recorded_at: AwareDatetime
    product_version: Text
    affected_projections: tuple[()] = ()


def event_receipt(event: MutationEvent) -> MutationReceipt:
    return MutationReceipt(
        operation_id=event.request.operation_id,
        event_id=event.id,
        workspace_id=event.request.workspace_id,
        work_id=event.request.work_id,
        previous_revision=event.request.expected_revision,
        new_revision=event.state_revision,
        fingerprint=event.fingerprint,
        recorded_at=event.recorded_at,
        product_version=event.product_version,
    )


class MutationHistory(RecordModel):
    workspace_id: UUID
    state_revision: Annotated[int, Field(strict=True, ge=0)]
    events: tuple[MutationEvent, ...]
    receipts: tuple[MutationReceipt, ...]
