"""Small transactional authority. Every public call closes its connection."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NoReturn, cast

from .formats import validate_value
from .shapes import Ref, validate
from .types import CoreError, Request, digest, wire

SCHEMA = """
CREATE TABLE meta(instance TEXT, space TEXT, epoch INTEGER);
CREATE TABLE credentials(hash TEXT PRIMARY KEY, principal TEXT NOT NULL, origin TEXT NOT NULL);
CREATE TABLE rights(principal TEXT PRIMARY KEY, permissions TEXT NOT NULL);
CREATE TABLE receipts(command TEXT PRIMARY KEY, principal TEXT, fingerprint TEXT, response TEXT);
CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, subject TEXT, body TEXT);
CREATE TABLE records(id TEXT NOT NULL, revision INTEGER NOT NULL,
 kind TEXT NOT NULL, key TEXT NOT NULL, scope TEXT NOT NULL, body TEXT,
 PRIMARY KEY(id,revision));
CREATE TABLE heads(id TEXT PRIMARY KEY NOT NULL, revision INTEGER NOT NULL,
 kind TEXT NOT NULL, key TEXT NOT NULL, scope TEXT NOT NULL,
 UNIQUE(kind,key,scope));
CREATE TABLE conversations(id TEXT PRIMARY KEY NOT NULL, cursor INTEGER NOT NULL DEFAULT 0);
CREATE TABLE messages(conversation TEXT, seq INTEGER, event TEXT, fingerprint TEXT, raw TEXT,
 origin TEXT, reply TEXT, PRIMARY KEY(conversation,seq), UNIQUE(conversation,event));
CREATE TABLE works(id TEXT PRIMARY KEY NOT NULL, revision INTEGER, conversation TEXT, status TEXT,
 generation INTEGER, body TEXT, reserved INTEGER DEFAULT 0);
CREATE TABLE attempts(id TEXT PRIMARY KEY NOT NULL, work TEXT, conversation TEXT, status TEXT,
 generation INTEGER, original_cursor INTEGER, cutoff INTEGER, body TEXT);
CREATE UNIQUE INDEX active_work ON attempts(work) WHERE status IN ('prepared','claimed','unknown');
CREATE UNIQUE INDEX active_turn ON attempts(conversation)
 WHERE status IN ('prepared','claimed','unknown');
CREATE TABLE actions(id TEXT PRIMARY KEY NOT NULL, attempt TEXT UNIQUE, executor TEXT, state TEXT,
 correlation TEXT, reserve INTEGER);
CREATE TABLE observations(attempt TEXT, event TEXT, fingerprint TEXT, body TEXT,
 PRIMARY KEY(attempt,event));
CREATE TABLE results(attempt TEXT, slot TEXT, fingerprint TEXT, body TEXT,
 PRIMARY KEY(attempt,slot));
CREATE TABLE waits(id TEXT PRIMARY KEY NOT NULL, revision INTEGER, conversation TEXT, work TEXT,
 status TEXT, body TEXT);
CREATE TABLE tool_calls(attempt TEXT, native_id TEXT, command TEXT UNIQUE, action TEXT,
 receipt TEXT, PRIMARY KEY(attempt,native_id));
CREATE TABLE intents(kind TEXT, subject TEXT, body TEXT, PRIMARY KEY(kind,subject));
CREATE TABLE acceptance(attempt TEXT, slot TEXT, result_hash TEXT, principal TEXT,
 PRIMARY KEY(attempt,slot));
