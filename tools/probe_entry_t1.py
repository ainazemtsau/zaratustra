"""Reproduce the T1 create/publish/accept/open chain from an installed wheel."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from zaratustra.core import (
        Artifact,
        ContextQuery,
        Handoff,
        LocalAuthorization,
        MutationReceipt,
        MutationRequest,
        RecordsSnapshot,
        Work,
    )

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "entry-core-recovery-demo"
MAX_CONTEXT_BYTES = 65536
DEMO_CONTENT = (
    b'{"kind":"entry-t1-demo","new_material":'
    b'"A previously absent observation is now preserved.",'
    b'"next_step":"Open the exact accepted Work context.","version":1}\n'
)


class RecoveryRefused(RuntimeError):
    """The preserved transfer intent cannot be resumed against current state."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def database_sha256(path: Path) -> str:
    from zaratustra.core import read_workspace

    return sha256_file(read_workspace(path).database)


def records(path: Path) -> RecordsSnapshot:
    from zaratustra.core import read_records

    return read_records(path)


def selected(snapshot: RecordsSnapshot) -> tuple[Work, Artifact]:
    from zaratustra.core import Artifact, Work

    work = next(row for row in snapshot.records if isinstance(row, Work))
    artifact = next(
        row for row in snapshot.records if isinstance(row, Artifact) and row.work_id == work.id
    )
    return work, artifact


def confirm(path: Path, value: MutationRequest | ContextQuery | Any) -> LocalAuthorization:
    """Trusted development adapter for an explicitly requested disposable demo."""
    from zaratustra.core import authorize_local, prepare_authorization

    return authorize_local(
        prepare_authorization(path, value),
        channel="local-chat",
        actor="entry-t1-development-evaluator",
        source_ref=f"explicitly requested {SCENARIO}; disposable demo",
    )


def request_for(
    path: Path,
    operation: str,
    *,
    operation_id: UUID | None = None,
    content: bytes | None = None,
    **changes: Any,
) -> MutationRequest:
    from zaratustra.core import MutationRequest

    snapshot = records(path)
    work, artifact = selected(snapshot)
    value: dict[str, Any] = dict(
        operation_id=operation_id or uuid4(),
        workspace_id=snapshot.workspace_id,
        work_id=work.id,
        expected_revision=snapshot.state_revision,
        operation=operation,
        provenance="Explicit entry T1 demo operation",
    )
    if operation in ("authorize_artifact", "publish_artifact"):
        value.update(version=2, artifact_id=artifact.id, artifact_revision=artifact.revision)
    if content is not None:
        value.update(content_sha256=sha256_bytes(content), content_size=len(content))
    return MutationRequest.model_validate(value | changes)


def execute(
    path: Path, request: MutationRequest, *, content: bytes | None = None
) -> MutationReceipt:
    from zaratustra.core import apply_mutation

    return apply_mutation(path, request, confirm(path, request), content=content)


def save_state(evidence: Path, name: str, path: Path) -> None:
    from zaratustra.core import read_handoffs, read_history

    snapshot = records(path)
    save(
        evidence / "states" / f"{name}.json",
        dict(
            database_sha256=database_sha256(path),
            snapshot=snapshot.model_dump(mode="json"),
            history=read_history(path).model_dump(mode="json"),
            accepted_handoffs=[row.model_dump(mode="json") for row in read_handoffs(path)],
        ),
    )


def verify_installed_runtime(base: Path, source: Path) -> dict[str, Any]:
    import sqlite3
    from importlib.metadata import version

    import pydantic

    import zaratustra

    package = Path(zaratustra.__file__).resolve().parent
    environment = (base / "venv").resolve()
    source_package = (source / "src" / "zaratustra").resolve()
    if not package.is_relative_to(environment):
        raise AssertionError("Evaluator did not import the installed environment")
    if any(Path(item).resolve() == source_package.parent for item in sys.path if item):
        raise AssertionError("Source package path leaked into installed evaluator")
    wheel = next(base.glob("*.whl"))
    identities = []
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith("zaratustra/") and name.endswith(".py"):
                installed = package.parent / name
                expected = archive.read(name)
                source_bytes = (source / "src" / name).read_bytes()
                if installed.read_bytes() != expected or source_bytes != expected:
                    raise AssertionError(f"Installed source differs: {name}")
                identities.append(dict(path=name, sha256=sha256_file(installed)))
    save(base / "installed-source.json", identities)
    return dict(
        product_version=version("zaratustra"),
        package=str(package),
        wheel_sha256=sha256_file(wheel),
        python=sys.version,
        sqlite=sqlite3.sqlite_version,
        pydantic=pydantic.__version__,
        isolated=sys.flags.isolated == 1,
    )


