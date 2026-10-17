"""Explicit bounded projections; retained history remains the SQLite authority."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Mapping
from typing import Any, NoReturn

from .shapes import Ref
from .types import CoreError, wire

TABLES = {
    "heads",
    "works",
    "attempts",
    "messages",
    "conversations",
    "waits",
    "results",
    "observations",
    "actions",
    "intents",
    "tool_calls",
    "acceptance",
}
PUBLIC_COLUMNS = {
    "heads": {"id", "revision", "kind", "key", "scope"},
    "works": {"id", "revision", "conversation", "status", "generation", "body", "reserved"},
    "attempts": {
        "id",
        "work",
        "conversation",
        "status",
        "generation",
        "original_cursor",
        "cutoff",
        "body",
    },
    "messages": {"conversation", "seq", "event", "fingerprint", "raw", "origin", "reply"},
    "conversations": {"id", "cursor"},
    "waits": {"id", "revision", "conversation", "work", "status", "body"},
    "results": {"attempt", "slot", "fingerprint", "body"},
    "observations": {"attempt", "event", "fingerprint", "body"},
    "actions": {"id", "attempt", "executor", "state", "correlation", "reserve"},
    "intents": {"kind", "subject", "body"},
    "tool_calls": {"attempt", "native_id", "command", "action", "receipt"},
    "acceptance": {"attempt", "slot", "result_hash", "principal"},
}
DIRECT = {
    "conversation": {"messages", "works", "attempts", "waits"},
    "work": {"attempts", "waits"},
    "scope": {"heads"},
}
VIA_ATTEMPT = {"results", "observations", "actions", "tool_calls", "acceptance"}


def invalid(field: str) -> NoReturn:
    raise CoreError("invalid_request", field)


def read_page(db: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    """Page a table's fenced prefix; unrelated writes and later appends are safe."""
    table = payload.get("table")
    if table not in TABLES:
        invalid("table")
    columns = payload.get("columns")
    if "columns" in payload and (
        not isinstance(columns, list)
        or not columns
        or any(type(column) is not str or column not in PUBLIC_COLUMNS[table] for column in columns)
        or len(set(columns)) != len(columns)
    ):
        invalid("columns")
    cursor, limit = payload.get("cursor", 0), payload.get("limit", 100)
    if type(cursor) is not int or cursor < 0:
        invalid("cursor")
    if type(limit) is not int or not 1 <= limit <= 100:
        invalid("limit")
    supplied = payload.get("snapshot_revision")
    if supplied is not None and (
        not isinstance(supplied, dict)
        or set(supplied) != {"high_watermark", "sha256"}
        or type(supplied.get("high_watermark")) is not int
        or supplied["high_watermark"] < 0
        or not isinstance(supplied.get("sha256"), str)
        or len(supplied["sha256"]) != 64
    ):
        invalid("snapshot_revision")
    if cursor and supplied is None:
        invalid("snapshot_revision")
    conditions: list[str] = []
    values: list[Any] = []
    filters: dict[str, str] = {}
    for name in ("conversation", "work", "scope"):
        value = payload.get(name)
        if value is None:
            continue
        if not isinstance(value, str) or not value:
            invalid(name)
        if table in DIRECT[name]:
            conditions.append("t." + name + "=?")
        elif name == "conversation" and table == "conversations":
            conditions.append("t.id=?")
        elif name == "work" and table == "works":
            conditions.append("t.id=?")
        elif name in {"conversation", "work"} and table in VIA_ATTEMPT:
            conditions.append(
                "EXISTS (SELECT 1 FROM attempts a WHERE a.id=t.attempt AND a." + name + "=?)"
            )
        else:
            invalid(name + ".table")
        values.append(value)
        filters[name] = value
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    high = (
        supplied["high_watermark"]
        if supplied is not None
        else db.execute(
            "SELECT COALESCE(MAX(t.rowid),0) FROM " + table + " t" + where, values
        ).fetchone()[0]
    )
    prefix_where = where + (" AND " if conditions else " WHERE ") + "t.rowid<=?"
    fingerprint = hashlib.sha256(wire([table, filters, high]))
    if columns is not None:
        fingerprint.update(b"\ncolumns:" + wire(columns))
    total = 0
    for row in db.execute(
        "SELECT t.rowid AS _page_rowid,t.* FROM "
        + table
        + " t"
        + prefix_where
        + " ORDER BY t.rowid",
        [*values, high],
    ):
        fingerprint.update(b"\n" + wire(dict(row)))
        total += 1
    revision = {"high_watermark": high, "sha256": fingerprint.hexdigest()}
    if supplied is not None and supplied != revision:
        raise CoreError("stale_basis", "snapshot_revision", "after_refresh")
    page_where = prefix_where + " AND t.rowid>?"
    rows = db.execute(
        "SELECT t.rowid AS _page_rowid,"
        + ("t.*" if columns is None else ",".join("t." + column for column in columns))
        + " FROM "
        + table
        + " t"
        + page_where
        + " ORDER BY t.rowid LIMIT ?",
        [*values, high, cursor, limit + 1],
    ).fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = rows[-1]["_page_rowid"] if more else None
    projected = [{k: row[k] for k in row.keys() if k != "_page_rowid"} for row in rows]
    result = {
        "rows": projected,
        "next_cursor": next_cursor,
        "has_more": more,
        "snapshot_revision": revision,
        "coverage": {
            "table": table,
            "total_rows": total,
            "returned_rows": len(projected),
            "selection": "rowid_page",
            "complete": cursor == 0 and not more,
            "snapshot_high_watermark": high,
            "snapshot_scope": "table and filters; later rows require a fresh snapshot",
        },
    }
    if columns is not None:
        result["projection"] = {"columns": columns, "full_rows": False}
    return result


