"""Result effect and recovery on new copies of the accepted Work6 main graph."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any
from uuid import UUID, uuid4

import pytest

from zaratustra.core import (
    Artifact,
    ContextQuery,
    Event,
    LocalAuthorization,
    MutationError,
    MutationRequest,
    NextWork,
    ProjectionRebuildError,
    ReceiptQuery,
    ResultSubmission,
    Work,
    WorkspaceError,
    apply_mutation,
    authorize_local,
    migrate_workspace,
    open_work,
    parse_result_request,
    prepare_authorization,
    read_handoffs,
    read_history,
    read_projection_status,
    read_receipt,
    read_records,
    read_result,
    read_workspace,
    rebuild_projections,
    submit_result,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    archive = Path(__file__).resolve().parents[3] / "docs/work6/evidence/retained-trial.zip"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(
            tmp_path / "selected", [n for n in bundle.namelist() if n.startswith("workspace/")]
        )
    selected = tmp_path / "selected/workspace"
    migrate_workspace(selected, target_version=6)
    return selected


def confirm(path: Path, value: MutationRequest | ReceiptQuery | ContextQuery) -> LocalAuthorization:
    return authorize_local(
        prepare_authorization(path, value),
        channel="local-chat",
        actor="fictional-test-adapter",
        source_ref="Work7:simulated-prior-permission",
    )


def request_for(path: Path) -> MutationRequest:
    state = read_records(path)
    initial = next(r for r in state.records if isinstance(r, Event))
    work = next(r for r in state.records if isinstance(r, Work) and r.id == initial.work_id)
    accepted = read_handoffs(path)
    return MutationRequest(
        version=4,
        operation_id=uuid4(),
        workspace_id=state.workspace_id,
        work_id=work.id,
        expected_revision=state.state_revision,
        operation="submit_result",
        provenance="Work7 fictional trial; exact fixture confirmed by owner",
        references=(accepted[0].handoff.result,),
        submission=ResultSubmission(
            source_revision=state.state_revision,
            result=accepted[0].handoff.result,
            acceptance_ids=tuple(a.handoff.handoff_id for a in accepted),
            next_work=NextWork(
                work_id=uuid4(),
                artifact_id=uuid4(),
                goal="Сравнить два сохранённых описания вымышленной луны",
                expected_result="Краткое сравнение",
                acceptance=(
                    "Указать, что серебряный край виден на закате, "
                    "и сослаться на обе сохранённые версии",
                ),
                boundaries=("Только Fictional observatory, без внешних действий",),
                budget="One short local session",
                executor_requirements=(),
                artifact_title="Краткое сравнение",
                authority_scope="work_metadata",
            ),
        ),
    )


def receipt_query(request: MutationRequest) -> ReceiptQuery:
    return ReceiptQuery(
        workspace_id=request.workspace_id,
        work_id=request.work_id,
        operation_id=request.operation_id,
    )


def context_query(path: Path, work_id: UUID, **changes: Any) -> ContextQuery:
    state = read_records(path)
    work = next(r for r in state.records if isinstance(r, Work) and r.id == work_id)
    return ContextQuery.model_validate(
        dict(
            workspace_id=state.workspace_id,
            work_id=work_id,
            process_id=work.process_id,
            expected_revision=state.state_revision,
            max_bytes=65536,
        )
        | changes
    )


def mutation(path: Path, work_id: UUID, operation: str, **changes: Any) -> MutationRequest:
    state = read_records(path)
    return MutationRequest.model_validate(
        dict(
            operation_id=uuid4(),
            workspace_id=state.workspace_id,
            work_id=work_id,
            expected_revision=state.state_revision,
            operation=operation,
            provenance="Explicit fictional diagnostic",
        )
        | changes
    )


def opened(path: Path, query: ContextQuery) -> bytes:
    return open_work(path, query, confirm(path, query)).output


def test_atomic_result_next_and_complete_five_fact_context(workspace: Path) -> None:
    request = request_for(workspace)
    before = read_records(workspace)
    receipt = submit_result(workspace, request, confirm(workspace, request))
    query = receipt_query(request)
    saved = read_result(workspace, query, confirm(workspace, query))
    assert saved.receipt == receipt == read_receipt(workspace, query, confirm(workspace, query))
    assert saved.event.request == request and saved.event.before.revision == before.state_revision
    assert saved.event.after.status == "done" and saved.event.after.revision == receipt.new_revision
    assert request.submission is not None
    assert saved.next_work_id == request.submission.next_work.work_id
    assert len(read_records(workspace).records) == len(before.records) + 2
    assert read_records(workspace).state_revision == before.state_revision + 1
    q = context_query(workspace, saved.next_work_id)
    database = read_workspace(workspace).database
    after = database.read_bytes()
    wire = opened(workspace, q)
    assert wire == opened(workspace, q) and database.read_bytes() == after
    value = json.loads(wire)
    sources = {s["locator"]: s["data"] for s in value["context"]["sources"]}
    assert sources[f"result:{request.operation_id}"] == saved.model_dump(mode="json")
    assert sources[f"work:{saved.next_work_id}"]["goal"] == request.submission.next_work.goal
    for accepted in read_handoffs(workspace):
        assert sources[f"acceptance:{accepted.handoff.handoff_id}"] == accepted.model_dump(
            mode="json"
        )
    for ref in saved.event.result_references:
        source = sources[f"artifact-version:{ref.version_id}"]
        assert hashlib.sha256(base64.b64decode(source["content_base64"])).hexdigest() == ref.sha256
    assert value["manifest"]["budget"]["used"] == len(wire)
    assert read_projection_status(workspace).status == "current"
    with pytest.raises(MutationError, match="permission_denied"):
        opened(workspace, context_query(workspace, request.work_id))


@pytest.mark.parametrize(
    "change,code",
    [
        ("stale", "conflict"),
        ("source", "conflict"),
        ("collision", "collision"),
        ("omit", "invalid_result"),
        ("identity", "invalid_result"),
        ("hash", "invalid_result"),
    ],
)
def test_invalid_first_result_is_no_effect(workspace: Path, change: str, code: str) -> None:
    request = request_for(workspace)
    value = request.model_dump(mode="json")
    if change == "stale":
        value["expected_revision"] -= 1
    elif change == "source":
        value["submission"]["source_revision"] -= 1
    elif change == "collision":
        value["operation_id"] = value["submission"]["acceptance_ids"][0]
    elif change == "omit":
        value["submission"]["acceptance_ids"].pop()
    elif change == "identity":
        value["submission"]["next_work"]["work_id"] = value["work_id"]
    else:
        value["submission"]["result"]["sha256"] = "0" * 64
        value["references"][0]["sha256"] = "0" * 64
    altered = MutationRequest.model_validate(value)
    database = read_workspace(workspace).database
    before = database.read_bytes()
    with pytest.raises(MutationError, match=code):
        submit_result(workspace, altered, confirm(workspace, altered))
    assert database.read_bytes() == before


def test_terminal_replay_new_id_and_current_discovery_rights(workspace: Path) -> None:
    request = request_for(workspace)
    receipt = submit_result(workspace, request, confirm(workspace, request))
    before = read_workspace(workspace).database.read_bytes()
    for operation_id in (request.operation_id, uuid4()):
        replay = request.model_copy(
            update=dict(operation_id=operation_id, expected_revision=receipt.new_revision)
        )
        with pytest.raises(MutationError, match="permission_denied"):
            submit_result(workspace, replay, confirm(workspace, replay))
    assert read_workspace(workspace).database.read_bytes() == before

    for op in ("authorize_work", "set_work_requirements", "cancel_work"):
        attempted = mutation(workspace, request.work_id, op)
        with pytest.raises(MutationError, match="permission_denied"):
            apply_mutation(workspace, attempted, confirm(workspace, attempted))
    revoked = mutation(workspace, request.work_id, "revoke_work")
    apply_mutation(workspace, revoked, confirm(workspace, revoked))
    query = receipt_query(request)
    with pytest.raises(MutationError, match="permission_denied"):
        read_result(workspace, query, confirm(workspace, query))
    assert request.submission is not None
    assert opened(workspace, context_query(workspace, request.submission.next_work.work_id))


@pytest.mark.parametrize(
    "table", ["core_records", "core_state", "mutation_events", "mutation_receipts", "work_results"]
)
def test_transaction_failure_preserves_whole_old_graph(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, table: str
) -> None:
    request = request_for(workspace)
    caller = confirm(workspace, request)
    database = read_workspace(workspace).database
    before = database.read_bytes()
    connect = sqlite3.connect

    def fail(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = connect(*args, **kwargs)

        def deny(action: int, target: str | None, *_: object) -> int:
            return (
                sqlite3.SQLITE_DENY
                if target == table and action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE)
                else sqlite3.SQLITE_OK
            )

        connection.set_authorizer(deny)
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", fail)
        with pytest.raises(WorkspaceError):
            submit_result(workspace, request, caller)
    assert (
        database.read_bytes() == before
        and read_records(workspace).state_revision == request.expected_revision
    )
    query = receipt_query(request)
    with pytest.raises(MutationError, match="not_found"):
        read_result(workspace, query, confirm(workspace, query))
    assert (
        submit_result(workspace, request, confirm(workspace, request)).new_revision
        == request.expected_revision + 1
    )


@pytest.mark.parametrize("lost", [False, True])
def test_postcommit_projection_failure_or_lost_reply_preserves_next(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, lost: bool
) -> None:
    from zaratustra.core import mutations

    request = request_for(workspace)

    def fail(*_: object) -> None:
        if lost:
            raise RuntimeError("simulated transport loss after commit")
        raise OSError("simulated projection failure")

    with monkeypatch.context() as patch:
        patch.setattr(mutations, "rebuild_projections", fail)
        with pytest.raises(RuntimeError if lost else ProjectionRebuildError):
            submit_result(workspace, request, confirm(workspace, request))
    query = receipt_query(request)
    saved = read_result(workspace, query, confirm(workspace, query))
    assert saved.receipt.new_revision == request.expected_revision + 1
    assert saved.next_work_id is not None
    assert opened(workspace, context_query(workspace, saved.next_work_id))
    before = read_workspace(workspace).database.read_bytes()
    assert rebuild_projections(workspace).status == "current"
    assert (
        rebuild_projections(workspace).expected_sha256
        == read_projection_status(workspace).expected_sha256
    )
    assert read_workspace(workspace).database.read_bytes() == before


def test_late_loss_exact_repair_and_global_invalidation(workspace: Path) -> None:
    request = request_for(workspace)
    submit_result(workspace, request, confirm(workspace, request))
    query = receipt_query(request)
    saved = read_result(workspace, query, confirm(workspace, query))
    assert saved.next_work_id is not None
    q = context_query(workspace, saved.next_work_id)
    ref = saved.event.result_references[0]
    content_path = workspace / "artifacts" / str(ref.artifact_id) / f"{ref.version_id}.blob"
    content = content_path.read_bytes()
    content_path.unlink()
    assert read_result(workspace, query, confirm(workspace, query)) == saved
    with pytest.raises(WorkspaceError, match="content_unavailable"):
        opened(workspace, q)
    artifact = next(
        r
        for r in read_records(workspace).records
        if isinstance(r, Artifact) and r.id == ref.artifact_id
    )
    repair = mutation(
        workspace,
        request.work_id,
        "restore_artifact",
        version=2,
        artifact_id=artifact.id,
        artifact_revision=artifact.revision,
        restore_version=ref.version_id,
        content_sha256=ref.sha256,
        content_size=len(content),
    )
    apply_mutation(workspace, repair, confirm(workspace, repair), content=content)
    assert content_path.read_bytes() == content
    assert read_result(workspace, query, confirm(workspace, query)) == saved
    with pytest.raises(MutationError, match="conflict"):
        opened(workspace, q)
    assert saved.next_work_id is not None
    assert opened(workspace, context_query(workspace, saved.next_work_id))


def test_next_current_rights_scope_all_acceptances_and_budget(workspace: Path) -> None:
    request = request_for(workspace)
    submit_result(workspace, request, confirm(workspace, request))
    assert request.submission is not None
    next_id = request.submission.next_work.work_id
    q = context_query(workspace, next_id)
    wire = opened(workspace, q)
    exact = context_query(workspace, next_id, max_bytes=len(wire))
    assert len(opened(workspace, exact)) == len(wire)
    with pytest.raises(MutationError, match="budget_exceeded"):
        opened(workspace, context_query(workspace, next_id, max_bytes=len(wire) - 1))
    with pytest.raises(MutationError, match="scope"):
        opened(workspace, context_query(workspace, next_id, process_id=uuid4()))
    with pytest.raises(MutationError, match="scope"):
        opened(
            workspace,
            context_query(
                workspace,
                next_id,
                references=(dict(artifact_id=uuid4(), version_id=uuid4(), sha256="0" * 64),),
            ),
        )
    change = mutation(workspace, next_id, "set_work_requirements", requirements=("reasoning",))
    apply_mutation(workspace, change, confirm(workspace, change))
    assert read_history(workspace).events[-1].after.id == next_id
    with pytest.raises(MutationError, match="conflict"):
        opened(workspace, q)
    revoked = mutation(workspace, next_id, "revoke_work")
    apply_mutation(workspace, revoked, confirm(workspace, revoked))
    with pytest.raises(MutationError, match="permission_denied"):
        opened(workspace, context_query(workspace, next_id))


def test_final_next_validation_detects_late_change_and_physical_loss(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zaratustra.core import context

    request = request_for(workspace)
    submit_result(workspace, request, confirm(workspace, request))
    assert request.submission is not None
    next_id = request.submission.next_work.work_id
    original = context._compile

    def changed(*args: Any) -> Any:
        package = original(*args)
        change = mutation(workspace, next_id, "set_work_requirements", requirements=("coding",))
        apply_mutation(workspace, change, confirm(workspace, change))
        return package

    with monkeypatch.context() as patch:
        patch.setattr(context, "_compile", changed)
        with pytest.raises(MutationError, match="conflict"):
            opened(workspace, context_query(workspace, next_id))

    def lost(*args: Any) -> Any:
        package = original(*args)
        assert request.submission is not None
        ref = request.submission.result
        (workspace / "artifacts" / str(ref.artifact_id) / f"{ref.version_id}.blob").unlink()
        return package

    with monkeypatch.context() as patch:
        patch.setattr(context, "_compile", lost)
        with pytest.raises(WorkspaceError, match="content_unavailable"):
            opened(workspace, context_query(workspace, next_id))


def test_exact_request_path_no_self_authorization_and_parser(
    workspace: Path, tmp_path: Path
) -> None:
    request = request_for(workspace)
    before = read_workspace(workspace).database.read_bytes()
    with pytest.raises(MutationError, match="permission_denied"):
        submit_result(workspace, request)
    changed = request.model_copy(update=dict(provenance="Other instruction"))
    with pytest.raises(MutationError, match="permission_denied"):
        submit_result(workspace, changed, confirm(workspace, request))
    other = tmp_path / "other-selected-copy"
    shutil.copytree(workspace, other)
    with pytest.raises(MutationError, match="permission_denied"):
        submit_result(other, request, confirm(workspace, request))
    assert parse_result_request(request.model_dump_json().encode()) == request
    with pytest.raises(WorkspaceError, match="Duplicate JSON key"):
        parse_result_request(b'{"version":4,"version":4}')
    value = request.model_dump(mode="json") | {"approved": True}
    with pytest.raises(WorkspaceError):
        parse_result_request(json.dumps(value).encode())
    assert read_workspace(workspace).database.read_bytes() == before


def test_competing_submissions_commit_one_continuation(workspace: Path) -> None:
    first = request_for(workspace)
    second = request_for(workspace)
    barrier = Barrier(2)
    first_caller, second_caller = confirm(workspace, first), confirm(workspace, second)

    def attempt(request: MutationRequest, caller: LocalAuthorization) -> str:
        barrier.wait(timeout=10)
        try:
            submit_result(workspace, request, caller)
            return "committed"
        except MutationError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = [
            executor.submit(attempt, first, first_caller),
            executor.submit(attempt, second, second_caller),
        ]
        outcomes = [job.result(timeout=15) for job in jobs]
    assert sorted(outcomes) == ["committed", "permission_denied"]
    assert read_records(workspace).state_revision == first.expected_revision + 1
    assert len([r for r in read_records(workspace).records if isinstance(r, Work)]) == 2
    assert len([e for e in read_history(workspace).events if e.next_work is not None]) == 1


def test_result_cli_discovery_survives_ascii_pipe_encoding(workspace: Path) -> None:
    request = request_for(workspace)
    submit_result(workspace, request, confirm(workspace, request))
    query = receipt_query(request)
    expected = read_result(workspace, query, confirm(workspace, query))
    script = """import sys
from zaratustra import cli
from zaratustra.core import authorize_local
def confirmed(prompt):
    return authorize_local(prompt, channel='local-chat', actor='fictional-test-adapter',
                           source_ref='Work7:simulated-prior-permission')
cli.confirm_on_console = confirmed
raise SystemExit(cli.main(['result', 'read', sys.argv[1], sys.argv[2]]))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(workspace), query.model_dump_json()],
        capture_output=True,
        check=False,
        env=os.environ | {"PYTHONIOENCODING": "ascii"},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.decode("ascii")) == expected.model_dump(mode="json")
