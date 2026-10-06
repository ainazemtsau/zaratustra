"""Indexed shared memory and source-backed, durable text selections.

Core records remain the originals. Selection parts are ordinary derived views,
so their bytes, receipts, backups and deletion follow the existing authority path.
"""

from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
from collections.abc import Iterator
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

from .knowledge import (
    BODY_ADAPTER,
    _checked_read,
    _read_scope_limited,
    open_knowledge,
    read_knowledge,
)
from .models import (
    AnalysisState,
    ClaimState,
    ContextState,
    CreateKnowledgeRequest,
    HandoffState,
    KnowledgeBody,
    KnowledgeRef,
    MemorySelectionBasis,
    MemorySelector,
    MemoryViewState,
    SourceState,
    SpaceInfo,
)
from .operations import LocalAuthority, _authorize, _local_space, apply_operation
from .storage import (
    MEMORY_SCHEMA_NAME,
    MEMORY_SCHEMA_SHA256,
    MEMORY_SCHEMA_STATEMENTS,
    FoundationError,
    canonical_json,
    read_space,
    space_connection,
    utc_now,
)

GENERATOR = "zaratustra.memory/1"
NAMESPACE = UUID("e27bf85c-ec92-456b-bbd7-769843ae6848")
COMPILING_SELECTION: ContextVar[bool] = ContextVar("compiling_memory_selection", default=False)


def _retain(path: Path, request: CreateKnowledgeRequest, authority: LocalAuthority) -> None:
    token = COMPILING_SELECTION.set(True)
    try:
        apply_operation(path, request, authority)
    finally:
        COMPILING_SELECTION.reset(token)


def index_memory(
    connection: sqlite3.Connection,
    record_id: UUID,
    state: KnowledgeBody,
    revision: int,
    changed: int,
) -> None:
    """Called in the normal mutation transaction; no prose interpretation."""
    identifier = str(record_id)
    connection.execute("DELETE FROM memory_topics WHERE record_id=?", (identifier,))
    connection.execute("DELETE FROM memory_index WHERE record_id=?", (identifier,))
    if (
        isinstance(state, ContextState)
        or (isinstance(state, SourceState) and state.capture == "excluded")
        or (isinstance(state, MemoryViewState) and state.generation_method == GENERATOR)
    ):
        return
    metadata = getattr(state, "memory", None)
    activity = getattr(state, "scope_activity_id", None)
    if metadata is not None:
        if activity is not None and activity != metadata.activity_id:
            raise FoundationError("wrong_scope", "Memory organization contradicts original scope")
        if (
            isinstance(state, ClaimState)
            and state.scope_global
            and metadata.activity_id is not None
        ):
            raise FoundationError("wrong_scope", "A global Claim stays global")
        activity = metadata.activity_id
    common = activity is None and not getattr(state, "scope_method_id", None)
    title = (
        metadata.title
        if metadata is not None
        else next(
            (
                value
                for value in (
                    getattr(state, "proposition", None),
                    getattr(state, "task", None),
                    getattr(state, "subject", None),
                    getattr(state, "purpose", None),
                )
                if value
            ),
            f"{state.kind} {identifier}",
        )[:500]
    )
    raw = isinstance(state, SourceState) and state.channel in (
        "conversation_user",
        "conversation_assistant",
        "tool_result",
        "core_operation",
    )
    unprocessed = (
        isinstance(state, SourceState)
        and state.channel
        in (
            "conversation_user",
            "document",
            "external_report",
        )
        and metadata is None
    )
    connection.execute(
        "INSERT INTO memory_index VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            identifier,
            revision,
            state.kind,
            str(activity) if activity else None,
            int(common),
            title,
            int(metadata is not None or not raw),
            int(unprocessed),
            metadata.context_role if metadata else "legacy",
            changed,
            int(getattr(state, "status", None) not in ("superseded", "retracted", "retired")),
        ),
    )
    if metadata is not None:
        for topic in {value.strip().casefold() for value in metadata.topics}:
            connection.execute("INSERT INTO memory_topics VALUES (?,?)", (identifier, topic))
    refresh_intake(connection, identifier)


