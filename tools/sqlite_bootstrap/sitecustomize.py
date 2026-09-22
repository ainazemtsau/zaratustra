"""Load the explicit fixed SQLite DLL before development-tool plugins start."""

from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path

EXPECTED_VERSION = "3.53.3"
EXPECTED_SHA256 = "79FD9EC89DBA3F8BD64529A2CA8E9DDE6AE6EDC486C55A1D3F1CE77975A8375C"
ENVIRONMENT_NAME = "ZARATUSTRA_SQLITE_DLL"

_library: ctypes.CDLL | None = None


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest().upper()


def _load() -> None:
    global _library

    configured = os.environ.get(ENVIRONMENT_NAME)
    if not configured:
        return
    path = Path(configured).expanduser().resolve()
    if os.name != "nt" or not path.is_file() or path.name.casefold() != "sqlite3.dll":
        raise SystemExit(f"Invalid {ENVIRONMENT_NAME}: {path}")
    actual = _digest(path)
    if actual != EXPECTED_SHA256:
        raise SystemExit(f"Unsupported SQLite DLL hash: {actual}")
    try:
        _library = ctypes.WinDLL(str(path))
        import sqlite3
    except OSError as error:
        raise SystemExit(f"Cannot load configured SQLite DLL: {error}") from error
    if sqlite3.sqlite_version != EXPECTED_VERSION:
        raise SystemExit(
            f"Configured SQLite runtime is {sqlite3.sqlite_version}; expected {EXPECTED_VERSION}"
        )


_load()
