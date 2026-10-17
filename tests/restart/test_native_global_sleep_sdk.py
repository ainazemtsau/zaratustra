"""Public Pi global Sleep routing; fictional localhost provider, no semantic proof."""

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


@pytest.mark.parametrize("mode", ["empty", "activity", "targeted", "invalid", "unknown"])
def test_public_global_sleep(tmp_path: Path, mode: str) -> None:
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
            if index == 0:
                delta["tool_calls"] = [
                    {
                        "index": 0,
                        "id": "sleep-result",
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
                            "finish_reason": "tool_calls" if index == 0 else "stop",
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
                str(Path(__file__).with_name("native_global_sleep_fixture.mjs")),
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
            timeout=60,
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
    if mode in {"invalid", "unknown"}:
        assert not calls
        assert value["context"]["current"] == value["before"]["current"]
        assert value["delivery"]["state"] == "error"
        return
    assert len(calls) == 2
    assert len(value["results"]["rows"]) == 1
    result = json.loads(value["results"]["rows"][0]["body"])
    assert result["text"] == final
    assert result["outputs"] == []
    assert result["accepted"] is False
    assert result["state"] == "completed"
    assert value["context"]["current"] == {}
    contexts = [
        json.loads(message["content"])
        for message in value["messages"]
        if message.get("customType") == "zaratustra-context"
    ]
    context = contexts[-1]
    expected_scope = "fictional" if mode == "targeted" else "space"
    assert context["current"]["scope"] == expected_scope
    assert context["current"]["mode"] == "sleep"
    assert expected_scope in json.dumps(value["notifications"])
    descriptions = [
        tool["function"]["description"]
        for tool in calls[0]["tools"]
        if tool["function"]["name"] == "zara_result"
    ]
    assert "Sleep" in descriptions[0] and "outputs:[]" in descriptions[0]
    assert "ordinary" in descriptions[0] and "review" in descriptions[0]
    if expected_scope == "space":
        contract = context["sleep"]["scope_contract"]
        assert contract["work_ownership"] == "workspace (space)"
        assert "all permitted Activities" in contract["source_read_domain"]
        assert "original scope" in contract["source_provenance"]
        assert "explicit grants" in contract["write_authority"]
        assert "proposal" in context["sleep"]["instructions"].lower()
        assert "scope_contract" in json.dumps(calls[0])
    activities = [head for head in value["context"]["core"]["heads"] if head["kind"] == "activity"]
    assert len(activities) == (0 if mode == "empty" else 1)
