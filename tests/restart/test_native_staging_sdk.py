"""Real installed Pi metadata correction transport; no semantic or paid-model evidence."""

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
FINAL = "Fictional corrected metadata task completed; semantic usefulness untested."


@pytest.mark.parametrize("scenario", ["bad-progress", "wrong-family", "stale-stage"])
def test_native_staging_correction(tmp_path: Path, scenario: str) -> None:
    command = shutil.which("pi") or shutil.which("pi.ps1")
    assert command, "Installed Pi required"
    sdk = Path(command).parent / "node_modules/@earendil-works/pi-coding-agent"
    source = Path(os.environ.get("ZARA_STAGING_SOURCE", str(SOURCE / "pi-package")))
    route = {
        "changes": [
            {
                "id": "fictional",
                "kind": "activity",
                "key": "fictional",
                "body": "Fictional staging task",
            }
        ],
        "expected_heads": {"fictional": 0},
        "outputs": [{"id": "fictional", "revision": 1}],
        "next_work": {"scope": "fictional", "goal": "Fictional task", "inputs": []},
    }
    good: dict[str, Any] = {"outputs": [{"id": "fictional", "revision": 1}]}
    progress = {
        "format": "sleep-progress/v1",
        "work_id": "fictional-work",
        "method_ref": {"id": "fictional", "revision": 1},
        "source_high_watermark": 0,
        "enumeration_cursor": [0, 0],
        "enumerated_source_refs": [],
        "selected_source_refs": [],
        "delivered_manifest_refs": [],
        "analysis_result_refs": [],
        "unexplored_coverage_position": None,
        "applied_receipts": [],
        "proposed_changes": [],
        "remaining_refs": [],
        "return_conditions": [],
        "consumed_resource": 0,
        "unresolved_calls": [],
        "stop_reason": "fictional",
        "continuation": "fictional",
    }
    history = {"sequence": 1, "index": 0, "sha256": "0" * 64}
    change: dict[str, Any] = {
        "id": "fictional-data",
        "kind": "data",
        "key": "fictional-data",
        "scope": "fictional",
        "body": progress if scenario == "bad-progress" else "Fictional",
    }
    if scenario in {"wrong-family", "stale-stage"}:
        change["source_refs"] = [history]
        good |= {
            "changes": [
                {
                    "id": "fictional-data",
                    "kind": "data",
                    "key": "fictional-data",
                    "scope": "fictional",
                    "body": {"sources": [history], "content": "Fictional"},
                    "source_refs": [{"id": "fictional", "revision": 1}],
                }
            ],
            "expected_heads": {"fictional-data": 0},
        }
    bad = {
        "outputs": [{"id": "fictional", "revision": 1}],
        "changes": [change],
        "expected_heads": {"fictional-data": 0},
    }
    script = [
        ("zara_route", {"payload": route}),
        ("zara_result", {"payload": bad}),
        ("zara_result", {"payload": good}),
    ]
    if scenario == "stale-stage":
        script = [
            script[0],
            ("zara_result", {"payload": {"outputs": [{"id": "fictional", "revision": 1}]}}),
            ("zara_result", {"payload": bad}),
        ]
    calls: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:
            pass

        def do_POST(self) -> None:
            calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            index = len(calls) - 1
            assert index < 5, "Finite fictional provider budget exceeded"
            if index < len(script):
                name, arguments = script[index]
                delta = {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": f"fictional-{index}",
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                    ],
                }
                finish = "tool_calls"
            else:
                delta = {"role": "assistant", "content": FINAL}
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
    env = os.environ.copy()
    env["ZARATUSTRA_HOME"] = str(tmp_path / "fictional-home")
    try:
        result = subprocess.run(
            [
                "node",
                str(Path(__file__).with_name("native_staging_fixture.mjs")),
                str(sdk),
                str(source),
                str(tmp_path),
                sys.executable,
                f"http://127.0.0.1:{server.server_port}/v1",
            ],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf8",
            timeout=90,
        )
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)
    (tmp_path / "stdout.jsonl").write_text(result.stdout, encoding="utf8")
    (tmp_path / "stderr.txt").write_text(result.stderr, encoding="utf8")
    (tmp_path / "requests.json").write_text(json.dumps(calls), encoding="utf8")
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout.splitlines()[-1])
    stages = [event for event in evidence["events"] if event.get("toolName") == "zara_result"]
    assert len(stages) == 2
    if scenario == "stale-stage":
        assert stages[0]["isError"] is False
        assert stages[1]["isError"] is True
        assert evidence["context"]["current"]
        assert all(not json.loads(row["body"])["text"] for row in evidence["results"]["rows"])
        return
    if scenario == "bad-progress":
        rejected = json.loads(stages[0]["result"]["content"][0]["text"])
        assert rejected["state"] == "rejected"
        assert rejected["staged"] is False
        assert rejected["previous_metadata_cleared"] is False
        assert rejected["rejection"]["code"] == "invalid_request"
        assert rejected["rejection"]["field"] == "changes.0.body.scope"
    else:
        assert stages[0]["isError"] is True
        assert not any(
            row["packet"].get("name") == "result" and row["packet"].get("payload") == bad
            for row in evidence["receipts"]
        )
    assert stages[1]["isError"] is False
    assert stages[1]["result"]["details"]["state"] == "staged"
    assert not evidence["context"]["current"]
    useful = [
        json.loads(row["body"])
        for row in evidence["results"]["rows"]
        if json.loads(row["body"])["text"]
    ]
    assert len(useful) == 1 and useful[0]["text"] == FINAL
    assert useful[0]["accepted"] is False
    terminal = [row for row in evidence["receipts"] if row["packet"].get("command") == "settled"]
    assert len(terminal) == 1 and terminal[0]["packet"]["text"] == FINAL
    contract = next(
        row["result"]["outcome_metadata_contract"]
        for row in evidence["receipts"]
        if row["packet"].get("command") == "verify-profile"
    )
    assert contract["metadata_schema"]
    assert set(contract["progress_schemas"]) == {"sleep-progress/v1", "sleep-progress/v2"}
    assert "scope" in contract["progress_schemas"]["sleep-progress/v1"]["required"]
    assert "predecessor_ref" in contract["progress_schemas"]["sleep-progress/v2"]["required"]
    assert not {"predecessor_ref", "transition", "range_start"} & set(
        contract["progress_schemas"]["sleep-progress/v1"]["properties"]
    )
    assert contract["guidance"]
