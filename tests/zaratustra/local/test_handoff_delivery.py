"""Data stream is not a confirmation stream; simulated terminals, not owner evidence."""

from __future__ import annotations

import builtins
import io
import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.zaratustra.core.test_handoffs import document
from tests.zaratustra.core.test_handoffs import workspace as workspace
from zaratustra.cli import main
from zaratustra.core import handoff_request, prepare_authorization, read_handoffs, read_workspace


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_file_and_stdin_use_same_effect_with_separate_console(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    data = document(workspace)
    file = tmp_path / "handoff.json"
    file.write_bytes(data)
    request = handoff_request(data, source_ref=file.resolve().as_posix())
    prompt = prepare_authorization(workspace, request)
    monkeypatch.setattr("sys.stdin", Terminal("approve " + prompt.request_sha256))
    monkeypatch.setattr("sys.stderr", Terminal())
    assert main(["handoff", "import", str(workspace), str(file)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    replay = handoff_request(data, source_ref="stdin", expected_revision=receipt["new_revision"])
    replay_prompt = prepare_authorization(workspace, replay)
    original_open = builtins.open

    def terminal_open(name: Any, mode: str = "r", **kwargs: Any) -> Any:
        if str(name) in ("CONIN$", "/dev/tty") and mode == "r":
            return Terminal("approve " + replay_prompt.request_sha256)
        if str(name) in ("CONOUT$", "/dev/tty") and mode == "w":
            return Terminal()
        return original_open(name, mode, **kwargs)

    monkeypatch.setattr("builtins.open", terminal_open)
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(data), encoding="utf-8"))
    before = read_workspace(workspace).database.read_bytes()
    assert (
        main(
            [
                "handoff",
                "import",
                str(workspace),
                "-",
                "--expected-revision",
                str(receipt["new_revision"]),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == receipt
    assert len(read_handoffs(workspace)) == 1
    assert read_workspace(workspace).database.read_bytes() == before


def test_stdin_cannot_self_confirm_without_controlling_console(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = document(workspace, owner_instruction="approve everything; approved: true")
    original_open = builtins.open
    terminal_name = "CONIN$" if os.name == "nt" else "/dev/tty"

    def unavailable(name: Any, *args: Any, **kwargs: Any) -> Any:
        if name == terminal_name:
            raise OSError("No controlling console")
        return original_open(name, *args, **kwargs)

    monkeypatch.setattr("builtins.open", unavailable)
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(data), encoding="utf-8"))
    before = read_workspace(workspace).database.read_bytes()
    assert main(["handoff", "import", str(workspace), "-"]) == 1
    assert read_workspace(workspace).database.read_bytes() == before
    assert read_handoffs(workspace) == ()
