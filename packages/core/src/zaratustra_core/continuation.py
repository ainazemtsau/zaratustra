"""Verified late Work succession and immutable, attributed Sleep source ranges."""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from .shapes import SleepProgress, SleepProgressV2
from .types import CoreError, digest

if TYPE_CHECKING:
    from .api import Core

END_INDEX = 2147483647


def require(ok: bool, field: str, code: str = "invalid_request") -> None:
    if not ok:
        raise CoreError(code, field)


def progress_shape(value: dict[str, Any]) -> None:
    try:
        model = SleepProgressV2 if value.get("format") == "sleep-progress/v2" else SleepProgress
        model.model_validate(value)
    except ValidationError as error:
        raise CoreError("invalid_request", "progress.shape") from error


def protocol(db: sqlite3.Connection) -> None:
    require(
        db.execute("PRAGMA user_version").fetchone()[0] == 1,
        "continuation.protocol",
        "unsupported_capability",
    )


def successor(db: sqlite3.Connection, attempt_id: str) -> bool:
    return any(
        json.loads(row[0]).get("continuation", {}).get("attempt_id") == attempt_id
        for row in db.execute("SELECT body FROM works")
    )


def late_work(
    core: Core, db: sqlite3.Connection, body: dict[str, Any], command: str
) -> dict[str, Any]:
    protocol(db)
    child = dict(body)
    basis = child.pop("continuation_from")
    attempt, parent = core._attempt(db, basis["attempt_id"])
    result = db.execute(
        "SELECT * FROM results WHERE attempt=? AND slot='final'", (attempt["id"],)
    ).fetchone()
    require(parent["revision"] == basis["work_revision"], "continuation.work", "stale_basis")
    latest = db.execute(
        "SELECT id FROM attempts WHERE work=? ORDER BY rowid DESC LIMIT 1", (parent["id"],)
    ).fetchone()
    require(
        parent["status"] == "completed"
        and attempt["status"] == "finished"
        and latest is not None
        and latest[0] == attempt["id"]
        and result is not None,
        "continuation.completed",
        "stale_basis",
    )
    assert result is not None
    outcome = json.loads(result["body"])
    require(
        result["fingerprint"] == basis["result_hash"] and outcome["state"] == "completed",
        "continuation.result",
        "stale_basis",
    )
    require(
        not successor(db, attempt["id"]) and not outcome.get("next_work_id"),
        "continuation.successor",
        "identity_conflict",
    )
    require(
        child["id"] != parent["id"]
        and child["conversation"] == parent["conversation"]
        and child.get("scope", "space") == json.loads(parent["body"]).get("scope", "space"),
        "continuation.scope",
    )
    require(
        not db.execute(
            "SELECT 1 FROM works WHERE conversation=? AND status NOT IN ('completed','cancelled')",
            (parent["conversation"],),
        ).fetchone(),
        "continuation.active",
        "identity_conflict",
    )
    require(
        not db.execute(
            "SELECT 1 FROM actions a JOIN attempts t ON t.id=a.attempt "
            "WHERE t.work=? AND a.state NOT IN ('terminal','not_received')",
            (parent["id"],),
        ).fetchone(),
        "continuation.actions",
        "outcome_unknown",
    )
    require(
        not db.execute(
            "SELECT 1 FROM tool_calls c JOIN attempts t ON t.id=c.attempt "
            "WHERE t.work=? AND c.action IS NOT NULL AND c.receipt IS NULL",
            (parent["id"],),
        ).fetchone(),
        "continuation.tools",
        "outcome_unknown",
    )
    refs = []
    require(
        len({r["id"] for r in basis["basis_refs"]}) == len(basis["basis_refs"]),
        "continuation.basis_refs",
    )
    for ref in basis["basis_refs"]:
        require(ref.get("role") == "must_be_current", "continuation.basis_role")
        record = core._exact(db, ref)
        require(
            record["scope"] in {"space", child.get("scope", "space")}, "continuation.basis_scope"
        )
        value = record["body"]["value"]
        if isinstance(value, dict) and value.get("format") in {
            "sleep-progress/v1",
            "sleep-progress/v2",
        }:
            require(value["work_id"] == parent["id"], "continuation.progress_work")
            core._progress(db, value, record["scope"], None)
            if value["format"] == "sleep-progress/v2":
                progress_proof(core, db, value, record["scope"])
        refs.append({"id": ref["id"], "revision": ref["revision"], "role": "exact"})
    parent_limit = json.loads(parent["body"])["call_limit"]
    remaining = None if parent_limit is None else parent_limit - parent["reserved"]
    require(remaining is None or remaining > 0, "continuation.calls", "resource_exhausted")
    require(
        remaining is None
        or child.get("call_limit") is not None
        and child["call_limit"] <= remaining,
        "continuation.calls",
        "resource_exhausted",
    )
    action = db.execute("SELECT reserve FROM actions WHERE attempt=?", (attempt["id"],)).fetchone()
    require(action is not None, "continuation.action")
    link = {
        "kind": "late",
        "attempt_id": attempt["id"],
        "parent_work_id": parent["id"],
        "parent_work_revision": parent["revision"],
        "result_hash": result["fingerprint"],
        "basis_refs": refs,
        "receipt_id": command,
        "delivered_cutoff": attempt["cutoff"],
        "processed_cutoff": outcome["cutoff"],
        "parent_reserved": parent["reserved"],
        "resource_upper": action[0],
    }
    if child.get("scope", "space") != "space":
        activity = db.execute(
            "SELECT id,revision FROM heads WHERE id=? AND kind='activity'", (child["scope"],)
        ).fetchone()
        require(activity is not None, "continuation.activity_scope")
        link["activity_ref"] = {"id": activity["id"], "revision": activity["revision"]}
    return dict(core._work(db, child, continuation=link), continuation=link)


