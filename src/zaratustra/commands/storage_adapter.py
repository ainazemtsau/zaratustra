"""Explicit complete migration and cache operations for a selected Home."""

from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import ExitStack, closing
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from zaratustra import home, storage
from zaratustra.core import inspect_artifacts, read_records, read_workspace
from zaratustra.core import storage_factory as workspace_factory
from zaratustra.journal import Scope, Store

from . import Command, Context, registry


def inventory(root: Path) -> list[tuple[Path, str]]:
    rows = []
    offset = 0
    while True:
        page = home.list_processes(root, limit=100, offset=offset)
        rows.extend(page)
        if len(page) < 100:
            break
        offset += 100
    result = [(root, "home")]
    for row in rows:
        location = Path(row["location"])
        if not location.is_absolute() or not location.is_dir():
            raise home.HomeError("source_unavailable", f"Map workspace {row['workspace_id']} first")
        result.append((location, "workspace"))
    shared = root / ".zara-home/shared"
    if shared.exists():
        result.append((shared, "workspace"))
    return result


def _legacy(path: Path, kind: str) -> Path:
    return path / (".zara-home/registry.sqlite3" if kind == "home" else ".zara/state.sqlite3")


def _verify_artifacts(path: Path) -> None:
    if read_workspace(path).schema_version >= 4:
        inspection = inspect_artifacts(path)
        failed = [
            item.model_dump(mode="json")
            for item in inspection.versions
            if item.status != "verified"
        ]
        if failed:
            raise storage.StorageError(
                "Registered artifact bytes failed verification: "
                + json.dumps(failed, ensure_ascii=False)
            )


def migrate(root: Path) -> dict[str, Any]:
    """Back up bytes and SQLite consistently, verify conversion, then retire old DBs."""
    root = root.resolve()
    with ExitStack() as stack:
        stack.enter_context(storage.locked(root))
        scopes = inventory(root)
        for path, _ in sorted(scopes[1:], key=lambda item: item[0].as_posix()):
            stack.enter_context(storage.locked(path))
            _verify_artifacts(path)
        pending = [
            (path, kind)
            for path, kind in scopes
            if not storage.enabled(path) or _legacy(path, kind).exists()
        ]
        if not pending:
            _upgrade_vocab(root, scopes)
            return {"changed": False, "scopes": inspect(root, rebuild=False)}
        # Legacy writers use SQLite's lock. Hold those locks for the whole conversion.
        legacy_handles = stack.enter_context(ExitStack())
        legacy_connections: list[sqlite3.Connection] = []
        for path, kind in pending:
            db = legacy_handles.enter_context(
                closing(sqlite3.connect(_legacy(path, kind), autocommit=True))
            )
            db.execute("BEGIN IMMEDIATE")
            legacy_connections.append(db)
        backup = root / ".zara-cache/backups" / str(uuid4())
        backup.mkdir(parents=True)
        copied: dict[Path, Path] = {}
        for index, (path, kind) in enumerate(scopes):
            destination = backup / str(index)
            shutil.copytree(
                path,
                destination,
                ignore=shutil.ignore_patterns(".git", ".venv", ".zara-cache", "__pycache__"),
            )
            copied[path] = destination
            legacy = _legacy(path, kind)
            if legacy.exists():
                with closing(sqlite3.connect(legacy.as_uri() + "?mode=ro", uri=True)) as source:
                    with closing(sqlite3.connect(_legacy(destination, kind))) as target:
                        source.backup(target)
                        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                            raise storage.StorageError("Backup failed SQLite integrity check")
        report = []
        # Process bytes first. Home routing is switched last.
        for path, kind in reversed(pending):
            factory = home.storage_factory if kind == "home" else workspace_factory
            legacy = _legacy(path, kind)
            with closing(sqlite3.connect(legacy)) as original:
                before = storage.snapshot(original)
            result = storage.activate(path, legacy, kind, factory)
            with storage.connection(path, factory) as (rebuilt, _):
                after = storage.snapshot(rebuilt)
            # External paths intentionally need a per-device mapping; initialize this device.
            if kind == "home":
                locations = {
                    row["workspace_id"]: row["location"]
                    for row in before.get("processes", {}).values()
                    if not Path(row["location"]).is_relative_to(root)
                }
                if locations:
                    (path / ".zara-device.json").write_text(
                        json.dumps(locations, ensure_ascii=False), encoding="utf-8"
                    )
                    storage.verify(path, factory, rebuild=True)
                    with storage.connection(path, factory) as (rebuilt, _):
                        after = storage.snapshot(rebuilt)
            if before != after:
                raise storage.StorageError("Conversion differs from original rows; backup retained")
            if kind == "workspace":
                read_records(path)
            report.append({"path": path.as_posix(), **result})
        # Old releases do not know the file lock. Fence their waiting writers before
        # releasing SQLite locks, then close handles for Windows retirement.
        for db in legacy_connections:
            for (table,) in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall():
                if not table.startswith("sqlite_"):
                    for action in ("INSERT", "UPDATE", "DELETE"):
                        db.execute(
                            f'CREATE TRIGGER IF NOT EXISTS "retired_{table}_{action}" '
                            f'BEFORE {action} ON "{table}" BEGIN '
                            "SELECT RAISE(ABORT, 'Storage moved to .zara-data; "
                            "upgrade client'); END"
                        )
            db.execute("PRAGMA user_version=22000")
            db.execute("COMMIT")
        legacy_handles.close()
        for path, kind in pending:
            legacy = _legacy(path, kind)
            if legacy.exists():
                legacy.rename(copied[path] / ("retired-" + legacy.name))
    _upgrade_vocab(root, scopes)
    from .navigation import refresh

    refresh(root, all_processes=True)
    return {"changed": True, "backup": backup.as_posix(), "scopes": report}