def publish_phase(base: Path, source: Path, *, require_installed: bool = True) -> dict[str, Any]:
    from zaratustra.core import (
        ArtifactReference,
        ContextQuery,
        Handoff,
        InitialRecords,
        MutationError,
        apply_mutation,
        create_initial_records,
        init_workspace,
        migrate_workspace,
        open_work,
        read_artifact,
        read_handoffs,
        read_workspace,
    )

    runtime = (
        verify_installed_runtime(base, source)
        if require_installed
        else dict(product_version="source-test", isolated=False)
    )
    evidence = base / "evidence"
    workspace = base / "workspace"
    workspace.mkdir()
    init_workspace(workspace)
    migrate_workspace(workspace, target_version=7)
    if read_workspace(workspace).schema_version != 7:
        raise AssertionError("T1 evaluator requires the current explicit schema 7")
    save_state(evidence, "00-empty", workspace)
    initial = InitialRecords(
        process_title="Entry T1 explicit demo",
        goal="Preserve and open one newly supplied demo observation",
        expected_result="Exact accepted bytes in a bounded context package",
        acceptance=("The new bytes and their exact reference are accepted",),
        boundaries=("Disposable local demo only; no external actions",),
        budget="One bounded feasibility probe",
        artifact_title="Entry T1 demo material",
    )
    save(evidence / "initial-records.json", initial.model_dump(mode="json"))
    create_initial_records(workspace, initial)
    save_state(evidence, "01-created", workspace)

    grant_work = request_for(workspace, "authorize_work")
    unchanged = database_sha256(workspace)
    try:
        apply_mutation(workspace, grant_work)
    except MutationError as error:
        if error.code != "permission_denied":
            raise
        save(evidence / "untrusted-refusal.json", dict(code=error.code, detail=str(error)))
    else:
        raise AssertionError("Untrusted demo mutation was accepted")
    if database_sha256(workspace) != unchanged:
        raise AssertionError("Untrusted refusal changed the database")
    grant_work_receipt = execute(workspace, grant_work)
    save(evidence / "receipts" / "authorize-work.json", grant_work_receipt.model_dump(mode="json"))
    save_state(evidence, "02-work-authorized", workspace)

    grant_artifact = request_for(workspace, "authorize_artifact")
    grant_artifact_receipt = execute(workspace, grant_artifact)
    save(
        evidence / "receipts" / "authorize-artifact.json",
        grant_artifact_receipt.model_dump(mode="json"),
    )
    save_state(evidence, "03-artifact-authorized", workspace)

    before = records(workspace)
    work, artifact = selected(before)
    if artifact.active_version is not None:
        raise AssertionError("Fresh demo already contains published bytes")
    publication_id = uuid4()
    publication = request_for(
        workspace, "publish_artifact", operation_id=publication_id, content=DEMO_CONTENT
    )
    handoff = Handoff(
        kind="handoff",
        version=1,
        handoff_id=uuid4(),
        workspace_id=before.workspace_id,
        process=work.process_id,
        related_work=work.id,
        intent="accepted_result",
        source_revision=before.state_revision + 1,
        result=ArtifactReference(
            artifact_id=artifact.id,
            version_id=publication_id,
            sha256=sha256_bytes(DEMO_CONTENT),
        ),
        provenance="New entry T1 demo material, preserved before publication",
        constraints=("Disposable local demo only",),
        open_questions=("End-user entry shell remains outside T1",),
        created_by="entry-t1-development-evaluator",
    )
    handoff_bytes = handoff.model_dump_json(indent=2).encode("utf-8") + b"\n"
    (evidence / "preserved-handoff.json").write_bytes(handoff_bytes)
    save(
        evidence / "origin-intent.json",
        dict(
            version=1,
            origin_revision=before.state_revision,
            workspace_id=str(before.workspace_id),
            process_id=str(work.process_id),
            work_id=str(work.id),
            artifact_id=str(artifact.id),
            content_base64=base64.b64encode(DEMO_CONTENT).decode("ascii"),
            content_sha256=sha256_bytes(DEMO_CONTENT),
            content_size=len(DEMO_CONTENT),
            publication_request=publication.model_dump(mode="json"),
            preserved_handoff_sha256=sha256_bytes(handoff_bytes),
        ),
    )
    publication_receipt = execute(workspace, publication, content=DEMO_CONTENT)
    save(
        evidence / "receipts" / "publish-artifact.json",
        publication_receipt.model_dump(mode="json"),
    )
    save_state(evidence, "04-published-not-accepted", workspace)
    if read_handoffs(workspace):
        raise AssertionError("Publication was confused with acceptance")
    published = read_artifact(workspace, artifact.id, publication_id)
    if published.content != DEMO_CONTENT or published.version.sha256 != sha256_bytes(DEMO_CONTENT):
        raise AssertionError("Published bytes do not match the preserved intent")
    query = ContextQuery(
        workspace_id=before.workspace_id,
        work_id=work.id,
        process_id=work.process_id,
        expected_revision=publication_receipt.new_revision,
        max_bytes=MAX_CONTEXT_BYTES,
    )
    try:
        open_work(workspace, query, confirm(workspace, query))
    except MutationError as error:
        if error.code != "dependency_missing":
            raise
        save(
            evidence / "published-context-refusal.json",
            dict(
                code=error.code,
                detail=str(error),
                state_revision=publication_receipt.new_revision,
            ),
        )
    else:
        raise AssertionError("Published bytes were treated as accepted context")
    stage = dict(
        phase="published_not_accepted",
        origin_revision=before.state_revision,
        publication_revision=publication_receipt.new_revision,
        publication_receipt=publication_receipt.model_dump(mode="json"),
        handoff_id=str(handoff.handoff_id),
        artifact_version_id=str(publication_id),
        artifact_sha256=published.version.sha256,
        accepted_count=0,
        schema_version=read_workspace(workspace).schema_version,
        runtime=runtime,
    )
    save(evidence / "interruption.json", stage)
    print(json.dumps(stage, ensure_ascii=True, indent=2), flush=True)
    return stage


