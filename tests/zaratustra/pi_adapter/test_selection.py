"""Ordinary native choices preserve exact old pins through stop and commit faults."""

import threading
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

import zaratustra.foundation as core
import zaratustra.pi_adapter.selection as selection_module
from tests.zaratustra.foundation.test_activity_setup_recovery import _recovery_case
from tests.zaratustra.foundation.test_conversations import _selection_transition_case
from tests.zaratustra.pi_adapter.test_child_assigned import _config
from zaratustra.pi_adapter import Bridge
from zaratustra.pi_adapter.activity_setup import SetupCoordinator
from zaratustra.pi_adapter.conversation import conversation
from zaratustra.pi_adapter.selection import transition


def _case(tmp_path: Path, *, prior_assignment: bool = False) -> tuple[Any, ...]:
    case, request, _, _ = _selection_transition_case(tmp_path, prior_assignment=prior_assignment)
    proof = request.selection_transition
    assert proof is not None
    source = core.read_knowledge(case[0], proof.observation.record_id, case[2])
    assert isinstance(source.state, core.SourceState)
    metadata = source.state.native_selection
    terminal = source.state.conversation_terminal
    assert metadata is not None and terminal is not None
    execution = core.read_execution(case[0], request.work_id, case[2])
    bridge = Bridge(case[0], case[2], execution.resources[0].state.root)
    bridge.connect(request.session_id)
    bridge.select(request.session_id, execution.work.state.activity_id, request.work_id)
    host = {key: getattr(metadata, key) for key in ("host_id", "branch_id", "generation")}
    conversation(bridge, request.session_id, {"mode": "host", **host})
    bridge.bind_request_origin(
        request.session_id,
        {"origin": "owner", "sources": [proof.owner_source.model_dump(mode="json")]},
    )
    handoff = {
        **host,
        "operation_id": str(uuid4()),
        "origin": "owner_tool",
        "owner_source": proof.owner_source.model_dump(mode="json"),
        "tool_call_id": metadata.tool_call_id,
        "tool_name": metadata.tool_name,
        "arguments_json": metadata.arguments_json,
        "departing": {
            "work_id": str(request.work_id),
            "attempt_id": str(request.attempt_id),
            "session_id": str(request.session_id),
            **{
                key: getattr(proof, key)
                for key in (
                    "execution_epoch",
                    "work_revision",
                    "attempt_revision",
                    "resource_id",
                    "resource_revision",
                )
            },
        },
        "boundary": {
            "content": (source.state.content or b"").decode(),
            "source_event_id": "adapter-native-choice",
            "conversation_terminal": {
                **terminal.model_dump(mode="json"),
                "assistant_entry_id": "adapter-native-choice",
            },
        },
    }
    return bridge, request, proof.target, handoff, host


def test_selection_receipt_precedes_new_target_and_fences_same_batch(tmp_path: Path) -> None:
    bridge, request, target, handoff, _ = _case(tmp_path)
    before = core.read_work(bridge.path, request.work_id, bridge.authority)
    result = transition(bridge, request.session_id, target, {"selection_handoff": handoff})
    old = core.read_execution(bridge.path, request.work_id, bridge.authority)
    assert old.attempts[-1].status == "interrupted"
    assert core.read_work(bridge.path, request.work_id, bridge.authority) == before
    assert bridge._selection(request.session_id).work_id == target.work_id
    assert result["receipt"]["kind"] == "stop_attempt"
    with pytest.raises(core.FoundationError, match="selection_pending"):
        bridge._require_model_effect(request.session_id)
    bridge.prepare_context(request.session_id)
    bridge._require_model_effect(request.session_id)
    destination = core.read_execution(bridge.path, target.work_id, bridge.authority)
    assert not destination.attempts and destination.work.state.acceptance is None


