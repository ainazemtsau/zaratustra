"""The ordinary launcher supplies the installed workflow, not an instance copy."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from zaratustra.pi_adapter import external_workflow_skill, pi_main, prepare_space


def test_interactive_launcher_passes_installed_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    space = tmp_path / "space"
    space.mkdir()
    prepare_space(space, "fictional-owner", create=True)
    workspace = tmp_path / "working directory"
    workspace.mkdir()
    runtime = tmp_path / "runtime"
    (runtime / "node_modules").mkdir(parents=True)
    cli = runtime / "fictional-pi.js"
    cli.write_text("// Launcher fixture; never executed.\n", encoding="utf-8")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "CONNECT")
    monkeypatch.setattr("getpass.getuser", lambda: "fictional-owner")
    launched: list[list[str]] = []

    def run(
        command: list[str], *, cwd: Path, env: dict[str, str], check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert cwd == workspace
        assert env["ZARA_PROVIDER_PROFILE"] == "local-completions"
        assert not check
        launched.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    result = pi_main(
        [
            "--space",
            str(space),
            "--workspace",
            str(workspace),
            "--pi-cli",
            str(cli),
            "--pi-runtime",
            str(runtime),
            "--reserve-units",
            "1000",
            "--provider-profile",
            "local-completions",
            "--provider-base-url",
            "http://127.0.0.1:9/v1",
            "--local-provider-id",
            "fictional-local",
            "--local-model-id",
            "fictional-model",
            "--local-context-window",
            "16384",
            "--local-max-tokens",
            "512",
        ]
    )
    assert result == 0
    assert len(launched) == 1
    command = launched[0]
    path = Path(command[command.index("--skill") + 1])
    assert path == external_workflow_skill()
    assert path.is_file()
    assert not path.is_relative_to(workspace)
    assert list(workspace.iterdir()) == []
    assert not (runtime / "zaratustra-extension.ts").exists()


def test_missing_installed_workflow_does_not_fall_back_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("zaratustra.pi_adapter.skills.files", lambda _: tmp_path)
    with pytest.raises(FileNotFoundError, match="Installed external workflow is unavailable"):
        external_workflow_skill()
