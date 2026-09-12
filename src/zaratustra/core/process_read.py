"""Exact Process metadata and optional selected context, with one consistency boundary."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from .artifacts import read_versions
from .context import ContextPackage, _compile
from .context import _collect as collect_context
from .mutations import LocalAuthorization, MutationError, _caller, _history, _work
from .protocol import ArtifactReference, ContextQuery, NextWork, ProcessQuery
from .records import Process, RecordModel, Work, _read_records
from .results import incoming_events
from .workspace import WorkspaceError, WorkspaceInfo, workspace_connection


class ResultHeader(RecordModel):
    id: UUID
    work_id: UUID
    state_revision: int


class ProcessMetadata(RecordModel):
    query: ProcessQuery
    process: Process
    works: tuple[Work, ...]
    results: tuple[ResultHeader, ...]
    context_references: tuple[ArtifactReference, ...]


@dataclass(frozen=True)
class ProcessView:
    metadata: ProcessMetadata
    context: ContextPackage | None
    context_code: str


class AcceptedBasis(RecordModel):
    """One explicitly accepted Handoff, without opening referenced bytes."""

    acceptance_id: UUID
    accepted_revision: int
    source_revision: int
    result: ArtifactReference
    basis: tuple[ArtifactReference, ...]


class InheritedResultBasis(RecordModel):
    """Exact immutable grounds carried by a committed incoming Result."""

    result_id: UUID
    source_work_id: UUID
    accepted_revision: int
    references: tuple[ArtifactReference, ...]


class SavedContinuation(RecordModel):
    """The accepted next-Work value; not its current authority or state."""

    result_id: UUID
    accepted_revision: int
    references: tuple[ArtifactReference, ...]
    next_work: NextWork


class BasicProcessDocument(RecordModel):
    version: Literal[1] = 1
    workspace_id: UUID
    state_revision: int
    process: Process
    selected_work: Work
    accepted_basis: tuple[AcceptedBasis, ...]
    inherited_result_basis: tuple[InheritedResultBasis, ...]
    continuation_state: Literal["selected_work_ready", "saved_result", "cancelled", "draft"]
    saved_continuation: SavedContinuation | None
    content_state: Literal["not_requested"] = "not_requested"
    scope: Literal["selected_work_metadata_and_exact_saved_basis_only"] = (
        "selected_work_metadata_and_exact_saved_basis_only"
    )
    freshness: Literal["one_locked_revision; reopen_after_change"] = (
        "one_locked_revision; reopen_after_change"
    )


@dataclass(frozen=True)
class BasicProcessPackage:
    """Complete canonical basic-reader bytes, bounded by the exact ProcessQuery."""

    output: bytes

    @property
    def output_sha256(self) -> str:
        return hashlib.sha256(self.output).hexdigest()


def _wire(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + chr(10)
    ).encode("utf-8")


def _basic_document(
    connection: sqlite3.Connection,
    info: WorkspaceInfo,
    query: ProcessQuery,
    caller: LocalAuthorization | None,
) -> BasicProcessDocument:
    selected_id = query.selected_work_id
    if selected_id is None or query.visible_work_ids != (selected_id,):
        raise MutationError("scope", "Basic read requires exactly one selected visible Work")
    metadata, _ = _metadata(connection, info, query, caller)
    selected = metadata.works[0]
    snapshot = _read_records(connection, info.workspace_id)
    history = _history(connection, snapshot, artifacts_enabled=True)
    accepted = tuple(
        AcceptedBasis(
            acceptance_id=handoff.handoff_id,
            accepted_revision=event.state_revision,
            source_revision=handoff.source_revision,
            result=handoff.result,
            basis=handoff.basis,
        )
        for event in history.events
        if event.request.work_id == selected_id and (handoff := event.request.handoff) is not None
    )
    try:
        incoming = incoming_events(history.events, selected_id)
    except ValueError as error:
        raise WorkspaceError(str(error)) from error
    inherited = tuple(
        InheritedResultBasis(
            result_id=event.request.operation_id,
            source_work_id=event.before.id,
            accepted_revision=event.state_revision,
            references=event.result_references,
        )
        for event in incoming
    )
    completed = tuple(
        event
        for event in history.events
        if event.before.id == selected_id and event.request.submission is not None
    )
    continuation: SavedContinuation | None = None
    continuation_state: Literal["selected_work_ready", "saved_result", "cancelled", "draft"]
    if selected.status == "done":
        submission = completed[0].request.submission if len(completed) == 1 else None
        if (
            len(completed) != 1
            or selected.completion_id != completed[0].request.operation_id
            or submission is None
        ):
            raise WorkspaceError("Completed Work does not match one saved Result")
        event = completed[0]
        continuation = SavedContinuation(
            result_id=event.request.operation_id,
            accepted_revision=event.state_revision,
            references=event.result_references,
            next_work=submission.next_work,
        )
        continuation_state = "saved_result"
    elif completed:
        raise WorkspaceError("Nonterminal Work has a saved Result")
    else:
        if selected.status == "ready":
            continuation_state = "selected_work_ready"
        elif selected.status == "cancelled":
            continuation_state = "cancelled"
        else:
            continuation_state = "draft"
    return BasicProcessDocument(
        workspace_id=snapshot.workspace_id,
        state_revision=snapshot.state_revision,
        process=metadata.process,
        selected_work=selected,
        accepted_basis=accepted,
        inherited_result_basis=inherited,
        continuation_state=continuation_state,
        saved_continuation=continuation,
    )


def read_basic_process(
    path: Path, query: ProcessQuery, caller: LocalAuthorization | None = None
) -> BasicProcessPackage:
    """Read one selected Work's metadata and exact saved basis, never content."""
    query = ProcessQuery.model_validate(query.model_dump())
    with workspace_connection(path, write=True) as (connection, info):
        document = _basic_document(connection, info, query, caller)
        output = _wire(document.model_dump(mode="json"))
        if len(output) > query.max_bytes:
            raise MutationError("budget_exceeded", "Basic read exceeds the complete byte budget")
        return BasicProcessPackage(output)


