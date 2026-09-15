"""The trusted host adapter composes existing authority paths without console input."""

import json
import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest

import zaratustra.process_creation as creation_module
import zaratustra.trusted_chat.__main__ as server
from tests.zaratustra.entry.test_catalog import bootstrap as bootstrap_catalog
from tests.zaratustra.intake.test_material import bootstrap
from tests.zaratustra.intake.test_material import prepared as prepared_material
from tests.zaratustra.onboarding.test_onboarding import _activate
from tests.zaratustra.process_creation.test_creation import _research_and_proposal
from zaratustra.core import (
    MutationError,
    apply_mutation,
    authorize_local,
    init_workspace,
    prepare_authorization,
    read_workspace,
)
from zaratustra.entry import add_entry
from zaratustra.intake import preview_bytes
from zaratustra.onboarding import prepare_onboarding_read, save_prose_creation_draft
from zaratustra.process_creation import (
    ProcessCreationError,
    inspect_process_creation,
    prepare_process_activation,
)
from zaratustra.trusted_chat import (
    ElicitationDecision,
    TrustedLocalChatBackend,
    run,
    run_trusted,
)
from zaratustra.trusted_chat.agent import preview_process_activation


def test_exact_read_is_authorized_only_by_accepted_host_form(tmp_path: Path) -> None:
    catalog, _, _, _ = _activate(tmp_path, "simple")
    seen: list[tuple[str, str, bool]] = []

    def accepted(title: str, exact: str, allow_reject: bool) -> ElicitationDecision:
        seen.append((title, exact, allow_reject))
        return "approve"

    code, stdout, stderr = run_trusted(
        ["entry", "ready", "--catalog", str(catalog), "--designation", "Fictional simple prose"],
        actor="trusted-codex-host",
        source_ref="owner-chat-message:fictional-read-1",
        decide=accepted,
    )
    assert code == 0
    assert not stderr
    assert "Data: exact authorized Core Process state" in stdout
    assert len(seen) == 1
    assert '"channel": "local-chat"' not in seen[0][1]


