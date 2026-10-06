"""Resolve the user's ordinary Pi installation without keeping a frozen copy."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

PI_PACKAGE = "@earendil-works/pi-coding-agent"


@dataclass(frozen=True)
class PiRuntime:
    root: Path
    cli: Path
    version: str


def read_pi_runtime(root: Path) -> PiRuntime:
    root = root.expanduser().resolve()
    package = root / "node_modules" / "@earendil-works" / "pi-coding-agent"
    metadata = json.loads((package / "package.json").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or metadata.get("name") != PI_PACKAGE:
        raise ValueError("Selected runtime is not the ordinary Pi coding agent")
    version = metadata.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("Pi package has no version")
    binary = metadata.get("bin", {})
    entry = binary.get("pi") if isinstance(binary, dict) else None
    if entry is not None and not isinstance(entry, str):
        raise ValueError("Pi CLI entry must be a path")
    # Earlier fixture/package metadata omitted bin; preserve that ordinary layout.
    cli = (package / (entry or "dist/bundle/cli.js")).resolve()
    if not cli.is_relative_to(package.resolve()) or not cli.is_file():
        raise ValueError("Pi CLI is missing or leaves its package")
    return PiRuntime(root, cli, version)


def system_pi_runtime() -> PiRuntime:
    executable = shutil.which("pi")
    if executable is None:
        raise ValueError("Pi is not on PATH. Install Pi, then retry zaratustra")
    shim = Path(executable).absolute()
    # npm shims on Windows and resolved bin symlinks on Unix both lead to a
    # node_modules ancestor. The same PATH selection is used again at each run.
    for selected in (shim, shim.resolve()):
        for parent in selected.parents:
            package = parent / "node_modules" / "@earendil-works" / "pi-coding-agent"
            if (package / "package.json").is_file():
                return read_pi_runtime(parent)
    raise ValueError(f"Cannot resolve the npm Pi package behind {shim}")
