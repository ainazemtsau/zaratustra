"""Run one synthetic composite child Work through ordinary Pi RPC and DBOS 3.0.0.

The file imports only the standard library and the installed ``zaratustra`` package,
so the same trial runs from the checkout and from a wheel installed outside it.
Every model answer comes from a localhost synthetic provider.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import zaratustra.foundation as foundation  # admits the pinned SQLite before DBOS loads
from zaratustra.foundation import (
    AcceptWorkRequest,
    ActivityState,
    ArtifactRef,
    AssignAttemptRequest,
    BootstrapRequest,
    ConfirmObligationRequest,
    CreateActivityRequest,
    CreateArtifactRequest,
    CreateCompositeWorkRequest,
    CreateDecisionRequest,
    CreateMethodVersionRequest,
    CreateResourceRequest,
    DecisionState,
    DeleteArtifactRequest,
    DeleteMethodVersionRequest,
    DeleteWorkRequest,
    FoundationError,
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
    ResourceState,
    ReviseDecisionRequest,
    ReviseWorkPlanRequest,
    WorkPlan,
    WorkState,
    apply_operation,
    authorize_local,
    authorize_recovery,
    initialize_space,
    managed_pi_session_lock,
    managed_pi_sessions,
    read_activity,
    read_execution,
    read_obligation,
    read_receipt,
    read_space,
    read_work,
    read_work_plan,
    read_work_status,
    restore_backup,
    upgrade_child_execution_space,
    upgrade_composition_space,
    upgrade_continuation_space,
    upgrade_execution_space,
    upgrade_space,
)
from zaratustra.pi_adapter import Bridge, BridgeServer
from zaratustra.pi_adapter.assigned import (
    EXECUTOR_VERSION,
    AssignedConfig,
    complete_assigned_deletions,
    create_assigned_backup,
    deliver_outbox,
    run_assigned,
)

ACTOR = "owner"
PI_ENVIRONMENT = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP"}


class Markers:
    """Unique synthetic texts whose bytes deletion must remove from managed copies."""

    def __init__(self) -> None:
        token = uuid4().hex[:12]
        self.question = f"Какая строка учебной заметки основная? [{token}-q]"
        self.answer = f"Основная первая строка [{token}-a]"
        self.partial = f"В заметке две строки [{token}-p]"
        self.a_result = f"Сведения проверены: основная первая строка [{token}-ra]"
        self.b_result = f"Итог учебного пакета по первой строке [{token}-rb]"

    def responses(self) -> tuple[str, ...]:
        wait = {
            "zara": "wait",
            "partial": self.partial,
            "question": self.question,
            "remainder": "Сверить основную строку и завершить проверку",
        }
        return (
            json.dumps(wait, ensure_ascii=False),
            json.dumps({"zara": "final", "text": self.a_result}, ensure_ascii=False),
            json.dumps({"zara": "final", "text": self.b_result}, ensure_ascii=False),
        )

    def all(self) -> tuple[str, ...]:
        return (self.question, self.answer, self.partial, self.a_result, self.b_result)


class SyntheticProvider(ThreadingHTTPServer):
    def __init__(self, responses: tuple[str, ...]) -> None:
        super().__init__(("127.0.0.1", 0), SyntheticHandler)
        self.responses = responses
        self.digests: list[str] = []
        self.guard = threading.Lock()


class SyntheticHandler(BaseHTTPRequestHandler):
    server: SyntheticProvider

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        with self.server.guard:
            self.server.digests.append(hashlib.sha256(body).hexdigest().upper())
            number = len(self.server.digests)
        text = self.server.responses[min(number, len(self.server.responses)) - 1]
        usage = {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140}
        chunks: list[dict[str, object]] = [
            {
                "id": "synthetic",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            },
            {
                "id": "synthetic",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
            },
            {
                "id": "synthetic",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            },
            {"id": "synthetic", "object": "chat.completion.chunk", "choices": [], "usage": usage},
        ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def _apply(root: Path, owner: LocalAuthority, request_type: type[Any], **fields: Any) -> Any:
    request = request_type(operation_id=uuid4(), space_id=owner.space_id, actor=ACTOR, **fields)
    return apply_operation(root, request, owner)


def _refusal(action: Any) -> str:
    try:
        action()
    except FoundationError as error:
        return error.code
    raise AssertionError("Expected an addressed Core refusal")


def _state(root: Path, owner: LocalAuthority, work: UUID) -> dict[str, object]:
    status = read_work_status(root, work, owner)
    return {"status": status.status, "reasons": [reason.code for reason in status.reasons]}


def _text(revision: Any) -> str:
    assert revision.content is not None
    return str(revision.content.decode("utf-8"))


def _contains(directory: Path, marker: str) -> list[str]:
    data = marker.encode("utf-8")
    return sorted(
        str(path.relative_to(directory)).replace(os.sep, "/")
        for path in directory.rglob("*")
        if path.is_file() and data in path.read_bytes()
    )


def _workflows(root: Path) -> list[dict[str, object]]:
    from dbos import DBOSClient

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
                name="zara-assigned-work-v1",
                application_name="zaratustra-assigned-rpc",
                load_input=False,
                load_output=False,
            )
        ]
    finally:
        client.destroy()


class StatusRecorder:
    """Sample one Work's derived Core state while an assigned Pi run proceeds."""

    def __init__(self, root: Path, owner: LocalAuthority, work: UUID) -> None:
        self.root, self.owner, self.work = root, owner, work
        self.seen: list[str] = []
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._poll, daemon=True)

    def _poll(self) -> None:
        while not self.done.is_set():
            try:
                status = read_work_status(self.root, self.work, self.owner)
            except FoundationError:
                time.sleep(0.02)
                continue
            label = status.status + (f":{status.reasons[0].code}" if status.reasons else "")
            if not self.seen or self.seen[-1] != label:
                self.seen.append(label)
            time.sleep(0.02)

    def __enter__(self) -> StatusRecorder:
        self.thread.start()
        return self

    def __exit__(self, *_error: object) -> None:
        self.done.set()
        self.thread.join(timeout=5)


