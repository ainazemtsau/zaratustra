"""Composite child Work on the assigned bridge, DBOS delivery and managed cleanup."""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4, uuid5

import pytest
from dbos import DBOS, DBOSClient

import zaratustra.pi_adapter.assigned as assigned_module
from tests.zaratustra.foundation import test_applicability as applicability
from tests.zaratustra.foundation import test_waivers as waivers
from tests.zaratustra.foundation.test_active_plan import _keep, _replace, _revision_request
from tests.zaratustra.foundation.test_child_execution import _stop
from tests.zaratustra.foundation.test_composition import _apply, _result, _seed, _sqlite_contains
from tests.zaratustra.foundation.test_parallel_branches import _issue as _issue_branch
from tests.zaratustra.foundation.test_parallel_branches import _pipeline
from tests.zaratustra.foundation.test_plan_transfers import _case as _transfer_case
from tests.zaratustra.foundation.test_plan_transfers import _pair, _replaced_a
from zaratustra.foundation import (
    AssignAttemptRequest,
    CreateDecisionRequest,
    CreateResourceRequest,
    DecisionState,
    DeleteWorkRequest,
    FoundationError,
    IssueChildWorkRequest,
    LocalAuthority,
    PlanCondition,
    ResourceState,
    ReviseDecisionRequest,
    apply_operation,
    read_assigned_control,
    read_execution,
    read_obligation,
    read_work,
    read_work_status,
    upgrade_child_execution_space,
)
from zaratustra.pi_adapter import Bridge
from zaratustra.pi_adapter.assigned import (
    EXECUTOR_VERSION,
    PI_VERSION,
    WORKFLOW_NAME,
    AssignedConfig,
    complete_assigned_deletions,
    deliver_outbox,
    run_assigned,
)


@pytest.fixture(scope="module")
def child_dbos_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database = tmp_path_factory.mktemp("child-dbos") / "executor.sqlite3"
    DBOS(
        config={
            "name": "zaratustra-assigned-rpc",
            "system_database_url": f"sqlite:///{database.resolve().as_posix()}",
            "application_version": EXECUTOR_VERSION,
        }
    )
    DBOS.launch()
    DBOS.destroy(destroy_registry=True, workflow_completion_timeout_sec=1)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
    return database


def _workflows(root: Path) -> list[dict[str, object]]:
    client = DBOSClient(
        system_database_url=(
            f"sqlite:///{(root / '.zara-core' / 'executor.sqlite3').resolve().as_posix()}"
        ),
        application_name="zaratustra-assigned-rpc",
        retry_connection_errors=False,
    )
    try:
        return [
            dict(workflow.attributes or {})
            for workflow in client.list_workflows(
                name=WORKFLOW_NAME,
                application_name="zaratustra-assigned-rpc",
                load_input=False,
                load_output=False,
            )
        ]
    finally:
        client.destroy()


def _resource(root: Path, space: UUID, owner: LocalAuthority, work: UUID, name: str) -> Path:
    directory = root.parent / name
    directory.mkdir(exist_ok=True)
    _apply(
        root,
        space,
        owner,
        CreateResourceRequest,
        resource_id=uuid4(),
        work_id=work,
        state=ResourceState(label=name, root=directory, limit_units=100),
    )
    return directory


def _assign(root: Path, space: UUID, owner: LocalAuthority, work: UUID) -> tuple[UUID, UUID]:
    snapshot = read_execution(root, work, owner)
    attempt, session = uuid4(), uuid4()
    apply_operation(
        root,
        AssignAttemptRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            attempt_id=attempt,
            work_id=work,
            expected_work_revision=snapshot.work.revision,
            resource_id=snapshot.resources[0].resource_id,
            expected_resource_revision=1,
            session_id=session,
            executor_version=EXECUTOR_VERSION,
        ),
        owner,
    )
    return attempt, session


def _issue(root: Path, space: UUID, owner: LocalAuthority, parent: UUID, child: UUID) -> None:
    _apply(
        root,
        space,
        owner,
        IssueChildWorkRequest,
        parent_work_id=parent,
        work_id=child,
        expected_plan_revision=1,
        expected_work_revision=1,
    )


