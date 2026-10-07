"""Durable, bounded setup of one new Activity; no model or executor in Core."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4, uuid5

from pydantic import ValidationError

from .models import (
    ActivitySetupDraft,
    ActivitySetupRequest,
    ActivitySetupReview,
    ActivitySetupRevision,
    ActivitySetupState,
    ActivityState,
    ApplyCandidateRequest,
    ArtifactRef,
    ChangeCandidateState,
    ChangeDecisionState,
    ClaimState,
    CompositeChange,
    CreateActivityRequest,
    CreateArtifactRequest,
    CreateCompositeWorkRequest,
    CreateDecisionRequest,
    CreateDevelopmentRequest,
    CreateKnowledgeRequest,
    CreateWorkRequest,
    DomainRequest,
    KnowledgeRef,
    MemoryMetadata,
    MemoryRequirement,
    MethodChange,
    MethodRef,
    OutputContract,
    RequestAttemptStopRequest,
    ReviseActivityRequest,
    SetupStage,
    SourceState,
    SpaceInfo,
    ValidationCriterion,
    ValidationPlanState,
    ValidationResultState,
    WorkState,
)
from .operations import LocalAuthority, _authorize, _local_space
from .storage import (
    SETUP_SCHEMA_NAME,
    SETUP_SCHEMA_SHA256,
    SETUP_SCHEMA_STATEMENTS,
    FoundationError,
    canonical_json,
    read_space,
    space_connection,
    utc_now,
)

AREAS = ("goal", "workflow", "history", "continuation", "extension", "capabilities", "consistency")


def upgrade_activity_setup_space(path: Path, authority: LocalAuthority) -> SpaceInfo:
    """Explicit additive 13 to 14 upgrade; no reinterpretation of old records."""
    with space_connection(path, writable=True) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active" or info.schema_version < 13:
            raise FoundationError("unsupported_schema", "Activity setup needs active schema 13")
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.backup",
            epoch=info.execution_epoch,
        )
        if info.schema_version == 13:
            for statement in SETUP_SCHEMA_STATEMENTS:
                connection.execute(statement)
            now = utc_now().isoformat()
            connection.execute(
                "INSERT INTO schema_migrations VALUES (14,?,?,?)",
                (SETUP_SCHEMA_NAME, SETUP_SCHEMA_SHA256, now),
            )
            connection.execute("PRAGMA user_version=14")
            connection.execute(
                "UPDATE spaces SET state_revision=state_revision+1 WHERE singleton=1"
            )
            connection.execute(
                "INSERT INTO maintenance_events VALUES (?,'schema_upgrade',?,?)",
                (str(uuid4()), now, canonical_json({"from": 13, "to": 14})),
            )
    return read_space(path)


def _current(
    connection: sqlite3.Connection, setup_id: UUID, revision: int | None = None
) -> ActivitySetupRevision:
    row = connection.execute(
        "SELECT s.current_revision,s.status,r.payload,r.sha256 FROM activity_setups s JOIN "
        "activity_setup_revisions r ON r.setup_id=s.setup_id "
        "AND r.revision=COALESCE(?,s.current_revision) WHERE s.setup_id=?",
        (revision, str(setup_id)),
    ).fetchone()
    if row is None:
        raise FoundationError("setup_unavailable", f"Activity setup {setup_id} is absent")
    if row[1] != "active" or row[2] is None:
        raise FoundationError("content_unavailable", f"Activity setup {setup_id} lost its basis")
    if hashlib.sha256(bytes(row[2])).hexdigest().upper() != row[3]:
        raise FoundationError("corrupt_content", "Activity setup revision checksum differs")
    return ActivitySetupRevision(
        setup_id=setup_id,
        revision=revision or row[0],
        state=ActivitySetupState.model_validate_json(row[2]),
    )


def _basis(
    connection: sqlite3.Connection,
    ref: KnowledgeRef,
    actor: str,
    epoch: int,
    *,
    current: bool = True,
) -> dict[str, Any]:
    from .knowledge import _require_ref

    _require_ref(connection, ref, actor, epoch)
    row = connection.execute(
        "SELECT r.current_revision,v.payload FROM knowledge_records r JOIN knowledge_revisions v "
        "ON v.record_id=r.record_id AND v.revision=? WHERE r.record_id=?",
        (ref.revision, str(ref.record_id)),
    ).fetchone()
    if row is None or (current and row[0] != ref.revision):
        raise FoundationError("stale_basis", f"Setup basis {ref.record_id} changed")
    state = json.loads(row[1])
    if state.get("kind") == "source":
        source = SourceState.model_validate_json(row[1])
        state = source.model_dump(mode="json", exclude={"content"})
        state["text"] = source.content.decode("utf-8") if source.content else None
    return {"ref": ref.model_dump(mode="json"), "state": state}


def _artifact(
    connection: sqlite3.Connection,
    ref: ArtifactRef,
    actor: str,
    epoch: int,
    *,
    current: bool = True,
) -> bytes:
    from .operations import _authorize_artifact_ref

    _authorize_artifact_ref(connection, ref, actor=actor, epoch=epoch, grants=[], decisions=[])
    row = connection.execute(
        "SELECT r.current_revision,c.payload,c.sha256 FROM records r JOIN managed_content c "
        "ON c.record_id=r.record_id AND c.revision=? WHERE r.record_id=?",
        (ref.revision, str(ref.artifact_id)),
    ).fetchone()
    if row is None or (current and row[0] != ref.revision) or row[1] is None:
        raise FoundationError("stale_basis", f"Setup Artifact {ref.artifact_id} changed")
    content = bytes(row[1])
    if hashlib.sha256(content).hexdigest().upper() != row[2]:
        raise FoundationError("corrupt_content", "Setup Artifact checksum differs")
    return content


def _readable(
    connection: sqlite3.Connection, state: ActivitySetupState, actor: str, epoch: int
) -> None:
    _authorize(
        connection,
        actor=actor,
        action="record.read",
        epoch=epoch,
        resource_type="activity",
        resource_id=state.activity_id,
    )
    for ref in state.sources:
        _basis(connection, ref, actor, epoch, current=False)


def read_activity_setup(
    path: Path, setup_id: UUID, authority: LocalAuthority, *, revision: int | None = None
) -> ActivitySetupRevision:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 14:
            raise FoundationError("upgrade_required", "Activity setup needs schema 14")
        item = _current(connection, setup_id, revision)
        _readable(connection, item.state, authority.actor, info.execution_epoch)
        return item


def list_activity_setups(
    path: Path,
    authority: LocalAuthority,
    *,
    activity_id: UUID | None = None,
    limit: int = 50,
    pending_only: bool = False,
) -> tuple[ActivitySetupRevision, ...]:
    if not 1 <= limit <= 100:
        raise FoundationError("invalid_request", "Setup page must contain 1 to 100 records")
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 14:
            return ()
        result = []
        for (identifier,) in connection.execute(
            (
                "SELECT a.setup_id FROM activity_setups a JOIN activity_setup_revisions r "
                "ON r.setup_id=a.setup_id AND r.revision=a.current_revision "
                "WHERE a.status='active' AND (? IS NULL OR a.activity_id=?) "
                "AND (?=0 OR json_extract(CAST(r.payload AS TEXT),'$.phase') "
                "NOT IN ('ready','cancelled')) ORDER BY a.setup_id"
            ),
            (str(activity_id) if activity_id else None,) * 2 + (int(pending_only),),
        ):
            item = _current(connection, UUID(identifier))
            try:
                _readable(connection, item.state, authority.actor, info.execution_epoch)
            except FoundationError as error:
                if error.code in (
                    "permission_denied",
                    "decision_denied",
                    "content_unavailable",
                    "stale_basis",
                ):
                    continue
                raise
            result.append(item)
            if len(result) == limit:
                break
        return tuple(result)


def check_setup_execution(
    connection: sqlite3.Connection, work_id: UUID, actor: str, epoch: int
) -> None:
    """Old Activities are untouched; unfinished new setups admit only their stages."""
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 14:
        return
    row = connection.execute(
        (
            "SELECT a.setup_id FROM activity_setups a JOIN subject_records w ON "
            "w.parent_id=a.activity_id WHERE w.record_id=?"
        ),
        (str(work_id),),
    ).fetchone()
    if row is None:
        return
    state = _current(connection, UUID(row[0])).state
    if state.phase == "ready":
        return
    for ref in state.sources:
        _basis(connection, ref, actor, epoch)
    if state.phase not in ("paused", "cancelled", "needs_attention") and any(
        stage.work_id == work_id
        and stage.output is None
        and not stage.retired
        and stage.input_version == state.input_version
        for stage in state.stages
    ):
        return
    raise FoundationError("setup_pending", f"Activity setup {row[0]} is {state.phase}")


def check_setup_record_access(
    connection: sqlite3.Connection, record_id: UUID, actor: str, epoch: int
) -> None:
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 14:
        return
    for (identifier,) in connection.execute(
        "SELECT DISTINCT setup_id FROM activity_setup_edges WHERE target_id=? "
        "AND role IN ('derived_artifact','derived_knowledge','method','work','activity')",
        (str(record_id),),
    ):
        row = connection.execute(
            "SELECT status FROM activity_setups WHERE setup_id=?", (identifier,)
        ).fetchone()
        if row[0] != "active":
            continue
        state = _current(connection, UUID(identifier)).state
        for ref in state.sources:
            _basis(connection, ref, actor, epoch, current=False)


def activity_setup_memory(
    path: Path, activity_id: UUID, authority: LocalAuthority
) -> tuple[MemoryRequirement, ...]:
    """Exact ready setup requirements, also for subsequent plain Work."""
    entries = list_activity_setups(path, authority, activity_id=activity_id, limit=1)
    if not entries or entries[0].state.phase != "ready" or not entries[0].state.draft:
        return ()
    with space_connection(path) as (connection, info):
        draft = ActivitySetupDraft.model_validate_json(
            _artifact(
                connection,
                entries[0].state.draft,
                authority.actor,
                info.execution_epoch,
                current=False,
            )
        )
        return draft.memory


def _save(
    connection: sqlite3.Connection,
    request: ActivitySetupRequest,
    state: ActivitySetupState,
    revision: int,
    now: str,
) -> None:
    if revision == 1:
        connection.execute(
            "INSERT INTO activity_setups VALUES (?,?,1,'active')",
            (str(request.setup_id), str(state.activity_id)),
        )
    else:
        connection.execute(
            "UPDATE activity_setups SET current_revision=? WHERE setup_id=?",
            (revision, str(request.setup_id)),
        )
    data = state.model_dump_json().encode("utf-8")
    connection.execute(
        "INSERT INTO activity_setup_revisions VALUES (?,?,?,?,?)",
        (
            str(request.setup_id),
            revision,
            str(request.operation_id),
            data,
            hashlib.sha256(data).hexdigest().upper(),
        ),
    )
    refs: list[tuple[str, UUID, int]] = [
        ("basis", ref.record_id, ref.revision) for ref in state.sources
    ]
    for ref in state.sources:
        row = connection.execute(
            "SELECT payload FROM knowledge_revisions WHERE record_id=? AND revision=?",
            (str(ref.record_id), ref.revision),
        ).fetchone()
        if row and row[0]:
            original = json.loads(row[0])
            if original.get("connection") == "activity-setup" and original.get(
                "scope_activity_id"
            ) == str(state.activity_id):
                refs.append(("owned_source", ref.record_id, ref.revision))
    refs.append(("activity", state.activity_id, 1))
    for stage in state.stages:
        refs.extend(
            (
                ("work", stage.work_id, 1),
                ("derived_artifact", stage.packet.artifact_id, stage.packet.revision),
            )
        )
        if stage.output:
            refs.append(("derived_artifact", stage.output.artifact_id, stage.output.revision))
    refs.extend(("work", ref, 1) for ref in state.activated_works)
    refs.extend(("method", ref.method_id, ref.version) for ref in state.activated_methods)
    if state.repair_work:
        refs.append(("work", state.repair_work, 1))
    if state.phase == "ready":
        refs.append(("derived_knowledge", uuid5(request.setup_id, "instructions"), 1))
    for ordinal, (role, identifier, version) in enumerate(refs):
        connection.execute(
            "INSERT INTO activity_setup_edges VALUES (?,?,?,?,?,?)",
            (str(request.setup_id), revision, ordinal, str(identifier), version, role),
        )


def apply_setup_change(
    connection: sqlite3.Connection,
    request: ActivitySetupRequest,
    *,
    now: str,
    epoch: int,
    authority: LocalAuthority,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, Any], list[dict[str, object]]]:
    from .operations import _apply_change, _operation_action

    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 14:
        raise FoundationError("upgrade_required", "Activity setup needs explicit schema 14")
    targets: list[dict[str, object]] = []

    def effect(kind: type[Any], **fields: Any) -> dict[str, Any]:
        nested = kind(
            operation_id=request.operation_id,
            space_id=request.space_id,
            actor=request.actor,
            **fields,
        )
        action, resource_type, resource_id = _operation_action(nested)
        added_grants, added_decisions = _authorize(
            connection,
            actor=request.actor,
            action=action,
            epoch=epoch,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        grants.extend(added_grants)
        decisions.extend(added_decisions)
        answer, refs = _apply_change(
            connection,
            cast(DomainRequest, nested),
            now=now,
            epoch=epoch,
            authority=authority,
            grants=grants,
            decisions=decisions,
        )
        targets.extend(refs)
        return answer

    def source(text: str) -> KnowledgeRef:
        identifier = uuid5(request.operation_id, "user-source")
        effect(
            CreateKnowledgeRequest,
            record_id=identifier,
            state=SourceState(
                channel="conversation_user",
                connection="activity-setup",
                profile_revision=1,
                source_event_id=str(request.operation_id),
                scope_activity_id=request.activity_id,
                sender=request.actor,
                media_type="text/plain",
                capture="full",
                content=text.encode("utf-8"),
            ),
        )
        return KnowledgeRef(record_id=identifier, revision=1)

    if request.action == "begin":
        if not request.title or not request.text or request.expected_revision is not None:
            raise FoundationError("invalid_request", "Begin needs a title and original request")
        effect(
            CreateActivityRequest,
            activity_id=request.activity_id,
            state=ActivityState(title=request.title, goal=request.text[:4096]),
        )
        refs = (source(request.text),) + request.source_refs
        for ref in refs:
            _basis(connection, ref, request.actor, epoch)
        state = ActivitySetupState(
            activity_id=request.activity_id, owner=request.actor, phase="collecting", sources=refs
        )
        revision = 1
    else:
        current = _current(connection, request.setup_id)
        if (
            current.revision != request.expected_revision
            or current.state.activity_id != request.activity_id
        ):
            raise FoundationError("stale_setup", "Setup revision or Activity differs")
        state, revision = current.state, current.revision + 1
        if state.owner != request.actor:
            raise FoundationError(
                "permission_denied", "Only the initiating local owner controls setup"
            )
        _readable(connection, state, request.actor, epoch)
        if state.phase in ("ready", "cancelled"):
            raise FoundationError("setup_closed", "Setup is already ready or cancelled")
        updates: dict[str, Any] = {}
        if request.action == "answer":
            if not request.text:
                raise FoundationError("invalid_request", "Answer must retain original text")
            answering_wait = False
            restart_wait = False
            retired = state.stages
            if state.stages and state.stages[-1].output is None and not state.stages[-1].retired:
                waiting_work_id = str(state.stages[-1].work_id)
                answering_wait = (
                    state.phase == "needs_input"
                    and connection.execute(
                        "SELECT 1 FROM execution_waits "
                        "WHERE work_id=? AND status='answered' LIMIT 1",
                        (waiting_work_id,),
                    ).fetchone()
                    is not None
                )
                live = connection.execute(
                    (
                        "SELECT 1 FROM execution_assignments WHERE work_id=? AND status IN "
                        "('assigned','waiting','ready','stop_requested','unknown') LIMIT 1"
                    ),
                    (waiting_work_id,),
                ).fetchone()
                if not answering_wait and live:
                    raise FoundationError(
                        "setup_running", "Pause the active stage before changing its inputs"
                    )
                if not live and state.phase in ("needs_input", "paused") and state.question:
                    restart_wait = (
                        connection.execute(
                            "SELECT 1 FROM execution_waits WHERE work_id=? AND status='closed' "
                            "AND question=? LIMIT 1",
                            (waiting_work_id, state.question.encode("utf-8")),
                        ).fetchone()
                        is not None
                    )
                    answering_wait = restart_wait
                if not answering_wait:
                    retired = state.stages[:-1] + (
                        state.stages[-1].model_copy(update={"retired": True}),
                    )
            refs = state.sources + (source(request.text),) + request.source_refs
            for ref in refs:
                _basis(connection, ref, request.actor, epoch)
            if restart_wait:
                stage = state.stages[-1]
                continuation_packet = json.loads(
                    _artifact(connection, stage.packet, request.actor, epoch)
                )
                continuation_packet["sources"] = [
                    _basis(connection, ref, request.actor, epoch) for ref in refs
                ]
                packet_id = uuid5(request.operation_id, "continuation-packet")
                effect(
                    CreateArtifactRequest,
                    artifact_id=packet_id,
                    media_type="application/json",
                    content=canonical_json(continuation_packet).encode("utf-8"),
                )
                from .operations import _subject_state, _write_subject

                work_revision = connection.execute(
                    "SELECT current_revision FROM subject_records WHERE record_id=?",
                    (str(stage.work_id),),
                ).fetchone()[0]
                current_work = WorkState.model_validate(
                    _subject_state(connection, stage.work_id, work_revision)
                )
                new_packet = ArtifactRef(artifact_id=packet_id, revision=1)
                added_grants, added_decisions = _authorize(
                    connection,
                    actor=request.actor,
                    action="work.write",
                    epoch=epoch,
                    resource_type="work",
                    resource_id=stage.work_id,
                )
                grants.extend(added_grants)
                decisions.extend(added_decisions)
                _write_subject(
                    connection,
                    record_id=stage.work_id,
                    kind="work",
                    parent_id=state.activity_id,
                    operation_id=request.operation_id,
                    actor=request.actor,
                    now=now,
                    status=current_work.status,
                    state=current_work.model_copy(update={"inputs": (new_packet,)}),
                    revision=work_revision + 1,
                )
                targets.append({"record_id": str(stage.work_id), "revision": work_revision + 1})
                retired = state.stages[:-1] + (stage.model_copy(update={"packet": new_packet}),)
            updates = dict(
                sources=refs,
                input_version=state.input_version + int(not answering_wait),
                phase={"draft": "drafting", "correction": "correcting", "review": "reviewing"}[
                    state.stages[-1].kind
                ]
                if answering_wait
                else "collecting",
                question=None,
                draft=state.draft if answering_wait else None,
                review=state.review if answering_wait else None,
                stages=retired,
            )
        elif request.action == "question":
            if not request.text:
                raise FoundationError("invalid_request", "Question text is required")
            updates = dict(question=request.text, phase="needs_input")
        elif request.action in ("pause", "cancel", "attention"):
            for stage in state.stages:
                for attempt_id, session_id, assignment_revision in connection.execute(
                    "SELECT a.attempt_id,t.session_id,a.revision FROM execution_assignments a "
                    "JOIN execution_attempts t ON t.attempt_id=a.attempt_id "
                    "WHERE a.work_id=? AND a.status IN ('assigned','waiting','ready')",
                    (str(stage.work_id),),
                ):
                    effect(
                        RequestAttemptStopRequest,
                        work_id=stage.work_id,
                        attempt_id=UUID(attempt_id),
                        session_id=UUID(session_id),
                        expected_assignment_revision=assignment_revision,
                        reason="Activity setup stopped by its saved state",
                    )
            updates = dict(
                phase={"pause": "paused", "cancel": "cancelled", "attention": "needs_attention"}[
                    request.action
                ],
                result=request.text,
                auto_resume=request.auto_resume if request.action == "pause" else False,
            )
            if request.action == "attention" and state.repair_work is None:
                repair_id = uuid5(request.setup_id, "technical-repair")
                effect(
                    CreateWorkRequest,
                    work_id=repair_id,
                    state=WorkState(
                        activity_id=state.activity_id,
                        goal="Diagnose the saved technical obstacle to Activity setup",
                        constraints=(request.text or "Read the exact interrupted setup history",),
                        inputs=(state.stages[-1].packet,) if state.stages else (),
                        expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
                    ),
                )
                updates["repair_work"] = repair_id
        elif request.action in ("resume", "retry"):
            if state.question:
                raise FoundationError("incomplete_context", "Answer the saved question first")
            successful_review = False
            if state.review and state.draft:
                report = ActivitySetupReview.model_validate_json(
                    _artifact(connection, state.review, request.actor, epoch)
                )
                successful_review = (
                    report.draft == state.draft
                    and report.input_version == state.input_version
                    and not report.unresolved
                    and not any(item.blocking for item in report.findings)
                )
            if request.action == "retry":
                updates["pass_boundary"] = state.reviews_started
            elif state.reviews_started - state.pass_boundary >= 5 and not successful_review:
                raise FoundationError(
                    "setup_review_exhausted", "Explicit retry is required after five review passes"
                )
            updates["phase"] = (
                "activating"
                if successful_review
                else "collecting"
                if not state.draft
                else "correcting"
                if state.review
                else "drafting"
            )
            updates["result"] = None
            updates["auto_resume"] = False
        elif request.action == "start_stage":
            if (
                state.phase in ("paused", "needs_input", "needs_attention")
                or not request.stage_kind
                or not request.stage_instruction
            ):
                raise FoundationError(
                    "invalid_transition", "Setup must be runnable with a stage instruction"
                )
            if state.stages and state.stages[-1].output is None and not state.stages[-1].retired:
                raise FoundationError(
                    "setup_running", "Existing stage must finish or be explicitly retired"
                )
            if request.stage_kind != "draft" and state.draft is None:
                raise FoundationError(
                    "invalid_transition", "Correction/review needs the whole current draft"
                )
            if state.reviews_started - state.pass_boundary >= 5:
                raise FoundationError("setup_review_exhausted", "Five reviews already started")
            packet: dict[str, Any] = {
                "setup_id": str(request.setup_id),
                "activity_id": str(state.activity_id),
                "input_version": state.input_version,
                "sources": [_basis(connection, ref, request.actor, epoch) for ref in state.sources],
            }
            if state.draft:
                packet["draft_ref"] = state.draft.model_dump(mode="json")
                packet["draft"] = ActivitySetupDraft.model_validate_json(
                    _artifact(connection, state.draft, request.actor, epoch)
                ).model_dump(mode="json")
            if state.review:
                packet["previous_review"] = ActivitySetupReview.model_validate_json(
                    _artifact(connection, state.review, request.actor, epoch)
                ).model_dump(mode="json")
            packet["result_schema"] = (
                ActivitySetupReview.model_json_schema()
                if request.stage_kind == "review"
                else ActivitySetupDraft.model_json_schema()
            )
            packet["supported_path"] = (
                "Source originals and revisioned knowledge; "
                "public memory catalog/batch/history/cache; "
                "plain Work with output contracts or composite Method Work "
                "with at least one child; "
                "all initial children are fresh plain Work in this Activity. "
                "Named inputs must match "
                "the Method exactly. Initial Methods are self-contained (no existing role Methods "
                "or capability admission). Outputs remain separately owner-accepted. Sleep stores "
                "experience and scoped Candidates for later change. Manual external exchange "
                "preserves provenance; external API sending is not provided by this setup."
            )
            packet_id = uuid5(request.operation_id, "packet")
            work_id = uuid5(request.operation_id, "stage-work")
            effect(
                CreateArtifactRequest,
                artifact_id=packet_id,
                media_type="application/json",
                content=canonical_json(packet).encode("utf-8"),
            )
            effect(
                CreateWorkRequest,
                work_id=work_id,
                state=WorkState(
                    activity_id=state.activity_id,
                    goal=request.stage_instruction,
                    inputs=(ArtifactRef(artifact_id=packet_id, revision=1),),
                    expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
                ),
            )
            reviews = state.reviews_started + int(request.stage_kind == "review")
            stage = SetupStage(
                work_id=work_id,
                kind=request.stage_kind,
                input_version=state.input_version,
                packet=ArtifactRef(artifact_id=packet_id, revision=1),
                draft=state.draft,
                review_pass=reviews if request.stage_kind == "review" else 0,
            )
            updates = dict(
                stages=state.stages + (stage,),
                reviews_started=reviews,
                phase={"draft": "drafting", "correction": "correcting", "review": "reviewing"}[
                    request.stage_kind
                ],
            )
        elif request.action == "complete_stage":
            if not state.stages or not request.output or state.stages[-1].output is not None:
                raise FoundationError(
                    "invalid_transition", "Completion needs one active stage output"
                )
            stage = state.stages[-1]
            if stage.retired:
                raise FoundationError("stale_basis", "The stage was retired after changed inputs")
            from .operations import _subject_state

            row = connection.execute(
                "SELECT current_revision FROM subject_records WHERE record_id=?",
                (str(stage.work_id),),
            ).fetchone()
            work = WorkState.model_validate(_subject_state(connection, stage.work_id, row[0]))
            if (
                request.output not in [item.artifact for item in work.linked_outputs]
                or stage.input_version != state.input_version
            ):
                raise FoundationError(
                    "stale_basis", "Output does not belong to the current setup stage"
                )
            raw = _artifact(connection, request.output, request.actor, epoch)
            try:
                if stage.kind == "review":
                    review = ActivitySetupReview.model_validate_json(raw)
                    if review.draft != state.draft or review.input_version != state.input_version:
                        raise FoundationError(
                            "stale_basis", "Review addresses an old draft or interview"
                        )
                    updates = dict(
                        review=request.output,
                        reviews_completed=state.reviews_completed + 1,
                        phase="correcting"
                        if any(item.blocking for item in review.findings)
                        else "needs_input"
                        if review.unresolved
                        else "activating",
                        question="\n".join(review.unresolved) or None,
                    )
                    if (
                        updates["phase"] == "correcting"
                        and state.reviews_started - state.pass_boundary >= 5
                    ):
                        updates.update(phase="needs_attention", result=review.conclusion)
                else:
                    draft = ActivitySetupDraft.model_validate_json(raw)
                    updates = dict(
                        draft=request.output,
                        review=None,
                        phase="needs_input" if draft.open_questions else "drafting",
                        question="\n".join(draft.open_questions) or None,
                    )
            except ValidationError as error:
                raise FoundationError("invalid_setup_result", str(error)) from error
            updates["stages"] = state.stages[:-1] + (
                stage.model_copy(update={"output": request.output}),
            )
        elif request.action == "finish":
            state = _activate(connection, request, state, effect, epoch)
        else:
            raise FoundationError("invalid_request", "Unknown setup action")
        state = ActivitySetupState.model_validate({**state.model_dump(), **updates})
    _save(connection, request, state, revision, now)
    targets.append({"record_id": str(request.setup_id), "revision": revision})
    return {
        "setup_id": str(request.setup_id),
        "revision": revision,
        "phase": state.phase,
        "activity_id": str(state.activity_id),
    }, targets


def _activate(
    connection: sqlite3.Connection,
    request: ActivitySetupRequest,
    state: ActivitySetupState,
    effect: Any,
    epoch: int,
) -> ActivitySetupState:
    from .composition import method_checksum

    if state.phase != "activating" or not state.draft or not state.review:
        raise FoundationError(
            "setup_not_reviewed", "Activation needs a successful whole current review"
        )
    for basis in state.sources:
        _basis(connection, basis, request.actor, epoch)
    draft = ActivitySetupDraft.model_validate_json(
        _artifact(connection, state.draft, request.actor, epoch)
    )
    review = ActivitySetupReview.model_validate_json(
        _artifact(connection, state.review, request.actor, epoch)
    )
    if (
        review.draft != state.draft
        or review.input_version != state.input_version
        or review.unresolved
        or draft.open_questions
        or any(item.blocking for item in review.findings)
    ):
        raise FoundationError("stale_basis", "Setup does not have a current successful review")
    activity_revision = connection.execute(
        "SELECT current_revision FROM subject_records WHERE record_id=?",
        (str(state.activity_id),),
    ).fetchone()[0]
    effect(
        ReviseActivityRequest,
        activity_id=state.activity_id,
        expected_revision=activity_revision,
        state=ActivityState(title=draft.title, goal=draft.goal),
    )
    effect(
        CreateKnowledgeRequest,
        record_id=uuid5(request.setup_id, "instructions"),
        state=ClaimState(
            proposition=draft.instructions,
            epistemic_kind="derived",
            status="current",
            scope_activity_id=state.activity_id,
            evidence=state.sources
            + (
                KnowledgeRef(record_id=state.draft.artifact_id, revision=state.draft.revision),
                KnowledgeRef(record_id=state.review.artifact_id, revision=state.review.revision),
            ),
            interpretation_basis="Initial setup admitted after its exact complete review",
            memory=MemoryMetadata(
                title="Activity instructions",
                activity_id=state.activity_id,
                context_role="required",
            ),
        ),
    )
    refs = {
        item.key: MethodRef(
            method_id=uuid5(request.setup_id, f"method:{item.key}"),
            version=1,
            checksum=method_checksum(item.definition),
        )
        for item in draft.methods
    }
    if draft.methods:
        candidate_id = uuid5(request.setup_id, f"candidate:{state.draft.artifact_id}")
        decision_id = uuid5(candidate_id, "adoption")
        changes = tuple(
            MethodChange(
                method_id=refs[item.key].method_id, to_version=1, definition=item.definition
            )
            for item in draft.methods
        )
        evidence = KnowledgeRef(record_id=state.review.artifact_id, revision=state.review.revision)
        results = tuple(
            ValidationResultState(
                result_id=uuid5(candidate_id, area),
                criterion=area,
                outcome="met",
                evidence=(evidence,),
                actual_input=(
                    f"Whole setup {state.draft.artifact_id}@{state.draft.revision}; "
                    f"interview {state.input_version}"
                ),
                environment=(
                    "Structure review in an assigned ordinary Pi; no trial or owner acceptance"
                ),
            )
            for area in AREAS
        )
        candidate = ChangeCandidateState(
            target=changes[0]
            if len(changes) == 1
            else CompositeChange(
                package_id=uuid5(candidate_id, "methods"), to_version=1, parts=changes
            ),
            proposal="Reviewed initial setup of this new Activity",
            evidence=state.sources + (evidence,),
            expected_outcome="Usable initial Methods preserving versioned history",
            scope_activity_ids=(state.activity_id,),
            exclusions="No other Activity, Grant, deletion, program change or publication",
            impact="Only new Methods and Work of this setup",
            affected_work_ids=(),
            unknowns="Semantic review is not proof of future behavior",
            validation_plan=ValidationPlanState(
                baseline=str(state.draft),
                environment="Ordinary Pi setup review",
                criteria=tuple(
                    ValidationCriterion(
                        key=area,
                        question=f"Review {area}",
                        pass_condition="No material obstacle",
                        basis=(evidence,),
                    )
                    for area in AREAS
                ),
                cases="Whole current setup and actual user requirements",
                method="Fresh full review after every correction",
                sufficiency="Initial structure; no claim of real-use quality",
                limits="No synthetic onboarding trial",
                stop_and_restore="Retain draft and stop setup",
                decision_condition="All areas reviewed; no blocking finding",
                follow_up="Real use and Sleep",
            ),
            results=results,
            restore_plan="Stop adoption without rewriting history",
            irreversible_effects="None outside this new Activity",
        )
        effect(CreateDevelopmentRequest, record_id=candidate_id, state=candidate)
        effect(
            CreateDecisionRequest,
            decision_id=decision_id,
            state=ChangeDecisionState(
                statement=(
                    f"Initial setup authorized by {state.owner}; "
                    f"exact complete review {state.review.artifact_id}"
                ),
                candidate_id=candidate_id,
                candidate_revision=1,
                mode="regular",
                use="permitted",
                scope_activity_id=state.activity_id,
                validation_result_ids=tuple(item.result_id for item in results),
                review_condition="Review again when premises or process change",
            ),
        )
        effect(
            ApplyCandidateRequest,
            candidate_id=candidate_id,
            candidate_revision=1,
            decision_id=decision_id,
            decision_revision=1,
            mode="regular",
        )
    works = []
    for template in draft.works:
        identifier = uuid5(request.setup_id, f"work:{template.key}")
        method = refs.get(template.method_key) if template.method_key else None
        outputs = (
            next(
                item.definition.named_outputs
                for item in draft.methods
                if item.key == template.method_key
            )
            if method
            else template.expected_outputs
        )
        work = WorkState(
            activity_id=state.activity_id,
            goal=template.goal,
            inputs=tuple(item.artifact for item in template.plan.named_inputs)
            if template.plan is not None
            else (state.draft,),
            constraints=(draft.instructions,),
            expected_outputs=outputs,
            method=method or "none",
        )
        if method:
            if template.plan is None:
                raise FoundationError(
                    "invalid_setup_result", "A Method Work needs its actual typed composite plan"
                )
            for child in template.plan.children:
                if (
                    child.state.activity_id != state.activity_id
                    or child.state.method != "none"
                    or child.state.status != "proposed"
                    or child.state.linked_outputs
                ):
                    raise FoundationError(
                        "out_of_scope",
                        "Initial plan children must be fresh plain Work in this Activity",
                    )
            plan = template.plan.model_copy(
                update={"basis": tuple(dict.fromkeys(template.plan.basis + (state.draft,)))}
            )
            effect(CreateCompositeWorkRequest, work_id=identifier, state=work, plan=plan)
        else:
            effect(CreateWorkRequest, work_id=identifier, state=work)
        works.append(identifier)
    return state.model_copy(
        update={
            "phase": "ready",
            "activated_works": tuple(works),
            "activated_methods": tuple(refs.values()),
            "result": draft.instructions + "\n\n" + draft.first_action,
        }
    )


def sanitize_setup_dependency(connection: sqlite3.Connection, record_id: UUID, now: str) -> None:
    """Retire copies and receipts, keeping addresses when their basis is deleted."""
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 14:
        return
    affected = [
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT setup_id FROM activity_setup_edges WHERE target_id=? "
            "AND role IN ('basis','owned_source','derived_artifact','method','activity')",
            (str(record_id),),
        )
    ]
    for identifier in affected:
        if (
            connection.execute(
                "SELECT status FROM activity_setups WHERE setup_id=?", (identifier,)
            ).fetchone()[0]
            != "active"
        ):
            continue
        connection.execute(
            "UPDATE activity_setups SET status='unavailable' WHERE setup_id=?", (identifier,)
        )
        for (operation,) in connection.execute(
            "SELECT operation_id FROM activity_setup_revisions WHERE setup_id=?", (identifier,)
        ):
            connection.execute("DELETE FROM receipts WHERE operation_id=?", (operation,))
            connection.execute(
                "UPDATE operations SET fingerprint='DELETED' WHERE operation_id=?", (operation,)
            )
        connection.execute(
            "UPDATE activity_setup_revisions SET payload=NULL,sha256=NULL WHERE setup_id=?",
            (identifier,),
        )
        assigned = [
            {"work_id": row[0], "attempt_id": row[1]}
            for row in connection.execute(
                "SELECT a.work_id,a.attempt_id FROM execution_assignments a WHERE a.work_id IN "
                "(SELECT target_id FROM activity_setup_edges WHERE setup_id=? AND role='work')",
                (identifier,),
            )
        ]
        connection.execute(
            "UPDATE execution_waits SET question=NULL,remainder=NULL,answer=NULL,status='purged' "
            "WHERE work_id IN (SELECT target_id FROM activity_setup_edges "
            "WHERE setup_id=? AND role='work')",
            (identifier,),
        )
        for target, role in connection.execute(
            (
                "SELECT DISTINCT target_id,role FROM activity_setup_edges WHERE setup_id=? "
                "AND role IN ('derived_artifact','derived_knowledge','owned_source',"
                "'method','work','activity')"
            ),
            (identifier,),
        ):
            if role in ("derived_knowledge", "owned_source"):
                from .knowledge import _sanitize_deleted

                _sanitize_deleted(connection, UUID(target), now)
            elif role == "derived_artifact":
                origin = connection.execute(
                    "SELECT operation_id FROM record_revisions WHERE record_id=? "
                    "ORDER BY revision LIMIT 1",
                    (target,),
                ).fetchone()[0]
                connection.execute(
                    "INSERT OR IGNORE INTO deletion_jobs(operation_id,record_id,status,created_at) "
                    "VALUES (?,?,'pending',?)",
                    (origin, target, now),
                )
                connection.execute(
                    "INSERT OR REPLACE INTO maintenance_events VALUES "
                    "(?,'technical_deletion_targets',?,?)",
                    (origin, now, canonical_json({"artifact_id": target, "assigned": assigned})),
                )
                connection.execute(
                    "DELETE FROM managed_content WHERE record_id=?",
                    (target,),
                )
                connection.execute(
                    "UPDATE records SET status='deleted' WHERE record_id=?", (target,)
                )
                for (operation,) in connection.execute(
                    "SELECT operation_id FROM record_revisions WHERE record_id=?", (target,)
                ):
                    connection.execute("DELETE FROM receipts WHERE operation_id=?", (operation,))
                    connection.execute(
                        "UPDATE operations SET fingerprint='DELETED' WHERE operation_id=?",
                        (operation,),
                    )
            elif role == "method":
                from .composition import _sanitize_deleted_method_sources

                for version, checksum in connection.execute(
                    "SELECT version,checksum FROM method_versions WHERE method_id=?", (target,)
                ):
                    _sanitize_deleted_method_sources(
                        connection,
                        MethodRef(method_id=UUID(target), version=version, checksum=checksum),
                    )
                connection.execute(
                    "UPDATE method_versions SET payload=NULL,status='deleted' WHERE method_id=?",
                    (target,),
                )
            else:
                connection.execute("DELETE FROM subject_content WHERE record_id=?", (target,))
                if role == "activity":
                    origin = connection.execute(
                        "SELECT operation_id FROM subject_revisions WHERE record_id=? "
                        "ORDER BY revision LIMIT 1",
                        (target,),
                    ).fetchone()[0]
                    connection.execute(
                        "INSERT OR IGNORE INTO subject_deletion_jobs"
                        "(operation_id,record_id,status,created_at) VALUES (?,?,'pending',?)",
                        (origin, target, now),
                    )
            from .development import sanitize_deleted_development_dependency
            from .knowledge import sanitize_deleted_knowledge_dependency

            sanitize_deleted_knowledge_dependency(connection, UUID(target), now)
            sanitize_deleted_development_dependency(connection, UUID(target), now)
            from .composition import sanitize_deleted_dependency

            if role == "derived_artifact":
                sanitize_deleted_dependency(
                    connection,
                    artifact_id=UUID(target),
                    operation_id=uuid5(UUID(identifier), f"retire:{target}"),
                    now=now,
                )
            elif role in ("work", "activity"):
                for (operation,) in connection.execute(
                    "SELECT operation_id FROM subject_revisions WHERE record_id=?", (target,)
                ):
                    connection.execute("DELETE FROM receipts WHERE operation_id=?", (operation,))
                    connection.execute(
                        "UPDATE operations SET fingerprint='DELETED' WHERE operation_id=?",
                        (operation,),
                    )
        connection.execute(
            (
                "UPDATE backup_inventory SET status='contaminated' WHERE status IN "
                "('planned','failed','complete') AND state_revision >= (SELECT "
                "MIN(o.state_revision) FROM operations o JOIN activity_setup_revisions s ON "
                "s.operation_id=o.operation_id WHERE s.setup_id=?)"
            ),
            (identifier,),
        )
