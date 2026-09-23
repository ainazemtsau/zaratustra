"""The local bridge preserves proposal, explicit acceptance and restart reads."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_execution import InvocationFields, ready
from zaratustra.foundation import (
    AdmitInvocationRequest,
    DeleteWorkRequest,
    FinishInvocationRequest,
    FoundationError,
    PrepareInvocationRequest,
    SendInvocationRequest,
    apply_operation,
    authorize_local,
    complete_deletions,
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
    assert read_work(root, work_id, owner).state.status == "proposed"
    preview = bridge.accept_preview(session_id)
    nonce = UUID(cast(str, preview["nonce"]))
    accepted = bridge.accept(session_id, nonce, "I checked the summary")
    assert bridge.accept(session_id, nonce, "I checked the summary") == accepted
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
