"""Context invariants on NEW copies of the retained accepted fictional Work 5 graph."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import sqlite3
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from zaratustra.core import (
    Artifact,
    ArtifactError,
    ArtifactReference,
    ContextQuery,
    LocalAuthorization,
    MutationError,
    MutationRequest,
    Work,
    WorkspaceError,
    apply_mutation,
    authorize_local,
    handoff_request,
    open_work,
    prepare_authorization,
    read_artifact,
    read_handoffs,
    read_records,
    read_workspace,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    archive = Path(__file__).resolve().parents[3] / "docs/work5/evidence/retained-trial-v2.zip"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(tmp_path / "selected-copy")
    return tmp_path / "selected-copy/workspace"


def confirm(path: Path, query: ContextQuery | MutationRequest) -> LocalAuthorization:
    return authorize_local(
        prepare_authorization(path, query),
        channel="local-chat",
        actor="fictional-test-adapter",
        source_ref="executor-CALL:simulated-prior-permission",
    )


def query_for(path: Path, **changes: Any) -> ContextQuery:
    state = read_records(path)
    work = next(row for row in state.records if isinstance(row, Work))
    return ContextQuery.model_validate(
        dict(
            workspace_id=state.workspace_id,
            work_id=work.id,
            process_id=work.process_id,
            expected_revision=state.state_revision,
            max_bytes=65536,
        )
        | changes
    )


def mutate(path: Path, name: str, *, content: bytes | None = None, **fields: Any) -> None:
    query = query_for(path)
    artifact = next(row for row in read_records(path).records if isinstance(row, Artifact))
    if name in ("authorize_artifact", "publish_artifact", "restore_artifact"):
        fields.update(version=2, artifact_id=artifact.id, artifact_revision=artifact.revision)
    if content is not None:
        fields.update(content_sha256=hashlib.sha256(content).hexdigest(), content_size=len(content))
    request = MutationRequest.model_validate(
        dict(
            workspace_id=query.workspace_id,
            work_id=query.work_id,
            expected_revision=query.expected_revision,
            operation_id=uuid4(),
            operation=name,
            provenance="Fictional context negative fixture",
        )
        | fields
    )
    apply_mutation(path, request, confirm(path, request), content=content)


def compiled(path: Path, **changes: Any) -> bytes:
    query = query_for(path, **changes)
    return open_work(path, query, confirm(path, query)).output


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def test_actual_sources_budget_hashes_and_read_only_repeat(workspace: Path) -> None:
    database = read_workspace(workspace).database
    before = database.read_bytes()
    output = compiled(workspace)
    assert compiled(workspace) == output and database.read_bytes() == before
    value = json.loads(output)
    context, manifest = value["context"], value["manifest"]
    assert manifest["budget"]["used"] == len(output) <= manifest["budget"]["maximum"]
    assert manifest["context_sha256"] == hashlib.sha256(canonical(context)).hexdigest()
    for source, item in zip(context["sources"], manifest["sources"], strict=True):
        assert (source["locator"], source["revision"]) == (item["locator"], item["revision"])
        data = canonical(source["data"])
        assert item["value_bytes"] == len(data)
        assert item["value_sha256"] == hashlib.sha256(data).hexdigest()
        if "content_base64" in source["data"]:
            content = base64.b64decode(source["data"]["content_base64"], validate=True)
            assert item["content_bytes"] == len(content)
            assert item["content_sha256"] == hashlib.sha256(content).hexdigest()
    acceptances = [s["data"] for s in context["sources"] if s["locator"].startswith("acceptance:")]
    assert acceptances == [row.model_dump(mode="json") for row in read_handoffs(workspace)]
    assert context["envelope"]["skills"] == context["envelope"]["memory_entries"] == []
    limit = len(output)
    exact = compiled(workspace, max_bytes=limit)
    assert len(exact) == limit
    with pytest.raises(MutationError, match="budget_exceeded"):
        compiled(workspace, max_bytes=limit - 1)
    assert database.read_bytes() == before


@pytest.mark.parametrize("field", ["work_id", "workspace_id", "process_id"])
def test_foreign_identity_has_no_disclosure(workspace: Path, field: str) -> None:
    good = query_for(workspace)
    caller = confirm(workspace, good)
    bad = good.model_copy(update={field: uuid4()})
    with pytest.raises(MutationError):
        open_work(workspace, bad, caller)
    if field == "process_id":
        with pytest.raises(MutationError, match="scope"):
            open_work(workspace, bad, confirm(workspace, bad))
    assert read_records(workspace).state_revision == good.expected_revision


def test_exact_caller_budget_path_and_no_self_authority(workspace: Path) -> None:
    query = query_for(workspace)
    with pytest.raises(MutationError, match="permission_denied"):
        open_work(workspace, query)
    with pytest.raises(ValidationError):
        ContextQuery.model_validate(query.model_dump() | {"approved": True})
    caller = confirm(workspace, query)
    with pytest.raises(MutationError, match="permission_denied"):
        open_work(workspace, query.model_copy(update={"max_bytes": 100000}), caller)
    copy = workspace.parent / "another-selected-copy"
    shutil.copytree(workspace, copy)
    with pytest.raises(MutationError, match="permission_denied"):
        open_work(copy, query, caller)
    assert compiled(workspace)


@pytest.mark.parametrize("change", ["set_work_requirements", "revoke_work", "cancel_work"])
def test_current_rights_terminal_and_stale(workspace: Path, change: str) -> None:
    query = query_for(workspace)
    caller = confirm(workspace, query)
    if change == "set_work_requirements":
        mutate(workspace, change, requirements=("New requirement",))
    else:
        mutate(workspace, change)
    expected = "conflict" if change == "set_work_requirements" else "permission_denied"
    before = read_workspace(workspace).database.read_bytes()
    with pytest.raises(MutationError, match=expected):
        open_work(workspace, query, caller)
    if change == "set_work_requirements":
        assert "New requirement" in compiled(workspace).decode()
    else:
        with pytest.raises(MutationError, match="permission_denied"):
            compiled(workspace)
    assert read_workspace(workspace).database.read_bytes() == before


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_late_content_failure_despite_saved_receipt(workspace: Path, damage: str) -> None:
    ref = read_handoffs(workspace)[0].handoff.basis[0]
    content = read_artifact(workspace, ref.artifact_id, ref.version_id)
    file = workspace / content.version.relative_path
    if damage == "missing":
        file.unlink()
    else:
        file.write_bytes(b"x" * len(content.content))
    with pytest.raises(ArtifactError):
        compiled(workspace)
    assert len(read_handoffs(workspace)) == 2


@pytest.mark.parametrize("field", ["artifact_id", "version_id", "sha256"])
def test_exact_reference_scope_is_not_transitive_authority(workspace: Path, field: str) -> None:
    ref = read_handoffs(workspace)[0].handoff.result
    bad = ref.model_copy(update={field: "0" * 64 if field == "sha256" else uuid4()})
    before = read_workspace(workspace).database.read_bytes()
    with pytest.raises(WorkspaceError):
        compiled(workspace, references=(bad,))
    assert read_workspace(workspace).database.read_bytes() == before


def test_publication_closure_and_inert_foreign_link(workspace: Path) -> None:
    # One foreign file, no second Process. Link text cannot confer read authority.
    sentinel = workspace.parent / "foreign-context.txt"
    secret = b"FICTIONAL_FOREIGN_CONTENT_MUST_NOT_BE_DISCLOSED"
    sentinel.write_bytes(secret)
    old = read_handoffs(workspace)[0].handoff.result
    mutate(workspace, "authorize_artifact")
    first = b"Intermediate mandatory dependency"
    mutate(workspace, "publish_artifact", content=first, references=(old,))
    descriptor = read_artifact(workspace, old.artifact_id).version
    ref = ArtifactReference(
        artifact_id=descriptor.artifact_id, version_id=descriptor.id, sha256=descriptor.sha256
    )
    content = ("Foreign link is data: " + sentinel.as_uri()).encode()
    mutate(workspace, "publish_artifact", content=content, references=(ref,))
    output = compiled(workspace)
    decoded = [
        base64.b64decode(s["data"]["content_base64"])
        for s in json.loads(output)["context"]["sources"]
        if "content_base64" in s["data"]
    ]
    assert first in decoded and content in decoded and secret not in decoded
    assert all(secret not in data for data in decoded)
    assert len(decoded) == 4


@pytest.mark.parametrize("change", ["decision", "rights", "requirements", "bytes"])
def test_dependency_changes_during_compilation_refuse(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    from zaratustra.core import context

    original = context._compile

    def interleaved(*args: Any, **kwargs: Any) -> Any:
        package = original(*args, **kwargs)
        if change == "decision":
            value = read_handoffs(workspace)[-1].handoff.model_dump(mode="json")
            value.update(
                handoff_id=str(uuid4()),
                source_revision=query_for(workspace).expected_revision,
                owner_instruction="Different fictional accepted decision",
            )
            request = handoff_request(
                json.dumps(value).encode(), source_ref="fixture:changed-decision"
            )
            apply_mutation(workspace, request, confirm(workspace, request))
        elif change == "rights":
            mutate(workspace, "revoke_work")
        elif change == "requirements":
            mutate(workspace, "set_work_requirements", requirements=("Changed dependency",))
        else:
            ref = read_handoffs(workspace)[0].handoff.result
            content = read_artifact(workspace, ref.artifact_id, ref.version_id)
            (workspace / content.version.relative_path).unlink()
        return package

    monkeypatch.setattr(context, "_compile", interleaved)
    with pytest.raises(WorkspaceError):
        compiled(workspace)
    assert read_records(workspace).state_revision >= 11


def test_final_busy_refuses_and_never_mutates(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zaratustra.core import context

    original = context._compile
    database = read_workspace(workspace).database
    before = database.read_bytes()
    lock = sqlite3.connect(database, autocommit=True)

    def locked(*args: Any, **kwargs: Any) -> Any:
        package = original(*args, **kwargs)
        lock.execute("BEGIN IMMEDIATE")
        return package

    monkeypatch.setattr(context, "_compile", locked)
    try:
        with pytest.raises(WorkspaceError, match="locked"):
            compiled(workspace)
    finally:
        lock.execute("ROLLBACK")
        lock.close()
    assert database.read_bytes() == before


def test_unsupported_completed_value_cannot_open(workspace: Path) -> None:
    work = next(row for row in read_records(workspace).records if isinstance(row, Work))
    with pytest.raises(ValidationError):
        Work.model_validate(work.model_dump() | {"status": "done"})
    assert work.status == "ready"
