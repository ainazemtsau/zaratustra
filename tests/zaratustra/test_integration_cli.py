"""The model-free entry routes typed commands to the same Core-backed adapter."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from tests.zaratustra.foundation.test_binding import _ready
from zaratustra.foundation import read_space, upgrade_knowledge_space
from zaratustra.release import app_main, main


@pytest.mark.parametrize("native_entry", [False, True])
def test_cli_catalog_contract_apply_and_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    native_entry: bool,
) -> None:
    root, space, owner, activity, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    # Runtime verification is tested by release; this fixture has no live launch configuration.
    monkeypatch.setattr(
        "zaratustra.release._config",
        lambda _: {
            "space": str(root),
            "space_id": str(space),
            "actor": "owner",
        },
    )
    monkeypatch.setattr("getpass.getuser", lambda: "owner")
    prefix = ["integration"]
    configured_path = tmp_path / "fictional.json"
    reference = tmp_path / "launch-config.json"
    reference.write_text(
        json.dumps({"version": 1, "config": str(configured_path)}), encoding="utf-8"
    )
    monkeypatch.delenv("ZARATUSTRA_CONFIG", raising=False)
    monkeypatch.setattr("zaratustra.release._launch_reference", lambda: reference)
    invoke = app_main if native_entry else main
    config = [] if native_entry else ["--config", str(configured_path)]
    assert invoke([*prefix, "catalog", *config]) == 0
    assert json.loads(capsys.readouterr().out)["adapters"][0]["adapter"] == "manual"
    assert (
        invoke([*prefix, "contract", *config, "--adapter", "manual", "--operation", "retain_text"])
        == 0
    )
    assert json.loads(capsys.readouterr().out)["schema"]["additionalProperties"] is False
    args = tmp_path / "arguments.json"
    text = "  Свободный текст; no required package fields\r\n"
    args.write_text(
        json.dumps(
            {
                "activity_id": str(activity),
                "origin": "Fictional service",
                "content_text": text,
            }
        ),
        encoding="utf-8",
    )
    operation_id = str(uuid4())
    command = [
        *prefix,
        "apply",
        *config,
        "--adapter",
        "manual",
        "--operation",
        "retain_text",
        "--contract-version",
        "1",
        "--operation-id",
        operation_id,
        "--arguments",
        str(args),
    ]
    assert invoke(command) == 0
    retained = json.loads(capsys.readouterr().out)
    revision = read_space(root).state_revision
    assert invoke(command) == 0
    assert json.loads(capsys.readouterr().out) == retained
    assert read_space(root).state_revision == revision
    args.write_text(
        json.dumps({"record_id": retained["record_id"], "revision": 1}), encoding="utf-8"
    )
    assert (
        invoke(
            [
                *prefix,
                "apply",
                *config,
                "--adapter",
                "manual",
                "--operation",
                "read_document",
                "--contract-version",
                "1",
                "--operation-id",
                str(uuid4()),
                "--arguments",
                str(args),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["content_text"] == text
