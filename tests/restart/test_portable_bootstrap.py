"""Exercise the real Node installer and installed Python bridge, without a model."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tools.build_permanent_package import ROOT, build


@pytest.fixture(scope="module")
def portable(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    base = tmp_path_factory.mktemp("portable")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("UV_CACHE_DIR", str(base / "uv-cache"))
        initial = build(base / "initial")
        dist = base / "dist"
        shutil.copytree(initial / "wheels", dist)
        baseline = ROOT / "evidence/package-d/final-f80180a/owner-bundle/wheels"
        if os.name == "nt":
            for wheel in baseline.glob("*.whl"):
                if not wheel.name.startswith("zaratustra_"):
                    shutil.copyfile(wheel, dist / wheel.name)
        yield build(base / "package", dist)


def environment(root: Path) -> dict[str, str]:
    result = dict(os.environ, ZARATUSTRA_HOME=str(root))
    if os.name == "nt":
        result["ZARATUSTRA_OFFLINE"] = "1"
    return result


def launch(package: Path, root: Path) -> subprocess.Popen[str]:
    script = f"import {{bootstrap}} from {json.dumps((package / 'bootstrap.mjs').as_uri())};"
    script += " console.log(await bootstrap());"
    return subprocess.Popen(
        ["node", "--input-type=module", "-e", script],
        env=environment(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def install(package: Path, root: Path) -> Path:
    process = launch(package, root)
    stdout, stderr = process.communicate(timeout=120)
    assert process.returncode == 0, stderr
    return Path(stdout.strip())


def test_long_home_uses_short_immutable_runtime(portable: Path, tmp_path: Path) -> None:
    parent = tmp_path.parent
    suffix = "long-home-" + "x" * max(0, 128 - len(str(parent)) - 11)
    root = parent / suffix
    python = install(portable, root)
    selected = json.loads((root / ".current").read_text(encoding="utf-8"))
    runtime = Path(selected["runtime"])
    assert len(str(root)) >= 127
    assert len(runtime.name) == 32
    assert (runtime / ".ready").read_text(encoding="utf-8") == selected["identity"]
    assert install(portable, root) == python


def new_identity(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    requirements = destination / "requirements.txt"
    requirements.write_bytes(requirements.read_bytes() + bytes([10]))
    release = destination / "release.json"
    body = json.loads(release.read_text(encoding="utf-8"))
    body["requirements_sha256"] = hashlib.sha256(requirements.read_bytes()).hexdigest()
    release.write_text(json.dumps(body), encoding="utf-8")
    return destination


def initialize(python: Path, root: Path) -> None:
    script = (
        "import sys; from pathlib import Path; from zaratustra_core import Core; "
        "root=Path(sys.argv[1]); core,token=Core.initialize(root); "
        "(root/'owner.credential').write_text(token,encoding='utf-8')"
    )
    subprocess.run([str(python), "-c", script, str(root)], check=True)


def test_real_bootstrap_and_racing_attach(portable: Path, tmp_path: Path) -> None:
    root = tmp_path / "home"
    processes = [launch(portable, root), launch(portable, root)]
    results = [process.communicate(timeout=120) for process in processes]
    assert all(process.returncode == 0 for process in processes), results
    assert results[0][0] == results[1][0]
    assert not (root / "data").exists()
    assert install(portable, root).exists()


def test_integrity_and_missing_dependency_preserve_current(portable: Path, tmp_path: Path) -> None:
    root = tmp_path / "home"
    install(portable, root)
    before = (root / ".current").read_bytes()
    corrupt = new_identity(portable, tmp_path / "corrupt")
    next((corrupt / "wheels").glob("zaratustra_core-*.whl")).write_bytes(b"broken")
    process = launch(corrupt, root)
    process.communicate(timeout=120)
    assert process.returncode != 0
    assert (root / ".current").read_bytes() == before
    missing = new_identity(portable, tmp_path / "missing")
    # Valid manifest with absent dependency must fail during actual offline resolution.
    manifest = missing / "wheels/SHA256SUMS"
    lines = manifest.read_text(encoding="utf-8").splitlines()
    manifest.write_text("\n".join(line for line in lines if "pydantic_core-" not in line) + "\n")
    for wheel in (missing / "wheels").glob("pydantic_core-*.whl"):
        wheel.unlink()
    if os.name == "nt":
        process = launch(missing, root)
        process.communicate(timeout=120)
        assert process.returncode != 0
        assert (root / ".current").read_bytes() == before


def test_update_verifies_backup_and_rejects_incompatible_schema(
    portable: Path,
    tmp_path: Path,
) -> None:
    root = tmp_path / "home"
    python = install(portable, root)
    initialize(python, root / "data")
    update = new_identity(portable, tmp_path / "update")
    install(update, root)
    backups = list((root / "backups").iterdir())
    assert len(backups) == 1
    assert (backups[0] / "core.sqlite3").exists()
    before = (root / ".current").read_bytes()
    with sqlite3.connect(root / "data/core.sqlite3") as database:
        database.execute("PRAGMA user_version=999")
    database_before = (root / "data/core.sqlite3").read_bytes()
    incompatible = new_identity(update, tmp_path / "incompatible")
    process = launch(incompatible, root)
    process.communicate(timeout=120)
    assert process.returncode != 0
    assert (root / ".current").read_bytes() == before
    assert (root / "data/core.sqlite3").read_bytes() == database_before


def test_interrupted_candidate_does_not_erase_selected_runtime(
    portable: Path,
    tmp_path: Path,
) -> None:
    root = tmp_path / "home"
    python = install(portable, root)
    before = (root / ".current").read_bytes()
    update = new_identity(portable, tmp_path / "update")
    process = launch(update, root)
    deadline = time.monotonic() + 30
    while len(list((root / "runtimes").iterdir())) < 2:
        assert process.poll() is None
        assert time.monotonic() < deadline
        time.sleep(0.01)
    process.kill()
    process.communicate(timeout=120)
    assert python.exists()
    assert (root / ".current").read_bytes() == before
    assert install(update, root).exists()


def test_requirements_have_all_platform_hashes(portable: Path) -> None:
    release: dict[str, Any] = json.loads((portable / "release.json").read_text())
    assert set(release["versions"]) == {"zaratustra-core", "zaratustra-next"}
    requirements = (portable / "requirements.txt").read_text()
    assert "pydantic-core==" in requirements
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    dependency = next(p for p in lock["package"] if p["name"] == "pydantic-core")
    for wheel in dependency["wheels"]:
        assert "--hash=" + wheel["hash"] in requirements
    urls = " ".join(wheel["url"] for wheel in dependency["wheels"])
    assert all(platform in urls for platform in ("win_amd64", "macosx", "manylinux"))


def test_actual_010_wheels_upgrade_without_reinitializing_data(
    portable: Path,
    tmp_path: Path,
) -> None:
    old = tmp_path / "old-package"
    shutil.copytree(portable, old)
    baseline = ROOT / "evidence/package-d/final-f80180a/owner-bundle/wheels"
    requirements = (old / "requirements.txt").read_text(encoding="utf-8").splitlines()
    for product in ("zaratustra_core", "zaratustra_next"):
        for wheel in (old / "wheels").glob(product + "-*.whl"):
            wheel.unlink()
        wheel = next(baseline.glob(product + "-0.1.0-*.whl"))
        shutil.copyfile(wheel, old / "wheels" / wheel.name)
        name = product.replace("_", "-")
        requirements = [line for line in requirements if not line.startswith(name + "==")]
        requirements.append(
            name + "==0.1.0 --hash=sha256:" + hashlib.sha256(wheel.read_bytes()).hexdigest()
        )
    requirement_file = old / "requirements.txt"
    requirement_file.write_text("\n".join(requirements) + "\n", encoding="utf-8")
    release = json.loads((old / "release.json").read_text(encoding="utf-8"))
    release["versions"] = {name: "0.1.0" for name in release["versions"]}
    release["requirements_sha256"] = hashlib.sha256(requirement_file.read_bytes()).hexdigest()
    (old / "release.json").write_text(json.dumps(release), encoding="utf-8")
    manifest = "".join(
        hashlib.sha256(wheel.read_bytes()).hexdigest() + "  " + wheel.name + "\n"
        for wheel in sorted((old / "wheels").glob("*.whl"))
    )
    (old / "wheels/SHA256SUMS").write_text(manifest, encoding="utf-8")
    root = tmp_path / "home"
    runtime = root / "runtimes/baseline-0.1.0"
    runtime.parent.mkdir(parents=True)
    subprocess.run(["uv", "venv", "--python", "3.13.7", str(runtime)], check=True)
    previous = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    flags = ["--no-index"] if os.name == "nt" else []
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(previous),
            "--require-hashes",
            *flags,
            "--find-links",
            str(old / "wheels"),
            "-r",
            str(requirement_file),
        ],
        check=True,
    )
    (runtime / ".ready").write_text("baseline-0.1.0", encoding="utf-8")
    (root / ".current").write_text(
        json.dumps({"identity": "baseline-0.1.0", "runtime": str(runtime)}),
        encoding="utf-8",
    )
    initialize(previous, root / "data")
    seed = """
