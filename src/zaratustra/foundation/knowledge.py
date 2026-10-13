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
    ActivityStructureState,
    AnalysisState,
    ClaimState,
    ContextState,
    CreateKnowledgeRequest,
    DataEntryState,
    DataFormatState,
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
    DELIVERY_CORRELATION_SCHEMA_NAME,
    DELIVERY_CORRELATION_SCHEMA_SHA256,
    DELIVERY_CORRELATION_SCHEMA_STATEMENTS,
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


def _context_correlation(context: ContextState) -> tuple[str | None, str | None, str, str]:
    if context.attempt_id is not None and context.work_id is None:
        raise FoundationError("invalid_delivery_correlation", "Attempt context requires its Work")
    return (
        str(context.work_id) if context.work_id else None,
        str(context.attempt_id) if context.attempt_id else None,
        str(context.session_id),
        "exact" if context.attempt_id else "not_attempt",
    )


def _execution_correlation(
    connection: sqlite3.Connection,
    invocation: str,
) -> tuple[str, str, str, str] | None:
    row = connection.execute(
        "SELECT work_id,attempt_id,session_id FROM execution_invocations WHERE invocation_id=?",
        (invocation,),
    ).fetchone()
    return (*row, "exact") if row else None


def _context_matches_exact_correlation(
    context: ContextState,
    pin: tuple[str | None, str | None, str | None, str],
) -> bool:
    """Missing legacy optional fields do not contradict exact domain accounting."""
    return (
        (context.work_id is None or str(context.work_id) == pin[0])
        and (context.attempt_id is None or str(context.attempt_id) == pin[1])
        and str(context.session_id) == pin[2]
    )


def upgrade_delivery_correlation_space(path: Path, authority: LocalAuthority) -> SpaceInfo:
    """Explicit 17 to 18 upgrade; exact delivery pins survive manifest sanitation."""
    with space_connection(path, writable=True) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active" or info.schema_version < 17:
            raise FoundationError("upgrade_required", "Delivery correlation needs active schema 17")
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.backup",
            epoch=info.execution_epoch,
        )
        if info.schema_version == 17:
            for statement in DELIVERY_CORRELATION_SCHEMA_STATEMENTS:
                connection.execute(statement)
            unresolved = False
            for invocation, payload, stage in connection.execute(
                "SELECT d.invocation_id,r.payload,d.stage FROM knowledge_delivery d "
                "LEFT JOIN knowledge_revisions r ON r.record_id=d.manifest_id "
                "AND r.revision=d.manifest_revision ORDER BY d.invocation_id",
            ):
                try:
                    context = ContextState.model_validate_json(payload) if payload else None
                except ValidationError as error:
                    raise FoundationError(
                        "invalid_delivery_correlation",
                        f"Invalid retained Context for invocation {invocation}",
                    ) from error
                execution_pin = _execution_correlation(connection, invocation)
                if (
                    context is not None
                    and execution_pin is not None
                    and not _context_matches_exact_correlation(context, execution_pin)
                ):
                    raise FoundationError(
                        "delivery_correlation_conflict", "Manifest and execution pins disagree"
                    )
                pin = execution_pin or (
                    _context_correlation(context)
                    if context is not None
                    else (None, None, None, "unresolved_legacy")
                )
                connection.execute(
                    "UPDATE knowledge_delivery SET context_work_id=?,context_attempt_id=?,"
                    "context_session_id=?,correlation_state=? WHERE invocation_id=?",
                    (*pin, invocation),
                )
                unresolved |= pin[3] == "unresolved_legacy" and stage != "prepared"
            if unresolved:
                connection.execute(
                    "UPDATE execution_attempts SET legacy_delivery_correlation_uncertain=1 "
                    "WHERE status='active'",
                )
            now = utc_now().isoformat()
            connection.execute(
                "INSERT INTO schema_migrations VALUES (18,?,?,?)",
                (DELIVERY_CORRELATION_SCHEMA_NAME, DELIVERY_CORRELATION_SCHEMA_SHA256, now),
            )
            connection.execute("PRAGMA user_version=18")
            connection.execute(
                "UPDATE spaces SET state_revision=state_revision+1 WHERE singleton=1"
            )
            connection.execute(
                "INSERT INTO maintenance_events VALUES (?,'schema_upgrade',?,?)",
                (str(uuid4()), now, canonical_json({"from": 17, "to": 18})),
            )
    return read_space(path)


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


