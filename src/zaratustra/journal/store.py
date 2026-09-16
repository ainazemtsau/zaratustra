"""Revision snapshots reuse the existing Core material/audit transaction."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from zaratustra.core import (
    Process,
    ProcessMaterial,
    ProcessMaterialQuery,
    ProcessMaterialRequest,
    ProcessMaterialSubmission,
    ProcessProjectionRebuildError,
    ProcessStateQuery,
    authorize_local,
    prepare_authorization,
    read_process_material,
    read_process_state,
    read_records,
    save_process_material,
)

from .types import (
    DEFAULT_REGISTRY,
    MAX_CONTENT,
    MEDIA_TYPE,
    Change,
    Document,
    JournalError,
    Reference,
    Registry,
    Revision,
    Scope,
    canonical,
)


class Store:
    """One explicitly allowed owner scope. A snapshot never follows foreign links."""

    def __init__(
        self, path: Path, scope: Scope, source_ref: str, registry: Registry = DEFAULT_REGISTRY
    ) -> None:
        if not source_ref.strip():
            raise JournalError("missing_source", "A live host source is required")
        self.path, self.scope, self.source_ref, self.registry = path, scope, source_ref, registry
        snapshot = read_records(path)
        processes = [r for r in snapshot.records if isinstance(r, Process)]
        if len(processes) != 1 or (scope.kind == "process" and processes[0].id != scope.id):
            raise JournalError("identity_mismatch", "Scope does not identify this Process")
        self.query = ProcessStateQuery(
            workspace_id=snapshot.workspace_id,
            process_id=processes[0].id,
            expected_revision=snapshot.state_revision,
        )
        state = read_process_state(path, self.query, self.permission(self.query))
        self.materials = {m.id: m for m in state.materials}
        self.records: dict[UUID, list[Revision]] = {}
        self.operations: dict[UUID, Revision] = {}
        for material in state.materials:
            if material.media_type == MEDIA_TYPE:
                if material.content_size > 16_000_000:
                    raise JournalError("invalid_record", "Record envelope exceeds size limit")
                record = Revision.model_validate_json(self.material_bytes(material.id))
                if record.scope != scope or record.operation_id != material.id:
                    raise JournalError("invalid_record", "Record owner or operation differs")
                history = self.records.setdefault(record.id, [])
                if not history and record.revision == 2 and record.id in self.materials:
                    history.append(self.legacy(record.id))
                previous = history[-1] if history else None
                if (
                    record.revision != len(history) + 1
                    or record.previous != (previous.reference() if previous else None)
                    or (
                        previous
                        and (record.type_name, record.schema_version, record.payload_schema)
                        != (previous.type_name, previous.schema_version, previous.payload_schema)
                    )
                ):
                    raise JournalError("invalid_record", "Broken revision lineage")
                if record.operation_id in self.operations:
                    raise JournalError("invalid_record", "Repeated operation")
                history.append(record)
                self.operations[record.operation_id] = record

    def permission(self, request: Any) -> Any:
        return authorize_local(
            prepare_authorization(self.path, request),
            channel="local-chat",
            actor="Zaratustra journal",
            source_ref=self.source_ref,
        )

    def material_bytes(self, identity: UUID) -> bytes:
        query = ProcessMaterialQuery(**self.query.model_dump(), material_id=identity)
        return read_process_material(self.path, query, self.permission(query)).content

    def legacy(self, identity: UUID) -> Revision:
        material = self.materials.get(identity)
        if material is None or material.media_type == MEDIA_TYPE:
            raise JournalError("not_found", "No such saved document")
        if material.content_size > MAX_CONTENT:
            raise JournalError("document_too_large", "Read this source through material.read")
        content = self.material_bytes(identity)
        try:
            document = Document(media_type=material.media_type, text=content.decode("utf-8"))
        except UnicodeDecodeError:
            document = Document(
                media_type=material.media_type, base64=base64.b64encode(content).decode("ascii")
            )
        return Revision(
            id=identity,
            revision=1,
            scope=self.scope,
            type_name="document",
            schema_version=1,
            payload_schema=Document.model_json_schema(),
            type_source="installed: zaratustra.journal",
            title=material.title,
            payload=document.model_dump(mode="json"),
            state="active",
            action="create",
            reason="Original immutable material; logical document revision 1",
            recorded_at=material.created_at,
            source_ref=f"core-material-operation:{material.operation_id}",
            operation_id=material.operation_id,
            fingerprint=material.content_sha256,
        )

    def get(self, identity: UUID, revision: int | None = None) -> Revision:
        history = self.records.get(identity)
        if history is None:
            result = self.legacy(identity)
            if revision not in (None, 1):
                raise JournalError("not_found", "No such document revision")
            return result
        if revision is not None and not 1 <= revision <= len(history):
            raise JournalError("not_found", "No such record revision")
        return history[-1] if revision is None else history[revision - 1]

    def history(self, identity: UUID) -> list[Revision]:
        return self.records.get(identity) or [self.legacy(identity)]

    def write(self, change: Change) -> dict[str, Any]:
        if self.scope.kind == "home" and not change.authority_source:
            raise JournalError("explicit_sharing_required", "Shared writes need owner authority")
        prior = self.operations.get(change.operation_id)
        if prior is not None:
            if prior.fingerprint != change.fingerprint():
                raise JournalError(
                    "operation_conflict", "Operation id already has different intent"
                )
            return {"record": prior.model_dump(mode="json"), "replayed": True}
        if change.operation_id in self.materials:
            raise JournalError("operation_conflict", "Operation id already belongs to a material")
        old = None
        if change.action == "create":
            if (
                change.expected_revision is not None
                or change.type_name is None
                or change.title is None
                or change.payload is None
            ):
                raise JournalError(
                    "invalid_create", "Create needs type, title, payload; no old revision"
                )
            if change.record_id in self.records or change.record_id in self.materials:
                raise JournalError("record_conflict", "Identity already belongs to a saved record")
            spec = self.registry.get(change.type_name, change.schema_version)
            state = spec.initial_state
        else:
            if change.record_id is None or change.expected_revision is None:
                raise JournalError(
                    "missing_revision", "Read the record; supply id and its revision"
                )
            old = self.get(change.record_id)
            if old.revision != change.expected_revision:
                raise JournalError(
                    "revision_conflict", "Record changed; read before choosing again"
                )
            if (
                change.type_name not in (None, old.type_name)
                or change.schema_version != old.schema_version
            ):
                raise JournalError(
                    "type_conflict", "Revision cannot silently change type or schema"
                )
            spec = self.registry.get(old.type_name, old.schema_version)
            if spec.schema() != old.payload_schema:
                raise JournalError("schema_conflict", "Installed schema differs from saved version")
            state = spec.transition(old.state, change.action)
        if change.action not in spec.operations:
            raise JournalError("unsupported_operation", "Type does not support this operation")
        if change.action in ("adopt", "replace", "revoke") and not change.authority_source:
            raise JournalError("missing_authority", "Give the actual available owner instruction")
        if change.action in ("adopt", "revoke") and any(
            value is not None for value in (change.payload, change.title, change.links)
        ):
            raise JournalError("changed_acceptance", "Adopt/revoke binds exactly the read revision")
        if change.action in ("create", "revise", "replace") and change.payload is None:
            raise JournalError("missing_payload", "Supply the complete intended payload")
        payload = spec.validate(
            change.payload if change.payload is not None else old.payload if old else {}
        )
        links = list(change.links if change.links is not None else old.links if old else ())
        for reference in spec.references(payload):
            if reference not in links:
                links.append(reference)
        if len(links) > 32:
            raise JournalError(
                "too_many_links", "At most 32 explicit and typed links are supported"
            )
        for link in links:
            resolve([self], link)
        result = Revision(
            id=old.id if old else change.record_id or change.operation_id,
            revision=old.revision + 1 if old else 1,
            scope=self.scope,
            type_name=spec.name,
            schema_version=spec.version,
            payload_schema=spec.schema(),
            type_source=spec.source,
            title=change.title or (old.title if old else ""),
            payload=payload,
            links=tuple(links),
            state=state,
            action=change.action,
            reason=change.reason,
            authority_source=change.authority_source,
            previous=old.reference() if old else None,
            recorded_at=datetime.now(UTC),
            source_ref=self.source_ref,
            operation_id=change.operation_id,
            fingerprint=change.fingerprint(),
        )
        content = canonical(result.model_dump(mode="json"))
        if len(content) > 16_000_000:
            raise JournalError("record_too_large", "Record envelope exceeds size limit")
        request = ProcessMaterialRequest(
            **self.query.model_dump(),
            operation_id=change.operation_id,
            provenance=f"zaratustra-journal:{change.operation_id}",
            material=ProcessMaterialSubmission(
                material_id=change.operation_id,
                title=result.title,
                media_type=MEDIA_TYPE,
                content_sha256=hashlib.sha256(content).hexdigest(),
                content_size=len(content),
            ),
        )
        try:
            receipt = save_process_material(
                self.path, request, self.permission(request), content=content
            )
        except ProcessProjectionRebuildError as error:
            return {
                "record": result.model_dump(mode="json"),
                "committed": True,
                "projection_warning": str(error),
                "receipt": error.receipt.model_dump(mode="json"),
            }
        return {
            "record": result.model_dump(mode="json"),
            "replayed": False,
            "receipt": receipt.model_dump(mode="json"),
        }

    def current(self) -> list[Revision]:
        return [history[-1] for history in self.records.values()]


def header(record: Revision) -> dict[str, Any]:
    result = {
        key: value
        for key, value in record.model_dump(mode="json").items()
        if key not in ("payload", "payload_schema")
    }
    truncated = []
    for name in ("reason", "authority_source", "source_ref", "type_source"):
        value = result.get(name)
        if isinstance(value, str) and len(value) > 500:
            result[name] = value[:500]
            truncated.append(name)
    if truncated:
        result["truncated_fields"] = truncated
    return result


def search(
    stores: list[Store],
    query: str,
    *,
    type_name: str | None = None,
    state: str | None = None,
    linked_to: Reference | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """FTS5 literal prefix terms, OR recall; agent must open and assess sources."""
    if not 1 <= limit <= 100 or offset < 0 or len(query) > 128:
        raise JournalError("invalid_query", "Bounded query/page required")
    records = [
        r
        for store in stores
        for r in store.current()
        if (type_name is None or r.type_name == type_name)
        and (state is None or r.state == state)
        and (linked_to is None or linked_to in r.links)
    ]
    terms = [part for part in "".join(c if c.isalnum() else " " for c in query).split() if part]
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute(
            "CREATE VIRTUAL TABLE search USING fts5(title, body, tokenize='unicode61')"
        )
        for index, record in enumerate(records):
            # Binary content is not indexed as base64; scope filtering happened before this point.
            payload = {k: v for k, v in record.payload.items() if k != "base64"}
            connection.execute(
                "INSERT INTO search(rowid, title, body) VALUES (?, ?, ?)",
                (index + 1, record.title, json.dumps(payload, ensure_ascii=False)),
            )
        if terms:
            match = " OR ".join('"' + term + '"*' for term in terms)
            rows = connection.execute(
                "SELECT rowid, snippet(search, 1, '[', ']', '…', 24) FROM search "
                "WHERE search MATCH ? ORDER BY rank, rowid LIMIT ? OFFSET ?",
                (match, limit, offset),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT rowid, substr(body, 1, 320) FROM search "
                "ORDER BY rowid DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
    return {
        "matches": [header(records[row[0] - 1]) | {"snippet": row[1]} for row in rows],
        "query": query,
        "method": "FTS5 unicode61, literal prefix terms OR",
        "limit": limit,
        "offset": offset,
        "limitation": "No Russian morphology or semantic guarantee. "
        "No match is not proof of absence.",
    }


def resolve(stores: list[Store], reference: Reference) -> dict[str, Any]:
    store = next((s for s in stores if s.scope == reference.scope), None)
    if store is None:
        return {
            "status": "scope_unavailable",
            "reference": reference.model_dump(mode="json"),
            "detail": "Source is not included in the current selected context",
        }
    if reference.kind == "record":
        return {
            "status": "available",
            "record": store.get(reference.id, reference.revision).model_dump(mode="json"),
        }
    material: ProcessMaterial | None = store.materials.get(reference.id)
    if material is None or material.revision != reference.revision:
        raise JournalError("not_found", "No such exact material version")
    return {
        "status": "available",
        "material": material.model_dump(mode="json"),
        "base64": base64.b64encode(store.material_bytes(material.id)).decode("ascii"),
    }