def refresh_intake(connection: sqlite3.Connection, record_id: str | None = None) -> None:
    """Interpretation is explicit: a retained Claim/Analysis names the source as a basis."""
    connection.execute(
        "UPDATE memory_index AS m SET unprocessed=NOT EXISTS ("
        "SELECT 1 FROM knowledge_edges e JOIN memory_index interpretation "
        "ON interpretation.record_id=e.record_id AND interpretation.revision=e.revision "
        "JOIN knowledge_revisions result ON result.record_id=interpretation.record_id "
        "AND result.revision=interpretation.revision WHERE e.target_id=m.record_id "
        "AND (interpretation.kind='claim' OR (interpretation.kind='analysis' "
        "AND json_extract(result.payload,'$.status') IN ('result','no_change')))) "
        "WHERE m.kind='source' AND m.context_role='legacy' "
        "AND EXISTS (SELECT 1 FROM knowledge_revisions original "
        "WHERE original.record_id=m.record_id AND original.revision=m.revision "
        "AND json_extract(original.payload,'$.channel') IN "
        "('conversation_user','document','external_report')) "
        + (
            "AND (m.record_id=? OR m.record_id IN "
            "(SELECT target_id FROM knowledge_edges WHERE record_id=?))"
            if record_id
            else ""
        ),
        (record_id, record_id) if record_id else (),
    )


def upgrade_memory_space(path: Path, authority: LocalAuthority) -> SpaceInfo:
    """Explicit additive upgrade, retaining every original revision byte."""
    with space_connection(path, writable=True) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active" or info.schema_version < 12:
            raise FoundationError("unsupported_schema", "Memory upgrade needs active schema 12")
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.backup",
            epoch=info.execution_epoch,
        )
        if info.schema_version == 12:
            for statement in MEMORY_SCHEMA_STATEMENTS:
                connection.execute(statement)
            for row in connection.execute(
                "SELECT r.record_id,r.current_revision,r.updated_state_revision,v.payload "
                "FROM knowledge_records r JOIN knowledge_revisions v "
                "ON v.record_id=r.record_id AND v.revision=r.current_revision "
                "WHERE r.status='active' AND v.payload IS NOT NULL"
            ):
                index_memory(
                    connection,
                    UUID(row[0]),
                    BODY_ADAPTER.validate_json(row[3]),
                    int(row[1]),
                    int(row[2]),
                )
            refresh_intake(connection)
            now = utc_now().isoformat()
            connection.execute(
                "INSERT INTO schema_migrations VALUES (13,?,?,?)",
                (MEMORY_SCHEMA_NAME, MEMORY_SCHEMA_SHA256, now),
            )
            connection.execute("PRAGMA user_version=13")
            connection.execute(
                "UPDATE spaces SET state_revision=state_revision+1 WHERE singleton=1"
            )
            connection.execute(
                "INSERT INTO maintenance_events(event_id,kind,occurred_at,detail_json) "
                "VALUES (?,'schema_upgrade',?,?)",
                (str(uuid4()), now, canonical_json({"from": 12, "to": 13})),
            )
    return read_space(path)


def _ready(info: SpaceInfo, authority: LocalAuthority) -> None:
    _local_space(authority, info)
    if info.schema_version < 13 or info.recovery_state != "active":
        raise FoundationError("unsupported_schema", "Shared memory needs explicit schema 13")