def _technical_copies(root: Path, texts: tuple[str, ...]) -> dict[str, object]:
    """DBOS and Pi RPC copies may carry addresses, never plan or result text."""

    managed = root / ".zara-core"
    files = [path for path in managed.glob("executor.sqlite3*") if path.is_file()]
    home = managed / "pi-rpc-home"
    files += [path for path in home.rglob("*") if path.is_file()] if home.exists() else []
    return {
        "files": sorted(str(path.relative_to(managed)).replace(os.sep, "/") for path in files),
        "text_found": sorted(
            text for text in texts for path in files if text.encode("utf-8") in path.read_bytes()
        ),
    }


def status_via_pi(
    root: Path,
    workspace: Path,
    owner: LocalAuthority,
    config: AssignedConfig,
    activity: UUID,
    work: UUID,
    expected: tuple[str, ...],
) -> str:
    """Ask an ordinary Pi with the interactive extension for /zara-status; no model call."""

    bridge = Bridge(root, owner, workspace, 10000)
    server = BridgeServer(bridge)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    extension = Path(str(files("zaratustra.pi_adapter").joinpath("extension.ts")))
    installed = config.pi_runtime / f"zaratustra-status-{uuid4()}.ts"
    home = managed_pi_sessions(root, owner.space_id, create=True) / f"status-{uuid4()}"
    home.mkdir()
    environment = {key: value for key, value in os.environ.items() if key.upper() in PI_ENVIRONMENT}
    environment.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "APPDATA": str(home / "AppData"),
            "LOCALAPPDATA": str(home / "LocalAppData"),
            "PI_CODING_AGENT_DIR": str(home / "pi-agent"),
            "PI_OFFLINE": "1",
            "PI_SKIP_VERSION_CHECK": "1",
            "PI_TELEMETRY": "0",
            "ZARA_CORE_ENDPOINT": f"http://127.0.0.1:{server.server_port}",
            "ZARA_CORE_TOKEN": bridge.token,
            "ZARA_RESERVE_UNITS": "1000",
            "ZARA_PROVIDER_PROFILE": "local-completions",
            "ZARA_PROVIDER_BASE_URL": config.provider_base_url,
            "ZARA_PROVIDER_ORIGIN": config.provider_base_url.split("/v1", 1)[0],
            "ZARA_LOCAL_PROVIDER_ID": config.provider_id,
            "ZARA_LOCAL_MODEL_ID": config.model_id,
            "ZARA_LOCAL_CONTEXT_WINDOW": "4096",
            "ZARA_LOCAL_MAX_TOKENS": "512",
            "ZARA_INITIAL_ACTIVITY_ID": str(activity),
            "ZARA_INITIAL_WORK_ID": str(work),
        }
    )
    command = [
        config.node,
        str(config.pi_cli),
        "--mode",
        "rpc",
        "--provider",
        config.provider_id,
        "--model",
        config.model_id,
        "--extension",
        str(installed),
        "--no-extensions",
        "--no-context-files",
        "--no-tools",
        "--no-session",
        "--no-skills",
        "--no-prompt-templates",
        "--no-themes",
        "--no-approve",
        "--offline",
    ]
    try:
        shutil.copy2(extension, installed)
        with managed_pi_session_lock(root):
            process = subprocess.Popen(
                command,
                cwd=workspace,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            received: queue.Queue[dict[str, object]] = queue.Queue()

            def read_events() -> None:
                assert process.stdout is not None
                for raw in process.stdout:
                    try:
                        event = json.loads(raw)
                    except ValueError:
                        continue
                    if isinstance(event, dict):
                        received.put(event)

            reader = threading.Thread(target=read_events, daemon=True)
            reader.start()
            try:
                assert process.stdin is not None
                process.stdin.write(b'{"id":"status","type":"prompt","message":"/zara-status"}\n')
                process.stdin.flush()
                deadline = time.monotonic() + 40
                while time.monotonic() < deadline:
                    try:
                        event = received.get(timeout=0.25)
                    except queue.Empty:
                        continue
                    if event.get("type") == "extension_ui_request" and event.get("method") == (
                        "notify"
                    ):
                        text = str(event.get("message", json.dumps(event, ensure_ascii=False)))
                        if all(fragment in text for fragment in expected):
                            return text
                    if event.get("type") == "response" and event.get("id") == "status":
                        if event.get("success") is not True:
                            raise AssertionError(f"Pi refused /zara-status: {event}")
                raise AssertionError(f"Ordinary Pi did not show the Core state {expected}")
            finally:
                process.terminate()
                process.wait(timeout=10)
                reader.join(timeout=5)
    finally:
        installed.unlink(missing_ok=True)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def reopen(data: dict[str, str]) -> dict[str, object]:
    """Fresh process: read the same Core records without the originating objects."""

    root = Path(data["space"])
    owner = authorize_local(root, actor=ACTOR, source_ref="synthetic-reopened-process")
    parent, a, b = UUID(data["parent"]), UUID(data["a"]), UUID(data["b"])
    a_state, b_state = read_execution(root, a, owner), read_execution(root, b, owner)
    return {
        "module": str(Path(foundation.__file__).resolve()),
        "statuses": {
            name: read_work_status(root, work, owner).status
            for name, work in (("parent", parent), ("a", a), ("b", b))
        },
        "plan_revision": read_work_plan(root, parent, owner).revision,
        "obligations": {
            key: read_obligation(root, parent, key, owner).status for key in ("checked", "final")
        },
        "a_output": _text(a_state.outputs[0]) if a_state.outputs else None,
        "b_output": _text(b_state.outputs[0]) if b_state.outputs else None,
        "a_pins": [pin.plan_revision for pin in cast(Any, a_state.composition).pins],
        "receipts": {
            name: read_receipt(root, UUID(data[name]), owner).model_dump(mode="json")
            for name in ("a_accept", "b_accept", "parent_accept")
        },
        "activity": read_activity(root, UUID(data["activity"]), owner).state.status,
    }


def _reopen_in_new_process(data: dict[str, str]) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-I", str(Path(__file__).resolve()), "--reopen", json.dumps(data)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise AssertionError(f"Reopened process failed: {result.stderr}")
    return cast(dict[str, object], json.loads(result.stdout.strip().splitlines()[-1]))


def _space(base: Path) -> dict[str, Any]:
    root = base / "space"
    root.mkdir()
    info = initialize_space(root)
    owner = authorize_local(root, actor=ACTOR, source_ref="synthetic-local-console")
    apply_operation(
        root,
        BootstrapRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=ACTOR,
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        owner,
    )
    upgrade_space(root, owner)
    upgrade_execution_space(root, owner)
    upgrade_continuation_space(root, owner)
    upgrade_composition_space(root, owner)
    schemas = [read_space(root).schema_version]
    upgrade_child_execution_space(root, owner)
    schemas.append(read_space(root).schema_version)
    activity, source, method, parent, a, b = (uuid4() for _ in range(6))
    _apply(
        root,
        owner,
        CreateActivityRequest,
        activity_id=activity,
        state=ActivityState(
            title="Подготовить учебный пакет", goal="Синтетический учебный пакет без личных данных"
        ),
    )
    _apply(
        root,
        owner,
        CreateArtifactRequest,
        artifact_id=source,
        media_type="text/plain",
        content="Учебная заметка: первая строка, вторая строка.".encode(),
    )
    definition = MethodDefinition(
        instruction="Проверить синтетические сведения, затем составить итог.",
        named_inputs=(OutputContract(slot="source", media_type="text/plain"),),
        named_outputs=(OutputContract(slot="final", media_type="text/plain"),),
        obligations=(
            MethodObligation(
                key="checked",
                source="synthetic method v1",
                role="a",
                slot="checked",
                media_type="text/plain",
            ),
            MethodObligation(
                key="final",
                source="synthetic method v1",
                role="b",
                slot="final",
                media_type="text/plain",
            ),
        ),
        source_ref="synthetic-method-proposal",
    )
    created = _apply(
        root, owner, CreateMethodVersionRequest, method_id=method, version=1, definition=definition
    )
    ref = MethodRef(method_id=method, version=1, checksum=str(created.result["checksum"]))
    source_ref = ArtifactRef(artifact_id=source, revision=1)
    plan = WorkPlan(
        named_inputs=(NamedInput(slot="source", artifact=source_ref),),
        output_bindings=(
            PlanOutputBinding(
                parent_slot="final", role="b", child_slot="final", media_type="text/plain"
            ),
        ),
        children=(
            PlanChild(
                role="a",
                work_id=a,
                state=WorkState(
                    activity_id=activity,
                    goal="Проверить сведения",
                    inputs=(source_ref,),
                    expected_outputs=(OutputContract(slot="checked", media_type="text/plain"),),
                ),
            ),
            PlanChild(
                role="b",
                work_id=b,
                state=WorkState(
                    activity_id=activity,
                    goal="Составить итог",
                    expected_outputs=(OutputContract(slot="final", media_type="text/plain"),),
                ),
                readiness=PlanCondition(
                    kind="accepted_output", role="a", slot="checked", media_type="text/plain"
                ),
            ),
        ),
        completion=PlanCondition(
            kind="all",
            members=(
                PlanCondition(kind="work_succeeded", role="a"),
                PlanCondition(kind="work_succeeded", role="b"),
            ),
        ),
        basis=(source_ref,),
        rationale="Первичный синтетический план",
        source_ref="synthetic-owner-plan",
    )
    create = CreateCompositeWorkRequest(
        operation_id=uuid4(),
        space_id=info.space_id,
        actor=ACTOR,
        work_id=parent,
        state=WorkState(
            activity_id=activity,
            goal="Подготовить учебный пакет",
            inputs=(source_ref,),
            expected_outputs=definition.named_outputs,
            method=ref,
        ),
        plan=plan,
    )
    apply_operation(root, create, owner)
    revised = plan.model_copy(update={"rationale": "Проверено до запуска"})
    _apply(
        root, owner, ReviseWorkPlanRequest, work_id=parent, expected_plan_revision=1, plan=revised
    )
    stale = _refusal(
        lambda: _apply(
            root,
            owner,
            ReviseWorkPlanRequest,
            work_id=parent,
            expected_plan_revision=1,
            plan=plan,
        )
    )
    resources: dict[str, Path] = {}
    for name, work in (("a", a), ("b", b)):
        workspace = base / f"workspace-{name}"
        workspace.mkdir()
        resources[name] = workspace
        _apply(
            root,
            owner,
            CreateResourceRequest,
            resource_id=uuid4(),
            work_id=work,
            state=ResourceState(label=f"Synthetic {name}", root=workspace, limit_units=10000),
        )
    return {
        "root": root,
        "owner": owner,
        "activity": activity,
        "source": source,
        "method": ref,
        "parent": parent,
        "a": a,
        "b": b,
        "create": create,
        "plan": revised,
        "resources": resources,
        "schemas": schemas,
        "stale_plan_refusal": stale,
    }


def _assign(root: Path, owner: LocalAuthority, work: UUID, previous: UUID | None = None) -> Any:
    snapshot = read_execution(root, work, owner)
    return AssignAttemptRequest(
        operation_id=uuid4(),
        space_id=owner.space_id,
        actor=ACTOR,
        attempt_id=uuid4(),
        work_id=work,
        expected_work_revision=snapshot.work.revision,
        resource_id=snapshot.resources[0].resource_id,
        expected_resource_revision=snapshot.resources[0].revision,
        session_id=uuid4(),
        previous_attempt_id=previous,
        executor_version=EXECUTOR_VERSION,
    )


def _issue(root: Path, owner: LocalAuthority, parent: UUID, child: UUID, plan: int) -> Any:
    return IssueChildWorkRequest(
        operation_id=uuid4(),
        space_id=owner.space_id,
        actor=ACTOR,
        parent_work_id=parent,
        work_id=child,
        expected_plan_revision=plan,
        expected_work_revision=read_work(root, child, owner).revision,
    )


def _accept(bridge: Bridge, session: UUID, basis: str) -> dict[str, object]:
    preview = bridge.accept_preview(session)
    return bridge.accept(session, UUID(str(preview["nonce"])), basis)


def _refusing_composite(
    base: Path, root: Path, owner: LocalAuthority, data: dict[str, Any]
) -> dict[str, Any]:
    """An independent composite child whose Decision dependency changes after assignment."""

    decision = uuid4()
    _apply(
        root,
        owner,
        CreateDecisionRequest,
        decision_id=decision,
        state=DecisionState(
            statement="Синтетическое решение ветки",
            effect="require_grant",
            actions=("space.inspect",),
            subjects=("synthetic-nobody",),
        ),
    )
    plan = cast(WorkPlan, data["plan"])
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
    create = cast(CreateCompositeWorkRequest, data["create"])
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
    apply_operation(root, _issue(root, owner, parent, first.work_id, 1), owner)
    output = uuid4()
    _apply(
        root,
        owner,
        CreateArtifactRequest,
        artifact_id=output,
        media_type="text/plain",
        content=b"Independent synthetic check",
    )
    linked = _apply(
        root,
        owner,
        LinkWorkOutputRequest,
        work_id=first.work_id,
        expected_revision=read_work(root, first.work_id, owner).revision,
        output=LinkedOutput(slot="checked", artifact=ArtifactRef(artifact_id=output, revision=1)),
    )
    _apply(
        root,
        owner,
        AcceptWorkRequest,
        work_id=first.work_id,
        expected_revision=linked.result["revision"],
        basis="Independent synthetic acceptance",
    )
    apply_operation(root, _issue(root, owner, parent, gated.work_id, 1), owner)
    workspace = base / "workspace-c"
    workspace.mkdir()
    _apply(
        root,
        owner,
        CreateResourceRequest,
        resource_id=uuid4(),
        work_id=gated.work_id,
        state=ResourceState(label="Synthetic c", root=workspace, limit_units=10000),
    )
    assignment = _assign(root, owner, gated.work_id)
    apply_operation(root, assignment, owner)
    _apply(
        root,
        owner,
        ReviseDecisionRequest,
        decision_id=decision,
        expected_revision=1,
        state=DecisionState(
            statement="Синтетическое решение ветки изменено",
            effect="require_grant",
            actions=("space.inspect",),
            subjects=("synthetic-nobody",),
        ),
    )
    return {
        "parent": parent,
        "first": first.work_id,
        "work": gated.work_id,
        "attempt": assignment.attempt_id,
        "workspace": workspace,
    }


def _clean(root: Path, markers: tuple[str, ...]) -> dict[str, list[str]]:
    managed = root / ".zara-core"
    return {marker: found for marker in markers if (found := _contains(managed, marker))}


def run(output: Path, pi_runtime: Path) -> dict[str, object]:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    markers = Markers()
    provider = SyntheticProvider(markers.responses())
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    report: dict[str, object] = {
        "python": sys.version,
        "sqlite": importlib.import_module("sqlite3").sqlite_version,
        "foundation_module": str(Path(foundation.__file__).resolve()),
        "extension_resource": str(
            Path(str(files("zaratustra.pi_adapter").joinpath("extension.ts"))).resolve()
        ),
    }
    try:
        data = _space(output)
        root, owner = cast(Path, data["root"]), cast(LocalAuthority, data["owner"])
        parent, a, b = cast(UUID, data["parent"]), cast(UUID, data["a"]), cast(UUID, data["b"])
        activity = cast(UUID, data["activity"])
        import dbos

        report["dbos_module"] = str(Path(dbos.__file__).resolve())
        report["schemas"] = data["schemas"]
        report["stale_plan_revision_refusal"] = data["stale_plan_refusal"]
        runtime = pi_runtime.resolve()
        package = runtime / "node_modules" / "@earendil-works" / "pi-coding-agent"
        report["pi_version"] = json.loads((package / "package.json").read_text("utf-8"))["version"]
        config = AssignedConfig(
            space=root,
            workspace=cast(dict[str, Path], data["resources"])["a"],
            pi_cli=package / "dist" / "bundle" / "cli.js",
            pi_runtime=runtime,
            node="node",
            provider_profile="local-completions",
            provider_base_url=f"http://127.0.0.1:{provider.server_port}/v1",
            provider_id="zara-synthetic",
            model_id="synthetic-model",
            context_window=4096,
            max_tokens=512,
            reserve_units=1000,
            limit_units=10000,
            offline=True,
        )
        timeline: list[dict[str, object]] = []

        def mark(step: str) -> None:
            entry: dict[str, object] = {"step": step}
            for name, work in (("a", a), ("b", b), ("parent", parent)):
                entry[name] = _state(root, owner, work)
            timeline.append(entry)

        mark("created")
        early_issue = _refusal(
            lambda: apply_operation(root, _issue(root, owner, parent, b, 2), owner)
        )
        early_assign = _refusal(lambda: apply_operation(root, _assign(root, owner, b), owner))
        early = read_execution(root, b, owner)
        report["early_b"] = {
            "issue": early_issue,
            "assign": early_assign,
            "attempts": len(early.attempts),
            "outbox": len(early.outbox),
            "http": len(provider.digests),
        }
        issue_a = _issue(root, owner, parent, a, 2)
        issued = apply_operation(root, issue_a, owner)
        report["issue_a"] = {
            "replay_same_receipt": apply_operation(root, issue_a, owner) == issued,
            "second_issue": _refusal(
                lambda: apply_operation(
                    root, issue_a.model_copy(update={"operation_id": uuid4()}), owner
                )
            ),
        }
        mark("a issued")
        assign_a = _assign(root, owner, a)
        assigned = apply_operation(root, assign_a, owner)
        report["assignment_a"] = {
            "plan": assigned.result["plan"],
            "replay_same_receipt": apply_operation(root, assign_a, owner) == assigned,
            "second_assignment": _refusal(
                lambda: apply_operation(
                    root, _assign(root, owner, a, previous=assign_a.attempt_id), owner
                )
            ),
        }
        mark("a assigned")
        result: dict[str, object] = {}

        def execute() -> None:
            try:
                result["workflow"] = run_assigned(config, owner, assign_a.attempt_id)
            except BaseException as error:
                result["error"] = repr(error)

        a_recorder = StatusRecorder(root, owner, a).__enter__()
        worker = threading.Thread(target=execute, daemon=True)
        worker.start()
        deadline = time.monotonic() + 60
        wait_record = None
        while time.monotonic() < deadline:
            try:
                snapshot = read_execution(root, a, owner)
            except FoundationError as error:
                if error.code not in ("busy", "storage"):
                    raise
                time.sleep(0.1)
                continue
            wait_record = next((item for item in snapshot.waits if item.status == "open"), None)
            if wait_record is not None:
                break
            if "error" in result:
                raise RuntimeError(str(result["error"]))
            time.sleep(0.1)
        if wait_record is None:
            raise TimeoutError("Assigned child did not save its question")
        mark("a waiting")
        http_before_answer = len(provider.digests)
        # run_assigned already delivered the launch; a second delivery must not re-issue A.
        redelivered = deliver_outbox(root, owner)
        report["delivery"] = {
            "launch_redelivered": list(map(str, redelivered)),
            "workflows_for_a": sum(
                1 for item in _workflows(root) if item.get("attempt_id") == str(assign_a.attempt_id)
            ),
            "http_after_redelivery": len(provider.digests),
        }
        shown_waiting = status_via_pi(
            root,
            cast(dict[str, Path], data["resources"])["a"],
            owner,
            config,
            activity,
            a,
            (": waiting", markers.question, f"Plan {parent}@2", "role a"),
        )
        report["interactive_waiting"] = {
            "shown": True,
            "summary": shown_waiting.splitlines()[:2],
            "http_during_status": len(provider.digests) - http_before_answer,
        }
        interactive = Bridge(
            root,
            owner,
            cast(dict[str, Path], data["resources"])["a"],
            10000,
            deliver_answer=lambda outbox_id: deliver_outbox(root, owner, outbox_id),
        )
        session = uuid4()
        interactive.connect(session)
        interactive.select(session, activity, a)
        first_answer = interactive.answer_wait(session, wait_record.wait_id, markers.answer)
        duplicate_answer = interactive.answer_wait(session, wait_record.wait_id, markers.answer)
        worker.join(timeout=90)
        if worker.is_alive():
            raise TimeoutError("DBOS workflow for A did not finish")
        if "error" in result:
            raise RuntimeError(str(result["error"]))
        a_recorder.__exit__()
        after_a = read_execution(root, a, owner)
        mark("a published")
        report["a_run"] = {
            "workflow": result["workflow"],
            "http_before_answer": http_before_answer,
            "duplicate_answer_same_receipt": first_answer == duplicate_answer,
            "output": _text(after_a.outputs[0]),
            "invocations": [item.status for item in after_a.invocations],
            "digests_match_http": [item.request_sha256 for item in after_a.invocations]
            == provider.digests,
            "assignment": after_a.assignments[0].status,
            "work_record": after_a.work.state.status,
            "outbox": [item.kind + ":" + item.status for item in after_a.outbox],
            "http_total": len(provider.digests),
            "observed_states": a_recorder.seen,
        }
        a_accept = _accept(interactive, session, "Сведения проверены владельцем синтетически")
        mark("a accepted")
        issue_b = _issue(root, owner, parent, b, 2)
        issued_b = apply_operation(root, issue_b, owner)
        b_inputs = read_work(root, b, owner).state.inputs
        mark("b issued")
        assign_b = _assign(root, owner, b)
        apply_operation(root, assign_b, owner)
        b_config = AssignedConfig(
            **{**config.__dict__, "workspace": cast(dict[str, Path], data["resources"])["b"]}
        )
        with StatusRecorder(root, owner, b) as b_recorder:
            b_workflow = run_assigned(b_config, owner, assign_b.attempt_id)
        after_b = read_execution(root, b, owner)
        mark("b published")
        b_session = uuid4()
        b_bridge = Bridge(root, owner, cast(dict[str, Path], data["resources"])["b"], 10000)
        b_bridge.connect(b_session)
        b_bridge.select(b_session, activity, b)
        b_accept = _accept(b_bridge, b_session, "Итог принят синтетически")
        mark("b accepted")
        report["b_run"] = {
            "issued_inputs": [ref.model_dump(mode="json") for ref in b_inputs],
            "a_output_is_b_input": ArtifactRef(
                artifact_id=after_a.outputs[0].artifact_id, revision=after_a.outputs[0].revision
            )
            in b_inputs,
            "issue_receipt_inputs": issued_b.result["inputs"],
            "workflow": b_workflow,
            "output": _text(after_b.outputs[0]),
            "invocations": [item.status for item in after_b.invocations],
            "http_total": len(provider.digests),
            "observed_states": b_recorder.seen,
        }
        premature = _refusal(
            lambda: _apply(
                root,
                owner,
                AcceptWorkRequest,
                work_id=parent,
                expected_revision=read_work(root, parent, owner).revision,
                basis="Premature synthetic acceptance",
            )
        )
        confirmations: dict[str, OperationReceipt] = {}
        for key, state in (("checked", after_a), ("final", after_b)):
            evidence = ArtifactRef(
                artifact_id=state.outputs[0].artifact_id, revision=state.outputs[0].revision
            )
            confirmations[key] = _apply(
                root,
                owner,
                ConfirmObligationRequest,
                work_id=parent,
                key=key,
                expected_plan_revision=2,
                expected_obligation_revision=1,
                evidence=evidence,
                basis=f"Синтетическое подтверждение {key}",
            )
        mark("obligations confirmed")
        b_output = ArtifactRef(
            artifact_id=after_b.outputs[0].artifact_id, revision=after_b.outputs[0].revision
        )
        _apply(
            root,
            owner,
            LinkWorkOutputRequest,
            work_id=parent,
            expected_revision=read_work(root, parent, owner).revision,
            output=LinkedOutput(slot="final", artifact=b_output),
        )
        parent_accept = AcceptWorkRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor=ACTOR,
            work_id=parent,
            expected_revision=read_work(root, parent, owner).revision,
            basis="Отдельное синтетическое принятие родителя",
        )
        parent_receipt = apply_operation(root, parent_accept, owner)
        mark("parent accepted")
        report["parent"] = {
            "premature_acceptance": premature,
            "confirmations": {key: value.result["status"] for key, value in confirmations.items()},
            "status": parent_receipt.result["status"],
            "replay_same_receipt": apply_operation(root, parent_accept, owner) == parent_receipt,
            "activity": read_activity(root, activity, owner).state.status,
        }

        refused = _refusing_composite(output, root, owner, data)
        http_before_refusal = len(provider.digests)
        c_config = AssignedConfig(**{**config.__dict__, "workspace": refused["workspace"]})
        refusal_code = _refusal(lambda: run_assigned(c_config, owner, refused["attempt"]))
        refused_state = read_execution(root, refused["work"], owner)
        report["subject_refusal"] = {
            "code": refusal_code,
            "http_delta": len(provider.digests) - http_before_refusal,
            "invocations": len(refused_state.invocations),
            "assignment": refused_state.assignments[0].status,
            "attempt": refused_state.attempts[0].status,
            "status": _state(root, owner, refused["work"]),
            "pi_home_created": (
                root / ".zara-core" / "pi-rpc-home" / str(refused["attempt"])
            ).exists(),
        }

        reopen_data = {
            "space": str(root),
            "parent": str(parent),
            "a": str(a),
            "b": str(b),
            "activity": str(activity),
            "a_accept": str(a_accept["operation_id"]),
            "b_accept": str(b_accept["operation_id"]),
            "parent_accept": str(parent_accept.operation_id),
        }
        reopened = _reopen_in_new_process(reopen_data)
        report["reopen"] = reopened
        assert reopened == reopen(reopen_data) | {"module": reopened["module"]}
        shown_after = status_via_pi(
            root,
            cast(dict[str, Path], data["resources"])["b"],
            owner,
            config,
            activity,
            parent,
            (": succeeded", "child a: succeeded", "child b: succeeded", "obligation final"),
        )
        report["interactive_after_reopen"] = shown_after.splitlines()[:5]
        report["timeline"] = timeline

        report["technical_copies"] = _technical_copies(
            root,
            markers.all()
            + (
                "Проверено до запуска",
                "Проверить сведения",
                "Составить итог",
                "Проверить синтетические сведения",
            ),
        )
        backup = create_assigned_backup(root, uuid4(), owner)
        restored_root = output / "restored-space"
        restored_root.mkdir()
        recovery = authorize_recovery(actor=ACTOR, source_ref="synthetic-restore-console")
        restored = restore_backup(backup.package, restored_root, recovery)
        apply_operation(
            restored_root,
            RecoverRequest(
                operation_id=uuid4(),
                space_id=owner.space_id,
                actor=ACTOR,
                decision_id=uuid4(),
                grant_id=uuid4(),
            ),
            recovery,
        )
        restored_owner = authorize_local(restored_root, actor=ACTOR, source_ref="synthetic-epoch-2")
        restored_a = read_execution(restored_root, a, restored_owner)
        report["backup_restore"] = {
            "format": backup.manifest.format_version,
            "schema": backup.manifest.schema_version,
            "technical": cast(Any, backup.manifest.technical_versions).model_dump(mode="json"),
            "executor_sha256": backup.manifest.executor_sha256,
            "pi_files": len(backup.manifest.pi_rpc_home_files),
            "restored_epoch": restored.execution_epoch,
            "restored_statuses": {
                name: read_work_status(restored_root, work, restored_owner).status
                for name, work in (("parent", parent), ("a", a), ("b", b))
            },
            "restored_pins": [pin.plan_revision for pin in cast(Any, restored_a.composition).pins],
            "restored_question": restored_a.waits[0].question == markers.question,
            "restored_outbox": sorted({item.status for item in restored_a.outbox}),
            "old_executor_inert": (
                restored_root / ".zara-core" / "executor-restored.sqlite3"
            ).is_file(),
        }

        report["deletion"] = _delete_sequence(
            root, owner, data, after_a, after_b, wait_record, markers, backup.package, refused
        )
        restored_deleted = _delete_restored(restored_root, restored_owner, a, parent)
        report["restored_deletion"] = restored_deleted
        report["http_total"] = len(provider.digests)
        report["status"] = "passed"
        return report
    finally:
        provider.shutdown()
        provider.server_close()
        provider_thread.join(timeout=5)


