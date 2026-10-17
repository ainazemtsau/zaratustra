"""Actual installed Pi SDK negative controls; fictional localhost inference only."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

SOURCE = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "scenario",
    [
        "review-command",
        "review-reopen",
        "failed-input",
        "profile-failure",
        "tool-block",
        "command-failure",
        "cancel-stream",
    ],
)
def test_native_hook_boundaries(tmp_path: Path, scenario: str) -> None:
    command = shutil.which("pi") or shutil.which("pi.ps1")
    assert command, "Required installed Pi SDK unavailable"
    sdk = Path(command).parent / "node_modules/@earendil-works/pi-coding-agent"
    route = {
        "changes": [
            {
                "id": "fictional",
                "kind": "activity",
                "key": "fictional",
                "body": "Fictional boundary task",
            }
        ],
        "expected_heads": {"fictional": 0},
        "outputs": [{"id": "fictional", "revision": 1}],
        "next_work": {"scope": "fictional", "goal": "Fictional task", "inputs": []},
    }
    result = {"payload": {"outputs": [{"id": "fictional", "revision": 1}]}}
    script: list[tuple[str, Any]] = [("zara_route", {"payload": route})]
    if scenario in {"review-command", "review-reopen"}:
        script += [
            ("write", {"path": "fictional.txt", "content": "Fictional bytes"}),
            ("zara_result", result),
            ("text", "Fictional builder final"),
            ("read", {"path": "fictional.txt"}),
            ("zara_result", result),
            ("text", "Fictional independent review final"),
        ]
    elif scenario == "failed-input":
        script += [
            ("text", "Incomplete first turn"),
            ("write", {"path": "forbidden.txt", "content": "Must not happen"}),
            ("text", "Must not infer"),
        ]
    else:
        script += [
            ("write", {"path": "forbidden.txt", "content": "Must not happen"}),
            ("text", "Must not infer"),
        ]
    if scenario == "cancel-stream":
        script = script[:1] + [("stream-cancel", "Fictional in-flight text")]
    if scenario == "review-reopen":
        script = script[:5] + [("text", "Incomplete retained review")]
    calls: list[Any] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            index = len(calls) - 1
            if index >= len(script):
                self.send_response(429)
                self.end_headers()
                return
            name, args = script[index]
            if name == "stream-cancel":
                chunk = {
                    "id": "fictional",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "scripted-transport",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": args},
                            "finish_reason": None,
                        }
                    ],
                }
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.flush()
                time.sleep(1)
                return
            delta: dict[str, Any] = {"role": "assistant"}
            if name == "text":
                delta["content"] = args
            else:
                delta["tool_calls"] = [
                    {
                        "index": 0,
                        "id": f"fictional-{index}",
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }
                ]
            chunks = [
                {
                    "id": "fictional",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "scripted-transport",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                },
                {
                    "id": "fictional",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "scripted-transport",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop" if name == "text" else "tool_calls",
                        }
                    ],
                },
            ]
            body = (
                "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(body.encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        process = subprocess.run(
            [
                "node",
                str(Path(__file__).with_name("native_boundary_fixture.mjs")),
                str(sdk),
                str(SOURCE / "pi-package"),
                str(tmp_path),
                sys.executable,
                f"http://127.0.0.1:{server.server_port}/v1",
                scenario,
            ],
            env=dict(os.environ, ZARATUSTRA_HOME=str(tmp_path / "home")),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)
    (tmp_path / "sdk-output.json").write_text(process.stdout, encoding="utf-8")
    (tmp_path / "sdk-stderr.log").write_text(process.stderr, encoding="utf-8")
    assert process.returncode == 0, process.stderr
    value = json.loads(process.stdout.splitlines()[-1])
    assert not (tmp_path / "forbidden.txt").exists()
    if scenario == "review-command":
        assert value["originalSession"] != value["finalSession"]
        assert value["delivery"]["review"] is not None
        assert "write" in value["activeTools"] and "bash" in value["activeTools"]
        assert not any(
            m.get("role") == "user" and str(m.get("content", "")).startswith("/zara")
            for m in value["afterSecond"]
        )
        for provider_request in calls:
            for message in provider_request.get("messages", []):
                if message.get("role") == "user":
                    assert "/zaratustra" not in json.dumps(message.get("content"))
                    assert "/zara-review-start" not in json.dumps(message.get("content"))
        assert len(calls) == 7
    elif scenario == "review-reopen":
        assert "write" not in value["reopenTools"] and "bash" not in value["reopenTools"]
        assert "write" in value["activeTools"] and "bash" in value["activeTools"]
        assert len(calls) == 6
    elif scenario == "failed-input":
        assert len(calls) == 2
        assert len(value["messages"]["rows"]) == 1
        assert value["context"]["pinned"]["profile"]["body"]["value"]["cwd"] == str(tmp_path)
    elif scenario == "cancel-stream":
        assert len(calls) == 2
        assert value["context"]["current"] == {}
        assert any(w["status"] == "cancelled" for w in value["context"]["core"]["works"])
    elif scenario in {"profile-failure", "command-failure"}:
        assert not calls
    else:
        assert len(calls) == 2
    for row in value["observations"].get("rows", []):
        import base64

        observation = json.loads(row["body"])
        raw = json.loads(base64.b64decode(observation["raw_base64"]))
        if raw.get("kind") == "turn_end":
            assert "context" not in raw["event"]
            assert "message" in raw["event"]
