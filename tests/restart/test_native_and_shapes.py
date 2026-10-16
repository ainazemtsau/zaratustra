"""Native bridge effect limits and exact schemas; no live model."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from zaratustra_app.adapters.pi.bridge import Bridge
from zaratustra_core import CoreError

from .support import Provider, Receiver, fixture, inspect


def test_provider_limit_is_atomic(tmp_path: Path) -> None:
    receiver = Receiver()
    provider = Provider(receiver)
    bridge = Bridge(f"http://127.0.0.1:{provider.server_port}/v1", lambda *_: {}, 1)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (provider, bridge)]
    for thread in threads:
        thread.start()
    barrier = threading.Barrier(2)
    payload = json.dumps(
        {
            "messages": [
                {"role": "user", "content": json.dumps({"context": {}, "action_id": "only-effect"})}
            ]
        }
    ).encode()

    def send(_: int) -> int:
        barrier.wait()
        try:
            with urlopen(
                Request(
                    f"http://127.0.0.1:{bridge.server_port}/provider/v1/chat/completions",
                    payload,
                    {"Content-Type": "application/json"},
                ),
                timeout=10,
            ) as response:
                response.read()
                return int(response.status)
        except HTTPError as exc:
            return exc.code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(send, (1, 2)))
        assert sorted(statuses) == [200, 429]
        assert len(provider.packets) == len(receiver.actions) == bridge.sends == 1
    finally:
        for server in (bridge, provider):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)


@pytest.mark.parametrize(
    "kind,value",
    [
        ("boolean", "true"),
        ("integer", True),
        ("integer", "4"),
        ("decimal-string", "NaN"),
        ("decimal-string", "Infinity"),
        ("datetime", "2026-10-16T12:00:00"),
        ("date", "2026-13-01"),
        ("unknown", "text"),
    ],
)
def test_schema_rejects_coercion(tmp_path: Path, kind: str, value: object) -> None:
    core, owner, _ = fixture(tmp_path)
    owner.call(
        "apply_changes",
        {"changes": [{"id": "schema", "kind": "data", "key": "schema", "body": {"type": kind}}]},
        "schema",
        expected_heads={"schema": 0},
    )
    with pytest.raises(CoreError, match="invalid_request"):
        owner.call(
            "apply_changes",
            {
                "changes": [
                    {
                        "id": "entry",
                        "kind": "data",
                        "key": "entry",
                        "body": value,
                        "schema_ref": {"id": "schema", "revision": 1},
                    }
                ]
            },
            "entry",
            expected_heads={"entry": 0},
        )
    assert not any(h["id"] == "entry" for h in inspect(core, "heads"))


def test_duplicate_fields_and_valid_free_text(tmp_path: Path) -> None:
    core, owner, _ = fixture(tmp_path)
    schema = {
        "type": "object",
        "fields": [{"name": "x", "type": "integer"}, {"name": "x", "type": "text"}],
    }
    owner.call(
        "apply_changes",
        {"changes": [{"id": "schema", "kind": "data", "key": "schema", "body": schema}]},
        "schema",
        expected_heads={"schema": 0},
    )
    with pytest.raises(CoreError, match="invalid_request"):
        owner.call(
            "apply_changes",
            {
                "changes": [
                    {
                        "id": "entry",
                        "kind": "data",
                        "key": "entry",
                        "body": {"x": 1},
                        "schema_ref": {"id": "schema", "revision": 1},
                    }
                ]
            },
            "entry",
            expected_heads={"entry": 0},
        )
    owner.call(
        "apply_changes",
        {
            "changes": [
                {"id": "free", "kind": "data", "key": "free", "body": "The moon is made of cheese."}
            ]
        },
        "free",
        expected_heads={"free": 0},
    )
    assert any(h["id"] == "free" for h in inspect(core, "heads"))


def test_same_admission_preview_rolls_back(tmp_path: Path) -> None:
    core, owner, _ = fixture(tmp_path)
    request = owner.request(
        "apply_changes",
        {"changes": [{"id": "preview", "kind": "data", "key": "preview", "body": "value"}]},
        "preview",
        expected_heads={"preview": 0},
    )
    assert owner.preview(request)["admissible"] is True
    assert not any(h["id"] == "preview" for h in inspect(core, "heads"))
    assert not any(r["command"] == "preview" for r in inspect(core, "receipts"))
    owner.send(request)
    assert any(h["id"] == "preview" for h in inspect(core, "heads"))
    stale = request.model_copy(update={"command_id": "other"})
    readiness = owner.preview(stale)
    assert readiness["admissible"] is False and readiness["error"]["code"] == "stale_basis"
    with pytest.raises(CoreError, match="stale_basis"):
        owner.send(stale)
