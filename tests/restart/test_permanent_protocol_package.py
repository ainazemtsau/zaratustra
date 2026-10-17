"""Frozen 0.2 runtime to protocol-one package: real Node/uv, no model or auth."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from tools.build_permanent_package import ROOT, build

from .test_portable_bootstrap import install, launch


def run_python(python: Path, script: str, root: Path) -> str:
    result = subprocess.run(
        [str(python), "-c", script, str(root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.fixture(scope="module")
def protocol_package(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    base = tmp_path_factory.mktemp("protocol-package")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("UV_CACHE_DIR", str(base / "cache"))
        source = build(base / "source")
        dist = base / "dist"
        shutil.copytree(source / "wheels", dist)
        old = ROOT / "evidence/package-d/final-f80180a/owner-bundle/wheels"
        for wheel in old.glob("*.whl"):
            if not wheel.name.startswith("zaratustra_"):
                shutil.copyfile(wheel, dist / wheel.name)
        yield build(base / "package", dist)


SEED = """
import base64,json,sys
from pathlib import Path
from zaratustra_core import Core
from zaratustra_app import Coordinator,Driver,Sleep
root=Path(sys.argv[1]);core,token=Core.initialize(root)
(root/'owner.credential').write_text(token,encoding='utf-8')
owner=core.connect(token)
owner.call('apply_changes',{'changes':[
 {'id':'fictional-activity','kind':'activity','key':'fictional','body':'Original agreement'},
 {'id':'fixture-method','kind':'method','key':'fixture-method','body':'Original Method'},
 {'id':'fixture-profile','kind':'profile','key':'fixture-profile','body':{'mode':'fixture'}}]},
 'fixture-records',expected_heads={'fictional-activity':0,'fixture-method':0,'fixture-profile':0})
owner.call('ingest_message',{'conversation':'fixture-conversation','event_id':'fixture-input',
 'raw_base64':base64.b64encode(b'Exact fictional human request').decode()},'fixture-input')
permissions=['read','apply_changes','open_work','prepare_attempt','claim_dispatch',
 'observe_attempt','commit_outcome','control_work','reserve_tool',
 'write:method:fictional-activity']
client=core.connect(core.grant(token,'fixture-host',permissions,origin='host'))
coordinator=Coordinator(client)
coordinator.open_work({'id':'fixture-work','conversation':'fixture-conversation','goal':'Keep wait',
 'method_ref':{'id':'fixture-method','revision':1},'inputs':[{'id':'fictional-activity','revision':1}],
 'call_limit':4,'continuation_policy':'durable'},scope='fictional-activity')
prepared=coordinator.prepare('fixture-work','fixture-attempt',{'id':'fixture-profile','revision':1})
driver=Driver(lambda *_:json.dumps({'state':'waiting','text':'Exact retained question',
 'wait':{'id':'fixture-wait','question':'Exact retained question'},
 'outputs':[{'id':'fictional-activity','revision':1}]}).encode())
coordinator.dispatch('fixture-attempt',prepared['generation'],driver)
assert coordinator.recover('fixture-attempt')['state']=='waiting'
owner.call('apply_changes',{'changes':[{'id':'fictional-activity','kind':'activity','key':'fictional',
 'body':'Later agreement','source_refs':[{'id':'fictional-activity','revision':1}]}]},
 'fixture-revision',expected_heads={'fictional-activity':1})
