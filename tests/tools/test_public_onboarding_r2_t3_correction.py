"""Fresh CLI replay and retained-stage regression evidence, without freezing prose."""

import json
from typing import Any

import pytest

from tools.probe_public_onboarding_r2_t3_correction import run


@pytest.fixture(scope="module")
def correction(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return run(tmp_path_factory.mktemp("t3-correction") / "fresh-cli")


def test_fresh_cli_recovers_one_exact_receipt_with_separate_authority(
    correction: dict[str, Any],
) -> None:
    change = correction["change"]
    assert change["first"]["rc"] == change["retry"]["rc"] == 0
    assert change["exact_stdout_replay"] is True
    assert change["revision_delta"] == change["history_delta"] == change["operation_events"] == 1
    assert change["api_recovers_original_receipt"] is True
    assert change["replay_and_refusals_byte_stable"] is True
    first = change["first"]["runtime"]
    retry = change["retry"]["runtime"]
    assert first["pid"] != retry["pid"]
    assert len(first["prompts"]) == 2
    assert retry["prompts"] == first["prompts"][-1:]
    for name in ("missing", "wrong"):
        assert change[name]["rc"] == 1
        assert "permission_denied:" in change[name]["stderr"]


def test_retained_proposal_continues_to_a_distinct_stage_action_without_writes(
    correction: dict[str, Any],
) -> None:
    stages = {row["stage"]: row for row in correction["stages"]}
    assert list(stages) == [
        "draft",
        "research_waiting",
        "research_returned",
        "proposal_pending",
        "activation_pending",
    ]
    assert stages["research_returned"]["proposal_retained"] is False
    assert stages["proposal_pending"]["proposal_retained"] is True
    assert stages["activation_pending"]["proposal_retained"] is True
    assert stages["proposal_pending"]["next_action"] != stages["research_returned"]["next_action"]
    assert all(row["byte_stable"] for row in stages.values())
    assert all(row["first"]["runtime"]["prompts"] == [] for row in stages.values())


def test_projection_failure_replay_retains_warning_until_explicit_rebuild(
    correction: dict[str, Any],
) -> None:
    change = correction["projection_change"]
    first = json.loads(change["first"]["stdout"])
    retry = json.loads(change["retry"]["stdout"])
    assert change["first"]["rc"] == change["retry"]["rc"] == 0
    assert first["receipt"] == retry["receipt"]
    assert first["warnings"] and all("rebuild_required" in row for row in first["warnings"])
    assert retry["warnings"] == first["warnings"]
    assert change["exact_stdout_replay"] is True
    assert change["projection_first"] == change["projection_retry"]
    assert change["projection_retry"]["status"] == "stale_or_changed"
    assert change["first"]["runtime"]["projection_faults"] == 1
    assert change["retry"]["runtime"]["projection_faults"] == 0
    assert change["first"]["runtime"]["pid"] != change["retry"]["runtime"]["pid"]
    assert len(change["first"]["runtime"]["prompts"]) == 2
    assert change["retry"]["runtime"]["prompts"] == change["first"]["runtime"]["prompts"][-1:]
    assert change["revision_delta"] == change["history_delta"] == change["operation_events"] == 1
    assert change["replay_and_refusals_byte_stable"] is True
    assert list(change["api_warnings"]) == first["warnings"]
    for name in ("missing", "wrong"):
        assert change[name]["rc"] == 1
        assert "permission_denied:" in change[name]["stderr"]
    repair = change["repair"]
    repaired = json.loads(repair["retry"]["stdout"])
    assert repair["retry"]["rc"] == 0 and repair["projection"]["status"] == "current"
    assert repaired == first | {"warnings": []}
    assert repair["retry"]["runtime"]["prompts"] == change["retry"]["runtime"]["prompts"]
    assert repair["replay_byte_stable"] is True
    assert repair["only_overview_changed"] == ["workspace/projections/overview.md"]
