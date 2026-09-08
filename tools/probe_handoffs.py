"""Installed Work 5 on new accepted-fictional copies; console input is executor evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2), encoding="utf-8")


def command(args: list[str], *, cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, encoding="utf-8", check=True)
    print(result.stdout + result.stderr, flush=True)
    return result.stdout


def exercise(base: Path, source: Path) -> None:
    from importlib.metadata import version

    import pydantic

    import zaratustra
    from zaratustra.core import (
        ArtifactError,
        MutationError,
        MutationRequest,
        ProjectionRebuildError,
        Work,
        WorkspaceError,
        apply_mutation,
        authorize_local,
        handoff_request,
        prepare_authorization,
        read_artifact,
        read_handoffs,
        read_history,
        read_projection_status,
        read_records,
        read_workspace,
        rebuild_projections,
    )

    workspace = base / "workspace"
    zara = base / "venv" / ("Scripts/zara.exe" if os.name == "nt" else "bin/zara")
    cwd = base / "unrelated-cwd"
    package = Path(zaratustra.__file__).resolve().parent
    assert package.is_relative_to(base / "venv")
    assert not any(Path(p).resolve().is_relative_to(source) for p in sys.path if p)
    wheel = next(base.glob("*.whl"))
    identity = []
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith("zaratustra/") and name.endswith(".py"):
                installed = package.parent / name
                expected = archive.read(name)
                assert installed.read_bytes() == expected == (source / "src" / name).read_bytes()
                identity.append(dict(path=name, sha256=digest(installed)))
    save(base / "installed-source.json", identity)
    runtime = dict(
        version=version("zaratustra"),
        package=str(package),
        python=sys.version,
        sqlite=sqlite3.sqlite_version,
        pydantic=pydantic.__version__,
        sys_path=sys.path,
    )
    save(base / "runtime.json", runtime)
    print(json.dumps(runtime, indent=2), flush=True)
    runs: list[dict[str, Any]] = []

    def cli(
        label: str,
        args: list[str],
        *,
        data: bytes | None = None,
        console: bool = False,
        expected: int = 0,
    ) -> str:
        full = [str(zara), *args]
        if label == "stdin-without-console" and os.name == "nt":
            # Windows launchers can allocate a console for a detached child. Detach
            # in the final installed interpreter, immediately before the real CLI.
            code = (
                "import ctypes; import sys; from zaratustra.cli import main; "
                "ctypes.windll.kernel32.FreeConsole(); sys.exit(main())"
            )
            full = [sys.executable, "-I", "-c", code, *args]
        print("$ " + subprocess.list2cmdline(full), flush=True)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            full,
            cwd=cwd,
            env=env,
            input=data.decode("utf-8") if data else None,
            stdin=None if data or console else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=None if console else subprocess.PIPE,
            encoding="utf-8",
            creationflags=(0x08000000 if os.name == "nt" and not console else 0),
            timeout=None if console else 30,
        )
        record = dict(
            label=label,
            command=full,
            input_sha256=hashlib.sha256(data).hexdigest() if data else None,
            stdout=result.stdout,
            stderr=result.stderr,
            console=console,
            exit=result.returncode,
        )
        runs.append(record)
        save(base / "cli.json", runs)
        print(result.stdout, flush=True)
        if result.stderr:
            print(result.stderr, flush=True)
        print(f"exit={result.returncode}", flush=True)
        if result.returncode != expected:
            raise RuntimeError(f"{label}: expected {expected}; got {result.returncode}")
        return result.stdout

    cli("version", ["--version"])
    before = read_records(workspace)
    history_before = read_history(workspace)
    cli("explicit-upgrade", ["migrate", str(workspace), "--to", "5"])
    assert read_records(workspace) == before and read_history(workspace) == history_before
    assert read_workspace(workspace).schema_version == 5
    save(
        base / "pre-import.json",
        dict(
            snapshot=before.model_dump(mode="json"), history=history_before.model_dump(mode="json")
        ),
    )

    def document(path: Path, label: str) -> bytes:
        state = read_records(path)
        work = next(row for row in state.records if isinstance(row, Work))
        versions = [
            event.artifact_version for event in read_history(path).events if event.artifact_version
        ]
        refs = [
            dict(artifact_id=str(v.artifact_id), version_id=str(v.id), sha256=v.sha256)
            for v in versions
        ]
        return json.dumps(
            dict(
                kind="handoff",
                version=1,
                handoff_id=str(uuid4()),
                workspace_id=str(state.workspace_id),
                process=str(work.process_id),
                related_work=str(work.id),
                intent="accepted_result",
                source_revision=state.state_revision,
                result=refs[-1],
                basis=[refs[0]],
                provenance="Fictional observation accepted because the silver rim is visible.",
                owner_instruction="  Fictional quoted decision: retain this observation.  ",
                constraints=["Only the fictional observatory"],
                open_questions=["Continuation belongs to a later admitted Work"],
                created_by=f"executor-fictional-{label}",
            ),
            ensure_ascii=True,
            indent=2,
        ).encode("utf-8")

    first = document(workspace, "file")
    first_path = base / "handoff-file.json"
    first_path.write_bytes(first)
    first_request = handoff_request(first, source_ref=first_path.as_posix())
    save(
        base / "file-prompt.json",
        prepare_authorization(workspace, first_request).model_dump(mode="json"),
    )
    cli(
        "file-without-permission",
        ["handoff", "import", str(workspace), str(first_path)],
        expected=1,
    )
    assert read_handoffs(workspace) == ()
    receipt = json.loads(
        cli("file-import", ["handoff", "import", str(workspace), str(first_path)], console=True)
    )
    assert read_handoffs(workspace)[0].receipt.model_dump(mode="json") == receipt
    second = document(workspace, "stdin")
    (base / "handoff-stdin.json").write_bytes(second)
    second_request = handoff_request(second, source_ref="stdin")
    save(
        base / "stdin-prompt.json",
        prepare_authorization(workspace, second_request).model_dump(mode="json"),
    )
    unchanged = digest(read_workspace(workspace).database)
    cli(
        "stdin-without-console", ["handoff", "import", str(workspace), "-"], data=second, expected=1
    )
    assert digest(read_workspace(workspace).database) == unchanged
    second_receipt = json.loads(
        cli("stdin-import", ["handoff", "import", str(workspace), "-"], data=second, console=True)
    )
    assert len(read_handoffs(workspace)) == 2
    current = read_records(workspace).state_revision
    cli(
        "original-stale-replay",
        ["handoff", "import", str(workspace), str(first_path)],
        console=True,
        expected=1,
    )
    duplicate = json.loads(
        cli(
            "refreshed-stdin-duplicate",
            ["handoff", "import", str(workspace), "-", "--expected-revision", str(current)],
            data=first,
            console=True,
        )
    )
    assert duplicate == receipt and len(read_handoffs(workspace)) == 2
    cli("saved-acceptances", ["handoff", "list", str(workspace)])
    cli("history", ["history", str(workspace)])
    cli("projections", ["projections", "status", str(workspace)])
    cli("schema", ["handoff", "schema"])
    save(base / "acceptances.json", [x.model_dump(mode="json") for x in read_handoffs(workspace)])

    # Installed hidden-fault trial: explicit simulated prior-permission adapter.
    fault = base / "fault-workspace"
    shutil.copytree(workspace, fault)
    fault_data = document(fault, "fault")
    (base / "handoff-fault.json").write_bytes(fault_data)
    request = handoff_request(fault_data, source_ref="executor:fault-fixture")

    def confirmed(path: Path, value: MutationRequest) -> Any:
        return authorize_local(
            prepare_authorization(path, value),
            channel="local-chat",
            actor="executor-fictional-adapter",
            source_ref="development-CALL:simulated-prior-permission",
        )

    checks: list[dict[str, Any]] = []
    database = read_workspace(fault).database
    original_db = digest(database)
    try:
        apply_mutation(fault, request)
    except MutationError as error:
        assert error.code == "permission_denied"
        checks.append(dict(case="untrusted-import", error=str(error)))
    else:
        raise AssertionError("Untrusted import was accepted")
    caller = confirmed(fault, request)
    connect = sqlite3.connect
    for target in ("accepted_handoffs", "COMMIT"):

        def denied(*args: Any, blocked_target: str = target, **kwargs: Any) -> sqlite3.Connection:
            connection: sqlite3.Connection = connect(*args, **kwargs)
            connection.set_authorizer(
                lambda action, name, *_: (
                    sqlite3.SQLITE_DENY
                    if name == blocked_target
                    and action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_TRANSACTION)
                    else sqlite3.SQLITE_OK
                )
            )
            return connection

        with patch("sqlite3.connect", denied):
            try:
                apply_mutation(fault, request, caller)
            except WorkspaceError as error:
                checks.append(dict(case=f"rollback-{target}", error=str(error)))
            else:
                raise AssertionError("Fault did not refuse")
        assert digest(database) == original_db

    def fail_projection(*_: object) -> None:
        raise OSError("installed injected projection failure")

    with patch("zaratustra.core.mutations.write_projection", fail_projection):
        try:
            apply_mutation(fault, request, caller)
        except ProjectionRebuildError as error:
            committed = error.receipt
            checks.append(
                dict(
                    case="committed-rebuild-failure",
                    error=str(error),
                    receipt=committed.model_dump(mode="json"),
                )
            )
        else:
            raise AssertionError("Rebuild fault did not report committed receipt")
    committed_db = digest(database)
    assert rebuild_projections(fault).status == "current" and digest(database) == committed_db
    assert request.handoff is not None
    ref = request.handoff.result
    content = read_artifact(fault, ref.artifact_id, ref.version_id)
    missing_path = fault / content.version.relative_path
    missing_path.unlink()  # Explicit new negative fixture only.
    replay = request.model_copy(update={"expected_revision": read_records(fault).state_revision})
    assert apply_mutation(fault, replay, confirmed(fault, replay)) == committed
    try:
        read_artifact(fault, ref.artifact_id, ref.version_id)
    except ArtifactError as error:
        checks.append(dict(case="late-unavailable-after-receipt", error=str(error)))
    else:
        raise AssertionError("Missing bytes were accepted")
    assert len(read_handoffs(fault)) == 3 and digest(database) == committed_db
    assert read_projection_status(fault).status == "current"
    save(base / "hidden-checks.json", checks)
    save(
        base / "receipt.json",
        dict(
            runtime=runtime,
            file_receipt=receipt,
            stdin_receipt=second_receipt,
            database_sha256=digest(read_workspace(workspace).database),
            fault_database_sha256=digest(database),
            hidden_checks=checks,
            acceptance="Executor evidence only; no owner runtime PASS, fresh G5 or T4/M0 close",
        ),
    )
    print(
        "PASS: installed file/stdin, current authority, replay, persistence and fault boundaries",
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
        raise SystemExit("STOP: required uv unavailable")
    accepted = args.accepted_trial.resolve()
    old = {
        str(p): digest(p)
        for p in accepted.rglob("*")
        if p.is_file() and not p.is_relative_to(accepted / "venv")
    }
    base = Path(tempfile.mkdtemp(prefix="zaratustra-work5-")).resolve()
    if base.is_relative_to(ROOT) or base.is_relative_to(accepted):
        raise RuntimeError("Select a separate trial")
    (base / "unrelated-cwd").mkdir()
    shutil.copytree(accepted / "workspace", base / "workspace")
    wheel = base / "zaratustra-0.5.0-py3-none-any.whl"
    shutil.copyfile(ROOT / "dist" / wheel.name, wheel)
    shutil.copyfile(Path(__file__), base / "exercise.py")
    print(f"retained_trial={base}", flush=True)
    python = base / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    requirements = base / "runtime-requirements.txt"
    command(
        [
            uv,
            "export",
            "--locked",
            "--offline",
            "--no-dev",
            "--no-emit-project",
            "--no-hashes",
            "--output-file",
            str(requirements),
        ],
        cwd=ROOT,
    )
    command([uv, "venv", "--python", str(Path(sys.executable)), str(base / "venv")], cwd=ROOT)
    command(
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
        cwd=ROOT,
    )
    command([uv, "pip", "check", "--python", str(python)], cwd=ROOT)
    child = subprocess.run(
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
        check=False,
    )
    assert {name: digest(Path(name)) for name in old} == old
    save(
        base / "manifest.json",
        dict(
            source_commit=command(["git", "rev-parse", "HEAD"], cwd=ROOT).strip(),
            trial=str(base),
            wheel=str(wheel),
            wheel_sha256=digest(wheel),
            accepted_inputs_unchanged=old,
            exercise_exit=child.returncode,
        ),
    )
    raise SystemExit(child.returncode)


if __name__ == "__main__":
    main()
