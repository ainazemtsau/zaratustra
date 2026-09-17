"""One internal Core store backs the selected Home's explicit shared area."""

from pathlib import Path
from uuid import UUID, uuid5

from zaratustra import storage
from zaratustra.core import (
    Event,
    InitialProcess,
    create_process,
    init_workspace,
    migrate_workspace,
    read_records,
    storage_factory,
)

from .store import Store
from .types import JournalError, Scope


def shared_store(
    home: Path, identity: UUID, source_ref: str, *, create: bool = False
) -> Store | None:
    path = home / ".zara-home" / "shared"
    for part in (path, path.parent):
        if part.is_symlink() or part.is_junction():
            raise JournalError("shared_path_conflict", "Shared area cannot cross a link")
    if not path.exists() and not create:
        return None
    if create:
        path.mkdir(parents=True, exist_ok=True)
        info = init_workspace(path)
        if info.schema_version == 1:
            migrate_workspace(path, target_version=10)
        create_process(
            path,
            InitialProcess(
                title="Home shared area",
                purpose="Explicitly shared records of this Home; internal storage",
                operation_id=uuid5(identity, "zaratustra-home-shared-v1"),
            ),
        )
        if storage.enabled(home) and not storage.enabled(path):
            database = path / ".zara/state.sqlite3"
            storage.activate(path, database, "workspace", storage_factory)
            database.unlink()
    snapshot = read_records(path)
    bootstrap = next((r for r in snapshot.records if isinstance(r, Event)), None)
    if (
        bootstrap is None
        or bootstrap.action != "process_created"
        or bootstrap.id != uuid5(identity, "zaratustra-home-shared-v1")
    ):
        raise JournalError("shared_identity_mismatch", "Storage is not bound to this Home")
    return Store(path, Scope(kind="home", id=identity), source_ref)
