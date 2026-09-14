"""Both standard assets exercise the common CLI in fresh command processes."""

from pathlib import Path

from tools.probe_public_onboarding_r2_t4 import run


def test_both_connection_command_contracts(tmp_path: Path) -> None:
    summary = run(tmp_path / "connection-probe")
    assert summary["current_and_no_current_byte_stable"] is True
    assert summary["fresh_home_and_cwd_unchanged"] is True
    assert set(summary["agents"]) == {"codex", "claude"}
    for row in summary["agents"].values():
        assert row["unselected"]["stdout"] == row["fallback"]["stdout"]
        assert row["current_work"]["first"]["rc"] == row["no_current_work"]["first"]["rc"] == 0
