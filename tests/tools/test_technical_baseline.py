from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tools.technical_baseline import common
from tools.technical_baseline.common import (
    CheckConclusion,
    CheckResult,
    GateReport,
    GateStatus,
    gate_status,
)
from tools.technical_baseline.durable_execution_probe import (
    EXPECTED_CHECKS as DBOS_EXPECTED_CHECKS,
)
from tools.technical_baseline.durable_execution_probe import (
    _child_command,
    _fencing_contract,
    _json_stdout,
    _load_recorded_checks,
    _payload_remnants,
    _record_check,
    _vacuum,
)
from tools.technical_baseline.pi_integration_probe import (
    _assess_compaction,
    _assess_invocations,
    _assess_overflow,
    _env,
    _gate_status,
)


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
    assert decoded["checks"][0]["conclusion"] == "contract-violation"


def test_jsonl_reader_splits_only_on_lf(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    common.append_jsonl(path, {"content": "LF_ONLY\u2028NOT_A_FRAME"})

    assert common.read_jsonl(path) == [{"content": "LF_ONLY\u2028NOT_A_FRAME"}]


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
        CheckResult("request-identity-resource-accounting", True, "observed"),
        CheckResult("compaction-summary-context", True, "observed"),
        CheckResult("overflow-recovery-identities", True, "observed"),
    ]

    assert _gate_status(complete) is GateStatus.POSITIVE
    assert _gate_status(safety_ok) is GateStatus.INCONCLUSIVE
    assert (
        _gate_status(
            [
                *safety_ok,
                CheckResult(
                    "compaction-summary-context",
                    False,
                    "small",
                    conclusion=CheckConclusion.INSUFFICIENT_OBSERVATION,
                ),
            ]
        )
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


def test_pi_invocation_check_rejects_duplicate_identity_and_digest_mismatch() -> None:
    extension: list[dict[str, Any]] = [
        {
            "type": "transport_ready",
            "invocationId": "one",
            "bodySha256": "digest",
            "payloadHookSha256": "digest",
            "purpose": "content",
        }
    ]
    provider: list[dict[str, Any]] = [
        {
            "invocationId": "one",
            "bodySha256": "digest",
            "claimedSha256": "digest",
            "responseUsage": {"total_tokens": 3},
        }
    ]
    resources: list[dict[str, Any]] = [
        {"type": "resource_reserved", "invocationId": "one", "reservedUnits": 256},
        {"type": "transport_outcome", "invocationId": "one", "status": 200},
        {
            "type": "resource_accounted",
            "invocationId": "one",
            "usage": {"input": 2, "output": 1},
        },
    ]

    assert _assess_invocations(extension, provider, resources)[0]
    assert not _assess_invocations([*extension, dict(extension[0])], provider, resources)[0]
    mismatched = [dict(provider[0], bodySha256="different")]
    assert not _assess_invocations(extension, mismatched, resources)[0]
    summary_transport = [
        {
            **extension[0],
            "purpose": "compaction-summary",
            "payloadHookSha256": None,
        }
    ]
    assert _assess_invocations(summary_transport, provider, resources)[0]
    missing_content_hook = [{**extension[0], "payloadHookSha256": None}]
    assert not _assess_invocations(missing_content_hook, provider, resources)[0]


def test_pi_compaction_checks_lifecycle_and_current_obligation() -> None:
    extension: list[dict[str, Any]] = [
        {
            "type": "session_before_compact",
            "reason": "manual",
            "tokensBefore": 100,
        },
        {
            "type": "session_compact",
            "reason": "manual",
            "invocationId": "summary",
        },
    ]
    requests: list[dict[str, Any]] = [
        {
            "invocationId": "summary",
            "purpose": "compaction-summary",
            "payload": {"messages": []},
        },
        {
            "invocationId": "next",
            "purpose": "content",
            "payload": {"messages": [{"content": "AFTER_COMPACTION CURRENT_OBLIGATION_OMEGA"}]},
        },
    ]
    response = {"success": True, "data": {"usage": {"input": 80, "output": 20}}}

    assert _assess_compaction(extension, requests, response)[0]
    requests[1]["payload"] = {"messages": [{"content": "AFTER_COMPACTION"}]}
    assert not _assess_compaction(extension, requests, response)[0]


def test_pi_overflow_check_rejects_reused_identity() -> None:
    extension: list[dict[str, Any]] = [
        {
            "type": "session_before_compact",
            "reason": "overflow",
            "willRetry": True,
        },
        {
            "type": "session_compact",
            "reason": "overflow",
            "willRetry": True,
            "invocationId": "summary",
        },
    ]
    requests: list[dict[str, Any]] = [
        {
            "invocationId": "initial",
            "purpose": "content",
            "payload": {"messages": [{"content": "FORCE_OVERFLOW"}]},
        },
        {
            "invocationId": "summary",
            "purpose": "compaction-summary",
            "payload": {"messages": []},
        },
        {
            "invocationId": "retry",
            "purpose": "overflow-retry",
            "payload": {"messages": [{"content": "FORCE_OVERFLOW CURRENT_OBLIGATION_OMEGA"}]},
        },
    ]

    assert _assess_overflow(extension, requests)[0]
    requests[2]["invocationId"] = "initial"
    assert not _assess_overflow(extension, requests)[0]


def test_dbos_journal_survives_later_stand_failure(tmp_path: Path) -> None:
    check = CheckResult("executor-readiness", True, "ready")
    checks: list[CheckResult] = []

    _record_check(tmp_path, checks, check)
    restored = _load_recorded_checks(tmp_path)

    assert restored == [check]
    assert gate_status(restored, DBOS_EXPECTED_CHECKS) is GateStatus.INCONCLUSIVE


def test_dbos_fencing_check_detects_artificial_stale_write() -> None:
    assert _fencing_contract({"result": "fenced"}, {"result": "accepted"}, (1, 1))
    assert not _fencing_contract({"result": "accepted"}, {"result": "accepted"}, (2, 0))


def test_dbos_payload_scan_detects_artificial_deletion_defect(tmp_path: Path) -> None:
    database = tmp_path / "synthetic.sqlite3"
    database.write_bytes(b"prefix-SYNTHETIC-DELETABLE-PAYLOAD-7f93-suffix")

    assert _payload_remnants([database]) == [database.name]


def test_dbos_vacuum_sanitizes_closed_wal_without_changing_mode(tmp_path: Path) -> None:
    database = tmp_path / "synthetic.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA journal_mode=WAL").fetchone()
        connection.execute("CREATE TABLE payloads(body TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO payloads(body) VALUES(?)",
            ("SYNTHETIC-DELETABLE-PAYLOAD-7f93",),
        )
        connection.execute("DELETE FROM payloads")
        connection.commit()
    finally:
        connection.close()

    sanitation = _vacuum(database)

    assert _payload_remnants([database]) == []
    assert sanitation == {"journalMode": "wal", "freelist": 0, "integrity": "ok"}
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    finally:
        connection.close()
