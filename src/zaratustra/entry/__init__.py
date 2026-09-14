"""Explicit local discovery catalog; its rows never grant Core authority."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import import_module
from io import BufferedRandom
from pathlib import Path
from typing import Annotated, Any, Literal, Self
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from zaratustra.core import (
    Process,
    ProcessQuery,
    ProcessStateQuery,
    Work,
    WorkspaceError,
    read_records,
    read_workspace,
)

Designation = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=128)
]


class EntryError(RuntimeError):
    """A catalog operation failed without changing catalog or workspace state."""

    def __init__(self, code: str, message: str, *, choices: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.code = code
        self.choices = choices


class EntryModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CatalogEntry(EntryModel):
    id: UUID
    designation: Designation
    aliases: Annotated[tuple[Designation, ...], Field(max_length=32)] = ()
    source_path: str
    source_kind: Literal["relative", "absolute"]
    workspace_id: UUID
    process_id: UUID
    work_id: UUID

    @model_validator(mode="after")
    def distinct_names(self) -> Self:
        names = [self.designation.casefold(), *(alias.casefold() for alias in self.aliases)]
        if len(set(names)) != len(names):
            raise ValueError("Designation and aliases must be distinct")
        source = Path(self.source_path)
        if not self.source_path.strip() or source.is_absolute() != (self.source_kind == "absolute"):
            raise ValueError("Source path kind must match its path")
        if self.source_kind == "relative" and ".." in source.parts:
            raise ValueError("Relative source path must stay below the catalog directory")
        return self


class EntryCatalog(EntryModel):
    version: Literal[1] = 1
    entries: tuple[CatalogEntry, ...] = ()

    @model_validator(mode="after")
    def unique_designations(self) -> Self:
        names = [entry.designation.casefold() for entry in self.entries]
        if len(set(names)) != len(names) or len({entry.id for entry in self.entries}) != len(
            self.entries
        ):
            raise ValueError("Catalog designations and ids must be unique")
        return self


class CatalogMatch(EntryModel):
    entry: CatalogEntry
    resolved_path: str
    source_state: Literal["available", "unavailable", "mismatched"]
    code: str | None = None
    current_revision: int | None = None


class CatalogSearch(EntryModel):
    version: Literal[1] = 1
    query: str
    matches: tuple[CatalogMatch, ...]


@dataclass(frozen=True)
class PreparedEntryRead:
    entry: CatalogEntry
    workspace: Path
    query: ProcessQuery


@dataclass(frozen=True)
class PreparedProcessStateRead:
    entry: CatalogEntry
    workspace: Path
    query: ProcessStateQuery


def _catalog_path(path: Path) -> Path:
    return path.expanduser().resolve()


def _acquire_file_lock(stream: BufferedRandom) -> None:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
    else:
        fcntl: Any = import_module("fcntl")
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)


def _release_file_lock(stream: BufferedRandom) -> None:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl: Any = import_module("fcntl")
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def _catalog_mutation(path: Path) -> Iterator[None]:
    """Serialize cooperating read-modify-write operations at one stable path."""
    selected = _catalog_path(path)
    selected.parent.mkdir(parents=True, exist_ok=True)
    lock_path = selected.with_name(f".{selected.name}.lock")
    try:
        stream = lock_path.open("a+b")
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(bytes(1))
            stream.flush()
        _acquire_file_lock(stream)
    except OSError as error:
        if "stream" in locals():
            stream.close()
        raise EntryError(
            "catalog_lock_unavailable", "Catalog mutation lock is unavailable"
        ) from error
    try:
        yield
    finally:
        try:
            _release_file_lock(stream)
        except OSError:
            pass
        stream.close()


def _load(path: Path, *, missing_ok: bool = False) -> EntryCatalog:
    selected = _catalog_path(path)
    if not selected.exists() and missing_ok:
        return EntryCatalog()
    try:
        return EntryCatalog.model_validate_json(selected.read_bytes())
    except FileNotFoundError as error:
        raise EntryError("catalog_unavailable", "Catalog file does not exist") from error
    except (OSError, ValidationError) as error:
        raise EntryError("catalog_invalid", "Catalog file is unavailable or invalid") from error


def _save(path: Path, catalog: EntryCatalog) -> None:
    selected = _catalog_path(path)
    selected.parent.mkdir(parents=True, exist_ok=True)
    temporary = selected.with_name(f".{selected.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(catalog.model_dump_json(indent=2) + chr(10), encoding="utf-8")
        os.replace(temporary, selected)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise EntryError(
            "catalog_unavailable", "Catalog could not be written atomically"
        ) from error


def _stored_source(
    catalog_path: Path, workspace: Path
) -> tuple[str, Literal["relative", "absolute"]]:
    parent = _catalog_path(catalog_path).parent
    selected = workspace.expanduser().resolve()
    try:
        return selected.relative_to(parent).as_posix(), "relative"
    except ValueError:
        return selected.as_posix(), "absolute"


def source_path(catalog_path: Path, entry: CatalogEntry) -> Path:
    selected = Path(entry.source_path)
    if entry.source_kind == "relative":
        selected = _catalog_path(catalog_path).parent / selected
    return selected.resolve()


def _source_revision(path: Path, entry: CatalogEntry) -> int:
    info = read_workspace(path)
    if info.schema_version < 7:
        raise EntryError("source_unavailable", "Entry reading requires explicit schema 7")
    snapshot = read_records(path)
    process = next((row for row in snapshot.records if isinstance(row, Process)), None)
    work = next(
        (row for row in snapshot.records if isinstance(row, Work) and row.id == entry.work_id),
        None,
    )
    if (
        snapshot.workspace_id != entry.workspace_id
        or process is None
        or process.id != entry.process_id
        or work is None
        or work.process_id != entry.process_id
    ):
        raise EntryError("source_mismatch", "Source identities do not match the catalog row")
    return snapshot.state_revision


def add_entry(
    catalog_path: Path,
    designation: str,
    workspace: Path,
    work_id: UUID,
    *,
    aliases: tuple[str, ...] = (),
) -> CatalogEntry:
    """Add one explicit source after observing its stable public Core identities."""
    selected_designation = designation.strip()
    selected_aliases = tuple(alias.strip() for alias in aliases)
    if not selected_designation or any(not alias for alias in selected_aliases):
        raise EntryError("invalid_designation", "Designation and aliases must not be blank")
    selected_workspace = workspace.expanduser().resolve()
    try:
        info = read_workspace(selected_workspace)
        if info.schema_version < 7:
            raise EntryError("source_unavailable", "Entry reading requires explicit schema 7")
        snapshot = read_records(selected_workspace)
    except EntryError:
        raise
    except (OSError, WorkspaceError, ValidationError) as error:
        raise EntryError("source_unavailable", "Selected workspace is unavailable") from error
    process = next((row for row in snapshot.records if isinstance(row, Process)), None)
    work = next(
        (row for row in snapshot.records if isinstance(row, Work) and row.id == work_id), None
    )
    if process is None or work is None or work.process_id != process.id:
        raise EntryError("source_mismatch", "Selected Work is not in the workspace Process")
    stored, kind = _stored_source(catalog_path, selected_workspace)
    try:
        entry = CatalogEntry(
            id=uuid4(),
            designation=selected_designation,
            aliases=selected_aliases,
            source_path=stored,
            source_kind=kind,
            workspace_id=snapshot.workspace_id,
            process_id=process.id,
            work_id=work.id,
        )
    except ValidationError as error:
        raise EntryError("invalid_designation", "Designation or alias is invalid") from error
    with _catalog_mutation(catalog_path):
        catalog = _load(catalog_path, missing_ok=True)
        if any(
            row.designation.casefold() == selected_designation.casefold() for row in catalog.entries
        ):
            raise EntryError("designation_exists", "Catalog designation already exists")
        _save(catalog_path, EntryCatalog(entries=(*catalog.entries, entry)))
    return entry


def _matches(entry: CatalogEntry, query: str) -> bool:
    needle = query.casefold()
    return not needle or any(
        needle in candidate.casefold() for candidate in (entry.designation, *entry.aliases)
    )


def find_entries(catalog_path: Path, query: str = "") -> CatalogSearch:
    """Find rows and validate each source independently without granting authority."""
    if len(query) > 128:
        raise EntryError("invalid_query", "Search query exceeds 128 characters")
    catalog = _load(catalog_path)
    matches = []
    for entry in catalog.entries:
        if not _matches(entry, query.strip()):
            continue
        try:
            resolved = source_path(catalog_path, entry)
            revision = _source_revision(resolved, entry)
            row = CatalogMatch(
                entry=entry,
                resolved_path=resolved.as_posix(),
                source_state="available",
                current_revision=revision,
            )
        except EntryError as error:
            state: Literal["unavailable", "mismatched"] = (
                "mismatched" if error.code == "source_mismatch" else "unavailable"
            )
            row = CatalogMatch(
                entry=entry,
                resolved_path=resolved.as_posix(),
                source_state=state,
                code=error.code,
            )
        except (OSError, RuntimeError, WorkspaceError, ValidationError):
            row = CatalogMatch(
                entry=entry,
                resolved_path=entry.source_path,
                source_state="unavailable",
                code="source_unavailable",
            )
        matches.append(row)
    return CatalogSearch(query=query.strip(), matches=tuple(matches))


def _resolve(catalog: EntryCatalog, designation_or_alias: str) -> CatalogEntry:
    term = designation_or_alias.strip().casefold()
    if not term:
        raise EntryError("invalid_query", "An exact designation or alias is required")
    exact_designation = tuple(
        entry for entry in catalog.entries if term == entry.designation.casefold()
    )
    if exact_designation:
        return exact_designation[0]
    found = tuple(
        entry for entry in catalog.entries if term in {alias.casefold() for alias in entry.aliases}
    )
    if not found:
        raise EntryError("not_found", "No exact designation or alias matches")
    if len(found) > 1:
        choices = tuple(entry.designation for entry in found)
        raise EntryError(
            "ambiguous",
            f"Designation is ambiguous; choose one of: {', '.join(choices)}",
            choices=choices,
        )
    return found[0]


def resolve_entry(catalog_path: Path, designation_or_alias: str) -> CatalogEntry:
    return _resolve(_load(catalog_path), designation_or_alias)


def prepare_entry_read(
    catalog_path: Path, designation_or_alias: str, *, max_bytes: int
) -> PreparedEntryRead:
    """Resolve current identity/query only; the caller must separately authorize it."""
    entry = resolve_entry(catalog_path, designation_or_alias)
    try:
        workspace = source_path(catalog_path, entry)
        revision = _source_revision(workspace, entry)
    except EntryError:
        raise
    except (OSError, RuntimeError, WorkspaceError, ValidationError) as error:
        raise EntryError("source_unavailable", "Selected workspace is unavailable") from error
    try:
        query = ProcessQuery(
            workspace_id=entry.workspace_id,
            work_id=entry.work_id,
            process_id=entry.process_id,
            expected_revision=revision,
            visible_work_ids=(entry.work_id,),
            selected_work_id=entry.work_id,
            max_bytes=max_bytes,
        )
    except ValidationError as error:
        raise EntryError("invalid_query", "Basic read byte budget is invalid") from error
    return PreparedEntryRead(entry, workspace, query)


def prepare_process_state_read(
    catalog_path: Path, designation_or_alias: str
) -> PreparedProcessStateRead:
    """Resolve one exact Process-state query without selecting a historical Work."""
    entry = resolve_entry(catalog_path, designation_or_alias)
    try:
        workspace = source_path(catalog_path, entry)
        revision = _source_revision(workspace, entry)
    except EntryError:
        raise
    except (OSError, RuntimeError, WorkspaceError, ValidationError) as error:
        raise EntryError("source_unavailable", "Selected workspace is unavailable") from error
    return PreparedProcessStateRead(
        entry=entry,
        workspace=workspace,
        query=ProcessStateQuery(
            workspace_id=entry.workspace_id,
            process_id=entry.process_id,
            expected_revision=revision,
        ),
    )


def relocate_entry(catalog_path: Path, designation_or_alias: str, workspace: Path) -> CatalogEntry:
    """Rewrite one source path only after exact identity validation at the new path."""
    selected = workspace.expanduser().resolve()
    with _catalog_mutation(catalog_path):
        catalog = _load(catalog_path)
        entry = _resolve(catalog, designation_or_alias)
        try:
            _source_revision(selected, entry)
        except EntryError:
            raise
        except (OSError, WorkspaceError, ValidationError) as error:
            raise EntryError("source_unavailable", "Relocation source is unavailable") from error
        stored, kind = _stored_source(catalog_path, selected)
        moved = entry.model_copy(update=dict(source_path=stored, source_kind=kind))
        _save(
            catalog_path,
            EntryCatalog(
                entries=tuple(moved if row.id == entry.id else row for row in catalog.entries)
            ),
        )
    return moved


__all__ = [
    "CatalogEntry",
    "CatalogMatch",
    "CatalogSearch",
    "EntryCatalog",
    "EntryError",
    "PreparedEntryRead",
    "PreparedProcessStateRead",
    "add_entry",
    "find_entries",
    "prepare_entry_read",
    "prepare_process_state_read",
    "relocate_entry",
    "resolve_entry",
    "source_path",
]