def load_intent(base: Path) -> tuple[dict[str, Any], bytes, Handoff]:
    from zaratustra.core import Handoff

    evidence = base / "evidence"
    intent: dict[str, Any] = json.loads((evidence / "origin-intent.json").read_bytes())
    handoff_bytes = (evidence / "preserved-handoff.json").read_bytes()
    if sha256_bytes(handoff_bytes) != intent["preserved_handoff_sha256"]:
        raise RecoveryRefused("Preserved Handoff bytes changed")
    return intent, handoff_bytes, Handoff.model_validate_json(handoff_bytes)


def recover_acceptance(base: Path, workspace: Path) -> MutationReceipt:
    from zaratustra.core import (
        MutationRequest,
        ReceiptQuery,
        apply_mutation,
        handoff_request,
        read_artifact,
        read_handoffs,
        read_history,
        read_receipt,
    )

    intent, handoff_bytes, handoff = load_intent(base)
    matches = [
        row for row in read_handoffs(workspace) if row.handoff.handoff_id == handoff.handoff_id
    ]
    if matches:
        if len(matches) != 1 or matches[0].handoff != handoff:
            raise RecoveryRefused("Handoff id belongs to different accepted meaning")
        if matches[0].delivery.input_sha256 != sha256_bytes(handoff_bytes):
            raise RecoveryRefused("Accepted delivery does not match preserved bytes")
        return matches[0].receipt
    snapshot = records(workspace)
    publication = MutationRequest.model_validate(intent["publication_request"])
    expected = int(intent["origin_revision"]) + 1
    if snapshot.state_revision != expected:
        raise RecoveryRefused(
            f"foreign_state_change: expected publication revision {expected}; "
            f"found {snapshot.state_revision}"
        )
    query = ReceiptQuery(
        workspace_id=UUID(intent["workspace_id"]),
        work_id=UUID(intent["work_id"]),
        operation_id=publication.operation_id,
    )
    receipt = read_receipt(workspace, query, confirm(workspace, query))
    history = read_history(workspace)
    events = [
        event for event in history.events if event.request.operation_id == publication.operation_id
    ]
    if len(events) != 1:
        raise RecoveryRefused("Saved publication identity is not unique")
    event = events[0]
    version = event.artifact_version
    if (
        event.request != publication
        or publication.operation != "publish_artifact"
        or event.id != receipt.event_id
        or receipt not in history.receipts
        or receipt.operation_id != publication.operation_id
        or receipt.workspace_id != publication.workspace_id
        or receipt.work_id != publication.work_id
        or receipt.previous_revision != publication.expected_revision
        or receipt.new_revision != expected
        or version is None
        or version.id != publication.operation_id
        or version.artifact_id != UUID(intent["artifact_id"])
        or version.sha256 != intent["content_sha256"]
        or version.size != intent["content_size"]
    ):
        raise RecoveryRefused("Saved publication receipt is not the intended stage")
    content = read_artifact(workspace, UUID(intent["artifact_id"]), publication.operation_id)
    if (
        content.content != base64.b64decode(intent["content_base64"])
        or content.version.sha256 != intent["content_sha256"]
        or content.version.size != intent["content_size"]
        or handoff.source_revision != expected
        or handoff.result.version_id != publication.operation_id
    ):
        raise RecoveryRefused("Published stage differs from preserved intent")
    request = handoff_request(handoff_bytes, source_ref="entry-t1:preserved-intent")
    return apply_mutation(workspace, request, confirm(workspace, request))