def _filter(selectors: tuple[MemorySelector, ...]) -> tuple[str, list[object]]:
    unions: list[str] = []
    params: list[object] = []
    for selector in selectors or (MemorySelector(),):
        if selector.current_activity:
            raise FoundationError("invalid_request", "Resolve current_activity from the host focus")
        clauses: list[str] = []
        if not selector.full and not selector.record_ids:
            clauses.extend(("m.current=1", "(m.catalogued=1 OR m.unprocessed=1)"))
        scopes: list[str] = []
        if selector.activity_ids:
            scopes.append("m.activity_id IN (SELECT value FROM json_each(?))")
            params.append(canonical_json(list(map(str, selector.activity_ids))))
        if selector.common:
            scopes.append("m.common=1")
        if scopes:
            clauses.append("(" + " OR ".join(scopes) + ")")
        if selector.record_ids:
            clauses.append("m.record_id IN (SELECT value FROM json_each(?))")
            params.append(canonical_json(list(map(str, selector.record_ids))))
        if selector.topics:
            clauses.append(
                "EXISTS (SELECT 1 FROM memory_topics t WHERE t.record_id=m.record_id "
                "AND t.topic IN (SELECT value FROM json_each(?)))"
            )
            params.append(canonical_json([value.strip().casefold() for value in selector.topics]))
        if selector.query is not None:
            clauses.append(
                "m.record_id IN (SELECT record_id FROM knowledge_fts "
                "WHERE knowledge_fts MATCH ? AND revision=m.revision)"
            )
            params.append(selector.query)
        if selector.context_role is not None:
            clauses.append("m.context_role=?")
            params.append(selector.context_role)
        unions.append("(" + " AND ".join(clauses or ["1"]) + ")")
    return "(" + " OR ".join(unions or ["1"]) + ")", params


@dataclass(frozen=True)
class _Reader:
    actor: str
    epoch: int


def _rows(
    connection: sqlite3.Connection,
    reader: _Reader,
    selectors: tuple[MemorySelector, ...],
    *,
    after: str = "",
    catalog: bool = False,
    unprocessed_only: bool = False,
) -> Iterator[sqlite3.Row | tuple[Any, ...]]:
    where, params = _filter(selectors)
    query = "SELECT m.* FROM memory_index m WHERE " + where + " AND m.record_id>?"
    if catalog:
        query += " AND (m.catalogued=1 OR m.unprocessed=1)"
    if unprocessed_only:
        query += " AND m.unprocessed=1"
    query += " ORDER BY m.record_id"
    try:
        for row in connection.execute(query, (*params, after)):
            try:
                _authorize(
                    connection,
                    actor=reader.actor,
                    action="record.read",
                    epoch=reader.epoch,
                    resource_type="artifact",
                    resource_id=UUID(row[0]),
                )
            except FoundationError as error:
                if error.code in ("permission_denied", "decision_denied"):
                    continue
                raise
            yield row
    except sqlite3.OperationalError as error:
        raise FoundationError("invalid_query", str(error)) from error


def memory_catalog(
    path: Path,
    authority: LocalAuthority,
    *,
    selectors: tuple[MemorySelector, ...] = (),
    limit: int = 25,
    cursor: str | None = None,
    full: bool = False,
    unprocessed_only: bool = False,
) -> dict[str, object]:
    if not 1 <= limit <= 100:
        raise FoundationError("invalid_request", "Catalog page size must be 1..100")
    if full:
        selectors = tuple(
            selector.model_copy(update={"full": True})
            for selector in selectors or (MemorySelector(),)
        )
    after = str(UUID(cursor)) if cursor else ""
    with space_connection(path) as (connection, info):
        _ready(info, authority)
        entries: list[dict[str, object]] = []
        more = False
        for row in _rows(
            connection,
            _Reader(authority.actor, info.execution_epoch),
            selectors,
            after=after,
            catalog=not full,
            unprocessed_only=unprocessed_only,
        ):
            if len(entries) == limit:
                more = True
                break
            revisions = connection.execute(
                "SELECT COUNT(*) FROM knowledge_revisions "
                "WHERE record_id=? AND payload IS NOT NULL",
                (row[0],),
            ).fetchone()[0]
            entries.append(
                {
                    "record_id": row[0],
                    "revision": row[1],
                    "kind": row[2],
                    "activity_id": row[3],
                    "common": bool(row[4]),
                    "title": row[5],
                    "unprocessed": bool(row[7]),
                    "context_role": row[8],
                    "has_history": revisions > 1,
                    "topics": [
                        t[0]
                        for t in connection.execute(
                            "SELECT topic FROM memory_topics WHERE record_id=? ORDER BY topic",
                            (row[0],),
                        )
                    ],
                }
            )
        return {
            "items": entries,
            "next_cursor": entries[-1]["record_id"] if more else None,
            "complete": not more,
            "restricted": _read_scope_limited(connection, info, authority),
            "coverage": "authorized memory; other scopes may be unavailable",
            "state_revision": info.state_revision,
        }


