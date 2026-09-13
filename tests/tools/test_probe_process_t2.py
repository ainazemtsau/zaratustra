"""The T2 probe exposes both complete synthetic creation paths."""

from pathlib import Path

from tools.probe_process_t2 import run


def test_small_creation_probe_retains_recurrence_and_opens(tmp_path: Path) -> None:
    summary = run(tmp_path / "small", "small")
    assert summary["selected"]["node"]["recurring"] is True
    assert summary["provider_contacted"] is False
    assert summary["research_approval"] is False
    assert summary["final_status"]["stage"] == "activated"
    assert summary["final_status"]["first_work_openable"] is True


def test_project_creation_probe_retains_dependencies_and_opens(tmp_path: Path) -> None:
    summary = run(tmp_path / "project", "project")
    assert summary["blocked"][0]["missing_dependencies"] == [
        "read-request",
        "read-research",
    ]
    assert summary["request_is_readable"] is True
    assert summary["research_status"] == "untrusted_research"
    assert len(summary["activation_receipts"]) == 6
