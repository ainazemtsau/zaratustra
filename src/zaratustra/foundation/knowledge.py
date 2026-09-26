"""Primary sources, knowledge, retrieval, context and external document handoffs.

All state lives in the selected Core database and shares its operation, audit,
receipt, authority, backup and deletion transaction boundaries.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import TypeAdapter, ValidationError

from .models import (
    AnalysisState,
    ClaimState,
    ContextState,
    CreateKnowledgeRequest,
    DeleteKnowledgeRequest,
    GrantState,
    HandoffState,
    KnowledgeBody,
    KnowledgeRef,
    KnowledgeRevision,
    MemoryLinkState,
    MemoryViewState,
    RecordContextDeliveryRequest,
    ReviseKnowledgeRequest,
    SourceState,
    SpaceInfo,
)
from .operations import LocalAuthority, _authorize, _local_space
from .storage import (
    KNOWLEDGE_SCHEMA_NAME,
    KNOWLEDGE_SCHEMA_SHA256,
    KNOWLEDGE_SCHEMA_STATEMENTS,
    FoundationError,
    canonical_json,
    read_space,
    space_connection,
    utc_now,
)

BODY_ADAPTER: TypeAdapter[KnowledgeBody] = TypeAdapter(KnowledgeBody)
KnowledgeChange = (
    CreateKnowledgeRequest
    | ReviseKnowledgeRequest
    | DeleteKnowledgeRequest
    | RecordContextDeliveryRequest
)


def upgrade_knowledge_space(path: Path, authority: LocalAuthority) -> SpaceInfo:
    """Explicit additive schema 9 to 10 upgrade; ordinary reads never migrate."""

    with space_connection(path, writable=True) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active" or info.schema_version < 9:
            raise FoundationError("unsupported_schema", "Knowledge upgrade needs active schema 9")
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.backup",
            epoch=info.execution_epoch,
        )
        if info.schema_version == 9:
            for statement in KNOWLEDGE_SCHEMA_STATEMENTS:
                connection.execute(statement)
            now = utc_now().isoformat()
            connection.execute(
                "INSERT INTO schema_migrations(version,name,sha256,applied_at) VALUES (10,?,?,?)",
                (KNOWLEDGE_SCHEMA_NAME, KNOWLEDGE_SCHEMA_SHA256, now),
            )
            connection.execute("PRAGMA user_version = 10")
            connection.execute(
                "UPDATE spaces SET state_revision=state_revision+1 WHERE singleton=1"
            )
            connection.execute(
                "INSERT INTO maintenance_events(event_id,kind,occurred_at,detail_json) "
                "VALUES (?,'schema_upgrade',?,?)",
                (str(uuid4()), now, canonical_json({"from": 9, "to": 10})),
            )
    return read_space(path)


def _refs(state: KnowledgeBody) -> list[tuple[str, KnowledgeRef]]:
    if isinstance(state, SourceState):
        return [("derived_from", ref) for ref in state.derived_from]
    if isinstance(state, ClaimState):
        refs = [("evidence", ref) for ref in state.evidence]
        refs += [("counter_evidence", ref) for ref in state.counter_evidence]
        return refs + ([("supersedes", state.supersedes)] if state.supersedes else [])
    if isinstance(state, AnalysisState):
        return [("input", ref) for ref in state.inputs] + [("effect", ref) for ref in state.effects]
    if isinstance(state, MemoryLinkState):
        return [("source", state.source), ("target", state.target)] + [
            ("basis", ref) for ref in state.basis
        ]
    if isinstance(state, MemoryViewState):
        return [("source", ref) for ref in state.sources]
    if isinstance(state, ContextState):
        return [("mandatory", ref) for ref in state.mandatory] + [
            ("optional", ref) for ref in state.optional
        ]
    refs = [("included", ref) for ref in state.included]
    if state.transfer_source is not None:
        refs.append(("transfer_source", state.transfer_source))
    if state.return_source is not None:
        refs.append(("return_source", state.return_source))
    return refs


def _require_ref(connection: sqlite3.Connection, ref: KnowledgeRef, actor: str, epoch: int) -> None:
    kind = connection.execute(
        "SELECT kind FROM subject_records WHERE record_id=?", (str(ref.record_id),)
    ).fetchone()
    _authorize(
        connection,
        actor=actor,
        action="record.read",
        epoch=epoch,
        resource_type=kind[0] if kind is not None else "artifact",
        resource_id=ref.record_id,
    )
    row = connection.execute(
        "SELECT r.status,v.payload FROM knowledge_records r "
        "JOIN knowledge_revisions v ON v.record_id=r.record_id "
        "WHERE r.record_id=? AND v.revision=?",
        (str(ref.record_id), ref.revision),
    ).fetchone()
    if row is not None:
        if row[0] != "active" or row[1] is None:
            raise FoundationError(
                "content_unavailable", f"Knowledge basis {ref.record_id}@{ref.revision}"
            )
        if ref.end is not None:
            referenced = BODY_ADAPTER.validate_json(row[1])
            content = (
                referenced.content
                if isinstance(referenced, SourceState)
                else (referenced.document if isinstance(referenced, HandoffState) else None)
            )
            if content is None or ref.end > len(content):
                raise FoundationError("invalid_fragment", "Fragment exceeds retained source bytes")
        return
    other = connection.execute(
        "SELECT 1 FROM record_revisions WHERE record_id=? AND revision=? UNION ALL "
        "SELECT 1 FROM subject_revisions WHERE record_id=? AND revision=? LIMIT 1",
        (str(ref.record_id), ref.revision, str(ref.record_id), ref.revision),
    ).fetchone()
    if other is None:
        raise FoundationError("not_found", f"Exact basis {ref.record_id}@{ref.revision} is absent")
    if ref.start is not None:
        raise FoundationError(
            "invalid_fragment", "Only retained knowledge payloads have byte fragments"
        )


def _prior_state(connection: sqlite3.Connection, record_id: UUID) -> tuple[str, int, KnowledgeBody]:
    row = connection.execute(
        "SELECT r.kind,r.current_revision,v.payload FROM knowledge_records r "
        "JOIN knowledge_revisions v ON v.record_id=r.record_id "
        "AND v.revision=r.current_revision WHERE r.record_id=? AND r.status='active'",
        (str(record_id),),
    ).fetchone()
    if row is None or row[2] is None:
        raise FoundationError("content_unavailable", f"Knowledge record {record_id} is unavailable")
    try:
        return str(row[0]), int(row[1]), BODY_ADAPTER.validate_json(row[2])
    except ValidationError as error:
        raise FoundationError("corrupt_space", f"Invalid knowledge state: {error}") from error


def _check_transition(prior: KnowledgeBody, state: KnowledgeBody) -> None:
    if type(prior) is not type(state):
        raise FoundationError("wrong_kind", "Knowledge kind cannot change")
    if isinstance(prior, SourceState):
        raise FoundationError("source_immutable", "A correction is a new primary source")
    if isinstance(prior, ClaimState) and isinstance(state, ClaimState):
        if prior.status in ("superseded", "retracted"):
            raise FoundationError("claim_closed", "A closed Claim remains historical")
        if state.status == "superseded" and state.supersedes is None:
            raise FoundationError("invalid_transition", "Supersession needs an exact linked basis")
    if isinstance(prior, HandoffState) and isinstance(state, HandoffState):
        allowed = {
            "prepared": {"reported_sent", "delivered"},
            "reported_sent": {"delivered", "returned"},
            "delivered": {"returned"},
            "returned": {"matched"},
            "matched": set(),
        }
        if state.status not in allowed[prior.status]:
            raise FoundationError(
                "invalid_transition", "Handoff stages cannot be collapsed or rewound"
            )
        if (
            state.document != prior.document
            or state.included != prior.included
            or state.subject != prior.subject
            or state.expected_return != prior.expected_return
            or state.basis_state_revision != prior.basis_state_revision
            or (
                prior.transfer_source is not None and state.transfer_source != prior.transfer_source
            )
            or (prior.return_source is not None and state.return_source != prior.return_source)
        ):
            raise FoundationError(
                "invalid_transition", "A sent document and its source set stay exact"
            )
        if state.status == "returned" and state.return_source is None:
            raise FoundationError("invalid_transition", "Return needs a separately captured source")
        if state.status in ("reported_sent", "delivered") and state.transfer_source is None:
            raise FoundationError(
                "invalid_transition", "Transfer needs an exact report or receipt source"
            )
        if state.status == "matched" and (not state.match_basis or state.return_source is None):
            raise FoundationError("invalid_transition", "Matching needs source and explicit basis")


def _write_revision(
    connection: sqlite3.Connection,
    request: CreateKnowledgeRequest | ReviseKnowledgeRequest,
    state: KnowledgeBody,
    revision: int,
    now: str,
    state_revision: int,
    epoch: int,
) -> None:
    for _, ref in _refs(state):
        _require_ref(connection, ref, request.actor, epoch)
    if isinstance(state, ContextState):
        if not state.mandatory:
            raise FoundationError(
                "incomplete_context", "Context requires an explicit mandatory set"
            )
        for ref in state.mandatory:
            row = connection.execute(
                "SELECT current_revision FROM knowledge_records WHERE record_id=?",
                (str(ref.record_id),),
            ).fetchone()
            if row is not None and int(row[0]) != ref.revision:
                raise FoundationError("stale_context", "Mandatory knowledge revision changed")
    if isinstance(state, MemoryViewState) and state.coverage_state_revision > state_revision:
        raise FoundationError("stale_revision", "View coverage is from the future")
    if isinstance(state, HandoffState):
        if state.basis_state_revision > state_revision:
            raise FoundationError("stale_revision", "Handoff basis is from the future")
        if state.status == "matched":
            for ref in state.included:
                current = connection.execute(
                    "SELECT current_revision,status FROM knowledge_records WHERE record_id=?",
                    (str(ref.record_id),),
                ).fetchone()
                if current is None:
                    current = connection.execute(
                        "SELECT current_revision,status FROM records WHERE record_id=? UNION ALL "
                        "SELECT current_revision,status FROM subject_records "
                        "WHERE record_id=? LIMIT 1",
                        (str(ref.record_id), str(ref.record_id)),
                    ).fetchone()
                if (
                    current is None
                    or current[0] != ref.revision
                    or current[1] == "deleted"
                    or current[1] == "unavailable"
                ):
                    raise FoundationError("stale_basis", "Handoff input changed before matching")
    payload = state.model_dump_json().encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest().upper()
    if revision == 1:
        collision = connection.execute(
            "SELECT 1 FROM records WHERE record_id=? UNION ALL "
            "SELECT 1 FROM subject_records WHERE record_id=? UNION ALL "
            "SELECT 1 FROM knowledge_records WHERE record_id=? LIMIT 1",
            (str(request.record_id),) * 3,
        ).fetchone()
        if collision is not None:
            raise FoundationError("record_exists", "Knowledge address is already used")
        connection.execute(
            "INSERT INTO knowledge_records(record_id,kind,current_revision,status,received_at,"
            "updated_at,created_state_revision,updated_state_revision) "
            "VALUES (?,?,1,'active',?,?,?,?)",
            (str(request.record_id), state.kind, now, now, state_revision, state_revision),
        )
    else:
        connection.execute(
            "UPDATE knowledge_records SET current_revision=?,updated_at=?,updated_state_revision=? "
            "WHERE record_id=?",
            (revision, now, state_revision, str(request.record_id)),
        )
    connection.execute(
        "INSERT INTO knowledge_revisions(record_id,revision,operation_id,actor,created_at,event_at,"
        "payload,sha256) VALUES (?,?,?,?,?,?,?,?)",
        (
            str(request.record_id),
            revision,
            str(request.operation_id),
            request.actor,
            now,
            state.event_at.isoformat()
            if isinstance(state, SourceState) and state.event_at
            else None,
            payload,
            digest,
        ),
    )
    for index, (role, ref) in enumerate(_refs(state)):
        connection.execute(
            "INSERT INTO knowledge_edges(record_id,revision,ordinal,target_id,"
            "target_revision,role,target_mode) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                str(request.record_id),
                revision,
                index,
                str(ref.record_id),
                ref.revision,
                role,
                state.target_mode
                if isinstance(state, MemoryLinkState) and role == "target"
                else "exact",
            ),
        )
    if isinstance(state, SourceState):
        if state.source_event_id:
            connection.execute(
                "INSERT INTO knowledge_source_events(connection,profile_revision,source_event_id,"
                "record_id) VALUES (?,?,?,?)",
                (
                    state.connection,
                    state.profile_revision,
                    state.source_event_id,
                    str(request.record_id),
                ),
            )
    searchable: str | None = None
    if (
        isinstance(state, SourceState)
        and state.content is not None
        and state.media_type.startswith("text/")
    ):
        try:
            searchable = state.content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise FoundationError("invalid_content", "Text source must be UTF-8") from error
    elif isinstance(state, ClaimState):
        searchable = state.proposition
    elif isinstance(state, AnalysisState):
        searchable = "\n".join(filter(None, (state.task, state.conclusion, state.remainder)))
    elif isinstance(state, MemoryLinkState):
        searchable = state.explanation
    elif isinstance(state, MemoryViewState):
        searchable = state.text
    elif isinstance(state, HandoffState) and state.media_type.startswith("text/"):
        try:
            searchable = state.subject + "\n" + state.document.decode("utf-8")
        except UnicodeDecodeError as error:
            raise FoundationError("invalid_content", "Text handoff must be UTF-8") from error
    if searchable:
        connection.execute(
            "INSERT INTO knowledge_fts(record_id,revision,text) VALUES (?,?,?)",
            (str(request.record_id), revision, searchable),
        )


def _sanitize_deleted(connection: sqlite3.Connection, record_id: UUID, now: str) -> None:
    """Retire dependent copies by provenance, including transitive derived records."""

    affected = {str(record_id)}
    queue = [str(record_id)]
    while queue:
        current = queue.pop()
        rows = connection.execute(
            "SELECT DISTINCT record_id FROM knowledge_edges WHERE target_id=?", (current,)
        ).fetchall()
        for row in rows:
            child = str(row[0])
            if child not in affected:
                affected.add(child)
                queue.append(child)
    for item in affected:
        connection.execute("DELETE FROM knowledge_fts WHERE record_id=?", (item,))
        operation_rows = connection.execute(
            "SELECT operation_id FROM knowledge_revisions WHERE record_id=?", (item,)
        ).fetchall()
        for (operation_id,) in operation_rows:
            connection.execute("DELETE FROM receipts WHERE operation_id=?", (operation_id,))
            connection.execute(
                "UPDATE operations SET fingerprint='DELETED' WHERE operation_id=?", (operation_id,)
            )
        connection.execute(
            "UPDATE knowledge_revisions SET payload=NULL,sha256=NULL WHERE record_id=?", (item,)
        )
        connection.execute(
            "UPDATE knowledge_records SET status=?,updated_at=? WHERE record_id=?",
            ("deleted" if item == str(record_id) else "unavailable", now, item),
        )
    if affected:
        marks = ",".join("?" for _ in affected)
        connection.execute(
            f"UPDATE knowledge_delivery SET stage='unknown',request_sha256=NULL "
            f"WHERE manifest_id IN ({marks})",
            tuple(sorted(affected)),
        )
    # A backup may contain the source or one of its derived payloads. The same
    # quarantine purge used for other managed deletions removes all such copies.
    connection.execute(
        "UPDATE backup_inventory SET status='contaminated' "
        "WHERE status IN ('planned','failed','complete')"
    )


def sanitize_deleted_knowledge_dependency(
    connection: sqlite3.Connection, record_id: UUID, now: str
) -> None:
    """Retire derived payloads after an Artifact, Work or Activity is deleted."""

    found = connection.execute(
        "SELECT 1 FROM knowledge_edges WHERE target_id=? LIMIT 1", (str(record_id),)
    ).fetchone()
    if found is not None:
        _sanitize_deleted(connection, record_id, now)


def apply_knowledge_change(
    connection: sqlite3.Connection,
    request: KnowledgeChange,
    *,
    now: str,
    state_revision: int,
    epoch: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if isinstance(request, RecordContextDeliveryRequest):
        _require_ref(connection, request.manifest, request.actor, epoch)
        kind, current_revision, manifest = _prior_state(connection, request.manifest.record_id)
        if kind != "context" or not isinstance(manifest, ContextState):
            raise FoundationError("wrong_kind", "Delivery needs a ContextManifest")
        if current_revision != request.manifest.revision:
            raise FoundationError("stale_context", "Manifest revision changed")
        if request.stage in ("prepared", "sent"):
            for ref in manifest.mandatory:
                _require_ref(connection, ref, request.actor, epoch)
                knowledge = connection.execute(
                    "SELECT current_revision,status FROM knowledge_records WHERE record_id=?",
                    (str(ref.record_id),),
                ).fetchone()
                if knowledge is not None and (
                    knowledge[0] != ref.revision or knowledge[1] != "active"
                ):
                    raise FoundationError("stale_context", "Mandatory knowledge changed")
                ordinary = connection.execute(
                    "SELECT current_revision,status FROM records WHERE record_id=? UNION ALL "
                    "SELECT current_revision,status FROM subject_records WHERE record_id=? LIMIT 1",
                    (str(ref.record_id), str(ref.record_id)),
                ).fetchone()
                if ordinary is not None and (
                    ordinary[0] != ref.revision or ordinary[1] == "deleted"
                ):
                    raise FoundationError("stale_context", "Mandatory Core record changed")
        old = connection.execute(
            "SELECT manifest_id,manifest_revision,stage,free_call,reserve_units "
            "FROM knowledge_delivery "
            "WHERE invocation_id=?",
            (str(request.invocation_id),),
        ).fetchone()
        order = {"prepared": 0, "sent": 1, "answered": 2, "unknown": 2}
        if old is None:
            if request.stage != "prepared":
                raise FoundationError("invalid_transition", "Delivery starts prepared")
            if request.free_call:
                spent = int(
                    connection.execute(
                        "SELECT COALESCE(SUM(CASE WHEN stage='answered' THEN usage_units "
                        "ELSE reserve_units END),0) FROM knowledge_delivery WHERE free_call=1"
                    ).fetchone()[0]
                )
                if spent + request.reserve_units > request.budget_limit_units:
                    raise FoundationError(
                        "resource_exhausted", "Free conversation model budget is spent"
                    )
            connection.execute(
                "INSERT INTO knowledge_delivery(invocation_id,manifest_id,manifest_revision,stage,"
                "request_sha256,request_bytes,free_call,reserve_units,usage_units,"
                "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(request.invocation_id),
                    str(request.manifest.record_id),
                    request.manifest.revision,
                    request.stage,
                    request.request_sha256,
                    request.request_bytes,
                    int(request.free_call),
                    request.reserve_units,
                    None,
                    now,
                    now,
                ),
            )
        else:
            if old[:2] != (str(request.manifest.record_id), request.manifest.revision):
                raise FoundationError("stale_context", "Invocation cannot change its manifest")
            if bool(old[3]) != request.free_call:
                raise FoundationError("invalid_transition", "Invocation budget class changed")
            if order[request.stage] <= order[old[2]]:
                raise FoundationError("invalid_transition", "Delivery stage must advance")
            connection.execute(
                "UPDATE knowledge_delivery SET stage=?,request_sha256=COALESCE(?,request_sha256),"
                "request_bytes=COALESCE(?,request_bytes),usage_units=?,updated_at=? "
                "WHERE invocation_id=?",
                (
                    request.stage,
                    request.request_sha256,
                    request.request_bytes,
                    request.usage_units,
                    now,
                    str(request.invocation_id),
                ),
            )
        return {"invocation_id": str(request.invocation_id), "stage": request.stage}, [
            {"record_id": str(request.manifest.record_id), "revision": request.manifest.revision}
        ]
    if isinstance(request, DeleteKnowledgeRequest):
        _, revision, _ = _prior_state(connection, request.record_id)
        if revision != request.expected_revision:
            raise FoundationError("stale_revision", "Knowledge revision changed")
        _sanitize_deleted(connection, request.record_id, now)
        new_revision = revision + 1
        connection.execute(
            "UPDATE knowledge_records SET current_revision=?,updated_state_revision=? "
            "WHERE record_id=?",
            (new_revision, state_revision, str(request.record_id)),
        )
        connection.execute(
            "INSERT INTO knowledge_revisions(record_id,revision,operation_id,actor,created_at) "
            "VALUES (?,?,?,?,?)",
            (str(request.record_id), new_revision, str(request.operation_id), request.actor, now),
        )
        connection.execute(
            "INSERT INTO knowledge_deletion_jobs(operation_id,record_id,status,created_at) "
            "VALUES (?,?,'pending',?)",
            (str(request.operation_id), str(request.record_id), now),
        )
        return {
            "record_id": str(request.record_id),
            "revision": new_revision,
            "content": "unavailable",
            "deletion": "pending",
        }, [{"record_id": str(request.record_id), "revision": new_revision}]
    state = request.state
    if isinstance(request, CreateKnowledgeRequest):
        revision = 1
        if isinstance(state, HandoffState) and state.status != "prepared":
            raise FoundationError("invalid_transition", "Handoff starts with a prepared document")
        if isinstance(state, SourceState) and state.source_event_id:
            existing = connection.execute(
                "SELECT record_id FROM knowledge_source_events WHERE connection=? "
                "AND profile_revision=? AND source_event_id=?",
                (state.connection, state.profile_revision, state.source_event_id),
            ).fetchone()
            if existing is not None:
                raise FoundationError(
                    "duplicate_source", f"Source event already captured as {existing[0]}"
                )
    else:
        _, prior_revision, prior = _prior_state(connection, request.record_id)
        if prior_revision != request.expected_revision:
            raise FoundationError("stale_revision", "Knowledge revision changed")
        _check_transition(prior, state)
        revision = prior_revision + 1
    _write_revision(connection, request, state, revision, now, state_revision, epoch)
    return {"record_id": str(request.record_id), "revision": revision}, [
        {"record_id": str(request.record_id), "revision": revision}
    ]


def _checked_read(
    connection: sqlite3.Connection,
    info: SpaceInfo,
    authority: LocalAuthority,
    record_id: UUID,
    revision: int | None,
) -> KnowledgeRevision:
    _local_space(authority, info)
    _authorize(
        connection,
        actor=authority.actor,
        action="record.read",
        epoch=info.execution_epoch,
        resource_type="artifact",
        resource_id=record_id,
    )
    row = (
        connection.execute(
            "SELECT r.kind,r.current_revision,r.status,r.received_at,v.revision,v.operation_id,"
            "v.actor,v.created_at,v.payload,v.sha256 FROM knowledge_records r "
            "JOIN knowledge_revisions v ON v.record_id=r.record_id AND v.revision=? "
            "WHERE r.record_id=?",
            (revision if revision is not None else -1, str(record_id)),
        ).fetchone()
        if revision is not None
        else connection.execute(
            "SELECT r.kind,r.current_revision,r.status,r.received_at,v.revision,v.operation_id,"
            "v.actor,v.created_at,v.payload,v.sha256 FROM knowledge_records r "
            "JOIN knowledge_revisions v ON v.record_id=r.record_id "
            "AND v.revision=r.current_revision WHERE r.record_id=?",
            (str(record_id),),
        ).fetchone()
    )
    if row is None:
        raise FoundationError("not_found", "Knowledge address is absent")
    payload = row[8]
    if payload is not None and hashlib.sha256(payload).hexdigest().upper() != row[9]:
        raise FoundationError("corrupt_space", "Knowledge payload digest mismatch")
    state = BODY_ADAPTER.validate_json(payload) if payload is not None else None
    stale = int(row[1]) != int(row[4])
    if state is not None:
        for role, ref in _refs(state):
            target = connection.execute(
                "SELECT status,current_revision FROM knowledge_records WHERE record_id=?",
                (str(ref.record_id),),
            ).fetchone()
            if target is None:
                target = connection.execute(
                    "SELECT status,current_revision FROM records WHERE record_id=? UNION ALL "
                    "SELECT status,current_revision FROM subject_records WHERE record_id=? LIMIT 1",
                    (str(ref.record_id), str(ref.record_id)),
                ).fetchone()
            follows_current = (
                isinstance(state, MemoryLinkState)
                and role == "target"
                and state.target_mode == "current"
            )
            if (
                target is None
                or target[0] in ("deleted", "unavailable")
                or (target[1] != ref.revision and not follows_current)
            ):
                stale = True
        if isinstance(state, MemoryViewState) and state.mode == "current":
            if _read_scope_limited(connection, info, authority):
                stale = True
            else:
                newer = connection.execute(
                    "SELECT v.payload FROM knowledge_records r JOIN knowledge_revisions v "
                    "ON v.record_id=r.record_id AND v.revision=r.current_revision "
                    "WHERE r.status='active' AND r.kind IN ('source','claim') "
                    "AND r.updated_state_revision>?",
                    (state.coverage_state_revision,),
                )
                for (new_payload,) in newer:
                    candidate = BODY_ADAPTER.validate_json(new_payload)
                    matches = False
                    if state.scope_kind == "space":
                        matches = True
                    elif isinstance(candidate, SourceState):
                        matches = (
                            (
                                state.scope_kind == "conversation"
                                and candidate.conversation_id == state.scope_id
                            )
                            or (
                                state.scope_kind == "activity"
                                and str(candidate.scope_activity_id) == state.scope_id
                            )
                            or (
                                state.scope_kind == "work"
                                and str(candidate.scope_work_id) == state.scope_id
                            )
                        )
                    elif isinstance(candidate, ClaimState):
                        matches = (
                            state.scope_kind == "activity"
                            and (
                                candidate.scope_global
                                or str(candidate.scope_activity_id) == state.scope_id
                            )
                        ) or (
                            state.scope_kind == "work"
                            and (candidate.scope_global or candidate.scope_activity_id is not None)
                        )
                    stale = stale or matches
                    if stale:
                        break
    return KnowledgeRevision(
        record_id=record_id,
        kind=row[0],
        revision=row[4],
        operation_id=UUID(row[5]),
        received_at=datetime.fromisoformat(row[3]),
        created_at=datetime.fromisoformat(row[7]),
        actor=row[6],
        state=state,
        sha256=row[9],
        availability="deleted"
        if row[2] == "deleted"
        else "unavailable"
        if payload is None
        else "available",
        stale=stale,
    )


def read_knowledge(
    path: Path,
    record_id: UUID,
    authority: LocalAuthority,
    *,
    revision: int | None = None,
) -> KnowledgeRevision:
    with space_connection(path) as (connection, info):
        if info.schema_version < 10 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Knowledge reads need active schema 10")
        return _checked_read(connection, info, authority, record_id, revision)


def _read_scope_limited(
    connection: sqlite3.Connection, info: SpaceInfo, authority: LocalAuthority
) -> bool:
    """Describe the actor's scope without testing whether hidden rows exist."""

    try:
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
        )
    except FoundationError as error:
        if error.code in ("permission_denied", "decision_denied"):
            return True
        raise
    return False


