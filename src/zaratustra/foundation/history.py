"""Managed Pi session history inside one Core space."""

from __future__ import annotations

import importlib
import os
import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from .storage import STATE_DIRECTORY, FoundationError, layout

HISTORY_DIRECTORY = "pi-sessions"
HISTORY_MARKER = "owner.txt"
LOCK_BYTES = 4096
EXECUTOR_START_BYTE = LOCK_BYTES


def _check_plain(path: Path) -> None:
    if path.is_symlink() or path.is_junction():
        raise FoundationError(
            "history_layout", f"Managed Pi history must not contain links: {path}"
        )


@contextmanager
def managed_pi_lock(path: Path) -> Iterator[None]:
    """Keep Pi writes and Core deletion maintenance mutually exclusive."""

    root, _, _ = layout(path)
    marker = root / STATE_DIRECTORY / "pi-owner.lock"
    _check_plain(marker)
    try:
        opened = marker.open("a+b")
    except OSError as error:
        raise FoundationError("history_busy", "Pi owns this Core space") from error
    with opened as handle:
        try:
            handle.seek(0)
            if not handle.read(1):
                handle.seek(0)
                handle.write(bytes([0]))
                handle.flush()
        except OSError as error:
            raise FoundationError("history_busy", "Pi owns this Core space") from error
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, LOCK_BYTES)
            except OSError as error:
                raise FoundationError("history_busy", "Pi owns this Core space") from error
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, LOCK_BYTES)
        else:
            fcntl = importlib.import_module("fcntl")
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise FoundationError("history_busy", "Pi owns this Core space") from error
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def managed_pi_session_lock(path: Path) -> Iterator[None]:
    """Allow concurrent Pi sessions while still excluding deletion maintenance."""

    root, _, _ = layout(path)
    marker = root / STATE_DIRECTORY / "pi-owner.lock"
    _check_plain(marker)
    try:
        opened = marker.open("a+b")
    except OSError as error:
        raise FoundationError("history_busy", "Cannot open managed Pi lock") from error
    with opened as handle:
        if os.name == "nt":
            import msvcrt

            for _ in range(LOCK_BYTES - 1):
                position = secrets.randbelow(LOCK_BYTES - 1) + 1
                handle.seek(position)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    continue
                try:
                    yield
                finally:
                    handle.seek(position)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                return
            raise FoundationError("history_busy", "Pi lock is held by maintenance")
        fcntl = importlib.import_module("fcntl")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError as error:
            raise FoundationError("history_busy", "Pi lock is held by maintenance") from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def managed_executor_start_lock(path: Path) -> Iterator[None]:
    """Serialize DBOS SQLite startup across assigned runners in one Core space.

    A runner holds its ordinary Pi session lock around this short startup lock, so
    maintenance remains excluded while DBOS creates or migrates its database.
    """

    root, _, _ = layout(path)
    marker = root / STATE_DIRECTORY / "pi-owner.lock"
    _check_plain(marker)
    try:
        opened = marker.open("a+b")
    except OSError as error:
        raise FoundationError("history_busy", "Cannot open DBOS startup lock") from error
    with opened as handle:
        deadline = time.monotonic() + 30
        if os.name == "nt":
            import msvcrt

            while True:
                handle.seek(EXECUTOR_START_BYTE)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if time.monotonic() >= deadline:
                        raise FoundationError(
                            "history_busy", "DBOS startup is held by another runner"
                        ) from error
                    time.sleep(0.05)
            try:
                yield
            finally:
                handle.seek(EXECUTOR_START_BYTE)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl = importlib.import_module("fcntl")
            while True:
                try:
                    fcntl.lockf(
                        handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB, 1, EXECUTOR_START_BYTE
                    )
                    break
                except OSError as error:
                    if time.monotonic() >= deadline:
                        raise FoundationError(
                            "history_busy", "DBOS startup is held by another runner"
                        ) from error
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.lockf(handle.fileno(), fcntl.LOCK_UN, 1, EXECUTOR_START_BYTE)


def managed_pi_sessions(path: Path, space_id: UUID, *, create: bool = False) -> Path:
    """Resolve and validate the adapter-owned Pi JSONL directory."""

    root, _, _ = layout(path)
    directory = root / STATE_DIRECTORY / HISTORY_DIRECTORY
    _check_plain(directory)
    if create:
        directory.mkdir(exist_ok=True)
    if not directory.exists():
        return directory
    if not directory.is_dir():
        raise FoundationError("history_layout", "Pi history path is not a directory")
    marker = directory / HISTORY_MARKER
    _check_plain(marker)
    expected = f"zaratustra-core:{space_id}\n"
    if create and not marker.exists() and not any(directory.iterdir()):
        marker.write_text(expected, encoding="utf-8", newline="\n")
    if not marker.is_file() or marker.read_text(encoding="utf-8") != expected:
        raise FoundationError("history_layout", "Pi history does not belong to this Core space")
    return directory


def purge_managed_pi_sessions(path: Path, space_id: UUID) -> None:
    """Retire every adapter-created session after any Core content deletion."""

    directory = managed_pi_sessions(path, space_id)
    if not directory.exists():
        return
    files: list[Path] = []
    folders: list[Path] = []
    pending = [directory]
    while pending:
        current = pending.pop()
        for entry in current.iterdir():
            _check_plain(entry)
            if entry == directory / HISTORY_MARKER:
                continue
            if entry.is_dir():
                pending.append(entry)
                folders.append(entry)
            elif entry.is_file():
                files.append(entry)
            else:
                raise FoundationError("history_layout", f"Unsupported Pi history entry: {entry}")
    for entry in files:
        entry.unlink()
    for entry in sorted(folders, key=lambda value: len(value.parts), reverse=True):
        entry.rmdir()
