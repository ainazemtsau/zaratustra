"""Native Pi callback and bounded provider forwarding; no database access."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from zaratustra_core import CoreError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def capture(directory: Path | None, name: str, raw: bytes) -> None:
    if directory is not None:
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / name).open("xb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())


def public_body(directory: Path | None, name: str, raw: bytes, authorization: str) -> bytes:
    secret = authorization.removeprefix("Bearer ").encode()
    if secret and secret in raw:
        capture(
            directory,
            name + ".redaction.json",
            json.dumps(
                {
                    "original_sha256": hashlib.sha256(raw).hexdigest(),
                    "original_size": len(raw),
                    "forwarded_credential_redacted": True,
                }
            ).encode(),
        )
        raw = raw.replace(secret, b"[REDACTED_AUTH]")
    capture(directory, name, raw)
    return raw


class Bridge(ThreadingHTTPServer):
    def __init__(
        self,
        endpoint: str,
        tool_handler: Any,
        limit: int,
        *,
        bearer: str = "synthetic",
        timeout: int = 35,
        native_auth: bool = False,
        capture_dir: Path | None = None,
    ):
        super().__init__(("127.0.0.1", 0), Handler)
        self.endpoint, self.tool_handler, self.limit = endpoint, tool_handler, limit
        self.bearer, self.timeout = bearer, timeout
        if native_auth and endpoint != "https://api.openai.com/v1":
            raise CoreError("invalid_request", "native_auth.endpoint")
        self.native_auth = native_auth
        self.capture_dir = capture_dir
        self.token = secrets.token_urlsafe(32)
        self.sends = 0
        self.send_lock = threading.Lock()
        self.callbacks: list[dict[str, Any]] = []


class Handler(BaseHTTPRequestHandler):
    server: Bridge

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path == "/tool":
            if self.headers.get("Authorization") != "Bearer " + self.server.token:
                self.send_error(403)
                return
            try:
                payload = json.loads(raw)
                result = self.server.tool_handler(payload["native_id"], payload["intent"])
                self.server.callbacks.append({"native_id": payload["native_id"], "receipt": result})
                self.send_response(200)
            except CoreError as exc:
                result = {"error": exc.as_dict()}
                self.server.callbacks.append(
                    {"native_id": payload["native_id"], "error": exc.as_dict()}
                )
                self.send_response(409)
            except Exception:
                result = {"error": {"code": "invalid_request", "field": "tool.payload"}}
                self.send_response(409)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
            return
        if not self.path.startswith("/provider/"):
            self.send_error(404)
            return
        authorization = "Bearer " + self.server.bearer
        if self.server.native_auth:
            if self.path != "/provider/v1/responses":
                self.send_error(403)
                return
            authorization = self.headers.get("Authorization", "")
            if not authorization.startswith("Bearer ") or authorization == "Bearer synthetic":
                self.send_error(403)
                return
        # The native Pi process may retry internally. Each physical provider send is bounded here.
        with self.server.send_lock:
            exhausted = self.server.sends >= self.server.limit
            if not exhausted:
                self.server.sends += 1
            send_number = self.server.sends
        if exhausted:
            self.send_error(429, "reserved provider call limit exhausted")
            return
        url = self.server.endpoint.rstrip("/") + self.path[len("/provider/v1") :]
        capture(self.server.capture_dir, str(send_number) + "-request.bin", raw)
        request = Request(
            url,
            raw,
            {"Content-Type": "application/json", "Authorization": authorization},
        )
        try:
            with build_opener(NoRedirect()).open(request, timeout=self.server.timeout) as response:
                content = public_body(
                    self.server.capture_dir,
                    str(send_number) + "-response.bin",
                    response.read(),
                    authorization,
                )
                self.send_response(response.status)
                self.send_header(
                    "Content-Type", response.headers.get("Content-Type", "application/json")
                )
                self.end_headers()
                self.wfile.write(content)
        except HTTPError as exc:
            content = public_body(
                self.server.capture_dir, str(send_number) + "-error.bin", exc.read(), authorization
            )
            self.send_response(exc.code)
            self.end_headers()
            self.wfile.write(content)
