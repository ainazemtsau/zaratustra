"""Deterministic DB-derived overview; never ingest projection content as state."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from .protocol import (
    ArtifactVersion,
    MutationEvent,
    MutationHistory,
    ProcessMaterialEvent,
    WorkCreationEvent,
)
from .records import RecordModel, RecordsSnapshot
from .workspace import _plain_path


class ProjectionStatus(RecordModel):
    generated_from_revision: int
    generated_at: datetime
    relative_path: Literal["projections/overview.md"] = "projections/overview.md"
    status: Literal["current", "missing", "stale_or_changed"]
    expected_sha256: str


def render_overview(
    snapshot: RecordsSnapshot,
    history: MutationHistory,
    versions: tuple[ArtifactVersion, ...],
    created_at: datetime,
) -> tuple[bytes, datetime]:
    events: tuple[MutationEvent | ProcessMaterialEvent | WorkCreationEvent, ...] = tuple(
        sorted(
            (*history.events, *history.process_events, *history.work_creation_events),
            key=lambda row: row.state_revision,
        )
    )
    generated_at = events[-1].recorded_at if events else created_at
    if snapshot.records and not events:
        generated_at = snapshot.records[0].created_at
    lines = [
        "# Zaratustra — generated overview",
        "",
        f"generated_from_revision: {snapshot.state_revision}",
        f"generated_at: {generated_at.isoformat()}",
        f"workspace_id: {snapshot.workspace_id}",
        "",
        "Read-only projection. Rebuild from saved state; edits do not change Zaratustra.",
        "Version metadata records publication. Use artifact read to verify current bytes.",
        "This owner-local overview is not a Work context package.",
        "",
    ]
    for record in snapshot.records:
        lines.extend(
            [f"## {record.kind}", "", "```json", record.model_dump_json(indent=2), "```", ""]
        )
    lines.extend(["## Registered versions", ""])
    for descriptor in sorted(versions, key=lambda item: item.artifact_revision):
        lines.extend(
            [
                f"- Version: {descriptor.id}; Artifact revision: {descriptor.artifact_revision}",
                f"  SHA-256: {descriptor.sha256}; bytes: {descriptor.size}",
                f"  File: {descriptor.relative_path}",
                "",
            ]
        )
    lines.extend(["## Mutation provenance", ""])
    for event in events:
        # Escaped JSON keeps untrusted text from becoming Markdown structure.
        lines.extend(["```json", event.model_dump_json(indent=2), "```", ""])
    return (chr(10).join(lines) + chr(10)).encode("utf-8"), generated_at


def projection_status(
    root: Path, content: bytes, revision: int, generated_at: datetime
) -> ProjectionStatus:
    path = root / "projections/overview.md"
    _plain_path(path)
    status: Literal["current", "missing", "stale_or_changed"] = "missing"
    if path.exists():
        status = (
            "current" if path.is_file() and path.read_bytes() == content else "stale_or_changed"
        )
    return ProjectionStatus(
        generated_from_revision=revision,
        generated_at=generated_at,
        status=status,
        expected_sha256=hashlib.sha256(content).hexdigest(),
    )


def write_projection(root: Path, content: bytes) -> None:
    destination = root / "projections/overview.md"
    _plain_path(destination.parent)
    _plain_path(destination)
    destination.parent.mkdir(exist_ok=True)
    temporary = destination.with_name(f"overview-{uuid4()}.tmp")
    with temporary.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, destination)
