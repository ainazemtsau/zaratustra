from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.technical_baseline import common
from tools.technical_baseline.common import CheckResult, GateReport, GateStatus
from tools.technical_baseline.durable_execution_probe import _child_command, _json_stdout
from tools.technical_baseline.pi_integration_probe import _env, _gate_status


def test_probe_output_must_be_a_new_scratch_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(common, "SCRATCH", scratch.resolve())

    created = common.new_scratch_output(scratch / "one-run")

    assert created == (scratch / "one-run").resolve()
    with pytest.raises(FileExistsError):
        common.new_scratch_output(created)
    with pytest.raises(ValueError):
        common.new_scratch_output(tmp_path / "outside")


def test_gate_report_is_lf_framed_machine_readable_json(tmp_path: Path) -> None:
    report = GateReport(
        gate="criterion",
        status=GateStatus.INCONCLUSIVE,
        checks=(CheckResult("bounded-check", False, "not enough evidence"),),
        versions={"component": "1.0"},
        commands=("probe --bounded",),
        untested=("external service",),
    )
    path = tmp_path / "report.json"

    report.write(path)
    raw = path.read_text(encoding="utf-8")
    decoded = json.loads(raw)

    assert raw.endswith("\n") and "\r" not in raw
    assert decoded["status"] == "inconclusive"
    assert decoded["checks"][0]["name"] == "bounded-check"


def test_pi_gate_distinguishes_safety_failure_from_incomplete_coverage() -> None:
    safety_ok = [
        CheckResult("final-request", True, "observed"),
        CheckResult("readiness-stops-transport", True, "observed"),
        CheckResult("strict-lf-jsonl", True, "observed"),
        CheckResult("busy-question-single-continuation", True, "observed"),
        CheckResult("ui-close-preserves-wait", True, "observed"),
    ]

    complete = [
        *safety_ok,
        CheckResult("compaction-summary-context", True, "observed"),
        CheckResult("overflow-recovery-identities", True, "observed"),
    ]

    assert _gate_status(complete) is GateStatus.POSITIVE
    assert _gate_status(safety_ok) is GateStatus.INCONCLUSIVE
    assert (
        _gate_status([*safety_ok, CheckResult("compaction-summary-context", False, "small")])
        is GateStatus.INCONCLUSIVE
    )
    assert (
        _gate_status([CheckResult("readiness-stops-transport", False, "sent")])
        is GateStatus.NEGATIVE
    )


def test_pi_environment_excludes_provider_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-inherited")
    output = tmp_path / "probe"
    output.mkdir()

    env = _env(output, "http://127.0.0.1:1/v1")

    assert "OPENAI_API_KEY" not in env
    assert env["HOME"] == str(output / "isolated-user")
    assert env["ZARATUSTRA_PROBE_PROVIDER_BASE_URL"].startswith("http://127.0.0.1:")


def test_durable_probe_child_command_uses_descriptive_module_name(tmp_path: Path) -> None:
    command = _child_command(tmp_path, "fault", workflow_id="workflow")

    assert "tools.technical_baseline.durable_execution_probe" in command
    assert "--workflow-id" in command


def test_json_stdout_ignores_dbos_log_lines() -> None:
    result = subprocess.CompletedProcess(
        args=["probe"],
        returncode=0,
        stdout='informational line\n{"result":"accepted"}\n',
        stderr="",
    )

    assert _json_stdout(result) == {"result": "accepted"}
