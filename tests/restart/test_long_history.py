"""Explicit bounded context and stable paging retain a long Activity's full history."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from zaratustra_core import Core, CoreError

from .support import PROFILE, fixture


def long_history(tmp_path: Path) -> tuple[Core, Any, dict[str, Any]]:
    core, owner, _ = fixture(tmp_path)
    raw = base64.b64encode(b"exact pending owner input").decode()
    with sqlite3.connect(core.path) as db:
        db.execute("UPDATE conversations SET cursor=1020 WHERE id='conversation'")
        db.executemany(
            "INSERT INTO messages VALUES('conversation',?,?,?,?,'human',NULL)",
            [(n, f"old-{n}", f"hash-{n}", raw) for n in range(21, 1022)],
        )
        db.executemany(
            "INSERT INTO attempts VALUES(?,'work','conversation','completed',1,0,1,'{}')",
            [(f"old-{n}",) for n in range(1001)],
        )
        db.executemany(
            "INSERT INTO results VALUES(?,'final',?,?)",
            [(f"old-{n}", f"hash-{n}", json.dumps({"text": f"retained-{n}"})) for n in range(1001)],
        )
        db.executemany(
            "INSERT INTO records VALUES(?,1,'data',?,'space',?)",
            [(f"record-{n}", f"key-{n}", json.dumps({"value": f"exact-{n}"})) for n in range(1001)],
        )
        db.executemany(
            "INSERT INTO heads VALUES(?,1,'data',?,'space')",
            [(f"record-{n}", f"key-{n}") for n in range(1001)],
        )
    return (
        core,
        owner,
        {
            "id": "next",
            "work_id": "work",
            "work_revision": 1,
            "original_cursor": 1020,
            "cutoff": 1021,
            "message_sequences": [1021],
            "manifest": [
                {"sequence": 1021, "sha256": hashlib.sha256(base64.b64decode(raw)).hexdigest()}
            ],
            "profile_ref": PROFILE,
        },
    )


def test_explicit_context_continues_same_activity_without_dropping_mandatory_inputs(
    tmp_path: Path,
) -> None:
    core, owner, request = long_history(tmp_path)
    with pytest.raises(CoreError, match="context.max_rows"):
        owner.call("prepare_attempt", request, "unbounded-prepare")
    selection = {
        "catalog_refs": [{"id": f"record-{n}", "revision": 1} for n in range(100)],
        "prior_message_sequences": list(range(1, 101)),
        "prior_result_attempts": [f"old-{n}" for n in range(100)],
    }
    pinned = owner.call(
        "prepare_attempt", request | {"context_selection": selection}, "bounded-prepare"
    )["pinned"]
    assert pinned["work"]["id"] == "work"
    assert pinned["work"]["conversation"] == "conversation"
    assert pinned["messages"][0]["seq"] == 1021
    assert base64.b64decode(pinned["messages"][0]["raw"]) == b"exact pending owner input"
    assert pinned["inputs"][0]["body"]["value"] == "Keep practice brief."
    assert pinned["method"]["id"] == "method"
    assert pinned["profile"]["id"] == "profile"
    assert [r["seq"] for r in pinned["prior_messages"]] == list(range(1, 101))
    assert len(pinned["prior_results"]) == len(pinned["catalog"]) == 100
    assert pinned["context_coverage"]["total_rows"] == {
        "catalog": 1004,
        "prior_messages": 1020,
        "prior_results": 1001,
        "prior_waits": 0,
    }
    assert "not inspected" in pinned["context_coverage"]["excluded_history"]
    for table, expected in (("messages", 1021), ("results", 1001), ("heads", 1004)):
        found: list[dict[str, Any]] = []
        payload: dict[str, Any] = {"table": table, "limit": 100}
        while True:
            page = owner.call("read_page", payload, f"page:{table}:{len(found)}")
            found.extend(page["rows"])
            if not page["has_more"]:
                break
            payload |= {
                "cursor": page["next_cursor"],
                "snapshot_revision": page["snapshot_revision"],
            }
        assert len(found) == expected
        if table == "messages":
            assert [r["seq"] for r in found] == list(range(1, 1022))
        if table == "results":
            assert {r["attempt"] for r in found} == {f"old-{n}" for n in range(1001)}
    assert (
        Core(core.root)
        .connect(owner.token)
        .call(
            "read_exact",
            {"id": "record-1000", "revision": 1},
            "excluded-exact",
        )["body"]["value"]
        == "exact-1000"
    )


@pytest.mark.parametrize(
    "selection",
    [
        {"catalog_refs": [{"id": "missing", "revision": 1}]},
        {"prior_message_sequences": [1021]},
        {"prior_result_attempts": ["foreign"]},
        {"prior_wait_ids": ["foreign-wait"]},
        {"prior_message_sequences": [1, 1]},
    ],
)
def test_explicit_selection_rejects_missing_foreign_pending_or_duplicate_history(
    tmp_path: Path, selection: dict[str, Any]
) -> None:
    core, owner, request = long_history(tmp_path)
    with sqlite3.connect(core.path) as db:
        db.execute("INSERT INTO conversations VALUES('other',0)")
        db.execute("INSERT INTO attempts VALUES('foreign','work','other','completed',1,0,0,'{}')")
        db.execute("INSERT INTO results VALUES('foreign','final','hash','{}')")
        db.execute("INSERT INTO waits VALUES('foreign-wait',1,'other','work','waiting','{}')")
    with pytest.raises(CoreError, match="context_selection"):
        owner.call(
            "prepare_attempt", request | {"context_selection": selection}, "invalid-selection"
        )


def test_page_mutation_fence_ignores_reads_but_rejects_changed_history(tmp_path: Path) -> None:
    _, owner, _ = long_history(tmp_path)
    first = owner.call(
        "read_page", {"table": "messages", "conversation": "conversation", "limit": 3}, "first-page"
    )
    owner.call("read_exact", PROFILE, "intervening-read")
    payload = {
        "table": "messages",
        "conversation": "conversation",
        "limit": 3,
        "cursor": first["next_cursor"],
        "snapshot_revision": first["snapshot_revision"],
    }
    second = owner.call("read_page", payload, "second-page")
    assert [row["seq"] for row in second["rows"]] == [4, 5, 6]
    owner.call(
        "ingest_message",
        {"conversation": "conversation", "event_id": "later", "raw_base64": "bGF0ZXI="},
        "intervening-write",
    )
    third = owner.call("read_page", payload | {"cursor": second["next_cursor"]}, "third-page")
    assert third["snapshot_revision"] == first["snapshot_revision"]
    assert third["coverage"]["total_rows"] == 1021
    assert [row["seq"] for row in third["rows"]] == [7, 8, 9]
    heads = owner.call("read_page", {"table": "heads", "limit": 1}, "heads-before")
    owner.call(
        "apply_changes",
        {"changes": [{"id": "memory", "kind": "memory", "key": "preference", "body": "Changed"}]},
        "change-prefix-head",
        expected_heads={"memory": 1},
    )
    with pytest.raises(CoreError, match="snapshot_revision"):
        owner.call(
            "read_page",
            {
                "table": "heads",
                "cursor": heads["next_cursor"],
                "snapshot_revision": heads["snapshot_revision"],
            },
            "stale-page",
        )


def test_native_read_pages_survive_normal_tool_execution_observations(tmp_path: Path) -> None:
    from zaratustra_app.native_session import NativeSession

    core, token = Core.initialize(tmp_path / "native")
    session = NativeSession(core, token, "fictional-paging-session")
    session.input("fictional-input", "Inspect fictional retained history")
    for index in range(3):
        session.observation(f"initial-{index}", {"type": "tool_execution_end", "toolName": "read"})

    def page(table: str, suffix: str, **continuation: Any) -> dict[str, Any]:
        return session.tool(
            "read",
            "read-" + suffix,
            {
                "operation": "read_page",
                "arguments": {"table": table, "limit": 1, **continuation},
            },
        )

    for table in ("heads", "observations"):
        first = page(table, table + "-first")
        assert first["has_more"]
        session.observation(
            table + "-read-end",
            {
                "type": "tool_execution_end",
                "toolName": "zara_read",
                "toolCallId": table + "-first",
                "result": first,
            },
        )
        second = page(
            table,
            table + "-second",
            cursor=first["next_cursor"],
            snapshot_revision=first["snapshot_revision"],
        )
        assert second["snapshot_revision"] == first["snapshot_revision"]
        assert second["coverage"]["total_rows"] == first["coverage"]["total_rows"]
        assert second["rows"] != first["rows"]
        retained = list(first["rows"]) + list(second["rows"])
        while second["has_more"]:
            second = page(
                table,
                table + "-" + str(len(retained)),
                cursor=second["next_cursor"],
                snapshot_revision=first["snapshot_revision"],
            )
            retained.extend(second["rows"])
        assert len(retained) == first["coverage"]["total_rows"]
        if table == "observations":
            assert not any(row["event"] == table + "-read-end" for row in retained)
            fresh = session.owner.call(
                "read_page", {"table": table, "limit": 100}, "fresh-observations"
            )
            assert any(row["event"] == table + "-read-end" for row in fresh["rows"])


def test_page_prefix_rejects_deletion_and_token_reuse_for_other_filters(tmp_path: Path) -> None:
    core, owner, _ = long_history(tmp_path)
    first = owner.call("read_page", {"table": "heads", "scope": "space", "limit": 1}, "first")
    continuation = {
        "table": "heads",
        "scope": "space",
        "cursor": first["next_cursor"],
        "snapshot_revision": first["snapshot_revision"],
    }
    with pytest.raises(CoreError, match="snapshot_revision"):
        owner.call("read_page", continuation | {"scope": "other"}, "changed-filter")
    with pytest.raises(CoreError, match="snapshot_revision"):
        owner.call(
            "read_page",
            {
                "table": "works",
                "cursor": first["next_cursor"],
                "snapshot_revision": first["snapshot_revision"],
            },
            "changed-table",
        )
    with sqlite3.connect(core.path) as db:
        db.execute("DELETE FROM heads WHERE id='record-1000'")
    with pytest.raises(CoreError, match="snapshot_revision"):
        owner.call("read_page", continuation, "deleted-prefix")


@pytest.mark.parametrize(
    "payload",
    [
        {"table": "credentials"},
        {"table": "heads;DROP TABLE heads"},
        {"table": "heads", "conversation": "conversation"},
        {"table": "messages", "scope": "space"},
        {"table": "heads", "limit": 101},
        {"table": "messages", "cursor": 1},
    ],
)
def test_paging_rejects_unsupported_table_filter_or_bounds(
    tmp_path: Path, payload: dict[str, Any]
) -> None:
    _, owner, _ = fixture(tmp_path)
    with pytest.raises(CoreError):
        owner.call("read_page", payload, "bad-page")
