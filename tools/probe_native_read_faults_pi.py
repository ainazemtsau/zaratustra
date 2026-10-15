"""Observe native retry boundaries with fictional localhost provider failures."""

from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from zaratustra.foundation import (
    ActivityState,
    CreateActivityRequest,
    CreateWorkRequest,
    FoundationError,
    OutputContract,
    WorkState,
    apply_operation,
    read_execution,
)
from zaratustra.pi_adapter import Bridge
from zaratustra.pi_adapter.__main__ import INTERACTIVE_ZARA_TOOLS, _prepare_space
from zaratustra.pi_adapter.runtime import system_pi_runtime

from .probe_conversation_responses_pi import (
    RawResponsesHandler,
    RawResponsesProvider,
    completed_response,
    decoded_request,
)
from .probe_knowledge_pi import run_process


class FaultProvider(RawResponsesProvider):
    def __init__(self, kind: str) -> None:
        super().__init__(
            [
                completed_response(
                    None,
                    call=(
                        "zara_result",
                        {
                            "mode": "publish",
                            "slot": "result",
                            "content_text": "Exact once fictional result",
                        },
                    ),
                ),
                completed_response("This response must not replace the failed send."),
            ]
        )
        self.kind = kind
        self.RequestHandlerClass = FaultHandler


class FaultHandler(RawResponsesHandler):
    server: FaultProvider

    def do_POST(self) -> None:
        if self.server.calls != 1 or self.server.kind == "context":
            return super().do_POST()
        body = decoded_request(
            self.rfile.read(int(self.headers["Content-Length"])),
            self.headers.get("Content-Encoding"),
        )
        self.server.requests.append(body)
        self.server.calls += 1
        self.server.wire_responses.append([])
        if self.server.kind == "tcp":
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
        elif self.server.kind == "http":
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"Fictional service unavailable"}}')
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(
                b'event: error\ndata: {"type":"error","code":"server_error",'
                b'"message":"Fictional server error"}\n\n'
            )
            self.wfile.flush()


class FaultBridge(Bridge):
    fault_kind = ""
    context_count = 0

    def prepare_context(self, *args: Any, **kwargs: Any) -> dict[str, object]:
        self.context_count += 1
        if self.fault_kind == "context" and self.context_count > 1:
            raise FoundationError(
                "fictional_context_fault", "Fictional mandatory material unavailable"
            )
        return super().prepare_context(*args, **kwargs)


def run_case(directory: Path, kind: str, runtime: Path) -> dict[str, object]:
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    root = directory / "core"
    root.mkdir()
    owner = _prepare_space(root, "fictional-owner", create=True, upgrade_existing=True)
    activity, work = uuid4(), uuid4()
    apply_operation(
        root,
        CreateActivityRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor=owner.actor,
            activity_id=activity,
            state=ActivityState(title="Fictional faults", goal="Retain once and explain"),
        ),
        owner,
    )
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor=owner.actor,
            work_id=work,
            state=WorkState(
                activity_id=activity,
                goal="Save one result and explain it",
                expected_outputs=(OutputContract(slot="result", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    provider = FaultProvider(kind)
    bridge = FaultBridge(root, owner, directory)
    bridge.fault_kind = kind
    replies: list[dict[str, object]] = []
    expected = 1 if kind == "context" else 2
    events = run_process(
        directory,
        runtime,
        bridge,
        provider,
        work=(activity, work),
        provider_profile="codex-sse",
        local_model_id="gpt-6.1-sol",
        prompt="Save this fictional result once and explain the next step.",
        tool_names=INTERACTIVE_ZARA_TOOLS,
        expected_provider_calls=expected,
        on_bridge_response=lambda path, payload: replies.append({"path": path, "payload": payload}),
        timeout_seconds=60,
    )
    before = read_execution(root, work, owner)
    assert len(before.outputs) == 1 and before.outputs[0].content == b"Exact once fictional result"
    assert before.work.state.acceptance is None
    statuses = [item.status for item in before.invocations]
    assert statuses == (["answered"] if kind == "context" else ["answered", "unknown"]), statuses
    errors = [
        str(cast(dict[str, Any], event["message"]).get("errorMessage", ""))
        for event in events
        if isinstance(event.get("message"), dict)
    ]
    error_text = "\n".join(errors)
    if kind == "context":
        assert "fictional_context_fault" in error_text, errors
        assert "Core capture or ContextManifest is not ready" not in error_text
    else:
        assert "unknown_send" in error_text, errors
    assert not provider.errors, provider.errors

    # A new native owner message can explain retained state. No earlier send is replayed.
    resumed = RawResponsesProvider(
        [completed_response("Saved state remains; the failed send is unknown.")]
    )
    reopened = Bridge(root, owner, directory)
    reopened_events = run_process(
        directory,
        runtime,
        reopened,
        resumed,
        provider_profile="codex-sse",
        local_model_id="gpt-6.1-sol",
        prompt="What happened? Explain the saved state.",
        tool_names=INTERACTIVE_ZARA_TOOLS,
        expected_provider_calls=1,
        timeout_seconds=40,
    )
    after = read_execution(root, work, owner)
    assert before.outputs == after.outputs
    assert before.invocations == after.invocations
    assert after.work.state.acceptance is None
    report: dict[str, object] = {
        "outcome": "PASS",
        "kind": kind,
        "initial_http": provider.calls,
        "context_calls": bridge.context_count,
        "reopen_http": resumed.calls,
        "invocation_statuses": statuses,
        "outputs": len(after.outputs),
        "accepted": False,
        "real_model_calls": 0,
    }
    for name, value in (
        ("report", report),
        ("native_events", events),
        ("reopen_events", reopened_events),
        ("bridge_replies", replies),
        ("requests", provider.requests),
    ):
        (directory / f"{name}.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--kind", choices=("http", "tcp", "sse", "context", "all"), default="all")
    args = parser.parse_args()
    kinds = ("http", "tcp", "sse", "context") if args.kind == "all" else (args.kind,)
    assert not args.directory.exists(), "Use a new fictional output directory"
    runtime = system_pi_runtime().root
    reports = [run_case(args.directory / kind, kind, runtime) for kind in kinds]
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
