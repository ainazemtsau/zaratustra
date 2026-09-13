"""Behavioral proof of one reviewed future-edition change and its refusals."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import pytest

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
    ProcessChangeError,
    ProcessChangeStatus,
    ReviewedProcessChange,
    authorize_process_change,
    decide_process_change,
    execute_process_change_continuation,
    inspect_process_change,
    prepare_process_change,
    prepare_process_change_continuation,
    process_change_continuation_query,
    process_change_preview_bytes,
    process_change_review_query,
    resume_process_change_review,
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
    DataValue,
    NodeDefinition,
    ProcessDefinition,
    ProcessSnapshot,
    definition_sha256,
    record_result,
    snapshot_bytes,
)


def _confirm(path: Path, value: MutationRequest | ContextQuery) -> LocalAuthorization:
    return authorize_local(
        prepare_authorization(path, value),
        channel="local-chat",
        actor="fictional-process-change-test-исполнитель",
        source_ref="T3 точное техническое подтверждение; not owner acceptance",
    )


def _activate(tmp_path: Path, case: str) -> tuple[Path, Path, str, ProcessDefinition, Work]:
    catalog = tmp_path / "catalog.json"
    workspace = tmp_path / "workspace"
    designation = f"T3 fictional {case}"
    save_creation_draft(catalog, designation, creation_draft(case))
    request = create_research_request(catalog, designation)
    request_file = tmp_path / "request.json"
    save_research_request(request_file, request)
    response = creation_research(case)
    returned = receive_research_return(
        catalog,
        designation,
        request_file.read_bytes(),
        response,
        created_by="fictional-research-fixture",
        source_ref=f"fixture:{case}:research",
    )
    definition = linked_creation_definition(
        case,
        hashlib.sha256(request_file.read_bytes()).hexdigest(),
        returned.content_sha256,
    )
    save_supported_proposal(catalog, designation, definition.model_dump_json().encode())
    prepared = prepare_process_activation(catalog, designation, workspace)
    authorization = authorize_process_activation(
        prepared,
        channel="local-chat",
        actor="fictional-process-change-test",
        source_ref="T3 synthetic activation; not owner acceptance",
    )
    activated = execute_process_activation(prepared, authorization)
    assert activated.creation.first_work_id is not None
    current = _work(workspace, activated.creation.first_work_id)
    return catalog, workspace, designation, definition, current


def _work(path: Path, identity: UUID) -> Work:
    return next(
        row for row in read_records(path).records if isinstance(row, Work) and row.id == identity
    )


def _process(path: Path) -> Process:
    return next(row for row in read_records(path).records if isinstance(row, Process))


def _artifact(path: Path, work_id: UUID) -> Artifact:
    return next(
        row
        for row in read_records(path).records
        if isinstance(row, Artifact) and row.work_id == work_id
    )


def _authorize_artifact(path: Path, work: Work) -> None:
    artifact = _artifact(path, work.id)
    state = read_records(path)
    request = MutationRequest(
        version=2,
        operation="authorize_artifact",
        operation_id=uuid4(),
        workspace_id=state.workspace_id,
        work_id=work.id,
        expected_revision=state.state_revision,
        provenance="Synthetic ordinary continuation mutation",
        artifact_id=artifact.id,
        artifact_revision=artifact.revision,
    )
    apply_mutation(path, request, _confirm(path, request))


def _changed(definition: ProcessDefinition, case: str) -> ProcessDefinition:
    if case == "small":
        source = definition.nodes[0]
        added = NodeDefinition(
            node_id="review",
            goal="Review the fictional amber brief before recurrence",
            expected_result="One exact fictional review",
            acceptance=("review is present",),
            boundaries=source.boundaries,
            budget="One technical review",
            artifact_title="Amber review snapshot",
            output_keys=("review",),
            reasons=source.reasons,
        )
        return ProcessDefinition.model_validate(
            definition.model_dump() | dict(edition=2, nodes=(*definition.nodes, added))
        )
    changed = definition.nodes[1].model_copy(
        update=dict(
            goal="Read and retain the reviewed fictional research note",
            expected_result="The exact reviewed research limit fact",
            acceptance=("research_fact is present after explicit review",),
        )
    )
    return ProcessDefinition.model_validate(
        definition.model_dump()
        | dict(edition=2, nodes=(definition.nodes[0], changed, definition.nodes[2]))
    )


def _add_future(
    definition: ProcessDefinition, *, node_id: str, goal: str, output_key: str
) -> ProcessDefinition:
    source = definition.nodes[-1]
    added = NodeDefinition(
        node_id=node_id,
        goal=goal,
        expected_result=f"One exact fictional {output_key}",
        acceptance=(f"{output_key} is present",),
        boundaries=source.boundaries,
        budget="One technical continuation",
        artifact_title=f"Fictional {output_key} snapshot",
        output_keys=(output_key,),
        reasons=source.reasons,
    )
    return ProcessDefinition.model_validate(
        definition.model_dump()
        | dict(edition=definition.edition + 1, nodes=(*definition.nodes, added))
    )


def _review(
    catalog: Path,
    workspace: Path,
    designation: str,
    changed: ProcessDefinition,
) -> ReviewedProcessChange:
    prepared = prepare_process_change(
        catalog, designation, changed.model_dump_json().encode("utf-8")
    )
    return review_process_change(prepared, _confirm(workspace, prepared.query))


def _decide(
    review: ReviewedProcessChange, decision: Literal["approve", "reject"]
) -> ProcessChangeStatus:
    actor = "fictional-process-change-test-рецензент"
    source_ref = f"T3 точное synthetic {decision}; not owner acceptance"
    authorization = authorize_process_change(
        review,
        decision=decision,
        channel="local-chat",
        actor=actor,
        source_ref=source_ref,
    )
    assert authorization.actor == actor and authorization.source_ref == source_ref
    return decide_process_change(review, authorization)


def _accept_current_result(
    workspace: Path,
    current: Work,
    snapshot: ProcessSnapshot,
    data: tuple[DataValue, ...],
) -> bytes:
    content = snapshot_bytes(record_result(snapshot, data))
    artifact = _artifact(workspace, current.id)
    state = read_records(workspace)
    publication = MutationRequest(
        version=2,
        operation="publish_artifact",
        operation_id=uuid4(),
        workspace_id=state.workspace_id,
        work_id=current.id,
        expected_revision=state.state_revision,
        provenance="T3 exact fictional current Result snapshot",
        artifact_id=artifact.id,
        artifact_revision=artifact.revision,
        content_sha256=hashlib.sha256(content).hexdigest(),
        content_size=len(content),
    )
    apply_mutation(workspace, publication, _confirm(workspace, publication), content=content)
    state = read_records(workspace)
    handoff = Handoff(
        kind="handoff",
        version=1,
        handoff_id=uuid4(),
        workspace_id=state.workspace_id,
        process=current.process_id,
        related_work=current.id,
        intent="accepted_result",
        source_revision=state.state_revision,
        result=ArtifactReference(
            artifact_id=artifact.id,
            version_id=publication.operation_id,
            sha256=hashlib.sha256(content).hexdigest(),
        ),
        provenance="Accepted fictional T3 current result; technical fixture only",
        created_by="fictional-process-change-test",
    )
    request = handoff_request(handoff.model_dump_json().encode(), source_ref="process-t3-test")
    apply_mutation(workspace, request, _confirm(workspace, request))
    return content


@pytest.mark.parametrize("case", ["small", "project"])
def test_approved_change_is_pending_then_affects_real_future_work_exactly(
    tmp_path: Path, case: str
) -> None:
    catalog, workspace, designation, definition, current = _activate(tmp_path, case)
    initial_process = _process(workspace)
    assert initial_process.pack_binding is not None
    pack_bytes = initial_process.pack_binding.model_dump_json().encode()
    basis = read_artifact(workspace, _artifact(workspace, current.id).id).content
    records_before = read_records(workspace)
    history_before = read_history(workspace)
    handoffs_before = read_handoffs(workspace)
    database_before = read_workspace(workspace).database.read_bytes()

    review = _review(catalog, workspace, designation, _changed(definition, case))
    preview = process_change_preview_bytes(review)
    assert hashlib.sha256(preview).hexdigest() == review.preview_sha256
    assert review.preview.current_work == current
    assert review.preview.current_work_effect.startswith("unchanged")
    assert review.preview.committed_effect.startswith("none")
    assert review.preview.next_work_without_change != review.preview.next_work_with_change
    pending = _decide(review, "approve")
    assert pending.stage == "pending" and pending.intent_is_core_effect is False
    assert read_workspace(workspace).database.read_bytes() == database_before
    assert read_records(workspace) == records_before
    assert read_history(workspace) == history_before
    assert read_handoffs(workspace) == handoffs_before
    assert read_artifact(workspace, _artifact(workspace, current.id).id).content == basis

    data = small_result_data() if case == "small" else project_request_data()
    accepted = _accept_current_result(
        workspace, current, ProcessSnapshot(definition=definition), data
    )
    result_version = _artifact(workspace, current.id).active_version
    assert result_version is not None
    query = process_change_continuation_query(catalog, designation)
    planned = prepare_process_change_continuation(catalog, designation, _confirm(workspace, query))
    status = inspect_process_change(catalog, designation)
    assert status.stage == "planned" and status.planned_request == planned.request
    assert (
        read_artifact(workspace, _artifact(workspace, current.id).id, result_version).content
        == accepted
    )
    before_effect = read_records(workspace)
    history_count = len(read_history(workspace).events)

    receipt = execute_process_change_continuation(planned, _confirm(workspace, planned.request))
    after = read_records(workspace)
    source = _work(workspace, current.id)
    next_work = _work(workspace, receipt.change.current_work_id)
    assert receipt.change.stage == "applied"
    assert after.state_revision == before_effect.state_revision + 1
    assert len(read_history(workspace).events) == history_count + 1
    assert source.status == "done" and next_work.status == "ready"
    assert source.pack_binding == next_work.pack_binding == _process(workspace).pack_binding
    assert next_work.pack_binding is not None
    assert next_work.pack_binding.model_dump_json().encode() == pack_bytes
    assert f"definition-sha256:{definition_sha256(_changed(definition, case))}" in (
        next_work.executor_requirements
    )
    assert (
        read_artifact(workspace, _artifact(workspace, current.id).id, result_version).content
        == accepted
    )
    assert read_artifact(workspace, _artifact(workspace, current.id).id).content == accepted
    assert read_handoffs(workspace)[: len(handoffs_before)] == handoffs_before

    replay_before = read_records(workspace)
    replay = execute_process_change_continuation(planned, _confirm(workspace, planned.request))
    assert replay.receipt == receipt.receipt
    assert read_records(workspace) == replay_before
    restarted = prepare_process_change_continuation(catalog, designation, None)
    assert restarted.request == planned.request
    assert inspect_process_change(catalog, designation).current_work_id == next_work.id


def test_rejection_retains_decision_and_preserves_all_core_bytes(tmp_path: Path) -> None:
    catalog, workspace, designation, definition, _current = _activate(tmp_path, "project")
    before = {
        path.relative_to(workspace).as_posix(): path.read_bytes()
        for path in workspace.rglob("*")
        if path.is_file()
    }
    review = _review(catalog, workspace, designation, _changed(definition, "project"))
    waiting = inspect_process_change(catalog, designation)
    assert waiting.stage == "review_pending" and waiting.pending_preview == review.preview
    query = process_change_review_query(catalog, designation)
    resumed = resume_process_change_review(catalog, designation, _confirm(workspace, query))
    assert process_change_preview_bytes(resumed) == process_change_preview_bytes(review)
    status = _decide(resumed, "reject")
    after = {
        path.relative_to(workspace).as_posix(): path.read_bytes()
        for path in workspace.rglob("*")
        if path.is_file()
    }
    assert status.stage == "rejected" and status.rejected_changes == 1
    assert status.approved_change_id is None and before == after


@pytest.mark.parametrize("failure", ["edition_only", "no_future"])
def test_unsupported_change_refuses_before_review_is_saved(tmp_path: Path, failure: str) -> None:
    catalog, workspace, designation, definition, _current = _activate(tmp_path, "project")
    if failure == "edition_only":
        changed = definition.model_copy(update=dict(edition=2))
        code = "no_change"
    else:
        changed = definition.model_copy(update=dict(edition=2, nodes=(definition.nodes[0],)))
        code = "no_future_work"
    before_database = read_workspace(workspace).database.read_bytes()
    before_records = read_records(workspace)
    prepared = prepare_process_change(
        catalog, designation, changed.model_dump_json().encode("utf-8")
    )

    with pytest.raises(ProcessChangeError, match=code):
        review_process_change(prepared, _confirm(workspace, prepared.query))

    assert read_workspace(workspace).database.read_bytes() == before_database
    assert read_records(workspace) == before_records
    with pytest.raises(ProcessChangeError, match="change_not_found"):
        inspect_process_change(catalog, designation)


@pytest.mark.parametrize("failure", ["wrong_id", "skipped_edition", "current_change"])
def test_wrong_or_started_definition_change_refuses_without_journal(
    tmp_path: Path, failure: str
) -> None:
    catalog, workspace, designation, definition, _current = _activate(tmp_path, "project")
    changed = _changed(definition, "project")
    if failure == "wrong_id":
        changed = changed.model_copy(update=dict(definition_id="fictional.other"))
    elif failure == "skipped_edition":
        changed = changed.model_copy(update=dict(edition=3))
    else:
        first = changed.nodes[0].model_copy(update=dict(goal="Changed current Work"))
        changed = changed.model_copy(update=dict(nodes=(first, *changed.nodes[1:])))
    before = read_workspace(workspace).database.read_bytes()
    prepared = prepare_process_change(catalog, designation, changed.model_dump_json().encode())
    with pytest.raises(ProcessChangeError, match="invalid_change|started"):
        review_process_change(prepared, _confirm(workspace, prepared.query))
    assert read_workspace(workspace).database.read_bytes() == before
    with pytest.raises(ProcessChangeError, match="change_not_found"):
        inspect_process_change(catalog, designation)


def test_missing_or_wrong_context_rights_and_stale_review_refuse(tmp_path: Path) -> None:
    catalog, workspace, designation, definition, current = _activate(tmp_path, "small")
    prepared = prepare_process_change(
        catalog, designation, _changed(definition, "small").model_dump_json().encode()
    )
    before = read_workspace(workspace).database.read_bytes()
    with pytest.raises(ProcessChangeError, match="permission_denied"):
        review_process_change(prepared, None)
    wrong = prepared.query.model_copy(update=dict(max_bytes=MAX_SMALL_BUDGET))
    with pytest.raises(ProcessChangeError, match="permission_denied"):
        review_process_change(prepared, _confirm(workspace, wrong))
    assert read_workspace(workspace).database.read_bytes() == before

    review = review_process_change(prepared, _confirm(workspace, prepared.query))
    state = read_records(workspace)
    request = MutationRequest(
        operation_id=uuid4(),
        workspace_id=state.workspace_id,
        work_id=current.id,
        expected_revision=state.state_revision,
        operation="set_work_requirements",
        requirements=current.executor_requirements,
        provenance="Synthetic intervening current-Work revision",
    )
    apply_mutation(workspace, request, _confirm(workspace, request))
    decision = authorize_process_change(
        review,
        decision="approve",
        channel="local-chat",
        actor="fictional-process-change-test",
        source_ref="T3 stale decision test",
    )
    with pytest.raises(ProcessChangeError, match="stale_change"):
        decide_process_change(review, decision)


def test_continuation_needs_both_context_and_core_rights_and_stale_request_refuses(
    tmp_path: Path,
) -> None:
    catalog, workspace, designation, definition, current = _activate(tmp_path, "project")
    _decide(_review(catalog, workspace, designation, _changed(definition, "project")), "approve")
    _accept_current_result(
        workspace,
        current,
        ProcessSnapshot(definition=definition),
        project_request_data(),
    )
    with pytest.raises(ProcessChangeError, match="permission_denied"):
        prepare_process_change_continuation(catalog, designation, None)
    query = process_change_continuation_query(catalog, designation)
    planned = prepare_process_change_continuation(catalog, designation, _confirm(workspace, query))
    before = read_records(workspace)
    with pytest.raises(ProcessChangeError, match="permission_denied"):
        execute_process_change_continuation(planned, None)
    assert read_records(workspace) == before

    content = b'{"fictional":"intervening-version"}\n'
    artifact = _artifact(workspace, current.id)
    request = MutationRequest(
        version=2,
        operation="publish_artifact",
        operation_id=uuid4(),
        workspace_id=before.workspace_id,
        work_id=current.id,
        expected_revision=before.state_revision,
        provenance="Synthetic stale planned-change sibling",
        artifact_id=artifact.id,
        artifact_revision=artifact.revision,
        content_sha256=hashlib.sha256(content).hexdigest(),
        content_size=len(content),
    )
    apply_mutation(workspace, request, _confirm(workspace, request), content=content)
    with pytest.raises(ProcessChangeError, match="conflict"):
        execute_process_change_continuation(planned, _confirm(workspace, planned.request))
    assert inspect_process_change(catalog, designation).stage == "planned"


def test_multiple_applied_changes_follow_mutated_continuation_and_rebuild_bases(
    tmp_path: Path,
) -> None:
    catalog, workspace, designation, edition1, work1 = _activate(tmp_path, "small")
    edition2 = _changed(edition1, "small")
    _decide(_review(catalog, workspace, designation, edition2), "approve")
    accepted1 = record_result(ProcessSnapshot(definition=edition1), small_result_data())
    _accept_current_result(
        workspace, work1, ProcessSnapshot(definition=edition1), small_result_data()
    )
    query1 = process_change_continuation_query(catalog, designation)
    planned1 = prepare_process_change_continuation(
        catalog, designation, _confirm(workspace, query1)
    )
    applied1 = execute_process_change_continuation(planned1, _confirm(workspace, planned1.request))
    work2 = _work(workspace, applied1.change.current_work_id)
    _authorize_artifact(workspace, work2)

    edition3 = _add_future(
        edition2,
        node_id="archive",
        goal="Archive the reviewed fictional amber brief",
        output_key="archive_note",
    )
    review2 = _review(catalog, workspace, designation, edition3)
    assert review2.snapshot == ProcessSnapshot(definition=edition2, results=accepted1.results)
    pending2 = _decide(review2, "approve")
    assert pending2.stage == "pending" and pending2.applied_changes == 1

    basis2 = ProcessSnapshot(definition=edition2, results=accepted1.results)
    _accept_current_result(
        workspace,
        work2,
        basis2,
        (DataValue(key="review", value="Fictional review retained"),),
    )
    query2 = process_change_continuation_query(catalog, designation)
    planned2 = prepare_process_change_continuation(
        catalog, designation, _confirm(workspace, query2)
    )
    applied2 = execute_process_change_continuation(planned2, _confirm(workspace, planned2.request))
    assert applied2.change.applied_changes == 2
    work3 = _work(workspace, applied2.change.current_work_id)
    _authorize_artifact(workspace, work3)

    edition4 = _add_future(
        edition3,
        node_id="close",
        goal="Close the fictional amber review chain",
        output_key="closure",
    )
    review3 = _review(catalog, workspace, designation, edition4)
    assert review3.preview.source_work_id == work3.id
    assert review3.snapshot.definition == edition3
    assert inspect_process_change(catalog, designation).stage == "review_pending"


def test_later_future_change_is_valid_and_later_current_no_future_refuses(
    tmp_path: Path,
) -> None:
    catalog, workspace, designation, edition1, work1 = _activate(tmp_path, "project")
    later = edition1.nodes[2].model_copy(
        update=dict(goal="Assemble the later reviewed fictional panel decision")
    )
    edition2 = edition1.model_copy(update=dict(edition=2, nodes=(*edition1.nodes[:2], later)))
    review = _review(catalog, workspace, designation, edition2)
    without = review.preview.next_work_without_change
    with_change = review.preview.next_work_with_change
    assert without is not None and with_change is not None
    assert (
        without.model_copy(update=dict(definition_sha256=with_change.definition_sha256))
        == with_change
    )
    _decide(review, "approve")
    _accept_current_result(
        workspace,
        work1,
        ProcessSnapshot(definition=edition1),
        project_request_data(),
    )
    query = process_change_continuation_query(catalog, designation)
    planned = prepare_process_change_continuation(catalog, designation, _confirm(workspace, query))
    applied = execute_process_change_continuation(planned, _confirm(workspace, planned.request))
    work2 = _work(workspace, applied.change.current_work_id)
    assert work2.goal == edition1.nodes[1].goal
    assert f"definition-sha256:{definition_sha256(edition2)}" in (work2.executor_requirements)

    _authorize_artifact(workspace, work2)
    before_records = read_records(workspace)
    before_status = inspect_process_change(catalog, designation)
    no_future = edition2.model_copy(update=dict(edition=3, nodes=edition2.nodes[:2]))
    prepared = prepare_process_change(
        catalog, designation, no_future.model_dump_json().encode("utf-8")
    )
    with pytest.raises(ProcessChangeError, match="no_future_work"):
        review_process_change(prepared, _confirm(workspace, prepared.query))

    assert read_records(workspace) == before_records
    assert inspect_process_change(catalog, designation) == before_status


MAX_SMALL_BUDGET = 999_999
