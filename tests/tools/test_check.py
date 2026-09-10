"""Seeded misses for invisible development-gate behavior, never product acceptance."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from tools.check import ROOT, hygiene, report_errors


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "src/zaratustra").mkdir(parents=True)
    (tmp_path / "validation.config").write_text(
        '[result_report]\npath = "RESULT.md"\nfields = ["outcome", "evidence"]\n',
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.parametrize(
    ("name", "source", "message"),
    [
        ("test_bad.py", "def test_ok():\n    assert True\n", "test outside"),
        ("tests/zaratustra/test_bad.py", "def test_empty():\n    pass\n", "assertion-free"),
        (
            "tests/zaratustra/test_bad.py",
            "import pytest\n@pytest.mark.skip\ndef test_hidden():\n    assert True\n",
            "disabled test",
        ),
        (
            "tests/zaratustra/test_bad.py",
            "import pytest\n@pytest.mark.xfail\ndef test_hidden():\n    assert True\n",
            "disabled test",
        ),
        (
            "tests/zaratustra/test_bad.py",
            "from pytest import skip as hide\ndef test_hidden():\n    hide()\n    assert True\n",
            "disabled test import",
        ),
        ("tests/missing/test_bad.py", "def test_ok():\n    assert True\n", "no source"),
        ("src/zaratustra/bad.py", 'value = "C:/private/data"\n', "non-portable"),
    ],
)
def test_hygiene_rejects_seed(sandbox: Path, name: str, source: str, message: str) -> None:
    path = sandbox / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    assert any(message in error for error in hygiene(sandbox))


def test_clean_hygiene(sandbox: Path) -> None:
    path = sandbox / "tests/zaratustra/test_clean.py"
    path.parent.mkdir(parents=True)
    path.write_text("def test_visible():\n    assert True\n", encoding="utf-8")
    assert hygiene(sandbox) == []


def test_report_presence_and_config_fields(sandbox: Path) -> None:
    assert report_errors(sandbox, required=True) == ["missing RESULT report"]
    report = sandbox / "RESULT.md"
    report.write_text("## outcome\nPrepared\n", encoding="utf-8")
    assert report_errors(sandbox, required=True) == ["missing report field: evidence"]
    report.write_text("## outcome\nPrepared\n## evidence\nCommands\n", encoding="utf-8")
    assert report_errors(sandbox, required=True) == []


def test_citation_absent_present_and_omitted(sandbox: Path) -> None:
    report = sandbox / "RESULT.md"
    report.write_text("See docs/reviews/review-seed.md", encoding="utf-8")
    assert report_errors(sandbox, required=False) == [
        "missing cited artifact: docs/reviews/review-seed.md"
    ]
    target = sandbox / "docs/reviews/review-seed.md"
    target.parent.mkdir(parents=True)
    target.write_text("Seeded fixture, no real review claim.", encoding="utf-8")
    assert report_errors(sandbox, required=False) == []
    report.write_text("No citation.", encoding="utf-8")
    assert report_errors(sandbox, required=False) == []


def test_scratch_ignore_and_forced_stage_rejected(sandbox: Path) -> None:
    scratch = sandbox / "_scratch"
    scratch.mkdir()
    shutil.copy(ROOT / "_scratch/.gitignore", scratch / ".gitignore")
    (scratch / "seed.txt").write_text("seed", encoding="utf-8")
    result = subprocess.run(
        ["git", "check-ignore", "_scratch/seed.txt"], cwd=sandbox, capture_output=True
    )
    assert result.returncode == 0
    subprocess.run(["git", "add", "-f", "_scratch/seed.txt"], cwd=sandbox, check=True)
    assert "scratch file is tracked: _scratch/seed.txt" in hygiene(sandbox)


@pytest.mark.parametrize(
    "forbidden", ["zaratustra.cli", "tests.fixtures.fictional_lot", "tools.probe_first_process"]
)
def test_real_boundary_clean_and_reverse_import_rejected(tmp_path: Path, forbidden: str) -> None:
    """Run the installed linter on an isolated copy; do not alter the product tree."""
    for name in ("src", "tools", "tests"):
        shutil.copytree(ROOT / name, tmp_path / name, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    command = shutil.which("lint-imports")
    assert command is not None, "required tool lint-imports unavailable"
    environment = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join((str(tmp_path / "src"), str(tmp_path))),
        PYTHONIOENCODING="utf-8",
    )
    clean = subprocess.run(
        [command, "--no-cache"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert clean.returncode == 0, clean.stdout + clean.stderr
    (tmp_path / "src/zaratustra/core/boundary_seed.py").write_text(
        f"import {forbidden}\n", encoding="utf-8"
    )
    broken = subprocess.run(
        [command, "--no-cache"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken.returncode != 0
    assert "BROKEN" in broken.stdout, broken.stdout + broken.stderr
    print(clean.stdout, broken.stdout)


def test_built_distributions_exclude_residual_fictional_directories(tmp_path: Path) -> None:
    """Old checkout caches must not leave importable namespace directories in a wheel."""
    shutil.copytree(ROOT / "src", tmp_path / "src", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("pyproject.toml", "uv.lock", ".python-version", "README.md"):
        shutil.copyfile(ROOT / name, tmp_path / name)
    for name in ("fictional_lot", "process_probe"):
        cache = tmp_path / "src/zaratustra" / name / "__pycache__"
        cache.mkdir(parents=True)
        (cache / "stale.cpython-313.pyc").write_bytes(b"retained cache marker")
    uv = shutil.which("uv")
    assert uv is not None, "required tool uv unavailable"
    subprocess.run([uv, "build", "--no-sources"], cwd=tmp_path, check=True)
    with zipfile.ZipFile(next((tmp_path / "dist").glob("*.whl"))) as wheel:
        assert not any(
            name.startswith(("zaratustra/fictional_lot/", "zaratustra/process_probe/"))
            for name in wheel.namelist()
        )
    with tarfile.open(next((tmp_path / "dist").glob("*.tar.gz"))) as source:
        assert not any(
            "/src/zaratustra/fictional_lot" in name or "/src/zaratustra/process_probe" in name
            for name in source.getnames()
        )


def test_python_hook_rejects_forced_scratch_commit(sandbox: Path) -> None:
    hook_dir = sandbox / ".githooks"
    hook_dir.mkdir()
    shutil.copy(ROOT / ".githooks/pre-commit", hook_dir / "pre-commit")
    shutil.copytree(ROOT / "tools", sandbox / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    scratch = sandbox / "_scratch"
    scratch.mkdir()
    (scratch / "seed.txt").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "config", "core.hooksPath", ".githooks"], cwd=sandbox, check=True)
    subprocess.run(["git", "add", "_scratch/seed.txt"], cwd=sandbox, check=True)
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Setup fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "Must be rejected",
        ],
        cwd=sandbox,
        capture_output=True,
        text=True,
        env=dict(
            os.environ, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]
        ),
    )
    assert result.returncode != 0
    assert "scratch file is tracked" in result.stdout + result.stderr
