"""Recoverable provider-neutral creation of one exact constructed Process."""

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
    ValidationError,
    model_validator,
)

from zaratustra.core import (
    Artifact,
    ArtifactReference,
    Handoff,
    LocalAuthorization,
    MutationReceipt,
    MutationRequest,
    PackReference,
    Process,
    ProjectionRebuildError,
    Work,
    WorkspaceError,
    apply_mutation,
    authorize_local,
    create_initial_records,
    handoff_request,
    init_workspace,
    migrate_workspace,
    mutation_fingerprint,
    prepare_authorization,
    read_artifact,
    read_handoffs,
    read_history,
    read_records,
    read_workspace,
)
from zaratustra.entry import CatalogEntry, EntryError, add_entry, resolve_entry, source_path
from zaratustra.process_packs import (
    SUPPORTED_CAPABILITIES,
    ConstructionError,
    PackRegistry,
    ProcessDefinition,
    ProcessSnapshot,
    ReadyWork,
    binding_request,
    definition_sha256,
    evaluate_snapshot,
    initial_records,
    initial_requirements,
    registration,
    snapshot_bytes,
)

MAX_DRAFT_BYTES = 131_072
MAX_RESEARCH_BYTES = 1_048_576
MAX_PROPOSAL_BYTES = 1_048_576
MAX_JOURNAL_BYTES = 4_500_000
Digest = Annotated[str, Field(strict=True, pattern="^[0-9a-f]{64}$")]
ShortText = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=256)
]
Text = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=4096)
]
LongContent = Annotated[str, Field(strict=True, min_length=1, max_length=MAX_RESEARCH_BYTES)]
CreationStage = Literal[
    "draft",
    "research_waiting",
    "research_returned",
    "proposal_pending",
    "activation_pending",
    "activated",
]


