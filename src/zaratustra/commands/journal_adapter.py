"""The same scoped journal operations for Pi and other trusted local hosts."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
from uuid import UUID

from zaratustra import home
from zaratustra.journal import (
    DEFAULT_REGISTRY,
    Change,
    JournalError,
    Revision,
    Scope,
    Store,
    header,
    resolve,
    search,
    shared_store,
)
from zaratustra.process_skills import SKILL_TYPE, Skill

from . import Command, Context, _selected, required


def _page(record: dict[str, Any], command: Command) -> dict[str, Any]:
    """Payload pages never silently truncate; callers can request the next page."""
    import json

    payload = json.dumps(record.pop("payload"), ensure_ascii=False)
    end = command.content_offset + command.content_limit
    record.pop("payload_schema", None)
    return {
        "record": record,
        "payload_json": payload[command.content_offset : end],
        "offset_unit": "characters",
        "total": len(payload),
        "next_offset": end if end < len(payload) else None,
    }


def _source_page(result: dict[str, Any], command: Command) -> dict[str, Any]:
    if "record" in result:
        return {"status": result["status"], **_page(result["record"], command)}
    if "base64" not in result:
        return result
    raw = base64.b64decode(result.pop("base64"), validate=True)
    end = command.content_offset + command.content_limit
    try:
        text = raw.decode("utf-8")
        result.update(
            text=text[command.content_offset : end],
            offset_unit="characters",
            total=len(text),
            next_offset=end if end < len(text) else None,
        )
    except UnicodeDecodeError:
        result.update(
            base64=base64.b64encode(raw[command.content_offset : end]).decode("ascii"),
            offset_unit="bytes",
            total=len(raw),
            next_offset=end if end < len(raw) else None,
        )
    return result


def execute_journal(
    context: Context,
    command: Command,
    *,
    source_ref: str,
    operation_id: UUID,
    guarded_revision: int | None = None,
) -> dict[str, Any]:
    action = command.action
    if action == "type.list":
        return {"types": DEFAULT_REGISTRY.describe()}
    if action == "export.read":
        from zaratustra.journal import read_export

        result = read_export(
            Path(required(command.path, "export path")),
            offset=command.offset,
            limit=command.limit,
            reference=command.reference,
        )
        return _source_page(result, command)
    writing = action in (
        "record.create",
        "record.revise",
        "record.adopt",
        "record.replace",
        "record.revoke",
    )
    if writing and command.scope == "home" and not command.authority_source:
        raise JournalError(
            "explicit_sharing_required", "Cite the owner's explicit shared instruction"
        )
    home_path = Path(context.home)
    home_id = UUID(home.read_home(home_path)["id"])
    stores: list[Store] = []
    if command.scope == "process":
        workspace, source = _selected(context, command.process)
        stores.append(Store(workspace, Scope(kind="process", id=UUID(source["id"])), source_ref))
        if (
            writing
            and command.process is None
            and guarded_revision is not None
            and stores[0].query.expected_revision != guarded_revision
        ):
            raise JournalError("context_changed", "Process changed during command preparation")
    if command.scope == "home" or command.include_shared:
        shared = shared_store(
            home_path, home_id, source_ref, create=writing and command.scope == "home"
        )
        if shared is not None:
            stores.append(shared)
    if action == "record.search":
        return search(
            stores,
            command.query,
            type_name=command.type_name,
            state=command.state,
            linked_to=command.reference,
            limit=command.limit,
            offset=command.offset,
        )
    if action == "source.read":
        if command.reference is None:
            raise JournalError("missing_reference", "Supply a version-pinned source reference")
        result = resolve(stores, command.reference)
        return _source_page(result, command)
    if not stores:
        raise JournalError("not_found", "The shared area has no records")
    store = stores[0]
    if writing:
        if action == "record.create" and command.record is not None:
            raise JournalError("invalid_create", "New record identity comes from its operation id")
        old = store.get(command.record) if action != "record.create" and command.record else None
        type_name = old.type_name if old else required(command.type_name, "record type")
        spec = DEFAULT_REGISTRY.get(
            type_name, old.schema_version if old else command.schema_version
        )
        if spec.managed_by:
            raise JournalError("managed_type", "Use " + spec.managed_by)
        payload = spec.validate(command.payload) if command.payload is not None else None
        if type_name == SKILL_TYPE and payload is not None:
            skill = Skill.model_validate(payload)
            if skill.derived_from:
                origin = resolve(stores, skill.derived_from)
                if skill.derived_from.kind != "record" or (
                    origin["status"] == "available" and origin["record"]["type_name"] != SKILL_TYPE
                ):
                    raise JournalError(
                        "invalid_origin", "Derived skill needs an exact skill source"
                    )
        change = Change.model_validate(
            {
                "operation_id": operation_id,
                "action": action.split(".")[1],
                "record_id": command.record,
                "expected_revision": command.expected_revision,
                "type_name": command.type_name,
                "schema_version": command.schema_version,
                "title": command.title,
                "payload": command.payload,
                "links": command.links,
                "reason": required(command.reason, "reason"),
                "authority_source": command.authority_source,
            }
        )
        for link in change.links or ():
            resolve(stores, link)  # Accessible sources must actually exist at the pinned version.
        for link in spec.references(payload or {}):
            resolve(stores, link)
        result = store.write(change)
        result["record"] = header(store_record := Revision.model_validate(result["record"]))
        result["reference"] = store_record.reference().model_dump(mode="json")
        return result
    if action == "records.export":
        from zaratustra.journal import export_records

        # An explicit list is required; links never select another Process for the caller.
        return export_records(
            stores if command.export_shared else [store],
            store,
            command.records,
            Path(required(command.path, "export destination")),
        )
    if command.record is None:
        raise JournalError("missing_record", "Select a record found through search")
    if action == "record.history":
        history = store.history(command.record)
        return {
            "history": [
                header(r) for r in history[command.offset : command.offset + command.limit]
            ],
            "total": len(history),
        }
    return _page(store.get(command.record, command.revision).model_dump(mode="json"), command)
