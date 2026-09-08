"""Installed Work7 trial, exact console delivery and bounded hidden failure checks."""

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
from importlib.metadata import version
from pathlib import Path
from typing import Any, Never
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2), encoding="utf-8")


def run(args: list[str], cwd: Path) -> dict[str, Any]:
    result = subprocess.run(args, cwd=cwd, capture_output=True, encoding="utf-8", check=False)
    value = dict(
        command=args,
        cwd=str(cwd),
        exit=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
    if result.returncode:
        raise RuntimeError(value)
    return value


def executable(base: Path, name: str) -> Path:
    return base / "venv" / (f"Scripts/{name}.exe" if os.name == "nt" else f"bin/{name}")


def confirm(path: Path, value: Any) -> Any:
    from zaratustra.core import authorize_local, prepare_authorization

    return authorize_local(
        prepare_authorization(path, value),
        channel="local-chat",
        actor="executor-fictional-adapter",
        source_ref="Work7:simulated-prior-permission",
    )


def prepare(base: Path, source: Path) -> None:
    import pydantic

    import zaratustra
    from zaratustra.core import (
        ContextQuery,
        MutationRequest,
        NextWork,
        ResultSubmission,
        Work,
        migrate_workspace,
        open_work,
        read_handoffs,
        read_records,
        read_workspace,
    )

    installed = Path(zaratustra.__file__).resolve().parent
    assert installed.is_relative_to(base / "venv")
    assert not any(Path(p).resolve().is_relative_to(source) for p in sys.path if p)
    wheel = next(base.glob("*.whl"))
    identity = []
    with zipfile.ZipFile(wheel) as bundle:
        for name in bundle.namelist():
            if name.startswith("zaratustra/") and name.endswith(".py"):
                assert (
                    (installed.parent / name).read_bytes()
                    == bundle.read(name)
                    == (source / "src" / name).read_bytes()
                )
                identity.append(dict(path=name, sha256=sha(installed.parent / name)))
    save(base / "installed-source.json", identity)
    save(
        base / "runtime.json",
        dict(
            version=version("zaratustra"),
            python=sys.version,
            sqlite=sqlite3.sqlite_version,
            pydantic=pydantic.__version__,
            package=str(installed),
            sys_path=sys.path,
        ),
    )
    path = base / "workspace"
    state = read_records(path)
    work = next(r for r in state.records if isinstance(r, Work))
    q = ContextQuery(
        workspace_id=state.workspace_id,
        work_id=work.id,
        process_id=work.process_id,
        expected_revision=state.state_revision,
        max_bytes=65536,
    )
    old = open_work(path, q, confirm(path, q)).output
    assert old == (source / "docs/work6/evidence/context-library.json").read_bytes()
    (base / "work6-context.stdout").write_bytes(old)
    before = sha(read_workspace(path).database)
    info = migrate_workspace(path, target_version=6)
    assert info.schema_version == 6 and read_records(path) == state
    save(
        base / "migration.json",
        dict(
            before=before,
            after=sha(info.database),
            old_schema=5,
            new_schema=6,
            revision=state.state_revision,
        ),
    )
    accepted = read_handoffs(path)
    request = MutationRequest(
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
    save(base / "request.json", request.model_dump(mode="json"))
    shutil.copytree(path, base / "negative-copies/pre-submit")
    save(
        base / "prepare.json",
        dict(
            request_sha256=sha(base / "request.json"),
            revision=state.state_revision,
            old_context_sha256=sha(base / "work6-context.stdout"),
            mutation="not yet submitted",
        ),
    )
    print(f"Prepared installed fictional trial: {base}", flush=True)


def console(base: Path) -> None:
    from zaratustra.core import ContextQuery, MutationRequest, ReceiptQuery, prepare_authorization

    path = base / "workspace"
    request = MutationRequest.model_validate_json((base / "request.json").read_bytes())
    assert request.submission is not None
    query = ReceiptQuery(
        workspace_id=request.workspace_id,
        work_id=request.work_id,
        operation_id=request.operation_id,
    )
    next_id = request.submission.next_work.work_id
    prompt = prepare_authorization(path, request)
    source_work = next(r for r in prompt.current.records if r.id == request.work_id)
    process_id = source_work.model_dump()["process_id"]
    next_query = ContextQuery(
        workspace_id=request.workspace_id,
        work_id=next_id,
        process_id=process_id,
        expected_revision=request.expected_revision + 1,
        max_bytes=65536,
    )
    save(base / "query.json", next_query.model_dump(mode="json"))
    save(base / "receipt-query.json", query.model_dump(mode="json"))
    zara = str(executable(base, "zara"))
    rows = []
    for label in ("submit", "discover", "next", "replay", "stale", "budget"):
        expected = 0 if label in ("submit", "discover", "next") else 1
        if label in ("submit", "replay"):
            value: Any = request
            args = [zara, "result", "submit", str(path), str(base / "request.json")]
        elif label == "discover":
            value = query
            args = [zara, "result", "read", str(path), query.model_dump_json()]
        else:
            changes = (
                dict(expected_revision=request.expected_revision)
                if label == "stale"
                else dict(max_bytes=5000)
                if label == "budget"
                else {}
            )
            value = ContextQuery.model_validate(next_query.model_dump() | changes)
            args = [
                zara,
                "work",
                "open",
                str(next_id),
                "--workspace",
                str(path),
                "--workspace-id",
                str(value.workspace_id),
                "--process",
                str(value.process_id),
                "--expected-revision",
                str(value.expected_revision),
                "--max-bytes",
                str(value.max_bytes),
            ]
        save(
            base / f"console-{label}-prompt.json",
            prepare_authorization(path, value).model_dump(mode="json"),
        )
        print(f"Executor fictional console check: {label}", flush=True)
        result = subprocess.run(
            args, cwd=base / "unrelated-cwd", stdout=subprocess.PIPE, stderr=None, check=False
        )
        (base / f"console-{label}.stdout").write_bytes(result.stdout)
        rows.append(
            dict(
                label=label,
                command=args,
                cwd=str(base / "unrelated-cwd"),
                exit=result.returncode,
                stdout_sha256=sha(base / f"console-{label}.stdout"),
                stdout_bytes=len(result.stdout),
                stderr="retained terminal transcript",
            )
        )
        save(base / "console-checks.json", rows)
        assert result.returncode == expected
        if expected:
            assert result.stdout == b""
    print("PASS: actual console submit/discovery/next/replay/stale/budget", flush=True)


def exercise(base: Path) -> None:
    from zaratustra.core import (
        ContextQuery,
        MutationRequest,
        ProjectionRebuildError,
        ReceiptQuery,
        Work,
        WorkspaceError,
        apply_mutation,
        context,
        mutations,
        open_work,
        read_records,
        read_result,
        read_workspace,
        rebuild_projections,
        submit_result,
    )

    path = base / "workspace"
    request = MutationRequest.model_validate_json((base / "request.json").read_bytes())
    query = ReceiptQuery.model_validate_json((base / "receipt-query.json").read_bytes())
    q = ContextQuery.model_validate_json((base / "query.json").read_bytes())
    saved = read_result(path, query, confirm(path, query))
    assert saved.event.request == request
    assert saved.model_dump(mode="json") == json.loads(
        (base / "console-discover.stdout").read_bytes()
    )
    assert saved.receipt.model_dump(mode="json") == json.loads(
        (base / "console-submit.stdout").read_bytes()
    )
    wire = open_work(path, q, confirm(path, q)).output
    assert wire == (base / "console-next.stdout").read_bytes()
    (base / "context-library.json").write_bytes(wire)
    save(base / "context-manifest.json", json.loads(wire)["manifest"])
    save(base / "result.json", saved.model_dump(mode="json"))
    before = sha(read_workspace(path).database)
    checks: list[dict[str, Any]] = []

    def copy(label: str, pre: bool = False) -> Path:
        target = base / "negative-copies" / label
        shutil.copytree(base / "negative-copies/pre-submit" if pre else path, target)
        return target

    def refuse(label: str, fn: Any, expected: str) -> None:
        try:
            fn()
        except WorkspaceError as error:
            assert expected in str(error), str(error)
            checks.append(dict(label=label, outcome="expected refusal", detail=str(error)))
        else:
            raise AssertionError(label)

    for label, change, expected in (
        ("terminal-original", {}, "permission_denied"),
        ("terminal-new-id", dict(operation_id=uuid4()), "permission_denied"),
        ("stale", dict(expected_revision=request.expected_revision - 1), "conflict"),
        (
            "collision",
            dict(
                operation_id=request.submission.acceptance_ids[0] if request.submission else uuid4()
            ),
            "collision",
        ),
    ):
        target = copy(label, pre=label in ("stale", "collision"))
        altered = MutationRequest.model_validate(request.model_dump() | change)
        unchanged = sha(read_workspace(target).database)
        refuse(label, lambda p=target, r=altered: submit_result(p, r, confirm(p, r)), expected)
        assert sha(read_workspace(target).database) == unchanged
    target = copy("no-authority", pre=True)
    refuse("no-authority", lambda: submit_result(target, request), "permission_denied")
    target = copy("postcommit", pre=True)
    original_rebuild = mutations.rebuild_projections

    def lost(path: Path) -> Never:
        raise RuntimeError("simulated lost response after commit")

    mutations.rebuild_projections = lost
    try:
        try:
            submit_result(target, request, confirm(target, request))
        except RuntimeError as error:
            checks.append(dict(label="lost-response", detail=str(error)))
    finally:
        mutations.rebuild_projections = original_rebuild
    assert read_result(target, query, confirm(target, query)).next_work_id == saved.next_work_id
    assert open_work(target, q, confirm(target, q)).output
    assert rebuild_projections(target).status == "current"
    target = copy("projection-failure", pre=True)

    def projection_error(path: Path) -> Never:
        raise OSError("simulated projection failure")

    mutations.rebuild_projections = projection_error
    try:
        try:
            submit_result(target, request, confirm(target, request))
        except ProjectionRebuildError as error:
            assert error.receipt.new_revision == q.expected_revision
            checks.append(
                dict(label="projection-failure", receipt=error.receipt.model_dump(mode="json"))
            )
    finally:
        mutations.rebuild_projections = original_rebuild
    assert read_result(target, query, confirm(target, query)).next_work_id == saved.next_work_id
    for label in ("missing", "corrupt", "late-loss"):
        target = copy(label)
        ref = saved.event.result_references[0]
        content = target / "artifacts" / str(ref.artifact_id) / f"{ref.version_id}.blob"
        original_compile = context._compile

        def remove_after_compile(
            collected: context._Collected,
            query: ContextQuery,
            *,
            compiled: Any = original_compile,
            file: Path = content,
        ) -> context.ContextPackage:
            package: context.ContextPackage = compiled(collected, query)
            file.unlink()
            return package

        try:
            if label == "missing":
                content.unlink()
            elif label == "corrupt":
                content.write_bytes(b"diagnostic damaged content")
            else:
                context._compile = remove_after_compile
            assert (
                read_result(target, query, confirm(target, query)).next_work_id
                == saved.next_work_id
            )
            refuse(label, lambda p=target: open_work(p, q, confirm(p, q)), "content_")
        finally:
            context._compile = original_compile
    for label, changes, expected in (
        ("budget", dict(max_bytes=len(wire) - 1), "budget_exceeded"),
        ("foreign-process", dict(process_id=uuid4()), "scope"),
        (
            "foreign-ref",
            dict(references=[dict(artifact_id=uuid4(), version_id=uuid4(), sha256="0" * 64)]),
            "scope",
        ),
    ):
        altered_query = ContextQuery.model_validate(q.model_dump() | changes)
        refuse(
            label,
            lambda query=altered_query: open_work(path, query, confirm(path, query)),
            expected,
        )
    target = copy("revoked-next")
    revocation = MutationRequest(
        operation_id=uuid4(),
        workspace_id=q.workspace_id,
        work_id=q.work_id,
        expected_revision=q.expected_revision,
        operation="revoke_work",
        provenance="Explicit fictional diagnostic",
    )
    apply_mutation(target, revocation, confirm(target, revocation))
    refuse("revoked-next", lambda p=target: open_work(p, q, confirm(p, q)), "permission_denied")
    assert len([r for r in read_records(path).records if isinstance(r, Work)]) == 2
    assert sha(read_workspace(path).database) == before
    save(base / "hidden-checks.json", checks)
    save(
        base / "exercise-receipt.json",
        dict(
            checks=len(checks),
            database_sha256=before,
            output_sha256=sha(base / "context-library.json"),
            output_bytes=len(wire),
            state_revision=q.expected_revision,
            acceptance="executor checks; owner runtime/clean-chat/fresh G5 unverified",
        ),
    )
    print(f"PASS: installed Result/restart/context and {len(checks)} diagnostic checks", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-trial", type=Path)
    parser.add_argument("--prepare", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--console", type=Path)
    parser.add_argument("--exercise", type=Path)
    args = parser.parse_args()
    if args.console:
        console(args.console.resolve())
    elif args.exercise:
        exercise(args.exercise.resolve())
    elif args.prepare and args.source:
        prepare(args.prepare.resolve(), args.source.resolve())
    else:
        if args.accepted_trial is None:
            parser.error("--accepted-trial required")
        if any((ROOT / name).exists() for name in ("STOP", "STEER.md")):
            raise SystemExit("STOP: read STOP/STEER.md")
        accepted = args.accepted_trial.resolve()
        expected = json.loads(
            (ROOT / "docs/work6/evidence/retained-trial-manifest.json").read_text()
        )
        assert {n: sha(accepted / n) for n in expected["files"]} == expected["files"]
        assert all((accepted / n).is_dir() for n in expected["directories"])
        base = Path(tempfile.mkdtemp(prefix="zaratustra-work7-")).resolve()
        shutil.copytree(accepted / "workspace", base / "workspace")
        (base / "unrelated-cwd").mkdir()
        wheel = base / "zaratustra-0.7.0-py3-none-any.whl"
        shutil.copyfile(ROOT / "dist" / wheel.name, wheel)
        shutil.copyfile(Path(__file__), base / "exercise.py")
        uv = shutil.which("uv")
        if uv is None:
            raise SystemExit("STOP: required uv unavailable")
        requirements = base / "runtime-requirements.txt"
        commands = [
            run(
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
                ROOT,
            ),
            run([uv, "venv", "--python", sys.executable, str(base / "venv")], ROOT),
            run(
                [
                    uv,
                    "pip",
                    "install",
                    "--offline",
                    "--python",
                    str(executable(base, "python")),
                    "-r",
                    str(requirements),
                    str(wheel),
                ],
                ROOT,
            ),
            run([uv, "pip", "check", "--python", str(executable(base, "python"))], ROOT),
        ]
        save(base / "install.json", commands)
        prepared = run(
            [
                str(executable(base, "python")),
                "-I",
                str(base / "exercise.py"),
                "--prepare",
                str(base),
                "--source",
                str(ROOT),
            ],
            base / "unrelated-cwd",
        )
        save(base / "installed-prepare.json", prepared)
        save(
            base / "manifest.json",
            dict(
                trial=str(base),
                accepted_trial=str(accepted),
                source_commit=run(["git", "rev-parse", "HEAD"], ROOT)["stdout"].strip(),
                wheel_sha256=sha(wheel),
            ),
        )
        print(str(base), flush=True)


if __name__ == "__main__":
    main()