def _config(root: Path, workspace: Path, runtime: Path) -> AssignedConfig:
    package = runtime / "node_modules" / "@earendil-works" / "pi-coding-agent"
    cli = package / "dist" / "bundle" / "cli.js"
    cli.parent.mkdir(parents=True, exist_ok=True)
    cli.write_text("synthetic", encoding="utf-8")
    (package / "package.json").write_text(
        '{"name":"@earendil-works/pi-coding-agent","version":"' + PI_VERSION + '"}',
        encoding="utf-8",
    )
    return AssignedConfig(
        space=root,
        workspace=workspace,
        pi_cli=cli,
        pi_runtime=runtime,
        node="node",
        provider_profile="local-completions",
        provider_base_url="http://127.0.0.1:9/v1",
        provider_id="synthetic",
        model_id="synthetic",
        context_window=4096,
        max_tokens=512,
        reserve_units=10,
        limit_units=100,
        offline=True,
    )


def test_bridges_show_child_state_and_carry_one_addressed_answer(tmp_path: Path) -> None:
    root, space, owner, activity, _source, _ref, parent, a, b, _plan, _create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    workspace = _resource(root, space, owner, a, "workspace-a")
    interactive = Bridge(root, owner, workspace, 100)
    session = uuid4()
    records = cast(list[dict[str, Any]], interactive.connect(session)["records"])
    lifecycle = {row["record_id"]: row.get("lifecycle") for row in records if row["kind"] == "work"}
    assert lifecycle == {str(parent): "ready", str(a): "proposed", str(b): "blocked"}
    parent_view = interactive.select(session, activity, parent)
    assert parent_view["resources"] == []
    blocked = interactive.select(session, activity, b)
    assert blocked["resources"] == []
    assert cast(dict[str, Any], blocked["status"])["status"] == "blocked"

    _issue(root, space, owner, parent, a)
    attempt, rpc_session = _assign(root, space, owner, a)
    rpc = Bridge(
        root,
        owner,
        workspace,
        100,
        assigned_attempt_id=attempt,
        assigned_session_id=rpc_session,
    )
    rpc.connect(rpc_session)
    rpc.select(rpc_session, activity, a)
    wait_id = uuid4()
    rpc.open_wait(rpc_session, attempt, wait_id, "Synthetic partial", "Which line?", "Finish")
    interactive.select(session, activity, a)
    shown = interactive.snapshot(session)
    assert cast(dict[str, Any], shown["status"])["status"] == "waiting"
    assert cast(dict[str, Any], shown["status"])["wait_id"] == str(wait_id)
    composition = cast(dict[str, Any], shown["composition"])
    assert composition["parent_work_id"] == str(parent) and composition["role"] == "a"
    assert [pin["attempt_id"] for pin in composition["pins"]] == [str(attempt)]
    assert cast(list[dict[str, Any]], shown["waits"])[0]["question"] == "Which line?"
    first = interactive.answer_wait(session, wait_id, "The first line")
    assert interactive.answer_wait(session, wait_id, "The first line") == first
    assert read_work_status(root, a, owner).status == "ready"

    invocation = uuid4()
    common = {
        "protocol_version": 1,
        "space_id": str(space),
        "actor": "owner",
        "invocation_id": str(invocation),
        "attempt_id": str(attempt),
        "work_id": str(a),
        "session_id": str(rpc_session),
    }
    rpc.operation(
        rpc_session,
        {
            **common,
            "operation_id": str(uuid4()),
            "kind": "prepare_invocation",
            "purpose": "content",
            "provider": "synthetic",
            "model": "synthetic",
            "transport": "http-sse",
            "request_sha256": "B" * 64,
            "request_bytes": 12,
            "reserve_units": 10,
        },
    )
    for kind in ("admit_invocation", "send_invocation"):
        rpc.operation(rpc_session, {**common, "operation_id": str(uuid4()), "kind": kind})
    rpc.operation(
        rpc_session,
        {
            **common,
            "operation_id": str(uuid4()),
            "kind": "finish_invocation",
            "outcome": "answered",
            "usage_units": 4,
        },
    )
    rpc.publish(rpc_session, attempt, "checked", "text/plain", "Synthetic checked result")
    assert read_work_status(root, a, owner).status == "running"
    preview = interactive.accept_preview(session)
    accepted = interactive.accept(session, UUID(str(preview["nonce"])), "Checked synthetic line")
    assert accepted["result"] == {
        "record_id": str(a),
        "revision": read_work(root, a, owner).revision,
        "status": "succeeded",
    }
    assert read_work_status(root, a, owner).status == "succeeded"
    assert read_work_status(root, b, owner).status == "proposed"