Sleep(client).start(work_id='fixture-sleep',scope='fictional-activity',portion=2)
"""


def protected(root: Path) -> dict[str, list[tuple[object, ...]]]:
    with sqlite3.connect(root / "core.sqlite3") as db:
        names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return {
            name: list(db.execute('SELECT * FROM "' + name + '"'))
            for name in names
            if name not in {"events", "receipts", "sqlite_sequence"}
        }


def test_manifest_declares_durable_protocol(protocol_package: Path) -> None:
    release = json.loads((protocol_package / "release.json").read_text(encoding="utf-8"))
    assert release["versions"] == {"zaratustra-core": "0.3.0", "zaratustra-next": "0.3.0"}
    assert release["core_required_protocol"] == 1
    assert release["supported_read_protocols"] == [0, 1]


def test_unsupported_manifest_stops_before_runtime_or_data(
    protocol_package: Path, tmp_path: Path
) -> None:
    package = tmp_path / "unsupported-package"
    shutil.copytree(protocol_package, package)
    release_file = package / "release.json"
    release = json.loads(release_file.read_text(encoding="utf-8"))
    release["core_required_protocol"] = 999
    release_file.write_text(json.dumps(release), encoding="utf-8")
    root = tmp_path / "home"
    process = launch(package, root)
    stdout, stderr = process.communicate(timeout=30)
    assert process.returncode != 0, stdout
    assert "Unsupported Core protocol manifest" in stderr
    assert not root.exists()


def test_actual_020_update_recovers_after_marker_before_publication(
    protocol_package: Path, tmp_path: Path
) -> None:
    # Keep the frozen delivery untouched; add only its hash-pinned dependencies
    # to a disposable copy for deterministic offline installation.
    old_package = tmp_path / "old-package"
    shutil.copytree(ROOT / "delivery/zaratustra-pi-0.2.0-32b096a", old_package)
    for wheel in (protocol_package / "wheels").glob("*.whl"):
        if not wheel.name.startswith("zaratustra_"):
            shutil.copyfile(wheel, old_package / "wheels" / wheel.name)
    (old_package / "wheels/SHA256SUMS").write_text(
        "".join(
            hashlib.sha256(wheel.read_bytes()).hexdigest() + "  " + wheel.name + "\n"
            for wheel in sorted((old_package / "wheels").glob("*.whl"))
        ),
        encoding="utf-8",
    )
    root = tmp_path / "home"
    previous = install(old_package, root)
    data = root / "data"
    run_python(previous, SEED, data)
    rows = protected(data)
    credential = (data / "owner.credential").read_bytes()
    selected = (root / ".current").read_bytes()
    interrupted = tmp_path / "interrupted-package"
    shutil.copytree(protocol_package, interrupted)
    script = interrupted / "bootstrap.mjs"
    source = script.read_text(encoding="utf-8")
    assert source.count("os.replace(temporary,current)") == 1
    script.write_text(
        source.replace("os.replace(temporary,current)", "os._exit(73)"), encoding="utf-8"
    )
    process = launch(interrupted, root)
    stdout, stderr = process.communicate(timeout=180)
    assert process.returncode != 0, (stdout, stderr)
    assert (root / ".current").read_bytes() == selected
    with sqlite3.connect(data / "core.sqlite3") as db:
        count = db.execute("SELECT COUNT(*) FROM events WHERE kind='protocol_upgrade'").fetchone()
        assert count == (1,)
        assert db.execute("PRAGMA user_version").fetchone() == (1,)
    assert protected(data) == rows
    assert (data / "owner.credential").read_bytes() == credential
    # A real frozen old wheel must refuse before a command creates any receipt/event.
    before_refusal = (data / "core.sqlite3").read_bytes()
    refused = subprocess.run(
        [
            str(previous),
            "-c",
            "from pathlib import Path; from zaratustra_core import Core; import sys; "
            "core=Core(Path(sys.argv[1])); token=(core.root/'owner.credential').read_text(); "
            "core.connect(token).call('read_snapshot',{},'old-wheel-must-refuse')",
            str(data),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert refused.returncode != 0
    assert "unsupported_capability" in refused.stderr
    assert (data / "core.sqlite3").read_bytes() == before_refusal
    updated = install(protocol_package, root)
    assert updated != previous
    assert protected(data) == rows
    assert (data / "owner.credential").read_bytes() == credential
    assert install(protocol_package, root) == updated
    with sqlite3.connect(data / "core.sqlite3") as db:
        count = db.execute("SELECT COUNT(*) FROM events WHERE kind='protocol_upgrade'").fetchone()
        assert count == (1,)
        assert db.execute("SELECT status FROM waits WHERE id='fixture-wait'").fetchone() == (
            "waiting",
        )
        progress = db.execute(
            "SELECT body FROM records WHERE id='fixture-sleep:progress'"
        ).fetchone()
        assert progress is not None and "sleep-progress/v1" in progress[0]
    snapshots = list((root / "backups").iterdir())
    assert snapshots
    generations = []
    for path in snapshots:
        with sqlite3.connect(path / "core.sqlite3") as snapshot:
            generations.append(snapshot.execute("PRAGMA user_version").fetchone())
    assert (0,) in generations
    # Switching the data selection to a different legacy space must not take
    # the already-current runtime shortcut without upgrading that space.
    legacy = root / "another-legacy-space"
    run_python(previous, SEED, legacy)
    legacy_rows = protected(legacy)
    (root / "data-selection.json").write_text(
        json.dumps({"data_root": str(legacy)}), encoding="utf-8"
    )
    assert install(protocol_package, root).exists()
    with sqlite3.connect(legacy / "core.sqlite3") as db:
        assert db.execute("PRAGMA user_version").fetchone() == (1,)
    assert protected(legacy) == legacy_rows
