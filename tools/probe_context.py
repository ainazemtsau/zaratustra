"""Installed Work 6 trial on new copies of the accepted fictional Work 5 workspace."""

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
import zipfile
from importlib.metadata import version
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2), encoding="utf-8")


def command(args: list[str], cwd: Path) -> dict[str, Any]:
    result = subprocess.run(args, cwd=cwd, capture_output=True, encoding="utf-8", check=False)
    record = dict(
        command=args,
        cwd=str(cwd),
        exit=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
    if result.returncode:
        raise RuntimeError(record)
    return record


def exercise(base: Path, source: Path) -> None:
    import pydantic

    import zaratustra
    from zaratustra.core import (
        Artifact,
        ArtifactReference,
        ContextQuery,
        LocalAuthorization,
        MutationRequest,
        Work,
        WorkspaceError,
        apply_mutation,
        authorize_local,
        context,
        handoff_request,
        open_work,
        prepare_authorization,
        read_artifact,
        read_handoffs,
        read_records,
        read_workspace,
    )

    workspace = base / "workspace"
    package = Path(zaratustra.__file__).resolve().parent
    assert package.is_relative_to(base / "venv")
    assert not any(Path(p).resolve().is_relative_to(source) for p in sys.path if p)
    wheel = next(base.glob("*.whl"))
    identity = []
    with zipfile.ZipFile(wheel) as bundle:
        for name in bundle.namelist():
            if name.startswith("zaratustra/") and name.endswith(".py"):
                installed = package.parent / name
                assert (
                    installed.read_bytes()
                    == bundle.read(name)
                    == (source / "src" / name).read_bytes()
                )
                identity.append(dict(path=name, sha256=digest(installed)))
    save(base / "installed-source.json", identity)
    save(
        base / "runtime.json",
        dict(
            version=version("zaratustra"),
            package=str(package),
            python=sys.version,
            sqlite=sqlite3.sqlite_version,
            pydantic=pydantic.__version__,
            sys_path=sys.path,
        ),
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

    def confirmed(path: Path, value: ContextQuery | MutationRequest) -> LocalAuthorization:
        return authorize_local(
            prepare_authorization(path, value),
            channel="local-chat",
            actor="executor-fictional-adapter",
            source_ref="Work6-CALL:simulated-prior-permission",
        )

    def mutate(path: Path, name: str, content: bytes | None = None, **fields: Any) -> None:
        query = query_for(path)
        if name in ("authorize_artifact", "publish_artifact"):
            artifact = next(row for row in read_records(path).records if isinstance(row, Artifact))
            fields.update(version=2, artifact_id=artifact.id, artifact_revision=artifact.revision)
        if content is not None:
            fields.update(
                content_sha256=hashlib.sha256(content).hexdigest(), content_size=len(content)
            )
        request = MutationRequest.model_validate(
            dict(
                workspace_id=query.workspace_id,
                work_id=query.work_id,
                expected_revision=query.expected_revision,
                operation_id=uuid4(),
                operation=name,
                provenance="Fictional Work6 installed check",
            )
            | fields
        )
        apply_mutation(path, request, confirmed(path, request), content=content)

    query = query_for(workspace)
    before = digest(read_workspace(workspace).database)
    output = open_work(workspace, query, confirmed(workspace, query))
    (base / "context-library.json").write_bytes(output.output)
    save(base / "query.json", query.model_dump(mode="json"))
    value = json.loads(output.output)
    assert value["manifest"]["budget"]["used"] == len(output.output)
    assert open_work(workspace, query, confirmed(workspace, query)).output == output.output
    for row, item in zip(value["context"]["sources"], value["manifest"]["sources"], strict=True):
        canonical = json.dumps(
            row["data"], sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
        assert item["value_sha256"] == hashlib.sha256(canonical).hexdigest()
        if "content_base64" in row["data"]:
            raw = base64.b64decode(row["data"]["content_base64"], validate=True)
            assert item["content_sha256"] == hashlib.sha256(raw).hexdigest()
    save(base / "context-manifest.json", value["manifest"])
    save(
        base / "context-identity.json",
        dict(
            output_sha256=output.output_sha256,
            output_bytes=len(output.output),
            state_revision=query.expected_revision,
            database_sha256=before,
            source_count=len(value["manifest"]["sources"]),
        ),
    )

    checks: list[dict[str, Any]] = []

    def refusal(
        label: str,
        path: Path,
        request: ContextQuery,
        expected: str,
        *,
        caller: LocalAuthorization | None = None,
    ) -> None:
        prior = digest(read_workspace(path).database)
        try:
            open_work(path, request, caller)
        except WorkspaceError as error:
            assert expected in str(error), str(error)
            checks.append(
                dict(
                    case=label,
                    error=str(error),
                    query=request.model_dump(mode="json"),
                    before_db_sha256=prior,
                    after_db_sha256=digest(read_workspace(path).database),
                )
            )
            save(base / "hidden-checks.json", checks)
        else:
            raise AssertionError(f"{label}: unexpected output")

    refusal("no-permission", workspace, query, "permission_denied")
    for label, changes, expected in (
        ("stale", dict(expected_revision=query.expected_revision - 1), "conflict"),
        ("overflow", dict(max_bytes=len(output.output) - 1), "budget_exceeded"),
        ("foreign-process", dict(process_id=uuid4()), "scope"),
        (
            "foreign-artifact",
            dict(
                references=(
                    ArtifactReference(artifact_id=uuid4(), version_id=uuid4(), sha256="0" * 64),
                )
            ),
            "scope",
        ),
    ):
        altered = query.model_copy(update=changes)
        refusal(label, workspace, altered, expected, caller=confirmed(workspace, altered))

    def copied(label: str) -> Path:
        selected = base / "negative-copies" / label
        shutil.copytree(workspace, selected)
        return selected

    for label, operation in (("revoked", "revoke_work"), ("terminal", "cancel_work")):
        selected = copied(label)
        mutate(selected, operation)
        current = query_for(selected)
        refusal(label, selected, current, "permission_denied", caller=confirmed(selected, current))
    for label in ("missing", "corrupt"):
        selected = copied(label)
        ref = read_handoffs(selected)[0].handoff.basis[0]
        content = read_artifact(selected, ref.artifact_id, ref.version_id)
        file = selected / content.version.relative_path
        if label == "missing":
            file.unlink()  # Explicit negative copy; never repair operational DB.
        else:
            file.write_bytes(b"x" * len(content.content))
        refusal(label, selected, query, "content_", caller=confirmed(selected, query))

    for change in ("decision", "rights", "requirements", "bytes"):
        selected = copied(f"during-{change}")
        original = context._compile

        def interleaved(
            *args: Any,
            selected: Path = selected,
            change: str = change,
            original: Any = original,
            **kwargs: Any,
        ) -> Any:
            result = original(*args, **kwargs)
            if change == "decision":
                handoff = read_handoffs(selected)[-1].handoff.model_dump(mode="json")
                handoff.update(
                    handoff_id=str(uuid4()),
                    source_revision=query.expected_revision,
                    owner_instruction="Changed fictional decision during compilation",
                )
                mutation = handoff_request(
                    json.dumps(handoff).encode(), source_ref="executor:interleaving"
                )
                apply_mutation(selected, mutation, confirmed(selected, mutation))
            elif change == "rights":
                mutate(selected, "revoke_work")
            elif change == "requirements":
                mutate(selected, "set_work_requirements", requirements=("Changed dependency",))
            else:
                ref = read_handoffs(selected)[0].handoff.result
                content = read_artifact(selected, ref.artifact_id, ref.version_id)
                (selected / content.version.relative_path).unlink()
            return result

        with patch.object(context, "_compile", interleaved):
            expected = (
                "permission_denied"
                if change == "rights"
                else ("content_unavailable" if change == "bytes" else "conflict")
            )
            refusal(
                f"during-{change}", selected, query, expected, caller=confirmed(selected, query)
            )

    selected = copied("foreign-text-link")
    sentinel = base / "foreign-context.txt"
    secret = b"FOREIGN_FICTIONAL_SENTINEL_CONTENT"
    sentinel.write_bytes(secret)
    mutate(selected, "authorize_artifact")
    mutate(selected, "publish_artifact", ("Inert link: " + sentinel.as_uri()).encode())
    current = query_for(selected)
    foreign_output = open_work(selected, current, confirmed(selected, current)).output
    (base / "foreign-link-context.json").write_bytes(foreign_output)
    contents = [
        base64.b64decode(row["data"]["content_base64"])
        for row in json.loads(foreign_output)["context"]["sources"]
        if "content_base64" in row["data"]
    ]
    assert all(secret not in content for content in contents)
    checks.append(
        dict(
            case="foreign-text-link",
            sentinel_sha256=digest(sentinel),
            output_sha256=hashlib.sha256(foreign_output).hexdigest(),
            foreign_content_disclosed=False,
        )
    )
    save(base / "hidden-checks.json", checks)
    assert digest(read_workspace(workspace).database) == before
    save(
        base / "exercise-receipt.json",
        dict(
            checks=len(checks),
            before_db_sha256=before,
            after_db_sha256=digest(read_workspace(workspace).database),
            acceptance="Executor checks; no owner runtime, clean chat or binding G5 verdict",
        ),
    )
    print(f"PASS: installed context and {len(checks)} hidden checks; trial={base}", flush=True)


def console_checks(base: Path) -> None:
    from zaratustra.core import ContextQuery, prepare_authorization

    workspace = base / "workspace"
    query = ContextQuery.model_validate_json((base / "query.json").read_bytes())
    zara = base / "venv" / ("Scripts/zara.exe" if os.name == "nt" else "bin/zara")
    records = []
    for label, changes, expected in (
        ("open", {}, 0),
        ("stale", dict(expected_revision=query.expected_revision - 1), 1),
        ("budget", dict(max_bytes=5000), 1),
        ("scope", dict(process_id=uuid4()), 1),
    ):
        current = ContextQuery.model_validate(query.model_dump() | changes)
        args = [
            str(zara),
            "work",
            "open",
            str(current.work_id),
            "--workspace",
            str(workspace),
            "--workspace-id",
            str(current.workspace_id),
            "--process",
            str(current.process_id),
            "--expected-revision",
            str(current.expected_revision),
            "--max-bytes",
            str(current.max_bytes),
        ]
        save(
            base / f"console-{label}-prompt.json",
            prepare_authorization(workspace, current).model_dump(mode="json"),
        )
        print(f"Executor fictional console check: {label}", flush=True)
        result = subprocess.run(
            args, cwd=base / "unrelated-cwd", stdout=subprocess.PIPE, stderr=None, check=False
        )
        (base / f"console-{label}.stdout").write_bytes(result.stdout)
        records.append(
            dict(
                label=label,
                command=args,
                cwd=str(base / "unrelated-cwd"),
                exit=result.returncode,
                stdout_sha256=hashlib.sha256(result.stdout).hexdigest(),
                stderr="inherited console; retained terminal-session transcript",
            )
        )
        save(base / "console-checks.json", records)
        assert result.returncode == expected
        if expected == 0:
            assert result.stdout == (base / "context-library.json").read_bytes()
        else:
            assert result.stdout == b""
    print(
        "PASS: actual installed console open/stale/budget/scope; executor confirmations only",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-trial", type=Path)
    parser.add_argument("--exercise", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--console", type=Path)
    args = parser.parse_args()
    if args.console is not None:
        console_checks(args.console.resolve())
        return
    if args.exercise is not None and args.source is not None:
        exercise(args.exercise.resolve(), args.source.resolve())
        return
    if args.accepted_trial is None:
        parser.error("--accepted-trial is required")
    for name in ("STOP", "STEER.md"):
        if (ROOT / name).exists():
            raise SystemExit(f"STOP: read {name}")
    accepted = args.accepted_trial.resolve()
    expected = json.loads(
        (ROOT / "docs/work5/evidence/retained-trial-v2-manifest.json").read_text(encoding="utf-8")
    )
    before = {name: digest(accepted / name) for name in expected["files"]}
    assert before == expected["files"], "Accepted Work 5 trial does not match retained v2"
    base = Path(tempfile.mkdtemp(prefix="zaratustra-work6-")).resolve()
    shutil.copytree(accepted / "workspace", base / "workspace")
    (base / "unrelated-cwd").mkdir()
    wheel = base / "zaratustra-0.6.0-py3-none-any.whl"
    shutil.copyfile(ROOT / "dist" / wheel.name, wheel)
    shutil.copyfile(Path(__file__), base / "exercise.py")
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("STOP: required uv unavailable")
    python = base / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    requirements = base / "runtime-requirements.txt"
    runs = [
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
            ROOT,
        ),
        command([uv, "venv", "--python", str(Path(sys.executable)), str(base / "venv")], ROOT),
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
            ROOT,
        ),
        command([uv, "pip", "check", "--python", str(python)], ROOT),
    ]
    save(base / "install.json", runs)
    run = command(
        [
            str(python),
            "-I",
            str(base / "exercise.py"),
            "--exercise",
            str(base),
            "--source",
            str(ROOT),
        ],
        base / "unrelated-cwd",
    )
    save(base / "installed-run.json", run)
    after = {name: digest(accepted / name) for name in before}
    assert after == before
    save(
        base / "manifest.json",
        dict(
            trial=str(base),
            accepted_trial=str(accepted),
            source_commit=command(["git", "rev-parse", "HEAD"], ROOT)["stdout"].strip(),
            wheel_sha256=digest(wheel),
            accepted_before=before,
            accepted_after=after,
            accepted_directories=expected["directories"],
            exercise_exit=run["exit"],
        ),
    )
    print(run["stdout"], flush=True)


if __name__ == "__main__":
    main()
