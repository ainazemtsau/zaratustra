"""Independent localhost receiver and fixed contract trace; no legacy test helpers."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

from zaratustra_app import Coordinator, Driver, Pi
from zaratustra_core import Core

REQUEST = "Есть десять минут, потренируем разговор в отеле. Начни без плана и карточек"
CORRECTION = "Теперь только пять минут"
METHOD = {"id": "method", "revision": 1}
PROFILE = {"id": "profile", "revision": 1}
MEMORY = {"id": "memory", "revision": 1, "role": "must_be_current"}


class Receiver:
    def __init__(self) -> None:
        self.received: list[dict[str, Any]] = []
        self.actions: list[str] = []
        self.outputs: list[dict[str, Any]] = [
            {
                "state": "waiting",
                "text": "Good evening. Do you have a reservation?",
                "wait": {"id": "W7", "question": "Do you have a reservation?"},
                "native_tool_call_id": "create-activity",
                "expected_heads": {"activity": 0},
                "tool_changes": [
                    {
                        "id": "activity",
                        "kind": "activity",
                        "key": "practice",
                        "body": "Hotel conversation",
                    }
                ],
            },
            {
                "state": "completed",
                "text": "Welcome. Here is your key. Five-minute practice saved.",
            },
        ]

    def __call__(self, context: dict[str, Any], action_id: str) -> bytes:
        self.received.append(context)
        self.actions.append(action_id)
        return json.dumps(self.outputs[len(self.actions) - 1], ensure_ascii=False).encode()


class Provider(ThreadingHTTPServer):
    def __init__(self, receiver: Receiver):
        super().__init__(("127.0.0.1", 0), Handler)
        self.receiver = receiver
        self.packets: list[dict[str, Any]] = []


class Handler(BaseHTTPRequestHandler):
    server: Provider

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        packet = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.packets.append(packet)
        user = next(m for m in reversed(packet["messages"]) if m["role"] == "user")
        content = user["content"]
        if isinstance(content, list):
            content = "".join(c.get("text", "") for c in content)
        supplied = json.loads(content)
        is_tool_return = any(m["role"] == "tool" for m in packet["messages"])
        if is_tool_return:
            output = dict(self.server.receiver.outputs[0])
            for field in ("tool_changes", "native_tool_call_id", "expected_heads"):
                output.pop(field)
            text = json.dumps(output)
        else:
            text = self.server.receiver(supplied["context"], supplied["action_id"]).decode()
        parsed = json.loads(text)
        tool = parsed.get("tool_changes")
        tool_delta = (
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": parsed["native_tool_call_id"],
                        "type": "function",
                        "function": {
                            "name": "zara_change",
                            "arguments": json.dumps(
                                {
                                    "intent_json": json.dumps(
                                        {
                                            "changes": tool,
                                            "expected_heads": parsed["expected_heads"],
                                        }
                                    )
                                }
                            ),
                        },
                    }
                ]
            }
            if tool
            else {"content": text}
        )
        chunks = [
            {
                "id": "synthetic",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            },
            {
                "id": "synthetic",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": tool_delta, "finish_reason": None}],
            },
            {
                "id": "synthetic",
                "object": "chat.completion.chunk",
                "choices": [
                    {"index": 0, "delta": {}, "finish_reason": "tool_calls" if tool else "stop"}
                ],
            },
            {
                "id": "synthetic",
                "object": "chat.completion.chunk",
                "choices": [],
                "usage": {"prompt_tokens": 20, "completion_tokens": 20, "total_tokens": 40},
            },
        ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(("data: " + json.dumps(chunk) + chr(10) * 2).encode())
        self.wfile.write(("data: [DONE]" + chr(10) * 2).encode())
        self.wfile.flush()


def fixture(root: Path) -> tuple[Any, Any, Any]:
    core, owner_token = Core.initialize(root / "space")
    owner = core.connect(owner_token)
    permissions = [
        "read",
        "read_snapshot",
        "apply_changes",
        "open_work",
        "prepare_attempt",
        "claim_dispatch",
        "observe_attempt",
        "commit_outcome",
        "reserve_tool",
        "control_work",
    ]
    executor_token = core.grant(owner_token, "executor", permissions, origin="host")
    executor = core.connect(executor_token)
    changes: list[dict[str, Any]] = [
        {
            "id": "method",
            "kind": "method",
            "key": "conversation",
            "body": "Begin useful practice; preserve original request and corrections.",
        },
        {
            "id": "profile",
            "kind": "profile",
            "key": "local-scripted",
            "body": {"resource_unit": "calls", "reconcile": "receiver-log/v1"},
        },
        {"id": "memory", "kind": "memory", "key": "preference", "body": "Keep practice brief."},
    ]
    owner.call(
        "apply_changes", {"changes": changes}, "seed", expected_heads={c["id"]: 0 for c in changes}
    )
    for n in range(1, 21):
        ingest(owner, str(n), REQUEST if n == 20 else f"Synthetic prior input {n}")
    owner.call(
        "open_work",
        {
            "id": "work",
            "conversation": "conversation",
            "goal": "Begin requested practice",
            "method_ref": METHOD,
            "inputs": [MEMORY],
            "call_limit": 4,
            "continuation_policy": "durable",
        },
        "work:create",
    )
    return core, owner, executor


def ingest(client: Any, event: str, text: str, reply: Any = None) -> dict[str, Any]:
    payload = {
        "conversation": "conversation",
        "event_id": event,
        "raw_base64": base64.b64encode(text.encode()).decode(),
    }
    if reply:
        payload["reply_to"] = reply
    return cast(dict[str, Any], client.call("ingest_message", payload, "input:" + event))


def inspect(core: Core, table: str) -> list[dict[str, Any]]:
    # Independent physical oracle: not production readers/admission functions.
    with sqlite3.connect(core.path) as db:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute("SELECT * FROM " + table)]


def pi_cli() -> Path:
    command = shutil.which("pi") or shutil.which("pi.ps1")
    if not command:
        raise RuntimeError("required native Pi unavailable")
    return (
        Path(command).parent
        / "node_modules"
        / "@earendil-works"
        / "pi-coding-agent"
        / "dist"
        / "bundle"
        / "cli.js"
    )


def trace(root: Path, mode: str) -> dict[str, Any]:
    core, owner, executor = fixture(root)
    receiver = Receiver()
    provider = Provider(receiver) if mode == "pi" else None
    thread = threading.Thread(target=provider.serve_forever, daemon=True) if provider else None
    if thread:
        thread.start()
    port = (
        Pi(pi_cli(), root / "pi-home", f"http://127.0.0.1:{provider.server_port}/v1")
        if provider
        else Driver(receiver)
    )
    coordinator = Coordinator(executor)
    try:
        prepared = coordinator.prepare("work", "A1", PROFILE)
        assert prepared["pinned"]["messages"][-1]["seq"] == 20
        raw = coordinator.dispatch("A1", 1, port)
        assert len(receiver.actions) == 1
        assert receiver.received[0]["raw_messages"][-1] == REQUEST
        assert receiver.received[0]["inputs"][0]["body"]["value"] == "Keep practice brief."
        assert receiver.received[0]["method"]["revision"] == 1
        assert any(r["key"] == "preference" for r in receiver.received[0]["catalog"])
        assert (
            receiver.received[0]["manifest"][-1]["sha256"]
            == hashlib.sha256(REQUEST.encode()).hexdigest()
        )
        ingest(owner, "21", CORRECTION)
        # Reopen and discard all client-local history: retained raw terminal is sufficient.
        reopened = Core(core.root).connect(executor.token)
        result1 = Coordinator(reopened).recover("A1", pi=mode == "pi")
        assert result1["cutoff"] == 20
        assert inspect(core, "conversations")[0]["cursor"] == 20
        assert any(i["kind"] == "input" for i in inspect(core, "intents"))
        assert len(receiver.actions) == 1
        assert Coordinator(reopened).recover("A1", pi=mode == "pi") == result1
        assert len(inspect(core, "results")) == 1
        assert len(inspect(core, "tool_calls")) == 1, json.dumps(
            port.events if isinstance(port, Pi) else [], ensure_ascii=False
        )
        assert inspect(core, "tool_calls")[0]["receipt"] == "A1:tool:create-activity"
        assert inspect(core, "waits")[0]["id"] == "W7"
        ingest(owner, "22", "Yes, under the name Sam.", {"id": "W7", "revision": 1})
        prepared2 = Coordinator(reopened).prepare("work", "A2", PROFILE)
        assert prepared2["pinned"]["messages"][0]["seq"] == 21
        assert (
            base64.b64decode(prepared2["pinned"]["prior_messages"][-1]["raw"]).decode() == REQUEST
        )
        assert prepared2["pinned"]["prior_waits"][0]["id"] == "W7"
        assert (
            json.loads(prepared2["pinned"]["prior_results"][0]["body"])["text"]
            == "Good evening. Do you have a reservation?"
        )
        assert prepared2["pinned"]["work"]["goal"] == "Begin requested practice"
        assert prepared2["pinned"]["tool_ledger"][0]["receipt"] == "A1:tool:create-activity"
        Coordinator(reopened).dispatch("A2", 1, port)
        final = Coordinator(Core(core.root).connect(executor.token)).recover("A2", pi=mode == "pi")
        assert receiver.received[1]["raw_messages"] == [CORRECTION, "Yes, under the name Sam."]
        assert (
            base64.b64decode(receiver.received[1]["prior_messages"][-1]["raw"]).decode() == REQUEST
        )
        assert receiver.received[1]["prior_waits"][0]["body"] == json.dumps(
            {"id": "W7", "question": "Do you have a reservation?"},
            sort_keys=True,
            separators=(",", ":"),
        )
        assert receiver.received[1]["work"]["goal"] == "Begin requested practice"
        assert any(r["id"] == "activity" for r in receiver.received[1]["catalog"])
        assert len(receiver.actions) == len(set(receiver.actions)) == 2
        assert final["state"] == "completed" and final["accepted"] is False
        assert inspect(core, "acceptance") == []
        assert inspect(core, "conversations")[0]["cursor"] == 22
        assert inspect(core, "waits")[0]["status"] == "answered"
        evidence = {
            "client": mode,
            "actions": receiver.actions,
            "received": receiver.received,
            "results": inspect(core, "results"),
            "conversations": inspect(core, "conversations"),
            "tool_calls": inspect(core, "tool_calls"),
            "raw_terminal_sha256": hashlib.sha256(raw).hexdigest(),
            "native_rpc_events": port.events if isinstance(port, Pi) else [],
            "native_provider_packets": provider.packets if provider else [],
            "native_callbacks": port.callbacks if isinstance(port, Pi) else [],
        }
        destination = os.environ.get("ZARA_RESTART_EVIDENCE")
        if destination:
            directory = Path(destination)
            directory.mkdir(parents=True, exist_ok=True)
            (directory / (mode + "-trace.json")).write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return evidence
    finally:
        if provider:
            provider.shutdown()
            provider.server_close()
        if thread:
            thread.join(timeout=2)
