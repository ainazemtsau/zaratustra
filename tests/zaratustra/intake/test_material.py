"""Incoming material identity, authority, integrity and partial-effect checks."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from zaratustra.core import (
    Artifact,
    ArtifactReference,
    InitialRecords,
    MutationError,
    MutationRequest,
    Process,
    Work,
    apply_mutation,
    authorize_local,
    create_initial_records,
    init_workspace,
    migrate_workspace,
    prepare_authorization,
    read_artifact,
    read_handoffs,
    read_records,
)
from zaratustra.intake import (
    MAX_INTAKE_BYTES,
    MAX_MATERIAL_BYTES,
    IncompleteIntakeError,
    IntakeError,
    IntakeSelection,
    authorize_material_intake,
    execute_material_intake,
    prepare_material_intake,
    preview_bytes,
)
from zaratustra.local import confirm_material_intake_on_console


@dataclass(frozen=True)
class Scenario:
    path: Path
    selection: IntakeSelection
    artifact_id: UUID
    basis: ArtifactReference | None


def confirm(path: Path, request: MutationRequest) -> Any:
    return authorize_local(
        prepare_authorization(path, request),
        channel="local-chat",
        actor="generic-intake-test",
        source_ref="explicit-test-permission",
    )


def request(path: Path, work_id: UUID, operation: str, **values: object) -> MutationRequest:
    snapshot = read_records(path)
    return MutationRequest.model_validate(
        dict(
            operation_id=uuid4(),
            workspace_id=snapshot.workspace_id,
            work_id=work_id,
            expected_revision=snapshot.state_revision,
            operation=operation,
            provenance="New generic intake test",
        )
        | values
    )


def bootstrap(tmp_path: Path, *, artifact_rights: bool = True, with_basis: bool = True) -> Scenario:
    path = tmp_path / "workspace"
    path.mkdir(parents=True)
    init_workspace(path)
    migrate_workspace(path, target_version=7)
    snapshot = create_initial_records(
        path,
        InitialRecords(
            process_title="Generic reading queue",
            goal="Compare a new generic report with an exact saved note",
            expected_result="One accepted generic report",
            acceptance=("Exact new text is retained",),
            boundaries=("Generic data only",),
            budget="One local intake",
            artifact_title="Generic report",
        ),
    )
    process = next(row for row in snapshot.records if isinstance(row, Process))
    work = next(row for row in snapshot.records if isinstance(row, Work))
    artifact = next(row for row in snapshot.records if isinstance(row, Artifact))
    authorize_work = request(path, work.id, "authorize_work")
    apply_mutation(path, authorize_work, confirm(path, authorize_work))
    basis = None
    if artifact_rights:
        authorize_artifact = request(
            path,
            work.id,
            "authorize_artifact",
            version=2,
            artifact_id=artifact.id,
            artifact_revision=artifact.revision,
        )
        apply_mutation(path, authorize_artifact, confirm(path, authorize_artifact))
        if with_basis:
            content = b"Generic saved basis, revision one.\n"
            publish = request(
                path,
                work.id,
                "publish_artifact",
                version=2,
                artifact_id=artifact.id,
                artifact_revision=artifact.revision,
                content_sha256=hashlib.sha256(content).hexdigest(),
                content_size=len(content),
            )
            apply_mutation(path, publish, confirm(path, publish), content=content)
            basis = ArtifactReference(
                artifact_id=artifact.id,
                version_id=publish.operation_id,
                sha256=hashlib.sha256(content).hexdigest(),
            )
    return Scenario(
        path=path,
        selection=IntakeSelection(
            workspace_id=snapshot.workspace_id,
            process_id=process.id,
            work_id=work.id,
        ),
        artifact_id=artifact.id,
        basis=basis,
    )


def envelope(scenario: Scenario, **changes: object) -> bytes:
    value: dict[str, object] = dict(
        kind="external_material",
        version=1,
        intake_id=str(uuid4()),
        publication_id=str(uuid4()),
        acceptance_id=str(uuid4()),
        workspace_id=str(scenario.selection.workspace_id),
        process_id=str(scenario.selection.process_id),
        work_id=str(scenario.selection.work_id),
        artifact_id=str(scenario.artifact_id),
        source_revision=read_records(scenario.path).state_revision,
        basis=([] if scenario.basis is None else [scenario.basis.model_dump(mode="json")]),
        material="New generic external report.\nExact line two.\n",
        provenance="Explicit generic external file",
        owner_instruction="Review only the displayed exact change.",
        constraints=["No personal material"],
        open_questions=["A later increment handles durable replay"],
        created_by="generic-external-author",
    )
    return json.dumps(value | changes, ensure_ascii=False).encode("utf-8")


def prepared(scenario: Scenario, content: bytes | None = None) -> Any:
    return prepare_material_intake(
        scenario.path,
        scenario.selection,
        envelope(scenario) if content is None else content,
        source_ref="new-generic-report.json",
    )


def authorize(value: Any) -> Any:
    return authorize_material_intake(
        value,
        channel="local-chat",
        actor="generic-intake-test",
        source_ref="explicit-review-of-complete-preview",
    )


def test_exact_new_material_is_previewed_published_accepted_and_not_completed(
    tmp_path: Path,
) -> None:
    scenario = bootstrap(tmp_path)
    value = prepared(scenario)
    original = read_records(scenario.path)
    assert value.preview.material == value.envelope.material
    assert value.preview.target.original_revision == original.state_revision
    assert value.preview.current_active_version == scenario.basis
    assert value.preview.basis == (scenario.basis,)
    assert value.preview.publication_request.expected_revision == original.state_revision
    assert value.preview.acceptance_request.expected_revision == original.state_revision + 1
    assert value.preview.acceptance_request.handoff is not None
    assert value.preview.acceptance_request.handoff.source_revision == original.state_revision + 1
    assert hashlib.sha256(preview_bytes(value)).hexdigest() == value.preview_sha256

    receipt = execute_material_intake(value, authorize(value))

    assert receipt.received.envelope_sha256 == hashlib.sha256(value.input_bytes).hexdigest()
    assert receipt.received.material_sha256 == hashlib.sha256(value.material_bytes).hexdigest()
    assert receipt.publication.operation_id == value.envelope.publication_id
    assert receipt.acceptance.operation_id == value.envelope.acceptance_id
    assert receipt.publication.event_id != receipt.acceptance.event_id
    assert receipt.publication.new_revision + 1 == receipt.acceptance.new_revision
    assert receipt.completion.status == "not_requested"
    assert receipt.completion.result_operation_id is None
    assert receipt.continuation.state == "selected_work_ready"
    saved = read_artifact(scenario.path, scenario.artifact_id, value.envelope.publication_id)
    assert saved.content == value.material_bytes
    (accepted,) = read_handoffs(scenario.path)
    assert accepted.handoff.result == ArtifactReference(
        artifact_id=scenario.artifact_id,
        version_id=value.envelope.publication_id,
        sha256=receipt.received.material_sha256,
    )
    assert accepted.handoff.basis == (scenario.basis,)
    final = read_records(scenario.path)
    work = next(row for row in final.records if isinstance(row, Work))
    process = next(row for row in final.records if isinstance(row, Process))
    assert final.state_revision == original.state_revision + 2
    assert work.status == "ready" and work.completion_id is None
    assert process.pack_binding is None and work.pack_binding is None


def test_first_material_creates_missing_version_reference_through_core(tmp_path: Path) -> None:
    scenario = bootstrap(tmp_path, with_basis=False)
    value = prepared(scenario)
    assert value.preview.current_active_version is None and value.preview.basis == ()
    receipt = execute_material_intake(value, authorize(value))
    saved = read_artifact(scenario.path, scenario.artifact_id, receipt.publication.operation_id)
    assert saved.content == value.material_bytes
    assert (
        read_handoffs(scenario.path)[0].handoff.result.version_id
        == receipt.publication.operation_id
    )


@pytest.mark.parametrize("field", ["workspace_id", "process_id", "work_id", "artifact_id"])
def test_external_identity_cannot_redirect_selected_work(tmp_path: Path, field: str) -> None:
    scenario = bootstrap(tmp_path)
    before = read_records(scenario.path)
    with pytest.raises(IntakeError, match="target_mismatch"):
        prepared(scenario, envelope(scenario, **{field: str(uuid4())}))
    assert read_records(scenario.path) == before


def test_revision_rights_terminal_and_basis_integrity_are_current(tmp_path: Path) -> None:
    no_rights = bootstrap(tmp_path / "rights", artifact_rights=False)
    with pytest.raises(IntakeError, match="permission_denied"):
        prepared(no_rights)

    stale = bootstrap(tmp_path / "stale")
    with pytest.raises(IntakeError, match="stale_basis"):
        prepared(
            stale, envelope(stale, source_revision=read_records(stale.path).state_revision - 1)
        )

    terminal = bootstrap(tmp_path / "terminal")
    cancel = request(terminal.path, terminal.selection.work_id, "cancel_work")
    apply_mutation(terminal.path, cancel, confirm(terminal.path, cancel))
    with pytest.raises(IntakeError, match="permission_denied"):
        prepared(terminal)

    damaged = bootstrap(tmp_path / "damaged")
    assert damaged.basis is not None
    saved = read_artifact(damaged.path, damaged.artifact_id, damaged.basis.version_id)
    (damaged.path / saved.version.relative_path).write_bytes(b"x" * len(saved.content))
    with pytest.raises(IntakeError, match="invalid_basis"):
        prepared(damaged)


@pytest.mark.parametrize(
    "content",
    [
        b'{"kind":"external_material","kind":"external_material"}',
        b"\xff",
        b"{}",
    ],
)
def test_malformed_external_data_grants_nothing(tmp_path: Path, content: bytes) -> None:
    scenario = bootstrap(tmp_path)
    before = read_records(scenario.path)
    with pytest.raises(IntakeError, match="invalid_envelope"):
        prepared(scenario, content)
    assert read_records(scenario.path) == before


def test_asserted_approval_boolean_and_real_size_limits_are_refused(tmp_path: Path) -> None:
    scenario = bootstrap(tmp_path)
    with pytest.raises(IntakeError, match="invalid_envelope"):
        prepared(scenario, envelope(scenario, approved=True))
    with pytest.raises(IntakeError, match="invalid_envelope"):
        prepared(scenario, envelope(scenario, source_revision=True))
    with pytest.raises(IntakeError, match="input_too_large"):
        prepared(scenario, b"x" * (MAX_INTAKE_BYTES + 1))
    with pytest.raises(IntakeError, match="material_too_large"):
        prepared(scenario, envelope(scenario, material="x" * (MAX_MATERIAL_BYTES + 1)))


@pytest.mark.parametrize("change", ["material", "basis", "path"])
def test_old_confirmation_cannot_follow_changed_payload_basis_or_target(
    tmp_path: Path, change: str
) -> None:
    scenario = bootstrap(tmp_path)
    first = prepared(scenario)
    approval = authorize(first)
    if change == "material":
        changed = prepared(scenario, envelope(scenario, material="Different generic report.\n"))
    elif change == "basis":
        changed = prepared(scenario, envelope(scenario, basis=[]))
    else:
        copied = tmp_path / "copied-workspace"
        shutil.copytree(scenario.path, copied)
        changed = prepare_material_intake(
            copied,
            scenario.selection,
            first.input_bytes,
            source_ref=first.source_ref,
        )
    before = read_records(changed.workspace)
    with pytest.raises(IntakeError, match="permission_denied"):
        execute_material_intake(changed, approval)
    assert read_records(changed.workspace) == before


def test_foreign_change_is_not_silently_refreshed_after_preview(tmp_path: Path) -> None:
    scenario = bootstrap(tmp_path)
    value = prepared(scenario)
    approval = authorize(value)
    foreign = request(
        scenario.path,
        scenario.selection.work_id,
        "set_work_requirements",
        requirements=("A later caller changed the Work",),
    )
    apply_mutation(scenario.path, foreign, confirm(scenario.path, foreign))
    changed = read_records(scenario.path)
    with pytest.raises(IntakeError, match="stale_basis"):
        execute_material_intake(value, approval)
    assert read_records(scenario.path) == changed


def test_missing_trusted_confirmation_and_changed_preview_refuse_without_effect(
    tmp_path: Path,
) -> None:
    scenario = bootstrap(tmp_path)
    value = prepared(scenario)
    before = read_records(scenario.path)
    with pytest.raises(IntakeError, match="permission_denied"):
        execute_material_intake(value)
    altered = replace(
        value,
        preview=value.preview.model_copy(update={"material": "Changed after confirmation"}),
    )
    with pytest.raises(IntakeError, match="permission_denied"):
        execute_material_intake(altered, authorize(value))
    assert read_records(scenario.path) == before


def test_partial_acceptance_failure_reports_committed_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = bootstrap(tmp_path)
    value = prepared(scenario)
    original_apply = apply_mutation
    calls = 0

    def fail_second(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise MutationError("injected", "acceptance did not run")
        return original_apply(*args, **kwargs)

    monkeypatch.setattr("zaratustra.intake.apply_mutation", fail_second)
    with pytest.raises(IncompleteIntakeError) as failure:
        execute_material_intake(value, authorize(value))
    assert failure.value.stage == "acceptance"
    assert failure.value.progress.publication is not None
    assert failure.value.progress.acceptance is None
    assert failure.value.progress.completion.status == "not_requested"
    assert failure.value.unregistered_bytes_possible is False
    assert read_artifact(scenario.path, scenario.artifact_id, value.envelope.publication_id).content
    assert read_handoffs(scenario.path) == ()


def test_projection_errors_report_both_committed_domain_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = bootstrap(tmp_path)
    value = prepared(scenario)

    def fail_projection(*args: object, **kwargs: object) -> None:
        raise OSError("injected projection failure")

    monkeypatch.setattr("zaratustra.core.mutations.rebuild_projections", fail_projection)
    receipt = execute_material_intake(value, authorize(value))
    assert receipt.publication.operation_id == value.envelope.publication_id
    assert receipt.acceptance.operation_id == value.envelope.acceptance_id
    assert len(receipt.warnings) == 2
    assert read_artifact(scenario.path, scenario.artifact_id, value.envelope.publication_id).content
    assert read_handoffs(scenario.path)[0].handoff.handoff_id == value.envelope.acceptance_id


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_console_confirmation_displays_complete_preview_and_requires_exact_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = bootstrap(tmp_path)
    value = prepared(scenario)
    output = Terminal()
    monkeypatch.setattr("sys.stdin", Terminal(f"approve {value.preview_sha256}\n"))
    monkeypatch.setattr("sys.stderr", output)
    approval = confirm_material_intake_on_console(value)
    assert approval.preview_sha256 == value.preview_sha256
    monkeypatch.setattr("sys.stdin", io.StringIO(f"approve {value.preview_sha256}\n"))
    with pytest.raises(MutationError, match="permission_denied"):
        confirm_material_intake_on_console(value)
