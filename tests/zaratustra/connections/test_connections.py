"""Connection identity and non-overwriting export; no domain authority."""

import hashlib
import shutil
from pathlib import Path

import pytest

from zaratustra.connections import Agent, export_connection, inspect_connection


@pytest.mark.parametrize("agent", ["codex", "claude"])
def test_new_export_exact_identity_and_collision(tmp_path: Path, agent: Agent) -> None:
    root = tmp_path / "chat"
    assert inspect_connection(agent, None).state == "not_selected"
    assert inspect_connection(agent, root).state == "missing"
    assert not root.exists()
    result = export_connection(agent, root)
    assert result.state == "files_match"
    assert result.skill is not None
    before = result.skill.read_bytes()
    assert result.actual_sha256 == result.expected_sha256 == hashlib.sha256(before).hexdigest()
    with pytest.raises(FileExistsError):
        export_connection(agent, root)
    assert result.skill.read_bytes() == before
    result.skill.write_bytes(before + b"changed")
    assert inspect_connection(agent, root).state == "different"


@pytest.mark.parametrize("agent", ["codex", "claude"])
def test_copied_slot_is_not_certified_for_another_root(tmp_path: Path, agent: Agent) -> None:
    original = tmp_path / "original"
    export_connection(agent, original)
    copied = tmp_path / "copied"
    shutil.copytree(original, copied)
    assert inspect_connection(agent, copied).state == "different"
    assert inspect_connection(agent, original).state == "files_match"
