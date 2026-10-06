"""The selected ordinary Pi follows PATH updates and keeps its actual CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zaratustra.pi_adapter import read_pi_runtime, system_pi_runtime


def _runtime(root: Path, version: str) -> Path:
    package = root / "node_modules" / "@earendil-works" / "pi-coding-agent"
    cli = package / "dist" / "bundle" / "cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("fictional-cli", encoding="utf-8")
    (package / "package.json").write_text(
        json.dumps(
            {
                "name": "@earendil-works/pi-coding-agent",
                "version": version,
                "bin": {"pi": "dist/bundle/cli.js"},
            }
        ),
        encoding="utf-8",
    )
    return cli


def test_system_pi_follows_the_next_path_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first_cli, second_cli = _runtime(first, "1.0.4"), _runtime(second, "1.0.5")
    monkeypatch.setattr("zaratustra.pi_adapter.runtime.shutil.which", lambda _: str(first / "pi"))
    selected = system_pi_runtime()
    assert selected.cli == first_cli and selected.version == "1.0.4"
    monkeypatch.setattr("zaratustra.pi_adapter.runtime.shutil.which", lambda _: str(second / "pi"))
    selected = system_pi_runtime()
    assert selected.cli == second_cli and selected.version == "1.0.5"


def test_runtime_refuses_a_cli_outside_the_selected_package(tmp_path: Path) -> None:
    cli = _runtime(tmp_path, "1.0.4")
    path = cli.parents[2] / "package.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["bin"] = {"pi": "../../../../outside.js"}
    path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="leaves its package"):
        read_pi_runtime(tmp_path)
