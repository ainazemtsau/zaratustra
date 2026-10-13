"""Current conversation actions derived from Core; receipt-backed delivery evidence.

Delivery rows record communication only. Work, setup and workflow remain the sole
authority for execution, questions and acceptance.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from .knowledge import _require_ref
from .models import (
    ActivityState,
    ContextState,
    ConversationActionPage,
    ConversationActionRef,
    ConversationActionView,
    ConversationAnswerTarget,
    ConversationDeliveryRequest,
    ConversationDeliveryView,
    KnowledgeRef,
    OrdinaryFinalProof,
    SourceState,
    SpaceInfo,
    WorkState,
)
from .operations import LocalAuthority, _authorize, _local_space, _subject_current, _subject_state
from .storage import (
    CONVERSATION_SCHEMA_NAME,
    CONVERSATION_SCHEMA_SHA256,
    CONVERSATION_SCHEMA_STATEMENTS,
    FoundationError,
    canonical_json,
    read_space,
    space_connection,
    utc_now,
)
from .work_status import work_status


def upgrade_conversation_space(path: Path, authority: LocalAuthority) -> SpaceInfo:
    """Explicit additive 16 to 17 upgrade. Old revisions and checksums are untouched."""
    with space_connection(path, writable=True) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active" or info.schema_version < 16:
            raise FoundationError("upgrade_required", "Conversation upgrade needs active schema 16")
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.backup",
            epoch=info.execution_epoch,
        )
        if info.schema_version == 16:
            for statement in CONVERSATION_SCHEMA_STATEMENTS:
                connection.execute(statement)
            now = utc_now().isoformat()
            connection.execute(
                "INSERT INTO schema_migrations VALUES (17,?,?,?)",
                (CONVERSATION_SCHEMA_NAME, CONVERSATION_SCHEMA_SHA256, now),
            )
            connection.execute("PRAGMA user_version=17")
            connection.execute(
                "UPDATE spaces SET state_revision=state_revision+1 WHERE singleton=1"
            )
            connection.execute(
                "INSERT INTO maintenance_events VALUES (?,'schema_upgrade',?,?)",
                (str(uuid4()), now, canonical_json({"from": 16, "to": 17})),
            )
    return read_space(path)


def _schema(connection: sqlite3.Connection) -> None:
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 17:
        raise FoundationError("upgrade_required", "Conversation delivery needs explicit schema 17")


def _subject(
    connection: sqlite3.Connection, identifier: UUID, kind: str, authority: LocalAuthority
) -> tuple[int, Any]:
    _authorize(
        connection,
        actor=authority.actor,
        action="record.read",
        epoch=authority.execution_epoch,
        resource_type=cast(Any, kind),
        resource_id=identifier,
    )
    revision, status, _ = _subject_current(connection, identifier, kind)
    if status == "deleted":
        raise FoundationError("content_unavailable", "Conversation subject was deleted")
    state = _subject_state(connection, identifier, revision)
    return revision, ActivityState.model_validate(
        state
    ) if kind == "activity" else WorkState.model_validate(state)


def _make(
    connection: sqlite3.Connection,
    authority: LocalAuthority,
    *,
    subject_kind: str,
    subject_id: UUID,
    subject_revision: int,
    activity_id: UUID,
    work_id: UUID | None,
    kind: str,
    explanation: str,
    next_action: str,
    bases: tuple[KnowledgeRef, ...],
    answer_target: ConversationAnswerTarget | None = None,
    detail: Any = None,
) -> ConversationActionView:
    activity_revision, activity = _subject(connection, activity_id, "activity", authority)
    refs = tuple(
        dict.fromkeys((KnowledgeRef(record_id=activity_id, revision=activity_revision),) + bases)
    )
    for ref in refs:
        _require_ref(connection, ref, authority.actor, authority.execution_epoch)
    value = {
        "subject_kind": subject_kind,
        "subject_id": str(subject_id),
        "subject_revision": subject_revision,
        "activity_id": str(activity_id),
        "work_id": str(work_id) if work_id else None,
        "kind": kind,
        "label": activity.title,
        "explanation": explanation,
        "next_action": next_action,
        "bases": [ref.model_dump(mode="json") for ref in refs],
        "answer_target": answer_target.model_dump(mode="json") if answer_target else None,
        "detail": detail,
    }
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest().upper()
    value.pop("detail")
    return ConversationActionView.model_validate(
        {**value, "ref": {"action_id": str(subject_id), "digest": digest}}
    )


def _action(
    connection: sqlite3.Connection, identifier: UUID, authority: LocalAuthority
) -> ConversationActionView | None:
    from .activity_setup import _current as current_setup
    from .workflows import _descendant_runs, _native_waits, _waits, _work_family

    setup_row = connection.execute(
        "SELECT setup_id FROM activity_setups WHERE setup_id=? AND status='active'",
        (str(identifier),),
    ).fetchone()
    if setup_row:
        setup = current_setup(connection, identifier)
        state = setup.state
        kinds = {
            "needs_input": "question",
            "ready": "ready",
            "needs_attention": "attention",
            "paused": "paused",
            "cancelled": "cancelled",
            "collecting": "available_work",
        }
        if state.phase not in kinds:
            return None
        bases = state.sources
        for artifact in (state.draft, state.review, state.manifest):
            if artifact:
                bases += (KnowledgeRef(record_id=artifact.artifact_id, revision=artifact.revision),)
        for work in state.activated_works:
            # Completion belongs to this exact setup, not the later state of its
            # first Work. Still recheck that the continuation exists and is readable.
            _subject(connection, work, "work", authority)
        text = (
            state.question
            if state.phase == "needs_input"
            else state.result
            or {
                "ready": "Activity created and fully reviewed; "
                "continue with the existing first Work.",
                "collecting": "Activity setup has saved requirements and can continue.",
                "paused": "Activity setup is paused; resume explicitly.",
                "cancelled": "Activity setup is cancelled.",
                "needs_attention": "Activity setup needs attention; inspect its saved diagnostics.",
            }[state.phase]
        )
        target = (
            ConversationAnswerTarget(kind="setup", subject_id=identifier, revision=setup.revision)
            if state.phase == "needs_input"
            else None
        )
        return _make(
            connection,
            authority,
            subject_kind="setup",
            subject_id=identifier,
            subject_revision=setup.revision,
            activity_id=state.activity_id,
            work_id=state.activated_works[0] if state.activated_works else state.root_work_id,
            kind=kinds[state.phase],
            explanation=text or "Saved question awaits an answer.",
            next_action="answer"
            if target
            else "select_work"
            if state.phase == "ready"
            else "resume"
            if state.phase == "paused"
            else "inspect",
            bases=bases,
            answer_target=target,
            detail=state.model_dump(mode="json"),
        )
    run = connection.execute(
        "SELECT revision,control FROM workflow_runs WHERE root_work_id=?", (str(identifier),)
    ).fetchone()
    if run:
        if connection.execute(
            "SELECT 1 FROM activity_setup_revisions WHERE "
            "json_extract(CAST(payload AS TEXT),'$.root_work_id')=? LIMIT 1",
            (str(identifier),),
        ).fetchone():
            return None
        revision, work = _subject(connection, identifier, "work", authority)
        waits = _waits(connection, identifier) + _native_waits(
            connection, identifier, authority.actor, authority.execution_epoch
        )
        for child in _descendant_runs(connection, identifier):
            _subject(connection, child, "work", authority)
            waits += _waits(connection, child) + _native_waits(
                connection, child, authority.actor, authority.execution_epoch
            )
        last = connection.execute(
            "SELECT kind,detail FROM workflow_events WHERE root_work_id=? "
            "ORDER BY revision DESC LIMIT 1",
            (str(identifier),),
        ).fetchone()
        kind, text, next_action = "available_work", "Workflow has saved continuation.", "inspect"
        target = None
        refs: tuple[KnowledgeRef, ...] = (KnowledgeRef(record_id=identifier, revision=revision),)
        if run[1] == "cancelled":
            kind, text = "cancelled", "Workflow is cancelled."
        elif run[1] == "paused":
            kind, text, next_action = "paused", "Workflow is paused; resume explicitly.", "resume"
        elif last and last[0] == "attention":
            kind, text = "attention", json.loads(last[1])["explanation"]
        elif waits:
            wait = waits[0]
            kind, text, next_action = "question", wait.question, "answer"
            refs += wait.bases
            target = ConversationAnswerTarget(
                kind="work" if wait.native else "workflow",
                subject_id=wait.work_id if wait.native else wait.root_work_id or identifier,
                revision=wait.revision,
                wait_id=wait.wait_id,
            )
        elif last and last[0] == "finish":
            kind, text = "result", "Workflow finished; its exact output is available."
        refs += tuple(
            KnowledgeRef(record_id=item.artifact.artifact_id, revision=item.artifact.revision)
            for item in work.linked_outputs
        )
        return _make(
            connection,
            authority,
            subject_kind="workflow",
            subject_id=identifier,
            subject_revision=run[0],
            activity_id=work.activity_id,
            work_id=identifier,
            kind=kind,
            explanation=text,
            next_action=next_action,
            bases=refs,
            answer_target=target,
            detail={
                "control": run[1],
                "last": last,
                "waits": [wait.model_dump(mode="json") for wait in waits],
                "status": work_status(connection, identifier).model_dump(mode="json"),
            },
        )
    exists = connection.execute(
        "SELECT 1 FROM subject_records WHERE record_id=? AND kind='work' AND status!='deleted'",
        (str(identifier),),
    ).fetchone()
    if not exists:
        raise FoundationError("not_found", "Conversation subject is absent")
    if connection.execute(
        "SELECT 1 FROM workflow_nodes WHERE work_id=? UNION ALL "
        "SELECT 1 FROM work_plan_children WHERE child_id=? LIMIT 1",
        (str(identifier), str(identifier)),
    ).fetchone():
        return None
    if connection.execute(
        "SELECT 1 FROM activity_setups a JOIN activity_setup_revisions r "
        "ON r.setup_id=a.setup_id AND r.revision=a.current_revision, "
        "json_each(CAST(r.payload AS TEXT),'$.stages') s WHERE "
        "json_extract(s.value,'$.work_id')=? LIMIT 1",
        (str(identifier),),
    ).fetchone():
        return None
    revision, work = _subject(connection, identifier, "work", authority)
    status = work_status(connection, identifier)
    refs = (KnowledgeRef(record_id=identifier, revision=revision),)
    refs += tuple(
        KnowledgeRef(record_id=ref.artifact_id, revision=ref.revision) for ref in work.inputs
    )
    refs += tuple(
        KnowledgeRef(record_id=item.artifact.artifact_id, revision=item.artifact.revision)
        for item in work.linked_outputs
    )
    target = None
    kind, text, next_action = "available_work", work.goal, "select_work"
    native_wait = None
    if status.status not in ("failed", "cancelled", "stale"):
        for work_id in _work_family(connection, identifier):
            row = connection.execute(
                "SELECT revision,question,expected_actor,wait_id FROM execution_waits "
                "WHERE work_id=? AND status IN ('open','closed') AND answer IS NULL "
                "AND question IS NOT NULL AND NOT EXISTS (SELECT 1 FROM execution_invocations "
                "i WHERE i.attempt_id=execution_waits.attempt_id AND i.status IN "
                "('sent','unknown')) ORDER BY created_at DESC LIMIT 1",
                (str(work_id),),
            ).fetchone()
            if row:
                native_wait = (work_id, row)
                break
    if native_wait:
        waiting_work, row = native_wait
        if row and row[1]:
            waiting_revision, _ = _subject(connection, waiting_work, "work", authority)
            refs += (KnowledgeRef(record_id=waiting_work, revision=waiting_revision),)
            text = bytes(row[1]).decode("utf-8") if isinstance(row[1], bytes) else row[1]
            kind, next_action = "question", "answer"
            target = ConversationAnswerTarget(
                kind="work", subject_id=waiting_work, revision=row[0], wait_id=UUID(row[3])
            )
    elif status.status in ("failed", "stale", "blocked"):
        kind, text, next_action = (
            "attention",
            "Work needs attention: " + ", ".join(item.code for item in status.reasons),
            "inspect",
        )
    elif status.status == "cancelled":
        kind, text, next_action = "cancelled", "Work is cancelled.", "inspect"
    elif status.status == "running":
        kind, text, next_action = (
            "running",
            "Work has an active execution; inspect its observed state before continuing.",
            "inspect_execution",
        )
    elif work.linked_outputs:
        kind, text, next_action = (
            "result",
            "Work has saved output; owner acceptance remains separate.",
            "read_result",
        )
    procedure = connection.execute(
        "SELECT run_id,procedure_key FROM procedure_runs WHERE work_id=?", (str(identifier),)
    ).fetchone()
    return _make(
        connection,
        authority,
        subject_kind="procedure" if procedure else "work",
        subject_id=identifier,
        subject_revision=revision,
        activity_id=work.activity_id,
        work_id=identifier,
        kind=kind,
        explanation=text,
        next_action=next_action,
        bases=refs,
        answer_target=target,
        detail={"status": status.model_dump(mode="json"), "procedure": procedure},
    )


def _checked_action(
    connection: sqlite3.Connection, ref: ConversationActionRef, authority: LocalAuthority
) -> ConversationActionView:
    value = _action(connection, ref.action_id, authority)
    if value is None or value.ref != ref:
        raise FoundationError(
            "stale_conversation_action", "Conversation action changed or is no longer available"
        )
    return value


def check_conversation_context(
    connection: sqlite3.Connection, context: ContextState, actor: str, epoch: int
) -> None:
    """Recheck the actual manifest before provider accounting admits a send."""
    if not context.conversation_actions:
        return
    _schema(connection)
    authority = LocalAuthority(
        actor=actor,
        source_ref="context-action-read",
        established_at=utc_now(),
        space_root=Path("."),
        space_id=UUID(connection.execute("SELECT space_id FROM spaces").fetchone()[0]),
        execution_epoch=epoch,
    )
    for ref in context.conversation_actions:
        action = _checked_action(connection, ref, authority)
        if not set(action.bases).issubset(context.mandatory):
            raise FoundationError("stale_context", "Context omits exact conversation action bases")


def validate_conversation_answer(
    path: Path,
    authority: LocalAuthority,
    source: KnowledgeRef,
    *,
    kind: str,
    subject_id: UUID,
    wait_id: UUID | None = None,
) -> None:
    """A new delivered owner Source may answer only an already saved exact question."""
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        _require_ref(connection, source, authority.actor, info.execution_epoch)
        source_row = connection.execute(
            "SELECT k.payload,o.state_revision FROM knowledge_revisions k JOIN operations o "
            "ON o.operation_id=k.operation_id WHERE k.record_id=? AND k.revision=?",
            (str(source.record_id), source.revision),
        ).fetchone()
        if not source_row or not source_row[0]:
            raise FoundationError("invalid_conversation_answer", "Owner Source is unavailable")
        original = SourceState.model_validate_json(source_row[0])
        if (
            original.channel != "conversation_user"
            or original.sender != authority.actor
            or original.capture != "full"
            or source.start is not None
            or source.end is not None
        ):
            raise FoundationError("invalid_conversation_answer", "Answer needs a full owner Source")
        if kind == "setup":
            from .activity_setup import _current as current_setup

            current = current_setup(connection, subject_id)
            _subject(connection, current.state.activity_id, "activity", authority)
            if current.state.phase not in ("needs_input", "paused") or not current.state.question:
                raise FoundationError("stale_wait", "Setup has no current saved question")
            interaction = next(
                (
                    item
                    for item in reversed(current.state.interactions)
                    if item.answer is None and item.question == current.state.question
                ),
                None,
            )
            question_revision = None
            for payload, state_revision in connection.execute(
                "SELECT r.payload,o.state_revision FROM activity_setup_revisions r "
                "JOIN operations o ON o.operation_id=r.operation_id WHERE r.setup_id=? "
                "AND r.revision<=? ORDER BY r.revision DESC",
                (str(subject_id), current.revision),
            ):
                if payload is None:
                    raise FoundationError("content_unavailable", "Question history is unavailable")
                previous = json.loads(payload)
                present = (
                    any(
                        item["interaction_id"] == str(interaction.interaction_id)
                        for item in previous.get("interactions", [])
                    )
                    if interaction
                    else previous.get("question") == current.state.question
                )
                if not present:
                    break
                question_revision = state_revision
            if current.state.owner != authority.actor:
                raise FoundationError("permission_denied", "Question has another designated owner")
        elif kind == "workflow":
            _subject(connection, subject_id, "work", authority)
            row = connection.execute(
                "SELECT w.expected_actor,o.state_revision FROM workflow_waits w JOIN "
                "operations o ON o.operation_id=w.operation_id WHERE w.root_work_id=? "
                "AND w.wait_id=? AND w.closed=0 AND w.answer IS NULL",
                (str(subject_id), str(wait_id)),
            ).fetchone()
            if not row:
                raise FoundationError("stale_wait", "Workflow question is no longer open")
            if row[0] != authority.actor:
                raise FoundationError("permission_denied", "Question has another designated owner")
            question_revision = row[1]
        elif kind == "work":
            _subject(connection, subject_id, "work", authority)
            row = connection.execute(
                "SELECT w.expected_actor,o.state_revision FROM execution_waits w JOIN "
                "operation_audit a ON EXISTS (SELECT 1 FROM json_each(a.target_refs_json) r "
                "WHERE json_extract(r.value,'$.record_id')=w.wait_id "
                "AND json_extract(r.value,'$.revision')=1) JOIN operations o "
                "ON o.operation_id=a.operation_id AND o.kind='open_wait' "
                "WHERE w.work_id=? AND w.wait_id=? AND w.status IN ('open','closed') "
                "AND w.answer IS NULL",
                (str(subject_id), str(wait_id)),
            ).fetchone()
            if not row:
                raise FoundationError("stale_wait", "Work question is no longer open")
            if row[0] != authority.actor:
                raise FoundationError("permission_denied", "Question has another designated owner")
            question_revision = row[1]
        else:
            raise FoundationError("invalid_request", "Unsupported conversation answer target")
        if question_revision is None or source_row[1] <= question_revision:
            raise FoundationError(
                "invalid_conversation_answer", "Owner message predates the saved question"
            )


def read_conversation_action(
    path: Path, ref: ConversationActionRef, authority: LocalAuthority
) -> ConversationActionView:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        _schema(connection)
        return _checked_action(connection, ref, authority)


def current_conversation_action(
    path: Path, subject_id: UUID, authority: LocalAuthority
) -> ConversationActionView | None:
    """Read one watched subject directly, without a workspace scan or an old digest."""
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 17:
            return None
        try:
            return _action(connection, subject_id, authority)
        except FoundationError as error:
            if error.code in (
                "not_found",
                "content_unavailable",
                "permission_denied",
                "decision_denied",
                "stale_basis",
            ):
                return None
            raise


def read_ordinary_final_proof(
    path: Path, work_id: UUID, authority: LocalAuthority, *, attempt_id: UUID | None = None
) -> OrdinaryFinalProof | None:
    """Read saved final evidence for closing an unassigned ordinary active Attempt.

    This reads exact producer evidence, without sending, accepting Work or changing
    execution. An absent proof leaves interruption and other recovery decisions to
    the existing addressed operations.
    """
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        return ordinary_final_proof(connection, info, work_id, authority, attempt_id=attempt_id)


def ordinary_final_proof(
    connection: sqlite3.Connection,
    info: SpaceInfo,
    work_id: UUID,
    authority: LocalAuthority,
    *,
    attempt_id: UUID | None = None,
) -> OrdinaryFinalProof | None:
    """Same-transaction proof check used by observed final completion."""
    from .execution import _available_resource, _current_inputs

    if info.schema_version < 17:
        return None
    work_revision, work = _subject(connection, work_id, "work", authority)
    if work.status != "proposed":
        return None
    row = connection.execute(
        "SELECT attempt_id,revision,session_id,execution_epoch,work_revision,"
        "resource_id,resource_revision,input_refs_json FROM execution_attempts "
        "WHERE work_id=? AND status='active' AND (? IS NULL OR attempt_id=?) "
        "ORDER BY generation DESC LIMIT 1",
        (
            str(work_id),
            str(attempt_id) if attempt_id else None,
            str(attempt_id) if attempt_id else None,
        ),
    ).fetchone()
    if not row or row[3] != info.execution_epoch:
        return None
    (
        attempt,
        attempt_revision,
        session,
        _,
        held_revision,
        resource,
        resource_revision,
        inputs,
    ) = row
    if connection.execute(
        "SELECT 1 FROM execution_assignments WHERE attempt_id=? UNION ALL "
        "SELECT 1 FROM execution_waits WHERE attempt_id=? AND status='open' LIMIT 1",
        (attempt, attempt),
    ).fetchone():
        return None
    if connection.execute(
        "SELECT 1 FROM execution_invocations WHERE work_id=? AND "
        "(status IN ('admitted','sent','unknown') OR (attempt_id=? AND status!='answered')) "
        "LIMIT 1",
        (str(work_id), attempt),
    ).fetchone():
        return None
    # Work may have advanced only through this Attempt's own publications.
    # This exception proves closure, never admission of another model effect.
    if work_revision != held_revision:
        publications = connection.execute(
            "SELECT COUNT(*) FROM subject_revisions r JOIN execution_events e "
            "ON e.operation_id=r.operation_id AND e.work_id=r.record_id "
            "WHERE r.record_id=? AND r.revision>? AND r.revision<=? "
            "AND e.attempt_id=? AND e.kind='publish_attempt_output'",
            (str(work_id), held_revision, work_revision, attempt),
        ).fetchone()[0]
        if work_revision < held_revision or publications != work_revision - held_revision:
            return None
    if json.loads(inputs) != [ref.model_dump(mode="json") for ref in work.inputs]:
        return None
    _current_inputs(connection, work, actor=authority.actor, epoch=info.execution_epoch)
    _available_resource(connection, UUID(resource), work_id, resource_revision)
    invocation = connection.execute(
        "SELECT i.invocation_id,k.manifest_id,k.manifest_revision,o.state_revision "
        "FROM execution_invocations i JOIN execution_events e "
        "ON e.invocation_id=i.invocation_id AND e.kind='prepare_invocation' "
        "JOIN knowledge_delivery k ON k.invocation_id=i.invocation_id "
        "JOIN execution_events f ON f.invocation_id=i.invocation_id "
        "AND f.kind='finish_invocation' JOIN operations o ON o.operation_id=f.operation_id "
        "WHERE i.attempt_id=? AND i.session_id=? AND i.status='answered' "
        "AND k.stage='answered' ORDER BY e.sequence DESC LIMIT 1",
        (attempt, session),
    ).fetchone()
    if not invocation:
        return None
    latest = connection.execute(
        "SELECT i.invocation_id FROM execution_invocations i JOIN execution_events e "
        "ON e.invocation_id=i.invocation_id AND e.kind='prepare_invocation' "
        "WHERE i.attempt_id=? ORDER BY e.sequence DESC LIMIT 1",
        (attempt,),
    ).fetchone()
    if latest != (invocation[0],):
        return None
    manifest = KnowledgeRef(record_id=UUID(invocation[1]), revision=invocation[2])
    _require_ref(connection, manifest, authority.actor, info.execution_epoch)
    manifest_row = connection.execute(
        "SELECT r.payload FROM knowledge_revisions r JOIN knowledge_records k "
        "ON k.record_id=r.record_id AND k.current_revision=r.revision AND k.status='active' "
        "WHERE r.record_id=? AND r.revision=?",
        (str(manifest.record_id), manifest.revision),
    ).fetchone()
    if not manifest_row or manifest_row[0] is None:
        return None
    context = ContextState.model_validate_json(manifest_row[0])
    if (context.work_id, context.attempt_id, str(context.session_id)) != (
        work_id,
        UUID(attempt),
        session,
    ):
        return None
    for ref in context.mandatory + context.historical_memory:
        _require_ref(connection, ref, authority.actor, info.execution_epoch)
    for source_id, revision, payload in connection.execute(
        "SELECT r.record_id,r.revision,r.payload FROM knowledge_edges e "
        "JOIN knowledge_revisions r ON r.record_id=e.record_id AND r.revision=e.revision "
        "JOIN knowledge_records k ON k.record_id=r.record_id AND k.kind='source' "
        "AND k.status='active' AND k.current_revision=r.revision "
        "JOIN operations o ON o.operation_id=r.operation_id "
        "WHERE e.target_id=? AND e.target_revision=? AND e.role='derived_from' "
        "AND o.state_revision>? ORDER BY o.state_revision DESC LIMIT 100",
        (str(manifest.record_id), manifest.revision, invocation[3]),
    ):
        if payload is None:
            continue
        source = SourceState.model_validate_json(payload)
        prefix = f"{session}:"
        if (
            not source.conversation_final
            or source.channel != "conversation_assistant"
            or source.sender != "pi-assistant"
            or source.capture != "full"
            or not source.content
            or source.conversation_id != session
            or source.scope_work_id != work_id
            or not source.source_event_id
            or not source.source_event_id.startswith(prefix)
            or source.source_event_id == prefix
            or manifest not in source.derived_from
        ):
            continue
        source_ref = KnowledgeRef(record_id=UUID(source_id), revision=revision)
        _require_ref(connection, source_ref, authority.actor, info.execution_epoch)
        return OrdinaryFinalProof(
            work_id=work_id,
            work_revision=work_revision,
            attempt_id=UUID(attempt),
            attempt_revision=attempt_revision,
            session_id=UUID(session),
            execution_epoch=info.execution_epoch,
            manifest=manifest,
            invocation_id=UUID(invocation[0]),
            assistant_source=source_ref,
            assistant_entry_id=source.source_event_id[len(prefix) :],
        )
    return None


def read_conversation_actions_page(
    path: Path,
    authority: LocalAuthority,
    *,
    activity_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    scan_limit: int = 200,
) -> ConversationActionPage:
    if not 1 <= limit <= 100 or not 0 <= offset <= 100000 or not 1 <= scan_limit <= 1000:
        raise FoundationError("invalid_request", "Conversation discovery needs a bounded page")
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 17:
            return ConversationActionPage(actions=(), scanned=0)
        identifiers = connection.execute(
            "SELECT setup_id AS id FROM activity_setups WHERE status='active' "
            "AND (? IS NULL OR activity_id=?) UNION ALL SELECT record_id AS id "
            "FROM subject_records WHERE kind='work' AND status!='deleted' "
            "AND (? IS NULL OR parent_id=?) ORDER BY id LIMIT ? OFFSET ?",
            (str(activity_id) if activity_id else None,) * 4 + (scan_limit + 1, offset),
        ).fetchall()
        result = []
        scanned = 0
        for (identifier,) in identifiers[:scan_limit]:
            scanned += 1
            try:
                action = _action(connection, UUID(identifier), authority)
            except FoundationError as error:
                if error.code in (
                    "permission_denied",
                    "decision_denied",
                    "content_unavailable",
                    "stale_basis",
                    "not_found",
                ):
                    continue
                raise
            if action:
                result.append(action)
                if len(result) == limit:
                    break
        return ConversationActionPage(
            actions=tuple(result),
            scanned=scanned,
            next_offset=offset + scanned if len(identifiers) > scanned else None,
        )


def list_conversation_actions(
    path: Path,
    authority: LocalAuthority,
    *,
    activity_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[ConversationActionView, ...]:
    """Compatibility first page; cursor-aware consumers use the explicit page API."""
    return read_conversation_actions_page(
        path, authority, activity_id=activity_id, limit=limit, offset=offset
    ).actions


def _delivery(connection: sqlite3.Connection, identifier: UUID) -> ConversationDeliveryView:
    row = connection.execute(
        "SELECT action_id,action_digest,actor,epoch,host_id,session_id,branch_id,status,"
        "manifest_id,manifest_revision,invocation_id,assistant_source_id,"
        "assistant_source_revision,assistant_entry_id FROM conversation_deliveries "
        "WHERE delivery_id=?",
        (str(identifier),),
    ).fetchone()
    if row is None:
        raise FoundationError("not_found", "Conversation delivery is absent")
    return ConversationDeliveryView(
        delivery_id=identifier,
        action_ref=ConversationActionRef(action_id=UUID(row[0]), digest=row[1]),
        actor=row[2],
        epoch=row[3],
        host_id=row[4],
        session_id=UUID(row[5]),
        branch_id=row[6],
        status=row[7],
        manifest=KnowledgeRef(record_id=UUID(row[8]), revision=row[9]) if row[8] else None,
        invocation_id=UUID(row[10]) if row[10] else None,
        assistant_source=KnowledgeRef(record_id=UUID(row[11]), revision=row[12])
        if row[11]
        else None,
        assistant_entry_id=row[13],
    )


def read_conversation_delivery(
    path: Path, delivery_id: UUID, authority: LocalAuthority
) -> ConversationDeliveryView:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        _schema(connection)
        result = _delivery(connection, delivery_id)
        # Historical delivery evidence is readable after a new action revision.
        # It cannot authorize a new effect; mutation still checks the exact digest.
        _action(connection, result.action_ref.action_id, authority)
        for target, revision in connection.execute(
            "SELECT target_id,target_revision FROM conversation_delivery_edges WHERE delivery_id=?",
            (str(delivery_id),),
        ):
            _require_ref(
                connection,
                KnowledgeRef(record_id=UUID(target), revision=revision),
                authority.actor,
                authority.execution_epoch,
            )
        return result


def list_conversation_deliveries(
    path: Path, authority: LocalAuthority, *, action_id: UUID | None = None, limit: int = 50
) -> tuple[ConversationDeliveryView, ...]:
    if not 1 <= limit <= 100:
        raise FoundationError("invalid_request", "Conversation delivery page is bounded")
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 17:
            return ()
        result = []
        for (identifier,) in connection.execute(
            "SELECT delivery_id FROM conversation_deliveries WHERE (? IS NULL OR action_id=?) "
            "ORDER BY created_at DESC,delivery_id LIMIT ?",
            (str(action_id) if action_id else None,) * 2 + (limit,),
        ):
            delivery = _delivery(connection, UUID(identifier))
            try:
                action = _action(connection, delivery.action_ref.action_id, authority)
            except FoundationError as error:
                if error.code in (
                    "permission_denied",
                    "decision_denied",
                    "content_unavailable",
                    "not_found",
                ):
                    continue
                raise
            if action:
                result.append(delivery)
        return tuple(result)


def _edge(connection: sqlite3.Connection, delivery_id: UUID, role: str, ref: KnowledgeRef) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO conversation_delivery_edges VALUES (?,?,?,?)",
        (str(delivery_id), role, str(ref.record_id), ref.revision),
    )


def apply_conversation_change(
    connection: sqlite3.Connection,
    request: ConversationDeliveryRequest,
    *,
    authority: LocalAuthority,
    now: str,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    _schema(connection)
    if request.action == "abandon":
        return _abandon_delivery(connection, request, authority=authority, now=now)
    action = _checked_action(connection, request.action_ref, authority)
    refs = [{"record_id": str(ref.record_id), "revision": ref.revision} for ref in action.bases]
    if request.action == "claim":
        old = connection.execute(
            "SELECT delivery_id FROM conversation_deliveries WHERE action_id=? "
            "AND action_digest=? AND status IN ('claimed','included','responded','unknown')",
            (str(request.action_ref.action_id), request.action_ref.digest),
        ).fetchone()
        if old:
            raise FoundationError(
                "conversation_delivery_claimed",
                "This exact action already has a claimed, completed or unknown delivery",
            )
        connection.execute(
            "INSERT INTO conversation_deliveries(delivery_id,action_id,action_digest,actor,"
            "epoch,host_id,session_id,branch_id,status,operation_id,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,'claimed',?,?,?)",
            (
                str(request.delivery_id),
                str(request.action_ref.action_id),
                request.action_ref.digest,
                authority.actor,
                authority.execution_epoch,
                request.host_id,
                str(request.session_id),
                request.branch_id,
                str(request.operation_id),
                now,
                now,
            ),
        )
        for ref in action.bases:
            _edge(connection, request.delivery_id, "basis", ref)
        if action.subject_kind == "setup":
            from .activity_setup import _current as current_setup

            for work in current_setup(connection, action.subject_id).state.activated_works:
                revision, _ = _subject(connection, work, "work", authority)
                _edge(
                    connection,
                    request.delivery_id,
                    "continuation_work",
                    KnowledgeRef(record_id=work, revision=revision),
                )
        connection.execute(
            "INSERT INTO conversation_delivery_events VALUES (?,?,?)",
            (str(request.delivery_id), str(request.operation_id), request.action),
        )
        return {"delivery_id": str(request.delivery_id), "status": "claimed"}, refs
    delivery = _delivery(connection, request.delivery_id)
    if delivery.action_ref != request.action_ref or (
        delivery.actor,
        delivery.host_id,
        delivery.session_id,
        delivery.branch_id,
    ) != (
        authority.actor,
        request.host_id,
        request.session_id,
        request.branch_id,
    ):
        raise FoundationError(
            "stale_conversation_delivery", "Delivery host, session, branch or epoch changed"
        )
    if delivery.epoch != authority.execution_epoch:
        raise FoundationError("stale_conversation_delivery", "Delivery epoch changed")
    if delivery.status in ("responded", "unknown", "abandoned", "stale"):
        raise FoundationError("invalid_transition", "Conversation delivery is terminal")
    manifest = request.manifest or delivery.manifest
    invocation_id = request.invocation_id or delivery.invocation_id
    ledger = None
    context = None
    if manifest or invocation_id:
        if manifest is None or invocation_id is None:
            raise FoundationError(
                "invalid_request", "Delivery correlation needs manifest and invocation"
            )
        _require_ref(connection, manifest, authority.actor, authority.execution_epoch)
        row = connection.execute(
            "SELECT payload FROM knowledge_revisions WHERE record_id=? AND revision=?",
            (str(manifest.record_id), manifest.revision),
        ).fetchone()
        if not row or not row[0]:
            raise FoundationError("stale_context", "Delivery manifest is unavailable")
        context = ContextState.model_validate_json(row[0])
        if (
            context.session_id != request.session_id
            or request.action_ref not in context.conversation_actions
            or not set(action.bases).issubset(context.mandatory)
        ):
            raise FoundationError(
                "stale_context", "Manifest did not include the exact action and its bases"
            )
        ledger = connection.execute(
            "SELECT manifest_id,manifest_revision,stage FROM knowledge_delivery "
            "WHERE invocation_id=?",
            (str(invocation_id),),
        ).fetchone()
        if not ledger or ledger[:2] != (str(manifest.record_id), manifest.revision):
            raise FoundationError("stale_context", "Actual invocation used another manifest")
        if request.action != "include" and delivery.manifest and delivery.manifest != manifest:
            raise FoundationError("stale_context", "Delivery cannot change its manifest")
        if (
            request.action != "include"
            and delivery.invocation_id
            and delivery.invocation_id != invocation_id
        ):
            raise FoundationError("stale_context", "Delivery cannot change its invocation")
    if request.action == "include":
        if manifest is None or invocation_id is None:
            raise FoundationError("invalid_request", "Inclusion requires exact correlation")
        unsettled = connection.execute(
            "SELECT 1 FROM conversation_delivery_invocations c JOIN knowledge_delivery k "
            "ON k.invocation_id=c.invocation_id WHERE c.delivery_id=? AND c.invocation_id!=? "
            "AND k.stage!='answered' LIMIT 1",
            (str(request.delivery_id), str(invocation_id)),
        ).fetchone()
        if unsettled:
            raise FoundationError(
                "unknown_conversation_delivery", "Earlier provider outcome is not confirmed"
            )
        if (
            delivery.status not in ("claimed", "included")
            or ledger is None
            or ledger[2] not in ("prepared", "sent", "answered")
        ):
            raise FoundationError(
                "invalid_transition", "Inclusion requires an observed correlated invocation"
            )
        old_invocation = connection.execute(
            "SELECT delivery_id,manifest_id,manifest_revision "
            "FROM conversation_delivery_invocations WHERE invocation_id=?",
            (str(invocation_id),),
        ).fetchone()
        if old_invocation and old_invocation != (
            str(request.delivery_id),
            str(manifest.record_id),
            manifest.revision,
        ):
            raise FoundationError(
                "stale_context", "Invocation belongs to another conversation delivery"
            )
        connection.execute(
            "INSERT OR IGNORE INTO conversation_delivery_invocations VALUES (?,?,?,?,?)",
            (
                str(request.delivery_id),
                str(invocation_id),
                str(manifest.record_id),
                manifest.revision,
                str(request.operation_id),
            ),
        )
        status = "included"
    elif request.action == "respond":
        if (
            delivery.status != "included"
            or ledger is None
            or ledger[2] != "answered"
            or request.assistant_source is None
            or not request.assistant_entry_id
        ):
            raise FoundationError(
                "invalid_transition",
                "Response requires answered invocation and saved final assistant evidence",
            )
        _require_ref(
            connection, request.assistant_source, authority.actor, authority.execution_epoch
        )
        row = connection.execute(
            "SELECT payload FROM knowledge_revisions WHERE record_id=? AND revision=?",
            (str(request.assistant_source.record_id), request.assistant_source.revision),
        ).fetchone()
        source = SourceState.model_validate_json(row[0])
        if (
            not source.conversation_final
            or source.channel != "conversation_assistant"
            or source.sender != "pi-assistant"
            or source.conversation_id != str(request.session_id)
            or source.source_event_id != f"{request.session_id}:{request.assistant_entry_id}"
            or source.capture != "full"
            or not source.content
            or manifest not in source.derived_from
        ):
            raise FoundationError(
                "invalid_conversation_response",
                "Saved Source does not prove a final answer for this delivery",
            )
        _edge(connection, request.delivery_id, "response", request.assistant_source)
        refs.append(
            {
                "record_id": str(request.assistant_source.record_id),
                "revision": request.assistant_source.revision,
            }
        )
        status = "responded"
    elif request.action == "unknown":
        if ledger is None or ledger[2] not in ("sent", "unknown", "answered"):
            raise FoundationError("invalid_transition", "Unknown delivery needs an observed send")
        status = "unknown"
    if manifest:
        _edge(connection, request.delivery_id, "manifest", manifest)
    connection.execute(
        "INSERT INTO conversation_delivery_events VALUES (?,?,?)",
        (str(request.delivery_id), str(request.operation_id), request.action),
    )
    connection.execute(
        "UPDATE conversation_deliveries SET status=?,manifest_id=?,manifest_revision=?,"
        "invocation_id=?,assistant_source_id=?,assistant_source_revision=?,"
        "assistant_entry_id=?,operation_id=?,updated_at=? WHERE delivery_id=?",
        (
            status,
            str(manifest.record_id) if manifest else None,
            manifest.revision if manifest else None,
            str(invocation_id) if invocation_id else None,
            str(request.assistant_source.record_id) if request.assistant_source else None,
            request.assistant_source.revision if request.assistant_source else None,
            request.assistant_entry_id,
            str(request.operation_id),
            now,
            str(request.delivery_id),
        ),
    )
    return {"delivery_id": str(request.delivery_id), "status": status}, refs


def _abandon_delivery(
    connection: sqlite3.Connection,
    request: ConversationDeliveryRequest,
    *,
    authority: LocalAuthority,
    now: str,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Release exact unsent host evidence even after the current action has changed."""
    delivery = _delivery(connection, request.delivery_id)
    if delivery.action_ref != request.action_ref or (
        delivery.actor,
        delivery.host_id,
        delivery.session_id,
        delivery.branch_id,
    ) != (authority.actor, request.host_id, request.session_id, request.branch_id):
        raise FoundationError("stale_conversation_delivery", "Saved delivery identity differs")
    if not request.fenced:
        raise FoundationError("invalid_transition", "Release requires explicit host fencing")
    if delivery.status not in ("claimed", "included"):
        raise FoundationError("invalid_transition", "Conversation delivery is terminal")
    if (
        request.manifest is not None
        and request.manifest != delivery.manifest
        or request.invocation_id is not None
        and request.invocation_id != delivery.invocation_id
        or request.assistant_source is not None
        or request.assistant_entry_id is not None
    ):
        raise FoundationError("stale_context", "Release cannot add or substitute send evidence")
    # Exact historical addresses are read through current permissions. A release
    # carries no authority to answer a question or repeat execution in a new epoch.
    refs = []
    for target, revision in connection.execute(
        "SELECT target_id,target_revision FROM conversation_delivery_edges WHERE delivery_id=?",
        (str(request.delivery_id),),
    ):
        ref = KnowledgeRef(record_id=UUID(target), revision=revision)
        _require_ref(connection, ref, authority.actor, authority.execution_epoch)
        refs.append({"record_id": target, "revision": revision})
    if not refs:
        raise FoundationError("content_unavailable", "Delivery bases were sanitized")
    unsettled = connection.execute(
        "SELECT 1 FROM conversation_delivery_invocations c LEFT JOIN knowledge_delivery k "
        "ON k.invocation_id=c.invocation_id WHERE c.delivery_id=? AND "
        "(k.invocation_id IS NULL OR k.stage!='prepared') LIMIT 1",
        (str(request.delivery_id),),
    ).fetchone()
    if unsettled:
        raise FoundationError("unknown_conversation_delivery", "A delivery has observed sends")
    if (
        delivery.invocation_id
        and not connection.execute(
            "SELECT 1 FROM conversation_delivery_invocations WHERE delivery_id=? "
            "AND invocation_id=?",
            (str(request.delivery_id), str(delivery.invocation_id)),
        ).fetchone()
    ):
        raise FoundationError("technical_state", "Delivery invocation link is absent")
    connection.execute(
        "INSERT INTO conversation_delivery_events VALUES (?,?,?)",
        (str(request.delivery_id), str(request.operation_id), request.action),
    )
    connection.execute(
        "UPDATE conversation_deliveries SET status='abandoned',operation_id=?,updated_at=? "
        "WHERE delivery_id=?",
        (str(request.operation_id), now, str(request.delivery_id)),
    )
    return {"delivery_id": str(request.delivery_id), "status": "abandoned"}, refs