def test_fresh_setup_resolves_actual_graph_before_departing_stop_and_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge, request, _, handoff, _ = _case(tmp_path)
    identifier = uuid4()
    bridge.activity_setup(
        request.session_id,
        {
            "action": "begin",
            "setup_id": str(identifier),
            "activity_id": str(uuid4()),
            "title": "Fictional observations",
            "goal": "Organize observations and review them",
        },
    )
    initial = core.read_activity_setup(bridge.path, identifier, bridge.authority)
    assert initial.state.root_work_id is not None and not initial.state.stages
    controller = SetupCoordinator(
        bridge, _config(bridge.path, bridge.workspace, tmp_path / "runtime")
    )
    bridge.setup_controller = controller
    launched: list[Any] = []

    def launch(setup_id: Any, _model: Any) -> None:
        current = core.read_activity_setup(bridge.path, setup_id, bridge.authority)
        assert current.state.root_work_id == initial.state.root_work_id
        assert (
            core.read_execution(bridge.path, request.work_id, bridge.authority).attempts[-1].status
            == "interrupted"
        )
        assert bridge._session(request.session_id) is None
        assert current.state.root_work_id is not None
        target = core.read_execution(bridge.path, current.state.root_work_id, bridge.authority)
        assert not target.attempts
        launched.append(current.state.root_work_id)

    monkeypatch.setattr(controller, "start", launch)
    result = bridge.activity_setup(
        request.session_id,
        {
            "action": "submit",
            "setup_id": str(identifier),
            "selection_handoff": handoff,
            "model": {"provider": "synthetic", "id": "synthetic", "thinking": "off"},
        },
    )
    assert len(launched) == 1
    assert result["selection_transition"]["target"]["work_id"] == str(launched[0])
    assert result["selection_transition"]["target"]["mode"] == "assigned"


def test_legacy_setup_prepares_real_target_without_dispatch(tmp_path: Path) -> None:
    case = _recovery_case(tmp_path, 15)
    root, _, owner, identifier, *_ = case
    before = core.read_activity_setup(root, identifier, owner)
    assert before.state.root_work_id is None and not before.state.stages
    bridge = Bridge(root, owner, root)
    controller = SetupCoordinator(bridge, _config(root, root, tmp_path / "runtime"))
    target = controller.prepare(identifier, {"provider": "synthetic", "id": "synthetic"})
    after = core.read_activity_setup(root, identifier, owner)
    assert target == after.state.stages[-1].work_id
    assert not core.read_execution(root, target, owner).attempts
    assert controller.thread is None
    assert controller.prepare(identifier, {"provider": "synthetic", "id": "synthetic"}) == target
    assert core.read_activity_setup(root, identifier, owner) == after


def test_interview_answer_preserves_ordinary_attempt(tmp_path: Path) -> None:
    bridge, request, _, handoff, _ = _case(tmp_path)
    identifier = uuid4()
    bridge.activity_setup(
        request.session_id,
        {
            "action": "begin",
            "setup_id": str(identifier),
            "activity_id": str(uuid4()),
            "title": "Fictional observations",
            "goal": "Organize observations",
        },
    )
    before = core.read_execution(bridge.path, request.work_id, bridge.authority)
    result = bridge.activity_setup(
        request.session_id,
        {
            "action": "answer",
            "setup_id": str(identifier),
            "selection_handoff": handoff,
        },
    )
    assert result["selection_transition"]["changed"] is False
    assert result["selection_transition"]["preserve_attempt"] is True
    assert core.read_execution(bridge.path, request.work_id, bridge.authority) == before
    assert bridge._selection(request.session_id).work_id == request.work_id


def test_same_work_noop_requires_actual_resource_pin(tmp_path: Path) -> None:
    bridge, request, _, _, _ = _case(tmp_path)
    work = core.read_work(bridge.path, request.work_id, bridge.authority)
    target = core.SelectionTarget(
        mode="ordinary", work_id=work.work_id, work_revision=work.revision
    )
    before = core.read_execution(bridge.path, request.work_id, bridge.authority)
    result = transition(bridge, request.session_id, target, {})
    assert result["changed"] is False and result["preserve_attempt"] is True
    assert core.read_execution(bridge.path, request.work_id, bridge.authority) == before
    other = tmp_path / "different-root"
    other.mkdir()
    bridge.workspace = other
    with pytest.raises(core.FoundationError, match="stale_resource"):
        transition(bridge, request.session_id, target, {})
    assert core.read_execution(bridge.path, request.work_id, bridge.authority) == before


def test_stopped_assigned_history_does_not_forbid_current_ordinary_work(tmp_path: Path) -> None:
    bridge, request, _, _, _ = _case(tmp_path, prior_assignment=True)
    before = core.read_execution(bridge.path, request.work_id, bridge.authority)
    assert before.assignments and all(item.status == "stopped" for item in before.assignments)
    current = core.read_work(bridge.path, request.work_id, bridge.authority)
    result = transition(
        bridge,
        request.session_id,
        {"mode": "ordinary", "work_id": current.work_id, "work_revision": current.revision},
        {},
    )
    assert result["changed"] is False and result["preserve_attempt"] is True
    assert core.read_execution(bridge.path, request.work_id, bridge.authority) == before


