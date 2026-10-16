"""Build both wheels and exercise them in a separate, newly created environment."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]


def test_built_wheels_are_independent(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None
    external = os.environ.get("ZARA_RESTART_INSTALL_ROOT")
    target = (Path(external) if external else tmp_path) / ("install-" + uuid4().hex)
    target.mkdir(parents=True)
    if external:
        assert not target.is_relative_to(ROOT)
    wheels = tmp_path / "wheels"
    env = os.environ.copy()
    env["UV_CACHE_DIR"] = str(ROOT / "_scratch" / "uv-cache")
    for package in ("zaratustra-core", "zaratustra-next"):
        build = subprocess.run(
            [uv, "build", "--package", package, "--wheel", "--out-dir", str(wheels)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        assert build.returncode == 0, build.stderr
    venv = target / "env"
    create = subprocess.run(
        [uv, "venv", str(venv), "--python", sys.executable],
        cwd=target,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert create.returncode == 0, create.stderr
    python = venv / "Scripts" / "python.exe" if os.name == "nt" else venv / "bin" / "python"
    core_wheel = next(wheels.glob("zaratustra_core-*.whl"))
    app_wheel = next(wheels.glob("zaratustra_next-*.whl"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    constraints = target / "constraints.txt"
    constraints.write_text(
        chr(10).join(
            p["name"] + "==" + p["version"] for p in lock["package"] if "registry" in p["source"]
        ),
        encoding="utf-8",
    )
    install = subprocess.run(
        [
            uv,
            "pip",
            "install",
            "--constraint",
            str(constraints),
            "--index-url",
            "https://pypi.org/simple",
            "--python",
            str(python),
            str(core_wheel),
        ],
        cwd=target,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert install.returncode == 0, install.stderr
    guard = """
import importlib.abc, importlib.util, json, sys
from pathlib import Path
class Deny(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'zaratustra','dbos','sqlalchemy','pi'}:
            raise AssertionError('forbidden runtime dependency: '+fullname)
sys.meta_path.insert(0,Deny())
def restrict_environment():
    allowed=[Path.cwd().resolve(),Path(sys.base_prefix).resolve(),Path(sys.prefix).resolve()]
    def audit(event,args):
        if event.startswith('socket.') or event.startswith('subprocess.'):
            raise AssertionError('forbidden process/network access: '+event)
        if event in {'open','os.listdir','os.scandir','os.mkdir','sqlite3.connect'}:
            item=args[0]
            if isinstance(item,(str,bytes)):
                actual=Path(item).resolve()
                if not any(actual.is_relative_to(root) for root in allowed):
                    raise AssertionError('forbidden file/config access: '+str(actual))
    sys.addaudithook(audit)
"""
    smoke = (
        guard
        + """
restrict_environment()
import zaratustra_core
assert importlib.util.find_spec('zaratustra_app') is None
core, token = zaratustra_core.Core.initialize(Path('core-only'))
client = core.connect(token)
assert client.call('describe_contract',{},'describe')['version']=='wire/v1'
payload={'conversation':'c','event_id':'e','raw_base64':'ZXhhY3QgYnl0ZXM='}
assert client.call('ingest_message',payload,'input')['message_sequence']==1
print(json.dumps({'core':zaratustra_core.__file__,'independent':True}))
"""
    )
    child_env = {k: v for k, v in env.items() if not k.startswith("ZARA_RESTART_")}
    child_env = {
        k: v
        for k, v in child_env.items()
        if k.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP"}
    }
    child_env["PATH"] = ""
    core_only = subprocess.run(
        [str(python), "-I", "-X", "utf8", "-c", smoke],
        cwd=target,
        env=child_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert core_only.returncode == 0, core_only.stderr
    install_app = subprocess.run(
        [uv, "pip", "install", "--offline", "--python", str(python), str(app_wheel)],
        cwd=target,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert install_app.returncode == 0, install_app.stderr
    fixture_copy = target / "independent_trace.py"
    shutil.copyfile(ROOT / "tests" / "restart" / "support.py", fixture_copy)
    driver_script = (
        guard
        + """
import importlib.util
restrict_environment()
import zaratustra_core, zaratustra_app
spec=importlib.util.spec_from_file_location('independent_trace',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
result=module.trace(Path('driver-space'), 'driver')
assert result['conversations'][0]['cursor']==22
assert not Path(zaratustra_core.__file__).is_relative_to(Path(sys.argv[2]))
assert not Path(zaratustra_app.__file__).is_relative_to(Path(sys.argv[2]))
assert (Path(zaratustra_app.__file__).parent/'adapters'/'pi'/'extension.ts').is_file()
print(json.dumps({'core':zaratustra_core.__file__,'app':zaratustra_app.__file__,'cursor':22,'effects':len(result['actions'])}))
"""
    )
    driver = subprocess.run(
        [
            str(python),
            "-I",
            "-X",
            "utf8",
            "-c",
            driver_script,
            str(fixture_copy),
            str(ROOT / "packages"),
        ],
        cwd=target,
        env=child_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert driver.returncode == 0, driver.stdout + driver.stderr
    evidence = {
        "core_only": json.loads(core_only.stdout),
        "installed_driver": json.loads(driver.stdout),
        "outside_checkout": not target.is_relative_to(ROOT),
        "environment": str(venv),
        "wheel_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (core_wheel, app_wheel)
        },
    }
    destination = os.environ.get("ZARA_RESTART_EVIDENCE")
    if destination:
        (Path(destination) / "wheel-install.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    assert evidence["core_only"]["independent"] is True
    assert evidence["installed_driver"]["effects"] == 2
