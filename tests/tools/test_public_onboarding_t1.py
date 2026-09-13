"""Behavior check for the public-onboarding T1 recovery risk probe."""

from importlib.metadata import version
from pathlib import Path

from tools.probe_public_onboarding_t1 import exercise


def test_migration_copy_and_full_pair_restore(tmp_path: Path) -> None:
    summary = exercise(
        tmp_path,
        program_version=version("zaratustra"),
        program_sha256="0" * 64,
    )

    assert summary["migration_copy"] == {
        "source_schema": 2,
        "target_schema": 7,
        "workspace_id": summary["migration_copy"]["workspace_id"],
        "state_revision": 1,
        "current_work_id": summary["migration_copy"]["current_work_id"],
        "current_work_status": "draft",
        "source_unchanged": True,
    }
    assert summary["recovery"]["fault_code"] == "progress_unavailable"
    assert summary["recovery"]["restored_same_pair_manifest"] is True
    assert summary["recovery"]["continuation_state"] == "selected_work_ready"
    assert summary["recovery"]["same_publication_receipt"] is True
    assert summary["recovery"]["same_acceptance_receipt"] is True
    assert summary["recovery"]["same_catalog_target"] is True
