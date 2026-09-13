"""Reviewed, recoverable future-edition changes through existing Core Result."""

from __future__ import annotations

import base64
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
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from zaratustra.core import (
    ContextQuery,
    LocalAuthorization,
    MutationError,
    MutationReceipt,
    MutationRequest,
    PackReference,
    Process,
    ProjectionRebuildError,
    RecordsSnapshot,
    Work,
    open_work,
    prepare_authorization,
    read_history,
    read_records,
    submit_result,
)
from zaratustra.entry import CatalogEntry, EntryError, resolve_entry, source_path
from zaratustra.process_packs import (
    ConstructionError,
    DataValue,
    DefinitionTransition,
    PackError,
    PackRegistry,
    ProcessDefinition,
    ProcessSnapshot,
    ReadyWork,
    definition_sha256,
    edition_transition,
    evaluate_snapshot,
    propose_result,
    record_result,
    registration,
    snapshot_bytes,
)

MAX_CHANGE_BYTES = 1_048_576
MAX_JOURNAL_BYTES = 4_500_000
Digest = Annotated[str, Field(strict=True, pattern="^[0-9a-f]{64}$")]
ChangeStage = Literal["rejected", "review_pending", "pending", "planned", "applied"]


class ProcessChangeError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


class ChangeModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class DefinitionDifference(ChangeModel):
    path: str
    before: str | None
    after: str | None


class ProjectedWork(ChangeModel):
    definition_sha256: Digest
    node_id: str
    occurrence: int
    goal: str
    expected_result: str
    acceptance: tuple[str, ...]
    boundaries: tuple[str, ...]
    budget: str
    artifact_title: str


class ProcessChangePreview(ChangeModel):
    version: Literal[1] = 1
    change_id: UUID
    designation: str
    workspace_path: str
    workspace_id: UUID
    process_id: UUID
    source_work_id: UUID
    source_revision: int
    pack_reference: PackReference
    source_snapshot_sha256: Digest
    from_definition_sha256: Digest
    to_definition_sha256: Digest
    transition: DefinitionTransition
    differences: Annotated[tuple[DefinitionDifference, ...], Field(min_length=1)]
    current_work: Work
    current_work_effect: Literal[
        "unchanged; remains pinned to the original edition until its exact Result commits"
    ]
    next_work_without_change: ProjectedWork | None
    next_work_with_change: ProjectedWork | None
    committed_effect: Literal[
        "none; approval retains pending intent, Core submit_result is the future effect"
    ]


class ProcessChangeDecision(ChangeModel):
    change_id: UUID
    decision: Literal["approve", "reject"]
    preview_sha256: Digest
    channel: Literal["local-console", "local-chat"]
    actor: str
    source_ref: str
    confirmed_at: datetime


class RejectedChange(ChangeModel):
    change_id: UUID
    preview_sha256: Digest
    from_definition_sha256: Digest
    to_definition_sha256: Digest
    decision: ProcessChangeDecision


class ApprovedChange(ChangeModel):
    change_id: UUID
    preview: ProcessChangePreview
    preview_sha256: Digest
    decision: ProcessChangeDecision
    result_operation_id: UUID
    next_work_id: UUID
    next_artifact_id: UUID
    request: MutationRequest | None = None


class _ChangeJournal(ChangeModel):
    version: Literal[1] = 1
    designation: str
    workspace_id: UUID
    process_id: UUID
    rejected: tuple[RejectedChange, ...] = ()
    completed: tuple[ApprovedChange, ...] = ()
    pending_review: ProcessChangePreview | None = None
    approved: ApprovedChange | None = None


class ProcessChangeStatus(ChangeModel):
    version: Literal[1] = 1
    designation: str
    stage: ChangeStage
    workspace_id: UUID
    process_id: UUID
    source_work_id: UUID | None
    current_work_id: UUID
    pack_reference: PackReference
    rejected_changes: int
    applied_changes: int
    pending_preview: ProcessChangePreview | None
    approved_change_id: UUID | None
    from_definition_sha256: Digest | None
    to_definition_sha256: Digest | None
    planned_request: MutationRequest | None
    receipt: MutationReceipt | None
    intent_is_core_effect: Literal[False] = False


class ProcessChangeReceipt(ChangeModel):
    status: Literal["applied"] = "applied"
    change: ProcessChangeStatus
    receipt: MutationReceipt
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PreparedProcessChange:
    catalog: Path
    designation: str
    entry: CatalogEntry
    workspace: Path
    query: ContextQuery
    proposed_definition: ProcessDefinition
    change_id: UUID


@dataclass(frozen=True)
class ReviewedProcessChange:
    prepared: PreparedProcessChange
    caller: LocalAuthorization
    snapshot: ProcessSnapshot
    transition: DefinitionTransition
    preview: ProcessChangePreview
    preview_sha256: str


