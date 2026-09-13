"""Reproduce one synthetic T2 creation through the installed public product path."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Literal

from tests.fixtures.process_creation import (
    creation_draft,
    creation_research,
    linked_creation_definition,
)
from zaratustra.core import authorize_local, prepare_authorization
from zaratustra.first_use import open_selected_context, prepare_selected_context
from zaratustra.process_creation import (
    activation_preview_bytes,
    authorize_process_activation,
    create_research_request,
    execute_process_activation,
    inspect_process_creation,
    prepare_process_activation,
    receive_research_return,
    save_creation_draft,
    save_research_request,
    save_supported_proposal,
)
from zaratustra.process_packs import ProcessSnapshot, evaluate_snapshot

ROOT = Path(__file__).resolve().parents[1]
Case = Literal["small", "project"]


def run(output: Path, case: Case) -> dict[str, Any]:
    output.mkdir()
    catalog = output / "catalog.json"
    workspace = output / "workspace"
    designation = f"T2 synthetic {case} process"
    stages = []
    stages.append(
        save_creation_draft(catalog, designation, creation_draft(case)).model_dump(mode="json")
    )
    request = create_research_request(catalog, designation)
    request_file = output / "manual-research-request.json"
    save_research_request(request_file, request)
    stages.append(inspect_process_creation(catalog, designation).model_dump(mode="json"))
    request_bytes = request_file.read_bytes()
    returned = creation_research(case)
    research = receive_research_return(
        catalog,
        designation,
        request_bytes,
        returned,
        created_by=f"synthetic-{case}-research-fixture",
        source_ref=f"tests/fixtures/process_creation:{case}:research",
    )
    stages.append(inspect_process_creation(catalog, designation).model_dump(mode="json"))
    definition = linked_creation_definition(
        case,
        hashlib.sha256(request_bytes).hexdigest(),
        research.content_sha256,
    )
    proposal = save_supported_proposal(
        catalog, designation, definition.model_dump_json().encode("utf-8")
    )
    stages.append(inspect_process_creation(catalog, designation).model_dump(mode="json"))
    prepared = prepare_process_activation(catalog, designation, workspace)
    preview = activation_preview_bytes(prepared)
    (output / "activation-preview.json").write_bytes(preview)
    activation = authorize_process_activation(
        prepared,
        channel="local-chat",
        actor="synthetic-probe-owner",
        source_ref=f"probe-process-t2:{case}:explicit-confirmation",
    )
    receipt = execute_process_activation(prepared, activation)
    stages.append(inspect_process_creation(catalog, designation).model_dump(mode="json"))

    selected = prepare_selected_context(catalog, designation, max_bytes=1_048_576)
    caller = authorize_local(
        prepare_authorization(selected.workspace, selected.query),
        channel="local-chat",
        actor="synthetic-probe-owner",
        source_ref=f"probe-process-t2:{case}:common-entry-open",
    )
    opened = open_selected_context(selected, caller).output
    (output / "opened-first-work.json").write_bytes(opened)
    initial_view = evaluate_snapshot(ProcessSnapshot(definition=definition))
    summary = dict(
        case=case,
        commit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, encoding="utf-8"
        ).strip(),
        designation=designation,
        draft_sha256=stages[0]["draft_sha256"],
        request_id=str(request.request_id),
        request_sha256=hashlib.sha256(request_bytes).hexdigest(),
        request_is_readable=(
            "Need\n" in request.copyable_request
            and "Relevant declared capabilities\n" in request.copyable_request
        ),
        provider_contacted=request.provider_contacted,
        research_sha256=research.content_sha256,
        research_status=research.status,
        research_approval=research.approval,
        definition_sha256=proposal.definition_sha256,
        selected=initial_view.selected.model_dump(mode="json")
        if initial_view.selected is not None
        else None,
        blocked=[row.model_dump(mode="json") for row in initial_view.blocked],
        activation_preview_sha256=hashlib.sha256(preview).hexdigest(),
        activation_receipts=[row.model_dump(mode="json") for row in receipt.receipts],
        final_status=receipt.creation.model_dump(mode="json"),
        opened_first_work_sha256=hashlib.sha256(opened).hexdigest(),
        stages=stages,
        fixture_notice=(
            "Synthetic technical development fixture only. A future human must run an actual "
            "manual research handoff; this probe does not fabricate one."
        ),
    )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=("small", "project"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if (ROOT / "STOP").exists() or (ROOT / "STEER.md").exists():
        parser.error("Read and resolve STOP/STEER before running")
    output = args.output.resolve()
    scratch = (ROOT / "_scratch").resolve()
    if output == scratch or not output.is_relative_to(scratch) or output.exists():
        parser.error("Choose a NEW directory inside this worktree's ignored _scratch")
    print(json.dumps(run(output, args.case), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
