"""Bounded deterministic structural retrieval over selected scopes only."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from .types import JournalError, Reference, Revision, canonical

if TYPE_CHECKING:
    from .store import Store


def card(record: Revision) -> dict[str, Any]:
    occurred = record.payload.get("occurred_at") if record.type_name == "episode" else None
    return {
        "id": str(record.id),
        "revision": record.revision,
        "title": record.title,
        "type_name": record.type_name,
        "state": record.state,
        "date": occurred or record.recorded_at.isoformat(),
        "date_source": "occurred_at" if occurred else "recorded_at",
        "category": record.payload.get("category") if record.type_name == "episode" else None,
        **record.metadata.model_dump(mode="json"),
        "reference": record.reference().model_dump(mode="json"),
    }


def _date(value: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise JournalError("invalid_date", "Search dates require a timezone")
    return parsed.astimezone(UTC).isoformat()


def retrieve(
    stores: list[Store],
    query: str,
    *,
    type_name: str | None = None,
    state: str | None = None,
    linked_to: Reference | None = None,
    limit: int = 20,
    offset: int = 0,
    category: str | None = None,
    problem_status: str | None = None,
    document_purpose: UUID | None = None,
    tags_all: tuple[UUID, ...] = (),
    tags_any: tuple[UUID, ...] = (),
    date_from: str | None = None,
    date_to: str | None = None,
    history: bool = False,
    generation: str | None = None,
) -> dict[str, Any]:
    if not 1 <= limit <= 100 or offset < 0 or len(query) > 128:
        raise JournalError("invalid_query", "Bounded query/page required")
    records = [
        r
        for store in stores
        for current in store.current()
        for r in (store.history(current.id) if history else [current])
    ]
    records.sort(key=lambda r: (str(r.scope.id), str(r.id), r.revision))
    digest = hashlib.sha256(canonical([r.model_dump(mode="json") for r in records])).hexdigest()
    if generation is not None and generation != digest:
        raise JournalError("search_changed", "Selected data changed; restart the paginated search")
    if offset and generation is None:
        raise JournalError("missing_generation", "Continue with the generation from the first page")
    selection = hashlib.sha256(
        canonical([s.scope.model_dump(mode="json") for s in stores])
    ).hexdigest()
    database: Any = ":memory:"
    if stores:
        cache = stores[0].path / ".zara-cache"
        cache.mkdir(exist_ok=True)
        database = cache / f"search-{selection[:16]}-{int(history)}.sqlite3"
    try:
        connection = sqlite3.connect(database)
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            connection.close()
            raise sqlite3.DatabaseError("Damaged search cache")
    except sqlite3.DatabaseError:
        if database != ":memory:":
            database.unlink(missing_ok=True)
        connection = sqlite3.connect(database)
    with closing(connection) as db:
        db.execute("CREATE TABLE IF NOT EXISTS generation (value TEXT)")
        saved = db.execute("SELECT value FROM generation").fetchone()
        if saved != (digest,):
            db.execute("DROP TABLE IF EXISTS records")
            db.execute("DROP TABLE IF EXISTS text_search")
            db.execute(
                "CREATE TABLE records (id TEXT PRIMARY KEY, type TEXT, state TEXT, "
                "category TEXT, problem_status TEXT, purpose TEXT, date TEXT, "
                "tags TEXT, links TEXT, card TEXT)"
            )
            db.execute(
                "CREATE INDEX properties ON records(type,state,category,problem_status,date)"
            )
            db.execute(
                "CREATE VIRTUAL TABLE text_search USING fts5(title,body,tokenize='unicode61')"
            )
            for index, record in enumerate(records, start=1):
                value = card(record)
                stamp = datetime.fromisoformat(value["date"])
                # Legacy naive occurred_at remains readable; use recorded time for ordering.
                if stamp.tzinfo is None:
                    stamp = record.recorded_at
                    value["date"] = stamp.isoformat()
                    value["date_source"] = "recorded_at"
                identity = (
                    f"{record.scope.kind}:{record.scope.id}:{record.id}:{record.revision:09d}"
                )
                db.execute(
                    "INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        identity,
                        record.type_name,
                        record.state,
                        value["category"],
                        value["problem_status"],
                        value["document_purpose"],
                        stamp.astimezone(UTC).isoformat(),
                        json.dumps(value["tags"]),
                        json.dumps(
                            [r.model_dump(mode="json") for r in record.links], sort_keys=True
                        ),
                        json.dumps(value, ensure_ascii=False),
                    ),
                )
                payload = {k: v for k, v in record.payload.items() if k != "base64"}
                db.execute(
                    "INSERT INTO text_search(rowid,title,body) VALUES (?,?,?)",
                    (index, record.title, json.dumps(payload, ensure_ascii=False)),
                )
            db.execute("DELETE FROM generation")
            db.execute("INSERT INTO generation VALUES (?)", (digest,))
            db.commit()
        clauses: list[str] = []
        args: list[Any] = []
        for column, filter_value in (
            ("type", type_name),
            ("state", state),
            ("category", category),
            ("purpose", str(document_purpose) if document_purpose else None),
        ):
            if filter_value is not None:
                clauses.append(f"r.{column}=?")
                args.append(filter_value)
        if problem_status is not None:
            clauses.append(
                "r.problem_status IS NULL" if problem_status == "unknown" else "r.problem_status=?"
            )
            if problem_status != "unknown":
                args.append(problem_status)
        for tag in tags_all:
            clauses.append("EXISTS(SELECT 1 FROM json_each(r.tags) WHERE value=?)")
            args.append(str(tag))
        if tags_any:
            clauses.append(
                "EXISTS(SELECT 1 FROM json_each(r.tags) WHERE value IN ("
                + ",".join("?" for _ in tags_any)
                + "))"
            )
            args.extend(str(tag) for tag in tags_any)
        if linked_to:
            clauses.append("EXISTS(SELECT 1 FROM json_each(r.links) WHERE json(value)=json(?))")
            args.append(json.dumps(linked_to.model_dump(mode="json"), sort_keys=True))
        start, end = _date(date_from) if date_from else None, _date(date_to) if date_to else None
        if start and end and start >= end:
            raise JournalError("invalid_date_range", "Start must precede exclusive end")
        for operator, bound in ((">=", start), ("<", end)):
            if bound:
                clauses.append(f"r.date {operator} ?")
                args.append(bound)
        terms = "".join(c if c.isalnum() else " " for c in query).split()
        if terms:
            clauses.append("text_search MATCH ?")
            args.append(" OR ".join('"' + term + '"*' for term in terms))
        where = " AND ".join(clauses) or "1"
        order = "bm25(text_search),r.date DESC,r.id" if terms else "r.date DESC,r.id"
        rows = db.execute(
            "SELECT r.card,substr(text_search.body,1,320) FROM records r "
            "JOIN text_search ON text_search.rowid=r.rowid WHERE "
            + where
            + " ORDER BY "
            + order
            + " LIMIT ? OFFSET ?",
            [*args, limit + 1, offset],
        ).fetchall()
    return {
        "matches": [json.loads(row[0]) | {"snippet": row[1]} for row in rows[:limit]],
        "generation": digest,
        "next_offset": offset + limit if len(rows) > limit else None,
        "query": query,
        "limit": limit,
        "offset": offset,
        "method": "structured filters + FTS5 unicode61 literal prefix terms OR",
        "limitation": "No Russian morphology or semantic guarantee; "
        "no match is not proof of absence.",
    }
