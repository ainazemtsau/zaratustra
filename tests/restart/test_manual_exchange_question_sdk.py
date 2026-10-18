"""Real native SDK corrects exchange metadata and resumes a saved question."""

import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from zaratustra_app.manual_exchange import ManualExchange
from zaratustra_app.pi_host import initialize

SOURCE = Path(__file__).resolve().parents[2]
QUESTION = "Which direction should the fictional paper notes cover?"
FINAL = "Partial profile saved; setup remains pending. " + QUESTION


def test_native_exchange_question_metadata_correction_and_fresh_input(tmp_path: Path) -> None:
    command = shutil.which("pi") or shutil.which("pi.ps1")
    assert command, "Installed Pi SDK required"
    sdk = Path(command).parent / "node_modules/@earendil-works/pi-coding-agent"
    home = tmp_path / "fictional-home"
    home.mkdir()
    core, token = initialize(home / "data")
    helper = ManualExchange(core.connect(token))
    calls: list[dict[str, Any]] = []
    phase, index = "pending", 0
    profile_ref: dict[str, Any] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:
            pass

        def do_POST(self) -> None:
            nonlocal index, profile_ref
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append({"phase": phase, "request": request})
            current = index
            index += 1
            assert index <= 7, "Finite fictional localhost budget exceeded"
            name = "zara_exchange"
            payload: dict[str, Any] | None
            if phase == "pending":
                if current == 0:
                    payload = {"operation": "workflow"}
                elif current == 1:
                    payload = {"operation": "begin"}
                elif current == 2:
                    payload = {
                        "operation": "profile",
                        "arguments": {
                            "service": "fictional paper notebook",
                            "configuration": {
                                "route": "manual text",
                                "status": "pending",
                                "question": QUESTION,
                            },
                            "capabilities": {"account_access": "not applicable"},
                        },
                    }
                elif current in {3, 4, 5}:
                    h = next(h for h in helper.catalog()["records"] if ":profile:" in h["id"])
                    profile_ref = {"id": h["id"], "revision": h["revision"]}
                    name = "zara_result"
                    payload = {"outputs": [profile_ref], "state": "completed"}
                    if current == 4:
                        payload = {
                            "outputs": [],
                            "state": "waiting",
                            "wait": {"id": "manual-exchange:direction", "question": QUESTION},
                        }
                else:
                    payload = None
            else:
                if current == 0:
                    payload = {"operation": "begin"}
                elif current == 1:
                    payload = {"operation": "catalog"}
                elif current == 2:
                    name = "zara_read"
                    payload = {"operation": "read_exact", "arguments": profile_ref}
                elif current == 3:
                    name = "zara_result"
                    payload = {"outputs": [profile_ref]}
                else:
                    payload = None
            delta: dict[str, Any] = (
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": f"{phase}-{current}",
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps({"payload": payload}),
                            },
                        }
                    ],
                }
                if payload is not None
                else {"role": "assistant", "content": FINAL}
            )
            chunks = [
                {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "tool_calls" if payload else "stop",
                        }
                    ]
                },
            ]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(
                (
                    "".join("data: " + json.dumps(c) + chr(10) * 2 for c in chunks)
                    + "data: [DONE]"
                    + chr(10) * 2
                ).encode()
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = os.environ.copy()
    env["ZARATUSTRA_HOME"] = str(home)
    evidence = []
    try:
        for stage in ("pending", "pending-resume"):
            phase, index = stage, 0
            folder = tmp_path / stage
            folder.mkdir()
            result = subprocess.run(
                [
                    "node",
                    str(Path(__file__).with_name("native_exchange_fixture.mjs")),
                    str(sdk),
                    os.environ.get("ZARA_EXCHANGE_SOURCE", str(SOURCE / "pi-package")),
                    str(folder),
                    os.environ.get("ZARA_EXCHANGE_PYTHON", sys.executable),
                    f"http://127.0.0.1:{server.server_port}/v1",
                    stage,
                ],
                env=env,
                capture_output=True,
                text=True,
                encoding="utf8",
                timeout=120,
            )
            (folder / "stdout.json").write_text(result.stdout, encoding="utf8")
            (folder / "stderr.txt").write_text(result.stderr, encoding="utf8")
            assert result.returncode == 0, result.stderr
            saved = json.loads(result.stdout.splitlines()[-1])
            evidence.append(saved)
            assert index == (7 if stage == "pending" else 5), saved["messages"]
            assert not any(e.get("isError") or e.get("extensionError") for e in saved["events"])
            assert saved["context"]["current"] == {}
            assert saved["confirmations"] == []
    finally:
        (tmp_path / "provider-requests.json").write_text(json.dumps(calls), encoding="utf8")
        server.shutdown()
        server.server_close()
        thread.join(5)
    rejection = next(
        json.loads(m["content"])
        for m in calls[5]["request"]["messages"]
        if m.get("tool_call_id") == "pending-4"
    )
    assert rejection["state"] == "rejected" and rejection["staged"] is False
    assert rejection["previous_metadata_cleared"] is True
    assert rejection["rejection"]["field"] == "exchange.result_state"
    assert "completed" in rejection["text"] and "pending" in rejection["text"]
    exchange_results = [
        json.loads(r["body"])
        for r in evidence[-1]["results"]["rows"]
        if json.loads(r["body"])["text"] == FINAL
    ]
    assert len(exchange_results) == 2
    assert all(r["outputs"] == [profile_ref] for r in exchange_results)
    assert not helper.coordinator.rows("waits")
    assert not any(h["kind"] == "activity" for h in helper.coordinator.rows("heads"))
    assert [
        {"id": h["id"], "revision": h["revision"]}
        for h in helper.catalog()["records"]
        if ":profile:" in h["id"]
    ] == [profile_ref]
    readback = next(
        json.loads(m["content"])
        for m in calls[10]["request"]["messages"]
        if m.get("tool_call_id") == "pending-resume-2"
    )
    assert readback["body"]["value"]["configuration"]["status"] == "pending"
    assert readback["body"]["value"]["configuration"]["question"] == QUESTION
    assert readback["revision"] == 1
    assert FINAL in json.dumps(calls[7]["request"], ensure_ascii=False)
    begin = next(
        r["result"]
        for r in evidence[0]["receipts"]
        if r["packet"].get("payload", {}).get("operation") == "begin"
    )
    assert begin["outcome_metadata_contract"]["mode"] == "exchange"
    assert begin["outcome_metadata_contract"]["metadata_schema"]["properties"]["state"]["enum"] == [
        "completed"
    ]
