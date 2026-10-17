"""First entry atomically publishes the DB with its owner credential."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from zaratustra_app.pi_host import handle


@pytest.mark.parametrize("window", ["database", "credential"])
def test_first_entry_crash_never_publishes_a_tokenless_core(tmp_path: Path, window: str) -> None:
    root = tmp_path / "data"
    script = """
import os,sys
from pathlib import Path
from zaratustra_app import pi_host
if sys.argv[2]=='database':
 original=pi_host.Core.initialize
 def create(path):
  original(path)
  os._exit(91)
 pi_host.Core.initialize=create
else:
 pi_host.os.rename=lambda *args: os._exit(91)
pi_host.handle({'data_root':sys.argv[1],'command':'diagnostics'})
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(root), window], capture_output=True, timeout=20
    )
    assert result.returncode == 91, result.stderr
    assert not root.exists()
    remnants = list(tmp_path.glob("data.initializing-*"))
    assert len(remnants) == 1 and (remnants[0] / "core.sqlite3").is_file()
    assert (remnants[0] / "owner.credential").exists() is (window == "credential")
    reopened = handle({"data_root": str(root), "session_id": "fresh-Pi", "command": "attach"})
    assert reopened["state"] == "attached"
    assert (root / "owner.credential").is_file()
    assert len(list(tmp_path.glob("data.initializing-*"))) == 1
