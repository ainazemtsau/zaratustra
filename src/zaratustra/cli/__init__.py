"""Installed zara command. All workspace logic belongs to Core."""

from __future__ import annotations

import argparse
import base64
import json
import sys
from importlib.metadata import version
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from zaratustra.core import (
    InitialRecords,
    MutationRequest,
    ProjectionRebuildError,
    ReceiptQuery,
    WorkspaceError,
    apply_mutation,
    create_initial_records,
    init_workspace,
    inspect_artifacts,
    migrate_workspace,
    prepare_authorization,
    read_artifact,
    read_history,
    read_projection_status,
    read_receipt,
    read_records,
    read_workspace,
    rebuild_projections,
)
from zaratustra.local import confirm_on_console


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zara", description="Zaratustra workspace foundation")
    parser.add_argument("--version", action="version", version=f"zara {version('zaratustra')}")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, description in (
        ("init", "Initialize an empty directory or read its existing workspace."),
        ("status", "Read persisted workspace metadata without changing it."),
        ("migrate", "Explicitly migrate an initialized workspace to schema 4."),
        ("history", "Read the owner-local mutation audit; not Work context."),
    ):
        command = commands.add_parser(name, help=description, description=description)
        command.add_argument("path", nargs="?", default=".", type=Path)
        if name == "migrate":
            command.add_argument("--to", type=int, choices=(2, 3, 4), default=4)
    for name in ("mutate", "receipt"):
        command = commands.add_parser(name, help="Confirm an exact internal operation/query.")
        command.add_argument("path", type=Path)
        command.add_argument("request_json", help="Core request JSON; no Handoff importer.")
        if name == "mutate":
            command.add_argument(
                "--content-file", type=Path, help="Exact confirmed Artifact bytes."
            )
    artifacts = commands.add_parser(
        "artifacts", help="Inspect registered versions and verified bytes."
    )
    artifact_commands = artifacts.add_subparsers(dest="artifacts_command", required=True)
    for name in ("read", "inspect"):
        command = artifact_commands.add_parser(name)
        command.add_argument("path", type=Path)
        if name == "read":
            command.add_argument("artifact_id", type=UUID)
            command.add_argument("--version-id", type=UUID)
    projections = commands.add_parser("projections", help="Inspect or rebuild DB-derived overview.")
    projection_commands = projections.add_subparsers(dest="projections_command", required=True)
    for name in ("status", "rebuild"):
        command = projection_commands.add_parser(name)
        command.add_argument("path", type=Path)
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
        if args.command == "mutate":
            request = MutationRequest.model_validate_json(args.request_json)
            caller = confirm_on_console(prepare_authorization(args.path, request))
            content = args.content_file.read_bytes() if args.content_file is not None else None
            output = apply_mutation(args.path, request, caller, content=content).model_dump_json(
                indent=2
            )
        elif args.command == "receipt":
            query = ReceiptQuery.model_validate_json(args.request_json)
            caller = confirm_on_console(prepare_authorization(args.path, query))
            output = read_receipt(args.path, query, caller).model_dump_json(indent=2)
        elif args.command == "migrate":
            output = migrate_workspace(args.path, target_version=args.to).model_dump_json(indent=2)
        elif args.command == "history":
            output = read_history(args.path).model_dump_json(indent=2)
        elif args.command == "artifacts":
            if args.artifacts_command == "inspect":
                output = inspect_artifacts(args.path).model_dump_json(indent=2)
            else:
                artifact = read_artifact(args.path, args.artifact_id, args.version_id)
                output = json.dumps(
                    dict(
                        version=artifact.version.model_dump(mode="json"),
                        relative_path=artifact.version.relative_path,
                        content_base64=base64.b64encode(artifact.content).decode("ascii"),
                    ),
                    indent=2,
                )
        elif args.command == "projections":
            projection_operation = (
                rebuild_projections
                if args.projections_command == "rebuild"
                else read_projection_status
            )
            output = projection_operation(args.path).model_dump_json(indent=2)
        elif args.command == "records":
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
            }[args.command]
            output = operation(args.path).model_dump_json(indent=2)
    except ProjectionRebuildError as error:
        print(
            json.dumps(
                dict(
                    status="rebuild_required",
                    receipt=error.receipt.model_dump(mode="json"),
                    error=str(error),
                ),
                indent=2,
            )
        )
        return 2
    except (WorkspaceError, ValidationError, OSError) as error:
        print(f"zara: {error}", file=sys.stderr)
        return 1
    print(output)
    return 0
