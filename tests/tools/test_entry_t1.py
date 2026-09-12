"""Hidden recovery, authority and foreign-change checks for the T1 evaluator."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tools.probe_entry_t1 import (
    RecoveryRefused,
    foreign_change_phase,
    publish_phase,
    recover_acceptance,
    resume_phase,
    save,
)


def test_publication_interruption_resumes_once_and_opens_exact_context(tmp_path: Path) -> None:
    base = tmp_path / "trial"
    base.mkdir()
    published = publish_phase(base, Path(__file__).resolve().parents[2], require_installed=False)
    assert published["phase"] == "published_not_accepted"
    assert published["schema_version"] == 7
    shutil.copytree(base / "workspace", base / "foreign-workspace")

    resumed = resume_phase(base)

    assert resumed["accepted_count"] == 1
    assert resumed["schema_version"] == 7
    assert resumed["acceptance_event_count"] == 1
    assert resumed["repeated_recovery_same_receipt"] is True
    assert resumed["repeated_recovery_no_write"] is True
    assert resumed["publication_revision"] + 1 == resumed["acceptance_revision"]
    assert resumed["direct_core_replay"]["code"] == "conflict"
    assert resumed["changed_intent"]["code"] == "collision"


def test_recovery_validates_the_exact_publication_event(tmp_path: Path) -> None:
    base = tmp_path / "trial"
    base.mkdir()
    publish_phase(base, Path(__file__).resolve().parents[2], require_installed=False)
    intent_path = base / "evidence" / "origin-intent.json"
    intent = json.loads(intent_path.read_bytes())
    intent["publication_request"]["provenance"] = "Different publication meaning"
    save(intent_path, intent)

    with pytest.raises(RecoveryRefused, match="intended stage"):
        recover_acceptance(base, base / "workspace")


def test_foreign_revision_is_not_adopted_as_transfer_progress(tmp_path: Path) -> None:
    base = tmp_path / "trial"
    base.mkdir()
    publish_phase(base, Path(__file__).resolve().parents[2], require_installed=False)
    shutil.copytree(base / "workspace", base / "foreign-workspace")

    refused = foreign_change_phase(base)

    assert refused["accepted_count"] == 0
    assert refused["recovery"]["code"] == "foreign_state_change"
    assert refused["core_source_refresh"]["code"] == "conflict"
    assert refused["publication_revision"] + 1 == refused["foreign_revision"]
