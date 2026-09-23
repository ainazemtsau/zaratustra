"""Interactive execution ledger and pre-send admission against synthetic Core data."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, TypedDict
from uuid import UUID, uuid4

import pytest

from zaratustra.foundation import (
    Action,
    ActivityState,
    AdmitInvocationRequest,
    ArtifactRef,
    BootstrapRequest,
    CreateActivityRequest,
    CreateArtifactRequest,
    CreateGrantRequest,
    CreateResourceRequest,
    CreateWorkRequest,
    FinishInvocationRequest,
    FoundationError,
    GrantState,
    LocalAuthority,
    OutputContract,
    PrepareInvocationRequest,
    ResourceState,
    ReviseArtifactRequest,
    RevokeGrantRequest,
    SendInvocationRequest,
    StartAttemptRequest,
    StopAttemptRequest,
    WorkState,
    apply_operation,
    authorize_local,
    initialize_space,
    read_execution,
    read_receipt,
    upgrade_execution_space,
    upgrade_space,
)


class InvocationFields(TypedDict):
    invocation_id: UUID
    attempt_id: UUID
    work_id: UUID
    session_id: UUID


def ready(tmp_path: Path) -> tuple[Path, Path, UUID, UUID, UUID, UUID, LocalAuthority]:
    root = tmp_path / "space"
    root.mkdir()
    working = tmp_path / "workdir"
    working.mkdir()
    info = initialize_space(root)
    owner = authorize_local(root, actor="synthetic-owner", source_ref="local-synthetic")
    apply_operation(
        root,
        BootstrapRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=owner.actor,
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        owner,
    )
    assert upgrade_space(root, owner).schema_version == 2
    assert upgrade_execution_space(root, owner).schema_version == 3
    input_id, activity_id, work_id, resource_id = (uuid4() for _ in range(4))
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=owner.actor,
            artifact_id=input_id,
            media_type="text/plain",
            content=b"fictional note",
        ),
        owner,
    )
    apply_operation(
        root,
        CreateActivityRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=owner.actor,
            activity_id=activity_id,
            state=ActivityState(title="Fictional", goal="Keep going"),
        ),
        owner,
    )
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=owner.actor,
            work_id=work_id,
            state=WorkState(
                activity_id=activity_id,
                goal="Summarize the fictional note",
                inputs=(ArtifactRef(artifact_id=input_id, revision=1),),
                expected_outputs=(OutputContract(slot="summary", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    apply_operation(
        root,
        CreateResourceRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=owner.actor,
            resource_id=resource_id,
            work_id=work_id,
            state=ResourceState(label="Synthetic workdir", root=working, limit_units=100),
        ),
        owner,
    )
    return root, working, info.space_id, input_id, work_id, resource_id, owner


def start(
    root: Path,
    space_id: UUID,
    work_id: UUID,
    resource_id: UUID,
    owner: LocalAuthority,
    *,
    previous: UUID | None = None,
) -> tuple[UUID, UUID]:
    attempt_id, session_id = uuid4(), uuid4()
    apply_operation(
        root,
        StartAttemptRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            attempt_id=attempt_id,
            work_id=work_id,
            expected_work_revision=1,
            resource_id=resource_id,
            expected_resource_revision=1,
            session_id=session_id,
            previous_attempt_id=previous,
        ),
        owner,
    )
    return attempt_id, session_id


def invocation(
    root: Path,
    space_id: UUID,
    work_id: UUID,
    attempt_id: UUID,
    session_id: UUID,
    owner: LocalAuthority,
    reserve: int,
) -> tuple[UUID, PrepareInvocationRequest]:
    invocation_id = uuid4()
    prepared = PrepareInvocationRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor=owner.actor,
        invocation_id=invocation_id,
        attempt_id=attempt_id,
        work_id=work_id,
        session_id=session_id,
        purpose="content",
        provider="local",
        model="synthetic",
        transport="http-sse",
        request_sha256="A" * 64,
        request_bytes=123,
        reserve_units=reserve,
    )
    apply_operation(root, prepared, owner)
    return invocation_id, prepared


def test_reserve_replay_unknown_and_new_session(tmp_path: Path) -> None:
    root, _, space_id, _, work_id, resource_id, owner = ready(tmp_path)
    attempt_id, session_id = start(root, space_id, work_id, resource_id, owner)
    invocation_id, prepared = invocation(root, space_id, work_id, attempt_id, session_id, owner, 40)
    assert apply_operation(root, prepared, owner).operation_id == prepared.operation_id
    assert read_receipt(root, prepared.operation_id, owner).kind == "prepare_invocation"
    common: InvocationFields = dict(
        invocation_id=invocation_id, attempt_id=attempt_id, work_id=work_id, session_id=session_id
    )
    apply_operation(
        root,
        AdmitInvocationRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            **common,
        ),
        owner,
    )
    apply_operation(
        root,
        SendInvocationRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            **common,
        ),
        owner,
    )
    before = read_execution(root, work_id, owner)
    assert before.held_units == 40 and before.committed_units == 0
    apply_operation(
        root,
        FinishInvocationRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            outcome="unknown",
            **common,
        ),
        owner,
    )
    apply_operation(
        root,
        StopAttemptRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
            outcome="interrupted",
        ),
        owner,
    )
    next_attempt, next_session = start(
        root, space_id, work_id, resource_id, owner, previous=attempt_id
    )
    second_id, _ = invocation(root, space_id, work_id, next_attempt, next_session, owner, 61)
    with pytest.raises(FoundationError, match="budget_exhausted"):
        apply_operation(
            root,
            AdmitInvocationRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor=owner.actor,
                invocation_id=second_id,
                attempt_id=next_attempt,
                work_id=work_id,
                session_id=next_session,
            ),
            owner,
        )
    reopened = authorize_local(root, actor=owner.actor, source_ref="new-local-session")
    snapshot = read_execution(root, work_id, reopened)
    assert snapshot.held_units == 40 and snapshot.remaining_units == 60
    assert snapshot.attempts[-1].previous_attempt_id == attempt_id
    assert snapshot.invocations[0].status == "unknown"


def test_stale_input_blocks_pre_send(tmp_path: Path) -> None:
    root, _, space_id, input_id, work_id, resource_id, owner = ready(tmp_path)
    attempt_id, session_id = start(root, space_id, work_id, resource_id, owner)
    apply_operation(
        root,
        ReviseArtifactRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            artifact_id=input_id,
            expected_revision=1,
            media_type="text/plain",
            content=b"revised fictional note",
        ),
        owner,
    )
    with pytest.raises(FoundationError, match="stale_input"):
        invocation(root, space_id, work_id, attempt_id, session_id, owner, 20)
    assert read_execution(root, work_id, owner).invocations == ()


def test_current_execution_and_model_grants_are_separate(tmp_path: Path) -> None:
    root, _, space_id, input_id, work_id, resource_id, owner = ready(tmp_path)
    execution_grant = uuid4()
    scoped_grants: tuple[
        tuple[UUID, tuple[Action, ...], Literal["artifact", "work"], UUID], ...
    ] = (
        (uuid4(), ("record.read",), "artifact", input_id),
        (execution_grant, ("work.execute",), "work", work_id),
    )
    for grant_id, actions, resource_type, target_id in scoped_grants:
        apply_operation(
            root,
            CreateGrantRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor=owner.actor,
                grant_id=grant_id,
                state=GrantState(
                    grantee="synthetic-worker",
                    actions=actions,
                    resource_type=resource_type,
                    resource_id=target_id,
                ),
            ),
            owner,
        )
    worker = authorize_local(root, actor="synthetic-worker", source_ref="worker-console")
    attempt_id, session_id = start(root, space_id, work_id, resource_id, worker)
    with pytest.raises(FoundationError, match="permission_denied"):
        invocation(root, space_id, work_id, attempt_id, session_id, worker, 10)
    invoke_grant = uuid4()
    apply_operation(
        root,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            grant_id=invoke_grant,
            state=GrantState(
                grantee=worker.actor,
                actions=("model.invoke",),
                resource_type="work",
                resource_id=work_id,
            ),
        ),
        owner,
    )
    invocation_id, _ = invocation(root, space_id, work_id, attempt_id, session_id, worker, 10)
    apply_operation(
        root,
        RevokeGrantRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            grant_id=invoke_grant,
            expected_revision=1,
        ),
        owner,
    )
    with pytest.raises(FoundationError, match="permission_denied"):
        apply_operation(
            root,
            AdmitInvocationRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor=worker.actor,
                invocation_id=invocation_id,
                attempt_id=attempt_id,
                work_id=work_id,
                session_id=session_id,
            ),
            worker,
        )
    assert read_execution(root, work_id, owner).invocations[0].status == "prepared"
