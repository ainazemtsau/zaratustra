"""Incoming material identity, authority, integrity and partial-effect checks."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
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
    NextWork,
    Process,
    ResultSubmission,
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
    submit_result,
)
from zaratustra.intake import (
    MAX_INTAKE_BYTES,
    MAX_MATERIAL_BYTES,
    IncompleteIntakeError,
    IntakeError,
    IntakeSelection,
    authorize_material_intake,
    execute_material_intake,
    inspect_material_intake_progress,
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


@pytest.mark.parametrize("invalid_version", [True, 1.0, "1"])
def test_envelope_version_is_exact_strict_integer_one(
    tmp_path: Path, invalid_version: object
) -> None:
    scenario = bootstrap(tmp_path)
    accepted = prepared(scenario, envelope(scenario, version=1))
    before = read_records(scenario.path)
    assert accepted.envelope.version == 1
    with pytest.raises(IntakeError, match="invalid_envelope"):
        prepared(scenario, envelope(scenario, version=invalid_version))
    assert read_records(scenario.path) == before


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


def test_completed_transfer_repeats_with_original_receipts_and_one_effect(
    tmp_path: Path,
) -> None:
    scenario = bootstrap(tmp_path)
    content = envelope(scenario)
    value = prepared(scenario, content)
    first = execute_material_intake(value, authorize(value))
    after = read_records(scenario.path)

    recovered = prepared(scenario, content)
    second = execute_material_intake(recovered, authorize(recovered))

    assert second.publication == first.publication
    assert second.acceptance == first.acceptance
    assert second.continuation == first.continuation
    assert second.current_continuation.state == "selected_work_ready"
    assert read_records(scenario.path) == after
    assert len(read_handoffs(scenario.path)) == 1
    inspection = inspect_material_intake_progress(scenario.path, value.envelope.intake_id)
    assert inspection is not None
    assert inspection.claimed_stages == ("publication", "acceptance")
    assert inspection.trust == "unverified_coordinator_journal"
    assert inspection.authorization_required_for_recovery is True
    assert "receipt" not in inspection.model_dump_json()
    assert value.envelope.material not in inspection.model_dump_json()


@pytest.mark.parametrize("change", ["material", "target", "basis"])
def test_changed_intent_under_completed_intake_identity_is_refused(
    tmp_path: Path, change: str
) -> None:
    scenario = bootstrap(tmp_path)
    content = envelope(scenario)
    value = prepared(scenario, content)
    execute_material_intake(value, authorize(value))
    body = json.loads(content)
    if change == "material":
        body["material"] = "Changed report under an old identity.\n"
    elif change == "target":
        body["artifact_id"] = str(uuid4())
    else:
        body["basis"] = []
    changed = json.dumps(body).encode()
    before = read_records(scenario.path)
    with pytest.raises(IntakeError, match="intake_collision|target_mismatch"):
        prepared(scenario, changed)
    assert read_records(scenario.path) == before


def test_publication_commit_survives_missing_progress_update_and_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = bootstrap(tmp_path)
    content = envelope(scenario)
    value = prepared(scenario, content)
    original_save = __import__("zaratustra.intake", fromlist=["_save_journal"])._save_journal

    def fail_after_publication(path: Path, journal: Any) -> None:
        if journal.publication is not None:
            raise IntakeError("injected", "publication progress reply was lost")
        original_save(path, journal)

    monkeypatch.setattr("zaratustra.intake._save_journal", fail_after_publication)
    with pytest.raises(IncompleteIntakeError) as failure:
        execute_material_intake(value, authorize(value))
    assert failure.value.stage == "acceptance"
    assert failure.value.progress.publication is not None
    assert read_handoffs(scenario.path) == ()
    committed = read_records(scenario.path)
    monkeypatch.setattr("zaratustra.intake._save_journal", original_save)

    recovered = prepared(scenario, content)
    receipt = execute_material_intake(recovered, authorize(recovered))
    assert receipt.publication == failure.value.progress.publication
    assert receipt.acceptance.new_revision == receipt.publication.new_revision + 1
    assert read_records(scenario.path).state_revision == committed.state_revision + 1
    assert len(read_handoffs(scenario.path)) == 1


def test_acceptance_commit_survives_lost_progress_and_final_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = bootstrap(tmp_path)
    content = envelope(scenario)
    value = prepared(scenario, content)
    original_save = __import__("zaratustra.intake", fromlist=["_save_journal"])._save_journal

    def fail_after_acceptance(path: Path, journal: Any) -> None:
        if journal.acceptance is not None:
            raise IntakeError("injected", "acceptance response was lost")
        original_save(path, journal)

    monkeypatch.setattr("zaratustra.intake._save_journal", fail_after_acceptance)
    with pytest.raises(IncompleteIntakeError) as failure:
        execute_material_intake(value, authorize(value))
    assert failure.value.stage == "continuation"
    assert failure.value.progress.acceptance is not None
    accepted_state = read_records(scenario.path)
    monkeypatch.setattr("zaratustra.intake._save_journal", original_save)

    recovered = prepared(scenario, content)
    receipt = execute_material_intake(recovered, authorize(recovered))
    assert receipt.publication == failure.value.progress.publication
    assert receipt.acceptance == failure.value.progress.acceptance
    assert read_records(scenario.path) == accepted_state
    assert len(read_handoffs(scenario.path)) == 1


def test_lost_final_response_after_saved_progress_replays_without_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = bootstrap(tmp_path)
    content = envelope(scenario)
    value = prepared(scenario, content)
    original_current = __import__(
        "zaratustra.intake", fromlist=["_current_continuation"]
    )._current_continuation

    def lose_final_response(*args: Any, **kwargs: Any) -> Any:
        raise OSError("injected final response loss")

    monkeypatch.setattr("zaratustra.intake._current_continuation", lose_final_response)
    with pytest.raises(IncompleteIntakeError) as failure:
        execute_material_intake(value, authorize(value))
    assert failure.value.stage == "continuation"
    assert failure.value.progress.acceptance is not None
    accepted_state = read_records(scenario.path)
    inspection = inspect_material_intake_progress(scenario.path, value.envelope.intake_id)
    assert inspection is not None and inspection.claimed_stages == ("publication", "acceptance")
    monkeypatch.setattr("zaratustra.intake._current_continuation", original_current)

    recovered = prepared(scenario, content)
    receipt = execute_material_intake(recovered, authorize(recovered))
    assert receipt.acceptance == failure.value.progress.acceptance
    assert read_records(scenario.path) == accepted_state
    assert len(read_handoffs(scenario.path)) == 1


def test_authoritative_receipts_recover_when_journal_is_absent(tmp_path: Path) -> None:
    scenario = bootstrap(tmp_path)
    content = envelope(scenario)
    value = prepared(scenario, content)
    first = execute_material_intake(value, authorize(value))
    journal = scenario.path / "inbox" / "transfers" / f"{value.envelope.intake_id}.json"
    journal.unlink()
    assert inspect_material_intake_progress(scenario.path, value.envelope.intake_id) is None
    before = read_records(scenario.path)

    recovered = prepared(scenario, content)
    second = execute_material_intake(recovered, authorize(recovered))
    assert second.publication == first.publication
    assert second.acceptance == first.acceptance
    assert read_records(scenario.path) == before
    assert len(read_handoffs(scenario.path)) == 1


def test_malformed_and_inconsistent_progress_are_refused_safely(tmp_path: Path) -> None:
    malformed = bootstrap(tmp_path / "malformed")
    malformed_content = envelope(malformed)
    malformed_value = prepared(malformed, malformed_content)
    transfer_dir = malformed.path / "inbox" / "transfers"
    transfer_dir.mkdir()
    malformed_path = transfer_dir / f"{malformed_value.envelope.intake_id}.json"
    malformed_path.write_text("{not-json", encoding="utf-8")
    before = read_records(malformed.path)
    with pytest.raises(IntakeError, match="progress_invalid"):
        prepared(malformed, malformed_content)
    assert read_records(malformed.path) == before

    inconsistent = bootstrap(tmp_path / "inconsistent")
    inconsistent_content = envelope(inconsistent)
    inconsistent_value = prepared(inconsistent, inconsistent_content)
    execute_material_intake(inconsistent_value, authorize(inconsistent_value))
    journal_path = (
        inconsistent.path / "inbox" / "transfers" / f"{inconsistent_value.envelope.intake_id}.json"
    )
    body = json.loads(journal_path.read_bytes())
    body["publication"]["event_id"] = str(uuid4())
    journal_path.write_text(json.dumps(body), encoding="utf-8")
    recovered = prepared(inconsistent, inconsistent_content)
    with pytest.raises(IntakeError, match="progress_invalid"):
        execute_material_intake(recovered, authorize(recovered))


def test_failure_before_first_effect_saves_no_false_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = bootstrap(tmp_path)
    value = prepared(scenario)
    before = read_records(scenario.path)

    def fail_before_effect(*args: Any, **kwargs: Any) -> Any:
        raise MutationError("injected", "no effect ran")

    monkeypatch.setattr("zaratustra.intake.apply_mutation", fail_before_effect)
    with pytest.raises(IncompleteIntakeError) as failure:
        execute_material_intake(value, authorize(value))
    assert failure.value.stage == "publication"
    assert failure.value.progress.publication is None
    assert read_records(scenario.path) == before
    inspection = inspect_material_intake_progress(scenario.path, value.envelope.intake_id)
    assert inspection is not None and inspection.claimed_stages == ()


def test_unregistered_publication_file_is_reused_but_not_claimed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = bootstrap(tmp_path)
    content = envelope(scenario)
    value = prepared(scenario, content)
    connect = sqlite3.connect

    def failing_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = connect(*args, **kwargs)

        def block(action: int, target: str | None, *_: object) -> int:
            if (action, target) == (sqlite3.SQLITE_INSERT, "artifact_versions"):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(block)
        return connection

    before = read_records(scenario.path)
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", failing_connect)
        with pytest.raises(IncompleteIntakeError) as failure:
            execute_material_intake(value, authorize(value))
    assert failure.value.unregistered_bytes_possible is True
    assert failure.value.progress.publication is None
    assert read_records(scenario.path) == before

    receipt = execute_material_intake(prepared(scenario, content), authorize(value))
    assert receipt.publication.previous_revision == before.state_revision
    assert len(read_handoffs(scenario.path)) == 1


def test_unrelated_change_after_publication_is_not_adopted_as_acceptance_basis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = bootstrap(tmp_path)
    content = envelope(scenario)
    value = prepared(scenario, content)
    original_apply = apply_mutation
    calls = 0

    def stop_acceptance(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise MutationError("injected", "acceptance paused")
        return original_apply(*args, **kwargs)

    monkeypatch.setattr("zaratustra.intake.apply_mutation", stop_acceptance)
    with pytest.raises(IncompleteIntakeError):
        execute_material_intake(value, authorize(value))
    monkeypatch.setattr("zaratustra.intake.apply_mutation", original_apply)
    foreign = request(
        scenario.path,
        scenario.selection.work_id,
        "set_work_requirements",
        requirements=("Unrelated current change",),
    )
    apply_mutation(scenario.path, foreign, confirm(scenario.path, foreign))
    before = read_records(scenario.path)

    resumed = prepared(scenario, content)
    with pytest.raises(IntakeError, match="stale_basis"):
        execute_material_intake(resumed, authorize(resumed))
    assert read_records(scenario.path) == before
    assert read_handoffs(scenario.path) == ()


def test_completed_work_reports_saved_result_without_resurrection(tmp_path: Path) -> None:
    scenario = bootstrap(tmp_path)
    content = envelope(scenario)
    value = prepared(scenario, content)
    transfer = execute_material_intake(value, authorize(value))
    accepted = read_handoffs(scenario.path)[0]
    state = read_records(scenario.path)
    result = MutationRequest(
        version=4,
        operation_id=uuid4(),
        workspace_id=state.workspace_id,
        work_id=scenario.selection.work_id,
        expected_revision=state.state_revision,
        operation="submit_result",
        provenance="Generic standard completion after material transfer",
        references=(accepted.handoff.result,),
        submission=ResultSubmission(
            source_revision=state.state_revision,
            result=accepted.handoff.result,
            acceptance_ids=(accepted.handoff.handoff_id,),
            next_work=NextWork(
                work_id=uuid4(),
                artifact_id=uuid4(),
                goal="Review the saved generic continuation",
                expected_result="One bounded generic follow-up",
                acceptance=("The saved continuation remains explicit",),
                boundaries=("No external action",),
                budget="One local follow-up",
                executor_requirements=(),
                artifact_title="Generic follow-up",
                authority_scope="work_metadata",
            ),
        ),
    )
    submit_result(scenario.path, result, confirm(scenario.path, result))
    terminal = read_records(scenario.path)

    recovered = prepared(scenario, content)
    receipt = execute_material_intake(recovered, authorize(recovered))
    assert receipt.publication == transfer.publication
    assert receipt.acceptance == transfer.acceptance
    assert receipt.continuation.state == "selected_work_ready"
    assert receipt.continuation.at_revision == transfer.acceptance.new_revision
    assert receipt.current_continuation.state == "saved_result"
    assert receipt.current_continuation.result_operation_id == result.operation_id
    assert result.submission is not None
    assert receipt.current_continuation.next_work_id == result.submission.next_work.work_id
    assert read_records(scenario.path) == terminal


def test_receipt_recovery_requires_current_metadata_rights(tmp_path: Path) -> None:
    scenario = bootstrap(tmp_path)
    content = envelope(scenario)
    value = prepared(scenario, content)
    execute_material_intake(value, authorize(value))
    revoke = request(scenario.path, scenario.selection.work_id, "revoke_work")
    apply_mutation(scenario.path, revoke, confirm(scenario.path, revoke))
    inspection = inspect_material_intake_progress(scenario.path, value.envelope.intake_id)
    assert inspection is not None and inspection.claimed_stages == ("publication", "acceptance")

    recovered = prepared(scenario, content)
    with pytest.raises(MutationError, match="permission_denied"):
        execute_material_intake(recovered, authorize(recovered))


def test_cooperating_simultaneous_retry_serializes_to_one_transfer(tmp_path: Path) -> None:
    scenario = bootstrap(tmp_path)
    content = envelope(scenario)
    first = prepared(scenario, content)
    second = prepared(scenario, content)
    approvals = (authorize(first), authorize(second))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = (
            pool.submit(execute_material_intake, first, approvals[0]),
            pool.submit(execute_material_intake, second, approvals[1]),
        )
        receipts = tuple(future.result(timeout=20) for future in futures)
    assert receipts[0].publication == receipts[1].publication
    assert receipts[0].acceptance == receipts[1].acceptance
    assert len(read_handoffs(scenario.path)) == 1
