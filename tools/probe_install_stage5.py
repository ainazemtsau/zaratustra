"""Install a built wheel outside checkout and run its Core, DBOS and Pi RPC path."""

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
EXPECTED_SQLITE_SHA256 = "79FD9EC89DBA3F8BD64529A2CA8E9DDE6AE6EDC486C55A1D3F1CE77975A8375C"


def _command(*parts: str, cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(parts, cwd=cwd, env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pi-runtime", required=True, type=Path)
    parser.add_argument("--sqlite-dll", required=True, type=Path)
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
    sqlite_source = args.sqlite_dll.resolve()
    if hashlib.sha256(sqlite_source.read_bytes()).hexdigest().upper() != EXPECTED_SQLITE_SHA256:
        raise SystemExit("STOP: unsupported SQLite DLL")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = metadata["project"]["version"]
    _command(uv, "build", "--no-sources", cwd=ROOT)
    wheel = ROOT / f"dist/zaratustra-{version}-py3-none-any.whl"
    wheel_sha256 = hashlib.sha256(wheel.read_bytes()).hexdigest()
    source_commit = subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()
    source_tree_dirty = bool(
        subprocess.check_output(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", "status", "--porcelain"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        ).strip()
    )
    with tempfile.TemporaryDirectory(prefix="zaratustra-installed-stage5-") as temporary:
        base = Path(temporary).resolve()
        temp_root = Path(tempfile.gettempdir()).resolve()
        if not base.is_relative_to(temp_root) or base.is_relative_to(ROOT):
            raise RuntimeError("Installed trial cleanup target escaped the system temp root")
        venv = base / "venv"
        working = base / "working"
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
        _command(
            uv,
            "venv",
            "--python",
            "3.13.7",
            "--python-preference",
            "only-managed",
            str(venv),
            cwd=working,
        )
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
        sqlite_copy = base / "sqlite3.dll"
        shutil.copyfile(sqlite_source, sqlite_copy)
        if hashlib.sha256(sqlite_copy.read_bytes()).hexdigest().upper() != EXPECTED_SQLITE_SHA256:
            raise RuntimeError("Temporary SQLite copy changed")
        runtime = base / "pi-runtime"
        runtime.mkdir()
        link = runtime / "node_modules"
        try:
            if os.name == "nt":
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(source_nodes)],
                    cwd=working,
                    stdout=subprocess.DEVNULL,
                    check=True,
                )
            else:
                link.symlink_to(source_nodes, target_is_directory=True)
            if link.resolve() != source_nodes:
                raise RuntimeError("Pi runtime link points outside the pinned package tree")
            script = base / "installed_stage5_case.py"
            shutil.copyfile(ROOT / "tools" / "installed_stage5_case.py", script)
            child_env = dict(os.environ)
            for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
                child_env.pop(name, None)
            child_env["PYTHONIOENCODING"] = "utf-8"
            child_env["ZARATUSTRA_SQLITE_DLL"] = str(sqlite_copy)
            trial = subprocess.run(
                [
                    str(python),
                    "-I",
                    str(script),
                    "--base",
                    str(working),
                    "--venv",
                    str(venv),
                    "--checkout",
                    str(ROOT),
                    "--pi-runtime",
                    str(runtime),
                ],
                cwd=working,
                env=child_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=180,
            )
            (output / "installed-trial.log").write_text(
                trial.stdout + trial.stderr, encoding="utf-8", newline="\n"
            )
            if trial.returncode:
                raise RuntimeError(
                    f"Installed Stage 5 trial exited {trial.returncode}; see installed-trial.log"
                )
            report = json.loads(trial.stdout.strip().splitlines()[-1])
            report.update(
                {
                    "source_commit": source_commit,
                    "source_tree_dirty": source_tree_dirty,
                    "wheel_sha256": wheel_sha256,
                    "outside_checkout": True,
                    "isolated_python": True,
                    "source_imports": False,
                    "sqlite_dll_sha256": EXPECTED_SQLITE_SHA256,
                    "pi_runtime_link_target": str(source_nodes),
                }
            )
            (output / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            print(json.dumps(report, ensure_ascii=False))
        finally:
            if link.exists():
                if link.resolve() != source_nodes:
                    raise RuntimeError("Refusing to unlink an unexpected Pi runtime target")
                if link.is_junction():
                    os.rmdir(link)
                elif link.is_symlink():
                    link.unlink()
                else:
                    raise RuntimeError("Refusing to remove a non-link Pi runtime directory")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
