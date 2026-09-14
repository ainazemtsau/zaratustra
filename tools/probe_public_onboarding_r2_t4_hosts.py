"""No-inference native skill discovery with explicit host binaries and empty homes."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, TextIO


def selected_skill(agent: str, events: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    """Check the actual host discovery result, not an arbitrary matching string."""
    if agent == "codex":
        response = next(row["result"] for row in events if row.get("id") == 1)
        data = next(row for row in response["data"] if Path(row["cwd"]) == root)
        assert not data.get("errors"), data
        skill = next(row for row in data["skills"] if row["name"] == "zaratustra")
        assert Path(skill["path"]) == root / ".agents/skills/zaratustra/SKILL.md"
        assert skill["enabled"] is True
        return dict(skill)
    response = next(row["response"] for row in events if row.get("type") == "control_response")
    assert response["subtype"] == "success"
    command = next(row for row in response["response"]["commands"] if row["name"] == "zaratustra")
    assert "(project)" in command["description"]
    return dict(command)


def _observe(executable: Path, agent: str, root: Path, home: Path) -> dict[str, Any]:
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP"}
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    environment.update(
        HOME=str(home),
        USERPROFILE=str(home),
        APPDATA=str(home / "appdata"),
        LOCALAPPDATA=str(home / "localappdata"),
    )
    if agent == "codex":
        environment["CODEX_HOME"] = str(home)
        command = [str(executable), "app-server", "--stdio"]
    else:
        environment["CLAUDE_CONFIG_DIR"] = str(home)
        environment["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        command = [
            str(executable),
            "--print",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
            "--setting-sources",
            "project",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--no-chrome",
        ]
    host_version = subprocess.check_output(
        [str(executable), "--version"], cwd=root, env=environment, encoding="utf-8"
    ).strip()
    process = subprocess.Popen(
        command,
        cwd=root,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    events: list[dict[str, Any]] = []
    sent: list[dict[str, Any]] = []
    incoming: queue.Queue[str] = queue.Queue()
    errors: list[str] = []

    def read_stdout(stream: TextIO) -> None:
        for line in stream:
            incoming.put(line)

    def read_stderr(stream: TextIO) -> None:
        errors.extend(stream.readlines())

    stdout_reader = threading.Thread(target=read_stdout, args=(process.stdout,), daemon=True)
    stderr_reader = threading.Thread(target=read_stderr, args=(process.stderr,), daemon=True)
    stdout_reader.start()
    stderr_reader.start()

    def send(value: dict[str, Any]) -> None:
        assert process.stdin is not None
        sent.append(value)
        process.stdin.write(json.dumps(value) + chr(10))
        process.stdin.flush()

    try:
        if agent == "codex":
            send(
                dict(
                    id=0,
                    method="initialize",
                    params=dict(
                        clientInfo=dict(name="zaratustra_local_discovery_probe", version="1")
                    ),
                )
            )
        else:
            send(
                dict(
                    type="control_request",
                    request_id="t4-initialize",
                    request=dict(subtype="initialize"),
                )
            )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                line = incoming.get(timeout=0.2)
            except queue.Empty:
                if process.poll() is not None:
                    break
                continue
            event = json.loads(line)
            events.append(event)
            if agent == "codex" and event.get("id") == 0 and "result" in event:
                send(dict(method="initialized", params={}))
                send(
                    dict(
                        id=1, method="skills/list", params=dict(cwds=[str(root)], forceReload=True)
                    )
                )
            if (agent == "codex" and event.get("id") == 1) or (
                agent == "claude" and event.get("type") == "control_response"
            ):
                break
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
        stdout_reader.join(timeout=1)
        stderr_reader.join(timeout=1)
    return dict(
        command=command,
        version=host_version,
        home=str(home),
        root=str(root),
        pid=process.pid,
        sent=sent,
        received=events,
        stderr=errors,
    )


def run(output: Path, codex: Path, claude: Path) -> None:
    from zaratustra.connections import Agent, export_connection

    output.mkdir()
    hosts: tuple[tuple[Agent, Path], ...] = (("codex", codex), ("claude", claude))
    # Retain native host evidence: descendants may retain Windows cwd handles after exit.
    base = Path(tempfile.mkdtemp(prefix="zaratustra-t4-hosts-")).resolve()
    assert base.is_relative_to(Path(tempfile.gettempdir()).resolve())
    for agent, executable in hosts:
        root = base / f"{agent}-chat"
        skill = export_connection(agent, root)
        assert skill.skill is not None
        original = skill.skill.read_bytes()
        (output / f"{agent}-SKILL.md").write_bytes(original)
        for attempt in (1, 2):
            home = base / f"{agent}-home-{attempt}"
            home.mkdir()
            record = _observe(executable, agent, root, home)
            # Retain failures before asserting, too.
            path = output / f"{agent}-{attempt}.json"
            path.write_text(json.dumps(record, indent=2) + chr(10), encoding="utf-8")
            record["selected_skill"] = selected_skill(agent, record["received"], root)
            assert skill.skill.read_bytes() == original
            record.update(
                skill_sha256=skill.actual_sha256,
                installed_python=sys.executable,
                no_model_turn_sent=True,
                skill_bytes_unchanged=True,
                native_root_retained=True,
            )
            path.write_text(json.dumps(record, indent=2) + chr(10), encoding="utf-8")
