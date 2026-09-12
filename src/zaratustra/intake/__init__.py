"""Exact preview and standard-operation intake of new external text material."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from io import BufferedRandom
from pathlib import Path
from typing import Annotated, Any, Literal, Self
from uuid import UUID, uuid4

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
    BasicProcessDocument,
    Handoff,
    LocalAuthorization,
    MutationError,
    MutationReceipt,
    MutationRequest,
    PackReference,
    Process,
    ProcessQuery,
    ProjectionRebuildError,
    ReceiptQuery,
    Work,
    WorkspaceError,
    apply_mutation,
    authorize_local,
    handoff_request,
    mutation_fingerprint,
    prepare_authorization,
    read_artifact,
    read_basic_process,
    read_handoffs,
    read_receipt,
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
    version: Annotated[int, Field(strict=True, ge=1, le=1)]
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


class IntakeCurrentContinuation(IntakeModel):
    """Current Work fact, distinct from the transfer's saved acceptance revision."""

    state: Literal["selected_work_ready", "saved_result", "cancelled"]
    work_id: UUID
    at_revision: Annotated[int, Field(strict=True, ge=1)]
    result_operation_id: UUID | None = None
    next_work_id: UUID | None = None

    @model_validator(mode="after")
    def exact_terminal_fields(self) -> Self:
        if self.state == "saved_result" and (
            self.result_operation_id is None or self.next_work_id is None
        ):
            raise ValueError("A saved Result requires Result and next-Work identities")
        if self.state != "saved_result" and (
            self.result_operation_id is not None or self.next_work_id is not None
        ):
            raise ValueError("Only a saved Result carries Result and next-Work identities")
        return self


class IntakeProgress(IntakeModel):
    intake_id: UUID
    preview_sha256: Digest
    received: ReceivedMaterial
    publication: MutationReceipt | None = None
    acceptance: MutationReceipt | None = None
    completion: CompletionEffect = CompletionEffect()
    continuation: IntakeContinuation | None = None
    current_continuation: IntakeCurrentContinuation | None = None
    warnings: tuple[ShortText, ...] = ()


class MaterialIntakeReceipt(IntakeProgress):
    status: Literal["accepted"] = "accepted"
    publication: MutationReceipt
    acceptance: MutationReceipt
    continuation: IntakeContinuation
    current_continuation: IntakeCurrentContinuation


class IntakeProgressInspection(IntakeModel):
    """Non-authoritative coordinator state; no receipt body or material disclosure."""

    version: Literal[1] = 1
    intake_id: UUID
    preview_sha256: Digest
    claimed_stages: tuple[Literal["publication", "acceptance"], ...]
    trust: Literal["unverified_coordinator_journal"] = "unverified_coordinator_journal"
    authorization_required_for_recovery: Literal[True] = True


class _IntakeJournal(IntakeModel):
    version: Literal[1] = 1
    intake_id: UUID
    input_sha256: Digest
    preview_sha256: Digest
    preview: MaterialIntakePreview
    publication: MutationReceipt | None = None
    acceptance: MutationReceipt | None = None
    continuation: IntakeContinuation | None = None

    @model_validator(mode="after")
    def ordered_progress(self) -> Self:
        if self.preview.intake_id != self.intake_id:
            raise ValueError("Journal identity does not match its preview")
        if hashlib.sha256(_canonical_bytes(self.preview)).hexdigest() != self.preview_sha256:
            raise ValueError("Journal preview hash does not match its bytes")
        if self.acceptance is not None and self.publication is None:
            raise ValueError("Acceptance cannot precede publication")
        if (self.acceptance is None) != (self.continuation is None):
            raise ValueError("Saved continuation must match accepted progress")
        return self


