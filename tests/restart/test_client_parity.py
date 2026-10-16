"""Compare domain identities/states and real callback refusals across two client paths."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app import Coordinator, Driver, Pi

from .support import PROFILE, Provider, Receiver, fixture, inspect, pi_cli, trace

TABLES = ("heads", "works", "attempts", "waits", "conversations", "tool_calls", "acceptance")


def save(name: str, data: Any) -> None:
    destination = os.environ.get("ZARA_RESTART_EVIDENCE")
    if destination:
        (Path(destination) / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def test_fixed_trace_domain_parity(tmp_path: Path) -> None:
    driver_root, pi_root = tmp_path / "driver", tmp_path / "pi"
    driver_root.mkdir()
    pi_root.mkdir()
    driver = trace(driver_root, "driver")
    pi = trace(pi_root, "pi")
    assert driver["domain"] == pi["domain"]
    save(
        "client-parity.json",
        {"equal": True, "compared_tables": list(TABLES), "domain": driver["domain"]},
    )


def refused_trace(root: Path, mode: str, refusal: str) -> dict[str, Any]:
    core, _, executor = fixture(root)
    receiver = Receiver()
    change = (
        {"id": "memory", "kind": "memory", "key": "preference", "body": "stale write"}
        if refusal == "stale"
        else {"id": "forged", "kind": "grant", "key": "owner", "body": "*"}
    )
    receiver.outputs[0]["tool_changes"] = [change]
    receiver.outputs[0]["expected_heads"] = {change["id"]: 0}
    provider = Provider(receiver) if mode == "pi" else None
    thread = threading.Thread(target=provider.serve_forever, daemon=True) if provider else None
    if thread:
        thread.start()
    port = (
        Pi(pi_cli(), root / "pi-home", f"http://127.0.0.1:{provider.server_port}/v1")
        if provider
        else Driver(receiver)
    )
    coordinator = Coordinator(executor)
    try:
        coordinator.prepare("work", "A1", PROFILE)
        coordinator.dispatch("A1", 1, port)
        final = coordinator.recover("A1", pi=mode == "pi")
        assert final["state"] == "waiting"
        assert len(port.callbacks) == 1 and "error" in port.callbacks[0]
        error = port.callbacks[0]["error"]
        assert error["code"] == ("stale_basis" if refusal == "stale" else "denied")
        assert not any(h["id"] == "forged" for h in inspect(core, "heads"))
        assert next(h for h in inspect(core, "heads") if h["id"] == "memory")["revision"] == 1
        if isinstance(port, Pi) and provider:
            assert error["code"] in json.dumps(provider.packets[-1])
            assert any(e["type"] == "tool_execution_end" and e.get("isError") for e in port.events)
        return {"error": error, "domain": {t: inspect(core, t) for t in TABLES}}
    finally:
        if provider:
            provider.shutdown()
            provider.server_close()
        if thread:
            thread.join(timeout=2)


@pytest.mark.parametrize("refusal", ["stale", "forbidden"])
def test_callback_refusal_parity(tmp_path: Path, refusal: str) -> None:
    driver_root, pi_root = tmp_path / "driver", tmp_path / "pi"
    driver_root.mkdir()
    pi_root.mkdir()
    driver = refused_trace(driver_root, "driver", refusal)
    pi = refused_trace(pi_root, "pi", refusal)
    assert driver == pi
    save(
        "client-parity-" + refusal + ".json",
        {"equal": True, "refusal": refusal, "comparison": driver},
    )
