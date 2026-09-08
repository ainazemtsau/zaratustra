"""Retained installed Work 4 trial on a new fictional copy; executor evidence only."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], *, cwd: Path, console: bool = False, expected: int = 0) -> str:
    print("$ " + subprocess.list2cmdline(command), flush=True)
    child_env = dict(os.environ)
    child_env.pop("PYTHONPATH", None)
    child_env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        command,
        cwd=cwd,
        env=child_env,
        stdin=None if console else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=None if console else subprocess.PIPE,
        encoding="utf-8",
        text=True,
    )
    print(result.stdout, flush=True)
    if result.stderr:
        print(result.stderr, flush=True)
    print(f"exit={result.returncode}", flush=True)
    if result.returncode != expected:
        raise RuntimeError(f"Expected exit {expected}; got {result.returncode}")
    return result.stdout


def exercise(base: Path, source: Path) -> None:
    from importlib.metadata import version

    import pydantic

    import zaratustra
    from zaratustra.core import (
        Artifact,
        MutationRequest,
        ProjectionRebuildError,
        Work,
        WorkspaceError,
        apply_mutation,
        authorize_local,
        inspect_artifacts,
        prepare_authorization,
        read_artifact,
        read_history,
        read_records,
        read_workspace,
    )

    workspace = base / "workspace"
    zara = base / "venv" / ("Scripts/zara.exe" if os.name == "nt" else "bin/zara")
    working = base / "unrelated-cwd"
    runtime = dict(
        version=version("zaratustra"),
        python=sys.version,
        sqlite=sqlite3.sqlite_version,
        pydantic=pydantic.__version__,
        package=str(Path(zaratustra.__file__).resolve()),
    )
    assert Path(runtime["package"]).is_relative_to(base / "venv")
    assert not Path(runtime["package"]).is_relative_to(source)
    assert not any(Path(p).resolve().is_relative_to(source) for p in sys.path if p)
    print(json.dumps(runtime, indent=2), flush=True)

    def cli(*args: str, console: bool = False, expected: int = 0) -> str:
        return run([str(zara), *args], cwd=working, console=console, expected=expected)

    cli("--version")
    before = json.loads(cli("records", "read", str(workspace)))
    previous = read_records(workspace)
    original_history = read_history(workspace)
    upgrade = json.loads(cli("migrate", str(workspace)))
    assert upgrade["schema_version"] == 4
    assert read_records(workspace) == previous and read_history(workspace) == original_history
    assert json.loads(cli("records", "read", str(workspace))) == before
    migrated = digest(workspace / ".zara/state.sqlite3")
    cli("migrate", str(workspace))
    assert digest(workspace / ".zara/state.sqlite3") == migrated

    def request(
        path: Path, operation: str, content: bytes | None = None, **extra: object
    ) -> MutationRequest:
        snapshot = read_records(path)
        work = next(record for record in snapshot.records if isinstance(record, Work))
        artifact = next(record for record in snapshot.records if isinstance(record, Artifact))
        fields: dict[str, object] = dict(
            version=2,
            operation_id=uuid4(),
            workspace_id=snapshot.workspace_id,
            work_id=work.id,
            expected_revision=snapshot.state_revision,
            operation=operation,
            provenance="Fictional installed Work 4 trial under the development CALL",
        )
        if operation in ("authorize_artifact", "publish_artifact", "restore_artifact"):
            fields.update(artifact_id=artifact.id, artifact_revision=artifact.revision)
        if content is not None:
            fields.update(
                content_sha256=hashlib.sha256(content).hexdigest(), content_size=len(content)
            )
        return MutationRequest.model_validate(fields | extra)

    def mutate(value: MutationRequest, content_file: Path | None = None) -> dict[str, Any]:
        args = ["mutate", str(workspace), value.model_dump_json()]
        if content_file is not None:
            args.extend(["--content-file", str(content_file)])
        output: dict[str, Any] = json.loads(cli(*args, console=True))
        return output

    grant = request(workspace, "authorize_work")
    cli("mutate", str(workspace), grant.model_dump_json(), expected=1)
    assert digest(workspace / ".zara/state.sqlite3") == migrated
    mutate(grant)
    mutate(request(workspace, "authorize_artifact"))
    first_bytes = b"Fictional observation: the imaginary moon has a silver rim."
    second_bytes = b"Fictional observation, revision two: the silver rim appears at dusk."
    first_source, second_source = base / "observation-1.txt", base / "observation-2.txt"
    first_source.write_bytes(first_bytes)
    second_source.write_bytes(second_bytes)
    first = request(workspace, "publish_artifact", first_bytes)
    first_receipt = mutate(first, first_source)
    second = request(workspace, "publish_artifact", second_bytes)
    second_receipt = mutate(second, second_source)
    assert first.artifact_id is not None
    latest = json.loads(cli("artifacts", "read", str(workspace), str(first.artifact_id)))
    older = json.loads(
        cli(
            "artifacts",
            "read",
            str(workspace),
            str(first.artifact_id),
            "--version-id",
            str(first.operation_id),
        )
    )
    assert base64.b64decode(latest["content_base64"]) == second_bytes
    assert base64.b64decode(older["content_base64"]) == first_bytes

    projection = workspace / "projections/overview.md"
    generated = projection.read_bytes()
    database = workspace / ".zara/state.sqlite3"
    before_rebuild = digest(database)
    print("FAULT FIXTURE: remove generated overview; DB untouched", flush=True)
    projection.unlink()
    assert json.loads(cli("projections", "status", str(workspace)))["status"] == "missing"
    cli("projections", "rebuild", str(workspace))
    assert projection.read_bytes() == generated and digest(database) == before_rebuild

    descriptor = read_artifact(workspace, first.artifact_id).version
    content_file = workspace / descriptor.relative_path
    print("FAULT FIXTURE: damage published bytes; Core must refuse and repair", flush=True)
    content_file.write_bytes(b"injected damage")
    cli("artifacts", "read", str(workspace), str(first.artifact_id), expected=1)
    assert digest(database) == before_rebuild
    repair = request(workspace, "restore_artifact", second_bytes, restore_version=descriptor.id)
    repair_receipt = mutate(repair, second_source)
    assert read_artifact(workspace, first.artifact_id).version == descriptor
    assert read_artifact(workspace, first.artifact_id).content == second_bytes
    cli("artifacts", "inspect", str(workspace))
    cli("projections", "status", str(workspace))
    cli("history", str(workspace))

    # Separate copy: installed Core fault boundaries, trusted local-chat test adapter.
    # No SQL/state edit constructs success. Each successful write uses apply_mutation.
    fault = base / "fault-workspace"
    shutil.copytree(workspace, fault)
    fault_db = fault / ".zara/state.sqlite3"
    fault_request = request(fault, "publish_artifact", b"fault boundary content")
    caller = authorize_local(
        prepare_authorization(fault, fault_request),
        channel="local-chat",
        actor="executor-fictional-trial",
        source_ref="development-call:Work4",
    )
    saved = digest(fault_db)
    connect = sqlite3.connect

    def reject_commit(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = connect(*args, **kwargs)
        connection.set_authorizer(
            lambda action, target, *_: (
                sqlite3.SQLITE_DENY
                if (action, target) == (sqlite3.SQLITE_TRANSACTION, "COMMIT")
                else sqlite3.SQLITE_OK
            )
        )
        return connection

    with patch("sqlite3.connect", reject_commit):
        try:
            apply_mutation(fault, fault_request, caller, content=b"fault boundary content")
        except WorkspaceError as error:
            print(f"EXPECTED precommit failure: {error}", flush=True)
        else:
            raise AssertionError("Injected commit refusal did not fail")
    assert digest(fault_db) == saved
    print(inspect_artifacts(fault).model_dump_json(indent=2), flush=True)

    def fail_rebuild(*_: object) -> None:
        raise OSError("installed injected rebuild failure")

    with patch("zaratustra.core.mutations.write_projection", fail_rebuild):
        try:
            apply_mutation(fault, fault_request, caller, content=b"fault boundary content")
        except ProjectionRebuildError as error:
            fault_receipt = error.receipt
            print(f"EXPECTED committed rebuild failure: {error}", flush=True)
            print(fault_receipt.model_dump_json(indent=2), flush=True)
        else:
            raise AssertionError("Injected rebuild failure did not fail")
    committed = digest(fault_db)
    cli("projections", "rebuild", str(fault))
    assert digest(fault_db) == committed
    assert fault_receipt.operation_id == fault_request.operation_id
    fault_history = read_history(fault)
    assert fault_history.events[-1].request == fault_request
    assert len(fault_history.events) == len(read_history(workspace).events) + 1
    assert fault_request.artifact_id is not None
    assert read_artifact(fault, fault_request.artifact_id).content == b"fault boundary content"
    receipt = dict(
        runtime=runtime,
        workspace=str(workspace),
        installed_command=str(zara),
        database_sha256=digest(database),
        snapshot=read_records(workspace).model_dump(mode="json"),
        history=read_history(workspace).model_dump(mode="json"),
        artifact_inspection=inspect_artifacts(workspace).model_dump(mode="json"),
        publication_receipts=[first_receipt, second_receipt],
        repair_receipt=repair_receipt,
        fault_workspace=str(fault),
        fault_receipt=fault_receipt.model_dump(mode="json"),
        fault_database_sha256=digest(fault_db),
        schema=read_workspace(workspace).schema_version,
        acceptance="Executor fictional checks only; no owner runtime PASS or binding G5",
    )
    (base / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2), flush=True)
    print(
        "PASS: installed versioned publication/read/repair, DB refusal, committed rebuild recovery",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-trial", type=Path)
    parser.add_argument("--exercise", type=Path)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    if args.exercise is not None and args.source is not None:
        exercise(args.exercise.resolve(), args.source.resolve())
        return
    if args.accepted_trial is None:
        parser.error("--accepted-trial is required")
    for name in ("STOP", "STEER.md"):
        if (ROOT / name).exists():
            raise SystemExit(f"STOP: read {name}")
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("STOP: required tool uv unavailable")
    accepted = args.accepted_trial.resolve()
    old_files = [
        accepted / "workspace/.zara/state.sqlite3",
        accepted / "zaratustra-0.3.0-py3-none-any.whl",
    ]
    old_hashes = {str(path): digest(path) for path in old_files}
    package_version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    base = Path(tempfile.mkdtemp(prefix="zaratustra-work4-")).resolve()
    if base.is_relative_to(ROOT) or base.is_relative_to(accepted):
        raise RuntimeError("Installed trial must be outside product and accepted inputs")
    (base / "unrelated-cwd").mkdir()
    shutil.copytree(accepted / "workspace", base / "workspace")
    wheel = base / f"zaratustra-{package_version}-py3-none-any.whl"
    shutil.copyfile(ROOT / "dist" / wheel.name, wheel)
    shutil.copyfile(Path(__file__), base / "exercise.py")
    environment = base / "venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    requirements = base / "runtime-requirements.txt"
    print(f"retained_trial={base}", flush=True)
    source_commit = run(["git", "rev-parse", "HEAD"], cwd=ROOT).strip()
    print(f"wheel_sha256={digest(wheel)}", flush=True)
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
        cwd=ROOT,
    )
    run(
        [uv, "venv", "--python", "3.13.7", "--python-preference", "only-managed", str(environment)],
        cwd=ROOT,
    )
    run(
        [uv, "pip", "install", "--python", str(python), "-r", str(requirements), str(wheel)],
        cwd=ROOT,
    )
    run([uv, "pip", "check", "--python", str(python)], cwd=ROOT)
    transcript = run(
        [
            str(python),
            "-I",
            str(base / "exercise.py"),
            "--exercise",
            str(base),
            "--source",
            str(ROOT),
        ],
        cwd=base / "unrelated-cwd",
        console=True,
    )
    (base / "transcript.txt").write_text(transcript, encoding="utf-8")
    assert {str(path): digest(path) for path in old_files} == old_hashes
    manifest = dict(
        source_commit=source_commit,
        version=package_version,
        retained_trial=str(base),
        wheel=str(wheel),
        wheel_sha256=digest(wheel),
        accepted_inputs_unchanged=old_hashes,
        installed_receipt=str(base / "receipt.json"),
    )
    (base / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    main()
