"""Retain a wheel-only installation and run both explicitly external dev fixtures."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASIS = "2df9b286b3b54ac3fabd07db0e7d9b343bc17850"


def save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2) + chr(10), encoding="utf-8")


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def command(args: list[str], cwd: Path = ROOT) -> None:
    print("$ " + " ".join(args), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def isolated_child(base: Path) -> None:
    # This function runs under the new wheel-only Python with -I and an empty cwd.
    import zaratustra
    from zaratustra.core import init_workspace, migrate_workspace, read_records

    installed_root = Path(zaratustra.__file__).resolve().parent
    assert installed_root.is_relative_to(base / "venv"), installed_root
    assert not any(Path(item).resolve() in {ROOT, ROOT / "src"} for item in sys.path if item)
    assert list(Path.cwd().iterdir()) == []
    for name in (
        "zaratustra.fictional_lot",
        "zaratustra.fictional_signal",
        "zaratustra.process_probe",
        "tests",
        "tools",
    ):
        assert importlib.util.find_spec(name) is None, name
    blank = base / "blank-workspace"
    blank.mkdir()
    init_workspace(blank)
    migrate_workspace(blank, target_version=7)
    snapshot = read_records(blank)
    assert snapshot.records == () and snapshot.state_revision == 0
    save(
        base / "installed.json",
        dict(
            version=importlib.metadata.version("zaratustra"),
            installed_root=str(installed_root),
            fixture_modules_absent=True,
            dev_packages_absent=True,
            initial_records=0,
            initial_revision=snapshot.state_revision,
        ),
    )
    # Only now expose external dev helpers. ROOT/src is never added to sys.path.
    sys.path.append(str(ROOT))
    import tests.fixtures.fictional_lot as lot
    import tests.fixtures.fictional_signal as signal
    from tools.probe_second_process import run

    for fixture in (lot, signal):
        assert Path(fixture.__file__).resolve().is_relative_to(ROOT / "tests/fixtures")
    summary = run(
        base / "scenario",
        ROOT / "docs/m1-second-process/inputs.json",
        ROOT / "docs/m1-first-process/inputs.json",
    )
    assert summary["lot"]["outcome"] == "release" and summary["lot"]["final_revision"] == 19
    assert summary["lot"]["expected_refusals"] == dict(
        incomplete="lot_blocked", missing_pack="missing_pack", wrong_basis="lot_blocked"
    )
    recurring = summary["signal"]
    assert recurring["expected_refusals"] == dict(
        invalid="invalid_signal_input", missing_pack="missing_pack", wrong_basis="signal_blocked"
    )
    assert len(recurring["results"]) == 4
    final = recurring["final_answers"]
    assert final["available_works"]["count"] == 1
    assert final["recent_important_results"]["count"] == 4
    assert final["available_works"]["value"][0]["executor_requirements"] == [
        "fictional.signal/v1:observe"
    ]
    modules = {
        name: str(module.__file__)
        for name, module in sys.modules.items()
        if (name == "zaratustra" or name.startswith("zaratustra."))
        and getattr(module, "__file__", None)
    }
    assert all(Path(path).resolve().is_relative_to(installed_root) for path in modules.values())
    save(base / "product-module-paths.json", modules)
    print("PASS: wheel-only Core; empty initial data; both external Processes; scoped separation")


def verify(base: Path) -> None:
    base.mkdir(parents=True)
    uv = shutil.which("uv")
    assert uv is not None, "STOP: required tool uv unavailable"
    head = git("rev-parse", "HEAD").decode().strip()
    assert not git("diff", "HEAD", "--", "src", "tests", "tools", "pyproject.toml", "uv.lock")
    assert not git(
        "diff",
        BASIS,
        head,
        "--",
        "src/zaratustra",
        "tests/fixtures/fictional_lot",
        "uv.lock",
    )
    wheel = ROOT / "dist/zaratustra-0.10.1-py3-none-any.whl"
    assert wheel.is_file(), "Run native Deliver first"
    retained = base / wheel.name
    shutil.copyfile(wheel, retained)
    with zipfile.ZipFile(retained) as archive:
        names = archive.namelist()
        assert not any(
            any(part in name for part in ("fictional_lot", "fictional_signal", "process_probe"))
            for name in names
        )
        assert {name.split("/")[0] for name in names} == {
            "zaratustra",
            "zaratustra-0.10.1.dist-info",
        }
        package = {
            name: archive.read(name)
            for name in names
            if name.startswith("zaratustra/") and not name.endswith("/")
        }
        source = git("ls-tree", "-r", "--name-only", head, "src/zaratustra").decode().splitlines()
        assert set(package) == {name.removeprefix("src/") for name in source}
        for name, raw in package.items():
            assert raw == git("show", f"{head}:src/{name}")
    sdist = ROOT / "dist/zaratustra-0.10.1.tar.gz"
    shutil.copyfile(sdist, base / sdist.name)
    with tarfile.open(sdist) as archive:
        source_names = archive.getnames()
        assert not any(
            part in name
            for name in source_names
            for part in (
                "/tests/",
                "/tools/",
                "/fictional_lot",
                "/fictional_signal",
                "/process_probe",
            )
        )
    environment = base / "venv"
    working = base / "empty-cwd"
    working.mkdir()
    requirements = base / "runtime-requirements.txt"
    command(
        [
            uv,
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--no-hashes",
            "--output-file",
            str(requirements),
        ]
    )
    command(
        [uv, "venv", "--python", "3.13.7", "--python-preference", "only-managed", str(environment)]
    )
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    command([uv, "pip", "install", "--python", str(python), "-r", str(requirements), str(retained)])
    command([uv, "pip", "check", "--python", str(python)])
    command(
        [str(python), "-I", str(Path(__file__).resolve()), "--output", str(base), "--child"],
        working,
    )
    save(
        base / "verification.json",
        dict(
            source_commit=head,
            baseline=BASIS,
            wheel_sha256=hashlib.sha256(retained.read_bytes()).hexdigest(),
            wheel_files=names,
            sdist_files=source_names,
            installed_files_equal_committed_source=True,
            product_and_first_rules_unchanged=True,
            installed=json.loads((base / "installed.json").read_bytes()),
            external_processes="PASS: finite release and recurring observe/compare",
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    for name in ("STOP", "STEER.md"):
        if (ROOT / name).exists():
            parser.error(f"Read and resolve {name} before running")
    base = args.output.resolve()
    scratch = (ROOT / "_scratch").resolve()
    if base == scratch or not base.is_relative_to(scratch):
        parser.error("Choose a directory inside this execution worktree's ignored _scratch")
    if args.child:
        isolated_child(base)
    else:
        if base.exists():
            parser.error("Choose a NEW directory; retained installations are never deleted")
        verify(base)


if __name__ == "__main__":
    main()
