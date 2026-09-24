"""Independent child branches run at once; a failed branch is reviewed by its address.

Part 3.2 of Stage 6 pass 3, model-free through public Core operations.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import NamedTuple
from uuid import UUID, uuid4

import pytest

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
from tests.zaratustra.foundation.test_composition import _apply, _result, _seed, _sqlite_contains
from tests.zaratustra.foundation.test_work_outcomes import _close
from zaratustra.foundation import (
    AcceptWorkRequest,
    ArtifactRef,
    ConfirmObligationRequest,
    CreateArtifactRequest,
    CreateCompositeWorkRequest,
    CreateGrantRequest,
    CreateMethodVersionRequest,
    DeleteWorkRequest,
    FoundationError,
    GrantState,
    IssueChildWorkRequest,
    LinkedOutput,
    LinkWorkOutputRequest,
    LocalAuthority,
    MethodDefinition,
    MethodObligation,
    MethodRef,
    NamedInput,
    OpenWaitRequest,
    OutputContract,
    PlanChild,
    PlanCondition,
    PlanOutputBinding,
    PublishAttemptOutputRequest,
    RecoverRequest,
    ReviseArtifactRequest,
    WorkPlan,
    WorkState,
    WorkStatus,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    read_execution,
    read_obligation,
    read_space,
    read_work,
    read_work_plan,
    read_work_status,
    restore_backup,
    upgrade_child_execution_space,
    upgrade_plan_revision_space,
)

type Reason = tuple[str, str | None, UUID | None]
type Children = Callable[[UUID, ArtifactRef], tuple[PlanChild, ...]]


class Branches(NamedTuple):
    root: Path
    space: UUID
    owner: LocalAuthority
    parent: UUID
    works: dict[str, UUID]


def _reasons(status: WorkStatus) -> list[Reason]:
    return [(reason.code, reason.role, reason.record_id) for reason in status.reasons]


def _child(
    activity: UUID,
    role: str,
    slot: str,
    *,
    inputs: tuple[ArtifactRef, ...] = (),
    readiness: PlanCondition | None = None,
) -> PlanChild:
    return PlanChild(
        role=role,
        work_id=uuid4(),
        state=WorkState(
            activity_id=activity,
            goal=f"Synthetic branch {role}",
            inputs=inputs,
            expected_outputs=(OutputContract(slot=slot, media_type="text/plain"),),
        ),
        readiness=readiness,
    )


def _accepted(role: str, slot: str = "checked") -> PlanCondition:
    return PlanCondition(kind="accepted_output", role=role, slot=slot, media_type="text/plain")


def _succeeded(role: str) -> PlanCondition:
    return PlanCondition(kind="work_succeeded", role=role)


def _branches(
    tmp_path: Path,
    children: Children,
    *,
    bound: tuple[str, str],
    completion: PlanCondition,
    obligations: tuple[tuple[str, str], ...],
) -> Branches:
    root, space, owner, activity, source, _ref, _parent, _a, _b, _plan, _create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    assert upgrade_plan_revision_space(root, owner).schema_version == 7
    definition = MethodDefinition(
        instruction="Check the synthetic source in parallel branches, then integrate them.",
        named_inputs=(OutputContract(slot="source", media_type="text/plain"),),
        named_outputs=(OutputContract(slot="final", media_type="text/plain"),),
        obligations=tuple(
            MethodObligation(
                key=f"{role}_{slot}",
                source="synthetic parallel contract",
                role=role,
                slot=slot,
                media_type="text/plain",
            )
            for role, slot in obligations
        ),
        source_ref="synthetic-parallel-method",
    )
    method = uuid4()
    created = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=method,
        version=1,
        definition=definition,
    )
    source_ref = ArtifactRef(artifact_id=source, revision=1)
    plan = WorkPlan(
        named_inputs=(NamedInput(slot="source", artifact=source_ref),),
        output_bindings=(
            PlanOutputBinding(
                parent_slot="final", role=bound[0], child_slot=bound[1], media_type="text/plain"
            ),
        ),
        children=children(activity, source_ref),
        completion=completion,
        basis=(source_ref,),
        rationale="Parallel synthetic checks",
        source_ref="fictional-owner-plan",
    )
    parent = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateCompositeWorkRequest,
        work_id=parent,
        state=WorkState(
            activity_id=activity,
            goal="Integrate parallel synthetic checks",
            inputs=(source_ref,),
            expected_outputs=definition.named_outputs,
            method=MethodRef(method_id=method, version=1, checksum=str(created.result["checksum"])),
        ),
        plan=plan,
    )
    return Branches(
        root, space, owner, parent, {child.role: child.work_id for child in plan.children}
    )


def _pipeline(tmp_path: Path) -> Branches:
    """A1 and A2 in parallel, C beside them, D after A1, integration I after both."""

    def children(activity: UUID, source: ArtifactRef) -> tuple[PlanChild, ...]:
        return (
            _child(activity, "a1", "checked", inputs=(source,)),
            _child(activity, "a2", "checked", inputs=(source,)),
            _child(activity, "c", "extra"),
            _child(activity, "d", "extra", readiness=_accepted("a1")),
            _child(
                activity,
                "i",
                "final",
                readiness=PlanCondition(kind="all", members=(_accepted("a1"), _accepted("a2"))),
            ),
        )

    return _branches(
        tmp_path,
        children,
        bound=("i", "final"),
        completion=_succeeded("i"),
        obligations=(("a1", "checked"), ("a2", "checked"), ("i", "final")),
    )


def _issue(branches: Branches, role: str) -> None:
    root, space, owner, parent, works = branches
    _apply(
        root,
        space,
        owner,
        IssueChildWorkRequest,
        parent_work_id=parent,
        work_id=works[role],
        expected_plan_revision=1,
        expected_work_revision=read_work(root, works[role], owner).revision,
    )


def _running(branches: Branches, role: str, workspace: str) -> tuple[UUID, UUID, UUID]:
    """Issue, give an own resource, assign and claim one branch."""

    root, space, owner, _parent, works = branches
    _issue(branches, role)
    resource = _resource(root, space, owner, works[role], workspace)
    attempt, session, _request, _receipt = _assign(root, space, owner, works[role], resource)
    _claim(root, space, owner, works[role], attempt, session)
    return attempt, session, resource


def _ask(branches: Branches, role: str, attempt: UUID, session: UUID, question: str) -> UUID:
    root, space, owner, _parent, works = branches
    wait = uuid4()
    _apply(
        root,
        space,
        owner,
        OpenWaitRequest,
        wait_id=wait,
        attempt_id=attempt,
        work_id=works[role],
        session_id=session,
        expected_assignment_revision=_assignment_revision(root, owner, works[role], attempt),
        question=question,
        expected_actor="owner",
        remainder="Finish the synthetic check",
    )
    return wait


def _publish(branches: Branches, role: str, attempt: UUID, session: UUID, slot: str) -> ArtifactRef:
    root, space, owner, _parent, works = branches
    _invocation(root, space, owner, works[role], attempt, session)
    published = _apply(
        root,
        space,
        owner,
        PublishAttemptOutputRequest,
        attempt_id=attempt,
        work_id=works[role],
        session_id=session,
        slot=slot,
        media_type="text/plain",
        content=f"synthetic {role} result".encode(),
    )
    return ArtifactRef(artifact_id=UUID(str(published.result["artifact_id"])), revision=1)


def _accept(branches: Branches, role: str) -> None:
    root, space, owner, _parent, works = branches
    _apply(
        root,
        space,
        owner,
        AcceptWorkRequest,
        work_id=works[role],
        expected_revision=read_work(root, works[role], owner).revision,
        basis=f"Synthetic acceptance of {role}",
    )


def _confirm(branches: Branches, key: str, evidence: ArtifactRef) -> None:
    root, space, owner, parent, _works = branches
    _apply(
        root,
        space,
        owner,
        ConfirmObligationRequest,
        work_id=parent,
        key=key,
        expected_plan_revision=1,
        expected_obligation_revision=1,
        evidence=evidence,
        basis=f"Synthetic confirmation of {key}",
    )


def _accept_parent(branches: Branches) -> None:
    root, space, owner, parent, _works = branches
    _apply(
        root,
        space,
        owner,
        AcceptWorkRequest,
        work_id=parent,
        expected_revision=read_work(root, parent, owner).revision,
        basis="Synthetic parent acceptance",
    )


def _states_in_new_process(root: Path, works: dict[str, UUID]) -> dict[str, list[object]]:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, sys; from pathlib import Path; from uuid import UUID; "
            "from zaratustra.foundation import authorize_local, read_work_status; "
            "p=Path(sys.argv[1]); o=authorize_local(p, actor='owner', source_ref='restart'); "
            "works=json.loads(sys.argv[2]); "
            "print(json.dumps({name: [s.status, [[r.code, r.role, str(r.record_id)] "
            "for r in s.reasons]] for name, work in works.items() "
            "for s in [read_work_status(p, UUID(work), o)]}))",
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


def _as_json(status: WorkStatus) -> list[object]:
    return [status.status, [[code, role, str(record)] for code, role, record in _reasons(status)]]


def test_independent_branches_run_at_once_and_an_exclusive_root_stays_single(
    tmp_path: Path,
) -> None:
    branches = _pipeline(tmp_path)
    root, space, owner, parent, works = branches
    a1_attempt, a1_session, _a1_resource = _running(branches, "a1", "workspace-shared")
    a2_attempt, a2_session, _a2_resource = _running(branches, "a2", "workspace-a2")
    assert [read_work_status(root, works[role], owner).status for role in ("a1", "a2")] == [
        "running",
        "running",
    ]
    running = read_work_status(root, parent, owner)
    assert running.status == "running"
    assert _reasons(running) == [
        ("child_running", "a1", works["a1"]),
        ("child_running", "a2", works["a2"]),
    ]

    # A2 asks while A1 publishes: the waiting phase leads, both branches keep an address.
    wait = _ask(branches, "a2", a2_attempt, a2_session, "Which synthetic line counts?")
    _publish(branches, "a1", a1_attempt, a1_session, "checked")
    waiting = read_work_status(root, parent, owner)
    assert waiting.status == "waiting"
    assert _reasons(waiting) == [
        ("child_waiting", "a2", works["a2"]),
        ("child_running", "a1", works["a1"]),
    ]
    assert read_work_status(root, works["a2"], owner).wait_id == wait

    # C shares A1's exclusive root: its assignment creates nothing while A1 holds it.
    _issue(branches, "c")
    c_resource = _resource(root, space, owner, works["c"], "workspace-shared")
    before = read_space(root)
    with pytest.raises(FoundationError, match="resource_busy"):
        _assign(root, space, owner, works["c"], c_resource)
    assert read_space(root) == before
    refused = read_execution(root, works["c"], owner)
    assert refused.attempts == () and refused.assignments == () and refused.outbox == ()
    assert read_work_status(root, works["c"], owner).status == "ready"
    # A requested stop is not yet an observed one: the root stays held until it is recorded.
    _request_stop(root, space, owner, works["a1"], a1_attempt, a1_session)
    with pytest.raises(FoundationError, match="resource_busy"):
        _assign(root, space, owner, works["c"], c_resource)
    assert read_execution(root, works["c"], owner).attempts == ()

    _stop(root, space, owner, works["a1"], a1_attempt, a1_session)
    c_attempt, _c_session, _request, _receipt = _assign(root, space, owner, works["c"], c_resource)
    assert _codes(read_work_status(root, works["c"], owner)) == ["launch_pending"]
    assert read_execution(root, works["c"], owner).attempts[0].attempt_id == c_attempt
    # A2 on its own root was never held back by either of them.
    assert read_work_status(root, works["a2"], owner).status == "waiting"
    assert _states_in_new_process(root, {"parent": parent, **works}) == {
        name: _as_json(read_work_status(root, work, owner))
        for name, work in {"parent": parent, **works}.items()
    }


def test_failed_branch_is_reviewed_while_independent_branches_go_on(tmp_path: Path) -> None:
    branches = _pipeline(tmp_path)
    root, space, owner, parent, works = branches
    a1_attempt, a1_session, _a1_resource = _running(branches, "a1", "workspace-a1")
    a2_attempt, a2_session, _a2_resource = _running(branches, "a2", "workspace-a2")
    _ask(branches, "a2", a2_attempt, a2_session, "Which synthetic line counts?")
    a1_result = _publish(branches, "a1", a1_attempt, a1_session, "checked")
    _stop(root, space, owner, works["a1"], a1_attempt, a1_session)
    _accept(branches, "a1")

    apply_operation(root, _close(root, space, owner, works["a2"], "failed", "Check failed"), owner)
    assert _codes(read_work_status(root, works["a2"], owner)) == ["stop_requested"]
    review = read_work_status(root, parent, owner)
    assert review.status == "ready"
    assert _reasons(review) == [
        ("issue_pending", "c", works["c"]),
        ("issue_pending", "d", works["d"]),
        ("confirmation_pending", "a1", parent),
        ("branch_review", "a2", works["a2"]),
    ]

    # Integration that needs A2 refuses by its address; nothing independent is cancelled.
    with pytest.raises(FoundationError, match="dependency_closed") as issue_refused:
        _issue(branches, "i")
    assert str(works["a2"]) in issue_refused.value.detail
    integration = read_work_status(root, works["i"], owner)
    assert integration.status == "blocked"
    assert _reasons(integration) == [("dependency_closed", "a2", works["a2"])]
    with pytest.raises(FoundationError, match="dependency_closed") as confirm_refused:
        _confirm(branches, "a2_checked", a1_result)
    assert str(works["a2"]) in confirm_refused.value.detail
    _confirm(branches, "a1_checked", a1_result)
    with pytest.raises(FoundationError, match="dependency_closed") as accept_refused:
        _accept_parent(branches)
    assert f"a2 ({works['a2']})" in accept_refused.value.detail
    assert read_work(root, parent, owner).state.status == "proposed"

    _issue(branches, "d")
    d_resource = _resource(root, space, owner, works["d"], "workspace-d")
    d_attempt, d_session, _request, _receipt = _assign(root, space, owner, works["d"], d_resource)
    progress = read_work_status(root, parent, owner)
    assert progress.status == "ready"
    assert _reasons(progress) == [
        ("issue_pending", "c", works["c"]),
        ("child_ready", "d", works["d"]),
        ("branch_review", "a2", works["a2"]),
    ]
    _claim(root, space, owner, works["d"], d_attempt, d_session)
    running = read_work_status(root, parent, owner)
    assert running.status == "running"
    assert _reasons(running) == [
        ("child_running", "d", works["d"]),
        ("branch_review", "a2", works["a2"]),
    ]
    _stop(root, space, owner, works["a2"], a2_attempt, a2_session)
    assert read_work_status(root, works["a2"], owner).reasons == ()
    assert [read_work(root, works[role], owner).state.status for role in ("c", "d", "i")] == [
        "proposed",
        "proposed",
        "proposed",
    ]
    assert _states_in_new_process(root, {"parent": parent, **works}) == {
        name: _as_json(read_work_status(root, work, owner))
        for name, work in {"parent": parent, **works}.items()
    }

    # A stale prerequisite still blocks the parent first; the review keeps its address.
    source = read_work(root, parent, owner).state.inputs[0]
    _apply(
        root,
        space,
        owner,
        ReviseArtifactRequest,
        artifact_id=source.artifact_id,
        expected_revision=source.revision,
        media_type="text/plain",
        content=b"synthetic source revised",
    )
    blocked = read_work_status(root, parent, owner)
    assert blocked.status == "blocked"
    assert _reasons(blocked) == [
        ("stale_basis", None, source.artifact_id),
        ("branch_review", "a2", works["a2"]),
    ]


def _two_branches(
    tmp_path: Path, bound: str, obligations: tuple[tuple[str, str], ...] = (("a1", "checked"),)
) -> Branches:
    def children(activity: UUID, source: ArtifactRef) -> tuple[PlanChild, ...]:
        return (
            _child(activity, "a1", "checked", inputs=(source,)),
            _child(activity, "a2", "checked", inputs=(source,)),
        )

    return _branches(
        tmp_path,
        children,
        bound=(bound, "checked"),
        completion=PlanCondition(kind="any", members=(_succeeded("a1"), _succeeded("a2"))),
        obligations=obligations,
    )


def _link_parent(branches: Branches, artifact: ArtifactRef) -> None:
    root, space, owner, parent, _works = branches
    _apply(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=parent,
        expected_revision=read_work(root, parent, owner).revision,
        output=LinkedOutput(slot="final", artifact=artifact),
    )


def test_any_completion_stays_reachable_through_the_other_branch(tmp_path: Path) -> None:
    branches = _two_branches(tmp_path, "a1")
    root, space, owner, parent, works = branches
    apply_operation(root, _close(root, space, owner, works["a2"], "failed", "Not usable"), owner)
    assert _reasons(read_work_status(root, parent, owner)) == [
        ("issue_pending", "a1", works["a1"]),
        ("branch_review", "a2", works["a2"]),
    ]
    _issue(branches, "a1")
    result = _result(root, space, owner, works["a1"], "checked", b"synthetic surviving check")
    _confirm(branches, "a1_checked", result)
    _apply(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=parent,
        expected_revision=read_work(root, parent, owner).revision,
        output=LinkedOutput(slot="final", artifact=result),
    )
    pending = read_work_status(root, parent, owner)
    assert pending.status == "ready"
    assert _reasons(pending) == [
        ("acceptance_pending", None, parent),
        ("branch_review", "a2", works["a2"]),
    ]
    _accept_parent(branches)
    assert read_work_status(root, parent, owner).status == "succeeded"
    assert read_work(root, works["a2"], owner).state.status == "failed"


def test_any_completion_without_obligations_reads_acceptance_pending(tmp_path: Path) -> None:
    branches = _two_branches(tmp_path, "a1", obligations=())
    root, space, owner, parent, works = branches
    apply_operation(root, _close(root, space, owner, works["a2"], "failed", "Not usable"), owner)
    _issue(branches, "a1")
    result = _result(root, space, owner, works["a1"], "checked", b"synthetic surviving check")
    # Until the exact output is linked Core's acceptance rules refuse: nothing is pending.
    unlinked = read_work_status(root, parent, owner)
    assert unlinked.status == "ready"
    assert _reasons(unlinked) == [
        ("output_link_pending", "a1", result.artifact_id),
        ("branch_review", "a2", works["a2"]),
    ]
    with pytest.raises(FoundationError, match="output_mismatch"):
        _accept_parent(branches)

    _link_parent(branches, result)
    # any(A1, A2) holds through A1 and no obligation is declared: the same rules the
    # acceptance operation applies hold, and the failed branch stays under review.
    expected = [("acceptance_pending", None, parent), ("branch_review", "a2", works["a2"])]
    pending = read_work_status(root, parent, owner)
    assert pending.status == "ready" and _reasons(pending) == expected
    execution = read_execution(root, parent, owner).status
    assert execution is not None and _as_json(execution) == _as_json(pending)
    assert _states_in_new_process(root, {"parent": parent}) == {"parent": _as_json(pending)}

    # The derived state grants nothing: acceptance stays separate and rights-checked.
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest,
        grant_id=uuid4(),
        state=GrantState(grantee="reader", actions=("record.read",)),
    )
    reader = authorize_local(root, actor="reader", source_ref="fictional-reader")
    with pytest.raises(FoundationError, match="permission_denied"):
        apply_operation(
            root,
            AcceptWorkRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="reader",
                work_id=parent,
                expected_revision=read_work(root, parent, owner).revision,
                basis="A reader cannot accept",
            ),
            reader,
        )
    assert read_work(root, parent, owner).state.status == "proposed"
    _accept_parent(branches)
    assert read_work_status(root, parent, owner).status == "succeeded"


def test_pending_acceptance_stays_behind_active_branches(tmp_path: Path) -> None:
    branches = _two_branches(tmp_path, "a1", obligations=())
    root, space, owner, parent, works = branches
    a2_attempt, a2_session, _a2_resource = _running(branches, "a2", "workspace-a2")
    _issue(branches, "a1")
    _link_parent(
        branches, _result(root, space, owner, works["a1"], "checked", b"synthetic surviving check")
    )
    # Core would accept the parent already; the pass 2 phase order still comes first.
    running = read_work_status(root, parent, owner)
    assert running.status == "running"
    assert _reasons(running) == [("child_running", "a2", works["a2"])]
    _ask(branches, "a2", a2_attempt, a2_session, "Which synthetic line counts?")
    waiting = read_work_status(root, parent, owner)
    assert waiting.status == "waiting"
    assert _reasons(waiting) == [("child_waiting", "a2", works["a2"])]
    apply_operation(root, _close(root, space, owner, works["a2"], "failed", "Not needed"), owner)
    pending = read_work_status(root, parent, owner)
    assert pending.status == "ready"
    assert _reasons(pending) == [
        ("acceptance_pending", None, parent),
        ("branch_review", "a2", works["a2"]),
    ]


def test_any_completion_without_a_surviving_branch_is_not_pending(tmp_path: Path) -> None:
    branches = _two_branches(tmp_path, "a1", obligations=())
    root, space, owner, parent, works = branches
    apply_operation(root, _close(root, space, owner, works["a1"], "cancelled", "Dropped"), owner)
    apply_operation(root, _close(root, space, owner, works["a2"], "failed", "Not usable"), owner)
    status = read_work_status(root, parent, owner)
    assert status.status == "ready"
    assert _reasons(status) == [
        ("branch_review", "a1", works["a1"]),
        ("branch_review", "a2", works["a2"]),
    ]
    with pytest.raises(FoundationError, match="dependency_closed"):
        _accept_parent(branches)
    assert read_work(root, parent, owner).state.status == "proposed"


def test_output_bound_to_a_closed_branch_cannot_be_linked_or_accepted(tmp_path: Path) -> None:
    branches = _two_branches(tmp_path, "a2")
    root, space, owner, parent, works = branches
    apply_operation(root, _close(root, space, owner, works["a2"], "cancelled", "Dropped"), owner)
    _issue(branches, "a1")
    result = _result(root, space, owner, works["a1"], "checked", b"synthetic surviving check")
    _confirm(branches, "a1_checked", result)
    other = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=other,
        media_type="text/plain",
        content=b"synthetic stand-in output",
    )
    before = read_work(root, parent, owner)
    for artifact in (result, ArtifactRef(artifact_id=other, revision=1)):
        with pytest.raises(FoundationError, match="dependency_closed") as refused:
            _apply(
                root,
                space,
                owner,
                LinkWorkOutputRequest,
                work_id=parent,
                expected_revision=before.revision,
                output=LinkedOutput(slot="final", artifact=artifact),
            )
        assert f"a2 ({works['a2']})" in refused.value.detail
    assert read_work(root, parent, owner) == before
    with pytest.raises(FoundationError, match="dependency_closed"):
        _accept_parent(branches)
    status = read_work_status(root, parent, owner)
    assert status.status == "ready"
    assert _reasons(status) == [("branch_review", "a2", works["a2"])]


def test_backup_with_two_assignments_restores_both_as_history(tmp_path: Path) -> None:
    branches = _pipeline(tmp_path)
    root, space, owner, parent, works = branches
    a1_attempt, a1_session, _a1_resource = _running(branches, "a1", "workspace-a1")
    a2_attempt, a2_session, _a2_resource = _running(branches, "a2", "workspace-a2")
    question = f"Which synthetic line counts? {uuid4()}"
    _ask(branches, "a2", a2_attempt, a2_session, question)
    backup = create_backup(root, uuid4(), owner)

    restored_root = tmp_path / "restored"
    restored_root.mkdir()
    restored = restore_backup(
        backup.package, restored_root, authorize_recovery(actor="owner", source_ref="restore")
    )
    assert restored.schema_version == 7 and restored.recovery_state == "quarantined"
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
    restored_owner = authorize_local(restored_root, actor="owner", source_ref="new-epoch")
    for role, attempt, session in (("a1", a1_attempt, a1_session), ("a2", a2_attempt, a2_session)):
        history = read_execution(restored_root, works[role], restored_owner)
        assert [item.status for item in history.attempts] == ["interrupted"]
        assert [item.status for item in history.assignments] == ["interrupted"]
        assert history.outbox and all(item.status == "cancelled" for item in history.outbox)
        assert all(item.status == "closed" for item in history.waits)
        # Ownership is not resumed: the old Attempt cannot claim again in the new epoch.
        with pytest.raises(FoundationError, match="stale_attempt"):
            _claim(restored_root, space, restored_owner, works[role], attempt, session)
        assert read_work_status(restored_root, works[role], restored_owner).status == "ready"
    assert read_execution(restored_root, works["a2"], restored_owner).waits[0].question == question
    assert [
        (code, role)
        for code, role, _record in _reasons(read_work_status(restored_root, parent, restored_owner))
    ] == [
        ("child_ready", "a1"),
        ("child_ready", "a2"),
        ("issue_pending", "c"),
    ]


def test_deleting_one_branch_keeps_its_neighbour_and_the_obligations(tmp_path: Path) -> None:
    branches = _pipeline(tmp_path)
    root, space, owner, parent, works = branches
    a1_attempt, _a1_session, _a1_resource = _running(branches, "a1", "workspace-a1")
    a2_attempt, a2_session, _a2_resource = _running(branches, "a2", "workspace-a2")
    question = f"Which synthetic line counts? {uuid4()}"
    _ask(branches, "a2", a2_attempt, a2_session, question)
    apply_operation(root, _close(root, space, owner, works["a2"], "failed", "Check failed"), owner)
    _stop(root, space, owner, works["a2"], a2_attempt, a2_session)
    old_backup = create_backup(root, uuid4(), owner)

    _apply(
        root,
        space,
        owner,
        DeleteWorkRequest,
        work_id=works["a2"],
        expected_revision=read_work(root, works["a2"], owner).revision,
    )
    assert complete_deletions(root, owner).live_store_sanitized
    assert not old_backup.package.exists()
    with closing(sqlite3.connect(root / ".zara-core" / "core.sqlite3")) as connection:
        pins = dict(
            connection.execute(
                "SELECT work_id, count(*) FROM execution_plan_pins GROUP BY work_id"
            ).fetchall()
        )
        attempts = dict(
            connection.execute("SELECT attempt_id, status FROM execution_attempts").fetchall()
        )
    assert pins == {str(works["a1"]): 1}
    assert attempts == {str(a1_attempt): "active"}
    for key in ("a1_checked", "a2_checked", "i_final"):
        assert read_obligation(root, parent, key, owner).status == "open"
    # The deleted child was in the plan: its plan revision is sanitized as in pass 1.
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_work_plan(root, parent, owner)
    assert read_execution(root, works["a1"], owner).attempts[0].attempt_id == a1_attempt
    assert not _sqlite_contains(root / ".zara-core", question)
    assert not _sqlite_contains(create_backup(root, uuid4(), owner).package, question)