def _delete(root: Path, owner: LocalAuthority, request_type: type[Any], **fields: Any) -> None:
    _apply(root, owner, request_type, **fields)


def _delete_sequence(
    root: Path,
    owner: LocalAuthority,
    data: dict[str, Any],
    after_a: Any,
    after_b: Any,
    wait_record: Any,
    markers: Markers,
    old_backup: Path,
    refused: dict[str, Any],
) -> dict[str, object]:
    parent, a, b = cast(UUID, data["parent"]), cast(UUID, data["a"]), cast(UUID, data["b"])
    steps: dict[str, object] = {}
    a_output = after_a.outputs[0].artifact_id
    _delete(root, owner, DeleteArtifactRequest, artifact_id=a_output, expected_revision=1)
    status = complete_assigned_deletions(root, owner)
    steps["a_output_artifact"] = {
        "sanitized": status.live_store_sanitized,
        "old_backup_removed": not old_backup.exists(),
        "workflows": _workflows(root),
        "pi_homes": sorted(
            item.name for item in (root / ".zara-core" / "pi-rpc-home").glob("*") if item.is_dir()
        ),
        "obligations": {
            key: read_obligation(root, parent, key, owner).status for key in ("checked", "final")
        },
        "plan_readable": read_work_plan(root, parent, owner).revision,
        "remaining_markers": _clean(root, (markers.a_result,)),
    }
    restarted = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys, json; from pathlib import Path; from uuid import UUID; "
            "from zaratustra.foundation import authorize_local, read_obligation, "
            "read_work_status; p=Path(sys.argv[1]); o=authorize_local(p, actor='owner', "
            "source_ref='restart'); print(json.dumps({"
            "'checked': read_obligation(p, UUID(sys.argv[2]), 'checked', o).status, "
            "'b': read_work_status(p, UUID(sys.argv[3]), o).status}))",
            str(root),
            str(parent),
            str(b),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    if restarted.returncode:
        raise AssertionError(restarted.stderr)
    steps["restart_between_deletions"] = json.loads(restarted.stdout.strip().splitlines()[-1])
    b_output = after_b.outputs[0].artifact_id
    _delete(
        root,
        owner,
        DeleteWorkRequest,
        work_id=b,
        expected_revision=read_work(root, b, owner).revision,
    )
    _delete(root, owner, DeleteArtifactRequest, artifact_id=b_output, expected_revision=1)
    status = complete_assigned_deletions(root, owner)
    steps["child_b"] = {
        "sanitized": status.live_store_sanitized,
        "remaining_markers": _clean(root, (markers.b_result,)),
        "parent_obligation_final": read_obligation(root, parent, "final", owner).status,
    }
    partial = wait_record.partial_refs[0].artifact_id
    _delete(
        root,
        owner,
        DeleteWorkRequest,
        work_id=a,
        expected_revision=read_work(root, a, owner).revision,
    )
    _delete(root, owner, DeleteArtifactRequest, artifact_id=partial, expected_revision=1)
    status = complete_assigned_deletions(root, owner)
    steps["child_a"] = {
        "sanitized": status.live_store_sanitized,
        "remaining_markers": _clean(root, markers.all()),
        "parent_obligation_checked": read_obligation(root, parent, "checked", owner).status,
        "independent_refused_child": read_work_status(root, refused["work"], owner).status,
        "independent_plan_revision": read_work_plan(root, refused["parent"], owner).revision,
    }
    _delete(
        root,
        owner,
        DeleteWorkRequest,
        work_id=parent,
        expected_revision=read_work(root, parent, owner).revision,
    )
    method = cast(MethodRef, data["method"])
    steps["shared_method_delete"] = _refusal(
        lambda: _delete(
            root,
            owner,
            DeleteMethodVersionRequest,
            method_id=method.method_id,
            version=method.version,
            checksum=method.checksum,
        )
    )
    status = complete_assigned_deletions(root, owner)
    clean_backup = create_assigned_backup(root, uuid4(), owner)
    steps["parent"] = {
        "sanitized": status.live_store_sanitized,
        "pending": status.pending_jobs,
        "remaining_markers": _clean(root, markers.all()),
        "new_backup_markers": {
            marker: found
            for marker in markers.all()
            if (found := _contains(clean_backup.package, marker))
        },
        "workflows": _workflows(root),
    }
    return steps


def _delete_restored(
    restored_root: Path, owner: LocalAuthority, a: UUID, parent: UUID
) -> dict[str, object]:
    _delete(
        restored_root,
        owner,
        DeleteWorkRequest,
        work_id=a,
        expected_revision=read_work(restored_root, a, owner).revision,
    )
    status = complete_assigned_deletions(restored_root, owner)
    return {
        "sanitized": status.live_store_sanitized,
        "inert_executor_removed": not (
            restored_root / ".zara-core" / "executor-restored.sqlite3"
        ).exists(),
        "inert_pi_home_removed": not (
            restored_root / ".zara-core" / "pi-rpc-home-restored"
        ).exists(),
        "parent_obligation_checked": read_obligation(
            restored_root, parent, "checked", owner
        ).status,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pi-runtime", type=Path)
    parser.add_argument("--reopen")
    args = parser.parse_args()
    if args.reopen is not None:
        print(json.dumps(reopen(json.loads(args.reopen)), ensure_ascii=False))
        return 0
    if args.output is None or args.pi_runtime is None:
        parser.error("Supply --output and --pi-runtime")
    report = run(args.output, args.pi_runtime)
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
