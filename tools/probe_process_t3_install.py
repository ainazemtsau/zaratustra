"""Run both explicit T3 fixtures against only the built installed wheel."""

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
import tomllib
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _command(arguments: list[str], *, cwd: Path = ROOT) -> None:
    print("$ " + " ".join(arguments), flush=True)
    subprocess.run(arguments, cwd=cwd, check=True)


def _child(base: Path) -> None:
    import zaratustra

    installed_root = Path(zaratustra.__file__).resolve().parent
    environment = base / "venv"
    assert installed_root.is_relative_to(environment), installed_root
    assert not any(Path(item).resolve() in {ROOT, ROOT / "src"} for item in sys.path if item)
    assert list(Path.cwd().iterdir()) == []
    for name in ("tests", "tools"):
        assert importlib.util.find_spec(name) is None, name
    sys.path.append(str(ROOT))
    from tools.probe_process_t3 import run, run_correction_refusals

    small = run(base / "small", "small")
    project = run(base / "project", "project")
    correction = run_correction_refusals(base / "correction-refusals")
    assert small["stage"] == project["stage"] == "applied"
    assert small["pack_reference_bytes_preserved"] is True
    assert project["pack_reference_bytes_preserved"] is True
    assert correction["edition_only"]["small"]["refusal_code"] == "no_change"
    assert correction["edition_only"]["project"]["refusal_code"] == "no_change"
    assert correction["no_future"]["refusal_code"] == "no_future_work"
    modules = {
        name: str(module.__file__)
        for name, module in sys.modules.items()
        if (name == "zaratustra" or name.startswith("zaratustra."))
        and getattr(module, "__file__", None)
    }
    assert all(Path(path).resolve().is_relative_to(installed_root) for path in modules.values())
    _save(base / "product-module-paths.json", modules)
    _save(
        base / "installed-scenarios.json",
        dict(
            version=importlib.metadata.version("zaratustra"),
            installed_root=str(installed_root),
            small_summary=str((base / "small/summary.json").resolve()),
            project_summary=str((base / "project/summary.json").resolve()),
            correction_summary=str((base / "correction-refusals/summary.json").resolve()),
            dev_packages_absent_before_explicit_fixture_exposure=True,
            external_fixtures_explicitly_exposed_by_harness=True,
            all_product_modules_loaded_from_wheel=True,
            actual_human_research=False,
            manual_acceptance="pending",
        ),
    )
    print(
        "PASS: wheel-only T3 safe change and R1 refusals; two explicit external fixtures",
        flush=True,
    )


def verify(base: Path) -> None:
    base.mkdir(parents=True)
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("STOP: required tool uv unavailable")
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_version = metadata["project"]["version"]
    wheel = ROOT / f"dist/zaratustra-{package_version}-py3-none-any.whl"
    if not wheel.is_file():
        raise RuntimeError("Run the native build before the installed T3 probe")
    retained = base / wheel.name
    shutil.copyfile(wheel, retained)
    with zipfile.ZipFile(retained) as archive:
        names = archive.namelist()
        assert "zaratustra/process_change/__init__.py" in names
        assert not any(name.startswith(("tests/", "tools/")) for name in names)
    environment = base / "venv"
    working = base / "empty-cwd"
    working.mkdir()
    requirements = base / "runtime-requirements.txt"
    _command(
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
    _command(
        [
            uv,
            "venv",
            "--python",
            "3.13.7",
            "--python-preference",
            "only-managed",
            str(environment),
        ]
    )
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    _command(
        [uv, "pip", "install", "--python", str(python), "-r", str(requirements), str(retained)]
    )
    _command([uv, "pip", "check", "--python", str(python)])
    _command(
        [str(python), "-I", str(Path(__file__).resolve()), "--output", str(base), "--child"],
        cwd=working,
    )
    _save(
        base / "verification.json",
        dict(
            source_commit=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, encoding="utf-8"
            ).strip(),
            wheel_sha256=hashlib.sha256(retained.read_bytes()).hexdigest(),
            wheel_files=names,
            installed=json.loads((base / "installed-scenarios.json").read_bytes()),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    for name in ("STOP", "STEER.md"):
        if (ROOT / name).exists():
            parser.error(f"Read and resolve {name} before running")
    base = args.output.resolve()
    scratch = (ROOT / "_scratch").resolve()
    if base == scratch or not base.is_relative_to(scratch):
        parser.error("Choose a directory inside this worktree's ignored _scratch")
    if args.child:
        _child(base)
    elif base.exists():
        parser.error("Choose a NEW directory; retained installations are never deleted")
    else:
        verify(base)


if __name__ == "__main__":
    main()
