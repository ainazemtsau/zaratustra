"""Exact local preflight denials survive RPC without an invented model result."""

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

import pytest

import zaratustra.pi_adapter.assigned as assigned_host
from tests.zaratustra.foundation import test_workflows as core_cases
from tests.zaratustra.foundation.test_execution import invocation
from tests.zaratustra.pi_adapter.test_assigned import _valid_assigned_config
from zaratustra.foundation import (
    AdmitInvocationRequest,
    AssignAttemptRequest,
    CreateResourceRequest,
    FinishInvocationRequest,
    FoundationError,
    PublishAttemptOutputRequest,
    ResourceState,
    SendInvocationRequest,
    SourceState,
    WorkflowModel,
    WorkflowNode,
    WorkflowRequest,
    inspect_space,
    read_execution,
    read_knowledge,
    read_work,
    read_workflow_run,
)
from zaratustra.pi_adapter import Bridge, BridgeServer
from zaratustra.pi_adapter.assigned import EXECUTOR_VERSION, read_assignment_refusal
from zaratustra.pi_adapter.bridge import ProviderPreflightRefusal
from zaratustra.pi_adapter.workflows import (
    WORKER_ERROR_PREFIX,
    WorkerFailureRecord,
    _read_worker_failure,
)


def _prepared_case(tmp_path: Path) -> tuple[Any, UUID, UUID, UUID, Any]:
    case = core_cases._setup(
        tmp_path,
        (WorkflowNode(key="prepare", kind="model", instruction="Return the proposed JSON"),),
    )
    root, space, owner, activity, _, identifier = case
    core_cases._op(
        root,
        space,
        owner,
        WorkflowRequest,
        action="bind_node",
        root_work_id=identifier,
        expected_revision=read_workflow_run(root, identifier, owner).revision,
        node_key="prepare",
        model=WorkflowModel(
            provider="synthetic", model_id="synthetic", profile="local-completions", reasoning="off"
        ),
    )
    work = read_workflow_run(root, identifier, owner).nodes[0].work_id
    resource, attempt, session = uuid4(), uuid4(), uuid4()
    core_cases._op(
        root,
        space,
        owner,
        CreateResourceRequest,
        resource_id=resource,
        work_id=work,
        state=ResourceState(
            label="Fictional preflight", root=tmp_path, mode="shared", limit_units=100
        ),
    )
    core_cases._op(
        root,
        space,
        owner,
        AssignAttemptRequest,
        attempt_id=attempt,
        work_id=work,
        expected_work_revision=read_work(root, work, owner).revision,
        resource_id=resource,
        expected_resource_revision=1,
        session_id=session,
        executor_version=EXECUTOR_VERSION,
    )
    config = _valid_assigned_config(root, tmp_path, tmp_path / "runtime")
    return case, work, attempt, session, config


