"""Fresh explicit native Sleep after cancellation; fictional provider only."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

SOURCE = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("mode", ["initial", "child", "window", "unknown"])
def test_fresh_sleep_after_explicit_cancel(tmp_path: Path, mode: str) -> None:
    executable = shutil.which("pi") or shutil.which("pi.ps1")
    assert executable
    sdk = Path(executable).parent / "node_modules/@earendil-works/pi-coding-agent"
    calls: list[dict[str, Any]] = []
    final = "Exact global fixture final. No source analysis or adaptation is asserted."

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            index = len(calls) - 1
            delta: dict[str, Any] = {"role": "assistant"}
            text_only = index == (2 if mode == "child" else 0)
            tool_turns = {0, 3, 5} if mode == "child" else {1}
            if not text_only and index in tool_turns:
                delta["tool_calls"] = [
                    {
                        "index": 0,
                        "id": f"sleep-result-{index}",
                        "type": "function",
                        "function": {
                            "name": "zara_result",
                            "arguments": json.dumps({"payload": {"outputs": []}}),
                        },
                    }
                ]
            else:
                delta["content"] = final
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
                            "finish_reason": "tool_calls"
                            if not text_only and index in tool_turns
                            else "stop",
                        }
                    ],
                },
            ]
            separator = chr(10) * 2
            body = (
                separator.join("data: " + json.dumps(chunk) for chunk in chunks)
                + separator
                + "data: [DONE]"
                + separator
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
                str(Path(__file__).with_name("native_cancelled_sleep_fixture.mjs")),
                str(sdk),
                os.environ.get("ZARA_GLOBAL_EXTENSION_SOURCE", str(SOURCE)),
                str(tmp_path),
                sys.executable,
                f"http://127.0.0.1:{server.server_port}/v1",
                mode,
            ],
            env=dict(os.environ, ZARATUSTRA_HOME=str(tmp_path / "home")),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)
    (tmp_path / "sdk-output.json").write_text(process.stdout, encoding="utf-8")
    (tmp_path / "sdk-stderr.log").write_text(process.stderr, encoding="utf-8")
    (tmp_path / "provider-requests.json").write_text(json.dumps(calls), encoding="utf-8")
    assert process.returncode == 0, process.stderr
    value = json.loads(process.stdout)
    assert not value["selections"]
    stages = {row["label"]: row["value"] for row in value["stages"]}
    if mode == "unknown":
        assert len(calls) == 1
        assert stages["first"]["current"] == stages["refused"]["current"]
        assert "native.previous_attempt" in json.dumps(value["notifications"])
        return
    assert len(calls) == (7 if mode == "child" else 3)
    works = value["tables"]["works"]["rows"]
    cancelled = [work for work in works if work["status"] == "cancelled"]
    assert len(cancelled) == 1
    old_id = cancelled[0]["id"]
    assert old_id == stages["child" if mode == "child" else "first"]["current"]["work"]
    results = [json.loads(row["body"]) for row in value["tables"]["results"]["rows"]]
    assert all(result["text"] == final and result["accepted"] is False for result in results)
    assert all(result["outputs"] == [] for result in results)
    assert len(results) == (3 if mode == "child" else 1)
    assert stages["fresh"]["current"] == {}
    roots = [work for work in works if not json.loads(work["body"]).get("continuation")]
    assert len(roots) == 2
    closed_root_id = (
        json.loads(cancelled[0]["body"])["continuation"]["parent_work_id"]
        if mode == "child"
        else old_id
    )
    fresh_root = next(work for work in roots if work["id"] != closed_root_id)
    assert json.loads(fresh_root["body"])["scope"] == "space"
    assert json.loads(fresh_root["body"])["call_limit"] is None
    if mode == "child":
        assert len(works) == 4
        assert stages["successor"]["current"] == {}
    if mode == "window":
        assert stages["reopened-cancelled"]["current"]["work"] == old_id
        assert stages["reopened-cancelled"]["current"]["attempt"]
    old_attempts = [
        attempt for attempt in value["tables"]["attempts"]["rows"] if attempt["work"] == old_id
    ]
    assert old_attempts and all(attempt["status"] == "fenced" for attempt in old_attempts)
    old_actions = [
        action
        for action in value["tables"]["actions"]["rows"]
        if action["attempt"] in {attempt["id"] for attempt in old_attempts}
    ]
    assert len(old_actions) == 1
    assert old_actions[0]["state"] != "terminal"
