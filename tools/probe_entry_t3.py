"""Reproduce installed exact preview, publication and acceptance of new generic material."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from zaratustra.core import LocalAuthorization, MutationRequest

ROOT = Path(__file__).resolve().parents[1]


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + chr(10),
        encoding="utf-8",
    )


def confirm(path: Path, request: MutationRequest) -> LocalAuthorization:
    from zaratustra.core import authorize_local, prepare_authorization

    return authorize_local(
        prepare_authorization(path, request),
        channel="local-chat",
        actor="generic-installed-intake-demo",
        source_ref="explicit-permission-in-disposable-installed-demo",
    )


def request(path: Path, work_id: UUID, operation: str, **values: object) -> MutationRequest:
    from zaratustra.core import MutationRequest, read_records

    snapshot = read_records(path)
    return MutationRequest.model_validate(
        dict(
            operation_id=uuid4(),
            workspace_id=snapshot.workspace_id,
            work_id=work_id,
            expected_revision=snapshot.state_revision,
            operation=operation,
            provenance="New installed generic intake demo",
        )
        | values
    )


def exercise(base: Path) -> dict[str, Any]:
    from zaratustra.core import (
        Artifact,
        ArtifactReference,
        InitialRecords,
        Process,
        Work,
        apply_mutation,
        create_initial_records,
        init_workspace,
        inspect_artifacts,
        migrate_workspace,
        read_artifact,
        read_handoffs,
        read_records,
    )
    from zaratustra.entry import add_entry, resolve_entry, source_path
    from zaratustra.intake import (
        IntakeError,
        IntakeSelection,
        authorize_material_intake,
        execute_material_intake,
        prepare_material_intake,
    )

    workspace = base / "workspace"
    catalog = base / "catalog.json"
    external = base / "incoming" / "generic-report.json"
    workspace.mkdir()
    init_workspace(workspace)
    migrate_workspace(workspace, target_version=7)
    snapshot = create_initial_records(
        workspace,
        InitialRecords(
            process_title="Generic research notes",
            goal="Receive one exact new external report",
            expected_result="One published and accepted generic report",
            acceptance=("Exact incoming text and basis are retained",),
            boundaries=("Generic demonstration data only",),
            budget="One installed local demonstration",
            artifact_title="Generic research report",
        ),
    )
    process = next(row for row in snapshot.records if isinstance(row, Process))
    work = next(row for row in snapshot.records if isinstance(row, Work))
    artifact = next(row for row in snapshot.records if isinstance(row, Artifact))
    allow_work = request(workspace, work.id, "authorize_work")
    apply_mutation(workspace, allow_work, confirm(workspace, allow_work))
    allow_artifact = request(
        workspace,
        work.id,
        "authorize_artifact",
        version=2,
        artifact_id=artifact.id,
        artifact_revision=artifact.revision,
    )
    apply_mutation(workspace, allow_artifact, confirm(workspace, allow_artifact))
    baseline = b"Existing generic basis before external intake.\n"
    baseline_digest = hashlib.sha256(baseline).hexdigest()
    publish_basis = request(
        workspace,
        work.id,
        "publish_artifact",
        version=2,
        artifact_id=artifact.id,
        artifact_revision=artifact.revision,
        content_sha256=baseline_digest,
        content_size=len(baseline),
    )
    apply_mutation(workspace, publish_basis, confirm(workspace, publish_basis), content=baseline)
    basis = ArtifactReference(
        artifact_id=artifact.id,
        version_id=publish_basis.operation_id,
        sha256=baseline_digest,
    )
    add_entry(catalog, "Generic Research", workspace, work.id, aliases=("research",))
    selected = resolve_entry(catalog, "Generic Research")
    selection = IntakeSelection(
        workspace_id=selected.workspace_id,
        process_id=selected.process_id,
        work_id=selected.work_id,
    )
    selected_workspace = source_path(catalog, selected)
    material = "New external generic report.\nMeasured value: seven sample units.\n"
    state = read_records(workspace)
    envelope_value: dict[str, object] = dict(
        kind="external_material",
        version=1,
        intake_id=str(uuid4()),
        publication_id=str(uuid4()),
        acceptance_id=str(uuid4()),
        workspace_id=str(state.workspace_id),
        process_id=str(process.id),
        work_id=str(work.id),
        artifact_id=str(artifact.id),
        source_revision=state.state_revision,
        basis=[basis.model_dump(mode="json")],
        material=material,
        provenance="New explicit generic external demo material",
        owner_instruction="Accept only after reviewing the exact displayed change.",
        constraints=["No personal data"],
        open_questions=["External provider interaction remains outside this demonstration"],
        created_by="generic-manual-provider",
    )
    external.parent.mkdir()
    external.write_text(
        json.dumps(envelope_value, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8"
    )
    incoming = external.read_bytes()
    incoming_material = material.encode("utf-8")
    incoming_digest = hashlib.sha256(incoming_material).hexdigest()
    before_versions = inspect_artifacts(workspace).versions
    if any(row.version.sha256 == incoming_digest for row in before_versions):
        raise AssertionError("Incoming bytes were already registered before intake")
    prepared = prepare_material_intake(
        selected_workspace, selection, incoming, source_ref=external.as_posix()
    )
    save(base / "evidence" / "preview.json", prepared.preview.model_dump(mode="json"))
    authorization = authorize_material_intake(
        prepared,
        channel="local-chat",
        actor="generic-installed-intake-demo",
        source_ref="explicit-review-of-complete-installed-preview",
    )
    adverse: dict[str, str] = {}
    unchanged = read_records(workspace)
    try:
        execute_material_intake(prepared)
    except IntakeError as error:
        adverse["missing_confirmation"] = error.code
    else:
        raise AssertionError("Input data granted authority")
    altered_value = envelope_value | {"material": "Changed after the trusted preview.\n"}
    altered = prepare_material_intake(
        selected_workspace,
        selection,
        json.dumps(altered_value).encode("utf-8"),
        source_ref=external.as_posix(),
    )
    try:
        execute_material_intake(altered, authorization)
    except IntakeError as error:
        adverse["changed_material"] = error.code
    else:
        raise AssertionError("Old confirmation followed changed material")
    asserted_value = envelope_value | {"approved": True}
    try:
        prepare_material_intake(
            selected_workspace,
            selection,
            json.dumps(asserted_value).encode("utf-8"),
            source_ref=external.as_posix(),
        )
    except IntakeError as error:
        adverse["asserted_approval"] = error.code
    else:
        raise AssertionError("Asserted approval was accepted as envelope data")
    foreign_value = envelope_value | {"work_id": str(uuid4())}
    try:
        prepare_material_intake(
            selected_workspace,
            selection,
            json.dumps(foreign_value).encode("utf-8"),
            source_ref=external.as_posix(),
        )
    except IntakeError as error:
        adverse["foreign_target"] = error.code
    else:
        raise AssertionError("Foreign target was accepted")
    if read_records(workspace) != unchanged:
        raise AssertionError("Adverse preview/authority cases changed the workspace")
    receipt = execute_material_intake(prepared, authorization)
    save(base / "evidence" / "receipt.json", receipt.model_dump(mode="json"))
    final = read_records(workspace)
    saved = read_artifact(workspace, artifact.id, prepared.envelope.publication_id)
    accepted = read_handoffs(workspace)
    final_work = next(row for row in final.records if isinstance(row, Work) and row.id == work.id)
    if (
        saved.content != incoming_material
        or len(accepted) != 1
        or accepted[0].handoff.result.version_id != prepared.envelope.publication_id
        or accepted[0].handoff.basis != (basis,)
        or final_work.status != "ready"
        or final_work.completion_id is not None
    ):
        raise AssertionError("Installed intake effects do not match the exact preview")
    summary = dict(
        scenario="installed-new-external-material-intake",
        schema_version=7,
        catalog_designation=selected.designation,
        original_revision=prepared.envelope.source_revision,
        planned_publication_revision=prepared.preview.publication_request.expected_revision + 1,
        planned_acceptance_revision=prepared.preview.expected_revision_after_acceptance,
        final_revision=final.state_revision,
        preview_sha256=prepared.preview_sha256,
        envelope_sha256=receipt.received.envelope_sha256,
        material_sha256=incoming_digest,
        material_was_unregistered_before=True,
        exact_material_read_after=True,
        exact_basis_accepted=True,
        publication_operation_id=str(receipt.publication.operation_id),
        acceptance_operation_id=str(receipt.acceptance.operation_id),
        distinct_stage_receipts=receipt.publication.event_id != receipt.acceptance.event_id,
        completion_status=receipt.completion.status,
        continuation_state=receipt.continuation.state,
        adverse=adverse,
    )
    save(base / "summary.json", summary)
    return summary


def run(command: list[str], cwd: Path, runs: list[dict[str, Any]]) -> None:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    runs.append(
        dict(
            command=command,
            cwd=str(cwd),
            exit=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    )
    if result.stdout:
        print(result.stdout, end="", flush=True)
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr, flush=True)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command}")


def orchestrate(output: Path) -> dict[str, Any]:
    for name in ("STOP", "STEER.md"):
        if (ROOT / name).exists():
            raise SystemExit(f"STOP: read and resolve {name}")
    target = output.resolve()
    scratch = (ROOT / "_scratch").resolve()
    if target == scratch or not target.is_relative_to(scratch) or target.exists():
        raise SystemExit("Output must be a NEW directory inside this checkout's _scratch")
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("STOP: required tool uv unavailable")
    target.mkdir(parents=True)
    (target / "unrelated-cwd").mkdir()
    runs: list[dict[str, Any]] = []
    run([uv, "build", "--no-sources"], ROOT, runs)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    wheel_name = f"zaratustra-{project['version']}-py3-none-any.whl"
    shutil.copyfile(ROOT / "dist" / wheel_name, target / wheel_name)
    requirements = target / "runtime-requirements.txt"
    run(
        [
            uv,
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--no-hashes",
            "--output-file",
            str(requirements),
        ],
        ROOT,
        runs,
    )
    environment = target / "venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run(
        [
            uv,
            "venv",
            "--python",
            "3.13.7",
            "--python-preference",
            "only-managed",
            str(environment),
        ],
        ROOT,
        runs,
    )
    run(
        [
            uv,
            "pip",
            "install",
            "--offline",
            "--python",
            str(python),
            "-r",
            str(requirements),
            str(target / wheel_name),
        ],
        ROOT,
        runs,
    )
    run([uv, "pip", "check", "--python", str(python)], ROOT, runs)
    exercise_script = target / "exercise.py"
    shutil.copyfile(Path(__file__), exercise_script)
    run(
        [str(python), "-I", str(exercise_script), "--phase", "exercise", "--base", str(target)],
        target / "unrelated-cwd",
        runs,
    )
    save(target / "commands.json", runs)
    return cast(dict[str, Any], json.loads((target / "summary.json").read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--phase", choices=("exercise",))
    parser.add_argument("--base", type=Path)
    args = parser.parse_args(argv)
    if args.phase == "exercise":
        if args.base is None:
            parser.error("--base is required for the internal exercise phase")
        print(json.dumps(exercise(args.base), ensure_ascii=True, indent=2))
        return 0
    if args.output is None:
        parser.error("--output is required")
    print(json.dumps(orchestrate(args.output), ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
