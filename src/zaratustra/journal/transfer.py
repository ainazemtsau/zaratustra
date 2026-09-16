"""Bounded standalone ZIP packages; no extraction, live import or schema execution."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from .store import Store, header, resolve
from .types import JournalError, Reference, Revision, canonical

MAX_PACKAGE = 64_000_000
MAX_ENTRIES = 1000


def key(reference: Reference) -> str:
    scope = reference.scope
    return f"{scope.kind}/{scope.id}/{reference.kind}/{reference.id}/{reference.revision}.json"


def export_records(
    stores: list[Store], owner: Store, identities: tuple[UUID, ...], destination: Path
) -> dict[str, Any]:
    if not identities or len(identities) > 100:
        raise JournalError("invalid_selection", "Select 1..100 records explicitly")
    pending = [r.reference() for identity in identities for r in owner.history(identity)]
    selected = list(pending)
    entries: dict[str, bytes] = {}
    schemas: dict[tuple[str, int], dict[str, Any]] = {}
    missing: dict[str, dict[str, Any]] = {}
    links: list[dict[str, Any]] = []
    total = 0
    while pending:
        reference = pending.pop(0)
        name = key(reference)
        if name in entries or name in missing:
            continue
        if len(entries) + len(missing) >= MAX_ENTRIES:
            raise JournalError("export_too_large", "Reference closure exceeds 1000 entries")
        try:
            value = resolve(stores, reference)
        except JournalError as error:
            if error.code != "not_found":
                raise
            value = {"status": "missing", "detail": str(error)}
        if value["status"] != "available":
            missing[name] = {
                "reference": reference.model_dump(mode="json"),
                "status": value["status"],
                "detail": value["detail"],
            }
            continue
        if "record" in value:
            record = Revision.model_validate(value["record"])
            schema_key = (record.type_name, record.schema_version)
            schema = {
                "type": record.type_name,
                "version": record.schema_version,
                "schema": record.payload_schema,
                "source": record.type_source,
            }
            if schema_key in schemas and schemas[schema_key] != schema:
                raise JournalError("schema_conflict", "Same type/version has differing schemas")
            schemas[schema_key] = schema
            for target in (*record.links, *((record.previous,) if record.previous else ())):
                links.append(
                    {
                        "from": reference.model_dump(mode="json"),
                        "to": target.model_dump(mode="json"),
                    }
                )
                pending.append(target)
        content = canonical(value)
        total += len(content)
        if total > MAX_PACKAGE:
            raise JournalError("export_too_large", "Package exceeds 64 MB")
        entries[name] = content
    manifest = {
        "format": "zaratustra-journal-export-v1",
        "selected": [ref.model_dump(mode="json") for ref in selected],
        "scopes": [store.scope.model_dump(mode="json") for store in stores],
        "schemas": list(schemas.values()),
        "links": links,
        "missing": list(missing.values()),
        "entries": [
            {"name": name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            for name, content in entries.items()
        ],
    }
    manifest_bytes = canonical(manifest)
    if total + len(manifest_bytes) > MAX_PACKAGE:
        raise JournalError("export_too_large", "Manifest and content exceed 64 MB")
    # Exclusive create never overwrites a user's package. All reads complete before creating it.
    with destination.open("xb") as output:
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as package:
            package.writestr("manifest.json", manifest_bytes)
            for name, content in entries.items():
                package.writestr(name, content)
    return {
        "path": destination.resolve().as_posix(),
        "entry_count": len(entries),
        "selected_count": len(identities),
        "missing": list(missing.values()),
        "scopes": manifest["scopes"],
    }


def load_export(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Validate every entry before returning any content. Schema descriptors are inert data."""
    try:
        with ZipFile(path) as package:
            infos = package.infolist()
            names = [info.filename for info in infos]
            if (
                len(infos) > MAX_ENTRIES + 1
                or len(set(names)) != len(names)
                or sum(info.file_size for info in infos) > MAX_PACKAGE
            ):
                raise ValueError("Package exceeds bounds or has duplicate entries")
            manifest = json.loads(package.read("manifest.json"))
            if manifest["format"] != "zaratustra-journal-export-v1":
                raise ValueError("Unsupported export format")
            expected = [entry["name"] for entry in manifest["entries"]]
            if len(expected) != len(set(expected)) or set(names) != {*expected, "manifest.json"}:
                raise ValueError("Manifest inventory differs")
            result: dict[str, dict[str, Any]] = {}
            records: dict[str, Revision] = {}
            for entry in manifest["entries"]:
                name = entry["name"]
                content = package.read(name)
                if (
                    len(content) != entry["size"]
                    or hashlib.sha256(content).hexdigest() != entry["sha256"]
                ):
                    raise ValueError("Export content hash differs")
                value = json.loads(content)
                if value["status"] != "available":
                    raise ValueError("Invalid entry status")
                if "record" in value:
                    record = Revision.model_validate(value["record"])
                    if key(record.reference()) != name:
                        raise ValueError("Record identity differs from entry name")
                    records[name] = record
                elif "material" in value:
                    raw = base64.b64decode(value["base64"], validate=True)
                    material = value["material"]
                    if (
                        len(raw) != material["content_size"]
                        or hashlib.sha256(raw).hexdigest() != material["content_sha256"]
                    ):
                        raise ValueError("Material bytes differ from saved identity")
                    # Scope is included in the canonical entry name and manifest references.
                    parts = name.split("/")
                    if (
                        len(parts) != 5
                        or parts[2] != "material"
                        or parts[3] != material["id"]
                        or parts[4] != f"{material['revision']}.json"
                        or (parts[0] == "process" and parts[1] != material["process_id"])
                    ):
                        raise ValueError("Material identity differs from entry name")
                else:
                    raise ValueError("Unknown entry kind")
                result[name] = value
            missing = {key(Reference.model_validate(m["reference"])) for m in manifest["missing"]}
            available = set(result)
            if available & missing:
                raise ValueError("Source both included and missing")
            schemas = {(s["type"], s["version"]): s for s in manifest["schemas"]}
            actual_links = []
            for record in records.values():
                schema = schemas[record.type_name, record.schema_version]
                if (
                    schema["schema"] != record.payload_schema
                    or schema["source"] != record.type_source
                ):
                    raise ValueError("Schema inventory differs from revision")
                for target in (*record.links, *((record.previous,) if record.previous else ())):
                    if key(target) not in available | missing:
                        raise ValueError("Source is neither included nor declared missing")
                    actual_links.append(
                        {
                            "from": record.reference().model_dump(mode="json"),
                            "to": target.model_dump(mode="json"),
                        }
                    )
            if sorted(map(canonical, actual_links)) != sorted(map(canonical, manifest["links"])):
                raise ValueError("Link inventory differs from saved records")
            for ref in manifest["selected"]:
                if key(Reference.model_validate(ref)) not in available:
                    raise ValueError("Selected record is missing")
            return manifest, result
    except (BadZipFile, KeyError, TypeError, ValueError, RuntimeError) as error:
        raise JournalError("invalid_export", str(error)) from error


