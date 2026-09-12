"""Reproduce installed catalog discovery and exact generic basic reads."""

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
from time import monotonic, sleep
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from zaratustra.core import LocalAuthorization, MutationRequest, ProcessQuery

ROOT = Path(__file__).resolve().parents[1]


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + chr(10),
        encoding="utf-8",
    )


def confirm(path: Path, value: MutationRequest | ProcessQuery) -> LocalAuthorization:
    from zaratustra.core import authorize_local, prepare_authorization

    return authorize_local(
        prepare_authorization(path, value),
        channel="local-chat",
        actor="generic-entry-demo",
        source_ref="explicit new disposable installed-package demo",
    )


def request(path: Path, work_id: UUID, operation: str, **fields: Any) -> MutationRequest:
    from zaratustra.core import MutationRequest, read_records

    snapshot = read_records(path)
    return MutationRequest.model_validate(
        dict(
            operation_id=uuid4(),
            workspace_id=snapshot.workspace_id,
            work_id=work_id,
            expected_revision=snapshot.state_revision,
            operation=operation,
            provenance="Explicit new generic entry demo",
        )
        | fields
    )


def bootstrap(path: Path, title: str) -> UUID:
    from zaratustra.core import (
        InitialRecords,
        Work,
        apply_mutation,
        create_initial_records,
        init_workspace,
        migrate_workspace,
    )

    path.mkdir(parents=True)
    init_workspace(path)
    migrate_workspace(path, target_version=7)
    snapshot = create_initial_records(
        path,
        InitialRecords(
            process_title=title,
            goal="Inspect exact generic metadata",
            expected_result="One bounded basic read",
            acceptance=("Only explicitly created disposable data",),
            boundaries=("No external or personal content",),
            budget="One local demonstration",
            artifact_title="Generic demo value",
        ),
    )
    work = next(row for row in snapshot.records if isinstance(row, Work))
    authorize = request(path, work.id, "authorize_work")
    apply_mutation(path, authorize, confirm(path, authorize))
    return work.id


def complete(path: Path, work_id: UUID) -> tuple[UUID, str]:
    from zaratustra.core import (
        Artifact,
        ArtifactReference,
        Handoff,
        NextWork,
        ResultSubmission,
        Work,
        apply_mutation,
        handoff_request,
        read_records,
        submit_result,
    )

    artifact = next(
        row
        for row in read_records(path).records
        if isinstance(row, Artifact) and row.work_id == work_id
    )
    allow = request(
        path,
        work_id,
        "authorize_artifact",
        version=2,
        artifact_id=artifact.id,
        artifact_revision=artifact.revision,
    )
    apply_mutation(path, allow, confirm(path, allow))
    content = b'{"accepted":"generic demo basis","version":1}\n'
    digest = hashlib.sha256(content).hexdigest()
    publish = request(
        path,
        work_id,
        "publish_artifact",
        version=2,
        artifact_id=artifact.id,
        artifact_revision=artifact.revision,
        content_sha256=digest,
        content_size=len(content),
    )
    apply_mutation(path, publish, confirm(path, publish), content=content)
    reference = ArtifactReference(
        artifact_id=artifact.id, version_id=publish.operation_id, sha256=digest
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
        provenance="Explicit accepted generic demo value",
        created_by="installed generic entry demo",
    )
    accept = handoff_request(handoff.model_dump_json().encode(), source_ref="generic-demo")
    apply_mutation(path, accept, confirm(path, accept))
    snapshot = read_records(path)
    next_work_id = uuid4()
    finish = request(
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
                artifact_id=uuid4(),
                goal="A later separate generic Work",
                expected_result="A later separate result",
                acceptance=("Use only the exact inherited basis",),
                boundaries=("No implied content authority",),
                budget="A later local read",
                executor_requirements=(),
                artifact_title="Later generic value",
                authority_scope="work_metadata",
            ),
        ),
    )
    submit_result(path, finish, confirm(path, finish))
    return next_work_id, digest


