"""Native Pi callback and bounded provider forwarding; no database access."""

from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class Bridge(ThreadingHTTPServer):
    def __init__(self, endpoint: str, tool_handler: Any, limit: int):
        super().__init__(("127.0.0.1", 0), Handler)
        self.endpoint, self.tool_handler, self.limit = endpoint, tool_handler, limit
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
            except Exception as exc:
                result = {"error": str(exc)}
                self.send_response(409)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
            return
        if not self.path.startswith("/provider/"):
            self.send_error(404)
            return
        # The native Pi process may retry internally. Each physical provider send is bounded here.
        with self.server.send_lock:
            exhausted = self.server.sends >= self.server.limit
            if not exhausted:
                self.server.sends += 1
        if exhausted:
            self.send_error(429, "reserved provider call limit exhausted")
            return
        url = self.server.endpoint.rstrip("/") + self.path[len("/provider/v1") :]
        request = Request(
            url, raw, {"Content-Type": "application/json", "Authorization": "Bearer synthetic"}
        )
        try:
            with urlopen(request, timeout=35) as response:
                content = response.read()
                self.send_response(response.status)
                self.send_header(
                    "Content-Type", response.headers.get("Content-Type", "application/json")
                )
                self.end_headers()
                self.wfile.write(content)
        except HTTPError as exc:
            self.send_response(exc.code)
            self.end_headers()
            self.wfile.write(exc.read())
