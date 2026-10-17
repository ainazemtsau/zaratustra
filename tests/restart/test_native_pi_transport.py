"""Installed Pi transport evidence, never semantic model or installed-bootstrap evidence."""

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


@pytest.mark.parametrize("metadata", ["valid", "missing", "wrong", "aborted", "review"])
def test_installed_pi_native_transport(tmp_path: Path, metadata: str) -> None:
    command = shutil.which("pi") or shutil.which("pi.ps1")
    assert command, "Required installed native Pi unavailable"
    sdk = Path(command).parent / "node_modules/@earendil-works/pi-coding-agent"
    assert (sdk / "dist/index.js").is_file(), "Installed native Pi SDK required"
    calls: list[dict[str, Any]] = []
    route = {
        "changes": [
            {
                "id": "fictional",
                "kind": "activity",
                "key": "fictional",
                "body": "Fictional transport activity",
            }
        ],
        "expected_heads": {"fictional": 0},
        "outputs": [{"id": "fictional", "revision": 1}],
        "next_work": {"scope": "fictional", "goal": "Verify fictional file", "inputs": []},
    }
    script: list[tuple[str, dict[str, Any]]] = [
        ("zara_route", {"payload": route}),
        ("write", {"path": "fictional.txt", "content": "fictional transport verified"}),
        ("bash", {"command": "cat fictional.txt"}),
    ]
    if metadata == "aborted":
        script[-1] = ("bash", {"command": "cat fictional.txt; sleep 10"})
    if metadata not in {"missing", "aborted"}:
        script.append(
            (
                "zara_result",
                {
                    "payload": {
                        "outputs": [
                            {
                                "id": "fictional" if metadata in {"valid", "review"} else "absent",
                                "revision": 1,
                            }
                        ]
                    }
                },
            )
        )
    if metadata == "review":
        script.extend(
            [
                ("text", {"text": "The fictional artifact was written and checked."}),
                ("read", {"path": "fictional.txt"}),
                ("zara_result", {"payload": {"outputs": [{"id": "fictional", "revision": 1}]}}),
            ]
        )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:
            pass

        def do_POST(self) -> None:
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(request)
            index = len(calls) - 1
            assert index < 8, "Finite fictional provider request budget exceeded"
            delta: dict[str, Any] = {"role": "assistant"}
            if index < len(script):
                name, arguments = script[index]
                if name == "text":
                    delta["content"] = arguments["text"]
                    finish = "stop"
                else:
                    delta["tool_calls"] = [
                        {
                            "index": 0,
                            "id": f"fictional-{index}",
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                    ]
                    finish = "tool_calls"
            else:
                delta["content"] = (
                    "Controlled review read the fictional file; semantic correctness untested."
                    if metadata == "review"
                    else "The fictional artifact was written and checked."
                )
                finish = "stop"
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
                    "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                },
            ]
            body = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
            body += "data: [DONE]\n\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(body.encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    env = os.environ.copy()
    env["ZARATUSTRA_HOME"] = str(tmp_path / "fictional-home")
    try:
        completed = subprocess.run(
            [
                "node",
                str(Path(__file__).with_name("native_pi_fixture.mjs")),
                str(sdk),
                str(SOURCE),
                str(tmp_path),
                sys.executable,
                f"http://127.0.0.1:{server.server_port}/v1",
                metadata,
            ],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
    (tmp_path / "fictional-transport.stdout").write_text(completed.stdout, encoding="utf-8")
    (tmp_path / "fictional-transport.stderr").write_text(completed.stderr, encoding="utf-8")
    assert completed.returncode == 0, completed.stderr
    evidence = json.loads(completed.stdout.splitlines()[-1])
    assert evidence["provenance"]["semanticEvidence"] is False
    assert len(calls) == len(script) + (metadata != "aborted")
    assert all(call["model"] == "scripted-transport" for call in calls)
    assert all(
        "zara_route" in {tool["function"]["name"] for tool in call["tools"]} for call in calls[:5]
    )
    assert (tmp_path / "fictional.txt").read_text() == "fictional transport verified"
    if metadata != "wrong":
        assert not any("extensionError" in event for event in evidence["events"])
    tools = [event for event in evidence["events"] if event.get("type") == "tool_execution_end"]
    assert {"write", "bash", "zara_route"} <= {event["toolName"] for event in tools}
    if metadata != "aborted":
        assert not next(event for event in tools if event["toolName"] == "bash")["isError"]
    assert not next(event for event in tools if event["toolName"] == "zara_route")["isError"]
    initial_context = next(
        message
        for message in evidence["firstMessages"]
        if message.get("customType") == "zaratustra-context"
    )
    actual_profile = json.loads(initial_context["content"])["current"]["profile"]
    assert actual_profile["model"] == "scripted-transport"
    assert actual_profile["provider"] == "fictional"
    assert actual_profile["api"] == "openai-completions"
    context = next(
        message
        for message in evidence["reopened"]
        if message.get("customType") == "zaratustra-context"
    )
    restored = json.loads(context["content"])
    assert bool(restored["current"]) is (metadata not in {"valid", "review"})
    if metadata not in {"valid", "review"}:
        assert restored["current"]["profile"]["provider"] == "fictional"
        assert restored["current"]["profile"]["model"] == "scripted-transport"
    if metadata == "aborted":
        assert any(event.get("aborted") for event in evidence["events"])
    if metadata in {"valid", "review"}:
        assert any("fictional artifact" in row["body"] for row in restored["core"]["results"])
    if metadata == "review":
        assert len(calls) == 8
        for request in calls[5:]:
            active = {tool["function"]["name"] for tool in request["tools"]}
            assert {"read", "zara_result"} <= active
            assert not {"write", "bash", "zara_change", "zara_route"} & active
        review_contexts = [
            json.loads(message["content"])
            for message in evidence["reviewMessages"]
            if message.get("customType") == "zaratustra-context"
        ]
        review = next(
            context for context in review_contexts if context["current"].get("mode") == "review"
        )
        assert review["current"]["scope"] == "fictional"
        pinned = review["review"]["profile"]["body"]["value"]
        assert pinned["session_id"] == review["current"]["session_id"]
        assert pinned["model"] == "scripted-transport"
        assert any(
            row["attempt"] == review["current"]["builder_attempt"]
            for row in restored["core"]["results"]
        )
        assert (
            review["current"]["session_id"]
            != json.loads(initial_context["content"])["current"]["session_id"]
        )
        final_context = next(
            message
            for message in evidence["reviewReopened"]
            if message.get("customType") == "zaratustra-context"
        )
        final = json.loads(final_context["content"])
        assert not final["current"]
        assert any("Controlled review" in row["body"] for row in final["core"]["results"])
        assert evidence["reviewAcceptance"]["rows"] == []
