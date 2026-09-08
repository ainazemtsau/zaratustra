"""Retained installed Work 3 trial. Run in a terminal; confirm each displayed request.

This executor/owner preparation probe does not infer owner runtime acceptance.
It preserves the accepted v2 original and never writes DB state except via Core.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-trial", type=Path, required=True)
    args = parser.parse_args()
    for name in ("STOP", "STEER.md"):
        if (ROOT / name).exists():
            raise SystemExit(f"STOP: read {name}")
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("STOP: required tool uv unavailable")
    accepted = args.accepted_trial.resolve()
    old_database = accepted / "workspace/.zara/state.sqlite3"
    old_wheel = accepted / "zaratustra-0.2.0-py3-none-any.whl"
    original_hashes = {str(path): digest(path) for path in (old_database, old_wheel)}
    package_version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    base = Path(tempfile.mkdtemp(prefix="zaratustra-work3-")).resolve()
    if base.is_relative_to(ROOT) or base.is_relative_to(accepted):
        raise RuntimeError("Installed trial must be separate from product and accepted inputs")
    working = base / "unrelated-cwd"
    working.mkdir()
    workspace = base / "workspace"
    shutil.copytree(accepted / "workspace", workspace)
    wheel = base / f"zaratustra-{package_version}-py3-none-any.whl"
    shutil.copyfile(ROOT / "dist" / wheel.name, wheel)
    environment = base / "venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    zara = environment / ("Scripts/zara.exe" if os.name == "nt" else "bin/zara")
    old_zara = accepted / "venv" / ("Scripts/zara.exe" if os.name == "nt" else "bin/zara")
    requirements = base / "runtime-requirements.txt"
    transcript = base / "transcript.txt"
    child_env = dict(os.environ)
    child_env.pop("PYTHONPATH", None)
    child_env["PYTHONIOENCODING"] = "utf-8"

    def log(message: str) -> None:
        print(message, flush=True)
        with transcript.open("a", encoding="utf-8", newline="") as stream:
            stream.write(message + chr(10))

    def run(
        command: list[str], *, expected: int = 0, console: bool = False, cwd: Path = working
    ) -> str:
        log("$ " + subprocess.list2cmdline(command))
        # Console stdin/stderr remain real terminal handles. No test approval bypass.
        result = subprocess.run(
            command,
            cwd=cwd,
            env=child_env,
            stdin=None if console else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=None if console else subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        log(result.stdout)
        if result.stderr:
            log(result.stderr)
        log(f"exit={result.returncode}")
        if result.returncode != expected:
            raise RuntimeError(f"Expected exit {expected}; got {result.returncode}")
        return result.stdout

    log(f"retained_trial={base}")
    commit = run(["git", "rev-parse", "HEAD"], cwd=ROOT).strip()
    log(f"source_commit={commit}")
    log(f"wheel_sha256={digest(wheel)}")
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
    run([uv, "venv", "--python", "3.13.7", "--python-preference", "only-managed", str(environment)])
    run([uv, "pip", "install", "--python", str(python), "-r", str(requirements), str(wheel)])
    run([uv, "pip", "check", "--python", str(python)])
    isolated = """
import importlib.metadata, json, sqlite3, sys
from pathlib import Path
import pydantic, zaratustra
package = Path(zaratustra.__file__).resolve()
assert package.is_relative_to(Path(sys.argv[1]).resolve())
assert not package.is_relative_to(Path(sys.argv[2]).resolve())
assert not any(Path(p).resolve().is_relative_to(Path(sys.argv[2]).resolve()) for p in sys.path if p)
print(json.dumps(dict(version=importlib.metadata.version('zaratustra'), python=sys.version,
    sqlite=sqlite3.sqlite_version, pydantic=pydantic.__version__, package=str(package)), indent=2))
