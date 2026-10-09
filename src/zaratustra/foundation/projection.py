"""Exact readable delivery snapshot over the existing domain store.

No schema change, shadow backend or write transaction. The read snapshot is
streamed to chosen files; final admission catches concurrent edits and revocation.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .knowledge import BODY_ADAPTER, _require_ref
from .models import KnowledgeRef, SourceState
from .operations import LocalAuthority, _authorize, _local_space
from .storage import FoundationError, canonical_json, space_connection

type ProjectionSection = Literal[
    "subject",
    "artifact",
    "knowledge",
    "method",
    "development",
    "setup",
    "plan",
    "binding",
    "decision",
]


class ProjectionRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    section: ProjectionSection
    record_id: UUID
    revision: int
    current_revision: int
    sha256: str


class ProjectionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    space_id: UUID
    state_revision: int
    refs: tuple[ProjectionRef, ...]
    files: dict[str, str]
    operational_refs: dict[str, str] = Field(default_factory=dict)
    complete: bool = True


# Each query yields one exact retained revision at a time. No full-store fetchall.
QUERIES: dict[ProjectionSection, str] = {
    "subject": (
        "SELECT r.kind,r.record_id,v.revision,r.current_revision,c.payload,c.sha256 "
        "FROM subject_records r JOIN subject_revisions v USING(record_id) "
        "JOIN subject_content c USING(record_id,revision) WHERE r.status!='deleted' "
        "ORDER BY r.kind,r.record_id,v.revision"
    ),
    "artifact": (
        "SELECT 'artifact',r.record_id,v.revision,r.current_revision,c.payload,c.sha256 "
        "FROM records r JOIN record_revisions v USING(record_id) "
        "JOIN managed_content c USING(record_id,revision) "
        "WHERE r.kind='artifact' AND r.status!='deleted' ORDER BY r.record_id,v.revision"
    ),
    "knowledge": (
        "SELECT r.kind,r.record_id,v.revision,r.current_revision,v.payload,v.sha256 "
        "FROM knowledge_records r JOIN knowledge_revisions v USING(record_id) "
        "WHERE r.status='active' AND v.payload IS NOT NULL "
        "ORDER BY r.kind,r.record_id,v.revision"
    ),
    "method": (
        "SELECT 'method',method_id,version,version,payload,checksum FROM method_versions "
        "WHERE status='active' AND payload IS NOT NULL ORDER BY method_id,version"
    ),
    "development": (
        "SELECT r.kind,r.record_id,v.revision,r.current_revision,v.payload,v.sha256 "
        "FROM development_records r JOIN development_revisions v USING(record_id) "
        "WHERE r.status='active' AND v.payload IS NOT NULL ORDER BY r.record_id,v.revision"
    ),
    "setup": (
        "SELECT 'setup',s.setup_id,r.revision,s.current_revision,r.payload,r.sha256 "
        "FROM activity_setups s JOIN activity_setup_revisions r USING(setup_id) "
        "WHERE s.status='active' AND r.payload IS NOT NULL ORDER BY s.setup_id,r.revision"
    ),
    "plan": (
        "SELECT 'plan',p.parent_id,p.revision,(SELECT MAX(q.revision) FROM work_plan_revisions q "
        "WHERE q.parent_id=p.parent_id),p.payload,NULL FROM work_plan_revisions p "
        "JOIN subject_records r ON r.record_id=p.parent_id WHERE r.status!='deleted' "
        "ORDER BY p.parent_id,p.revision"
    ),
    "binding": (
        "SELECT 'binding',binding_id,version,version,payload,checksum FROM binding_versions "
        "WHERE payload IS NOT NULL ORDER BY binding_id,version"
    ),
    "decision": (
        "SELECT 'decision',r.record_id,v.revision,r.current_revision,v.body_json,NULL "
        "FROM records r JOIN record_revisions v USING(record_id) "
        "WHERE r.kind='decision' AND r.status!='deleted' ORDER BY r.record_id,v.revision"
    ),
}


def _write_text(root: Path, name: str, text: str, files: dict[str, str]) -> list[str]:
    # Split at character boundaries; concatenating parts reproduces the full text.
    names = []
    for number, start in enumerate(range(0, max(1, len(text)), 24000), 1):
        suffix = "" if len(text) <= 24000 else f"-part-{number:04d}"
        relative = f"{name}{suffix}.md"
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        data = text[start : start + 24000].encode("utf-8")
        target.write_bytes(data)
        files[relative] = hashlib.sha256(data).hexdigest().upper()
        names.append(relative)
    return names


def export_workspace_projection(
    path: Path,
    authority: LocalAuthority,
    destination: Path,
) -> ProjectionReceipt:
    """Build in a new staging directory; the caller publishes it after validation."""
    if destination.exists():
        raise FoundationError("file_exists", "Projection staging directory must be new")
    files: dict[str, str] = {}
    refs: list[ProjectionRef] = []
    operational_refs: dict[str, str] = {}
    index = [
        "# Activity and memory catalog\n\n",
        "Core is authoritative. This is a versioned read-only snapshot; editing "
        "these files does not update Core. Git is not a full Core backup.\n\n",
    ]
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version != 14 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Workspace export needs active schema 14")
        _authorize(
            connection, actor=authority.actor, action="record.read", epoch=info.execution_epoch
        )
        _authorize(
            connection, actor=authority.actor, action="memory.transfer", epoch=info.execution_epoch
        )
        for section, query in QUERIES.items():
            for kind, identifier, revision, current, payload, checksum in connection.execute(query):
                record_id = UUID(identifier)
                _authorize(
                    connection,
                    actor=authority.actor,
                    action="record.read",
                    epoch=info.execution_epoch,
                    resource_type=kind if section == "subject" else "artifact",
                    resource_id=record_id,
                )
                raw = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
                digest = hashlib.sha256(raw).hexdigest().upper()
                checked_digest = (
                    hashlib.sha256(canonical_json(json.loads(raw)).encode()).hexdigest().upper()
                    if section in ("method", "binding")
                    else digest
                )
                if checksum is not None and checked_digest != checksum:
                    raise FoundationError("corrupt_content", "Projection basis digest differs")
                ref = ProjectionRef(
                    section=section,
                    record_id=record_id,
                    revision=revision,
                    current_revision=current,
                    sha256=digest,
                )
                refs.append(ref)
                stem = f"{kind}/{identifier}/{revision:06d}"
                title = f"{kind} {identifier}@{revision}"
                heading = (
                    f"# {title}\n\nCurrent revision at export: {current}\nSHA-256: {digest}\n\n"
                )
                text: str
                if section == "artifact":
                    provenance = [
                        dict(
                            zip(("relation", "record_id", "revision", "external"), row, strict=True)
                        )
                        for row in connection.execute(
                            "SELECT relation,source_record_id,source_revision,external_ref "
                            "FROM revision_provenance WHERE record_id=? AND revision=? "
                            "ORDER BY ordinal",
                            (identifier, revision),
                        )
                    ]
                    for item in provenance:
                        if item["record_id"]:
                            _require_ref(
                                connection,
                                KnowledgeRef(
                                    record_id=UUID(str(item["record_id"])),
                                    revision=int(str(item["revision"])),
                                ),
                                authority.actor,
                                info.execution_epoch,
                            )
                    heading += (
                        "Provenance:\n```json\n"
                        + json.dumps(provenance, ensure_ascii=False, indent=2)
                        + "\n```\n\n"
                    )
                    try:
                        text = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        text = (
                            "Binary original is retained in Core; text export contains its address."
                        )
                else:
                    data = json.loads(raw)
                    if section == "knowledge":
                        state = BODY_ADAPTER.validate_json(raw)
                        if isinstance(state, SourceState) and state.content is not None:
                            data.pop("content", None)
                            try:
                                original = state.content.decode("utf-8")
                            except UnicodeDecodeError:
                                original = (
                                    "Binary source is retained in Core (not a text original)."
                                )
                            data["original_files"] = _write_text(
                                destination, stem + "-original", original, files
                            )
                    text = "```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```\n"
                    label = data.get("title") or data.get("goal") or data.get("name")
                    if label and revision == current:
                        first_file = (
                            stem + ("-part-0001" if len(heading + text) > 24000 else "") + ".md"
                        )
                        index.append(
                            f"- **{kind}**: {str(label).replace(chr(10), ' ')} "
                            f"— [{identifier}@{revision}]({first_file})\n"
                        )
                _write_text(destination, stem, heading + text, files)
        # Execution addresses, accounting and resource history stay separate from Work status.
        for (work_id,) in connection.execute(
            "SELECT record_id FROM subject_records WHERE kind='work' AND status!='deleted'"
        ):
            sections = []
            for table, id_column in (
                ("execution_resource_revisions", "resource_id"),
                ("execution_attempts", "work_id"),
                ("execution_invocations", "work_id"),
            ):
                query = f"SELECT * FROM {table} WHERE {id_column}=?"
                if table == "execution_resource_revisions":
                    query = (
                        "SELECT v.* FROM execution_resource_revisions v JOIN execution_resources "
                        "r USING(resource_id) WHERE r.work_id=? ORDER BY v.revision"
                    )
                cursor = connection.execute(query, (work_id,))
                columns = [column[0] for column in cursor.description]
                sections.append(f"## {table}\n\n")
                for row in cursor:
                    row_state = dict(zip(columns, row, strict=True))
                    key_column = {
                        "execution_resource_revisions": "resource_id",
                        "execution_attempts": "attempt_id",
                        "execution_invocations": "invocation_id",
                    }[table]
                    key = f"{table}/{row_state[key_column]}/{row_state['revision']}"
                    operational_refs[key] = (
                        hashlib.sha256(canonical_json(row_state).encode()).hexdigest().upper()
                    )
                    sections.append(
                        "```json\n"
                        + json.dumps(row_state, ensure_ascii=False, indent=2)
                        + "\n```\n\n"
                    )
            _write_text(destination, f"work/{work_id}/execution", "".join(sections), files)
        cursor = connection.execute("SELECT * FROM knowledge_delivery ORDER BY invocation_id")
        columns = [column[0] for column in cursor.description]
        for row in cursor:
            data = dict(zip(columns, row, strict=True))
            _write_text(
                destination,
                f"accounting/{data['invocation_id']}",
                "```json\n" + json.dumps(data, indent=2) + "\n```\n",
                files,
            )
            operational_refs[f"knowledge_delivery/{data['invocation_id']}/0"] = (
                hashlib.sha256(canonical_json(data).encode()).hexdigest().upper()
            )
        index.append("\n## Exact versions and originals\n\n")
        index.extend(f"- [{name}]({name})\n" for name in sorted(files))
        catalog = "".join(index)
        if len(catalog) > 24000:
            parts = _write_text(destination, "catalog", catalog, files)
            catalog = "# Activity and memory catalog\n\n" + "".join(
                f"- [Catalog part {number}]({name})\n" for number, name in enumerate(parts, 1)
            )
        _write_text(destination, "README", catalog, files)
        receipt = ProjectionReceipt(
            space_id=info.space_id,
            state_revision=info.state_revision,
            refs=tuple(refs),
            files=files,
            operational_refs=operational_refs,
        )
    validate_workspace_projection(path, authority, receipt)
    return receipt


def validate_workspace_projection(
    path: Path,
    authority: LocalAuthority,
    receipt: ProjectionReceipt,
) -> None:
    """Reject deleted, edited or no-longer-authorized prepared bases before delivery."""
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.space_id != receipt.space_id or info.recovery_state != "active":
            raise FoundationError("wrong_space", "Prepared snapshot belongs to another space")
        _authorize(
            connection, actor=authority.actor, action="record.read", epoch=info.execution_epoch
        )
        _authorize(
            connection, actor=authority.actor, action="memory.transfer", epoch=info.execution_epoch
        )
        expected = {(ref.section, str(ref.record_id), ref.revision): ref for ref in receipt.refs}
        for section, query in QUERIES.items():
            for row in connection.execute(query):
                kind, identifier, revision, current, _payload, checksum = row
                key = (section, identifier, revision)
                prior = expected.pop(key, None)
                if prior is None:
                    continue  # A new record is not silently added to an already approved snapshot.
                raw = _payload.encode("utf-8") if isinstance(_payload, str) else bytes(_payload)
                digest = hashlib.sha256(raw).hexdigest().upper()
                if current != prior.current_revision or digest != prior.sha256:
                    raise FoundationError("stale_basis", "Prepared projection basis changed")
                _authorize(
                    connection,
                    actor=authority.actor,
                    action="record.read",
                    epoch=info.execution_epoch,
                    resource_type=kind if section == "subject" else "artifact",
                    resource_id=UUID(identifier),
                )
        if expected:
            raise FoundationError("content_unavailable", "Prepared projection basis was removed")
        _validate_operational(connection, receipt)


def _validate_operational(connection: sqlite3.Connection, receipt: ProjectionReceipt) -> None:
    columns_by_table = {
        "execution_resource_revisions": "resource_id",
        "execution_attempts": "attempt_id",
        "execution_invocations": "invocation_id",
        "knowledge_delivery": "invocation_id",
    }
    for key, digest in receipt.operational_refs.items():
        table, identifier, revision = key.split("/")
        if table not in columns_by_table:
            raise FoundationError("invalid_request", "Unknown operational projection basis")
        query = f"SELECT * FROM {table} WHERE {columns_by_table[table]}=?"
        values: tuple[str, ...] = (identifier,)
        if table != "knowledge_delivery":
            query += " AND revision=?"
            values += (revision,)
        cursor = connection.execute(query, values)
        row = cursor.fetchone()
        if row is None:
            raise FoundationError("content_unavailable", "Prepared execution basis was removed")
        data = dict(zip((column[0] for column in cursor.description), row, strict=True))
        if hashlib.sha256(canonical_json(data).encode()).hexdigest().upper() != digest:
            raise FoundationError("stale_basis", "Prepared execution accounting changed")
