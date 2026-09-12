"""Generic one-Work metadata reading with exact accepted bases and continuation."""

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from zaratustra.core import (
    Artifact,
    ArtifactReference,
    ContextQuery,
    Handoff,
    InitialRecords,
    LocalAuthorization,
    MutationError,
    MutationRequest,
    NextWork,
    ProcessQuery,
    ResultSubmission,
    Work,
    apply_mutation,
    authorize_local,
    create_initial_records,
    handoff_request,
    init_workspace,
    migrate_workspace,
    prepare_authorization,
    read_basic_process,
    read_records,
    read_workspace,
    submit_result,
)


def confirm(path: Path, value: MutationRequest | ProcessQuery | ContextQuery) -> LocalAuthorization:
    return authorize_local(
        prepare_authorization(path, value),
        channel="local-chat",
        actor="generic-basic-reader-test",
        source_ref="explicit disposable test workspace",
    )


def request(path: Path, work_id: UUID, operation: str, **fields: Any) -> MutationRequest:
    snapshot = read_records(path)
    return MutationRequest.model_validate(
        dict(
            operation_id=uuid4(),
            workspace_id=snapshot.workspace_id,
            work_id=work_id,
            expected_revision=snapshot.state_revision,
            operation=operation,
            provenance="Explicit generic reader test",
        )
        | fields
    )


def bootstrap(path: Path) -> UUID:
    path.mkdir()
    init_workspace(path)
    migrate_workspace(path, target_version=7)
    snapshot = create_initial_records(
        path,
        InitialRecords(
            process_title="Generic reading Process",
            goal="Read exact saved metadata",
            expected_result="One bounded metadata document",
            acceptance=("Exact accepted reference is retained",),
            boundaries=("No Artifact content is opened",),
            budget="One local read",
            artifact_title="Generic accepted value",
        ),
    )
    work = next(row for row in snapshot.records if isinstance(row, Work))
    authorize = request(path, work.id, "authorize_work")
    apply_mutation(path, authorize, confirm(path, authorize))
    return work.id


def query(path: Path, work_id: UUID, **changes: Any) -> ProcessQuery:
    snapshot = read_records(path)
    work = next(row for row in snapshot.records if isinstance(row, Work) and row.id == work_id)
    return ProcessQuery.model_validate(
        dict(
            workspace_id=snapshot.workspace_id,
            work_id=work.id,
            process_id=work.process_id,
            expected_revision=snapshot.state_revision,
            visible_work_ids=(work.id,),
            selected_work_id=work.id,
            max_bytes=65536,
        )
        | changes
    )


def accept_value(path: Path, work_id: UUID) -> tuple[ArtifactReference, UUID]:
    artifact = next(
        row
        for row in read_records(path).records
        if isinstance(row, Artifact) and row.work_id == work_id
    )
    authorize = request(
        path,
        work_id,
        "authorize_artifact",
        version=2,
        artifact_id=artifact.id,
        artifact_revision=artifact.revision,
    )
    apply_mutation(path, authorize, confirm(path, authorize))
    content = b'{"generic":"accepted metadata basis"}\n'
    publish = request(
        path,
        work_id,
        "publish_artifact",
        version=2,
        artifact_id=artifact.id,
        artifact_revision=artifact.revision,
        content_sha256=hashlib.sha256(content).hexdigest(),
        content_size=len(content),
    )
    apply_mutation(path, publish, confirm(path, publish), content=content)
    reference = ArtifactReference(
        artifact_id=artifact.id,
        version_id=publish.operation_id,
        sha256=hashlib.sha256(content).hexdigest(),
    )
    snapshot = read_records(path)
    work = next(row for row in snapshot.records if isinstance(row, Work) and row.id == work_id)
    acceptance_id = uuid4()
    handoff = Handoff(
        kind="handoff",
        version=1,
        handoff_id=acceptance_id,
        workspace_id=snapshot.workspace_id,
        process=work.process_id,
        related_work=work.id,
        intent="accepted_result",
        source_revision=snapshot.state_revision,
        result=reference,
        provenance="Explicit generic accepted value",
        created_by="generic test adapter",
    )
    accepted = handoff_request(handoff.model_dump_json().encode(), source_ref="generic-test")
    apply_mutation(path, accepted, confirm(path, accepted))
    return reference, acceptance_id


