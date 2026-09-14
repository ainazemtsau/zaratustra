"""Clean installed command-contract probes for both shipped standard agent skills."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def _save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8")


def _hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _invoke(
    output: Path, name: str, arguments: list[str], *, home: Path, cwd: Path, console: bool = False
) -> dict[str, Any]:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.update(HOME=str(home), USERPROFILE=str(home), PYTHONIOENCODING="utf-8")
    prefix = (
        [str(Path(sys.executable).parent / ("zara.exe" if os.name == "nt" else "zara"))]
        if console
        else [sys.executable, "-I", "-m", "zaratustra"]
    )
    result = subprocess.run(
        [*prefix, *arguments],
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    record = dict(
        command=[*prefix, *arguments],
        rc=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        home=str(home),
        cwd=str(cwd),
    )
    _save(output / f"{name}.json", record)
    return record


def run(output: Path) -> dict[str, Any]:
    """Exercise real CLI effects; exact confirmations are explicit fictional fixtures."""
    from tools.probe_public_onboarding_r2_t3 import _activate, _confirm
    from tools.probe_public_onboarding_r2_t3_correction import _cli
    from zaratustra.connections import Agent, inspect_connection
    from zaratustra.core import MutationRequest, apply_mutation, read_records

    output.mkdir(parents=True)
    home = output / "empty-home"
    cwd = output / "empty-cwd"
    home.mkdir()
    cwd.mkdir()
    rows: dict[str, Any] = {}
    agents: tuple[Agent, ...] = ("codex", "claude")
    for agent in agents:
        chat = output / f"{agent}-chat"
        exported = _invoke(
            output,
            f"{agent}-export",
            ["entry", "connection", agent, str(chat)],
            home=home,
            cwd=cwd,
            console=True,
        )
        assert exported["rc"] == 0, exported
        connection = inspect_connection(agent, chat)
        assert connection.state == "files_match" and connection.skill is not None
        args = ["entry", "ready", "--connection", agent, "--connection-root", str(chat)]
        first = _invoke(output, f"{agent}-unselected", args, home=home, cwd=cwd, console=True)
        fallback = _invoke(output, f"{agent}-fallback", args, home=home, cwd=cwd)
        assert first["rc"] == fallback["rc"] == 0, (first, fallback)
        assert first["stdout"] == fallback["stdout"]
        before = connection.skill.read_bytes()
        collision = _invoke(
            output,
            f"{agent}-collision",
            ["entry", "connection", agent, str(chat)],
            home=home,
            cwd=cwd,
        )
        assert collision["rc"] == 1 and connection.skill.read_bytes() == before
        connection.skill.write_bytes(before + b"fictional changed connection")
        changed = _invoke(output, f"{agent}-changed", args, home=home, cwd=cwd)
        assert changed["rc"] == 1
        connection.skill.write_bytes(before)
        assert inspect_connection(agent, chat).state == "files_match"
        rows[agent] = dict(
            skill=str(connection.skill),
            sha256=connection.actual_sha256,
            exported=exported,
            unselected=first,
            fallback=fallback,
            collision=collision,
            changed=changed,
            args=args,
        )
    assert list(home.iterdir()) == list(cwd.iterdir()) == []
    missing = _invoke(
        output,
        "missing-connection",
        ["entry", "ready", "--connection", "codex", "--connection-root", str(home)],
        home=home,
        cwd=cwd,
    )
    assert missing["rc"] == 1 and list(home.iterdir()) == []
    absent = _invoke(
        output,
        "absent-selection",
        [
            "entry",
            "ready",
            "--catalog",
            str(home / "catalog.json"),
            "--designation",
            "Fictional missing",
        ],
        home=home,
        cwd=cwd,
    )
    assert absent["rc"] == 1 and list(home.iterdir()) == []
    # Ordinary user prose flows through the actual executable, without input JSON.
    draft_catalog = output / "draft-catalog.json"
    draft_args = [
        "entry",
        "create",
        "prose",
        str(draft_catalog),
        "Fictional draft",
        "Retain a fictional note",
        "--title",
        "Fictional draft",
        "--outcome",
        "A saved fictional note",
        "--constraint",
        "Local fictional data only",
        "--created-by",
        "fictional-probe",
    ]
    draft = _invoke(output, "draft", draft_args, home=home, cwd=cwd)
    assert draft["rc"] == 0, draft
    for agent in agents:
        args = [
            *rows[agent]["args"],
            "--catalog",
            str(draft_catalog),
            "--designation",
            "Fictional draft",
        ]
        draft_first = _invoke(output, f"{agent}-draft-first", args, home=home, cwd=cwd)
        draft_retry = _invoke(output, f"{agent}-draft-retry", args, home=home, cwd=cwd)
        assert draft_first["rc"] == draft_retry["rc"] == 0
        assert draft_first["stdout"] == draft_retry["stdout"]
        rows[agent]["draft"] = draft_first
    # Only development setup exposes a fictional supported definition and confirmation.
    selected = _activate(output / "fictional-data", "simple")
    workspace: Path = selected["workspace"]
    catalog: Path = selected["catalog"]
    for stage in ("current_work", "no_current_work"):
        if stage == "no_current_work":
            state = read_records(workspace)
            request = MutationRequest(
                operation_id=uuid4(),
                workspace_id=state.workspace_id,
                work_id=selected["first_work_id"],
                expected_revision=state.state_revision,
                operation="cancel_work",
                provenance="Fictional T4 terminal/no-current probe",
            )
            apply_mutation(workspace, request, _confirm(workspace, request))
        state_before = _hashes(output / "fictional-data")
        for agent in agents:
            args = [
                *rows[agent]["args"],
                "--catalog",
                str(catalog),
                "--designation",
                selected["designation"],
            ]
            denied = _invoke(output, f"{agent}-{stage}-console-refusal", args, home=home, cwd=cwd)
            assert denied["rc"] == 1 and "permission_denied" in denied["stderr"], denied
            first = _cli(output, f"{agent}-{stage}-first", args)
            retry = _cli(output, f"{agent}-{stage}-retry", args)
            assert first["rc"] == retry["rc"] == 0, (first, retry)
            assert first["stdout"] == retry["stdout"]
            assert f"Stage: {stage}" in first["stdout"]
            assert first["runtime"]["pid"] != retry["runtime"]["pid"]
            assert len(first["runtime"]["prompts"]) == 1
            assert first["runtime"]["prompts"] == retry["runtime"]["prompts"]
            rows[agent][stage] = dict(first=first, retry=retry, console_refusal=denied)
        assert _hashes(output / "fictional-data") == state_before
        _save(output / f"{stage}-data-hashes.json", state_before)
    summary = dict(
        agents=rows,
        current_and_no_current_byte_stable=True,
        fresh_home_and_cwd_unchanged=list(home.iterdir()) == list(cwd.iterdir()) == [],
        source_commit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, encoding="utf-8"
        ).strip(),
        synthetic_confirmation_not_owner_acceptance=True,
        native_agent_session_loading="pending separate host probe",
        remote_exact_pin_download="pending publication authorization",
    )
    _save(output / "summary.json", summary)
    return summary


def verify(output: Path, hosts: list[str] | None = None) -> None:
    """Build locally and install locked cached artifacts outside checkout; no remote fetch."""
    output.mkdir(parents=True)
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("STOP: required tool uv unavailable")
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    wheel = ROOT / f"dist/zaratustra-{metadata['project']['version']}-py3-none-any.whl"
    subprocess.run([uv, "build", "--no-sources"], cwd=ROOT, check=True)
    retained = output / wheel.name
    shutil.copyfile(wheel, retained)
    with zipfile.ZipFile(retained) as archive:
        names = archive.namelist()
        assert "zaratustra/connections/SKILL.md" in names
        assert "zaratustra/__main__.py" in names
        assert not any(name.startswith(("tests/", "tools/")) for name in names)
    requirements = output / "runtime-requirements.txt"
    subprocess.run(
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
        cwd=ROOT,
        check=True,
    )
    with tempfile.TemporaryDirectory(prefix="zaratustra-t4-") as temporary:
        base = Path(temporary).resolve()
        assert not base.is_relative_to(ROOT)
        assert base.is_relative_to(Path(tempfile.gettempdir()).resolve())
        environment = base / "venv"
        subprocess.run([uv, "venv", "--python", "3.13.7", str(environment)], cwd=base, check=True)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [
                uv,
                "pip",
                "install",
                "--offline",
                "--python",
                str(python),
                "-r",
                str(requirements),
                str(retained),
            ],
            cwd=base,
            check=True,
        )
        subprocess.run([uv, "pip", "check", "--python", str(python)], cwd=base, check=True)
        home = base / "home"
        cwd = base / "cwd"
        home.mkdir()
        cwd.mkdir()
        child_env = dict(os.environ)
        child_env.pop("PYTHONPATH", None)
        child_env.update(HOME=str(home), USERPROFILE=str(home), PYTHONIOENCODING="utf-8")
        subprocess.run(
            [
                str(python),
                "-I",
                "-X",
                "utf8",
                str(Path(__file__).resolve()),
                "--child",
                "--output",
                str(output),
                *(hosts or []),
            ],
            cwd=cwd,
            env=child_env,
            check=True,
        )
        assert list(home.iterdir()) == list(cwd.iterdir()) == []
    _save(
        output / "installation.json",
        dict(
            wheel_sha256=hashlib.sha256(retained.read_bytes()).hexdigest(),
            wheel_files=names,
            offline_dependency_install=True,
            temporary_runtime_cleaned=True,
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--codex", type=Path, help="Explicit native Codex binary for no-turn discovery."
    )
    parser.add_argument(
        "--claude", type=Path, help="Explicit native Claude binary for no-turn discovery."
    )
    args = parser.parse_args()
    if (args.codex is None) != (args.claude is None):
        parser.error("Supply both explicit host binaries or neither")
    for name in ("STOP", "STEER.md"):
        if (ROOT / name).exists():
            parser.error(f"Read and resolve {name} before running")
    output = args.output.resolve()
    if output == ROOT / "_scratch" or not output.is_relative_to(ROOT / "_scratch"):
        parser.error("Choose a NEW directory inside this worktree's ignored _scratch")
    if args.child:
        import zaratustra

        package = Path(zaratustra.__file__).resolve()
        assert package.is_relative_to(Path(sys.executable).parent.parent)
        assert not package.is_relative_to(ROOT)
        assert (
            importlib.util.find_spec("tests") is None and importlib.util.find_spec("tools") is None
        )
        sys.path.append(str(ROOT))
        run(output / "commands")
        modules = {
            name: str(module.__file__)
            for name, module in sys.modules.items()
            if (name == "zaratustra" or name.startswith("zaratustra."))
            and getattr(module, "__file__", None)
        }
        assert all(Path(path).resolve().is_relative_to(package.parent) for path in modules.values())
        _save(output / "installed-modules.json", modules)
        if args.codex is not None:
            from tools.probe_public_onboarding_r2_t4_hosts import run as discover

            discover(output / "native-hosts", args.codex.resolve(), args.claude.resolve())
    elif output.exists():
        parser.error("Choose a NEW directory; evidence is never overwritten")
    else:
        hosts = (
            ["--codex", str(args.codex.resolve()), "--claude", str(args.claude.resolve())]
            if args.codex is not None
            else None
        )
        verify(output, hosts)
    print(f"PASS: both shipped command contracts; evidence at {output}")


if __name__ == "__main__":
    main()
