"""Version metadata and checked local bytes; mutations owns all domain writes."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

from .protocol import ArtifactVersion
from .records import Artifact, RecordModel, RecordsSnapshot, Text
from .workspace import WorkspaceError, _plain_path


class ArtifactError(WorkspaceError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


class ArtifactContent(RecordModel):
    version: ArtifactVersion
    content: bytes


class ArtifactHealth(RecordModel):
    version: ArtifactVersion
    status: Text


class ArtifactInspection(RecordModel):
    state_revision: int
    versions: tuple[ArtifactHealth, ...]
    unregistered_files: tuple[str, ...]


def current_artifact(snapshot: RecordsSnapshot, work_id: UUID | None = None) -> Artifact:
    for record in snapshot.records:
        if isinstance(record, Artifact) and (work_id is None or record.work_id == work_id):
            return record
    raise ArtifactError("invalid_artifact", "Create initial records first")


def read_versions(connection: sqlite3.Connection) -> tuple[ArtifactVersion, ...]:
    versions = []
    for identity, artifact_id, body in connection.execute(
        "SELECT id, artifact_id, body FROM artifact_versions ORDER BY id"
    ):
        descriptor = ArtifactVersion.model_validate_json(body)
        if (str(descriptor.id), str(descriptor.artifact_id)) != (identity, artifact_id):
            raise ArtifactError("invalid_artifact", "Version metadata mismatch")
        versions.append(descriptor)
    return tuple(versions)


def resolve_version(
    versions: tuple[ArtifactVersion, ...], artifact: Artifact, version_id: UUID | None = None
) -> ArtifactVersion:
    selected = artifact.active_version if version_id is None else version_id
    for descriptor in versions:
        if descriptor.id == selected and (
            descriptor.artifact_id,
            descriptor.work_id,
            descriptor.process_id,
        ) == (artifact.id, artifact.work_id, artifact.process_id):
            return descriptor
    raise ArtifactError("invalid_artifact", "No such registered version in this Work")


def content_path(root: Path, descriptor: ArtifactVersion) -> Path:
    path = root / descriptor.relative_path
    for component in (root / "artifacts", path.parent, path):
        _plain_path(component)
    return path


def validate_bytes(content: bytes | None, sha256: str | None, size: int | None) -> bytes:
    if type(content) is not bytes:
        raise ArtifactError("content_required", "Supply the exact confirmed content bytes")
    if len(content) != size or hashlib.sha256(content).hexdigest() != sha256:
        raise ArtifactError("content_changed", "Content differs from the confirmed digest/size")
    return content


def verified_content(root: Path, descriptor: ArtifactVersion) -> ArtifactContent:
    try:
        path = content_path(root, descriptor)
        if not path.is_file():
            raise ArtifactError("content_unavailable", "Registered content is not a regular file")
        if path.stat().st_size != descriptor.size:
            raise ArtifactError("content_changed", "Registered content size changed")
        content = validate_bytes(path.read_bytes(), descriptor.sha256, descriptor.size)
        return ArtifactContent(version=descriptor, content=content)
    except OSError as error:
        raise ArtifactError("content_unavailable", str(error)) from error


def publish_bytes(
    root: Path, descriptor: ArtifactVersion, content: bytes, *, restore: bool = False
) -> None:
    """Publish complete bytes without replacing an existing immutable version.

    A DB failure can leave an unregistered final file. A checked retry can reuse it.
    Explicit repair retains damaged bytes in quarantine before restoring the exact
    registered version; it never changes the descriptor or active reference.
    """
    content = validate_bytes(content, descriptor.sha256, descriptor.size)
    try:
        path = content_path(root, descriptor)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            try:
                verified_content(root, descriptor)
                return
            except ArtifactError:
                if not restore or not path.is_file():
                    raise
                quarantine = path.with_name(f"quarantine-{uuid4()}.blob")
                path.rename(quarantine)
        staging = path.with_name(f"staging-{uuid4()}.tmp")
        with staging.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # Hash the actual saved file before exposing its final immutable name.
        validate_bytes(staging.read_bytes(), descriptor.sha256, descriptor.size)
        os.link(staging, path)  # Atomic no-replace publication on the local filesystem.
        staging.unlink()
        verified_content(root, descriptor)
    except OSError as error:
        raise ArtifactError("publication_failed", str(error)) from error


def inspect_files(
    root: Path, snapshot: RecordsSnapshot, versions: tuple[ArtifactVersion, ...]
) -> ArtifactInspection:
    health = []
    for descriptor in versions:
        try:
            verified_content(root, descriptor)
            status = "verified"
        except WorkspaceError as error:
            status = str(error)
        health.append(ArtifactHealth(version=descriptor, status=status))
    registered = {descriptor.relative_path for descriptor in versions}
    unknown: list[str] = []
    # Owner-local inspection covers declared Artifacts only, never foreign directories.
    for artifact in (r for r in snapshot.records if isinstance(r, Artifact)):
        directory = root / "artifacts" / str(artifact.id)
        _plain_path(directory)
        if directory.is_dir():
            unknown.extend(
                path.relative_to(root).as_posix()
                for path in directory.iterdir()
                if path.relative_to(root).as_posix() not in registered
            )
    return ArtifactInspection(
        state_revision=snapshot.state_revision,
        versions=tuple(health),
        unregistered_files=tuple(sorted(unknown)),
    )