def test_basic_read_is_bounded_exact_authorized_and_content_free(tmp_path: Path) -> None:
    path = tmp_path / "workspace"
    work_id = bootstrap(path)
    reference, acceptance_id = accept_value(path, work_id)
    selected = query(path, work_id)
    database = read_workspace(path).database
    before = database.read_bytes()
    package = read_basic_process(path, selected, confirm(path, selected))
    value = json.loads(package.output)

    assert database.read_bytes() == before
    assert value["selected_work"]["id"] == str(work_id)
    assert value["selected_work"]["status"] == "ready"
    assert value["continuation_state"] == "selected_work_ready"
    assert value["saved_continuation"] is None
    assert value["accepted_basis"] == [
        {
            "acceptance_id": str(acceptance_id),
            "accepted_revision": selected.expected_revision,
            "source_revision": selected.expected_revision - 1,
            "result": reference.model_dump(mode="json"),
            "basis": [],
        }
    ]
    assert value["inherited_result_basis"] == []
    assert "content_base64" not in package.output.decode()
    assert len(package.output) <= selected.max_bytes

    with pytest.raises(MutationError, match="scope"):
        expanded = selected.model_copy(update=dict(visible_work_ids=(work_id, uuid4())))
        read_basic_process(path, expanded, confirm(path, expanded))
    with pytest.raises(MutationError, match="permission_denied"):
        changed = selected.model_copy(update=dict(max_bytes=selected.max_bytes - 1))
        read_basic_process(path, changed, confirm(path, selected))
    with pytest.raises(MutationError, match="budget_exceeded"):
        tiny = selected.model_copy(update=dict(max_bytes=1))
        read_basic_process(path, tiny, confirm(path, tiny))


def test_terminal_result_and_inherited_basis_are_exact_but_separately_scoped(
    tmp_path: Path,
) -> None:
    path = tmp_path / "workspace"
    work_id = bootstrap(path)
    reference, acceptance_id = accept_value(path, work_id)
    snapshot = read_records(path)
    process_id = next(
        row.process_id for row in snapshot.records if isinstance(row, Work) and row.id == work_id
    )
    next_work_id, next_artifact_id = uuid4(), uuid4()
    result = request(
        path,
        work_id,
        "submit_result",
        version=4,
        references=(reference,),
        submission=ResultSubmission(
            source_revision=snapshot.state_revision,
            result=reference,
            acceptance_ids=(acceptance_id,),
            next_work=NextWork(
                work_id=next_work_id,
                artifact_id=next_artifact_id,
                goal="Continue from the exact accepted generic result",
                expected_result="A separate next result",
                acceptance=("Use only inherited exact grounds",),
                boundaries=("No implied content authority",),
                budget="One later read",
                executor_requirements=(),
                artifact_title="Next generic value",
                authority_scope="work_metadata",
            ),
        ),
    )
    receipt = submit_result(path, result, confirm(path, result))

    terminal_query = query(path, work_id)
    terminal = json.loads(
        read_basic_process(path, terminal_query, confirm(path, terminal_query)).output
    )
    assert result.submission is not None
    assert terminal["selected_work"]["status"] == "done"
    assert terminal["continuation_state"] == "saved_result"
    assert terminal["saved_continuation"] == {
        "result_id": str(result.operation_id),
        "accepted_revision": receipt.new_revision,
        "references": [reference.model_dump(mode="json")],
        "next_work": result.submission.next_work.model_dump(mode="json"),
    }
    assert str(next_work_id) not in json.dumps(terminal["selected_work"])

    next_query = query(path, next_work_id)
    next_value = json.loads(read_basic_process(path, next_query, confirm(path, next_query)).output)
    assert next_value["selected_work"]["process_id"] == str(process_id)
    assert next_value["continuation_state"] == "selected_work_ready"
    assert next_value["accepted_basis"] == []
    assert next_value["inherited_result_basis"] == [
        {
            "result_id": str(result.operation_id),
            "source_work_id": str(work_id),
            "accepted_revision": receipt.new_revision,
            "references": [reference.model_dump(mode="json")],
        }
    ]

    revoked = request(path, work_id, "revoke_work")
    apply_mutation(path, revoked, confirm(path, revoked))
    stale_terminal = terminal_query.model_copy(
        update=dict(expected_revision=receipt.new_revision + 1)
    )
    with pytest.raises(MutationError, match="permission_denied"):
        read_basic_process(path, stale_terminal, confirm(path, stale_terminal))