def _members(
    connection: sqlite3.Connection,
    reader: _Reader,
    selectors: tuple[MemorySelector, ...],
) -> tuple[tuple[KnowledgeRef, ...], str]:
    refs: list[KnowledgeRef] = []
    full_roots: list[KnowledgeRef] = []
    digest = hashlib.sha256()
    try:
        _authorize(connection, actor=reader.actor, action="record.read", epoch=reader.epoch)
        digest.update(b"unrestricted")
    except FoundationError as error:
        if error.code not in ("permission_denied", "decision_denied"):
            raise
        digest.update(b"restricted")
    for selector in selectors:
        for identifier in selector.record_ids:
            _authorize(
                connection,
                actor=reader.actor,
                action="record.read",
                epoch=reader.epoch,
                resource_type="artifact",
                resource_id=identifier,
            )
            item = connection.execute(
                "SELECT status FROM knowledge_records WHERE record_id=?", (str(identifier),)
            ).fetchone()
            if item is None:
                raise FoundationError("not_found", "Explicit memory input is absent")
            if item[0] != "active":
                raise FoundationError("content_unavailable", "Explicit memory input is unavailable")
            if (
                connection.execute(
                    "SELECT 1 FROM memory_index WHERE record_id=?", (str(identifier),)
                ).fetchone()
                is None
            ):
                raise FoundationError("wrong_kind", "Use open_selection for generated selections")
    for row in _rows(connection, reader, selectors):
        digest.update(canonical_json(list(row)).encode())
        # Full history is explicit per selector, not a heuristic date-based choice.
        full = any(
            selector.full
            and (not selector.record_ids or UUID(row[0]) in selector.record_ids)
            and next(
                _rows(
                    connection,
                    reader,
                    (selector.model_copy(update={"record_ids": (UUID(row[0]),)}),),
                ),
                None,
            )
            is not None
            for selector in selectors
        )
        revisions = connection.execute(
            "SELECT revision,sha256 FROM knowledge_revisions WHERE record_id=? "
            "AND payload IS NOT NULL " + ("" if full else "AND revision=? ") + "ORDER BY revision",
            (row[0],) if full else (row[0], row[1]),
        )
        for revision, checksum in revisions:
            reference = KnowledgeRef(record_id=UUID(row[0]), revision=revision)
            refs.append(reference)
            if full:
                full_roots.append(reference)
            digest.update(f"{row[0]}:{revision}:{checksum}".encode())
    # Full areas also retain exact knowledge bases originating in another area.
    # Structural Activity/Work anchors remain addresses, not imported work ownership.
    seen = set(refs)
    while full_roots:
        root = full_roots.pop()
        for identifier, revision, checksum in connection.execute(
            "SELECT e.target_id,e.target_revision,v.sha256 FROM knowledge_edges e "
            "JOIN knowledge_revisions v ON v.record_id=e.target_id "
            "AND v.revision=e.target_revision WHERE e.record_id=? AND e.revision=? "
            "ORDER BY e.ordinal",
            (str(root.record_id), root.revision),
        ):
            reference = KnowledgeRef(record_id=UUID(identifier), revision=revision)
            if reference in seen:
                continue
            _authorize(
                connection,
                actor=reader.actor,
                action="record.read",
                epoch=reader.epoch,
                resource_type="artifact",
                resource_id=reference.record_id,
            )
            if checksum is None:
                raise FoundationError(
                    "content_unavailable", f"Full memory basis {identifier}@{revision}"
                )
            seen.add(reference)
            refs.append(reference)
            full_roots.append(reference)
            digest.update(f"{identifier}:{revision}:{checksum}".encode())
    return tuple(refs), digest.hexdigest()


