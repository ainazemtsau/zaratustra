"""Observe addressed stop of ordinary Pi RPC through Core and DBOS on localhost."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

from tools.probe_stage5_faults import host as fault_host
from tools.probe_stage5_faults import make_case, snapshot, wait_for_question
from tools.probe_stage5_rpc import SyntheticProvider
from zaratustra.foundation import (
    OperationReceipt,
    RecordAttemptStopRequest,
    RequestAttemptStopRequest,
    RevokeGrantRequest,
    WaitRecord,
    apply_operation,
    authorize_local,
    read_artifact,
    read_execution,
)
from zaratustra.pi_adapter.assigned import _client, _workflow_id, deliver_outbox


class HeldProvider(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), HeldHandler)
        self.digests: list[str] = []
        self.guard = threading.Lock()
        self.received = threading.Event()
        self.release = threading.Event()


class HeldHandler(BaseHTTPRequestHandler):
    server: HeldProvider

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(size)
        with self.server.guard:
            self.server.digests.append(hashlib.sha256(body).hexdigest().upper())
        self.server.received.set()
        self.server.release.wait(timeout=45)
        self.close_connection = True


def host(case: Path, pid_file: Path) -> int:
    import zaratustra.pi_adapter.assigned as assigned

    data = json.loads(case.read_text(encoding="utf-8"))
    original = vars(assigned)["subprocess"]
    real_popen = cast(Callable[..., subprocess.Popen[bytes]], original.Popen)

    def observe(command: object, *args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        child = real_popen(command, *args, **kwargs)
        if isinstance(command, list) and data["pi_cli"] in [str(item) for item in command]:
            pid_file.write_text(json.dumps({"pid": child.pid}), encoding="utf-8", newline="\n")
        return child

    vars(assigned)["subprocess"] = SimpleNamespace(
        Popen=observe,
        PIPE=original.PIPE,
        DEVNULL=original.DEVNULL,
        TimeoutExpired=original.TimeoutExpired,
    )
    return fault_host(case, "none")


def start(case: Path) -> tuple[subprocess.Popen[bytes], Path]:
    pid_file = case.parent / "child-pid.json"
    log = (case.parent / "host.log").open("wb")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tools.probe_stage5_stop",
            "--host",
            str(case),
            "--pid-file",
            str(pid_file),
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    log.close()
    return process, pid_file


def child_pid(pid_file: Path) -> int:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if pid_file.is_file():
            return int(json.loads(pid_file.read_text(encoding="utf-8"))["pid"])
        time.sleep(0.1)
    raise TimeoutError("The ordinary Pi child PID was not observed")


def child_running(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        return False
    try:
        return bool(kernel.WaitForSingleObject(handle, 0) == 258)
    finally:
        kernel.CloseHandle(handle)


def stop(data: dict[str, str], reason: str) -> OperationReceipt:
    root = Path(data["space"])
    owner = authorize_local(root, actor="owner", source_ref="synthetic-owner-stop-console")
    current = snapshot(data)
    request = RequestAttemptStopRequest(
        operation_id=uuid4(),
        space_id=owner.space_id,
        actor="owner",
        attempt_id=UUID(data["attempt_id"]),
        work_id=UUID(data["work_id"]),
        session_id=UUID(data["session_id"]),
        expected_assignment_revision=current.assignments[0].revision,
        reason=reason,
    )
    receipt = apply_operation(root, request, owner)
    assert apply_operation(root, request, owner) == receipt
    assert not deliver_outbox(root, owner)
    return receipt


def cleanup(process: subprocess.Popen[bytes], data: dict[str, str], pid_file: Path) -> None:
    if process.poll() is None:
        client = _client(Path(data["space"]))
        try:
            client.send(
                _workflow_id(UUID(data["attempt_id"])),
                "synthetic-cleanup-wake",
                topic="answer",
                idempotency_key=str(uuid4()),
            )
        finally:
            client.destroy()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if pid_file.is_file():
        pid = child_pid(pid_file)
        if child_running(pid):
            os.kill(pid, signal.SIGTERM)


def waiting_case(output: Path, pi_cli: Path, pi_runtime: Path) -> dict[str, object]:
    provider = SyntheticProvider()
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    case, data = make_case(
        output, "waiting", f"http://127.0.0.1:{provider.server_port}/v1", pi_cli, pi_runtime
    )
    process, pid_file = start(case)
    try:
        wait = cast(WaitRecord, wait_for_question(data, provider))
        pid = child_pid(pid_file)
        assert child_running(pid)
        receipt = stop(data, "Stop the waiting fictional Pi")
        assert receipt.result["status"] == "stop_requested"
        assert process.wait(timeout=25) != 0
        state = snapshot(data)
        saved = state.waits[0]
        owner = authorize_local(Path(data["space"]), actor="owner", source_ref="synthetic-owner")
        partial = read_artifact(
            Path(data["space"]), saved.partial_refs[0].artifact_id, owner
        ).content
        assert state.assignments[0].status == "stopped"
        assert saved.status == "closed" and saved.question == wait.question
        assert saved.remainder == wait.remainder and partial
        assert len(provider.digests) == 1 and not child_running(pid)
        return {
            "assignment": "stopped",
            "child_running_after": False,
            "provider_calls": 1,
            "question_preserved": saved.question == wait.question,
            "remainder_preserved": saved.remainder == wait.remainder,
            "partial_bytes_preserved": bool(partial),
            "duplicate_stop_same_receipt": True,
        }
    finally:
        cleanup(process, data, pid_file)
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=5)


def active_case(output: Path, pi_cli: Path, pi_runtime: Path) -> dict[str, object]:
    provider = HeldProvider()
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    case, data = make_case(
        output, "active", f"http://127.0.0.1:{provider.server_port}/v1", pi_cli, pi_runtime
    )
    process, pid_file = start(case)
    try:
        assert provider.received.wait(timeout=35)
        pid = child_pid(pid_file)
        assert child_running(pid)
        stop(data, "Stop the active fictional Pi")
        assert process.wait(timeout=25) != 0
        state = snapshot(data)
        assert state.assignments[0].status == "unknown"
        assert len(provider.digests) == 1 and not child_running(pid)
        assert state.held_units == 1000
        return {
            "assignment": "unknown",
            "child_running_after": False,
            "provider_calls": 1,
            "invocation": state.invocations[0].status,
            "held_units": state.held_units,
        }
    finally:
        provider.release.set()
        cleanup(process, data, pid_file)
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=5)


def revoked_case(output: Path, pi_cli: Path, pi_runtime: Path) -> dict[str, object]:
    provider = SyntheticProvider()
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    case, data = make_case(
        output,
        "revoked",
        f"http://127.0.0.1:{provider.server_port}/v1",
        pi_cli,
        pi_runtime,
        actor="runner",
    )
    process, pid_file = start(case)
    try:
        wait_for_question(data, provider)
        pid = child_pid(pid_file)
        root = Path(data["space"])
        owner = authorize_local(root, actor="owner", source_ref="synthetic-owner")
        apply_operation(
            root,
            RevokeGrantRequest(
                operation_id=uuid4(),
                space_id=owner.space_id,
                actor="owner",
                grant_id=UUID(data["grant_id"]),
                expected_revision=1,
            ),
            owner,
        )
        assert process.wait(timeout=25) != 0 and not child_running(pid)
        before = read_execution(root, UUID(data["work_id"]), owner)
        assert before.assignments[0].status == "waiting"
        request = RequestAttemptStopRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor="owner",
            attempt_id=UUID(data["attempt_id"]),
            work_id=UUID(data["work_id"]),
            session_id=UUID(data["session_id"]),
            expected_assignment_revision=before.assignments[0].revision,
            reason="Owner reconciles revoked runner after observed child exit",
        )
        apply_operation(root, request, owner)
        stopping = read_execution(root, UUID(data["work_id"]), owner)
        apply_operation(
            root,
            RecordAttemptStopRequest(
                operation_id=uuid4(),
                space_id=owner.space_id,
                actor="owner",
                attempt_id=UUID(data["attempt_id"]),
                work_id=UUID(data["work_id"]),
                session_id=UUID(data["session_id"]),
                expected_assignment_revision=stopping.assignments[0].revision,
                outcome="stopped",
            ),
            owner,
        )
        after = snapshot(data)
        assert after.assignments[0].status == "stopped"
        assert len(provider.digests) == 1
        return {
            "after_runner_revocation": before.assignments[0].status,
            "child_running_after": False,
            "owner_reconciled": after.assignments[0].status,
            "provider_calls": 1,
        }
    finally:
        cleanup(process, data, pid_file)
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pi-cli", type=Path)
    parser.add_argument("--pi-runtime", type=Path)
    parser.add_argument("--host", type=Path)
    parser.add_argument("--pid-file", type=Path)
    args = parser.parse_args()
    if args.host is not None:
        assert args.pid_file is not None
        return host(args.host, args.pid_file)
    if args.output is None or args.pi_cli is None or args.pi_runtime is None:
        parser.error("Supply output, Pi CLI and Pi runtime")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    pi_cli, pi_runtime = args.pi_cli.resolve(), args.pi_runtime.resolve()
    report = {
        "waiting_stop": waiting_case(output, pi_cli, pi_runtime),
        "active_stop": active_case(output, pi_cli, pi_runtime),
        "revoked_runner_owner_reconcile": revoked_case(output, pi_cli, pi_runtime),
    }
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
