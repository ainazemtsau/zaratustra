"""Adapter presentation contracts; authoritative Core bytes and receipts remain unchanged."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

from zaratustra_core import Core

SOURCE = Path(__file__).resolve().parents[2]


def present(packet: dict[str, Any]) -> dict[str, Any]:
    executable = shutil.which("pi") or shutil.which("pi.ps1")
    assert executable, "Installed Pi SDK required"
    sdk = Path(executable).parent / "node_modules/@earendil-works/pi-coding-agent"
    process = subprocess.run(
        [
            "node",
            str(Path(__file__).with_name("native_presentation_fixture.mjs")),
            str(sdk),
            str(SOURCE),
        ],
        input=json.dumps(packet),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )
    assert process.returncode == 0, process.stderr
    return cast(dict[str, Any], json.loads(process.stdout))


def test_whole_source_budget_utf8_escaping_zero_boundary_and_mutation_ack() -> None:
    assert present({"mode": "contracts"})["passed"] is True


def test_core_history_receipt_and_replay_unchanged_after_presentation(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "core")
    owner = core.connect(token)
    owner.call(
        "apply_changes",
        {
            "changes": [
                {"id": "small", "kind": "data", "key": "small", "body": "Exact small source"},
                {
                    "id": "large",
                    "kind": "data",
                    "key": "large",
                    "body": ('Ж🙂"' + chr(92) + chr(10)) * 20000,
                },
            ]
        },
        "seed",
        expected_heads={"small": 0, "large": 0},
    )
    request = owner.request("read_history", {"scope": "space", "limit": 100}, "immutable-read")
    original = owner.send(request)
    original_bytes = json.dumps(original, ensure_ascii=False, sort_keys=True).encode()
    result = present(
        {
            "mode": "project",
            "name": "read",
            "payload": {"operation": "read_history", "arguments": {"scope": "space", "limit": 100}},
            "result": original["result"],
        }
    )
    projected = json.loads(result["envelope"]["content"][0]["text"])
    assert projected["has_more"] and len(projected["sources"]) < len(original["result"]["sources"])
    assert projected["sources"] == original["result"]["sources"][: len(projected["sources"])]
    assert (
        original_bytes
        == json.dumps(owner.send(request), ensure_ascii=False, sort_keys=True).encode()
    )
    receipt = owner.call("lookup_receipt", {"command_id": "immutable-read"}, "inspect-receipt")
    assert receipt == original