@dataclass(frozen=True)
class PreparedChangeContinuation:
    catalog: Path
    designation: str
    workspace: Path
    request: MutationRequest


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON key: {key}")
        value[key] = item
    return value


def parse_process_change(content: bytes) -> ProcessDefinition:
    if not content or len(content) > MAX_CHANGE_BYTES:
        raise ProcessChangeError(
            "invalid_change", f"Definition must be 1..{MAX_CHANGE_BYTES} bytes"
        )
    try:
        json.loads(content.decode("utf-8"), object_pairs_hook=_duplicates)
        return ProcessDefinition.model_validate_json(content)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError) as error:
        raise ProcessChangeError(
            "invalid_change", "Definition must be strict UTF-8 JSON"
        ) from error


def _wire(value: BaseModel, *, readable: bool = False) -> bytes:
    return (
        json.dumps(
            value.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=not readable,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def process_change_preview_bytes(review: ReviewedProcessChange) -> bytes:
    return _wire(review.preview, readable=True)


def _journal_path(catalog: Path, designation: str) -> Path:
    selected = catalog.expanduser().resolve()
    key = hashlib.sha256(designation.strip().casefold().encode("utf-8")).hexdigest()
    return selected.parent / f"{selected.name}.process-changes" / f"{key}.json"


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
def _change_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    with lock.open("a+b") as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"0")
            stream.flush()
        _acquire_file_lock(stream)
        try:
            yield
        finally:
            _release_file_lock(stream)


def _save(path: Path, journal: _ChangeJournal) -> None:
    content = _wire(journal)
    if len(content) > MAX_JOURNAL_BYTES:
        raise ProcessChangeError("journal_too_large", "Process change journal exceeds its limit")
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
        raise ProcessChangeError("journal_unavailable", "Change journal cannot be saved") from error


def _load(path: Path) -> _ChangeJournal:
    try:
        content = path.read_bytes()
        if not content or len(content) > MAX_JOURNAL_BYTES:
            raise ValueError("Invalid journal size")
        json.loads(content.decode("utf-8"), object_pairs_hook=_duplicates)
        journal = _ChangeJournal.model_validate_json(content)
    except FileNotFoundError as error:
        raise ProcessChangeError(
            "change_not_found", "No saved change for this designation"
        ) from error
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
    ) as error:
        raise ProcessChangeError(
            "journal_invalid", "Change journal is unavailable or invalid"
        ) from error
    _validate_journal(journal)
    return journal


def _validate_journal(journal: _ChangeJournal) -> None:
    for rejected in journal.rejected:
        decision = rejected.decision
        if (
            decision.change_id != rejected.change_id
            or decision.decision != "reject"
            or decision.preview_sha256 != rejected.preview_sha256
        ):
            raise ProcessChangeError("journal_invalid", "Rejected change binding differs")
    approved_rows = (*journal.completed, *((journal.approved,) if journal.approved else ()))
    if len({row.change_id for row in approved_rows}) != len(approved_rows):
        raise ProcessChangeError("journal_invalid", "Approved change identities repeat")
    for approved in approved_rows:
        if (
            approved.change_id != approved.preview.change_id
            or approved.decision.change_id != approved.change_id
            or approved.decision.decision != "approve"
            or approved.preview_sha256
            != hashlib.sha256(_wire(approved.preview, readable=True)).hexdigest()
            or approved.decision.preview_sha256 != approved.preview_sha256
            or approved.preview.workspace_id != journal.workspace_id
            or approved.preview.process_id != journal.process_id
        ):
            raise ProcessChangeError("journal_invalid", "Approved change binding differs")
        request = approved.request
        if request is not None and (
            request.operation != "submit_result"
            or request.operation_id != approved.result_operation_id
            or request.work_id != approved.preview.source_work_id
            or request.submission is None
            or request.submission.next_work.work_id != approved.next_work_id
            or request.submission.next_work.artifact_id != approved.next_artifact_id
        ):
            raise ProcessChangeError("journal_invalid", "Planned Result request differs")
        _validate_saved_preview(approved.preview)
    if journal.pending_review is not None and (
        journal.pending_review.workspace_id != journal.workspace_id
        or journal.pending_review.process_id != journal.process_id
    ):
        raise ProcessChangeError("journal_invalid", "Pending review names another Process")
    if journal.pending_review is not None:
        _validate_saved_preview(journal.pending_review)


def _validate_saved_preview(preview: ProcessChangePreview) -> None:
    if preview.transition.from_definition.nodes == preview.transition.to_definition.nodes:
        raise ProcessChangeError(
            "saved_change_unsupported",
            "Saved edition-only intent is not a process change",
        )
    if preview.next_work_with_change is None:
        raise ProcessChangeError(
            "saved_change_unsupported",
            "Saved intent has no supported future Work effect",
        )


