"""The trusted host adapter composes existing authority paths without console input."""

import json
from io import StringIO
from pathlib import Path

import pytest

import zaratustra.trusted_chat.__main__ as server
from tests.zaratustra.intake.test_material import bootstrap
from tests.zaratustra.intake.test_material import prepared as prepared_material
from tests.zaratustra.onboarding.test_onboarding import _activate
from tests.zaratustra.process_creation.test_creation import _research_and_proposal
from zaratustra.core import MutationError, prepare_authorization
from zaratustra.intake import preview_bytes
from zaratustra.onboarding import prepare_onboarding_read
from zaratustra.trusted_chat import ElicitationDecision, TrustedLocalChatBackend, run


def test_exact_read_is_authorized_only_by_accepted_host_form(tmp_path: Path) -> None:
    catalog, _, _, _ = _activate(tmp_path, "simple")
    seen: list[tuple[str, str, bool]] = []

    def accepted(title: str, exact: str, allow_reject: bool) -> ElicitationDecision:
        seen.append((title, exact, allow_reject))
        return "approve"

    code, stdout, stderr = run(
        ["entry", "ready", "--catalog", str(catalog), "--designation", "Fictional simple prose"],
        call_id="read-1",
        elicit=accepted,
    )
    assert code == 0
    assert not stderr
    assert "Data: exact authorized Core Process state" in stdout
    assert len(seen) == 1
    assert '"channel": "local-chat"' not in seen[0][1]


def test_refused_host_form_does_not_report_process_state(tmp_path: Path) -> None:
    catalog, _, _, _ = _activate(tmp_path, "simple")
    code, stdout, stderr = run(
        ["entry", "ready", "--catalog", str(catalog), "--designation", "Fictional simple prose"],
        call_id="read-2",
        elicit=lambda _title, _exact, _allow_reject: "decline",
    )
    assert code == 1
    assert "Current Work: unknown; read refused" in stdout
    assert "permission_denied" in stderr
    assert "Stage: no_current_work" not in stdout


def test_reject_on_nondecision_form_refuses_without_backend_error(tmp_path: Path) -> None:
    catalog, workspace, _, _ = _activate(tmp_path, "simple")
    prepared = prepare_onboarding_read(catalog, "Fictional simple prose")
    assert prepared.process_read is not None
    prompt = prepare_authorization(
        workspace,
        prepared.process_read.query,
    )
    backend = TrustedLocalChatBackend(
        "read-reject",
        lambda _title, _exact, _allow_reject: "reject",
    )
    with pytest.raises(MutationError, match="Trusted local agent permission was not granted"):
        backend.confirm(prompt)


def test_activation_uses_same_host_backend_without_console(tmp_path: Path) -> None:
    catalog, workspace, _, _ = _research_and_proposal(tmp_path, "minimal")
    seen: list[tuple[str, str, bool]] = []

    def accepted(title: str, exact: str, allow_reject: bool) -> ElicitationDecision:
        seen.append((title, exact, allow_reject))
        return "approve"

    code, stdout, stderr = run(
        [
            "entry",
            "create",
            "activate",
            str(catalog),
            "Fictional minimal creation",
            str(workspace),
        ],
        call_id="activation-1",
        elicit=accepted,
    )
    assert code == 0
    assert not stderr
    assert '"status": "activated"' in stdout
    assert len(seen) == 1
    assert seen[0][0] == "Authorize this exact Zaratustra Process activation"


def test_material_intake_uses_same_host_backend(tmp_path: Path) -> None:
    intake = prepared_material(bootstrap(tmp_path))
    seen: list[tuple[str, str, bool]] = []

    def accepted(title: str, exact: str, allow_reject: bool) -> ElicitationDecision:
        seen.append((title, exact, allow_reject))
        return "approve"

    authorization = TrustedLocalChatBackend("material-1", accepted).confirm_material(intake)
    assert authorization.channel == "local-chat"
    assert authorization.preview_sha256 == intake.preview_sha256
    assert seen == [
        (
            "Authorize this exact Zaratustra material intake",
            preview_bytes(intake).decode("utf-8"),
            False,
        )
    ]


def test_mcp_change_form_preserves_explicit_reject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(argv: list[str], *, call_id: str, elicit: object) -> tuple[int, str, str]:
        assert argv == ["entry", "change", "review"]
        assert call_id == "call-1"
        assert callable(elicit)
        return 0, f"decision={elicit('Exact change', '{"revision": 4}', True)}\n", ""

    monkeypatch.setattr(server, "run", fake_run)
    monkeypatch.setattr(server, "uuid4", lambda: "change-form")
    incoming = StringIO(
        "\n".join(
            (
                '{"jsonrpc":"2.0","id":"init","method":"initialize","params":{}}',
                '{"jsonrpc":"2.0","id":"call-1","method":"tools/call","params":{"name":"run","arguments":{"argv":["entry","change","review"]}}}',
                '{"jsonrpc":"2.0","id":"elicitation-change-form","result":{"action":"accept","content":{"decision":"reject"}}}',
                "",
            )
        )
    )
    outgoing = StringIO()
    server.serve(incoming, outgoing)
    responses = [json.loads(line) for line in outgoing.getvalue().splitlines()]
    form = next(item for item in responses if item.get("method") == "elicitation/create")
    assert form["params"]["requestedSchema"]["properties"]["decision"]["enum"] == [
        "approve",
        "reject",
    ]
    final = responses[-1]["result"]["content"][0]["text"]
    assert final == "decision=reject\n"
