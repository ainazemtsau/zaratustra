"""Development check for the installed entry T4 restart phase."""

from __future__ import annotations

from pathlib import Path

from tools.probe_entry_t3 import exercise
from tools.probe_entry_t4 import recover


def test_generic_transfer_recovery_in_a_new_session(tmp_path: Path) -> None:
    exercise(tmp_path)
    summary = recover(tmp_path)
    recovery = summary["recovery"]
    assert recovery == {
        "current_continuation_state": "selected_work_ready",
        "exact_acceptance_receipt_recovered": True,
        "exact_publication_receipt_recovered": True,
        "no_revision_change": True,
        "one_acceptance": True,
        "restart_process": True,
        "saved_continuation_recovered": True,
        "unconfirmed_progress_fields": [
            "authorization_required_for_recovery",
            "claimed_stages",
            "intake_id",
            "preview_sha256",
            "trust",
            "version",
        ],
    }