"""
    runtime = json.loads(run([str(python), "-I", "-c", isolated, str(environment), str(ROOT)]))
    assert runtime["version"] == package_version
    original = json.loads(run([str(old_zara), "records", "read", str(workspace)]))
    before = json.loads(run([str(zara), "records", "read", str(workspace)]))
    assert before == original
    upgraded = json.loads(run([str(zara), "migrate", str(workspace), "--to", "3"]))
    assert upgraded["schema_version"] == 3
    assert json.loads(run([str(zara), "records", "read", str(workspace)])) == before
    database = workspace / ".zara/state.sqlite3"
    migrated_hash = digest(database)
    run([str(old_zara), "records", "read", str(workspace)], expected=1)
    assert json.loads(run([str(zara), "migrate", str(workspace), "--to", "3"])) == upgraded
    assert digest(database) == migrated_hash
    work = next(record for record in before["records"] if record["kind"] == "work")

    def request(operation: str, revision: int, **extra: object) -> dict[str, Any]:
        return (
            dict(
                version=1,
                operation_id=str(uuid4()),
                workspace_id=before["workspace_id"],
                work_id=work["id"],
                operation=operation,
                expected_revision=revision,
                requirements=[],
                artifact_references=[],
                provenance="Fictional Work 3 executor trial under the development CALL",
            )
            | extra
        )

    def mutation(value: dict[str, Any], *, expected: int = 0) -> dict[str, Any] | None:
        output = run(
            [str(zara), "mutate", str(workspace), json.dumps(value)],
            expected=expected,
            console=True,
        )
        decoded: dict[str, Any] | None = json.loads(output) if expected == 0 else None
        return decoded

    grant = request("authorize_work", 1)
    run([str(zara), "mutate", str(workspace), json.dumps(grant)], expected=1)
    run([str(zara), "mutate", str(workspace), json.dumps(grant | {"approved": True})], expected=1)
    assert digest(database) == migrated_hash
    granted = mutation(grant)
    assert granted is not None and granted["new_revision"] == 2
    grant_hash = digest(database)
    mutation(grant, expected=1)
    assert digest(database) == grant_hash
    change = request("set_work_requirements", 2, requirements=["reasoning", "coding"])
    changed = mutation(change)
    assert changed is not None and changed["new_revision"] == 3
    query = {name: change[name] for name in ("version", "workspace_id", "work_id", "operation_id")}
    current_hash = digest(database)
    observed = json.loads(
        run([str(zara), "receipt", str(workspace), json.dumps(query)], console=True)
    )
    assert observed == changed
    mutation(request("set_work_requirements", 2, requirements=["stale"]), expected=1)
    assert digest(database) == current_hash
    revoked = mutation(request("revoke_work", 3))
    assert revoked is not None and revoked["new_revision"] == 4
    revoked_hash = digest(database)
    mutation(change, expected=1)
    run([str(zara), "receipt", str(workspace), json.dumps(query)], expected=1, console=True)
    assert digest(database) == revoked_hash
    history = json.loads(run([str(zara), "history", str(workspace)]))
    snapshot = json.loads(run([str(zara), "records", "read", str(workspace)]))
    assert history["state_revision"] == snapshot["state_revision"] == 4
    assert len(history["events"]) == len(history["receipts"]) == 3
    assert [event["request"]["operation"] for event in history["events"]] == [
        "authorize_work",
        "set_work_requirements",
        "revoke_work",
    ]
    assert history["events"][1]["request"] == change
    assert history["events"][1]["confirmation"]["channel"] == "local-console"
    assert history["receipts"][1] == changed
    assert {str(path): digest(path) for path in (old_database, old_wheel)} == original_hashes
    assert list((workspace / "artifacts").iterdir()) == []
    assert list((workspace / "projections").iterdir()) == []
    receipt = dict(
        source_commit=commit,
        version=package_version,
        wheel_sha256=digest(wheel),
        retained_trial=str(base),
        installed_command=str(zara),
        workspace=str(workspace),
        runtime=runtime,
        accepted_inputs_unchanged=original_hashes,
        database_sha256=digest(database),
        snapshot=snapshot,
        history=history,
        acceptance="executor checks only; no owner runtime PASS or binding G5",
    )
    (base / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    log(json.dumps(receipt, indent=2))
    log(
        "PASS: installed console mutation, replay/stale refusal, current authority, "
        "audit/receipt and preserved accepted input"
    )


if __name__ == "__main__":
    main()
