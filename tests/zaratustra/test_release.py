"""Selecting a restored space preserves the already selected operation history."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from zaratustra.release import _preserves_operations, _register_config, _run, _selected_config


def _history(root: Path, fingerprint: str | None) -> None:
    import sqlite3

    database = root / ".zara-core" / "core.sqlite3"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE operations(operation_id TEXT PRIMARY KEY, fingerprint TEXT)"
        )
        if fingerprint is not None:
            connection.execute("INSERT INTO operations VALUES ('operation-1',?)", (fingerprint,))


def test_restored_selection_keeps_each_exact_operation(tmp_path: Path) -> None:
    import sqlite3

    original, restored = tmp_path / "original", tmp_path / "restored"
    _history(original, "original-fingerprint")
    _history(restored, "original-fingerprint")
    _preserves_operations(original, restored)
    with sqlite3.connect(restored / ".zara-core" / "core.sqlite3") as connection:
        connection.execute("UPDATE operations SET fingerprint='changed'")
    with pytest.raises(ValueError, match="omits or changes operation"):
        _preserves_operations(original, restored)
    with sqlite3.connect(restored / ".zara-core" / "core.sqlite3") as connection:
        connection.execute("DELETE FROM operations")
    with pytest.raises(ValueError, match="omits or changes operation"):
        _preserves_operations(original, restored)


def test_default_launch_reference_and_explicit_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zaratustra import release

    monkeypatch.delenv("ZARATUSTRA_CONFIG", raising=False)
    monkeypatch.setattr(release, "_launch_reference", lambda: tmp_path / "reference.json")
    with pytest.raises(ValueError, match="Select your installation"):
        _selected_config(None)
    chosen = tmp_path / "instance" / "config.json"
    _register_config(chosen)
    assert _selected_config(None) == chosen.resolve()
    other = tmp_path / "other.json"
    assert _selected_config(other) == other.resolve()
    monkeypatch.setenv("ZARATUSTRA_CONFIG", str(other))
    assert _selected_config(None) == other.resolve()
    # Bare navigation commands must inspect the selected space, not fail parsing.
    observed: list[tuple[str, str, Path]] = []
    monkeypatch.setattr(release, "_config", lambda _: {})
    monkeypatch.setattr(release, "_actor", lambda _: None)

    def inspect(args: argparse.Namespace, path: Path) -> int:
        observed.append((args.command, args.mode, path))
        return 0

    monkeypatch.setattr(release, "_workspace_cli", inspect)
    for command in ("workspace", "projects", "git"):
        assert release.main([command]) == 0
    assert observed == [
        ("workspace", "info", other.resolve()),
        ("projects", "list", other.resolve()),
        ("git", "status", other.resolve()),
    ]


def test_run_uses_system_pi_and_selected_subscription_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zaratustra import pi_adapter, release

    runtime = pi_adapter.PiRuntime(tmp_path, tmp_path / "cli.js", "1.0.4")
    monkeypatch.setattr(pi_adapter, "system_pi_runtime", lambda: runtime)
    monkeypatch.setattr(release, "_ready_space", lambda _: None)
    observed: list[list[str]] = []

    def launch(command: list[str]) -> int:
        observed.append(command)
        return 0

    monkeypatch.setattr(pi_adapter, "pi_main", launch)
    config: dict[str, object] = {
        "pi_source": "system",
        "pi_runtime": str(tmp_path / "old"),
        "space": str(tmp_path / "space"),
        "workspace": str(tmp_path / "work"),
        "node": "node",
        "reserve_units": 3000,
        "provider_profile": "codex-sse",
        "provider_base_url": "https://chatgpt.com/backend-api",
        "model_id": "gpt-5.6-luna",
        "subscription_agent_dir": str(tmp_path / "subscription"),
    }
    args = argparse.Namespace(
        model="gpt-6.1-sol", thinking=None, activity_id=None, work_id=None, pi_tools=None
    )
    assert _run(args, config) == 0
    command = observed[0]
    assert command[command.index("--pi-cli") + 1] == str(runtime.cli)
    assert command[command.index("--model") + 1] == "gpt-6.1-sol"
    assert command[command.index("--provider-profile") + 1] == "codex-sse"
    assert command[command.index("--subscription-agent-dir") + 1] == str(tmp_path / "subscription")