def sanitize_conversation_dependency(
    connection: sqlite3.Connection, identifiers: set[str], now: str
) -> None:
    """Remove derived correlation links when any exact basis is sanitized."""
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 17:
        return
    affected: set[str] = set()
    for identifier in identifiers:
        affected.update(
            row[0]
            for row in connection.execute(
                "SELECT delivery_id FROM conversation_delivery_edges WHERE target_id=?",
                (identifier,),
            )
        )
    for identifier in affected:
        operations = connection.execute(
            "SELECT operation_id FROM conversation_delivery_events WHERE delivery_id=?",
            (identifier,),
        ).fetchall()
        for (operation_id,) in operations:
            connection.execute("DELETE FROM receipts WHERE operation_id=?", (operation_id,))
            connection.execute(
                "UPDATE operations SET fingerprint='DELETED' WHERE operation_id=?", (operation_id,)
            )
        connection.execute(
            "UPDATE conversation_deliveries SET status='stale',manifest_id=NULL,"
            "manifest_revision=NULL,invocation_id=NULL,assistant_source_id=NULL,"
            "assistant_source_revision=NULL,assistant_entry_id=NULL,updated_at=? "
            "WHERE delivery_id=?",
            (now, identifier),
        )
        connection.execute(
            "DELETE FROM conversation_delivery_edges WHERE delivery_id=?", (identifier,)
        )
        connection.execute(
            "DELETE FROM conversation_delivery_invocations WHERE delivery_id=?", (identifier,)
        )


__all__ = [
    "current_conversation_action",
    "read_ordinary_final_proof",
    "list_conversation_actions",
    "read_conversation_action",
    "list_conversation_deliveries",
    "read_conversation_delivery",
    "upgrade_conversation_space",
]
