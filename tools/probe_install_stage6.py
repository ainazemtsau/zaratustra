"""Install a built wheel outside checkout and run the composite child Pi RPC trial there."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SQLITE_SHA256 = "79FD9EC89DBA3F8BD64529A2CA8E9DDE6AE6EDC486C55A1D3F1CE77975A8375C"
ISOLATED_UTF8 = ("-I", "-X", "utf8")


def _command(*parts: str, cwd: Path) -> None:
    subprocess.run(parts, cwd=cwd, check=True)


def _git(*parts: str) -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *parts],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def _inside(value: object, prefix: Path) -> bool:
    return isinstance(value, str) and Path(value).resolve().is_relative_to(prefix)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pi-runtime", required=True, type=Path)
    parser.add_argument(
        "--python",
        help="Interpreter for the new venv; defaults to uv-managed 3.13.7",
    )
    parser.add_argument("--sqlite-dll", type=Path, help="Pinned SQLite DLL; required on Windows")
    parser.add_argument("--parent-execution", action="store_true")
    args = parser.parse_args()
    for name in ("STOP", "STEER.md"):
        if (ROOT / name).exists():
            raise SystemExit(f"STOP: read {name} before the installed trial")
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("STOP: required tool uv unavailable")
    source_nodes = (args.pi_runtime.resolve() / "node_modules").resolve()
    if not source_nodes.is_dir():
        raise SystemExit("STOP: pinned ordinary Pi runtime unavailable")
    sqlite_source: Path | None = None
    if os.name == "nt":
        if args.sqlite_dll is None:
            raise SystemExit("STOP: the Windows trial needs --sqlite-dll")
        sqlite_source = args.sqlite_dll.resolve()
        if hashlib.sha256(sqlite_source.read_bytes()).hexdigest().upper() != (
            EXPECTED_SQLITE_SHA256
        ):
            raise SystemExit("STOP: unsupported SQLite DLL")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    _command(uv, "build", "--no-sources", cwd=ROOT)
    wheel = ROOT / f"dist/zaratustra-{version}-py3-none-any.whl"
    report: dict[str, object] = {
        "source_commit": _git("rev-parse", "HEAD"),
        "source_tree_dirty": bool(_git("status", "--porcelain")),
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest().upper(),
    }
    with tempfile.TemporaryDirectory(prefix="zaratustra-installed-stage6-") as temporary:
        base = Path(temporary).resolve()
        if base.is_relative_to(ROOT) or not base.is_relative_to(
            Path(tempfile.gettempdir()).resolve()
        ):
            raise RuntimeError("Installed trial must run outside the checkout in system temp")
        venv, working = base / "venv", base / "working"
        working.mkdir()
        requirements = base / "runtime-requirements.txt"
        _command(
            uv,
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--no-hashes",
            "--output-file",
            str(requirements),
            cwd=ROOT,
        )
        interpreter = (
            ["--python", args.python]
            if args.python
            else ["--python", "3.13.7", "--python-preference", "only-managed"]
        )
        _command(uv, "venv", *interpreter, str(venv), cwd=working)
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        _command(
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "-r",
            str(requirements),
            str(wheel),
            cwd=working,
        )
        _command(uv, "pip", "check", "--python", str(python), cwd=working)
        runtime = base / "pi-runtime"
        runtime.mkdir()
        link = runtime / "node_modules"
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(source_nodes)],
                cwd=working,
                stdout=subprocess.DEVNULL,
                check=True,
            )
        else:
            link.symlink_to(source_nodes, target_is_directory=True)
        try:
            if link.resolve() != source_nodes:
                raise RuntimeError("Pi runtime link points outside the pinned package tree")
            script = base / "probe_stage6_rpc.py"
            shutil.copyfile(ROOT / "tools" / "probe_stage6_rpc.py", script)
            environment = dict(os.environ)
            for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
                environment.pop(name, None)
            if sqlite_source is not None:
                copy = base / "sqlite3.dll"
                shutil.copyfile(sqlite_source, copy)
                environment["ZARATUSTRA_SQLITE_DLL"] = str(copy)
            trial = subprocess.run(
                [
                    str(python),
                    # -I ignores PYTHONIOENCODING; UTF-8 mode is the child's explicit encoding.
                    *ISOLATED_UTF8,
                    str(script),
                    "--output",
                    str(working / "trial"),
                    "--pi-runtime",
                    str(runtime),
                    *(["--parent-execution"] if args.parent_execution else []),
                ],
                cwd=working,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=900,
            )
            (output / "installed-trial.log").write_text(
                trial.stdout + trial.stderr, encoding="utf-8", newline="\n"
            )
            if trial.returncode:
                raise RuntimeError(
                    f"Installed Stage 6 trial exited {trial.returncode}; see installed-trial.log"
                )
            trial_report = json.loads(trial.stdout.strip().splitlines()[-1])
            site = venv.resolve()
            modules = {
                "foundation": trial_report["foundation_module"],
                "extension": trial_report["extension_resource"],
            }
            if args.parent_execution:
                if trial_report["schema"] != 8 or trial_report["http_total"] != 3:
                    raise RuntimeError("Installed parent execution did not complete three HTTP")
                modules["dbos"] = trial_report["dbos_module"]
            else:
                modules["dbos"] = trial_report["dbos_module"]
                modules["reopened_foundation"] = trial_report["reopen"]["module"]
            if not all(_inside(value, site) for value in modules.values()):
                raise RuntimeError(f"Installed trial imported code outside the venv: {modules}")
            report.update(
                {
                    "outside_checkout": not Path(trial_report["foundation_module"])
                    .resolve()
                    .is_relative_to(ROOT),
                    "isolated_python": True,
                    "python": trial_report["python"],
                    "sqlite": trial_report["sqlite"],
                    "modules": modules,
                    "pi_runtime_link_target": str(source_nodes),
                    "trial": trial_report,
                }
            )
        finally:
            if link.is_symlink():
                link.unlink()
            elif link.exists() and link.is_junction():
                os.rmdir(link)
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({key: report[key] for key in report if key != "trial"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
