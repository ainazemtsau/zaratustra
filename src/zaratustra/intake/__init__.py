"""Exact preview and standard-operation intake of new external text material."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from zaratustra.core import (
    Artifact,
    ArtifactError,
    ArtifactReference,
    Handoff,
    LocalAuthorization,
    MutationError,
    MutationReceipt,
    MutationRequest,
    PackReference,
    Process,
    ProjectionRebuildError,
    Work,
    WorkspaceError,
    apply_mutation,
    authorize_local,
    handoff_request,
    prepare_authorization,
    read_artifact,
    read_records,
    read_workspace,
)

MAX_INTAKE_BYTES = 393_216
MAX_MATERIAL_BYTES = 262_144

Digest = Annotated[str, Field(strict=True, pattern="^[0-9a-f]{64}$")]
MetadataText = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=4096)
]
ShortText = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=256)
]
MaterialText = Annotated[str, StringConstraints(strict=True, min_length=1)]
SOURCE_REF_ADAPTER: TypeAdapter[str] = TypeAdapter(MetadataText)


class IntakeError(WorkspaceError):
    """An intake was refused before the complete requested effects were known complete."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


class IntakeModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class IntakeSelection(IntakeModel):
    """Exact identities obtained from explicit discovery; never an authority value."""

    workspace_id: UUID
    process_id: UUID
    work_id: UUID


class ExternalMaterial(IntakeModel):
    """Strict untrusted transport envelope. Every field is data, never approval."""

    kind: Literal["external_material"]
    version: Literal[1]
    intake_id: UUID
    publication_id: UUID
    acceptance_id: UUID
    workspace_id: UUID
    process_id: UUID
    work_id: UUID
    artifact_id: UUID
    source_revision: Annotated[int, Field(strict=True, ge=1)]
    basis: Annotated[tuple[ArtifactReference, ...], Field(max_length=32)] = ()
    material: MaterialText
    provenance: MetadataText
    owner_instruction: MetadataText | None = None
    constraints: Annotated[tuple[MetadataText, ...], Field(max_length=32)] = ()
    open_questions: Annotated[tuple[MetadataText, ...], Field(max_length=32)] = ()
    created_by: ShortText

    @model_validator(mode="after")
    def distinct_ids_and_basis(self) -> Self:
        if len({self.intake_id, self.publication_id, self.acceptance_id}) != 3:
            raise ValueError("Intake, publication and acceptance ids must be distinct")
        if len({reference.version_id for reference in self.basis}) != len(self.basis):
            raise ValueError("Basis version references must be distinct")
        return self


class ReceivedMaterial(IntakeModel):
    status: Literal["validated_input"] = "validated_input"
    durability: Literal["published_by_separate_operation"] = "published_by_separate_operation"
    source_ref: MetadataText
    envelope_sha256: Digest
    envelope_size: Annotated[int, Field(strict=True, ge=1)]
    material_sha256: Digest
    material_size: Annotated[int, Field(strict=True, ge=1)]


class IntakeTarget(IntakeModel):
    workspace_id: UUID
    process_id: UUID
    work_id: UUID
    artifact_id: UUID
    original_revision: Annotated[int, Field(strict=True, ge=1)]
    current_artifact_revision: Annotated[int, Field(strict=True, ge=1)]
    work_status: Literal["ready"]
    authority_scope: Literal["work_metadata_and_artifact"]
    pack_binding: PackReference | None


class MaterialIntakePreview(IntakeModel):
    version: Literal[1] = 1
    intake_id: UUID
    received: ReceivedMaterial
    target: IntakeTarget
    current_active_version: ArtifactReference | None
    basis: tuple[ArtifactReference, ...]
    material: MaterialText
    publication_request: MutationRequest
    acceptance_request: MutationRequest
    expected_revision_after_acceptance: Annotated[int, Field(strict=True, ge=1)]
    completion: Literal["not_requested"] = "not_requested"


class CompletionEffect(IntakeModel):
    status: Literal["not_requested"] = "not_requested"
    result_operation_id: None = None
    next_work_id: None = None


class IntakeContinuation(IntakeModel):
    state: Literal["selected_work_ready"] = "selected_work_ready"
    work_id: UUID
    at_revision: Annotated[int, Field(strict=True, ge=1)]


class IntakeProgress(IntakeModel):
    intake_id: UUID
    preview_sha256: Digest
    received: ReceivedMaterial
    publication: MutationReceipt | None = None
    acceptance: MutationReceipt | None = None
    completion: CompletionEffect = CompletionEffect()
    continuation: IntakeContinuation | None = None
    warnings: tuple[ShortText, ...] = ()


class MaterialIntakeReceipt(IntakeProgress):
    status: Literal["accepted"] = "accepted"
    publication: MutationReceipt
    acceptance: MutationReceipt
    continuation: IntakeContinuation