def test_read_focus_preserves_execution_and_pins_exact_inspected_work(tmp_path: Path) -> None:
    bridge, request, target, _, _ = _case(tmp_path)
    before = core.read_execution(bridge.path, request.work_id, bridge.authority)
    result = bridge.snapshot(request.session_id, target.work_id)
    assert result["work"]["work_id"] == str(target.work_id)
    assert core.read_execution(bridge.path, request.work_id, bridge.authority) == before
    assert bridge._selection(request.session_id).work_id == request.work_id
    packet = bridge.prepare_context(request.session_id, inspection_work_id=target.work_id)
    focus = packet["packet"]["read_focus"]["reference"]
    assert core.KnowledgeRef.model_validate(focus) == core.KnowledgeRef(
        record_id=target.work_id, revision=target.work_revision
    )
    context = core.read_knowledge(bridge.path, UUID(str(packet["manifest_id"])), bridge.authority)
    assert isinstance(context.state, core.ContextState)
    assert core.KnowledgeRef.model_validate(focus) in context.state.mandatory
    assert context.state.work_id == request.work_id
    assert not core.read_execution(bridge.path, target.work_id, bridge.authority).attempts


def test_changed_target_refuses_before_departing_stop(tmp_path: Path) -> None:
    bridge, request, target, handoff, _ = _case(tmp_path)
    with pytest.raises(core.FoundationError, match="stale_work"):
        transition(
            bridge,
            request.session_id,
            target.model_copy(update={"work_revision": 99}),
            {"selection_handoff": handoff},
        )
    assert (
        core.read_execution(bridge.path, request.work_id, bridge.authority).attempts[-1].status
        == "active"
    )
    assert bridge._selection(request.session_id).work_id == request.work_id


def test_target_change_after_stop_retains_pending_without_committing_new_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge, request, target, handoff, _ = _case(tmp_path)
    original = core.apply_operation

    def close_after_stop(path: Path, operation: Any, authority: Any) -> Any:
        receipt = original(path, operation, authority)
        if isinstance(operation, core.StopAttemptRequest):
            assert target.work_id is not None and target.work_revision is not None
            original(
                path,
                core.CloseWorkRequest(
                    operation_id=uuid4(),
                    space_id=authority.space_id,
                    actor=authority.actor,
                    work_id=target.work_id,
                    expected_revision=target.work_revision,
                    outcome="cancelled",
                    basis="Independent fictional owner change",
                ),
                authority,
            )
        return receipt

    monkeypatch.setattr(selection_module, "apply_operation", close_after_stop)
    with pytest.raises(core.FoundationError, match="stale_work"):
        transition(bridge, request.session_id, target, {"selection_handoff": handoff})
    assert (
        core.read_execution(bridge.path, request.work_id, bridge.authority).attempts[-1].status
        == "interrupted"
    )
    assert bridge._session(request.session_id) is None
    assert bridge.pending_selections[request.session_id]["target"] == target.model_dump(mode="json")
    destination = core.read_execution(bridge.path, target.work_id, bridge.authority)
    assert destination.work.state.status == "cancelled" and not destination.attempts


def test_host_registration_cannot_supersede_guarded_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge, request, target, handoff, host = _case(tmp_path)
    stopping, registering, registered = (threading.Event() for _ in range(3))
    failures: list[BaseException] = []
    original = core.apply_operation

    def register() -> None:
        try:
            assert stopping.wait(5)
            registering.set()
            conversation(
                bridge,
                request.session_id,
                {"mode": "host", **host, "generation": int(host["generation"]) + 1},
            )
            registered.set()
        except BaseException as error:
            failures.append(error)

    def guarded(path: Path, operation: Any, authority: Any) -> Any:
        if isinstance(operation, core.StopAttemptRequest):
            stopping.set()
            assert registering.wait(5)
            assert not registered.is_set()
            assert bridge.conversation_hosts[request.session_id]["generation"] == str(
                host["generation"]
            )
        return original(path, operation, authority)

    monkeypatch.setattr(selection_module, "apply_operation", guarded)
    worker = threading.Thread(target=register)
    worker.start()
    try:
        transition(bridge, request.session_id, target, {"selection_handoff": handoff})
    finally:
        stopping.set()
        worker.join(5)
    assert not worker.is_alive() and not failures and registered.is_set()
    assert (
        core.read_execution(bridge.path, request.work_id, bridge.authority).attempts[-1].status
        == "interrupted"
    )
    assert bridge.request_origins[request.session_id] == "history"


