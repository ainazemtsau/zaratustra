"""Native package isolation and boundary observations in a fresh interpreter."""

import subprocess
import sys
from pathlib import Path


def test_import_without_legacy_or_pi(tmp_path: Path) -> None:
    script = """
import importlib.abc, sys
class Deny(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'zaratustra','zaratustra_app','dbos','sqlalchemy','pi'}:
            raise AssertionError('Forbidden runtime dependency: ' + fullname)
sys.meta_path.insert(0,Deny())
import zaratustra_core
assert not list(__import__('pathlib').Path.cwd().iterdir())
core, token = zaratustra_core.Core.initialize(__import__('pathlib').Path('new-space'))
client=core.connect(token)
assert client.call('describe_contract',{},'describe')['version']=='wire/v1'
"""
    import zaratustra_core

    source = Path(zaratustra_core.__file__).parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-c",
            "import sys;sys.path.insert(0,sys.argv[1]);" + script,
            str(source),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
