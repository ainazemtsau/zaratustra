"""Admission of the one supported SQLite runtime before importing ``sqlite3``."""

from __future__ import annotations

import ctypes
import hashlib
import os
import sys
from pathlib import Path

EXPECTED_SQLITE_VERSION = "3.53.3"
EXPECTED_WINDOWS_DLL_SHA256 = "79FD9EC89DBA3F8BD64529A2CA8E9DDE6AE6EDC486C55A1D3F1CE77975A8375C"
SQLITE_DLL_ENV = "ZARATUSTRA_SQLITE_DLL"

_loaded_library: ctypes.CDLL | None = None


class RuntimeConfigurationError(RuntimeError):
    """The process does not provide the fixed SQLite contract required by Core."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _load_configured_windows_library() -> None:
    global _loaded_library

    configured = os.environ.get(SQLITE_DLL_ENV)
    if not configured:
        return
    if os.name != "nt":
        raise RuntimeConfigurationError(
            f"{SQLITE_DLL_ENV} is supported only for the admitted Windows runtime"
        )
    path = Path(configured).expanduser().resolve()
    if not path.is_file() or path.name.casefold() != "sqlite3.dll":
        raise RuntimeConfigurationError(f"Invalid configured SQLite library: {path}")
    actual = _sha256(path)
    if actual != EXPECTED_WINDOWS_DLL_SHA256:
        raise RuntimeConfigurationError(
            f"Unsupported SQLite DLL hash: {actual}; expected {EXPECTED_WINDOWS_DLL_SHA256}"
        )
    try:
        _loaded_library = ctypes.WinDLL(str(path))
    except OSError as error:
        raise RuntimeConfigurationError(f"Cannot load configured SQLite DLL: {error}") from error


def ensure_sqlite_runtime() -> None:
    """Load and validate the fixed runtime; calling twice is safe."""

    if "sqlite3" not in sys.modules:
        _load_configured_windows_library()

    import sqlite3

    if sqlite3.sqlite_version != EXPECTED_SQLITE_VERSION:
        detail = ""
        if SQLITE_DLL_ENV not in os.environ:
            detail = f"; set {SQLITE_DLL_ENV} before process start on Windows"
        raise RuntimeConfigurationError(
            "Unsupported SQLite runtime: "
            f"{sqlite3.sqlite_version}; expected {EXPECTED_SQLITE_VERSION}{detail}"
        )
    try:
        with sqlite3.connect(":memory:") as connection:
            fts5 = connection.execute("SELECT sqlite_compileoption_used('ENABLE_FTS5')").fetchone()
    except sqlite3.Error as error:
        raise RuntimeConfigurationError(f"Cannot inspect SQLite runtime: {error}") from error
    if fts5 != (1,):
        raise RuntimeConfigurationError("Supported SQLite runtime must include FTS5")


__all__ = [
    "EXPECTED_SQLITE_VERSION",
    "EXPECTED_WINDOWS_DLL_SHA256",
    "RuntimeConfigurationError",
    "SQLITE_DLL_ENV",
    "ensure_sqlite_runtime",
]