def open_knowledge(
    path: Path,
    record_id: UUID,
    authority: LocalAuthority,
    *,
    revision: int | None = None,
    offset: int = 0,
    max_bytes: int = 16384,
) -> dict[str, object]:
    """Open exact retained bytes with an explicit continuation and availability."""

    if offset < 0 or not 1 <= max_bytes <= 65536:
        raise FoundationError("invalid_request", "Open needs a finite byte window")
    item = read_knowledge(path, record_id, authority, revision=revision)
    if item.state is None:
        return {
            "record_id": str(record_id),
            "revision": item.revision,
            "availability": item.availability,
            "stale": item.stale,
            "content": None,
            "next_offset": None,
        }
    state = item.state
    field: str | None = None
    content: bytes | None = None
    if isinstance(state, SourceState):
        field, content = "content", state.content
    elif isinstance(state, HandoffState):
        field, content = "document", state.document
    elif isinstance(state, MemoryViewState):
        field, content = "text", state.text.encode("utf-8")
    elif isinstance(state, ClaimState):
        field, content = "proposition", state.proposition.encode("utf-8")
    elif isinstance(state, AnalysisState) and state.conclusion is not None:
        field, content = "conclusion", state.conclusion.encode("utf-8")
    metadata = state.model_dump(mode="json", exclude={field} if field else None)
    if content is None:
        return {
            "record_id": str(record_id),
            "revision": item.revision,
            "availability": item.availability,
            "stale": item.stale,
            "state": metadata,
            "content": None,
            "next_offset": None,
        }
    if offset > len(content):
        raise FoundationError("invalid_request", "Open offset exceeds exact content")
    end = min(offset + max_bytes, len(content))
    if isinstance(state, (SourceState, HandoffState)) and state.media_type.startswith("text/"):
        while end < len(content):
            try:
                content[offset:end].decode("utf-8")
                break
            except UnicodeDecodeError:
                end -= 1
        if end == offset and offset < len(content):
            raise FoundationError("invalid_request", "Window cannot hold a UTF-8 character")
    chunk = content[offset:end]
    return {
        "record_id": str(record_id),
        "revision": item.revision,
        "availability": item.availability,
        "stale": item.stale,
        "state": metadata,
        "field": field,
        "offset": offset,
        "total_bytes": len(content),
        "content_base64": base64.b64encode(chunk).decode("ascii"),
        "content_sha256": hashlib.sha256(content).hexdigest().upper(),
        "next_offset": end if end < len(content) else None,
    }


