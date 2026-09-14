"""The public-onboarding R2 T3 probe covers both prose sizes and continuations."""

from pathlib import Path

from tools.probe_public_onboarding_r2_t3 import run


def test_user_like_public_onboarding_r2_t3_probe(tmp_path: Path) -> None:
    summary = run(tmp_path / "public-onboarding-r2-t3")
    assert summary["user_json_required"] is False
    assert summary["simple_stage"] == summary["complex_stage"] == "current_work"
    assert summary["complex_outcomes"] == 3
    assert summary["terminal_resume_stage"] == "no_current_work"
    assert summary["process_materials_after_terminal"] == 1
    assert summary["fresh_later_stage"] == "current_work"
    assert summary["later_work_replay_same_receipt"] is True
    assert summary["safe_change_stage"] == "applied"
    assert summary["safe_change_replay_same_receipt"] is True