class IncompleteIntakeError(IntakeError):
    """The progress value states exactly which cross-invocation effects committed."""

    def __init__(
        self,
        stage: Literal["publication", "acceptance"],
        progress: IntakeProgress,
        detail: str,
        *,
        unregistered_bytes_possible: bool = False,
    ) -> None:
        self.stage = stage
        self.progress = progress
        self.unregistered_bytes_possible = unregistered_bytes_possible
        super().__init__("intake_incomplete", f"{stage} incomplete: {detail}")


@dataclass(frozen=True)
class PreparedMaterialIntake:
    workspace: Path
    selection: IntakeSelection
    source_ref: str
    input_bytes: bytes
    envelope: ExternalMaterial
    material_bytes: bytes
    handoff_bytes: bytes
    preview: MaterialIntakePreview
    preview_sha256: str


@dataclass(frozen=True)
class MaterialIntakeAuthorization:
    """Trusted application token, created only after review of the complete preview."""

    workspace_path: str
    preview_sha256: str
    channel: Literal["local-console", "local-chat"]
    actor: str
    source_ref: str
    confirmed_at: datetime


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON key: {key}")
        value[key] = item
    return value


def _canonical_bytes(value: IntakeModel | Handoff) -> bytes:
    return json.dumps(
        value.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def preview_bytes(prepared: PreparedMaterialIntake) -> bytes:
    """Canonical complete bytes displayed by trusted adapters before confirmation."""
    return _canonical_bytes(prepared.preview)


def _parse(content: bytes) -> tuple[ExternalMaterial, bytes]:
    if not content:
        raise IntakeError("invalid_envelope", "External material envelope is empty")
    if len(content) > MAX_INTAKE_BYTES:
        raise IntakeError(
            "input_too_large", f"External material envelope exceeds {MAX_INTAKE_BYTES} bytes"
        )
    try:
        envelope = ExternalMaterial.model_validate(
            json.loads(content.decode("utf-8-sig"), object_pairs_hook=_unique_object)
        )
        material = envelope.material.encode("utf-8")
    except (UnicodeError, ValueError, RecursionError, ValidationError) as error:
        raise IntakeError("invalid_envelope", f"Invalid external material: {error}") from error
    if len(material) > MAX_MATERIAL_BYTES:
        raise IntakeError(
            "material_too_large", f"External material exceeds {MAX_MATERIAL_BYTES} UTF-8 bytes"
        )
    return envelope, material


def _record_graph(
    workspace: Path, selection: IntakeSelection, envelope: ExternalMaterial
) -> tuple[Process, Work, Artifact]:
    try:
        info = read_workspace(workspace)
        if info.schema_version < 7:
            raise IntakeError("schema", "Incoming material requires explicit schema 7")
        snapshot = read_records(workspace)
    except IntakeError:
        raise
    except (OSError, WorkspaceError, ValidationError) as error:
        raise IntakeError("source_unavailable", "Selected workspace is unavailable") from error
    if snapshot.workspace_id != selection.workspace_id:
        raise IntakeError("target_mismatch", "Selected workspace identity changed")
    process = next((row for row in snapshot.records if isinstance(row, Process)), None)
    work = next(
        (row for row in snapshot.records if isinstance(row, Work) and row.id == selection.work_id),
        None,
    )
    artifact = next(
        (
            row
            for row in snapshot.records
            if isinstance(row, Artifact) and row.work_id == selection.work_id
        ),
        None,
    )
    if (
        process is None
        or work is None
        or artifact is None
        or process.id != selection.process_id
        or work.process_id != process.id
        or artifact.process_id != process.id
    ):
        raise IntakeError("target_mismatch", "Selected Process/Work/Artifact identity changed")
    if (envelope.workspace_id, envelope.process_id, envelope.work_id, envelope.artifact_id) != (
        selection.workspace_id,
        selection.process_id,
        selection.work_id,
        artifact.id,
    ):
        raise IntakeError("target_mismatch", "Envelope does not name the exact selected target")
    if snapshot.state_revision != envelope.source_revision:
        raise IntakeError("stale_basis", "Envelope source revision is not current")
    if work.status != "ready" or work.authority_scope != "work_metadata_and_artifact":
        raise IntakeError("permission_denied", "Selected Work lacks current Artifact authority")
    return process, work, artifact


def _verified_reference(workspace: Path, reference: ArtifactReference) -> ArtifactReference:
    try:
        content = read_artifact(workspace, reference.artifact_id, reference.version_id)
    except (ArtifactError, MutationError, WorkspaceError, OSError) as error:
        raise IntakeError("invalid_basis", "Basis content is unavailable or invalid") from error
    if content.version.sha256 != reference.sha256:
        raise IntakeError("invalid_basis", "Basis hash does not match its immutable version")
    return reference


def prepare_material_intake(
    workspace: Path,
    selection: IntakeSelection,
    content: bytes,
    *,
    source_ref: str,
) -> PreparedMaterialIntake:
    """Build an exact preview without granting permission or changing the workspace."""
    try:
        selection = IntakeSelection.model_validate(selection.model_dump())
        source_ref = SOURCE_REF_ADAPTER.validate_python(source_ref)
    except (ValidationError, ValueError) as error:
        raise IntakeError("invalid_source", "Source reference is invalid") from error
    selected = workspace.expanduser().resolve()
    envelope, material = _parse(content)
    process, work, artifact = _record_graph(selected, selection, envelope)
    if any(reference.artifact_id != artifact.id for reference in envelope.basis):
        raise IntakeError("invalid_basis", "Basis is outside the selected Work Artifact")
    basis = tuple(_verified_reference(selected, reference) for reference in envelope.basis)
    current_active = None
    if artifact.active_version is not None:
        try:
            current = read_artifact(selected, artifact.id, artifact.active_version).version
        except (ArtifactError, MutationError, WorkspaceError, OSError) as error:
            raise IntakeError(
                "invalid_basis", "Current Artifact content is unavailable or invalid"
            ) from error
        current_active = ArtifactReference(
            artifact_id=artifact.id, version_id=current.id, sha256=current.sha256
        )
    # Public reads are separate transactions; reject a mixed preview if anything changed.
    process_after, work_after, artifact_after = _record_graph(selected, selection, envelope)
    if (process_after, work_after, artifact_after) != (process, work, artifact):
        raise IntakeError("stale_basis", "Selected target changed while preparing the preview")
    material_sha256 = hashlib.sha256(material).hexdigest()
    publication = MutationRequest(
        version=2,
        operation_id=envelope.publication_id,
        workspace_id=envelope.workspace_id,
        work_id=envelope.work_id,
        expected_revision=envelope.source_revision,
        operation="publish_artifact",
        provenance=envelope.provenance,
        artifact_id=envelope.artifact_id,
        artifact_revision=artifact.revision,
        content_sha256=material_sha256,
        content_size=len(material),
    )
    result = ArtifactReference(
        artifact_id=artifact.id,
        version_id=envelope.publication_id,
        sha256=material_sha256,
    )
    handoff = Handoff(
        kind="handoff",
        version=1,
        handoff_id=envelope.acceptance_id,
        workspace_id=envelope.workspace_id,
        process=envelope.process_id,
        related_work=envelope.work_id,
        intent="accepted_result",
        source_revision=envelope.source_revision + 1,
        result=result,
        basis=basis,
        provenance=envelope.provenance,
        owner_instruction=envelope.owner_instruction,
        constraints=envelope.constraints,
        open_questions=envelope.open_questions,
        created_by=envelope.created_by,
    )
    handoff_bytes = _canonical_bytes(handoff)
    try:
        acceptance = handoff_request(handoff_bytes, source_ref=f"entry-intake:{envelope.intake_id}")
    except WorkspaceError as error:
        raise IntakeError("invalid_envelope", "Generated Handoff metadata is invalid") from error
    received = ReceivedMaterial(
        source_ref=source_ref,
        envelope_sha256=hashlib.sha256(content).hexdigest(),
        envelope_size=len(content),
        material_sha256=material_sha256,
        material_size=len(material),
    )
    preview = MaterialIntakePreview(
        intake_id=envelope.intake_id,
        received=received,
        target=IntakeTarget(
            workspace_id=envelope.workspace_id,
            process_id=process.id,
            work_id=work.id,
            artifact_id=artifact.id,
            original_revision=envelope.source_revision,
            current_artifact_revision=artifact.revision,
            work_status="ready",
            authority_scope="work_metadata_and_artifact",
            pack_binding=work.pack_binding,
        ),
        current_active_version=current_active,
        basis=basis,
        material=envelope.material,
        publication_request=publication,
        acceptance_request=acceptance,
        expected_revision_after_acceptance=envelope.source_revision + 2,
    )
    digest = hashlib.sha256(_canonical_bytes(preview)).hexdigest()
    return PreparedMaterialIntake(
        workspace=selected,
        selection=selection,
        source_ref=source_ref,
        input_bytes=content,
        envelope=envelope,
        material_bytes=material,
        handoff_bytes=handoff_bytes,
        preview=preview,
        preview_sha256=digest,
    )


def authorize_material_intake(
    prepared: PreparedMaterialIntake,
    *,
    channel: Literal["local-console", "local-chat"],
    actor: str,
    source_ref: str,
) -> MaterialIntakeAuthorization:
    """Trusted seam: call only after actual review of ``preview_bytes(prepared)``."""
    if hashlib.sha256(preview_bytes(prepared)).hexdigest() != prepared.preview_sha256:
        raise IntakeError("permission_denied", "Changed intake preview")
    if not actor.strip() or not source_ref.strip():
        raise IntakeError("permission_denied", "Trusted confirmation identity is incomplete")
    return MaterialIntakeAuthorization(
        workspace_path=prepared.workspace.as_posix(),
        preview_sha256=prepared.preview_sha256,
        channel=channel,
        actor=actor.strip(),
        source_ref=source_ref.strip(),
        confirmed_at=datetime.now(UTC),
    )


def _authorization(
    prepared: PreparedMaterialIntake,
    authorization: MaterialIntakeAuthorization | None,
    request: MutationRequest,
    stage: str,
) -> LocalAuthorization:
    if type(authorization) is not MaterialIntakeAuthorization or (
        authorization.workspace_path != prepared.workspace.as_posix()
        or authorization.preview_sha256 != prepared.preview_sha256
        or hashlib.sha256(preview_bytes(prepared)).hexdigest() != prepared.preview_sha256
    ):
        raise IntakeError("permission_denied", "Exact trusted intake confirmation required")
    prompt = prepare_authorization(prepared.workspace, request)
    return authorize_local(
        prompt,
        channel=authorization.channel,
        actor=authorization.actor,
        source_ref=f"{authorization.source_ref}:{stage}:{prepared.envelope.intake_id}",
    )


def _progress(
    prepared: PreparedMaterialIntake,
    publication: MutationReceipt | None = None,
    acceptance: MutationReceipt | None = None,
    *,
    warnings: tuple[str, ...] = (),
) -> IntakeProgress:
    continuation = (
        IntakeContinuation(
            work_id=prepared.selection.work_id,
            at_revision=acceptance.new_revision,
        )
        if acceptance is not None
        else None
    )
    return IntakeProgress(
        intake_id=prepared.envelope.intake_id,
        preview_sha256=prepared.preview_sha256,
        received=prepared.preview.received,
        publication=publication,
        acceptance=acceptance,
        continuation=continuation,
        warnings=warnings,
    )


def execute_material_intake(
    prepared: PreparedMaterialIntake,
    authorization: MaterialIntakeAuthorization | None = None,
) -> MaterialIntakeReceipt:
    """Publish then accept through standard Core calls; never complete the Work."""
    if type(authorization) is not MaterialIntakeAuthorization:
        raise IntakeError("permission_denied", "Exact trusted intake confirmation required")
    fresh = prepare_material_intake(
        prepared.workspace,
        prepared.selection,
        prepared.input_bytes,
        source_ref=prepared.source_ref,
    )
    if fresh.preview != prepared.preview or fresh.preview_sha256 != prepared.preview_sha256:
        raise IntakeError("permission_denied", "Target, material or basis changed after preview")
    publication_caller = _authorization(
        fresh, authorization, fresh.preview.publication_request, "publication"
    )
    acceptance_caller = _authorization(
        fresh, authorization, fresh.preview.acceptance_request, "acceptance"
    )
    warnings: list[str] = []
    try:
        publication = apply_mutation(
            fresh.workspace,
            fresh.preview.publication_request,
            publication_caller,
            content=fresh.material_bytes,
        )
    except ProjectionRebuildError as error:
        publication = error.receipt
        warnings.append("publication committed; projection rebuild reported an error")
    except (WorkspaceError, OSError, ValueError) as error:
        raise IncompleteIntakeError(
            "publication",
            _progress(fresh),
            str(error),
            unregistered_bytes_possible=True,
        ) from error
    try:
        acceptance = apply_mutation(
            fresh.workspace, fresh.preview.acceptance_request, acceptance_caller
        )
    except ProjectionRebuildError as error:
        acceptance = error.receipt
        warnings.append("acceptance committed; projection rebuild reported an error")
    except (WorkspaceError, OSError, ValueError) as error:
        raise IncompleteIntakeError(
            "acceptance", _progress(fresh, publication, warnings=tuple(warnings)), str(error)
        ) from error
    progress = _progress(fresh, publication, acceptance, warnings=tuple(warnings))
    assert progress.continuation is not None
    return MaterialIntakeReceipt.model_validate(progress.model_dump() | {"status": "accepted"})


__all__ = [
    "MAX_INTAKE_BYTES",
    "MAX_MATERIAL_BYTES",
    "CompletionEffect",
    "ExternalMaterial",
    "IncompleteIntakeError",
    "IntakeContinuation",
    "IntakeError",
    "IntakeProgress",
    "IntakeSelection",
    "MaterialIntakeAuthorization",
    "MaterialIntakePreview",
    "MaterialIntakeReceipt",
    "PreparedMaterialIntake",
    "ReceivedMaterial",
    "authorize_material_intake",
    "execute_material_intake",
    "prepare_material_intake",
    "preview_bytes",
]