import base64,json,sys
from pathlib import Path
from zaratustra_core import Core
from zaratustra_app import Coordinator,Driver
root=Path(sys.argv[1]); core=Core(root)
token=(root/'owner.credential').read_text().strip(); owner=core.connect(token)
owner.call('apply_changes',{'changes':[
 {'id':'kept-activity','kind':'activity','key':'kept','body':'Actual pre-update agreement'},
 {'id':'old-method','kind':'method','key':'old-method','body':'Supported original Method'},
 {'id':'old-profile','kind':'profile','key':'old-profile','body':{'mode':'fictional'}}]},
 'old-records',expected_heads={'kept-activity':0,'old-method':0,'old-profile':0})
owner.call('ingest_message',{'conversation':'old-conversation','event_id':'old-input',
 'raw_base64':base64.b64encode(b'Exact pre-update human request').decode()},'old-input')
permissions=['read','apply_changes','open_work','prepare_attempt','claim_dispatch',
 'observe_attempt','commit_outcome','control_work','reserve_tool']
coordinator=Coordinator(core.connect(core.grant(token,'old-executor',permissions,origin='host')))
coordinator.open_work({'id':'old-work','conversation':'old-conversation','goal':'Keep actual work',
 'method_ref':{'id':'old-method','revision':1},'inputs':[{'id':'kept-activity','revision':1}],
 'call_limit':4,'continuation_policy':'durable'},scope='kept-activity')
