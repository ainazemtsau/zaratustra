"""Reproduce T3 safe future-edition change with explicit fictional fixtures."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from tests.fixtures.process_creation import (
    creation_draft,
    creation_research,
    linked_creation_definition,
    project_request_data,
    small_result_data,
)
from zaratustra.core import (
    Artifact,
    ArtifactReference,
    ContextQuery,
    Handoff,
    LocalAuthorization,
    MutationRequest,
    Process,
    Work,
    apply_mutation,
    authorize_local,
    handoff_request,
    prepare_authorization,
    read_artifact,
    read_handoffs,
    read_history,
    read_records,
    read_workspace,
)
from zaratustra.process_change import (
    ReviewedProcessChange,
    authorize_process_change,
    decide_process_change,
    execute_process_change_continuation,
    prepare_process_change,
    prepare_process_change_continuation,
    process_change_continuation_query,
    process_change_preview_bytes,
    review_process_change,
)
from zaratustra.process_creation import (
    authorize_process_activation,
    create_research_request,
    execute_process_activation,
    prepare_process_activation,
    receive_research_return,
    save_creation_draft,
    save_research_request,
    save_supported_proposal,
)
from zaratustra.process_packs import (
    NodeDefinition,
    ProcessDefinition,
    ProcessSnapshot,
    definition_sha256,
    record_result,
    snapshot_bytes,
)

from .retain_trial import retain_trial

ROOT = Path(__file__).resolve().parents[1]
Case = Literal["small", "project"]


def _save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _confirm(path: Path, value: MutationRequest | ContextQuery, case: Case) -> LocalAuthorization:
    return authorize_local(
        prepare_authorization(path, value),
        channel="local-chat",
        actor="fictional-process-t3-probe",
        source_ref=(
            f"T3 {case} technical fixture confirmation; simulated local chat, "
            "not real owner acceptance"
        ),
    )


def _work(path: Path, identity: UUID) -> Work:
    return next(
        row for row in read_records(path).records if isinstance(row, Work) and row.id == identity
    )


def _artifact(path: Path, work_id: UUID) -> Artifact:
    return next(
        row
        for row in read_records(path).records
        if isinstance(row, Artifact) and row.work_id == work_id
    )


def _process(path: Path) -> Process:
    return next(row for row in read_records(path).records if isinstance(row, Process))


def _changed(definition: ProcessDefinition, case: Case) -> ProcessDefinition:
    if case == "small":
        node = definition.nodes[0]
        added = NodeDefinition(
            node_id="review",
            goal="Review the fictional amber brief before recurrence",
            expected_result="One exact fictional review",
            acceptance=("review is present",),
            boundaries=node.boundaries,
            budget="One technical review",
            artifact_title="Amber review snapshot",
            output_keys=("review",),
            reasons=node.reasons,
        )
        nodes = (*definition.nodes, added)
    else:
        reviewed = definition.nodes[1].model_copy(
            update=dict(
                goal="Read and retain the reviewed fictional research note",
                expected_result="The exact reviewed research limit fact",
                acceptance=("research_fact is present after explicit review",),
            )
        )
        nodes = (definition.nodes[0], reviewed, definition.nodes[2])
    return ProcessDefinition.model_validate(definition.model_dump() | dict(edition=2, nodes=nodes))


def _review(
    catalog: Path,
    workspace: Path,
    designation: str,
    definition: ProcessDefinition,
    case: Case,
) -> ReviewedProcessChange:
    prepared = prepare_process_change(
        catalog, designation, definition.model_dump_json().encode("utf-8")
    )
    return review_process_change(prepared, _confirm(workspace, prepared.query, case))


def _accept_result(
    workspace: Path,
    work: Work,
    definition: ProcessDefinition,
    case: Case,
) -> tuple[bytes, UUID]:
    data = small_result_data() if case == "small" else project_request_data()
    content = snapshot_bytes(record_result(ProcessSnapshot(definition=definition), data))
    artifact = _artifact(workspace, work.id)
    state = read_records(workspace)
    publication = MutationRequest(
        version=2,
        operation="publish_artifact",
        operation_id=uuid4(),
        workspace_id=state.workspace_id,
        work_id=work.id,
        expected_revision=state.state_revision,
        provenance=f"T3 {case} exact fictional current Result snapshot",
        artifact_id=artifact.id,
        artifact_revision=artifact.revision,
        content_sha256=hashlib.sha256(content).hexdigest(),
        content_size=len(content),
    )
    apply_mutation(workspace, publication, _confirm(workspace, publication, case), content=content)
    state = read_records(workspace)
    handoff = Handoff(
        kind="handoff",
        version=1,
        handoff_id=uuid4(),
        workspace_id=state.workspace_id,
        process=work.process_id,
        related_work=work.id,
        intent="accepted_result",
        source_revision=state.state_revision,
        result=ArtifactReference(
            artifact_id=artifact.id,
            version_id=publication.operation_id,
            sha256=hashlib.sha256(content).hexdigest(),
        ),
        provenance=f"Accepted fictional T3 {case} Result; technical fixture only",
        created_by="fictional-process-t3-probe",
    )
    acceptance = handoff_request(
        handoff.model_dump_json().encode("utf-8"), source_ref=f"process-t3-probe:{case}"
    )
    apply_mutation(workspace, acceptance, _confirm(workspace, acceptance, case))
    return content, publication.operation_id


def run(output: Path, case: Case) -> dict[str, Any]:
    output.mkdir()
    catalog = output / "catalog.json"
    workspace = output / "workspace"
    designation = f"T3 synthetic {case} process"
    request_file = output / "manual-research-request.json"
    save_creation_draft(catalog, designation, creation_draft(case))
    request = create_research_request(catalog, designation)
    save_research_request(request_file, request)
    research_bytes = creation_research(case)
    research = receive_research_return(
        catalog,
        designation,
        request_file.read_bytes(),
        research_bytes,
        created_by=f"synthetic-{case}-research-fixture",
        source_ref=f"tests/fixtures/process_creation:{case}:research",
    )
    definition = linked_creation_definition(
        case,
        hashlib.sha256(request_file.read_bytes()).hexdigest(),
        research.content_sha256,
    )
    changed = _changed(definition, case)
    (output / "definition-before.json").write_bytes(definition.model_dump_json(indent=2).encode())
    (output / "definition-after.json").write_bytes(changed.model_dump_json(indent=2).encode())
    save_supported_proposal(catalog, designation, definition.model_dump_json().encode())
    activation = prepare_process_activation(catalog, designation, workspace)
    activation_auth = authorize_process_activation(
        activation,
        channel="local-chat",
        actor="fictional-process-t3-probe",
        source_ref=f"T3 {case} synthetic activation; not owner acceptance",
    )
    activated = execute_process_activation(activation, activation_auth)
    assert activated.creation.first_work_id is not None
    first_work = _work(workspace, activated.creation.first_work_id)
    process = _process(workspace)
    assert process.pack_binding is not None
    initial_artifact = _artifact(workspace, first_work.id)
    initial_version = initial_artifact.active_version
    assert initial_version is not None
    initial_bytes = read_artifact(workspace, initial_artifact.id, initial_version).content
    pack_bytes = process.pack_binding.model_dump_json().encode("utf-8")
    (output / "pack-reference-before.json").write_bytes(pack_bytes)
    (output / "initial-snapshot-before.json").write_bytes(initial_bytes)
    before_review = retain_trial(workspace, output / "before-review.zip")
    database_before_review = read_workspace(workspace).database.read_bytes()

    rejected_review = _review(catalog, workspace, designation, changed, case)
    rejected_decision = authorize_process_change(
        rejected_review,
        decision="reject",
        channel="local-chat",
        actor="fictional-process-t3-probe",
        source_ref=f"T3 {case} explicit synthetic rejection; not owner acceptance",
    )
    rejected = decide_process_change(rejected_review, rejected_decision)
    assert rejected.stage == "rejected"
    assert read_workspace(workspace).database.read_bytes() == database_before_review

    review = _review(catalog, workspace, designation, changed, case)
    preview = process_change_preview_bytes(review)
    (output / "change-preview.json").write_bytes(preview)
    decision = authorize_process_change(
        review,
        decision="approve",
        channel="local-chat",
        actor="fictional-process-t3-probe",
        source_ref=f"T3 {case} explicit synthetic approval; not owner acceptance",
    )
    pending = decide_process_change(review, decision)
    assert pending.stage == "pending" and pending.intent_is_core_effect is False
    assert read_workspace(workspace).database.read_bytes() == database_before_review
    _save(output / "pending-status.json", pending.model_dump(mode="json"))

    accepted_bytes, result_version = _accept_result(workspace, first_work, definition, case)
    (output / "accepted-edition-1-result.json").write_bytes(accepted_bytes)
    query = process_change_continuation_query(catalog, designation)
    planned = prepare_process_change_continuation(
        catalog, designation, _confirm(workspace, query, case)
    )
    _save(output / "planned-result-request.json", planned.request.model_dump(mode="json"))
    before_effect = read_records(workspace)
    history_before = read_history(workspace)
    handoffs_before = read_handoffs(workspace)
    before_effect_manifest = retain_trial(workspace, output / "before-effect.zip")
    result = execute_process_change_continuation(
        planned, _confirm(workspace, planned.request, case)
    )
    after = read_records(workspace)
    history_after = read_history(workspace)
    next_work = _work(workspace, result.change.current_work_id)
    source = _work(workspace, first_work.id)
    final_process = _process(workspace)
    assert source.status == "done" and next_work.status == "ready"
    assert final_process.pack_binding == process.pack_binding == next_work.pack_binding
    assert final_process.pack_binding is not None
    assert final_process.pack_binding.model_dump_json().encode("utf-8") == pack_bytes
    assert read_artifact(workspace, initial_artifact.id, initial_version).content == initial_bytes
    assert read_artifact(workspace, initial_artifact.id, result_version).content == accepted_bytes
    assert read_handoffs(workspace)[: len(handoffs_before)] == handoffs_before
    revision_after = after.state_revision
    replay = execute_process_change_continuation(
        planned, _confirm(workspace, planned.request, case)
    )
    restarted = prepare_process_change_continuation(catalog, designation, None)
    assert replay.receipt == result.receipt and restarted.request == planned.request
    assert read_records(workspace).state_revision == revision_after
    after_effect_manifest = retain_trial(workspace, output / "after-effect.zip")
    (output / "pack-reference-after.json").write_bytes(
        final_process.pack_binding.model_dump_json().encode("utf-8")
    )
    _save(output / "result-receipt.json", result.receipt.model_dump(mode="json"))
    _save(output / "applied-status.json", result.change.model_dump(mode="json"))
    summary = dict(
        case=case,
        source_commit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, encoding="utf-8"
        ).strip(),
        product_version="0.15.0",
        provider_contacted=False,
        simulated_confirmation_not_owner_acceptance=True,
        rejected_without_core_change=True,
        approval_stage=pending.stage,
        approval_is_core_effect=pending.intent_is_core_effect,
        preview_sha256=hashlib.sha256(preview).hexdigest(),
        from_definition_sha256=definition_sha256(definition),
        to_definition_sha256=definition_sha256(changed),
        initial_snapshot_sha256=hashlib.sha256(initial_bytes).hexdigest(),
        accepted_edition_1_result_sha256=hashlib.sha256(accepted_bytes).hexdigest(),
        pack_reference_sha256=hashlib.sha256(pack_bytes).hexdigest(),
        pack_reference_bytes_preserved=True,
        workspace_id=str(after.workspace_id),
        process_id=str(final_process.id),
        source_work_id=str(first_work.id),
        future_work_id=str(next_work.id),
        future_work_goal=next_work.goal,
        future_definition_requirement=(f"definition-sha256:{definition_sha256(changed)}"),
        before_effect_revision=before_effect.state_revision,
        applied_revision=result.receipt.new_revision,
        replay_revision=revision_after,
        result_operation_id=str(result.receipt.operation_id),
        event_id=str(result.receipt.event_id),
        history_events_before=len(history_before.events),
        history_events_after=len(history_after.events),
        rejected_changes=result.change.rejected_changes,
        stage=result.change.stage,
        restart_same_request=True,
        replay_same_receipt=True,
        before_review_manifest=before_review,
        before_effect_manifest=before_effect_manifest,
        after_effect_manifest=after_effect_manifest,
    )
    _save(output / "summary.json", summary)
    return summary


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=("small", "project"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    for name in ("STOP", "STEER.md"):
        if (ROOT / name).exists():
            parser.error(f"Read and resolve {name} before running")
    output = args.output.resolve()
    scratch = (ROOT / "_scratch").resolve()
    if output == scratch or not output.is_relative_to(scratch) or output.exists():
        parser.error("Choose a NEW directory inside this worktree's ignored _scratch")
    summary = run(output, args.case)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
