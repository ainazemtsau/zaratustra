"""Probe published Pi RPC and Provider integration against localhost only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

from .common import (
    CheckConclusion,
    CheckResult,
    GateReport,
    GateStatus,
    append_jsonl,
    gate_status,
    new_scratch_output,
    read_jsonl,
    sha256_file,
)

SAFETY_CHECKS = frozenset(
    {
        "final-request",
        "readiness-stops-transport",
        "strict-lf-jsonl",
        "busy-question-single-continuation",
        "ui-close-preserves-wait",
    }
)
EXPECTED_CHECKS = SAFETY_CHECKS | {
    "request-identity-resource-accounting",
    "compaction-summary-context",
    "overflow-recovery-identities",
}


@dataclass
class ProviderState:
    log_path: Path
    requests: list[dict[str, Any]]
    slow_seen: threading.Event
    release_slow: threading.Event
    overflow_sent: bool = False


def _message_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload.get("messages", []), ensure_ascii=False)


def _sse(
    handler: BaseHTTPRequestHandler,
    text: str,
    record: dict[str, Any],
    *,
    delay: bool = False,
) -> None:
    prompt_tokens = max(1, len(json.dumps(record["payload"], ensure_ascii=False)) // 4)
    completion_tokens = max(1, len(text) // 4)
    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    record["responseUsage"] = usage
    handler.send_response(200)
    handler.send_header("content-type", "text/event-stream")
    handler.end_headers()
    chunks = [
        {
            "id": "probe",
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        },
        {
            "id": "probe",
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
        },
        {
            "id": "probe",
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        },
        {
            "id": "probe",
            "object": "chat.completion.chunk",
            "choices": [],
            "usage": usage,
        },
    ]
    for index, chunk in enumerate(chunks):
        if delay and index == 1:
            state = handler.server.provider_state  # type: ignore[attr-defined]
            state.slow_seen.set()
            state.release_slow.wait(timeout=10)
        data = json.dumps(chunk, separators=(",", ":")).encode()
        handler.wfile.write(b"data: " + data + b"\n\n")
        handler.wfile.flush()
    handler.wfile.write(b"data: [DONE]\n\n")
    handler.wfile.flush()


class ProviderHandler(BaseHTTPRequestHandler):
    server_version = "ZaratustraPiProbe/1"

    def do_POST(self) -> None:  # noqa: N802
        state: ProviderState = self.server.provider_state  # type: ignore[attr-defined]
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length)
        digest = hashlib.sha256(body).hexdigest()
        payload = json.loads(body)
        record = {
            "path": self.path,
            "invocationId": self.headers.get("x-zara-invocation-id"),
            "claimedSha256": self.headers.get("x-zara-body-sha256"),
            "bodySha256": digest,
            "purpose": self.headers.get("x-zara-purpose"),
            "payload": payload,
        }
        state.requests.append(record)
        append_jsonl(state.log_path, record)
        text = _message_text(payload)
        if "FORCE_OVERFLOW" in text and not state.overflow_sent:
            state.overflow_sent = True
            response = json.dumps(
                {"error": {"message": "context_length_exceeded", "type": "invalid_request_error"}}
            ).encode()
            self.send_response(400)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        if record["purpose"] == "compaction-summary":
            _sse(self, "CURRENT_OBLIGATION_OMEGA remains required", record)
            append_jsonl(state.log_path, {"type": "response", **record})
            return
        _sse(self, "probe-ok", record, delay="SLOW_MAIN" in text)
        append_jsonl(state.log_path, {"type": "response", **record})

    def log_message(self, _format: str, *_args: object) -> None:
        return


class RpcClient:
    def __init__(self, command: list[str], env: dict[str, str], cwd: Path, raw_log: Path) -> None:
        self.process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.raw_log = raw_log
        self._stdout = threading.Thread(target=self._read_stdout, daemon=True)
        self._stdout.start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        stdout = cast(Any, self.process.stdout)
        pending = b""
        with self.raw_log.open("ab") as log:
            while True:
                chunk = stdout.read1(4096)
                if not chunk:
                    break
                log.write(chunk)
                log.flush()
                pending += chunk
                while b"\n" in pending:
                    raw, pending = pending.split(b"\n", 1)
                    if raw.endswith(b"\r"):
                        raw = raw[:-1]
                    if raw:
                        value = json.loads(raw.decode("utf-8"))
                        if isinstance(value, dict):
                            self.events.put(value)
            if pending:
                self.events.put({"type": "probe_invalid_unframed_tail", "raw": pending.hex()})

    def send(self, value: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        data = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.process.stdin.write(data + b"\n")
        self.process.stdin.flush()

    def wait_for(self, predicate: Any, timeout: float = 15) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                event = self.events.get(timeout=min(0.25, deadline - time.monotonic()))
            except queue.Empty:
                continue
            if predicate(event):
                return event
        raise TimeoutError("RPC event not observed before deadline")

    def stop(self) -> str:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        assert self.process.stderr is not None
        stderr = cast(bytes, self.process.stderr.read())
        return stderr.decode("utf-8", errors="replace")


def _gate_status(checks: list[CheckResult]) -> GateStatus:
    return gate_status(checks, frozenset(EXPECTED_CHECKS))


def _settings(config_dir: Path) -> None:
    config_dir.mkdir(parents=True)
    settings = {
        "cacheWarming": "off",
        "enableInstallTelemetry": False,
        "defaultProjectTrust": "never",
        "compaction": {"enabled": True, "reserveTokens": 1024, "keepRecentTokens": 512},
        "retry": {
            "enabled": False,
            "maxRetries": 0,
            "provider": {"maxRetries": 0, "timeoutMs": 10000, "maxRetryDelayMs": 1000},
        },
    }
    (config_dir / "settings.json").write_text(
        json.dumps(settings, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def _pi_command(node: Path, cli: Path, extension: Path) -> list[str]:
    return [
        str(node),
        str(cli),
        "--mode",
        "rpc",
        "--provider",
        "zara-probe",
        "--model",
        "probe-model",
        "--no-tools",
        "--no-context-files",
        "--no-skills",
        "--no-prompt-templates",
        "--no-themes",
        "--no-approve",
        "--offline",
        "--extension",
        str(extension),
    ]


def _env(output: Path, base_url: str) -> dict[str, str]:
    isolated_home = output / "isolated-user"
    isolated_temp = output / "temp"
    for path in (
        isolated_home,
        isolated_home / "appdata",
        isolated_home / "local-appdata",
        isolated_temp,
    ):
        path.mkdir(parents=True, exist_ok=True)
    allowed_host_names = ("COMSPEC", "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR")
    env = {name: os.environ[name] for name in allowed_host_names if name in os.environ}
    env.update(
        {
            "APPDATA": str(isolated_home / "appdata"),
            "HOME": str(isolated_home),
            "LOCALAPPDATA": str(isolated_home / "local-appdata"),
            "PI_CODING_AGENT_DIR": str(output / "pi-config"),
            "PI_CODING_AGENT_SESSION_DIR": str(output / "pi-sessions"),
            "PI_OFFLINE": "1",
            "PI_SKIP_VERSION_CHECK": "1",
            "PI_TELEMETRY": "0",
            "TEMP": str(isolated_temp),
            "TMP": str(isolated_temp),
            "USERPROFILE": str(isolated_home),
            "ZARATUSTRA_PROBE_PROVIDER_BASE_URL": base_url,
            "ZARATUSTRA_PROBE_EXTENSION_LOG": str(output / "extension.jsonl"),
            "ZARATUSTRA_PROBE_RESOURCE_LOG": str(output / "resource-ledger.jsonl"),
            "ZARATUSTRA_PROBE_WAIT_LOG": str(output / "waits.jsonl"),
            "ZARATUSTRA_PROBE_FAIL_PERSIST": str(output / "fail-persist"),
        }
    )
    return env


def _positive_usage(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return int(value.get("input", 0)) + int(value.get("output", 0)) > 0


def _assess_invocations(
    extension_records: list[dict[str, Any]],
    provider_requests: list[dict[str, Any]],
    resource_records: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any]]:
    """Join the hook, transport, server and resource evidence by invocation identity."""

    transports = [row for row in extension_records if row.get("type") == "transport_ready"]
    invocation_ids = [str(row.get("invocationId")) for row in transports]
    reservations = {
        str(row.get("invocationId")): row
        for row in resource_records
        if row.get("type") == "resource_reserved"
    }
    outcomes = {
        str(row.get("invocationId")): row
        for row in resource_records
        if row.get("type") == "transport_outcome"
    }
    accounting = {
        str(row.get("invocationId")): row
        for row in resource_records
        if row.get("type") == "resource_accounted" and row.get("invocationId")
    }
    server = {str(row.get("invocationId")): row for row in provider_requests}
    problems: list[str] = []
    hook_missing: list[str] = []
    if len(invocation_ids) != len(set(invocation_ids)):
        problems.append("duplicate invocation identity")
    if len(transports) != len(provider_requests):
        problems.append("transport/server request count differs")
    for transport in transports:
        invocation_id = str(transport.get("invocationId"))
        request = server.get(invocation_id)
        if request is None:
            problems.append(f"{invocation_id}: no server observation")
            continue
        body_sha256 = transport.get("bodySha256")
        hook_sha256 = transport.get("payloadHookSha256")
        if body_sha256 != request.get("bodySha256") or body_sha256 != request.get("claimedSha256"):
            problems.append(f"{invocation_id}: serialized request digest mismatch")
        if hook_sha256 is None:
            hook_missing.append(str(transport.get("purpose")))
            if transport.get("purpose") != "compaction-summary":
                problems.append(f"{invocation_id}: content call bypassed payload hook")
        elif body_sha256 != hook_sha256:
            problems.append(f"{invocation_id}: payload hook digest mismatch")
        reservation = reservations.get(invocation_id)
        if reservation is None or int(reservation.get("reservedUnits", 0)) <= 0:
            problems.append(f"{invocation_id}: no positive pre-network reserve")
        outcome = outcomes.get(invocation_id)
        if outcome is None:
            problems.append(f"{invocation_id}: no transport outcome")
        elif int(outcome.get("status", 0)) == 200:
            account = accounting.get(invocation_id)
            if account is None or not _positive_usage(account.get("usage")):
                problems.append(f"{invocation_id}: successful call lacks usage accounting")
            response_usage = request.get("responseUsage")
            if (
                not isinstance(response_usage, dict)
                or int(response_usage.get("total_tokens", 0)) <= 0
            ):
                problems.append(f"{invocation_id}: provider returned no measurable usage")
    return not problems, {
        "invocationCount": len(invocation_ids),
        "uniqueInvocationCount": len(set(invocation_ids)),
        "purposes": [row.get("purpose") for row in transports],
        "payloadHookMissingPurposes": hook_missing,
        "problems": problems,
    }


def _assess_compaction(
    extension_records: list[dict[str, Any]],
    provider_requests: list[dict[str, Any]],
    compact_response: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    started = [
        row
        for row in extension_records
        if row.get("type") == "session_before_compact" and row.get("reason") == "manual"
    ]
    completed = [
        row
        for row in extension_records
        if row.get("type") == "session_compact" and row.get("reason") == "manual"
    ]
    compaction_id = completed[-1].get("invocationId") if completed else None
    summary_indexes = [
        index
        for index, request in enumerate(provider_requests)
        if request.get("invocationId") == compaction_id
        and request.get("purpose") == "compaction-summary"
    ]
    following = provider_requests[summary_indexes[-1] + 1 :] if summary_indexes else []
    delivered = [
        request
        for request in following
        if request.get("purpose") == "content"
        and "AFTER_COMPACTION" in _message_text(request["payload"])
    ]
    obligation_delivered = bool(
        delivered and "CURRENT_OBLIGATION_OMEGA" in _message_text(delivered[0]["payload"])
    )
    response_data = compact_response.get("data")
    data: dict[str, Any] = response_data if isinstance(response_data, dict) else {}
    passed = (
        compact_response.get("success") is True
        and len(started) == 1
        and len(completed) == 1
        and bool(compaction_id)
        and len(summary_indexes) == 1
        and int(started[0].get("tokensBefore") or 0) > 0
        and _positive_usage(data.get("usage"))
        and obligation_delivered
    )
    return passed, {
        "lifecycleStartCount": len(started),
        "lifecycleCompletionCount": len(completed),
        "reason": completed[-1].get("reason") if completed else None,
        "summaryInvocationId": compaction_id,
        "tokensBefore": started[0].get("tokensBefore") if started else None,
        "usage": data.get("usage"),
        "obligationDelivered": obligation_delivered,
    }


def _assess_overflow(
    extension_records: list[dict[str, Any]],
    provider_requests: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any]]:
    started = [
        row
        for row in extension_records
        if row.get("type") == "session_before_compact" and row.get("reason") == "overflow"
    ]
    completed = [
        row
        for row in extension_records
        if row.get("type") == "session_compact" and row.get("reason") == "overflow"
    ]
    summary_id = completed[-1].get("invocationId") if completed else None
    summary_indexes = [
        index
        for index, request in enumerate(provider_requests)
        if request.get("invocationId") == summary_id
        and request.get("purpose") == "compaction-summary"
    ]
    summary = [provider_requests[index] for index in summary_indexes]
    before_summary = provider_requests[: summary_indexes[0]] if summary_indexes else []
    after_summary = provider_requests[summary_indexes[-1] + 1 :] if summary_indexes else []
    initial_candidates = [
        request
        for request in before_summary
        if request.get("purpose") == "content"
        and "FORCE_OVERFLOW" in _message_text(request["payload"])
    ]
    initial = initial_candidates[-1:]
    retried = [
        request
        for request in after_summary
        if request.get("purpose") == "overflow-retry"
        and "FORCE_OVERFLOW" in _message_text(request["payload"])
    ]
    identities = [request.get("invocationId") for request in [*initial, *summary, *retried]]
    obligation_delivered = bool(
        retried and "CURRENT_OBLIGATION_OMEGA" in _message_text(retried[0]["payload"])
    )
    passed = (
        len(started) == 1
        and started[0].get("willRetry") is True
        and len(completed) == 1
        and completed[0].get("willRetry") is True
        and len(initial) == 1
        and len(summary) == 1
        and len(retried) == 1
        and len(identities) == len(set(identities))
        and obligation_delivered
    )
    return passed, {
        "lifecycleStartCount": len(started),
        "lifecycleCompletionCount": len(completed),
        "willRetry": completed[-1].get("willRetry") if completed else None,
        "invocationIds": identities,
        "purposes": [request.get("purpose") for request in [*initial, *summary, *retried]],
        "obligationDelivered": obligation_delivered,
    }


def run_probe(*, node: Path, pi_cli: Path, output: Path, package_integrity: str) -> GateReport:
    output = new_scratch_output(output)
    extension = output / "pi_probe_extension.ts"
    shutil.copyfile(Path(__file__).with_name("pi_probe_extension.ts"), extension)
    _settings(output / "pi-config")
    state = ProviderState(output / "provider.jsonl", [], threading.Event(), threading.Event())
    server = ThreadingHTTPServer(("127.0.0.1", 0), ProviderHandler)
    server.provider_state = state  # type: ignore[attr-defined]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{server.server_port}/v1"
    command = _pi_command(node.resolve(), pi_cli.resolve(), extension)
    client = RpcClient(command, _env(output, base_url), output, output / "rpc-stdout.jsonl")
    checks: list[CheckResult] = []
    stderr_parts: list[str] = []
    try:
        client.send(
            {"id": "normal", "type": "prompt", "message": "NORMAL CURRENT_OBLIGATION_OMEGA"}
        )
        accepted = client.wait_for(lambda event: event.get("id") == "normal")
        settled = client.wait_for(lambda event: event.get("type") == "agent_settled")
        first = state.requests[0]
        checks.append(
            CheckResult(
                "final-request",
                accepted.get("success") is True
                and settled.get("type") == "agent_settled"
                and first["claimedSha256"] == first["bodySha256"]
                and "CURRENT_OBLIGATION_OMEGA" in json.dumps(first["payload"]),
                "Pi sent the byte-identical persisted request body to the localhost simulator.",
                {"bodySha256": first["bodySha256"]},
            )
        )

        before_failure = len(state.requests)
        (output / "fail-persist").write_text("fail\n", encoding="utf-8")
        client.send({"id": "persist-fail", "type": "prompt", "message": "MUST_NOT_REACH_NETWORK"})
        client.wait_for(lambda event: event.get("id") == "persist-fail")
        client.wait_for(lambda event: event.get("type") == "agent_settled")
        (output / "fail-persist").unlink()
        checks.append(
            CheckResult(
                "readiness-stops-transport",
                len(state.requests) == before_failure,
                "A forced durable-observation failure caused zero new HTTP requests.",
                {"requestsBefore": before_failure, "requestsAfter": len(state.requests)},
            )
        )

        client.send({"id": "unicode", "type": "prompt", "message": "LF_ONLY\u2028NOT_A_FRAME"})
        unicode_accepted = client.wait_for(lambda event: event.get("id") == "unicode")
        client.wait_for(lambda event: event.get("type") == "agent_settled")
        checks.append(
            CheckResult(
                "strict-lf-jsonl",
                unicode_accepted.get("success") is True
                and "LF_ONLY\u2028NOT_A_FRAME" in _message_text(state.requests[-1]["payload"]),
                "U+2028 remained JSON string content and did not split the RPC frame.",
            )
        )

        client.send({"id": "auto-off", "type": "set_auto_compaction", "enabled": False})
        auto_off = client.wait_for(lambda event: event.get("id") == "auto-off")
        if auto_off.get("success") is not True:
            raise RuntimeError(f"could not disable threshold compaction: {auto_off!r}")
        for index in range(5):
            marker = "CURRENT_OBLIGATION_OMEGA" if index == 0 else f"SEED_{index}"
            seed = f"{marker} " + (f"bounded-seed-{index} " * 160)
            prompt_id = f"compact-seed-{index}"
            client.send({"id": prompt_id, "type": "prompt", "message": seed})
            client.wait_for(lambda event, value=prompt_id: event.get("id") == value)
            client.wait_for(lambda event: event.get("type") == "agent_settled", timeout=20)

        client.send({"id": "compact", "type": "compact"})
        compact_response = client.wait_for(lambda event: event.get("id") == "compact", timeout=45)
        client.send({"id": "after-compact", "type": "prompt", "message": "AFTER_COMPACTION"})
        client.wait_for(lambda event: event.get("id") == "after-compact")
        client.wait_for(lambda event: event.get("type") == "agent_settled", timeout=20)

        for index in range(3):
            prompt_id = f"overflow-seed-{index}"
            seed = f"OVERFLOW_HISTORY_{index} " + (f"bounded-overflow-{index} " * 120)
            client.send({"id": prompt_id, "type": "prompt", "message": seed})
            client.wait_for(lambda event, value=prompt_id: event.get("id") == value)
            client.wait_for(lambda event: event.get("type") == "agent_settled", timeout=20)
        client.send({"id": "auto-on", "type": "set_auto_compaction", "enabled": True})
        auto_on = client.wait_for(lambda event: event.get("id") == "auto-on")
        if auto_on.get("success") is not True:
            raise RuntimeError(f"could not enable overflow recovery: {auto_on!r}")

        before_overflow = len(state.requests)
        client.send({"id": "overflow", "type": "prompt", "message": "FORCE_OVERFLOW"})
        overflow_accepted = client.wait_for(lambda event: event.get("id") == "overflow")
        overflow_settled = client.wait_for(
            lambda event: event.get("type") == "agent_settled", timeout=45
        )
        if (
            overflow_accepted.get("success") is not True
            or overflow_settled.get("type") != "agent_settled"
            or len(state.requests) <= before_overflow
        ):
            raise RuntimeError("overflow prompt did not reach a settled observed attempt")

        before_question = len(state.requests)
        client.send({"id": "slow", "type": "prompt", "message": "SLOW_MAIN"})
        slow_accept = client.wait_for(lambda event: event.get("id") == "slow")
        if not state.slow_seen.wait(timeout=10):
            raise TimeoutError("slow provider request did not start")
        client.send({"id": "question", "type": "prompt", "message": "/probe-question"})
        question = client.wait_for(lambda event: event.get("type") == "extension_ui_request")
        requests_at_question = len(state.requests)
        client.send({"type": "extension_ui_response", "id": question["id"], "confirmed": True})
        client.send({"type": "extension_ui_response", "id": question["id"], "confirmed": True})
        state.release_slow.set()
        client.wait_for(lambda event: event.get("type") == "agent_settled")
        waits = [json.loads(line) for line in (output / "waits.jsonl").read_text().splitlines()]
        continued = [row for row in waits if row["state"] == "continued"]
        checks.append(
            CheckResult(
                "busy-question-single-continuation",
                slow_accept.get("success") is True
                and requests_at_question == before_question + 1
                and len(continued) == 1,
                "The RPC UI showed a question during streaming without a model turn; a "
                "duplicate answer produced one continuation.",
                {"waitId": continued[0]["waitId"] if continued else None},
            )
        )

        client.send({"id": "orphan-question", "type": "prompt", "message": "/probe-question"})
        orphan = client.wait_for(lambda event: event.get("type") == "extension_ui_request")
        stderr_parts.append(client.stop())
        client = RpcClient(
            command, _env(output, base_url), output, output / "rpc-resume-stdout.jsonl"
        )
        client.send(
            {"id": "resume-question", "type": "prompt", "message": "/probe-resume-question"}
        )
        redisplayed = client.wait_for(lambda event: event.get("type") == "extension_ui_request")
        client.send({"type": "extension_ui_response", "id": redisplayed["id"], "confirmed": False})
        client.wait_for(lambda event: event.get("id") == "resume-question")
        waits = [json.loads(line) for line in (output / "waits.jsonl").read_text().splitlines()]
        checks.append(
            CheckResult(
                "ui-close-preserves-wait",
                orphan["id"] != redisplayed["id"]
                and waits[-2]["state"] == "redisplayed"
                and waits[-1]["state"] == "continued",
                "A pending synthetic wait survived RPC process termination and was "
                "redisplayed after restart.",
            )
        )

        stderr_parts.append(client.stop())
        extension_records = read_jsonl(output / "extension.jsonl")
        resource_records = read_jsonl(output / "resource-ledger.jsonl")
        invocations_ok, invocation_evidence = _assess_invocations(
            extension_records, state.requests, resource_records
        )
        checks.append(
            CheckResult(
                "request-identity-resource-accounting",
                invocations_ok,
                "Every observed HTTP request joined to one persisted final payload, one "
                "pre-network reserve and a terminal transport/accounting record.",
                invocation_evidence,
            )
        )
        compaction_ok, compaction_evidence = _assess_compaction(
            extension_records, state.requests, compact_response
        )
        checks.append(
            CheckResult(
                "compaction-summary-context",
                compaction_ok,
                "Pi emitted manual compaction lifecycle events around a separately identified "
                "service generation, then delivered the current obligation in the next turn.",
                compaction_evidence,
            )
        )
        overflow_ok, overflow_evidence = _assess_overflow(extension_records, state.requests)
        checks.append(
            CheckResult(
                "overflow-recovery-identities",
                state.overflow_sent and overflow_ok,
                "Pi identified an overflow, generated a lifecycle-linked summary and retried "
                "once with distinct invocation identities and the current obligation.",
                overflow_evidence,
            )
        )
    except Exception as error:  # pragma: no cover - only reached by live probe failures
        checks.append(
            CheckResult(
                "probe-completion",
                False,
                f"live probe lacked a bounded observation: {error!r}",
                conclusion=CheckConclusion.INSUFFICIENT_OBSERVATION,
            )
        )
    finally:
        stderr_parts.append(client.stop())
        server.shutdown()
        server.server_close()
        (output / "stderr.log").write_text("\n".join(stderr_parts), encoding="utf-8")

    status = _gate_status(checks)
    report = GateReport(
        gate="pi-integration",
        status=status,
        checks=tuple(checks),
        versions={
            "pi": "0.87.0",
            "node": subprocess.check_output([node, "--version"], text=True).strip(),
            "packageIntegrity": package_integrity,
            "probeSha256": sha256_file(Path(__file__)),
            "extensionSha256": sha256_file(Path(__file__).with_name("pi_probe_extension.ts")),
        },
        commands=(
            "python -m tools.technical_baseline.pi_integration_probe "
            "--node ... --pi-cli ... --output ...",
        ),
        untested=(
            "real providers, accounts, billing and model quality",
            "all Pi transports and all provider adapters",
            "full Core persistence and production UI races",
        ),
        notes=(
            "Startup network, telemetry, agent retry, provider retry and cache warming were "
            "disabled.",
            "Only the localhost OpenAI-completions Provider path was exercised.",
            "The allowlisted environment used an isolated HOME, APPDATA, LOCALAPPDATA, TEMP "
            "and Pi configuration/session directory.",
        ),
    )
    report.write(output / "pi-integration.json")
    return report


def reanalyze_probe_output(output: Path) -> GateReport:
    """Re-evaluate an immutable live run without starting Pi or issuing HTTP requests."""

    original = json.loads((output / "pi-integration.json").read_text(encoding="utf-8"))
    checks = [
        CheckResult(
            name=str(row["name"]),
            passed=bool(row["passed"]),
            observation=str(row["observation"]),
            evidence=dict(row.get("evidence", {})),
            conclusion=CheckConclusion(str(row["conclusion"])),
        )
        for row in original["checks"]
        if row["name"] in SAFETY_CHECKS
    ]
    extension_records = read_jsonl(output / "extension.jsonl")
    resource_records = read_jsonl(output / "resource-ledger.jsonl")
    provider_records = read_jsonl(output / "provider.jsonl")
    response_usage = {
        str(row.get("invocationId")): row.get("responseUsage")
        for row in provider_records
        if row.get("type") == "response"
    }
    provider_requests = []
    for row in provider_records:
        if row.get("type") == "response":
            continue
        request = dict(row)
        request["responseUsage"] = response_usage.get(str(row.get("invocationId")))
        provider_requests.append(request)
    rpc_records = read_jsonl(output / "rpc-stdout.jsonl")
    compact_response = next(row for row in rpc_records if row.get("id") == "compact")

    invocations_ok, invocation_evidence = _assess_invocations(
        extension_records, provider_requests, resource_records
    )
    checks.append(
        CheckResult(
            "request-identity-resource-accounting",
            invocations_ok,
            "Offline join confirmed one persisted final payload, pre-network reserve and "
            "terminal transport/accounting record per observed HTTP request.",
            invocation_evidence,
        )
    )
    compaction_ok, compaction_evidence = _assess_compaction(
        extension_records, provider_requests, compact_response
    )
    checks.append(
        CheckResult(
            "compaction-summary-context",
            compaction_ok,
            "Offline lifecycle join confirmed the manual service generation and delivery of "
            "the current obligation in the next content turn.",
            compaction_evidence,
        )
    )
    overflow_ok, overflow_evidence = _assess_overflow(extension_records, provider_requests)
    checks.append(
        CheckResult(
            "overflow-recovery-identities",
            overflow_ok,
            "Offline lifecycle join confirmed one overflow, one service generation and one "
            "distinct retry carrying the current obligation.",
            overflow_evidence,
        )
    )
    versions = {str(key): str(value) for key, value in original["versions"].items()}
    versions["reanalysisProbeSha256"] = sha256_file(Path(__file__))
    report = GateReport(
        gate="pi-integration",
        status=_gate_status(checks),
        checks=tuple(checks),
        versions=versions,
        commands=tuple(original["commands"])
        + ("python -m tools.technical_baseline.pi_integration_probe --reanalyze <run>",),
        untested=tuple(original["untested"]),
        notes=tuple(original["notes"])
        + (
            "This report reanalyzes persisted live evidence and performs no Pi or HTTP run.",
            "Pi 0.87.0 did not emit before_provider_request for the two compaction "
            "streamSimple calls; the Provider transport wrapper still persisted and matched "
            "their final bytes, identities, reserves, responses and usage.",
        ),
    )
    report.write(output / "pi-reanalysis.json")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", type=Path)
    parser.add_argument("--pi-cli", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--package-integrity")
    parser.add_argument("--reanalyze", type=Path)
    args = parser.parse_args(argv)
    if args.reanalyze is not None:
        report = reanalyze_probe_output(args.reanalyze.resolve())
    else:
        if None in (args.node, args.pi_cli, args.output, args.package_integrity):
            raise SystemExit(
                "a live run requires --node, --pi-cli, --output and --package-integrity"
            )
        report = run_probe(
            node=cast(Path, args.node),
            pi_cli=cast(Path, args.pi_cli),
            output=cast(Path, args.output),
            package_integrity=cast(str, args.package_integrity),
        )
    print(json.dumps({"gate": report.gate, "status": report.status}, ensure_ascii=False))
    return 0 if report.status == GateStatus.POSITIVE else 1


if __name__ == "__main__":
    raise SystemExit(main())
