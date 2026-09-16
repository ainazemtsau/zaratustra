"""SQLite Home Registry with bounded discovery and transactional local receipts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from zaratustra.core import Process, WorkspaceError, read_records

APPLICATION_ID = 0x5A484F4D
SCHEMA = (
    "CREATE TABLE home (id TEXT PRIMARY KEY, created_at TEXT NOT NULL) STRICT",
    """CREATE TABLE processes (
        id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL UNIQUE,
        location TEXT NOT NULL UNIQUE, name TEXT NOT NULL, name_key TEXT NOT NULL,
        cached_title TEXT, cached_revision INTEGER,
        observed_at TEXT
    ) STRICT""",
    "CREATE INDEX processes_name ON processes(name_key)",
    """CREATE TABLE aliases (
        name TEXT NOT NULL, name_key TEXT NOT NULL, process_id TEXT NOT NULL
        REFERENCES processes(id), PRIMARY KEY(name_key, process_id)
    ) STRICT""",
    """CREATE TABLE groups (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE
    ) STRICT""",
    """CREATE TABLE members (
        group_id TEXT NOT NULL REFERENCES groups(id),
        process_id TEXT NOT NULL REFERENCES processes(id),
        PRIMARY KEY(group_id, process_id)
    ) STRICT""",
    "CREATE INDEX members_process ON members(process_id)",
    """CREATE TABLE relations (
        id TEXT PRIMARY KEY, source TEXT NOT NULL REFERENCES processes(id),
        target TEXT NOT NULL REFERENCES processes(id), type TEXT NOT NULL,
        UNIQUE(source, target, type)
    ) STRICT""",
    "CREATE INDEX relations_target ON relations(target)",
    """CREATE TABLE operations (
        id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, action TEXT NOT NULL,
        input TEXT NOT NULL, result TEXT NOT NULL, recorded_at TEXT NOT NULL
    ) STRICT""",
    "CREATE TABLE imports (source TEXT PRIMARY KEY, sha256 TEXT NOT NULL) STRICT",
)


class HomeError(WorkspaceError):
    def __init__(self, code: str, detail: str, *, choices: tuple[dict[str, Any], ...] = ()):
        self.code = code
        self.choices = choices
        super().__init__(f"{code}: {detail}")


def _name(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 128:
        raise HomeError("invalid_name", "Use a nonempty name of at most 128 characters")
    return value


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _aliases(values: tuple[str, ...]) -> tuple[str, ...]:
    if len(values) > 32:
        raise HomeError("invalid_aliases", "Use at most 32 aliases")
    return tuple({_name(value).casefold(): _name(value) for value in values}.values())


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _database(home: Path) -> Path:
    root = home.expanduser().resolve()
    directory = root / ".zara-home"
    database = directory / "registry.sqlite3"
    if directory.is_symlink() or directory.is_junction() or database.is_symlink():
        raise HomeError("invalid_home", "Home database must not be a link")
    return database


@contextmanager
def _connect(home: Path, *, write: bool = False) -> Iterator[sqlite3.Connection]:
    database = _database(home)
    try:
        with closing(
            sqlite3.connect(
                database.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                uri=True,
                autocommit=True,
                timeout=5,
            )
        ) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            if not write:
                connection.execute("PRAGMA query_only=ON")
            if (
                connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
                or connection.execute("PRAGMA user_version").fetchone()[0] != 1
                or connection.execute("SELECT COUNT(*) FROM home").fetchone()[0] != 1
            ):
                raise HomeError("invalid_home", "Unknown or incomplete Home database")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield connection
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
    except (OSError, sqlite3.Error) as error:
        raise HomeError("home_unavailable", str(error)) from error


def init_home(home: Path) -> dict[str, Any]:
    """Explicitly prepare Home in a chosen existing directory; preserve other files."""
    root = home.expanduser().resolve()
    if not root.is_dir():
        raise HomeError("invalid_home", "Choose an existing directory")
    database = _database(root)
    if database.exists():
        return read_home(root)
    if database.parent.exists():
        raise HomeError("incomplete_home", "Reserved Home folder exists; inspect it before retry")
    database.parent.mkdir()
    with database.open("xb"):
        pass
    with closing(sqlite3.connect(database, autocommit=True)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in SCHEMA:
                connection.execute(statement)
            connection.execute("INSERT INTO home VALUES (?, ?)", (str(uuid4()), _now()))
            connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
            connection.execute("PRAGMA user_version=1")
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
    return read_home(root)


def read_home(home: Path) -> dict[str, Any]:
    with _connect(home) as connection:
        return dict(connection.execute("SELECT * FROM home").fetchone()) | {
            "path": home.expanduser().resolve().as_posix(),
            "schema": 1,
        }


def _mutate(
    home: Path,
    action: str,
    payload: dict[str, Any],
    operation_id: UUID,
    apply: Callable[[sqlite3.Connection], dict[str, Any]],
) -> dict[str, Any]:
    body = _json(payload)
    fingerprint = hashlib.sha256(_json([action, payload]).encode()).hexdigest()
    with _connect(home, write=True) as connection:
        prior = connection.execute(
            "SELECT fingerprint, result FROM operations WHERE id=?", (str(operation_id),)
        ).fetchone()
        if prior is not None:
            if prior["fingerprint"] != fingerprint:
                raise HomeError("operation_conflict", "Operation id was used for different content")
            result: dict[str, Any] = json.loads(prior["result"])
            return result
        result = apply(connection)
        connection.execute(
            "INSERT INTO operations VALUES (?, ?, ?, ?, ?, ?)",
            (str(operation_id), fingerprint, action, body, _json(result), _now()),
        )
        return result


def inspect_source(workspace: Path) -> dict[str, Any]:
    snapshot = read_records(workspace)
    process = next((row for row in snapshot.records if isinstance(row, Process)), None)
    if process is None:
        raise HomeError("no_process", "Selected workspace has no Process")
    return {
        "id": str(process.id),
        "workspace_id": str(snapshot.workspace_id),
        "title": process.title,
        "purpose": process.purpose,
        "revision": snapshot.state_revision,
        "location": workspace.expanduser().resolve().as_posix(),
    }


def reserve_creation(home: Path, intent: dict[str, Any], *, operation_id: UUID) -> dict[str, Any]:
    """Bind the creation id before effects in the separate Process database.

    This is a retained command intent, not a registration or cached Process state.
    It makes changed-location retries refuse before creating a second workspace.
    """
    return _mutate(home, "process.create", intent, operation_id, lambda connection: intent)


def reserve_catalog_import(
    home: Path, source: Path, digest: str, *, operation_id: UUID
) -> dict[str, Any]:
    intent = {"source": source.resolve().as_posix(), "sha256": digest}
    return _mutate(home, "catalog.import.intent", intent, operation_id, lambda connection: intent)


def _insert_process(
    connection: sqlite3.Connection,
    source: dict[str, Any],
    name: str,
    aliases: tuple[str, ...],
) -> dict[str, Any]:
    existing = connection.execute("SELECT * FROM processes WHERE id=?", (source["id"],)).fetchone()
    if existing is not None:
        if (
            existing["workspace_id"] != source["workspace_id"]
            or existing["location"] != source["location"]
        ):
            raise HomeError(
                "registration_conflict", "Use explicit relocation for an existing Process"
            )
        aliases = (*aliases, name) if name != existing["name"] else aliases
    else:
        connection.execute(
            "INSERT INTO processes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source["id"],
                source["workspace_id"],
                source["location"],
                name,
                name.casefold(),
                source.get("title"),
                source.get("revision"),
                _now() if source.get("revision") is not None else None,
            ),
        )
    for alias in aliases:
        connection.execute(
            "INSERT OR IGNORE INTO aliases VALUES (?, ?, ?)",
            (alias, alias.casefold(), source["id"]),
        )
    return dict(
        connection.execute("SELECT * FROM processes WHERE id=?", (source["id"],)).fetchone()
    )


def register_process(
    home: Path,
    workspace: Path,
    *,
    operation_id: UUID,
    name: str | None = None,
    aliases: tuple[str, ...] = (),
) -> dict[str, Any]:
    source = inspect_source(workspace)
    designation = _name(name or source["title"])
    clean_aliases = _aliases(aliases)
    return _mutate(
        home,
        "register",
        {
            "process_id": source["id"],
            "workspace_id": source["workspace_id"],
            "location": source["location"],
            "name": designation,
            "aliases": clean_aliases,
        },
        operation_id,
        lambda connection: _insert_process(connection, source, designation, clean_aliases),
    )


def _resolve(connection: sqlite3.Connection, selector: str) -> dict[str, Any]:
    exact = connection.execute("SELECT * FROM processes WHERE id=?", (selector,)).fetchone()
    if exact is not None:
        return dict(exact)
    rows = connection.execute(
        """SELECT DISTINCT p.* FROM processes p LEFT JOIN aliases a ON a.process_id=p.id
        WHERE p.id=? OR p.name_key=? OR a.name_key=? ORDER BY p.id LIMIT 21""",
        (selector, selector.strip().casefold(), selector.strip().casefold()),
    ).fetchall()
    if not rows:
        raise HomeError("process_not_found", "No registered Process matches this name")
    if len(rows) != 1:
        raise HomeError(
            "ambiguous_name",
            "Choose a Process explicitly",
            choices=tuple(
                {"id": row["id"], "name": row["name"], "location": row["location"]} for row in rows
            ),
        )
    return dict(rows[0])


def resolve_process(home: Path, selector: str) -> dict[str, Any]:
    with _connect(home) as connection:
        row = _resolve(connection, selector)
    return _observe(row)


def _observe(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["cache"] = {
        "title": row["cached_title"],
        "revision": row["cached_revision"],
        "observed_at": row["observed_at"],
    }
    try:
        source = inspect_source(Path(row["location"]))
        if (source["id"], source["workspace_id"]) != (row["id"], row["workspace_id"]):
            result.update(availability="mismatched", current=None)
        else:
            result.update(availability="available", current=source, checked_at=_now())
    except (OSError, ValueError, WorkspaceError) as error:
        result.update(availability="unavailable", current=None, error=str(error))
    return result


def _page(limit: int, offset: int) -> None:
    if type(limit) is not int or type(offset) is not int or not 1 <= limit <= 100 or offset < 0:
        raise HomeError("invalid_page", "Limit must be 1..100 and offset nonnegative")


def _group(connection: sqlite3.Connection, selector: str) -> dict[str, Any]:
    exact = connection.execute("SELECT * FROM groups WHERE id=?", (selector,)).fetchone()
    if exact is not None:
        return dict(exact)
    row = connection.execute(
        "SELECT * FROM groups WHERE id=? OR name_key=?", (selector, selector.strip().casefold())
    ).fetchone()
    if row is None:
        raise HomeError("group_not_found", "No such group")
    return dict(row)


def list_processes(
    home: Path,
    *,
    query: str = "",
    group: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    _page(limit, offset)
    if len(query) > 128:
        raise HomeError("invalid_query", "Search query is too long")
    with _connect(home) as connection:
        group_id = _group(connection, group)["id"] if group is not None else None
        rows = connection.execute(
            """SELECT DISTINCT p.* FROM processes p LEFT JOIN aliases a ON a.process_id=p.id
            WHERE (instr(p.name_key, ?) > 0 OR instr(COALESCE(a.name_key, ''), ?) > 0)
            AND (? IS NULL OR EXISTS(
                SELECT 1 FROM members m WHERE m.process_id=p.id AND m.group_id=?))
            ORDER BY p.name_key, p.id LIMIT ? OFFSET ?""",
            (query.casefold(), query.casefold(), group_id, group_id, limit, offset),
        ).fetchall()
    return [_observe(dict(row)) for row in rows]


def relocate_process(
    home: Path, selector: str, workspace: Path, *, operation_id: UUID
) -> dict[str, Any]:
    source = inspect_source(workspace)

    def apply(connection: sqlite3.Connection) -> dict[str, Any]:
        old = _resolve(connection, selector)
        if (old["id"], old["workspace_id"]) != (source["id"], source["workspace_id"]):
            raise HomeError("identity_mismatch", "New location contains a different Process")
        connection.execute(
            "UPDATE processes SET location=?, cached_title=?, cached_revision=?, observed_at=? "
            "WHERE id=?",
            (source["location"], source["title"], source["revision"], _now(), old["id"]),
        )
        return dict(
            connection.execute("SELECT * FROM processes WHERE id=?", (old["id"],)).fetchone()
        )

    return _mutate(
        home,
        "relocate",
        {"selector": selector, "location": source["location"]},
        operation_id,
        apply,
    )


def set_aliases(
    home: Path, selector: str, aliases: tuple[str, ...], *, operation_id: UUID
) -> dict[str, Any]:
    cleaned = _aliases(aliases)

    def apply(connection: sqlite3.Connection) -> dict[str, Any]:
        process = _resolve(connection, selector)
        connection.execute("DELETE FROM aliases WHERE process_id=?", (process["id"],))
        for alias in cleaned:
            connection.execute(
                "INSERT INTO aliases VALUES (?, ?, ?)", (alias, alias.casefold(), process["id"])
            )
        return {"process_id": process["id"], "aliases": list(cleaned)}

    return _mutate(home, "aliases", {"selector": selector, "aliases": cleaned}, operation_id, apply)


def create_group(home: Path, name: str, *, operation_id: UUID) -> dict[str, Any]:
    name = _name(name)

    def apply(connection: sqlite3.Connection) -> dict[str, Any]:
        existing = connection.execute(
            "SELECT * FROM groups WHERE name_key=?", (name.casefold(),)
        ).fetchone()
        if existing is not None:
            return dict(existing)
        identity = str(uuid4())
        connection.execute("INSERT INTO groups VALUES (?, ?, ?)", (identity, name, name.casefold()))
        return {"id": identity, "name": name, "name_key": name.casefold()}

    return _mutate(home, "group.create", {"name": name}, operation_id, apply)


def list_groups(home: Path, *, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    _page(limit, offset)
    with _connect(home) as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT g.*, (SELECT COUNT(*) FROM members m WHERE m.group_id=g.id) "
                "AS member_count "
                "FROM groups g ORDER BY name_key, id LIMIT ? OFFSET ?",
                (limit, offset),
            )
        ]


def set_membership(
    home: Path, group: str, process: str, included: bool, *, operation_id: UUID
) -> dict[str, Any]:
    if type(included) is not bool:
        raise HomeError("invalid_membership", "included must be boolean")

    def apply(connection: sqlite3.Connection) -> dict[str, Any]:
        selected_group = _group(connection, group)
        selected_process = _resolve(connection, process)
        pair = (selected_group["id"], selected_process["id"])
        if included:
            connection.execute("INSERT OR IGNORE INTO members VALUES (?, ?)", pair)
        else:
            connection.execute("DELETE FROM members WHERE group_id=? AND process_id=?", pair)
        return {"group_id": pair[0], "process_id": pair[1], "included": included}

    return _mutate(
        home,
        "membership",
        {"group": group, "process": process, "included": included},
        operation_id,
        apply,
    )


def set_relation(
    home: Path,
    source: str,
    target: str,
    relation_type: str,
    *,
    operation_id: UUID,
    relation_id: UUID | None = None,
) -> dict[str, Any]:
    relation_type = _name(relation_type)

    def apply(connection: sqlite3.Connection) -> dict[str, Any]:
        left, right = _resolve(connection, source)["id"], _resolve(connection, target)["id"]
        if relation_id is not None:
            if (
                connection.execute(
                    "SELECT 1 FROM relations WHERE id=?", (str(relation_id),)
                ).fetchone()
                is None
            ):
                raise HomeError("relation_not_found", "No such relation to update")
            identity = str(relation_id)
            connection.execute(
                "UPDATE relations SET source=?, target=?, type=? WHERE id=?",
                (left, right, relation_type, identity),
            )
        else:
            existing = connection.execute(
                "SELECT id FROM relations WHERE source=? AND target=? AND type=?",
                (left, right, relation_type),
            ).fetchone()
            identity = existing[0] if existing is not None else str(uuid4())
            connection.execute(
                "INSERT OR IGNORE INTO relations VALUES (?, ?, ?, ?)",
                (identity, left, right, relation_type),
            )
        return {"id": identity, "source": left, "target": right, "type": relation_type}

    return _mutate(
        home,
        "relation.set",
        {
            "source": source,
            "target": target,
            "type": relation_type,
            "id": str(relation_id) if relation_id else None,
        },
        operation_id,
        apply,
    )


def delete_relation(home: Path, relation_id: UUID, *, operation_id: UUID) -> dict[str, Any]:
    def apply(connection: sqlite3.Connection) -> dict[str, Any]:
        connection.execute("DELETE FROM relations WHERE id=?", (str(relation_id),))
        return {"id": str(relation_id), "deleted": True}

    return _mutate(home, "relation.delete", {"id": str(relation_id)}, operation_id, apply)


def list_relations(
    home: Path, process: str | None = None, *, limit: int = 20, offset: int = 0
) -> list[dict[str, Any]]:
    _page(limit, offset)
    with _connect(home) as connection:
        identity = _resolve(connection, process)["id"] if process else None
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM relations WHERE ? IS NULL OR source=? OR target=? "
                "ORDER BY id LIMIT ? OFFSET ?",
                (identity, identity, identity, limit, offset),
            )
        ]


def import_registrations(
    home: Path,
    source_path: Path,
    source_sha256: str,
    rows: list[dict[str, Any]],
    *,
    operation_id: UUID,
) -> dict[str, Any]:
    """Called by the compatibility adapter after validating each explicit source."""
    source = source_path.resolve().as_posix()

    def apply(connection: sqlite3.Connection) -> dict[str, Any]:
        prior = connection.execute(
            "SELECT sha256 FROM imports WHERE source=?", (source,)
        ).fetchone()
        if prior is not None and prior[0] != source_sha256:
            raise HomeError("import_conflict", "Previously imported catalog changed")
        result = {"source": source, "count": len(rows), "home": home.resolve().as_posix()}
        if prior is not None:
            return result
        for row in rows:
            _insert_process(connection, row, _name(row["name"]), _aliases(tuple(row["aliases"])))
        connection.execute("INSERT OR IGNORE INTO imports VALUES (?, ?)", (source, source_sha256))
        return result

    return _mutate(
        home, "catalog.import", {"source": source, "sha256": source_sha256}, operation_id, apply
    )
