"""Observed assigned answers and receipt-backed recovery, without a new execution graph."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, ValidationError

from .models import (
    ArtifactRef,
    AttemptResponseView,
    ConversationResponseProblem,
    CreateArtifactRequest,
    KnowledgeRef,
    LinkedOutput,
    LinkWorkOutputRequest,
    RecoverAttemptOutputRequest,
    RecoveredResponseProof,
    SourceState,
    WorkState,
)
from .operations import LocalAuthority, _authorize, _local_space, _subject_current, _subject_state
from .storage import FoundationError, canonical_json, space_connection


class _FinalEnvelope(BaseModel):
    # Match the existing assigned envelope: extra metadata does not alter final.text.
    model_config = ConfigDict(extra="allow", strict=True)
    zara: str
    text: str


def _problem(code: str, message: str) -> tuple[ConversationResponseProblem, ...]:
    return (ConversationResponseProblem(code=code, message=message),)


def _recovery_proof(
    connection: sqlite3.Connection, artifact: ArtifactRef
) -> RecoveredResponseProof | None:
    row = connection.execute(
        "SELECT body_json FROM record_revisions WHERE record_id=? AND revision=?",
        (str(artifact.artifact_id), artifact.revision),
    ).fetchone()
    if row is None:
        return None
    value = json.loads(row[0]).get("recovered_response")
    return None if value is None else RecoveredResponseProof.model_validate(value)


def read_artifact_recovery_proof(
    path: Path, artifact: ArtifactRef, authority: LocalAuthority
) -> RecoveredResponseProof | None:
    from .operations import read_artifact

    read_artifact(path, artifact.artifact_id, authority, revision=artifact.revision)
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        from .knowledge import _require_ref

        _require_ref(
            connection,
            KnowledgeRef(record_id=artifact.artifact_id, revision=artifact.revision),
            authority.actor,
            info.execution_epoch,
        )
        return _recovery_proof(connection, artifact)


def _attempt_response(
    connection: sqlite3.Connection,
    work_id: UUID,
    authority: LocalAuthority,
    *,
    epoch: int,
    attempt_id: UUID | None = None,
) -> AttemptResponseView:
    from .conversations import _terminal_response
    from .execution import _has_current_publication
    from .knowledge import _require_ref

    _authorize(
        connection,
        actor=authority.actor,
        action="record.read",
        epoch=epoch,
        resource_type="work",
        resource_id=work_id,
    )
    revision, status, _ = _subject_current(connection, work_id, "work")
    state = WorkState.model_validate(_subject_state(connection, work_id, revision))
    base: dict[str, Any] = {"work_id": work_id, "work_revision": revision}
    row = connection.execute(
        "SELECT attempt_id,session_id,status,work_revision,execution_epoch,generation "
        "FROM execution_attempts WHERE work_id=? "
        + ("AND attempt_id=? " if attempt_id else "")
        + "ORDER BY generation DESC LIMIT 1",
        (str(work_id), str(attempt_id)) if attempt_id else (str(work_id),),
    ).fetchone()
    if row is None:
        if attempt_id:
            raise FoundationError("not_found", "The addressed Attempt is absent")
        expected = {item.slot for item in state.expected_outputs}
        if expected and expected == {item.slot for item in state.linked_outputs}:
            for output in state.linked_outputs:
                _require_ref(
                    connection,
                    KnowledgeRef(
                        record_id=output.artifact.artifact_id, revision=output.artifact.revision
                    ),
                    authority.actor,
                    epoch,
                )
            return AttemptResponseView(
                **base, outcome="applied", artifact=state.linked_outputs[0].artifact
            )
        return AttemptResponseView(**base, outcome="no_send")
    attempt, session = UUID(row[0]), UUID(row[1])
    base.update(attempt_id=attempt, session_id=session)
    latest = connection.execute(
        "SELECT attempt_id FROM execution_attempts WHERE work_id=? "
        "ORDER BY generation DESC LIMIT 1",
        (str(work_id),),
    ).fetchone()
    if latest != (str(attempt),):
        return AttemptResponseView(
            **base,
            outcome="attention",
            diagnostics=_problem(
                "response_generation_changed",
                "A newer Attempt exists; inspect the historical answer before reuse",
            ),
        )
    expected = {item.slot for item in state.expected_outputs}
    calls = connection.execute(
        "SELECT invocation_id,status FROM execution_invocations WHERE attempt_id=? ORDER BY rowid",
        (str(attempt),),
    ).fetchall()
    assignment = connection.execute(
        "SELECT status FROM execution_assignments WHERE attempt_id=?", (str(attempt),)
    ).fetchone()
    earlier_unresolved = connection.execute(
        "SELECT i.invocation_id FROM execution_invocations i JOIN execution_attempts a "
        "ON a.attempt_id=i.attempt_id WHERE a.work_id=? AND a.generation<? "
        "AND i.status IN ('admitted','sent','unknown') ORDER BY a.generation DESC LIMIT 1",
        (str(work_id), row[5]),
    ).fetchone()
    if earlier_unresolved is not None:
        return AttemptResponseView(
            **base,
            outcome="unknown",
            invocation_id=UUID(earlier_unresolved[0]),
            diagnostics=_problem(
                "response_outcome_unknown", "An earlier send remains unresolved; do not dispatch"
            ),
        )
    if any(call[1] == "unknown" for call in calls) or assignment == ("unknown",):
        return AttemptResponseView(
            **base,
            outcome="unknown",
            diagnostics=_problem(
                "response_outcome_unknown",
                "Inspect the existing send; a fresh dispatch is forbidden",
            ),
        )
    if any(call[1] in ("admitted", "sent") for call in calls):
        if row[2] == "active" and assignment and assignment[0] not in ("stopped", "unknown"):
            return AttemptResponseView(**base, outcome="running")
        return AttemptResponseView(
            **base,
            outcome="unknown",
            diagnostics=_problem(
                "response_outcome_unknown",
                "Inspect the existing send; a fresh dispatch is forbidden",
            ),
        )
    if expected and expected == {item.slot for item in state.linked_outputs}:
        # A public Core link is a proposed output, not an assertion of Attempt success.
        for output in state.linked_outputs:
            _require_ref(
                connection,
                KnowledgeRef(
                    record_id=output.artifact.artifact_id, revision=output.artifact.revision
                ),
                authority.actor,
                epoch,
            )
        return AttemptResponseView(
            **base, outcome="applied", artifact=state.linked_outputs[0].artifact
        )
    if row[2] == "active" and assignment and assignment[0] not in ("stopped", "unknown"):
        # Saved assignment is not a license to replay its launch. Runtime owns observation.
        if calls:
            return AttemptResponseView(**base, outcome="running")
    answered = [UUID(call[0]) for call in calls if call[1] == "answered"]
    if answered and _has_current_publication(connection, work_id, attempt, state):
        return AttemptResponseView(**base, outcome="partial_output")
    if not answered:
        previous = connection.execute(
            "SELECT i.invocation_id,i.attempt_id FROM execution_invocations i "
            "JOIN execution_attempts a "
            "ON a.attempt_id=i.attempt_id JOIN execution_assignments s "
            "ON s.attempt_id=a.attempt_id WHERE a.work_id=? AND a.generation<? "
            "AND i.status='answered' ORDER BY a.generation DESC",
            (str(work_id), row[5]),
        ).fetchall()
        previous = [
            item
            for item in previous
            if not _has_current_publication(connection, work_id, UUID(item[1]), state)
        ]
        if previous:
            return AttemptResponseView(
                **base,
                outcome="attention",
                invocation_id=UUID(previous[0][0]),
                diagnostics=_problem(
                    "previous_response_pending",
                    "An earlier assigned answer has no complete output; do not dispatch again",
                ),
            )
        return AttemptResponseView(**base, outcome="no_send")
    if row[4] != epoch or status != "proposed" or revision != row[3]:
        return AttemptResponseView(
            **base,
            outcome="attention",
            diagnostics=_problem(
                "stale_response_basis", "Work or execution epoch changed after the observed reply"
            ),
        )
    if row[2] != "interrupted" or assignment != ("stopped",):
        return AttemptResponseView(
            **base,
            outcome="attention",
            diagnostics=_problem(
                "response_process_unresolved",
                "Observe the executor stop before recovering its answer",
            ),
        )
    if state.method != "none" or len(state.expected_outputs) != 1:
        return AttemptResponseView(
            **base,
            outcome="attention",
            diagnostics=_problem(
                "response_output_contract",
                "Recovery requires a simple Work with one declared output",
            ),
        )
    output_contract = state.expected_outputs[0]
    if not (
        output_contract.media_type.startswith("text/")
        or output_contract.media_type == "application/json"
        and output_contract.format_ref is not None
    ):
        return AttemptResponseView(
            **base,
            outcome="attention",
            diagnostics=_problem(
                "response_output_contract",
                "This output needs an explicit typed publication, not a textual reply",
            ),
        )
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 18:
        return AttemptResponseView(
            **base,
            outcome="attention",
            diagnostics=_problem(
                "response_proof_missing",
                "Old response has no schema-18 terminal proof; do not regenerate",
            ),
        )
    invocation = answered[-1]
    candidates: list[tuple[KnowledgeRef, SourceState]] = []
    for identifier, source_revision, payload in connection.execute(
        "SELECT r.record_id,r.revision,r.payload FROM knowledge_revisions r "
        "JOIN knowledge_records k ON k.record_id=r.record_id "
        "WHERE k.kind='source' AND k.status='active' "
        "AND json_extract(r.payload,'$.conversation_terminal.invocation_id')=?",
        (str(invocation),),
    ):
        source = SourceState.model_validate_json(payload)
        terminal = source.conversation_terminal
        if terminal and terminal.native_outcome == "completed" and terminal.stop_reason == "stop":
            candidates.append(
                (KnowledgeRef(record_id=UUID(identifier), revision=source_revision), source)
            )
    if len(candidates) != 1:
        return AttemptResponseView(
            **base,
            outcome="attention",
            invocation_id=invocation,
            diagnostics=_problem(
                "response_proof_missing",
                "Exactly one completed native original is required; do not regenerate",
            ),
        )
    ref, source = candidates[0]
    try:
        proof = _terminal_response(
            connection, ref, authority, epoch=epoch, session_id=session, invocation_id=invocation
        )
    except FoundationError as error:
        if error.code in ("permission_denied", "corrupt_space", "storage"):
            raise
        return AttemptResponseView(
            **base, outcome="attention", diagnostics=_problem(error.code, error.detail)
        )
    terminal = source.conversation_terminal
    assert terminal is not None
    if proof.outcome not in ("visible", "empty") or (proof.work_id, proof.attempt_id) != (
        work_id,
        attempt,
    ):
        return AttemptResponseView(
            **base,
            outcome="attention",
            diagnostics=proof.diagnostics
            or _problem("invalid_response_proof", "Answer belongs to another execution"),
        )
    if terminal.result_protocol is None:
        return AttemptResponseView(
            **base,
            outcome="attention",
            diagnostics=_problem(
                "response_protocol_missing", "The old assigned result protocol was not pinned"
            ),
        )
    from .activity_setup import _stage_for_work

    stage, setup = _stage_for_work(connection, work_id)
    expected_protocol = "zara_envelope"
    if stage is not None:
        if stage.retired or setup is None or stage.input_version != setup.input_version:
            return AttemptResponseView(
                **base,
                outcome="attention",
                diagnostics=_problem(
                    "stale_response_basis", "The setup inputs changed after this stage"
                ),
            )
        expected_protocol = stage.result_protocol or "zara_envelope"
    elif int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 16:
        node = connection.execute(
            "SELECT root_work_id FROM workflow_nodes WHERE work_id=?", (str(work_id),)
        ).fetchone()
        if node is not None:
            from .workflows import _nodes

            retained = next(
                item for item in _nodes(connection, UUID(node[0])) if item.work_id == work_id
            )
            if retained.retired:
                return AttemptResponseView(
                    **base,
                    outcome="attention",
                    diagnostics=_problem("stale_response_basis", "The workflow node was retired"),
                )
            expected_protocol = "workflow_json"
    if terminal.result_protocol != expected_protocol:
        return AttemptResponseView(
            **base,
            outcome="attention",
            diagnostics=_problem(
                "response_protocol_changed",
                "Native result protocol differs from the saved Work contract",
            ),
        )
    base.update(
        invocation_id=invocation,
        assistant_source=ref,
        manifest=proof.manifest,
        assistant_entry_id=proof.assistant_entry_id,
        result_protocol=terminal.result_protocol,
        slot=state.expected_outputs[0].slot,
    )
    return AttemptResponseView(**base, outcome="recoverable")


def read_attempt_response(
    path: Path, work_id: UUID, authority: LocalAuthority, *, attempt_id: UUID | None = None
) -> AttemptResponseView:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        return _attempt_response(
            connection, work_id, authority, epoch=info.execution_epoch, attempt_id=attempt_id
        )


def recover_attempt_output(
    connection: sqlite3.Connection,
    request: RecoverAttemptOutputRequest,
    *,
    authority: LocalAuthority,
    now: str,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    from .composition import check_composite_action
    from .data_store import index_artifact_knowledge_bases
    from .execution import _available_resource, _current_inputs
    from .operations import _apply_change, _write_artifact

    view = _attempt_response(
        connection, request.work_id, authority, epoch=epoch, attempt_id=request.attempt_id
    )
    if view.outcome != "recoverable":
        problem = view.diagnostics[0] if view.diagnostics else None
        raise FoundationError(
            problem.code if problem else "response_not_recoverable",
            problem.message if problem else f"Response is {view.outcome}",
        )
    if (
        view.work_revision != request.expected_work_revision
        or view.session_id != request.session_id
        or view.invocation_id != request.invocation_id
        or view.assistant_source != request.assistant_source
        or view.slot != request.slot
    ):
        raise FoundationError(
            "stale_response_basis", "Recovery address differs from saved response"
        )
    revision, state_status, _ = _subject_current(connection, request.work_id, "work")
    state = WorkState.model_validate(_subject_state(connection, request.work_id, revision))
    _current_inputs(connection, state, actor=request.actor, epoch=epoch)
    resource = connection.execute(
        "SELECT resource_id,resource_revision FROM execution_attempts WHERE attempt_id=?",
        (str(request.attempt_id),),
    ).fetchone()
    _available_resource(connection, UUID(resource[0]), request.work_id, resource[1])
    # The unchanged child issue/method/dependency admission applies to this proposed output.
    source_row = connection.execute(
        "SELECT payload FROM knowledge_revisions WHERE record_id=? AND revision=?",
        (str(request.assistant_source.record_id), request.assistant_source.revision),
    ).fetchone()
    source = SourceState.model_validate_json(source_row[0])
    assert (
        source.content is not None
        and source.conversation_terminal is not None
        and view.manifest is not None
    )
    content = source.content
    if view.result_protocol == "zara_envelope":
        try:
            envelope = _FinalEnvelope.model_validate_json(content)
        except ValidationError as error:
            raise FoundationError(
                "invalid_assigned_result", "Saved answer is not a final result envelope"
            ) from error
        if envelope.zara != "final" or not envelope.text.strip():
            raise FoundationError(
                "invalid_assigned_result", "Saved answer is not a nonblank final result"
            )
        content = envelope.text.encode("utf-8")
    contract = state.expected_outputs[0]
    artifact_id = uuid5(request.invocation_id, f"recovered-output:{request.slot}")
    child = CreateArtifactRequest(
        operation_id=request.operation_id,
        space_id=request.space_id,
        actor=request.actor,
        artifact_id=artifact_id,
        media_type=contract.media_type,
        content=content,
    )
    g, d = _authorize(
        connection,
        actor=request.actor,
        action="artifact.write",
        epoch=epoch,
        resource_type="artifact",
        resource_id=artifact_id,
    )
    grants.extend(g)
    decisions.extend(d)
    _write_artifact(connection, child, now, 1)
    proof = RecoveredResponseProof(
        work_id=request.work_id,
        work_revision=revision,
        attempt_id=request.attempt_id,
        session_id=request.session_id,
        invocation_id=request.invocation_id,
        assistant_source=request.assistant_source,
        manifest=view.manifest,
        assistant_entry_id=cast(str, view.assistant_entry_id),
        result_protocol=cast(Any, view.result_protocol),
        source_sha256=hashlib.sha256(source.content).hexdigest().upper(),
        content_sha256=hashlib.sha256(content).hexdigest().upper(),
        operation_id=request.operation_id,
    )
    connection.execute(
        "UPDATE record_revisions SET body_json=? WHERE record_id=? AND revision=1",
        (
            canonical_json(
                {"status": "active", "recovered_response": proof.model_dump(mode="json")}
            ),
            str(artifact_id),
        ),
    )
    artifact = ArtifactRef(artifact_id=artifact_id, revision=1)
    index_artifact_knowledge_bases(connection, artifact, (request.assistant_source, view.manifest))
    link = LinkWorkOutputRequest(
        operation_id=request.operation_id,
        space_id=request.space_id,
        actor=request.actor,
        work_id=request.work_id,
        expected_revision=revision,
        output=LinkedOutput(slot=request.slot, artifact=artifact),
    )
    check_composite_action(
        connection, link, actor=request.actor, epoch=epoch, grants=grants, decisions=decisions
    )
    _, targets = _apply_change(
        connection,
        link,
        now=now,
        epoch=epoch,
        authority=authority,
        grants=grants,
        decisions=decisions,
    )
    connection.execute(
        "INSERT INTO execution_events(operation_id,work_id,attempt_id,invocation_id,"
        "kind,created_at) "
        "VALUES (?,?,?,?,?,?)",
        (
            str(request.operation_id),
            str(request.work_id),
            str(request.attempt_id),
            str(request.invocation_id),
            request.kind,
            now,
        ),
    )
    return {
        "artifact_id": str(artifact_id),
        "revision": revision + 1,
        "work_id": str(request.work_id),
    }, [{"record_id": str(artifact_id), "revision": 1}, *targets]
