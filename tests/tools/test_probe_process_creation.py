"""The development probe exposes both product-construction traces."""

from pathlib import Path

from tools.probe_process_creation import run


def test_small_probe_exposes_next_occurrence(tmp_path: Path) -> None:
    summary = run(tmp_path / "small", "small")
    selected = summary["states"][-1]["view"]["selected"]
    assert selected["node"]["node_id"] == "capture"
    assert selected["occurrence"] == 2
    assert selected["grounds"][0]["data"][0]["key"] == "note"


def test_project_probe_exposes_two_exact_grounds(tmp_path: Path) -> None:
    summary = run(tmp_path / "project", "project")
    initial = summary["states"][0]["view"]
    selected = summary["states"][-1]["view"]["selected"]
    assert initial["blocked"][0]["missing_dependencies"] == [
        "read-request",
        "read-research",
    ]
    assert selected["node"]["node_id"] == "assemble"
    assert [ground["data"][0]["key"] for ground in selected["grounds"]] == [
        "request_fact",
        "research_fact",
    ]
