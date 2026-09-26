"""Ordinary Pi source/Claim/memory/context/handoff trace with a local synthetic model."""

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
from typing import Any, cast
from uuid import uuid4

from tests.zaratustra.foundation.test_binding import _apply, _ready
from zaratustra.foundation import (
    ClaimState,
    CreateWorkRequest,
    HandoffState,
    OutputContract,
    StopAttemptRequest,
    WorkState,
    read_execution,
    read_knowledge,
    read_space,
    search_knowledge,
    upgrade_knowledge_space,
)
from zaratustra.pi_adapter import Bridge, BridgeServer


class Provider(ThreadingHTTPServer):
    def __init__(self, script: list[dict[str, object]]) -> None:
        super().__init__(("127.0.0.1", 0), ProviderHandler)
        self.script = script
        self.calls = 0
        self.requests: list[dict[str, Any]] = []


class ProviderHandler(BaseHTTPRequestHandler):
    server: Provider

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(body)
        self.server.calls += 1
        call = self.server.calls
        scripted = self.server.script[call - 1] if call <= len(self.server.script) else None
        chunks: list[dict[str, object]] = [
            {
                "id": "synthetic",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            }
        ]
        delta = (
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": f"call-{call}",
                        "type": "function",
                        "function": {"name": "zara_memory", "arguments": json.dumps(scripted)},
                    }
                ]
            }
            if scripted is not None
            else {"content": "The addressed step is complete."}
        )
        chunks.append(
            {
                "id": "synthetic",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
        )
        chunks.append(
            {
                "id": "synthetic",
                "object": "chat.completion.chunk",
                "choices": [
                    {"index": 0, "delta": {}, "finish_reason": "tool_calls" if scripted else "stop"}
                ],
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


def source(text: str, channel: str = "document") -> dict[str, object]:
    return {
        "kind": "source",
        "channel": channel,
        "connection": "local-document",
        "profile_revision": 1,
        "sender": "owner",
        "media_type": "text/plain",
        "capture": "full",
        "content_text": text,
    }


def apply(
    record_id: object, state: dict[str, object], *, revision: int | None = None
) -> dict[str, object]:
    intent: dict[str, object] = {
        "kind": "revise_knowledge" if revision else "create_knowledge",
        "record_id": str(record_id),
        "state": state,
    }
    if revision is not None:
        intent["expected_revision"] = revision
    return {"mode": "apply", "intent": intent}


def run_process(
    directory: Path,
    runtime: Path,
    bridge: Bridge,
    provider: Provider,
    *,
    work: tuple[object, object] | None = None,
    compact: bool = False,
    continue_after_compact: bool = False,
) -> list[dict[str, object]]:
    bridge_server = BridgeServer(bridge)
    bridge_thread = threading.Thread(target=bridge_server.serve_forever, daemon=True)
    bridge_thread.start()
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    installed = runtime / f"zaratustra-knowledge-{uuid4()}.ts"
    shutil.copyfile(Path(str(files("zaratustra.pi_adapter").joinpath("extension.ts"))), installed)
    home = directory / f"pi-home-{uuid4()}"
    home.mkdir()
    if compact:
        agent_home = home / "pi-agent"
        agent_home.mkdir()
        (agent_home / "settings.json").write_text(
            json.dumps(
                {"compaction": {"enabled": True, "keepRecentTokens": 1, "reserveTokens": 512}}
            ),
            encoding="utf-8",
        )
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP"}
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
            "ZARA_LOCAL_CONTEXT_WINDOW": "16384",
            "ZARA_LOCAL_MAX_TOKENS": "512",
        }
    )
    if work:
        env["ZARA_INITIAL_ACTIVITY_ID"], env["ZARA_INITIAL_WORK_ID"] = map(str, work)
    cli = runtime / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js"
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
    observed: list[dict[str, object]] = []
    try:
        process = subprocess.Popen(
            command,
            cwd=directory,
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
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    events.put(event)

        threading.Thread(target=reader, daemon=True).start()
        assert process.stdin is not None
        process.stdin.write(
            json.dumps(
                {
                    "id": "knowledge",
                    "type": "prompt",
                    "message": "Keep the fictional material, Claim and handoff trace.",
                }
            ).encode()
            + b"\n"
        )
        process.stdin.flush()
        compaction_started = False
        continuation_started = False
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                event = events.get(timeout=0.25)
            except queue.Empty:
                if process.poll() is not None:
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
            if (
                compact
                and event.get("type") == ("agent_settled" if work else "agent_end")
                and not compaction_started
            ):
                assert provider.calls >= 1, [
                    item for item in observed if item.get("type") == "extension_error"
                ]
                process.stdin.write(b'{"id":"compact","type":"compact"}\n')
                process.stdin.flush()
                compaction_started = True
                continue
            if compact and event.get("type") == "response" and event.get("id") == "compact":
                assert event.get("success") is True, (
                    event,
                    provider.calls,
                    [
                        item
                        for item in observed
                        if item.get("type") in ("extension_error", "compaction_end")
                    ],
                )
                if not continue_after_compact:
                    break
                process.stdin.write(
                    b'{"id":"continue","type":"prompt","message":"Continue the fictional Work."}\n'
                )
                process.stdin.flush()
                continuation_started = True
                continue
            if (
                continuation_started
                and event.get("type") == "agent_settled"
                and provider.calls >= 3
            ):
                break
            if not compact and event.get("type") == ("agent_settled" if work else "agent_end"):
                break
        errors = [
            event
            for event in observed
            if event.get("type") == "tool_execution_end" and event.get("isError")
        ]
        stderr = (
            process.stderr.read().decode("utf-8", errors="replace")
            if process.poll() is not None and process.stderr
            else ""
        )
        failures = [
            event for event in observed if event.get("type") in ("extension_error", "response")
        ]
        expected_calls = len(provider.script) + (
            3 if continue_after_compact else 2 if compact else 1
        )
        assert provider.calls == expected_calls, (
            provider.calls,
            stderr,
            failures,
        )
        if compact:
            assert all("ZARA_MANIFEST:" in json.dumps(body) for body in provider.requests)
        assert not errors, errors
        return observed
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


def run_probe(tmp_path: Path, runtime: Path) -> None:
    root, space, owner, activity, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    document_id, claim_id, handoff_id = uuid4(), uuid4(), uuid4()
    transfer_id, return_id, correction_id = uuid4(), uuid4(), uuid4()
    evidence = {"record_id": str(document_id), "revision": 1}
    initial_claim: dict[str, object] = {
        "kind": "claim",
        "proposition": "The fictional valve setting is 8",
        "epistemic_kind": "reported",
        "status": "current",
        "scope_activity_id": str(activity),
        "evidence": [evidence],
        "interpretation_basis": "Owner-supplied design note",
    }
    handoff: dict[str, object] = {
        "kind": "handoff",
        "subject": "Review fictional valve setting",
        "document_text": "Please review setting 8 and return a written note.",
        "media_type": "text/plain",
        "included": [evidence],
        "expected_return": "Written review note",
        "status": "prepared",
        "basis_state_revision": read_space(root).state_revision,
    }
    # One ordinary free conversation saves a source and Claim, then prepares,
    # reports transfer, receives and matches a separate document result.
    first = Provider(
        [
            {"mode": "contract", "kind": "create_knowledge"},
            apply(document_id, source("The fictional valve setting is 8.")),
            apply(claim_id, initial_claim),
            apply(handoff_id, handoff),
            {"mode": "open", "record_id": str(handoff_id), "revision": 1},
            apply(transfer_id, source("Owner sent the document to reviewer", "external_report")),
            apply(
                handoff_id,
                {
                    **handoff,
                    "status": "reported_sent",
                    "transfer_source": {"record_id": str(transfer_id), "revision": 1},
                },
                revision=1,
            ),
            apply(return_id, source("Reviewer reports setting 8 is documented", "document")),
            apply(
                handoff_id,
                {
                    **handoff,
                    "status": "returned",
                    "transfer_source": {"record_id": str(transfer_id), "revision": 1},
                    "return_source": {"record_id": str(return_id), "revision": 1},
                },
                revision=2,
            ),
            apply(
                handoff_id,
                {
                    **handoff,
                    "status": "matched",
                    "transfer_source": {"record_id": str(transfer_id), "revision": 1},
                    "return_source": {"record_id": str(return_id), "revision": 1},
                    "match_basis": "Return is for this exact document and prior source set",
                },
                revision=3,
            ),
        ]
    )
    first_events = run_process(tmp_path, runtime, Bridge(root, owner, tmp_path, 10000), first)
    assert any(
        "Please review setting 8" in json.dumps(event)
        for event in first_events
        if event.get("type") == "tool_execution_end"
    )
    assert isinstance(read_knowledge(root, claim_id, owner).state, ClaimState)
    assert isinstance(read_knowledge(root, handoff_id, owner).state, HandoffState)
    assert read_knowledge(root, handoff_id, owner).revision == 4

    # A new Pi process searches and opens the exact retained source, then starts
    # a Work whose current ContextManifest must include the Claim and its source.
    second = Provider(
        [
            {"mode": "search", "query": "fictional valve"},
            {"mode": "open", "record_id": str(document_id), "revision": 1},
        ]
    )
    run_process(tmp_path, runtime, Bridge(root, owner, tmp_path, 10000), second, compact=True)
    found = cast(list[dict[str, object]], search_knowledge(root, owner, "fictional valve")["items"])
    assert found[0]["record_id"] == str(document_id)
    work_one = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=work_one,
        state=WorkState(
            activity_id=activity,
            goal="Use current fictional setting",
            expected_outputs=(
                OutputContract(slot="result", media_type="text/plain"),
                OutputContract(slot="review", media_type="text/plain"),
            ),
        ),
    )
    before = Provider([])
    run_process(
        tmp_path,
        runtime,
        Bridge(root, owner, tmp_path, 10000),
        before,
        work=(activity, work_one),
        compact=True,
        continue_after_compact=True,
    )
    assert len(before.requests) == 3
    assert all(str(work_one) in json.dumps(body) for body in before.requests)
    assert "work_address" in json.dumps(before.requests[1])
    assert str(claim_id) in json.dumps(before.requests[2])
    active = read_execution(root, work_one, owner).attempts[-1]
    _apply(
        root,
        space,
        owner,
        StopAttemptRequest,
        attempt_id=active.attempt_id,
        work_id=work_one,
        session_id=active.session_id,
        outcome="interrupted",
    )
    assert any(
        str(claim_id) in json.dumps(body) and str(document_id) in json.dumps(body)
        for body in before.requests
    )

    correction = Provider(
        [
            apply(
                correction_id,
                source("Correction: fictional valve setting is 9.", "conversation_user"),
            ),
            apply(
                claim_id,
                {
                    **initial_claim,
                    "proposition": "The fictional valve setting is disputed",
                    "status": "contested",
                    "counter_evidence": [{"record_id": str(correction_id), "revision": 1}],
                    "interpretation_basis": "Owner correction contests the earlier note",
                },
                revision=1,
            ),
        ]
    )
    run_process(tmp_path, runtime, Bridge(root, owner, tmp_path, 10000), correction)
    assert read_knowledge(root, claim_id, owner).revision == 2
    work_two = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=work_two,
        state=WorkState(
            activity_id=activity,
            goal="Use corrected fictional setting",
            expected_outputs=(OutputContract(slot="result", media_type="text/plain"),),
        ),
    )
    after = Provider([])
    run_process(
        tmp_path, runtime, Bridge(root, owner, tmp_path, 10000), after, work=(activity, work_two)
    )
    assert any(
        str(correction_id) in json.dumps(body) and str(claim_id) in json.dumps(body)
        for body in after.requests
    ), json.dumps(after.requests)[:3000]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi-runtime", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="zara-knowledge-pi-") as directory:
        run_probe(Path(directory), args.pi_runtime.resolve())
    print("ordinary Pi knowledge and handoff probe: passed")


if __name__ == "__main__":
    main()
