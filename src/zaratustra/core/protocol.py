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

from .records import Artifact, PackReference, Process, ProcessMaterial, RecordModel, Text, Work

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
    "accept_handoff",
    "submit_result",
    "bind_pack",
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
V3_FIELDS = {"handoff", "delivery"}
V4_FIELDS = {"submission"}
V5_FIELDS = {"pack_binding"}
V6_FIELDS = {"terminal_submission"}


class NextWork(RecordModel):
    work_id: UUID
    artifact_id: UUID
    goal: Text
    expected_result: Text
    acceptance: Annotated[tuple[Text, ...], Field(min_length=1)]
    boundaries: Annotated[tuple[Text, ...], Field(min_length=1)]
    budget: Text
    executor_requirements: tuple[Text, ...]
    artifact_title: Text
    authority_scope: Literal["work_metadata"]


class ArtifactReference(RecordModel):
    artifact_id: UUID
    version_id: UUID
    sha256: Digest


class ProcessMaterialSubmission(RecordModel):
    material_id: UUID
    title: Text
    media_type: Text
    content_sha256: Digest
    content_size: Annotated[int, Field(strict=True, ge=0)]


class ResultSubmission(RecordModel):
    source_revision: Revision
    result: ArtifactReference
    acceptance_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    next_work: NextWork

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len(set(self.acceptance_ids)) != len(self.acceptance_ids):
            raise ValueError("Acceptance ids must be unique")
        if self.next_work.work_id == self.next_work.artifact_id:
            raise ValueError("Next Work and Artifact ids must be distinct")
        return self


class TerminalResultSubmission(RecordModel):
    source_revision: Revision
    result: ArtifactReference
    acceptance_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len(set(self.acceptance_ids)) != len(self.acceptance_ids):
            raise ValueError("Acceptance ids must be unique")
        return self


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


HandoffText = Annotated[str, Field(strict=True, min_length=1, max_length=4096)]


class Handoff(RecordModel):
    """Portable accepted-result data. Every field is untrusted, including owner text."""

    kind: Literal["handoff"]
    version: Annotated[int, Field(strict=True, ge=1, le=1)]
    handoff_id: UUID
    workspace_id: UUID
    process: UUID
    related_work: UUID
    intent: Literal["accepted_result"]
    source_revision: Revision
    result: ArtifactReference
    basis: Annotated[tuple[ArtifactReference, ...], Field(max_length=32)] = ()
    provenance: HandoffText
    owner_instruction: HandoffText | None = None
    constraints: Annotated[tuple[HandoffText, ...], Field(max_length=32)] = ()
    open_questions: Annotated[tuple[HandoffText, ...], Field(max_length=32)] = ()
    created_by: Annotated[str, Field(strict=True, min_length=1, max_length=256)]


class HandoffDelivery(RecordModel):
    source_ref: HandoffText
    input_sha256: Digest


