"""Installed structured tool adapter and explicit local setup command."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError

from zaratustra.commands import Command, ContextGuard, execute, read_context
from zaratustra.commands.connect import connect_agent
from zaratustra.commands.storage_adapter import migrate
from zaratustra.core import WorkspaceError
from zaratustra.home import HomeError, init_home
from zaratustra.journal import Reference, read_export


class Invocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: Command
    source_ref: str
    session_process: UUID | None = None
    guard: ContextGuard | None = None


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
    inspect = commands.add_parser("inspect-export", help="Read a standalone export without a Home")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--reference", help="JSON version-pinned reference inside the package")
    inspect.add_argument("--offset", type=int, default=0)
    inspect.add_argument("--limit", type=int, default=20)
    migration = commands.add_parser("storage-migrate", help="Back up and migrate a complete Home")
    migration.add_argument("--home", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result: dict[str, Any]
        if args.command == "setup":
            new_home = (
                not (args.home / ".zara-home").exists() and not (args.home / ".zara-data").exists()
            )
            init_home(args.home)
            if new_home:
                migrate(args.home)
            result = connect_agent(
                args.directory,
                args.home,
                agent=args.agent,
                workspace=args.workspace,
                update=args.update_connection,
            )
        elif args.command == "storage-migrate":
            result = migrate(args.home)
        elif args.command == "schema":
            result = Command.model_json_schema()
        elif args.command == "inspect-export":
            result = read_export(
                args.path,
                reference=Reference.model_validate_json(args.reference) if args.reference else None,
                offset=args.offset,
                limit=args.limit,
            )
        else:
            raw = sys.stdin.buffer.read(2_000_001)
            if len(raw) > 2_000_000:
                raise HomeError("input_too_large", "Command exceeds 2 MB")
            invocation = Invocation.model_validate_json(raw)
            result = execute(
                read_context(args.directory),
                invocation.command,
                source_ref=invocation.source_ref,
                session_process=invocation.session_process,
                guard=invocation.guard,
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
