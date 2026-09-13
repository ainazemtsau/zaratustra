"""Probe migration-on-copy and exact full-pair recovery for onboarding T1."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from zaratustra.core import ContextQuery, LocalAuthorization, MutationRequest

ROOT = Path(__file__).resolve().parents[1]


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + chr(10),
        encoding="utf-8",
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(root: Path) -> dict[str, dict[str, str | int]]:
    return {
        path.relative_to(root).as_posix(): {
            "sha256": _digest(path),
            "size": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _setup() -> bytes:
    return json.dumps(
        {
            "version": 1,
            "process_title": "Fictional recovery notes",
            "goal": "Retain one fictional stage through an exact recovery",
            "expected_result": "The same saved continuation after recovery",
            "acceptance": ["Workspace identity and current stage are unchanged"],
            "boundaries": ["Fictional isolated bytes only"],
            "budget": "One bounded technical probe",
            "artifact_title": "Fictional recovery material",
            "created_by": "public onboarding T1 risk probe",
        }
    ).encode()


def _creation_draft() -> bytes:
    return json.dumps(
        {
            "version": 1,
            "process_title": "Fictional future process",
            "need": "Compare two invented recovery labels",
            "desired_outcomes": ["One inspectable fictional comparison"],
            "constraints": ["Use no personal or remote data"],
            "declared_capabilities": ["request_manual_research"],
            "clarifications": [],
            "created_by": "public onboarding T1 risk probe",
        }
    ).encode()


def _initial_records() -> Any:
    from zaratustra.core import InitialRecords

    return InitialRecords(
        process_title="Fictional migration notes",
        goal="Preserve a fictional draft while migrating a copy",
        expected_result="The same draft record graph",
        acceptance=("Identity and draft revision remain exact",),
        boundaries=("No real workspace data",),
        budget="One bounded migration copy",
        artifact_title="Fictional migration draft",
    )


def _confirm(path: Path, request: MutationRequest | ContextQuery) -> LocalAuthorization:
    from zaratustra.core import authorize_local, prepare_authorization

    return authorize_local(
        prepare_authorization(path, request),
        channel="local-chat",
        actor="public-onboarding-t1-probe",
        source_ref="explicit-fictional-isolated-probe-confirmation",
    )


def exercise(
    base: Path,
    *,
    program_version: str,
    program_sha256: str,
    runtime_root: Path | None = None,
    checkout_root: Path | None = None,
) -> dict[str, Any]:
    """Use public product APIs, then fault and restore only disposable pair files."""
    import zaratustra
    from zaratustra.core import (
        Work,
        create_initial_records,
        init_workspace,
        migrate_workspace,
        read_records,
        read_workspace,
    )
    from zaratustra.entry import resolve_entry, source_path
    from zaratustra.first_use import (
        FirstUseError,
        create_external_chat_request,
        execute_first_use,
        open_selected_context,
        prepare_external_chat_response,
        prepare_first_use,
        prepare_selected_context,
        save_external_chat_request,
    )
    from zaratustra.intake import authorize_material_intake, execute_material_intake
    from zaratustra.process_creation import save_creation_draft

    package_path = Path(zaratustra.__file__).resolve()
    if runtime_root is not None and not package_path.is_relative_to(runtime_root.resolve()):
        raise AssertionError("Product import did not come from the isolated installed runtime")
    if checkout_root is not None and package_path.is_relative_to(
        (checkout_root / "src" / "zaratustra").resolve()
    ):
        raise AssertionError("Installed probe imported product code from the checkout")
    installed_version = importlib.metadata.version("zaratustra")
    if installed_version != program_version:
        raise AssertionError("Installed product version differs from the pinned program identity")
    entry_points = tuple(
        point.value
        for point in importlib.metadata.entry_points(group="console_scripts")
        if point.name == "zara"
    )
    if entry_points != ("zaratustra.cli:main",):
        raise AssertionError("Installed zara connection entry point is missing or ambiguous")

    migration_source = base / "migration-source"
    migration_source.mkdir()
    source_info = init_workspace(migration_source)
    migrate_workspace(migration_source, target_version=2)
    source_records = create_initial_records(migration_source, _initial_records())
    migration_copy = base / "migration-copy"
    shutil.copytree(migration_source, migration_copy)
    migrated_info = migrate_workspace(migration_copy, target_version=7)
    migrated_records = read_records(migration_copy)
    source_after = read_workspace(migration_source)
    source_work = next(row for row in source_records.records if isinstance(row, Work))
    migrated_work = next(row for row in migrated_records.records if isinstance(row, Work))
    if (
        source_after.schema_version != 2
        or migrated_info.schema_version != 7
        or migrated_info.workspace_id != source_info.workspace_id
        or migrated_records != source_records
        or migrated_work.id != source_work.id
        or migrated_work.status != "draft"
    ):
        raise AssertionError("Migration-on-copy changed identity or the current draft stage")

    pair = base / "active-pair"
    workspace = pair / "workspace"
    catalog = pair / "catalog.json"
    setup = _setup()
    initial_material = b"Fictional recovery value: seventeen units.\n"
    prepared = prepare_first_use(
        catalog,
        "Fictional Recovery",
        workspace,
        setup,
        initial_material,
    )
    first = execute_first_use(
        prepared,
        tuple(_confirm(workspace, request) for request in prepared.pending),
    )
    selected = prepare_selected_context(catalog, first.designation, max_bytes=1_048_576)
    opened = open_selected_context(selected, _confirm(workspace, selected.query))
    external_request = create_external_chat_request(selected, opened)
    request_path = pair / "exchange" / "request.json"
    save_external_chat_request(request_path, external_request)
    response = b"Fictional returned recovery value: nineteen units.\n"
    prepared_return = prepare_external_chat_response(
        catalog,
        first.designation,
        request_path.read_bytes(),
        response,
        created_by="fictional manual supplier",
        source_ref="fictional-return.txt",
    )
    returned = execute_material_intake(
        prepared_return,
        authorize_material_intake(
            prepared_return,
            channel="local-chat",
            actor="public-onboarding-t1-probe",
            source_ref="explicit-review-of-fictional-return",
        ),
    )
    creation = save_creation_draft(catalog, "Fictional Future", _creation_draft())
    if creation.stage != "draft":
        raise AssertionError("Creation journal did not retain its fictional draft stage")

    entry = resolve_entry(catalog, first.designation)
    if source_path(catalog, entry) != workspace.resolve():
        raise AssertionError("Catalog connection does not resolve the selected workspace")
    before_info = read_workspace(workspace)
    before_records = read_records(workspace)
    before_manifest = _manifest(pair)
    recovery_root = base / "recovery-root"
    shutil.copytree(pair, recovery_root)
    if _manifest(recovery_root) != before_manifest:
        raise AssertionError("Quiescent recovery root differs from the selected pair")

    plan = workspace / "inbox" / "first-use" / "plan.json"
    faulted_plan = base / "faulted-first-use-plan.json"
    plan.rename(faulted_plan)
    try:
        prepare_first_use(
            catalog,
            first.designation,
            workspace,
            setup,
            initial_material,
        )
    except FirstUseError as error:
        fault_code = error.code
    else:
        raise AssertionError("Missing coordinator plan was silently reconstructed")
    if fault_code != "progress_unavailable":
        raise AssertionError("Coordinator fault did not produce the exact refusal")

    faulted_pair = base / "faulted-active-pair"
    pair.rename(faulted_pair)
    shutil.copytree(recovery_root, pair)
    after_manifest = _manifest(pair)
    after_info = read_workspace(workspace)
    after_records = read_records(workspace)
    restored_request = pair / "exchange" / "request.json"
    restored_return = prepare_external_chat_response(
        catalog,
        first.designation,
        restored_request.read_bytes(),
        response,
        created_by="fictional manual supplier",
        source_ref="fictional-return.txt",
    )
    recovered = execute_material_intake(
        restored_return,
        authorize_material_intake(
            restored_return,
            channel="local-chat",
            actor="public-onboarding-t1-probe",
            source_ref="explicit-review-of-fictional-return",
        ),
    )
    restored_entry = resolve_entry(catalog, first.designation)
    if (
        before_manifest != after_manifest
        or after_info != before_info
        or after_records != before_records
        or source_path(catalog, restored_entry) != workspace.resolve()
        or recovered.publication != returned.publication
        or recovered.acceptance != returned.acceptance
        or recovered.current_continuation != returned.current_continuation
    ):
        raise AssertionError("Full-pair restore did not recover the exact prior continuation")

    connection_value = entry_points[0]
    summary = {
        "scenario": "public-onboarding-t1-migration-copy-and-full-pair-restore",
        "installed_product_only": runtime_root is not None,
        "program": {"version": installed_version, "wheel_sha256": program_sha256},
        "connection": {
            "console_script": f"zara={connection_value}",
            "console_script_sha256": hashlib.sha256(connection_value.encode()).hexdigest(),
            "catalog_sha256": before_manifest["catalog.json"]["sha256"],
        },
        "migration_copy": {
            "source_schema": source_after.schema_version,
            "target_schema": migrated_info.schema_version,
            "workspace_id": str(migrated_info.workspace_id),
            "state_revision": migrated_records.state_revision,
            "current_work_id": str(migrated_work.id),
            "current_work_status": migrated_work.status,
            "source_unchanged": True,
        },
        "recovery": {
            "write_fence": "single-process quiescent snapshot; no open product operation",
            "fault_boundary": "advanced SQLite state without required first-use coordinator plan",
            "fault_code": fault_code,
            "restored_same_pair_manifest": before_manifest == after_manifest,
            "workspace_id": str(after_info.workspace_id),
            "state_revision": after_records.state_revision,
            "continuation_state": recovered.current_continuation.state,
            "same_publication_receipt": recovered.publication == returned.publication,
            "same_acceptance_receipt": recovered.acceptance == returned.acceptance,
            "same_catalog_target": source_path(catalog, restored_entry) == workspace.resolve(),
        },
        "preserved_carrier_files": sorted(before_manifest),
        "claim_limit": "risk probe only; no shipped updater, release, or agent adapter",
    }
    _save(base / "summary.json", summary)
    _save(base / "evidence" / "pair-manifest.json", before_manifest)
    _save(base / "evidence" / "first-use-receipt.json", first.model_dump(mode="json"))
    _save(base / "evidence" / "intake-receipt.json", returned.model_dump(mode="json"))
    return summary


def _run(command: list[str], cwd: Path, runs: list[dict[str, Any]]) -> None:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        command, cwd=cwd, env=environment, capture_output=True, encoding="utf-8", check=False
    )
    runs.append(
        {
            "command": command,
            "cwd": str(cwd),
            "exit": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
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
    unrelated = target / "unrelated-cwd"
    unrelated.mkdir()
    runs: list[dict[str, Any]] = []
    _run([uv, "build", "--no-sources"], ROOT, runs)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = cast(str, project["version"])
    wheel_name = f"zaratustra-{version}-py3-none-any.whl"
    wheel = target / wheel_name
    shutil.copyfile(ROOT / "dist" / wheel_name, wheel)
    wheel_sha256 = _digest(wheel)
    requirements = target / "runtime-requirements.txt"
    _run(
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
    executable = environment / ("Scripts/zara.exe" if os.name == "nt" else "bin/zara")
    _run(
        [uv, "venv", "--python", "3.13.7", "--python-preference", "only-managed", str(environment)],
        ROOT,
        runs,
    )
    _run(
        [
            uv,
            "pip",
            "install",
            "--offline",
            "--python",
            str(python),
            "-r",
            str(requirements),
            str(wheel),
        ],
        ROOT,
        runs,
    )
    _run([uv, "pip", "check", "--python", str(python)], ROOT, runs)
    _run([str(executable), "--version"], unrelated, runs)
    script = target / "exercise.py"
    shutil.copyfile(Path(__file__), script)
    _run(
        [
            str(python),
            "-I",
            str(script),
            "--phase",
            "exercise",
            "--base",
            str(target / "trial"),
            "--program-version",
            version,
            "--program-sha256",
            wheel_sha256,
            "--runtime-root",
            str(environment),
            "--checkout-root",
            str(ROOT),
        ],
        unrelated,
        runs,
    )
    _save(target / "commands.json", runs)
    return cast(
        dict[str, Any],
        json.loads((target / "trial" / "summary.json").read_text(encoding="utf-8")),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--phase", choices=("exercise",))
    parser.add_argument("--base", type=Path)
    parser.add_argument("--program-version")
    parser.add_argument("--program-sha256")
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--checkout-root", type=Path)
    args = parser.parse_args(argv)
    if args.phase == "exercise":
        if args.base is None or args.program_version is None or args.program_sha256 is None:
            parser.error("--base, --program-version and --program-sha256 are required")
        args.base.mkdir(parents=True)
        print(
            json.dumps(
                exercise(
                    args.base,
                    program_version=args.program_version,
                    program_sha256=args.program_sha256,
                    runtime_root=args.runtime_root,
                    checkout_root=args.checkout_root,
                ),
                ensure_ascii=True,
                indent=2,
            )
        )
        return 0
    if args.output is None:
        parser.error("--output is required")
    print(json.dumps(orchestrate(args.output), ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