def selection_current(
    connection: sqlite3.Connection,
    info: SpaceInfo,
    authority: LocalAuthority,
    basis: MemorySelectionBasis,
) -> bool:
    return selection_current_for_actor(connection, authority.actor, info.execution_epoch, basis)


def selection_current_for_actor(
    connection: sqlite3.Connection,
    actor: str,
    epoch: int,
    basis: MemorySelectionBasis,
) -> bool:
    if basis.actor != actor or basis.epoch != epoch or basis.rule_version != 1:
        return False
    refs, fingerprint = _members(connection, _Reader(actor, epoch), basis.selectors)
    return refs == basis.members and fingerprint == basis.fingerprint


def _text(state: KnowledgeBody) -> str:
    """Lossless source bytes and an explicit provenance trailer."""
    provenance = state.model_dump(mode="json", exclude={"content", "document", "text"})
    if isinstance(state, SourceState):
        text = (
            state.content.decode("utf-8")
            if state.content is not None and (state.media_type.startswith("text/"))
            else "Binary content (base64): " + base64.b64encode(state.content or b"").decode()
        )
    elif isinstance(state, ClaimState):
        text = state.proposition
    elif isinstance(state, AnalysisState):
        text = "\n".join(filter(None, (state.task, state.conclusion, state.remainder)))
    elif isinstance(state, HandoffState):
        text = (
            state.document.decode("utf-8")
            if state.media_type.startswith("text/")
            else "Binary document (base64): " + base64.b64encode(state.document).decode()
        )
    elif isinstance(state, MemoryViewState):
        text = state.text
    else:
        text = ""
    return text + "\n\nProvenance:\n```json\n" + canonical_json(provenance) + "\n```\n"


def memory_history(
    path: Path,
    record_id: UUID,
    authority: LocalAuthority,
    *,
    after_revision: int = 0,
    limit: int = 25,
) -> dict[str, object]:
    if not 1 <= limit <= 100 or after_revision < 0:
        raise FoundationError("invalid_request", "Use a finite history page")
    with space_connection(path) as (connection, info):
        _ready(info, authority)
        _checked_read(connection, info, authority, record_id, None)
        revisions = connection.execute(
            "SELECT revision,created_at,event_at FROM knowledge_revisions WHERE record_id=? "
            "AND revision>? ORDER BY revision LIMIT ?",
            (str(record_id), after_revision, limit + 1),
        ).fetchall()
        entries = []
        for revision, created_at, event_at in revisions[:limit]:
            item = _checked_read(connection, info, authority, record_id, revision)
            entries.append(
                {
                    "revision": revision,
                    "created_at": created_at,
                    "event_at": event_at,
                    "availability": item.availability,
                    "sha256": item.sha256,
                    "basis": [
                        {"role": edge[0], "record_id": edge[1], "revision": edge[2]}
                        for edge in connection.execute(
                            "SELECT role,target_id,target_revision FROM knowledge_edges "
                            "WHERE record_id=? AND revision=? ORDER BY ordinal",
                            (str(record_id), revision),
                        )
                    ],
                }
            )
        return {
            "record_id": str(record_id),
            "items": entries,
            "next_revision": entries[-1]["revision"] if len(revisions) > limit else None,
            "complete": len(revisions) <= limit,
        }


