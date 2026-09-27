"""Selecting a restored space preserves the already selected operation history."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from zaratustra.release import _preserves_operations


def _history(root: Path, fingerprint: str | None) -> None:
    database = root / ".zara-core" / "core.sqlite3"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE operations(operation_id TEXT PRIMARY KEY, fingerprint TEXT)"
        )
        if fingerprint is not None:
            connection.execute("INSERT INTO operations VALUES ('operation-1',?)", (fingerprint,))


def test_restored_selection_keeps_each_exact_operation(tmp_path: Path) -> None:
    original, restored = tmp_path / "original", tmp_path / "restored"
    _history(original, "original-fingerprint")
    _history(restored, "original-fingerprint")
    _preserves_operations(original, restored)
    with sqlite3.connect(restored / ".zara-core" / "core.sqlite3") as connection:
        connection.execute("UPDATE operations SET fingerprint='changed'")
    with pytest.raises(ValueError, match="omits or changes operation"):
        _preserves_operations(original, restored)
    with sqlite3.connect(restored / ".zara-core" / "core.sqlite3") as connection:
        connection.execute("DELETE FROM operations")
    with pytest.raises(ValueError, match="omits or changes operation"):
        _preserves_operations(original, restored)