def list_knowledge(
    path: Path,
    authority: LocalAuthority,
    *,
    kind: str | None = None,
    received_from: datetime | None = None,
    event_from: datetime | None = None,
    limit: int = 25,
    cursor: str | None = None,
) -> dict[str, object]:
    if not 1 <= limit <= 100:
        raise FoundationError("invalid_request", "Page size must be 1..100")
    with space_connection(path) as (connection, info):
        if info.schema_version < 10 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Knowledge listing needs schema 10")
        _local_space(authority, info)
        try:
            after = "" if cursor is None else str(UUID(cursor))
        except ValueError as error:
            raise FoundationError(
                "invalid_cursor", "List cursor is not a record address"
            ) from error
        query = (
            "SELECT r.record_id,r.kind,r.current_revision,r.received_at "
            "FROM knowledge_records r JOIN knowledge_revisions v ON v.record_id=r.record_id "
            "AND v.revision=r.current_revision WHERE r.status='active' "
            "AND r.record_id>?"
        )
        params: list[object] = [after]
        if kind is not None:
            query += " AND r.kind=?"
            params.append(kind)
        if received_from is not None:
            query += " AND r.received_at>=?"
            params.append(received_from.isoformat())
        if event_from is not None:
            query += " AND v.event_at>=?"
            params.append(event_from.isoformat())
        query += " ORDER BY r.record_id"
        entries: list[dict[str, object]] = []
        restricted = _read_scope_limited(connection, info, authority)
        more = False
        for row in connection.execute(query, params):
            try:
                _authorize(
                    connection,
                    actor=authority.actor,
                    action="record.read",
                    epoch=info.execution_epoch,
                    resource_type="artifact",
                    resource_id=UUID(row[0]),
                )
            except FoundationError as error:
                if error.code in ("permission_denied", "decision_denied"):
                    continue
                raise
            if len(entries) >= limit:
                more = True
                break
            entries.append(
                {
                    "record_id": row[0],
                    "kind": row[1],
                    "revision": row[2],
                    "received_at": row[3],
                }
            )
        next_cursor = str(entries[-1]["record_id"]) if more and entries else None
        return {
            "items": entries,
            "next_cursor": next_cursor,
            "restricted": restricted,
            "complete": not more and not restricted,
            "consistency": "live; restart listing to include concurrent earlier addresses",
        }