def select_context(
    db: sqlite3.Connection,
    work: Mapping[str, Any],
    selection: dict[str, Any],
    *,
    cursor: int | None = None,
    exact: Callable[[sqlite3.Connection, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Materialize only owner/client-named optional context, never semantic ranking."""
    allowed = {"catalog_refs", "prior_message_sequences", "prior_result_attempts", "prior_wait_ids"}
    if set(selection) - allowed:
        invalid("context_selection")
    for name in allowed:
        values = selection.get(name, [])
        if not isinstance(values, list) or len(values) > 100:
            invalid("context_selection." + name)
        if name != "catalog_refs":
            expected = int if name == "prior_message_sequences" else str
            if any(type(value) is not expected for value in values):
                invalid("context_selection." + name)
            if len(set(values)) != len(values):
                invalid("context_selection." + name)
    conversation = work["conversation"]
    if cursor is None:
        cursor = db.execute(
            "SELECT cursor FROM conversations WHERE id=?", (conversation,)
        ).fetchone()[0]
    selected: dict[str, Any] = {
        "catalog": [],
        "prior_messages": [],
        "prior_results": [],
        "prior_waits": [],
    }
    refs = selection.get("catalog_refs", [])
    seen: set[tuple[str, int]] = set()
    for ref in refs:
        Ref.model_validate(ref)
        key = (ref["id"], ref["revision"])
        if key in seen:
            invalid("context_selection.catalog_refs")
        seen.add(key)
        row = db.execute(
            "SELECT r.* FROM records r JOIN heads h ON h.id=r.id AND h.revision=r.revision "
            "WHERE r.id=? AND r.revision=?",
            key,
        ).fetchone()
        if row is None:
            invalid("context_selection.catalog_refs")
        if exact is not None:
            exact(db, ref)
        selected["catalog"].append(dict(row))
    for seq in selection.get("prior_message_sequences", []):
        if type(seq) is not int or seq < 1 or seq > cursor:
            invalid("context_selection.prior_message_sequences")
        row = db.execute(
            "SELECT * FROM messages WHERE conversation=? AND seq=?", (conversation, seq)
        ).fetchone()
        if row is None:
            invalid("context_selection.prior_message_sequences")
        selected["prior_messages"].append(dict(row))
    for attempt in selection.get("prior_result_attempts", []):
        if not isinstance(attempt, str) or not attempt:
            invalid("context_selection.prior_result_attempts")
        rows = db.execute(
            "SELECT r.* FROM results r JOIN attempts a ON a.id=r.attempt "
            "WHERE a.id=? AND a.conversation=? AND a.cutoff<=? ORDER BY r.rowid",
            (attempt, conversation, cursor),
        ).fetchall()
        if not rows:
            invalid("context_selection.prior_result_attempts")
        selected["prior_results"].extend(dict(row) for row in rows)
    for wait_id in selection.get("prior_wait_ids", []):
        if not isinstance(wait_id, str) or not wait_id:
            invalid("context_selection.prior_wait_ids")
        row = db.execute(
            "SELECT * FROM waits WHERE id=? AND conversation=?", (wait_id, conversation)
        ).fetchone()
        if row is None:
            invalid("context_selection.prior_wait_ids")
        wait_attempt = json.loads(row["body"]).get("attempt_id")
        if wait_attempt is not None:
            source = db.execute(
                "SELECT 1 FROM attempts WHERE id=? AND conversation=? AND cutoff<=?",
                (wait_attempt, conversation, cursor),
            ).fetchone()
            if source is None:
                invalid("context_selection.prior_wait_ids")
        selected["prior_waits"].append(dict(row))
    counts = {
        "catalog": db.execute("SELECT COUNT(*) FROM heads").fetchone()[0],
        "prior_messages": db.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation=? AND seq<=?", (conversation, cursor)
        ).fetchone()[0],
        "prior_results": db.execute(
            "SELECT COUNT(*) FROM results r JOIN attempts a ON a.id=r.attempt "
            "WHERE a.conversation=? AND a.cutoff<=?",
            (conversation, cursor),
        ).fetchone()[0],
        "prior_waits": db.execute(
            "SELECT COUNT(*) FROM waits WHERE conversation=?", (conversation,)
        ).fetchone()[0],
    }
    selected["context_coverage"] = {
        "mode": "explicit",
        "selection": json.loads(json.dumps(selection)),
        "total_rows": counts,
        "selected_rows": {k: len(selected[k]) for k in counts},
        "excluded_history": "retained; not inspected or summarized by this selection",
    }
    return selected