def _post(
    server: BridgeServer, session: UUID, endpoint: str, data: dict[str, Any]
) -> dict[str, Any]:
    request = Request(
        f"http://127.0.0.1:{server.server_port}{endpoint}",
        data=json.dumps({"session_id": str(session), **data}).encode(),
        headers={
            "Authorization": f"Bearer {server.bridge.token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read())  # type: ignore[no-any-return]
    except HTTPError as error:
        with error:
            return json.loads(error.read())  # type: ignore[no-any-return]


@pytest.mark.parametrize("code", ("permission_denied", "storage"))
def test_actual_bridge_records_only_marked_native_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    """A tool read refusal is recoverable; the same Core code at native preflight is terminal."""
    case, work, attempt, session, _ = _prepared_case(tmp_path)
    root, _, owner, activity, *_ = case
    bridge = Bridge(root, owner, tmp_path, assigned_attempt_id=attempt, assigned_session_id=session)
    bridge.connect(session)
    bridge.select(session, activity, work)
    server = BridgeServer(bridge)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def deny(*args: Any, **kwargs: Any) -> Any:
        raise FoundationError(code, "Exact Core preflight refusal")

    monkeypatch.setattr(bridge, "prepare_context", deny)
    monkeypatch.setattr(bridge, "knowledge_read", deny)
    try:
        assert (
            _post(server, session, "/v1/knowledge-read", {"provider_preflight": True})["error"]
            == code
        )
        assert bridge.provider_preflight_refusal is None
        assert _post(server, session, "/v1/context-prepare", {})["error"] == code
        assert bridge.provider_preflight_refusal is None
        result = _post(server, session, "/v1/context-prepare", {"provider_preflight": True})
        refusal = bridge.provider_preflight_refusal
        assert refusal is not None and refusal.code == code
        assert refusal.detail == result["foundation_detail"] == "Exact Core preflight refusal"
        assert refusal.attempt_id == attempt and refusal.session_id == session
        assert refusal.boundary == "context-prepare" and refusal.invocation_id is None
        before = refusal
        _post(server, uuid4(), "/v1/context-prepare", {"provider_preflight": True})
        assert bridge.provider_preflight_refusal == before
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    snapshot = read_execution(root, work, owner)
    assert not snapshot.invocations and not snapshot.outputs
    assert len(snapshot.attempts) == 1


@pytest.mark.parametrize("rpc_mask", (False, True))
def test_native_terminal_refusal_keeps_code_diagnosis_and_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rpc_mask: bool
) -> None:
    """A settled/error RPC turn must not replace a known Core refusal with rpc_result."""
    case, work, attempt, session, config = _prepared_case(tmp_path)
    root, _, owner, *_ = case
    work_ids = {
        item.record_id for item in inspect_space(root, owner).records if item.kind == "work"
    }
    servers: list[BridgeServer] = []
    actual_server = BridgeServer
    actual_popen = subprocess.Popen

    def server(bridge: Bridge) -> BridgeServer:
        result = actual_server(bridge)
        servers.append(result)
        return result

    def child(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        return actual_popen(
            [sys.executable, "-c", "import sys; sys.stdin.buffer.readline()"],
            cwd=kwargs["cwd"],
            env=kwargs["env"],
            stdin=kwargs["stdin"],
            stdout=kwargs["stdout"],
            stderr=kwargs["stderr"],
        )

    def prompt(*args: Any, **kwargs: Any) -> None:
        local = servers[-1]
        local.bridge.connect(session)
        local.bridge.select(session, case[3], work)

        def denied(*unused: Any, **options: Any) -> Any:
            raise FoundationError("trial_send_limit", "The exact Core delivery limit was reached")

        monkeypatch.setattr(local.bridge, "prepare_context", denied)
        result = _post(local, session, "/v1/context-prepare", {"provider_preflight": True})
        assert result["error"] == "trial_send_limit"
        if rpc_mask:
            raise FoundationError("rpc_extension", "Native RPC lost the structured detail")

    monkeypatch.setattr(assigned_host, "BridgeServer", server)
    monkeypatch.setattr(subprocess, "Popen", child)
    monkeypatch.setattr(assigned_host, "_rpc_prompt", prompt)
    before = read_execution(root, work, owner)
    pinned = before.attempts[0]
    with pytest.raises(FoundationError) as refused:
        assigned_host._execute_under_lock(
            config, owner, work, attempt, before.execution_epoch, pinned.generation
        )
    assert refused.value.code == "trial_send_limit"
    snapshot = read_execution(root, work, owner)
    assert not snapshot.invocations and not snapshot.outputs and snapshot.held_units == 0
    assert snapshot.assignments[0].status == "stopped"
    reason = snapshot.assignments[0].stop_reason
    assert reason is not None
    record = ProviderPreflightRefusal.model_validate_json(reason)
    assert record.diagnostic is not None
    saved = read_knowledge(root, record.diagnostic.record_id, owner).state
    assert isinstance(saved, SourceState) and saved.content is not None
    assert saved.scope_work_id == work and saved.derived_from[0].record_id == work
    assert json.loads(saved.content)["refusal"]["code"] == "trial_send_limit"
    recovered = read_assignment_refusal(root, work, attempt, owner)
    assert recovered is not None and recovered.code == "trial_send_limit"
    assert (
        str(record.diagnostic.record_id) in recovered.detail and "Traceback" not in recovered.detail
    )
    assert work_ids == {
        item.record_id for item in inspect_space(root, owner).records if item.kind == "work"
    }


def test_parent_worker_protocol_is_exact_and_does_not_parse_prose() -> None:
    """Long stderr or a different worker's error cannot become this node's cause."""
    work, attempt = uuid4(), uuid4()
    record = WorkerFailureRecord(
        work_id=work, attempt_id=attempt, code="permission_denied", detail="Exact Core cause"
    )
    prose = bytearray(b"Traceback: trial_send_limit: invented prose\n")
    assert _read_worker_failure(prose, work, attempt) is None
    tail = prose + (WORKER_ERROR_PREFIX + record.model_dump_json()).encode()
    refusal = _read_worker_failure(tail, work, attempt)
    assert refusal is not None and refusal.code == "permission_denied"
    assert refusal.detail == "Exact Core cause"
    assert _read_worker_failure(tail, uuid4(), attempt) is None


@pytest.mark.parametrize("published", (False, True))
def test_observer_preserves_exact_attempt_bases_output_and_unknown_send(
    tmp_path: Path, published: bool
) -> None:
    """A refusal neither retargets diagnosis to a newer Work nor erases previous send evidence."""
    case, work, attempt, session, config = _prepared_case(tmp_path)
    root, space, owner, *_ = case
    pinned = read_execution(root, work, owner).attempts[0]
    call, _ = invocation(root, space, work, attempt, session, owner, 9)
    common = {"invocation_id": call, "attempt_id": attempt, "work_id": work, "session_id": session}
    for kind in (AdmitInvocationRequest, SendInvocationRequest):
        core_cases._op(root, space, owner, kind, **common)
    if published:
        core_cases._op(
            root,
            space,
            owner,
            FinishInvocationRequest,
            outcome="answered",
            usage_units=2,
            **common,
        )
        core_cases._op(
            root,
            space,
            owner,
            PublishAttemptOutputRequest,
            work_id=work,
            attempt_id=attempt,
            session_id=session,
            slot="report",
            media_type="text/plain",
            content=b'{"result":"retained"}',
        )
        assert read_work(root, work, owner).revision > pinned.work_revision
    assert assigned_host._has_published_attempt_output(config, owner, work, attempt) is published
    refusal = ProviderPreflightRefusal(
        attempt_id=attempt,
        session_id=session,
        boundary="context-prepared",
        invocation_id=uuid4(),
        code="permission_denied",
        detail="Next request was refused",
    )
    saved = assigned_host._retain_preflight_diagnostic(
        config, owner, work, refusal, [], bytearray()
    )
    assert saved.diagnostic is not None
    source = read_knowledge(root, saved.diagnostic.record_id, owner).state
    assert isinstance(source, SourceState)
    assert source.derived_from[0].revision == pinned.work_revision
    assert tuple((ref.record_id, ref.revision) for ref in source.derived_from[1:]) == tuple(
        (ref.artifact_id, ref.revision)
        for ref in read_work(root, work, owner, revision=pinned.work_revision).state.inputs
    )
    assigned_host._record_stop(
        config, owner, work, attempt, session, observed=True, reason=saved.model_dump_json()
    )
    snapshot = read_execution(root, work, owner)
    assert snapshot.work.state.acceptance is None
    if published:
        assert snapshot.assignments[0].status == "stopped"
        assert snapshot.invocations[0].status == "answered" and snapshot.outputs
        assert assigned_host._has_published_attempt_output(config, owner, work, attempt)
    else:
        assert snapshot.assignments[0].status == "unknown"
        assert snapshot.invocations[0].status == "sent" and snapshot.held_units == 9
        assert not snapshot.outputs