def _upgrade_vocab(root: Path, scopes: list[tuple[Path, str]]) -> None:
    if home.read_home(root)["schema"] == 2:
        return
    categories: set[str] = set()
    for path, kind in scopes:
        if kind == "home":
            continue
        if read_workspace(path).schema_version < 8:
            continue
        snapshot = read_records(path)
        from zaratustra.core import Process

        process = next(r for r in snapshot.records if isinstance(r, Process))
        shared = path == root / ".zara-home/shared"
        scope = Scope(
            kind="home" if shared else "process",
            id=UUID(home.read_home(root)["id"]) if shared else process.id,
        )
        store = Store(path, scope, "storage migration: preserve existing classifications")
        for history in store.records.values():
            for revision in history:
                if revision.type_name == "episode":
                    categories.add(revision.payload.get("category", "work"))
    home.upgrade_vocabulary(root, existing_categories=tuple(sorted(categories)))


def inspect(root: Path, *, rebuild: bool = False) -> list[dict[str, Any]]:
    result = []
    for path, kind in inventory(root):
        if storage.enabled(path):
            factory = home.storage_factory if kind == "home" else workspace_factory
            if kind == "workspace":
                _verify_artifacts(path)
            result.append(
                {"path": path.as_posix(), **storage.verify(path, factory, rebuild=rebuild)}
            )
        else:
            result.append({"path": path.as_posix(), "kind": kind, "format": "legacy-sqlite"})
    return result


def activate_new_workspace(path: Path) -> None:
    """New empty/bootstrap data has no migration backup requirement."""
    if storage.enabled(path):
        return
    info = read_workspace(path)
    storage.activate(path, info.database, "workspace", workspace_factory)
    info.database.unlink()


class StorageCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeviceMapping(StorageCommand):
    workspace_id: UUID
    path: str


def _execute(
    context: Context, command: Command, source: str, operation: UUID, guard: int | None
) -> dict[str, Any]:
    root = Path(context.home)
    if command.action == "storage.map":
        from .connect import _replace

        mapping = DeviceMapping.model_validate(command.payload)
        selected = Path(mapping.path).expanduser().resolve()
        source_info = home.inspect_source(selected)
        if source_info["workspace_id"] != str(mapping.workspace_id):
            raise home.HomeError("identity_mismatch", "Selected folder has a different workspace")
        registered = home.resolve_process(root, source_info["id"])
        if registered["workspace_id"] != str(mapping.workspace_id):
            raise home.HomeError(
                "identity_mismatch", "Registration differs from selected workspace"
            )
        with storage.locked(root):
            path = root / ".zara-device.json"
            values = json.loads(path.read_bytes()) if path.exists() else {}
            values[str(mapping.workspace_id)] = selected.as_posix()
            _replace(path, json.dumps(values, ensure_ascii=False, indent=2))
            storage.verify(root, home.storage_factory, rebuild=True)
        return {"mapped_workspace": str(mapping.workspace_id), "path": selected.as_posix()}
    if command.action == "storage.migrate":
        return migrate(root)
    if command.action in ("storage.verify", "index.rebuild"):
        from .navigation import refresh

        refresh(root, all_processes=True)
    return {"scopes": inspect(root, rebuild=command.action == "index.rebuild")}


def register() -> None:
    registry.register(
        registry.CommandSpec(
            "storage.map",
            DeviceMapping,
            _execute,
            "Map an external registered workspace to a verified path on this device",
        )
    )
    for name in ("storage.status", "storage.migrate", "storage.verify", "index.rebuild"):
        registry.register(
            registry.CommandSpec(
                name,
                StorageCommand,
                _execute,
                "Inspect portable files, explicitly migrate complete Home, or rebuild local caches",
            )
        )
