"""Executor ports: independent driver and native Pi RPC, without legacy imports."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from zaratustra_core import CoreError

from .adapters.pi.bridge import Bridge


class Executor(Protocol):
    tool_handler: Any
    resource_upper: int

    def run(self, context: dict[str, Any], action_id: str) -> bytes: ...


class Driver:
    """A callable technical client; receiver owns its own input/effect log."""

    resource_upper = 2

    def __init__(self, receiver: Any):
        self.receiver = receiver
        self.tool_handler: Any = None
        self.callbacks: list[dict[str, Any]] = []

    def run(self, context: dict[str, Any], action_id: str) -> bytes:
        raw = self.receiver(context, action_id)
        result = json.loads(raw)
        if result.get("tool_changes"):
            native_id = result.pop("native_tool_call_id")
            intent = {
                "changes": result.pop("tool_changes"),
                "expected_heads": result.pop("expected_heads"),
            }
            if "initial_work" in result:
                intent["initial_work"] = result.pop("initial_work")
            try:
                receipt = self.tool_handler(native_id, intent)
                self.callbacks.append({"native_id": native_id, "receipt": receipt})
            except CoreError as error:
                self.callbacks.append({"native_id": native_id, "error": error.as_dict()})
        return json.dumps(result, ensure_ascii=False).encode()


@dataclass(frozen=True)
class LiveProfile:
    """Explicit supported provider access. Credential value never enters model context."""

    endpoint: str
    model: str
    credential_env: str
    api: str = "openai-responses"
    max_tokens: int = 8192
    context_window: int = 32768
    timeout: int = 150

    def __post_init__(self) -> None:
        if any(
            type(v) is not str for v in (self.endpoint, self.model, self.credential_env, self.api)
        ) or any(
            type(v) is not int or v < 1
            for v in (self.max_tokens, self.context_window, self.timeout)
        ):
            raise CoreError("invalid_request", "live_profile")
        if (
            not self.endpoint.startswith("https://")
            or not self.model
            or not self.credential_env
            or self.api not in {"openai-responses", "openai-completions"}
            or self.max_tokens < 1
            or self.timeout < 1
            or self.max_tokens > self.context_window
        ):
            raise CoreError("invalid_request", "live_profile")

    def bearer(self) -> str:
        value = os.environ.get(self.credential_env)
        if not value:
            raise CoreError("denied", "live_profile.credential_unavailable")
        return value


class Pi:
    """Actual installed Pi process, fresh isolated profile per call, no ambient auth."""

    resource_upper = 2

    def __init__(self, cli: Path, profile: Path, endpoint: str, *, live: LiveProfile | None = None):
        if live is None and not endpoint.startswith("http://127.0.0.1:"):
            raise CoreError("unsupported_capability", "only_explicit_localhost_profile")
        if live is not None and endpoint != live.endpoint:
            raise CoreError("invalid_request", "live_profile.endpoint")
        self.cli, self.profile, self.endpoint = cli.resolve(), profile.resolve(), endpoint
        self.live = live
        self.events: list[dict[str, Any]] = []
        self.stderr: str = ""
        self.callbacks: list[dict[str, Any]] = []
        self.tool_handler: Any = None

    def run(self, context: dict[str, Any], action_id: str) -> bytes:
        home = self.profile / hashlib.sha256(action_id.encode()).hexdigest()
        agent = home / "agent"
        agent.mkdir(parents=True, exist_ok=False)
        bridge = Bridge(
            self.endpoint,
            self.tool_handler,
            self.resource_upper,
            bearer=self.live.bearer() if self.live else "synthetic",
            timeout=self.live.timeout if self.live else 35,
        )
        bridge_thread = threading.Thread(target=bridge.serve_forever, daemon=True)
        bridge_thread.start()
        (agent / "settings.json").write_text(
            json.dumps({"retry": {"enabled": False}, "compaction": {"enabled": False}}),
            encoding="utf-8",
        )
        (agent / "models.json").write_text(
            json.dumps(
                {
                    "providers": {
                        "local": {
                            "baseUrl": f"http://127.0.0.1:{bridge.server_port}/provider/v1",
                            "api": self.live.api if self.live else "openai-completions",
                            "apiKey": "synthetic",
                            "models": [
                                {
                                    "id": self.live.model if self.live else "scripted",
                                    "name": self.live.model
                                    if self.live
                                    else "Local scripted transport",
                                    "reasoning": False,
                                    "input": ["text"],
                                    "cost": {
                                        "input": 0,
                                        "output": 0,
                                        "cacheRead": 0,
                                        "cacheWrite": 0,
                                    },
                                    "contextWindow": self.live.context_window
                                    if self.live
                                    else 32768,
                                    "maxTokens": self.live.max_tokens if self.live else 2048,
                                }
                            ],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper() in {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP"}
        }
        env.update(
            {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "APPDATA": str(home / "AppData"),
                "LOCALAPPDATA": str(home / "LocalAppData"),
                "PI_CODING_AGENT_DIR": str(agent),
                "PI_OFFLINE": "1",
                "PI_SKIP_VERSION_CHECK": "1",
                "PI_TELEMETRY": "0",
                "ZARA_NEXT_TOOL_ENDPOINT": f"http://127.0.0.1:{bridge.server_port}/tool",
                "ZARA_NEXT_TOOL_TOKEN": bridge.token,
            }
        )
        cmd = [
            shutil.which("node") or "node",
            str(self.cli),
            "--mode",
            "rpc",
            "--provider",
            "local",
            "--model",
            self.live.model if self.live else "scripted",
            "--no-session",
            "--no-builtin-tools",
            "--tools",
            "zara_change",
            "--no-mcp",
            "--no-extensions",
            "--extension",
            str(Path(__file__).parent / "adapters" / "pi" / "extension.ts"),
            "--no-context-files",
            "--no-skills",
            "--no-prompt-templates",
            "--no-themes",
            "--no-approve",
            "--offline",
        ]
        process = subprocess.Popen(
            cmd,
            cwd=home,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        incoming: queue.Queue[dict[str, Any]] = queue.Queue()
        errors: list[bytes] = []

        def read() -> None:
            assert process.stdout is not None
            for line in iter(process.stdout.readline, b""):
                try:
                    incoming.put({"event": json.loads(line), "raw": line})
                except ValueError:
                    incoming.put({"event": {"type": "invalid_protocol"}, "raw": line})

        def stderr() -> None:
            assert process.stderr is not None
            errors.append(process.stderr.read())

        reader = threading.Thread(target=read, daemon=True)
        error_reader = threading.Thread(target=stderr, daemon=True)
        reader.start()
        error_reader.start()
        try:
            assert process.stdin is not None
            message = json.dumps({"action_id": action_id, "context": context}, ensure_ascii=False)
            process.stdin.write(
                (
                    json.dumps(
                        {"id": action_id, "type": "prompt", "message": message}, ensure_ascii=False
                    )
                    + chr(10)
                ).encode()
            )
            process.stdin.flush()
            terminal = None
            deadline = time.monotonic() + (self.live.timeout + 15 if self.live else 50)
            while time.monotonic() < deadline:
                try:
                    packet = incoming.get(timeout=0.2)
                    event = packet["event"]
                except queue.Empty:
                    if process.poll() is not None:
                        raise CoreError("outcome_unknown", "pi_exit", "reconcile") from None
                    continue
                self.events.append(event)
                if event.get("type") == "invalid_protocol":
                    raise CoreError("outcome_unknown", "pi_protocol", "reconcile")
                if event.get("type") == "response" and event.get("success") is False:
                    raise CoreError("outcome_unknown", str(event.get("error")), "reconcile")
                if event.get("type") == "message_end":
                    msg = event.get("message", {})
                    if msg.get("role") == "assistant":
                        if msg.get("stopReason") == "error":
                            raise CoreError(
                                "outcome_unknown", str(msg.get("errorMessage")), "reconcile"
                            )
                        terminal = packet["raw"]
                if event.get("type") == "agent_settled":
                    if terminal is None:
                        raise CoreError("outcome_unknown", "pi_missing_terminal", "reconcile")
                    return bytes(terminal)
            raise CoreError("outcome_unknown", "pi_timeout", "reconcile")
        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            reader.join(timeout=1)
            error_reader.join(timeout=1)
            self.stderr = b"".join(errors).decode("utf-8", errors="replace")
            self.callbacks.extend(bridge.callbacks)
            bridge.shutdown()
            bridge.server_close()
            bridge_thread.join(timeout=2)

    @staticmethod
    def decode(raw: bytes) -> dict[str, Any]:
        event = json.loads(raw)
        message = event["message"] if event.get("type") == "message_end" else event
        return cast(
            dict[str, Any],
            json.loads(
                "".join(block["text"] for block in message["content"] if block["type"] == "text")
            ),
        )