def _split(text: str, size: int = 32768) -> Iterator[str]:
    current: list[str] = []
    total = 0
    for char in text:
        length = len(char.encode())
        if total + length > size:
            yield "".join(current)
            current, total = [], 0
        current.append(char)
        total += length
    if current:
        yield "".join(current)


def prepare_memory_cache(
    path: Path,
    authority: LocalAuthority,
    selectors: tuple[MemorySelector, ...],
    *,
    cache: bool = True,
    operation_id: UUID | None = None,
    max_bytes: int = 16384,
    _retry: bool = True,
) -> dict[str, object]:
    """Freeze membership first; render exact revisions outside a write transaction."""
    selectors = selectors or (MemorySelector(),)
    with space_connection(path) as (connection, info):
        _ready(info, authority)
        members, fingerprint = _members(
            connection, _Reader(authority.actor, info.execution_epoch), selectors
        )
        restricted = _read_scope_limited(connection, info, authority)
        identity = canonical_json(
            {
                "actor": authority.actor,
                "epoch": info.execution_epoch,
                "selectors": [s.model_dump(mode="json") for s in selectors],
                "fingerprint": fingerprint,
                "rule": 1,
            }
        )
    selection_id = (
        uuid5(NAMESPACE, identity) if cache else uuid5(operation_id or uuid4(), "selection")
    )
    try:
        existing = read_knowledge(path, selection_id, authority)
        if isinstance(existing.state, MemoryViewState) and existing.state.selection is not None:
            if existing.state.selection.fingerprint != fingerprint:
                raise FoundationError(
                    "operation_conflict", "Selection identity has different inputs"
                )
            result = open_memory_selection(path, selection_id, authority, max_bytes=max_bytes)
            if cache and not result["current"]:
                if not _retry:
                    raise FoundationError(
                        "stale_context", "Memory changed during cache preparation"
                    )
                return prepare_memory_cache(
                    path, authority, selectors, max_bytes=max_bytes, _retry=False
                )
            return result
    except FoundationError as error:
        if error.code != "not_found":
            raise
    parts: list[KnowledgeRef] = []
    total_bytes = 0
    for member in members:
        item = read_knowledge(path, member.record_id, authority, revision=member.revision)
        if item.state is None:
            raise FoundationError("content_unavailable", "Selection input disappeared")
        header = f"\n## {member.record_id}@{member.revision}\n"
        metadata = getattr(item.state, "memory", None)
        if metadata is not None:
            header += f"{metadata.title}\nActivity: {metadata.activity_id or 'common'}\n"
        text = header + _text(item.state) + "\n"
        for fragment in _split(text):
            total_bytes += len(fragment.encode("utf-8"))
            part_id = uuid5(selection_id, f"part:{len(parts)}")
            _retain(
                path,
                CreateKnowledgeRequest(
                    operation_id=uuid5(part_id, "prepare"),
                    space_id=info.space_id,
                    actor=authority.actor,
                    record_id=part_id,
                    state=MemoryViewState(
                        purpose="Selection text part",
                        scope="Exact source-backed selection",
                        scope_kind="space",
                        generation_method=GENERATOR,
                        mode="historical",
                        sources=(member,),
                        text=fragment,
                        coverage_state_revision=0,
                    ),
                ),
                authority,
            )
            parts.append(KnowledgeRef(record_id=part_id, revision=1))
    basis = MemorySelectionBasis(
        selectors=selectors,
        fingerprint=fingerprint,
        actor=authority.actor,
        epoch=info.execution_epoch,
        parts=tuple(parts),
        members=members,
        total_bytes=total_bytes,
        cache=cache,
        restricted=restricted,
    )
    _retain(
        path,
        CreateKnowledgeRequest(
            operation_id=uuid5(selection_id, "prepare"),
            space_id=info.space_id,
            actor=authority.actor,
            record_id=selection_id,
            state=MemoryViewState(
                purpose="Shared memory selection",
                scope="Explicit multi-area selection",
                scope_kind="space",
                generation_method=GENERATOR,
                mode="historical",
                sources=members + tuple(parts),
                text=f"Memory selection: {len(members)} revisions; "
                f"{len(parts)} text parts. Exact snapshot; "
                "external files do not update themselves.",
                selection=basis,
                coverage_state_revision=0,
            ),
        ),
        authority,
    )
    result = open_memory_selection(path, selection_id, authority, max_bytes=max_bytes)
    if cache and not result["current"]:
        if not _retry:
            raise FoundationError("stale_context", "Memory changed during both cache preparations")
        return prepare_memory_cache(path, authority, selectors, max_bytes=max_bytes, _retry=False)
    return result


