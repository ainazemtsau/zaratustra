"""A real old 0.3 wheel creates v1; v2 upgrade preserves it and rejects that writer."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from zaratustra_core import Core

from .support import inspect

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "delivery/zaratustra-pi-0.3.0-945df9e/wheels/zaratustra_core-0.3.0-py3-none-any.whl"


def test_frozen_v1_writer_preserving_setup_upgrade(tmp_path: Path) -> None:
    root = tmp_path / "core"
    create = (
        "import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
        "from zaratustra_core import Core;c,t=Core.initialize(Path(sys.argv[2]));"
        "c.connect(t).call('apply_changes',{'changes':[{'id':'kept','kind':'activity',"
        "'key':'kept','body':'Retained fictional goal'}]},'save',expected_heads={'kept':0});"
        "print(json.dumps({'token':t,'protocol':c.data_protocol}))"
    )
    first = subprocess.run(
        [sys.executable, "-I", "-c", create, str(OLD), str(root)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert first.returncode == 0, first.stderr
    value = json.loads(first.stdout)
    assert value["protocol"] == 1
    core = Core(root)
    retained = {
        table: inspect(core, table)
        for table in ("meta", "credentials", "rights", "records", "heads")
    }
    update = core.prepare_update(value["token"], tmp_path / "before-v2")
    assert update["upgrade"]["from"] == 1 and update["upgrade"]["to"] == 2
    assert core.prepare_update(value["token"], tmp_path / "before-v2") == update
    assert retained == {table: inspect(core, table) for table in retained}
    before = hashlib.sha256(core.path.read_bytes()).hexdigest()
    reject = (
        "import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
        "from zaratustra_core import Core,CoreError"
        + chr(10)
        + "try: Core(Path(sys.argv[2]))"
        + chr(10)
        + "except CoreError as e: print(e.code,e.field);sys.exit(37)"
        + chr(10)
        + "sys.exit(99)"
    )
    old = subprocess.run(
        [sys.executable, "-I", "-c", reject, str(OLD), str(root)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert old.returncode == 37 and "maintenance.schema" in old.stdout
    assert hashlib.sha256(core.path.read_bytes()).hexdigest() == before
