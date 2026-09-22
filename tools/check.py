"""One repo-native check; scanners below check hygiene and file presence only."""

from __future__ import annotations

import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], root: Path = ROOT) -> None:
    print("$ " + " ".join(command), flush=True)
    environment = os.environ.copy()
    if environment.get("ZARATUSTRA_SQLITE_DLL"):
        bootstrap = str((root / "tools" / "sqlite_bootstrap").resolve())
        inherited = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            bootstrap if not inherited else bootstrap + os.pathsep + inherited
        )
    subprocess.run(command, cwd=root, check=True, env=environment)


def git_paths(root: Path, *, tracked_only: bool = False) -> list[str]:
    flags = ["--cached"] if tracked_only else ["--cached", "--others", "--exclude-standard"]
    output = subprocess.check_output(["git", "ls-files", "-z", *flags], cwd=root)
    return sorted(set(output.decode().split(chr(0))) - {""})


def hygiene(root: Path) -> list[str]:
    errors: list[str] = []
    for name in git_paths(root, tracked_only=True):
        if name.startswith("_scratch/") and name != "_scratch/.gitignore":
            errors.append(f"scratch file is tracked: {name}")
    for name in git_paths(root):
        path = root / name
        if path.suffix != ".py" or not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=name)
        is_test = path.name.startswith("test_") or path.name.endswith("_test.py")
        if is_test and not name.startswith("tests/"):
            errors.append(f"test outside tests/: {name}")
        if is_test and name.startswith("tests/"):
            module = Path(name).parts[1]
            source = root / ("tools" if module == "tools" else f"src/{module}")
            if not source.is_dir():
                errors.append(f"test module has no source: {name}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if chr(92) in node.value or re.match("^[A-Za-z]:/", node.value):
                    errors.append(f"non-portable path/string: {name}:{node.lineno}")
            if not is_test:
                continue
            if isinstance(node, ast.ImportFrom) and node.module == "pytest":
                if any(item.name in {"skip", "skipif", "xfail"} for item in node.names):
                    errors.append(f"disabled test import: {name}:{node.lineno}")
            if isinstance(node, ast.Attribute) and node.attr in {"skip", "skipif", "xfail"}:
                errors.append(f"disabled test: {name}:{node.lineno}")
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                if node.name.startswith("test_") and not any(
                    isinstance(child, ast.Assert)
                    or (
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Attribute)
                        and child.func.attr == "raises"
                    )
                    for child in ast.walk(node)
                ):
                    errors.append(f"assertion-free test: {name}:{node.lineno}")
    return errors


def report_errors(root: Path, *, required: bool) -> list[str]:
    config = tomllib.loads((root / "validation.config").read_text(encoding="utf-8"))
    report_config = config["result_report"]
    report = root / report_config["path"]
    errors = []
    if required:
        if not report.is_file():
            errors.append("missing RESULT report")
        else:
            body = report.read_text(encoding="utf-8")
            sections = re.split("^## ", body, flags=re.MULTILINE)[1:]
            present = {
                part.splitlines()[0].strip(): part.partition(chr(10))[2].strip()
                for part in sections
            }
            for field in report_config["fields"]:
                if not present.get(field):
                    errors.append(f"missing report field: {field}")
    reports = ([report] if report.is_file() else []) + list((root / "docs/results").glob("*.md"))
    for path in reports:
        body = path.read_text(encoding="utf-8")
        for name in re.findall("docs/(?:reviews/review-|adr/)[A-Za-z0-9_./-]+[.]md", body):
            target = (root / name).resolve()
            if not target.is_relative_to(root.resolve()) or not target.is_file():
                errors.append(f"missing cited artifact: {name}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="+", help="Narrow formatting/lint/type/test selection.")
    parser.add_argument("--deliver", action="store_true", help="Also require a complete RESULT.md.")
    args = parser.parse_args()
    if (ROOT / "STOP").exists():
        print("STOP file present; owner continuation required.")
        return 1
    if (ROOT / "STEER.md").exists():
        print("STEER.md is present; read the owner's instructions before proceeding.")
        return 1
    config = tomllib.loads((ROOT / "validation.config").read_text(encoding="utf-8"))
    if config["default_mode"] != "PROBA" or config["synced_contract_version"] != 36:
        print(
            "STOP: this setup enables PROBA v36 only; install an authorized mode before proceeding."
        )
        return 1
    errors = hygiene(ROOT) + report_errors(ROOT, required=args.deliver)
    if errors:
        print(chr(10).join(errors))
        return 1
    files = args.files or ["src", "tools", "tests"]
    for name in files:
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or not path.exists():
            parser.error(f"file scope must exist inside this repo: {name}")
    run([sys.executable, "-m", "ruff", "format", "--check", *files])
    run([sys.executable, "-m", "ruff", "check", *files])
    run([sys.executable, "-m", "mypy", *files])
    boundary = shutil.which("lint-imports")
    if boundary is None:
        print("STOP: required tool lint-imports unavailable.")
        return 1
    run([boundary, "--no-cache"])
    test_files = [name for name in files if Path(name).parts[0] == "tests"]
    run([sys.executable, "-m", "pytest", *(test_files or ["tests"]), "-q"])
    uv = shutil.which("uv")
    if uv is None:
        print("STOP: required tool uv unavailable.")
        return 1
    run([uv, "build", "--no-sources"])
    print(
        "PASS: native build, hygiene, types, boundaries, tests"
        + (", report structure" if args.deliver else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
