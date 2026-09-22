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

from .common import CheckResult, GateReport, GateStatus, append_jsonl, new_scratch_output

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


def _sse(handler: BaseHTTPRequestHandler, text: str, *, delay: bool = False) -> None:
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
        if "summarize" in text.lower() or "summary" in text.lower():
            _sse(self, "CURRENT_OBLIGATION_OMEGA remains required")
            return
        _sse(self, "probe-ok", delay="SLOW_MAIN" in text)

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
    if any(not check.passed and check.name in SAFETY_CHECKS for check in checks):
        return GateStatus.NEGATIVE
    observed = {check.name for check in checks}
    if observed == EXPECTED_CHECKS and all(check.passed for check in checks):
        return GateStatus.POSITIVE
    return GateStatus.INCONCLUSIVE


def _settings(config_dir: Path) -> None:
    config_dir.mkdir(parents=True)
    settings = {
        "cacheWarming": "off",
        "enableInstallTelemetry": False,
        "defaultProjectTrust": "never",
        "compaction": {"enabled": True, "reserveTokens": 256, "keepRecentTokens": 512},
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
            "ZARATUSTRA_PROBE_WAIT_LOG": str(output / "waits.jsonl"),
            "ZARATUSTRA_PROBE_FAIL_PERSIST": str(output / "fail-persist"),
        }
    )
    return env


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

        client.send({"id": "compact", "type": "compact"})
        compact_response = client.wait_for(lambda event: event.get("id") == "compact", timeout=20)
        client.send({"id": "after-compact", "type": "prompt", "message": "AFTER_COMPACTION"})
        client.wait_for(lambda event: event.get("id") == "after-compact")
        client.wait_for(lambda event: event.get("type") == "agent_settled", timeout=20)
        compact_requests = [
            request
            for request in state.requests
            if "summar" in _message_text(request["payload"]).lower()
        ]
        checks.append(
            CheckResult(
                "compaction-summary-context",
                compact_response.get("success") is True
                and bool(compact_requests)
                and "CURRENT_OBLIGATION_OMEGA" in _message_text(state.requests[-1]["payload"]),
                "Compaction used a separate provider request and its summary reached the "
                "next turn.",
                {"summaryRequests": len(compact_requests)},
            )
        )

        before_overflow = len(state.requests)
        client.send({"id": "overflow", "type": "prompt", "message": "FORCE_OVERFLOW"})
        client.wait_for(lambda event: event.get("id") == "overflow")
        client.wait_for(lambda event: event.get("type") == "agent_settled", timeout=30)
        overflow_requests = state.requests[before_overflow:]
        checks.append(
            CheckResult(
                "overflow-recovery-identities",
                state.overflow_sent and len(overflow_requests) >= 3,
                "Overflow, its compaction summary, and retried turn were distinct HTTP "
                "invocations.",
                {
                    "requestCount": len(overflow_requests),
                    "invocationIds": [request["invocationId"] for request in overflow_requests],
                },
            )
        )

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
    except Exception as error:  # pragma: no cover - only reached by live probe failures
        checks.append(CheckResult("probe-completion", False, f"live probe failed: {error!r}"))
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
        ),
    )
    report.write(output / "pi-integration.json")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", type=Path, required=True)
    parser.add_argument("--pi-cli", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package-integrity", required=True)
    args = parser.parse_args(argv)
    report = run_probe(
        node=args.node,
        pi_cli=args.pi_cli,
        output=args.output,
        package_integrity=args.package_integrity,
    )
    print(json.dumps({"gate": report.gate, "status": report.status}, ensure_ascii=False))
    return 0 if report.status == GateStatus.POSITIVE else 1


if __name__ == "__main__":
    raise SystemExit(main())