def search_knowledge(
    path: Path,
    authority: LocalAuthority,
    query: str,
    *,
    limit: int = 25,
    cursor: str | None = None,
) -> dict[str, object]:
    if not query.strip() or not 1 <= limit <= 100:
        raise FoundationError("invalid_request", "Search needs text, a page and a valid cursor")
    with space_connection(path) as (connection, info):
        if info.schema_version < 10 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Text search needs schema 10")
        _local_space(authority, info)
        after_rowid = 0
        cursor_query = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
        if cursor is not None:
            parts = cursor.split(":")
            if len(parts) != 3 or parts[2] != cursor_query:
                raise FoundationError("invalid_cursor", "Search cursor differs from this query")
            try:
                visible_id, visible_revision = UUID(parts[0]), int(parts[1])
            except ValueError as error:
                raise FoundationError("invalid_cursor", "Search cursor is malformed") from error
            _authorize(
                connection,
                actor=authority.actor,
                action="record.read",
                epoch=info.execution_epoch,
                resource_type="artifact",
                resource_id=visible_id,
            )
            position = connection.execute(
                "SELECT rowid FROM knowledge_fts WHERE record_id=? AND revision=?",
                (str(visible_id), visible_revision),
            ).fetchone()
            if position is None:
                raise FoundationError("invalid_cursor", "Search cursor source is unavailable")
            after_rowid = int(position[0])
        try:
            rows = connection.execute(
                "SELECT rowid,record_id,revision,snippet(knowledge_fts,2,'[',']','…',12) "
                "FROM knowledge_fts WHERE knowledge_fts MATCH ? AND rowid>? ORDER BY rowid",
                (query, after_rowid),
            ).fetchall()
        except sqlite3.OperationalError as error:
            raise FoundationError("invalid_query", str(error)) from error
        entries: list[dict[str, object]] = []
        restricted = _read_scope_limited(connection, info, authority)
        more = False
        last_visible: tuple[str, int] | None = None
        for row in rows:
            try:
                _authorize(
                    connection,
                    actor=authority.actor,
                    action="record.read",
                    epoch=info.execution_epoch,
                    resource_type="artifact",
                    resource_id=UUID(row[1]),
                )
            except FoundationError as error:
                if error.code in ("permission_denied", "decision_denied"):
                    continue
                raise
            if len(entries) >= limit:
                more = True
                break
            current = connection.execute(
                "SELECT current_revision,status FROM knowledge_records WHERE record_id=?",
                (row[1],),
            ).fetchone()
            if current is None or current[1] != "active":
                continue
            entries.append(
                {
                    "record_id": row[1],
                    "revision": row[2],
                    "match": row[3],
                    "stale": int(current[0]) != int(row[2]),
                }
            )
            last_visible = (str(row[1]), int(row[2]))
        return {
            "items": entries,
            "next_cursor": (
                f"{last_visible[0]}:{last_visible[1]}:{cursor_query}"
                if more and last_visible is not None
                else None
            ),
            "restricted": restricted,
            "coverage": "retained UTF-8 source and knowledge revisions",
            "complete": not more and not restricted,
        }