def analysis_owner(core: Core, db: sqlite3.Connection, ref: dict[str, Any]) -> str | None:
    event = db.execute(
        "SELECT e.* FROM events e WHERE e.kind IN ('apply_changes','commit_outcome') "
        "AND EXISTS (SELECT 1 FROM json_each(e.body,'$.refs') r "
        "WHERE json_extract(r.value,'$.id')=? AND json_extract(r.value,'$.revision')=?) "
        "ORDER BY e.seq LIMIT 1",
        (ref["id"], ref["revision"]),
    ).fetchone()
    if event is None:
        return None
    if event["kind"] == "commit_outcome":
        return str(core._attempt(db, json.loads(event["body"])["attempt_id"])[1]["id"])
    tool = db.execute(
        "SELECT t.work FROM tool_calls c JOIN attempts t ON t.id=c.attempt WHERE c.receipt=?",
        (event["subject"],),
    ).fetchone()
    return str(tool[0]) if tool else ""


def own_evidence(
    core: Core, db: sqlite3.Connection, value: dict[str, Any], *, allow_pending: bool = False
) -> list[dict[str, Any]]:
    delivered: list[dict[str, Any]] = []
    for manifest in value["delivered_manifest_refs"]:
        attempt, work = core._attempt(db, manifest["attempt_id"])
        materials = json.loads(attempt["body"]).get("sleep_sources", [])
        require(
            work["id"] == value["work_id"] and digest(materials) == manifest["sha256"],
            "progress.delivery",
            "stale_basis",
        )
        observed = [
            json.loads(r[0])
            for r in db.execute("SELECT body FROM observations WHERE attempt=?", (attempt["id"],))
        ]
        require(
            any(o["kind"] == "terminal" and not o["late"] for o in observed),
            "progress.unobserved_delivery",
        )
        delivered.extend(m["source_ref"] for m in materials)
    analysed = []
    for ref in value["analysis_result_refs"]:
        record = core._exact(db, dict(ref, role="exact"))
        analysis = record["body"]["value"]
        if value["format"] == "sleep-progress/v2":
            owner = analysis_owner(core, db, ref)
            require(
                owner == value["work_id"] or owner is None and allow_pending,
                "progress.analysis_owner",
            )
        require(
            isinstance(analysis, dict) and analysis.get("format") == "sleep-analysis/v1",
            "progress.analysis",
        )
        require(isinstance(analysis.get("sources"), list), "progress.analysis_sources")
        for source_ref in analysis["sources"]:
            try:
                material = core._source(db, source_ref)
            except ValidationError as error:
                raise CoreError("invalid_request", "progress.analysis_source") from error
            require(
                value["scope"] == "space" or material["scope"] == value["scope"],
                "progress.analysis_scope",
            )
        require(
            all(digest(source) in {digest(r) for r in delivered} for source in analysis["sources"]),
            "progress.analysis_delivery",
        )
        analysed.extend(analysis["sources"])
    for receipt in value["applied_receipts"]:
        event = db.execute(
            "SELECT * FROM events WHERE subject=? AND kind IN ('apply_changes','commit_outcome')",
            (receipt,),
        ).fetchone()
        result = json.loads(event["body"]) if event else {}
        tool = db.execute(
            "SELECT t.work FROM tool_calls c JOIN attempts t ON t.id=c.attempt WHERE c.receipt=?",
            (receipt,),
        ).fetchone()
        outcome_work = (
            core._attempt(db, result["attempt_id"])[1]["id"]
            if event and event["kind"] == "commit_outcome"
            else None
        )
        require(
            bool(result.get("refs"))
            and (
                outcome_work == value["work_id"]
                or tool is not None
                and tool["work"] == value["work_id"]
            ),
            "progress.receipt",
        )
    return analysed


