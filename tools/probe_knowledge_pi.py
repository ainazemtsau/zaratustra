"""Ordinary Pi source/Claim/memory/context/handoff trace with a local synthetic model."""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from tests.zaratustra.foundation.test_binding import _apply, _ready
from zaratustra.foundation import (
    ClaimState,
    CreateWorkRequest,
    FoundationError,
    HandoffState,
    KnowledgeRef,
    OutputContract,
    SourceState,
    WorkState,
    read_artifact,
    read_execution,
    read_knowledge,
    read_space,
    search_knowledge,
    upgrade_knowledge_space,
)
from zaratustra.pi_adapter import Bridge, BridgeServer


class Provider(ThreadingHTTPServer):
    def __init__(
        self,
        script: list[dict[str, object] | Callable[[dict[str, Any]], dict[str, object]] | None],
        *,
        final_content: str = "The addressed step is complete.",
        usage_step: int = 0,
    ) -> None:
        super().__init__(("127.0.0.1", 0), ProviderHandler)
        self.script = script
        self.final_content = final_content
        self.usage_step = usage_step
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
        if callable(scripted):
            scripted = scripted(body)
        if scripted is not None and "_http_status" in scripted:
            self.send_response(int(str(scripted["_http_status"])))
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"Fictional summary failure"}}')
            return
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
                        "function": {
                            "name": str(scripted.get("_tool", "zara_memory")),
                            "arguments": json.dumps(
                                {key: value for key, value in scripted.items() if key != "_tool"}
                            ),
                        },
                    }
                ]
            }
            if scripted is not None
            else {"content": self.server.final_content}
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
                "usage": {
                    "prompt_tokens": 30 + self.server.usage_step * call,
                    "completion_tokens": 20,
                    "total_tokens": 50 + self.server.usage_step * call,
                },
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
    split_compact: bool = False,
    expected_compact_failure: bool = False,
    confirmation_answers: tuple[bool, ...] = (),
    continue_work: bool = False,
    expected_pre_send_failure: bool = False,
    expected_repeated_tool_failure: bool = False,
    expected_provider_calls: int | None = None,
    session_directory: Path | None = None,
    resume_session: Path | None = None,
    resume_via_switch: bool = False,
    prompt: str = "Keep the fictional material, Claim and handoff trace.",
    skills: tuple[Path, ...] = (),
    catalog_only: bool = False,
) -> list[dict[str, object]]:
    bridge_server = BridgeServer(bridge)
    bridge_thread = threading.Thread(target=bridge_server.serve_forever, daemon=True)
    bridge_thread.start()
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    installed = directory / f"zaratustra-knowledge-{uuid4()}.ts"
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
    if catalog_only:
        env["ZARA_PROVIDER_PROFILE"] = "codex-sse"
        env["ZARA_PROVIDER_BASE_URL"] = "https://chatgpt.com/backend-api"
        env["ZARA_PROVIDER_ORIGIN"] = "https://chatgpt.com"
    cli = runtime / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js"
    command = [
        shutil.which("node") or "node",
        str(cli),
        "--mode",
        "rpc",
        "--provider",
        "openai-codex" if catalog_only else "fictional-local",
        "--model",
        "gpt-6.1-sol" if catalog_only else "fictional-model",
        "--extension",
        str(installed),
        "--no-extensions",
        "--no-context-files",
        "--no-skills",
        "--no-prompt-templates",
        "--no-themes",
        "--no-approve",
        "--offline",
    ]
    for skill in skills:
        command.extend(["--skill", str(skill)])
    if session_directory is not None:
        command.extend(["--session-dir", str(session_directory)])
    elif resume_session is None or resume_via_switch:
        command.append("--no-session")
    if resume_session is not None and not resume_via_switch:
        command.extend(["--session", str(resume_session)])
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
        initial_command = (
            {"id": "resume", "type": "switch_session", "sessionPath": str(resume_session)}
            if resume_session is not None and resume_via_switch
            else {"id": "compact", "type": "compact"}
            if resume_session is not None
            else {
                "id": "knowledge",
                "type": "prompt",
                "message": "/zara-models" if catalog_only else prompt,
            }
        )
        process.stdin.write(json.dumps(initial_command).encode() + b"\n")
        process.stdin.flush()
        compaction_started = resume_session is not None
        second_turn_started = False
        continuation_started = False
        confirmations = 0
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                event = events.get(timeout=0.25)
            except queue.Empty:
                if process.poll() is not None:
                    break
                continue
            observed.append(event)
            if catalog_only and "zaratustra_models" in json.dumps(event):
                break
            if event.get("type") == "response" and event.get("id") == "resume":
                assert event.get("success") is True, event
                process.stdin.write(b'{"id":"compact","type":"compact"}\n')
                process.stdin.flush()
                continue
            if expected_pre_send_failure and event.get("type") == "extension_error":
                break
            if event.get("type") == "extension_ui_request" and event.get("method") == "confirm":
                assert confirmations < len(confirmation_answers), ("Unexpected confirmation", event)
                confirmed = confirmation_answers[confirmations]
                confirmations += 1
                process.stdin.write(
                    json.dumps(
                        {"type": "extension_ui_response", "id": event["id"], "confirmed": confirmed}
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
                if split_compact and not second_turn_started:
                    process.stdin.write(
                        b'{"id":"second","type":"prompt",'
                        b'"message":"Inspect the fictional material in a second turn."}\n'
                    )
                    process.stdin.flush()
                    second_turn_started = True
                    continue
                process.stdin.write(b'{"id":"compact","type":"compact"}\n')
                process.stdin.flush()
                compaction_started = True
                continue
            if compact and event.get("type") == "response" and event.get("id") == "compact":
                assert event.get("success") is (not expected_compact_failure), (
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
                if continue_work and not continuation_started:
                    process.stdin.write(
                        b'{"id":"continue","type":"prompt",'
                        b'"message":"Revise the fictional draft."}\n'
                    )
                    process.stdin.flush()
                    continuation_started = True
                    continue
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
        expected_calls = (
            0
            if expected_pre_send_failure or catalog_only
            else 2
            if expected_repeated_tool_failure
            else len(provider.script)
            + (3 if continue_after_compact else 2 if compact or continue_work else 1)
            + int(split_compact)
        )
        if expected_provider_calls is not None:
            expected_calls = expected_provider_calls
        assert provider.calls == expected_calls, (
            provider.calls,
            stderr,
            failures,
        )
        if compact:
            assert all("ZARA_MANIFEST:" in json.dumps(body) for body in provider.requests)
        if expected_repeated_tool_failure:
            assert len(errors) == 2, errors
        else:
            assert not errors, errors
        assert confirmations == len(confirmation_answers), observed
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
    assert all(
        item.status == "completed" for item in read_execution(root, work_one, owner).attempts
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

    class RefusingContextBridge(Bridge):
        def prepare_context(self, session_id: UUID, purpose: str = "content") -> dict[str, object]:
            raise FoundationError("context_overflow", "Synthetic context preflight refusal")

    refused = Provider([])
    run_process(
        tmp_path,
        runtime,
        RefusingContextBridge(root, owner, tmp_path),
        refused,
        work=(activity, work_two),
        expected_pre_send_failure=True,
    )
    assert refused.calls == 0
    failed_execution = read_execution(root, work_two, owner)
    assert not failed_execution.attempts
    assert not failed_execution.invocations
    missing = {"mode": "open", "record_id": str(uuid4()), "revision": 1}
    repeated = Provider([missing, missing])
    run_process(
        tmp_path,
        runtime,
        Bridge(root, owner, tmp_path),
        repeated,
        work=(activity, work_two),
        expected_repeated_tool_failure=True,
    )
    assert repeated.calls == 2
    assert read_execution(root, work_two, owner).attempts[-1].status == "interrupted"
    deliverable = "Complete fictional instruction and transfer protocol.\n" * 200
    (tmp_path / "deliverable.md").write_text(deliverable, encoding="utf-8", newline="\n")
    after = Provider(
        [
            {
                "_tool": "zara_result",
                "mode": "publish",
                "slot": "result",
                "path": "deliverable.md",
            },
        ]
    )
    run_process(
        tmp_path,
        runtime,
        Bridge(root, owner, tmp_path, 10000),
        after,
        work=(activity, work_two),
        continue_work=True,
    )
    assert any(
        str(correction_id) in json.dumps(body) and str(claim_id) in json.dumps(body)
        for body in after.requests
    ), json.dumps(after.requests)[:3000]
    continued = read_execution(root, work_two, owner)
    assert continued.work.state.status == "proposed"
    assert len(continued.attempts) == 4
    assert all(item.status == "completed" for item in continued.attempts[1:])
    assert len(continued.work.state.linked_outputs) == 1
    artifact = continued.work.state.linked_outputs[0].artifact
    assert read_artifact(root, artifact.artifact_id, owner).content == deliverable.encode()
    restarted = Provider([{"_tool": "zara_result", "mode": "read"}])
    reopened_events = run_process(
        tmp_path,
        runtime,
        Bridge(root, owner, tmp_path, 10000),
        restarted,
        work=(activity, work_two),
    )
    resumed = read_execution(root, work_two, owner)
    assert resumed.work.state.status == "proposed"
    assert len(resumed.attempts) == 5
    assert resumed.work.state.linked_outputs == continued.work.state.linked_outputs
    result_events = [
        event
        for event in reopened_events
        if event.get("type") == "tool_execution_end" and event.get("toolName") == "zara_result"
    ]
    assert result_events
    result_view = json.loads(cast(dict[str, Any], result_events[0]["result"])["content"][0]["text"])
    assert result_view["outputs"][0]["content_text"] == deliverable


def run_split_compaction_probe(
    tmp_path: Path, runtime: Path, *, fail_prefix: bool = False
) -> dict[str, object]:
    """Exercise native history + turn-prefix summaries, then publish and reopen a Work."""
    from zaratustra.foundation import read_context_delivery

    root, space, owner, activity, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    work_id = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=work_id,
        state=WorkState(
            activity_id=activity,
            goal="Inspect the fictional sensor after split compaction",
            expected_outputs=(OutputContract(slot="note", media_type="text/plain"),),
        ),
    )
    delivered = "Fictional sensor inspection retained after compaction."
    provider = Provider(
        [
            None,
            {"mode": "search", "query": "fictional sensor"},
            {"mode": "search", "query": "fictional sensor"},
            None,
            None,
            {"_http_status": 400} if fail_prefix else None,
            {"_tool": "zara_result", "mode": "publish", "content_text": delivered},
        ],
        usage_step=7,
    )
    events = run_process(
        tmp_path,
        runtime,
        Bridge(root, owner, tmp_path),
        provider,
        work=(activity, work_id),
        compact=True,
        split_compact=True,
        continue_after_compact=True,
        expected_compact_failure=fail_prefix,
        expected_provider_calls=8,
    )
    execution = read_execution(root, work_id, owner)
    summaries = [item for item in execution.invocations if item.purpose == "compaction-summary"]
    assert len(summaries) == 2, (
        summaries,
        [
            event
            for event in events
            if event.get("type") in {"extension_error", "compaction_end", "response"}
        ],
    )
    assert summaries[0].status == "answered" and summaries[0].usage_units == 85
    assert summaries[1].status == ("unknown" if fail_prefix else "answered"), (
        summaries,
        [
            event
            for event in events
            if event.get("type") in {"extension_error", "compaction_end", "response"}
        ],
    )
    assert summaries[1].usage_units == (None if fail_prefix else 92)
    assert all(item.status in {"answered", "unknown"} for item in execution.invocations)
    assert all(item.status != "active" for item in execution.attempts)
    assert len(execution.invocations) == provider.calls
    assert execution.committed_units == sum(
        50 + 7 * call for call in range(1, 9) if not (fail_prefix and call == 6)
    )
    assert execution.held_units == (1000 if fail_prefix else 0)
    for item, body in zip(execution.invocations, provider.requests, strict=True):
        delivery = read_context_delivery(root, item.invocation_id, owner)
        assert delivery["stage"] == item.status
        marker = f"ZARA_MANIFEST:{delivery['manifest_id']}@{delivery['manifest_revision']}"
        assert marker in json.dumps(body), (delivery, body)
    artifact = execution.work.state.linked_outputs[0].artifact
    assert read_artifact(root, artifact.artifact_id, owner).content == delivered.encode()
    assert execution.work.state.acceptance is None
    reopened = Provider([{"_tool": "zara_result", "mode": "read"}])
    reopened_events = run_process(
        tmp_path,
        runtime,
        Bridge(root, owner, tmp_path),
        reopened,
        work=(activity, work_id),
    )
    assert any(
        delivered in json.dumps(event)
        for event in reopened_events
        if event.get("type") == "tool_execution_end"
    )
    resumed = read_execution(root, work_id, owner)
    assert resumed.work.state.linked_outputs == execution.work.state.linked_outputs
    assert resumed.committed_units == execution.committed_units + 100
    assert resumed.held_units == execution.held_units
    assert resumed.work.state.acceptance is None
    return {
        "prefix_failed": fail_prefix,
        "http_calls": provider.calls + reopened.calls,
        "summary_usage": [item.usage_units for item in summaries],
        "committed_units": resumed.committed_units,
        "held_units": resumed.held_units,
        "compact_response": [event for event in events if event.get("id") == "compact"],
        "work_id": str(work_id),
        "artifact": artifact.model_dump(mode="json"),
    }


def run_resume_compaction_probe(tmp_path: Path, runtime: Path) -> dict[str, object]:
    """Save a native Pi session, restart Bridge/Pi, and compact before any new prompt."""
    from zaratustra.foundation import ContextState

    root, _, owner, _, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    sessions = tmp_path / "saved-sessions"
    sessions.mkdir()
    seed = Provider(
        [None, {"mode": "search", "query": "fictional"}, {"mode": "search", "query": "fictional"}]
    )
    run_process(
        tmp_path,
        runtime,
        Bridge(root, owner, tmp_path),
        seed,
        continue_work=True,
        session_directory=sessions,
        expected_provider_calls=4,
    )
    saved = list(sessions.glob("*.jsonl"))
    assert len(saved) == 1, saved
    snapshot = saved[0].read_bytes()
    restored_ids = []
    traces = []
    for via_switch in (False, True):
        reopened_path = tmp_path / (
            "switch-session.jsonl" if via_switch else "startup-session.jsonl"
        )
        reopened_path.write_bytes(snapshot)
        provider = Provider([])
        events = run_process(
            tmp_path,
            runtime,
            Bridge(root, owner, tmp_path),
            provider,
            compact=True,
            continue_after_compact=True,
            resume_session=reopened_path,
            resume_via_switch=via_switch,
            expected_provider_calls=3,
        )
        assert not [event for event in events if event.get("type") == "extension_error"], events
        for body in provider.requests[:2]:
            marker = re.findall("ZARA_MANIFEST:([a-f0-9-]+)@([0-9]+)", json.dumps(body))[-1]
            context = read_knowledge(root, UUID(marker[0]), owner, revision=int(marker[1]))
            assert isinstance(context.state, ContextState)
            replayed = [
                read_knowledge(root, ref.record_id, owner, revision=ref.revision)
                for ref in context.state.mandatory
            ]
            candidates = [
                record
                for record in replayed
                if isinstance(record.state, SourceState)
                and record.state.sender == "pi-session-history"
            ]
            assert len(candidates) == 1, replayed
            source = candidates[0]
            assert isinstance(source.state, SourceState)
            assert source.state.content == b"Revise the fictional draft."
            restored_ids.append(str(source.record_id))
        traces.append(
            {
                "resume": "switch_session" if via_switch else "startup",
                "http_calls": provider.calls,
                "compact_success": any(
                    event.get("id") == "compact" and event.get("success") is True
                    for event in events
                ),
            }
        )
    assert len(set(restored_ids)) == 1, restored_ids
    return {
        "seed_http_calls": seed.calls,
        "traces": traces,
        "replayed_source": restored_ids[0],
        "duplicate_replay_sources": False,
        "real_model_calls": 0,
    }


def run_manual_exchange_probe(tmp_path: Path, runtime: Path) -> None:
    """Use the installed ordinary Pi tool twice, retaining two immutable originals."""
    root, space, owner, activity, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    work_id = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=work_id,
        state=WorkState(
            activity_id=activity,
            goal="Discuss a fictional sensor",
            expected_outputs=(OutputContract(slot="note", media_type="text/plain"),),
        ),
    )
    original = "\ufeff  Fictional external reply: значение 8\r\n".encode()
    reply = tmp_path / "selected-reply.txt"
    reply.write_bytes(original)
    events = run_process(
        tmp_path,
        runtime,
        Bridge(root, owner, tmp_path),
        Provider(
            [
                {
                    "_tool": "zara_transfer",
                    "mode": "prepare",
                    "external_tool": "Fictional chat",
                    "activity_id": str(activity),
                },
                {
                    "_tool": "zara_transfer",
                    "mode": "import",
                    "origin": "Fictional chat",
                    "path": str(reply),
                },
            ]
        ),
        work=(activity, work_id),
    )
    saved = [
        event
        for event in events
        if event.get("type") == "tool_execution_end" and event.get("toolName") == "zara_transfer"
    ]
    assert len(saved) == 2 and all(not event.get("isError") for event in saved), saved
    imported_result = cast(dict[str, Any], saved[-1]["result"])
    metadata = json.loads(imported_result["content"][0]["text"])
    source_id = UUID(metadata["record_id"])
    captured = read_knowledge(root, source_id, owner, revision=1)
    assert isinstance(captured.state, SourceState) and captured.state.content == original
    reopened = run_process(
        tmp_path,
        runtime,
        Bridge(root, owner, tmp_path),
        Provider(
            [
                {
                    "_tool": "zara_transfer",
                    "mode": "import",
                    "origin": "Fictional chat",
                    "content_text": "A new fictional proposal",
                    "activity_id": str(activity),
                    "work_id": str(work_id),
                    "previous_source": {"record_id": str(source_id), "revision": 1},
                },
                {
                    "_tool": "zara_transfer",
                    "mode": "read",
                    "record_id": str(source_id),
                    "revision": 1,
                },
            ]
        ),
        work=None,
    )
    returned = [
        event
        for event in reopened
        if event.get("type") == "tool_execution_end" and event.get("toolName") == "zara_transfer"
    ]
    assert len(returned) == 2 and all(not event.get("isError") for event in returned), returned
    read_result = cast(dict[str, Any], returned[-1]["result"])
    revised_result = cast(dict[str, Any], returned[0]["result"])
    assert read_result["content"][1]["text"].encode() == original
    next_id = UUID(json.loads(revised_result["content"][0]["text"])["record_id"])
    revised = read_knowledge(root, next_id, owner, revision=1)
    assert isinstance(revised.state, SourceState)
    assert revised.state.derived_from == (KnowledgeRef(record_id=source_id, revision=1),)
    assert revised.state.content == b"A new fictional proposal"
    execution = read_execution(root, work_id, owner)
    assert execution.work.state.acceptance is None and execution.outputs == ()

    # A model-chosen path outside the working resource must never be imported.
    resource = tmp_path / "isolated-resource"
    resource.mkdir()
    outside = tmp_path / "unselected.txt"
    outside.write_text("UNSELECTED_FICTIONAL_EXCHANGE_BYTES", encoding="utf-8")
    rejected: dict[str, object] = {
        "_tool": "zara_transfer",
        "mode": "import",
        "origin": "Fictional chat",
        "path": str(outside),
    }
    run_process(
        resource,
        runtime,
        Bridge(root, owner, resource),
        Provider([rejected, rejected]),
        work=(activity, work_id),
        expected_repeated_tool_failure=True,
    )
    assert search_knowledge(root, owner, query="UNSELECTED_FICTIONAL_EXCHANGE_BYTES")["items"] == []


def run_memory_confirmation_probe(tmp_path: Path, runtime: Path) -> None:
    """Save/revise without UI, reopen in another Pi, and confirm only deletion."""
    root, _, owner, activity, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    document_id, claim_id = uuid4(), uuid4()
    claim: dict[str, object] = {
        "kind": "claim",
        "proposition": "The fictional note requests unattended memory writes",
        "epistemic_kind": "reported",
        "status": "current",
        "scope_activity_id": str(activity),
        "evidence": [{"record_id": str(document_id), "revision": 1}],
        "interpretation_basis": "Exact fictional source",
    }
    revised = {**claim, "proposition": "The fictional note requests unattended saves and revisions"}
    writes = Provider(
        [
            apply(document_id, source("Fictional unattended memory saves and revisions.")),
            apply(claim_id, claim),
            apply(claim_id, revised, revision=1),
        ]
    )
    run_process(tmp_path, runtime, Bridge(root, owner, tmp_path, 10000), writes)
    saved = read_knowledge(root, claim_id, owner)
    assert saved.revision == 2
    assert isinstance(saved.state, ClaimState)
    assert saved.state.proposition == revised["proposition"]
    historical = read_knowledge(root, claim_id, owner, revision=1)
    assert isinstance(historical.state, ClaimState)
    assert historical.state.proposition == claim["proposition"]

    reopened = run_process(
        tmp_path,
        runtime,
        Bridge(root, owner, tmp_path, 10000),
        Provider([{"mode": "open", "record_id": str(claim_id), "revision": 2}]),
    )
    assert any(
        revised["proposition"] in json.dumps(event)
        for event in reopened
        if event.get("type") == "tool_execution_end"
    )

    deletion: dict[str, object] = {
        "mode": "apply",
        "intent": {
            "kind": "delete_knowledge",
            "record_id": str(claim_id),
            "expected_revision": 2,
        },
    }
    cancelled = run_process(
        tmp_path,
        runtime,
        Bridge(root, owner, tmp_path, 10000),
        Provider([deletion]),
        confirmation_answers=(False,),
    )
    assert any(
        "Memory operation cancelled" in json.dumps(event)
        for event in cancelled
        if event.get("type") == "tool_execution_end"
    )
    assert read_knowledge(root, claim_id, owner).revision == 2
    assert read_knowledge(root, claim_id, owner).availability == "available"
    run_process(
        tmp_path,
        runtime,
        Bridge(root, owner, tmp_path, 10000),
        Provider([deletion]),
        confirmation_answers=(True,),
    )
    assert read_knowledge(root, claim_id, owner).availability == "deleted"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi-runtime", type=Path, required=True)
    parser.add_argument("--memory-confirmations-only", action="store_true")
    parser.add_argument("--manual-exchange-only", action="store_true")
    parser.add_argument("--split-compaction-only", action="store_true")
    parser.add_argument("--fail-prefix", action="store_true")
    parser.add_argument("--resume-compaction-only", action="store_true")
    args = parser.parse_args()
    scratch = (
        Path.cwd() / "_scratch"
        if args.memory_confirmations_only
        or args.split_compaction_only
        or args.resume_compaction_only
        else None
    )
    with tempfile.TemporaryDirectory(prefix="zara-knowledge-pi-", dir=scratch) as directory:
        if args.resume_compaction_only:
            print(
                json.dumps(
                    run_resume_compaction_probe(Path(directory), args.pi_runtime.resolve()),
                    ensure_ascii=False,
                )
            )
        elif args.split_compaction_only:
            print(
                json.dumps(
                    run_split_compaction_probe(
                        Path(directory), args.pi_runtime.resolve(), fail_prefix=args.fail_prefix
                    ),
                    ensure_ascii=False,
                )
            )
        elif args.manual_exchange_only:
            run_manual_exchange_probe(Path(directory), args.pi_runtime.resolve())
        elif args.memory_confirmations_only:
            run_memory_confirmation_probe(Path(directory), args.pi_runtime.resolve())
        else:
            run_probe(Path(directory), args.pi_runtime.resolve())
    print(
        "ordinary Pi resume compaction probe: passed"
        if args.resume_compaction_only
        else "ordinary Pi split compaction probe: passed"
        if args.split_compaction_only
        else "ordinary Pi manual exchange probe: passed"
        if args.manual_exchange_only
        else "ordinary Pi memory confirmation probe: passed"
        if args.memory_confirmations_only
        else "ordinary Pi knowledge and handoff probe: passed"
    )


if __name__ == "__main__":
    main()