def test_refused_host_form_does_not_report_process_state(tmp_path: Path) -> None:
    catalog, _, _, _ = _activate(tmp_path, "simple")
    code, stdout, stderr = run_trusted(
        ["entry", "ready", "--catalog", str(catalog), "--designation", "Fictional simple prose"],
        actor="trusted-codex-host",
        source_ref="owner-chat-message:unrelated-request",
        decide=lambda _title, _exact, _allow_reject: "decline",
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


def test_agent_entry_saves_and_recovers_prose_in_fresh_processes(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    designation = "Fictional Russian draft"
    common = [sys.executable, "-I", "-m", "zaratustra.trusted_chat.agent"]
    saved = subprocess.run(
        [
            *common,
            "draft",
            str(catalog),
            designation,
            "Сохранить точный вымышленный замысел.",
            "--title",
            "Вымышленный процесс",
            "--outcome",
            "Черновик доступен после перезапуска.",
            "--constraint",
            "Только локальные вымышленные данные.",
            "--created-by",
            "trusted-local-agent-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert saved.returncode == 0, saved.stderr
    assert "Stage: draft" in saved.stdout

    resumed = subprocess.run(
        [
            *common,
            "read",
            str(catalog),
            designation,
            "--actor",
            "trusted-local-agent-test",
            "--source-ref",
            "owner-message:fresh-read",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert resumed.returncode == 0, resumed.stderr
    assert "Сохранить точный вымышленный замысел." in resumed.stdout
    assert "Черновик доступен после перезапуска." in resumed.stdout

    repeated = subprocess.run(
        saved.args, check=False, capture_output=True, text=True, encoding="utf-8"
    )
    assert repeated.returncode == 0, repeated.stderr
    assert repeated.stdout == saved.stdout


def test_agent_entry_reads_active_selected_core_state_without_form(tmp_path: Path) -> None:
    catalog, _workspace, _definition, receipt = _activate(tmp_path, "simple")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "zaratustra.trusted_chat.agent",
            "read",
            str(catalog),
            "Fictional simple prose",
            "--actor",
            "trusted-local-agent-test",
            "--source-ref",
            "owner-message:active-selection",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 0, result.stderr
    assert "Stage: current_work" in result.stdout
    assert f"Current Work: {receipt.entry.work_id}" in result.stdout


def test_agent_entry_refuses_missing_selection_without_reading_catalog(tmp_path: Path) -> None:
    missing = tmp_path / "must-not-be-created.json"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "zaratustra.trusted_chat.agent",
            "read",
            str(missing),
            "",
            "--actor",
            "trusted-local-agent-test",
            "--source-ref",
            "owner-message:missing-selection",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 1
    assert "Explicit designation is required" in result.stderr
    assert not missing.exists()


def test_agent_entry_has_no_activation_or_change_route(tmp_path: Path) -> None:
    catalog = tmp_path / "must-not-be-created.json"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "zaratustra.trusted_chat.agent",
            "activate",
            str(catalog),
            "Fictional selection",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 2
    assert "invalid choice: 'activate'" in result.stderr
    assert not catalog.exists()


def test_agent_entry_refuses_directory_catalog_without_side_effect(tmp_path: Path) -> None:
    before = tuple(tmp_path.iterdir())
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "zaratustra.trusted_chat.agent",
            "draft",
            str(tmp_path),
            "Fictional draft",
            "A need",
            "--title",
            "A title",
            "--outcome",
            "An outcome",
            "--constraint",
            "A constraint",
            "--created-by",
            "trusted-local-agent-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 1
    assert "catalog must be a file path" in result.stderr
    assert tuple(tmp_path.iterdir()) == before


def test_agent_entry_cannot_shadow_cataloged_process_and_reports_prior_conflict(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    work_id = bootstrap_catalog(workspace, "Legacy fictional Process")
    catalog = tmp_path / "catalog.json"
    add_entry(catalog, "Legacy fictional Process", workspace, work_id, aliases=("legacy",))
    before = catalog.read_bytes()
    refused = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "zaratustra.trusted_chat.agent",
            "draft",
            str(catalog),
            "legacy",
            "A shadow must not be saved.",
            "--title",
            "Shadow",
            "--outcome",
            "No shadow",
            "--constraint",
            "Keep exact selection",
            "--created-by",
            "trusted-local-agent-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert refused.returncode == 1
    assert "A cataloged Process already has this designation or alias" in refused.stderr
    assert catalog.read_bytes() == before
    assert not catalog.with_name(f"{catalog.name}.process-creations").exists()

    save_prose_creation_draft(
        catalog,
        "Legacy fictional Process",
        process_title="Pre-existing conflicting draft",
        need="Simulate a journal retained by an older entry path.",
        desired_outcomes=("Report ambiguity.",),
        constraints=("Do not choose silently.",),
        created_by="legacy-supported-api",
    )
    ambiguous = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "zaratustra.trusted_chat.agent",
            "read",
            str(catalog),
            "Legacy fictional Process",
            "--actor",
            "trusted-local-agent-test",
            "--source-ref",
            "owner-message:ambiguous-selection",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert ambiguous.returncode == 1
    assert "selection_conflict" in ambiguous.stderr


def _activation_digest(output: str) -> str:
    prefix = "Assistant freshness SHA-256: "
    return next(
        line.removeprefix(prefix) for line in output.splitlines() if line.startswith(prefix)
    )


def test_agent_entry_previews_then_activates_exact_unchanged_intent(
    tmp_path: Path,
) -> None:
    catalog, workspace, _request, _definition = _research_and_proposal(tmp_path, "small")
    designation = "Fictional small creation"
    common = [sys.executable, "-I", "-m", "zaratustra.trusted_chat.agent"]
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    preview = subprocess.run(
        [*common, "activation-preview", str(catalog), designation, str(workspace)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    assert preview.returncode == 0, preview.stderr
    assert "Proposed Zaratustra Process activation" in preview.stdout
    assert "This preview is read-only; it created no Process records." in preview.stdout
    assert not workspace.exists()
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    digest = _activation_digest(preview.stdout)

    missing_confirmation = subprocess.run(
        [
            *common,
            "activation-confirm",
            str(catalog),
            designation,
            str(workspace),
            "--actor",
            "trusted-local-agent-test",
            "--source-ref",
            "owner-message:missing-confirmation-binding",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    assert missing_confirmation.returncode == 2
    assert "--expected-sha256" in missing_confirmation.stderr
    assert not workspace.exists()

    wrong_confirmation = subprocess.run(
        [
            *common,
            "activation-confirm",
            str(catalog),
            designation,
            str(workspace),
            "--expected-sha256",
            "0" * 64,
            "--actor",
            "trusted-local-agent-test",
            "--source-ref",
            "owner-message:wrong-confirmation-binding",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    assert wrong_confirmation.returncode == 1
    assert "stale_activation" in wrong_confirmation.stderr
    assert not workspace.exists()

    changed_target = tmp_path / "changed-target"
    refused = subprocess.run(
        [
            *common,
            "activation-confirm",
            str(catalog),
            designation,
            str(changed_target),
            "--expected-sha256",
            digest,
            "--actor",
            "trusted-local-agent-test",
            "--source-ref",
            "owner-message:create-exact-proposal",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    assert refused.returncode == 1
    assert "stale_activation" in refused.stderr
    assert not changed_target.exists()
    assert inspect_process_creation(catalog, designation).activation_target is None

    activated = subprocess.run(
        [
            *common,
            "activation-confirm",
            str(catalog),
            designation,
            str(workspace),
            "--expected-sha256",
            digest,
            "--actor",
            "trusted-local-agent-test",
            "--source-ref",
            "owner-message:create-exact-proposal",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    assert activated.returncode == 0, activated.stderr
    status = inspect_process_creation(catalog, designation)
    assert status.stage == "activated"
    assert str(status.process_id) in activated.stdout
    assert str(status.first_work_id) in activated.stdout

    fresh_read = subprocess.run(
        [
            *common,
            "read",
            str(catalog),
            designation,
            "--actor",
            "trusted-local-agent-test",
            "--source-ref",
            "owner-message:fresh-activation-read",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    assert fresh_read.returncode == 0, fresh_read.stderr
    assert "Stage: current_work" in fresh_read.stdout
    assert str(status.first_work_id) in fresh_read.stdout

    repeated_preview = subprocess.run(
        preview.args,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    assert repeated_preview.returncode == 0, repeated_preview.stderr
    repeated = subprocess.run(
        [
            *common,
            "activation-confirm",
            str(catalog),
            designation,
            str(workspace),
            "--expected-sha256",
            _activation_digest(repeated_preview.stdout),
            "--actor",
            "trusted-local-agent-test",
            "--source-ref",
            "owner-message:recover-existing-activation",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    assert repeated.returncode == 0, repeated.stderr
    repeated_status = inspect_process_creation(catalog, designation)
    assert repeated_status.process_id == status.process_id
    assert repeated_status.first_work_id == status.first_work_id


def test_agent_activation_preserves_selected_initialized_empty_workspace(
    tmp_path: Path,
) -> None:
    catalog, _default_workspace, _request, _definition = _research_and_proposal(tmp_path, "small")
    designation = "Fictional small creation"
    workspace = tmp_path / "selected-empty-workspace"
    workspace.mkdir()
    initialized = init_workspace(workspace)
    before = {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
    common = [sys.executable, "-I", "-m", "zaratustra.trusted_chat.agent"]
    preview = subprocess.run(
        [*common, "activation-preview", str(catalog), designation, str(workspace)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    assert preview.returncode == 0, preview.stderr
    assert f"Target workspace identity: {initialized.workspace_id}" in preview.stdout
    assert {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()} == before

    confirmed = subprocess.run(
        [
            *common,
            "activation-confirm",
            str(catalog),
            designation,
            str(workspace),
            "--expected-sha256",
            _activation_digest(preview.stdout),
            "--actor",
            "trusted-local-agent-test",
            "--source-ref",
            "owner-message:create-in-selected-workspace",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    assert confirmed.returncode == 0, confirmed.stderr
    assert read_workspace(workspace).workspace_id == initialized.workspace_id


def test_agent_activation_fresh_preview_resumes_retained_partial_plan(tmp_path: Path) -> None:
    catalog, workspace, _request, _definition = _research_and_proposal(tmp_path, "small")
    designation = "Fictional small creation"
    prepared = prepare_process_activation(catalog, designation, workspace)
    first = prepared.pending[0]
    caller = authorize_local(
        prepare_authorization(workspace, first),
        channel="local-chat",
        actor="trusted-local-agent-test",
        source_ref="owner-message:interrupted-after-first-operation",
    )
    apply_mutation(workspace, first, caller)
    partial = inspect_process_creation(catalog, designation)
    assert partial.stage == "activation_pending"
    assert partial.completed_operations == ("authorize_work",)

    common = [sys.executable, "-I", "-m", "zaratustra.trusted_chat.agent"]
    preview = subprocess.run(
        [*common, "activation-preview", str(catalog), designation, str(workspace)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    assert preview.returncode == 0, preview.stderr
    assert "Target state: activated_workspace" in preview.stdout
    resumed = subprocess.run(
        [
            *common,
            "activation-confirm",
            str(catalog),
            designation,
            str(workspace),
            "--expected-sha256",
            _activation_digest(preview.stdout),
            "--actor",
            "trusted-local-agent-test",
            "--source-ref",
            "owner-message:resume-same-activation",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    assert resumed.returncode == 0, resumed.stderr
    complete = inspect_process_creation(catalog, designation)
    assert complete.stage == "activated"
    assert complete.process_id == partial.process_id
    assert complete.first_work_id == partial.first_work_id


def test_agent_preview_refuses_replaced_early_reserved_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, workspace, _request, _definition = _research_and_proposal(tmp_path, "small")
    designation = "Fictional small creation"

    def interrupted_migrate(_workspace: Path, *, target_version: int) -> None:
        assert target_version == 9
        raise OSError("synthetic interruption before activation plan")

    with monkeypatch.context() as context:
        context.setattr(creation_module, "migrate_workspace", interrupted_migrate)
        with pytest.raises(OSError, match="synthetic interruption"):
            prepare_process_activation(catalog, designation, workspace)
    reserved = inspect_process_creation(catalog, designation)
    assert reserved.activation_target is not None
    assert reserved.activation_target.workspace_path == workspace.resolve().as_posix()
    assert reserved.bootstrap_workspace_id == read_workspace(workspace).workspace_id
    shutil.rmtree(workspace)
    workspace.mkdir()
    replacement = init_workspace(workspace)
    before = {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
    assert replacement.workspace_id != reserved.bootstrap_workspace_id
    with pytest.raises(ProcessCreationError, match="workspace identity changed"):
        preview_process_activation(catalog, designation, workspace)
    with pytest.raises(ProcessCreationError, match="workspace identity changed"):
        prepare_process_activation(catalog, designation, workspace)
    assert {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()} == before