def _refs(
    state: KnowledgeBody, connection: sqlite3.Connection | None = None
) -> list[tuple[str, KnowledgeRef]]:
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
        return (
            [("mandatory", ref) for ref in state.mandatory]
            + [("optional", ref) for ref in state.optional]
            + [("memory_snapshot", ref) for ref in state.historical_memory]
            + ([("structure_pin", state.pinned_structure)] if state.pinned_structure else [])
            + (
                [("procedure_snapshot", state.procedure_snapshot)]
                if state.procedure_snapshot
                else []
            )
        )
    if isinstance(state, DataEntryState):
        from .data_store import data_references

        if connection is None:
            raise FoundationError("invalid_request", "Data references need their database resolver")
        return data_references(connection, state)
    if isinstance(state, DataFormatState):
        return []
    if isinstance(state, ActivityStructureState):
        return [("structure_basis", ref) for ref in state.bases] + [
            ("structure_format", ref) for ref in state.formats.values()
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
        "SELECT r.status,v.payload IS NOT NULL,r.kind FROM knowledge_records r "
        "JOIN knowledge_revisions v ON v.record_id=r.record_id "
        "WHERE r.record_id=? AND v.revision=?",
        (str(ref.record_id), ref.revision),
    ).fetchone()
    if row is not None:
        retained_typed_revision = row[0] == "unavailable" and row[2] in (
            "data_format",
            "data_entry",
            "activity_structure",
        )
        if (row[0] != "active" and not retained_typed_revision) or not row[1]:
            raise FoundationError(
                "content_unavailable", f"Knowledge basis {ref.record_id}@{ref.revision}"
            )
        if ref.end is not None:
            payload = connection.execute(
                "SELECT payload FROM knowledge_revisions WHERE record_id=? AND revision=?",
                (str(ref.record_id), ref.revision),
            ).fetchone()[0]
            referenced = BODY_ADAPTER.validate_json(payload)
            content = (
                referenced.content
                if isinstance(referenced, SourceState)
                else referenced.document
                if isinstance(referenced, HandoffState)
                else referenced.text.encode("utf-8")
                if isinstance(referenced, MemoryViewState)
                else None
            )
            if content is None or ref.end > len(content):
                raise FoundationError("invalid_fragment", "Fragment exceeds retained source bytes")
        return
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 11:
        development = connection.execute(
            "SELECT r.status,v.payload FROM development_records r "
            "JOIN development_revisions v ON v.record_id=r.record_id "
            "WHERE r.record_id=? AND v.revision=?",
            (str(ref.record_id), ref.revision),
        ).fetchone()
        if development is not None:
            if development[0] != "active" or development[1] is None:
                raise FoundationError("content_unavailable", "Development basis is unavailable")
            if ref.start is not None:
                raise FoundationError("invalid_fragment", "Development basis has no byte fragments")
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
    if isinstance(prior, (DataEntryState, DataFormatState, ActivityStructureState)) and (
        prior.scope_activity_id != getattr(state, "scope_activity_id", None)
    ):
        raise FoundationError("wrong_scope", "Data origin cannot change through a correction")
    if (
        isinstance(prior, DataEntryState)
        and isinstance(state, DataEntryState)
        and (
            (prior.external_namespace, prior.external_key)
            != (state.external_namespace, state.external_key)
        )
    ):
        raise FoundationError("identity_changed", "Correction keeps the external event identity")
    if isinstance(prior, SourceState):
        if (
            isinstance(state, SourceState)
            and prior.memory != state.memory
            and (prior.model_dump(exclude={"memory"}) == state.model_dump(exclude={"memory"}))
        ):
            return
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
    schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if schema >= 15:
        from .data_store import validate_data_state

        state = validate_data_state(connection, state, request.actor, epoch)
    if isinstance(state, MemoryViewState) and (
        state.selection is not None or state.generation_method == "zaratustra.memory/1"
    ):
        from .memory import COMPILING_SELECTION

        if not COMPILING_SELECTION.get():
            raise FoundationError("permission_denied", "Use the Core memory selection compiler")
    if schema < 13 and (
        getattr(state, "memory", None) is not None
        or (isinstance(state, MemoryViewState) and state.selection is not None)
        or (isinstance(state, ContextState) and state.historical_memory)
    ):
        raise FoundationError("unsupported_schema", "Memory organization needs schema 13")
    if (
        isinstance(state, MemoryViewState)
        and state.selection is not None
        and (state.selection.actor != request.actor or state.selection.epoch != epoch)
    ):
        raise FoundationError("permission_denied", "Selection actor/epoch must match its creator")
    for _, ref in _refs(state, connection):
        _require_ref(connection, ref, request.actor, epoch)
    metadata = getattr(state, "memory", None)
    memory_scope = None
    if metadata is not None and metadata.activity_id is not None:
        memory_scope = connection.execute(
            "SELECT current_revision FROM subject_records "
            "WHERE record_id=? AND kind='activity' AND status!='deleted'",
            (str(metadata.activity_id),),
        ).fetchone()
        if memory_scope is None:
            raise FoundationError("not_found", "Memory Activity is absent or deleted")
        _authorize(
            connection,
            actor=request.actor,
            action="record.read",
            epoch=epoch,
            resource_type="activity",
            resource_id=metadata.activity_id,
        )
    if isinstance(state, ContextState):
        from .data_store import check_context_pins

        check_context_pins(connection, state, request.actor, epoch)
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
        for ref in state.historical_memory:
            _, _, historic = _prior_state(connection, ref.record_id)
            if not isinstance(historic, MemoryViewState) or historic.selection is None:
                raise FoundationError("wrong_kind", "Historical memory needs a compiled selection")
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
    for index, (role, ref) in enumerate(_refs(state, connection)):
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
                else "current"
                if role == "data_current"
                else "exact",
            ),
        )
    if memory_scope is not None and metadata is not None:
        connection.execute(
            "INSERT INTO knowledge_edges VALUES (?,?,?,?,?,?,'exact')",
            (
                str(request.record_id),
                revision,
                len(_refs(state, connection)),
                str(metadata.activity_id),
                memory_scope[0],
                "memory_scope",
            ),
        )
    if isinstance(state, SourceState) and revision == 1:
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
    elif isinstance(state, (DataFormatState, DataEntryState, ActivityStructureState)):
        searchable = canonical_json(state.model_dump(mode="json"))
    elif isinstance(state, HandoffState) and state.media_type.startswith("text/"):
        try:
            searchable = state.subject + "\n" + state.document.decode("utf-8")
        except UnicodeDecodeError as error:
            raise FoundationError("invalid_content", "Text handoff must be UTF-8") from error
    metadata = getattr(state, "memory", None)
    if metadata is not None:
        searchable = "\n".join(
            filter(
                None,
                (
                    searchable,
                    metadata.title,
                    " ".join(metadata.topics),
                    " ".join(metadata.aliases),
                ),
            )
        )
    if searchable:
        connection.execute(
            "INSERT INTO knowledge_fts(record_id,revision,text) VALUES (?,?,?)",
            (str(request.record_id), revision, searchable),
        )
    if schema >= 13:
        from .memory import index_memory

        index_memory(connection, request.record_id, state, revision, state_revision)
    if schema >= 15:
        from .data_store import index_data

        index_data(connection, request.record_id, state, revision)


