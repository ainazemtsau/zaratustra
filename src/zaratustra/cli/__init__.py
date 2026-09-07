"""Installed zara command. All workspace logic belongs to Core."""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import version
from pathlib import Path

from zaratustra.core import WorkspaceError, init_workspace, read_workspace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zara", description="Zaratustra workspace foundation")
    parser.add_argument("--version", action="version", version=f"zara {version('zaratustra')}")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, description in (
        ("init", "Initialize an empty directory or read its existing workspace."),
        ("status", "Read persisted workspace metadata without changing it."),
    ):
        command = commands.add_parser(name, help=description, description=description)
        command.add_argument("path", nargs="?", default=".", type=Path)
    args = parser.parse_args(argv)
    try:
        info = init_workspace(args.path) if args.command == "init" else read_workspace(args.path)
    except WorkspaceError as error:
        print(f"zara: {error}", file=sys.stderr)
        return 1
    print(info.model_dump_json(indent=2))
    return 0
