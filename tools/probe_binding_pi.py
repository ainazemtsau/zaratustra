"""Development-only ordinary Pi Binding probe with a synthetic localhost model."""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from uuid import uuid4

from tests.zaratustra.foundation.test_binding import _apply, _ready
from zaratustra.foundation import (
    ArtifactRef,
    CreateArtifactRequest,
    CreateWorkRequest,
    LinkedOutput,
    LinkWorkOutputRequest,
    OutputContract,
    WorkState,
    authorize_local,
    read_binding_firings,
    read_binding_version,
)
from zaratustra.pi_adapter import Bridge, BridgeServer


class _Provider(ThreadingHTTPServer):
    def __init__(self, calls: tuple[dict[str, object], ...]) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.scripted_calls = calls
        self.calls = 0
        self.requests: list[dict[str, Any]] = []


class _Handler(BaseHTTPRequestHandler):
    server: _Provider

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.requests.append(json.loads(raw))
        self.server.calls += 1
        number = self.server.calls
        chunks: list[dict[str, object]] = [
            {
                "id": "synthetic",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            },
        ]
        if number <= len(self.server.scripted_calls):
            args = json.dumps(self.server.scripted_calls[number - 1])
            chunks.append(
                {
                    "id": "synthetic",
                    "object": "chat.completion.chunk",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": f"call-{number}",
                                        "type": "function",
                                        "function": {"name": "zara_binding", "arguments": args},
                                    }
                                ]
                            },
                            "finish_reason": None,
                        }
                    ],
                }
            )
            reason = "tool_calls"
        else:
            chunks.append(
                {
                    "id": "synthetic",
                    "object": "chat.completion.chunk",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": "The transfer is enabled."},
                            "finish_reason": None,
                        }
                    ],
                }
            )
            reason = "stop"
        chunks.append(
            {
                "id": "synthetic",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {}, "finish_reason": reason}],
            }
        )
        chunks.append(
            {
                "id": "synthetic",
                "object": "chat.completion.chunk",
                "choices": [],
                "usage": {"prompt_tokens": 30, "completion_tokens": 20, "total_tokens": 50},
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def run_pi_binding_probe(tmp_path: Path, runtime: Path) -> None:
    root, space, owner, producer, consumer = _ready(tmp_path)
    source_work, source_artifact = uuid4(), uuid4()
    _apply(
        root,
        space,
        owner,
        CreateArtifactRequest,
        artifact_id=source_artifact,
        media_type="text/plain",
        content=b"fictional finished design",
    )
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=source_work,
        state=WorkState(
            activity_id=producer,
            goal="Finish a fictional design",
            expected_outputs=(OutputContract(slot="design", media_type="text/plain"),),
        ),
    )
    _apply(
        root,
        space,
        owner,
        LinkWorkOutputRequest,
        work_id=source_work,
        expected_revision=1,
        output=LinkedOutput(
            slot="design",
            artifact=ArtifactRef(artifact_id=source_artifact, revision=1),
        ),
    )
    target = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=target,
        state=WorkState(
            activity_id=consumer,
            goal="Plan from accepted design",
            expected_outputs=(OutputContract(slot="plan", media_type="text/plain"),),
        ),
    )
    binding_id = uuid4()
    scripted_calls: tuple[dict[str, object], ...] = (
        {"mode": "catalog"},
        {"mode": "contract", "kind": "create_binding_version"},
        {
            "mode": "apply",
            "intent": {
                "kind": "create_binding_version",
                "binding_id": str(binding_id),
                "version": 1,
                "definition": {
                    "source_activity_id": str(producer),
                    "source_slot": "design",
                    "media_type": "text/plain",
                    "basis": "Owner-approved fictional transfer",
                    "target": {
                        "kind": "offer_work",
                        "work_id": str(target),
                        "input_slot": "design",
                    },
                },
            },
        },
        {
            "mode": "apply",
            "intent": {
                "kind": "set_binding_state",
                "binding_id": str(binding_id),
                "version": 1,
                "expected_state_revision": 1,
                "state": "enabled",
            },
        },
    )
    provider = _Provider(scripted_calls)
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    bridge = Bridge(root, owner, tmp_path, 1000)
    bridge_server = BridgeServer(bridge)
    bridge_thread = threading.Thread(target=bridge_server.serve_forever, daemon=True)
    bridge_thread.start()
    cli = runtime / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js"
    extension = Path(str(files("zaratustra.pi_adapter").joinpath("extension.ts")))
    installed = runtime / f"zaratustra-binding-{uuid4()}.ts"
    shutil.copyfile(extension, installed)
    home = tmp_path / "pi-home"
    home.mkdir()
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper()
        in {
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "TEMP",
            "TMP",
        }
    }
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "APPDATA": str(home / "AppData"),
            "LOCALAPPDATA": str(home / "LocalAppData"),
            "PI_CODING_AGENT_DIR": str(home / "pi-agent"),
            "PI_OFFLINE": "1",
            "PI_SKIP_VERSION_CHECK": "1",
            "PI_TELEMETRY": "0",
            "ZARA_CORE_ENDPOINT": f"http://127.0.0.1:{bridge_server.server_port}",
            "ZARA_CORE_TOKEN": bridge.token,
            "ZARA_RESERVE_UNITS": "1000",
            "ZARA_PROVIDER_PROFILE": "local-completions",
            "ZARA_PROVIDER_BASE_URL": f"http://127.0.0.1:{provider.server_port}/v1",
            "ZARA_PROVIDER_ORIGIN": f"http://127.0.0.1:{provider.server_port}",
            "ZARA_LOCAL_PROVIDER_ID": "fictional-local",
            "ZARA_LOCAL_MODEL_ID": "fictional-model",
            "ZARA_LOCAL_CONTEXT_WINDOW": "4096",
            "ZARA_LOCAL_MAX_TOKENS": "512",
        }
    )
    command = [
        shutil.which("node") or "node",
        str(cli),
        "--mode",
        "rpc",
        "--provider",
        "fictional-local",
        "--model",
        "fictional-model",
        "--extension",
        str(installed),
        "--no-extensions",
        "--no-context-files",
        "--no-session",
        "--no-skills",
        "--no-prompt-templates",
        "--no-themes",
        "--no-approve",
        "--offline",
    ]
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=tmp_path,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        events: queue.Queue[dict[str, object]] = queue.Queue()

        def reader() -> None:
            assert process is not None and process.stdout is not None
            for line in process.stdout:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict):
                    events.put(item)

        threading.Thread(target=reader, daemon=True).start()
        assert process.stdin is not None
        process.stdin.write(
            json.dumps(
                {
                    "id": "binding",
                    "type": "prompt",
                    "message": (
                        "Please keep transferring accepted design results to the planning Work."
                    ),
                }
            ).encode()
            + b"\n"
        )
        process.stdin.flush()
        observed: list[dict[str, object]] = []
        deadline = time.monotonic() + 75
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                event = events.get(timeout=0.25)
            except queue.Empty:
                if (
                    provider.calls >= len(scripted_calls) + 1
                    and read_binding_version(root, binding_id, 1, owner).state == "enabled"
                ):
                    break
                continue
            observed.append(event)
            if event.get("type") == "extension_ui_request" and event.get("method") == "confirm":
                process.stdin.write(
                    json.dumps(
                        {"type": "extension_ui_response", "id": event["id"], "confirmed": True}
                    ).encode()
                    + b"\n"
                )
                process.stdin.flush()
            if event.get("type") == "agent_end":
                break
        stderr = (
            process.stderr.read().decode("utf-8", errors="replace")
            if process.poll() is not None and process.stderr
            else ""
        )
        assert provider.calls >= len(scripted_calls) + 1, (stderr, observed[-8:])
        assert any("zara_binding" in json.dumps(request) for request in provider.requests)
        assert read_binding_version(root, binding_id, 1, owner).state == "enabled"
        assert not any(
            event.get("type") == "tool_execution_end" and event.get("isError") for event in observed
        ), observed[-8:]
        process.terminate()
        process.wait(timeout=10)
        accept_env = {
            **env,
            "ZARA_INITIAL_ACTIVITY_ID": str(producer),
            "ZARA_INITIAL_WORK_ID": str(source_work),
        }
        process = subprocess.Popen(
            command,
            cwd=tmp_path,
            env=accept_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        events = queue.Queue()
        threading.Thread(target=reader, daemon=True).start()
        assert process.stdin is not None
        process.stdin.write(b'{"id":"accept","type":"prompt","message":"/zara-accept"}\n')
        process.stdin.flush()
        accepted = False
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                event = events.get(timeout=0.25)
            except queue.Empty:
                continue
            observed.append(event)
            if event.get("type") == "extension_ui_request":
                response: dict[str, object] = {
                    "type": "extension_ui_response",
                    "id": event["id"],
                }
                if event.get("method") == "input":
                    response["value"] = "Fictional design accepted in ordinary Pi"
                elif event.get("method") == "confirm":
                    response["confirmed"] = True
                else:
                    continue
                process.stdin.write(json.dumps(response).encode() + b"\n")
                process.stdin.flush()
            if event.get("type") == "response" and event.get("id") == "accept":
                accepted = event.get("success") is True
            if accepted and read_binding_firings(root, binding_id, owner):
                break
        assert accepted, observed[-8:]
        assert read_binding_firings(root, binding_id, owner)[0].outcome == "offered"
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=10)
        installed.unlink(missing_ok=True)
        bridge_server.shutdown()
        bridge_server.server_close()
        bridge_thread.join(timeout=5)
        provider.shutdown()
        provider.server_close()
        provider_thread.join(timeout=5)
    assert read_binding_firings(root, binding_id, owner)[0].outcome == "offered"
    assert (
        authorize_local(root, actor="owner", source_ref="reopened").execution_epoch
        == owner.execution_epoch
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi-runtime", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="zara-binding-pi-") as directory:
        run_pi_binding_probe(Path(directory), args.pi_runtime.resolve())
    print("ordinary Pi Binding probe: passed")


if __name__ == "__main__":
    main()
