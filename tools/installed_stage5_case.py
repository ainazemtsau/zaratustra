"""Standalone installed-wheel Core, DBOS and ordinary Pi RPC localhost trial."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4, uuid5

if os.name != "nt":
    raise SystemExit("This pinned SQLite installed trial currently requires Windows")
sqlite_dll = Path(os.environ["ZARATUSTRA_SQLITE_DLL"]).resolve()
_sqlite_library = ctypes.WinDLL(str(sqlite_dll))
import sqlite3  # noqa: E402

if sqlite3.sqlite_version != "3.53.3":
    raise SystemExit(f"Unsupported installed SQLite: {sqlite3.sqlite_version}")

import zaratustra  # noqa: E402
import zaratustra.pi_adapter.assigned as assigned  # noqa: E402
from zaratustra.foundation import (  # noqa: E402
    ActivityState,
    ArtifactRef,
    AssignAttemptRequest,
    BootstrapRequest,
    ClaimAttemptLaunchRequest,
    CreateActivityRequest,
    CreateArtifactRequest,
    CreateResourceRequest,
    CreateWorkRequest,
    FoundationError,
    OutputContract,
    ResourceState,
    WaitRecord,
    WorkState,
    apply_operation,
    authorize_local,
    initialize_space,
    read_execution,
    upgrade_continuation_space,
    upgrade_execution_space,
    upgrade_space,
)
from zaratustra.pi_adapter import Bridge  # noqa: E402
from zaratustra.pi_adapter.assigned import (  # noqa: E402
    EXECUTOR_VERSION,
    AssignedConfig,
    deliver_outbox,
    run_assigned,
)

WAIT_TEXT = json.dumps(
    {
        "zara": "wait",
        "partial": "The fictional note has a heading.",
        "question": "Which fictional code should the summary use?",
        "remainder": "Add the selected code to the fictional summary.",
    }
)
FINAL_TEXT = json.dumps({"zara": "final", "text": "The fictional note uses code A."})


class Provider(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), Handler)
        self.digests: list[str] = []
        self.guard = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server: Provider

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(size)
        with self.server.guard:
            self.server.digests.append(hashlib.sha256(body).hexdigest().upper())
            number = len(self.server.digests)
        text = WAIT_TEXT if number == 1 else FINAL_TEXT
        chunks = [
            {
                "id": "installed",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            },
            {
                "id": "installed",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
            },
            {
                "id": "installed",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            },
            {
                "id": "installed",
                "object": "chat.completion.chunk",
                "choices": [],
                "usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140},
            },
        ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def make_space(base: Path) -> dict[str, str]:
    root = base / "space"
    root.mkdir(parents=True)
    workspace = base / "fictional-workspace"
    workspace.mkdir()
    info = initialize_space(root)
    owner = authorize_local(root, actor="owner", source_ref="installed-synthetic-console")
    apply_operation(
        root,
        BootstrapRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        owner,
    )
    assert upgrade_space(root, owner).schema_version == 2
    assert upgrade_execution_space(root, owner).schema_version == 3
    assert upgrade_continuation_space(root, owner).schema_version == 4
    artifact_id, activity_id, work_id, resource_id, attempt_id, session_id = (
        uuid4() for _ in range(6)
    )
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="owner",
            artifact_id=artifact_id,
            media_type="text/plain",
            content=b"fictional input",
        ),
        owner,
    )
    apply_operation(
        root,
        CreateActivityRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="owner",
            activity_id=activity_id,
            state=ActivityState(title="Fictional activity", goal="Continue safely"),
        ),
        owner,
    )
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="owner",
            work_id=work_id,
            state=WorkState(
                activity_id=activity_id,
                goal="Summarize fictional material",
                inputs=(ArtifactRef(artifact_id=artifact_id, revision=1),),
                expected_outputs=(OutputContract(slot="summary", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    apply_operation(
        root,
        CreateResourceRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="owner",
            work_id=work_id,
            resource_id=resource_id,
            state=ResourceState(label="Fictional directory", root=workspace, limit_units=10000),
        ),
        owner,
    )
    apply_operation(
        root,
        AssignAttemptRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="owner",
            attempt_id=attempt_id,
            work_id=work_id,
            expected_work_revision=1,
            resource_id=resource_id,
            expected_resource_revision=1,
            session_id=session_id,
            executor_version=EXECUTOR_VERSION,
        ),
        owner,
    )
    return {
        "space": str(root),
        "workspace": str(workspace),
        "space_id": str(info.space_id),
        "activity_id": str(activity_id),
        "work_id": str(work_id),
        "resource_id": str(resource_id),
        "attempt_id": str(attempt_id),
        "session_id": str(session_id),
    }


def configuration(data: dict[str, str]) -> AssignedConfig:
    runtime = Path(data["pi_runtime"])
    return AssignedConfig(
        space=Path(data["space"]),
        workspace=Path(data["workspace"]),
        pi_cli=runtime
        / "node_modules"
        / "@earendil-works"
        / "pi-coding-agent"
        / "dist"
        / "bundle"
        / "cli.js",
        pi_runtime=runtime,
        node="node",
        provider_profile="local-completions",
        provider_base_url=data["provider_url"],
        provider_id="zara-synthetic",
        model_id="synthetic-model",
        context_window=4096,
        max_tokens=512,
        reserve_units=1000,
        limit_units=10000,
        offline=True,
    )


def host(case: Path) -> int:
    data = json.loads(case.read_text(encoding="utf-8"))
    assert assigned.__file__ is not None
    print(json.dumps({"host_assigned_module": str(Path(assigned.__file__).resolve())}), flush=True)
    original = vars(assigned)["subprocess"]
    real_popen = original.Popen

    def observe(command: object, *args: object, **kwargs: object) -> object:
        child = real_popen(command, *args, **kwargs)
        if isinstance(command, list) and str(configuration(data).pi_cli) in [
            str(item) for item in command
        ]:
            (case.parent / "pi-child-pid.json").write_text(
                json.dumps({"pid": child.pid}), encoding="utf-8", newline="\n"
            )
        return child

    vars(assigned)["subprocess"] = SimpleNamespace(
        Popen=observe,
        PIPE=original.PIPE,
        DEVNULL=original.DEVNULL,
        TimeoutExpired=original.TimeoutExpired,
    )
    authority = authorize_local(
        Path(data["space"]), actor="owner", source_ref="installed-synthetic-host"
    )
    try:
        outcome = run_assigned(configuration(data), authority, UUID(data["attempt_id"]))
    except FoundationError as error:
        print(json.dumps({"error": error.code}), flush=True)
        return 1
    print(json.dumps({"outcome": outcome}), flush=True)
    return 0


def start(script: Path, data: dict[str, str], case_dir: Path) -> subprocess.Popen[bytes]:
    case_dir.mkdir()
    case = case_dir / "case.json"
    case.write_text(json.dumps(data), encoding="utf-8", newline="\n")
    log = (case_dir / "host.log").open("wb")
    process = subprocess.Popen(
        [sys.executable, "-I", str(script), "--host", str(case)],
        cwd=case_dir,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    log.close()
    return process


def wait_for_question(data: dict[str, str], provider: Provider) -> WaitRecord:
    root = Path(data["space"])
    owner = authorize_local(root, actor="owner", source_ref="installed-synthetic-console")
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        state = read_execution(root, UUID(data["work_id"]), owner)
        waits = [item for item in state.waits if item.status == "open"]
        if waits and len(provider.digests) == 1:
            return waits[0]
        time.sleep(0.1)
    raise TimeoutError("Installed ordinary Pi RPC did not save one addressed question")


def conflict_on_same_resource(data: dict[str, str]) -> str:
    root = Path(data["space"])
    owner = authorize_local(root, actor="owner", source_ref="installed-synthetic-console")
    state = read_execution(root, UUID(data["work_id"]), owner)
    work_id, resource_id = uuid4(), uuid4()
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor="owner",
            work_id=work_id,
            state=WorkState(
                activity_id=state.activity.activity_id,
                goal="Conflicting fictional Work",
                expected_outputs=(OutputContract(slot="summary", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    apply_operation(
        root,
        CreateResourceRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor="owner",
            work_id=work_id,
            resource_id=resource_id,
            state=ResourceState(
                label="Same fictional directory",
                root=Path(data["workspace"]),
                limit_units=10000,
            ),
        ),
        owner,
    )
    try:
        apply_operation(
            root,
            AssignAttemptRequest(
                operation_id=uuid4(),
                space_id=owner.space_id,
                actor="owner",
                attempt_id=uuid4(),
                work_id=work_id,
                expected_work_revision=1,
                resource_id=resource_id,
                expected_resource_revision=1,
                session_id=uuid4(),
                executor_version=EXECUTOR_VERSION,
            ),
            owner,
        )
    except FoundationError as error:
        return error.code
    raise AssertionError("Unknown Attempt released its exclusive resource")


def cleanup_host(process: subprocess.Popen[bytes], case_dir: Path) -> None:
    if process.poll() is None:
        process.kill()
        process.wait(timeout=10)
    pid_file = case_dir / "pi-child-pid.json"
    if pid_file.is_file():
        pid = int(json.loads(pid_file.read_text(encoding="utf-8"))["pid"])
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def run(base: Path, venv: Path, checkout: Path, runtime: Path) -> dict[str, object]:
    base, venv, checkout, runtime = (
        base.resolve(),
        venv.resolve(),
        checkout.resolve(),
        runtime.resolve(),
    )
    assert not base.is_relative_to(checkout)
    assert not Path.cwd().resolve().is_relative_to(checkout)
    assert not any(Path(entry).resolve().is_relative_to(checkout) for entry in sys.path if entry)
    package = Path(zaratustra.__file__).resolve()
    assert package.is_relative_to(venv)
    extension = Path(str(files("zaratustra.pi_adapter").joinpath("extension.ts"))).resolve()
    assert extension.is_relative_to(venv) and extension.is_file()
    import dbos

    assert dbos.__file__ is not None
    dbos_path = Path(dbos.__file__).resolve()
    assert dbos_path.is_relative_to(venv)
    module_paths = {
        name: str(Path(cast(str, module.__file__)).resolve())
        for name, module in tuple(sys.modules.items())
        if (name == "zaratustra" or name.startswith("zaratustra."))
        and getattr(module, "__file__", None)
    }
    assert module_paths and all(Path(value).is_relative_to(venv) for value in module_paths.values())
    package_meta = json.loads(
        (
            runtime / "node_modules" / "@earendil-works" / "pi-coding-agent" / "package.json"
        ).read_text(encoding="utf-8")
    )
    assert package_meta["name"] == "@earendil-works/pi-coding-agent"
    assert package_meta["version"] == "0.87.0"
    provider = Provider()
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    script = Path(__file__).resolve()
    assert not script.is_relative_to(checkout)
    normal_host: subprocess.Popen[bytes] | None = None
    unknown_host: subprocess.Popen[bytes] | None = None
    try:
        normal_dir = base / "normal"
        normal_dir.mkdir()
        normal = make_space(normal_dir)
        normal["pi_runtime"] = str(runtime)
        normal["provider_url"] = f"http://127.0.0.1:{provider.server_port}/v1"
        normal_host = start(script, normal, normal_dir / "host")
        wait = wait_for_question(normal, provider)
        root = Path(normal["space"])
        owner = authorize_local(root, actor="owner", source_ref="installed-synthetic-console")
        bridge = Bridge(
            root,
            owner,
            Path(normal["workspace"]),
            10000,
            deliver_answer=lambda outbox_id: deliver_outbox(root, owner, outbox_id),
        )
        session = uuid4()
        bridge.connect(session)
        bridge.select(session, UUID(normal["activity_id"]), UUID(normal["work_id"]))
        shown = cast(list[dict[str, object]], bridge.snapshot(session)["waits"])
        assert any(
            row["wait_id"] == str(wait.wait_id) and row["question"] == wait.question
            for row in shown
        )
        assert bridge.answer_wait(session, wait.wait_id, "Code A") == bridge.answer_wait(
            session, wait.wait_id, "Code A"
        )
        assert normal_host.wait(timeout=50) == 0
        normal_log = (normal_dir / "host" / "host.log").read_text(encoding="utf-8")
        assert '"outcome": "proposed"' in normal_log
        host_path = Path(
            json.loads(
                next(
                    line
                    for line in normal_log.splitlines()
                    if line.startswith('{"host_assigned_module":')
                )
            )["host_assigned_module"]
        ).resolve()
        assert host_path.is_relative_to(venv)
        state = read_execution(root, UUID(normal["work_id"]), owner)
        assert state.work.state.status == "proposed"
        assert state.outputs[0].content == b"The fictional note uses code A."
        assert [item.status for item in state.invocations] == ["answered", "answered"]
        assert [item.request_sha256 for item in state.invocations] == provider.digests
        assert len(provider.digests) == 2
        assert state.committed_units == 280 and state.held_units == 0
        assert state.assignments[0].status == "stopped"

        unknown_dir = base / "unknown"
        unknown_dir.mkdir()
        unknown = make_space(unknown_dir)
        unknown["pi_runtime"] = str(runtime)
        unknown["provider_url"] = normal["provider_url"]
        unknown_root = Path(unknown["space"])
        unknown_owner = authorize_local(
            unknown_root, actor="owner", source_ref="installed-synthetic-console"
        )
        attempt = UUID(unknown["attempt_id"])
        apply_operation(
            unknown_root,
            ClaimAttemptLaunchRequest(
                operation_id=uuid5(attempt, "rpc-launch-claim"),
                space_id=unknown_owner.space_id,
                actor="owner",
                attempt_id=attempt,
                work_id=UUID(unknown["work_id"]),
                session_id=UUID(unknown["session_id"]),
                expected_assignment_revision=1,
                claim_nonce=uuid4(),
            ),
            unknown_owner,
        )
        unknown_host = start(script, unknown, unknown_dir / "host")
        assert unknown_host.wait(timeout=35) != 0
        unknown_log = (unknown_dir / "host" / "host.log").read_text(encoding="utf-8")
        assert "process_outcome_unknown" in unknown_log
        unknown_state = read_execution(unknown_root, UUID(unknown["work_id"]), unknown_owner)
        assert unknown_state.assignments[0].status == "unknown"
        assert len(provider.digests) == 2
        assert conflict_on_same_resource(unknown) == "resource_busy"
        return {
            "python_package": str(package),
            "dbos_module": str(dbos_path),
            "host_assigned_module": str(host_path),
            "extension_resource": str(extension),
            "module_paths": module_paths,
            "python_version": sys.version,
            "sqlite_version": sqlite3.sqlite_version,
            "dbos_version": importlib.metadata.version("dbos"),
            "pi_name": package_meta["name"],
            "pi_version": package_meta["version"],
            "pi_runtime": str(runtime),
            "normal": {
                "provider_calls": 2,
                "invocations": ["answered", "answered"],
                "committed_units": state.committed_units,
                "held_units": state.held_units,
                "output": state.outputs[0].content.decode("utf-8"),
                "work": state.work.state.status,
                "assignment": state.assignments[0].status,
                "duplicate_answer_one_receipt": True,
            },
            "claim_restart": {
                "provider_calls_after": len(provider.digests),
                "assignment": unknown_state.assignments[0].status,
                "conflicting_assignment": "resource_busy",
            },
        }
    finally:
        if normal_host is not None:
            cleanup_host(normal_host, base / "normal" / "host")
        if unknown_host is not None:
            cleanup_host(unknown_host, base / "unknown" / "host")
        provider.shutdown()
        provider.server_close()
        provider_thread.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--venv", type=Path)
    parser.add_argument("--checkout", type=Path)
    parser.add_argument("--pi-runtime", type=Path)
    parser.add_argument("--host", type=Path)
    args = parser.parse_args()
    if args.host is not None:
        return host(args.host)
    if any(value is None for value in (args.base, args.venv, args.checkout, args.pi_runtime)):
        parser.error("Supply base, venv, checkout and Pi runtime")
    report = run(args.base, args.venv, args.checkout, args.pi_runtime)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
