"""Durable immutable bytes and process-scoped maintenance exclusion."""

from __future__ import annotations

import hashlib
import importlib
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .types import CoreError


@contextmanager
def exclusion(root: Path) -> Iterator[None]:
    """No lock survives a process crash; idle clients hold no lock or transaction."""
    with (root / "maintenance.lock").open("a+b") as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        deadline = time.monotonic() + 5
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl: Any = importlib.import_module("fcntl")
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if time.monotonic() >= deadline:
                    raise CoreError("resource_exhausted", "maintenance", "same_id") from error
                time.sleep(0.01)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def durable(path: Path, raw: bytes) -> None:
    """Publish a complete synchronized file, then synchronize its directory on POSIX."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".staging-" + os.urandom(8).hex())
    try:
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if temporary.read_bytes() != raw:
            raise CoreError("invalid_request", "artifact.integrity")
        os.replace(temporary, path)
        if os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def verified(root: Path, sha256: str, size: int) -> bytes:
    if (
        not isinstance(sha256, str)
        or re.fullmatch("[0-9a-f]{64}", sha256) is None
        or type(size) is not int
        or size < 0
    ):
        raise CoreError("invalid_request", "artifact.identity")
    try:
        raw = (root / "artifacts" / sha256).read_bytes()
    except OSError as error:
        raise CoreError("invalid_request", "artifact.missing") from error
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != sha256:
        raise CoreError("invalid_request", "artifact.integrity")
    return raw