prepared=coordinator.prepare('old-work','old-attempt',{'id':'old-profile','revision':1})
driver=Driver(lambda *_: json.dumps({'state':'waiting','text':'Exact pre-update question',
 'wait':{'id':'old-wait','question':'Exact pre-update question'},
 'outputs':[{'id':'kept-activity','revision':1}]}).encode())
coordinator.dispatch('old-attempt',prepared['generation'],driver)
assert coordinator.recover('old-attempt')['state']=='waiting'
owner.call('apply_changes',{'changes':[{'id':'kept-activity','kind':'activity','key':'kept',
 'body':'Later version preserved too','source_refs':[{'id':'kept-activity','revision':1}]}]},
 'old-revision',expected_heads={'kept-activity':1})
"""
    subprocess.run([str(previous), "-c", seed, str(root / "data")], check=True)
    credential = (root / "data/owner.credential").read_bytes()
    with sqlite3.connect(root / "data/core.sqlite3") as old_database:
        old_dump = list(old_database.iterdump())
        tables = [
            row[0]
            for row in old_database.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if row[0] not in {"events", "receipts", "sqlite_sequence"}
        ]
        protected = {
            table: list(old_database.execute('SELECT * FROM "' + table + '"')) for table in tables
        }
    updated = install(portable, root)
    assert updated != previous
    assert (root / "data/owner.credential").read_bytes() == credential
    backup = next((root / "backups").iterdir())
    manifest_body = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    backup_database = backup / "core.sqlite3"
    assert (
        manifest_body["database_sha256"] == hashlib.sha256(backup_database.read_bytes()).hexdigest()
    )
    with sqlite3.connect(root / "data/core.sqlite3") as original:
        assert original.execute("PRAGMA user_version").fetchone() == (2,)
        assert {
            table: list(original.execute('SELECT * FROM "' + table + '"')) for table in tables
        } == protected
        assert original.execute("SELECT status FROM works WHERE id='old-work'").fetchone() == (
            "waiting",
        )
        assert original.execute("SELECT status FROM waits WHERE id='old-wait'").fetchone() == (
            "waiting",
        )
        assert original.execute(
            "SELECT COUNT(*) FROM records WHERE id='kept-activity'"
        ).fetchone() == (2,)
    with sqlite3.connect(backup_database) as restored:
        assert list(restored.iterdump()) == old_dump
        assert restored.execute("PRAGMA user_version").fetchone() == (0,)
