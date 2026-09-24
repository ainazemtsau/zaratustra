"""Deletion retires the bases of Work outcomes that structurally depend on it, without a model."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_composition import _apply, _seed, _sqlite_contains
from zaratustra.foundation import (
    AcceptWorkRequest,
    ActivityState,
    ArtifactRef,
    BootstrapRequest,
    CloseWorkRequest,
    CreateActivityRequest,
    CreateArtifactRequest,
    CreateCompositeWorkRequest,
    CreateGrantRequest,
    CreateWorkRequest,
    DeleteArtifactRequest,
    DeleteWorkRequest,
    FoundationError,
    GrantState,
    IssueChildWorkRequest,
    LinkedOutput,
    LinkWorkOutputRequest,
    LocalAuthority,
    OperationReceipt,
    OutputContract,
    PlanChild,
    ReviseWorkPlanRequest,
    WorkPlan,
    WorkState,
    apply_operation,
    authorize_local,
    complete_deletions,
    create_backup,
    initialize_space,
    read_obligation,
    read_operation_audit,
    read_receipt,
    read_space,
    read_work,
    read_work_plan,
    read_work_status,
    upgrade_child_execution_space,
    upgrade_composition_space,
    upgrade_continuation_space,
    upgrade_execution_space,
    upgrade_plan_revision_space,
    upgrade_space,
)

type Outcome = tuple[CloseWorkRequest | AcceptWorkRequest, OperationReceipt]


def _space(
    tmp_path: Path,
) -> tuple[
    Path,
    UUID,
    LocalAuthority,
    UUID,
    tuple[UUID, UUID, UUID],
    WorkPlan,
    CreateCompositeWorkRequest,
]:
    root, space, owner, activity, _source, _ref, parent, a, b, plan, create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    assert upgrade_plan_revision_space(root, owner).schema_version == 7
    return root, space, owner, activity, (parent, a, b), plan, create


def _artifact(root: Path, space: UUID, owner: LocalAuthority, content: bytes) -> UUID:
    artifact = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=artifact,
        media_type="text/plain",
        content=content,
    )
    return artifact


def _composite(
    root: Path,
    owner: LocalAuthority,
    create: CreateCompositeWorkRequest,
    plan: WorkPlan,
    *,
    basis: tuple[ArtifactRef, ...] = (),
    a_goal: str | None = None,
    a_inputs: tuple[ArtifactRef, ...] = (),
    c_inputs: tuple[ArtifactRef, ...] | None = None,
) -> tuple[UUID, dict[str, UUID]]:
    """A fresh composite from the seed plan; ``c_inputs`` adds an independent role c."""

    parent = uuid4()
    first, second = plan.children
    a_state = first.state.model_copy(
        update={
            "goal": first.state.goal if a_goal is None else a_goal,
            "inputs": first.state.inputs + a_inputs,
        }
    )
    children = [
        first.model_copy(update={"work_id": uuid4(), "state": a_state}),
        second.model_copy(update={"work_id": uuid4()}),
    ]
    if c_inputs is not None:
        children.append(
            PlanChild(
                role="c",
                work_id=uuid4(),
                state=WorkState(
                    activity_id=first.state.activity_id,
                    goal="Independent synthetic check",
                    inputs=c_inputs,
                    expected_outputs=(OutputContract(slot="extra", media_type="text/plain"),),
                ),
            )
        )
    apply_operation(
        root,
        create.model_copy(
            update={
                "operation_id": uuid4(),
                "work_id": parent,
                "plan": plan.model_copy(
                    update={"basis": plan.basis + basis, "children": tuple(children)}
                ),
            }
        ),
        owner,
    )
    return parent, {child.role: child.work_id for child in children}


def _close(
    root: Path, space: UUID, owner: LocalAuthority, work: UUID, outcome: str, basis: str
) -> Outcome:
    request = CloseWorkRequest.model_validate(
        {
            "operation_id": uuid4(),
            "space_id": space,
            "actor": "owner",
            "work_id": work,
            "expected_revision": read_work(root, work, owner).revision,
            "outcome": outcome,
            "basis": basis,
        }
    )
    return request, apply_operation(root, request, owner)


def _accept(
    root: Path, space: UUID, owner: LocalAuthority, work: UUID, slot: str, basis: str
) -> Outcome:
    output = _artifact(root, space, owner, b"neutral synthetic output")
    linked = _apply(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=work,
        expected_revision=read_work(root, work, owner).revision,
        output=LinkedOutput(slot=slot, artifact=ArtifactRef(artifact_id=output, revision=1)),
    )
    request = AcceptWorkRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        work_id=work,
        expected_revision=int(linked.result["revision"]),  # type: ignore[arg-type]
        basis=basis,
    )
    return request, apply_operation(root, request, owner)


def _plain_accepted(
    root: Path, space: UUID, owner: LocalAuthority, activity: UUID, source: UUID, basis: str
) -> tuple[UUID, Outcome]:
    work = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=work,
        state=WorkState(
            activity_id=activity,
            goal="Summarize the synthetic input",
            inputs=(ArtifactRef(artifact_id=source, revision=1),),
            expected_outputs=(OutputContract(slot="summary", media_type="text/plain"),),
        ),
    )
    return work, _accept(root, space, owner, work, "summary", basis)


def _basis(root: Path, owner: LocalAuthority, work: UUID) -> str | None:
    state = read_work(root, work, owner).state
    outcome = state.acceptance or state.closure
    assert outcome is not None
    return outcome.basis


def _assert_retired(root: Path, owner: LocalAuthority, work: UUID, outcome: Outcome) -> None:
    request, receipt = outcome
    state = read_work(root, work, owner).state
    recorded = state.acceptance or state.closure
    # The terminal outcome and its addresses stay; the deleted basis is never the original.
    assert state.status == receipt.result["status"] and recorded is not None
    assert recorded.operation_id == request.operation_id and recorded.basis is None
    assert read_work_status(root, work, owner).status == state.status
    with pytest.raises(FoundationError, match="history_unavailable"):
        apply_operation(root, request, owner)
    with pytest.raises(FoundationError, match="not_found"):
        read_receipt(root, request.operation_id, owner)
    # Addressed operation facts remain: who, when and which revisions, without the text.
    audit = read_operation_audit(root, request.operation_id, owner)
    assert (work, receipt.result["revision"]) in [
        (item.record_id, item.revision) for item in audit.target_refs
    ]


def _assert_kept(
    root: Path, owner: LocalAuthority, work: UUID, outcome: Outcome, basis: str
) -> None:
    request, receipt = outcome
    assert _basis(root, owner, work) == basis
    assert apply_operation(root, request, owner) == receipt


def _assert_clean(
    root: Path, owner: LocalAuthority, removed: tuple[str, ...], kept: str | None
) -> None:
    fresh = create_backup(root, uuid4(), owner)
    for marker in removed:
        assert not _sqlite_contains(root / ".zara-core", marker)
        assert not _sqlite_contains(fresh.package, marker)
    if kept is not None:
        assert _sqlite_contains(root / ".zara-core", kept)
        assert _sqlite_contains(fresh.package, kept)


def _restarted_bases(root: Path, owner: LocalAuthority, works: tuple[UUID, ...]) -> list[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; from uuid import UUID; "
            "from zaratustra.foundation import authorize_local, read_work; "
            "p=Path(sys.argv[1]); o=authorize_local(p, actor='owner', source_ref='restart'); "
            "states=[read_work(p, UUID(w), o).state for w in sys.argv[2:]]; "
            "print(*[repr((s.acceptance or s.closure).basis) for s in states], sep='|')",
            str(root),
            *(str(work) for work in works),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().split("|")


def test_plan_basis_deletion_retires_every_basis_under_that_plan(tmp_path: Path) -> None:
    root, space, owner, _activity, seed, plan, create = _space(tmp_path)
    marker = f"synthetic plan basis {uuid4()}"
    kept = f"synthetic independent basis {uuid4()}"
    x = _artifact(root, space, owner, marker.encode())
    parent, roles = _composite(
        root, owner, create, plan, basis=(ArtifactRef(artifact_id=x, revision=1),)
    )
    _apply(
        root,
        space,
        owner,
        IssueChildWorkRequest,
        parent_work_id=parent,
        work_id=roles["a"],
        expected_plan_revision=1,
        expected_work_revision=1,
    )
    # X is only in WorkPlan.basis: no Work state duplicates its address.
    dependent = {
        roles["a"]: _accept(root, space, owner, roles["a"], "checked", "Checked output"),
        roles["b"]: _close(root, space, owner, roles["b"], "cancelled", f"X said: {marker}"),
        parent: _close(root, space, owner, parent, "failed", f"Basis X said: {marker}"),
    }
    seed_parent, seed_a, seed_b = seed
    independent = {
        seed_a: _close(root, space, owner, seed_a, "cancelled", kept),
        seed_b: _close(root, space, owner, seed_b, "cancelled", kept),
        seed_parent: _close(root, space, owner, seed_parent, "failed", kept),
    }
    old_backup = create_backup(root, uuid4(), owner)

    _apply(root, space, owner, DeleteArtifactRequest, artifact_id=x, expected_revision=1)
    # The deletion transaction already stops serving the dependent bases.
    assert _basis(root, owner, parent) is None
    assert complete_deletions(root, owner).live_store_sanitized
    assert not old_backup.package.exists()

    with pytest.raises(FoundationError, match="content_unavailable"):
        read_work_plan(root, parent, owner)
    for work, outcome in dependent.items():
        _assert_retired(root, owner, work, outcome)
    for work, outcome in independent.items():
        _assert_kept(root, owner, work, outcome, kept)
    assert read_obligation(root, parent, "final", owner).status == "open"
    _assert_clean(root, owner, (marker,), kept)
    assert _restarted_bases(root, owner, (roles["b"], parent, seed_parent)) == [
        "None",
        "None",
        repr(kept),
    ]


def test_historical_plan_revision_keeps_its_dependency(tmp_path: Path) -> None:
    root, space, owner, _activity, _seed_works, plan, create = _space(tmp_path)
    marker = f"synthetic dropped basis {uuid4()}"
    x = _artifact(root, space, owner, marker.encode())
    parent, roles = _composite(
        root, owner, create, plan, basis=(ArtifactRef(artifact_id=x, revision=1),)
    )
    first = read_work_plan(root, parent, owner)
    _apply(
        root,
        space,
        owner,
        ReviseWorkPlanRequest,
        work_id=parent,
        expected_plan_revision=1,
        plan=first.plan.model_copy(update={"basis": plan.basis, "rationale": "X dropped"}),
    )
    outcomes = {
        roles["a"]: _close(root, space, owner, roles["a"], "cancelled", "Not needed"),
        roles["b"]: _close(root, space, owner, roles["b"], "cancelled", "Not needed"),
        parent: _close(root, space, owner, parent, "failed", f"Dropped X said: {marker}"),
    }

    _apply(root, space, owner, DeleteArtifactRequest, artifact_id=x, expected_revision=1)
    assert complete_deletions(root, owner).live_store_sanitized
    # Only the plan revision naming X is unreadable, but every basis of that plan depended on it.
    assert read_work_plan(root, parent, owner).revision == 2
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_work_plan(root, parent, owner, revision=1)
    for work, outcome in outcomes.items():
        _assert_retired(root, owner, work, outcome)
    _assert_clean(root, owner, (marker,), None)


def test_child_deletion_retires_parent_and_downstream_bases_only(tmp_path: Path) -> None:
    root, space, owner, _activity, _seed_works, plan, create = _space(tmp_path)
    marker = f"synthetic child goal {uuid4()}"
    kept = f"synthetic independent sibling {uuid4()}"
    parent, roles = _composite(root, owner, create, plan, a_goal=f"Check {marker}", c_inputs=())
    _close(root, space, owner, roles["a"], "cancelled", "Branch not needed")
    downstream = _close(root, space, owner, roles["b"], "cancelled", "Depended on A")
    sibling = _close(root, space, owner, roles["c"], "failed", kept)
    parent_outcome = _close(root, space, owner, parent, "failed", f"A was to: Check {marker}")
    old_backup = create_backup(root, uuid4(), owner)

    _apply(
        root,
        space,
        owner,
        DeleteWorkRequest,
        work_id=roles["a"],
        expected_revision=read_work(root, roles["a"], owner).revision,
    )
    assert complete_deletions(root, owner).live_store_sanitized
    assert not old_backup.package.exists()

    with pytest.raises(FoundationError, match="content_unavailable"):
        read_work(root, roles["a"], owner)
    _assert_retired(root, owner, parent, parent_outcome)
    _assert_retired(root, owner, roles["b"], downstream)
    _assert_kept(root, owner, roles["c"], sibling, kept)
    _assert_clean(root, owner, (marker,), kept)
    assert _restarted_bases(root, owner, (parent, roles["b"], roles["c"])) == [
        "None",
        "None",
        repr(kept),
    ]


def test_input_deletion_retires_the_acceptance_basis(tmp_path: Path) -> None:
    root, space, owner, activity, _seed_works, _plan, _create = _space(tmp_path)
    marker = f"synthetic accepted input {uuid4()}"
    kept = f"synthetic independent acceptance {uuid4()}"
    x = _artifact(root, space, owner, marker.encode())
    y = _artifact(root, space, owner, b"synthetic other input")
    work, outcome = _plain_accepted(root, space, owner, activity, x, f"Input X said: {marker}")
    other, other_outcome = _plain_accepted(root, space, owner, activity, y, kept)
    old_backup = create_backup(root, uuid4(), owner)

    _apply(root, space, owner, DeleteArtifactRequest, artifact_id=x, expected_revision=1)
    assert complete_deletions(root, owner).live_store_sanitized
    assert not old_backup.package.exists()

    _assert_retired(root, owner, work, outcome)
    acceptance = read_work(root, work, owner).state.acceptance
    assert acceptance is not None
    assert acceptance.authority_source == "fictional-trusted-console"
    with pytest.raises(FoundationError, match="work_closed"):
        _apply(
            root,
            space,
            owner,
            AcceptWorkRequest,
            work_id=work,
            expected_revision=read_work(root, work, owner).revision,
            basis="Accept again",
        )
    _assert_kept(root, owner, other, other_outcome, kept)
    _assert_clean(root, owner, (marker,), kept)
    assert _restarted_bases(root, owner, (work, other)) == ["None", repr(kept)]


def _delete_in_new_process(root: Path, space: UUID, kind: str, record: UUID) -> None:
    """Delete one Work or Artifact and finish maintenance in a separate Python process."""

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; from uuid import UUID, uuid4; "
            "from zaratustra.foundation import DeleteArtifactRequest, DeleteWorkRequest, "
            "apply_operation, authorize_local, complete_deletions, read_artifact, read_work; "
            "p=Path(sys.argv[1]); o=authorize_local(p, actor='owner', source_ref='restart'); "
            "s, r = UUID(sys.argv[2]), UUID(sys.argv[4]); "
            "q = DeleteWorkRequest(operation_id=uuid4(), space_id=s, actor='owner', work_id=r, "
            "expected_revision=read_work(p, r, o).revision) if sys.argv[3] == 'work' else "
            "DeleteArtifactRequest(operation_id=uuid4(), space_id=s, actor='owner', "
            "artifact_id=r, expected_revision=read_artifact(p, r, o).revision); "
            "apply_operation(p, q, o); print(complete_deletions(p, o).live_store_sanitized)",
            str(root),
            str(space),
            kind,
            str(record),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


@pytest.mark.parametrize("second", ["work", "artifact"])
def test_sequential_deletions_follow_the_sanitized_plan_index_after_restart(
    tmp_path: Path, second: str
) -> None:
    root, space, owner, _activity, _seed_works, plan, create = _space(tmp_path)
    markers = {role: f"synthetic {role} basis {uuid4()}" for role in ("a", "b", "c", "parent")}
    q = _artifact(root, space, owner, b"synthetic input of a only")
    z = _artifact(root, space, owner, b"synthetic input of c only")
    parent, roles = _composite(
        root,
        owner,
        create,
        plan,
        a_inputs=(ArtifactRef(artifact_id=q, revision=1),),
        c_inputs=(ArtifactRef(artifact_id=z, revision=1),),
    )
    outcomes = {
        "a": _close(root, space, owner, roles["a"], "failed", markers["a"]),
        "b": _close(root, space, owner, roles["b"], "cancelled", markers["b"]),
        "c": _close(root, space, owner, roles["c"], "failed", markers["c"]),
        "parent": _close(root, space, owner, parent, "failed", markers["parent"]),
    }
    first_backup = create_backup(root, uuid4(), owner)

    # Z belongs to role c only: c and the parent depend on it, a and b do not.
    _apply(root, space, owner, DeleteArtifactRequest, artifact_id=z, expected_revision=1)
    assert complete_deletions(root, owner).live_store_sanitized
    assert not first_backup.package.exists()
    with pytest.raises(FoundationError, match="content_unavailable"):
        read_work_plan(root, parent, owner)
    _assert_retired(root, owner, roles["c"], outcomes["c"])
    _assert_retired(root, owner, parent, outcomes["parent"])
    for role in ("a", "b"):
        _assert_kept(root, owner, roles[role], outcomes[role], markers[role])
    second_backup = create_backup(root, uuid4(), owner)

    # A new process deletes A or its own input Q; the plan is now known only by its index.
    if second == "work":
        _delete_in_new_process(root, space, "work", roles["a"])
        with pytest.raises(FoundationError, match="content_unavailable"):
            read_work(root, roles["a"], owner)
    else:
        _delete_in_new_process(root, space, "artifact", q)
        _assert_retired(root, owner, roles["a"], outcomes["a"])
    assert not second_backup.package.exists()
    _assert_retired(root, owner, roles["b"], outcomes["b"])
    _assert_clean(root, owner, tuple(markers.values()), None)


def test_older_schema_keeps_its_format_until_the_explicit_upgrade(tmp_path: Path) -> None:
    root = tmp_path / "space"
    root.mkdir()
    info = initialize_space(root)
    owner = authorize_local(root, actor="owner", source_ref="fictional-trusted-console")
    space = info.space_id
    _apply(root, space, owner, BootstrapRequest, decision_id=uuid4(), grant_id=uuid4())
    assert upgrade_space(root, owner).schema_version == 2
    activity = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateActivityRequest,
        activity_id=activity,
        state=ActivityState(title="Synthetic", goal="Synthetic acceptance"),
    )
    marker = f"synthetic schema two input {uuid4()}"
    kept = f"synthetic schema two independent {uuid4()}"
    x = _artifact(root, space, owner, marker.encode())
    y = _artifact(root, space, owner, b"synthetic other input")
    work, outcome = _plain_accepted(root, space, owner, activity, x, f"Input X said: {marker}")
    other, other_outcome = _plain_accepted(root, space, owner, activity, y, kept)
    _apply(root, space, owner, DeleteArtifactRequest, artifact_id=x, expected_revision=1)
    assert complete_deletions(root, owner).live_store_sanitized

    # Schema 2 has no sanitized acceptance format; reads never migrate the space.
    assert read_space(root).schema_version == 2
    assert _basis(root, owner, work) == f"Input X said: {marker}"
    assert apply_operation(root, outcome[0], owner) == outcome[1]
    backup = create_backup(root, uuid4(), owner)

    for upgrade, version in (
        (upgrade_execution_space, 3),
        (upgrade_continuation_space, 4),
        (upgrade_composition_space, 5),
        (upgrade_child_execution_space, 6),
    ):
        assert upgrade(root, owner).schema_version == version
    # Retiring bases finishes earlier deletions, so the upgrade also needs the delete right.
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest,
        grant_id=uuid4(),
        state=GrantState(grantee="maintainer", actions=("maintenance.backup",)),
    )
    maintainer = authorize_local(root, actor="maintainer", source_ref="fictional-maintainer")
    with pytest.raises(FoundationError, match="permission_denied"):
        upgrade_plan_revision_space(root, maintainer)
    assert read_space(root).schema_version == 6
    assert _basis(root, owner, work) == f"Input X said: {marker}"
    assert upgrade_plan_revision_space(root, owner).schema_version == 7
    # The explicit upgrade to 7 retires bases whose dependencies were deleted before it.
    _assert_retired(root, owner, work, outcome)
    _assert_kept(root, owner, other, other_outcome, kept)
    assert complete_deletions(root, owner).live_store_sanitized
    assert not backup.package.exists()
    _assert_clean(root, owner, (marker,), kept)
