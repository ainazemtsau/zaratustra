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
    MAX_HANDOFF_BYTES,
    ArtifactReference,
    ContextQuery,
    Handoff,
    InitialRecords,
    MutationRequest,
    ProjectionRebuildError,
    ReceiptQuery,
    WorkspaceError,
    apply_mutation,
    create_initial_records,
    handoff_request,
    init_workspace,
    inspect_artifacts,
    migrate_workspace,
    open_work,
    parse_result_request,
    prepare_authorization,
    read_artifact,
    read_basic_process,
    read_handoffs,
    read_history,
    read_projection_status,
    read_receipt,
    read_records,
    read_result,
    read_workspace,
    rebuild_projections,
    submit_result,
)
from zaratustra.entry import (
    EntryError,
    add_entry,
    find_entries,
    prepare_entry_read,
    relocate_entry,
    resolve_entry,
    source_path,
)
from zaratustra.first_use import (
    MAX_REQUEST_BYTES,
    MAX_SETUP_BYTES,
    FirstUseError,
    IncompleteFirstUseError,
    create_external_chat_request,
    execute_first_use,
    open_selected_context,
    prepare_external_chat_response,
    prepare_first_use,
    prepare_selected_context,
    save_external_chat_request,
)
from zaratustra.intake import (
    MAX_INTAKE_BYTES,
    IncompleteIntakeError,
    IntakeError,
    IntakeSelection,
    execute_material_intake,
    prepare_material_intake,
)
from zaratustra.local import confirm_material_intake_on_console, confirm_on_console


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zara", description="Zaratustra workspace foundation")
    parser.add_argument("--version", action="version", version=f"zara {version('zaratustra')}")
    commands = parser.add_subparsers(dest="command", required=True)
    entry_command = commands.add_parser(
        "entry", help="Discover and read explicitly cataloged Process instances."
    )
    entry_commands = entry_command.add_subparsers(dest="entry_command", required=True)
    entry_add = entry_commands.add_parser("add", help="Add one explicit workspace and Work.")
    entry_add.add_argument("catalog", type=Path)
    entry_add.add_argument("designation")
    entry_add.add_argument("workspace", type=Path)
    entry_add.add_argument("--work-id", type=UUID, required=True)
    entry_add.add_argument("--alias", action="append", default=[])
    entry_find = entry_commands.add_parser("find", help="Search designations and aliases.")
    entry_find.add_argument("catalog", type=Path)
    entry_find.add_argument("query", nargs="?", default="")
    entry_read = entry_commands.add_parser(
        "read", help="Authorize one selected Work's generic metadata read."
    )
    entry_read.add_argument("catalog", type=Path)
    entry_read.add_argument("designation")
    entry_read.add_argument("--max-bytes", type=int, default=65536)
    entry_relocate = entry_commands.add_parser(
        "relocate", help="Update a path only after stable identity validation."
    )
    entry_relocate.add_argument("catalog", type=Path)
    entry_relocate.add_argument("designation")
    entry_relocate.add_argument("workspace", type=Path)
    entry_intake = entry_commands.add_parser(
        "intake", help="Preview, confirm, publish and accept new external material."
    )
    entry_intake.add_argument("catalog", type=Path)
    entry_intake.add_argument("designation")
    entry_intake.add_argument("source", help="UTF-8 external-material JSON file, or '-' for stdin.")
    entry_start = entry_commands.add_parser(
        "start", help="Create, register and establish one generic accepted starting basis."
    )
    entry_start.add_argument("catalog", type=Path)
    entry_start.add_argument("designation")
    entry_start.add_argument("workspace", type=Path)
    entry_start.add_argument("setup", type=Path, help="Generic first-use JSON; no technical ids.")
    entry_start.add_argument("initial_material", type=Path, help="Initial UTF-8 basis text.")
    entry_start.add_argument("--alias", action="append", default=[])
    entry_open = entry_commands.add_parser(
        "open", help="Open current bounded accepted context by designation."
    )
    entry_open.add_argument("catalog", type=Path)
    entry_open.add_argument("designation")
    entry_open.add_argument("--max-bytes", type=int, default=1_048_576)
    entry_request = entry_commands.add_parser(
        "request", help="Save a copyable provider-neutral request with its exact basis."
    )
    entry_request.add_argument("catalog", type=Path)
    entry_request.add_argument("designation")
    entry_request.add_argument("output", type=Path)
    entry_request.add_argument("--max-bytes", type=int, default=1_048_576)
    entry_receive = entry_commands.add_parser(
        "receive", help="Wrap returned text and use the confirmed recoverable intake."
    )
    entry_receive.add_argument("catalog", type=Path)
    entry_receive.add_argument("designation")
    entry_receive.add_argument("request", type=Path)
    entry_receive.add_argument("response", help="Returned UTF-8 text file, or '-' for stdin.")
    entry_receive.add_argument("--created-by", required=True, help="Human-supplied provider label.")
    result_command = commands.add_parser(
        "result", help="Submit or discover an exact Result and continuation."
    )
    result_commands = result_command.add_subparsers(dest="result_command", required=True)
    result_submit = result_commands.add_parser("submit")
    result_submit.add_argument("path", type=Path)
    result_submit.add_argument("request_file", type=Path)
    result_read = result_commands.add_parser("read")
    result_read.add_argument("path", type=Path)
    result_read.add_argument("query_json")
    work_command = commands.add_parser("work", help="Open current bounded Work context.")
    work_commands = work_command.add_subparsers(dest="work_command", required=True)
    work_open = work_commands.add_parser("open")
    work_open.add_argument("work_id", type=UUID)
    work_open.add_argument("--workspace", type=Path, required=True)
    work_open.add_argument("--workspace-id", type=UUID, required=True)
    work_open.add_argument("--process", type=UUID, required=True)
    work_open.add_argument("--expected-revision", type=int, required=True)
    work_open.add_argument("--max-bytes", type=int, required=True)
    work_open.add_argument("--reference", action="append", default=[])
    for name, description in (
        ("init", "Initialize an empty directory or read its existing workspace."),
        ("status", "Read persisted workspace metadata without changing it."),
        ("migrate", "Explicit migration; use --to 6 for Result storage (default 4)."),
        ("history", "Read the owner-local mutation audit; not Work context."),
    ):
        command = commands.add_parser(name, help=description, description=description)
        command.add_argument("path", nargs="?", default=".", type=Path)
        if name == "migrate":
            command.add_argument("--to", type=int, choices=(2, 3, 4, 5, 6, 7), default=4)
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
    handoff = commands.add_parser("handoff", help="Import or inspect saved accepted results.")
    handoff_commands = handoff.add_subparsers(dest="handoff_command", required=True)
    handoff_commands.add_parser("schema", help="Print the portable Handoff JSON schema.")
    handoff_list = handoff_commands.add_parser("list", help="Owner-local saved acceptance audit.")
    handoff_list.add_argument("path", type=Path)
    handoff_import = handoff_commands.add_parser("import", help="Confirm a file/stdin Handoff.")
    handoff_import.add_argument("path", type=Path)
    handoff_import.add_argument("source", help="UTF-8 JSON file, or '-' for stdin until EOF.")
    handoff_import.add_argument("--expected-revision", type=int, help="Explicit replay revision.")
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
        if args.command == "entry":
            if args.entry_command == "add":
                output = add_entry(
                    args.catalog,
                    args.designation,
                    args.workspace,
                    args.work_id,
                    aliases=tuple(args.alias),
                ).model_dump_json(indent=2)
            elif args.entry_command == "find":
                output = find_entries(args.catalog, args.query).model_dump_json(indent=2)
            elif args.entry_command == "relocate":
                output = relocate_entry(
                    args.catalog, args.designation, args.workspace
                ).model_dump_json(indent=2)
            elif args.entry_command == "start":
                with args.setup.open("rb") as stream:
                    setup_content = stream.read(MAX_SETUP_BYTES + 1)
                with args.initial_material.open("rb") as stream:
                    initial_material = stream.read(MAX_INTAKE_BYTES + 1)
                first_use = prepare_first_use(
                    args.catalog,
                    args.designation,
                    args.workspace,
                    setup_content,
                    initial_material,
                    aliases=tuple(args.alias),
                )
                authorizations = tuple(
                    confirm_on_console(prepare_authorization(first_use.workspace, request))
                    for request in first_use.pending
                )
                output = execute_first_use(first_use, authorizations).model_dump_json(indent=2)
            elif args.entry_command in ("open", "request"):
                selected = prepare_selected_context(
                    args.catalog, args.designation, max_bytes=args.max_bytes
                )
                caller = confirm_on_console(
                    prepare_authorization(selected.workspace, selected.query)
                )
                package = open_selected_context(selected, caller)
                if args.entry_command == "open":
                    sys.stdout.buffer.write(package.output)
                    sys.stdout.buffer.flush()
                    return 0
                external_request = create_external_chat_request(selected, package)
                save_external_chat_request(args.output, external_request)
                output = json.dumps(
                    dict(
                        status="external_request_saved",
                        designation=external_request.designation,
                        output=args.output.expanduser().resolve().as_posix(),
                        request_id=str(external_request.request_id),
                        source_revision=external_request.source_revision,
                        context_sha256=external_request.context_sha256,
                        provider_contacted=False,
                    ),
                    indent=2,
                )
            elif args.entry_command == "receive":
                with args.request.open("rb") as stream:
                    request_content = stream.read(MAX_REQUEST_BYTES + 1)
                from_stdin = args.response == "-"
                if from_stdin:
                    response_content = sys.stdin.buffer.read(MAX_INTAKE_BYTES + 1)
                    response_ref = "stdin"
                else:
                    response = Path(args.response).expanduser().resolve()
                    with response.open("rb") as stream:
                        response_content = stream.read(MAX_INTAKE_BYTES + 1)
                    response_ref = response.as_posix()
                intake_prepared = prepare_external_chat_response(
                    args.catalog,
                    args.designation,
                    request_content,
                    response_content,
                    created_by=args.created_by,
                    source_ref=response_ref,
                )
                authorization = confirm_material_intake_on_console(
                    intake_prepared, separate_terminal=from_stdin
                )
                output = execute_material_intake(intake_prepared, authorization).model_dump_json(
                    indent=2
                )
            elif args.entry_command == "intake":
                entry = resolve_entry(args.catalog, args.designation)
                workspace = source_path(args.catalog, entry)
                from_stdin = args.source == "-"
                if from_stdin:
                    content = sys.stdin.buffer.read(MAX_INTAKE_BYTES + 1)
                    source_ref = "stdin"
                else:
                    source = Path(args.source).expanduser().resolve()
                    with source.open("rb") as stream:
                        content = stream.read(MAX_INTAKE_BYTES + 1)
                    source_ref = source.as_posix()
                intake_prepared = prepare_material_intake(
                    workspace,
                    IntakeSelection(
                        workspace_id=entry.workspace_id,
                        process_id=entry.process_id,
                        work_id=entry.work_id,
                    ),
                    content,
                    source_ref=source_ref,
                )
                authorization = confirm_material_intake_on_console(
                    intake_prepared, separate_terminal=from_stdin
                )
                output = execute_material_intake(intake_prepared, authorization).model_dump_json(
                    indent=2
                )
            else:
                prepared = prepare_entry_read(
                    args.catalog, args.designation, max_bytes=args.max_bytes
                )
                caller = confirm_on_console(
                    prepare_authorization(prepared.workspace, prepared.query)
                )
                basic_package = read_basic_process(prepared.workspace, prepared.query, caller)
                sys.stdout.buffer.write(basic_package.output)
                sys.stdout.buffer.flush()
                return 0
        elif args.command == "result":
            if args.result_command == "submit":
                with args.request_file.open("rb") as stream:
                    raw = stream.read(65537)
                if len(raw) > 65536:
                    raise WorkspaceError("Result request exceeds 64 KiB input limit")
                # Use the same duplicate-key rejection as the portable Handoff parser.
                request = parse_result_request(raw)
                caller = confirm_on_console(prepare_authorization(args.path, request))
                output = submit_result(args.path, request, caller).model_dump_json(indent=2)
            else:
                query = ReceiptQuery.model_validate_json(args.query_json)
                caller = confirm_on_console(prepare_authorization(args.path, query))
                output = json.dumps(
                    read_result(args.path, query, caller).model_dump(mode="json"), indent=2
                )
        elif args.command == "work":
            context_query = ContextQuery(
                workspace_id=args.workspace_id,
                work_id=args.work_id,
                process_id=args.process,
                expected_revision=args.expected_revision,
                max_bytes=args.max_bytes,
                references=tuple(
                    ArtifactReference.model_validate_json(ref) for ref in args.reference
                ),
            )
            caller = confirm_on_console(prepare_authorization(args.workspace, context_query))
            package = open_work(args.workspace, context_query, caller)
            sys.stdout.buffer.write(package.output)
            sys.stdout.buffer.flush()
            return 0
        elif args.command == "handoff":
            if args.handoff_command == "schema":
                output = json.dumps(Handoff.model_json_schema(), indent=2)
            elif args.handoff_command == "list":
                output = json.dumps(
                    [item.model_dump(mode="json") for item in read_handoffs(args.path)], indent=2
                )
            else:
                from_stdin = args.source == "-"
                if from_stdin:
                    content = sys.stdin.buffer.read(MAX_HANDOFF_BYTES + 1)
                    source_ref = "stdin"
                else:
                    source = Path(args.source).expanduser().resolve()
                    with source.open("rb") as stream:
                        content = stream.read(MAX_HANDOFF_BYTES + 1)
                    source_ref = source.as_posix()
                request = handoff_request(
                    content, source_ref=source_ref, expected_revision=args.expected_revision
                )
                caller = confirm_on_console(
                    prepare_authorization(args.path, request), separate_terminal=from_stdin
                )
                output = apply_mutation(args.path, request, caller).model_dump_json(indent=2)
        elif args.command == "mutate":
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
    except IncompleteIntakeError as error:
        print(
            json.dumps(
                dict(
                    status="intake_incomplete",
                    stage=error.stage,
                    progress=error.progress.model_dump(mode="json"),
                    unregistered_bytes_possible=error.unregistered_bytes_possible,
                    error=str(error),
                ),
                indent=2,
            )
        )
        return 2
    except IncompleteFirstUseError as error:
        print(
            json.dumps(
                dict(
                    status="setup_incomplete",
                    stage=error.stage,
                    completed=[receipt.model_dump(mode="json") for receipt in error.completed],
                    error=str(error),
                ),
                indent=2,
            )
        )
        return 2
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
    except EntryError as error:
        print(f"zara: [{error.code}] {error}", file=sys.stderr)
        return 1
    except IntakeError as error:
        print(f"zara: [{error.code}] {error}", file=sys.stderr)
        return 1
    except FirstUseError as error:
        print(f"zara: [{error.code}] {error}", file=sys.stderr)
        return 1
    except (WorkspaceError, ValidationError, OSError) as error:
        print(f"zara: {error}", file=sys.stderr)
        return 1
    print(output)
    return 0
