"""Reproduce the R2 T3 public prose, continuation, later-Work and change path."""

from __future__ import annotations

import hashlib
import json
import subprocess
from importlib.metadata import version
from pathlib import Path
from typing import Any
from uuid import uuid4

from tests.fixtures.process_creation import creation_research, project_definition, small_definition
from zaratustra.core import (
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

from .probe_process_t3 import run as run_safe_change

ROOT = Path(__file__).resolve().parents[1]


def _confirm(path: Path, value: Any) -> LocalAuthorization:
    return authorize_local(
        prepare_authorization(path, value),
        channel="local-chat",
        actor="fictional-public-onboarding-r2-t3-probe",
        source_ref="synthetic exact confirmation; not owner acceptance",
    )


def _definition(case: str, request_digest: str, research_digest: str) -> ProcessDefinition:
    base = small_definition() if case == "simple" else project_definition()
    capabilities = tuple(sorted(SUPPORTED_CAPABILITIES))
    sources = (
        SourceReference(
            source_id="saved-request",
            kind="request",
            locator=f"creation-request-sha256:{request_digest}",
        ),
        SourceReference(
            source_id="saved-research",
            kind="research",
            locator=f"research-return-sha256:{research_digest}",
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


def _activate(output: Path, case: str) -> dict[str, Any]:
    case_root = output / case
    case_root.mkdir(parents=True)
    catalog = case_root / "catalog.json"
    workspace = case_root / "workspace"
    designation = f"R2 T3 fictional {case} prose"
    outcomes = (
        ("Keep one exact fictional note.",)
        if case == "simple"
        else (
            "Retain the fictional request fact.",
            "Retain the separate fictional research fact.",
            "Combine only after both are present.",
        )
    )
    draft = save_prose_creation_draft(
        catalog,
        designation,
        process_title=f"R2 T3 readable {case} Process",
        need=f"Handle the {case} fictional need from ordinary prose.",
        desired_outcomes=outcomes,
        constraints=("Fictional local evidence only.", "No provider automation."),
        clarifications=(
            ProseClarification(
                question="Is this scope exact?",
                why_needed="The proposal must not widen it.",
                answer="Yes, retain exactly this fictional scope.",
            ),
        ),
        created_by="fictional-probe-owner",
    )
    (case_root / "readable-draft.txt").write_text(creation_status_text(draft), encoding="utf-8")
    request = create_research_request(catalog, designation)
    request_path = case_root / "manual-research-request.json"
    save_research_request(request_path, request)
    (case_root / "copyable-manual-research.txt").write_text(
        request.copyable_request + "\n", encoding="utf-8"
    )
    request_bytes = request_path.read_bytes()
    research = creation_research("small" if case == "simple" else "project")
    receive_research_return(
        catalog,
        designation,
        request_bytes,
        research,
        created_by="fictional-manual-research",
        source_ref=f"fixture:r2-t3:{case}:manual-return",
    )
    definition = _definition(
        case,
        hashlib.sha256(request_bytes).hexdigest(),
        hashlib.sha256(research).hexdigest(),
    )
    definition_path = case_root / "assistant-authored-definition.json"
    definition_path.write_text(definition.model_dump_json(indent=2), encoding="utf-8")
    save_supported_proposal(catalog, designation, definition_path.read_bytes())
    prepared = prepare_process_activation(catalog, designation, workspace)
    activated = execute_process_activation(
        prepared,
        authorize_process_activation(
            prepared,
            channel="local-chat",
            actor="fictional-probe-owner",
            source_ref="synthetic exact activation; not owner acceptance",
        ),
    )
    fresh = prepare_onboarding_read(catalog, designation)
    assert fresh.process_read is not None
    resumed = read_onboarding(fresh, _confirm(workspace, fresh.process_read.query))
    (case_root / "fresh-current.txt").write_text(onboarding_status_text(resumed), encoding="utf-8")
    assert resumed.process is not None and resumed.process.current_work is not None
    return {
        "catalog": catalog,
        "workspace": workspace,
        "designation": designation,
        "definition": definition,
        "process_id": activated.creation.process_id,
        "first_work_id": resumed.process.current_work.id,
        "draft_sha256": draft.draft_sha256,
        "research_request_id": request.request_id,
        "stage": resumed.stage,
    }


def run(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True)
    simple = _activate(output, "simple")
    complex_case = _activate(output, "complex")
    workspace: Path = simple["workspace"]
    catalog: Path = simple["catalog"]
    designation: str = simple["designation"]
    definition: ProcessDefinition = simple["definition"]
    snapshot = read_records(workspace)
    cancel = MutationRequest(
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        work_id=simple["first_work_id"],
        expected_revision=snapshot.state_revision,
        operation="cancel_work",
        provenance="R2 T3 fictional terminal/no-current probe",
    )
    apply_mutation(workspace, cancel, _confirm(workspace, cancel))
    snapshot = read_records(workspace)
    material_bytes = b"Fictional retained Process material after terminal Work.\n"
    material = ProcessMaterialRequest(
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        process_id=simple["process_id"],
        expected_revision=snapshot.state_revision,
        provenance="R2 T3 fictional Process material",
        material=ProcessMaterialSubmission(
            material_id=uuid4(),
            title="Fictional retained Process observation",
            media_type="text/plain; charset=utf-8",
            content_sha256=hashlib.sha256(material_bytes).hexdigest(),
            content_size=len(material_bytes),
        ),
    )
    save_process_material(
        workspace, material, _confirm(workspace, material), content=material_bytes
    )
    fresh = prepare_onboarding_read(catalog, designation)
    assert fresh.process_read is not None
    no_current = read_onboarding(fresh, _confirm(workspace, fresh.process_read.query))
    (output / "simple" / "fresh-no-current.txt").write_text(
        onboarding_status_text(no_current), encoding="utf-8"
    )
    later_input = LaterWorkInput(
        goal="Review the exact fictional retained Process observation.",
        expected_result="One fictional later review.",
        acceptance=("The fictional later review is present.",),
        boundaries=("Fictional local evidence only.",),
        budget="One bounded fictional review.",
        artifact_title="Fictional explicit later Work",
    )
    later = prepare_later_work(
        catalog,
        designation,
        no_current,
        definition.model_dump_json().encode(),
        later_input,
    )
    committed = execute_later_work(later, _confirm(workspace, later.request))
    restarted = prepare_onboarding_read(catalog, designation)
    assert restarted.process_read is not None
    current = read_onboarding(restarted, _confirm(workspace, restarted.process_read.query))
    recovered = prepare_later_work(
        catalog,
        designation,
        current,
        definition.model_dump_json().encode(),
        later_input,
    )
    replay = execute_later_work(recovered, _confirm(workspace, recovered.request))
    safe_change = run_safe_change(output / "safe-change", "project")
    summary = {
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, encoding="utf-8"
        ).strip(),
        "product_version": version("zaratustra"),
        "provider_contacted": False,
        "user_json_required": False,
        "simple_stage": simple["stage"],
        "complex_stage": complex_case["stage"],
        "complex_outcomes": 3,
        "manual_research_persisted": True,
        "process_materials_after_terminal": len(no_current.process.materials)
        if no_current.process is not None
        else 0,
        "terminal_resume_stage": no_current.stage,
        "later_work_id": str(later.request.work.work_id),
        "later_work_replay_same_receipt": replay == committed,
        "fresh_later_stage": current.stage,
        "safe_change_stage": safe_change["stage"],
        "safe_change_replay_same_receipt": safe_change["replay_same_receipt"],
        "simulated_confirmation_not_owner_acceptance": True,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    for name in ("STOP", "STEER.md"):
        if (ROOT / name).exists():
            parser.error(f"Read and resolve {name} before running")
    output = args.output.resolve()
    scratch = (ROOT / "_scratch").resolve()
    if output == scratch or not output.is_relative_to(scratch) or output.exists():
        parser.error("Choose a NEW directory inside this worktree's ignored _scratch")
    print(json.dumps(run(output), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
