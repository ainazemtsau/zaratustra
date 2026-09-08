"""Installed zara command. All workspace logic belongs to Core."""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import version
from pathlib import Path

from pydantic import ValidationError

from zaratustra.core import (
    InitialRecords,
    WorkspaceError,
    create_initial_records,
    init_workspace,
    migrate_workspace,
    read_records,
    read_workspace,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zara", description="Zaratustra workspace foundation")
    parser.add_argument("--version", action="version", version=f"zara {version('zaratustra')}")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, description in (
        ("init", "Initialize an empty directory or read its existing workspace."),
        ("status", "Read persisted workspace metadata without changing it."),
        ("migrate", "Explicitly migrate an initialized workspace to schema 2."),
    ):
        command = commands.add_parser(name, help=description, description=description)
        command.add_argument("path", nargs="?", default=".", type=Path)
    records = commands.add_parser("records", help="Create initial drafts or read stored records.")
    record_commands = records.add_subparsers(dest="records_command", required=True)
    read = record_commands.add_parser(
        "read", help="Read one persisted snapshot; no Work execution."
    )
    read.add_argument("path", nargs="?", default=".", type=Path)
    create = record_commands.add_parser(
        "create", help="Create initial records once; grants no rights."
    )
    create.add_argument("path", nargs="?", default=".", type=Path)
    for name in ("process-title", "goal", "expected-result", "budget", "artifact-title"):
        create.add_argument(f"--{name}", required=True)
    create.add_argument("--acceptance", action="append", required=True)
    create.add_argument("--boundary", action="append", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "records":
            snapshot = (
                read_records(args.path)
                if args.records_command == "read"
                else create_initial_records(
                    args.path,
                    InitialRecords(
                        process_title=args.process_title,
                        goal=args.goal,
                        expected_result=args.expected_result,
                        acceptance=tuple(args.acceptance),
                        boundaries=tuple(args.boundary),
                        budget=args.budget,
                        artifact_title=args.artifact_title,
                    ),
                )
            )
            output = snapshot.model_dump_json(indent=2)
        else:
            operation = {
                "init": init_workspace,
                "status": read_workspace,
                "migrate": migrate_workspace,
            }[args.command]
            output = operation(args.path).model_dump_json(indent=2)
    except (WorkspaceError, ValidationError) as error:
        print(f"zara: {error}", file=sys.stderr)
        return 1
    print(output)
    return 0
