"""Versioned DB-only operation values and deterministic intent/receipt semantics."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from .records import Artifact, RecordModel, Text, Work

Revision = Annotated[int, Field(strict=True, ge=1)]
Digest = Annotated[str, Field(strict=True, pattern="^[0-9a-f]{64}$")]
Operation = Literal[
    "authorize_work",
    "revoke_work",
    "set_work_requirements",
    "cancel_work",
    "authorize_artifact",
    "publish_artifact",
    "restore_artifact",
]
ARTIFACT_OPERATIONS = ("authorize_artifact", "publish_artifact", "restore_artifact")
V2_FIELDS = {
    "artifact_id",
    "artifact_revision",
    "content_sha256",
    "content_size",
    "restore_version",
    "references",
}


class ArtifactReference(RecordModel):
    artifact_id: UUID
    version_id: UUID
    sha256: Digest


class ArtifactVersion(RecordModel):
    id: UUID
    artifact_id: UUID
    work_id: UUID
    process_id: UUID
    artifact_revision: Annotated[int, Field(strict=True, ge=2)]
    sha256: Digest
    size: Annotated[int, Field(strict=True, ge=0)]
    created_at: AwareDatetime
    state_revision: Revision

    @property
    def relative_path(self) -> str:
        return f"artifacts/{self.artifact_id}/{self.id}.blob"


class MutationRequest(RecordModel):
    version: Annotated[int, Field(strict=True, ge=1, le=2)] = 1
    operation_id: UUID
    workspace_id: UUID
    work_id: UUID
    expected_revision: Revision
    operation: Operation
    requirements: tuple[Text, ...] = ()
    artifact_references: tuple[UUID, ...] = ()
    provenance: Annotated[Text, Field(max_length=4096)]
    artifact_id: UUID | None = None
    artifact_revision: Revision | None = None
    content_sha256: Digest | None = None
    content_size: Annotated[int, Field(strict=True, ge=0)] | None = None
    restore_version: UUID | None = None
    references: tuple[ArtifactReference, ...] = ()

    @model_serializer(mode="wrap")
    def serialized(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        value: dict[str, Any] = handler(self)
        if self.version == 1 and all(getattr(self, name) in (None, ()) for name in V2_FIELDS):
            # Preserve old request JSON and all stored authorization/fingerprint hashes.
            for name in V2_FIELDS:
                value.pop(name, None)
        return value

    @model_validator(mode="after")
    def operation_payload(self) -> Self:
        if self.operation != "set_work_requirements" and self.requirements:
            raise ValueError("Only set_work_requirements accepts requirements")
        if self.version == 1 and (
            self.operation in ARTIFACT_OPERATIONS
            or any(getattr(self, name) not in (None, ()) for name in V2_FIELDS)
        ):
            raise ValueError("Artifact lifecycle requires request version 2")
        if self.operation in ARTIFACT_OPERATIONS:
            if self.artifact_id is None or self.artifact_revision is None:
                raise ValueError("Artifact operations require exact id and revision")
            if self.operation != "authorize_artifact":
                if self.content_sha256 is None or self.content_size is None:
                    raise ValueError("Content operations require exact digest and size")
            elif self.content_sha256 is not None or self.content_size is not None:
                raise ValueError("Artifact authorization does not accept content")
        elif any(getattr(self, name) is not None for name in V2_FIELDS - {"references"}):
            raise ValueError("Only Artifact operations accept content fields")
        if (self.operation == "restore_artifact") != (self.restore_version is not None):
            raise ValueError("Only restoration requires a registered restore_version")
        return self


class ReceiptQuery(RecordModel):
    version: Annotated[int, Field(strict=True, ge=1, le=1)] = 1
    workspace_id: UUID
    work_id: UUID
    operation_id: UUID


def canonical(value: RecordModel, *, exclude: set[str] | None = None) -> str:
    # Keep the accepted v1 request bytes/digests despite additional v2 model fields.
    excluded = set(exclude or ())
    if isinstance(value, MutationRequest) and value.version == 1:
        excluded |= V2_FIELDS
    return json.dumps(
        value.model_dump(mode="json", exclude=excluded),
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
        if work.status != "ready" or work.authority_scope not in (
            "work_metadata",
            "work_metadata_and_artifact",
        ):
            raise ValueError("Work is not ready or has no current permission")
        if request.operation == "set_work_requirements":
            change["executor_requirements"] = request.requirements
        elif request.operation == "cancel_work":
            change["status"] = "cancelled"
        elif request.operation == "authorize_artifact":
            change["authority_scope"] = "work_metadata_and_artifact"
        elif work.authority_scope != "work_metadata_and_artifact":
            raise ValueError("Work has no current Artifact permission")
    return Work.model_validate({**work.model_dump(), **change})


def evolve_artifact(artifact: Artifact, descriptor: ArtifactVersion) -> Artifact:
    if (descriptor.artifact_id, descriptor.work_id, descriptor.process_id) != (
        artifact.id,
        artifact.work_id,
        artifact.process_id,
    ) or descriptor.artifact_revision != artifact.revision + 1:
        raise ValueError("Version does not belong to the next Artifact revision")
    return Artifact.model_validate(
        {
            **artifact.model_dump(),
            "revision": descriptor.artifact_revision,
            "status": "registered",
            "active_version": descriptor.id,
        }
    )


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
    affected_projections: tuple[Literal["overview.md"], ...] = ()
    artifact_before: Artifact | None = None
    artifact_after: Artifact | None = None
    artifact_version: ArtifactVersion | None = None

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
        if self.request.operation == "publish_artifact":
            descriptor = self.artifact_version
            if descriptor is None or self.artifact_before is None:
                raise ValueError("Publication event requires Artifact images/version")
            if evolve_artifact(self.artifact_before, descriptor) != self.artifact_after:
                raise ValueError("Publication event does not reconstruct Artifact")
            if (
                descriptor.id != self.request.operation_id
                or descriptor.artifact_id != self.request.artifact_id
                or self.artifact_before.revision != self.request.artifact_revision
                or descriptor.sha256 != self.request.content_sha256
                or descriptor.size != self.request.content_size
                or descriptor.state_revision != self.state_revision
                or descriptor.created_at != self.recorded_at
            ):
                raise ValueError("Publication descriptor does not match request/event")
        elif any(
            value is not None
            for value in (self.artifact_before, self.artifact_after, self.artifact_version)
        ):
            raise ValueError("Only publication changes Artifact metadata")
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
    affected_projections: tuple[Literal["overview.md"], ...] = ()


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
        affected_projections=event.affected_projections,
    )


class MutationHistory(RecordModel):
    workspace_id: UUID
    state_revision: Annotated[int, Field(strict=True, ge=0)]
    events: tuple[MutationEvent, ...]
    receipts: tuple[MutationReceipt, ...]
