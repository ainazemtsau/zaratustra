"""Select existing stores; all skill semantics stay in the common service."""

from pathlib import Path
from typing import Any
from uuid import UUID

from zaratustra import home
from zaratustra.journal import DEFAULT_REGISTRY, JournalError, Scope, Store, shared_store
from zaratustra.process_skills import Catalog, Skills

from . import Command, Context, _selected, required
from .registry import names


def service(
    context: Context, selector: str | None, source_ref: str
) -> tuple[Skills, dict[str, Any]]:
    workspace, source = _selected(context, selector)
    local = Store(workspace, Scope(kind="process", id=UUID(source["id"])), source_ref)
    stores = [local]
    home_path = Path(context.home)
    shared = shared_store(home_path, UUID(home.read_home(home_path)["id"]), source_ref)
    if shared is not None:
        stores.append(shared)
    catalog = Catalog(names(), DEFAULT_REGISTRY)
    return Skills(local, stores, catalog), source


def execute_skills(
    context: Context, command: Command, source_ref: str, operation_id: UUID
) -> dict[str, Any]:
    skills, source = service(context, command.process, source_ref)
    if command.action == "context.read":
        return skills.compile(source, command.loaded_slots)
    if command.action == "skill.catalog":
        return skills.available(command.offset, command.limit)
    slot = required(command.slot, "skill slot")
    if command.action == "skill.load":
        return skills.load(slot)
    if command.expected_configuration_revision is None:
        raise JournalError("missing_revision", "Read context for configuration revision")
    if command.action == "skill.bind" and command.reference is None:
        raise JournalError("missing_reference", "Choose an exact skill revision")
    return skills.change(
        slot=slot,
        reference=command.reference if command.action == "skill.bind" else None,
        settings=command.settings,
        expected=command.expected_configuration_revision,
        operation_id=operation_id,
        reason=required(command.reason, "reason"),
        authority_source=command.authority_source,
    )
