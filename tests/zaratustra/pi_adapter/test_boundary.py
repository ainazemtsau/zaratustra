"""Foreground observation returns saved boundaries without joining execution."""

import threading
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

import zaratustra.foundation as core
from tests.zaratustra.foundation import test_activity_setup as setup_cases
from tests.zaratustra.foundation import test_workflows as workflow_cases
from tests.zaratustra.pi_adapter.test_child_assigned import _config
from zaratustra.foundation import FoundationError, WorkflowNode, read_activity_setup, read_space
from zaratustra.pi_adapter import Bridge
from zaratustra.pi_adapter.__main__ import _prepare_space
from zaratustra.pi_adapter.activity_setup import SetupCoordinator
from zaratustra.pi_adapter.boundary import ProcessTarget, read_process_boundary
from zaratustra.pi_adapter.conversation import conversation
from zaratustra.pi_adapter.workflows import WorkflowCoordinator


def _setup(tmp_path: Path) -> tuple[Any, Bridge, UUID, dict[str, Any]]:
    case = setup_cases._case(tmp_path)
    root, _, owner, setup, *_ = case
    _prepare_space(root, owner.actor, create=False, upgrade_existing=True)
    bridge, session = Bridge(root, owner, root), uuid4()
    bridge.connect(session)
    conversation(
        bridge,
        session,
        {"mode": "host", "host_id": "foreground", "branch_id": "initial", "generation": 1},
    )
    raw = {
        "target": {"kind": "setup", "id": str(setup)},
        "operation_key": "native-call-one",
        "generation": 1,
        "timeout_seconds": 0,
    }
    return case, bridge, session, raw


def test_saved_setup_question_returns_without_executor_or_new_send(tmp_path: Path) -> None:
    case, bridge, session, raw = _setup(tmp_path)
    setup_cases._step(case, "question", text="Which observation period?")
    before = read_activity_setup(bridge.path, case[3], bridge.authority)
    boundary = bridge.process_boundary(session, raw)
    assert boundary["kind"] == "question"
    assert boundary["details"]["questions"][0]["question"] == "Which observation period?"
    assert boundary["execution"]["alive"] is False
    assert boundary["lease_token"] is not None
    assert read_activity_setup(bridge.path, case[3], bridge.authority) == before


def test_legacy_setup_host_observation_needs_no_schema_or_protocol_upgrade(tmp_path: Path) -> None:
    case = setup_cases._case(tmp_path)
    root, _, owner, setup, *_ = case
    setup_cases._step(case, "question", text="Which period?")
    bridge, session = Bridge(root, owner, root), uuid4()
    bridge.connect(session)
    before = read_space(root)
    conversation(
        bridge,
        session,
        {"mode": "host", "host_id": "legacy", "branch_id": "branch", "generation": 1},
    )
    boundary = bridge.process_boundary(
        session,
        {
            "target": {"kind": "setup", "id": str(setup)},
            "operation_key": "legacy-call",
            "generation": 1,
            "timeout_seconds": 0,
        },
    )
    assert boundary["kind"] == "question" and boundary["action"] is None
    assert read_space(root) == before and before.schema_version == 14


def test_absent_executor_returns_saved_stop_instead_of_unbounded_wait(tmp_path: Path) -> None:
    case, bridge, session, raw = _setup(tmp_path)
    setup_cases._step(
        case, "start_stage", stage_kind="draft", stage_instruction="Prepare structure"
    )
    boundary = bridge.process_boundary(session, raw)
    assert boundary["kind"] == "stopped"
    assert boundary["execution"]["reason"] == "executor_absent"
    assert boundary["execution"]["unresolved_invocations"] == []