def read_knowledge_neighbors(
    path: Path,
    record_id: UUID,
    authority: LocalAuthority,
    *,
    limit: int = 25,
    cursor: str | None = None,
) -> dict[str, object]:
    if not 1 <= limit <= 100:
        raise FoundationError("invalid_request", "Invalid neighbor page")
    with space_connection(path) as (connection, info):
        try:
            _checked_read(connection, info, authority, record_id, None)
        except FoundationError as error:
            if error.code != "not_found":
                raise
            kind = connection.execute(
                "SELECT kind FROM subject_records WHERE record_id=?", (str(record_id),)
            ).fetchone()
            _authorize(
                connection,
                actor=authority.actor,
                action="record.read",
                epoch=info.execution_epoch,
                resource_type=kind[0] if kind is not None else "artifact",
                resource_id=record_id,
            )
            ordinary = connection.execute(
                "SELECT 1 FROM records WHERE record_id=? UNION ALL "
                "SELECT 1 FROM subject_records WHERE record_id=? LIMIT 1",
                (str(record_id), str(record_id)),
            ).fetchone()
            if ordinary is None:
                raise FoundationError("not_found", "Neighbor address is absent") from None
        after_rowid = 0
        if cursor is not None:
            parts = cursor.split(":")
            if len(parts) != 3:
                raise FoundationError("invalid_cursor", "Neighbor cursor is malformed")
            try:
                source_id, source_revision, ordinal = UUID(parts[0]), int(parts[1]), int(parts[2])
            except ValueError as error:
                raise FoundationError("invalid_cursor", "Neighbor cursor is malformed") from error
            position = connection.execute(
                "SELECT rowid,target_id FROM knowledge_edges WHERE record_id=? "
                "AND revision=? AND ordinal=? AND (record_id=? OR target_id=?)",
                (str(source_id), source_revision, ordinal, str(record_id), str(record_id)),
            ).fetchone()
            if position is None:
                raise FoundationError("invalid_cursor", "Neighbor cursor is unavailable")
            other_id = source_id if source_id != record_id else UUID(position[1])
            other_kind = connection.execute(
                "SELECT kind FROM subject_records WHERE record_id=?", (str(other_id),)
            ).fetchone()
            _authorize(
                connection,
                actor=authority.actor,
                action="record.read",
                epoch=info.execution_epoch,
                resource_type=other_kind[0] if other_kind is not None else "artifact",
                resource_id=other_id,
            )
            after_rowid = int(position[0])
        rows = connection.execute(
            "SELECT e.rowid,e.record_id,e.revision,e.target_id,e.target_revision,"
            "e.role,e.target_mode,r.kind,v.payload,e.ordinal "
            "FROM knowledge_edges e JOIN knowledge_records r ON r.record_id=e.record_id "
            "JOIN knowledge_revisions v ON v.record_id=e.record_id AND v.revision=e.revision "
            "WHERE (e.record_id=? OR e.target_id=?) AND e.rowid>? "
            "AND e.revision=r.current_revision AND r.status='active' ORDER BY e.rowid",
            (str(record_id), str(record_id), after_rowid),
        ).fetchall()
        entries: list[dict[str, object]] = []
        restricted = _read_scope_limited(connection, info, authority)
        last_visible: tuple[str, int, int] | None = None
        more = False
        for row in rows:
            if row[7] == "link":
                link = BODY_ADAPTER.validate_json(row[8])
                if isinstance(link, MemoryLinkState) and link.status == "retired":
                    continue
            other = UUID(row[3] if row[1] == str(record_id) else row[1])
            other_kind = connection.execute(
                "SELECT kind FROM subject_records WHERE record_id=?", (str(other),)
            ).fetchone()
            try:
                _authorize(
                    connection,
                    actor=authority.actor,
                    action="record.read",
                    epoch=info.execution_epoch,
                    resource_type=other_kind[0] if other_kind is not None else "artifact",
                    resource_id=other,
                )
            except FoundationError as error:
                if error.code in ("permission_denied", "decision_denied"):
                    continue
                raise
            if len(entries) >= limit:
                more = True
                break
            target_revision = int(row[4])
            if row[6] == "current":
                target = connection.execute(
                    "SELECT current_revision,status FROM knowledge_records WHERE record_id=? "
                    "UNION ALL SELECT current_revision,status FROM records WHERE record_id=? "
                    "UNION ALL SELECT current_revision,status FROM subject_records "
                    "WHERE record_id=? LIMIT 1",
                    (row[3], row[3], row[3]),
                ).fetchone()
                if target is None or target[1] in ("deleted", "unavailable"):
                    continue
                target_revision = int(target[0])
            entries.append(
                {
                    "from": f"{row[1]}@{row[2]}",
                    "to": f"{row[3]}@{target_revision}",
                    "relation": row[5],
                    "target_mode": row[6],
                    "pinned_target": f"{row[3]}@{row[4]}" if row[6] == "current" else None,
                }
            )
            last_visible = (str(row[1]), int(row[2]), int(row[9]))
        return {
            "items": entries,
            "next_cursor": (
                f"{last_visible[0]}:{last_visible[1]}:{last_visible[2]}"
                if more and last_visible is not None
                else None
            ),
            "restricted": restricted,
            "complete": not more and not restricted,
        }