def _sanitize_deleted(connection: sqlite3.Connection, record_id: UUID, now: str) -> None:
    """Retire dependent copies by provenance, including transitive derived records."""
    from .workflows import sanitize_workflow_dependency

    sanitize_workflow_dependency(connection, record_id, now)
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 14:
        from .activity_setup import sanitize_setup_dependency

        sanitize_setup_dependency(connection, record_id, now)
    affected = {str(record_id)}
    queue = [str(record_id)]
    while queue:
        current = queue.pop()
        rows = connection.execute(
            "SELECT DISTINCT record_id,revision FROM knowledge_edges WHERE target_id=?", (current,)
        ).fetchall()
        for row in rows:
            child = str(row[0])
            if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 15:
                kind = connection.execute(
                    "SELECT kind FROM knowledge_records WHERE record_id=?", (child,)
                ).fetchone()
                if kind and kind[0] in ("data_entry", "data_format", "activity_structure"):
                    from .data_store import sanitize_data_revision

                    sanitize_data_revision(
                        connection, KnowledgeRef(record_id=UUID(child), revision=row[1]), now
                    )
                    continue
            if child not in affected:
                affected.add(child)
                queue.append(child)
        if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 15:
            for (child,) in connection.execute(
                "SELECT DISTINCT artifact_id FROM data_artifact_bases WHERE target_id=? UNION "
                "SELECT record_id FROM revision_provenance WHERE source_record_id=?",
                (current, current),
            ):
                if child not in affected:
                    affected.add(child)
                    queue.append(child)
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 11:
        from .development import sanitize_deleted_development_dependency

        for item in affected:
            sanitize_deleted_development_dependency(connection, UUID(item), now)
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 15:
        from .data_store import sanitize_data_dependency

        sanitize_data_dependency(connection, affected, now)
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 17:
        from .conversations import sanitize_conversation_dependency

        sanitize_conversation_dependency(connection, affected, now)
    for item in affected:
        connection.execute("DELETE FROM knowledge_fts WHERE record_id=?", (item,))
        if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 13:
            connection.execute("DELETE FROM memory_topics WHERE record_id=?", (item,))
            connection.execute("DELETE FROM memory_index WHERE record_id=?", (item,))
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
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 13:
        from .memory import refresh_intake

        refresh_intake(connection)
    if affected:
        marks = ",".join("?" for _ in affected)
        connection.execute(
            f"UPDATE knowledge_delivery SET stage='unknown',request_sha256=NULL "
            f"WHERE manifest_id IN ({marks})",
            tuple(sorted(affected)),
        )
    # A snapshot older than every affected record cannot contain its payload.
    # Keep those known-clean recovery points; conservatively quarantine later
    # snapshots, which may contain a source or any of its derived payloads.
    marks = ",".join("?" for _ in affected)
    earliest = connection.execute(
        f"SELECT MIN(created_state_revision) FROM knowledge_records WHERE record_id IN ({marks})",
        tuple(sorted(affected)),
    ).fetchone()[0]
    if earliest is not None:
        connection.execute(
            "UPDATE backup_inventory SET status='contaminated' "
            "WHERE status IN ('planned','failed','complete') AND state_revision >= ?",
            (earliest,),
        )


