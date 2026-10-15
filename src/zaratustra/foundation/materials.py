"""Exact, rights-checked navigation and bounded bytes across material families.

Navigation is newly derived metadata. Existing references and retained payloads
are never rewritten, and metadata does not count as content exposure.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path

from .knowledge import _material_content, read_knowledge
from .models import KnowledgeRef
from .operations import LocalAuthority, _authorize, _local_space, read_artifact
from .storage import FoundationError, space_connection


@dataclass(frozen=True)
class _Material:
    kind: str
    availability: str
    stale: bool
    field: str | None
    media_type: str | None
    content: bytes | None


def _kind(path: Path, ref: KnowledgeRef, authority: LocalAuthority) -> tuple[str, str, bool]:
    """Addressed metadata only; rights are checked before discovering the family."""

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active":
            raise FoundationError("permission_denied", "Quarantined spaces disclose no materials")
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="artifact",
            resource_id=ref.record_id,
        )
        address = str(ref.record_id), ref.revision
        if info.schema_version >= 10:
            row = connection.execute(
                "SELECT r.kind,r.status,v.payload IS NOT NULL,r.current_revision "
                "FROM knowledge_records r "
                "JOIN knowledge_revisions v ON v.record_id=r.record_id "
                "WHERE r.record_id=? AND v.revision=?",
                address,
            ).fetchone()
            if row is not None:
                return (
                    row[0],
                    "deleted" if row[1] == "deleted" else "available" if row[2] else "unavailable",
                    row[3] != ref.revision,
                )
        row = connection.execute(
            "SELECT r.kind,r.status,c.payload IS NOT NULL,r.current_revision FROM records r "
            "JOIN record_revisions v ON v.record_id=r.record_id "
            "LEFT JOIN managed_content c ON c.record_id=v.record_id AND c.revision=v.revision "
            "WHERE r.record_id=? AND v.revision=?",
            address,
        ).fetchone()
        if row is None:
            raise FoundationError("not_found", "Exact material address is absent")
        if row[0] != "artifact":
            raise FoundationError("wrong_kind", "Address is not a content-bearing material")
        return (
            "artifact",
            "deleted" if row[1] == "deleted" else "available" if row[2] else "unavailable",
            row[3] != ref.revision,
        )


def _read(path: Path, ref: KnowledgeRef, authority: LocalAuthority) -> _Material:
    kind, availability, stale = _kind(path, ref, authority)
    if kind == "artifact":
        if availability != "available":
            return _Material(kind, availability, stale, None, None, None)
        artifact = read_artifact(path, ref.record_id, authority, revision=ref.revision)
        content = artifact.content
        if (
            content is not None
            and hashlib.sha256(content).hexdigest().upper() != artifact.content_sha256
        ):
            raise FoundationError("corrupt_space", "Artifact content digest mismatch")
        return _Material("artifact", "available", stale, "content", artifact.media_type, content)
    item = read_knowledge(path, ref.record_id, authority, revision=ref.revision)
    state = item.state
    if state is None:
        return _Material(item.kind, item.availability, item.stale, None, None, None)
    field, content, media_type = _material_content(state)
    return _Material(
        item.kind,
        item.availability if content is not None else "unavailable",
        item.stale,
        field,
        media_type,
        content,
    )


def _fragment(material: _Material, ref: KnowledgeRef) -> tuple[bytes | None, int]:
    content = material.content
    start = ref.start if ref.start is not None else 0
    if content is None:
        return None, start
    end = ref.end if ref.end is not None else len(content)
    if end > len(content):
        raise FoundationError("invalid_fragment", "Fragment exceeds exact retained bytes")
    return content[start:end], start


def _navigation(material: _Material, ref: KnowledgeRef, content: bytes | None) -> dict[str, object]:
    return {
        **ref.model_dump(mode="json"),
        "record_kind": material.kind,
        "reader": "material",
        "availability": material.availability,
        "stale": material.stale,
        "field": material.field,
        "media_type": material.media_type,
        "total_bytes": len(content) if content is not None else None,
        "original_total_bytes": len(material.content) if material.content is not None else None,
        "content_sha256": hashlib.sha256(content).hexdigest().upper()
        if content is not None
        else None,
    }


def describe_material_reference(
    path: Path, ref: KnowledgeRef, authority: LocalAuthority
) -> dict[str, object]:
    """Describe an authorized exact material without disclosing any body bytes."""

    material = _read(path, ref, authority)
    content, _ = _fragment(material, ref)
    return _navigation(material, ref, content)


def open_material(
    path: Path,
    ref: KnowledgeRef,
    authority: LocalAuthority,
    *,
    offset: int = 0,
    max_bytes: int = 16384,
) -> dict[str, object]:
    """Open one exact fragment-relative window, exposing only its returned bytes.

    Valid UTF-8 is windowed on code point boundaries without enlarging the byte
    budget. Invalid UTF-8 and binary bodies stay byte-exact base64. Neither a
    caller fragment nor its continuation is ever widened to the original body.
    """

    if offset < 0 or not 1 <= max_bytes <= 65536:
        raise FoundationError("invalid_request", "Open needs a finite byte window")
    material = _read(path, ref, authority)
    content, fragment_start = _fragment(material, ref)
    result = _navigation(material, ref, content)
    result.update({"offset": offset, "exposed": [], "next_offset": None, "returned_bytes": 0})
    if content is None:
        result.update({"content": None, "content_complete": False})
        return result
    if offset > len(content):
        raise FoundationError("invalid_request", "Open offset exceeds exact fragment bytes")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        utf8 = False
    else:
        utf8 = True
    end = min(offset + max_bytes, len(content))
    if utf8:
        try:
            content[:offset].decode("utf-8")
        except UnicodeDecodeError as error:
            raise FoundationError("invalid_request", "Offset splits a UTF-8 character") from error
        while end < len(content) and content[end] & 0xC0 == 0x80:
            end -= 1
        if end == offset and offset < len(content):
            raise FoundationError("invalid_request", "Window cannot hold a UTF-8 character")
    chunk = content[offset:end]
    result.update(
        {
            "content_base64": base64.b64encode(chunk).decode("ascii"),
            "content_encoding": "utf-8" if utf8 else "base64",
            "chunk_sha256": hashlib.sha256(chunk).hexdigest().upper(),
            "next_offset": end if end < len(content) else None,
            "returned_bytes": len(chunk),
            "content_complete": offset == 0 and end == len(content),
            "exposed": [
                (
                    ref
                    if ref.start is None and offset == 0 and end == len(content)
                    else ref.model_copy(
                        update={"start": fragment_start + offset, "end": fragment_start + end}
                    )
                ).model_dump(mode="json")
            ]
            if chunk
            else [],
        }
    )
    if utf8:
        result["content_text"] = chunk.decode("utf-8")
    return result
