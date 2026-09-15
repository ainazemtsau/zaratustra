"""Ship thin standard skills; keep all product meaning in the common entry."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from typing import Literal

Agent = Literal["codex", "claude"]


@dataclass(frozen=True)
class ConnectionStatus:
    agent: Agent
    root: Path | None
    state: Literal["not_selected", "missing", "different", "files_match"]
    skill: Path | None
    tool_config: Path | None
    expected_sha256: str | None
    actual_sha256: str | None


def _relative(agent: Agent) -> Path:
    if agent not in ("codex", "claude"):
        raise ValueError("Unknown connection kind")
    return Path(".agents" if agent == "codex" else ".claude") / "skills/zaratustra/SKILL.md"


def _tool_relative(agent: Agent) -> Path:
    _relative(agent)
    return Path(".codex/config.toml" if agent == "codex" else ".mcp.json")


def connection_bytes(agent: Agent, root: Path) -> bytes:
    """Render only installation paths; never retain a user's data selection."""
    _relative(agent)
    content = files(__package__).joinpath("SKILL.md").read_text(encoding="utf-8")
    for key, value in (
        ("@@PYTHON@@", Path(sys.executable).as_posix()),
        ("@@ROOT@@", root.expanduser().resolve().as_posix()),
        ("@@AGENT@@", agent),
        ("@@VERSION@@", version("zaratustra")),
    ):
        content = content.replace(key, value)
    return content.encode("utf-8")


def tool_config_bytes(agent: Agent, root: Path) -> bytes:
    """Render the one local stdio adapter configuration for a fresh chat root."""
    selected = root.expanduser().resolve()
    if agent == "codex":
        content = "\n".join(
            (
                "[mcp_servers.zaratustra]",
                f'command = "{Path(sys.executable).as_posix()}"',
                'args = ["-I", "-m", "zaratustra.trusted_chat"]',
                f'cwd = "{selected.as_posix()}"',
                'enabled_tools = ["run"]',
                'default_tools_approval_mode = "approve"',
                "",
            )
        )
    elif agent == "claude":
        content = (
            json.dumps(
                {
                    "mcpServers": {
                        "zaratustra": {
                            "command": Path(sys.executable).as_posix(),
                            "args": ["-I", "-m", "zaratustra.trusted_chat"],
                            "cwd": selected.as_posix(),
                        }
                    }
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    else:
        raise ValueError("Unknown connection kind")
    return content.encode("utf-8")


def _manifest(agent: Agent, root: Path) -> bytes:
    return b"\0".join(
        (
            _relative(agent).as_posix().encode("utf-8"),
            connection_bytes(agent, root),
            _tool_relative(agent).as_posix().encode("utf-8"),
            tool_config_bytes(agent, root),
        )
    )


def inspect_connection(agent: Agent, root: Path | None) -> ConnectionStatus:
    relative = _relative(agent)
    if root is None:
        return ConnectionStatus(agent, None, "not_selected", None, None, None, None)
    selected = root.expanduser().resolve()
    skill = selected / relative
    tool_config = selected / _tool_relative(agent)
    expected = _manifest(agent, selected)
    expected_hash = hashlib.sha256(expected).hexdigest()
    try:
        actual = skill.read_bytes()
    except FileNotFoundError:
        return ConnectionStatus(agent, selected, "missing", skill, tool_config, expected_hash, None)
    try:
        actual_config = tool_config.read_bytes()
    except FileNotFoundError:
        return ConnectionStatus(agent, selected, "missing", skill, tool_config, expected_hash, None)
    actual = b"\0".join(
        (
            relative.as_posix().encode("utf-8"),
            actual,
            _tool_relative(agent).as_posix().encode("utf-8"),
            actual_config,
        )
    )
    actual_hash = hashlib.sha256(actual).hexdigest()
    state: Literal["different", "files_match"] = (
        "files_match" if actual == expected else "different"
    )
    return ConnectionStatus(agent, selected, state, skill, tool_config, expected_hash, actual_hash)


def export_connection(agent: Agent, root: Path) -> ConnectionStatus:
    """Create one new chat project; never replace any existing destination."""
    relative = _relative(agent)
    selected = root.expanduser().resolve()
    selected.mkdir(exist_ok=False)
    skill = selected / relative
    skill.parent.mkdir(parents=True)
    with skill.open("xb") as stream:
        stream.write(connection_bytes(agent, selected))
    tool_config = selected / _tool_relative(agent)
    tool_config.parent.mkdir(parents=True, exist_ok=True)
    with tool_config.open("xb") as stream:
        stream.write(tool_config_bytes(agent, selected))
    return inspect_connection(agent, selected)


__all__ = [
    "Agent",
    "ConnectionStatus",
    "connection_bytes",
    "export_connection",
    "inspect_connection",
    "tool_config_bytes",
]
