"""Development reproduction for the shipped first-use installed-package scenario."""

from pathlib import Path

from tools.probe_entry_t5 import exercise


def test_entry_t5_scenario(tmp_path: Path) -> None:
    summary = exercise(tmp_path)
    assert summary["generic_instances_created"] == 2
    assert summary["opened_actual_initial_bytes"] is True
    assert summary["new_immutable_bytes_verified"] is True
    assert summary["exact_accepted_basis"] is True
    assert summary["provider_contacted"] is False
    assert summary["continuation_state"] == "selected_work_ready"
    assert summary["adverse"] == {
        "ambiguous_alias": "ambiguous",
        "draft_context": "permission_denied",
        "request_overwrite": "output_exists",
        "stale_target": "stale_basis",
        "wrong_target": "wrong_target",
    }
    assert summary["neighbor_states"] == {
        "First Generic Notes": "available",
        "Second Generic Notes": "unavailable",
    }