def _metadata(
    connection: sqlite3.Connection,
    info: WorkspaceInfo,
    query: ProcessQuery,
    caller: LocalAuthorization | None,
) -> tuple[ProcessMetadata, str]:
    if info.schema_version < 7:
        raise MutationError("schema", "Process capabilities require explicit schema 7")
    snapshot = _read_records(connection, info.workspace_id)
    _caller(info.workspace, query, caller, snapshot)
    for identity in (query.work_id, *query.visible_work_ids):
        work = _work(snapshot, identity)
        if work.process_id != query.process_id or work.authority_scope == "none":
            raise MutationError("permission_denied", "Metadata scope is not currently permitted")
    if snapshot.state_revision != query.expected_revision:
        raise MutationError("conflict", "Reopen against current state")
    process = next(r for r in snapshot.records if isinstance(r, Process))
    if process.id != query.process_id:
        raise MutationError("scope", "Process does not match this scope")
    history = _history(connection, snapshot, artifacts_enabled=True)
    visible = set(query.visible_work_ids)
    allowed = (
        {
            ref.version_id: ref
            for event in incoming_events(history.events, query.selected_work_id)
            for ref in event.result_references
        }
        if query.selected_work_id is not None
        else {}
    )
    for descriptor in read_versions(connection):
        if descriptor.work_id == query.selected_work_id:
            allowed[descriptor.id] = ArtifactReference(
                artifact_id=descriptor.artifact_id,
                version_id=descriptor.id,
                sha256=descriptor.sha256,
            )
    metadata = ProcessMetadata(
        query=query,
        process=process,
        works=tuple(_work(snapshot, identity) for identity in query.visible_work_ids),
        results=tuple(
            ResultHeader(
                id=event.request.operation_id,
                work_id=event.before.id,
                state_revision=event.state_revision,
            )
            for event in reversed(history.events)
            if event.request.operation == "submit_result" and event.before.id in visible
        ),
        context_references=tuple(allowed.values()),
    )
    # Hidden state participates in integrity/revalidation, never in the disclosed value.
    return metadata, snapshot.model_dump_json() + history.model_dump_json()


def _context(
    connection: sqlite3.Connection,
    info: WorkspaceInfo,
    query: ProcessQuery,
    context_query: ContextQuery | None,
    caller: LocalAuthorization | None,
) -> tuple[ContextPackage | None, str]:
    if context_query is None:
        return None, "not_requested"
    if (
        context_query.workspace_id != query.workspace_id
        or context_query.process_id != query.process_id
        or context_query.work_id != query.selected_work_id
        or context_query.expected_revision != query.expected_revision
    ):
        return None, "scope"
    try:
        collected = collect_context(connection, info, context_query, caller)
        return _compile(collected, context_query), "ok"
    except MutationError as error:
        return None, error.code
    except WorkspaceError:
        return None, "context_unavailable"


@contextmanager
def process_view(
    path: Path,
    query: ProcessQuery,
    caller: LocalAuthorization | None,
    *,
    context_query: ContextQuery | None = None,
    context_caller: LocalAuthorization | None = None,
) -> Iterator[ProcessView]:
    """Hold managed writers, disclose only authorized inputs, revalidate before return.

    Consumers must finish assembling their value inside this context. Callback code
    remains trusted Python; this is not a hostile same-user execution sandbox.
    """
    query = ProcessQuery.model_validate(query.model_dump())
    if context_query is not None:
        context_query = ContextQuery.model_validate(context_query.model_dump())
    with workspace_connection(path, write=True) as (connection, info):
        initial = _metadata(connection, info, query, caller)
        content = _context(connection, info, query, context_query, context_caller)
        yield ProcessView(initial[0], *content)
        if (
            _metadata(connection, info, query, caller) != initial
            or _context(connection, info, query, context_query, context_caller) != content
        ):
            raise MutationError("dependency_changed", "Process read inputs changed; reopen")