def read_memory_batch(
    path: Path,
    authority: LocalAuthority,
    selectors: tuple[MemorySelector, ...],
    *,
    operation_id: UUID | None = None,
    max_bytes: int = 16384,
) -> dict[str, object]:
    return prepare_memory_cache(
        path, authority, selectors, cache=False, operation_id=operation_id, max_bytes=max_bytes
    )


def open_memory_selection(
    path: Path,
    selection_id: UUID,
    authority: LocalAuthority,
    *,
    part: int = 0,
    offset: int = 0,
    max_bytes: int = 16384,
    toc_offset: int = 0,
) -> dict[str, object]:
    if part < 0 or offset < 0 or toc_offset < 0 or not 1 <= max_bytes <= 65536:
        raise FoundationError("invalid_request", "Use a finite selection window")
    start_part, start_offset = part, offset
    with space_connection(path) as (connection, info):
        _ready(info, authority)
        item = _checked_read(connection, info, authority, selection_id, None)
        if not isinstance(item.state, MemoryViewState) or item.state.selection is None:
            raise FoundationError("wrong_kind", "Read a memory selection")
        basis = item.state.selection
        if basis.actor != authority.actor or basis.epoch != info.execution_epoch:
            raise FoundationError("permission_denied", "Rebuild selection for this actor/epoch")
        current = selection_current(connection, info, authority, basis)
    if part > len(basis.parts) or (part == len(basis.parts) and offset):
        raise FoundationError("invalid_request", "Selection position is outside its parts")
    result: dict[str, object] = {
        "selection_id": str(selection_id),
        "revision": item.revision,
        "selection_complete": not basis.restricted or all(s.record_ids for s in basis.selectors),
        "restricted": basis.restricted,
        "coverage": "retained authorized memory",
        "assembly_complete": True,
        "current": current,
        "members": len(basis.members),
        "parts": len(basis.parts),
        "part": part,
        "total_bytes": basis.total_bytes,
        "window_start": {"part": start_part, "offset": start_offset},
        "table_of_contents": [
            ref.model_dump(mode="json") for ref in basis.members[toc_offset : toc_offset + 25]
        ],
        "next_toc_offset": toc_offset + 25 if toc_offset + 25 < len(basis.members) else None,
        "content_text": "",
        "exposed": [],
        "next_part": None,
        "next_offset": None,
        "content_complete": False,
    }
    texts: list[str] = []
    exposed: list[dict[str, object]] = []
    remaining = max_bytes
    while part < len(basis.parts) and remaining:
        ref = basis.parts[part]
        try:
            opened = open_knowledge(
                path,
                ref.record_id,
                authority,
                revision=ref.revision,
                offset=offset,
                max_bytes=remaining,
            )
        except FoundationError as error:
            if texts and error.code == "invalid_request":
                break
            raise
        content = opened.get("content_base64")
        if not isinstance(content, str):
            raise FoundationError("content_unavailable", "Selection part is unavailable")
        chunk = base64.b64decode(content)
        texts.append(chunk.decode("utf-8"))
        exposed.append(
            ref.model_copy(update={"start": offset, "end": offset + len(chunk)}).model_dump(
                mode="json"
            )
        )
        remaining -= len(chunk)
        if opened["next_offset"] is not None:
            offset = int(str(opened["next_offset"]))
            break
        part, offset = part + 1, 0
    result["content_text"] = "".join(texts)
    result["exposed"] = exposed
    result["next_part"] = part if part < len(basis.parts) else None
    result["next_offset"] = offset if part < len(basis.parts) else None
    result["end_of_selection"] = part == len(basis.parts)
    result["content_complete"] = start_part == 0 and start_offset == 0 and part == len(basis.parts)
    result["returned_bytes"] = max_bytes - remaining
    result["window_end"] = {"part": part, "offset": offset}
    with space_connection(path) as (connection, latest):
        _ready(latest, authority)
        final = _checked_read(connection, latest, authority, selection_id, item.revision)
        result["current"] = not final.stale
        for member in basis.members:
            available = connection.execute(
                "SELECT r.status,v.payload IS NOT NULL FROM knowledge_records r "
                "JOIN knowledge_revisions v ON v.record_id=r.record_id "
                "WHERE r.record_id=? AND v.revision=?",
                (str(member.record_id), member.revision),
            ).fetchone()
            if available is None or available[0] != "active" or not available[1]:
                raise FoundationError("content_unavailable", "Selection basis became unavailable")
    return result


