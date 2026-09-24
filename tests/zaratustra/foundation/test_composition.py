"""Model-free composite Work behavior through public Core operations."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from zaratustra.foundation import (
    AcceptWorkRequest,
    ActivityState,
    ArtifactRef,
    BootstrapRequest,
    ConfirmObligationRequest,
    CreateActivityRequest,
    CreateArtifactRequest,
    CreateCompositeWorkRequest,
    CreateGrantRequest,
    CreateMethodVersionRequest,
    DeleteMethodVersionRequest,
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
    OperationReceipt,
    OutputContract,
    PlanChild,
    PlanCondition,
    PlanOutputBinding,
    RecoverRequest,
    ReviseArtifactRequest,
    ReviseWorkPlanRequest,
    RevokeGrantRequest,
    StartAttemptRequest,
    WorkPlan,
    WorkState,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    create_backup,
    initialize_space,
    read_activity,
    read_assigned_control,
    read_method_version,
    read_obligation,
    read_receipt,
    read_space,
    read_work,
    read_work_plan,
    restore_backup,
    upgrade_composition_space,
    upgrade_continuation_space,
    upgrade_execution_space,
    upgrade_space,
)


def _apply(
    root: Path, space: UUID, owner: LocalAuthority, request_type: type[Any], **fields: object
) -> OperationReceipt:
    request = request_type(operation_id=uuid4(), space_id=space, actor="owner", **fields)
    return apply_operation(root, request, owner)


type Seed = tuple[
    Path,
    UUID,
    LocalAuthority,
    UUID,
    UUID,
    MethodRef,
    UUID,
    UUID,
    UUID,
    WorkPlan,
    CreateCompositeWorkRequest,
]


def _seed(tmp_path: Path) -> Seed:
    root = tmp_path / "space"
    root.mkdir()
    info = initialize_space(root)
    owner = authorize_local(root, actor="owner", source_ref="fictional-trusted-console")
    _apply(
        root,
        info.space_id,
        owner,
        BootstrapRequest,
        decision_id=uuid4(),
        grant_id=uuid4(),
    )
    assert upgrade_space(root, owner).schema_version == 2
    assert upgrade_execution_space(root, owner).schema_version == 3
    assert upgrade_continuation_space(root, owner).schema_version == 4
    assert upgrade_composition_space(root, owner).schema_version == 5
    activity, source, method, parent, a, b = (uuid4() for _ in range(6))
    _apply(
        root,
        info.space_id,
        owner,
        CreateActivityRequest,
        activity_id=activity,
        state=ActivityState(title="Synthetic packet", goal="Prepare a synthetic packet"),
    )
    _apply(
        root,
        info.space_id,
        owner,
        CreateArtifactRequest,
        artifact_id=source,
        media_type="text/plain",
        content=b"synthetic source",
    )
    definition = MethodDefinition(
        instruction="Check the synthetic source, then write a synthetic summary.",
        named_inputs=(OutputContract(slot="source", media_type="text/plain"),),
        named_outputs=(OutputContract(slot="final", media_type="text/plain"),),
        obligations=(
            MethodObligation(
                key="checked",
                source="synthetic method contract",
                role="a",
                slot="checked",
                media_type="text/plain",
            ),
            MethodObligation(
                key="final",
                source="synthetic method contract",
                role="b",
                slot="final",
                media_type="text/plain",
            ),
        ),
        source_ref="synthetic-method-proposal",
    )
    method_result = _apply(
        root,
        info.space_id,
        owner,
        CreateMethodVersionRequest,
        method_id=method,
        version=1,
        definition=definition,
    )
    ref = MethodRef(
        method_id=method, version=1, checksum=cast(str, method_result.result["checksum"])
    )
    source_ref = ArtifactRef(artifact_id=source, revision=1)
    parent_state = WorkState(
        activity_id=activity,
        goal="Prepare the synthetic packet",
        inputs=(source_ref,),
        expected_outputs=definition.named_outputs,
        method=ref,
    )
    a_state = WorkState(
        activity_id=activity,
        goal="Check source",
        inputs=(source_ref,),
        expected_outputs=(OutputContract(slot="checked", media_type="text/plain"),),
    )
    b_state = WorkState(
        activity_id=activity,
        goal="Write final summary",
        expected_outputs=(OutputContract(slot="final", media_type="text/plain"),),
    )
    dependency = PlanCondition(
        kind="accepted_output",
        role="a",
        slot="checked",
        media_type="text/plain",
    )
    completion = PlanCondition(
        kind="all",
        members=(
            PlanCondition(kind="work_succeeded", role="a"),
            PlanCondition(kind="work_succeeded", role="b"),
        ),
    )
    plan = WorkPlan(
        named_inputs=(NamedInput(slot="source", artifact=source_ref),),
        output_bindings=(
            PlanOutputBinding(
                parent_slot="final",
                role="b",
                child_slot="final",
                media_type="text/plain",
            ),
        ),
        children=(
            PlanChild(role="a", work_id=a, state=a_state),
            PlanChild(role="b", work_id=b, state=b_state, readiness=dependency),
        ),
        completion=completion,
        basis=(source_ref,),
        rationale="Initial synthetic plan",
        source_ref="fictional-owner-plan",
    )
    create = CreateCompositeWorkRequest(
        operation_id=uuid4(),
        space_id=info.space_id,
        actor="owner",
        work_id=parent,
        state=parent_state,
        plan=plan,
    )
    receipt = apply_operation(root, create, owner)
    assert receipt.result["obligation_count"] == 2
    assert apply_operation(root, create, owner) == receipt
    return root, info.space_id, owner, activity, source, ref, parent, a, b, plan, create


def _result(
    root: Path, space: UUID, owner: LocalAuthority, work: UUID, slot: str, content: bytes
) -> ArtifactRef:
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
    linked = _apply(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=work,
        expected_revision=read_work(root, work, owner).revision,
        output=LinkedOutput(slot=slot, artifact=ArtifactRef(artifact_id=artifact, revision=1)),
    )
    _apply(
        root,
        space,
        owner,
        AcceptWorkRequest,
        work_id=work,
        expected_revision=linked.result["revision"],
        basis="Checked synthetic output",
    )
    return ArtifactRef(artifact_id=artifact, revision=1)


def _revised(
    root: Path, space: UUID, owner: LocalAuthority, parent: UUID, plan: WorkPlan
) -> WorkPlan:
    updated = plan.model_copy(update={"rationale": "Reviewed before any child was issued"})
    _apply(
        root,
        space,
        owner,
        ReviseWorkPlanRequest,
        work_id=parent,
        expected_plan_revision=1,
        plan=updated,
    )
    assert read_work_plan(root, parent, owner, revision=1).plan.rationale == plan.rationale
    assert read_work_plan(root, parent, owner).revision == 2
    return updated


def test_two_children_obligations_replay_and_restart(tmp_path: Path) -> None:
    root, space, owner, activity, _source, ref, parent, a, b, plan, _create = _seed(tmp_path)
    _revised(root, space, owner, parent, plan)
    assert read_method_version(root, ref, owner).reference == ref
    assert {read_obligation(root, parent, key, owner).status for key in ("checked", "final")} == {
        "open"
    }
    with pytest.raises(FoundationError, match="stale_plan"):
        _apply(
            root,
            space,
            owner,
            IssueChildWorkRequest,
            parent_work_id=parent,
            work_id=a,
            expected_plan_revision=1,
            expected_work_revision=1,
        )
    with pytest.raises(FoundationError, match="dependency_open"):
        _apply(
            root,
            space,
            owner,
            IssueChildWorkRequest,
            parent_work_id=parent,
            work_id=b,
            expected_plan_revision=2,
            expected_work_revision=1,
        )
    with pytest.raises(FoundationError, match="unsupported_composite_execution"):
        _apply(
            root,
            space,
            owner,
            StartAttemptRequest,
            attempt_id=uuid4(),
            work_id=b,
            expected_work_revision=1,
            resource_id=uuid4(),
            expected_resource_revision=1,
            session_id=uuid4(),
        )
    with pytest.raises(FoundationError, match="obligation_open"):
        _apply(
            root,
            space,
            owner,
            AcceptWorkRequest,
            work_id=parent,
            expected_revision=1,
            basis="Premature",
        )
    _apply(
        root,
        space,
        owner,
        IssueChildWorkRequest,
        parent_work_id=parent,
        work_id=a,
        expected_plan_revision=2,
        expected_work_revision=1,
    )
    a_ref = _result(root, space, owner, a, "checked", b"checked synthetic source")
    issue_b = IssueChildWorkRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        parent_work_id=parent,
        work_id=b,
        expected_plan_revision=2,
        expected_work_revision=1,
    )
    assert apply_operation(root, issue_b, owner).result["inputs"] == [a_ref.model_dump(mode="json")]
    assert apply_operation(root, issue_b, owner).result["inputs"] == [a_ref.model_dump(mode="json")]
    b_ref = _result(root, space, owner, b, "final", b"final synthetic summary")
    for key, evidence in (("checked", a_ref), ("final", b_ref)):
        request = ConfirmObligationRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=parent,
            key=key,
            expected_plan_revision=2,
            expected_obligation_revision=1,
            evidence=evidence,
            basis="Explicit synthetic owner review",
        )
        receipt = apply_operation(root, request, owner)
        assert apply_operation(root, request, owner) == receipt
        assert read_obligation(root, parent, key, owner, revision=1).status == "open"
        assert read_obligation(root, parent, key, owner).status == "satisfied"
    wrong = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=wrong,
        media_type="text/plain",
        content=b"unrelated synthetic text",
    )
    _apply(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=parent,
        expected_revision=1,
        output=LinkedOutput(slot="final", artifact=ArtifactRef(artifact_id=wrong, revision=1)),
    )
    with pytest.raises(FoundationError, match="output_mismatch"):
        _apply(
            root,
            space,
            owner,
            AcceptWorkRequest,
            work_id=parent,
            expected_revision=2,
            basis="Wrong parent output",
        )
    _apply(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=parent,
        expected_revision=2,
        output=LinkedOutput(slot="final", artifact=b_ref),
    )
    accepted = AcceptWorkRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        work_id=parent,
        expected_revision=3,
        basis="Separate synthetic parent acceptance",
    )
    assert apply_operation(root, accepted, owner).result["status"] == "succeeded"
    assert apply_operation(root, accepted, owner).result["status"] == "succeeded"
    assert read_activity(root, activity, owner).state.status == "ongoing"
    code = (
        "import sys; from pathlib import Path; from uuid import UUID; "
        "from zaratustra.foundation import authorize_local,read_method_version,"
        "read_work_plan,read_obligation,read_work,MethodRef; "
        "p=Path(sys.argv[1]); a=authorize_local(p,actor='owner',source_ref='restart'); "
        "w=UUID(sys.argv[2]); m=MethodRef.model_validate_json(sys.argv[3]); "
        "assert read_method_version(p,m,a).reference==m; "
        "assert read_work_plan(p,w,a).revision==2; "
        "assert read_obligation(p,w,'final',a).status=='satisfied'; "
        "assert read_work(p,w,a).state.status=='succeeded'"
    )
    child = subprocess.run(
        [sys.executable, "-c", code, str(root), str(parent), ref.model_dump_json()],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert child.returncode == 0, child.stderr


def test_stale_inputs_cycle_and_method_deletion(tmp_path: Path) -> None:
    root, space, owner, _activity, source, ref, parent, a, b, plan, create = _seed(tmp_path)
    cycle = plan.model_copy(
        update={
            "children": (
                plan.children[0].model_copy(
                    update={"readiness": PlanCondition(kind="work_succeeded", role="b")}
                ),
                plan.children[1],
            ),
        }
    )
    with pytest.raises(FoundationError, match="dependency_cycle"):
        _apply(
            root,
            space,
            owner,
            ReviseWorkPlanRequest,
            work_id=parent,
            expected_plan_revision=1,
            plan=cycle,
        )
    with pytest.raises(FoundationError, match="method_in_use"):
        _apply(
            root,
            space,
            owner,
            DeleteMethodVersionRequest,
            method_id=ref.method_id,
            version=ref.version,
            checksum=ref.checksum,
        )
    _apply(
        root,
        space,
        owner,
        ReviseArtifactRequest,
        artifact_id=source,
        expected_revision=1,
        media_type="text/plain",
        content=b"changed synthetic source",
    )
    with pytest.raises(FoundationError, match="stale_basis"):
        _apply(
            root,
            space,
            owner,
            IssueChildWorkRequest,
            parent_work_id=parent,
            work_id=a,
            expected_plan_revision=1,
            expected_work_revision=1,
        )
    conflict = create.model_copy(update={"plan": plan.model_copy(update={"rationale": "conflict"})})
    with pytest.raises(FoundationError, match="operation_conflict"):
        apply_operation(root, conflict, owner)
    assert read_obligation(root, parent, "final", owner).status == "open"


def test_revised_child_artifact_cannot_be_accepted(tmp_path: Path) -> None:
    root, space, owner, _activity, _source, _ref, parent, a, _b, _plan, _create = _seed(tmp_path)
    _apply(
        root,
        space,
        owner,
        IssueChildWorkRequest,
        parent_work_id=parent,
        work_id=a,
        expected_plan_revision=1,
        expected_work_revision=1,
    )
    result = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=result,
        media_type="text/plain",
        content=b"first version",
    )
    _apply(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=a,
        expected_revision=2,
        output=LinkedOutput(slot="checked", artifact=ArtifactRef(artifact_id=result, revision=1)),
    )
    _apply(
        root,
        space,
        owner,
        ReviseArtifactRequest,
        artifact_id=result,
        expected_revision=1,
        media_type="text/plain",
        content=b"changed version",
    )
    with pytest.raises(FoundationError, match="stale_basis"):
        _apply(
            root,
            space,
            owner,
            AcceptWorkRequest,
            work_id=a,
            expected_revision=3,
            basis="Stale result",
        )
    assert read_work(root, a, owner).state.status == "proposed"


def test_method_version_pin_and_revoked_right(tmp_path: Path) -> None:
    root, space, owner, _activity, _source, ref, parent, a, b, plan, _create = _seed(tmp_path)
    current = read_method_version(root, ref, owner)
    second = current.definition.model_copy(update={"instruction": "A newer fictional instruction"})
    v2 = _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=ref.method_id,
        version=2,
        definition=second,
    )
    assert v2.result["checksum"] != ref.checksum
    assert read_work(root, parent, owner).state.method == ref
    assert read_method_version(root, ref, owner).definition == current.definition
    worker_grant = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest,
        grant_id=worker_grant,
        state=GrantState(
            grantee="worker", actions=("work.execute", "method.use", "record.read", "receipt.read")
        ),
    )
    worker = authorize_local(root, actor="worker", source_ref="fictional-worker")
    apply_operation(
        root,
        IssueChildWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="worker",
            parent_work_id=parent,
            work_id=a,
            expected_plan_revision=1,
            expected_work_revision=1,
        ),
        worker,
    )
    _result(root, space, owner, a, "checked", b"checked")
    _apply(
        root,
        space,
        owner,
        RevokeGrantRequest,
        grant_id=worker_grant,
        expected_revision=1,
    )
    denied = IssueChildWorkRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="worker",
        parent_work_id=parent,
        work_id=b,
        expected_plan_revision=1,
        expected_work_revision=1,
    )
    with pytest.raises(FoundationError, match="permission_denied"):
        apply_operation(root, denied, worker)
    with pytest.raises(FoundationError, match="permission_denied"):
        read_assigned_control(root, b, uuid4(), worker)
    assert read_work(root, b, owner).revision == 1
    assert read_obligation(root, parent, "final", owner).status == "open"


def test_unplanned_child_does_not_erase_method_obligation(tmp_path: Path) -> None:
    root, space, owner, _activity, _source, _ref, _parent, _a, _b, plan, create = _seed(tmp_path)
    new_parent, new_a, new_b = (uuid4() for _ in range(3))
    first_a = plan.children[0].model_copy(update={"work_id": new_a})
    later_b = plan.children[1].model_copy(update={"work_id": new_b})
    first_plan = plan.model_copy(
        update={
            "children": (first_a,),
            "completion": PlanCondition(kind="work_succeeded", role="b"),
            "rationale": "Second child is not yet planned",
        }
    )
    request = create.model_copy(
        update={"operation_id": uuid4(), "work_id": new_parent, "plan": first_plan}
    )
    assert apply_operation(root, request, owner).result["obligation_count"] == 2
    assert read_obligation(root, new_parent, "final", owner).status == "open"
    with pytest.raises(FoundationError, match="obligation_open"):
        _apply(
            root,
            space,
            owner,
            AcceptWorkRequest,
            work_id=new_parent,
            expected_revision=1,
            basis="Missing second part",
        )
    revised = first_plan.model_copy(
        update={
            "children": (first_a, later_b),
            "completion": plan.completion,
            "rationale": "Second child now planned before execution",
        }
    )
    _apply(
        root,
        space,
        owner,
        ReviseWorkPlanRequest,
        work_id=new_parent,
        expected_plan_revision=1,
        plan=revised,
    )
    assert len(read_work_plan(root, new_parent, owner, revision=1).plan.children) == 1
    assert len(read_work_plan(root, new_parent, owner).plan.children) == 2
    assert read_obligation(root, new_parent, "final", owner).revision == 1
    assert read_work(root, new_b, owner).state.status == "proposed"


def test_composite_creation_rolls_back_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import zaratustra.foundation.composition as composition

    root, space, owner, _activity, _source, _ref, _parent, _a, _b, plan, create = _seed(tmp_path)
    replacement_parent, replacement_a, replacement_b = (uuid4() for _ in range(3))
    replacement_plan = plan.model_copy(
        update={
            "children": (
                plan.children[0].model_copy(update={"work_id": replacement_a}),
                plan.children[1].model_copy(update={"work_id": replacement_b}),
            )
        }
    )
    request = create.model_copy(
        update={
            "operation_id": uuid4(),
            "work_id": replacement_parent,
            "plan": replacement_plan,
        }
    )
    original = composition._write_subject  # type: ignore[attr-defined]
    calls = 0

    def fail_after_parent(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic failure between parent and child")
        original(*args, **kwargs)

    monkeypatch.setattr(composition, "_write_subject", fail_after_parent)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        apply_operation(root, request, owner)
    with pytest.raises(FoundationError):
        read_work(root, replacement_parent, owner)
    with pytest.raises(FoundationError):
        read_receipt(root, request.operation_id, owner)
    monkeypatch.setattr(composition, "_write_subject", original)
    assert apply_operation(root, request, owner).result["obligation_count"] == 2
    assert read_obligation(root, replacement_parent, "final", owner).status == "open"


def test_backup_restore_and_deletion_of_new_content(tmp_path: Path) -> None:
    root, space, owner, _activity, _source, ref, parent, a, b, plan, _create = _seed(tmp_path)
    _revised(root, space, owner, parent, plan)
    backup = create_backup(root, uuid4(), owner)
    restored_root = tmp_path / "restored"
    restored_root.mkdir()
    restored = restore_backup(
        backup.package, restored_root, authorize_recovery(actor="owner", source_ref="fresh-restore")
    )
    assert restored.recovery_state == "quarantined"
    recovery = authorize_recovery(actor="owner", source_ref="fresh-recovery")
    apply_operation(
        restored_root,
        RecoverRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        recovery,
    )
    restored_owner = authorize_local(restored_root, actor="owner", source_ref="reopened")
    assert read_work_plan(restored_root, parent, restored_owner).revision == 2
    assert (
        read_method_version(restored_root, ref, restored_owner).definition.obligations[1].key
        == "final"
    )
    assert read_obligation(restored_root, parent, "final", restored_owner).status == "open"
    for child_id in (a, b):
        _apply(root, space, owner, DeleteWorkRequest, work_id=child_id, expected_revision=1)
    assert read_obligation(root, parent, "final", owner).status == "open"
    _apply(root, space, owner, DeleteWorkRequest, work_id=parent, expected_revision=1)
    _apply(
        root,
        space,
        owner,
        DeleteMethodVersionRequest,
        method_id=ref.method_id,
        version=ref.version,
        checksum=ref.checksum,
    )
    deleted = complete_deletions(root, owner)
    assert deleted.live_store_sanitized and deleted.pending_jobs == 0
    assert not backup.package.exists()
    with pytest.raises(FoundationError):
        read_method_version(root, ref, owner)
    with pytest.raises(FoundationError):
        read_work_plan(root, parent, owner)
    assert read_space(root).schema_version == 5
