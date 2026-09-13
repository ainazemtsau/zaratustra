"""Mechanical behavior and integrity tests for the bounded definition adapter."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tests.fixtures.process_creation import (
    project_definition,
    project_reference,
    project_request_data,
    project_research_data,
    small_definition,
    small_reference,
    small_result_data,
)
from tools.probe_m1 import work_at
from tools.probe_packs import PacksTrial, proposed
from zaratustra.core import (
    ArtifactReference,
    Handoff,
    NextWork,
    Work,
    create_initial_records,
    handoff_request,
    init_workspace,
    migrate_workspace,
    read_records,
)
from zaratustra.process_packs import (
    ConstructionError,
    DataValue,
    Dependency,
    NodeResult,
    PackRegistry,
    ProcessDefinition,
    ProcessSnapshot,
    evaluate_snapshot,
    initial_records,
    initial_requirements,
    record_result,
    registration,
    snapshot_bytes,
)


def work_for(requirements: tuple[str, ...], *, project: bool = False) -> Work:
    reference = project_reference() if project else small_reference()
    definition = project_definition() if project else small_definition()
    initial = initial_records(definition)
    return Work(
        id=uuid4(),
        revision=2,
        created_at=datetime(2026, 9, 13, tzinfo=UTC),
        process_id=uuid4(),
        goal=initial.goal,
        expected_result=initial.expected_result,
        acceptance=initial.acceptance,
        boundaries=initial.boundaries,
        budget=initial.budget,
        status="ready",
        authority_scope="work_metadata",
        executor_requirements=requirements,
        pack_binding=reference,
    )


def work_from_spec(spec: NextWork, *, project: bool = False) -> Work:
    reference = project_reference() if project else small_reference()
    return Work(
        id=uuid4(),
        revision=3,
        created_at=datetime(2026, 9, 13, tzinfo=UTC),
        process_id=uuid4(),
        goal=spec.goal,
        expected_result=spec.expected_result,
        acceptance=spec.acceptance,
        boundaries=spec.boundaries,
        budget=spec.budget,
        status="ready",
        authority_scope=spec.authority_scope,
        executor_requirements=spec.executor_requirements,
        pack_binding=reference,
    )


def test_small_definition_projects_a_new_occurrence_without_a_backedge() -> None:
    definition = small_definition()
    empty = ProcessSnapshot(definition=definition)
    initial = evaluate_snapshot(empty)
    assert initial.selected is not None
    assert (initial.selected.node.node_id, initial.selected.occurrence) == ("capture", 1)
    assert initial.selected.grounds == () and initial.blocked == ()
    assert initial_records(definition).goal == initial.selected.node.goal

    accepted = record_result(empty, small_result_data())
    after = evaluate_snapshot(accepted)
    assert after.selected is not None
    assert (after.selected.node.node_id, after.selected.occurrence) == ("capture", 2)
    assert after.selected.grounds[0].data == small_result_data()
    assert after.selected.grounds[0].occurrence == 1
    assert definition.nodes[0].dependencies == () and definition.nodes[0].recurring

    registered = registration(small_reference(), definition)
    following = registered.rule.next_work(
        work_for(initial_requirements(definition)), snapshot_bytes(accepted), uuid4(), uuid4()
    )
    assert following.executor_requirements[-2:] == ("node:capture", "occurrence:2")
    assert following.authority_scope == "work_metadata"


def test_project_graph_retains_distinct_predecessor_data_before_dependent_work() -> None:
    definition = project_definition()
    empty = ProcessSnapshot(definition=definition)
    initial = evaluate_snapshot(empty)
    assert tuple(row.node.node_id for row in initial.ready) == (
        "read-request",
        "read-research",
    )
    assert initial.blocked[0].node.node_id == "assemble"
    assert initial.blocked[0].missing_dependencies == ("read-request", "read-research")

    request_done = record_result(empty, project_request_data())
    middle = evaluate_snapshot(request_done)
    assert middle.selected is not None and middle.selected.node.node_id == "read-research"
    assert middle.blocked[0].missing_dependencies == ("read-research",)

    research_done = record_result(request_done, project_research_data())
    ready = evaluate_snapshot(research_done)
    assert ready.selected is not None and ready.selected.node.node_id == "assemble"
    assert tuple(ground.node_id for ground in ready.selected.grounds) == (
        "read-request",
        "read-research",
    )
    assert tuple(ground.data for ground in ready.selected.grounds) == (
        project_request_data(),
        project_research_data(),
    )
    assert len({ground.result_sha256 for ground in ready.selected.grounds}) == 2
    source_kinds = {source.kind for source in definition.sources}
    reason_sources = set(ready.selected.node.reasons[0].source_ids)
    assert source_kinds == {"request", "research", "capability"}
    assert reason_sources == {source.source_id for source in definition.sources}

    registered = registration(project_reference(), definition)
    second_spec = registered.rule.next_work(
        work_for(initial_requirements(definition), project=True),
        snapshot_bytes(request_done),
        uuid4(),
        uuid4(),
    )
    combine_spec = registered.rule.next_work(
        work_from_spec(second_spec, project=True),
        snapshot_bytes(research_done),
        uuid4(),
        uuid4(),
    )
    assert combine_spec.goal == ready.selected.node.goal
    assert combine_spec.executor_requirements[-2:] == ("node:assemble", "occurrence:1")


@pytest.mark.parametrize(
    "replacement",
    [
        "Fictional request silently changed to four panels",
        "Fictional request silently changed to eleven panels",
    ],
)
def test_next_work_pins_the_exact_prior_snapshot_history(replacement: str) -> None:
    definition = project_definition()
    empty = ProcessSnapshot(definition=definition)
    request_done = record_result(empty, project_request_data())
    registered = registration(project_reference(), definition)
    second_spec = registered.rule.next_work(
        work_for(initial_requirements(definition), project=True),
        snapshot_bytes(request_done),
        uuid4(),
        uuid4(),
    )
    changed_request = request_done.results[0].model_copy(
        update=dict(data=(DataValue(key="request_fact", value=replacement),))
    )
    rewritten = request_done.model_copy(update=dict(results=(changed_request,)))
    rewritten = record_result(rewritten, project_research_data())
    with pytest.raises(ConstructionError, match="history_mismatch"):
        registered.rule.next_work(
            work_from_spec(second_spec, project=True),
            snapshot_bytes(rewritten),
            uuid4(),
            uuid4(),
        )


def test_existing_core_commits_the_adapter_proposal_and_inherits_binding(tmp_path: Path) -> None:
    definition = project_definition()
    reference = project_reference()
    installed = registration(reference, definition)
    selected_registry = PackRegistry((installed,))
    trial = PacksTrial(tmp_path / "workspace", tmp_path / "evidence")
    trial.path.mkdir()
    init_workspace(trial.path)
    migrate_workspace(trial.path, target_version=7)
    create_initial_records(trial.path, initial_records(definition))
    identity = work_at(trial.path).id
    trial.execute(trial.request(identity, "authorize_work"))
    trial.execute(
        trial.request(
            identity,
            "set_work_requirements",
            requirements=initial_requirements(definition),
        )
    )
    trial.execute(trial.bind(identity, reference, selected_registry))

    accepted = record_result(ProcessSnapshot(definition=definition), project_request_data())
    content = snapshot_bytes(accepted)
    trial.execute(trial.request(identity, "authorize_artifact"))
    publication = trial.request(
        identity,
        "publish_artifact",
        content_sha256=hashlib.sha256(content).hexdigest(),
        content_size=len(content),
    )
    trial.execute(publication, content)
    assert publication.artifact_id is not None
    state = read_records(trial.path)
    handoff = Handoff(
        kind="handoff",
        version=1,
        handoff_id=uuid4(),
        workspace_id=state.workspace_id,
        process=work_at(trial.path, identity).process_id,
        related_work=identity,
        intent="accepted_result",
        source_revision=state.state_revision,
        result=ArtifactReference(
            artifact_id=publication.artifact_id,
            version_id=publication.operation_id,
            sha256=hashlib.sha256(content).hexdigest(),
        ),
        provenance="Fictional constructor snapshot; technical test only",
        created_by="process creation test",
    )
    trial.execute(
        handoff_request(handoff.model_dump_json().encode("utf-8"), source_ref="process-t1-test")
    )
    request = proposed(trial.path, identity, selected_registry)
    assert request.submission is not None
    trial.execute(request)
    following = work_at(trial.path, request.submission.next_work.work_id)
    assert following.pack_binding == reference
    assert following.executor_requirements == request.submission.next_work.executor_requirements
    assert following.goal == definition.nodes[1].goal


@pytest.mark.parametrize("failure", ["unknown", "self", "cycle"])
def test_invalid_dependency_links_and_cycles_refuse(failure: str) -> None:
    definition = project_definition()
    payload = definition.model_dump()
    nodes = [dict(node) for node in payload["nodes"]]
    if failure == "unknown":
        nodes[2]["dependencies"] = (Dependency(node_id="absent"),)
    elif failure == "self":
        nodes[2]["dependencies"] = (Dependency(node_id="assemble"),)
    else:
        nodes[0]["dependencies"] = (Dependency(node_id="assemble"),)
    payload["nodes"] = tuple(nodes)
    with pytest.raises(ValidationError, match="target|self-edge|acyclic"):
        ProcessDefinition.model_validate(payload)


def test_incomplete_or_out_of_order_result_grounds_refuse() -> None:
    definition = project_definition()
    empty = ProcessSnapshot(definition=definition)
    with pytest.raises(ConstructionError, match="incomplete_result"):
        record_result(empty, (DataValue(key="wrong", value="present but not declared"),))
    forged = ProcessSnapshot(
        definition=definition,
        results=(
            NodeResult(
                node_id="assemble",
                occurrence=1,
                data=(DataValue(key="decision", value="ungrounded"),),
            ),
        ),
    )
    with pytest.raises(ConstructionError, match="invalid_result_order"):
        evaluate_snapshot(forged)


def test_unsupported_capability_and_unknown_reason_source_refuse() -> None:
    definition = small_definition()
    unsupported = ProcessDefinition.model_validate(
        definition.model_dump()
        | dict(required_capabilities=(*definition.required_capabilities, "fictional.unknown/v1"))
    )
    with pytest.raises(ConstructionError, match="unsupported_capability"):
        evaluate_snapshot(ProcessSnapshot(definition=unsupported))

    node = definition.nodes[0]
    reason = node.reasons[0].model_copy(update=dict(source_ids=("absent",)))
    changed_node = node.model_copy(update=dict(reasons=(reason,)))
    with pytest.raises(ValidationError, match="outside definition sources"):
        ProcessDefinition.model_validate(
            definition.model_dump() | dict(nodes=(changed_node.model_dump(),))
        )


@pytest.mark.parametrize("failure", ["noncanonical", "definition", "binding", "work"])
def test_rule_refuses_changed_snapshot_or_runtime_identity(failure: str) -> None:
    definition = small_definition()
    accepted = record_result(ProcessSnapshot(definition=definition), small_result_data())
    payload = snapshot_bytes(accepted)
    registered = registration(small_reference(), definition)
    work = work_for(initial_requirements(definition))
    if failure == "noncanonical":
        payload = payload.rstrip()
    elif failure == "definition":
        changed = definition.model_copy(update=dict(edition=2))
        payload = snapshot_bytes(
            record_result(ProcessSnapshot(definition=changed), small_result_data())
        )
    elif failure == "binding":
        work = work.model_copy(update=dict(pack_binding=project_reference()))
    else:
        work = work.model_copy(update=dict(executor_requirements=("wrong",)))
    with pytest.raises(
        ConstructionError,
        match="noncanonical_snapshot|definition_mismatch|binding_mismatch|work_mismatch",
    ):
        registered.rule.next_work(work, payload, uuid4(), uuid4())
