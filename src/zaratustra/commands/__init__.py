"""Shared agent-facing operations over Home and Process, without model heuristics."""

from __future__ import annotations

import base64
import hashlib
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from zaratustra import home
from zaratustra.core import (
    InitialProcess,
    Process,
    ProcessMaterialQuery,
    ProcessMaterialRequest,
    ProcessMaterialSubmission,
    ProcessStateQuery,
    WorkspaceError,
    authorize_local,
    create_process,
    init_workspace,
    migrate_workspace,
    prepare_authorization,
    read_process_material,
    read_process_state,
    read_workspace,
    save_process_material,
)
from zaratustra.entry import EntryCatalog, source_path, transfer_catalog
from zaratustra.journal import MEDIA_TYPE, Reference

Name = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=128)
]
CONFIG_NAME = ".zara-context.json"


class Context(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[1] = 1
    home: str
    workspace: str | None = None
    process_id: UUID | None = None


class Command(BaseModel):
    """Fixed operations; record types are independently registered schemas."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    action: Literal[
        "home.read",
        "process.list",
        "process.create",
        "process.register",
        "process.open",
        "process.relocate",
        "process.aliases",
        "group.create",
        "group.list",
        "group.membership",
        "relation.set",
        "relation.delete",
        "relation.list",
        "material.save",
        "material.read",
        "catalog.import",
        "workspace.upgrade",
        "type.list",
        "record.create",
        "record.revise",
        "record.adopt",
        "record.replace",
        "record.revoke",
        "record.read",
        "record.history",
        "record.search",
        "source.read",
        "records.export",
        "export.read",
    ]
    process: Name | None = None
    title: Name | None = None
    purpose: str | None = None
    path: str | None = None
    aliases: Annotated[tuple[Name, ...], Field(max_length=32)] = ()
    group: Name | None = None
    target: Name | None = None
    relation_type: Name | None = None
    relation_id: UUID | None = None
    included: bool = True
    query: Annotated[str, Field(max_length=128)] = ""
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 20
    offset: Annotated[int, Field(strict=True, ge=0)] = 0
    text: str | None = None
    media_type: Name = "text/plain"
    material: Name | None = None
    content_offset: Annotated[int, Field(strict=True, ge=0)] = 0
    content_limit: Annotated[int, Field(strict=True, ge=1, le=100_000)] = 20_000
    operation_id: UUID | None = None
    expected_revision: Annotated[int, Field(strict=True, ge=1)] | None = None
    scope: Literal["process", "home"] = "process"
    include_shared: bool = True
    export_shared: bool = False
    type_name: Name | None = None
    schema_version: Annotated[int, Field(strict=True, ge=1)] = 1
    record: UUID | None = None
    records: Annotated[tuple[UUID, ...], Field(max_length=100)] = ()
    revision: Annotated[int, Field(strict=True, ge=1)] | None = None
    payload: dict[str, Any] | None = None
    links: Annotated[tuple[Reference, ...], Field(max_length=32)] | None = None
    reference: Reference | None = None
    state: Name | None = None
    reason: str | None = None
    authority_source: str | None = None


def required(value: str | None, name: str) -> str:
    if value is None or not value.strip():
        raise home.HomeError("missing_field", f"Explicit {name} is required")
    return value


def read_context(directory: Path) -> Context:
    selected = directory.resolve() / CONFIG_NAME
    if not selected.is_file():
        raise home.HomeError("home_not_configured", "Set up Home in this chosen working directory")
    context = Context.model_validate_json(selected.read_bytes())
    if not Path(context.home).is_absolute():
        raise home.HomeError("invalid_context", "Configured Home path must be absolute")
    if context.workspace is not None and not Path(context.workspace).is_absolute():
        raise home.HomeError("invalid_context", "Configured workspace path must be absolute")
    home.read_home(Path(context.home))
    if (context.workspace is None) != (context.process_id is None):
        raise home.HomeError(
            "invalid_context", "Direct context needs both workspace and Process identity"
        )
    return context


def write_context(directory: Path, context: Context) -> Path:
    """Explicit setup only; never silently replace a prior context selection."""
    path = directory.resolve() / CONFIG_NAME
    if path.exists():
        if Context.model_validate_json(path.read_bytes()) != context:
            raise home.HomeError(
                "context_conflict", "A different context is already configured here"
            )
        return path
    with path.open("x", encoding="utf-8", newline="") as stream:
        stream.write(context.model_dump_json(indent=2) + chr(10))
    return path


def _selected(context: Context, selector: str | None) -> tuple[Path, dict[str, Any]]:
    if selector is not None:
        row = home.resolve_process(Path(context.home), selector)
        if row["availability"] != "available":
            raise home.HomeError(
                "source_unavailable", f"Process is {row['availability']}: {row['location']}"
            )
        return Path(row["location"]), row["current"]
    if context.workspace is None:
        raise home.HomeError("process_not_selected", "Choose a Process by name")
    workspace = Path(context.workspace)
    source = home.inspect_source(workspace)
    if source["id"] != str(context.process_id):
        raise home.HomeError("identity_mismatch", "Direct workspace contains a different Process")
    return workspace, source


def _permission(path: Path, request: Any, source_ref: str) -> Any:
    return authorize_local(
        prepare_authorization(path, request),
        channel="local-chat",
        actor="Zaratustra local agent command",
        source_ref=source_ref,
    )


def upgrade_workspace(workspace: Path) -> dict[str, Any]:
    """Back up an existing database before the explicit schema transition."""
    info = read_workspace(workspace)
    if info.schema_version == 10:
        return {"schema": 10, "workspace_id": str(info.workspace_id), "changed": False}
    backup = info.database.with_name(f"before-schema10-{uuid4()}.sqlite3")
    with closing(sqlite3.connect(info.database.as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(backup)) as destination:
            source.backup(destination)
    upgraded = migrate_workspace(workspace, target_version=10)
    return {
        "schema": 10,
        "workspace_id": str(upgraded.workspace_id),
        "backup": backup.as_posix(),
        "changed": True,
    }


def _create(context: Context, command: Command, operation_id: UUID) -> dict[str, Any]:
    title = required(command.title, "title")
    purpose = required(command.purpose, "purpose")
    registry = Path(context.home)
    workspace = (
        Path(command.path).expanduser().resolve()
        if command.path
        else (registry / "processes" / str(operation_id))
    )
    initial = InitialProcess(title=title, purpose=purpose, operation_id=operation_id)
    home.reserve_creation(
        registry,
        {
            "title": initial.title,
            "purpose": initial.purpose,
            "workspace": workspace.as_posix(),
            "aliases": command.aliases,
        },
        operation_id=operation_id,
    )
    workspace.mkdir(parents=True, exist_ok=True)
    info = init_workspace(workspace)
    if info.schema_version != 10:
        if info.schema_version == 1:
            migrate_workspace(workspace, target_version=10)
        else:
            raise home.HomeError(
                "upgrade_required", "Explicitly upgrade the existing workspace first"
            )
    snapshot = create_process(workspace, initial)
    process = next(row for row in snapshot.records if isinstance(row, Process))
    try:
        row = home.register_process(
            registry,
            workspace,
            operation_id=uuid5(operation_id, "registration"),
            aliases=command.aliases,
        )
    except (WorkspaceError, OSError) as error:
        return {
            "status": "registration_required",
            "process_id": str(process.id),
            "workspace": workspace.as_posix(),
            "error": str(error),
            "recovery": "Use process.register with this workspace; do not create another Process",
        }
    return {"status": "created", "process": row, "operation_id": str(operation_id)}


def _import(context: Context, command: Command, operation_id: UUID) -> dict[str, Any]:
    catalog_path = Path(required(command.path, "catalog path")).expanduser().resolve()
    registry = Path(context.home)

    def prepare_import(catalog: EntryCatalog, digest: str) -> Callable[[], dict[str, Any]]:
        rows = []
        for entry in catalog.entries:
            workspace = source_path(catalog_path, entry)
            try:
                source = home.inspect_source(workspace)
            except (OSError, WorkspaceError):
                source = {
                    "id": str(entry.process_id),
                    "workspace_id": str(entry.workspace_id),
                    "location": workspace.as_posix(),
                }
            if (source["id"], source["workspace_id"]) != (
                str(entry.process_id),
                str(entry.workspace_id),
            ):
                raise home.HomeError("identity_mismatch", "Catalog source identity changed")
            rows.append(source | {"name": entry.designation, "aliases": entry.aliases})
        home.reserve_catalog_import(registry, catalog_path, digest, operation_id=operation_id)
        return lambda: home.import_registrations(
            registry, catalog_path, digest, rows, operation_id=uuid5(operation_id, "import")
        )

    return transfer_catalog(catalog_path, registry, prepare_import)


def execute(context: Context, command: Command, *, source_ref: str) -> dict[str, Any]:
    """Trusted local host invokes this only for the owner's current instruction.

    There is no model-supplied permission field. Host instructions distinguish an
    explicit command from discussion and require owner consent to shown creation.
    Core still binds authorization to the exact request, revision and workspace.
    """
    source_ref = required(source_ref, "live instruction source")
    registry = Path(context.home)
    home.read_home(registry)
    operation_id = command.operation_id or uuid4()
    action = command.action
    if action.startswith(("record.", "records.", "source.", "type.", "export.")):
        from .journal_adapter import execute_journal

        return execute_journal(context, command, source_ref=source_ref, operation_id=operation_id)
    if action == "home.read":
        return {"home": home.read_home(registry), "context": context.model_dump(mode="json")}
    if action == "process.list":
        return {
            "processes": home.list_processes(
                registry,
                query=command.query,
                group=command.group,
                limit=command.limit,
                offset=command.offset,
            )
        }
    if action == "process.create":
        return _create(context, command, operation_id)
    if action == "process.register":
        return {
            "process": home.register_process(
                registry,
                Path(required(command.path, "workspace path")),
                operation_id=operation_id,
                name=command.title,
                aliases=command.aliases,
            )
        }
    if action == "process.relocate":
        return {
            "process": home.relocate_process(
                registry,
                required(command.process, "process"),
                Path(required(command.path, "workspace path")),
                operation_id=operation_id,
            )
        }
    if action == "process.aliases":
        return home.set_aliases(
            registry,
            required(command.process, "process"),
            command.aliases,
            operation_id=operation_id,
        )
    if action == "group.create":
        return home.create_group(
            registry, required(command.group, "group"), operation_id=operation_id
        )
    if action == "group.list":
        return {"groups": home.list_groups(registry, limit=command.limit, offset=command.offset)}
    if action == "group.membership":
        return home.set_membership(
            registry,
            required(command.group, "group"),
            required(command.process, "process"),
            command.included,
            operation_id=operation_id,
        )
    if action == "relation.set":
        return home.set_relation(
            registry,
            required(command.process, "source process"),
            required(command.target, "target process"),
            required(command.relation_type, "relation type"),
            operation_id=operation_id,
            relation_id=command.relation_id,
        )
    if action == "relation.delete":
        if command.relation_id is None:
            raise home.HomeError("missing_field", "relation_id is required")
        return home.delete_relation(registry, command.relation_id, operation_id=operation_id)
    if action == "relation.list":
        return {
            "relations": home.list_relations(
                registry, command.process, limit=command.limit, offset=command.offset
            )
        }
    if action == "catalog.import":
        return _import(context, command, operation_id)
    if action == "workspace.upgrade":
        return upgrade_workspace(Path(required(command.path, "workspace path")))
    workspace, source = _selected(context, command.process)
    revision = command.expected_revision or source["revision"]
    query = ProcessStateQuery(
        workspace_id=UUID(source["workspace_id"]),
        process_id=UUID(source["id"]),
        expected_revision=revision,
    )
    state = read_process_state(workspace, query, _permission(workspace, query, source_ref))
    if action == "process.open":
        return {
            "process": state.process.model_dump(mode="json"),
            "revision": state.state_revision,
            "location": workspace.as_posix(),
            "current_work": state.current_work.model_dump(mode="json")
            if state.current_work
            else None,
            "materials": [
                row.model_dump(mode="json")
                for row in state.materials[command.offset : command.offset + command.limit]
            ],
            "material_count": len(state.materials),
        }
    if action == "material.save":
        if command.media_type == MEDIA_TYPE:
            raise home.HomeError("reserved_type", "Use registered record operations")
        if (command.text is None) == (command.path is None):
            raise home.HomeError(
                "invalid_content", "Supply exactly one of text or a selected file path"
            )
        content = (
            command.text.encode("utf-8")
            if command.text is not None
            else Path(required(command.path, "material file")).read_bytes()
        )
        request = ProcessMaterialRequest(
            operation_id=operation_id,
            workspace_id=query.workspace_id,
            process_id=query.process_id,
            expected_revision=revision,
            provenance=f"zaratustra-command:{operation_id}",
            material=ProcessMaterialSubmission(
                material_id=operation_id,
                title=required(command.title, "material title"),
                media_type=command.media_type,
                content_sha256=hashlib.sha256(content).hexdigest(),
                content_size=len(content),
            ),
        )
        receipt = save_process_material(
            workspace, request, _permission(workspace, request, source_ref), content=content
        )
        return {"receipt": receipt.model_dump(mode="json"), "material_id": str(operation_id)}
    selector = required(command.material, "material id or title")
    matches = [
        row
        for row in state.materials
        if str(row.id) == selector or row.title.casefold() == selector.casefold()
    ]
    if len(matches) != 1:
        raise home.HomeError(
            "ambiguous_material" if matches else "material_not_found",
            "Select an exact material",
            choices=tuple(row.model_dump(mode="json") for row in matches[:20]),
        )
    material_query = ProcessMaterialQuery(**query.model_dump(), material_id=matches[0].id)
    result = read_process_material(
        workspace, material_query, _permission(workspace, material_query, source_ref)
    )
    response: dict[str, Any] = {"material": result.material.model_dump(mode="json")}
    try:
        text = result.content.decode("utf-8")
        end = command.content_offset + command.content_limit
        response.update(
            text=text[command.content_offset : end],
            offset_unit="characters",
            total=len(text),
            next_offset=end if end < len(text) else None,
        )
    except UnicodeDecodeError:
        end = command.content_offset + command.content_limit
        response.update(
            base64=base64.b64encode(result.content[command.content_offset : end]).decode("ascii"),
            offset_unit="bytes",
            total=len(result.content),
            next_offset=end if end < len(result.content) else None,
        )
    return response