def _process(snapshot: RecordsSnapshot, process_id: UUID) -> Process:
    rows = [row for row in snapshot.records if isinstance(row, Process) and row.id == process_id]
    if len(rows) != 1:
        raise ProcessChangeError("wrong_target", "Catalog Process is not in this workspace")
    return rows[0]


def _lineage_from_history(
    snapshot: RecordsSnapshot, entry: CatalogEntry, workspace: Path
) -> tuple[Work, tuple[UUID, ...]]:
    works = {
        row.id: row
        for row in snapshot.records
        if isinstance(row, Work) and row.process_id == entry.process_id
    }
    if entry.work_id not in works:
        raise ProcessChangeError("wrong_target", "Catalog initial Work is unavailable")
    outgoing: dict[UUID, Work] = {}
    for event in read_history(workspace).events:
        if event.next_work is None:
            continue
        if event.before.id in outgoing:
            raise ProcessChangeError("lineage_invalid", "A Work has more than one continuation")
        outgoing[event.before.id] = event.next_work
    identities: list[UUID] = []
    current = entry.work_id
    while True:
        if current in identities or current not in works:
            raise ProcessChangeError("lineage_invalid", "Committed Work lineage is broken")
        identities.append(current)
        following = outgoing.get(current)
        if following is None:
            break
        current_record = works.get(following.id)
        if current_record is None or (
            current_record.id,
            current_record.process_id,
            current_record.created_at,
            current_record.pack_binding,
        ) != (
            following.id,
            following.process_id,
            following.created_at,
            following.pack_binding,
        ):
            raise ProcessChangeError(
                "lineage_invalid", "Continuation identity differs from committed history"
            )
        current = following.id
    if set(identities) != set(works):
        raise ProcessChangeError("lineage_invalid", "Process contains an unlinked Work")
    return works[current], tuple(identities)


def _target(
    catalog: Path, designation: str
) -> tuple[CatalogEntry, Path, RecordsSnapshot, Work, Process]:
    try:
        entry = resolve_entry(catalog, designation)
        workspace = source_path(catalog, entry)
        snapshot = read_records(workspace)
    except EntryError as error:
        raise ProcessChangeError(error.code, str(error)) from error
    process = _process(snapshot, entry.process_id)
    if snapshot.workspace_id != entry.workspace_id:
        raise ProcessChangeError("wrong_target", "Catalog workspace identity changed")
    current, _chain = _lineage_from_history(snapshot, entry, workspace)
    if current.status != "ready":
        raise ProcessChangeError("terminal_work", "Actual current Work is not ready")
    if current.pack_binding is None or current.pack_binding != process.pack_binding:
        raise ProcessChangeError("binding_mismatch", "Current Work and Process binding differ")
    return entry, workspace, snapshot, current, process


def prepare_process_change(
    catalog: Path, designation: str, proposal_content: bytes
) -> PreparedProcessChange:
    proposed = parse_process_change(proposal_content)
    entry, workspace, snapshot, current, _process_record = _target(catalog, designation)
    return PreparedProcessChange(
        catalog=catalog.expanduser().resolve(),
        designation=entry.designation,
        entry=entry,
        workspace=workspace,
        query=ContextQuery(
            workspace_id=snapshot.workspace_id,
            work_id=current.id,
            process_id=current.process_id,
            expected_revision=snapshot.state_revision,
            max_bytes=MAX_CHANGE_BYTES,
        ),
        proposed_definition=proposed,
        change_id=uuid4(),
    )


def process_change_review_query(catalog: Path, designation: str) -> ContextQuery:
    """Return the exact saved review scope so another trusted chat can confirm it."""
    entry, workspace, snapshot, current, process = _target(catalog, designation)
    del workspace
    journal = _load(_journal_path(catalog, entry.designation))
    preview = journal.pending_review
    if preview is None:
        raise ProcessChangeError("review_not_found", "No reviewed change awaits a decision")
    if (
        preview.workspace_id != snapshot.workspace_id
        or preview.process_id != process.id
        or preview.source_work_id != current.id
        or preview.source_revision != snapshot.state_revision
    ):
        raise ProcessChangeError("stale_change", "Saved review no longer names current state")
    return ContextQuery(
        workspace_id=preview.workspace_id,
        work_id=preview.source_work_id,
        process_id=preview.process_id,
        expected_revision=preview.source_revision,
        max_bytes=MAX_CHANGE_BYTES,
    )


