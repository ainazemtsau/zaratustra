"""The local bridge preserves proposal, explicit acceptance and restart reads."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4, uuid5

import pytest

from tests.zaratustra.foundation.test_activity_setup import _case, _step
from tests.zaratustra.foundation.test_activity_structures import _activate, _structured_case
from tests.zaratustra.foundation.test_execution import InvocationFields, ready
from tests.zaratustra.foundation.test_memory import note
from tests.zaratustra.foundation.test_workflows import _raw_node_result, _setup
from zaratustra.foundation import (
    ActivityState,
    AdmitInvocationRequest,
    ArtifactRef,
    AssignAttemptRequest,
    CreateActivityRequest,
    CreateArtifactRequest,
    CreateGrantRequest,
    CreateKnowledgeRequest,
    CreateResourceRequest,
    CreateWorkRequest,
    DataOutputEnvelope,
    DeleteWorkRequest,
    FinishInvocationRequest,
    FoundationError,
    GrantState,
    KnowledgeRef,
    LinkedOutput,
    LinkWorkOutputRequest,
    OutputContract,
    PrepareInvocationRequest,
    PublishAttemptOutputRequest,
    RecordAttemptStopRequest,
    ResourceState,
    SendInvocationRequest,
    SourceState,
    StopAttemptRequest,
    WorkflowNode,
    WorkState,
    apply_operation,
    authorize_local,
    complete_deletions,
    managed_pi_lock,
    managed_pi_sessions,
    read_activity_setup,
    read_artifact,
    read_execution,
    read_knowledge,
    read_work,
    start_procedure,
)
from zaratustra.pi_adapter import Bridge, BridgeServer


def _typed_publication_bridge(tmp_path: Path) -> tuple[Bridge, UUID, UUID]:
    case = _structured_case(tmp_path)
    root, _, owner, _, activity, *_ = case
    _activate(case)
    run = start_procedure(root, owner, activity, "observe", "typed-output-contract")
    work_id, session = UUID(str(run["work_id"])), uuid4()
    bridge = Bridge(root, owner, root)
    bridge.connect(session)
    bridge.select(session, activity, work_id)
    attempt = UUID(cast(str, bridge.start_attempt(session, interrupt_previous=False)["attempt_id"]))
    common: InvocationFields = {
        "invocation_id": uuid4(),
        "attempt_id": attempt,
        "work_id": work_id,
        "session_id": session,
    }
    for request in (
        PrepareInvocationRequest(
            operation_id=uuid4(),
            space_id=bridge.authority.space_id,
            actor=owner.actor,
            purpose="content",
            provider="local",
            model="fictional",
            transport="http-sse",
            request_sha256="A" * 64,
            request_bytes=123,
            reserve_units=10,
            **common,
        ),
        AdmitInvocationRequest(
            operation_id=uuid4(), space_id=bridge.authority.space_id, actor=owner.actor, **common
        ),
        SendInvocationRequest(
            operation_id=uuid4(), space_id=bridge.authority.space_id, actor=owner.actor, **common
        ),
        FinishInvocationRequest(
            operation_id=uuid4(),
            space_id=bridge.authority.space_id,
            actor=owner.actor,
            outcome="answered",
            usage_units=1,
            **common,
        ),
    ):
        bridge.operation(session, request.model_dump(mode="json"))
    return bridge, session, attempt


def test_selected_work_snapshot_and_packet_supply_the_exact_publication_contract(
    tmp_path: Path,
) -> None:
    bridge, session, _ = _typed_publication_bridge(tmp_path)
    snapshot = bridge.snapshot(session)
    contracts = cast(list[dict[str, Any]], snapshot["output_publication_contracts"])
    assert len(contracts) == 1 and contracts[0]["slot"] == "result"
    schema = contracts[0]["content_schema"]
    assert schema == DataOutputEnvelope.model_json_schema()
    assert schema["properties"]["result"]["type"] == "string"
    assert schema["additionalProperties"] is False
    packet = cast(dict[str, Any], bridge.prepare_context(session, "content")["packet"])
    assert packet["output_publication_contracts"] == snapshot["output_publication_contracts"]
    assert packet["procedure"]["snapshot"] is not None
    assert contracts[0]["allow_incomplete"] is True
    assert contracts[0]["technical_requirements"]


@pytest.mark.parametrize("extra_kind", (False, True))
def test_actual_http_preserves_typed_publication_diagnostics_without_effects(
    tmp_path: Path, extra_kind: bool
) -> None:
    """The real-trial object result is rejected with an addressable field cause."""
    bridge, session, attempt = _typed_publication_bridge(tmp_path)
    selected = bridge.sessions[session]
    assert selected is not None
    before = read_execution(bridge.path, selected.work_id, bridge.authority)
    body = '{"entries":[],"complete":true,"result":{"value":"1.25"}}'
    if extra_kind:
        body = '{"kind":"data_output_envelope",' + body[1:]
    server = BridgeServer(bridge)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = Request(
        f"http://127.0.0.1:{server.server_port}/v1/publish",
        data=json.dumps(
            {
                "session_id": str(session),
                "attempt_id": str(attempt),
                "slot": "result",
                "media_type": "application/json",
                "content": body,
            }
        ).encode("utf-8"),
        headers={"Authorization": f"Bearer {bridge.token}", "Content-Type": "application/json"},
    )
    try:
        with pytest.raises(HTTPError) as failure:
            urlopen(request, timeout=5)
        with failure.value:
            error = json.loads(failure.value.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert error["error"] == "invalid_output"
    issues = {(issue["code"], tuple(issue["path"])) for issue in error["validation_issues"]}
    assert ("string_type", ("result",)) in issues
    assert (("extra_forbidden", ("kind",)) in issues) is extra_kind
    assert all("input" not in issue for issue in error["validation_issues"])
    assert read_execution(bridge.path, selected.work_id, bridge.authority) == before


def _status_case(tmp_path: Path, target: str) -> tuple[Bridge, UUID, dict[str, Any]]:
    if target == "setup":
        case = _case(tmp_path)
        root, _, owner, identifier, *_ = case
        _step(case, "start_stage", stage_kind="draft", stage_instruction="Keep exact inputs")
        query = {"action": "status", "setup_id": str(identifier)}
    else:
        workflow_case = _setup(
            tmp_path,
            (WorkflowNode(key="summarize", kind="model", instruction="Summarize observations"),),
        )
        root, _, owner, _, _, identifier = workflow_case
        _raw_node_result(
            workflow_case, "summarize", b'{"outcome":"result","values":{"kept":"confirmed"}}'
        )
        query = {"mode": target, "root_work_id": str(identifier)}
    bridge = Bridge(root, owner, root)
    session = uuid4()
    bridge.connect(session)
    return bridge, session, query


def _read_status(bridge: Bridge, session: UUID, query: dict[str, Any]) -> dict[str, Any]:
    return (
        bridge.activity_setup(session, query)
        if "setup_id" in query
        else bridge.workflow(session, query)
    )


@pytest.mark.parametrize("target", ("status", "explain", "setup"))
@pytest.mark.parametrize("transient", (True, False))
def test_status_recovers_read_lock_without_starting_or_changing_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, transient: bool
) -> None:
    """A real SQLite holder must not turn status reads into lost work or model replay."""
    import sqlite3
    import threading

    from zaratustra.foundation.storage import _identity_read, layout, space_connection

    bridge, session, query = _status_case(tmp_path, target)
    expected = _read_status(bridge, session, query)

    def accounting() -> tuple[int, int, int]:
        with space_connection(bridge.path) as (connection, info):
            return (
                info.state_revision,
                connection.execute("SELECT count(*) FROM operations").fetchone()[0],
                connection.execute("SELECT count(*) FROM execution_invocations").fetchone()[0],
            )

    before = accounting()
    database = layout(bridge.path)[1]
    locked, release = threading.Event(), threading.Event()
    holder_errors: list[Exception] = []

    def hold() -> None:
        try:
            connection = sqlite3.connect(database, autocommit=True, timeout=0.25)
            try:
                assert connection.execute("PRAGMA locking_mode=EXCLUSIVE").fetchone() == (
                    "exclusive",
                )
                connection.execute("BEGIN EXCLUSIVE")
                connection.execute("SELECT count(*) FROM spaces").fetchone()
                locked.set()
                assert release.wait(timeout=15)
                connection.execute("ROLLBACK")
            finally:
                connection.close()
        except Exception as error:
            holder_errors.append(error)
            locked.set()

    thread = threading.Thread(target=hold)
    thread.start()
    failures: list[FoundationError] = []

    def observed_identity(
        connection: sqlite3.Connection, statement: str, label: str
    ) -> list[tuple[Any, ...]]:
        try:
            return _identity_read(connection, statement, label)
        except FoundationError as error:
            failures.append(error)
            assert label == "application_id" and isinstance(error.__cause__, sqlite3.Error)
            assert error.__cause__.sqlite_errorcode == sqlite3.SQLITE_BUSY
            if transient:
                release.set()
                thread.join(timeout=3)
                assert not thread.is_alive()
            raise

    try:
        assert locked.wait(timeout=3) and not holder_errors
        with monkeypatch.context() as observation:
            observation.setattr("zaratustra.foundation.storage._identity_read", observed_identity)
            if transient:
                assert _read_status(bridge, session, query) == expected
                assert len(failures) == 1
            else:
                with pytest.raises(FoundationError) as refused:
                    _read_status(bridge, session, query)
                assert len(failures) == 3 and refused.value is failures[-1]
                assert refused.value.code == "storage"
                assert "application_id (SQLITE_BUSY)" in refused.value.detail
    finally:
        release.set()
        thread.join(timeout=3)
    assert not thread.is_alive() and not holder_errors
    assert accounting() == before and before[2] == 0
    assert _read_status(bridge, session, query) == expected
    assert bridge.setup_controller is None and bridge.workflow_controller is None


@pytest.mark.parametrize("target", ("status", "explain", "setup"))
def test_status_permission_refusal_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    """The read retry never overrides current rights or disguises their refusal."""
    import zaratustra.pi_adapter.bridge as bridge_module
    import zaratustra.pi_adapter.workflows as workflows_module

    bridge, session, query = _status_case(tmp_path, target)
    bridge.authority = authorize_local(
        bridge.path, actor="ungranted-observer", source_ref="fictional-observer"
    )
    calls = 0
    module = bridge_module if target == "setup" else workflows_module
    name = "read_activity_setup" if target == "setup" else "workflow_view"
    original = getattr(module, name)

    def observed(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(module, name, observed)
    with pytest.raises(FoundationError) as refused:
        _read_status(bridge, session, query)
    assert refused.value.code == "permission_denied" and calls == 1


@pytest.mark.parametrize("target", ("status", "explain", "setup"))
@pytest.mark.parametrize("transient", (True, False))
def test_status_retries_typed_begin_busy_before_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, transient: bool
) -> None:
    """Core's stable BEGIN refusal does not need the word locked to recover a pure read."""
    import sqlite3

    from zaratustra.foundation.storage import _begin, space_connection

    bridge, session, query = _status_case(tmp_path, target)
    expected = _read_status(bridge, session, query)

    def accounting() -> tuple[int, int, int]:
        with space_connection(bridge.path) as (connection, info):
            return (
                info.state_revision,
                connection.execute("SELECT count(*) FROM operations").fetchone()[0],
                connection.execute("SELECT count(*) FROM execution_invocations").fetchone()[0],
            )

    before = accounting()
    failures: list[FoundationError] = []
    admitted = 0

    def exhausted_begin(connection: sqlite3.Connection, *, writable: bool) -> None:
        nonlocal admitted
        assert not writable and not connection.in_transaction
        if not failures or not transient:
            error = FoundationError("busy", "SQLite write/read boundary remained busy")
            failures.append(error)
            raise error
        admitted += 1
        _begin(connection, writable=writable)

    with monkeypatch.context() as observation:
        observation.setattr("zaratustra.foundation.storage._begin", exhausted_begin)
        if transient:
            assert _read_status(bridge, session, query) == expected
            assert len(failures) == 1 and admitted >= 1
        else:
            with pytest.raises(FoundationError) as refused:
                _read_status(bridge, session, query)
            assert len(failures) == 3 and admitted == 0
            assert refused.value is failures[-1] and refused.value.code == "busy"
    assert accounting() == before and before[2] == 0
    assert _read_status(bridge, session, query) == expected
    assert bridge.setup_controller is None and bridge.workflow_controller is None


