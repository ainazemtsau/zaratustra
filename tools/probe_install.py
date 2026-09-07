"""Install the pinned wheel and exercise its CLI in disposable folders outside checkout."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("STOP: required tool uv unavailable")
    for name in ("STOP", "STEER.md"):
        if (ROOT / name).exists():
            raise SystemExit(f"STOP: read {name} before running the installation probe")
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_version = metadata["project"]["version"]
    wheel = ROOT / f"dist/zaratustra-{package_version}-py3-none-any.whl"
    print(
        "source_commit="
        + subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8"
        ).strip(),
        flush=True,
    )
    print("wheel_sha256=" + hashlib.sha256(wheel.read_bytes()).hexdigest(), flush=True)
    with tempfile.TemporaryDirectory(prefix="zaratustra-install-") as directory:
        base = Path(directory).resolve()
        if not base.is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise RuntimeError("Temporary cleanup target escaped the system temporary root")
        if base.is_relative_to(ROOT):
            raise RuntimeError("Installation probe must be outside the product repository")
        environment = base / "venv"
        working = base / "empty-cwd"
        working.mkdir()
        requirements = base / "runtime-requirements.txt"
        commands = [
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
            [
                uv,
                "venv",
                "--python",
                "3.13.7",
                "--python-preference",
                "only-managed",
                str(environment),
            ],
        ]
        for command in commands:
            print("$ " + " ".join(command), flush=True)
            subprocess.run(command, cwd=ROOT, check=True)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        for command in [
            [uv, "pip", "install", "--python", str(python), "-r", str(requirements), str(wheel)],
            [uv, "pip", "check", "--python", str(python)],
        ]:
            print("$ " + " ".join(command), flush=True)
            subprocess.run(command, cwd=working, check=True)
        code = """
import hashlib, importlib.metadata, json, sqlite3, sys
from pathlib import Path
import pydantic, zaratustra, zaratustra.core, zaratustra.cli
package = Path(zaratustra.__file__).resolve()
environment = Path(sys.argv[1]).resolve()
checkout = Path(sys.argv[2]).resolve()
assert package.is_relative_to(environment), package
assert not package.is_relative_to(checkout)
assert not any(Path(item).resolve().is_relative_to(checkout) for item in sys.path if item)
assert list(Path.cwd().iterdir()) == []
print(json.dumps({
    "python": sys.version,
    "base_executable": sys._base_executable,
    "package": str(package),
    "version": importlib.metadata.version("zaratustra"),
    "pydantic": pydantic.__version__,
    "sqlite": sqlite3.sqlite_version,
    "sha256_available": "sha256" in hashlib.algorithms_available,
    "outside_checkout": True,
    "empty_cwd_unchanged": True
}, indent=2))
"""
        print("$ isolated wheel import; no PYTHONPATH or editable project", flush=True)
        subprocess.run(
            [str(python), "-I", "-c", code, str(environment), str(ROOT)],
            cwd=working,
            check=True,
        )
        zara = environment / ("Scripts/zara.exe" if os.name == "nt" else "bin/zara")
        child_env = dict(os.environ)
        child_env.pop("PYTHONPATH", None)
        child_env["PYTHONIOENCODING"] = "utf-8"

        def invoke(*arguments: str) -> str:
            command = [str(zara), *arguments]
            print("$ " + " ".join(command), flush=True)
            result = subprocess.run(
                command,
                cwd=working,
                env=child_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            print(result.stdout, end="", flush=True)
            if result.stderr:
                print(result.stderr, end="", flush=True)
            return result.stdout

        assert invoke("--version").strip() == f"zara {package_version}"
        first = json.loads(invoke("init"))
        database = Path(first["database"])
        assert database == working / ".zara/state.sqlite3"
        before = database.read_bytes()
        # These are different OS processes using the installed executable.
        assert json.loads(invoke("status")) == first
        assert json.loads(invoke("init")) == first
        assert json.loads(invoke("status", str(working))) == first
        assert database.read_bytes() == before
        assert first["schema_version"] == 1
        assert {path.name for path in working.iterdir()} == {
            ".zara",
            "processes",
            "artifacts",
            "projections",
            "inbox",
        }
        print("database_sha256_before_after=" + hashlib.sha256(before).hexdigest(), flush=True)
        print(
            "PASS: installed CLI; migration v1; same persisted metadata and DB bytes across runs",
            flush=True,
        )


if __name__ == "__main__":
    main()