class MutationRequest(RecordModel):
    version: Annotated[int, Field(strict=True, ge=1, le=6)] = 1
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
    handoff: Handoff | None = None
    delivery: HandoffDelivery | None = None
    submission: ResultSubmission | None = None
    pack_binding: PackReference | None = None
    terminal_submission: TerminalResultSubmission | None = None

    @model_serializer(mode="wrap")
    def serialized(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        value: dict[str, Any] = handler(self)
        if self.version < 5 and self.pack_binding is None:
            value.pop("pack_binding", None)
        if self.version < 6:
            for name in V6_FIELDS:
                value.pop(name, None)
        if self.version < 4 and self.submission is None:
            value.pop("submission", None)
        if self.version < 3 and all(getattr(self, name) is None for name in V3_FIELDS):
            for name in V3_FIELDS:
                value.pop(name, None)
        if self.version == 1 and all(getattr(self, name) in (None, ()) for name in V2_FIELDS):
            # Preserve old request JSON and all stored authorization/fingerprint hashes.
            for name in V2_FIELDS:
                value.pop(name, None)
        return value

    @model_validator(mode="after")
    def operation_payload(self) -> Self:
        if self.operation == "bind_pack":
            if self.version != 5 or self.pack_binding is None:
                raise ValueError("Pack binding requires request 5 and an exact reference")
            if self.references or self.artifact_references:
                raise ValueError("Pack binding accepts no Artifact references")
        elif self.pack_binding is not None or self.version == 5:
            raise ValueError("Only bind_pack uses request 5/pack_binding")
        if self.operation == "submit_result":
            if self.version == 4 and self.submission is not None:
                result = self.submission.result
            elif self.version == 6 and self.terminal_submission is not None:
                result = self.terminal_submission.result
            else:
                raise ValueError("Result requires request 4+continuation or request 6 terminal")
            if self.references != (result,) or self.artifact_references:
                raise ValueError("Result request must retain its exact result reference")
        elif (
            self.submission is not None
            or self.terminal_submission is not None
            or self.version in (4, 6)
        ):
            raise ValueError("Only submit_result uses request 4/6 Result payload")
        if self.operation == "accept_handoff":
            handoff = self.handoff
            if self.version != 3 or handoff is None or self.delivery is None:
                raise ValueError("Handoff import requires request 3, Handoff and delivery")
            if (
                (self.operation_id, self.workspace_id, self.work_id)
                != (handoff.handoff_id, handoff.workspace_id, handoff.related_work)
                or self.references != (handoff.result, *handoff.basis)
                or self.provenance != handoff.provenance.strip()
                or self.artifact_references
            ):
                raise ValueError("Mutation must preserve the complete Handoff meaning")
        elif self.handoff is not None or self.delivery is not None or self.version == 3:
            raise ValueError("Only accept_handoff uses request 3/Handoff/delivery")
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


class ProcessMaterialRequest(RecordModel):
    version: Literal[1] = 1
    operation: Literal["save_process_material"] = "save_process_material"
    operation_id: UUID
    workspace_id: UUID
    process_id: UUID
    expected_revision: Revision
    provenance: Annotated[Text, Field(max_length=4096)]
    material: ProcessMaterialSubmission


class WorkCreationRequest(RecordModel):
    """Explicit Process-scoped intent to create one ordinary Work."""

    version: Literal[1] = 1
    operation: Literal["create_work"] = "create_work"
    operation_id: UUID
    workspace_id: UUID
    process_id: UUID
    expected_revision: Revision
    provenance: Annotated[Text, Field(max_length=4096)]
    pack_binding: PackReference
    work: NextWork

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if self.work.work_id == self.work.artifact_id:
            raise ValueError("Work and Artifact ids must be distinct")
        return self


class ReceiptQuery(RecordModel):
    version: Annotated[int, Field(strict=True, ge=1, le=1)] = 1
    workspace_id: UUID
    work_id: UUID
    operation_id: UUID


class ContextQuery(RecordModel):
    """Exact read request; the value itself never grants authority."""

    version: Annotated[int, Field(strict=True, ge=1, le=1)] = 1
    workspace_id: UUID
    work_id: UUID
    process_id: UUID
    expected_revision: Revision
    max_bytes: Annotated[int, Field(strict=True, ge=1, le=1048576)]
    references: Annotated[tuple[ArtifactReference, ...], Field(max_length=32)] = ()


class ProcessQuery(RecordModel):
    """Explicit metadata scope; neither the query nor a capability grants rights."""

    version: Literal[1] = 1
    workspace_id: UUID
    work_id: UUID
    process_id: UUID
    expected_revision: Revision
    visible_work_ids: Annotated[tuple[UUID, ...], Field(max_length=64)]
    selected_work_id: UUID | None = None
    max_bytes: Annotated[int, Field(strict=True, ge=1, le=1048576)]

    @model_validator(mode="after")
    def exact_scope(self) -> Self:
        if len(set(self.visible_work_ids)) != len(self.visible_work_ids):
            raise ValueError("Repeated metadata scope member")
        if self.selected_work_id is not None and self.selected_work_id not in self.visible_work_ids:
            raise ValueError("Selected Work must be in the explicit metadata scope")
        return self


class ProcessStateQuery(RecordModel):
    """Exact Process read; normal no-current is a value, not an error."""

    version: Literal[1] = 1
    workspace_id: UUID
    process_id: UUID
    expected_revision: Revision


class ProcessMaterialQuery(ProcessStateQuery):
    material_id: UUID


class ProcessReceiptQuery(ProcessStateQuery):
    operation_id: UUID


def canonical(value: RecordModel, *, exclude: set[str] | None = None) -> str:
    # Keep the accepted v1 request bytes/digests despite additional v2 model fields.
    excluded = set(exclude or ())
    if isinstance(value, MutationRequest) and value.version == 1:
        excluded |= V2_FIELDS
    if isinstance(value, MutationRequest) and value.version < 3:
        excluded |= V3_FIELDS
    if isinstance(value, MutationRequest) and value.version < 4:
        excluded |= V4_FIELDS
    if isinstance(value, MutationRequest) and value.version < 5:
        excluded |= V5_FIELDS
    if isinstance(value, MutationRequest) and value.version < 6:
        excluded |= V6_FIELDS
    return json.dumps(
        value.model_dump(mode="json", exclude=excluded),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def fingerprint(
    request: MutationRequest | ProcessMaterialRequest | WorkCreationRequest,
) -> str:
    excluded = {"operation_id", "expected_revision"}
    if request.operation == "accept_handoff":
        excluded.add("delivery")
    return hashlib.sha256(canonical(request, exclude=excluded).encode("utf-8")).hexdigest()


def authorization_digest(
    path: str,
    request: (
        MutationRequest
        | ProcessMaterialRequest
        | WorkCreationRequest
        | ReceiptQuery
        | ContextQuery
        | ProcessQuery
        | ProcessStateQuery
        | ProcessMaterialQuery
        | ProcessReceiptQuery
    ),
) -> str:
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
    change: dict[str, object] = {"revision": request.expected_revision + 1}
    if request.operation == "revoke_work":
        change["authority_scope"] = "none"
    elif request.operation == "authorize_work":
        if work.status in ("cancelled", "done"):
            raise ValueError("Terminal Work cannot be authorized")
        change.update(status="ready", authority_scope="work_metadata")
    else:
        repair_done = work.status == "done" and request.operation == "restore_artifact"
        if (work.status != "ready" and not repair_done) or work.authority_scope not in (
            "work_metadata",
            "work_metadata_and_artifact",
        ):
            raise ValueError("Work is not ready or has no current permission")
        if request.operation == "set_work_requirements":
            change["executor_requirements"] = request.requirements
        elif request.operation == "bind_pack":
            if work.pack_binding not in (None, request.pack_binding):
                raise ValueError("An existing Work pack binding cannot be changed")
            change["pack_binding"] = request.pack_binding
        elif request.operation == "cancel_work":
            change["status"] = "cancelled"
        elif request.operation == "authorize_artifact":
            change["authority_scope"] = "work_metadata_and_artifact"
        elif request.operation == "accept_handoff":
            if request.handoff is None or request.handoff.process != work.process_id:
                raise ValueError("Handoff is outside this Work's Process")
        elif request.operation == "submit_result":
            change["status"] = "done"
            change["completion_id"] = request.operation_id
        elif work.authority_scope != "work_metadata_and_artifact":
            raise ValueError("Work has no current Artifact permission")
    return Work.model_validate({**work.model_dump(), **change})


def evolve_process(process: Process, request: MutationRequest) -> Process:
    if request.operation != "bind_pack" or request.pack_binding is None:
        raise ValueError("Only bind_pack changes a Process binding")
    if process.pack_binding is not None:
        raise ValueError("Process is already bound; in-place pack migration is not supported")
    return Process.model_validate(
        process.model_dump()
        | dict(pack_binding=request.pack_binding, revision=request.expected_revision + 1)
    )


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
    next_work: Work | None = None
    next_artifact: Artifact | None = None
    result_artifact: Artifact | None = None
    result_references: tuple[ArtifactReference, ...] = ()
    process_before: Process | None = None
    process_after: Process | None = None

    @model_serializer(mode="wrap")
    def serialized(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        value: dict[str, Any] = handler(self)
        if self.request.operation != "bind_pack":
            value.pop("process_before", None)
            value.pop("process_after", None)
        if self.request.version < 4:
            for name in ("next_work", "next_artifact", "result_artifact", "result_references"):
                value.pop(name, None)
        return value

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.fingerprint != fingerprint(self.request):
            raise ValueError("Event intent fingerprint mismatch")
        if self.confirmation.request_sha256 != authorization_digest(
            self.confirmation.workspace_path, self.request
        ):
            raise ValueError("Event authorization binding mismatch")
        if (
            self.request.expected_revision < self.before.revision
            or self.state_revision != self.after.revision
            or self.state_revision != self.request.expected_revision + 1
        ):
            raise ValueError("Work event before/after revision mismatch")
        if self.request.operation == "bind_pack":
            if (
                self.process_before is None
                or self.process_before.id != self.before.process_id
                or self.before.pack_binding is not None
                or evolve_process(self.process_before, self.request) != self.process_after
            ):
                raise ValueError("Binding event must retain the exact Process transition")
        elif self.process_before is not None or self.process_after is not None:
            raise ValueError("Only bind_pack changes a Process")
        result_submission = self.request.submission or self.request.terminal_submission
        if result_submission is not None:
            if result_submission.source_revision != self.request.expected_revision:
                raise ValueError("Result source revision must be current at acceptance")
            if self.request.terminal_submission is not None:
                if self.next_work is not None or self.next_artifact is not None:
                    raise ValueError("Terminal Result cannot retain continuation records")
            else:
                work, artifact = next_records(
                    self.request, self.recorded_at, self.before.process_id, self.before.pack_binding
                )
                if self.next_work != work or self.next_artifact != artifact:
                    raise ValueError("Event must retain exact confirmed next records")
            if self.result_artifact is None or not self.result_references:
                raise ValueError("Result must retain source Artifact and reference closure")
        elif (
            any(x is not None for x in (self.next_work, self.next_artifact, self.result_artifact))
            or self.result_references
        ):
            raise ValueError("Only Result creates a continuation")
        if self.request.artifact_references:
            raise ValueError("Event does not describe an admitted change")
        if evolve_work(self.before, self.request) != self.after:
            raise ValueError("Event does not describe an admitted change")
        if self.request.handoff is not None and (
            self.request.handoff.source_revision != self.request.expected_revision
        ):
            raise ValueError("Accepted Handoff must have a current source revision")
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


class ProcessMutationReceipt(RecordModel):
    operation_id: UUID
    event_id: UUID
    workspace_id: UUID
    process_id: UUID
    previous_revision: Revision
    new_revision: Revision
    fingerprint: Digest
    recorded_at: AwareDatetime
    product_version: Text
    affected_projections: tuple[Literal["overview.md"], ...] = ()


class ProcessMaterialEvent(RecordModel):
    kind: Literal["process_material"] = "process_material"
    id: UUID
    state_revision: Revision
    recorded_at: AwareDatetime
    product_version: Text
    request: ProcessMaterialRequest
    confirmation: Confirmation
    fingerprint: Digest
    process_before: Process
    process_after: Process
    material: ProcessMaterial
    affected_projections: tuple[Literal["overview.md"], ...] = ()

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (
            self.fingerprint != fingerprint(self.request)
            or self.confirmation.request_sha256
            != authorization_digest(self.confirmation.workspace_path, self.request)
            or self.request.process_id != self.process_before.id
            or self.state_revision != self.request.expected_revision + 1
            or self.process_after
            != self.process_before.model_copy(update={"revision": self.state_revision})
            or material_record(self.request, self.recorded_at) != self.material
        ):
            raise ValueError("Material event must retain the exact Process transition")
        return self


class WorkCreationEvent(RecordModel):
    kind: Literal["work_creation"] = "work_creation"
    id: UUID
    state_revision: Revision
    recorded_at: AwareDatetime
    product_version: Text
    request: WorkCreationRequest
    confirmation: Confirmation
    fingerprint: Digest
    process_before: Process
    process_after: Process
    work: Work
    artifact: Artifact
    affected_projections: tuple[Literal["overview.md"], ...] = ()

    @model_validator(mode="after")
    def consistent(self) -> Self:
        expected_process = self.process_before.model_copy(update={"revision": self.state_revision})
        expected_work, expected_artifact = work_creation_records(self.request, self.recorded_at)
        if (
            self.fingerprint != fingerprint(self.request)
            or self.confirmation.request_sha256
            != authorization_digest(self.confirmation.workspace_path, self.request)
            or self.request.process_id != self.process_before.id
            or self.process_before.pack_binding is None
            or self.request.pack_binding != self.process_before.pack_binding
            or self.state_revision != self.request.expected_revision + 1
            or self.process_after != expected_process
            or (self.work, self.artifact) != (expected_work, expected_artifact)
        ):
            raise ValueError("Work creation event must retain the exact Process transition")
        return self


def process_event_receipt(
    event: ProcessMaterialEvent | WorkCreationEvent,
) -> ProcessMutationReceipt:
    return ProcessMutationReceipt(
        operation_id=event.request.operation_id,
        event_id=event.id,
        workspace_id=event.request.workspace_id,
        process_id=event.request.process_id,
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
    process_events: tuple[ProcessMaterialEvent, ...] = ()
    work_creation_events: tuple[WorkCreationEvent, ...] = ()
    process_receipts: tuple[ProcessMutationReceipt, ...] = ()

    @model_serializer(mode="wrap")
    def serialized(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        value: dict[str, Any] = handler(self)
        if not self.process_events:
            value.pop("process_events", None)
        if not self.work_creation_events:
            value.pop("work_creation_events", None)
        if not self.process_receipts:
            value.pop("process_receipts", None)
        return value


def next_records(
    request: MutationRequest,
    at: AwareDatetime,
    process_id: UUID,
    pack_binding: PackReference | None = None,
) -> tuple[Work, Artifact]:
    if request.submission is None:
        raise ValueError("Missing Result submission")
    spec = request.submission.next_work
    work = Work(
        id=spec.work_id,
        revision=request.expected_revision + 1,
        created_at=at,
        process_id=process_id,
        goal=spec.goal,
        expected_result=spec.expected_result,
        acceptance=spec.acceptance,
        boundaries=spec.boundaries,
        budget=spec.budget,
        executor_requirements=spec.executor_requirements,
        status="ready",
        authority_scope=spec.authority_scope,
        pack_binding=pack_binding,
    )
    artifact = Artifact(
        id=spec.artifact_id,
        revision=1,
        created_at=at,
        process_id=process_id,
        work_id=work.id,
        title=spec.artifact_title,
    )
    return work, artifact


def material_record(request: ProcessMaterialRequest, at: AwareDatetime) -> ProcessMaterial:
    submission = request.material
    return ProcessMaterial(
        id=submission.material_id,
        revision=request.expected_revision + 1,
        created_at=at,
        process_id=request.process_id,
        operation_id=request.operation_id,
        title=submission.title,
        media_type=submission.media_type,
        content_sha256=submission.content_sha256,
        content_size=submission.content_size,
    )


def work_creation_records(request: WorkCreationRequest, at: AwareDatetime) -> tuple[Work, Artifact]:
    spec = request.work
    work = Work(
        id=spec.work_id,
        revision=request.expected_revision + 1,
        created_at=at,
        process_id=request.process_id,
        goal=spec.goal,
        expected_result=spec.expected_result,
        acceptance=spec.acceptance,
        boundaries=spec.boundaries,
        budget=spec.budget,
        executor_requirements=spec.executor_requirements,
        status="ready",
        authority_scope=spec.authority_scope,
        pack_binding=request.pack_binding,
    )
    artifact = Artifact(
        id=spec.artifact_id,
        revision=1,
        created_at=at,
        process_id=request.process_id,
        work_id=work.id,
        title=spec.artifact_title,
    )
    return work, artifact


class SavedResult(RecordModel):
    event: MutationEvent
    receipt: MutationReceipt

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (
            self.event.request.submission is None and self.event.request.terminal_submission is None
        ) or self.receipt != event_receipt(self.event):
            raise ValueError("Saved Result must match its committed event and receipt")
        return self

    @property
    def next_work_id(self) -> UUID | None:
        return self.event.next_work.id if self.event.next_work is not None else None


class ProcessMaterialContent(RecordModel):
    material: ProcessMaterial
    content: bytes


class ProcessState(RecordModel):
    workspace_id: UUID
    state_revision: Revision
    process: Process
    resume_state: Literal["current_work", "no_current_work"]
    current_work: Work | None
    materials: tuple[ProcessMaterial, ...]
    results: tuple[SavedResult, ...]

    @model_validator(mode="after")
    def truthful_resume(self) -> Self:
        expected = "current_work" if self.current_work is not None else "no_current_work"
        if self.resume_state != expected:
            raise ValueError("Process resume state must match the authoritative current Work")
        if self.current_work is not None and self.current_work.process_id != self.process.id:
            raise ValueError("Current Work is outside the selected Process")
        return self
