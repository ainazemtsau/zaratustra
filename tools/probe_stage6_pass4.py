"""Live Stage 6 pass 4 DBOS/Pi fault windows against a localhost synthetic provider.

Each case uses a new disposable schema 8 space. Fault markers and runner logs stay
in the selected output directory; inspect each failed state before any restart.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
import traceback
import types
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4, uuid5

# This import admits the configured SQLite DLL before development fixtures can
# import sqlite3. Runner and inspect children enter through this module too.
from zaratustra.foundation import (
    AcceptWorkRequest,
    ClaimAttemptLaunchRequest,
    CreateResourceRequest,
    FoundationError,
    IssueChildWorkRequest,
    LocalAuthority,
    MethodRef,
    ResourceState,
    apply_operation,
    authorize_local,
    read_execution,
    read_method_version,
    read_obligation,
    read_receipt,
    read_space,
    read_work,
    read_work_status,
    upgrade_parent_execution_space,
    upgrade_plan_revision_space,
)

# isort: split
from tests.zaratustra.foundation.test_plan_transfers import _pair
from tools.probe_stage5_faults import DropFirstProvider, competing_resource
from tools.probe_stage6_rpc import (
    Markers,
    SyntheticHandler,
    SyntheticProvider,
    _assign,
    _issue,
    _space,
)
from zaratustra.pi_adapter.assigned import (
    AssignedConfig,
    _record_stop,
    deliver_outbox,
    executor_database,
    run_assigned,
)


def _save(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )


def _config(data: dict[str, str]) -> AssignedConfig:
    return AssignedConfig(
        space=Path(data["space"]),
        workspace=Path(data["workspace"]),
        pi_cli=Path(data["pi_cli"]),
        pi_runtime=Path(data["pi_runtime"]),
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


def _case(base: Path, pi_runtime: Path, provider_url: str) -> Path:
    base.mkdir()
    seeded = _space(base)
    root = cast(Path, seeded["root"])
    owner = cast(LocalAuthority, seeded["owner"])
    assert upgrade_plan_revision_space(root, owner).schema_version == 7
    assert upgrade_parent_execution_space(root, owner).schema_version == 8
    work, parent = cast(UUID, seeded["a"]), cast(UUID, seeded["parent"])
    apply_operation(root, _issue(root, owner, parent, work, 2), owner)
    assignment = _assign(root, owner, work)
    receipt = apply_operation(root, assignment, owner)
    runtime = pi_runtime.resolve()
    data = {
        "space": str(root),
        "workspace": str(cast(dict[str, Path], seeded["resources"])["a"]),
        "pi_cli": str(
            runtime
            / "node_modules"
            / "@earendil-works"
            / "pi-coding-agent"
            / "dist"
            / "bundle"
            / "cli.js"
        ),
        "pi_runtime": str(runtime),
        "provider_url": provider_url,
        "parent": str(parent),
        "b": str(cast(UUID, seeded["b"])),
        "work_id": str(work),
        "attempt_id": str(assignment.attempt_id),
        "assignment_id": str(assignment.operation_id),
        "assignment_receipt": receipt.model_dump(mode="json"),
        "assignment_request": assignment.model_dump(mode="json"),
    }
    _save(base / "case.json", data)
    return base / "case.json"


def _parallel_cases(base: Path, pi_runtime: Path, provider_url: str) -> tuple[Path, Path]:
    base.mkdir()
    branches = _pair(base)
    root, space, owner, parent, works = branches
    assert upgrade_parent_execution_space(root, owner).schema_version == 8
    paths: list[Path] = []
    runtime = pi_runtime.resolve()
    for role in ("a", "b"):
        work = works[role]
        apply_operation(
            root,
            IssueChildWorkRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                parent_work_id=parent,
                work_id=work,
                expected_plan_revision=1,
                expected_work_revision=read_work(root, work, owner).revision,
            ),
            owner,
        )
        workspace = base / f"pass4-parallel-{role}"
        workspace.mkdir()
        apply_operation(
            root,
            CreateResourceRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                resource_id=uuid4(),
                work_id=work,
                state=ResourceState(
                    label=f"pass4-parallel-{role}", root=workspace, limit_units=10000
                ),
            ),
            owner,
        )
        assignment = _assign(root, owner, work)
        receipt = apply_operation(root, assignment, owner)
        directory = base / role
        directory.mkdir()
        data = {
            "space": str(root),
            "workspace": str(workspace.resolve()),
            "pi_cli": str(
                runtime
                / "node_modules"
                / "@earendil-works"
                / "pi-coding-agent"
                / "dist"
                / "bundle"
                / "cli.js"
            ),
            "pi_runtime": str(runtime),
            "provider_url": provider_url,
            "parent": str(parent),
            "work_id": str(work),
            "attempt_id": str(assignment.attempt_id),
            "assignment_id": str(assignment.operation_id),
            "assignment_receipt": receipt.model_dump(mode="json"),
            "assignment_request": assignment.model_dump(mode="json"),
        }
        case = directory / "case.json"
        _save(case, data)
        paths.append(case)
    return paths[0], paths[1]


def _workflow_rows(root: Path) -> list[dict[str, object]]:
    from dbos import DBOSClient

    database = executor_database(root)
    if not database.is_file():
        return []
    if "workflow_status" not in _executor_tables(root):
        return []
    client = DBOSClient(
        system_database_url=f"sqlite:///{database.resolve().as_posix()}",
        application_name="zaratustra-assigned-rpc",
        retry_connection_errors=False,
    )
    try:
        return [
            {
                "id": item.workflow_id,
                "status": item.status,
                "queue": item.queue_name,
                "app_version": item.app_version,
                "executor_id": item.executor_id,
                "attributes": dict(item.attributes or {}),
            }
            for item in client.list_workflows(
                name="zara-assigned-work-v1", load_input=False, load_output=False
            )
        ]
    finally:
        client.destroy()


def _executor_tables(root: Path) -> list[str]:
    from sqlite3 import connect

    database = executor_database(root)
    if not database.is_file():
        return []
    with closing(connect(database)) as connection:
        return sorted(
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        )


def _inspect(case_file: Path) -> dict[str, object]:
    data = cast(dict[str, str], json.loads(case_file.read_text(encoding="utf-8")))
    root, work, parent = Path(data["space"]), UUID(data["work_id"]), UUID(data["parent"])
    owner = authorize_local(root, actor="owner", source_ref="pass4-reopen")
    state = read_execution(root, work, owner)
    parent_state = read_execution(root, parent, owner)
    method = parent_state.work.state.method
    assert isinstance(method, MethodRef)
    obligations = {
        item.key: read_obligation(root, parent, item.key, owner).model_dump(mode="json")
        for item in read_method_version(root, method, owner).definition.obligations
    }
    receipt_ids = {
        "assignment": UUID(data["assignment_id"]),
        "claim": uuid5(UUID(data["attempt_id"]), "rpc-launch-claim"),
        "stop_request": uuid5(UUID(data["attempt_id"]), "rpc-stop-request"),
        "stop_observed": uuid5(UUID(data["attempt_id"]), "rpc-stop-observed"),
        "stop_unknown": uuid5(UUID(data["attempt_id"]), "rpc-stop-unknown"),
    }
    receipts: dict[str, object] = {}
    for name, operation_id in receipt_ids.items():
        try:
            receipts[name] = read_receipt(root, operation_id, owner).model_dump(mode="json")
        except FoundationError as error:
            receipts[name] = {"error": error.code}
    return {
        "space": read_space(root).model_dump(mode="json"),
        "work_status": read_work_status(root, work, owner).model_dump(mode="json"),
        "work": state.work.model_dump(mode="json"),
        "attempts": [item.model_dump(mode="json") for item in state.attempts],
        "assignments": [item.model_dump(mode="json") for item in state.assignments],
        "invocations": [item.model_dump(mode="json") for item in state.invocations],
        "outputs": [item.model_dump(mode="json") for item in state.outputs],
        "resources": [item.model_dump(mode="json") for item in state.resources],
        "parent_obligations": obligations,
        "parent_outputs": [item.model_dump(mode="json") for item in parent_state.outputs],
        "outbox": [item.model_dump(mode="json") for item in state.outbox],
        "held_units": state.held_units,
        "receipts": receipts,
        "workflows": _workflow_rows(root),
        "executor_tables": _executor_tables(root),
    }


def _fresh(case_file: Path, label: str) -> dict[str, object]:
    record = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "tools.probe_stage6_pass4",
            "--inspect",
            str(case_file),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    (case_file.parent / f"inspect-{label}.log").write_text(
        record.stdout + record.stderr, encoding="utf-8"
    )
    assert record.returncode == 0, (label, record.stdout, record.stderr)
    snapshot = cast(dict[str, object], json.loads(record.stdout.strip().splitlines()[-1]))
    _save(case_file.parent / f"inspect-{label}.json", snapshot)
    return snapshot


def _runner(case_file: Path, fault: str) -> int:
    import zaratustra.foundation.operations as operations
    import zaratustra.pi_adapter.assigned as assigned
    import zaratustra.pi_adapter.bridge as bridge_module

    data = cast(dict[str, str], json.loads(case_file.read_text(encoding="utf-8")))
    config = _config(data)
    owner = authorize_local(config.space, actor="owner", source_ref="pass4-runner")
    marker = case_file.parent / f"fault-{fault}.json"
    bridge_reply = bridge_module.BridgeHandler._reply

    def log_bridge_reply(handler: Any, status: Any, payload: object) -> None:
        if int(status) >= 400:
            with (case_file.parent / f"bridge-{fault}.errors.log").open(
                "a", encoding="utf-8"
            ) as log:
                log.write(
                    json.dumps({"status": int(status), "payload": payload}, default=str) + chr(10)
                )
        bridge_reply(handler, status, payload)

    bridge_module.BridgeHandler._reply = log_bridge_reply  # type: ignore[method-assign, assignment]
    original_rpc_line = assigned._rpc_line

    def log_rpc_line(process: Any) -> dict[str, Any]:
        event = original_rpc_line(process)
        with (case_file.parent / f"rpc-{fault}.events.log").open("a", encoding="utf-8") as log:
            log.write(json.dumps(event, ensure_ascii=False, default=str) + chr(10))
        return event

    vars(assigned)["_rpc_line"] = log_rpc_line
    if fault == "migration-interrupt":
        from sqlalchemy import event
        from sqlalchemy.engine import Engine

        def exit_after_migration_lookup(
            connection: object,
            cursor: object,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
        ) -> None:
            if "SELECT name FROM sqlite_master" in statement and "dbos_migrations" in statement:
                _save(marker, {"point": "DBOS first migration lookup after SQLite file creation"})
                os._exit(71)

        event.listen(Engine, "after_cursor_execute", exit_after_migration_lookup)
    if fault == "precommit":
        original_write = operations._write_receipt

        def exit_after_receipt(connection: object, receipt: object) -> None:
            original_write(connection, cast(Any, receipt))
            if getattr(receipt, "kind", None) == "claim_attempt_launch":
                _save(marker, {"point": "Core claim receipt inserted before commit"})
                os._exit(72)

        operations._write_receipt = exit_after_receipt
    if fault == "postcommit":
        original_apply = cast(Any, vars(assigned)["apply_operation"])

        def exit_after_claim(root: Path, request: object, authority: LocalAuthority) -> Any:
            receipt = original_apply(root, cast(Any, request), authority)
            if isinstance(request, ClaimAttemptLaunchRequest):
                _save(marker, {"point": "Core claim committed before DBOS workflow checkpoint"})
                os._exit(73)
            return receipt

        vars(assigned)["apply_operation"] = exit_after_claim

    original_popen = subprocess.Popen
    pi_stderr = (case_file.parent / f"pi-{fault}.stderr.log").open("ab")

    def capture_pi(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("stderr") == subprocess.DEVNULL:
            kwargs["stderr"] = pi_stderr
        process = original_popen(*args, **kwargs)
        if kwargs.get("stderr") is pi_stderr:
            _save(case_file.parent / f"pi-{fault}.pid.json", {"pid": process.pid})
        return process

    proxy = types.SimpleNamespace(
        Popen=capture_pi,
        PIPE=subprocess.PIPE,
        DEVNULL=subprocess.DEVNULL,
        TimeoutExpired=subprocess.TimeoutExpired,
    )
    vars(assigned)["subprocess"] = proxy
    try:
        result = run_assigned(config, owner, UUID(data["attempt_id"]))
        _save(case_file.parent / f"result-{fault}.json", {"result": result})
        if fault == "postcheckpoint":
            _save(marker, {"point": "DBOS result returned before host response"})
            os._exit(74)
        print(json.dumps({"result": result}), flush=True)
        return 0
    except BaseException as error:
        print(f"{type(error).__name__}: {error}", flush=True)
        return 1
    finally:
        pi_stderr.close()


def _start(case_file: Path, fault: str) -> subprocess.Popen[bytes]:
    stream = (case_file.parent / f"runner-{fault}-{uuid4().hex[:8]}.log").open("wb")
    try:
        return subprocess.Popen(
            [
                sys.executable,
                "-X",
                "utf8",
                "-m",
                "tools.probe_stage6_pass4",
                "--runner",
                str(case_file),
                "--fault",
                fault,
            ],
            cwd=Path(__file__).resolve().parents[1],
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    finally:
        stream.close()


def _finish(process: subprocess.Popen[bytes], expected: int, timeout: float = 55) -> None:
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)
        raise AssertionError("Runner timeout; preserved log and space") from None
    assert code == expected, (process.pid, code, expected)


def _provider() -> tuple[SyntheticProvider, threading.Thread]:
    response = json.dumps({"zara": "final", "text": "fictional live result"})
    provider = SyntheticProvider((response,))
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    return provider, thread


class BarrierHandler(SyntheticHandler):
    def do_POST(self) -> None:
        server = cast(Any, self.server)
        try:
            server.arrivals.wait(timeout=25)
        except threading.BrokenBarrierError:
            server.barrier_broken = True
            self.send_error(503, "Second synthetic runner did not arrive")
            return
        super().do_POST()


class BarrierProvider(SyntheticProvider):
    def __init__(self) -> None:
        ThreadingHTTPServer.__init__(self, ("127.0.0.1", 0), BarrierHandler)
        self.responses = (json.dumps({"zara": "final", "text": "fictional concurrent result"}),)
        self.digests = []
        self.guard = threading.Lock()
        self.arrivals = threading.Barrier(2)
        self.barrier_broken = False


def _initialize_executor(root: Path, attempt_id: UUID) -> None:
    from dbos import DBOS

    DBOS(
        config={
            "name": "zaratustra-assigned-rpc",
            "system_database_url": f"sqlite:///{executor_database(root).resolve().as_posix()}",
            "application_version": f"zara-pi-rpc-dbos-3.0.0-v1-{attempt_id}",
            "executor_id": str(attempt_id),
        }
    )
    DBOS.launch()
    DBOS.destroy(destroy_registry=True, workflow_completion_timeout_sec=1)


def _run_parallel(
    output: Path, runtime: Path, *, preinitialize: bool = False, barrier: bool = True
) -> dict[str, object]:
    provider: Any
    if barrier:
        provider = BarrierProvider()
        server = threading.Thread(target=provider.serve_forever, daemon=True)
        server.start()
    else:
        provider, server = _provider()
    try:
        a, b = _parallel_cases(
            output / "parallel", runtime, f"http://127.0.0.1:{provider.server_port}/v1"
        )
        if preinitialize:
            data = cast(dict[str, str], json.loads(a.read_text(encoding="utf-8")))
            _initialize_executor(Path(data["space"]), UUID(data["attempt_id"]))
        before = {"a": _fresh(a, "before"), "b": _fresh(b, "before")}
        runner_a, runner_b = _start(a, "parallel"), _start(b, "parallel")
        _finish(runner_a, 0, timeout=65)
        _finish(runner_b, 0, timeout=65)
        after = {"a": _fresh(a, "after"), "b": _fresh(b, "after")}
        assert not getattr(provider, "barrier_broken", False) and len(provider.digests) == 2
        for role, case in (("a", a), ("b", b)):
            data = cast(dict[str, str], json.loads(case.read_text(encoding="utf-8")))
            current = after[role]
            assert cast(list[dict[str, object]], current["assignments"])[0]["status"] == "stopped"
            assert len(cast(list[object], current["outputs"])) == 1
            workflows = cast(list[dict[str, object]], current["workflows"])
            own = next(
                item
                for item in workflows
                if cast(dict[str, object], item["attributes"])["attempt_id"] == data["attempt_id"]
            )
            assert own["status"] == "SUCCESS"
            assert own["queue"] == f"zara-assigned-rpc-{data['attempt_id']}"
            assert own["executor_id"] == data["attempt_id"]
        _finish(_start(a, "replay"), 0)
        _finish(_start(b, "replay"), 0)
        replay = {"a": _fresh(a, "replay"), "b": _fresh(b, "replay")}
        assert replay == after and len(provider.digests) == 2
        return {"before": before, "after": after, "replay": replay, "http": [0, 2, 2]}
    finally:
        provider.shutdown()
        provider.server_close()
        server.join(timeout=5)


def _run_isolation(output: Path, runtime: Path) -> dict[str, object]:
    provider, server = _provider()
    try:
        a, b = _parallel_cases(
            output / "isolation", runtime, f"http://127.0.0.1:{provider.server_port}/v1"
        )
        before = {"a": _fresh(a, "before"), "b": _fresh(b, "before")}
        _finish(_start(a, "isolation-a"), 0)
        only_a = {"a": _fresh(a, "only-a"), "b": _fresh(b, "only-a")}
        b_data = cast(dict[str, str], json.loads(b.read_text(encoding="utf-8")))
        b_state = only_a["b"]
        b_workflow = next(
            item
            for item in cast(list[dict[str, object]], b_state["workflows"])
            if cast(dict[str, object], item["attributes"])["attempt_id"] == b_data["attempt_id"]
        )
        assert b_workflow["status"] == "ENQUEUED" and len(provider.digests) == 1
        assert not cast(list[object], b_state["invocations"])
        assert cast(dict[str, object], b_state["receipts"])["claim"] == {"error": "not_found"}
        _finish(_start(b, "isolation-b"), 0)
        after = {"a": _fresh(a, "after"), "b": _fresh(b, "after")}
        assert len(provider.digests) == 2
        _finish(_start(a, "replay"), 0)
        _finish(_start(b, "replay"), 0)
        replay = {"a": _fresh(a, "replay"), "b": _fresh(b, "replay")}
        assert replay == after and len(provider.digests) == 2
        return {
            "before": before,
            "only_a": only_a,
            "after": after,
            "replay": replay,
            "http": [0, 1, 2, 2],
        }
    finally:
        provider.shutdown()
        provider.server_close()
        server.join(timeout=5)


def _run_rpc_sequence(output: Path, runtime: Path) -> dict[str, object]:
    provider, server = _provider()
    try:
        a = _case(output / "rpc-a", runtime, f"http://127.0.0.1:{provider.server_port}/v1")
        before = _fresh(a, "before")
        _finish(_start(a, "rpc-a"), 0)
        after_a = _fresh(a, "after")
        assert len(provider.digests) == 1
        data = cast(dict[str, str], json.loads(a.read_text(encoding="utf-8")))
        root, work, parent = Path(data["space"]), UUID(data["work_id"]), UUID(data["parent"])
        owner = authorize_local(root, actor="owner", source_ref="pass4-rpc-sequence")
        accept = AcceptWorkRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor="owner",
            work_id=work,
            expected_revision=read_work(root, work, owner).revision,
            basis="Synthetic A accepted",
        )
        accepted = apply_operation(root, accept, owner)
        b_work = UUID(data["b"])
        issue = apply_operation(root, _issue(root, owner, parent, b_work, 2), owner)
        assignment = _assign(root, owner, b_work)
        assigned = apply_operation(root, assignment, owner)
        b_data = {
            **data,
            "work_id": str(b_work),
            "workspace": str(a.parent / "workspace-b"),
            "attempt_id": str(assignment.attempt_id),
            "assignment_id": str(assignment.operation_id),
            "assignment_receipt": assigned.model_dump(mode="json"),
            "assignment_request": assignment.model_dump(mode="json"),
        }
        b = output / "rpc-b" / "case.json"
        b.parent.mkdir()
        _save(b, b_data)
        before_b = _fresh(b, "before")
        _finish(_start(b, "rpc-b"), 0)
        after_b = _fresh(b, "after")
        assert len(provider.digests) == 2
        _finish(_start(a, "replay"), 0)
        _finish(_start(b, "replay"), 0)
        replay = {"a": _fresh(a, "replay"), "b": _fresh(b, "replay")}
        assert len(provider.digests) == 2
        return {
            "before": before,
            "after_a": after_a,
            "a_accept": accepted.model_dump(mode="json"),
            "b_issue": issue.model_dump(mode="json"),
            "before_b": before_b,
            "after_b": after_b,
            "replay": replay,
            "http": [0, 1, 1, 2, 2],
        }
    finally:
        provider.shutdown()
        provider.server_close()
        server.join(timeout=5)


def _run_core_lock(output: Path, runtime: Path) -> dict[str, object]:
    import sqlite3

    provider, server = _provider()
    try:
        case = _case(output / "core-lock", runtime, f"http://127.0.0.1:{provider.server_port}/v1")
        before = _fresh(case, "before")
        data = cast(dict[str, Any], json.loads(case.read_text(encoding="utf-8")))
        root, work, attempt = Path(data["space"]), UUID(data["work_id"]), UUID(data["attempt_id"])
        owner = authorize_local(root, actor="owner", source_ref="pass4-core-lock")
        assignment = cast(dict[str, Any], data["assignment_request"])
        database = root / ".zara-core" / "core.sqlite3"
        lock_log = output / "core-lock" / "lock-owner.json"
        with closing(sqlite3.connect(database, timeout=0.25, autocommit=True)) as holder:
            mode = holder.execute("PRAGMA locking_mode=EXCLUSIVE").fetchone()[0]
            holder.execute("BEGIN EXCLUSIVE")
            holder.execute("SELECT count(*) FROM spaces").fetchone()
            _save(lock_log, {"pid": os.getpid(), "mode": mode, "transaction": "BEGIN EXCLUSIVE"})
            error: str | None = None
            try:
                _record_stop(
                    _config(data),
                    owner,
                    work,
                    attempt,
                    UUID(assignment["session_id"]),
                    observed=True,
                )
            except FoundationError as failure:
                error = failure.code
                (case.parent / "locked-stop.traceback.log").write_text(
                    traceback.format_exc(), encoding="utf-8"
                )
            holder.rollback()
        unlocked = _fresh(case, "unlocked-before-retry")
        assert error == "storage" and unlocked == before and len(provider.digests) == 0
        _finish(_start(case, "restart"), 0)
        after = _fresh(case, "after-restart")
        _finish(_start(case, "replay"), 0)
        replay = _fresh(case, "replay")
        assert after == replay and len(provider.digests) == 1
        return {
            "before": before,
            "lock_error": error,
            "unlocked": unlocked,
            "after": after,
            "replay": replay,
            "http": [0, 0, 1, 1],
            "point_reached": True,
        }
    finally:
        provider.shutdown()
        provider.server_close()
        server.join(timeout=5)


def _run_window(output: Path, runtime: Path, window: str) -> dict[str, object]:
    provider: Any
    if window == "transport":
        provider = DropFirstProvider()
        server = threading.Thread(target=provider.serve_forever, daemon=True)
        server.start()
    elif window == "waiting":
        provider = SyntheticProvider(Markers().responses())
        server = threading.Thread(target=provider.serve_forever, daemon=True)
        server.start()
    else:
        provider, server = _provider()
    try:
        case = _case(output / window, runtime, f"http://127.0.0.1:{provider.server_port}/v1")
        if window == "delivery":
            initial = cast(dict[str, str], json.loads(case.read_text(encoding="utf-8")))
            _initialize_executor(Path(initial["space"]), UUID(initial["attempt_id"]))
        before = _fresh(case, "before")
        assert not provider.digests
        if window == "delivery":
            data = cast(dict[str, str], json.loads(case.read_text(encoding="utf-8")))
            root = Path(data["space"])
            owner = authorize_local(root, actor="owner", source_ref="pass4-delivery")
            first, second = deliver_outbox(root, owner), deliver_outbox(root, owner)
            queued = _fresh(case, "delivered-twice")
            assert first == second and len(cast(list[object], queued["workflows"])) == 1
            assert len(provider.digests) == 0
            _finish(_start(case, "none"), 0)
            after = _fresh(case, "after")
            _finish(_start(case, "none"), 0)
            replay = _fresh(case, "replay")
            assert len(provider.digests) == 1 and after == replay
            return {
                "before": before,
                "delivered": queued,
                "after": after,
                "replay": replay,
                "http": [0, 0, 1, 1],
            }
        if window == "transport":
            _finish(_start(case, "none"), 1)
            failed = _fresh(case, "failed-before-retry")
            assert len(provider.digests) == 1
            assert failed["held_units"] == 1000
            assert cast(list[dict[str, object]], failed["invocations"])[0]["status"] == "unknown"
            data = cast(dict[str, str], json.loads(case.read_text(encoding="utf-8")))
            conflict = competing_resource(data)
            assert conflict == "resource_busy"
            _finish(_start(case, "restart"), 1)
            after = _fresh(case, "after-restart")
            assert len(provider.digests) == 1
            return {
                "before": before,
                "failed": failed,
                "after": after,
                "competing_resource": conflict,
                "http": [0, 1, 1],
            }
        if window == "waiting":
            process = _start(case, "waiting")
            data = cast(dict[str, str], json.loads(case.read_text(encoding="utf-8")))
            root, work = Path(data["space"]), UUID(data["work_id"])
            owner = authorize_local(root, actor="owner", source_ref="pass4-wait-observer")
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                snapshot = read_execution(root, work, owner)
                if (
                    any(item.status == "open" for item in snapshot.waits)
                    and len(provider.digests) == 1
                ):
                    break
                if process.poll() is not None:
                    raise AssertionError(f"Runner exited before wait: {process.returncode}")
                time.sleep(0.1)
            else:
                process.kill()
                process.wait(timeout=10)
                raise AssertionError("Wait fault point was not reached")
            at_wait = _fresh(case, "open-wait-before-kill")
            process.kill()
            assert process.wait(timeout=10) != 0
            pi_pid_file = case.parent / "pi-waiting.pid.json"
            if pi_pid_file.is_file():
                pi_pid = int(json.loads(pi_pid_file.read_text(encoding="utf-8"))["pid"])
                try:
                    os.kill(pi_pid, signal.SIGTERM)
                except (OSError, ProcessLookupError):
                    pass
            _save(case.parent / "fault-waiting.json", {"point": "host killed while Core wait open"})
            killed = _fresh(case, "killed-before-retry")
            _finish(_start(case, "restart"), 1)
            after = _fresh(case, "after-restart")
            conflict = competing_resource(data)
            assert conflict == "resource_busy" and len(provider.digests) == 1
            return {
                "before": before,
                "at_wait": at_wait,
                "killed": killed,
                "after": after,
                "competing_resource": conflict,
                "http": [0, 1, 1],
            }
        fault, exit_code = {
            "migration": ("migration-interrupt", 71),
            "precommit": ("precommit", 72),
            "postcommit": ("postcommit", 73),
            "postcheckpoint": ("postcheckpoint", 74),
        }[window]
        _finish(_start(case, fault), exit_code)
        assert (case.parent / f"fault-{fault}.json").is_file(), "Fault point was not reached"
        crashed = _fresh(case, "crashed-before-retry")
        assert len(provider.digests) == (1 if window == "postcheckpoint" else 0)
        if window == "migration":
            assert crashed["executor_tables"] == []
            assert crashed["work"] == before["work"]
            assert crashed["attempts"] == before["attempts"]
            assert crashed["receipts"] == before["receipts"]
            assert crashed["held_units"] == before["held_units"]
            data = cast(dict[str, str], json.loads(case.read_text(encoding="utf-8")))
            database = executor_database(Path(data["space"]))
            assert database.is_file()
            database_identity = database.stat().st_ino
        restarted_process = _start(case, "restart")
        expected = 1 if window == "postcommit" else 0
        _finish(restarted_process, expected)
        after = _fresh(case, "after-restart")
        assert len(provider.digests) == (0 if window == "postcommit" else 1)
        if window == "migration":
            assert database.stat().st_ino == database_identity
            assert len(cast(list[object], after["workflows"])) == 1
            assert cast(dict[str, object], after["receipts"])["claim"] != {"error": "not_found"}
            _finish(_start(case, "none"), 0)
            replay = _fresh(case, "replay")
            assert replay == after and len(provider.digests) == 1
            return {
                "before": before,
                "crashed": crashed,
                "after": after,
                "replay": replay,
                "executor_database": str(database),
                "same_database_identity": True,
                "http": [0, 0, 1, 1],
            }
        after_conflict: str | None = None
        if window == "postcommit":
            data = cast(dict[str, str], json.loads(case.read_text(encoding="utf-8")))
            after_conflict = competing_resource(data)
            assert after_conflict == "resource_busy"
        return {
            "before": before,
            "crashed": crashed,
            "after": after,
            "competing_resource": after_conflict,
            "http": [0, len(provider.digests)],
        }
    finally:
        provider.shutdown()
        provider.server_close()
        server.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pi-runtime", type=Path)
    parser.add_argument(
        "--case",
        choices=(
            "delivery",
            "migration",
            "precommit",
            "postcommit",
            "postcheckpoint",
            "transport",
            "waiting",
            "parallel",
            "isolation",
            "rpc-sequence",
            "core-lock",
        ),
    )
    parser.add_argument("--inspect", type=Path)
    parser.add_argument("--runner", type=Path)
    parser.add_argument("--fault", default="none")
    parser.add_argument("--preinitialize", action="store_true")
    parser.add_argument("--no-barrier", action="store_true")
    args = parser.parse_args()
    if args.inspect is not None:
        print(json.dumps(_inspect(args.inspect), ensure_ascii=False))
        return 0
    if args.runner is not None:
        return _runner(args.runner, args.fault)
    if args.output is None or args.pi_runtime is None or args.case is None:
        parser.error("Supply --output, --pi-runtime and --case")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if args.case == "parallel":
        report = _run_parallel(
            output, args.pi_runtime, preinitialize=args.preinitialize, barrier=not args.no_barrier
        )
    elif args.case == "isolation":
        report = _run_isolation(output, args.pi_runtime)
    elif args.case == "rpc-sequence":
        report = _run_rpc_sequence(output, args.pi_runtime)
    elif args.case == "core-lock":
        report = _run_core_lock(output, args.pi_runtime)
    else:
        report = _run_window(output, args.pi_runtime, args.case)
    _save(output / "report.json", report)
    print(json.dumps({"case": args.case, "http": report["http"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
