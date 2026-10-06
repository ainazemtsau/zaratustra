"""Installed, read-only workflows for the ordinary interactive Pi entry."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def external_workflow_skill() -> Path:
    """Locate the packaged workflow, never an instance file or a cwd fallback."""
    resource = files("zaratustra.pi_adapter").joinpath("skills", "zaratustra-external", "SKILL.md")
    path = Path(str(resource))
    if not path.is_file():
        raise FileNotFoundError(f"Installed external workflow is unavailable: {path}")
    return path