@pytest.mark.parametrize(
    "detail,retry",
    (
        ("SQLite identity failed (SQLITE_BUSY): unavailable", True),
        ("SQLite identity failed (SQLITE_LOCKED): unavailable", True),
        ("SQLite read failed (SQLITE_IOERR): unavailable", False),
    ),
)
def test_status_storage_recovery_keeps_non_contention_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, detail: str, retry: bool
) -> None:
    """Only recognized SQLite contention permits another read, not arbitrary storage errors."""
    import zaratustra.pi_adapter.workflows as workflows_module

    bridge, session, query = _status_case(tmp_path, "status")
    expected = _read_status(bridge, session, query)
    original = workflows_module.workflow_view
    failure = FoundationError("storage", detail)
    calls = 0

    def interrupted(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise failure
        return original(*args, **kwargs)

    monkeypatch.setattr(workflows_module, "workflow_view", interrupted)
    if retry:
        assert _read_status(bridge, session, query) == expected and calls == 2
    else:
        with pytest.raises(FoundationError) as refused:
            _read_status(bridge, session, query)
        assert refused.value is failure and calls == 1


def test_exact_open_window_is_not_authority_for_unread_original(tmp_path: Path) -> None:
    """Risk: fragment exposure silently authorizes the rest of the source."""
    case = _case(tmp_path)
    root, space, owner, setup, *_ = case
    source = note(root, space, owner, "абв\nprivate unread suffix")
    bridge = Bridge(root, owner, root)
    session = uuid4()
    bridge.connect(session)
    bridge.knowledge_read(session, {"mode": "search", "query": "private"})
    assert KnowledgeRef(record_id=source, revision=1) not in bridge.exposed_refs.get(session, set())
    result = bridge.knowledge_read(
        session, {"mode": "open", "record_id": str(source), "max_bytes": 5}
    )
    exposed = KnowledgeRef.model_validate(cast(list[Any], result["exposed"])[0])
    assert exposed.start == 0 and exposed.end == 4
    with pytest.raises(FoundationError) as error:
        bridge.activity_setup(
            session,
            {
                "action": "attach_sources",
                "setup_id": str(setup),
                "source_refs": [{"record_id": str(source), "revision": 1}],
            },
        )
    assert error.value.code == "permission_denied"
    result = bridge.activity_setup(
        session,
        {
            "action": "attach_sources",
            "setup_id": str(setup),
            "source_refs": [exposed.model_dump(mode="json")],
        },
    )
    assert exposed in read_activity_setup(root, setup, owner).state.sources
    assert cast(dict[str, Any], result["state"])["phase"] == "collecting"


def test_repeated_answer_can_attach_sources_without_erasing_question(tmp_path: Path) -> None:
    """Risk: repeated answer drops new bases or erases a pending question."""
    case = _case(tmp_path)
    root, space, owner, setup, *_ = case
    bridge = Bridge(root, owner, root)
    session = uuid4()
    bridge.connect(session)
    bridge.capture_source(
        session,
        channel="conversation_user",
        content="Use monthly summaries",
        source_event_id="answer-one",
        input_source="interactive",
    )
    bridge.activity_setup(session, {"action": "answer", "setup_id": str(setup)})
    _step(case, "question", text="Which start date?")
    source = note(root, space, owner, "Existing confirmed calendar")
    bridge.knowledge_read(session, {"mode": "open", "record_id": str(source)})
    bridge.activity_setup(
        session,
        {
            "action": "answer",
            "setup_id": str(setup),
            "source_refs": [{"record_id": str(source), "revision": 1}],
        },
    )
    current = read_activity_setup(root, setup, owner).state
    assert KnowledgeRef(record_id=source, revision=1) in current.sources
    assert current.question == "Which start date?" and current.phase == "needs_input"


def test_begin_keeps_exact_original_request_fragment_after_later_message(tmp_path: Path) -> None:
    """An exposed fragment can anchor creation; its unread suffix remains unselected."""
    root, _, owner, *_ = _case(tmp_path)
    bridge = Bridge(root, owner, root)
    session = uuid4()
    bridge.connect(session)
    bridge.capture_source(
        session,
        channel="conversation_user",
        content="Create a learning activity; unread private suffix",
        source_event_id="original-goal",
        input_source="rpc",
    )
    original = bridge.last_sources[session]
    bridge.capture_source(
        session,
        channel="conversation_user",
        content="Explain the next step",
        source_event_id="later-message",
        input_source="rpc",
    )
    opened = bridge.knowledge_read(
        session, {"mode": "open", "record_id": str(original.record_id), "max_bytes": 26}
    )
    exposed = cast(list[Any], opened["exposed"])[0]
    setup = uuid4()
    bridge.activity_setup(
        session,
        {
            "action": "begin",
            "setup_id": str(setup),
            "activity_id": str(uuid4()),
            "title": "Learning",
            "goal": "Learn consistently",
            "request_source": exposed,
        },
    )
    sources = read_activity_setup(root, setup, owner).state.sources
    assert KnowledgeRef.model_validate(exposed) in sources
    assert original not in sources
    anchor = next(ref for ref in sources if ref.record_id == original.record_id)
    assert anchor.start == 0 and anchor.end == 26


def test_retained_file_has_honest_origin_and_addressed_packet_read(tmp_path: Path) -> None:
    """Risk: file receipts imply exposure or allow unrelated Artifact reads."""
    import base64
    import hashlib

    case = _case(tmp_path)
    root, _, owner, setup, *_ = case
    bridge = Bridge(root, owner, root)
    session = uuid4()
    bridge.connect(session)
    bridge.capture_source(
        session,
        channel="conversation_user",
        content="Use the selected original",
        source_event_id="file-request",
        input_source="interactive",
    )
    content = "Original вымышленный материал".encode()
    payload = {
        "action": "retain_file",
        "setup_id": str(setup),
        "operation_key": "file-one",
        "locator": "selected-original.txt",
        "content_base64": base64.b64encode(content).decode(),
        "content_sha256": hashlib.sha256(content).hexdigest(),
    }
    retained = bridge.activity_setup(session, payload)
    assert bridge.activity_setup(session, payload) == retained
    reference = KnowledgeRef.model_validate(retained["selected_source"])
    source = read_knowledge(root, reference.record_id, owner).state
    assert source is not None and source.kind == "source"
    assert source.content == content and source.derived_from == (bridge.last_sources[session],)
    assert reference not in bridge.exposed_refs.get(session, set())
    bridge.activity_setup(
        session,
        {
            "action": "attach_sources",
            "setup_id": str(setup),
            "source_refs": [reference.model_dump(mode="json")],
        },
    )
    _step(case, "start_stage", stage_kind="draft", stage_instruction="Use the complete packet")
    packet = read_activity_setup(root, setup, owner).state.stages[-1].packet
    read = bridge.activity_setup(
        session,
        {
            "action": "read_packet",
            "setup_id": str(setup),
            "reference": packet.model_dump(mode="json"),
            "max_bytes": 16,
        },
    )
    assert len(base64.b64decode(read["content_base64"])) <= 16 and read["next_offset"] == 16
    with pytest.raises(FoundationError) as error:
        bridge.activity_setup(
            session,
            {
                "action": "read_packet",
                "setup_id": str(setup),
                "reference": {"artifact_id": str(uuid4()), "revision": 1},
            },
        )
    assert error.value.code == "wrong_scope"


@pytest.mark.parametrize("unknown_send", [False, True])
def test_paused_setup_retains_file_and_received_supplement_without_answering(
    tmp_path: Path, unknown_send: bool
) -> None:
    """New requirements survive a stop without replaying or answering a saved wait."""
    import base64
    import hashlib

    from tests.zaratustra.foundation.test_activity_setup_recovery import _recovery_case, _start
    from tests.zaratustra.foundation.test_execution import invocation
    from zaratustra.pi_adapter.assigned import EXECUTOR_VERSION

    case = _recovery_case(tmp_path, 16)
    root, space, owner, setup, *_ = case
    _start(case)
    stage = read_activity_setup(root, setup, owner).state.stages[-1]
    resource, attempt, assigned_session = uuid4(), uuid4(), uuid4()
    apply_operation(
        root,
        CreateResourceRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            resource_id=resource,
            work_id=stage.work_id,
            state=ResourceState(label="Fictional setup", root=root, limit_units=100),
        ),
        owner,
    )
    apply_operation(
        root,
        AssignAttemptRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            attempt_id=attempt,
            work_id=stage.work_id,
            expected_work_revision=read_work(root, stage.work_id, owner).revision,
            resource_id=resource,
            expected_resource_revision=1,
            session_id=assigned_session,
            executor_version=EXECUTOR_VERSION,
        ),
        owner,
    )
    common: InvocationFields | None = None
    if unknown_send:
        invocation_id, _ = invocation(
            root, space, stage.work_id, attempt, assigned_session, owner, 10
        )
        common = dict(
            invocation_id=invocation_id,
            attempt_id=attempt,
            work_id=stage.work_id,
            session_id=assigned_session,
        )
        for request in (
            AdmitInvocationRequest(
                operation_id=uuid4(), space_id=space, actor=owner.actor, **common
            ),
            SendInvocationRequest(
                operation_id=uuid4(), space_id=space, actor=owner.actor, **common
            ),
        ):
            apply_operation(root, request, owner)
    bridge = Bridge(root, owner, root)
    session = uuid4()
    bridge.connect(session)
    supplement = "Use the existing research; weekly planning remains confirmed."
    bridge.capture_source(
        session,
        channel="conversation_user",
        content=supplement,
        source_event_id="received-supplement",
        input_source="interactive",
    )
    original = bridge.last_sources[session]
    content = "Complete вымышленное research original".encode()
    retained = bridge.activity_setup(
        session,
        {
            "action": "retain_file",
            "setup_id": str(setup),
            "operation_key": "selected-research",
            "locator": "research.txt",
            "content_base64": base64.b64encode(content).decode(),
            "content_sha256": hashlib.sha256(content).hexdigest(),
        },
    )
    selected = KnowledgeRef.model_validate(retained["selected_source"])
    attach = {
        "action": "attach_sources",
        "setup_id": str(setup),
        "source_refs": [selected.model_dump(mode="json")],
    }
    with pytest.raises(FoundationError, match="setup_running"):
        bridge.activity_setup(session, attach)
    paused = bridge.activity_setup(session, {"action": "pause", "setup_id": str(setup)})
    assert paused["state"]["phase"] == "paused"
    assert paused["execution"]["status"] == "stopping"
    assert paused["execution"]["next_action"] == "wait_for_stop"
    assert not paused["execution"]["can_resume"]
    assert paused["execution"]["can_attach_sources"] is unknown_send
    assignment = read_execution(root, stage.work_id, owner).assignments[-1]
    apply_operation(
        root,
        RecordAttemptStopRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            work_id=stage.work_id,
            attempt_id=attempt,
            session_id=assigned_session,
            expected_assignment_revision=assignment.revision,
            outcome="stopped",
        ),
        owner,
    )
    status = bridge.activity_setup(session, {"action": "status", "setup_id": str(setup)})
    assert status["execution"]["status"] == ("unknown" if unknown_send else "stopped")
    assert status["execution"]["can_attach_sources"]
    result = bridge.activity_setup(session, attach)
    current = read_activity_setup(root, setup, owner).state
    assert original in current.sources and selected in current.sources
    assert current.question is None
    assert current.stages[-1].retired is (not unknown_send)
    assert result["execution"]["can_retry"] is unknown_send
    assert result["execution"]["status"] == ("unknown" if unknown_send else "idle")
    assert current.phase == "paused"
    if unknown_send:
        with pytest.raises(FoundationError, match="unknown_effect"):
            bridge.activity_setup(session, {"action": "resume", "setup_id": str(setup)})
        assert read_execution(root, stage.work_id, owner).held_units == 10
    else:
        assert result["execution"]["can_resume"]
        _step(case, "resume")
        _start(case)
        fresh = read_activity_setup(root, setup, owner).state.stages[-1]
        packet = read_artifact(root, fresh.packet.artifact_id, owner).content
        assert packet is not None
        decoded = json.loads(packet)
        assert supplement in json.dumps(decoded, ensure_ascii=False)
        assert content.decode() in json.dumps(decoded, ensure_ascii=False)
    assert read_work(root, stage.work_id, owner).state.acceptance is None


