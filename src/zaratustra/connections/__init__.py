"""Ship thin standard skills; keep all product meaning in the common entry."""

from __future__ import annotations

import hashlib
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
    expected_sha256: str | None
    actual_sha256: str | None


def _relative(agent: Agent) -> Path:
    if agent not in ("codex", "claude"):
        raise ValueError("Unknown connection kind")
    return Path(".agents" if agent == "codex" else ".claude") / "skills/zaratustra/SKILL.md"


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


def inspect_connection(agent: Agent, root: Path | None) -> ConnectionStatus:
    relative = _relative(agent)
    if root is None:
        return ConnectionStatus(agent, None, "not_selected", None, None, None)
    selected = root.expanduser().resolve()
    skill = selected / relative
    expected = connection_bytes(agent, selected)
    expected_hash = hashlib.sha256(expected).hexdigest()
    try:
        actual = skill.read_bytes()
    except FileNotFoundError:
        return ConnectionStatus(agent, selected, "missing", skill, expected_hash, None)
    actual_hash = hashlib.sha256(actual).hexdigest()
    state: Literal["different", "files_match"] = (
        "files_match" if actual == expected else "different"
    )
    return ConnectionStatus(agent, selected, state, skill, expected_hash, actual_hash)


def export_connection(agent: Agent, root: Path) -> ConnectionStatus:
    """Create one new chat project; never replace any existing destination."""
    relative = _relative(agent)
    selected = root.expanduser().resolve()
    content = connection_bytes(agent, selected)
    selected.mkdir(exist_ok=False)
    skill = selected / relative
    skill.parent.mkdir(parents=True)
    with skill.open("xb") as stream:
        stream.write(content)
    return inspect_connection(agent, selected)


__all__ = [
    "Agent",
    "ConnectionStatus",
    "connection_bytes",
    "export_connection",
    "inspect_connection",
]