def read_context_delivery(
    path: Path,
    invocation_id: UUID,
    authority: LocalAuthority,
) -> dict[str, object]:
    with space_connection(path) as (connection, info):
        if info.schema_version < 10:
            raise FoundationError("unsupported_schema", "Context delivery needs schema 10")
        _local_space(authority, info)
        row = connection.execute(
            "SELECT manifest_id,manifest_revision,stage,request_sha256,request_bytes "
            "FROM knowledge_delivery WHERE invocation_id=?",
            (str(invocation_id),),
        ).fetchone()
        if row is None:
            raise FoundationError("not_found", "No delivered context for invocation")
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="artifact",
            resource_id=UUID(row[0]),
        )
        return {
            "invocation_id": str(invocation_id),
            "manifest_id": row[0],
            "manifest_revision": row[1],
            "stage": row[2],
            "request_sha256": row[3],
            "request_bytes": row[4],
        }


def read_current_rights(path: Path, authority: LocalAuthority) -> dict[str, object]:
    """Show the actor's current epoch-bound Grants without changing admission."""

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        _authorize(
            connection, actor=authority.actor, action="record.read", epoch=info.execution_epoch
        )
        rows = connection.execute(
            "SELECT r.record_id,r.current_revision,v.body_json FROM records r "
            "JOIN record_revisions v ON v.record_id=r.record_id "
            "AND v.revision=r.current_revision WHERE r.kind='grant' ORDER BY r.record_id"
        ).fetchall()
        grants: list[dict[str, object]] = []
        for record_id, revision, raw in rows:
            body = json.loads(raw)
            state = GrantState.model_validate(body["state"])
            if (
                state.status != "active"
                or state.grantee != authority.actor
                or (int(body["epoch"]) != info.execution_epoch)
            ):
                continue
            grants.append(
                {
                    "record_id": record_id,
                    "revision": revision,
                    "state": state.model_dump(mode="json"),
                }
            )
        return {"actor": authority.actor, "epoch": info.execution_epoch, "grants": grants}