def sanitize_deleted_knowledge_dependency(
    connection: sqlite3.Connection, record_id: UUID, now: str
) -> None:
    """Retire derived payloads after an Artifact, Work or Activity is deleted."""
    from .workflows import sanitize_workflow_dependency

    sanitize_workflow_dependency(connection, record_id, now)
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 17:
        from .conversations import sanitize_conversation_dependency

        sanitize_conversation_dependency(connection, {str(record_id)}, now)

    if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 14:
        from .activity_setup import sanitize_setup_dependency

        sanitize_setup_dependency(connection, record_id, now)
    found = connection.execute(
        "SELECT 1 FROM knowledge_edges WHERE target_id=? LIMIT 1", (str(record_id),)
    ).fetchone()
    if found is None and int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 15:
        found = connection.execute(
            "SELECT 1 FROM data_artifact_bases WHERE target_id=? UNION ALL "
            "SELECT 1 FROM revision_provenance WHERE source_record_id=? LIMIT 1",
            (str(record_id), str(record_id)),
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
            from .conversations import check_conversation_context

            check_conversation_context(connection, manifest, request.actor, epoch)
            from .data_store import check_context_pins

            check_context_pins(connection, manifest, request.actor, epoch)
            for ref in dict.fromkeys(manifest.mandatory + manifest.historical_memory):
                _require_ref(connection, ref, request.actor, epoch)
                if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 13:
                    _, _, selected = (
                        _prior_state(connection, ref.record_id)
                        if connection.execute(
                            "SELECT 1 FROM knowledge_records WHERE record_id=?",
                            (str(ref.record_id),),
                        ).fetchone()
                        else (None, None, None)
                    )
                    if (
                        isinstance(selected, MemoryViewState)
                        and selected.generation_method == "zaratustra.memory/1"
                    ):
                        # Recheck copied originals even for an explicit historical snapshot.
                        # Read metadata only, not all original bodies in this write transaction.
                        for original in selected.sources:
                            _authorize(
                                connection,
                                actor=request.actor,
                                action="record.read",
                                epoch=epoch,
                                resource_type="artifact",
                                resource_id=original.record_id,
                            )
                            available = connection.execute(
                                "SELECT r.status,v.payload IS NOT NULL FROM knowledge_records r "
                                "JOIN knowledge_revisions v ON v.record_id=r.record_id "
                                "WHERE r.record_id=? AND v.revision=?",
                                (str(original.record_id), original.revision),
                            ).fetchone()
                            if available is None or available[0] != "active" or not available[1]:
                                raise FoundationError(
                                    "content_unavailable", "Memory basis disappeared"
                                )
                        if (
                            selected.selection is not None
                            and selected.selection.cache
                            and ref in manifest.mandatory
                        ):
                            from .memory import selection_current_for_actor

                            if not selection_current_for_actor(
                                connection, request.actor, epoch, selected.selection
                            ):
                                raise FoundationError("stale_context", "Memory selection changed")
                knowledge = connection.execute(
                    "SELECT current_revision,status FROM knowledge_records WHERE record_id=?",
                    (str(ref.record_id),),
                ).fetchone()
                if knowledge is not None and (
                    knowledge[0] != ref.revision or knowledge[1] != "active"
                ):
                    raise FoundationError("stale_context", "Mandatory knowledge changed")
                if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 11:
                    development = connection.execute(
                        "SELECT current_revision,status FROM development_records WHERE record_id=?",
                        (str(ref.record_id),),
                    ).fetchone()
                    if development is not None and (
                        development[0] != ref.revision or development[1] != "active"
                    ):
                        raise FoundationError(
                            "stale_context", "Mandatory development record changed"
                        )
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
            if request.trial_total_send_limit is not None:
                admitted = int(
                    connection.execute("SELECT COUNT(*) FROM knowledge_delivery").fetchone()[0]
                )
                if admitted >= request.trial_total_send_limit:
                    raise FoundationError(
                        "trial_send_limit", "Local trial provider-send limit is spent"
                    )
            if request.free_call:
                spent = int(
                    connection.execute(
                        "SELECT COALESCE(SUM(CASE WHEN stage='answered' THEN usage_units "
                        "ELSE reserve_units END),0) FROM knowledge_delivery WHERE free_call=1"
                    ).fetchone()[0]
                )
                if (
                    request.budget_limit_units is not None
                    and spent + request.reserve_units > request.budget_limit_units
                ):
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
            if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 18:
                pin = _context_correlation(manifest)
                execution_pin = _execution_correlation(connection, str(request.invocation_id))
                if execution_pin is not None and pin != execution_pin:
                    raise FoundationError(
                        "delivery_correlation_conflict", "Manifest and execution pins disagree"
                    )
                if manifest.attempt_id is not None:
                    attempt = connection.execute(
                        "SELECT work_id,session_id,execution_epoch,status FROM execution_attempts "
                        "WHERE attempt_id=?",
                        (str(manifest.attempt_id),),
                    ).fetchone()
                    if attempt != (pin[0], pin[2], epoch, "active"):
                        raise FoundationError(
                            "invalid_delivery_correlation",
                            "Context does not name its active Attempt",
                        )
                connection.execute(
                    "UPDATE knowledge_delivery SET context_work_id=?,context_attempt_id=?,"
                    "context_session_id=?,correlation_state=? WHERE invocation_id=?",
                    (*pin, str(request.invocation_id)),
                )
        else:
            if old[:2] != (str(request.manifest.record_id), request.manifest.revision):
                raise FoundationError("stale_context", "Invocation cannot change its manifest")
            if bool(old[3]) != request.free_call:
                raise FoundationError("invalid_transition", "Invocation budget class changed")
            if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 18:
                pin = connection.execute(
                    "SELECT context_work_id,context_attempt_id,context_session_id,"
                    "correlation_state "
                    "FROM knowledge_delivery WHERE invocation_id=?",
                    (str(request.invocation_id),),
                ).fetchone()
                context_matches = (
                    _context_matches_exact_correlation(manifest, pin)
                    if pin[3] == "exact"
                    else pin == _context_correlation(manifest)
                )
                if not context_matches:
                    raise FoundationError(
                        "delivery_correlation_conflict", "Pinned delivery context changed"
                    )
                execution_pin = _execution_correlation(connection, str(request.invocation_id))
                if execution_pin is not None and execution_pin != pin:
                    raise FoundationError(
                        "delivery_correlation_conflict", "Pinned delivery and execution disagree"
                    )
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
        if isinstance(state, DataEntryState) and state.work_id is None:
            from .data_store import head_ref

            if (
                state.structure is not None
                and state.scope_activity_id is not None
                and (state.structure != head_ref(connection, state.scope_activity_id))
            ):
                raise FoundationError("stale_structure", "New data requires the current structure")
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
        if isinstance(prior, DataEntryState) and isinstance(state, DataEntryState):
            from .data_formats import validate_values
            from .data_store import exact_state

            definition = exact_state(connection, prior.format_ref, request.actor, epoch)
            assert isinstance(definition, DataFormatState)
            revised = validate_values(definition.fields, state.values)
            if any(prior.values.get(key) != revised.get(key) for key in definition.identity_fields):
                raise FoundationError("identity_changed", "Correction cannot become another event")
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
    if state is not None and info.schema_version >= 15:
        from .data_store import check_data_access

        check_data_access(connection, record_id, row[4], authority.actor, info.execution_epoch)
    stale = int(row[1]) != int(row[4])
    if state is not None:
        for role, ref in _refs(state, connection):
            if (
                isinstance(state, MemoryViewState)
                and state.generation_method == "zaratustra.memory/1"
            ):
                _authorize(
                    connection,
                    actor=authority.actor,
                    action="record.read",
                    epoch=info.execution_epoch,
                    resource_type="artifact",
                    resource_id=ref.record_id,
                )
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
            ) or role in (
                "data_current",
                "data_format",
                "data_structure",
                "structure_format",
                "data_scope",
            )
            if (
                target is None
                or target[0] in ("deleted", "unavailable")
                or (target[1] != ref.revision and not follows_current)
            ):
                stale = True
        if isinstance(state, MemoryViewState) and state.selection is not None:
            from .memory import selection_current

            stale = not selection_current(connection, info, authority, state.selection)
        elif isinstance(state, DataEntryState) and state.role == "analysis" and state.selection:
            from .data_store import exact_state
            from .memory import selection_current

            selected_basis = exact_state(
                connection, state.selection, authority.actor, info.execution_epoch
            )
            if isinstance(selected_basis, MemoryViewState) and selected_basis.selection:
                stale = stale or not selection_current(
                    connection, info, authority, selected_basis.selection
                )
        elif isinstance(state, MemoryViewState) and state.mode == "current":
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
    elif isinstance(state, (DataFormatState, DataEntryState, ActivityStructureState)):
        field, content = (
            "structured_data",
            canonical_json(state.model_dump(mode="json")).encode("utf-8"),
        )
    metadata = state.model_dump(mode="json", exclude={field} if field else None)
    if isinstance(state, (DataFormatState, DataEntryState, ActivityStructureState)):
        metadata = {
            "kind": state.kind,
            "scope_activity_id": str(state.scope_activity_id)
            if state.scope_activity_id is not None
            else None,
        }
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
    if isinstance(
        state,
        (
            ClaimState,
            AnalysisState,
            MemoryViewState,
            DataFormatState,
            DataEntryState,
            ActivityStructureState,
        ),
    ) or (isinstance(state, (SourceState, HandoffState)) and state.media_type.startswith("text/")):
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
            )
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
        result: dict[str, object] = {
            "invocation_id": str(invocation_id),
            "manifest_id": row[0],
            "manifest_revision": row[1],
            "stage": row[2],
            "request_sha256": row[3],
            "request_bytes": row[4],
        }
        if info.schema_version >= 18:
            pin = connection.execute(
                "SELECT context_work_id,context_attempt_id,context_session_id,correlation_state "
                "FROM knowledge_delivery WHERE invocation_id=?",
                (str(invocation_id),),
            ).fetchone()
            result.update(
                zip(
                    (
                        "context_work_id",
                        "context_attempt_id",
                        "context_session_id",
                        "correlation_state",
                    ),
                    pin,
                    strict=True,
                )
            )
        return result


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
