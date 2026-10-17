"""Model-free checks of the installed Pi host authority and private data boundary."""

import subprocess
import sys
from pathlib import Path

import pytest
from zaratustra_app import pi_host
from zaratustra_app.entry_lock import host_lock
from zaratustra_core import CoreError


def test_diagnostics_initializes_once_and_reopens_same_space(tmp_path: Path) -> None:
    root = tmp_path / "chosen-home" / "data"
    first = pi_host.handle({"data_root": str(root), "command": "diagnostics"})
    token = (root / "owner.credential").read_bytes()
    second = pi_host.handle({"data_root": str(root), "command": "diagnostics"})
    assert first == second
    assert first["state"] == "diagnostics"
    assert (root / "owner.credential").read_bytes() == token
    assert root.with_name("data.pi-host.lock").is_file()


def test_host_refuses_overlap_without_touching_core(tmp_path: Path) -> None:
    root = tmp_path / "data"
    lease = tmp_path / "data.pi-host.lock"
    with host_lock(lease), pytest.raises(CoreError, match="native.host_busy"):
        pi_host.handle({"data_root": str(root), "command": "diagnostics"})
    assert not root.exists()


def test_host_attach_never_requires_model_or_credentials(tmp_path: Path) -> None:
    root = tmp_path / "data"
    result = pi_host.handle(
        {"data_root": str(root), "session_id": "fictional-native", "command": "attach"}
    )
    assert result["state"] == "attached"
    assert result["current"] == {}
    assert not (root / "pi").exists()


def test_abrupt_host_exit_releases_os_lock_preserving_data(tmp_path: Path) -> None:
    root = tmp_path / "data"
    pi_host.handle({"data_root": str(root), "command": "diagnostics"})
    original_token = (root / "owner.credential").read_bytes()
    lease = tmp_path / "data.pi-host.lock"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path;import os,sys;"
            "from zaratustra_app.entry_lock import host_lock;"
            "guard=host_lock(Path(sys.argv[1]));guard.__enter__();os._exit(91)",
            str(lease),
        ],
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 91, result.stderr
    reopened = pi_host.handle({"data_root": str(root), "session_id": "new-Pi", "command": "attach"})
    assert reopened["state"] == "attached" and reopened["current"] == {}
    assert (root / "owner.credential").read_bytes() == original_token
