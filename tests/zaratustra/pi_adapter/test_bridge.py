"""The local bridge preserves proposal, explicit acceptance and restart reads."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import UUID, uuid4, uuid5

import pytest

from tests.zaratustra.foundation.test_execution import InvocationFields, ready
from zaratustra.foundation import (
    AdmitInvocationRequest,
    ArtifactRef,
    CreateArtifactRequest,
    CreateGrantRequest,
    DeleteWorkRequest,
    FinishInvocationRequest,
    FoundationError,
    GrantState,
    LinkedOutput,
    LinkWorkOutputRequest,
    PrepareInvocationRequest,
    SendInvocationRequest,
    apply_operation,
    authorize_local,
    complete_deletions,
    managed_pi_lock,
    managed_pi_sessions,
    read_artifact,
    read_execution,
    read_work,
)
from zaratustra.pi_adapter import Bridge


def test_publish_accept_and_fresh_read(tmp_path: Path) -> None:
    root, working, space_id, _, work_id, _, owner = ready(tmp_path)
    bridge = Bridge(root, owner, working, limit_units=100)
    session_id = uuid4()
    connection = bridge.connect(session_id)
    assert connection["execution_epoch"] == 1
    activity_id = read_work(root, work_id, owner).state.activity_id
    selected = bridge.select(session_id, activity_id, work_id)
    selected_work = selected["work"]
    assert isinstance(selected_work, dict)
    selected_state = selected_work["state"]
    assert isinstance(selected_state, dict)
    assert selected_state["status"] == "proposed"
    started = bridge.start_attempt(session_id, interrupt_previous=False)
    attempt_id = UUID(cast(str, started["attempt_id"]))
    invocation_id = uuid4()
    common: InvocationFields = dict(
        invocation_id=invocation_id, attempt_id=attempt_id, work_id=work_id, session_id=session_id
    )
    for request in (
        PrepareInvocationRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            purpose="content",
            provider="local",
            model="synthetic",
            transport="http-sse",
            request_sha256="B" * 64,
            request_bytes=10,
            reserve_units=30,
            **common,
        ),
        AdmitInvocationRequest(
            operation_id=uuid4(), space_id=space_id, actor=owner.actor, **common
        ),
        SendInvocationRequest(operation_id=uuid4(), space_id=space_id, actor=owner.actor, **common),
        FinishInvocationRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            outcome="answered",
            usage_units=9,
            **common,
        ),
    ):
        bridge.operation(session_id, request.model_dump(mode="json"))
    first = bridge.publish(
        session_id, attempt_id, "summary", "text/plain", "Fictional note summary."
    )
    assert (
        bridge.publish(session_id, attempt_id, "summary", "text/plain", "Fictional note summary.")
        == first
    )
    with pytest.raises(FoundationError, match="operation_conflict"):
        bridge.publish(session_id, attempt_id, "summary", "text/plain", "Different result")
    assert read_work(root, work_id, owner).state.status == "proposed"
    preview = bridge.accept_preview(session_id)
    nonce = UUID(cast(str, preview["nonce"]))
    accepted = bridge.accept(session_id, nonce, "I checked the summary")
    assert bridge.accept(session_id, nonce, "I checked the summary") == accepted
    assert (
        bridge.publish(session_id, attempt_id, "summary", "text/plain", "Fictional note summary.")
        == first
    )
    reopened = authorize_local(root, actor=owner.actor, source_ref="fresh-local-session")
    state = read_execution(root, work_id, reopened)
    assert state.work.state.status == "succeeded"
    assert "work.accept" in state.work_rights and "model.invoke" in state.work_rights
    assert state.activity.state.status == "ongoing"
    assert state.work.state.acceptance is not None
    assert state.work.state.acceptance.authority_source.startswith("pi-ui-confirm:")
    assert state.outputs[0].content == b"Fictional note summary."
    assert state.committed_units == 9 and state.held_units == 0


def test_work_deletion_purges_execution(tmp_path: Path) -> None:
    root, working, space_id, _, work_id, _, owner = ready(tmp_path)
    bridge = Bridge(root, owner, working, limit_units=100)
    session_id = uuid4()
    bridge.connect(session_id)
    bridge.select(session_id, read_work(root, work_id, owner).state.activity_id, work_id)
    bridge.start_attempt(session_id, interrupt_previous=False)
    apply_operation(
        root,
        DeleteWorkRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            work_id=work_id,
            expected_revision=1,
        ),
        owner,
    )
    result = complete_deletions(root, owner)
    assert result.pending_jobs == 0 and result.live_store_sanitized
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_execution(root, work_id, owner)


def test_late_attempt_cannot_replace_newer_output(tmp_path: Path) -> None:
    root, working, space_id, _, work_id, _, owner = ready(tmp_path)
    bridge = Bridge(root, owner, working, limit_units=100)
    session_id = uuid4()
    bridge.connect(session_id)
    bridge.select(session_id, read_work(root, work_id, owner).state.activity_id, work_id)
    attempt_id = UUID(
        cast(str, bridge.start_attempt(session_id, interrupt_previous=False)["attempt_id"])
    )
    common: InvocationFields = dict(
        invocation_id=uuid4(), attempt_id=attempt_id, work_id=work_id, session_id=session_id
    )
    for request in (
        PrepareInvocationRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            purpose="content",
            provider="local",
            model="synthetic",
            transport="http-sse",
            request_sha256="B" * 64,
            request_bytes=10,
            reserve_units=30,
            **common,
        ),
        AdmitInvocationRequest(
            operation_id=uuid4(), space_id=space_id, actor=owner.actor, **common
        ),
        SendInvocationRequest(operation_id=uuid4(), space_id=space_id, actor=owner.actor, **common),
        FinishInvocationRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            outcome="answered",
            usage_units=9,
            **common,
        ),
    ):
        apply_operation(root, request, owner)
    newer_id = uuid4()
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            artifact_id=newer_id,
            media_type="text/plain",
            content=b"Newer answer",
        ),
        owner,
    )
    apply_operation(
        root,
        LinkWorkOutputRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            work_id=work_id,
            expected_revision=1,
            output=LinkedOutput(
                slot="summary", artifact=ArtifactRef(artifact_id=newer_id, revision=1)
            ),
        ),
        owner,
    )
    with pytest.raises(FoundationError, match="stale_work"):
        bridge.publish(session_id, attempt_id, "summary", "text/plain", "Late answer")
    current = read_execution(root, work_id, owner)
    assert current.work.revision == 2
    assert current.work.state.linked_outputs[0].artifact.artifact_id == newer_id
    assert current.outputs[0].content == b"Newer answer"
    with pytest.raises(FoundationError, match="not_found"):
        read_artifact(root, uuid5(attempt_id, "artifact:summary"), owner)


def test_managed_pi_history_is_retired_with_content_deletion(tmp_path: Path) -> None:
    root, working, space_id, _, work_id, _, owner = ready(tmp_path)
    history = managed_pi_sessions(root, space_id, create=True)
    copied = history / "synthetic-session.jsonl"
    copied.write_text('{"text":"fictional note"}\n', encoding="utf-8")
    unrelated = tmp_path / "unmanaged-note.txt"
    unrelated.write_text("keep this", encoding="utf-8")
    apply_operation(
        root,
        DeleteWorkRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            work_id=work_id,
            expected_revision=1,
        ),
        owner,
    )
    with pytest.raises(FoundationError, match="deletion_pending"):
        Bridge(root, owner, working, limit_units=100).connect(uuid4())
    with managed_pi_lock(root), pytest.raises(FoundationError, match="history_busy"):
        complete_deletions(root, owner)
    assert copied.exists()
    assert complete_deletions(root, owner).pending_jobs == 0
    assert not copied.exists()
    assert history.joinpath("owner.txt").is_file()
    assert unrelated.read_text(encoding="utf-8") == "keep this"


def test_accept_retires_active_attempt_after_restart(tmp_path: Path) -> None:
    root, working, space_id, _, work_id, _, owner = ready(tmp_path)
    bridge = Bridge(root, owner, working, limit_units=100)
    session_id = uuid4()
    bridge.connect(session_id)
    bridge.select(session_id, read_work(root, work_id, owner).state.activity_id, work_id)
    attempt_id = UUID(
        cast(str, bridge.start_attempt(session_id, interrupt_previous=False)["attempt_id"])
    )
    result_id = uuid4()
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            artifact_id=result_id,
            media_type="text/plain",
            content=b"Synthetic result",
        ),
        owner,
    )
    apply_operation(
        root,
        LinkWorkOutputRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            work_id=work_id,
            expected_revision=1,
            output=LinkedOutput(
                slot="summary", artifact=ArtifactRef(artifact_id=result_id, revision=1)
            ),
        ),
        owner,
    )
    apply_operation(
        root,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            grant_id=uuid4(),
            state=GrantState(
                grantee="synthetic-acceptor",
                actions=("space.inspect", "record.read", "work.accept"),
            ),
        ),
        owner,
    )
    acceptor = authorize_local(root, actor="synthetic-acceptor", source_ref="local-acceptor")
    acceptor_bridge = Bridge(root, acceptor, working, limit_units=100)
    fresh_session = uuid4()
    acceptor_bridge.connect(fresh_session)
    acceptor_bridge.select(
        fresh_session, read_work(root, work_id, owner).state.activity_id, work_id
    )
    preview = acceptor_bridge.accept_preview(fresh_session)
    acceptor_bridge.accept(
        fresh_session, UUID(cast(str, preview["nonce"])), "Reviewed synthetic result"
    )
    current = read_execution(root, work_id, owner)
    assert current.work.state.status == "succeeded"
    assert current.attempts[-1].attempt_id == attempt_id
    assert current.attempts[-1].status == "interrupted"
    assert current.held_units == 0
    acceptor_rights = read_execution(root, work_id, acceptor).work_rights
    assert "work.accept" in acceptor_rights and "work.execute" not in acceptor_rights
