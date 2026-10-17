"""Real Pi SDK message boundaries and admission with fictional local inference."""

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


@pytest.mark.parametrize(
    "scenario",
    ["checkpoint", "route-sibling", "blocked-write", "override-read", "steps", "kill-turn"],
)
def test_native_setup_sdk(tmp_path: Path, scenario: str) -> None:
    command = shutil.which("pi") or shutil.which("pi.ps1")
    assert command
    sdk = Path(command).parent / "node_modules/@earendil-works/pi-coding-agent"
    route = {
        "changes": [
            {"id": "bird", "kind": "activity", "key": "bird", "body": "Fictional bird journal"}
        ],
        "expected_heads": {"bird": 0},
        "outputs": [{"id": "bird", "revision": 1}],
        "next_work": {
            "scope": "bird",
            "goal": "Create a useful journal",
            "inputs": [],
            "setup": True,
        },
    }
    stage = {
        "outputs": [{"id": "bird", "revision": 1}],
        "changes": [
            {
                "id": "notes",
                "kind": "data",
                "key": "notes",
                "scope": "bird",
                "body": "A useful saved fictional journal",
            }
        ],
        "expected_heads": {"notes": 0},
    }
    scripts: list[list[tuple[str, Any]]] = [[("zara_route", {"payload": route})]]
    if scenario == "route-sibling":
        scripts[0].append(("zara_result", {"payload": stage}))
    elif scenario in {"blocked-write", "override-read"}:
        # Keep a real write tool active deliberately; the trusted hook must still block execution.
        scripts.append(
            [("write", {"path": str(tmp_path / "forbidden.txt"), "content": "MUST NOT EXIST"})]
            if scenario == "blocked-write"
            else [("zara_read_file", {"path": "facts.txt"})]
        )
        scripts.append([("zara_result", {"payload": stage})])
    elif scenario == "steps":
        scripts.extend(
            [
                [
                    (
                        "zara_result",
                        {
                            "payload": stage
                            | {"next_work": {"goal": "Ask a necessary location", "inputs": []}}
                        },
                    )
                ],
                [],
                [
                    (
                        "zara_result",
                        {
                            "payload": {
                                "outputs": [{"id": "bird", "revision": 1}],
                                "state": "waiting",
                                "wait": {"id": "location", "question": "Which location?"},
                            }
                        },
                    )
                ],
                [],
                [("zara_result", {"payload": {"outputs": [{"id": "bird", "revision": 1}]}})],
            ]
        )
    else:
        (tmp_path / "facts.txt").write_text(
            "Distinctive fictional observation: amber bird.", encoding="utf-8"
        )
        scripts.extend(
            [[("zara_read_file", {"path": "facts.txt"})], [("zara_result", {"payload": stage})]]
        )
    calls: list[dict[str, Any]] = []
    in_flight = threading.Event()
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:
            pass

        def do_POST(self) -> None:
            calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            index = len(calls) - 1
            if scenario == "kill-turn" and index == 1:
                in_flight.set()
                release.wait(30)
                return
            assert index < (8 if scenario == "steps" else 6)
            if index < len(scripts) and scripts[index]:
                delta: dict[str, Any] = {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "index": n,
                            "id": f"call-{index}-{n}",
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                        for n, (name, arguments) in enumerate(scripts[index])
                    ],
                }
                finish = "tool_calls"
            else:
                delta = {
                    "role": "assistant",
                    "content": (
                        "Which location?"
                        if scenario == "steps" and index == 4
                        else "The useful fictional journal checkpoint is ready."
                    ),
                }
                finish = "stop"
            chunks = [
                {
                    "id": "fictional",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                },
                {
                    "id": "fictional",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                },
            ]
            body = "".join("data: " + json.dumps(chunk) + chr(10) * 2 for chunk in chunks)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write((body + "data: [DONE]" + chr(10) * 2).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    env = os.environ.copy()
    env["ZARATUSTRA_HOME"] = str(tmp_path / "home")
    try:
        argv = [
            "node",
            str(Path(__file__).with_name("native_setup_fixture.mjs")),
            str(sdk),
            str(SOURCE / "pi-package"),
            str(tmp_path),
            sys.executable,
            f"http://127.0.0.1:{server.server_port}/v1",
            scenario,
        ]
        if scenario == "kill-turn":
            from zaratustra_core import Core

            from .support import inspect
            from .test_activity_setup import session as fresh_session

            child = subprocess.Popen(
                argv,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            try:
                assert in_flight.wait(30), "Actual second model request was not reached"
                child.kill()
                stdout, stderr = child.communicate(timeout=15)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(15)
                release.set()
            assert child.returncode != 0
            core = Core(tmp_path / "home" / "data")
            token = (core.root / "owner.credential").read_text(encoding="utf-8")
            attempts = inspect(core, "attempts")
            old = attempts[-1]
            assert old["status"] == "claimed"
            recovered = fresh_session(core, token, "fresh-sdk-process").reopen()
            assert recovered["current"]["work"] == old["work"]
            assert recovered["current"]["generation"] == old["generation"] + 1
            assert inspect(core, "attempts")[-2]["status"] == "superseded"
            assert len(inspect(core, "results")) == 1
            (tmp_path / "kill-proof.json").write_text(
                json.dumps(
                    {
                        "modelRequests": len(calls),
                        "actualExit": child.returncode,
                        "oldAttempt": old["id"],
                        "newAttempt": recovered["current"]["attempt"],
                        "resultCount": 1,
                        "stdoutBytes": len(stdout),
                        "stderrBytes": len(stderr),
                    }
                ),
                encoding="utf-8",
            )
            return
        result = subprocess.run(
            argv, env=env, capture_output=True, text=True, encoding="utf-8", timeout=100
        )
        if scenario == "steps":
            assert result.returncode == 0, result.stderr
            before_reply = json.loads(result.stdout.splitlines()[-1])
            assert before_reply["context"]["waiting"][0]["question"] == "Which location?"
            assert len(before_reply["results"]["rows"]) == 3
            argv[-1] = "reply"
            result = subprocess.run(
                argv, env=env, capture_output=True, text=True, encoding="utf-8", timeout=100
            )
            (tmp_path / "before-reply.json").write_text(json.dumps(before_reply), encoding="utf-8")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)
    (tmp_path / "stdout.json").write_text(result.stdout, encoding="utf-8")
    (tmp_path / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    (tmp_path / "requests.json").write_text(json.dumps(calls), encoding="utf-8")
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout.splitlines()[-1])
    if scenario == "override-read":
        assert not calls
        assert "conflicts" in str(evidence["loaderErrors"])
        assert not (tmp_path / "forbidden.txt").exists()
        return
    assert calls, "Fixture inference must really reach localhost"
    if scenario in {"checkpoint", "steps"}:
        contexts = [
            json.loads(m["content"])
            for m in evidence["messages"]
            if m.get("customType") == "zaratustra-context"
        ]
        assert contexts
        shown = contexts[0]
        expected = (
            "The fictional lake"
            if scenario == "steps"
            else "Create a useful fictional bird journal in saved steps."
        )
        assert shown["pinned"]["messages"][-1]["raw_utf8"] == expected
        assert "raw" not in shown["pinned"]["messages"][-1]
        assert all("body" not in row for row in shown["core"]["attempts"])
        assert shown["pinned"]["native_message_data_view"]["kind"] == "source_data"
    results = evidence["results"]["rows"]
    if scenario == "route-sibling":
        assert len(results) == 1
        assert evidence["context"]["current"]["staged"] == {}
        assert any("native.origin" in str(e) for e in evidence["events"])
        observed = [json.loads(r["body"]) for r in evidence["observations"]["rows"]]
        assert not any(
            r["attempt_id"] == evidence["context"]["current"]["attempt"] for r in observed
        )
    else:
        assert len(results) == (4 if scenario == "steps" else 2)
        assert evidence["context"]["current"] == {}
        assert "useful fictional journal" in results[-1]["body"]
        assert not (tmp_path / "forbidden.txt").exists()
        if scenario == "checkpoint":
            assert "amber bird" in json.dumps(calls[-1])
