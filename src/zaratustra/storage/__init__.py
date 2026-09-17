"""File authority with disposable SQLite materializations; no domain policy."""

from .files import (
    StorageError,
    activate,
    connection,
    content_paths,
    enabled,
    fingerprint,
    locked,
    request_scoped,
    set_location,
    snapshot,
    verify,
)

__all__ = [
    "StorageError",
    "activate",
    "connection",
    "content_paths",
    "enabled",
    "fingerprint",
    "locked",
    "snapshot",
    "request_scoped",
    "set_location",
    "verify",
]
