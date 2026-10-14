"""Exact read-only native response proof independent of conversation deliveries."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_activity_setup import Case, _case
from tests.zaratustra.foundation.test_conversations import (
    _apply,
    _ordinary_final_case,
    _terminal_original,
    _upgrade,
)
from zaratustra.foundation import (
    ContextState,
    CreateDecisionRequest,
    CreateKnowledgeRequest,
    DecisionState,
    DeleteKnowledgeRequest,
    FoundationError,
    KnowledgeRef,
    PublishAttemptOutputRequest,
    RecordContextDeliveryRequest,
    RecoverRequest,
    ReviseKnowledgeRequest,
    SourceState,
    StopAttemptRequest,
    apply_operation,
    authorize_local,
    authorize_recovery,
    create_backup,
    read_activity_setup,
    read_context_delivery,
    read_execution,
    read_knowledge,
    read_space,
    read_terminal_response,
    read_work,
    restore_backup,
    upgrade_delivery_correlation_space,
)
from zaratustra.foundation.storage import space_connection


def _recorded(
    tmp_path: Path,
    *,
    stage: str = "answered",
    content: bytes = b"",
    reason: str = "stop",
    outcome: Any = "completed",
) -> tuple[Case, KnowledgeRef, KnowledgeRef, UUID, UUID, str]:
    case = _case(tmp_path)
    _upgrade(case)
    upgrade_delivery_correlation_space(case[0], case[2])
    manifest, invocation, session = KnowledgeRef(record_id=uuid4(), revision=1), uuid4(), uuid4()
    _apply(
        case,
        CreateKnowledgeRequest,
        record_id=manifest.record_id,
        state=ContextState(
            purpose="Fictional native reply",
            session_id=session,
            mandatory=read_activity_setup(case[0], case[3], case[2]).state.sources,
        ),
    )
    _apply(
        case,
        RecordContextDeliveryRequest,
        invocation_id=invocation,
        manifest=manifest,
        stage="prepared",
        free_call=True,
        reserve_units=1,
    )
    if stage != "prepared":
        _apply(
            case,
            RecordContextDeliveryRequest,
            invocation_id=invocation,
            manifest=manifest,
            stage="sent",
            free_call=True,
            request_sha256="A" * 64,
            request_bytes=100,
        )
    if stage in ("answered", "unknown"):
        _apply(
            case,
            RecordContextDeliveryRequest,
            invocation_id=invocation,
            manifest=manifest,
            stage=stage,
            free_call=True,
            usage_units=0 if stage == "answered" else None,
        )
    source, entry = _terminal_original(
        case,
        {"session_id": session},
        manifest,
        invocation,
        content,
        stop_reason=reason,
        outcome=outcome,
    )
    return case, source, manifest, invocation, session, entry


@pytest.mark.parametrize(
    "content,reason,native,outcome,code",
    (
        (b"", "stop", "completed", "empty", None),
        (b" \t\r\n", "stop", "completed", "empty", None),
        ("\u00a0\u3000".encode(), "stop", "completed", "empty", None),
        ("Готово".encode(), "stop", "completed", "visible", None),
        (b"text", "length", "completed", "attention", "response_truncated"),
        (b"", "toolUse", "tool_call", "attention", "native_response_not_final"),
        (b"", "error", "error", "attention", "native_response_incomplete"),
        (b"", "aborted", "aborted", "attention", "native_response_incomplete"),
        (b"", "stop", "unknown", "unknown", "native_response_unknown"),
    ),
)
def test_readonly_terminal_classification_without_action_or_delivery(
    tmp_path: Path,
    content: bytes,
    reason: str,
    native: str,
    outcome: str,
    code: str | None,
) -> None:
    case, source, manifest, invocation, session, entry = _recorded(
        tmp_path,
        content=content,
        reason=reason,
        outcome=native,
    )
    before = read_space(case[0])
    view = read_terminal_response(
        case[0],
        source,
        case[2],
        session_id=session,
        invocation_id=invocation,
        manifest=manifest,
        assistant_entry_id=entry,
    )
    assert view.outcome == outcome and view.assistant_source == source
    assert (view.manifest, view.invocation_id, view.session_id) == (manifest, invocation, session)
    assert view.work_id is None and view.attempt_id is None
    assert tuple(item.code for item in view.diagnostics) == (() if code is None else (code,))
    assert read_terminal_response(case[0], source, case[2], session_id=session) == view
    assert read_space(case[0]) == before
    original = read_knowledge(case[0], source.record_id, case[2]).state
    assert isinstance(original, SourceState) and original.content == content


@pytest.mark.parametrize(
    "stage,code",
    (
        ("prepared", "response_accounting_pending"),
        ("sent", "response_accounting_pending"),
        ("unknown", "response_send_unknown"),
    ),
)
def test_unconfirmed_provider_outcome_never_authorizes_empty_repair(
    tmp_path: Path,
    stage: str,
    code: str,
) -> None:
    case, source, _, _, session, _ = _recorded(tmp_path, stage=stage)
    view = read_terminal_response(case[0], source, case[2], session_id=session)
    assert view.outcome == "unknown" and view.diagnostics[0].code == code


@pytest.mark.parametrize(
    "mismatch",
    ("session", "invocation", "manifest", "entry", "source_fragment", "manifest_fragment"),
)
def test_terminal_reader_requires_exact_whole_native_correlations(
    tmp_path: Path, mismatch: str
) -> None:
    case, source, manifest, invocation, session, entry = _recorded(tmp_path, content=b"a")
    kwargs: dict[str, Any] = dict(
        session_id=session, invocation_id=invocation, manifest=manifest, assistant_entry_id=entry
    )
    if mismatch == "session":
        kwargs["session_id"] = uuid4()
    elif mismatch == "invocation":
        kwargs["invocation_id"] = uuid4()
    elif mismatch == "manifest":
        kwargs["manifest"] = KnowledgeRef(record_id=uuid4(), revision=1)
    elif mismatch == "entry":
        kwargs["assistant_entry_id"] = "another-native-entry"
    elif mismatch == "source_fragment":
        source = source.model_copy(update={"start": 0, "end": 1})
    else:
        kwargs["manifest"] = manifest.model_copy(update={"start": 0, "end": 1})
    with pytest.raises(FoundationError, match="invalid_response_proof"):
        read_terminal_response(case[0], source, case[2], **kwargs)


@pytest.mark.parametrize("published", (False, True))
def test_work_terminal_proof_survives_completed_attempt_without_acceptance(
    tmp_path: Path,
    published: bool,
) -> None:
    case, work, attempt, session = _ordinary_final_case(tmp_path, "valid")
    upgrade_delivery_correlation_space(case[0], case[2])
    execution = read_execution(case[0], work, case[2])
    invocation = execution.invocations[-1].invocation_id
    ledger = read_context_delivery(case[0], invocation, case[2])
    manifest = KnowledgeRef(record_id=UUID(str(ledger["manifest_id"])), revision=1)
    source, _ = _terminal_original(case, {"session_id": session}, manifest, invocation, b" ")
    if published:
        _apply(
            case,
            PublishAttemptOutputRequest,
            work_id=work,
            attempt_id=attempt,
            session_id=session,
            slot="report",
            media_type="text/plain",
            content=b"Fictional result",
        )
    _apply(
        case,
        StopAttemptRequest,
        work_id=work,
        attempt_id=attempt,
        session_id=session,
        outcome="completed",
    )
    view = read_terminal_response(case[0], source, case[2], session_id=session)
    assert view.outcome == "empty" and (view.work_id, view.attempt_id) == (work, attempt)
    assert read_work(case[0], work, case[2]).state.acceptance is None


@pytest.mark.parametrize(
    "corruption,expected",
    (
        ("unknown", "response_send_unknown"),
        ("digest", "invalid_response_proof"),
        ("missing", "invalid_response_proof"),
    ),
)
def test_work_reply_requires_actual_matching_execution_accounting(
    tmp_path: Path,
    corruption: str,
    expected: str,
) -> None:
    case, work, _, session = _ordinary_final_case(tmp_path, "valid")
    upgrade_delivery_correlation_space(case[0], case[2])
    invocation = read_execution(case[0], work, case[2]).invocations[-1].invocation_id
    ledger = read_context_delivery(case[0], invocation, case[2])
    manifest = KnowledgeRef(record_id=UUID(str(ledger["manifest_id"])), revision=1)
    source, _ = _terminal_original(case, {"session_id": session}, manifest, invocation, b"")
    with space_connection(case[0], writable=True) as (connection, _):
        if corruption == "unknown":
            connection.execute(
                "UPDATE execution_invocations SET status='unknown',usage_units=NULL "
                "WHERE invocation_id=?",
                (str(invocation),),
            )
        elif corruption == "digest":
            connection.execute(
                "UPDATE execution_invocations SET request_sha256=? WHERE invocation_id=?",
                ("B" * 64, str(invocation)),
            )
        else:
            connection.execute(
                "DELETE FROM execution_invocations WHERE invocation_id=?", (str(invocation),)
            )
    if corruption == "unknown":
        view = read_terminal_response(case[0], source, case[2], session_id=session)
        assert view.outcome == "unknown" and view.diagnostics[0].code == expected
    else:
        with pytest.raises(FoundationError, match=expected):
            read_terminal_response(case[0], source, case[2], session_id=session)


@pytest.mark.parametrize(
    "bad_ref,code",
    (("missing", "not_found"), ("context", "wrong_kind"), ("original", "invalid_response_proof")),
)
def test_unproved_originals_cannot_be_classified_as_empty(
    tmp_path: Path, bad_ref: str, code: str
) -> None:
    case, source, manifest, _, session, _ = _recorded(tmp_path)
    if bad_ref == "missing":
        source = KnowledgeRef(record_id=uuid4(), revision=1)
    elif bad_ref == "context":
        source = manifest
    else:
        source = read_activity_setup(case[0], case[3], case[2]).state.sources[0]
    with pytest.raises(FoundationError, match=code):
        read_terminal_response(case[0], source, case[2], session_id=session)


@pytest.mark.parametrize("removed", ("source", "manifest"))
def test_deleted_response_basis_is_unavailable_not_empty(tmp_path: Path, removed: str) -> None:
    case, source, manifest, _, session, _ = _recorded(tmp_path)
    target = source if removed == "source" else manifest
    _apply(case, DeleteKnowledgeRequest, record_id=target.record_id, expected_revision=1)
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_terminal_response(case[0], source, case[2], session_id=session)


def test_read_rights_are_rechecked_before_exposing_response_classification(tmp_path: Path) -> None:
    case, source, _, _, session, _ = _recorded(tmp_path)
    _apply(
        case,
        CreateDecisionRequest,
        decision_id=uuid4(),
        state=DecisionState(
            statement="Deny fictional record reads",
            effect="deny",
            actions=("record.read",),
            subjects=("owner",),
        ),
    )
    with pytest.raises(FoundationError, match="decision_denied"):
        read_terminal_response(case[0], source, case[2], session_id=session)


def test_old_context_revision_keeps_exact_historical_proof(tmp_path: Path) -> None:
    case, source, manifest, _, session, _ = _recorded(tmp_path)
    old = read_knowledge(case[0], manifest.record_id, case[2]).state
    assert isinstance(old, ContextState)
    _apply(
        case,
        ReviseKnowledgeRequest,
        record_id=manifest.record_id,
        expected_revision=1,
        state=old.model_copy(update={"purpose": "A later context"}),
    )
    view = read_terminal_response(case[0], source, case[2], session_id=session)
    assert view.manifest == manifest and view.outcome == "empty"


@pytest.mark.parametrize(
    "corruption,expected",
    (
        ("utf8", "invalid_response_utf8"),
        ("sender", "corrupt_space"),
        ("pin", "invalid_response_proof"),
    ),
)
def test_corrupt_stored_evidence_never_becomes_repair_permission(
    tmp_path: Path,
    corruption: str,
    expected: str,
) -> None:
    case, source, _, invocation, session, _ = _recorded(tmp_path)
    # Public operations reject these corrupt states. Inject only to test read refusal.
    with space_connection(case[0], writable=True) as (connection, _):
        if corruption == "pin":
            connection.execute(
                "UPDATE knowledge_delivery SET context_session_id=? WHERE invocation_id=?",
                (str(uuid4()), str(invocation)),
            )
        else:
            row = connection.execute(
                "SELECT payload FROM knowledge_revisions WHERE record_id=? AND revision=1",
                (str(source.record_id),),
            ).fetchone()
            payload = json.loads(row[0])
            payload["content" if corruption == "utf8" else "sender"] = (
                "_w==" if corruption == "utf8" else "another-agent"
            )
            connection.execute(
                "UPDATE knowledge_revisions SET payload=? WHERE record_id=? AND revision=1",
                (json.dumps(payload).encode("utf-8"), str(source.record_id)),
            )
    if corruption == "utf8":
        view = read_terminal_response(case[0], source, case[2], session_id=session)
        assert view.outcome == "attention" and view.diagnostics[0].code == expected
    else:
        with pytest.raises(FoundationError, match=expected):
            read_terminal_response(case[0], source, case[2], session_id=session)


def test_response_from_backup_remains_history_and_cannot_repair_new_epoch(tmp_path: Path) -> None:
    case, source, _, _, session, _ = _recorded(tmp_path)
    backup = create_backup(case[0], uuid4(), case[2])
    restored = tmp_path / "restored-terminal"
    restored.mkdir()
    recovery = authorize_recovery(actor="owner", source_ref="fictional recovery")
    restore_backup(backup.package, restored, recovery)
    apply_operation(
        restored,
        RecoverRequest(
            operation_id=uuid4(),
            space_id=case[1],
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        recovery,
    )
    authority = authorize_local(restored, actor="owner", source_ref="fictional reopened owner")
    with pytest.raises(FoundationError, match="stale_response_epoch"):
        read_terminal_response(restored, source, authority, session_id=session)
    assert isinstance(read_knowledge(restored, source.record_id, authority).state, SourceState)
