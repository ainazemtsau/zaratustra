"""User-like prose, fresh continuation and explicit later Work evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

import zaratustra.cli as cli_module
from tests.fixtures.process_creation import (
    creation_research,
    project_definition,
    small_definition,
)
from zaratustra.core import (
    AuthorizationPrompt,
    LocalAuthorization,
    MutationRequest,
    ProcessMaterialRequest,
    ProcessMaterialSubmission,
    apply_mutation,
    authorize_local,
    prepare_authorization,
    read_records,
    save_process_material,
)
from zaratustra.onboarding import (
    LaterWorkInput,
    OnboardingError,
    ProseClarification,
    creation_status_text,
    execute_later_work,
    onboarding_status_text,
    prepare_later_work,
    prepare_onboarding_read,
    read_onboarding,
    save_prose_creation_draft,
)
from zaratustra.process_creation import (
    ActivationReceipt,
    authorize_process_activation,
    create_research_request,
    execute_process_activation,
    prepare_process_activation,
    receive_research_return,
    save_research_request,
    save_supported_proposal,
)
from zaratustra.process_packs import (
    SUPPORTED_CAPABILITIES,
    ProcessDefinition,
    Reason,
    SourceReference,
)


def _confirm(path: Path, request: Any) -> LocalAuthorization:
    prompt = prepare_authorization(path, request)
    return authorize_local(
        prompt,
        channel="local-chat",
        actor="public-onboarding-r2-t3-test",
        source_ref="fictional-user-like-test",
    )


def _linked_definition(case: str, request_sha256: str, research_sha256: str) -> ProcessDefinition:
    base = small_definition() if case == "simple" else project_definition()
    capabilities = tuple(sorted(SUPPORTED_CAPABILITIES))
    sources = (
        SourceReference(
            source_id="saved-request",
            kind="request",
            locator=f"creation-request-sha256:{request_sha256}",
        ),
        SourceReference(
            source_id="saved-research",
            kind="research",
            locator=f"research-return-sha256:{research_sha256}",
        ),
        *(
            SourceReference(
                source_id=f"capability-{index}",
                kind="capability",
                locator=f"capability:{capability}",
            )
            for index, capability in enumerate(capabilities, start=1)
        ),
    )
    source_ids = tuple(row.source_id for row in sources)
    nodes = tuple(
        node.model_copy(
            update={"reasons": (Reason(text=node.reasons[0].text, source_ids=source_ids),)}
        )
        for node in base.nodes
    )
    return base.model_copy(
        update={"required_capabilities": capabilities, "sources": sources, "nodes": nodes}
    )


def _activate(root: Path, case: str) -> tuple[Path, Path, ProcessDefinition, ActivationReceipt]:
    catalog = root / "catalog.json"
    workspace = root / "workspace"
    designation = f"Fictional {case} prose"
    outcomes = (
        ("Keep one exact fictional note.",)
        if case == "simple"
        else (
            "Retain the fictional request fact.",
            "Retain the separate fictional research fact.",
            "Combine them only after both are present.",
        )
    )
    status = save_prose_creation_draft(
        catalog,
        designation,
        process_title=f"Readable {case} Process",
        need=f"Handle the {case} fictional need from ordinary prose.",
        desired_outcomes=outcomes,
        constraints=("Fictional local evidence only.", "No provider automation."),
        clarifications=(
            ProseClarification(
                question="Is the fictional scope exact?",
                why_needed="The proposal must not widen it.",
                answer="Yes, keep exactly the stated fictional scope.",
            ),
        ),
        created_by="fictional-owner",
    )
    assert status.draft.declared_capabilities == tuple(sorted(SUPPORTED_CAPABILITIES))
    request = create_research_request(catalog, designation)
    request_path = root / "research-request.json"
    save_research_request(request_path, request)
    request_bytes = request_path.read_bytes()
    research = creation_research("small" if case == "simple" else "project")
    receive_research_return(
        catalog,
        designation,
        request_bytes,
        research,
        created_by="fictional-manual-research",
        source_ref=f"fixture:{case}:manual-return",
    )
    definition = _linked_definition(
        case,
        hashlib.sha256(request_bytes).hexdigest(),
        hashlib.sha256(research).hexdigest(),
    )
    save_supported_proposal(catalog, designation, definition.model_dump_json().encode())
    prepared = prepare_process_activation(catalog, designation, workspace)
    receipt = execute_process_activation(
        prepared,
        authorize_process_activation(
            prepared,
            channel="local-chat",
            actor="fictional-owner",
            source_ref="exact-fictional-activation",
        ),
    )
    return catalog, workspace, definition, receipt


@pytest.mark.parametrize("case", ["simple", "complex"])
def test_ordinary_prose_is_readable_and_activates_without_user_json(
    tmp_path: Path, case: str
) -> None:
    catalog, workspace, _definition, receipt = _activate(tmp_path, case)
    designation = f"Fictional {case} prose"
    creation = receipt.creation
    rendered = creation_status_text(creation)
    assert f"Need:\nHandle the {case} fictional need from ordinary prose." in rendered
    assert "Installed construction capabilities:" in rendered
    assert rendered.count("- Retain") == (0 if case == "simple" else 2)

    prepared = prepare_onboarding_read(catalog, designation)
    assert prepared.process_read is not None
    with pytest.raises(Exception, match="permission_denied"):
        read_onboarding(prepared)
    resumed = read_onboarding(prepared, _confirm(workspace, prepared.process_read.query))
    assert resumed.stage == "current_work"
    assert resumed.process is not None
    assert resumed.process.current_work is not None
    assert str(resumed.process.current_work.id) in onboarding_status_text(resumed)


def test_unfinished_prose_stage_resumes_without_core_or_provider_call(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    status = save_prose_creation_draft(
        catalog,
        "Unfinished fictional prose",
        process_title="Unfinished fictional Process",
        need="Retain a draft until its manual research request is explicit.",
        desired_outcomes=("One readable saved draft.",),
        constraints=("No provider call.",),
        created_by="fictional-owner",
    )
    prepared = prepare_onboarding_read(catalog, "Unfinished fictional prose")
    assert prepared.process_read is None
    resumed = read_onboarding(prepared)
    assert resumed.stage == "draft" and resumed.creation == status
    assert "create the manual research request" in resumed.next_action


def test_cli_prose_and_fresh_resume_need_no_user_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    catalog = tmp_path / "catalog.json"
    designation = "CLI readable fictional need"
    assert (
        cli_module.main(
            [
                "entry",
                "create",
                "prose",
                str(catalog),
                designation,
                "Keep one fictional note from ordinary prose.",
                "--title",
                "CLI fictional Process",
                "--outcome",
                "One exact fictional note.",
                "--constraint",
                "No provider automation.",
                "--created-by",
                "fictional-owner",
            ]
        )
        == 0
    )
    shown = capsys.readouterr().out
    assert "Need:\nKeep one fictional note from ordinary prose." in shown
    assert "Stage: draft" in shown
    assert cli_module.main(["entry", "resume", str(catalog), designation]) == 0
    assert "Next: Answer saved clarifications" in capsys.readouterr().out


def test_cli_later_work_recovers_the_same_exact_operation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    catalog, workspace, definition, receipt = _activate(tmp_path, "simple")
    snapshot = read_records(workspace)
    assert receipt.creation.first_work_id is not None
    cancel = MutationRequest(
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        work_id=receipt.creation.first_work_id,
        expected_revision=snapshot.state_revision,
        operation="cancel_work",
        provenance="CLI fictional terminal Work",
    )
    apply_mutation(workspace, cancel, _confirm(workspace, cancel))
    definition_path = tmp_path / "definition.json"
    definition_path.write_text(definition.model_dump_json(indent=2), encoding="utf-8")

    def confirmed(prompt: AuthorizationPrompt) -> LocalAuthorization:
        return authorize_local(
            prompt,
            channel="local-chat",
            actor="fictional-cli-owner",
            source_ref="exact-cli-confirmation",
        )

    monkeypatch.setattr(cli_module, "confirm_on_console", confirmed)
    command = [
        "entry",
        "later-work",
        str(catalog),
        "Fictional simple prose",
        str(definition_path),
        "--goal",
        "Review one fictional observation.",
        "--expected-result",
        "One fictional review note.",
        "--acceptance",
        "The note is present.",
        "--boundary",
        "Fictional local evidence only.",
        "--budget",
        "One bounded review.",
        "--artifact-title",
        "Fictional CLI later review",
    ]
    assert cli_module.main(command) == 0
    first = capsys.readouterr().out
    revision = read_records(workspace).state_revision
    assert cli_module.main(command) == 0
    second = capsys.readouterr().out
    assert first == second
    assert read_records(workspace).state_revision == revision


def test_material_terminal_truth_and_exact_later_work_recover_across_fresh_reads(
    tmp_path: Path,
) -> None:
    catalog, workspace, definition, receipt = _activate(tmp_path, "simple")
    designation = "Fictional simple prose"
    snapshot = read_records(workspace)
    assert receipt.creation.first_work_id is not None and receipt.creation.process_id is not None
    cancel = MutationRequest(
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        work_id=receipt.creation.first_work_id,
        expected_revision=snapshot.state_revision,
        operation="cancel_work",
        provenance="Exact fictional terminal/no-current setup",
    )
    apply_mutation(workspace, cancel, _confirm(workspace, cancel))
    snapshot = read_records(workspace)
    content = b"Fictional Process-owned observation after terminal Work.\n"
    material = ProcessMaterialRequest(
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        process_id=receipt.creation.process_id,
        expected_revision=snapshot.state_revision,
        provenance="Exact fictional Process material",
        material=ProcessMaterialSubmission(
            material_id=uuid4(),
            title="Fictional retained observation",
            media_type="text/plain; charset=utf-8",
            content_sha256=hashlib.sha256(content).hexdigest(),
            content_size=len(content),
        ),
    )
    save_process_material(workspace, material, _confirm(workspace, material), content=content)

    fresh = prepare_onboarding_read(catalog, designation)
    assert fresh.process_read is not None
    no_current = read_onboarding(fresh, _confirm(workspace, fresh.process_read.query))
    assert no_current.stage == "no_current_work"
    assert no_current.process is not None and len(no_current.process.materials) == 1
    assert "Fictional retained observation" in onboarding_status_text(no_current)
    later_input = LaterWorkInput(
        goal="Review the exact fictional retained observation.",
        expected_result="One fictional review note.",
        acceptance=("The fictional note is present.",),
        boundaries=("Fictional local evidence only.",),
        budget="One bounded fictional review.",
        artifact_title="Fictional later review",
    )
    wrong_definition = definition.model_copy(update={"title": "Different fictional runtime"})
    with pytest.raises(OnboardingError, match="binding_mismatch"):
        prepare_later_work(
            catalog,
            designation,
            no_current,
            wrong_definition.model_dump_json().encode(),
            later_input,
        )
    later = prepare_later_work(
        catalog,
        designation,
        no_current,
        definition.model_dump_json().encode(),
        later_input,
    )
    with pytest.raises(OnboardingError, match="permission_denied"):
        execute_later_work(later, None)
    committed = execute_later_work(later, _confirm(workspace, later.request))

    restarted = prepare_onboarding_read(catalog, designation)
    assert restarted.process_read is not None
    current = read_onboarding(restarted, _confirm(workspace, restarted.process_read.query))
    assert current.stage == "current_work"
    assert current.process is not None and current.process.current_work is not None
    assert current.process.current_work.id == later.request.work.work_id
    recovered = prepare_later_work(
        catalog,
        designation,
        current,
        definition.model_dump_json().encode(),
        later_input,
    )
    replay = execute_later_work(recovered, _confirm(workspace, recovered.request))
    assert replay == committed
    changed = later_input.model_copy(update={"goal": "Different fictional intent."})
    with pytest.raises(OnboardingError, match="later_work_collision"):
        prepare_later_work(
            catalog,
            designation,
            current,
            definition.model_dump_json().encode(),
            changed,
        )


def test_uncommitted_later_work_plan_never_rebases_over_process_material(
    tmp_path: Path,
) -> None:
    catalog, workspace, definition, receipt = _activate(tmp_path, "simple")
    designation = "Fictional simple prose"
    snapshot = read_records(workspace)
    assert receipt.creation.first_work_id is not None and receipt.creation.process_id is not None
    cancel = MutationRequest(
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        work_id=receipt.creation.first_work_id,
        expected_revision=snapshot.state_revision,
        operation="cancel_work",
        provenance="Fictional stale later-Work setup",
    )
    apply_mutation(workspace, cancel, _confirm(workspace, cancel))
    fresh = prepare_onboarding_read(catalog, designation)
    assert fresh.process_read is not None
    no_current = read_onboarding(fresh, _confirm(workspace, fresh.process_read.query))
    later_input = LaterWorkInput(
        goal="Keep one explicit stale fictional intent.",
        expected_result="One fictional result.",
        acceptance=("The fictional result is present.",),
        boundaries=("Fictional local evidence only.",),
        budget="One bounded attempt.",
        artifact_title="Fictional stale later Work",
    )
    prepare_later_work(
        catalog,
        designation,
        no_current,
        definition.model_dump_json().encode(),
        later_input,
    )
    snapshot = read_records(workspace)
    content = b"Intervening exact fictional material.\n"
    material = ProcessMaterialRequest(
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        process_id=receipt.creation.process_id,
        expected_revision=snapshot.state_revision,
        provenance="Intervening fictional Process material",
        material=ProcessMaterialSubmission(
            material_id=uuid4(),
            title="Intervening fictional material",
            media_type="text/plain; charset=utf-8",
            content_sha256=hashlib.sha256(content).hexdigest(),
            content_size=len(content),
        ),
    )
    save_process_material(workspace, material, _confirm(workspace, material), content=content)
    restarted = prepare_onboarding_read(catalog, designation)
    assert restarted.process_read is not None
    changed_state = read_onboarding(restarted, _confirm(workspace, restarted.process_read.query))
    with pytest.raises(OnboardingError, match="stale_state"):
        prepare_later_work(
            catalog,
            designation,
            changed_state,
            definition.model_dump_json().encode(),
            later_input,
        )