def resume_process_change_review(
    catalog: Path, designation: str, caller: LocalAuthorization | None
) -> ReviewedProcessChange:
    entry, workspace, _snapshot, _current, _process_record = _target(catalog, designation)
    journal = _load(_journal_path(catalog, entry.designation))
    preview = journal.pending_review
    if preview is None:
        raise ProcessChangeError("review_not_found", "No reviewed change awaits a decision")
    prepared = PreparedProcessChange(
        catalog=catalog.expanduser().resolve(),
        designation=entry.designation,
        entry=entry,
        workspace=workspace,
        query=process_change_review_query(catalog, designation),
        proposed_definition=preview.transition.to_definition,
        change_id=preview.change_id,
    )
    resumed = review_process_change(prepared, caller)
    if process_change_preview_bytes(resumed) != _wire(preview, readable=True):
        raise ProcessChangeError("stale_change", "Rebuilt review differs from saved preview")
    return resumed


def _context_sources(output: bytes) -> dict[str, dict[str, Any]]:
    try:
        package = json.loads(output)
        return {row["locator"]: row["data"] for row in package["context"]["sources"]}
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ProcessChangeError("context_invalid", "Authorized Core context is invalid") from error


def _basis_snapshot(
    work: Work,
    sources: dict[str, dict[str, Any]],
    applied: tuple[ProcessChangePreview, ...],
) -> ProcessSnapshot:
    prefix = "basis-snapshot-sha256:"
    values = [row[len(prefix) :] for row in work.executor_requirements if row.startswith(prefix)]
    if len(values) != 1:
        raise ProcessChangeError("basis_missing", "Current Work has no exact basis snapshot")
    expected = values[0]
    candidates: list[tuple[bytes, ProcessSnapshot]] = []
    for locator, value in sources.items():
        if not locator.startswith("artifact-version:"):
            continue
        descriptor = value.get("descriptor", {})
        digest = descriptor.get("sha256")
        if not isinstance(digest, str):
            continue
        try:
            content = base64.b64decode(value["content_base64"], validate=True)
        except (KeyError, TypeError, ValueError) as error:
            raise ProcessChangeError(
                "basis_invalid", "Basis content is not exact base64"
            ) from error
        try:
            snapshot = ProcessSnapshot.model_validate_json(content)
        except ValidationError:
            continue
        if snapshot_bytes(snapshot) == content and hashlib.sha256(content).hexdigest() == digest:
            candidates.append((content, snapshot))
    expanded = list(candidates)
    for preview in applied:
        transition = preview.transition
        for _content, candidate in tuple(expanded):
            if candidate.definition != transition.from_definition or not candidate.results:
                continue
            before = candidate.model_copy(update=dict(results=candidate.results[:-1]))
            if hashlib.sha256(snapshot_bytes(before)).hexdigest() != (
                transition.from_snapshot_sha256
            ):
                continue
            try:
                checked = edition_transition(preview.current_work, before, transition.to_definition)
                if checked != transition:
                    continue
                projected = ProcessSnapshot(
                    definition=transition.to_definition, results=candidate.results
                )
                evaluate_snapshot(projected)
            except (ConstructionError, ValidationError):
                continue
            wire = snapshot_bytes(projected)
            if all(existing != wire for existing, _row in expanded):
                expanded.append((wire, projected))
    matching = [
        snapshot
        for content, snapshot in expanded
        if hashlib.sha256(content).hexdigest() == expected
    ]
    if len(matching) != 1:
        raise ProcessChangeError("basis_missing", "Exact current effective basis is unavailable")
    snapshot = matching[0]
    definition_requirements = [
        row.removeprefix("definition-sha256:")
        for row in work.executor_requirements
        if row.startswith("definition-sha256:")
    ]
    if definition_requirements != [definition_sha256(snapshot.definition)]:
        raise ProcessChangeError("basis_invalid", "Work definition requirement differs")
    return snapshot