@pytest.mark.parametrize("alive", [False, True])
def test_unknown_send_is_an_obstacle_even_with_live_executor(
    tmp_path: Path,
    alive: bool,
) -> None:
    case, bridge, session, raw = _setup(tmp_path)
    setup_cases._step(
        case, "start_stage", stage_kind="draft", stage_instruction="Prepare structure"
    )
    stage = read_activity_setup(bridge.path, case[3], bridge.authority).state.stages[-1]
    bridge.select(session, case[4], stage.work_id)
    attempt = bridge.start_attempt(session, interrupt_previous=False)["attempt_id"]
    common = {
        "attempt_id": attempt,
        "work_id": str(stage.work_id),
        "session_id": str(session),
        "invocation_id": str(uuid4()),
    }
    for kind in ("prepare_invocation", "admit_invocation", "send_invocation", "finish_invocation"):
        bridge.operation(
            session,
            {
                "kind": kind,
                "operation_id": str(uuid4()),
                "actor": bridge.authority.actor,
                "space_id": str(bridge.authority.space_id),
                **common,
                **(
                    {
                        "purpose": "content",
                        "provider": "fictional",
                        "model": "fictional",
                        "transport": "local",
                        "request_sha256": "A" * 64,
                        "request_bytes": 100,
                        "reserve_units": 1,
                    }
                    if kind == "prepare_invocation"
                    else {}
                ),
                **({"outcome": "unknown"} if kind == "finish_invocation" else {}),
            },
        )
    release = threading.Event()
    controller = SetupCoordinator(bridge, _config(bridge.path, bridge.path, tmp_path / "runtime"))
    controller.active = case[3]
    controller.thread = threading.Thread(target=lambda: release.wait(timeout=10))
    bridge.setup_controller = controller
    if alive:
        controller.thread.start()
    before = core.read_execution(bridge.path, stage.work_id, bridge.authority)
    try:
        boundary = bridge.process_boundary(session, raw)
        assert boundary["kind"] == "attention"
        assert boundary["execution"]["reason"] == "unresolved_execution"
        assert boundary["execution"]["unknown"] is True
        assert core.read_execution(bridge.path, stage.work_id, bridge.authority) == before
    finally:
        release.set()
        if alive:
            controller.thread.join(timeout=5)


def test_observation_identity_fences_retarget_and_replaced_branch(tmp_path: Path) -> None:
    _, bridge, session, raw = _setup(tmp_path)
    captured = bridge.process_boundary(session, raw)
    with pytest.raises(FoundationError, match="different process"):
        bridge.process_boundary(session, {**raw, "target": {"kind": "setup", "id": str(uuid4())}})
    conversation(
        bridge,
        session,
        {"mode": "host", "host_id": "foreground", "branch_id": "replacement", "generation": 2},
    )
    with pytest.raises(FoundationError, match="branch changed"):
        bridge.process_boundary(
            session, {**raw, "mode": "pause", "lease_token": captured["lease_token"]}
        )


def test_pause_records_stop_without_joining_live_worker(tmp_path: Path) -> None:
    case, bridge, session, raw = _setup(tmp_path)
    setup_cases._step(
        case, "start_stage", stage_kind="draft", stage_instruction="Prepare structure"
    )
    controller = SetupCoordinator(bridge, _config(bridge.path, bridge.path, tmp_path / "runtime"))
    release, entered = threading.Event(), threading.Event()

    def wait() -> None:
        entered.set()
        assert release.wait(timeout=10)

    controller.active = case[3]
    controller.thread = threading.Thread(target=wait)
    bridge.setup_controller = controller
    controller.thread.start()
    assert entered.wait(timeout=5)
    try:
        captured = bridge.process_boundary(session, raw)
        assert captured["kind"] == "running"
        paused = bridge.process_boundary(
            session, {**raw, "mode": "pause", "lease_token": captured["lease_token"]}
        )
        assert controller.thread.is_alive()
        assert paused["kind"] == "paused" and paused["execution"]["stop_requested"] is True
        assert read_activity_setup(bridge.path, case[3], bridge.authority).state.phase == "paused"
    finally:
        release.set()
        controller.thread.join(timeout=5)