def resume_phase(base: Path) -> dict[str, Any]:
    from zaratustra.core import (
        ContextQuery,
        MutationError,
        apply_mutation,
        handoff_request,
        open_work,
        read_handoffs,
        read_history,
    )

    evidence = base / "evidence"
    workspace = base / "workspace"
    intent, handoff_bytes, handoff = load_intent(base)
    first = recover_acceptance(base, workspace)
    save(evidence / "receipts" / "accept-handoff.json", first.model_dump(mode="json"))
    save_state(evidence, "05-accepted", workspace)
    accepted_state = records(workspace)
    work, _ = selected(accepted_state)
    query = ContextQuery(
        workspace_id=accepted_state.workspace_id,
        work_id=work.id,
        process_id=work.process_id,
        expected_revision=accepted_state.state_revision,
        max_bytes=MAX_CONTEXT_BYTES,
    )
    package = open_work(workspace, query, confirm(workspace, query))
    (evidence / "context.json").write_bytes(package.output)
    context = json.loads(package.output)
    source_map = {row["locator"]: row for row in context["context"]["sources"]}
    artifact_locator = f"artifact-version:{handoff.result.version_id}"
    acceptance_locator = f"acceptance:{handoff.handoff_id}"
    if artifact_locator not in source_map or acceptance_locator not in source_map:
        raise AssertionError("Bounded context omits the accepted exact references")
    artifact_data = source_map[artifact_locator]["data"]
    if base64.b64decode(artifact_data["content_base64"]) != DEMO_CONTENT:
        raise AssertionError("Bounded context returned different bytes")
    if context["manifest"]["budget"]["maximum"] != MAX_CONTEXT_BYTES:
        raise AssertionError("Context budget changed")
    if context["context"]["envelope"]["schema_version"] != 7:
        raise AssertionError("Opened context did not come from explicit schema 7")

    accepted_db = database_sha256(workspace)
    second = recover_acceptance(base, workspace)
    if second != first or database_sha256(workspace) != accepted_db:
        raise AssertionError("Recovery discovery repeated an accepted effect")
    exact_request = handoff_request(handoff_bytes, source_ref="entry-t1:preserved-intent")
    try:
        apply_mutation(workspace, exact_request, confirm(workspace, exact_request))
    except MutationError as error:
        if error.code != "conflict":
            raise
        direct_replay = dict(code=error.code, detail=str(error), no_write=True)
    else:
        raise AssertionError("Stale direct replay unexpectedly mutated the Work")
    if database_sha256(workspace) != accepted_db:
        raise AssertionError("Rejected stale replay changed the database")

    altered = handoff.model_copy(update={"provenance": "Different meaning under the same id"})
    altered_bytes = altered.model_dump_json().encode("utf-8")
    collision = handoff_request(
        altered_bytes,
        source_ref="entry-t1:changed-intent",
        expected_revision=accepted_state.state_revision,
    )
    try:
        apply_mutation(workspace, collision, confirm(workspace, collision))
    except MutationError as error:
        if error.code != "collision":
            raise
        collision_result = dict(code=error.code, detail=str(error), no_write=True)
    else:
        raise AssertionError("Changed meaning reused an accepted operation id")
    if database_sha256(workspace) != accepted_db:
        raise AssertionError("Rejected collision changed the database")
    acceptances = read_handoffs(workspace)
    history = read_history(workspace)
    acceptance_events = [
        event for event in history.events if event.request.operation == "accept_handoff"
    ]
    summary = dict(
        phase="accepted_and_opened",
        origin_revision=intent["origin_revision"],
        publication_revision=intent["origin_revision"] + 1,
        acceptance_revision=accepted_state.state_revision,
        publication_operation_id=intent["publication_request"]["operation_id"],
        acceptance_operation_id=str(handoff.handoff_id),
        artifact_reference=handoff.result.model_dump(mode="json"),
        acceptance_receipt=first.model_dump(mode="json"),
        context_sha256=package.output_sha256,
        context_bytes=len(package.output),
        context_budget=MAX_CONTEXT_BYTES,
        schema_version=context["context"]["envelope"]["schema_version"],
        context_sources=sorted(source_map),
        accepted_count=len(acceptances),
        acceptance_event_count=len(acceptance_events),
        repeated_recovery_same_receipt=second == first,
        repeated_recovery_no_write=database_sha256(workspace) == accepted_db,
        direct_core_replay=direct_replay,
        changed_intent=collision_result,
    )
    save(evidence / "resume-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=True, indent=2), flush=True)
    return summary


def foreign_change_phase(base: Path) -> dict[str, Any]:
    from zaratustra.core import MutationError, apply_mutation, handoff_request, read_handoffs

    evidence = base / "evidence"
    workspace = base / "foreign-workspace"
    intent, handoff_bytes, _ = load_intent(base)
    foreign = request_for(
        workspace,
        "set_work_requirements",
        requirements=("independent-demo-change-after-publication",),
    )
    foreign_receipt = execute(workspace, foreign)
    save(evidence / "receipts" / "foreign-change.json", foreign_receipt.model_dump(mode="json"))
    changed_db = database_sha256(workspace)
    try:
        recover_acceptance(base, workspace)
    except RecoveryRefused as error:
        recovery = dict(code="foreign_state_change", detail=str(error), no_write=True)
    else:
        raise AssertionError("Recovery silently adopted a foreign revision")
    if database_sha256(workspace) != changed_db or read_handoffs(workspace):
        raise AssertionError("Foreign-state refusal changed or accepted the workspace")

    refreshed = handoff_request(
        handoff_bytes,
        source_ref="entry-t1:forbidden-refresh-attempt",
        expected_revision=records(workspace).state_revision,
    )
    try:
        apply_mutation(workspace, refreshed, confirm(workspace, refreshed))
    except MutationError as error:
        if error.code != "conflict" or "source revision" not in str(error):
            raise
        refresh = dict(code=error.code, detail=str(error), no_write=True)
    else:
        raise AssertionError("Core silently refreshed the preserved Handoff source revision")
    if database_sha256(workspace) != changed_db or read_handoffs(workspace):
        raise AssertionError("Rejected source refresh changed the workspace")
    summary = dict(
        phase="foreign_change_refused",
        origin_revision=intent["origin_revision"],
        publication_revision=intent["origin_revision"] + 1,
        foreign_revision=foreign_receipt.new_revision,
        foreign_operation_id=str(foreign.operation_id),
        recovery=recovery,
        core_source_refresh=refresh,
        accepted_count=0,
        database_sha256=changed_db,
    )
    save(evidence / "foreign-change-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=True, indent=2), flush=True)
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
    wheel = ROOT / "dist" / wheel_name
    shutil.copyfile(wheel, target / wheel_name)
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
    exercise = target / "exercise.py"
    shutil.copyfile(Path(__file__), exercise)
    common = [str(python), "-I", str(exercise), "--base", str(target)]
    run([*common, "--phase", "publish", "--source", str(ROOT)], target / "unrelated-cwd", runs)
    shutil.copytree(target / "workspace", target / "foreign-workspace")
    run([*common, "--phase", "resume"], target / "unrelated-cwd", runs)
    run([*common, "--phase", "foreign"], target / "unrelated-cwd", runs)
    save(target / "commands.json", runs)
    resume = json.loads((target / "evidence" / "resume-summary.json").read_bytes())
    foreign = json.loads((target / "evidence" / "foreign-change-summary.json").read_bytes())
    summary = dict(
        scenario=SCENARIO,
        source_commit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, encoding="utf-8"
        ).strip(),
        installed_wheel=wheel_name,
        installed_wheel_sha256=sha256_file(target / wheel_name),
        process_boundary="publish child exited before acceptance; resume used a new child",
        resume=resume,
        foreign_change=foreign,
        acceptance=(
            "technical evaluator evidence only; owner acceptance and real chat transfer unverified"
        ),
    )
    save(target / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=True, indent=2), flush=True)
    print(f"PASS: retained entry T1 evidence at {target}", flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--phase", choices=("publish", "resume", "foreign"))
    args = parser.parse_args()
    if args.output is not None:
        if any(value is not None for value in (args.base, args.source, args.phase)):
            parser.error("--output cannot be combined with phase arguments")
        orchestrate(args.output)
        return
    if args.base is None or args.phase is None:
        parser.error("use --output, or use internal --base/--phase arguments")
    base = args.base.resolve()
    if args.phase == "publish":
        if args.source is None:
            parser.error("publish phase requires --source")
        publish_phase(base, args.source.resolve())
    elif args.phase == "resume":
        resume_phase(base)
    else:
        foreign_change_phase(base)


if __name__ == "__main__":
    main()