def read_export(
    path: Path, *, offset: int = 0, limit: int = 20, reference: Reference | None = None
) -> dict[str, Any]:
    if not 1 <= limit <= 100 or offset < 0:
        raise JournalError("invalid_page", "Limit must be 1..100 and offset nonnegative")
    manifest, values = load_export(path)
    if reference is not None:
        value = values.get(key(reference))
        if value is not None:
            return value
        omitted = next(
            (m for m in manifest["missing"] if m["reference"] == reference.model_dump(mode="json")),
            None,
        )
        return omitted or {
            "status": "not_in_package",
            "reference": reference.model_dump(mode="json"),
        }
    records = [
        header(Revision.model_validate(value["record"]))
        for value in values.values()
        if "record" in value
    ]
    inventories = {
        "records": records,
        "schemas": manifest["schemas"],
        "missing": manifest["missing"],
        "links": manifest["links"],
    }
    end = offset + limit
    return {
        "format": manifest["format"],
        **{name: rows[offset:end] for name, rows in inventories.items()},
        "counts": {name: len(rows) for name, rows in inventories.items()},
        "offset": offset,
        "next_offset": end if any(end < len(rows) for rows in inventories.values()) else None,
        "record_revision_count": len(records),
        "entry_count": len(values),
        "scopes": manifest["scopes"],
    }