class ProcessCreationError(WorkspaceError):
    """A creation stage was refused without replacing its retained intent."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


class CreationModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class _Designation(CreationModel):
    value: ShortText


class Clarification(CreationModel):
    question: Text
    why_needed: Text
    answer: Text | None = None


class CreationDraft(CreationModel):
    """Ordinary problem facts only; no product identity or path is requested."""

    version: Literal[1] = 1
    process_title: Text
    need: Text
    desired_outcomes: Annotated[tuple[Text, ...], Field(min_length=1, max_length=32)]
    constraints: Annotated[tuple[Text, ...], Field(min_length=1, max_length=32)]
    declared_capabilities: Annotated[tuple[Text, ...], Field(min_length=1, max_length=32)]
    clarifications: Annotated[tuple[Clarification, ...], Field(max_length=32)] = ()
    created_by: ShortText

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len(set(self.desired_outcomes)) != len(self.desired_outcomes):
            raise ValueError("Desired outcomes must be distinct")
        if len(set(self.constraints)) != len(self.constraints):
            raise ValueError("Constraints must be distinct")
        if len(set(self.declared_capabilities)) != len(self.declared_capabilities):
            raise ValueError("Declared capabilities must be distinct")
        if len({row.question for row in self.clarifications}) != len(self.clarifications):
            raise ValueError("Clarification questions must be distinct")
        return self


class ResearchRequest(CreationModel):
    version: Literal[1] = 1
    request_id: UUID
    creation_id: UUID
    designation: ShortText
    draft_sha256: Digest
    copyable_request: LongContent
    provider_contacted: Literal[False] = False


class ResearchReturn(CreationModel):
    version: Literal[1] = 1
    request_id: UUID
    request_sha256: Digest
    content_sha256: Digest
    content_size: Annotated[int, Field(strict=True, ge=1, le=MAX_RESEARCH_BYTES)]
    content: LongContent
    source_ref: Text
    created_by: ShortText
    status: Literal["untrusted_research"] = "untrusted_research"
    approval: Literal[False] = False


class SupportedProposal(CreationModel):
    version: Literal[1] = 1
    request_sha256: Digest
    research_sha256: Digest
    definition_sha256: Digest
    definition: ProcessDefinition
    capability_refusals: tuple[Text, ...] = ()
    status: Literal["pending_exact_activation"] = "pending_exact_activation"


class ActivationTarget(CreationModel):
    workspace_path: Text
    aliases: Annotated[tuple[ShortText, ...], Field(max_length=32)] = ()


class ActivationPlan(CreationModel):
    version: Literal[1] = 1
    workspace_path: Text
    aliases: Annotated[tuple[ShortText, ...], Field(max_length=32)] = ()
    workspace_id: UUID
    process_id: UUID
    work_id: UUID
    artifact_id: UUID
    pack_reference: PackReference
    definition_sha256: Digest
    initial_snapshot_sha256: Digest
    initial_snapshot_size: Annotated[int, Field(strict=True, ge=1)]
    requests: Annotated[tuple[MutationRequest, ...], Field(min_length=6, max_length=6)]

    @model_validator(mode="after")
    def exact_sequence(self) -> Self:
        if tuple(row.operation for row in self.requests) != (
            "authorize_work",
            "set_work_requirements",
            "bind_pack",
            "authorize_artifact",
            "publish_artifact",
            "accept_handoff",
        ):
            raise ValueError("Activation needs the exact six standard operations")
        if tuple(row.expected_revision for row in self.requests) != (1, 2, 3, 4, 5, 6):
            raise ValueError("Activation requests require the initial revision sequence")
        if len({row.operation_id for row in self.requests}) != 6:
            raise ValueError("Activation operation identities must be distinct")
        if any(
            (row.workspace_id, row.work_id) != (self.workspace_id, self.work_id)
            for row in self.requests
        ):
            raise ValueError("Activation requests must target the planned Work")
        requirements, binding, artifact_auth, publication, acceptance = self.requests[1:]
        handoff = acceptance.handoff
        if (
            requirements.requirements == ()
            or binding.pack_binding != self.pack_reference
            or artifact_auth.artifact_id != self.artifact_id
            or publication.artifact_id != self.artifact_id
            or publication.content_sha256 != self.initial_snapshot_sha256
            or publication.content_size != self.initial_snapshot_size
            or handoff is None
            or handoff.result
            != ArtifactReference(
                artifact_id=self.artifact_id,
                version_id=publication.operation_id,
                sha256=self.initial_snapshot_sha256,
            )
            or handoff.basis
        ):
            raise ValueError("Activation binding, snapshot publication or acceptance mismatch")
        return self


class _CreationJournal(CreationModel):
    version: Literal[1] = 1
    creation_id: UUID
    designation: ShortText
    draft: CreationDraft
    draft_sha256: Digest
    research_request: ResearchRequest | None = None
    research_return: ResearchReturn | None = None
    proposal: SupportedProposal | None = None
    activation_target: ActivationTarget | None = None
    bootstrap_workspace_id: UUID | None = None
    activation_plan: ActivationPlan | None = None


class ActivationSourceText(CreationModel):
    kind: Literal["request", "research"]
    locator: Text
    sha256: Digest
    content: LongContent
    trust: Literal["saved_need_and_constraints", "untrusted_research_not_approval"]


class ActivationPreview(CreationModel):
    version: Literal[1] = 1
    creation_id: UUID
    designation: str
    workspace_path: str
    request_sha256: Digest
    research_sha256: Digest
    definition_sha256: Digest
    pack_reference: PackReference
    initial_snapshot_sha256: Digest
    initial_snapshot_size: int
    proposal: SupportedProposal
    first_work: ReadyWork
    source_texts: Annotated[tuple[ActivationSourceText, ...], Field(min_length=2, max_length=2)]
    completed_operations: tuple[str, ...]
    pending_requests: tuple[MutationRequest, ...]
    assertions: tuple[str, ...]


class ProcessActivationAuthorization(CreationModel):
    workspace_path: str
    preview_sha256: Digest
    channel: Literal["local-console", "local-chat"]
    actor: ShortText
    source_ref: Text
    confirmed_at: datetime


class CreationStatus(CreationModel):
    version: Literal[1] = 1
    creation_id: UUID
    designation: str
    stage: CreationStage
    draft: CreationDraft
    draft_sha256: Digest
    open_clarifications: tuple[str, ...]
    research_request: ResearchRequest | None
    research_return: ResearchReturn | None
    proposal: SupportedProposal | None
    capability_refusals: tuple[str, ...]
    activation_target: ActivationTarget | None
    completed_operations: tuple[str, ...] = ()
    pending_operations: tuple[str, ...] = ()
    bootstrap_workspace_id: UUID | None = None
    workspace_id: UUID | None = None
    process_id: UUID | None = None
    first_work_id: UUID | None = None
    current_work_status: str | None = None
    current_authority_scope: str | None = None
    first_work_openable: bool = False
    cataloged: bool = False
    research_is_approval: Literal[False] = False


class ActivationReceipt(CreationModel):
    status: Literal["activated"] = "activated"
    creation: CreationStatus
    entry: CatalogEntry
    receipts: Annotated[tuple[MutationReceipt, ...], Field(min_length=6)]
    warnings: tuple[str, ...] = ()


class IncompleteActivationError(ProcessCreationError):
    def __init__(self, stage: str, status: CreationStatus, detail: str) -> None:
        self.stage = stage
        self.status = status
        super().__init__("activation_incomplete", detail)


@dataclass(frozen=True)
class PreparedActivation:
    catalog: Path
    journal_path: Path
    journal: _CreationJournal
    workspace: Path
    initial_snapshot: bytes
    completed: tuple[MutationReceipt, ...]
    pending: tuple[MutationRequest, ...]
    preview: ActivationPreview
    preview_sha256: str


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON key: {key}")
        value[key] = item
    return value


def _parse(content: bytes, maximum: int, label: str) -> Any:
    if not content or len(content) > maximum:
        raise ProcessCreationError("invalid_input", f"{label} must be 1..{maximum} bytes")
    try:
        return json.loads(content.decode("utf-8"), object_pairs_hook=_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ProcessCreationError("invalid_input", f"{label} must be strict UTF-8 JSON") from error


def _wire(value: BaseModel) -> bytes:
    return (
        json.dumps(
            value.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _digest(value: BaseModel) -> str:
    return hashlib.sha256(_wire(value)).hexdigest()


def _readable_wire(value: BaseModel) -> bytes:
    return (
        json.dumps(
            value.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def parse_creation_draft(content: bytes) -> CreationDraft:
    _parse(content, MAX_DRAFT_BYTES, "Creation draft")
    try:
        return CreationDraft.model_validate_json(content)
    except ValidationError as error:
        raise ProcessCreationError("invalid_draft", "Creation draft fields are invalid") from error


def parse_research_request(content: bytes) -> ResearchRequest:
    _parse(content, MAX_RESEARCH_BYTES, "Research request")
    try:
        return ResearchRequest.model_validate_json(content)
    except ValidationError as error:
        raise ProcessCreationError(
            "invalid_request", "Research request fields are invalid"
        ) from error


def parse_process_proposal(content: bytes) -> ProcessDefinition:
    _parse(content, MAX_PROPOSAL_BYTES, "Process proposal")
    try:
        return ProcessDefinition.model_validate_json(content)
    except ValidationError as error:
        raise ProcessCreationError("invalid_proposal", "Process definition is invalid") from error


def _journal_path(catalog: Path, designation: str) -> Path:
    selected = catalog.expanduser().resolve()
    key = hashlib.sha256(designation.strip().casefold().encode("utf-8")).hexdigest()
    return selected.parent / f"{selected.name}.process-creations" / f"{key}.json"


def _lock_path(path: Path) -> Path:
    return path.with_suffix(".lock")


def _acquire_file_lock(stream: BufferedRandom) -> None:
    if os.name == "nt":
        import msvcrt

        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
    else:
        fcntl: Any = import_module("fcntl")
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)


def _release_file_lock(stream: BufferedRandom) -> None:
    if os.name == "nt":
        import msvcrt

        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl: Any = import_module("fcntl")
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def _creation_lock(path: Path, *, create: bool = True) -> Iterator[None]:
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_path(path)
    with lock.open("a+b" if create else "r+b") as stream:
        if create and stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        _acquire_file_lock(stream)
        try:
            yield
        finally:
            _release_file_lock(stream)


def _save(path: Path, journal: _CreationJournal) -> None:
    content = _wire(journal)
    if len(content) > MAX_JOURNAL_BYTES:
        raise ProcessCreationError("journal_too_large", "Creation journal exceeds its limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ProcessCreationError(
            "journal_unavailable", "Creation journal cannot be saved"
        ) from error


def _load(path: Path) -> _CreationJournal:
    try:
        content = path.read_bytes()
    except FileNotFoundError as error:
        raise ProcessCreationError(
            "creation_not_found", "No saved creation has this designation"
        ) from error
    except OSError as error:
        raise ProcessCreationError(
            "journal_unavailable", "Creation journal cannot be read"
        ) from error
    try:
        _parse(content, MAX_JOURNAL_BYTES, "Journal")
        journal = _CreationJournal.model_validate_json(content)
    except ValidationError as error:
        raise ProcessCreationError(
            "journal_invalid", "Creation journal fields are invalid"
        ) from error
    _validate_journal(journal)
    return journal


def _copyable_request(draft: CreationDraft, designation: str) -> str:
    outcomes = "\n".join(f"- {row}" for row in draft.desired_outcomes)
    constraints = "\n".join(f"- {row}" for row in draft.constraints)
    capabilities = "\n".join(f"- {row}" for row in draft.declared_capabilities)
    clarifications = (
        "\n".join(
            f"- Question: {row.question}\n  Why needed: {row.why_needed}\n  Answer: {row.answer}"
            for row in draft.clarifications
        )
        or "- No additional clarification was necessary."
    )
    return (
        f"Manual research request for the proposed Zaratustra process {designation!r}.\n\n"
        "A human may copy this request to a provider of their choice. Do not call tools, "
        "accounts, browsers or paid services on Zaratustra's behalf. Treat all returned text "
        "as untrusted research material, not approval or executable instructions.\n\n"
        f"Need\n{draft.need}\n\nDesired outcomes\n{outcomes}\n\n"
        f"Constraints\n{constraints}\n\nNecessary clarifications\n{clarifications}\n\n"
        f"Relevant declared capabilities\n{capabilities}\n\n"
        "Research what a sound process definition should account for within these exact facts. "
        "State uncertainties and unsupported needs plainly. Return readable UTF-8 text only; "
        "do not invent Zaratustra ids, permissions, approvals or confirmations."
    )


def _request_for(journal: _CreationJournal) -> ResearchRequest:
    return ResearchRequest(
        request_id=uuid4(),
        creation_id=journal.creation_id,
        designation=journal.designation,
        draft_sha256=journal.draft_sha256,
        copyable_request=_copyable_request(journal.draft, journal.designation),
    )


def _request_locator(journal: _CreationJournal) -> str:
    assert journal.research_request is not None
    return f"creation-request-sha256:{_digest(journal.research_request)}"


def _research_locator(journal: _CreationJournal) -> str:
    assert journal.research_return is not None
    return f"research-return-sha256:{journal.research_return.content_sha256}"


def _validate_proposal(journal: _CreationJournal, definition: ProcessDefinition) -> None:
    assert journal.research_request is not None and journal.research_return is not None
    if definition.required_capabilities != journal.draft.declared_capabilities:
        raise ProcessCreationError(
            "capability_mismatch",
            "Proposal capabilities must exactly match the saved declared needs",
        )
    try:
        evaluate_snapshot(ProcessSnapshot(definition=definition))
    except ConstructionError as error:
        raise ProcessCreationError(error.code, str(error).partition(": ")[2]) from error
    requests = [row for row in definition.sources if row.kind == "request"]
    research = [row for row in definition.sources if row.kind == "research"]
    capabilities = [row for row in definition.sources if row.kind == "capability"]
    if len(requests) != 1 or requests[0].locator != _request_locator(journal):
        raise ProcessCreationError("source_mismatch", "Proposal must cite the exact saved request")
    if len(research) != 1 or research[0].locator != _research_locator(journal):
        raise ProcessCreationError(
            "source_mismatch", "Proposal must cite the exact research return"
        )
    if {row.locator for row in capabilities} != {
        f"capability:{row}" for row in definition.required_capabilities
    }:
        raise ProcessCreationError(
            "source_mismatch", "Proposal capability sources must name every exact capability"
        )
    used = {
        source_id
        for node in definition.nodes
        for reason in node.reasons
        for source_id in reason.source_ids
    }
    if requests[0].source_id not in used or research[0].source_id not in used:
        raise ProcessCreationError(
            "source_mismatch",
            "Proposal reasons must use both the saved request and research return",
        )


def _validate_journal(journal: _CreationJournal) -> None:
    if journal.draft_sha256 != _digest(journal.draft):
        raise ProcessCreationError("journal_invalid", "Saved draft digest does not match")
    request = journal.research_request
    returned = journal.research_return
    proposal = journal.proposal
    if request is not None and (
        request.creation_id != journal.creation_id
        or request.designation != journal.designation
        or request.draft_sha256 != journal.draft_sha256
        or request.copyable_request != _copyable_request(journal.draft, journal.designation)
    ):
        raise ProcessCreationError("journal_invalid", "Saved research request does not match draft")
    if returned is not None:
        if request is None or returned.request_id != request.request_id:
            raise ProcessCreationError("journal_invalid", "Research return has no exact request")
        encoded = returned.content.encode("utf-8")
        if (
            returned.request_sha256 != _digest(request)
            or returned.content_size != len(encoded)
            or returned.content_sha256 != hashlib.sha256(encoded).hexdigest()
        ):
            raise ProcessCreationError("journal_invalid", "Research return bytes do not match")
    if proposal is not None:
        if request is None or returned is None:
            raise ProcessCreationError("journal_invalid", "Proposal has no saved research grounds")
        _validate_proposal(journal, proposal.definition)
        if (
            proposal.request_sha256 != _digest(request)
            or proposal.research_sha256 != returned.content_sha256
            or proposal.definition_sha256 != definition_sha256(proposal.definition)
        ):
            raise ProcessCreationError("journal_invalid", "Proposal digests do not match")
    if journal.activation_plan is not None:
        if journal.activation_target is None or proposal is None:
            raise ProcessCreationError("journal_invalid", "Activation plan has no target/proposal")
        plan = journal.activation_plan
        if (
            plan.workspace_path != journal.activation_target.workspace_path
            or plan.aliases != journal.activation_target.aliases
            or plan.definition_sha256 != proposal.definition_sha256
        ):
            raise ProcessCreationError("journal_invalid", "Activation plan changed its target")
        if journal.bootstrap_workspace_id != plan.workspace_id:
            raise ProcessCreationError("journal_invalid", "Activation workspace identity changed")


def save_creation_draft(catalog: Path, designation: str, content: bytes) -> CreationStatus:
    draft = parse_creation_draft(content)
    try:
        cleaned = _Designation(value=designation).value
    except ValidationError as error:
        raise ProcessCreationError("invalid_designation", "Designation is invalid") from error
    path = _journal_path(catalog, cleaned)
    with _creation_lock(path):
        try:
            current = _load(path)
        except ProcessCreationError as error:
            if error.code != "creation_not_found":
                raise
            journal = _CreationJournal(
                creation_id=uuid4(),
                designation=cleaned,
                draft=draft,
                draft_sha256=_digest(draft),
            )
        else:
            if current.designation != cleaned:
                raise ProcessCreationError("designation_collision", "Creation designation changed")
            if current.research_request is not None and current.draft != draft:
                raise ProcessCreationError(
                    "stage_conflict", "A fixed research request prevents rewriting its draft"
                )
            journal = current.model_copy(update=dict(draft=draft, draft_sha256=_digest(draft)))
        _validate_journal(journal)
        _save(path, journal)
        return _status(catalog, path, journal)


def create_research_request(catalog: Path, designation: str) -> ResearchRequest:
    path = _journal_path(catalog, designation)
    with _creation_lock(path):
        journal = _load(path)
        if any(row.answer is None for row in journal.draft.clarifications):
            raise ProcessCreationError(
                "clarification_required", "Answer every saved necessary clarification first"
            )
        if journal.research_request is None:
            journal = journal.model_copy(update=dict(research_request=_request_for(journal)))
            _validate_journal(journal)
            _save(path, journal)
        assert journal.research_request is not None
        return journal.research_request


def save_research_request(path: Path, request: ResearchRequest) -> None:
    selected = path.expanduser().resolve()
    content = _wire(request)
    try:
        descriptor = os.open(selected, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
    except FileExistsError as error:
        raise ProcessCreationError(
            "output_exists", "Research request output already exists"
        ) from error
    except OSError as error:
        raise ProcessCreationError(
            "output_unavailable", "Research request cannot be saved"
        ) from error


def receive_research_return(
    catalog: Path,
    designation: str,
    request_content: bytes,
    response_content: bytes,
    *,
    created_by: str,
    source_ref: str,
) -> ResearchReturn:
    request = parse_research_request(request_content)
    if not response_content or len(response_content) > MAX_RESEARCH_BYTES:
        raise ProcessCreationError("invalid_research", "Research return is empty or too large")
    try:
        response = response_content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProcessCreationError("invalid_research", "Research return must be UTF-8") from error
    path = _journal_path(catalog, designation)
    with _creation_lock(path):
        journal = _load(path)
        if journal.research_request != request or _wire(request) != request_content:
            raise ProcessCreationError(
                "request_mismatch", "Return is not linked to the exact saved request"
            )
        candidate = ResearchReturn(
            request_id=request.request_id,
            request_sha256=_digest(request),
            content_sha256=hashlib.sha256(response_content).hexdigest(),
            content_size=len(response_content),
            content=response,
            source_ref=source_ref,
            created_by=created_by,
        )
        if journal.research_return is not None and journal.research_return != candidate:
            raise ProcessCreationError(
                "research_collision", "This request already has different returned material"
            )
        journal = journal.model_copy(update=dict(research_return=candidate))
        _validate_journal(journal)
        _save(path, journal)
        return candidate


def save_supported_proposal(
    catalog: Path, designation: str, proposal_content: bytes
) -> SupportedProposal:
    definition = parse_process_proposal(proposal_content)
    path = _journal_path(catalog, designation)
    with _creation_lock(path):
        journal = _load(path)
        if journal.research_request is None or journal.research_return is None:
            raise ProcessCreationError(
                "research_missing", "Proposal needs an exact research return"
            )
        _validate_proposal(journal, definition)
        candidate = SupportedProposal(
            request_sha256=_digest(journal.research_request),
            research_sha256=journal.research_return.content_sha256,
            definition_sha256=definition_sha256(definition),
            definition=definition,
        )
        if journal.proposal is not None and journal.proposal != candidate:
            raise ProcessCreationError(
                "proposal_collision", "A different proposal needs a new creation; T3 owns evolution"
            )
        journal = journal.model_copy(update=dict(proposal=candidate))
        _validate_journal(journal)
        _save(path, journal)
        return candidate


def _records(snapshot: Any) -> tuple[Process, Work, Artifact]:
    processes = [row for row in snapshot.records if isinstance(row, Process)]
    works = [row for row in snapshot.records if isinstance(row, Work)]
    artifacts = [row for row in snapshot.records if isinstance(row, Artifact)]
    if len(processes) != 1 or len(works) != 1 or len(artifacts) != 1:
        raise ProcessCreationError("workspace_collision", "Activation workspace has another graph")
    return processes[0], works[0], artifacts[0]


def _planned_records(snapshot: Any, plan: ActivationPlan) -> tuple[Process, Work, Artifact]:
    processes = [
        row for row in snapshot.records if isinstance(row, Process) and row.id == plan.process_id
    ]
    works = [row for row in snapshot.records if isinstance(row, Work) and row.id == plan.work_id]
    artifacts = [
        row for row in snapshot.records if isinstance(row, Artifact) and row.id == plan.artifact_id
    ]
    if len(processes) != 1 or len(works) != 1 or len(artifacts) != 1:
        raise ProcessCreationError("workspace_collision", "Planned Core graph is unavailable")
    return processes[0], works[0], artifacts[0]


def _pack_reference(definition: ProcessDefinition) -> PackReference:
    digest = definition_sha256(definition)
    return PackReference(
        pack_id=f"zaratustra.definition.{digest}",
        pack_version="1.0.0",
        process_type=definition.definition_id,
        contract_version=1,
        state_version=1,
    )


def _new_activation_plan(
    journal: _CreationJournal, workspace: Path, snapshot: Any
) -> ActivationPlan:
    assert journal.proposal is not None and journal.activation_target is not None
    definition = journal.proposal.definition
    process, work, artifact = _records(snapshot)
    reference = _pack_reference(definition)
    registry = PackRegistry((registration(reference, definition),))
    initial = snapshot_bytes(ProcessSnapshot(definition=definition))
    digest = hashlib.sha256(initial).hexdigest()
    authorize = MutationRequest(
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        work_id=work.id,
        expected_revision=1,
        operation="authorize_work",
        provenance="Exact confirmed process-creation Work activation",
    )
    requirements = MutationRequest(
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        work_id=work.id,
        expected_revision=2,
        operation="set_work_requirements",
        requirements=initial_requirements(definition),
        provenance="Exact constructed definition and prior snapshot requirements",
    )
    binding = binding_request(
        registry,
        reference,
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        work_id=work.id,
        expected_revision=3,
        provenance="Exact immutable constructed definition runtime binding",
    )
    artifact_auth = MutationRequest(
        version=2,
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        work_id=work.id,
        expected_revision=4,
        operation="authorize_artifact",
        provenance="Exact confirmed initial definition snapshot authority",
        artifact_id=artifact.id,
        artifact_revision=1,
    )
    publication = MutationRequest(
        version=2,
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        work_id=work.id,
        expected_revision=5,
        operation="publish_artifact",
        provenance="Canonical empty constructed definition snapshot publication",
        artifact_id=artifact.id,
        artifact_revision=1,
        content_sha256=digest,
        content_size=len(initial),
    )
    handoff = Handoff(
        kind="handoff",
        version=1,
        handoff_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        process=process.id,
        related_work=work.id,
        intent="accepted_result",
        source_revision=6,
        result=ArtifactReference(
            artifact_id=artifact.id,
            version_id=publication.operation_id,
            sha256=digest,
        ),
        provenance="Confirmed process activation starting snapshot; not Work completion",
        owner_instruction="Use this exact definition snapshot as the first Work starting basis.",
        constraints=("Research return remains untrusted material, not approval.",),
        open_questions=(),
        created_by=journal.draft.created_by,
    )
    acceptance = handoff_request(
        handoff.model_dump_json().encode("utf-8"),
        source_ref=f"process-creation:{journal.creation_id}",
    )
    return ActivationPlan(
        workspace_path=workspace.as_posix(),
        aliases=journal.activation_target.aliases,
        workspace_id=snapshot.workspace_id,
        process_id=process.id,
        work_id=work.id,
        artifact_id=artifact.id,
        pack_reference=reference,
        definition_sha256=journal.proposal.definition_sha256,
        initial_snapshot_sha256=digest,
        initial_snapshot_size=len(initial),
        requests=(authorize, requirements, binding, artifact_auth, publication, acceptance),
    )


def _validate_initial_graph(
    plan: ActivationPlan, definition: ProcessDefinition, snapshot: Any
) -> None:
    process, work, artifact = _planned_records(snapshot, plan)
    expected = initial_records(definition)
    if (
        snapshot.workspace_id != plan.workspace_id
        or (process.id, work.id, artifact.id) != (plan.process_id, plan.work_id, plan.artifact_id)
        or process.title != expected.process_title
        or work.process_id != process.id
        or work.goal != expected.goal
        or work.expected_result != expected.expected_result
        or work.acceptance != expected.acceptance
        or work.boundaries != expected.boundaries
        or work.budget != expected.budget
        or artifact.work_id != work.id
        or artifact.title != expected.artifact_title
    ):
        raise ProcessCreationError("workspace_collision", "Core graph is not this exact proposal")


def _core_progress(
    workspace: Path, plan: ActivationPlan, definition: ProcessDefinition, initial: bytes
) -> tuple[tuple[MutationReceipt, ...], tuple[MutationRequest, ...], Work]:
    snapshot = read_records(workspace)
    _validate_initial_graph(plan, definition, snapshot)
    history = read_history(workspace)
    if history.state_revision != snapshot.state_revision:
        raise ProcessCreationError("progress_invalid", "Core records and history revisions differ")
    for index, event in enumerate(history.events[:6]):
        request = plan.requests[index]
        if event.request != request or event.fingerprint != mutation_fingerprint(request):
            raise ProcessCreationError(
                "activation_collision", "Another mutation changed activation"
            )
    if len(history.events) < 6 and history.state_revision != 1 + len(history.events):
        raise ProcessCreationError("progress_invalid", "Activation is not a contiguous prefix")
    completed = history.receipts[: min(6, len(history.receipts))]
    process, work, _artifact = _planned_records(snapshot, plan)
    if len(completed) < 3 and process.pack_binding is not None:
        raise ProcessCreationError("activation_collision", "Process binding appeared out of order")
    if len(completed) >= 3 and process.pack_binding != plan.pack_reference:
        raise ProcessCreationError("activation_collision", "Process has another immutable binding")
    if len(completed) >= 2 and work.executor_requirements != plan.requests[1].requirements:
        raise ProcessCreationError("activation_collision", "Work requirements changed")
    if len(completed) >= 5:
        content = read_artifact(workspace, plan.artifact_id, plan.requests[4].operation_id)
        if content.content != initial:
            raise ProcessCreationError("activation_collision", "Initial snapshot bytes changed")
    if len(completed) >= 6:
        request = plan.requests[5]
        accepted = [
            row
            for row in read_handoffs(workspace)
            if row.handoff.handoff_id == request.operation_id
        ]
        if (
            len(accepted) != 1
            or request.handoff is None
            or accepted[0].handoff != request.handoff
            or accepted[0].delivery != request.delivery
            or accepted[0].receipt != completed[5]
        ):
            raise ProcessCreationError("progress_invalid", "Starting acceptance is inconsistent")
    pending = plan.requests[len(completed) :] if len(completed) < 6 else ()
    return completed, pending, work


def _entry_matches(
    catalog: Path,
    designation: str,
    entry: CatalogEntry,
    workspace: Path,
    plan: ActivationPlan,
) -> bool:
    return (
        entry.designation == designation
        and (entry.workspace_id, entry.process_id, entry.work_id)
        == (plan.workspace_id, plan.process_id, plan.work_id)
        and entry.aliases == plan.aliases
        and source_path(catalog, entry) == workspace
    )


def _ensure_entry(
    catalog: Path, designation: str, workspace: Path, plan: ActivationPlan
) -> CatalogEntry:
    try:
        entry = resolve_entry(catalog, designation)
    except EntryError as error:
        if error.code not in ("catalog_unavailable", "not_found", "ambiguous"):
            raise
        entry = add_entry(catalog, designation, workspace, plan.work_id, aliases=plan.aliases)
    if not _entry_matches(catalog, designation, entry, workspace, plan):
        raise ProcessCreationError("designation_collision", "Designation names another source")
    return entry


def _prepared(catalog: Path, path: Path, journal: _CreationJournal) -> PreparedActivation:
    assert journal.proposal is not None and journal.activation_plan is not None
    plan = journal.activation_plan
    workspace = Path(plan.workspace_path)
    initial = snapshot_bytes(ProcessSnapshot(definition=journal.proposal.definition))
    completed, pending, _work = _core_progress(
        workspace, plan, journal.proposal.definition, initial
    )
    request = journal.research_request
    returned = journal.research_return
    assert request is not None and returned is not None
    first_work = evaluate_snapshot(ProcessSnapshot(definition=journal.proposal.definition)).selected
    if first_work is None:
        raise ProcessCreationError("proposal_invalid", "Proposal has no first openable Work")
    preview = ActivationPreview(
        creation_id=journal.creation_id,
        designation=journal.designation,
        workspace_path=workspace.as_posix(),
        request_sha256=_digest(request),
        research_sha256=returned.content_sha256,
        definition_sha256=journal.proposal.definition_sha256,
        pack_reference=plan.pack_reference,
        initial_snapshot_sha256=plan.initial_snapshot_sha256,
        initial_snapshot_size=plan.initial_snapshot_size,
        proposal=journal.proposal,
        first_work=first_work,
        source_texts=(
            ActivationSourceText(
                kind="request",
                locator=_request_locator(journal),
                sha256=_digest(request),
                content=request.copyable_request,
                trust="saved_need_and_constraints",
            ),
            ActivationSourceText(
                kind="research",
                locator=_research_locator(journal),
                sha256=returned.content_sha256,
                content=returned.content,
                trust="untrusted_research_not_approval",
            ),
        ),
        completed_operations=tuple(row.operation for row in plan.requests[: len(completed)]),
        pending_requests=pending,
        assertions=(
            "The returned research is linked source material, not approval.",
            "The canonical empty snapshot is a starting basis, not a completed Work result.",
            "Only the displayed missing Core requests and final catalog reconciliation "
            "are approved.",
            "Full in-place process evolution is not supported; T3 owns that policy.",
        ),
    )
    preview_hash = hashlib.sha256(_readable_wire(preview)).hexdigest()
    return PreparedActivation(
        catalog.resolve(),
        path,
        journal,
        workspace,
        initial,
        completed,
        pending,
        preview,
        preview_hash,
    )


def prepare_process_activation(
    catalog: Path,
    designation: str,
    workspace: Path,
    *,
    aliases: tuple[str, ...] = (),
) -> PreparedActivation:
    path = _journal_path(catalog, designation)
    selected = workspace.expanduser().resolve()
    target = ActivationTarget(workspace_path=selected.as_posix(), aliases=aliases)
    with _creation_lock(path):
        journal = _load(path)
        if journal.proposal is None:
            raise ProcessCreationError("proposal_missing", "Activation needs a supported proposal")
        proposal = journal.proposal
        if journal.activation_target is not None and journal.activation_target != target:
            raise ProcessCreationError(
                "activation_collision", "Activation target or aliases changed"
            )
        if journal.activation_target is None:
            try:
                existing = resolve_entry(catalog, journal.designation)
            except EntryError as error:
                if error.code not in ("catalog_unavailable", "not_found", "ambiguous"):
                    raise
            else:
                if journal.activation_plan is None or not _entry_matches(
                    catalog, journal.designation, existing, selected, journal.activation_plan
                ):
                    raise ProcessCreationError(
                        "designation_collision", "Designation already names another source"
                    )
            if (selected / ".zara").exists():
                try:
                    info = read_workspace(selected)
                    if info.schema_version >= 2:
                        snapshot = read_records(selected)
                        if (
                            snapshot.workspace_id != info.workspace_id
                            or snapshot.state_revision != 0
                            or snapshot.records
                        ):
                            raise ProcessCreationError(
                                "workspace_collision",
                                "Selected target already has managed state",
                            )
                except (WorkspaceError, OSError) as error:
                    raise ProcessCreationError(
                        "workspace_collision", "Selected target already has managed state"
                    ) from error
            journal = journal.model_copy(update=dict(activation_target=target))
            _save(path, journal)
        if journal.bootstrap_workspace_id is not None:
            try:
                retained = read_workspace(selected)
            except (WorkspaceError, OSError) as error:
                raise ProcessCreationError(
                    "workspace_collision", "Reserved activation workspace is unavailable"
                ) from error
            if retained.workspace_id != journal.bootstrap_workspace_id:
                raise ProcessCreationError(
                    "workspace_collision", "Reserved activation workspace identity changed"
                )
        if not selected.exists():
            try:
                selected.mkdir(parents=True)
            except OSError as error:
                raise ProcessCreationError(
                    "workspace_unavailable", "Activation workspace cannot be created"
                ) from error
        info = init_workspace(selected)
        if journal.bootstrap_workspace_id is None:
            journal = journal.model_copy(update=dict(bootstrap_workspace_id=info.workspace_id))
            _save(path, journal)
        elif journal.bootstrap_workspace_id != info.workspace_id:
            raise ProcessCreationError(
                "workspace_collision", "Reserved activation workspace identity changed"
            )
        if info.schema_version < 9:
            migrate_workspace(selected, target_version=9)
        snapshot = read_records(selected)
        if not snapshot.records:
            snapshot = create_initial_records(selected, initial_records(proposal.definition))
        if journal.activation_plan is None:
            if snapshot.state_revision != 1 or read_history(selected).events:
                raise ProcessCreationError(
                    "progress_unavailable", "Advanced workspace has no retained activation plan"
                )
            plan = _new_activation_plan(journal, selected, snapshot)
            _validate_initial_graph(plan, proposal.definition, snapshot)
            journal = journal.model_copy(update=dict(activation_plan=plan))
            _validate_journal(journal)
            _save(path, journal)
        return _prepared(catalog, path, journal)


def activation_preview_bytes(prepared: PreparedActivation) -> bytes:
    """Exact confirmation bytes, rendered as readable UTF-8 without escaped text."""
    return _readable_wire(prepared.preview)


def authorize_process_activation(
    prepared: PreparedActivation,
    *,
    channel: Literal["local-console", "local-chat"],
    actor: str,
    source_ref: str,
) -> ProcessActivationAuthorization:
    if hashlib.sha256(activation_preview_bytes(prepared)).hexdigest() != prepared.preview_sha256:
        raise ProcessCreationError("permission_denied", "Changed activation preview")
    if not actor.strip() or not source_ref.strip():
        raise ProcessCreationError("permission_denied", "Confirmation identity is incomplete")
    return ProcessActivationAuthorization(
        workspace_path=prepared.workspace.as_posix(),
        preview_sha256=prepared.preview_sha256,
        channel=channel,
        actor=actor,
        source_ref=source_ref,
        confirmed_at=datetime.now(UTC),
    )


def _validate_activation_authorization(
    prepared: PreparedActivation, authorization: ProcessActivationAuthorization | None
) -> ProcessActivationAuthorization:
    if (
        authorization is None
        or authorization.workspace_path != prepared.workspace.as_posix()
        or authorization.preview_sha256 != prepared.preview_sha256
    ):
        raise ProcessCreationError(
            "permission_denied", "Exact current activation preview was not confirmed"
        )
    return authorization


def execute_process_activation(
    prepared: PreparedActivation, authorization: ProcessActivationAuthorization | None
) -> ActivationReceipt:
    auth = _validate_activation_authorization(prepared, authorization)
    with _creation_lock(prepared.journal_path):
        journal = _load(prepared.journal_path)
        fresh = _prepared(prepared.catalog, prepared.journal_path, journal)
        if activation_preview_bytes(fresh) != activation_preview_bytes(prepared):
            raise ProcessCreationError("stale_activation", "Activation changed after confirmation")
        warnings: list[str] = []
        for request in fresh.pending:
            try:
                prompt = prepare_authorization(fresh.workspace, request)
                caller: LocalAuthorization = authorize_local(
                    prompt,
                    channel=auth.channel,
                    actor=auth.actor,
                    source_ref=f"{auth.source_ref}:{request.operation}",
                )
                apply_mutation(
                    fresh.workspace,
                    request,
                    caller,
                    content=fresh.initial_snapshot
                    if request.operation == "publish_artifact"
                    else None,
                )
            except ProjectionRebuildError as error:
                warnings.append(
                    f"{request.operation} committed; projection rebuild reported an error: {error}"
                )
            except (WorkspaceError, OSError, ValueError) as error:
                status = _status(prepared.catalog, prepared.journal_path, journal)
                raise IncompleteActivationError(request.operation, status, str(error)) from error
        final = _prepared(prepared.catalog, prepared.journal_path, journal)
        if final.pending or len(final.completed) != 6:
            status = _status(prepared.catalog, prepared.journal_path, journal)
            raise IncompleteActivationError("core", status, "Core activation remains incomplete")
        try:
            plan = journal.activation_plan
            assert plan is not None
            entry = _ensure_entry(prepared.catalog, journal.designation, final.workspace, plan)
        except (EntryError, OSError, ValueError) as error:
            status = _status(prepared.catalog, prepared.journal_path, journal)
            raise IncompleteActivationError("catalog", status, str(error)) from error
        status = _status(prepared.catalog, prepared.journal_path, journal)
        if status.stage != "activated" or not status.first_work_openable:
            raise IncompleteActivationError("continuation", status, "First Work is not openable")
        return ActivationReceipt(
            creation=status, entry=entry, receipts=final.completed, warnings=tuple(warnings)
        )


def _cataloged(catalog: Path, designation: str, workspace: Path, plan: ActivationPlan) -> bool:
    try:
        entry = resolve_entry(catalog, designation)
        return _entry_matches(catalog, designation, entry, workspace, plan)
    except (EntryError, OSError, WorkspaceError, ProcessCreationError):
        return False


def _status(catalog: Path, path: Path, journal: _CreationJournal) -> CreationStatus:
    open_questions = tuple(
        row.question for row in journal.draft.clarifications if row.answer is None
    )
    stage: CreationStage
    if journal.research_request is None:
        stage = "draft"
    elif journal.research_return is None:
        stage = "research_waiting"
    elif journal.proposal is None:
        stage = "research_returned"
    elif journal.activation_plan is None:
        stage = "proposal_pending" if journal.activation_target is None else "activation_pending"
    else:
        stage = "activation_pending"
    completed_ops: tuple[str, ...] = ()
    pending_ops: tuple[str, ...] = ()
    workspace_id = process_id = work_id = None
    work_status = authority = None
    openable = cataloged = False
    if journal.activation_plan is not None and journal.proposal is not None:
        plan = journal.activation_plan
        selected = Path(plan.workspace_path)
        completed, pending, work = _core_progress(
            selected,
            plan,
            journal.proposal.definition,
            snapshot_bytes(ProcessSnapshot(definition=journal.proposal.definition)),
        )
        completed_ops = tuple(row.operation for row in plan.requests[: len(completed)])
        pending_ops = tuple(row.operation for row in pending)
        workspace_id, process_id, work_id = plan.workspace_id, plan.process_id, plan.work_id
        work_status, authority = work.status, work.authority_scope
        cataloged = len(completed) == 6 and _cataloged(catalog, journal.designation, selected, plan)
        openable = (
            len(completed) == 6
            and work.status == "ready"
            and work.authority_scope in ("work_metadata", "work_metadata_and_artifact")
        )
        if cataloged:
            stage = "activated"
    return CreationStatus(
        creation_id=journal.creation_id,
        designation=journal.designation,
        stage=stage,
        draft=journal.draft,
        draft_sha256=journal.draft_sha256,
        open_clarifications=open_questions,
        research_request=journal.research_request,
        research_return=journal.research_return,
        proposal=journal.proposal,
        capability_refusals=tuple(
            f"unsupported_capability:{capability}"
            for capability in journal.draft.declared_capabilities
            if capability not in SUPPORTED_CAPABILITIES
        ),
        activation_target=journal.activation_target,
        completed_operations=completed_ops,
        pending_operations=pending_ops,
        bootstrap_workspace_id=journal.bootstrap_workspace_id,
        workspace_id=workspace_id,
        process_id=process_id,
        first_work_id=work_id,
        current_work_status=work_status,
        current_authority_scope=authority,
        first_work_openable=openable,
        cataloged=cataloged,
    )


def inspect_process_creation(catalog: Path, designation: str) -> CreationStatus:
    path = _journal_path(catalog, designation)
    # Missing selection must not create a journal directory or lock on a read.
    # A concurrent creation after this observation is visible on an explicit retry.
    _load(path)
    try:
        with _creation_lock(path, create=False):
            return _status(catalog, path, _load(path))
    except OSError as error:
        raise ProcessCreationError(
            "journal_unavailable", "Saved creation lock is unavailable; inspection wrote nothing"
        ) from error


__all__ = [
    "MAX_DRAFT_BYTES",
    "MAX_PROPOSAL_BYTES",
    "MAX_RESEARCH_BYTES",
    "ActivationPreview",
    "ActivationReceipt",
    "Clarification",
    "CreationDraft",
    "CreationStatus",
    "IncompleteActivationError",
    "PreparedActivation",
    "ProcessActivationAuthorization",
    "ProcessCreationError",
    "ResearchRequest",
    "ResearchReturn",
    "SupportedProposal",
    "activation_preview_bytes",
    "authorize_process_activation",
    "create_research_request",
    "execute_process_activation",
    "inspect_process_creation",
    "parse_creation_draft",
    "parse_process_proposal",
    "parse_research_request",
    "prepare_process_activation",
    "receive_research_return",
    "save_creation_draft",
    "save_research_request",
    "save_supported_proposal",
]