def test_just_started_setup_remains_running_before_first_stage_commit(tmp_path: Path) -> None:
    case, bridge, session, raw = _setup(tmp_path)
    controller = SetupCoordinator(bridge, _config(bridge.path, bridge.path, tmp_path / "runtime"))
    release, entered = threading.Event(), threading.Event()

    def prepare() -> None:
        entered.set()
        assert release.wait(timeout=10)

    controller.active = case[3]
    controller.thread = threading.Thread(target=prepare)
    bridge.setup_controller = controller
    controller.thread.start()
    assert entered.wait(timeout=5)
    try:
        boundary = bridge.process_boundary(session, raw)
        assert boundary["details"]["state"]["phase"] == "collecting"
        assert boundary["execution"]["alive"] is True
        assert boundary["kind"] == "running"
    finally:
        release.set()
        controller.thread.join(timeout=5)


def test_terminal_executor_witness_precedes_authoritative_core_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, bridge, session, raw = _setup(tmp_path)
    setup_cases._step(
        case, "start_stage", stage_kind="draft", stage_instruction="Prepare structure"
    )
    controller = SetupCoordinator(bridge, _config(bridge.path, bridge.path, tmp_path / "runtime"))
    controller.active, controller.thread = case[3], threading.Thread(target=lambda: None)
    bridge.setup_controller = controller
    witnessed = False

    def completed() -> bool:
        nonlocal witnessed
        if not witnessed:
            setup_cases._step(case, "pause", text="Committed executor boundary")
            witnessed = True
        return False

    monkeypatch.setattr(controller.thread, "is_alive", completed)
    boundary = bridge.process_boundary(session, raw)
    assert witnessed
    assert boundary["kind"] == "paused"
    assert boundary["details"]["state"]["phase"] == "paused"
    assert (
        boundary["revision"] == read_activity_setup(bridge.path, case[3], bridge.authority).revision
    )


def test_late_pause_cannot_stop_new_execution_of_same_process(tmp_path: Path) -> None:
    case, bridge, session, raw = _setup(tmp_path)
    controller = SetupCoordinator(bridge, _config(bridge.path, bridge.path, tmp_path / "runtime"))
    controller.active = case[3]
    controller.thread = threading.Thread(target=lambda: None)
    bridge.setup_controller = controller
    captured = bridge.process_boundary(session, raw)
    controller.thread = threading.Thread(target=lambda: None)
    with pytest.raises(FoundationError, match="later execution"):
        bridge.process_boundary(
            session, {**raw, "mode": "pause", "lease_token": captured["lease_token"]}
        )
    assert controller.stop.is_set() is False
    assert read_activity_setup(bridge.path, case[3], bridge.authority).state.phase == "collecting"


def test_workflow_question_returns_while_controller_thread_is_alive(tmp_path: Path) -> None:
    case = workflow_cases._setup(
        tmp_path, (WorkflowNode(key="period", kind="question", instruction="Choose period"),)
    )
    root, _, owner, _, _, run = case
    _prepare_space(root, owner.actor, create=False, upgrade_existing=True)
    workflow_cases._step(case, "ask", node_key="period", question="Which period?", purpose="Review")
    bridge = Bridge(root, owner, root)
    controller = WorkflowCoordinator(bridge, _config(root, root, tmp_path / "runtime"))
    release = threading.Event()
    controller.active = run
    controller.thread = threading.Thread(target=lambda: release.wait(timeout=10))
    bridge.workflow_controller = controller
    controller.thread.start()
    try:
        boundary = read_process_boundary(bridge, ProcessTarget(kind="workflow", id=run))
        assert boundary.kind == "question" and boundary.execution["alive"] is True
        assert boundary.details["questions"][0]["question"] == "Which period?"
        assert controller.stop.is_set() is False
    finally:
        release.set()
        controller.thread.join(timeout=5)


@pytest.mark.parametrize("timeout", [-1, 21])
def test_observation_refuses_unbounded_or_negative_windows(tmp_path: Path, timeout: int) -> None:
    _, bridge, session, raw = _setup(tmp_path)
    with pytest.raises(FoundationError, match="bounded observation"):
        bridge.process_boundary(session, {**raw, "timeout_seconds": timeout})
