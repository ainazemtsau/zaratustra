"""Retain an installed Work 2 trial and migrate a copy of an accepted Work 1 workspace."""

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
    old_workspace = accepted / "workspace"
    old_database = old_workspace / ".zara/state.sqlite3"
    old_wheel = accepted / "zaratustra-0.1.0-py3-none-any.whl"
    old_hashes = {str(path): digest(path) for path in (old_database, old_wheel)}
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_version = metadata["project"]["version"]
    wheel = ROOT / f"dist/zaratustra-{package_version}-py3-none-any.whl"
    base = Path(tempfile.mkdtemp(prefix="zaratustra-work2-")).resolve()
    if base.is_relative_to(ROOT) or base.is_relative_to(accepted):
        raise RuntimeError("Trial must be separate from product and accepted sample")
    environment = base / "venv"
    working = base / "unrelated-cwd"
    working.mkdir()
    copied = base / "workspace"
    shutil.copytree(old_workspace, copied)
    retained_wheel = base / wheel.name
    shutil.copyfile(wheel, retained_wheel)
    requirements = base / "runtime-requirements.txt"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    zara = environment / ("Scripts/zara.exe" if os.name == "nt" else "bin/zara")
    old_zara = accepted / "venv" / ("Scripts/zara.exe" if os.name == "nt" else "bin/zara")
    child_env = dict(os.environ)
    child_env.pop("PYTHONPATH", None)
    child_env["PYTHONIOENCODING"] = "utf-8"

    def run(command: list[str], *, cwd: Path = working, expected: int = 0) -> str:
        print("$ " + subprocess.list2cmdline(command), flush=True)
        result = subprocess.run(
            command, cwd=cwd, env=child_env, capture_output=True, text=True, encoding="utf-8"
        )
        print(result.stdout, end="", flush=True)
        print(result.stderr, end="", flush=True)
        print(f"exit={result.returncode}", flush=True)
        if result.returncode != expected:
            raise RuntimeError(f"Expected exit {expected}; got {result.returncode}")
        return result.stdout

    commit = run(["git", "rev-parse", "HEAD"], cwd=ROOT).strip()
    print(f"source_commit={commit}", flush=True)
    print(f"wheel_sha256={digest(wheel)}", flush=True)
    print(f"retained_trial={base}", flush=True)
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
    run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "-r",
            str(requirements),
            str(retained_wheel),
        ]
    )
    run([uv, "pip", "check", "--python", str(python)])
    code = """
import importlib.metadata, json, sqlite3, sys
from pathlib import Path
import pydantic, zaratustra
package = Path(zaratustra.__file__).resolve()
assert package.is_relative_to(Path(sys.argv[1]).resolve())
assert not package.is_relative_to(Path(sys.argv[2]).resolve())
assert not any(Path(item).resolve().is_relative_to(Path(sys.argv[2]).resolve())
               for item in sys.path if item)
print(json.dumps(dict(package=str(package), version=importlib.metadata.version('zaratustra'),
                     python=sys.version, sqlite=sqlite3.sqlite_version,
                     pydantic=pydantic.__version__, outside_checkout=True), indent=2))
"""
    run([str(python), "-I", "-c", code, str(environment), str(ROOT)])
    assert run([str(zara), "--version"]).strip() == f"zara {package_version}"
    assert run([str(old_zara), "--version"]).strip() == "zara 0.1.0"
    original = json.loads(run([str(old_zara), "status", str(old_workspace)]))
    before = json.loads(run([str(zara), "status", str(copied)]))
    assert before["workspace_id"] == original["workspace_id"]
    assert digest(copied / ".zara/state.sqlite3") == old_hashes[str(old_database)]
    run([str(zara), "records", "read", str(copied)], expected=1)
    assert digest(copied / ".zara/state.sqlite3") == old_hashes[str(old_database)]
    upgraded = json.loads(run([str(zara), "migrate", str(copied)]))
    assert upgraded["schema_version"] == 2
    assert upgraded["workspace_id"] == before["workspace_id"]
    assert upgraded["created_at"] == before["created_at"]
    empty = json.loads(run([str(zara), "records", "read", str(copied)]))
    assert empty["state_revision"] == 0 and empty["records"] == []
    create_arguments = [
        "records",
        "create",
        str(copied),
        "--process-title",
        "Fictional observatory",
        "--goal",
        "Describe an imaginary moon",
        "--expected-result",
        "A short fictional observation",
        "--acceptance",
        "The observation is saved",
        "--boundary",
        "Fictional data only",
        "--budget",
        "One short local session",
        "--artifact-title",
        "Observation draft",
    ]
    created = json.loads(run([str(zara), *create_arguments]))
    database_hash = digest(copied / ".zara/state.sqlite3")
    # Every call starts a fresh installed OS process in an unrelated working directory.
    reread = json.loads(run([str(zara), "records", "read", str(copied)]))
    assert created == reread
    assert created["state_revision"] == 1
    assert {record["kind"] for record in created["records"]} == {
        "process",
        "work",
        "artifact",
        "event",
    }
    assert {record["revision"] for record in created["records"]} == {1}
    assert (
        next(record for record in created["records"] if record["kind"] == "event")[
            "product_version"
        ]
        == package_version
    )
    run([str(zara), *create_arguments], expected=1)
    assert json.loads(run([str(zara), "init", str(copied)])) == upgraded
    assert json.loads(run([str(zara), "migrate", str(copied)])) == upgraded
    run([str(old_zara), "status", str(copied)], expected=1)
    assert digest(copied / ".zara/state.sqlite3") == database_hash
    assert json.loads(run([str(old_zara), "status", str(old_workspace)])) == original
    assert {str(path): digest(path) for path in (old_database, old_wheel)} == old_hashes
    assert list(working.iterdir()) == []
    assert list((copied / "artifacts").iterdir()) == []
    assert list((copied / "projections").iterdir()) == []
    fresh = base / "fresh-workspace"
    fresh.mkdir()
    initialized = json.loads(run([str(zara), "init", str(fresh)]))
    assert initialized["schema_version"] == 1
    run([str(zara), "migrate", str(fresh)])
    fresh_arguments = [str(fresh) if arg == str(copied) else arg for arg in create_arguments]
    fresh_created = json.loads(run([str(zara), *fresh_arguments]))
    assert json.loads(run([str(zara), "records", "read", str(fresh)])) == fresh_created
    receipt = dict(
        source_commit=commit,
        version=package_version,
        wheel_sha256=digest(retained_wheel),
        retained_trial=str(base),
        installed_command=str(zara),
        workspace=str(copied),
        accepted_inputs_unchanged=old_hashes,
        database_sha256_after_reread=database_hash,
        snapshot=created,
    )
    (base / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2), flush=True)
    print(
        "PASS: installed records persist; explicit migration; accepted sample unchanged", flush=True
    )


if __name__ == "__main__":
    main()
