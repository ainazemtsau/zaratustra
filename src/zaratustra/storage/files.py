"""Checked row deltas in immutable files, with one atomic confirmation pointer."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

Factory = Callable[[sqlite3.Connection, int], None]
Rows = dict[str, dict[str, dict[str, Any]]]
_local = threading.local()
_identifier = re.compile(r"^[a-z][a-z0-9_]*$")


def request_scoped[**P, T](function: Callable[P, T]) -> Callable[P, T]:
    """Validate immutable source history once per command, not once per nested read."""

    @wraps(function)
    def invoke(*args: P.args, **kwargs: P.kwargs) -> T:
        existing = getattr(_local, "verified", None)
        if existing is not None:
            return function(*args, **kwargs)
        _local.verified = {}
        try:
            return function(*args, **kwargs)
        finally:
            del _local.verified

    return invoke


class StorageError(ValueError):
    """Confirmed source files are unavailable, damaged or incompatible."""


def _json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode(
            "utf-8"
        )
        + b"\n"
    )


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _path(root: Path, relative: str) -> Path:
    value = PurePosixPath(relative)
    if value.is_absolute() or not value.parts or any(p in ("..", ".") for p in value.parts):
        raise StorageError("Invalid storage path")
    target = root.joinpath(*value.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise StorageError("Storage path leaves its selected directory")
    for part in (target, *target.parents):
        if part == root.parent:
            break
        if part.is_symlink() or part.is_junction():
            raise StorageError("Managed storage paths cannot be links")
    return target


def _write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _sync_parents(path.parent)


def _sync_parents(directory: Path) -> None:
    if os.name == "nt":
        return
    for path in (directory, *directory.parents):
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _move(source: Path, destination: Path) -> None:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        function = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
        function.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        function.restype = wintypes.BOOL
        if not function(str(source), str(destination), 0x1 | 0x8):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.replace(source, destination)
        _sync_parents(destination.parent)


def _replace(path: Path, raw: bytes) -> None:
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    _write(temporary, raw)
    _move(temporary, path)


def enabled(root: Path) -> bool:
    return (root / ".zara-data").exists()


@contextmanager
def locked(root: Path) -> Iterator[None]:
    """OS releases the local lock after a crash; nested same-thread reads are legal."""
    root = root.resolve()
    locks = getattr(_local, "locks", None)
    if locks is None:
        locks = _local.locks = {}
    key = str(root)
    if key in locks:
        yield
        return
    cache = root / ".zara-cache"
    _path(root, ".zara-cache/lock")
    cache.mkdir(exist_ok=True)
    with (cache / "lock").open("a+b") as stream:
        if stream.seek(0, 2) == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            posix_locks: Any = fcntl
            posix_locks.flock(stream.fileno(), posix_locks.LOCK_EX)
        locks[key] = True
        try:
            yield
        finally:
            del locks[key]
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                posix_locks.flock(stream.fileno(), posix_locks.LOCK_UN)


def _tables(db: sqlite3.Connection) -> dict[str, tuple[list[str], list[str]]]:
    result = {}
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        if name.startswith("sqlite_"):
            continue
        if not _identifier.fullmatch(name):
            raise StorageError("Unsupported installed table name")
        columns = db.execute(f'PRAGMA table_info("{name}")').fetchall()
        names = [row[1] for row in columns]
        keys = [row[1] for row in sorted(columns, key=lambda row: row[5]) if row[5]]
        if not keys or any(not _identifier.fullmatch(column) for column in names):
            raise StorageError("Storage needs explicit installed primary keys")
        result[name] = (names, keys)
    return result


def snapshot(db: sqlite3.Connection) -> Rows:
    result: Rows = {}
    for table, (columns, keys) in _tables(db).items():
        rows = result[table] = {}
        for values in db.execute(f'SELECT * FROM "{table}"'):
            row = dict(zip(columns, values, strict=True))
            key = json.dumps([row[column] for column in keys], ensure_ascii=False)
            rows[key] = row
    return result


def _encode(
    row: dict[str, Any], directory: Path, prefix: str, root: Path, table: str
) -> dict[str, Any]:
    result = {}
    for column, value in row.items():
        if table == "processes" and column == "location" and isinstance(value, str):
            location = Path(value)
            if location.is_absolute() and location.is_relative_to(root):
                value = {"relative_location": location.relative_to(root).as_posix()}
            else:
                value = {
                    "external_workspace": row["workspace_id"],
                    "original_location": value,
                    "origin_home": root.as_posix(),
                }
        if isinstance(value, bytes) or (
            isinstance(value, str) and column in ("body", "input", "result")
        ):
            raw = value if isinstance(value, bytes) else value.encode("utf-8")
            try:
                json.loads(raw)
                suffix = "json"
            except (ValueError, UnicodeDecodeError):
                try:
                    raw.decode("utf-8")
                    suffix = "txt"
                except UnicodeDecodeError:
                    suffix = "bin"
            relative = f"content/{prefix}-{column}.{suffix}"
            _write(directory / relative, raw)
            value = {
                "file": relative,
                "sha256": _digest(raw),
                "encoding": "bytes" if isinstance(value, bytes) else "utf8",
            }
        result[column] = value
    return result


def _decode(
    row: dict[str, Any], directory: Path, root: Path, inventory: dict[str, str]
) -> dict[str, Any]:
    result = {}
    for column, value in row.items():
        if isinstance(value, dict) and "file" in value:
            source = _path(directory, value["file"])
            raw = source.read_bytes()
            if _digest(raw) != value["sha256"] or value["encoding"] not in ("bytes", "utf8"):
                raise StorageError(f"Changed or damaged confirmed content: {source}")
            inventory[source.relative_to(root).as_posix()] = value["sha256"]
            value = raw if value["encoding"] == "bytes" else raw.decode("utf-8")
        elif isinstance(value, dict) and "relative_location" in value:
            value = _path(root, value["relative_location"]).as_posix()
        elif isinstance(value, dict) and "external_workspace" in value:
            mapping = root / ".zara-device.json"
            locations = json.loads(mapping.read_bytes()) if mapping.is_file() else {}
            fallback = (
                value["original_location"]
                if value.get("origin_home") == root.as_posix()
                else f"unmapped:{value['external_workspace']}"
            )
            value = locations.get(value["external_workspace"], fallback)
        if isinstance(value, (list, dict)):
            raise StorageError("Unknown encoded storage value")
        result[column] = value
    return result


def _load(
    root: Path, sources: dict[str, dict[str, dict[str, str]]] | None = None
) -> tuple[dict[str, Any], Rows, str]:
    data = _path(root, ".zara-data")
    head_raw = (data / "HEAD.json").read_bytes()
    head = json.loads(head_raw)
    if head.get("format") != 1 or head.get("kind") not in ("home", "workspace"):
        raise StorageError("Unsupported file storage format")
    inventory = {".zara-data/HEAD.json": _digest(head_raw)}
    pending = head["commit"]
    chain = []
    seen = set()
    while pending is not None:
        if pending["path"] in seen:
            raise StorageError("Cyclic confirmed history")
        seen.add(pending["path"])
        manifest_path = _path(data, pending["path"])
        raw = manifest_path.read_bytes()
        if _digest(raw) != pending["sha256"]:
            raise StorageError(f"Changed confirmed operation: {manifest_path}")
        inventory[manifest_path.relative_to(root).as_posix()] = pending["sha256"]
        manifest = json.loads(raw)
        if manifest.get("format") != 1:
            raise StorageError("Unsupported operation format")
        chain.append((manifest_path.parent, manifest))
        pending = manifest["parent"]
    rows: Rows = {}
    for directory, manifest in reversed(chain):
        for item in manifest["changes"]:
            path = _path(directory, item["file"])
            raw = path.read_bytes()
            if _digest(raw) != item["sha256"]:
                raise StorageError(f"Changed confirmed row: {path}")
            inventory[path.relative_to(root).as_posix()] = item["sha256"]
            change = json.loads(raw)
            table = rows.setdefault(change["table"], {})
            if change["row"] is None:
                if change["key"] not in table:
                    raise StorageError("Deletion refers to missing row")
                del table[change["key"]]
                if sources is not None:
                    sources.setdefault(change["table"], {}).pop(change["key"], None)
            else:
                table[change["key"]] = _decode(change["row"], directory, root, inventory)
                if sources is not None:
                    sources.setdefault(change["table"], {})[change["key"]] = {
                        column: _path(directory, value["file"]).relative_to(root).as_posix()
                        for column, value in change["row"].items()
                        if isinstance(value, dict) and "file" in value
                    }
    digest = _digest(_json(inventory))
    return head, rows, digest


def fingerprint(root: Path) -> str:
    try:
        return _load(root)[2]
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise StorageError(f"Cannot validate file storage: {error}") from error


def content_paths(root: Path) -> dict[str, dict[str, dict[str, str]]]:
    """Relative confirmed source paths for small, disposable navigation catalogs."""
    result: dict[str, dict[str, dict[str, str]]] = {}
    _load(root, result)
    return result


def set_location(root: Path, workspace_id: str, path: Path) -> None:
    with locked(root):
        target = root / ".zara-device.json"
        values = json.loads(target.read_bytes()) if target.exists() else {}
        values[workspace_id] = path.resolve().as_posix()
        _replace(target, _json(values))


def _publish(
    root: Path,
    kind: str,
    db: sqlite3.Connection,
    before: Rows,
    *,
    location_root: Path | None = None,
) -> None:
    after = snapshot(db)
    changes: list[tuple[str, str, dict[str, Any] | None]] = [
        (table, key, row)
        for table in sorted(before.keys() | after.keys())
        for key, row in sorted(after.get(table, {}).items())
        if before.get(table, {}).get(key) != row
    ]
    changes += [
        (table, key, None)
        for table in sorted(before)
        for key in sorted(before[table])
        if key not in after.get(table, {})
    ]
    data = root / ".zara-data"
    attributes = data / ".gitattributes"
    if not attributes.exists():
        _write(attributes, b"* -text\nHEAD.json -merge\n")
    prior = json.loads((data / "HEAD.json").read_bytes()) if (data / "HEAD.json").exists() else None
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if not changes and prior and prior["schema_version"] == version:
        return
    now = datetime.now(UTC)
    relative = f"operations/{now:%Y/%m}/{uuid4()}"
    directory = data / relative
    directory.mkdir(parents=True)
    items = []
    for index, (table, key, row) in enumerate(changes):
        prefix = f"{index:06d}"
        change = {
            "table": table,
            "key": key,
            "row": None
            if row is None
            else _encode(row, directory, prefix, location_root or root, table),
        }
        raw = _json(change)
        filename = prefix + ".json"
        _write(directory / filename, raw)
        items.append({"file": filename, "sha256": _digest(raw)})
    manifest = {
        "format": 1,
        "parent": prior["commit"] if prior else None,
        "recorded_at": now.isoformat(),
        "changes": items,
    }
    raw = _json(manifest)
    _write(directory / "operation.json", raw)
    head = {
        "format": 1,
        "kind": kind,
        "schema_version": version,
        "application_id": db.execute("PRAGMA application_id").fetchone()[0],
        "commit": {"path": relative + "/operation.json", "sha256": _digest(raw)},
    }
    _replace(data / "HEAD.json", _json(head))


def _rebuild(
    root: Path, factory: Factory, head: dict[str, Any], rows: Rows, database: Path
) -> None:
    temporary = database.with_name(uuid4().hex + ".sqlite3")
    with closing(sqlite3.connect(temporary, autocommit=True)) as db:
        factory(db, head["schema_version"])
        if db.execute("PRAGMA application_id").fetchone()[0] != head["application_id"]:
            raise StorageError("Storage identity does not match the installed schema")
        tables = _tables(db)
        if rows.keys() - tables.keys():
            raise StorageError("Storage contains unknown tables; install a compatible version")
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("BEGIN IMMEDIATE")
        for table in tables:
            db.execute(f'DELETE FROM "{table}"')
        for table, entries in rows.items():
            columns, keys = tables[table]
            for key, row in entries.items():
                if set(row) != set(columns) or key != json.dumps(
                    [row[k] for k in keys], ensure_ascii=False
                ):
                    raise StorageError("Row does not match its installed schema/key")
                names = ",".join(f'"{name}"' for name in columns)
                marks = ",".join("?" for _ in columns)
                db.execute(
                    f'INSERT INTO "{table}" ({names}) VALUES ({marks})',
                    [row[column] for column in columns],
                )
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise StorageError("Broken references in source files")
        db.execute("COMMIT")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise StorageError("Rebuilt cache failed integrity check")
    _move(temporary, database)


def _ensure(root: Path, factory: Factory, *, force: bool = False) -> Path:
    cache = root / ".zara-cache"
    database = cache / "state.sqlite3"
    verified = getattr(_local, "verified", None)
    head_bytes = (root / ".zara-data/HEAD.json").read_bytes()
    mapping = root / ".zara-device.json"
    mapping_bytes = mapping.read_bytes() if mapping.exists() else b""
    signature = (
        head_bytes,
        mapping_bytes,
        (database.stat().st_mtime_ns, database.stat().st_size) if database.is_file() else None,
    )
    if not force and verified is not None and verified.get(root) == signature:
        return database
    head, rows, digest = _load(root)
    stamp = cache / "source.json"
    expected = {"source": digest, "root": root.as_posix()}
    valid = False
    if database.is_file() and stamp.is_file() and not force:
        try:
            valid = json.loads(stamp.read_bytes()) == expected
            if valid:
                with closing(sqlite3.connect(database)) as db:
                    actual = {table: values for table, values in snapshot(db).items() if values}
                    expected_rows = {table: values for table, values in rows.items() if values}
                    valid = (
                        db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
                        and actual == expected_rows
                        and db.execute("PRAGMA user_version").fetchone()[0]
                        == head["schema_version"]
                        and db.execute("PRAGMA application_id").fetchone()[0]
                        == head["application_id"]
                    )
        except (OSError, ValueError, sqlite3.Error):
            valid = False
    if not valid:
        _rebuild(root, factory, head, rows, database)
        _replace(stamp, _json(expected))
    if verified is not None:
        verified[root] = (
            head_bytes,
            mapping_bytes,
            (database.stat().st_mtime_ns, database.stat().st_size),
        )
    return database


def activate(root: Path, database: Path, kind: str, factory: Factory) -> dict[str, Any]:
    """Explicit conversion of an already-backed-up DB; leave source removal to caller."""
    root = root.resolve()
    with locked(root):
        if not enabled(root):
            staging = root / ".zara-cache" / ("migration-" + uuid4().hex)
            staging.mkdir()
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
                original = snapshot(db)
                _publish(staging, kind, db, {}, location_root=root)
            with locked(staging):
                locations = {
                    row["workspace_id"]: row["location"]
                    for row in original.get("processes", {}).values()
                    if not Path(row["location"]).is_relative_to(root)
                }
                _replace(staging / ".zara-device.json", _json(locations))
                staged_db = _ensure(staging, factory, force=True)
                with closing(sqlite3.connect(staged_db)) as db:
                    rebuilt = snapshot(db)
                expected = {
                    table: {key: dict(row) for key, row in rows.items()}
                    for table, rows in original.items()
                }
                for row in expected.get("processes", {}).values():
                    location = Path(row["location"])
                    if location.is_relative_to(root):
                        row["location"] = (staging / location.relative_to(root)).as_posix()
                if rebuilt != expected:
                    raise StorageError("Staged conversion differs from original; no activation")
            if locations:
                _replace(root / ".zara-device.json", _json(locations))
            _move(staging / ".zara-data", root / ".zara-data")
            if not staging.resolve().is_relative_to((root / ".zara-cache").resolve()):
                raise StorageError("Unexpected migration staging location")
            shutil.rmtree(staging)
        if kind == "workspace":
            attributes = root / "artifacts/.gitattributes"
            if not attributes.exists():
                _write(attributes, b"* -text\n")
        _ensure(root, factory, force=True)
        return verify(root, factory)


@contextmanager
def connection(
    root: Path, factory: Factory, *, write: bool = False
) -> Iterator[tuple[sqlite3.Connection, Path]]:
    root = root.resolve()
    with locked(root):
        database = _ensure(root, factory)
        with closing(sqlite3.connect(database, autocommit=True, timeout=5)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            if not write:
                db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            before = snapshot(db) if write else {}
            confirmed = False
            try:
                yield db, database
                if write:
                    memo = getattr(_local, "verified", None)
                    if memo is not None:
                        memo.pop(root, None)
                    kind = json.loads((root / ".zara-data/HEAD.json").read_bytes())["kind"]
                    _publish(root, kind, db, before)
                    confirmed = True
                db.execute("COMMIT")
            except BaseException as error:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                if not confirmed or not isinstance(error, (OSError, sqlite3.Error)):
                    raise
                (root / ".zara-cache/source.json").unlink(missing_ok=True)
                _replace(
                    root / ".zara-cache/warning.json",
                    _json(
                        {
                            "committed": True,
                            "cache_warning": str(error),
                            "recovery": "Next operation rebuilds cache from confirmed files",
                        }
                    ),
                )
                return
            # The next request verifies all source bytes; stamp only follows committed cache.
            if write:
                try:
                    _replace(
                        root / ".zara-cache/source.json",
                        _json({"source": fingerprint(root), "root": root.as_posix()}),
                    )
                except OSError:
                    # A missing stamp forces rebuild. Confirmed files already own the result.
                    pass


def verify(root: Path, factory: Factory, *, rebuild: bool = False) -> dict[str, Any]:
    root = root.resolve()
    with locked(root):
        database = _ensure(root, factory, force=rebuild)
        head, rows, digest = _load(root)
        return {
            "format": head["format"],
            "kind": head["kind"],
            "source": digest,
            "tables": {name: len(values) for name, values in rows.items()},
            "cache": database.as_posix(),
            "verified": True,
        }