def test_duplicate_delivery_issues_one_child_workflow_and_cleanup_is_addressed(
    tmp_path: Path, child_dbos_template: Path
) -> None:
    root, space, owner, _activity, _source, _ref, parent, a, _b, _plan, _create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    _resource(root, space, owner, a, "workspace-a")
    _issue(root, space, owner, parent, a)
    attempt, _session = _assign(root, space, owner, a)
    shutil.copyfile(child_dbos_template, root / ".zara-core" / "executor.sqlite3")
    first = deliver_outbox(root, owner)
    second = deliver_outbox(root, owner)
    assert first == second and len(first) == 1
    assert _workflows(root) == [{"work_id": str(a), "attempt_id": str(attempt)}]
    home = root / ".zara-core" / "pi-rpc-home" / str(attempt)
    home.mkdir(parents=True)
    marker = f"synthetic managed child copy {uuid4()}"
    (home / "copy.txt").write_text(marker, encoding="utf-8", newline="\n")
    snapshot = read_execution(root, a, owner)
    apply_operation(
        root,
        DeleteWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=a,
            expected_revision=snapshot.work.revision,
        ),
        owner,
    )
    deleted = complete_assigned_deletions(root, owner)
    assert deleted.live_store_sanitized and deleted.pending_jobs == 0
    assert _workflows(root) == [] and not home.exists()
    with closing(sqlite3.connect(root / ".zara-core" / "core.sqlite3")) as connection:
        assert connection.execute("SELECT count(*) FROM execution_plan_pins").fetchone() == (0,)
    assert not _sqlite_contains(root / ".zara-core", marker)
    assert read_obligation(root, parent, "checked", owner).status == "open"


def test_parallel_children_get_one_workflow_each_and_addressed_cleanup(
    tmp_path: Path, child_dbos_template: Path
) -> None:
    branches = _pipeline(tmp_path)
    root, space, owner, parent, works = branches
    attempts: dict[str, tuple[UUID, UUID]] = {}
    for role in ("a1", "a2"):
        _issue_branch(branches, role)
        _resource(root, space, owner, works[role], f"workspace-{role}")
        attempts[role] = _assign(root, space, owner, works[role])
    shutil.copyfile(child_dbos_template, root / ".zara-core" / "executor.sqlite3")
    first = deliver_outbox(root, owner)
    second = deliver_outbox(root, owner)
    # Redelivery never launches a node twice: one workflow per Attempt, whatever its neighbour.
    assert first == second and len(first) == 2
    expected = [
        {"work_id": str(works[role]), "attempt_id": str(attempts[role][0])} for role in ("a1", "a2")
    ]
    assert sorted(_workflows(root), key=str) == sorted(expected, key=str)
    client = DBOSClient(
        system_database_url=(
            f"sqlite:///{(root / '.zara-core' / 'executor.sqlite3').resolve().as_posix()}"
        ),
        application_name="zaratustra-assigned-rpc",
        retry_connection_errors=False,
    )
    try:
        routed = client.list_workflows(
            name=WORKFLOW_NAME,
            application_name="zaratustra-assigned-rpc",
            load_input=False,
            load_output=False,
        )
        assert {(item.app_version, item.queue_name) for item in routed} == {
            (
                f"{EXECUTOR_VERSION}-{attempts[role][0]}",
                f"zara-assigned-rpc-{attempts[role][0]}",
            )
            for role in ("a1", "a2")
        }
    finally:
        client.destroy()
    markers: dict[str, str] = {}
    for role in ("a1", "a2"):
        home = root / ".zara-core" / "pi-rpc-home" / str(attempts[role][0])
        home.mkdir(parents=True)
        markers[role] = f"synthetic managed {role} copy {uuid4()}"
        (home / "copy.txt").write_text(markers[role], encoding="utf-8", newline="\n")

    _stop(root, space, owner, works["a2"], *attempts["a2"])
    apply_operation(
        root,
        DeleteWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=works["a2"],
            expected_revision=read_work(root, works["a2"], owner).revision,
        ),
        owner,
    )
    deleted = complete_assigned_deletions(root, owner)
    assert deleted.live_store_sanitized and deleted.pending_jobs == 0
    assert _workflows(root) == [expected[0]]
    assert not (root / ".zara-core" / "pi-rpc-home" / str(attempts["a2"][0])).exists()
    assert (root / ".zara-core" / "pi-rpc-home" / str(attempts["a1"][0])).is_dir()
    assert not _sqlite_contains(root / ".zara-core", markers["a2"])
    with closing(sqlite3.connect(root / ".zara-core" / "core.sqlite3")) as connection:
        assert connection.execute(
            "SELECT work_id, attempt_id FROM execution_plan_pins"
        ).fetchall() == [(str(works["a1"]), str(attempts["a1"][0]))]
    for key in ("a1_checked", "a2_checked", "i_final"):
        assert read_obligation(root, parent, key, owner).status == "open"


