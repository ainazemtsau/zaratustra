"""Public column projection preserves full reads, replay and fenced paging."""

from __future__ import annotations

import base64
import hashlib
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app import Coordinator
from zaratustra_core import CoreError, wire

from .support import fixture, inspect
from .test_contract import prepared


def test_default_page_token_and_old_command_replay_remain_unchanged(tmp_path: Path) -> None:
    core, owner, _ = fixture(tmp_path)
    original = owner.call("read_page", {"table": "heads", "limit": 1}, "old-page")
    expected = hashlib.sha256(wire(["heads", {}, 3]))
    for index, row in enumerate(
        [
            {
                "id": "method",
                "revision": 1,
                "kind": "method",
                "key": "conversation",
                "scope": "space",
            },
            {
                "id": "profile",
                "revision": 1,
                "kind": "profile",
                "key": "local-scripted",
                "scope": "space",
            },
            {
                "id": "memory",
                "revision": 1,
                "kind": "memory",
                "key": "preference",
                "scope": "space",
            },
        ],
        1,
    ):
        expected.update(b"\n" + wire({"_page_rowid": index, **row}))
    assert original["snapshot_revision"] == {"high_watermark": 3, "sha256": expected.hexdigest()}
    assert original["rows"] == inspect(core, "heads")[:1]
    assert "projection" not in original
    owner.call(
        "apply_changes",
        {
            "changes": [
                {"id": "extra", "kind": "data", "key": "extra", "body": "later"},
            ]
        },
        "later",
        expected_heads={"extra": 0},
    )
    assert owner.call("read_page", {"table": "heads", "limit": 1}, "old-page") == original
    with pytest.raises(CoreError, match="idempotency_conflict"):
        owner.call("read_page", {"table": "heads", "limit": 1, "columns": ["id"]}, "old-page")


@pytest.mark.parametrize(
    "columns",
    [
        [],
        None,
        ["id", "id"],
        ["credential"],
        ["rowid"],
        ["_page_rowid"],
        ["id, (SELECT hash FROM credentials)"],
        ["id FROM credentials --"],
        [1],
        "id",
    ],
)
def test_invalid_private_or_expression_columns_are_rejected(tmp_path: Path, columns: Any) -> None:
    _, owner, _ = fixture(tmp_path)
    with pytest.raises(CoreError, match="columns"):
        owner.call("read_page", {"table": "heads", "columns": columns}, "bad-columns")


@pytest.mark.parametrize(
    "change",
    [
        {"columns": ["work", "id"]},
        {"columns": ["id"]},
        {"columns": None},
        {"conversation": "elsewhere"},
        {"table": "waits"},
    ],
)
def test_projection_token_cannot_be_reused_for_other_columns_or_filters(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    _, owner, _, _ = prepared(tmp_path)
    payload: dict[str, Any] = {"table": "attempts", "columns": ["id", "work"], "limit": 1}
    first = owner.call("read_page", payload, "first")
    continuation = payload | {"snapshot_revision": first["snapshot_revision"]} | change
    if change == {"columns": None}:
        continuation.pop("columns")
    with pytest.raises(CoreError, match="snapshot_revision"):
        owner.call("read_page", continuation, "different-projection")


def test_coordinator_projection_preserves_cursor_and_rejects_hidden_prefix_changes(
    tmp_path: Path,
) -> None:
    core, owner, _ = fixture(tmp_path)
    coordinator = Coordinator(owner)
    full = coordinator.rows("messages", conversation="conversation")
    assert coordinator.rows("messages", conversation="conversation", columns=["seq"]) == [
        {"seq": row["seq"]} for row in full
    ]
    payload = {"table": "messages", "conversation": "conversation", "columns": ["seq"], "limit": 3}
    first = owner.call("read_page", payload, "first-message-page")
    second = owner.call(
        "read_page",
        payload
        | {
            "cursor": first["next_cursor"],
            "snapshot_revision": first["snapshot_revision"],
        },
        "second-message-page",
    )
    assert first["rows"] == [{"seq": n} for n in range(1, 4)]
    assert second["rows"] == [{"seq": n} for n in range(4, 7)]
    assert first["projection"] == {"columns": ["seq"], "full_rows": False}
    with sqlite3.connect(core.path) as db:
        db.execute("UPDATE messages SET raw='Y2hhbmdlZA==' WHERE seq=10")
    with pytest.raises(CoreError, match="snapshot_revision"):
        owner.call(
            "read_page",
            payload
            | {"cursor": second["next_cursor"], "snapshot_revision": second["snapshot_revision"]},
            "hidden-field-changed",
        )


def test_compact_observation_reads_keep_body_retained_without_copying_it_to_receipts(
    tmp_path: Path,
) -> None:
    core, owner, _, _ = prepared(tmp_path)
    raw = base64.b64encode(("fictional retained bytes " * 20_000).encode()).decode()
    owner.call("claim_dispatch", {"attempt_id": "A1", "generation": 1}, "claim", action_id="action")
    owner.call(
        "observe_attempt",
        {"attempt_id": "A1", "event_id": "large", "kind": "progress", "raw_base64": raw},
        "large-observation",
    )
    before = inspect(core, "observations")
    full = owner.call("read_page", {"table": "observations"}, "full")
    projected = owner.call(
        "read_page", {"table": "observations", "columns": ["attempt", "event"]}, "compact"
    )
    assert projected["rows"] == [{"attempt": "A1", "event": "large"}]
    assert len(wire(projected)) < 1000
    assert len(wire(full)) > 500_000
    assert inspect(core, "observations") == before
    with sqlite3.connect(core.path) as db:
        sizes = dict(
            db.execute(
                "SELECT command,length(response) FROM receipts WHERE command IN ('full','compact')"
            )
        )
    assert sizes["compact"] < 1500
    assert sizes["full"] > 500_000
    assert raw in full["rows"][0]["body"]


def test_public_contract_discovers_supported_columns_without_exposing_private_tables(
    tmp_path: Path,
) -> None:
    _, owner, _ = fixture(tmp_path)
    contract = owner.call("describe_contract", {}, "contract")
    projection = contract["read_page"]
    assert projection["columns_optional"] is True
    assert projection["max_rows_per_page"] == 100
    assert {"id", "work", "body"} <= set(projection["columns"]["attempts"])
    assert {"attempt", "fingerprint", "body"} <= set(projection["columns"]["results"])
    assert not {"credentials", "rights", "receipts", "events"} & set(projection["columns"])
    for table, columns in projection["columns"].items():
        page = owner.call("read_page", {"table": table, "columns": columns}, "declared-" + table)
        assert page["projection"]["columns"] == columns
        assert all(set(row) == set(columns) for row in page["rows"])