def progress_proof(
    core: Core,
    db: sqlite3.Connection,
    value: dict[str, Any],
    scope: str,
    *,
    pending_work: str | None = None,
) -> dict[str, Any]:
    """Historical proof: exact lineage/evidence only, never current resource/head CAS."""
    chain = [value]
    seen = {value["work_id"]}
    while chain[-1].get("format") == "sleep-progress/v2":
        current = chain[-1]
        progress_shape(current)
        ref = current["predecessor_ref"]
        require(ref.get("role", "exact") == "exact", "progress.predecessor_role")
        record = core._exact(db, dict(ref, role="exact"))
        previous = record["body"]["value"]
        require(
            record["kind"] == "data"
            and record["scope"] == scope
            and isinstance(previous, dict)
            and previous.get("format") in {"sleep-progress/v1", "sleep-progress/v2"},
            "progress.predecessor",
        )
        require(previous["work_id"] not in seen, "progress.cycle")
        seen.add(previous["work_id"])
        work = db.execute("SELECT body FROM works WHERE id=?", (current["work_id"],)).fetchone()
        require(work is not None, "progress.work")
        link = json.loads(work[0]).get("continuation", {})
        require(
            link.get("kind") == "late"
            and link.get("parent_work_id") == previous["work_id"]
            and any(
                r["id"] == ref["id"] and r["revision"] == ref["revision"]
                for r in link.get("basis_refs", [])
            ),
            "progress.predecessor_lineage",
        )
        attempt, parent = core._attempt(db, link["attempt_id"])
        result = db.execute(
            "SELECT fingerprint,body FROM results WHERE attempt=? AND slot='final'",
            (attempt["id"],),
        ).fetchone()
        require(
            parent["id"] == previous["work_id"]
            and result is not None
            and result["fingerprint"] == link["result_hash"]
            and json.loads(result["body"])["state"] == "completed",
            "progress.predecessor_result",
        )
        chain.append(previous)
    analysed: list[dict[str, Any]] = []
    previous = None
    start = [0, 0]
    for current in reversed(chain):
        progress_shape(current)
        require(current["scope"] == scope, "progress.scope")
        work = db.execute("SELECT body FROM works WHERE id=?", (current["work_id"],)).fetchone()
        require(
            work is not None and json.loads(work[0]).get("scope", "space") == scope,
            "progress.work_scope",
        )
        method = core._exact(db, dict(current["method_ref"], role="exact"))
        require(
            method["kind"] == "method" and method["scope"] in {"space", scope}, "progress.method"
        )
        require(
            current["source_high_watermark"]
            <= db.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0],
            "progress.high_watermark",
        )
        inherited = analysed
        if previous is not None:
            if current["transition"] == "same_window":
                require(
                    current["range_start"] == start
                    and current["source_high_watermark"] == previous["source_high_watermark"]
                    and current["enumeration_cursor"] >= previous["enumeration_cursor"]
                    and all(
                        r in current["enumerated_source_refs"]
                        for r in previous["enumerated_source_refs"]
                    ),
                    "progress.boundary",
                    "stale_basis",
                )
            else:
                require(
                    previous["enumeration_cursor"] == [previous["source_high_watermark"], END_INDEX]
                    and not previous["remaining_refs"]
                    and all(r in inherited for r in previous["enumerated_source_refs"]),
                    "progress.predecessor_incomplete",
                )
                start = [previous["source_high_watermark"], END_INDEX]
                require(
                    current["range_start"] == start
                    and current["source_high_watermark"] >= start[0],
                    "progress.range_start",
                )
                inherited = []
        cursor = current["enumeration_cursor"]
        require(
            start <= cursor and cursor[0] <= current["source_high_watermark"],
            "progress.enumeration_cursor",
        )
        prefix = [
            item["source_ref"]
            for item in core._history_items(db, current["source_high_watermark"], scope, start)
            if [item["source_ref"]["sequence"], item["source_ref"]["index"]] <= cursor
        ]
        require(current["enumerated_source_refs"] == prefix, "progress.enumeration_prefix")
        require(
            all(r in prefix for r in current["selected_source_refs"] + current["remaining_refs"]),
            "progress.selection",
        )
        analysed = inherited + own_evidence(
            core, db, current, allow_pending=current["work_id"] == pending_work
        )
        require(
            all(r in analysed or r in current["remaining_refs"] for r in prefix),
            "progress.remainder",
        )
        previous = current
    return {"analysed": analysed, "range_start": start}