class IncompleteIntakeError(IntakeError):
    """The progress value states exactly which cross-invocation effects committed."""

    def __init__(
        self,
        stage: Literal["publication", "acceptance", "continuation"],
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


def _plain(path: Path) -> None:
    if path.is_symlink() or path.is_junction():
        raise IntakeError("progress_invalid", "Transfer progress paths must not be links")


def _journal_path(workspace: Path, intake_id: UUID) -> Path:
    inbox = workspace / "inbox"
    transfers = inbox / "transfers"
    for path in (inbox, transfers):
        _plain(path)
    return transfers / f"{intake_id}.json"


def _load_journal(workspace: Path, intake_id: UUID) -> _IntakeJournal | None:
    path = _journal_path(workspace, intake_id)
    _plain(path)
    try:
        if not path.exists():
            return None
        return _IntakeJournal.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as error:
        raise IntakeError(
            "progress_invalid", "Transfer progress is unavailable or invalid"
        ) from error


def _save_journal(workspace: Path, journal: _IntakeJournal) -> None:
    path = _journal_path(workspace, journal.intake_id)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _plain(path.parent)
        with temporary.open("xb") as stream:
            stream.write(_canonical_bytes(journal) + chr(10).encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise IntakeError("progress_unavailable", "Transfer progress could not be saved") from error


def _acquire_file_lock(stream: BufferedRandom) -> None:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
    else:
        fcntl: Any = import_module("fcntl")
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)


def _release_file_lock(stream: BufferedRandom) -> None:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl: Any = import_module("fcntl")
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def _intake_lock(workspace: Path, intake_id: UUID) -> Iterator[None]:
    locks = workspace / "inbox" / "transfer-locks"
    lock_path = locks / f"{intake_id}.lock"
    try:
        for path in (workspace / "inbox", locks, lock_path):
            _plain(path)
        locks.mkdir(parents=True, exist_ok=True)
        stream = lock_path.open("a+b")
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(bytes(1))
            stream.flush()
        _acquire_file_lock(stream)
    except OSError as error:
        if "stream" in locals():
            stream.close()
        raise IntakeError(
            "progress_lock_unavailable", "Transfer recovery lock is unavailable"
        ) from error
    try:
        yield
    finally:
        try:
            _release_file_lock(stream)
        except OSError:
            pass
        stream.close()


def inspect_material_intake_progress(
    workspace: Path, intake_id: UUID
) -> IntakeProgressInspection | None:
    """Read only untrusted stage names; authority is still required for recovery."""
    selected = workspace.expanduser().resolve()
    try:
        parsed_id = UUID(str(intake_id))
    except ValueError as error:
        raise IntakeError("progress_invalid", "Transfer identity is invalid") from error
    journal = _load_journal(selected, parsed_id)
    if journal is None:
        return None
    stages: list[Literal["publication", "acceptance"]] = []
    if journal.publication is not None:
        stages.append("publication")
    if journal.acceptance is not None:
        stages.append("acceptance")
    return IntakeProgressInspection(
        intake_id=journal.intake_id,
        preview_sha256=journal.preview_sha256,
        claimed_stages=tuple(stages),
    )


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


def _current_record_graph(
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
    return process, work, artifact


def _verified_reference(workspace: Path, reference: ArtifactReference) -> ArtifactReference:
    try:
        content = read_artifact(workspace, reference.artifact_id, reference.version_id)
    except (ArtifactError, MutationError, WorkspaceError, OSError) as error:
        raise IntakeError("invalid_basis", "Basis content is unavailable or invalid") from error
    if content.version.sha256 != reference.sha256:
        raise IntakeError("invalid_basis", "Basis hash does not match its immutable version")
    return reference


def _journal_intent(
    journal: _IntakeJournal,
    envelope: ExternalMaterial,
    content: bytes,
    material: bytes,
) -> MaterialIntakePreview:
    preview = journal.preview
    publication = preview.publication_request
    acceptance = preview.acceptance_request
    handoff = acceptance.handoff
    material_sha256 = hashlib.sha256(material).hexdigest()
    expected_publication = MutationRequest(
        version=2,
        operation_id=envelope.publication_id,
        workspace_id=envelope.workspace_id,
        work_id=envelope.work_id,
        expected_revision=envelope.source_revision,
        operation="publish_artifact",
        provenance=envelope.provenance,
        artifact_id=envelope.artifact_id,
        artifact_revision=preview.target.current_artifact_revision,
        content_sha256=material_sha256,
        content_size=len(material),
    )
    if (
        journal.input_sha256 != hashlib.sha256(content).hexdigest()
        or preview.received.envelope_sha256 != journal.input_sha256
        or preview.received.envelope_size != len(content)
        or preview.received.material_sha256 != material_sha256
        or preview.received.material_size != len(material)
        or preview.material != envelope.material
        or preview.basis != envelope.basis
        or preview.intake_id != envelope.intake_id
        or preview.target.workspace_id != envelope.workspace_id
        or preview.target.process_id != envelope.process_id
        or preview.target.work_id != envelope.work_id
        or preview.target.artifact_id != envelope.artifact_id
        or preview.target.original_revision != envelope.source_revision
        or publication != expected_publication
        or acceptance.operation_id != envelope.acceptance_id
        or acceptance.workspace_id != envelope.workspace_id
        or acceptance.work_id != envelope.work_id
        or acceptance.expected_revision != envelope.source_revision + 1
        or acceptance.operation != "accept_handoff"
        or handoff is None
        or handoff.handoff_id != envelope.acceptance_id
        or handoff.workspace_id != envelope.workspace_id
        or handoff.process != envelope.process_id
        or handoff.related_work != envelope.work_id
        or handoff.source_revision != envelope.source_revision + 1
        or handoff.result
        != ArtifactReference(
            artifact_id=envelope.artifact_id,
            version_id=envelope.publication_id,
            sha256=material_sha256,
        )
        or handoff.basis != envelope.basis
        or handoff.provenance != envelope.provenance
        or handoff.owner_instruction != envelope.owner_instruction
        or handoff.constraints != envelope.constraints
        or handoff.open_questions != envelope.open_questions
        or handoff.created_by != envelope.created_by
    ):
        raise IntakeError("intake_collision", "Intake identity belongs to another exact intent")
    expected_acceptance = handoff_request(
        _canonical_bytes(handoff), source_ref=f"entry-intake:{envelope.intake_id}"
    )
    if acceptance != expected_acceptance:
        raise IntakeError("intake_collision", "Intake identity belongs to another exact intent")
    return preview


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
    process, work, artifact = _current_record_graph(selected, selection, envelope)
    if any(reference.artifact_id != artifact.id for reference in envelope.basis):
        raise IntakeError("invalid_basis", "Basis is outside the selected Work Artifact")
    basis = tuple(_verified_reference(selected, reference) for reference in envelope.basis)
    journal = _load_journal(selected, envelope.intake_id)
    if journal is not None:
        preview = _journal_intent(journal, envelope, content, material)
        handoff = preview.acceptance_request.handoff
        assert handoff is not None
        return PreparedMaterialIntake(
            workspace=selected,
            selection=selection,
            source_ref=source_ref,
            input_bytes=content,
            envelope=envelope,
            material_bytes=material,
            handoff_bytes=_canonical_bytes(handoff),
            preview=preview,
            preview_sha256=journal.preview_sha256,
        )
    snapshot = read_records(selected)
    artifact_revision = artifact.revision
    if snapshot.state_revision == envelope.source_revision:
        if work.status != "ready" or work.authority_scope != "work_metadata_and_artifact":
            raise IntakeError("permission_denied", "Selected Work lacks current Artifact authority")
    elif snapshot.state_revision > envelope.source_revision:
        try:
            recovered = read_artifact(selected, artifact.id, envelope.publication_id)
        except (ArtifactError, MutationError, WorkspaceError, OSError) as error:
            raise IntakeError("stale_basis", "Envelope source revision is not current") from error
        if recovered.content != material:
            raise IntakeError("intake_collision", "Publication identity has different content")
        raise IntakeError(
            "progress_unavailable",
            "Original transfer progress/plan is unavailable; "
            "the exact original plan cannot be reconstructed",
        )
    else:
        raise IntakeError("stale_basis", "Envelope source revision is ahead of current state")
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
    process_after, work_after, artifact_after = _current_record_graph(selected, selection, envelope)
    if (process_after, work_after, artifact_after) != (process, work, artifact) or read_records(
        selected
    ).state_revision != snapshot.state_revision:
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
        artifact_revision=artifact_revision,
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
            current_artifact_revision=artifact_revision,
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


def _validate_intake_authorization(
    prepared: PreparedMaterialIntake,
    authorization: MaterialIntakeAuthorization | None,
) -> None:
    if type(authorization) is not MaterialIntakeAuthorization or (
        authorization.workspace_path != prepared.workspace.as_posix()
        or authorization.preview_sha256 != prepared.preview_sha256
        or hashlib.sha256(preview_bytes(prepared)).hexdigest() != prepared.preview_sha256
    ):
        raise IntakeError("permission_denied", "Exact trusted intake confirmation required")


def _authorization(
    prepared: PreparedMaterialIntake,
    authorization: MaterialIntakeAuthorization | None,
    request: MutationRequest | ReceiptQuery | ProcessQuery,
    stage: str,
) -> LocalAuthorization:
    _validate_intake_authorization(prepared, authorization)
    assert authorization is not None
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


def _journal_for(
    prepared: PreparedMaterialIntake,
    publication: MutationReceipt | None,
    acceptance: MutationReceipt | None,
) -> _IntakeJournal:
    continuation = (
        IntakeContinuation(work_id=prepared.selection.work_id, at_revision=acceptance.new_revision)
        if acceptance is not None
        else None
    )
    return _IntakeJournal(
        intake_id=prepared.envelope.intake_id,
        input_sha256=hashlib.sha256(prepared.input_bytes).hexdigest(),
        preview=prepared.preview,
        preview_sha256=prepared.preview_sha256,
        publication=publication,
        acceptance=acceptance,
        continuation=continuation,
    )


def _read_stage_receipt(
    prepared: PreparedMaterialIntake,
    authorization: MaterialIntakeAuthorization,
    request: MutationRequest,
    stage: Literal["publication", "acceptance"],
) -> MutationReceipt | None:
    query = ReceiptQuery(
        workspace_id=request.workspace_id,
        work_id=request.work_id,
        operation_id=request.operation_id,
    )
    caller = _authorization(prepared, authorization, query, f"{stage}-receipt")
    try:
        receipt = read_receipt(prepared.workspace, query, caller)
    except MutationError as error:
        if error.code == "not_found":
            return None
        raise
    if (
        receipt.workspace_id != request.workspace_id
        or receipt.work_id != request.work_id
        or receipt.operation_id != request.operation_id
        or receipt.previous_revision != request.expected_revision
        or receipt.new_revision != request.expected_revision + 1
        or receipt.fingerprint != mutation_fingerprint(request)
    ):
        raise IntakeError("intake_collision", f"{stage.title()} receipt has another exact intent")
    return receipt


def _validate_publication(prepared: PreparedMaterialIntake, receipt: MutationReceipt) -> None:
    try:
        content = read_artifact(
            prepared.workspace,
            prepared.envelope.artifact_id,
            prepared.envelope.publication_id,
        )
    except (ArtifactError, MutationError, WorkspaceError, OSError) as error:
        raise IntakeError(
            "progress_invalid", "Committed publication bytes are unavailable"
        ) from error
    request = prepared.preview.publication_request
    assert request.artifact_revision is not None
    if (
        receipt.operation_id != content.version.id
        or content.content != prepared.material_bytes
        or content.version.artifact_id != prepared.envelope.artifact_id
        or content.version.artifact_revision != request.artifact_revision + 1
        or content.version.state_revision != receipt.new_revision
        or content.version.sha256 != request.content_sha256
        or content.version.size != request.content_size
    ):
        raise IntakeError("intake_collision", "Publication record or bytes have another intent")


def _validate_acceptance(prepared: PreparedMaterialIntake, receipt: MutationReceipt) -> None:
    accepted = tuple(
        item
        for item in read_handoffs(prepared.workspace)
        if item.handoff.handoff_id == prepared.envelope.acceptance_id
    )
    request = prepared.preview.acceptance_request
    if (
        len(accepted) != 1
        or request.handoff is None
        or request.delivery is None
        or accepted[0].handoff != request.handoff
    ):
        raise IntakeError("progress_invalid", "Accepted Handoff record is inconsistent")
    if accepted[0].delivery != request.delivery or accepted[0].receipt != receipt:
        raise IntakeError("intake_collision", "Acceptance record has another exact intent")


def _validate_before_effect(
    prepared: PreparedMaterialIntake,
    publication: MutationReceipt | None,
    acceptance: MutationReceipt | None,
) -> tuple[Process, Work, Artifact]:
    if (
        tuple(
            _verified_reference(prepared.workspace, reference)
            for reference in prepared.preview.basis
        )
        != prepared.preview.basis
    ):
        raise IntakeError("invalid_basis", "Original basis changed during recovery")
    process, work, artifact = _current_record_graph(
        prepared.workspace, prepared.selection, prepared.envelope
    )
    snapshot = read_records(prepared.workspace)
    expected = prepared.envelope.source_revision + (1 if publication is not None else 0)
    if acceptance is None and snapshot.state_revision != expected:
        raise IntakeError("stale_basis", "Current revision was not derived by this transfer")
    if acceptance is None and (
        work.status != "ready"
        or work.authority_scope != "work_metadata_and_artifact"
        or work.pack_binding != prepared.preview.target.pack_binding
    ):
        raise IntakeError("permission_denied", "Selected Work is no longer ready with exact rights")
    expected_artifact_revision = prepared.preview.target.current_artifact_revision + (
        1 if publication is not None else 0
    )
    if acceptance is None and artifact.revision != expected_artifact_revision:
        raise IntakeError("stale_basis", "Artifact revision was not derived by this transfer")
    if publication is not None:
        _validate_publication(prepared, publication)
        if acceptance is None and artifact.active_version != publication.operation_id:
            raise IntakeError("stale_basis", "Transfer publication is no longer active")
    return process, work, artifact


def _current_continuation(
    prepared: PreparedMaterialIntake,
    authorization: MaterialIntakeAuthorization,
) -> IntakeCurrentContinuation:
    snapshot = read_records(prepared.workspace)
    query = ProcessQuery(
        workspace_id=prepared.selection.workspace_id,
        work_id=prepared.selection.work_id,
        process_id=prepared.selection.process_id,
        expected_revision=snapshot.state_revision,
        visible_work_ids=(prepared.selection.work_id,),
        selected_work_id=prepared.selection.work_id,
        max_bytes=1_048_576,
    )
    caller = _authorization(prepared, authorization, query, "current-continuation")
    package = read_basic_process(prepared.workspace, query, caller)
    document = BasicProcessDocument.model_validate_json(package.output)
    if document.continuation_state == "selected_work_ready":
        return IntakeCurrentContinuation(
            state="selected_work_ready",
            work_id=prepared.selection.work_id,
            at_revision=document.state_revision,
        )
    if document.continuation_state == "cancelled":
        return IntakeCurrentContinuation(
            state="cancelled",
            work_id=prepared.selection.work_id,
            at_revision=document.state_revision,
        )
    if document.continuation_state == "saved_result" and document.saved_continuation is not None:
        return IntakeCurrentContinuation(
            state="saved_result",
            work_id=prepared.selection.work_id,
            at_revision=document.state_revision,
            result_operation_id=document.saved_continuation.result_id,
            next_work_id=document.saved_continuation.next_work.work_id,
        )
    raise IntakeError("progress_invalid", "Accepted transfer has no truthful continuation")


def execute_material_intake(
    prepared: PreparedMaterialIntake,
    authorization: MaterialIntakeAuthorization | None = None,
) -> MaterialIntakeReceipt:
    """Recover, publish and accept through standard Core calls; never complete Work."""
    _validate_intake_authorization(prepared, authorization)
    assert authorization is not None
    with _intake_lock(prepared.workspace, prepared.envelope.intake_id):
        fresh = prepare_material_intake(
            prepared.workspace,
            prepared.selection,
            prepared.input_bytes,
            source_ref=prepared.source_ref,
        )
        if fresh.preview != prepared.preview or fresh.preview_sha256 != prepared.preview_sha256:
            raise IntakeError(
                "permission_denied", "Target, material or basis changed after preview"
            )
        stored = _load_journal(fresh.workspace, fresh.envelope.intake_id)
        if stored is None:
            try:
                _save_journal(fresh.workspace, _journal_for(fresh, None, None))
            except IntakeError as error:
                raise IncompleteIntakeError("publication", _progress(fresh), str(error)) from error
            stored = _load_journal(fresh.workspace, fresh.envelope.intake_id)
            assert stored is not None
        if (
            stored.input_sha256 != hashlib.sha256(fresh.input_bytes).hexdigest()
            or stored.preview != fresh.preview
            or stored.preview_sha256 != fresh.preview_sha256
        ):
            raise IntakeError("intake_collision", "Saved progress belongs to another exact intent")

        publication = _read_stage_receipt(
            fresh, authorization, fresh.preview.publication_request, "publication"
        )
        acceptance = _read_stage_receipt(
            fresh, authorization, fresh.preview.acceptance_request, "acceptance"
        )
        if stored.publication is not None and stored.publication != publication:
            raise IntakeError("progress_invalid", "Saved publication claim is not authoritative")
        if stored.acceptance is not None and stored.acceptance != acceptance:
            raise IntakeError("progress_invalid", "Saved acceptance claim is not authoritative")
        if acceptance is not None and publication is None:
            raise IntakeError("progress_invalid", "Acceptance exists without exact publication")

        warnings: list[str] = []
        _validate_before_effect(fresh, publication, acceptance)
        if publication is None:
            publication_caller = _authorization(
                fresh, authorization, fresh.preview.publication_request, "publication"
            )
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
            _validate_publication(fresh, publication)
            try:
                _save_journal(fresh.workspace, _journal_for(fresh, publication, None))
            except IntakeError as error:
                raise IncompleteIntakeError(
                    "acceptance",
                    _progress(fresh, publication, warnings=tuple(warnings)),
                    str(error),
                ) from error

        _validate_before_effect(fresh, publication, acceptance)
        if acceptance is None:
            acceptance_caller = _authorization(
                fresh, authorization, fresh.preview.acceptance_request, "acceptance"
            )
            try:
                acceptance = apply_mutation(
                    fresh.workspace, fresh.preview.acceptance_request, acceptance_caller
                )
            except ProjectionRebuildError as error:
                acceptance = error.receipt
                warnings.append("acceptance committed; projection rebuild reported an error")
            except (WorkspaceError, OSError, ValueError) as error:
                raise IncompleteIntakeError(
                    "acceptance",
                    _progress(fresh, publication, warnings=tuple(warnings)),
                    str(error),
                ) from error
            _validate_acceptance(fresh, acceptance)
            try:
                _save_journal(fresh.workspace, _journal_for(fresh, publication, acceptance))
            except IntakeError as error:
                raise IncompleteIntakeError(
                    "continuation",
                    _progress(fresh, publication, acceptance, warnings=tuple(warnings)),
                    str(error),
                ) from error
        else:
            _validate_acceptance(fresh, acceptance)
            if stored.acceptance is None or stored.publication is None:
                _save_journal(fresh.workspace, _journal_for(fresh, publication, acceptance))

        try:
            current = _current_continuation(fresh, authorization)
        except (WorkspaceError, OSError, ValueError) as error:
            raise IncompleteIntakeError(
                "continuation",
                _progress(fresh, publication, acceptance, warnings=tuple(warnings)),
                str(error),
            ) from error
        progress = _progress(fresh, publication, acceptance, warnings=tuple(warnings))
        assert progress.continuation is not None
        return MaterialIntakeReceipt.model_validate(
            progress.model_dump() | {"status": "accepted", "current_continuation": current}
        )


__all__ = [
    "MAX_INTAKE_BYTES",
    "MAX_MATERIAL_BYTES",
    "CompletionEffect",
    "IntakeCurrentContinuation",
    "ExternalMaterial",
    "IncompleteIntakeError",
    "IntakeContinuation",
    "IntakeError",
    "IntakeProgress",
    "IntakeProgressInspection",
    "IntakeSelection",
    "MaterialIntakeAuthorization",
    "MaterialIntakePreview",
    "MaterialIntakeReceipt",
    "PreparedMaterialIntake",
    "ReceivedMaterial",
    "authorize_material_intake",
    "execute_material_intake",
    "inspect_material_intake_progress",
    "prepare_material_intake",
    "preview_bytes",
]
