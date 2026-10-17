"""Native before-persistence query bound and separate presentation coverage."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import zaratustra_app.native_session as native_session
from zaratustra_app.native_session import NativeSession
from zaratustra_core import Core

from tests.restart.test_native_presentation import present


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, operation: str, arguments: dict[str, Any], command: str) -> dict[str, Any]:
        self.calls.append((operation, arguments))
        return {"operation": operation, "arguments": arguments}


@pytest.mark.parametrize("supplied", [None, 1, 90000000, False, "unbounded"])
def test_native_history_bound_is_fixed_before_public_call(supplied: Any) -> None:
    session = NativeSession.__new__(NativeSession)
    client = RecordingClient()
    session.owner = cast(Any, client)
    arguments = {"scope": "space", "limit": 100, "byte_limit": supplied}
    session.tool("read", "fictional-read", {"operation": "read_history", "arguments": arguments})
    assert client.calls == [("read_history", {**arguments, "byte_limit": 51200})]
    assert arguments["byte_limit"] == supplied
    session.tool(
        "read", "fictional-page", {"operation": "read_page", "arguments": {"table": "heads"}}
    )
    assert client.calls[-1] == ("read_page", {"table": "heads"})


def test_core_and_presentation_coverage_are_distinct() -> None:
    assert present({"mode": "query-coverage"})["passed"]


def test_native_large_history_is_bounded_before_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core, token = Core.initialize(tmp_path / "core")
    owner = core.connect(token)
    owner.call(
        "ingest_message",
        {
            "conversation": "fictional",
            "event_id": "large",
            "raw_base64": base64.b64encode(b"x" * 150000).decode(),
        },
        "seed-large",
    )
    unbounded = owner.call("read_history", {"scope": "space", "limit": 100}, "old-unbounded")
    assert len(json.dumps(unbounded, ensure_ascii=False).encode()) > 150000
    session = NativeSession.__new__(NativeSession)
    session.owner = owner
    monkeypatch.setattr(native_session, "uuid4", lambda: SimpleNamespace(hex="bounded-read"))
    bounded = session.tool(
        "read",
        "new-bound",
        {"operation": "read_history", "arguments": {"scope": "space", "limit": 100}},
    )
    assert len(json.dumps(bounded, ensure_ascii=False, separators=(",", ":")).encode()) <= 51200
    assert bounded["state"] == "NOT_DELIVERED"
    assert bounded["query_coverage"]["byte_limit"] == 51200
    assert bounded["query_coverage"]["returned"] == 0
    assert bounded["has_more"] and bounded["cursor"] == [0, 0]
    projected = present(
        {
            "mode": "project",
            "name": "read",
            "payload": {"operation": "read_history", "arguments": {}},
            "result": bounded,
        }
    )
    view = json.loads(projected["envelope"]["content"][0]["text"])
    assert view["query_coverage"] == bounded["query_coverage"]
    assert view["state"] == "NOT_DELIVERED"
    assert view["projection"]["core_returned"] == 0
    receipt = owner.call("lookup_receipt", {"command_id": "bounded-read"}, "inspect-bounded")
    assert receipt["result"] == bounded
    assert len(json.dumps(receipt, ensure_ascii=False).encode()) < 52000
    old_receipt = owner.call("lookup_receipt", {"command_id": "old-unbounded"}, "inspect-old")
    assert old_receipt["result"] == unbounded
    assert len(json.dumps(old_receipt, ensure_ascii=False).encode()) > 150000
    repeated = owner.call("lookup_receipt", {"command_id": "bounded-read"}, "inspect-again")
    assert repeated == receipt
    (tmp_path / "byte-bound-summary.json").write_text(
        json.dumps(
            {
                "old_unbounded_result_bytes": len(
                    json.dumps(unbounded, ensure_ascii=False).encode()
                ),
                "old_unbounded_receipt_bytes": len(
                    json.dumps(old_receipt, ensure_ascii=False).encode()
                ),
                "native_bounded_result_bytes": len(
                    json.dumps(bounded, ensure_ascii=False).encode()
                ),
                "native_bounded_receipt_bytes": len(
                    json.dumps(receipt, ensure_ascii=False).encode()
                ),
                "query_coverage": bounded["query_coverage"],
                "presentation_bytes": projected["bytes"],
                "receipt_replay_exact": repeated == receipt,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