def test_commit_failure_reopens_passively_and_reuses_exact_stop_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge, request, target, handoff, _ = _case(tmp_path)

    def fail_commit(*_args: Any) -> None:
        raise core.FoundationError("resource_unavailable", "Fictional target commit failed")

    monkeypatch.setattr(bridge, "select", fail_commit)
    with pytest.raises(core.FoundationError, match="resource_unavailable"):
        transition(bridge, request.session_id, target, {"selection_handoff": handoff})
    before = core.read_execution(bridge.path, request.work_id, bridge.authority)
    assert before.attempts[-1].status == "interrupted"
    assert bridge._session(request.session_id) is None
    pending = bridge.pending_selections[request.session_id]
    reopened = Bridge(bridge.path, bridge.authority, bridge.workspace)
    session = uuid4()
    reopened.connect(session)
    host = {"host_id": "reopened", "branch_id": "reopened-branch", "generation": 2}
    conversation(reopened, session, {"mode": "host", **host})
    conversation(reopened, session, {"mode": "selection_restore", **host, "pending": pending})
    assert core.read_execution(bridge.path, request.work_id, bridge.authority) == before
    with pytest.raises(core.FoundationError, match="delivered owner"):
        conversation(
            reopened,
            session,
            {"mode": "continue_selection", **host, "pending_id": handoff["operation_id"]},
        )
    owner = reopened.capture_source(
        session,
        channel="conversation_user",
        content="Continue my choice",
        source_event_id="native:new-choice",
        input_source="interactive",
    )["source_ref"]
    reopened.bind_request_origin(
        session, {"origin": "owner", "sources": [owner], "fresh_owner": True}
    )
    result = conversation(
        reopened,
        session,
        {"mode": "continue_selection", **host, "pending_id": handoff["operation_id"]},
    )
    selected = result["selection"]
    assert isinstance(selected, dict) and selected["work_id"] == str(target.work_id)
    assert core.read_execution(bridge.path, request.work_id, bridge.authority) == before
    assert not reopened.pending_selections


@pytest.mark.parametrize("stopped", [False, True])
def test_cancel_retained_choice_does_not_dispatch_or_reactivate_old_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stopped: bool
) -> None:
    bridge, request, target, handoff, host = _case(tmp_path)
    pending = {"handoff": handoff, "target": target.model_dump(mode="json")}
    if stopped:

        def fail_commit(*_args: Any) -> None:
            raise core.FoundationError("resource_unavailable", "Commit failed")

        monkeypatch.setattr(bridge, "select", fail_commit)
        with pytest.raises(core.FoundationError, match="resource_unavailable"):
            transition(bridge, request.session_id, target, {"selection_handoff": handoff})
    before = core.read_execution(bridge.path, request.work_id, bridge.authority)
    conversation(
        bridge, request.session_id, {"mode": "selection_restore", **host, "pending": pending}
    )
    result = conversation(
        bridge,
        request.session_id,
        {"mode": "cancel_selection", **host, "pending_id": handoff["operation_id"]},
    )
    assert result["cancelled"] is True and result["selection"] is None
    assert core.read_execution(bridge.path, request.work_id, bridge.authority) == before
    assert not core.read_execution(bridge.path, target.work_id, bridge.authority).attempts
    assert (result["recovery_obstacle"] is None) is stopped
    reopened = Bridge(bridge.path, bridge.authority, bridge.workspace)
    session = uuid4()
    reopened.connect(session)
    current_host = {**host, "branch_id": "reopened", "generation": 2}
    conversation(reopened, session, {"mode": "host", **current_host})
    if result["recovery_obstacle"] is not None:
        restored = conversation(
            reopened,
            session,
            {
                "mode": "selection_recovery",
                **current_host,
                "departing": result["recovery_obstacle"],
            },
        )
        assert restored["recovery_obstacle"] == handoff["departing"]
        packet = reopened.prepare_context(session)["packet"]
        assert isinstance(packet, dict)
        assert packet["recovery_obstacle"]["work_id"] == str(request.work_id)
    else:
        assert not reopened.recovery_obstacles
    assert reopened._session(session) is None
    assert core.read_execution(bridge.path, request.work_id, bridge.authority) == before
