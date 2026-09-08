"""Restoration must preserve workspace layout as well as database bytes."""

import zipfile
from pathlib import Path

from tools.retain_trial import retain_trial
from zaratustra.core import init_workspace, read_workspace


def test_extracted_trial_reopens_without_repair(tmp_path: Path) -> None:
    trial = tmp_path / "trial"
    original = trial / "workspace"
    original.mkdir(parents=True)
    info = init_workspace(original)
    before = info.database.read_bytes()
    extra = original / "inbox" / "nested-empty"
    extra.mkdir()
    environment = trial / "venv"
    environment.mkdir()
    (environment / "excluded.txt").write_text("separately installed", encoding="utf-8")
    target = tmp_path / "trial.zip"

    retain_trial(trial, target)
    extracted = tmp_path / "restored"
    with zipfile.ZipFile(target) as archive:
        archive.extractall(extracted)
    restored = extracted / "workspace"
    assert read_workspace(restored).workspace_id == info.workspace_id
    assert init_workspace(restored).database.read_bytes() == before
    assert (restored / "inbox" / "nested-empty").is_dir()
    assert not (extracted / "venv").exists()
    assert info.database.read_bytes() == before