def test_legacy_shared_queue_moves_only_the_selected_attempt(
    tmp_path: Path, child_dbos_template: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    branches = _pipeline(tmp_path)
    root, space, owner, _parent, works = branches
    attempts: dict[str, UUID] = {}
    workspaces: dict[UUID, Path] = {}
    for role in ("a2", "a1"):
        _issue_branch(branches, role)
        workspaces[works[role]] = _resource(root, space, owner, works[role], f"workspace-{role}")
        attempts[role] = _assign(root, space, owner, works[role])[0]
    shutil.copyfile(child_dbos_template, root / ".zara-core" / "executor.sqlite3")
    client = DBOSClient(
        system_database_url=(
            f"sqlite:///{(root / '.zara-core' / 'executor.sqlite3').resolve().as_posix()}"
        ),
        application_name="zaratustra-assigned-rpc",
        retry_connection_errors=False,
    )
    ids = {role: f"zara-{uuid5(attempts[role], 'launch')}" for role in attempts}
    try:
        for role in ("a2", "a1"):
            entry = read_execution(root, works[role], owner).outbox[0]
            client.enqueue(
                {
                    "workflow_name": WORKFLOW_NAME,
                    "queue_name": "zara-assigned-rpc",
                    "workflow_id": ids[role],
                    "app_version": EXECUTOR_VERSION,
                    "deduplication_id": str(entry.outbox_id),
                    "duplication_policy": "return-existing",
                    "attributes": {"work_id": str(works[role]), "attempt_id": str(attempts[role])},
                },
                str(works[role]),
                str(attempts[role]),
                entry.execution_epoch,
                entry.generation,
            )
    finally:
        client.destroy()

    executed: list[UUID] = []

    def execute(
        config: AssignedConfig,
        _authority: LocalAuthority,
        work_id: UUID,
        _attempt_id: UUID,
        _epoch: int,
        _generation: int,
    ) -> str:
        assert config.workspace == workspaces[work_id]
        executed.append(work_id)
        return "proposed"

    monkeypatch.setattr(assigned_module, "_execute", execute)

    def statuses() -> dict[str, str]:
        check = DBOSClient(
            system_database_url=(
                f"sqlite:///{(root / '.zara-core' / 'executor.sqlite3').resolve().as_posix()}"
            ),
            application_name="zaratustra-assigned-rpc",
            retry_connection_errors=False,
        )
        try:
            return {
                item.workflow_id: item.status
                for item in check.list_workflows(name=WORKFLOW_NAME, load_output=False)
            }
        finally:
            check.destroy()

    configs = {
        role: _config(root, workspaces[works[role]], tmp_path / "runtime") for role in attempts
    }
    assert run_assigned(configs["a1"], owner, attempts["a1"]) == "proposed"
    assert statuses() == {ids["a1"]: "SUCCESS", ids["a2"]: "ENQUEUED"}
    assert executed == [works["a1"]]
    assert run_assigned(configs["a2"], owner, attempts["a2"]) == "proposed"
    assert statuses() == {ids["a1"]: "SUCCESS", ids["a2"]: "SUCCESS"}
    assert run_assigned(configs["a2"], owner, attempts["a2"]) == "proposed"
    assert len(deliver_outbox(root, owner)) == 2
    assert statuses() == {ids["a1"]: "SUCCESS", ids["a2"]: "SUCCESS"}
    assert executed == [works["a1"], works["a2"]]


def test_assigned_child_context_carries_addressed_parent_obligations(tmp_path: Path) -> None:
    setup = applicability._space(tmp_path)
    case = waivers._case(setup)
    choice = applicability._choose(case, "not_required", applicability._work_scope(case))
    applicability._resolve(case, choice)
    exception = waivers._except(case)
    apply_operation(root := case.root, waivers._waive_request(case, exception), case.owner)
    applicability._issue(case, "a")
    workspace = _resource(root, case.space, case.owner, case.works["a"], "workspace-a")
    attempt, session = _assign(root, case.space, case.owner, case.works["a"])
    bridge = Bridge(
        root, case.owner, workspace, 100, assigned_attempt_id=attempt, assigned_session_id=session
    )
    bridge.connect(session)
    bridge.select(session, case.activity, case.works["a"])
    context = bridge.snapshot(session)
    composition = cast(dict[str, Any], context["composition"])
    assert composition["role"] == "a" and composition["parent_work_id"] == str(case.parent)
    obligations = {item["key"]: item for item in composition["obligations"]}
    assert obligations["checked"]["status"] == "waived"
    assert obligations["checked"]["exception"]["decision_id"] == str(exception.decision_id)
    assert obligations["art_review"]["applicability"] == "inactive"
    assert obligations["art_review"]["choice"]["decision_id"] == str(choice.decision_id)
    assert case.parent != case.works["a"]
    assert "Synthetic plan whose check may be waived" not in json.dumps(composition)


def test_subject_refusal_before_launch_stops_child_without_pi_or_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, space, owner, _activity, _source, _ref, _parent, _a, _b, plan, create = _seed(tmp_path)
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    decision = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateDecisionRequest,
        decision_id=decision,
        state=DecisionState(
            statement="Synthetic branch decision",
            effect="require_grant",
            actions=("space.inspect",),
            subjects=("synthetic-nobody",),
        ),
    )
    first = plan.children[0].model_copy(update={"work_id": uuid4()})
    gated = plan.children[1].model_copy(
        update={
            "work_id": uuid4(),
            "readiness": PlanCondition(
                kind="all",
                members=(
                    PlanCondition(
                        kind="accepted_output", role="a", slot="checked", media_type="text/plain"
                    ),
                    PlanCondition(
                        kind="decision_active", decision_id=decision, decision_revision=1
                    ),
                ),
            ),
        }
    )
    parent = uuid4()
    apply_operation(
        root,
        create.model_copy(
            update={
                "operation_id": uuid4(),
                "work_id": parent,
                "plan": plan.model_copy(update={"children": (first, gated)}),
            }
        ),
        owner,
    )
    _issue(root, space, owner, parent, first.work_id)
    _result(root, space, owner, first.work_id, "checked", b"synthetic checked source")
    _issue(root, space, owner, parent, gated.work_id)
    workspace = _resource(root, space, owner, gated.work_id, "workspace-gated")
    attempt, _session = _assign(root, space, owner, gated.work_id)
    _apply(
        root,
        space,
        owner,
        ReviseDecisionRequest,
        decision_id=decision,
        expected_revision=1,
        state=DecisionState(
            statement="Synthetic branch decision changed",
            effect="require_grant",
            actions=("space.inspect",),
            subjects=("synthetic-nobody",),
        ),
    )

    def no_process(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("A refused child must not start Pi")

    monkeypatch.setattr(
        assigned_module,
        "subprocess",
        SimpleNamespace(
            Popen=no_process,
            PIPE=subprocess.PIPE,
            DEVNULL=subprocess.DEVNULL,
            TimeoutExpired=subprocess.TimeoutExpired,
        ),
    )
    with pytest.raises(FoundationError) as refused:
        run_assigned(_config(root, workspace, tmp_path / "runtime"), owner, attempt)
    assert refused.value.code == "stale_basis"
    after = read_execution(root, gated.work_id, owner)
    assert after.assignments[0].status == "stopped"
    assert after.attempts[0].status == "interrupted"
    assert after.invocations == () and after.outputs == ()
    assert [item.status for item in after.outbox] == ["cancelled"]
    status = read_work_status(root, gated.work_id, owner)
    assert status.status == "blocked" and status.reasons[0].code == "stale_basis"


def test_fenced_child_stops_at_its_next_check_while_the_kept_child_continues(
    tmp_path: Path, child_dbos_template: Path
) -> None:
    branches = _pair(tmp_path)
    root, space, owner, parent, works = branches
    attempts: dict[str, tuple[UUID, UUID]] = {}
    workspaces: dict[str, Path] = {}
    for role in ("a", "b"):
        _issue_branch(branches, role)
        workspaces[role] = _resource(root, space, owner, works[role], f"workspace-{role}")
        attempts[role] = _assign(root, space, owner, works[role])
    shutil.copyfile(child_dbos_template, root / ".zara-core" / "executor.sqlite3")
    assert len(deliver_outbox(root, owner)) == 2
    revised, a, a2, b = _replaced_a(branches)
    case = _transfer_case(branches)
    apply_operation(
        root,
        _revision_request(case, revised, (_replace(case, a, a2, outcome="cancelled"), _keep(b))),
        owner,
    )
    configs = {role: _config(root, workspaces[role], tmp_path / "runtime") for role in ("a", "b")}
    # The kept child's control read passes through its transfer; the fenced one stops.
    assert read_assigned_control(root, b.work_id, attempts["b"][0], owner)
    assert not assigned_module._control_stop_requested(
        configs["b"], owner, b.work_id, attempts["b"][0]
    )
    assert assigned_module._control_stop_requested(configs["a"], owner, a.work_id, attempts["a"][0])
    snapshot = read_execution(root, b.work_id, owner)
    generation = snapshot.attempts[0].generation
    kept = assigned_module._current_snapshot(
        configs["b"], owner, b.work_id, attempts["b"][0], snapshot.execution_epoch, generation
    )
    assert kept.composition is not None and kept.composition.transfers
    with pytest.raises(FoundationError):
        assigned_module._current_snapshot(
            configs["a"], owner, a.work_id, attempts["a"][0], snapshot.execution_epoch, generation
        )
    # On the assigned bridge a fenced child's next call is refused before any HTTP send.
    rpc = Bridge(
        root,
        owner,
        workspaces["a"],
        100,
        assigned_attempt_id=attempts["a"][0],
        assigned_session_id=attempts["a"][1],
    )
    rpc.connect(attempts["a"][1])
    rpc.select(
        attempts["a"][1], read_execution(root, a.work_id, owner).activity.activity_id, a.work_id
    )
    with pytest.raises(FoundationError, match="stale_plan"):
        rpc.operation(
            attempts["a"][1],
            {
                "protocol_version": 1,
                "operation_id": str(uuid4()),
                "space_id": str(space),
                "actor": "owner",
                "kind": "prepare_invocation",
                "invocation_id": str(uuid4()),
                "attempt_id": str(attempts["a"][0]),
                "work_id": str(a.work_id),
                "session_id": str(attempts["a"][1]),
                "purpose": "content",
                "provider": "synthetic",
                "model": "synthetic",
                "transport": "http-sse",
                "request_sha256": "D" * 64,
                "request_bytes": 12,
                "reserve_units": 10,
            },
        )
    assert read_execution(root, a.work_id, owner).invocations == ()

    # Technical copies of both Attempts go by address with their child Works.
    markers: dict[str, str] = {}
    for role in ("a", "b"):
        home = root / ".zara-core" / "pi-rpc-home" / str(attempts[role][0])
        home.mkdir(parents=True)
        markers[role] = f"synthetic managed {role} copy {uuid4()}"
        (home / "copy.txt").write_text(markers[role], encoding="utf-8", newline="\n")
    for role, work in (("a", a.work_id), ("b", b.work_id)):
        _stop(root, space, owner, work, *attempts[role])
        apply_operation(
            root,
            DeleteWorkRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                work_id=work,
                expected_revision=read_work(root, work, owner).revision,
            ),
            owner,
        )
    deleted = complete_assigned_deletions(root, owner)
    assert deleted.live_store_sanitized and deleted.pending_jobs == 0
    assert _workflows(root) == []
    for role in ("a", "b"):
        assert not (root / ".zara-core" / "pi-rpc-home" / str(attempts[role][0])).exists()
        assert not _sqlite_contains(root / ".zara-core", markers[role])
    with closing(sqlite3.connect(root / ".zara-core" / "core.sqlite3")) as connection:
        assert connection.execute("SELECT count(*) FROM execution_plan_transfers").fetchone() == (
            0,
        )
    assert read_obligation(root, parent, "b_checked", owner).status == "open"
