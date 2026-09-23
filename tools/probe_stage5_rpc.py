"""Reproduce one synthetic assigned Work on ordinary Pi RPC and DBOS 3.0.0."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import cast
from uuid import uuid4

from tests.zaratustra.foundation.test_continuation import ready
from zaratustra.foundation import (
    AssignAttemptRequest,
    DeleteWorkRequest,
    FoundationError,
    RecoverRequest,
    ResourceState,
    ReviseResourceRequest,
    apply_operation,
    authorize_local,
    authorize_recovery,
    complete_deletions,
    managed_pi_session_lock,
    managed_pi_sessions,
    read_artifact,
    read_execution,
    read_space,
    restore_backup,
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

WAIT_TEXT = json.dumps(
    {
        "zara": "wait",
        "partial": "The fictional note has a heading.",
        "question": "Which fictional code should the summary use?",
        "remainder": "Add the selected code to the fictional summary.",
    },
    ensure_ascii=False,
)
FINAL_TEXT = json.dumps(
    {"zara": "final", "text": "The fictional note uses code A."}, ensure_ascii=False
)


class SyntheticProvider(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), SyntheticHandler)
        self.digests: list[str] = []
        self.guard = threading.Lock()


class SyntheticHandler(BaseHTTPRequestHandler):
    server: SyntheticProvider

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(size)
        with self.server.guard:
            self.server.digests.append(hashlib.sha256(body).hexdigest().upper())
            number = len(self.server.digests)
        text = WAIT_TEXT if number == 1 else FINAL_TEXT
        usage = {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140}
        chunks = [
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


def inspect_in_parallel_pi(
    root: Path,
    workspace: Path,
    space_id: object,
    work_id: object,
    activity_id: object,
    authority: object,
    pi_cli: Path,
    pi_runtime: Path,
    provider_url: str,
    question: str,
) -> bool:
    """Run the actual extension status command while the assigned Pi is waiting."""

    bridge = Bridge(root, authority, workspace, 10000)  # type: ignore[arg-type]
    server = BridgeServer(bridge)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    extension = Path(str(files("zaratustra.pi_adapter").joinpath("extension.ts")))
    installed = pi_runtime / f"zaratustra-status-probe-{uuid4()}.ts"
    sessions = managed_pi_sessions(root, space_id, create=True)  # type: ignore[arg-type]
    home = sessions / "status-probe"
    home.mkdir(exist_ok=True)
    parsed = provider_url.split("/v1", 1)[0]
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP"}
    }
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
            "ZARA_PROVIDER_BASE_URL": provider_url,
            "ZARA_PROVIDER_ORIGIN": parsed,
            "ZARA_LOCAL_PROVIDER_ID": "zara-synthetic",
            "ZARA_LOCAL_MODEL_ID": "synthetic-model",
            "ZARA_LOCAL_CONTEXT_WINDOW": "4096",
            "ZARA_LOCAL_MAX_TOKENS": "512",
            "ZARA_INITIAL_ACTIVITY_ID": str(activity_id),
            "ZARA_INITIAL_WORK_ID": str(work_id),
        }
    )
    command = [
        "node",
        str(pi_cli),
        "--mode",
        "rpc",
        "--provider",
        "zara-synthetic",
        "--model",
        "synthetic-model",
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
                process.stdin.write(
                    b'{"id":"status-probe","type":"prompt","message":"/zara-status"}\n'
                )
                process.stdin.flush()
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    try:
                        event = received.get(timeout=0.25)
                    except queue.Empty:
                        continue
                    if (
                        event.get("type") == "extension_ui_request"
                        and event.get("method") == "notify"
                        and question in json.dumps(event, ensure_ascii=False)
                    ):
                        return True
                    if event.get("type") == "response" and event.get("id") == "status-probe":
                        if event.get("success") is not True:
                            return False
                return False
            finally:
                process.terminate()
                process.wait(timeout=5)
                reader.join(timeout=5)
    finally:
        installed.unlink(missing_ok=True)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run(output: Path, pi_cli: Path, pi_runtime: Path) -> dict[str, object]:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    root, workspace, space_id, _, work_id, resource_id = ready(output)
    authority = authorize_local(root, actor="owner", source_ref="synthetic-local-console")
    apply_operation(
        root,
        ReviseResourceRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            resource_id=resource_id,
            work_id=work_id,
            expected_revision=1,
            state=ResourceState(label="Fictional directory", root=workspace, limit_units=10000),
        ),
        authority,
    )
    attempt_id, session_id = uuid4(), uuid4()
    apply_operation(
        root,
        AssignAttemptRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            attempt_id=attempt_id,
            work_id=work_id,
            expected_work_revision=1,
            resource_id=resource_id,
            expected_resource_revision=2,
            session_id=session_id,
            executor_version=EXECUTOR_VERSION,
        ),
        authority,
    )
    provider = SyntheticProvider()
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    config = AssignedConfig(
        space=root,
        workspace=workspace,
        pi_cli=pi_cli.resolve(),
        pi_runtime=pi_runtime.resolve(),
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
    result: dict[str, object] = {}

    def execute() -> None:
        try:
            result["workflow"] = run_assigned(config, authority, attempt_id)
        except BaseException as error:
            result["error"] = repr(error)

    worker = threading.Thread(target=execute, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 50
        while time.monotonic() < deadline:
            snapshot = read_execution(root, work_id, authority)
            if any(item.status == "open" for item in snapshot.waits):
                break
            if "error" in result:
                raise RuntimeError(str(result["error"]))
            time.sleep(0.1)
        else:
            raise TimeoutError("Pi RPC did not save its question")
        question = next(item for item in snapshot.waits if item.status == "open")
        calls_before_answer = len(provider.digests)
        # A fresh interactive adapter reads the saved question without prompting a model.
        interactive = Bridge(
            root,
            authority,
            workspace,
            10000,
            deliver_answer=lambda outbox_id: deliver_outbox(root, authority, outbox_id),
        )
        interactive_session = uuid4()
        interactive.connect(interactive_session)
        interactive.select(interactive_session, snapshot.activity.activity_id, work_id)
        visible = interactive.snapshot(interactive_session)
        visible_waits = cast(list[dict[str, object]], visible["waits"])
        assert any(
            row["wait_id"] == str(question.wait_id) and row["question"] == question.question
            for row in visible_waits
        )
        assert len(provider.digests) == calls_before_answer == 1
        pi_showed_question = inspect_in_parallel_pi(
            root,
            workspace,
            space_id,
            work_id,
            snapshot.activity.activity_id,
            authority,
            pi_cli.resolve(),
            pi_runtime.resolve(),
            config.provider_base_url,
            question.question or "",
        )
        if not pi_showed_question:
            interactive.answer_wait(interactive_session, question.wait_id, "Code A")
            worker.join(timeout=20)
            raise AssertionError("Parallel ordinary Pi did not show the saved question")
        assert len(provider.digests) == 1
        assert question.partial_refs
        partial = read_artifact(root, question.partial_refs[0].artifact_id, authority)
        assert partial.content == b"The fictional note has a heading."
        assert len(deliver_outbox(root, authority)) >= 1
        assert len(provider.digests) == 1
        first_answer = interactive.answer_wait(interactive_session, question.wait_id, "Code A")
        duplicate_answer = interactive.answer_wait(interactive_session, question.wait_id, "Code A")
        assert first_answer == duplicate_answer
        worker.join(timeout=50)
        if worker.is_alive():
            raise TimeoutError("DBOS workflow did not finish")
        if "error" in result:
            raise RuntimeError(str(result["error"]))
        after = read_execution(root, work_id, authority)
        assert result["workflow"] == "proposed"
        assert after.work.state.status == "proposed"
        assert len(after.outputs) == 1
        assert after.outputs[0].content == b"The fictional note uses code A."
        assert len(provider.digests) == 2
        assert [x.status for x in after.invocations] == ["answered", "answered"]
        assert [x.request_sha256 for x in after.invocations] == provider.digests
        assert after.held_units == 0 and after.committed_units == 280
        assert after.assignments[0].status == "stopped"
        assert [x.kind for x in after.outbox] == ["launch", "resume"]
        denied_root = output / "pre-send-denial"
        denied_root.mkdir()
        denied_space, denied_workspace, denied_space_id, _, denied_work_id, denied_resource = ready(
            denied_root
        )
        denied_authority = authorize_local(
            denied_space, actor="owner", source_ref="synthetic-denial-console"
        )
        denied_attempt = uuid4()
        apply_operation(
            denied_space,
            AssignAttemptRequest(
                operation_id=uuid4(),
                space_id=denied_space_id,
                actor="owner",
                attempt_id=denied_attempt,
                work_id=denied_work_id,
                expected_work_revision=1,
                resource_id=denied_resource,
                expected_resource_revision=1,
                session_id=uuid4(),
                executor_version=EXECUTOR_VERSION,
            ),
            denied_authority,
        )
        denied_config = replace(
            config,
            space=denied_space,
            workspace=denied_workspace,
            reserve_units=1000,
            limit_units=100,
        )
        calls_before_denial = len(provider.digests)
        try:
            run_assigned(denied_config, denied_authority, denied_attempt)
        except Exception:
            pass
        else:
            raise AssertionError("Over-budget RPC unexpectedly succeeded")
        denied = read_execution(denied_space, denied_work_id, denied_authority)
        assert len(provider.digests) == calls_before_denial
        assert len(denied.invocations) == 1 and denied.invocations[0].status == "prepared"
        assert not denied.outputs and denied.work.state.status == "proposed"
        backup = create_assigned_backup(root, uuid4(), authority)
        assert backup.manifest.executor_sha256 is not None
        assert backup.manifest.pi_rpc_home_files
        restored_root = output / "restored-space"
        restored_root.mkdir()
        recovery = authorize_recovery(actor="owner", source_ref="synthetic-restore-console")
        restored = restore_backup(backup.package, restored_root, recovery)
        assert restored.recovery_state == "quarantined" and restored.execution_epoch == 2
        assert (restored_root / ".zara-core" / "executor-restored.sqlite3").is_file()
        assert not (restored_root / ".zara-core" / "executor.sqlite3").exists()
        apply_operation(
            restored_root,
            RecoverRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor="owner",
                decision_id=uuid4(),
                grant_id=uuid4(),
            ),
            recovery,
        )
        restored_authority = authorize_local(
            restored_root, actor="owner", source_ref="synthetic-new-epoch-console"
        )
        restored_snapshot = read_execution(restored_root, work_id, restored_authority)
        assert restored_snapshot.execution_epoch == 2
        assert all(item.status == "cancelled" for item in restored_snapshot.outbox)
        apply_operation(
            root,
            DeleteWorkRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor="owner",
                work_id=work_id,
                expected_revision=after.work.revision,
            ),
            authority,
        )
        try:
            complete_deletions(root, authority)
        except FoundationError as error:
            assert error.code == "technical_cleanup_required"
        else:
            raise AssertionError("Core-only deletion must refuse live DBOS state")
        deletion = complete_assigned_deletions(root, authority)
        assert deletion.pending_jobs == 0 and deletion.live_store_sanitized
        assert not (root / ".zara-core" / "pi-rpc-home" / str(attempt_id)).exists()
        assert not backup.package.exists()
        assert read_space(root).execution_epoch == 1
        from dbos import DBOSClient

        client = DBOSClient(
            system_database_url=(
                f"sqlite:///{(root / '.zara-core' / 'executor.sqlite3').resolve().as_posix()}"
            ),
            application_name="zaratustra-assigned-rpc",
            retry_connection_errors=False,
        )
        try:
            assert not client.list_workflows(
                name="zara-assigned-work-v1", application_name="zaratustra-assigned-rpc"
            )
        finally:
            client.destroy()
        executor_bytes = (root / ".zara-core" / "executor.sqlite3").read_bytes()
        assert b"Which fictional code" not in executor_bytes
        assert b"The fictional note uses code A" not in executor_bytes
        apply_operation(
            restored_root,
            DeleteWorkRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor="owner",
                work_id=work_id,
                expected_revision=restored_snapshot.work.revision,
            ),
            restored_authority,
        )
        restored_deletion = complete_assigned_deletions(restored_root, restored_authority)
        assert restored_deletion.live_store_sanitized
        assert not (restored_root / ".zara-core" / "executor-restored.sqlite3").exists()
        assert not (restored_root / ".zara-core" / "pi-rpc-home-restored").exists()
        return {
            "status": "passed",
            "space": str(root),
            "work_id": str(work_id),
            "attempt_id": str(attempt_id),
            "wait_id": str(question.wait_id),
            "provider_calls_before_answer": calls_before_answer,
            "parallel_pi_showed_question_without_model_call": pi_showed_question,
            "provider_calls_total": len(provider.digests),
            "pre_send_denial_http_calls": len(provider.digests) - calls_before_denial,
            "invocation_sha256": provider.digests,
            "work_status": after.work.state.status,
            "assignment_status": after.assignments[0].status,
            "workflow": result["workflow"],
            "backup_executor_sha256": backup.manifest.executor_sha256,
            "backup_pi_files": len(backup.manifest.pi_rpc_home_files),
            "restored_epoch": restored_snapshot.execution_epoch,
            "deletion_sanitized": deletion.live_store_sanitized,
            "restored_archive_deleted": restored_deletion.live_store_sanitized,
        }
    finally:
        provider.shutdown()
        provider.server_close()
        provider_thread.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pi-cli", required=True, type=Path)
    parser.add_argument("--pi-runtime", required=True, type=Path)
    args = parser.parse_args()
    report = run(args.output, args.pi_cli, args.pi_runtime)
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