"""
READ_OPS = {"describe_contract", "read_snapshot", "read_exact", "lookup_receipt"}
OPS = READ_OPS | {
    "ingest_message",
    "apply_changes",
    "open_work",
    "prepare_attempt",
    "claim_dispatch",
    "observe_attempt",
    "commit_outcome",
    "control_work",
    "reserve_tool",
}
SUBJECTS = {"activity", "data", "memory", "method", "profile"}


def fail(code: str, field: str = "", retry: str = "never") -> NoReturn:
    raise CoreError(code, field, retry)


def loads(value: str) -> Any:
    return json.loads(value)


def dumps(value: Any) -> str:
    return wire(value).decode("utf-8")


class _Preview(Exception):
    def __init__(self, response: dict[str, Any]):
        self.response = response


class Core:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.path = self.root / "core.sqlite3"
        if not self.path.is_file():
            fail("wrong_instance", "data_root")

    @classmethod
    def initialize(cls, root: Path) -> tuple[Core, str]:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=False)
        connection = sqlite3.connect(root / "core.sqlite3")
        token = secrets.token_urlsafe(32)
        try:
            connection.executescript(SCHEMA)
            connection.execute(
                "INSERT INTO meta VALUES(?,?,1)", (secrets.token_hex(16), secrets.token_hex(16))
            )
            connection.execute(
                "INSERT INTO credentials VALUES(?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), "owner", "human"),
            )
            connection.execute("INSERT INTO rights VALUES(?,?)", ("owner", dumps(["*"])))
            connection.commit()
        finally:
            connection.close()
        return cls(root), token

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _identity(self, db: sqlite3.Connection, token: str, permission: str) -> sqlite3.Row:
        identity = db.execute(
            "SELECT * FROM credentials WHERE hash=?", (hashlib.sha256(token.encode()).hexdigest(),)
        ).fetchone()
        if identity is None:
            fail("denied", "credential")
        self._require(db, identity["principal"], permission)
        return cast(sqlite3.Row, identity)

    def _require(self, db: sqlite3.Connection, principal: str, permission: str) -> None:
        rights = db.execute(
            "SELECT permissions FROM rights WHERE principal=?", (principal,)
        ).fetchone()
        permissions = loads(rights[0]) if rights else []
        if "*" not in permissions and permission not in permissions:
            fail("denied", permission)

    def connect(self, token: str) -> Client:
        with self._transaction() as db:
            self._identity(db, token, "read")
        return Client(self, token)

    def grant(
        self, token: str, principal: str, permissions: list[str], *, origin: str = "tool"
    ) -> str:
        """Trusted owner boundary, deliberately not a model command operation."""
        with self._transaction() as db:
            actor = self._identity(db, token, "admin")
            if actor["origin"] != "human" or origin not in {"tool", "host"}:
                fail("denied", "origin")
            credential = secrets.token_urlsafe(32)
            db.execute(
                "INSERT INTO credentials VALUES(?,?,?)",
                (hashlib.sha256(credential.encode()).hexdigest(), principal, origin),
            )
            db.execute("INSERT OR REPLACE INTO rights VALUES(?,?)", (principal, dumps(permissions)))
            return credential

    def revoke(self, token: str, principal: str) -> None:
        with self._transaction() as db:
            self._identity(db, token, "admin")
            db.execute("DELETE FROM rights WHERE principal=?", (principal,))

    def accept_result(self, token: str, attempt: str, result_hash: str) -> None:
        with self._transaction() as db:
            actor = self._identity(db, token, "accept")
            if actor["origin"] != "human":
                fail("denied", "origin")
            result = db.execute(
                "SELECT * FROM results WHERE attempt=? AND slot='final'", (attempt,)
            ).fetchone()
            if result is None or result["fingerprint"] != result_hash:
                fail("stale_basis", "result")
            db.execute(
                "INSERT INTO acceptance VALUES(?,'final',?,?)",
                (attempt, result_hash, actor["principal"]),
            )

    def assess(self, token: str, request: Request) -> dict[str, Any]:
        """Same admission and SQL path, rolled back before returning readiness."""
        try:
            response = self.execute(token, request, _preview=True)
        except _Preview as preview:
            response = preview.response
        except CoreError as error:
            return {"admissible": False, "error": error.as_dict()}
        return {"admissible": True, "preview_receipt": response}

    def execute(self, token: str, request: Request, *, _preview: bool = False) -> dict[str, Any]:
        try:
            return self._execute(token, request, _preview=_preview)
        except (KeyError, TypeError, ValueError) as error:
            raise CoreError("invalid_request", "payload") from error
        except sqlite3.IntegrityError as error:
            raise CoreError("identity_conflict", "unique_identity") from error
        except sqlite3.OperationalError as error:
            raise CoreError("resource_exhausted", "sqlite_operation", "same_id") from error

    def _execute(self, token: str, request: Request, *, _preview: bool = False) -> dict[str, Any]:
        req = request
        try:
            fingerprint = digest(req.model_dump(exclude={"command_id"}))
        except ValueError:
            fail("invalid_request", "wire")
        if req.confirmation_ref is not None:
            fail("unsupported_capability", "confirmation_ref")
        permission = "read" if req.operation in READ_OPS else req.operation
        with self._transaction() as db:
            actor = self._identity(db, token, permission)
            self._identity(db, token, "read")
            validate(req.operation, req.payload)
            meta = db.execute("SELECT * FROM meta").fetchone()
            if (req.instance_id, req.space_id) != (meta["instance"], meta["space"]):
                fail("wrong_instance")
            if req.recovery_epoch != meta["epoch"]:
                fail("stale_epoch", retry="after_refresh")
            if req.operation not in OPS:
                fail("unsupported_capability", req.operation)
            old = db.execute("SELECT * FROM receipts WHERE command=?", (req.command_id,)).fetchone()
            if old:
                self._identity(db, token, "read")
                if old["principal"] != actor["principal"]:
                    fail("denied", "receipt")
                if old["fingerprint"] != fingerprint:
                    fail("idempotency_conflict", "command_id")
                return cast(dict[str, Any], loads(old["response"]))
            for subject, revision in req.expected_heads.items():
                head = db.execute("SELECT revision FROM heads WHERE id=?", (subject,)).fetchone()
                if (head[0] if head else 0) != revision:
                    fail("stale_basis", subject, "after_refresh")
            result = self._apply(db, actor, req)
            seq = db.execute(
                "INSERT INTO events(kind,subject,body) VALUES(?,?,?)",
                (req.operation, req.command_id, dumps(result)),
            ).lastrowid
            response = {
                "receipt_id": req.command_id,
                "command_id": req.command_id,
                "outcome": "committed",
                "result": result,
                "sequence": seq,
                "diagnostic_id": digest([req.command_id, seq])[:16],
            }
            db.execute(
                "INSERT INTO receipts VALUES(?,?,?,?)",
                (req.command_id, actor["principal"], fingerprint, dumps(response)),
            )
            if _preview:
                raise _Preview(response)
            return response

    def _exact(self, db: sqlite3.Connection, ref: dict[str, Any]) -> dict[str, Any]:
        Ref.model_validate(ref)
        row = db.execute(
            "SELECT * FROM records WHERE id=? AND revision=?", (ref["id"], ref["revision"])
        ).fetchone()
        if row is None:
            fail("invalid_request", "missing_ref")
        if ref.get("role") == "must_be_current":
            head = db.execute("SELECT revision FROM heads WHERE id=?", (ref["id"],)).fetchone()
            if head[0] != ref["revision"]:
                fail("stale_basis", ref["id"], "after_refresh")
        return dict(row) | {"body": loads(row["body"])}

    def _changes(
        self, db: sqlite3.Connection, changes: list[dict[str, Any]], expected: dict[str, int]
    ) -> list[dict[str, Any]]:
        if not changes or len(changes) > 32:
            fail("invalid_request", "changes")
        refs = []
        for change in changes:
            if set(change) - {
                "id",
                "kind",
                "key",
                "scope",
                "body",
                "source_refs",
                "schema_ref",
                "tombstone",
            }:
                fail("denied", "changes.system_field")
            if change["kind"] not in SUBJECTS:
                fail("denied", "changes.kind")
            for ref in change.get("source_refs", []):
                self._exact(db, ref)
            head = db.execute("SELECT * FROM heads WHERE id=?", (change["id"],)).fetchone()
            current = head["revision"] if head else 0
            if expected.get(change["id"]) != current:
                fail("stale_basis", change["id"], "after_refresh")
            if head and (head["kind"], head["key"], head["scope"]) != (
                change["kind"],
                change["key"],
                change.get("scope", "space"),
            ):
                fail("identity_conflict", "record_identity")
            if change.get("schema_ref"):
                schema = self._exact(db, change["schema_ref"])
                validate_value(change["body"], schema["body"]["value"])
            revision = current + 1
            body = {
                "value": change["body"],
                "source_refs": change.get("source_refs", []),
                "tombstone": change.get("tombstone", False),
                "schema_ref": change.get("schema_ref"),
            }
            db.execute(
                "INSERT INTO records VALUES(?,?,?,?,?,?)",
                (
                    change["id"],
                    revision,
                    change["kind"],
                    change["key"],
                    change.get("scope", "space"),
                    dumps(body),
                ),
            )
            db.execute(
                "INSERT INTO heads VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE "
                "SET revision=excluded.revision",
                (
                    change["id"],
                    revision,
                    change["kind"],
                    change["key"],
                    change.get("scope", "space"),
                ),
            )
            refs.append({"id": change["id"], "revision": revision})
        return refs

    def _work(self, db: sqlite3.Connection, body: dict[str, Any]) -> dict[str, Any]:
        if self._exact(db, body["method_ref"])["kind"] != "method":
            fail("invalid_request", "method_ref.kind")
        for ref in body.get("inputs", []):
            self._exact(db, ref)
        if type(body["call_limit"]) is not int or body["call_limit"] < 1:
            fail("invalid_request", "call_limit")
        if body.get("token_limit") or body.get("money_limit"):
            fail("unsupported_capability", "resource_unit")
        db.execute("INSERT OR IGNORE INTO conversations(id) VALUES(?)", (body["conversation"],))
        db.execute(
            "INSERT INTO works(id,revision,conversation,status,generation,body) "
            "VALUES(?,1,?,'ready',1,?)",
            (body["id"], body["conversation"], dumps(body)),
        )
        self._intent(db, "prepare", body["id"], {})
        return {"work_id": body["id"], "revision": 1}

    def _intent(self, db: sqlite3.Connection, kind: str, subject: str, body: Any) -> None:
        db.execute("INSERT OR REPLACE INTO intents VALUES(?,?,?)", (kind, subject, dumps(body)))

    def _attempt(self, db: sqlite3.Connection, attempt_id: str) -> tuple[sqlite3.Row, sqlite3.Row]:
        attempt = db.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone()
        if attempt is None:
            fail("invalid_request", "attempt_id")
        work = db.execute("SELECT * FROM works WHERE id=?", (attempt["work"],)).fetchone()
        return attempt, work

    def _fence(self, attempt: sqlite3.Row, work: sqlite3.Row, generation: int) -> None:
        if generation != work["generation"] or attempt["generation"] != generation:
            fail("stale_basis", "generation", "after_refresh")
        if work["status"] != "running" or attempt["status"] not in {"prepared", "claimed"}:
            fail("stale_basis", "execution.status", "after_refresh")

    def _check_basis(self, db: sqlite3.Connection, attempt: sqlite3.Row, work: sqlite3.Row) -> None:
        body = loads(work["body"])
        for ref in body.get("inputs", []) + [
            body["method_ref"],
            loads(attempt["body"])["profile_ref"],
        ]:
            self._exact(db, ref)

    def _tool_authority(
        self,
        db: sqlite3.Connection,
        actor: sqlite3.Row,
        attempt: sqlite3.Row,
        work: sqlite3.Row,
        generation: int,
    ) -> None:
        self._fence(attempt, work, generation)
        action = db.execute("SELECT * FROM actions WHERE attempt=?", (attempt["id"],)).fetchone()
        if (
            attempt["status"] != "claimed"
            or action is None
            or action["executor"] != actor["principal"]
            or action["state"] not in {"claimed", "running"}
        ):
            fail("denied", "tool.executor_claim")
        self._check_basis(db, attempt, work)

    def _apply(self, db: sqlite3.Connection, actor: sqlite3.Row, req: Request) -> dict[str, Any]:
        p = req.payload
        op = req.operation
        if op == "describe_contract":
            return {
                "version": "wire/v1",
                "operations": sorted(OPS),
                "resource_units": ["calls"],
                "snapshot": {"max_rows_per_table": 1000, "pagination": False},
                "one_shot_confirmation": False,
                "readiness": "Client.preview(Request): same admission, rollback",
                "scope": "single_local_space",
                "controls": ["pause", "cancel", "resume", "refresh"],
            }
        if op == "lookup_receipt":
            row = db.execute(
                "SELECT * FROM receipts WHERE command=?", (p["command_id"],)
            ).fetchone()
            if row is None:
                return {"missing": True}
            if row["principal"] != actor["principal"]:
                fail("denied", "receipt")
            return cast(dict[str, Any], loads(row["response"]))
        if op == "read_exact":
            return self._exact(db, p)
        if op == "read_snapshot":
            result: dict[str, Any] = {}
            for table in (
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
            ):
                limit = p.get("max_rows", 1000)
                rows = db.execute(f"SELECT * FROM {table} LIMIT ?", (limit + 1,)).fetchall()
                if len(rows) > limit:
                    fail("resource_exhausted", "snapshot.max_rows")
                result[table] = [dict(row) for row in rows]
            result["snapshot_revision"] = db.execute(
                "SELECT COALESCE(MAX(seq),0) FROM events"
            ).fetchone()[0]
            result["limit"] = {"max_rows_per_table": p.get("max_rows", 1000), "truncated": False}
            return result
        if op == "ingest_message":
            raw = p["raw_base64"]
            try:
                base64.b64decode(raw, validate=True)
            except ValueError:
                fail("invalid_request", "raw_base64")
            conversation = p["conversation"]
            db.execute("INSERT OR IGNORE INTO conversations(id) VALUES(?)", (conversation,))
            fp = digest(p)
            old = db.execute(
                "SELECT * FROM messages WHERE conversation=? AND event=?",
                (conversation, p["event_id"]),
            ).fetchone()
            if old:
                if old["fingerprint"] != fp:
                    fail("idempotency_conflict", "event_id")
                return {"message_sequence": old["seq"]}
            reply = p.get("reply_to")
            if reply:
                wait = db.execute("SELECT * FROM waits WHERE id=?", (reply["id"],)).fetchone()
                if (
                    actor["origin"] != "human"
                    or wait is None
                    or wait["revision"] != reply["revision"]
                    or wait["status"] != "waiting"
                    or wait["conversation"] != conversation
                ):
                    fail("stale_basis", "reply_to")
                db.execute(
                    "UPDATE waits SET status='answered',revision=revision+1 WHERE id=?",
                    (reply["id"],),
                )
                db.execute(
                    "UPDATE works SET status='ready',revision=revision+1 WHERE "
                    "id=? AND status='waiting'",
                    (wait["work"],),
                )
                self._intent(db, "prepare", wait["work"], {"reply_to": reply})
            seq = db.execute(
                "SELECT COALESCE(MAX(seq),0)+1 FROM messages WHERE conversation=?", (conversation,)
            ).fetchone()[0]
            db.execute(
                "INSERT INTO messages VALUES(?,?,?,?,?,?,?)",
                (conversation, seq, p["event_id"], fp, raw, actor["origin"], dumps(reply)),
            )
            self._intent(db, "input", conversation, {"high_watermark": seq})
            return {"message_sequence": seq}
        if op == "reserve_tool":
            attempt, work = self._attempt(db, p["attempt_id"])
            self._tool_authority(db, actor, attempt, work, p["generation"])
            old = db.execute(
                "SELECT * FROM tool_calls WHERE attempt=? AND native_id=?",
                (attempt["id"], p["native_id"]),
            ).fetchone()
            if old:
                return dict(old)
            db.execute(
                "INSERT INTO tool_calls VALUES(?,?,?,?,NULL)",
                (attempt["id"], p["native_id"], p["command_id"], p.get("action_id")),
            )
            return {"command_id": p["command_id"]}
        if op == "apply_changes":
            if p.get("initial_work"):
                self._require(db, actor["principal"], "open_work")
            correlation = p.get("tool")
            if correlation:
                attempt, work = self._attempt(db, correlation["attempt_id"])
                self._tool_authority(db, actor, attempt, work, correlation["generation"])
                tool = db.execute(
                    "SELECT * FROM tool_calls WHERE attempt=? AND native_id=?",
                    (attempt["id"], correlation["native_id"]),
                ).fetchone()
                if tool is None or tool["command"] != req.command_id:
                    fail("identity_conflict", "tool_call")
            refs = self._changes(db, p["changes"], req.expected_heads)
            if p.get("initial_work"):
                self._work(db, p["initial_work"])
            if correlation:
                db.execute(
                    "UPDATE tool_calls SET receipt=? WHERE attempt=? AND native_id=?",
                    (req.command_id, attempt["id"], correlation["native_id"]),
                )
            return {"refs": refs}
        if op == "open_work":
            return self._work(db, p)
        if op == "prepare_attempt":
            work = db.execute("SELECT * FROM works WHERE id=?", (p["work_id"],)).fetchone()
            if work is None or work["revision"] != p["work_revision"] or work["status"] != "ready":
                fail("stale_basis", "work", "after_refresh")
            cursor = db.execute(
                "SELECT cursor FROM conversations WHERE id=?", (work["conversation"],)
            ).fetchone()[0]
            messages = db.execute(
                "SELECT * FROM messages WHERE conversation=? AND seq>? AND seq<=? ORDER BY seq",
                (work["conversation"], cursor, p["cutoff"]),
            ).fetchall()
            if (
                p["original_cursor"] != cursor
                or p["cutoff"] < cursor
                or [m["seq"] for m in messages] != list(range(cursor + 1, p["cutoff"] + 1))
                or p["message_sequences"] != [m["seq"] for m in messages]
            ):
                fail("stale_basis", "input_range")
            body = loads(work["body"])
            material = [self._exact(db, ref) for ref in body.get("inputs", [])]
            method = self._exact(db, body["method_ref"])
            profile = self._exact(db, p["profile_ref"])
            if profile["kind"] != "profile":
                fail("invalid_request", "profile_ref.kind")
            tool_ledger = [
                dict(row)
                for row in db.execute(
                    "SELECT t.* FROM tool_calls t JOIN attempts a ON a.id=t.attempt WHERE a.work=?",
                    (work["id"],),
                )
            ]
            prior_messages = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM messages WHERE conversation=? AND seq<=? ORDER BY seq",
                    (work["conversation"], cursor),
                )
            ]
            prior_results = [
                dict(row)
                for row in db.execute(
                    "SELECT r.* FROM results r JOIN attempts a ON "
                    "a.id=r.attempt WHERE a.conversation=? ORDER BY a.rowid",
                    (work["conversation"],),
                )
            ]
            prior_waits = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM waits WHERE conversation=? ORDER BY rowid",
                    (work["conversation"],),
                )
            ]
            if len(prior_messages) + len(messages) > 1000 or len(prior_results) > 1000:
                fail("resource_exhausted", "context.max_rows")
            catalog = [
                dict(row)
                for row in db.execute(
                    "SELECT r.* FROM records r JOIN heads h ON h.id=r.id "
                    "AND h.revision=r.revision ORDER BY r.id"
                )
            ]
            if len(catalog) > 1000:
                fail("resource_exhausted", "catalog.max_rows")
            pinned = {
                "catalog": catalog,
                "work": body,
                "prior_messages": prior_messages,
                "prior_results": prior_results,
                "prior_waits": prior_waits,
                "messages": [dict(m) for m in messages],
                "inputs": material,
                "method": method,
                "profile": profile,
                "tool_ledger": tool_ledger,
                "manifest": p["manifest"],
                "profile_ref": p["profile_ref"],
            }
            if len(wire(pinned)) > 1048576:
                fail("resource_exhausted", "context.max_bytes")
            expected_manifest = [
                {
                    "sequence": m["seq"],
                    "sha256": hashlib.sha256(base64.b64decode(m["raw"])).hexdigest(),
                }
                for m in messages
            ]
            if p["manifest"] != expected_manifest:
                fail("stale_basis", "input_manifest")
            db.execute(
                "INSERT INTO attempts VALUES(?,?,?,'prepared',?,?,?,?)",
                (
                    p["id"],
                    work["id"],
                    work["conversation"],
                    work["generation"],
                    cursor,
                    p["cutoff"],
                    dumps(pinned),
                ),
            )
            db.execute(
                "UPDATE works SET status='running',revision=revision+1 WHERE id=?", (work["id"],)
            )
            db.execute("DELETE FROM intents WHERE kind='prepare' AND subject=?", (work["id"],))
            self._intent(db, "dispatch", p["id"], {})
            return {"attempt_id": p["id"], "generation": work["generation"], "pinned": pinned}
        if op == "claim_dispatch":
            attempt, work = self._attempt(db, p["attempt_id"])
            self._fence(attempt, work, p["generation"])
            if attempt["status"] != "prepared":
                fail("outcome_unknown", "claim", "reconcile")
            if not req.action_id:
                fail("invalid_request", "action_id")
            if db.execute("SELECT 1 FROM actions WHERE id=?", (req.action_id,)).fetchone():
                fail("idempotency_conflict", "action_id")
            pinned = loads(attempt["body"])
            body = loads(work["body"])
            self._check_basis(db, attempt, work)
            high = db.execute(
                "SELECT COALESCE(MAX(seq),0) FROM messages WHERE conversation=?",
                (attempt["conversation"],),
            ).fetchone()[0]
            if high != attempt["cutoff"]:
                fail("stale_basis", "new_input", "after_refresh")
            upper = p.get("resource_upper", 1)
            if type(upper) is not int or upper < 1:
                fail("invalid_request", "resource_upper")
            if work["reserved"] + upper > body["call_limit"]:
                fail("resource_exhausted", "calls")
            db.execute(
                "INSERT INTO actions VALUES(?,?,?,'claimed',NULL,?)",
                (req.action_id, attempt["id"], actor["principal"], upper),
            )
            db.execute("UPDATE works SET reserved=reserved+? WHERE id=?", (upper, work["id"]))
            db.execute("UPDATE attempts SET status='claimed' WHERE id=?", (attempt["id"],))
            db.execute("DELETE FROM intents WHERE kind='dispatch' AND subject=?", (attempt["id"],))
            return {"action_id": req.action_id, "pinned": pinned}
        if op == "observe_attempt":
            attempt, work = self._attempt(db, p["attempt_id"])
            action = db.execute(
                "SELECT * FROM actions WHERE attempt=?", (attempt["id"],)
            ).fetchone()
            if action is None or action["executor"] != actor["principal"]:
                fail("denied", "executor")
            old = db.execute(
                "SELECT * FROM observations WHERE attempt=? AND event=?",
                (attempt["id"], p["event_id"]),
            ).fetchone()
            if old:
                if old["fingerprint"] != digest(p):
                    fail("idempotency_conflict", "event_id")
                return cast(dict[str, Any], loads(old["body"]))
            body = dict(p)
            fenced = attempt["generation"] != work["generation"] or attempt["status"] in {
                "finished",
                "fenced",
                "superseded",
            }
            body["late"] = fenced
            if p["kind"] not in {"terminal", "progress", "unknown", "reconcile"}:
                fail("invalid_request", "observation.kind")
            if p["kind"] == "terminal":
                base64.b64decode(p["raw_base64"], validate=True)
            if p["kind"] == "reconcile":
                evidence = p.get("evidence", {})
                if (
                    actor["origin"] != "host"
                    or evidence.get("action_id") != action["id"]
                    or evidence.get("state") not in {"running", "terminal", "not_received"}
                    or not evidence.get("receiver_ref")
                ):
                    fail("denied", "reconciliation")
                body["verified"] = True
                db.execute(
                    "UPDATE actions SET state=?,correlation=? WHERE id=?",
                    (evidence["state"], dumps(evidence), action["id"]),
                )
            db.execute(
                "INSERT INTO observations VALUES(?,?,?,?)",
                (attempt["id"], p["event_id"], digest(p), dumps(body)),
            )
            if not fenced:
                if p["kind"] == "unknown":
                    db.execute("UPDATE works SET status='blocked' WHERE id=?", (work["id"],))
                    db.execute("UPDATE attempts SET status='unknown' WHERE id=?", (attempt["id"],))
                if p["kind"] == "terminal":
                    db.execute("UPDATE actions SET state='terminal' WHERE id=?", (action["id"],))
                self._intent(db, "observe", attempt["id"], {"event_id": p["event_id"]})
            return body
        if op == "commit_outcome":
            attempt, work = self._attempt(db, p["attempt_id"])
            old = db.execute(
                "SELECT * FROM results WHERE attempt=? AND slot='final'", (attempt["id"],)
            ).fetchone()
            if old:
                if old["fingerprint"] != digest(p):
                    fail("idempotency_conflict", "result_slot")
                return cast(dict[str, Any], loads(old["body"]))
            self._fence(attempt, work, p["generation"])
            event = db.execute(
                "SELECT body FROM observations WHERE attempt=? AND event=?",
                (attempt["id"], p["terminal_event"]),
            ).fetchone()
            if event is None or loads(event[0])["kind"] != "terminal" or loads(event[0])["late"]:
                fail("invalid_request", "terminal_ref")
            cursor = db.execute(
                "SELECT cursor FROM conversations WHERE id=?", (attempt["conversation"],)
            ).fetchone()[0]
            if (
                cursor != attempt["original_cursor"]
                or p["original_cursor"] != cursor
                or p["processed_cutoff"] != attempt["cutoff"]
            ):
                fail("stale_basis", "cursor", "after_refresh")
            self._check_basis(db, attempt, work)
            if p.get("changes"):
                self._require(db, actor["principal"], "apply_changes")
            refs = self._changes(db, p["changes"], req.expected_heads) if p.get("changes") else []
            for ref in p.get("outputs", []):
                self._exact(db, ref)
            state = p["state"]
            if state not in {"waiting", "ready", "completed"}:
                fail("invalid_request", "outcome.state")
            if state == "waiting":
                wait = p["wait"]
                db.execute(
                    "INSERT INTO waits VALUES(?,1,?,?,'waiting',?)",
                    (wait["id"], attempt["conversation"], work["id"], dumps(wait)),
                )
            high = db.execute(
                "SELECT COALESCE(MAX(seq),0) FROM messages WHERE conversation=?",
                (attempt["conversation"],),
            ).fetchone()[0]
            changed = db.execute(
                "UPDATE conversations SET cursor=? WHERE id=? AND cursor=?",
                (attempt["cutoff"], attempt["conversation"], cursor),
            ).rowcount
            if changed != 1:
                fail("stale_basis", "cursor")
            db.execute(
                "UPDATE works SET status=?,revision=revision+1 WHERE id=?", (state, work["id"])
            )
            db.execute("UPDATE attempts SET status='finished' WHERE id=?", (attempt["id"],))
            result = {
                "attempt_id": attempt["id"],
                "state": state,
                "refs": refs,
                "outputs": p.get("outputs", []),
                "accepted": False,
                "text": p.get("text", ""),
                "cutoff": attempt["cutoff"],
            }
            db.execute(
                "INSERT INTO results VALUES(?,'final',?,?)",
                (attempt["id"], digest(p), dumps(result)),
            )
            db.execute("DELETE FROM intents WHERE kind='observe' AND subject=?", (attempt["id"],))
            db.execute(
                "DELETE FROM intents WHERE kind='input' AND subject=?", (attempt["conversation"],)
            )
            if high > attempt["cutoff"]:
                self._intent(
                    db,
                    "input",
                    attempt["conversation"],
                    {"after": attempt["cutoff"], "high_watermark": high},
                )
            if state == "ready":
                self._intent(db, "prepare", work["id"], {})
            return result
        if op == "control_work":
            work = db.execute("SELECT * FROM works WHERE id=?", (p["work_id"],)).fetchone()
            if work is None or work["revision"] != p["revision"]:
                fail("stale_basis", "work")
            action = p["action"]
            if action in {"pause", "cancel"}:
                if work["status"] not in {"ready", "running", "waiting", "blocked"}:
                    fail("stale_basis", "work.status")
                state = "paused" if action == "pause" else "cancelled"
                db.execute(
                    "UPDATE works SET "
                    "status=?,generation=generation+1,revision=revision+1 WHERE id=?",
                    (state, work["id"]),
                )
                db.execute(
                    "UPDATE attempts SET status='fenced' WHERE work=? AND status "
                    "IN ('prepared','claimed','unknown')",
                    (work["id"],),
                )
            elif action == "refresh":
                attempt = db.execute(
                    "SELECT * FROM attempts WHERE work=? AND status IN "
                    "('prepared','claimed') ORDER BY rowid DESC LIMIT 1",
                    (work["id"],),
                ).fetchone()
                if attempt is None:
                    fail("stale_basis", "refresh.attempt")
                claimed = db.execute(
                    "SELECT * FROM actions WHERE attempt=?", (attempt["id"],)
                ).fetchone()
                if claimed and claimed["state"] != "terminal":
                    fail("outcome_unknown", "refresh.claim", "reconcile")
                body = loads(work["body"])
                for key in ("inputs", "method_ref"):
                    if key in p:
                        refs = p[key] if key == "inputs" else [p[key]]
                        for ref in refs:
                            self._exact(db, ref)
                        body[key] = p[key]
                db.execute("UPDATE attempts SET status='superseded' WHERE id=?", (attempt["id"],))
                db.execute(
                    "UPDATE works SET "
                    "status='ready',revision=revision+1,generation=generation+1,body=? WHERE id=?",
                    (dumps(body), work["id"]),
                )
                db.execute(
                    "DELETE FROM intents WHERE kind IN ('dispatch','observe') AND subject=?",
                    (attempt["id"],),
                )
                self._intent(db, "prepare", work["id"], {"reason": "fresh_basis"})
                state = "ready"
            elif action == "resume":
                if work["status"] not in {"blocked", "paused"}:
                    fail("stale_basis", "work.status")
                last = db.execute(
                    "SELECT a.* FROM actions a JOIN attempts t ON t.id=a.attempt "
                    "WHERE t.work=? ORDER BY t.rowid DESC LIMIT 1",
                    (work["id"],),
                ).fetchone()
                if last and last["state"] not in {"running", "terminal", "not_received"}:
                    fail("outcome_unknown", "action", "reconcile")
                state = "running" if last and last["state"] in {"running", "terminal"} else "ready"
                was_paused = work["status"] == "paused"
                if was_paused:
                    if last and last["state"] == "running":
                        fail("outcome_unknown", "fenced_running_action", "reconcile")
                    state = "ready"
                db.execute(
                    "UPDATE works SET status=?,revision=revision+1 WHERE id=?", (state, work["id"])
                )
                if last and not was_paused:
                    db.execute(
                        "UPDATE attempts SET generation=?,status=? WHERE id=?",
                        (
                            work["generation"],
                            "claimed" if state == "running" else "finished",
                            last["attempt"],
                        ),
                    )
                self._intent(db, "observe" if state == "running" else "prepare", work["id"], {})
            else:
                fail("invalid_request", "control.action")
            return {"status": state}
        fail("unsupported_capability", op)
        return {}


class Client:
    """Trusted host creates this connection; models submit only Request payloads."""

    def __init__(self, core: Core, token: str):
        self.core = core
        self.token = token
        with core._transaction() as db:
            core._identity(db, token, "read")
            self.meta = dict(db.execute("SELECT * FROM meta").fetchone())

    def request(
        self,
        operation: str,
        payload: dict[str, Any],
        command_id: str,
        *,
        expected_heads: dict[str, int] | None = None,
        action_id: str | None = None,
    ) -> Request:
        return Request(
            instance_id=self.meta["instance"],
            space_id=self.meta["space"],
            recovery_epoch=self.meta["epoch"],
            command_id=command_id,
            operation=operation,
            payload=payload,
            expected_heads=expected_heads or {},
            action_id=action_id,
        )

    def preview(self, request: Request) -> dict[str, Any]:
        return self.core.assess(self.token, request)

    def send(self, request: Request) -> dict[str, Any]:
        try:
            return self.core.execute(self.token, request)
        except (KeyError, TypeError, ValueError) as exc:
            raise CoreError("invalid_request", str(exc)) from exc
        except sqlite3.IntegrityError as exc:
            raise CoreError("identity_conflict", "unique_identity") from exc

    def call(
        self, operation: str, payload: dict[str, Any], command_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.send(self.request(operation, payload, command_id, **kwargs))["result"],
        )
