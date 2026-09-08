"""Bounded Work reads with complete final revalidation, never domain writes."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import current_artifact, read_versions, resolve_version, verified_content
from .handoffs import AcceptedHandoff
from .mutations import LocalAuthorization, MutationError, _caller, _history, _work
from .protocol import ArtifactReference, ContextQuery, event_receipt
from .records import Process, _read_records
from .workspace import WorkspaceInfo, workspace_connection


def _json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class ContextPackage:
    """The complete exact wire bytes, including manifest and one trailing LF.

    A retained package is historical evidence, not current read authorization.
    """

    output: bytes

    @property
    def output_sha256(self) -> str:
        return _sha(self.output)


@dataclass(frozen=True)
class _Collected:
    context: dict[str, Any]
    guard: bytes


def _collect(
    connection: sqlite3.Connection,
    info: WorkspaceInfo,
    query: ContextQuery,
    caller: LocalAuthorization | None,
) -> _Collected:
    if info.schema_version < 5:
        raise MutationError("schema", "Work context requires explicit schema 5")
    snapshot = _read_records(connection, info.workspace_id)
    _caller(info.workspace, query, caller, snapshot)
    work = _work(snapshot)
    if work.status != "ready" or work.authority_scope not in (
        "work_metadata",
        "work_metadata_and_artifact",
    ):
        raise MutationError(
            "permission_denied", "Work is terminal, not ready or lacks current rights"
        )
    if query.process_id != work.process_id:
        raise MutationError("scope", "Process is outside this Work")
    if query.expected_revision != snapshot.state_revision:
        raise MutationError(
            "conflict", "Context expected revision is not current; rebuild explicitly"
        )
    history = _history(connection, snapshot, artifacts_enabled=True)
    artifact = current_artifact(snapshot)
    process = next(row for row in snapshot.records if isinstance(row, Process))
    versions = read_versions(connection)
    sources: list[dict[str, Any]] = []

    def add(locator: str, revision: int, data: Any) -> None:
        sources.append(dict(locator=locator, revision=revision, data=data))

    for record in (process, work, artifact):
        add(f"{record.kind}:{record.id}", record.revision, record.model_dump(mode="json"))
    refs = list(query.references)
    decisions = []
    publications = {
        event.request.operation_id: event
        for event in history.events
        if event.artifact_version is not None
    }
    for event in history.events:
        handoff, delivery = event.request.handoff, event.request.delivery
        if handoff is None or delivery is None:
            continue
        if (handoff.workspace_id, handoff.process, handoff.related_work) != (
            snapshot.workspace_id,
            process.id,
            work.id,
        ):
            raise MutationError("scope", "Accepted decision is outside this Work")
        accepted = AcceptedHandoff(
            handoff=handoff,
            delivery=delivery,
            confirmation=event.confirmation,
            receipt=event_receipt(event),
        )
        add(
            f"acceptance:{handoff.handoff_id}",
            event.state_revision,
            accepted.model_dump(mode="json"),
        )
        decisions.append(dict(id=str(handoff.handoff_id), revision=event.state_revision))
        refs.extend((handoff.result, *handoff.basis))
    if not decisions:
        raise MutationError("dependency_missing", "Post-Handoff Work context requires acceptance")
    active = resolve_version(versions, artifact)
    refs.append(
        ArtifactReference(artifact_id=artifact.id, version_id=active.id, sha256=active.sha256)
    )
    seen = set()
    raw_bytes = 0
    for ref in refs:
        if ref.artifact_id != artifact.id:
            raise MutationError("scope", "Referenced Artifact is outside this Work")
        descriptor = resolve_version(versions, artifact, ref.version_id)
        if ref.sha256 != descriptor.sha256:
            raise MutationError(
                "dependency_changed", "Reference hash differs from registered bytes"
            )
        if descriptor.id in seen:
            continue
        seen.add(descriptor.id)
        raw_bytes += descriptor.size
        if raw_bytes > query.max_bytes:
            raise MutationError(
                "budget_exceeded",
                f"Mandatory content alone requires at least {raw_bytes} bytes; "
                f"allowed {query.max_bytes}; no output",
            )
        publication = publications[descriptor.id]
        # Edges are checked individually even when their target has been visited.
        refs.extend(publication.request.references)
        content = verified_content(info.workspace, descriptor)
        add(
            f"artifact-version:{descriptor.id}",
            descriptor.state_revision,
            dict(
                descriptor=descriptor.model_dump(mode="json"),
                content_base64=base64.b64encode(content.content).decode("ascii"),
                publication=dict(
                    request=publication.request.model_dump(mode="json"),
                    confirmation=publication.confirmation.model_dump(mode="json"),
                    receipt=event_receipt(publication).model_dump(mode="json"),
                ),
            ),
        )
    envelope = dict(
        version=1,
        workspace_id=str(snapshot.workspace_id),
        process_id=str(process.id),
        work_id=str(work.id),
        state_revision=snapshot.state_revision,
        schema_version=info.schema_version,
        namespaces=[
            f"workspace:{snapshot.workspace_id}/process:{process.id}/work:{work.id}",
            f"artifact:{artifact.id}",
        ],
        budget=dict(unit="utf8_bytes_entire_output", maximum=query.max_bytes),
        dependencies=dict(
            state_revision=snapshot.state_revision,
            work_revision=work.revision,
            authority_revision=work.revision,
            process_revision=process.revision,
            artifact_revision=artifact.revision,
            acceptances=decisions,
        ),
        selection="all_work_acceptances_active_artifact_and_exact_reference_closure",
        freshness="fully_revalidated_at_return; reopen_after_any_change",
        text_links="inert; never authorization or implicit content reads",
        skills=[],
        tools=[],
        memory_entries=[],
    )
    # Include even non-disclosed history in the consistency guard, never in output.
    guard = _json(
        dict(
            schema=info.schema_version,
            snapshot=snapshot.model_dump(mode="json"),
            history=history.model_dump(mode="json"),
            versions=[v.model_dump(mode="json") for v in versions],
        )
    )
    return _Collected(dict(envelope=envelope, sources=sources), guard)


def _compile(collected: _Collected, query: ContextQuery) -> ContextPackage:
    context = collected.context
    inventory = []
    for source in context["sources"]:
        data = source["data"]
        encoded = _json(data)
        item = dict(
            locator=source["locator"],
            revision=source["revision"],
            value_sha256=_sha(encoded),
            value_bytes=len(encoded),
        )
        if "content_base64" in data:
            item.update(
                content_sha256=data["descriptor"]["sha256"],
                content_bytes=data["descriptor"]["size"],
            )
        inventory.append(item)
    manifest = dict(
        version=1,
        sources=inventory,
        context_sha256=_sha(_json(context)),
        dependencies=context["envelope"]["dependencies"],
        skills=[],
        tools=[],
        memory_entries=[],
        budget=dict(unit="utf8_bytes_entire_output", maximum=query.max_bytes, used=0),
        delivery="exact_cli_stdout; chat_receipt_and_understanding_unverified",
    )
    while True:
        wire = _json(dict(context=context, manifest=manifest)) + bytes([10])
        if manifest["budget"]["used"] == len(wire):
            break
        manifest["budget"]["used"] = len(wire)
    if len(wire) > query.max_bytes:
        raise MutationError(
            "budget_exceeded",
            f"Mandatory output requires {len(wire)} bytes; allowed {query.max_bytes}; no output",
        )
    return ContextPackage(wire)


def open_work(
    path: Path, query: ContextQuery, caller: LocalAuthorization | None = None
) -> ContextPackage:
    """Read current scoped context, then fully revalidate before exposing any bytes."""
    query = ContextQuery.model_validate(query.model_dump())
    with workspace_connection(path) as (connection, info):
        collected = _collect(connection, info, query, caller)
    package = _compile(collected, query)
    # Serialize managed writers for final validation. This lock performs no DML.
    with workspace_connection(path, write=True) as (connection, info):
        checked = _collect(connection, info, query, caller)
        if checked != collected:
            raise MutationError("dependency_changed", "Context changed during assembly; reopen")
    return package