def _json_value(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _differences(before: Any, after: Any, path: str = "definition") -> list[DefinitionDifference]:
    if isinstance(before, dict) and isinstance(after, dict):
        rows: list[DefinitionDifference] = []
        for key in sorted(set(before) | set(after)):
            child = f"{path}.{key}"
            if key not in before:
                rows.append(
                    DefinitionDifference(path=child, before=None, after=_json_value(after[key]))
                )
            elif key not in after:
                rows.append(
                    DefinitionDifference(path=child, before=_json_value(before[key]), after=None)
                )
            else:
                rows.extend(_differences(before[key], after[key], child))
        return rows
    if isinstance(before, list) and isinstance(after, list):
        rows = []
        for index in range(max(len(before), len(after))):
            child = f"{path}[{index}]"
            if index >= len(before):
                rows.append(
                    DefinitionDifference(path=child, before=None, after=_json_value(after[index]))
                )
            elif index >= len(after):
                rows.append(
                    DefinitionDifference(path=child, before=_json_value(before[index]), after=None)
                )
            else:
                rows.extend(_differences(before[index], after[index], child))
        return rows
    if before == after:
        return []
    return [DefinitionDifference(path=path, before=_json_value(before), after=_json_value(after))]


def _projected(definition: ProcessDefinition, ready: ReadyWork | None) -> ProjectedWork | None:
    if ready is None:
        return None
    node = ready.node
    return ProjectedWork(
        definition_sha256=definition_sha256(definition),
        node_id=node.node_id,
        occurrence=ready.occurrence,
        goal=node.goal,
        expected_result=node.expected_result,
        acceptance=node.acceptance,
        boundaries=node.boundaries,
        budget=node.budget,
        artifact_title=node.artifact_title,
    )


def _future_impact(
    snapshot: ProcessSnapshot, current: ReadyWork, proposed: ProcessDefinition
) -> tuple[ProjectedWork | None, ProjectedWork | None]:
    placeholder = tuple(
        DataValue(key=key, value="Pending exact accepted value; content not assumed by preview")
        for key in current.node.output_keys
    )
    completed = record_result(snapshot, placeholder)
    previous = evaluate_snapshot(completed).selected
    changed_snapshot = ProcessSnapshot(definition=proposed, results=completed.results)
    changed = evaluate_snapshot(changed_snapshot).selected
    return _projected(snapshot.definition, previous), _projected(proposed, changed)


def _new_journal(prepared: PreparedProcessChange) -> _ChangeJournal:
    return _ChangeJournal(
        designation=prepared.designation,
        workspace_id=prepared.query.workspace_id,
        process_id=prepared.query.process_id,
    )


def _applied_previews(
    catalog: Path, designation: str, workspace: Path
) -> tuple[ProcessChangePreview, ...]:
    try:
        journal = _load(_journal_path(catalog, designation))
    except ProcessChangeError as error:
        if error.code == "change_not_found":
            return ()
        raise
    previews: list[ProcessChangePreview] = []
    for row in journal.completed:
        if _applied_receipt(workspace, row) is None:
            raise ProcessChangeError("journal_invalid", "Completed change has no Core effect")
        previews.append(row.preview)
    if journal.approved is not None and _applied_receipt(workspace, journal.approved) is not None:
        previews.append(journal.approved.preview)
    return tuple(previews)


def review_process_change(
    prepared: PreparedProcessChange, caller: LocalAuthorization | None
) -> ReviewedProcessChange:
    if caller is None:
        raise ProcessChangeError("permission_denied", "Current Work context was not authorized")
    try:
        output = open_work(prepared.workspace, prepared.query, caller).output
    except MutationError as error:
        raise ProcessChangeError(error.code, str(error).partition(": ")[2]) from error
    sources = _context_sources(output)
    try:
        work = Work.model_validate(sources[f"work:{prepared.query.work_id}"])
    except (KeyError, ValidationError) as error:
        raise ProcessChangeError(
            "context_invalid", "Context lacks the exact current Work"
        ) from error
    snapshot = _basis_snapshot(
        work,
        sources,
        _applied_previews(prepared.catalog, prepared.designation, prepared.workspace),
    )
    current = evaluate_snapshot(snapshot).selected
    if current is None:
        raise ProcessChangeError("work_mismatch", "Current basis has no selected Work")
    try:
        transition = edition_transition(work, snapshot, prepared.proposed_definition)
    except ConstructionError as error:
        raise ProcessChangeError(error.code, str(error).partition(": ")[2]) from error
    except ValidationError as error:
        raise ProcessChangeError(
            "invalid_change", "Proposed edition identity, sources or sequence is invalid"
        ) from error
    differences = tuple(
        _differences(
            snapshot.definition.model_dump(mode="json"),
            prepared.proposed_definition.model_dump(mode="json"),
        )
    )
    if not differences:
        raise ProcessChangeError("no_change", "Proposed edition contains no definition change")
    without, with_change = _future_impact(snapshot, current, prepared.proposed_definition)
    try:
        process = Process.model_validate(sources[f"process:{prepared.query.process_id}"])
    except (KeyError, ValidationError) as error:
        raise ProcessChangeError("context_invalid", "Context lacks the exact Process") from error
    assert process.pack_binding is not None
    preview = ProcessChangePreview(
        change_id=prepared.change_id,
        designation=prepared.designation,
        workspace_path=prepared.workspace.as_posix(),
        workspace_id=prepared.query.workspace_id,
        process_id=prepared.query.process_id,
        source_work_id=work.id,
        source_revision=prepared.query.expected_revision,
        pack_reference=process.pack_binding,
        source_snapshot_sha256=hashlib.sha256(snapshot_bytes(snapshot)).hexdigest(),
        from_definition_sha256=definition_sha256(snapshot.definition),
        to_definition_sha256=definition_sha256(prepared.proposed_definition),
        transition=transition,
        differences=differences,
        current_work=work,
        current_work_effect=(
            "unchanged; remains pinned to the original edition until its exact Result commits"
        ),
        next_work_without_change=without,
        next_work_with_change=with_change,
        committed_effect=(
            "none; approval retains pending intent, Core submit_result is the future effect"
        ),
    )
    digest = hashlib.sha256(_wire(preview, readable=True)).hexdigest()
    reviewed = ReviewedProcessChange(prepared, caller, snapshot, transition, preview, digest)
    path = _journal_path(prepared.catalog, prepared.designation)
    with _change_lock(path):
        try:
            journal = _load(path)
        except ProcessChangeError as error:
            if error.code != "change_not_found":
                raise
            journal = _new_journal(prepared)
        if (
            journal.designation != prepared.designation
            or journal.workspace_id != preview.workspace_id
            or journal.process_id != preview.process_id
        ):
            raise ProcessChangeError("wrong_target", "Saved change names another Process")
        if (
            journal.approved is not None
            and _applied_receipt(prepared.workspace, journal.approved) is None
        ):
            raise ProcessChangeError("change_pending", "Another approved change is pending")
        if journal.pending_review is None:
            journal = journal.model_copy(update=dict(pending_review=preview))
            _validate_journal(journal)
            _save(path, journal)
        elif journal.pending_review != preview:
            raise ProcessChangeError("review_pending", "Another reviewed change awaits decision")
    return reviewed


def authorize_process_change(
    review: ReviewedProcessChange,
    *,
    decision: Literal["approve", "reject"],
    channel: Literal["local-console", "local-chat"],
    actor: str,
    source_ref: str,
) -> ProcessChangeDecision:
    if hashlib.sha256(process_change_preview_bytes(review)).hexdigest() != review.preview_sha256:
        raise ProcessChangeError("permission_denied", "Changed process change preview")
    if not actor.strip() or not source_ref.strip():
        raise ProcessChangeError("permission_denied", "Decision identity is incomplete")
    return ProcessChangeDecision(
        change_id=review.preview.change_id,
        decision=decision,
        preview_sha256=review.preview_sha256,
        channel=channel,
        actor=actor,
        source_ref=source_ref,
        confirmed_at=datetime.now(UTC),
    )


def decide_process_change(
    review: ReviewedProcessChange, decision: ProcessChangeDecision | None
) -> ProcessChangeStatus:
    if (
        decision is None
        or decision.change_id != review.preview.change_id
        or decision.preview_sha256 != review.preview_sha256
    ):
        raise ProcessChangeError(
            "permission_denied", "Exact current change preview was not decided"
        )
    try:
        fresh = review_process_change(review.prepared, review.caller)
    except ProcessChangeError as error:
        if error.code in ("conflict", "dependency_changed", "permission_denied"):
            raise ProcessChangeError("stale_change", "Current Work changed after review") from error
        raise
    if process_change_preview_bytes(fresh) != process_change_preview_bytes(review):
        raise ProcessChangeError("stale_change", "Process change preview changed after review")
    path = _journal_path(review.prepared.catalog, review.prepared.designation)
    with _change_lock(path):
        try:
            journal = _load(path)
        except ProcessChangeError as error:
            if error.code != "change_not_found":
                raise
            journal = _new_journal(review.prepared)
        if (
            journal.designation != review.prepared.designation
            or journal.workspace_id != review.preview.workspace_id
            or journal.process_id != review.preview.process_id
        ):
            raise ProcessChangeError("wrong_target", "Saved change names another Process")
        if journal.pending_review != review.preview:
            raise ProcessChangeError("stale_change", "Saved pending review changed")
        if decision.decision == "reject":
            rejected = RejectedChange(
                change_id=review.preview.change_id,
                preview_sha256=review.preview_sha256,
                from_definition_sha256=review.preview.from_definition_sha256,
                to_definition_sha256=review.preview.to_definition_sha256,
                decision=decision,
            )
            if rejected not in journal.rejected:
                journal = journal.model_copy(
                    update=dict(rejected=(*journal.rejected, rejected), pending_review=None)
                )
                _save(path, journal)
        else:
            candidate = ApprovedChange(
                change_id=review.preview.change_id,
                preview=review.preview,
                preview_sha256=review.preview_sha256,
                decision=decision,
                result_operation_id=uuid4(),
                next_work_id=uuid4(),
                next_artifact_id=uuid4(),
            )
            completed = journal.completed
            if journal.approved is not None:
                if _applied_receipt(review.prepared.workspace, journal.approved) is None:
                    raise ProcessChangeError("change_pending", "Another approved change is pending")
                completed = (*completed, journal.approved)
            journal = journal.model_copy(
                update=dict(completed=completed, pending_review=None, approved=candidate)
            )
            _validate_journal(journal)
            _save(path, journal)
    return inspect_process_change(review.prepared.catalog, review.prepared.designation)


def _applied_receipt(workspace: Path, approved: ApprovedChange) -> MutationReceipt | None:
    matches = [
        event
        for event in read_history(workspace).events
        if event.request.operation_id == approved.result_operation_id
    ]
    if not matches:
        return None
    if len(matches) != 1 or approved.request is None or matches[0].request != approved.request:
        raise ProcessChangeError("change_collision", "Core operation differs from saved change")
    event = matches[0]
    if (
        event.next_work is None
        or event.next_work.id != approved.next_work_id
        or event.next_artifact is None
        or event.next_artifact.id != approved.next_artifact_id
    ):
        raise ProcessChangeError("change_collision", "Core continuation differs from saved change")
    for receipt in read_history(workspace).receipts:
        if receipt.operation_id == approved.result_operation_id:
            return receipt
    raise ProcessChangeError("change_collision", "Committed change receipt is unavailable")


def inspect_process_change(catalog: Path, designation: str) -> ProcessChangeStatus:
    entry, workspace, snapshot, current, process = _target(catalog, designation)
    journal = _load(_journal_path(catalog, entry.designation))
    if (journal.workspace_id, journal.process_id) != (snapshot.workspace_id, process.id):
        raise ProcessChangeError("wrong_target", "Saved change no longer names this Process")
    assert process.pack_binding is not None
    approved = journal.approved
    completed_receipts = tuple(_applied_receipt(workspace, row) for row in journal.completed)
    if any(row is None for row in completed_receipts):
        raise ProcessChangeError("journal_invalid", "Completed change has no Core effect")
    approved_receipt = _applied_receipt(workspace, approved) if approved is not None else None
    applied_count = len(journal.completed) + (1 if approved_receipt is not None else 0)
    pending_preview = journal.pending_review
    if pending_preview is not None:
        return ProcessChangeStatus(
            designation=entry.designation,
            stage="review_pending",
            workspace_id=snapshot.workspace_id,
            process_id=process.id,
            source_work_id=pending_preview.source_work_id,
            current_work_id=current.id,
            pack_reference=process.pack_binding,
            rejected_changes=len(journal.rejected),
            applied_changes=applied_count,
            pending_preview=pending_preview,
            approved_change_id=approved.change_id if approved is not None else None,
            from_definition_sha256=pending_preview.from_definition_sha256,
            to_definition_sha256=pending_preview.to_definition_sha256,
            planned_request=None,
            receipt=None,
        )
    if approved is None:
        return ProcessChangeStatus(
            designation=entry.designation,
            stage="rejected",
            workspace_id=snapshot.workspace_id,
            process_id=process.id,
            source_work_id=None,
            current_work_id=current.id,
            pack_reference=process.pack_binding,
            rejected_changes=len(journal.rejected),
            applied_changes=applied_count,
            pending_preview=None,
            approved_change_id=None,
            from_definition_sha256=None,
            to_definition_sha256=None,
            planned_request=None,
            receipt=None,
        )
    receipt = approved_receipt
    source = next(
        row
        for row in snapshot.records
        if isinstance(row, Work) and row.id == approved.preview.source_work_id
    )
    if receipt is None and source.status == "done":
        raise ProcessChangeError("change_diverged", "Source Work completed outside saved change")
    stage: ChangeStage = (
        "applied"
        if receipt is not None
        else ("planned" if approved.request is not None else "pending")
    )
    return ProcessChangeStatus(
        designation=entry.designation,
        stage=stage,
        workspace_id=snapshot.workspace_id,
        process_id=process.id,
        source_work_id=source.id,
        current_work_id=current.id,
        pack_reference=process.pack_binding,
        rejected_changes=len(journal.rejected),
        applied_changes=applied_count,
        pending_preview=None,
        approved_change_id=approved.change_id,
        from_definition_sha256=approved.preview.from_definition_sha256,
        to_definition_sha256=approved.preview.to_definition_sha256,
        planned_request=approved.request,
        receipt=receipt,
    )


def process_change_continuation_query(catalog: Path, designation: str) -> ContextQuery:
    """Expose the exact current read scope; the query itself grants no authority."""
    entry, workspace, snapshot, current, process = _target(catalog, designation)
    journal = _load(_journal_path(catalog, entry.designation))
    approved = journal.approved
    if approved is None:
        raise ProcessChangeError("change_not_approved", "No approved change is pending")
    if _applied_receipt(workspace, approved) is not None:
        raise ProcessChangeError("change_applied", "Approved change already has a Core effect")
    if current.id != approved.preview.source_work_id:
        raise ProcessChangeError("change_diverged", "Saved source is not actual current Work")
    return ContextQuery(
        workspace_id=snapshot.workspace_id,
        work_id=current.id,
        process_id=process.id,
        expected_revision=snapshot.state_revision,
        max_bytes=MAX_CHANGE_BYTES,
    )


def prepare_process_change_continuation(
    catalog: Path, designation: str, caller: LocalAuthorization | None
) -> PreparedChangeContinuation:
    entry, workspace, snapshot, current, process = _target(catalog, designation)
    path = _journal_path(catalog, entry.designation)
    with _change_lock(path):
        journal = _load(path)
        approved = journal.approved
        if approved is None:
            raise ProcessChangeError("change_not_approved", "No approved change is pending")
        receipt = _applied_receipt(workspace, approved)
        if receipt is not None:
            assert approved.request is not None
            return PreparedChangeContinuation(
                catalog.expanduser().resolve(), entry.designation, workspace, approved.request
            )
        if current.id != approved.preview.source_work_id:
            raise ProcessChangeError("change_diverged", "Saved source is not actual current Work")
        query = ContextQuery(
            workspace_id=snapshot.workspace_id,
            work_id=current.id,
            process_id=process.id,
            expected_revision=snapshot.state_revision,
            max_bytes=MAX_CHANGE_BYTES,
        )
        if caller is None:
            raise ProcessChangeError(
                "permission_denied", "Current Result context was not authorized"
            )
        registry = PackRegistry(
            (
                registration(
                    approved.preview.pack_reference,
                    approved.preview.transition.from_definition,
                    approved.preview.transition,
                ),
            )
        )
        try:
            request = propose_result(
                workspace,
                query,
                caller,
                registry,
                operation_id=approved.result_operation_id,
                next_work_id=approved.next_work_id,
                next_artifact_id=approved.next_artifact_id,
            )
        except (MutationError, ConstructionError, PackError) as error:
            code = getattr(error, "code", "change_not_ready")
            raise ProcessChangeError(code, str(error).partition(": ")[2] or str(error)) from error
        if approved.request is None:
            approved = approved.model_copy(update=dict(request=request))
            journal = journal.model_copy(update=dict(approved=approved))
            _validate_journal(journal)
            _save(path, journal)
        elif approved.request != request:
            raise ProcessChangeError("stale_change", "Saved Result request is no longer current")
        return PreparedChangeContinuation(
            catalog.expanduser().resolve(), entry.designation, workspace, request
        )


def execute_process_change_continuation(
    prepared: PreparedChangeContinuation, caller: LocalAuthorization | None
) -> ProcessChangeReceipt:
    path = _journal_path(prepared.catalog, prepared.designation)
    with _change_lock(path):
        journal = _load(path)
        approved = journal.approved
        if approved is None or approved.request != prepared.request:
            raise ProcessChangeError("stale_change", "Saved Result request changed")
        prompt = prepare_authorization(prepared.workspace, prepared.request)
        if (
            caller is None
            or caller.confirmation.workspace_path != prompt.workspace_path
            or caller.confirmation.request_sha256 != prompt.request_sha256
        ):
            raise ProcessChangeError("permission_denied", "Exact Core Result was not authorized")
        receipt = _applied_receipt(prepared.workspace, approved)
        warnings: list[str] = []
        if receipt is None:
            try:
                receipt = submit_result(prepared.workspace, prepared.request, caller)
            except ProjectionRebuildError as error:
                receipt = error.receipt
                warnings.append(f"Result committed; projection rebuild reported: {error}")
            except MutationError as error:
                raise ProcessChangeError(error.code, str(error).partition(": ")[2]) from error
        status = inspect_process_change(prepared.catalog, prepared.designation)
        if status.stage != "applied" or status.receipt != receipt:
            raise ProcessChangeError("change_incomplete", "Committed Result was not reconciled")
        return ProcessChangeReceipt(change=status, receipt=receipt, warnings=tuple(warnings))


__all__ = [
    "MAX_CHANGE_BYTES",
    "ApprovedChange",
    "DefinitionDifference",
    "PreparedChangeContinuation",
    "PreparedProcessChange",
    "ProcessChangeDecision",
    "ProcessChangeError",
    "ProcessChangePreview",
    "ProcessChangeReceipt",
    "ProcessChangeStatus",
    "ProjectedWork",
    "RejectedChange",
    "ReviewedProcessChange",
    "authorize_process_change",
    "decide_process_change",
    "execute_process_change_continuation",
    "inspect_process_change",
    "parse_process_change",
    "prepare_process_change",
    "prepare_process_change_continuation",
    "process_change_continuation_query",
    "process_change_preview_bytes",
    "process_change_review_query",
    "resume_process_change_review",
    "review_process_change",
]
