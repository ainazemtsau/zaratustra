"""A plan revision during execution: kept Attempts transfer, all others are fenced.

Part 3.7 of Stage 6 pass 3, model-free through public Core operations.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_active_plan import (
    _keep,
    _replace,
    _revision_request,
)
from tests.zaratustra.foundation.test_applicability import Case
from tests.zaratustra.foundation.test_child_execution import (
    _assign,
    _assignment_revision,
    _claim,
    _codes,
    _invocation,
    _request_stop,
    _resource,
    _stop,
)
from tests.zaratustra.foundation.test_composition import _apply, _sqlite_contains
from tests.zaratustra.foundation.test_parallel_branches import (
    Branches,
    _ask,
    _branches,
    _child,
    _running,
    _succeeded,
)
from zaratustra.foundation import (
    AnswerWaitRequest,
    ArtifactRef,
    ClaimAttemptLaunchRequest,
    DeleteWorkRequest,
    FoundationError,
    IssueChildWorkRequest,
    MethodRef,
    OpenWaitRequest,
    PlanChild,
    PlanCondition,
    PlanNodeDecision,
    PlanTransfer,
    PrepareInvocationRequest,
    PublishAttemptOutputRequest,
    RecordAttemptStopRequest,
    RecoverRequest,
    WorkPlan,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    read_assigned_control,
    read_execution,
    read_obligation,
    read_plan_nodes,
    read_receipt,
    read_space,
    read_technical_deletion_targets,
    read_work,
    read_work_plan,
    read_work_status,
    restore_backup,
)


def _pair(tmp_path: Path) -> Branches:
    """Two independent branches A and B; the parent output comes from B."""

    def children(activity: UUID, source: ArtifactRef) -> tuple[PlanChild, ...]:
        return (
            _child(activity, "a", "checked", inputs=(source,)),
            _child(activity, "b", "checked", inputs=(source,)),
        )

    return _branches(
        tmp_path,
        children,
        bound=("b", "checked"),
        completion=PlanCondition(kind="all", members=(_succeeded("a"), _succeeded("b"))),
        obligations=(("a", "checked"), ("b", "checked")),
    )


def _case(branches: Branches) -> Case:
    root, space, owner, parent, works = branches
    activity = read_work(root, parent, owner).state.activity_id
    return Case(root, space, owner, activity, parent, dict(works))


def _issue_now(branches: Branches, role: str) -> None:
    root, space, owner, parent, works = branches
    _apply(
        root,
        space,
        owner,
        IssueChildWorkRequest,
        parent_work_id=parent,
        work_id=works[role],
        expected_plan_revision=read_work_plan(root, parent, owner).revision,
        expected_work_revision=read_work(root, works[role], owner).revision,
    )


def _prepare(
    root: Path, space: UUID, work: UUID, attempt: UUID, session: UUID
) -> PrepareInvocationRequest:
    return PrepareInvocationRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        invocation_id=uuid4(),
        attempt_id=attempt,
        work_id=work,
        session_id=session,
        purpose="content",
        provider="synthetic",
        model="synthetic",
        transport="http-sse",
        request_sha256="C" * 64,
        request_bytes=10,
        reserve_units=5,
    )


def _publish(
    space: UUID, work: UUID, attempt: UUID, session: UUID, content: bytes
) -> PublishAttemptOutputRequest:
    return PublishAttemptOutputRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        attempt_id=attempt,
        work_id=work,
        session_id=session,
        slot="checked",
        media_type="text/plain",
        content=content,
    )


def _replaced_a(branches: Branches) -> tuple[WorkPlan, PlanChild, PlanChild, PlanChild]:
    plan = read_work_plan(branches.root, branches.parent, branches.owner).plan
    a, b = plan.children
    a2 = a.model_copy(update={"work_id": uuid4()})
    return plan.model_copy(update={"children": (a2, b), "rationale": "Replace A"}), a, a2, b


def _states_in_new_process(root: Path, works: dict[str, UUID]) -> dict[str, object]:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, sys; from pathlib import Path; from uuid import UUID; "
            "from zaratustra.foundation import authorize_local, read_execution; "
            "p=Path(sys.argv[1]); o=authorize_local(p, actor='owner', source_ref='restart'); "
            "works=json.loads(sys.argv[2]); "
            "print(json.dumps({name: read_execution(p, UUID(work), o).model_dump(mode='json', "
            "include={'status', 'composition', 'waits', 'assignments', 'invocations'}) "
            "for name, work in works.items()}))",
            str(root),
            json.dumps({name: str(work) for name, work in works.items()}),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return dict(json.loads(result.stdout))


def _states(root: Path, owner: object, works: dict[str, UUID]) -> dict[str, object]:
    return {
        name: read_execution(root, work, owner).model_dump(  # type: ignore[arg-type]
            mode="json", include={"status", "composition", "waits", "assignments", "invocations"}
        )
        for name, work in works.items()
    }


def test_kept_node_continues_through_a_transfer_and_the_replaced_node_is_fenced(
    tmp_path: Path,
) -> None:
    branches = _pair(tmp_path)
    root, space, owner, parent, works = branches
    case = _case(branches)
    a_attempt, a_session, _a_resource = _running(branches, "a", "workspace-a")
    b_attempt, b_session, _b_resource = _running(branches, "b", "workspace-b")
    # In revision 1 A has a sent call and waits for an addressed answer; B runs.
    _invocation(root, space, owner, works["a"], a_attempt, a_session, finish=False)
    question = f"synthetic question of A {uuid4()}"
    wait = _ask(branches, "a", a_attempt, a_session, question)
    _invocation(root, space, owner, works["b"], b_attempt, b_session)
    revised, a, a2, b = _replaced_a(branches)
    request = _revision_request(
        case, revised, (_replace(case, a, a2, outcome="cancelled"), _keep(b))
    )
    receipt = apply_operation(root, request, owner)
    assert apply_operation(root, request, owner) == receipt
    assert read_receipt(root, request.operation_id, owner) == receipt
    assert receipt.result["transfers"] == [
        {"attempt_id": str(b_attempt), "work_id": str(b.work_id), "plan_revision": 2}
    ]
    method = read_work(root, parent, owner).state.method
    assert isinstance(method, MethodRef)
    # The kept node's Attempt continues through an explicit transfer; its pin stays.
    b_view = read_execution(root, b.work_id, owner).composition
    assert b_view is not None
    assert [pin.plan_revision for pin in b_view.pins] == [1]
    assert b_view.transfers == (
        PlanTransfer(
            attempt_id=b_attempt,
            work_id=b.work_id,
            parent_work_id=parent,
            role="b",
            from_plan_revision=1,
            plan_revision=2,
            method=method,
            operation_id=request.operation_id,
        ),
    )
    assert read_plan_nodes(root, parent, owner).nodes[1].issue_carried
    assert read_assigned_control(root, b.work_id, b_attempt, owner)
    assert not read_assigned_control(root, a.work_id, a_attempt, owner)

    # B keeps running without a restart and publishes its result under revision 2.
    assert read_work_status(root, b.work_id, owner).status == "running"
    _invocation(root, space, owner, b.work_id, b_attempt, b_session)
    published = apply_operation(
        root, _publish(space, b.work_id, b_attempt, b_session, b"synthetic B result"), owner
    )
    b_output = ArtifactRef(artifact_id=UUID(str(published.result["artifact_id"])), revision=1)
    assert [item.attempt_id for item in read_execution(root, b.work_id, owner).attempts] == [
        b_attempt
    ]

    # Every next effect of A refuses stale_plan and records no new call.
    before = read_execution(root, a.work_id, owner)
    for refused_effect in (
        _prepare(root, space, a.work_id, a_attempt, a_session),
        _publish(space, a.work_id, a_attempt, a_session, b"late synthetic A result"),
        ClaimAttemptLaunchRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            attempt_id=a_attempt,
            work_id=a.work_id,
            session_id=a_session,
            expected_assignment_revision=_assignment_revision(root, owner, a.work_id, a_attempt),
            claim_nonce=uuid4(),
        ),
        OpenWaitRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            wait_id=uuid4(),
            attempt_id=a_attempt,
            work_id=a.work_id,
            session_id=a_session,
            expected_assignment_revision=_assignment_revision(root, owner, a.work_id, a_attempt),
            question="Another synthetic question",
            expected_actor="owner",
            remainder="Finish",
        ),
    ):
        state = read_space(root)
        with pytest.raises(FoundationError, match="stale_plan"):
            apply_operation(root, refused_effect, owner)
        assert read_space(root) == state
    fenced = read_execution(root, a.work_id, owner)
    assert fenced.invocations == before.invocations and fenced.outputs == ()
    # The hold closed A's wait; the question and remainder still read.
    assert [(item.wait_id, item.status) for item in fenced.waits] == [(wait, "closed")]
    assert fenced.waits[0].question == question
    assert fenced.waits[0].remainder == "Finish the synthetic check"
    with pytest.raises(FoundationError, match="stale_wait"):
        apply_operation(
            root,
            AnswerWaitRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                wait_id=wait,
                attempt_id=a_attempt,
                work_id=a.work_id,
                session_id=a_session,
                expected_wait_revision=1,
                answer="A late synthetic answer",
            ),
            owner,
        )
    # The sent call is unknown and keeps its reserve; nothing names it a success.
    assert [item.status for item in fenced.invocations] == ["unknown"]
    assert fenced.held_units == 5 and fenced.work.state.status == "cancelled"
    assert _codes(read_work_status(root, a.work_id, owner)) == ["stop_requested"]

    # A2 runs at once on another root; on A's exclusive root it waits for A's stop.
    after = Branches(root, space, owner, parent, {"a": a2.work_id, "b": b.work_id})
    _issue_now(after, "a")
    shared = _resource(root, space, owner, a2.work_id, "workspace-a")
    state = read_space(root)
    with pytest.raises(FoundationError, match="resource_busy"):
        _assign(root, space, owner, a2.work_id, shared)
    assert read_space(root) == state
    # A stop with a sent call is recorded unknown: reserve and root stay held.
    _apply(
        root,
        space,
        owner,
        RecordAttemptStopRequest,
        attempt_id=a_attempt,
        work_id=a.work_id,
        session_id=a_session,
        expected_assignment_revision=_assignment_revision(root, owner, a.work_id, a_attempt),
        outcome="unknown",
    )
    held = read_work_status(root, a.work_id, owner)
    assert held.status == "cancelled" and _codes(held) == ["outcome_unknown"]
    with pytest.raises(FoundationError, match="resource_busy"):
        _assign(root, space, owner, a2.work_id, shared)
    own = _resource(root, space, owner, a2.work_id, "workspace-a2")
    a2_attempt, _a2_session, _request, a2_receipt = _assign(root, space, owner, a2.work_id, own)
    assert a2_receipt.result["plan"] == {
        "parent_work_id": str(parent),
        "role": "a",
        "plan_revision": 2,
        "method": method.model_dump(mode="json"),
    }
    # A's materials never close the obligation of the new revision.
    assert read_obligation(root, parent, "a_checked", owner).status == "open"
    assert read_execution(root, a.work_id, owner).outputs == ()
    # B's result published through its transfer is its exact proposed output.
    _stop(root, space, owner, b.work_id, b_attempt, b_session)
    assert read_work(root, b.work_id, owner).state.linked_outputs[0].artifact == b_output
    works_now = {"parent": parent, "a": a.work_id, "a2": a2.work_id, "b": b.work_id}
    assert _states_in_new_process(root, works_now) == _states(root, owner, works_now)
    assert a2_attempt in {
        item.attempt_id for item in read_execution(root, a2.work_id, owner).attempts
    }


def test_public_revision_repeats_the_stale_pin_check_of_pass_2(tmp_path: Path) -> None:
    branches = _pair(tmp_path)
    root, space, owner, parent, works = branches
    case = _case(branches)
    _issue_now(branches, "a")
    resource = _resource(root, space, owner, works["a"], "workspace-a")
    attempt, session, _request, receipt = _assign(root, space, owner, works["a"], resource)
    assert cast(dict[str, object], receipt.result["plan"])["plan_revision"] == 1
    revised, a, a2, b = _replaced_a(branches)
    _revise = _revision_request(
        case, revised, (_replace(case, a, a2, outcome="cancelled"), _keep(b))
    )
    assert "transfers" not in apply_operation(root, _revise, owner).result
    # The pin names revision 1; nothing carries it into revision 2.
    with pytest.raises(FoundationError, match="stale_plan"):
        _claim(root, space, owner, a.work_id, attempt, session)
    assert not read_assigned_control(root, a.work_id, attempt, owner)
    assert _codes(read_work_status(root, a.work_id, owner)) == ["stop_requested"]
    _stop(root, space, owner, a.work_id, attempt, session)
    stopped = read_work_status(root, a.work_id, owner)
    assert stopped.status == "cancelled" and stopped.reasons == ()
    # The replacement reuses the root once the old Attempt's stop is recorded.
    after = Branches(root, space, owner, parent, {"a": a2.work_id, "b": b.work_id})
    _issue_now(after, "a")
    root_again = _resource(root, space, owner, a2.work_id, "workspace-a")
    new_attempt, new_session, _new, new_receipt = _assign(
        root, space, owner, a2.work_id, root_again
    )
    assert cast(dict[str, object], new_receipt.result["plan"])["plan_revision"] == 2
    _claim(root, space, owner, a2.work_id, new_attempt, new_session)
    assert read_work_status(root, a2.work_id, owner).status == "running"


def test_waiting_kept_node_is_answered_after_the_revision_and_transfers_again(
    tmp_path: Path,
) -> None:
    branches = _pair(tmp_path)
    root, space, owner, parent, works = branches
    case = _case(branches)
    b_attempt, b_session, _resource_b = _running(branches, "b", "workspace-b")
    wait = _ask(branches, "b", b_attempt, b_session, "Which synthetic line counts for B?")
    assert read_work_status(root, parent, owner).status == "waiting"
    plan = read_work_plan(root, parent, owner).plan
    a, b = plan.children
    note = _child(case.activity, "note", "extra")
    first = _revision_request(
        case,
        plan.model_copy(update={"children": (a, b, note)}),
        (_keep(a), _keep(b), PlanNodeDecision(role="note", decision="add", work_id=note.work_id)),
    )
    assert apply_operation(root, first, owner).result["transfers"] == [
        {"attempt_id": str(b_attempt), "work_id": str(b.work_id), "plan_revision": 2}
    ]
    # The open wait of the kept node belongs to its transferred Attempt.
    assert read_work_status(root, b.work_id, owner).wait_id == wait
    _apply(
        root,
        space,
        owner,
        AnswerWaitRequest,
        wait_id=wait,
        attempt_id=b_attempt,
        work_id=b.work_id,
        session_id=b_session,
        expected_wait_revision=1,
        answer="Use the first synthetic line",
    )
    assert _codes(read_work_status(root, b.work_id, owner)) == ["continuation_ready"]
    # Each later revision that keeps the node transfers the Attempt again, explicitly.
    second = _revision_request(case, first.plan, (_keep(a), _keep(b), _keep(note)))
    assert apply_operation(root, second, owner).result["transfers"] == [
        {"attempt_id": str(b_attempt), "work_id": str(b.work_id), "plan_revision": 3}
    ]
    view = read_execution(root, b.work_id, owner).composition
    assert view is not None
    assert [(item.from_plan_revision, item.plan_revision) for item in view.transfers] == [
        (1, 2),
        (2, 3),
    ]
    _invocation(root, space, owner, b.work_id, b_attempt, b_session)
    assert read_work_status(root, b.work_id, owner).status == "running"
    # A stopping Attempt is not transferred: it can take no effect any more.
    _request_stop(root, space, owner, b.work_id, b_attempt, b_session)
    third = _revision_request(case, first.plan, (_keep(a), _keep(b), _keep(note)))
    assert "transfers" not in apply_operation(root, third, owner).result
    with pytest.raises(FoundationError, match="stale_plan"):
        apply_operation(root, _prepare(root, space, b.work_id, b_attempt, b_session), owner)
    _stop(root, space, owner, b.work_id, b_attempt, b_session)
    assert read_work_status(root, b.work_id, owner).status == "ready"


def test_transfers_survive_restore_as_history_and_go_with_their_child(tmp_path: Path) -> None:
    branches = _pair(tmp_path)
    root, space, owner, parent, works = branches
    case = _case(branches)
    a_attempt, a_session, _resource_a = _running(branches, "a", "workspace-a")
    b_attempt, b_session, _resource_b = _running(branches, "b", "workspace-b")
    marker = f"synthetic fenced question {uuid4()}"
    _ask(branches, "a", a_attempt, a_session, marker)
    revised, a, a2, b = _replaced_a(branches)
    apply_operation(
        root,
        _revision_request(case, revised, (_replace(case, a, a2, outcome="cancelled"), _keep(b))),
        owner,
    )
    backup = create_backup(root, uuid4(), owner)
    restored_root = tmp_path / "restored"
    restored_root.mkdir()
    restore_backup(backup.package, restored_root, authorize_recovery(actor="owner", source_ref="r"))
    apply_operation(
        restored_root,
        RecoverRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        authorize_recovery(actor="owner", source_ref="fresh-recovery"),
    )
    restored = authorize_local(restored_root, actor="owner", source_ref="new-epoch")
    history = read_execution(restored_root, b.work_id, restored)
    assert history.composition is not None
    assert [(item.attempt_id, item.plan_revision) for item in history.composition.transfers] == [
        (b_attempt, 2)
    ]
    # Recovery interrupts every Attempt; a transfer never resumes ownership.
    assert [item.status for item in history.assignments] == ["interrupted"]
    assert all(item.status == "cancelled" for item in history.outbox)
    assert not read_assigned_control(restored_root, b.work_id, b_attempt, restored)
    with pytest.raises(FoundationError, match="stale_attempt"):
        apply_operation(
            restored_root, _prepare(restored_root, space, b.work_id, b_attempt, b_session), restored
        )

    # Deleting a child takes its pins, transfers and Attempts; the addresses of both
    # Attempts are the technical cleanup targets.
    _stop(root, space, owner, a.work_id, a_attempt, a_session)
    _stop(root, space, owner, b.work_id, b_attempt, b_session)
    for work in (a.work_id, b.work_id):
        _apply(
            root,
            space,
            owner,
            DeleteWorkRequest,
            work_id=work,
            expected_revision=read_work(root, work, owner).revision,
        )
    targets = read_technical_deletion_targets(root, owner, (a.work_id, b.work_id))
    assert set(targets.attempt_ids) == {a_attempt, b_attempt}
    assert complete_deletions(root, owner).live_store_sanitized
    assert not backup.package.exists()
    with closing(sqlite3.connect(root / ".zara-core" / "core.sqlite3")) as connection:
        for table in ("execution_plan_transfers", "execution_plan_pins", "execution_attempts"):
            assert connection.execute(
                f"SELECT count(*) FROM {table} WHERE work_id IN (?, ?)",
                (str(a.work_id), str(b.work_id)),
            ).fetchone() == (0,)
    assert not _sqlite_contains(root / ".zara-core", marker)
    assert read_plan_nodes(root, parent, owner).plan_revision == 2
    assert read_obligation(root, parent, "b_checked", owner).status == "open"