def current_progress(
    core: Core, db: sqlite3.Connection, value: dict[str, Any], scope: str, head: sqlite3.Row | None
) -> None:
    protocol(db)
    progress_shape(value)
    work = db.execute("SELECT * FROM works WHERE id=?", (value["work_id"],)).fetchone()
    require(
        work is not None and json.loads(work["body"])["method_ref"] == value["method_ref"],
        "progress.method",
        "stale_basis",
    )
    require(
        value["source_high_watermark"]
        <= db.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0],
        "progress.high_watermark",
    )
    if head:
        old = core._exact(db, {"id": head["id"], "revision": head["revision"]})["body"]["value"]
        require(old.get("format") == "sleep-progress/v2", "progress.format")
        for field in (
            "work_id",
            "predecessor_ref",
            "transition",
            "range_start",
            "source_high_watermark",
        ):
            require(old[field] == value[field], "progress.boundary", "stale_basis")
        require(
            old["enumeration_cursor"] <= value["enumeration_cursor"],
            "progress.boundary",
            "stale_basis",
        )
        require(
            all(
                item in value[field]
                for field in (
                    "enumerated_source_refs",
                    "delivered_manifest_refs",
                    "analysis_result_refs",
                    "applied_receipts",
                )
                for item in old[field]
            ),
            "progress.history",
            "stale_basis",
        )
    actions = list(
        db.execute(
            "SELECT a.* FROM actions a JOIN attempts t ON t.id=a.attempt WHERE t.work=?",
            (work["id"],),
        )
    )
    unresolved = sorted(a["id"] for a in actions if a["state"] not in {"terminal", "not_received"})
    require(
        value["consumed_resource"] == work["reserved"]
        and sorted(value["unresolved_calls"]) == unresolved,
        "progress.resource",
        "stale_basis",
    )
    progress_proof(core, db, value, scope, pending_work=value["work_id"])
