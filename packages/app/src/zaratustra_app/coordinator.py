"""Public-API-only coordination; durable core state is the continuation authority."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, cast
from uuid import uuid4

from zaratustra_core import Client, CoreError

from .executor_port import Executor, Pi


class Coordinator:
    def __init__(self, client: Client):
        self.client = client

    def rows(self, table: str, **filters: Any) -> list[dict[str, Any]]:
        """Read only the requested table/filter prefix through the public paged API."""
        rows: list[dict[str, Any]] = []
        payload: dict[str, Any] = {"table": table, "limit": 100, **filters}
        while True:
            page = self.client.call("read_page", payload, uuid4().hex)
            rows.extend(page["rows"])
            if not page["has_more"]:
                return rows
            payload |= {
                "cursor": page["next_cursor"],
                "snapshot_revision": page["snapshot_revision"],
            }

    def tables(self, *tables: str) -> dict[str, Any]:
        """Individually fenced tables; mutation commands still check current CAS."""
        return {table: self.rows(table) for table in tables}

    def snapshot(self) -> dict[str, Any]:
        try:
            return self.client.call("read_snapshot", {}, str(uuid4()))
        except CoreError as error:
            if error.code != "resource_exhausted" or error.field != "snapshot.max_rows":
                raise
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
            revision = None
            cursor, rows = 0, []
            while True:
                payload: dict[str, Any] = {"table": table, "cursor": cursor, "limit": 100}
                if revision is not None:
                    payload["snapshot_revision"] = revision
                page = self.client.call("read_page", payload, uuid4().hex)
                revision = page["snapshot_revision"]
                rows.extend(page["rows"])
                if not page["has_more"]:
                    break
                cursor = page["next_cursor"]
            result[table] = rows
        result["snapshot_revision"] = None
        result["limit"] = {
            "pagination": True,
            "max_rows_per_page": 100,
            "truncated": False,
            "consistency": "Each table has a fenced prefix; commands recheck current CAS.",
        }
        return result

    def open_work(self, payload: dict[str, Any], *, scope: str = "space") -> dict[str, Any]:
        """Pin current applicable memory and chosen scoped Method from fresh Core state."""
        heads = self.rows("heads")
        method = next(h for h in heads if h["id"] == payload["method_ref"]["id"])
        if method["scope"] not in {"space", scope}:
            raise CoreError("denied", "method.scope")
        return self.client.call(
            "open_work",
            payload
            | {
                "scope": scope,
                "inputs": self.scoped_inputs(scope, list(payload.get("inputs", []))),
                "method_ref": {
                    "id": method["id"],
                    "revision": method["revision"],
                    "role": "must_be_current",
                },
            },
            str(uuid4()),
        )

    def scoped_inputs(self, scope: str, inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        inputs = list(inputs)
        heads = self.rows("heads")
        for head in heads:
            if head["kind"] != "memory" or head["scope"] not in {"space", scope}:
                continue
            record = self.client.call(
                "read_exact", {"id": head["id"], "revision": head["revision"]}, str(uuid4())
            )
            inputs = [r for r in inputs if r["id"] != head["id"]]
            if (
                not record["body"]["tombstone"]
                and record["body"].get("application", "active") == "active"
            ):
                inputs.append(
                    {"id": head["id"], "revision": head["revision"], "role": "must_be_current"}
                )
        return inputs

    def prepare(
        self,
        work_id: str,
        attempt_id: str,
        profile_ref: dict[str, Any],
        *,
        context_selection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        work = self.rows("works", work=work_id)[0]
        cursor = next(
            c["cursor"] for c in self.rows("conversations", conversation=work["conversation"])
        )
        messages = sorted(
            (
                m
                for m in self.rows("messages", conversation=work["conversation"])
                if m["seq"] > cursor
            ),
            key=lambda m: m["seq"],
        )
        cutoff = messages[-1]["seq"] if messages else cursor
        manifest = [
            {"sequence": m["seq"], "sha256": hashlib.sha256(base64.b64decode(m["raw"])).hexdigest()}
            for m in messages
        ]
        return self.client.call(
            "prepare_attempt",
            {
                "work_id": work_id,
                "work_revision": work["revision"],
                "id": attempt_id,
                "profile_ref": profile_ref,
                "original_cursor": cursor,
                "cutoff": cutoff,
                "message_sequences": [m["seq"] for m in messages],
                "manifest": manifest,
            }
            | ({"context_selection": context_selection} if context_selection is not None else {}),
            attempt_id + ":prepare",
        )

    def refresh_basis(
        self, work_id: str, *, method_ref: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Explicit new intent over freshly read current refs; old terminal remains evidence."""
        work = self.rows("works", work=work_id)[0]
        body = json.loads(work["body"])
        heads = {h["id"]: h["revision"] for h in self.rows("heads")}

        def fresh(ref: dict[str, Any]) -> dict[str, Any]:
            if ref.get("role") == "must_be_current":
                return ref | {"revision": heads[ref["id"]]}
            return ref

        return self.client.call(
            "control_work",
            {
                "work_id": work_id,
                "revision": work["revision"],
                "action": "refresh",
                "inputs": [fresh(r) for r in body.get("inputs", [])],
                "method_ref": method_ref if method_ref is not None else fresh(body["method_ref"]),
            },
            str(uuid4()),
        )

    def dispatch(self, attempt_id: str, generation: int, executor: Executor) -> bytes:
        action_id = attempt_id + ":action"
        try:
            pinned = self.client.call(
                "claim_dispatch",
                {
                    "attempt_id": attempt_id,
                    "generation": generation,
                    "resource_upper": getattr(executor, "resource_upper", 1),
                },
                attempt_id + ":claim:" + str(uuid4()),
                action_id=action_id,
            )["pinned"]
        except CoreError as exc:
            if exc.code == "stale_basis" and exc.field == "new_input":
                attempt = next(a for a in self.rows("attempts") if a["id"] == attempt_id)
                work = self.rows("works", work=attempt["work"])[0]
                self.client.call(
                    "control_work",
                    {"work_id": work["id"], "revision": work["revision"], "action": "refresh"},
                    attempt_id + ":refresh",
                )
            raise
        # A replayed claim is potentially sent; a receipt never proves send safety.
        work_id = pinned["work"]["id"]
        action = next(a for a in self.rows("actions", work=work_id) if a["id"] == action_id)
        observations = [
            o for o in self.rows("observations", work=work_id) if o["attempt"] == attempt_id
        ]
        if observations or action["state"] != "claimed":
            raise CoreError("outcome_unknown", "existing_dispatch", "reconcile")
        context = dict(pinned)
        context["response_contract"] = getattr(
            executor,
            "response_contract",
            {
                "terminal": (
                    "JSON object: state ready/completed/waiting, text, "
                    "optional changes, expected_heads, outputs, wait"
                ),
                "changes": (
                    "C3 Change: id, kind, key, scope, body (record.body.value), "
                    "optional source_refs/application"
                ),
                "expected_heads": "each changed id maps to old revision, zero for a new id",
                "analysis": (
                    "ordinary data body {format: sleep-analysis/v1, "
                    "sources: [exact source_ref objects], content: free text/object}"
                ),
            },
        )
        context["raw_messages"] = [
            base64.b64decode(m["raw"]).decode("utf-8") for m in pinned["messages"]
        ]

        def tool_handler(native_id: str, intent: dict[str, Any]) -> dict[str, Any]:
            if not isinstance(intent, dict) or not isinstance(native_id, str) or not native_id:
                raise CoreError("invalid_request", "native_tool.intent")
            contract = getattr(executor, "response_contract", {})
            if contract.get("version") == "ordinary-routing/1":
                raise CoreError("denied", "ordinary.routing_atomic_handoff")
            if intent.get("initial_work") is not None:
                raise CoreError("denied", "native_tool.initial_work")
            if contract.get("version") == "ordinary-execution/2":
                from .ordinary import subject_scope

                subject_scope(intent.get("changes"), pinned["work"].get("scope", "space"))
            if set(intent) - {"changes", "expected_heads", "initial_work"} or not {
                "changes",
                "expected_heads",
            } <= set(intent):
                raise CoreError("invalid_request", "native_tool.intent")
            command_id = attempt_id + ":tool:" + native_id
            self.client.call(
                "reserve_tool",
                {
                    "attempt_id": attempt_id,
                    "generation": generation,
                    "native_id": native_id,
                    "command_id": command_id,
                },
                command_id + ":reserve",
            )
            change_payload = {
                "changes": intent["changes"],
                "tool": {
                    "attempt_id": attempt_id,
                    "generation": generation,
                    "native_id": native_id,
                },
            }
            if "initial_work" in intent:
                change_payload["initial_work"] = intent["initial_work"]
            request = self.client.request(
                "apply_changes", change_payload, command_id, expected_heads=intent["expected_heads"]
            )
            return self.client.send(request)

        executor.tool_handler = tool_handler
        try:
            raw = executor.run(context, action_id)
        except BaseException:
            report = {
                "events": [
                    e
                    for e in getattr(executor, "events", [])
                    if e.get("type") in {"message_end", "response", "agent_settled"}
                ],
                "provider_sends": getattr(executor, "provider_sends", None),
                "usage_complete": False,
            }
            self.client.call(
                "observe_attempt",
                {
                    "attempt_id": attempt_id,
                    "event_id": "unknown",
                    "kind": "unknown",
                    "raw_base64": base64.b64encode(
                        json.dumps(report, ensure_ascii=False).encode()
                    ).decode(),
                },
                attempt_id + ":unknown",
            )
            raise
        self.client.call(
            "observe_attempt",
            {
                "attempt_id": attempt_id,
                "event_id": "terminal",
                "kind": "terminal",
                "raw_base64": base64.b64encode(raw).decode(),
            },
            attempt_id + ":retain",
        )
        return raw

    def recover(
        self, attempt_id: str, *, pi: bool = False, decoder: Any = None, ordinary: bool = False
    ) -> dict[str, Any]:
        attempt = next(a for a in self.rows("attempts") if a["id"] == attempt_id)
        work_id = attempt["work"]
        retained = next(
            (r for r in self.rows("results", work=work_id) if r["attempt"] == attempt_id), None
        )
        if retained is not None:
            return cast(dict[str, Any], json.loads(retained["body"]))
        observations = [
            json.loads(o["body"])
            for o in self.rows("observations", work=work_id)
            if o["attempt"] == attempt_id
        ]
        terminal = next(
            (o for o in observations if o["kind"] == "terminal" and not o["late"]), None
        )
        if terminal is None:
            if any(a["attempt"] == attempt_id for a in self.rows("actions", work=work_id)):
                raise CoreError("outcome_unknown", "retained_claim", "reconcile")
            raise CoreError("invalid_request", "no_terminal")
        raw = base64.b64decode(terminal["raw_base64"])
        try:
            output = (
                decoder(raw) if decoder is not None else (Pi.decode(raw) if pi else json.loads(raw))
            )
        except (ValueError, KeyError, TypeError) as error:
            raise CoreError(
                "invalid_request", "retained_outcome_format", "after_refresh"
            ) from error
        if ordinary:
            from .ordinary import outcome

            work = self.rows("works", work=work_id)[0]
            output = outcome(output, attempt, work, self.scoped_inputs)
        if not isinstance(output, dict) or "state" not in output or "text" not in output:
            raise CoreError("invalid_request", "retained_outcome_format", "after_refresh")
        payload = {
            "attempt_id": attempt_id,
            "generation": attempt["generation"],
            "terminal_event": terminal["event_id"],
            "original_cursor": attempt["original_cursor"],
            "processed_cutoff": output.get("processed_cutoff", attempt["cutoff"]),
            "state": output["state"],
            "text": output["text"],
            "outputs": output.get("outputs", []),
            "changes": output.get("changes", []),
        }
        if output.get("wait"):
            payload["wait"] = output["wait"]
        if output.get("next_work") is not None:
            payload["next_work"] = output["next_work"]
        return self.client.call(
            "commit_outcome",
            payload,
            attempt_id + ":outcome",
            expected_heads=output.get("expected_heads", {}),
        )
