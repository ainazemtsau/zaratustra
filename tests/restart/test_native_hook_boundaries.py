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
        "review-cancel-normal",
        "failed-input",
        "profile-failure",
        "tool-block",
        "command-failure",
        "cancel-stream",
        "parallel-lifecycle",
        "parallel-rejection",
        "read-shape-correction",
        "read-admission-correction",
        "read-revoked",
        "read-transport",
        "read-payload",
        "read-wire",
        "history-large",
        "page-large",
        "exact-large",
        "codec-readable",
        "codec-fallback",
        "codec-unfit",
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
    if scenario in {"review-command", "review-reopen", "review-cancel-normal"}:
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
    if scenario == "review-cancel-normal":
        continuation = {
            "changes": [],
            "expected_heads": {},
            "outputs": [{"id": "fictional", "revision": 1}],
            "next_work": {"scope": "fictional", "goal": "New ordinary work", "inputs": []},
        }
        script = script[:5] + [
            ("text", "Incomplete retained review"),
            ("zara_route", {"payload": continuation}),
            ("zara_result", result),
            ("text", "Ordinary final after review cancel"),
        ]
    if scenario.startswith("parallel-"):
        script = script[:1] + [
            ("parallel-read", {}),
            ("zara_result", result),
            ("text", "Exact fictional parallel final"),
        ]
    if scenario.startswith("read-"):
        invalid_args = (
            {"conversation": "fictional-sleep-conversation"}
            if scenario == "read-shape-correction"
            else {"scope": "space", "high_watermark": 2147483647}
        )
        if scenario in {"read-revoked", "read-transport", "read-payload", "read-wire"}:
            invalid_args = {"scope": "space"}
        script = script[:1] + [
            ("zara_read", {"payload": {"operation": "read_history", "arguments": invalid_args}}),
            (
                "zara_read",
                {
                    "payload": {
                        "operation": "read_history",
                        "arguments": {"scope": "space", "limit": 1},
                    }
                },
            ),
            ("zara_result", result),
            ("text", "Exact corrected read final"),
        ]
    if scenario == "history-large":
        script = script[:1] + [
            (
                "zara_read",
                {
                    "payload": {
                        "operation": "read_history",
                        "arguments": {"scope": "fictional", "limit": 100},
                    }
                },
            ),
            (
                "zara_read",
                {
                    "payload": {
                        "operation": "read_history",
                        "arguments": {"scope": "fictional", "limit": 1},
                    }
                },
            ),
            ("zara_result", result),
            ("text", "Exact bounded history final; withheld source unexamined"),
        ]
    if scenario in {"page-large", "exact-large"}:
        first = (
            {
                "operation": "read_page",
                "arguments": {
                    "table": "messages",
                    "conversation": "fictional-large-page",
                    "limit": 1,
                },
            }
            if scenario == "page-large"
            else {"operation": "read_exact", "arguments": {"id": "huge-history", "revision": 1}}
        )
        second = {
            "operation": "read_page",
            "arguments": {
                "table": "messages",
                "conversation": "fictional-large-page",
                "limit": 1,
                "columns": ["seq", "event"],
            },
        }
        script = script[:1] + [
            ("zara_read", {"payload": first}),
            ("zara_read", {"payload": second}),
            ("zara_result", result),
            ("text", "Exact bounded read final"),
        ]
    if scenario == "codec-readable":
        script = script[:1] + [
            ("zara_result", result),
            ("text", "Fictional builder final"),
            (
                "zara_read",
                {
                    "payload": {
                        "operation": "read_history",
                        "arguments": {"scope": "fictional", "limit": 100},
                    }
                },
            ),
            ("text", "Readability protocol only; no Sleep analysis or adaptation asserted"),
        ]
    if scenario in {"codec-fallback", "codec-unfit"}:
        script = [
            (
                "text",
                "Encoded source retained; decoded text not delivered; no analysis asserted",
            )
        ]
    calls: list[Any] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            index = len(calls) - 1
            if (
                scenario == "codec-readable"
                and index >= 3
                and "CODEC_FACT_7F4A" not in json.dumps(calls[-1], ensure_ascii=False)
            ):
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    b'{"error":{"message":"Fixture source fact is not readable",'
                    b'"type":"invalid_request_error"}}'
                )
                return

            if scenario == "history-large" and len(json.dumps(calls[-1]).encode("utf-8")) > 256000:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    b'{"error":{"message":"Fictional provider context window exceeded",'
                    b'"type":"invalid_request_error"}}'
                )
                return

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
            if name == "parallel-read":
                delta["tool_calls"] = [
                    {
                        "index": i,
                        "id": f"parallel-read-{i}",
                        "type": "function",
                        "function": {"name": "read", "arguments": json.dumps({"path": path})},
                    }
                    for i, path in enumerate(["read-a.txt", "read-b.txt"])
                ]
            elif name == "text":
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
    elif scenario == "review-cancel-normal":
        assert "write" in value["activeTools"] and "bash" in value["activeTools"]
        assert "zara_route" in value["activeTools"]
        assert value["delivery"]["result"]["text"] == "Ordinary final after review cancel"
        assert len(calls) == 9
    elif scenario.startswith("parallel-"):
        trace = value["transport"]["trace"]
        ends = [
            row
            for row in trace
            if row["packet"].get("command") == "observation"
            and row["packet"].get("value", {}).get("kind") == "tool_execution_end"
            and row["packet"]["value"]["event"].get("toolCallId", "").startswith("parallel-read-")
        ]
        assert {row["packet"]["value"]["event"]["toolCallId"] for row in ends} == {
            "parallel-read-0",
            "parallel-read-1",
        }
        assert value["transport"]["maxRunning"] == 1
        assert len(ends) == 2
        assert all(row["packet"]["session_id"] == value["originalSession"] for row in ends)
        assert all(row["packet"]["data_root"] == str(tmp_path / "home" / "data") for row in ends)
        retained: dict[str, set[str]] = {"tool_call": set(), "tool_execution_end": set()}
        import base64

        for row in value["observations"]["rows"]:
            body = json.loads(row["body"])
            raw = json.loads(base64.b64decode(body["raw_base64"]))
            kind = raw.get("kind")
            if kind in retained:
                retained[kind].add(raw["event"].get("toolCallId", ""))
        assert {"parallel-read-0", "parallel-read-1"} <= retained["tool_call"]
        if scenario == "parallel-lifecycle":
            assert {"parallel-read-0", "parallel-read-1"} <= retained["tool_execution_end"]

        if scenario == "parallel-lifecycle":
            assert value["delivery"]["result"]["text"] == "Exact fictional parallel final"
            assert all(row["result"]["state"] == "observed" for row in ends)
        else:
            assert ends[0]["result"]["state"] == "error"
            assert ends[0]["result"]["rejection"]["code"] == "denied"
            assert ends[1]["result"]["state"] == "observed"
            assert value["context"]["current"]["attempt"]
            assert value["delivery"]["state"] == "error"
    elif scenario == "history-large":
        assert len(calls) == 5
        assert (
            value["delivery"]["result"]["text"]
            == "Exact bounded history final; withheld source unexamined"
        )
        ends = [
            e
            for e in value["events"]
            if e.get("type") == "tool_execution_end" and e.get("toolName") == "zara_read"
        ]
        assert len(ends) == 2 and not any(e["isError"] for e in ends)
        for event in ends:
            assert (
                len(
                    json.dumps(event["result"], ensure_ascii=False, separators=(",", ":")).encode(
                        "utf-8"
                    )
                )
                <= 50 * 1024
            )
        core_reads = [
            row["result"]
            for row in value["transport"]["trace"]
            if row["packet"].get("name") == "read"
            and row["packet"].get("payload", {}).get("operation") == "read_history"
        ]
        assert len(core_reads) == 2
        for event, core_read in zip(ends, core_reads, strict=True):
            assert (
                len(json.dumps(core_read, ensure_ascii=False, separators=(",", ":")).encode())
                <= 51200
            )
            presented = json.loads(event["result"]["content"][0]["text"])
            assert presented["query_coverage"] == core_read["query_coverage"]
            assert presented["query_coverage"]["byte_limit"] == 51200
            assert presented["query_coverage"]["returned"] == len(core_read["sources"])
            assert presented["projection"]["core_returned"] == len(core_read["sources"])
            assert "no analysis is asserted" in presented["projection"]["coverage"]
            assert "sources" not in event["result"]["details"]
            if not core_read["sources"] and core_read.get("state") == "NOT_DELIVERED":
                assert presented["state"] == "NOT_DELIVERED"
                assert presented["query_coverage"]["first_withheld_source_ref"]
                assert presented["query_coverage"]["first_withheld_source_bytes"] > 0
        first = json.loads(ends[0]["result"]["content"][0]["text"])
        assert first["has_more"] and first["projection"]["withheld"] > 0
        if first["sources"]:
            assert first["sources"][0]["source_ref"]["sha256"]
        else:
            assert first["state"] == "NOT_DELIVERED"
            assert first["reason"] == "single_source_too_large"
            assert first["cursor"] == [0, 0]
            assert first["source_bytes"] > 0 and first["source_view_bytes"] > 0
            assert first["required_tool_result_bytes"] > 50 * 1024
    elif scenario in {"page-large", "exact-large"}:
        assert len(calls) == 5
        assert value["delivery"]["result"]["text"] == "Exact bounded read final"
        ends = [
            e
            for e in value["events"]
            if e.get("type") == "tool_execution_end" and e.get("toolName") == "zara_read"
        ]
        first = json.loads(ends[0]["result"]["content"][0]["text"])
        assert first["state"] == "NOT_DELIVERED" and not ends[0]["isError"]
        if scenario == "exact-large":
            assert first["ref"] == {"id": "huge-history", "revision": 1}
        assert "rows" in json.loads(ends[1]["result"]["content"][0]["text"])
        for event in ends:
            assert (
                len(
                    json.dumps(event["result"], ensure_ascii=False, separators=(",", ":")).encode(
                        "utf-8"
                    )
                )
                <= 50 * 1024
            )
            assert "rows" not in event["result"]["details"]
    elif scenario in {"codec-fallback", "codec-unfit"}:
        assert value["context"]["current"]["mode"] == "sleep"
        assert value["context"]["current"]["attempt"]
        assert value["delivery"]["state"] == "error"
        if scenario == "codec-unfit":
            assert not calls
            assert "presentation does not fit" in json.dumps(value["notifications"])
        else:
            assert len(calls) == 1
            contexts = [
                json.loads(message["content"])
                for message in value["afterSecond"]
                if message.get("customType") == "zaratustra-context"
            ]
            fallback = contexts[-1]
            assert fallback["native_source_data_presentation"]["status"] == "decoded_NOT_DELIVERED"
            assert fallback["native_source_data_presentation"]["analysisAsserted"] is False
            assert fallback["sleep"] == value["context"]["sleep"]
            assert (
                len(json.dumps(fallback, ensure_ascii=False, separators=(",", ":")).encode())
                <= 1048576
            )
            import base64

            encoded = base64.b64encode(b"FALLBACK_SOURCE_9C2D:" + bytes(262144)).decode()
            assert json.dumps(fallback).count(encoded) == 1
            assert json.dumps(calls[0]).count(encoded) == 1
            assert "FALLBACK_SOURCE_9C2D" not in json.dumps(calls[0])
            assert "raw_utf8" not in json.dumps(fallback)
            assert "decoded_NOT_DELIVERED" in json.dumps(calls[0])
    elif scenario == "codec-readable":
        assert len(calls) == 5
        assert "CODEC_FACT_7F4A" in json.dumps(calls[3], ensure_ascii=False)
        reads = [
            e
            for e in value["events"]
            if e.get("type") == "tool_execution_end" and e.get("toolName") == "zara_read"
        ]
        assert "CODEC_FACT_7F4A" in reads[0]["result"]["content"][0]["text"]
        assert "CODEC_FACT_7F4A" in json.dumps(value["afterSecond"], ensure_ascii=False)
        assert value["context"]["current"]["mode"] == "sleep"
        assert value["context"]["current"]["attempt"]
    elif scenario.startswith("read-"):
        if scenario in {"read-shape-correction", "read-admission-correction"}:
            assert len(calls) == 5
            assert value["delivery"]["result"]["text"] == "Exact corrected read final"
            ends = [
                e
                for e in value["events"]
                if e.get("type") == "tool_execution_end" and e.get("toolName") == "zara_read"
            ]
            assert [e["toolCallId"] for e in ends] == ["fictional-1", "fictional-2"]
            assert (
                ends[0]["isError"]
                or ends[0]["result"].get("details", {}).get("state") == "rejected"
            )
            assert not ends[1]["isError"]
            import base64

            retained_calls: set[str] = set()
            retained_ends: set[str] = set()
            for observation in value["observations"]["rows"]:
                raw = json.loads(base64.b64decode(json.loads(observation["body"])["raw_base64"]))
                event = raw.get("event", {})
                if raw.get("kind") == "tool_call":
                    retained_calls.add(event["toolCallId"])
                elif raw.get("kind") == "tool_execution_end":
                    retained_ends.add(event["toolCallId"])
                elif raw.get("kind") == "turn_end":
                    retained_calls.update(
                        part["id"]
                        for part in event.get("message", {}).get("content", [])
                        if part.get("type") == "toolCall"
                    )
            assert {"fictional-1", "fictional-2"} <= retained_calls
            assert {"fictional-1", "fictional-2"} <= retained_ends

            if scenario == "read-admission-correction":
                assert (
                    ends[0]["result"]["details"]["rejection"]["field"] == "history.high_watermark"
                )
        else:
            assert len(calls) == 2
            assert value["delivery"]["state"] == "error"
            assert value["context"]["current"]["attempt"]
            failures = [
                e
                for e in value["events"]
                if e.get("type") == "tool_execution_end" and e.get("toolName") == "zara_read"
            ]
            assert len(failures) == 1 and failures[0]["isError"]
            assert failures[0]["result"].get("details", {}).get("state") != "rejected"
            text = failures[0]["result"]["content"][0]["text"]
            expected = {
                "read-revoked": "denied/read",
                "read-transport": "exited with 23",
                "read-payload": "invalid_request/payload",
                "read-wire": "invalid_request/wire",
            }
            assert expected[scenario] in text

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
        source_text = base64.b64decode(observation["raw_base64"]).decode("utf-8")
        if source_text == "CODEC_FACT_7F4A: Ж🙂 source data only":
            continue
        raw = json.loads(source_text)
        if raw.get("kind") == "turn_end":
            assert "context" not in raw["event"]
            assert "message" in raw["event"]
