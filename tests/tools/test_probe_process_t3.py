"""The T3 probe retains both exact fictional safe-change lifecycles."""

from pathlib import Path

from tools.probe_process_t3 import run, run_correction_refusals


def test_small_change_probe_applies_added_future_work(tmp_path: Path) -> None:
    summary = run(tmp_path / "small", "small")
    assert summary["stage"] == "applied"
    assert summary["future_work_goal"] == "Review the fictional amber brief before recurrence"
    assert summary["pack_reference_bytes_preserved"] is True
    assert summary["replay_same_receipt"] is True


def test_project_change_probe_applies_changed_future_work(tmp_path: Path) -> None:
    summary = run(tmp_path / "project", "project")
    assert summary["stage"] == "applied"
    assert summary["future_work_goal"] == "Read and retain the reviewed fictional research note"
    assert summary["approval_is_core_effect"] is False
    assert summary["restart_same_request"] is True


def test_correction_probe_refuses_empty_and_unsupported_changes(tmp_path: Path) -> None:
    summary = run_correction_refusals(tmp_path / "correction")

    assert summary["edition_only"]["small"]["refusal_code"] == "no_change"
    assert summary["edition_only"]["project"]["review_or_approval_saved"] is False
    assert summary["no_future"]["refusal_code"] == "no_future_work"
    assert summary["no_future"]["core_records_unchanged"] is True
