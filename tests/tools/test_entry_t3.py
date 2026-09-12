"""Development reproduction checks for installed entry T3 behavior."""

from __future__ import annotations

from pathlib import Path

from tools.probe_entry_t3 import exercise


def test_generic_new_material_reproduction(tmp_path: Path) -> None:
    summary = exercise(tmp_path)
    assert summary["schema_version"] == 7
    assert summary["material_was_unregistered_before"] is True
    assert summary["exact_material_read_after"] is True
    assert summary["exact_basis_accepted"] is True
    assert summary["distinct_stage_receipts"] is True
    assert summary["completion_status"] == "not_requested"
    assert summary["continuation_state"] == "selected_work_ready"
    assert summary["planned_publication_revision"] + 1 == summary["final_revision"]
    assert summary["planned_acceptance_revision"] == summary["final_revision"]
    assert summary["adverse"] == {
        "asserted_approval": "invalid_envelope",
        "changed_material": "permission_denied",
        "foreign_target": "target_mismatch",
        "missing_confirmation": "permission_denied",
    }