def export_memory_selection(
    path: Path,
    selection_id: UUID,
    authority: LocalAuthority,
    destination: Path,
) -> dict[str, object]:
    """A chosen delivery copy; Core selection parts remain the managed originals."""
    if destination.exists():
        raise FoundationError("file_exists", "Choose a new export file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending = destination.with_name(destination.name + f".{uuid4()}.pending")
    part = offset = 0
    digest = hashlib.sha256()
    try:
        with pending.open("xb") as stream:
            header = f"# Zaratustra memory snapshot\n\nSelection: {selection_id}\n\n".encode()
            stream.write(header)
            digest.update(header)
            source = read_knowledge(path, selection_id, authority)
            assert isinstance(source.state, MemoryViewState) and source.state.selection is not None
            for ref in source.state.selection.members:
                entry = (
                    f"- [{ref.record_id}@{ref.revision}](#{ref.record_id}{ref.revision})\n".encode()
                )
                stream.write(entry)
                digest.update(entry)
            while True:
                result = open_memory_selection(
                    path, selection_id, authority, part=part, offset=offset
                )
                chunk = str(result["content_text"]).encode()
                stream.write(chunk)
                digest.update(chunk)
                if result["next_part"] is None:
                    break
                part, offset = int(str(result["next_part"])), int(str(result["next_offset"]))
        # Recheck rights/deletion before exposing the completed copy.
        open_memory_selection(path, selection_id, authority)
        try:
            # Atomic publication cannot overwrite a concurrent delivery.
            os.link(pending, destination)
        except FileExistsError as error:
            raise FoundationError(
                "file_exists", "Export destination appeared during assembly"
            ) from error
    finally:
        pending.unlink(missing_ok=True)
    return {
        "path": str(destination),
        "sha256": digest.hexdigest().upper(),
        "selection_id": str(selection_id),
        "complete": True,
        "external_snapshot": True,
    }


def memory_required_refs(
    path: Path,
    authority: LocalAuthority,
    activity_id: UUID,
) -> tuple[KnowledgeRef, ...]:
    """Applicable declared constraints do not depend on semantic ranking."""
    with space_connection(path) as (connection, info):
        _ready(info, authority)
        refs = []
        for row in _rows(
            connection,
            _Reader(authority.actor, info.execution_epoch),
            (MemorySelector(activity_ids=(activity_id,), common=True),),
        ):
            if row[8] == "required":
                refs.append(KnowledgeRef(record_id=UUID(row[0]), revision=row[1]))
        return tuple(refs)