def test_paused_unknown_answer_does_not_wake_interrupted_native_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real owner answer is saved without sending to an unknown RPC session."""
    from tests.zaratustra.foundation.test_activity_setup_recovery import _recovery_case, _start
    from zaratustra.pi_adapter.assigned import EXECUTOR_VERSION

    case = _recovery_case(tmp_path, 16)
    root, space, owner, setup, activity, *_ = case
    _start(case)
    stage = read_activity_setup(root, setup, owner).state.stages[-1]
    resource, attempt, assigned_session, wait_id = uuid4(), uuid4(), uuid4(), uuid4()
    apply_operation(
        root,
        CreateResourceRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            resource_id=resource,
            work_id=stage.work_id,
            state=ResourceState(label="Fictional setup", root=root),
        ),
        owner,
    )
    apply_operation(
        root,
        AssignAttemptRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            attempt_id=attempt,
            work_id=stage.work_id,
            expected_work_revision=read_work(root, stage.work_id, owner).revision,
            resource_id=resource,
            expected_resource_revision=1,
            session_id=assigned_session,
            executor_version=EXECUTOR_VERSION,
        ),
        owner,
    )
    rpc = Bridge(
        root, owner, root, assigned_attempt_id=attempt, assigned_session_id=assigned_session
    )
    rpc.connect(assigned_session)
    rpc.select(assigned_session, activity, stage.work_id)
    question = "Which period should be compared?"
    rpc.open_wait(
        assigned_session,
        attempt,
        wait_id,
        "Known original observations",
        question,
        "Compare the addressed period",
    )
    _step(case, "question", text=question)
    _step(case, "pause")
    assignment = read_execution(root, stage.work_id, owner).assignments[-1]
    apply_operation(
        root,
        RecordAttemptStopRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            work_id=stage.work_id,
            attempt_id=attempt,
            session_id=assigned_session,
            expected_assignment_revision=assignment.revision,
            outcome="unknown",
        ),
        owner,
    )
    before = read_execution(root, stage.work_id, owner)
    assert before.waits[0].status == "open"
    delivered: list[UUID] = []
    monkeypatch.setattr(
        "zaratustra.pi_adapter.assigned.deliver_outbox",
        lambda _root, _owner, outbox: delivered.append(outbox),
    )
    bridge = Bridge(root, owner, root)
    session = uuid4()
    bridge.connect(session)
    pending = bridge.activity_setup(session, {"action": "status", "setup_id": str(setup)})
    assert pending["execution"]["next_action"] == "answer"
    assert not pending["execution"]["can_retry"]
    bridge.capture_source(
        session,
        channel="conversation_user",
        content="Previous complete month",
        source_event_id="received-owner-answer",
        input_source="interactive",
    )
    original = bridge.last_sources[session]
    result = bridge.activity_setup(session, {"action": "answer", "setup_id": str(setup)})
    state = read_activity_setup(root, setup, owner).state
    after = read_execution(root, stage.work_id, owner)
    assert not delivered and after.outbox == before.outbox
    assert after.waits[0] == before.waits[0]
    assert after.assignments[0].status == "unknown"
    assert original in state.sources and state.question is None
    assert state.phase == "paused" and not state.stages[-1].retired
    assert result["execution"]["status"] == "unknown" and not result["execution"]["can_retry"]
    assert read_work(root, stage.work_id, owner).state.acceptance is None


def test_internal_read_tools_cannot_write_through_bridge(tmp_path: Path) -> None:
    """Risk: a read-only tool allowlist still exposes mutation modes to a model node."""
    root, space, owner, *_ = _case(tmp_path)
    source = note(root, space, owner, "Readable original")
    bridge = Bridge(root, owner, root, restricted_core_reads=True)
    session = uuid4()
    bridge.connect(session)
    assert (
        bridge.knowledge_read(session, {"mode": "open", "record_id": str(source)})["content_base64"]
        is not None
    )
    identifier = uuid4()
    mutation = CreateKnowledgeRequest(
        operation_id=uuid4(),
        space_id=space,
        actor=owner.actor,
        record_id=identifier,
        state=SourceState(
            channel="document",
            connection="fictional",
            profile_revision=1,
            media_type="text/plain",
            capture="full",
            content=b"unauthorized effect",
        ),
    )
    with pytest.raises(FoundationError) as error:
        bridge.knowledge_operation(session, mutation.model_dump(mode="json"))
    assert error.value.code == "permission_denied"
    with pytest.raises(FoundationError) as error:
        read_knowledge(root, identifier, owner)
    assert error.value.code == "not_found"
    with pytest.raises(FoundationError) as error:
        bridge.knowledge_read(session, {"mode": "export", "file": "must-not-exist.md"})
    assert error.value.code == "permission_denied" and not (root / "must-not-exist.md").exists()


@pytest.mark.parametrize(
    "input_source,owner_input",
    [
        ("interactive", True),
        ("rpc", True),
        ("extension", False),
        ("session-resume", False),
    ],
)
def test_only_fresh_ordinary_owner_input_can_answer(
    tmp_path: Path, input_source: str, owner_input: bool
) -> None:
    """Risk: generated or restored user-shaped messages become answers to saved questions."""
    root, _, owner, *_ = _case(tmp_path)
    bridge = Bridge(root, owner, root)
    session = uuid4()
    bridge.connect(session)
    bridge.capture_source(
        session,
        channel="conversation_user",
        content="Original input",
        source_event_id="input-one",
        input_source=input_source,
        replay_session_id=uuid4() if input_source == "session-resume" else None,
    )
    source = read_knowledge(root, bridge.last_sources[session].record_id, owner).state
    assert source is not None and source.kind == "source"
    if owner_input:
        assert source.sender == owner.actor
        assert bridge._fresh_user_source(session)[1] == "Original input"
    else:
        assert source.sender != owner.actor
        with pytest.raises(FoundationError) as error:
            bridge._fresh_user_source(session)
        assert error.value.code == "permission_denied"


def test_development_creates_work_and_selected_resource(tmp_path: Path) -> None:
    root, working, space_id, _, _, _, owner = ready(tmp_path)
    bridge = Bridge(root, owner, working, limit_units=100)
    session_id = uuid4()
    bridge.connect(session_id)
    activity_id, work_id, resource_id = uuid4(), uuid4(), uuid4()
    activity = CreateActivityRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor=owner.actor,
        activity_id=activity_id,
        state=ActivityState(title="Fictional development", goal="Change one test resource"),
    )
    assert bridge.development_contract(session_id, "create_activity")["kind"] == "create_activity"
    bridge.development_operation(session_id, activity.model_dump(mode="json"))
    listed = bridge.connect(session_id)["records"]
    assert isinstance(listed, list)
    assert any(item["record_id"] == str(activity_id) for item in listed)
    exact_activity = bridge.activity_read(session_id, activity_id)
    exact_state = exact_activity["state"]
    assert isinstance(exact_state, dict)
    assert exact_state["title"] == "Fictional development"
    work = CreateWorkRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor=owner.actor,
        work_id=work_id,
        state=WorkState(
            activity_id=activity_id,
            goal="Make and verify a fictional edit",
            expected_outputs=(OutputContract(slot="result", media_type="text/plain"),),
        ),
    )
    bridge.development_operation(session_id, work.model_dump(mode="json"))
    resource = CreateResourceRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor=owner.actor,
        resource_id=resource_id,
        work_id=work_id,
        state=ResourceState(label="Selected resource", root=working, limit_units=100),
    )
    bridge.development_operation(session_id, resource.model_dump(mode="json"))
    assert read_execution(root, work_id, owner).resources[0].resource_id == resource_id
    artifact_id = uuid4()
    artifact = CreateArtifactRequest(
        operation_id=uuid4(),
        space_id=space_id,
        actor=owner.actor,
        artifact_id=artifact_id,
        media_type="text/plain",
        content=b"Test result",
    )
    bridge.development_operation(session_id, artifact.model_dump(mode="json"))
    bridge.development_operation(
        session_id,
        LinkWorkOutputRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            work_id=work_id,
            expected_revision=1,
            output=LinkedOutput(
                slot="result", artifact=ArtifactRef(artifact_id=artifact_id, revision=1)
            ),
        ).model_dump(mode="json"),
    )
    assert read_work(root, work_id, owner).state.status == "proposed"
    assert read_artifact(root, artifact_id, owner).content == b"Test result"
    with pytest.raises(FoundationError, match="resource_unavailable"):
        bridge.development_operation(
            session_id,
            resource.model_copy(
                update={
                    "operation_id": uuid4(),
                    "resource_id": uuid4(),
                    "state": resource.state.model_copy(update={"root": root}),
                }
            ).model_dump(mode="json"),
        )


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
    with pytest.raises(FoundationError, match="invalid_output"):
        apply_operation(
            root,
            PublishAttemptOutputRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor=owner.actor,
                attempt_id=attempt_id,
                work_id=work_id,
                session_id=session_id,
                slot="summary",
                media_type="text/plain",
                content=b"",
            ),
            owner,
        )
    assert not read_execution(root, work_id, owner).outputs
    first = bridge.publish(
        session_id, attempt_id, "summary", "text/plain", "Fictional note summary."
    )
    assert (
        bridge.publish(session_id, attempt_id, "summary", "text/plain", "Fictional note summary.")
        == first
    )
    with pytest.raises(FoundationError, match="operation_conflict"):
        bridge.publish(session_id, attempt_id, "summary", "text/plain", "Different result")
    assert read_work(root, work_id, owner).state.status == "proposed"
    preview = bridge.accept_preview(session_id)
    nonce = UUID(cast(str, preview["nonce"]))
    accepted = bridge.accept(session_id, nonce, "I checked the summary")
    assert bridge.accept(session_id, nonce, "I checked the summary") == accepted
    assert (
        bridge.publish(session_id, attempt_id, "summary", "text/plain", "Fictional note summary.")
        == first
    )
    reopened = authorize_local(root, actor=owner.actor, source_ref="fresh-local-session")
    state = read_execution(root, work_id, reopened)
    assert state.work.state.status == "succeeded"
    assert "work.accept" in state.work_rights and "model.invoke" in state.work_rights
    assert state.activity.state.status == "ongoing"
    assert state.work.state.acceptance is not None
    assert state.work.state.acceptance.authority_source.startswith("pi-ui-confirm:")
    assert state.outputs[0].content == b"Fictional note summary."
    assert state.committed_units == 9 and state.held_units == 0


def test_new_attempt_replaces_proposed_output_with_exact_history(tmp_path: Path) -> None:
    root, working, space_id, _, work_id, _, owner = ready(tmp_path)
    bridge = Bridge(root, owner, working, limit_units=100)
    activity_id = read_work(root, work_id, owner).state.activity_id

    def answered_attempt(session_id: UUID, attempt_id: UUID) -> None:
        fields: InvocationFields = dict(
            invocation_id=uuid4(), attempt_id=attempt_id, work_id=work_id, session_id=session_id
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
                **fields,
            ),
            AdmitInvocationRequest(
                operation_id=uuid4(), space_id=space_id, actor=owner.actor, **fields
            ),
            SendInvocationRequest(
                operation_id=uuid4(), space_id=space_id, actor=owner.actor, **fields
            ),
            FinishInvocationRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor=owner.actor,
                outcome="answered",
                usage_units=9,
                **fields,
            ),
        ):
            bridge.operation(session_id, request.model_dump(mode="json"))

    first_session = uuid4()
    bridge.connect(first_session)
    bridge.select(first_session, activity_id, work_id)
    first_attempt = UUID(
        cast(str, bridge.start_attempt(first_session, interrupt_previous=False)["attempt_id"])
    )
    answered_attempt(first_session, first_attempt)
    first = bridge.publish(first_session, first_attempt, "summary", "text/plain", "First answer")
    bridge.operation(
        first_session,
        StopAttemptRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            attempt_id=first_attempt,
            work_id=work_id,
            session_id=first_session,
            outcome="completed",
        ).model_dump(mode="json"),
    )
    proposed = read_work(root, work_id, owner, revision=2)
    assert proposed.state.status == "proposed"
    assert len(proposed.state.linked_outputs) == 1

    second_session = uuid4()
    bridge.connect(second_session)
    bridge.select(second_session, activity_id, work_id)
    second_attempt = UUID(
        cast(str, bridge.start_attempt(second_session, interrupt_previous=False)["attempt_id"])
    )
    answered_attempt(second_session, second_attempt)
    second = bridge.publish(
        second_session, second_attempt, "summary", "text/plain", "Revised answer"
    )
    assert second != first
    current = read_work(root, work_id, owner)
    assert current.revision == 3 and current.state.status == "proposed"
    assert len(current.state.linked_outputs) == 1
    first_artifact = proposed.state.linked_outputs[0].artifact.artifact_id
    second_artifact = current.state.linked_outputs[0].artifact.artifact_id
    assert first_artifact != second_artifact
    assert read_artifact(root, first_artifact, owner).content == b"First answer"
    assert read_artifact(root, second_artifact, owner).content == b"Revised answer"
    assert read_work(root, work_id, owner, revision=2) == proposed
    assert (
        bridge.publish(second_session, second_attempt, "summary", "text/plain", "Revised answer")
        == second
    )
    assert (
        bridge.publish(first_session, first_attempt, "summary", "text/plain", "First answer")
        == first
    )
    assert read_work(root, work_id, owner) == current

    preview = bridge.accept_preview(second_session)
    bridge.accept(second_session, UUID(cast(str, preview["nonce"])), "Reviewed revised answer")
    accepted = read_work(root, work_id, owner)
    assert accepted.revision == 4 and accepted.state.status == "succeeded"
    assert accepted.state.linked_outputs == current.state.linked_outputs
    with pytest.raises(FoundationError, match="work_closed"):
        bridge.start_attempt(second_session, interrupt_previous=False)


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


def test_late_attempt_cannot_replace_newer_output(tmp_path: Path) -> None:
    root, working, space_id, _, work_id, _, owner = ready(tmp_path)
    bridge = Bridge(root, owner, working, limit_units=100)
    session_id = uuid4()
    bridge.connect(session_id)
    bridge.select(session_id, read_work(root, work_id, owner).state.activity_id, work_id)
    attempt_id = UUID(
        cast(str, bridge.start_attempt(session_id, interrupt_previous=False)["attempt_id"])
    )
    common: InvocationFields = dict(
        invocation_id=uuid4(), attempt_id=attempt_id, work_id=work_id, session_id=session_id
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
        apply_operation(root, request, owner)
    newer_id = uuid4()
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            artifact_id=newer_id,
            media_type="text/plain",
            content=b"Newer answer",
        ),
        owner,
    )
    apply_operation(
        root,
        LinkWorkOutputRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            work_id=work_id,
            expected_revision=1,
            output=LinkedOutput(
                slot="summary", artifact=ArtifactRef(artifact_id=newer_id, revision=1)
            ),
        ),
        owner,
    )
    with pytest.raises(FoundationError, match="stale_work"):
        bridge.publish(session_id, attempt_id, "summary", "text/plain", "Late answer")
    current = read_execution(root, work_id, owner)
    assert current.work.revision == 2
    assert current.work.state.linked_outputs[0].artifact.artifact_id == newer_id
    assert current.outputs[0].content == b"Newer answer"
    with pytest.raises(FoundationError, match="not_found"):
        read_artifact(root, uuid5(attempt_id, "artifact:summary"), owner)


def test_managed_pi_history_is_retired_with_content_deletion(tmp_path: Path) -> None:
    root, working, space_id, _, work_id, _, owner = ready(tmp_path)
    history = managed_pi_sessions(root, space_id, create=True)
    copied = history / "synthetic-session.jsonl"
    copied.write_text('{"text":"fictional note"}\n', encoding="utf-8")
    unrelated = tmp_path / "unmanaged-note.txt"
    unrelated.write_text("keep this", encoding="utf-8")
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
    with pytest.raises(FoundationError, match="deletion_pending"):
        Bridge(root, owner, working, limit_units=100).connect(uuid4())
    with managed_pi_lock(root), pytest.raises(FoundationError, match="history_busy"):
        complete_deletions(root, owner)
    assert copied.exists()
    assert complete_deletions(root, owner).pending_jobs == 0
    assert not copied.exists()
    assert history.joinpath("owner.txt").is_file()
    assert unrelated.read_text(encoding="utf-8") == "keep this"


def test_accept_retires_active_attempt_after_restart(tmp_path: Path) -> None:
    root, working, space_id, _, work_id, _, owner = ready(tmp_path)
    bridge = Bridge(root, owner, working, limit_units=100)
    session_id = uuid4()
    bridge.connect(session_id)
    bridge.select(session_id, read_work(root, work_id, owner).state.activity_id, work_id)
    attempt_id = UUID(
        cast(str, bridge.start_attempt(session_id, interrupt_previous=False)["attempt_id"])
    )
    result_id = uuid4()
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            artifact_id=result_id,
            media_type="text/plain",
            content=b"Synthetic result",
        ),
        owner,
    )
    apply_operation(
        root,
        LinkWorkOutputRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            work_id=work_id,
            expected_revision=1,
            output=LinkedOutput(
                slot="summary", artifact=ArtifactRef(artifact_id=result_id, revision=1)
            ),
        ),
        owner,
    )
    apply_operation(
        root,
        CreateGrantRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor=owner.actor,
            grant_id=uuid4(),
            state=GrantState(
                grantee="synthetic-acceptor",
                actions=("space.inspect", "record.read", "work.accept"),
            ),
        ),
        owner,
    )
    acceptor = authorize_local(root, actor="synthetic-acceptor", source_ref="local-acceptor")
    acceptor_bridge = Bridge(root, acceptor, working, limit_units=100)
    fresh_session = uuid4()
    acceptor_bridge.connect(fresh_session)
    acceptor_bridge.select(
        fresh_session, read_work(root, work_id, owner).state.activity_id, work_id
    )
    preview = acceptor_bridge.accept_preview(fresh_session)
    acceptor_bridge.accept(
        fresh_session, UUID(cast(str, preview["nonce"])), "Reviewed synthetic result"
    )
    current = read_execution(root, work_id, owner)
    assert current.work.state.status == "succeeded"
    assert current.attempts[-1].attempt_id == attempt_id
    assert current.attempts[-1].status == "interrupted"
    assert current.held_units == 0
    acceptor_rights = read_execution(root, work_id, acceptor).work_rights
    assert "work.accept" in acceptor_rights and "work.execute" not in acceptor_rights
