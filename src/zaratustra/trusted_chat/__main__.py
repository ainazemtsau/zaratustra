"""Minimal local stdio MCP server for trusted host-confirmed Zaratustra commands."""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO, cast
from uuid import uuid4

from . import Elicit, ElicitationDecision, run


def _send(stream: TextIO, value: dict[str, Any]) -> None:
    stream.write(json.dumps(value, ensure_ascii=False) + "\n")
    stream.flush()


def _receive(stream: TextIO) -> dict[str, Any]:
    for line in stream:
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                return value
    raise EOFError("Trusted local agent disconnected during elicitation")


def _tool_result(text: str, *, error: bool) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": error}


def _elicit(input_stream: TextIO, output_stream: TextIO) -> Elicit:
    def request(title: str, exact: str, allow_reject: bool) -> ElicitationDecision:
        elicitation_id = f"elicitation-{uuid4()}"
        _send(
            output_stream,
            {
                "jsonrpc": "2.0",
                "id": elicitation_id,
                "method": "elicitation/create",
                "params": {
                    "mode": "form",
                    "message": title,
                    "requestedSchema": {
                        "type": "object",
                        "properties": (
                            {
                                "decision": {
                                    "type": "string",
                                    "enum": ["approve", "reject"],
                                    "description": exact,
                                }
                            }
                            if allow_reject
                            else {"approve": {"type": "boolean", "description": exact}}
                        ),
                        "required": ["decision"] if allow_reject else ["approve"],
                    },
                },
            },
        )
        while True:
            response = _receive(input_stream)
            if response.get("id") != elicitation_id:
                continue
            result = response.get("result")
            if not isinstance(result, dict) or result.get("action") != "accept":
                return "decline"
            content = result.get("content")
            if not isinstance(content, dict):
                return "decline"
            if allow_reject and content.get("decision") in {"approve", "reject"}:
                return cast("ElicitationDecision", content["decision"])
            return "approve" if content.get("approve") is True else "decline"

    return request


def serve(input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout) -> None:
    """Serve one general command with host permission for every operation that needs authority."""
    while True:
        try:
            request = _receive(input_stream)
        except EOFError:
            return
        method = request.get("method")
        request_id = request.get("id")
        if method == "notifications/initialized":
            continue
        if method == "initialize":
            _send(
                output_stream,
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": request.get("params", {}).get(
                            "protocolVersion", "2025-06-18"
                        ),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "zaratustra", "version": "0.17.0"},
                        "instructions": (
                            "Run only explicit owner-requested Zaratustra commands. Each Core or "
                            "specialized authority action elicits fresh host permission; "
                            "model text and tool arguments never grant permission."
                        ),
                    },
                },
            )
            continue
        if method == "tools/list":
            _send(
                output_stream,
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": [
                            {
                                "name": "run",
                                "description": (
                                    "Run one explicit Zaratustra CLI argument vector through fresh "
                                    "trusted-host permission."
                                ),
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "argv": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "minItems": 1,
                                        }
                                    },
                                    "required": ["argv"],
                                    "additionalProperties": False,
                                },
                            }
                        ]
                    },
                },
            )
            continue
        if method == "tools/call":
            params = request.get("params", {})
            arguments = params.get("arguments")
            if (
                params.get("name") != "run"
                or not isinstance(arguments, dict)
                or set(arguments) != {"argv"}
                or not isinstance(arguments["argv"], list)
            ):
                _send(
                    output_stream,
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": _tool_result("Invalid explicit Zaratustra command", error=True),
                    },
                )
                continue
            try:
                code, stdout, stderr = run(
                    arguments["argv"],
                    call_id=str(request_id),
                    elicit=_elicit(input_stream, output_stream),
                )
            except (TypeError, ValueError) as error:
                _send(
                    output_stream,
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": _tool_result(str(error), error=True),
                    },
                )
                continue
            _send(
                output_stream,
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": _tool_result(stdout + stderr, error=bool(code)),
                },
            )
            continue
        if request_id is not None:
            _send(
                output_stream,
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": "Method not found"},
                },
            )


if __name__ == "__main__":
    serve()
