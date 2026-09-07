"""Probe package installation outside the checkout; create no product workspace."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("STOP: required tool uv unavailable")
    wheel = ROOT / "dist/zaratustra-0.0.0-py3-none-any.whl"
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


if __name__ == "__main__":
    main()
