"""Installed structured tool adapter and explicit local setup command."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from zaratustra.commands import Command, execute, read_context
from zaratustra.commands.connect import connect_agent
from zaratustra.core import WorkspaceError
from zaratustra.home import HomeError, init_home


class Invocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: Command
    source_ref: str


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Trusted local agent operation, JSON input on stdin")
    run.add_argument("--directory", type=Path, default=Path.cwd())
    setup = commands.add_parser(
        "setup", help="Prepare a selected Home and additive agent connection"
    )
    setup.add_argument("--home", type=Path, required=True)
    setup.add_argument("--directory", type=Path, required=True)
    setup.add_argument("--agent", choices=("pi", "codex"), required=True)
    setup.add_argument("--workspace", type=Path)
    setup.add_argument("--update-connection", action="store_true")
    schema = commands.add_parser("schema", help="Describe structured operations")
    schema.set_defaults(command="schema")
    args = parser.parse_args(argv)
    try:
        result: dict[str, Any]
        if args.command == "setup":
            init_home(args.home)
            result = connect_agent(
                args.directory,
                args.home,
                agent=args.agent,
                workspace=args.workspace,
                update=args.update_connection,
            )
        elif args.command == "schema":
            result = Command.model_json_schema()
        else:
            raw = sys.stdin.buffer.read(2_000_001)
            if len(raw) > 2_000_000:
                raise HomeError("input_too_large", "Command exceeds 2 MB")
            invocation = Invocation.model_validate_json(raw)
            result = execute(
                read_context(args.directory), invocation.command, source_ref=invocation.source_ref
            )
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
        return 0
    except (WorkspaceError, OSError, ValueError, ValidationError) as error:
        failure = {
            "ok": False,
            "code": getattr(error, "code", "invalid_request"),
            "error": str(error),
        }
        if isinstance(error, HomeError) and error.choices:
            failure["choices"] = list(error.choices)
        print(json.dumps(failure, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