def concurrent_add(
    catalog: Path,
    designation: str,
    workspace: Path,
    work_id: UUID,
    aliases: tuple[str, ...],
    rendezvous: Path,
    participant: str,
) -> dict[str, Any]:
    import zaratustra.entry as entry_module
    from zaratustra.entry import add_entry

    entry_adapter: Any = entry_module
    original = entry_adapter.read_workspace
    synchronized = False

    def synchronized_source(path: Path) -> Any:
        nonlocal synchronized
        if not synchronized:
            synchronized = True
            (rendezvous / f"{participant}.ready").write_text("ready\n", encoding="utf-8")
            deadline = monotonic() + 20
            while len(tuple(rendezvous.glob("*.ready"))) < 2:
                if monotonic() >= deadline:
                    raise RuntimeError("Installed concurrent-add rendezvous timed out")
                sleep(0.01)
        return original(path)

    entry_adapter.read_workspace = synchronized_source
    return add_entry(catalog, designation, workspace, work_id, aliases=aliases).model_dump(
        mode="json"
    )


def exercise(base: Path) -> dict[str, Any]:
    import zaratustra
    from zaratustra.core import read_basic_process
    from zaratustra.entry import (
        EntryError,
        find_entries,
        prepare_entry_read,
        relocate_entry,
        resolve_entry,
    )

    package = Path(zaratustra.__file__).resolve().parent
    environment = (base / "venv").resolve()
    if not package.is_relative_to(environment):
        raise AssertionError("Demo did not import the installed wheel")
    workspaces = base / "workspaces"
    ready_path, completed_path = workspaces / "ready", workspaces / "completed"
    ready_work = bootstrap(ready_path, "Morning Notes")
    completed_work = bootstrap(completed_path, "Review Queue")
    next_work, expected_digest = complete(completed_path, completed_work)
    catalog = base / "catalog" / "entries.json"
    catalog.parent.mkdir(parents=True)
    rendezvous = base / "evidence" / "concurrent-add-rendezvous"
    rendezvous.mkdir(parents=True)
    commands = (
        [
            sys.executable,
            "-I",
            str(Path(__file__)),
            "--phase",
            "concurrent-add",
            "--catalog",
            str(catalog),
            "--designation",
            "Morning Notes",
            "--workspace",
            str(ready_path),
            "--work-id",
            str(ready_work),
            "--alias",
            "shared",
            "--rendezvous",
            str(rendezvous),
            "--participant",
            "morning",
        ],
        [
            sys.executable,
            "-I",
            str(Path(__file__)),
            "--phase",
            "concurrent-add",
            "--catalog",
            str(catalog),
            "--designation",
            "Review Queue",
            "--workspace",
            str(completed_path),
            "--work-id",
            str(completed_work),
            "--alias",
            "shared",
            "--alias",
            "Morning Notes",
            "--rendezvous",
            str(rendezvous),
            "--participant",
            "review",
        ],
    )
    processes = tuple(
        subprocess.Popen(
            command,
            cwd=base / "unrelated-cwd",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        )
        for command in commands
    )
    concurrent_runs = []
    for command, process in zip(commands, processes, strict=True):
        stdout, stderr = process.communicate(timeout=30)
        concurrent_runs.append(
            dict(command=command, exit=process.returncode, stdout=stdout, stderr=stderr)
        )
    save(base / "evidence" / "concurrent-adds.json", concurrent_runs)
    if any(row["exit"] for row in concurrent_runs):
        raise AssertionError("Installed concurrent catalog add failed")
    first = resolve_entry(catalog, "Morning Notes")
    second = resolve_entry(catalog, "Review Queue")
    initial_find = find_entries(catalog)
    save(base / "evidence" / "find-initial.json", initial_find.model_dump(mode="json"))
    try:
        resolve_entry(catalog, "shared")
    except EntryError as error:
        ambiguity = dict(code=error.code, choices=list(error.choices))
    else:
        raise AssertionError("Overlapping alias was not ambiguous")
    if resolve_entry(catalog, "Morning Notes") != first:
        raise AssertionError("Exact designation did not take precedence over another row's alias")
    if tuple(resolve_entry(catalog, choice) for choice in ambiguity["choices"]) != (first, second):
        raise AssertionError("Ambiguity offered a designation that was not actionable")
    reads = {}
    for name in (first.designation, second.designation):
        prepared = prepare_entry_read(catalog, name, max_bytes=65536)
        package_read = read_basic_process(
            prepared.workspace, prepared.query, confirm(prepared.workspace, prepared.query)
        )
        value = json.loads(package_read.output)
        if "content_base64" in package_read.output.decode():
            raise AssertionError("Basic reader disclosed Artifact content")
        save(base / "evidence" / f"read-{name.casefold().replace(' ', '-')}.json", value)
        reads[name] = dict(
            work_id=value["selected_work"]["id"],
            work_status=value["selected_work"]["status"],
            continuation_state=value["continuation_state"],
            acceptance_count=len(value["accepted_basis"]),
            output_sha256=package_read.output_sha256,
        )
    saved = json.loads((base / "evidence" / "read-review-queue.json").read_text(encoding="utf-8"))
    if (
        saved["saved_continuation"]["next_work"]["work_id"] != str(next_work)
        or saved["saved_continuation"]["references"][0]["sha256"] != expected_digest
    ):
        raise AssertionError("Saved Result continuation/basis was not exact")
    moved = workspaces / "ready-moved"
    ready_path.rename(moved)
    unavailable_find = find_entries(catalog)
    save(
        base / "evidence" / "find-one-unavailable.json",
        unavailable_find.model_dump(mode="json"),
    )
    relocate_entry(catalog, first.designation, moved)
    final_find = find_entries(catalog)
    save(base / "evidence" / "find-relocated.json", final_find.model_dump(mode="json"))
    zara = environment / ("Scripts/zara.exe" if os.name == "nt" else "bin/zara")
    cli = subprocess.run(
        [str(zara), "entry", "find", str(catalog), "review"],
        cwd=base / "unrelated-cwd",
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    save(
        base / "evidence" / "installed-cli.json",
        dict(command=["zara", "entry", "find", "<catalog>", "review"], **cli.__dict__),
    )
    if cli.returncode or json.loads(cli.stdout)["matches"][0]["entry"]["id"] != str(second.id):
        raise AssertionError("Installed zara entry find did not return the selected instance")
    summary = dict(
        scenario="installed-entry-discovery-basic-read",
        installed_package=package.as_posix(),
        designations=[first.designation, second.designation],
        ambiguity=ambiguity,
        exact_designation_precedes_alias=True,
        ambiguity_choices_actionable=True,
        initial_source_states={
            row.entry.designation: row.source_state for row in initial_find.matches
        },
        concurrent_adds_preserved={row.entry.designation for row in initial_find.matches}
        == {"Morning Notes", "Review Queue"},
        unavailable_source_states={
            row.entry.designation: row.source_state for row in unavailable_find.matches
        },
        relocated_source_states={
            row.entry.designation: row.source_state for row in final_find.matches
        },
        reads=reads,
        exact_saved_next_work=str(next_work),
        exact_saved_basis_sha256=expected_digest,
        catalog_sha256=hashlib.sha256(catalog.read_bytes()).hexdigest(),
    )
    save(base / "summary.json", summary)
    return summary


def run(command: list[str], cwd: Path, runs: list[dict[str, Any]]) -> None:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        command, cwd=cwd, env=environment, capture_output=True, encoding="utf-8", check=False
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
    summary: dict[str, Any] = json.loads((target / "summary.json").read_text(encoding="utf-8"))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--phase", choices=("exercise", "concurrent-add"))
    parser.add_argument("--base", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--designation")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--work-id", type=UUID)
    parser.add_argument("--alias", action="append")
    parser.add_argument("--rendezvous", type=Path)
    parser.add_argument("--participant")
    args = parser.parse_args(argv)
    if args.phase == "concurrent-add":
        required = (
            args.catalog,
            args.designation,
            args.workspace,
            args.work_id,
            args.alias,
            args.rendezvous,
            args.participant,
        )
        if any(value is None for value in required):
            parser.error("concurrent-add requires its complete explicit input")
        assert args.catalog is not None
        assert args.designation is not None
        assert args.workspace is not None
        assert args.work_id is not None
        assert args.alias is not None
        assert args.rendezvous is not None
        assert args.participant is not None
        print(
            json.dumps(
                concurrent_add(
                    args.catalog,
                    args.designation,
                    args.workspace,
                    args.work_id,
                    tuple(args.alias),
                    args.rendezvous,
                    args.participant,
                ),
                ensure_ascii=True,
                indent=2,
            )
        )
        return 0
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
