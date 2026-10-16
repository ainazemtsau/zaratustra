"""Sleep is an ordinary Work using public Core records, Attempts and continuation."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, cast
from uuid import uuid4

from zaratustra_core import Client, CoreError

from .coordinator import Coordinator
from .executor_port import Executor

SLEEP_INSTRUCTIONS = """Sleep method sleep/1. Work only inside granted scope and finite calls.
You are the meaning-making agent; do not ask the owner to pick problems. A finding
is not guaranteed. Use the actual source bytes in sleep_sources, not catalog titles.
1 Recover Work, exact Method, progress, resource_state, current rights, and outcomes
of previous changes. An unresolved send is unknown and its reservation stays spent.
2 Examine a bounded portion at source_high_watermark. Enumeration, selection,
delivery and analysis are distinct. Preserve enumeration_cursor and separately
unexplored_coverage_position for a bounded exploration outside known relations.
3 Maintain useful memory from ordinary work, successes AND errors, not complaints
alone. Apply necessary permitted corrections with exact provenance; preserve doubt.
4 Choose useful questions yourself. Make a bounded comparison beyond existing
links, including an ordinary or successful source. Record no finding honestly.
5 Ground claims in exact source refs/fragments. Distinguish observation, assertion
and hypothesis; consider alternatives, counterexamples and previous failed attempts.
6 Apply a useful permitted memory correction, or leave a proposal when rights are
insufficient. Reusable improvements may create a new scoped Method revision after
proportionate checking. Never change grants, acceptance, code or own authority.
Method rollback is another revision, preserving old bytes and limiting its scope.
7 Link changes to actual later Work outcomes delivered in history, including
negative outcomes. New work must use current applicable memory and Method. Revisit,
narrow or roll back a Method if outcomes oppose it; do not invent feedback.
8 Save a new sleep-progress/v1 data revision with all fields from its delivered
template. Preserve source_high_watermark, exact refs and honest remainder/unknown,
stop_reason and continuation. Reaching the cursor proves enumeration only.
Analysis is your claim, not machine proof. Persist analysis as ordinary data with
body {format:'sleep-analysis/v1', sources:[source_ref,...], content:<free text/object>}.
Keep each selected source in remaining_refs until such an analysis is retained.
For each actual delivery append context.sleep_delivery_manifest; do not fabricate
delivery from enumeration. Copy resource_state.consumed_resource. For terminal
progress use unresolved_calls=[] only for this returned terminal; preserve others.
Use subject changes only (data,memory,method/activity) and exact expected_heads.
Memory and Method content are free text or objects; no prescribed subject template.
Use the executor's response_contract for its exact wire representation. Method
defines the obligations; the executor codec defines serialization. Persist analysis
before progress. An analysis exact ref is an object containing id and revision.
Use ready for a further bounded portion; completed means this bounded pass ended,
never that all the environment is understood. Unknown/unexamined material remains.
Do not request external tools not present. No mandatory interview or activity form.
"""


class Sleep:
    """No SleepRun or independent status. Every effect goes through C3/C4/C5/C8."""

    def __init__(self, client: Client):
        self.client = client
        self.coordinator = Coordinator(client)

    def _save(
        self, change: dict[str, Any], revision: int, command: str | None = None
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.client.call(
                "apply_changes",
                {"changes": [change]},
                command or str(uuid4()),
                expected_heads={change["id"]: revision},
            )["refs"][0],
        )

    def start(
        self,
        *,
        work_id: str,
        scope: str = "space",
        call_limit: int,
        portion: int = 16,
        method_id: str = "sleep-method",
    ) -> dict[str, Any]:
        snapshot = self.coordinator.snapshot()
        method = next((h for h in snapshot["heads"] if h["id"] == method_id), None)
        if method is None:
            ref = self._save(
                {
                    "id": method_id,
                    "kind": "method",
                    "key": "sleep",
                    "scope": scope,
                    "body": {
                        "version": "sleep/1",
                        "status": "active",
                        "instructions": SLEEP_INSTRUCTIONS,
                    },
                },
                0,
                "sleep:install:" + method_id,
            )
        else:
            if method["kind"] != "method" or method["scope"] != scope:
                raise CoreError("identity_conflict", "sleep.method_scope")
            ref = {"id": method_id, "revision": method["revision"]}
        ref["role"] = "must_be_current"
        existing = next((w for w in snapshot["works"] if w["id"] == work_id), None)
        if existing:
            original = json.loads(existing["body"])
            if (
                original["goal"] != "Sleep"
                or original["call_limit"] != call_limit
                or original.get("scope", "space") != scope
                or original["method_ref"]["id"] != method_id
            ):
                raise CoreError("idempotency_conflict", "sleep.start")
            ref = original["method_ref"]
        else:
            self.client.call(
                "open_work",
                {
                    "id": work_id,
                    "conversation": work_id + ":conversation",
                    "goal": "Sleep",
                    "scope": scope,
                    "method_ref": ref,
                    "inputs": [],
                    "call_limit": call_limit,
                    "continuation_policy": "durable",
                },
                work_id + ":open",
            )
        current = next((h for h in snapshot["heads"] if h["id"] == work_id + ":progress"), None)
        if current:
            progress = {"id": current["id"], "revision": current["revision"]}
            record = self.client.call("read_exact", progress, str(uuid4()))
            more = record["body"]["value"]["enumeration_cursor"][1] != 2147483647
            if existing and existing["status"] != "ready":
                return {"work_id": work_id, "progress_ref": progress, "has_more": more}
        else:
            return self._start_progress(work_id, scope, portion, ref)
        self._bind_progress(work_id, progress)
        return {"work_id": work_id, "progress_ref": progress, "has_more": more}

    def _start_progress(
        self, work_id: str, scope: str, portion: int, ref: dict[str, Any]
    ) -> dict[str, Any]:
        history = self.client.call("read_history", {"scope": scope, "limit": portion}, str(uuid4()))
        sources = [s["source_ref"] for s in history["sources"]]
        body = {
            "format": "sleep-progress/v1",
            "work_id": work_id,
            "method_ref": ref,
            "scope": scope,
            "source_high_watermark": history["high_watermark"],
            "enumeration_cursor": history["cursor"],
            "enumerated_source_refs": sources,
            "selected_source_refs": sources,
            "delivered_manifest_refs": [],
            "analysis_result_refs": [],
            "unexplored_coverage_position": {"status": "unexplored"},
            "applied_receipts": [],
            "proposed_changes": [],
            "remaining_refs": sources,
            "return_conditions": ["Further arrivals require a new bounded pass"],
            "consumed_resource": 0,
            "unresolved_calls": [],
            "stop_reason": "not_started",
            "continuation": "Review selected sources and explore beyond known relations",
        }
        progress = self._save(
            {
                "id": work_id + ":progress",
                "kind": "data",
                "key": "sleep-progress:" + work_id,
                "scope": scope,
                "body": body,
            },
            0,
            work_id + ":progress:create",
        )
        self._bind_progress(work_id, progress)
        return {"work_id": work_id, "progress_ref": progress, "has_more": history["has_more"]}

    def _bind_progress(self, work_id: str, progress: dict[str, Any]) -> None:
        state = self.coordinator.snapshot()
        work = next(w for w in state["works"] if w["id"] == work_id)
        if json.loads(work["body"])["inputs"] == [progress | {"role": "must_be_current"}]:
            return
        self.client.call(
            "control_work",
            {
                "work_id": work_id,
                "revision": work["revision"],
                "action": "refresh",
                "inputs": [progress | {"role": "must_be_current"}],
            },
            str(uuid4()),
        )

    def progress(self, work_id: str) -> dict[str, Any]:
        state = self.coordinator.snapshot()
        head = next(h for h in state["heads"] if h["id"] == work_id + ":progress")
        return self.client.call(
            "read_exact", {"id": head["id"], "revision": head["revision"]}, str(uuid4())
        )

    def continue_portion(self, work_id: str, *, portion: int = 16) -> dict[str, Any]:
        """Enumerate more at the SAME cutoff; never derive analysis or exploration coverage."""
        record = self.progress(work_id)
        body = dict(record["body"]["value"])
        history = self.client.call(
            "read_history",
            {
                "scope": body["scope"],
                "high_watermark": body["source_high_watermark"],
                "after_sequence": body["enumeration_cursor"][0],
                "after_index": body["enumeration_cursor"][1],
                "limit": portion,
            },
            str(uuid4()),
        )
        refs = [s["source_ref"] for s in history["sources"]]
        body["enumeration_cursor"] = history["cursor"]
        body["enumerated_source_refs"] += refs
        body["selected_source_refs"] = refs
        body["remaining_refs"] += refs
        self._account(body, work_id)
        result = self._save(
            {
                "id": record["id"],
                "kind": "data",
                "key": record["key"],
                "scope": record["scope"],
                "body": body,
            },
            record["revision"],
        )
        self.coordinator.refresh_basis(work_id)
        return result

    def _account(self, body: dict[str, Any], work_id: str) -> None:
        snapshot = self.coordinator.snapshot()
        work = next(w for w in snapshot["works"] if w["id"] == work_id)
        attempts = {a["id"] for a in snapshot["attempts"] if a["work"] == work_id}
        body["consumed_resource"] = work["reserved"]
        body["method_ref"] = json.loads(work["body"])["method_ref"]
        body["unresolved_calls"] = [
            a["id"]
            for a in snapshot["actions"]
            if a["attempt"] in attempts and a["state"] not in {"terminal", "not_received"}
        ]

    def run(self, work_id: str, profile_ref: dict[str, Any], executor: Executor) -> dict[str, Any]:
        try:
            return self._run(work_id, profile_ref, executor)
        except CoreError as error:
            if error.code == "resource_exhausted":
                self._stop_resource(work_id)
            raise

    def _stop_resource(self, work_id: str) -> None:
        work = next(w for w in self.coordinator.snapshot()["works"] if w["id"] == work_id)
        if work["status"] in {"ready", "running"}:
            self.client.call(
                "control_work",
                {
                    "work_id": work_id,
                    "revision": work["revision"],
                    "action": "pause",
                    "reason": "resource_exhausted",
                },
                str(uuid4()),
            )
        record = self.progress(work_id)
        body = deepcopy(record["body"]["value"])
        self._account(body, work_id)
        body["stop_reason"] = "resource_exhausted"
        body["continuation"] = (
            "Resource exhausted; preserve remainder and reservations. "
            "Owner must choose a new finite Work."
        )
        if body != record["body"]["value"]:
            self._save(
                {
                    "id": record["id"],
                    "kind": "data",
                    "key": record["key"],
                    "scope": record["scope"],
                    "body": body,
                },
                record["revision"],
            )

    def _run(self, work_id: str, profile_ref: dict[str, Any], executor: Executor) -> dict[str, Any]:
        """One ordinary bounded Attempt. Reopen uses Coordinator.recover, never regeneration."""
        from .executor_port import Pi

        snapshot = self.coordinator.snapshot()
        attempts = [a for a in snapshot["attempts"] if a["work"] == work_id]
        work = next(w for w in snapshot["works"] if w["id"] == work_id)
        resource_pause = any(
            intent["kind"] in {"control", "resource"}
            and intent["subject"] == work_id
            and json.loads(intent["body"]).get("reason") == "resource_exhausted"
            for intent in snapshot["intents"]
        )
        if not attempts and work["status"] == "paused":
            if resource_pause:
                raise CoreError("resource_exhausted", "calls")
            raise CoreError("stale_basis", "sleep.paused", "after_refresh")
        if attempts:
            latest = attempts[-1]
            terminal = any(
                o["attempt"] == latest["id"]
                and json.loads(o["body"])["kind"] == "terminal"
                and not json.loads(o["body"])["late"]
                for o in snapshot["observations"]
            )
            result = next((r for r in snapshot["results"] if r["attempt"] == latest["id"]), None)
            work = next(w for w in snapshot["works"] if w["id"] == work_id)
            if terminal and result is None and latest["status"] in {"claimed", "prepared"}:
                recovered = self.coordinator.recover(
                    latest["id"],
                    pi=isinstance(executor, Pi),
                    decoder=getattr(executor, "decode", None),
                )
                self._checkpoint(work_id, latest["id"])
                return recovered
            if result is not None:
                self._checkpoint(work_id, latest["id"])
                if work["status"] == "completed":
                    return json.loads(result["body"])  # type: ignore[no-any-return]
            if work["status"] == "paused":
                if resource_pause:
                    raise CoreError("resource_exhausted", "calls")
                raise CoreError("stale_basis", "sleep.paused", "after_refresh")
            if latest["status"] == "prepared":
                self.coordinator.dispatch(latest["id"], latest["generation"], executor)
                recovered = self.coordinator.recover(
                    latest["id"],
                    pi=isinstance(executor, Pi),
                    decoder=getattr(executor, "decode", None),
                )
                self._checkpoint(work_id, latest["id"])
                return recovered
            if latest["status"] in {"claimed", "unknown"}:
                raise CoreError("outcome_unknown", "sleep.pending_attempt", "reconcile")
            progress = self.progress(work_id)["body"]["value"]
            if work["status"] == "ready" and progress["enumeration_cursor"][1] != 2147483647:
                self.continue_portion(work_id)
        self.coordinator.refresh_basis(work_id)
        attempt_id = work_id + ":" + uuid4().hex
        prepared = self.coordinator.prepare(work_id, attempt_id, profile_ref)
        self.coordinator.dispatch(attempt_id, prepared["generation"], executor)
        result = self.coordinator.recover(
            attempt_id, pi=isinstance(executor, Pi), decoder=getattr(executor, "decode", None)
        )
        self._checkpoint(work_id, attempt_id)
        return result

    def _checkpoint(self, work_id: str, attempt_id: str) -> None:
        """Record mechanical delivery/receipts only; never infer analysis or coverage."""
        record = self.progress(work_id)
        body = deepcopy(record["body"]["value"])
        state = self.coordinator.snapshot()
        attempt = next(a for a in state["attempts"] if a["id"] == attempt_id)
        pinned = json.loads(attempt["body"])
        manifest = pinned["sleep_delivery_manifest"]
        if manifest not in body["delivered_manifest_refs"]:
            body["delivered_manifest_refs"].append(manifest)
        receipt = attempt_id + ":outcome"
        result = self.client.call("lookup_receipt", {"command_id": receipt}, str(uuid4()))
        if result["result"].get("refs") and receipt not in body["applied_receipts"]:
            body["applied_receipts"].append(receipt)
        self._account(body, work_id)
        work = next(w for w in state["works"] if w["id"] == work_id)
        if body["stop_reason"] == "not_started":
            body["stop_reason"] = "terminal_received"
            body["continuation"] = "Analysis progress was not reported; preserve remaining sources."
        if (
            work["status"] == "paused"
            and work["reserved"] >= json.loads(work["body"])["call_limit"]
        ):
            body["stop_reason"] = "resource_exhausted"
            body["continuation"] = (
                "Preserve remainder; no further inference within the exhausted Work."
            )
        if body != record["body"]["value"]:
            self._save(
                {
                    "id": record["id"],
                    "kind": "data",
                    "key": record["key"],
                    "scope": record["scope"],
                    "body": body,
                },
                record["revision"],
            )

    def open_work(self, payload: dict[str, Any], *, scope: str = "space") -> dict[str, Any]:
        """Ordinary work uses the common coordinator's current-memory admission."""
        return self.coordinator.open_work(payload, scope=scope)


def sleep_method_json() -> str:
    """Inspectable versioned resource, with no runtime I/O."""
    return json.dumps({"version": "sleep/1", "instructions": SLEEP_INSTRUCTIONS})
