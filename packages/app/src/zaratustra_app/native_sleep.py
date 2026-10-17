"""Sleep preparation for the existing native Pi conversation, without dispatch."""

from __future__ import annotations

import base64
import json
from typing import Any, cast
from uuid import uuid4

from zaratustra_core import Core, CoreError, digest

from .conversation import pin_profile
from .coordinator import Coordinator
from .sleep import Sleep


class NativeSleep:
    def __init__(self, core: Core, token: str, scope: str):
        self.scope = scope
        self.owner = core.connect(token)
        self.client = core.connect(
            core.grant(
                token,
                "native-sleep:" + scope,
                [
                    "read",
                    "apply_changes",
                    "open_work",
                    "prepare_attempt",
                    "claim_dispatch",
                    "observe_attempt",
                    "commit_outcome",
                    "control_work",
                    "reserve_tool",
                    "write:memory:" + scope,
                    "write:method:" + scope,
                ],
                origin="host",
            )
        )
        self.coordinator = Coordinator(self.client)
        self.sleep = Sleep(self.client)

    def _cancelled_fact(self, work: dict[str, Any]) -> bool:
        if work["status"] != "cancelled":
            return False
        control = next(
            (
                i
                for i in self.coordinator.rows("intents")
                if i["kind"] == "control" and i["subject"] == work["id"]
            ),
            None,
        )
        attempts = self.coordinator.rows(
            "attempts", work=work["id"], columns=["id", "status", "generation"]
        )
        if (
            control is None
            or json.loads(control["body"]).get("action") != "cancel"
            or work["generation"] < 2
            or any(
                a["generation"] >= work["generation"]
                or a["status"] not in {"fenced", "finished", "superseded"}
                for a in attempts
            )
        ):
            raise CoreError("stale_basis", "sleep.cancellation_proof", "reconcile")
        return True

    def _components(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Validate lineage before retiring any component; old effects remain untouched."""
        works: dict[str, Any] = {}
        for work in self.coordinator.rows("works"):
            body = json.loads(work["body"])
            if body.get("scope") == self.scope and body.get("goal") == "Sleep":
                if body["method_ref"]["id"] != "native-sleep-method:" + self.scope:
                    raise CoreError("stale_basis", "sleep.method_lineage", "reconcile")
                works[work["id"]] = work
        children: dict[str, str] = {}
        roots = []
        for identity, work in works.items():
            body = json.loads(work["body"])
            link = body.get("continuation")
            if link is None:
                roots.append(identity)
                continue
            parent_id = link.get("parent_work_id")
            if parent_id not in works:
                raise CoreError("stale_basis", "sleep.missing_predecessor", "reconcile")
            parent = works[parent_id]
            attempts = self.coordinator.rows(
                "attempts", work=parent_id, columns=["id", "status", "generation"]
            )
            attempt = next((a for a in attempts if a["id"] == link.get("attempt_id")), None)
            result = next(
                (
                    r
                    for r in self.coordinator.rows("results", work=parent_id)
                    if r["attempt"] == link.get("attempt_id")
                ),
                None,
            )
            if (
                link.get("kind") != "late"
                or parent["status"] != "completed"
                or body["conversation"] != json.loads(parent["body"])["conversation"]
                or attempt is None
                or attempt["status"] != "finished"
                or not attempts
                or attempts[-1]["id"] != attempt["id"]
                or result is None
                or result["fingerprint"] != link.get("result_hash")
                or json.loads(result["body"])["state"] != "completed"
            ):
                raise CoreError("stale_basis", "sleep.invalid_predecessor", "reconcile")
            if parent_id in children:
                raise CoreError("stale_basis", "sleep.lineage_fork", "reconcile")
            predecessor_records = []
            for ref in link.get("basis_refs", []):
                if ref.get("role") != "exact":
                    raise CoreError("stale_basis", "sleep.invalid_predecessor", "reconcile")
                record = self.client.call("read_exact", ref, uuid4().hex)
                value = record["body"]["value"]
                if (
                    record["scope"] == self.scope
                    and isinstance(value, dict)
                    and value.get("format") in {"sleep-progress/v1", "sleep-progress/v2"}
                    and value.get("work_id") == parent_id
                ):
                    predecessor_records.append(record)
            if (
                len(predecessor_records) != 1
                or link.get("parent_work_revision") != parent["revision"]
            ):
                raise CoreError("stale_basis", "sleep.invalid_predecessor", "reconcile")
            children[parent_id] = identity
        visited: set[str] = set()
        frontier = []
        for root in roots:
            identity = root
            while True:
                if identity in visited:
                    raise CoreError("stale_basis", "sleep.lineage_cycle", "reconcile")
                visited.add(identity)
                if identity not in children:
                    break
                identity = children[identity]
            leaf = works[identity]
            if not self._cancelled_fact(leaf):
                frontier.append(leaf)
        if len(visited) != len(works):
            raise CoreError("stale_basis", "sleep.lineage_cycle", "reconcile")
        return works, frontier

    def verified_cancelled_work(self, work_id: str) -> bool:
        """Explicit-start mapping recovery seam; never resolves or reactivates old effects."""
        works, _ = self._components()
        if work_id not in works:
            raise CoreError("stale_basis", "sleep.cancellation_work", "reconcile")
        return self._cancelled_fact(works[work_id])

    def follow(
        self, profile: dict[str, Any], portion: int = 16, *, call_limit: int | None = None
    ) -> dict[str, Any]:
        """An explicit owner request follows the unique retained Sleep frontier."""
        if type(portion) is not int or not 1 <= portion <= 100:
            raise CoreError("invalid_request", "sleep.portion")
        _, frontier = self._components()
        if not frontier:
            return self.start(
                "native-sleep-work:" + uuid4().hex, profile, portion, call_limit=call_limit
            )
        if len(frontier) != 1:
            raise CoreError("stale_basis", "native.ambiguous_unclaimed_sleep", "reconcile")
        work = frontier[0]
        body = json.loads(work["body"])
        attempts = self.coordinator.rows("attempts", work=work["id"])
        if not attempts:
            if work["status"] != "ready" or self.coordinator.rows("actions", work=work["id"]):
                raise CoreError("outcome_unknown", "sleep.pending_attempt", "reconcile")
            if body.get("continuation", {}).get("kind") == "late":
                self.sleep.initialize_successor(work["id"], portion=portion)
            else:
                self.sleep.start(
                    work_id=work["id"],
                    scope=self.scope,
                    portion=portion,
                    call_limit=body["call_limit"],
                    method_id=body["method_ref"]["id"],
                )
            return self._claim(work["id"], profile)
        latest = attempts[-1]
        result = next(
            (
                r
                for r in self.coordinator.rows("results", work=work["id"])
                if r["attempt"] == latest["id"]
            ),
            None,
        )
        if (
            result is None
            or latest["status"] not in {"finished", "superseded"}
            or any(
                a["state"] not in {"terminal", "not_received"}
                for a in self.coordinator.rows("actions", work=work["id"])
            )
        ):
            raise CoreError("outcome_unknown", "sleep.pending_attempt", "reconcile")
        if work["status"] == "ready" and json.loads(result["body"])["state"] == "ready":
            return self.resume(work["id"], profile, portion)
        if work["status"] != "completed" or json.loads(result["body"])["state"] != "completed":
            raise CoreError("stale_basis", "sleep.terminal_predecessor", "reconcile")
        self.checkpoint(work["id"], latest["id"])
        return self._successor(work["id"], latest["id"], result["fingerprint"], profile, portion)

    def _successor(
        self,
        parent_id: str,
        attempt_id: str,
        result_hash: str,
        profile: dict[str, Any],
        portion: int,
    ) -> dict[str, Any]:
        parent = self.coordinator.rows("works", work=parent_id)[0]
        body = json.loads(parent["body"])
        progress = self.sleep.progress(parent_id)
        basis = {
            "attempt_id": attempt_id,
            "result_hash": result_hash,
            "work_revision": parent["revision"],
            "basis_refs": [
                {"id": progress["id"], "revision": progress["revision"], "role": "must_be_current"}
            ],
        }
        limit = body["call_limit"]
        remainder = None if limit is None else limit - parent["reserved"]
        if remainder is not None and remainder <= 0:
            raise CoreError("resource_exhausted", "continuation.calls")
        method = next(
            h for h in self.coordinator.rows("heads") if h["id"] == body["method_ref"]["id"]
        )
        work_id = "native-sleep-work:" + digest(basis)
        self.client.call(
            "open_work",
            {
                "id": work_id,
                "conversation": body["conversation"],
                "goal": "Sleep",
                "scope": self.scope,
                "inputs": [],
                "call_limit": remainder,
                "continuation_policy": "durable",
                "method_ref": {
                    "id": method["id"],
                    "revision": method["revision"],
                    "role": "must_be_current",
                },
                "continuation_from": basis,
            },
            work_id + ":open",
        )
        self.sleep.initialize_successor(work_id, portion=portion)
        return self._claim(work_id, profile)

    def start(
        self,
        work_id: str,
        profile: dict[str, Any],
        portion: int = 16,
        *,
        call_limit: int | None = None,
    ) -> dict[str, Any]:
        self.sleep.start(
            work_id=work_id,
            scope=self.scope,
            portion=portion,
            call_limit=call_limit,
            method_id="native-sleep-method:" + self.scope,
        )
        snapshot = {"attempts": self.coordinator.rows("attempts", work=work_id)}
        # A previous native send is never permission to regenerate or redispatch.
        if any(a["work"] == work_id for a in snapshot["attempts"]):
            raise CoreError("outcome_unknown", "sleep.pending_attempt", "reconcile")
        return self._claim(work_id, profile)

    def resume(self, work_id: str, profile: dict[str, Any], portion: int = 16) -> dict[str, Any]:
        if type(portion) is not int or not 1 <= portion <= 100:
            raise CoreError("invalid_request", "sleep.portion")
        snapshot = {
            table: self.coordinator.rows(table, work=work_id)
            for table in ("works", "attempts", "results")
        }
        work = next(w for w in snapshot["works"] if w["id"] == work_id)
        body = json.loads(work["body"])
        if body.get("scope") != self.scope or body.get("goal") != "Sleep":
            raise CoreError("denied", "sleep.resume_scope")
        attempts = [a for a in snapshot["attempts"] if a["work"] == work_id]
        latest = attempts[-1] if attempts else None
        result = next(
            (r for r in snapshot["results"] if latest and r["attempt"] == latest["id"]), None
        )
        if latest is None or result is None:
            raise CoreError("outcome_unknown", "sleep.pending_attempt", "reconcile")
        if work["status"] != "ready" or json.loads(result["body"])["state"] != "ready":
            raise CoreError("stale_basis", "sleep.not_ready", "reconcile")
        self.checkpoint(work_id, latest["id"])
        record = self.sleep.progress(work_id)
        progress = record["body"]["value"]
        if progress["remaining_refs"]:
            self.sleep.select_sources(
                work_id, progress["remaining_refs"][:portion], expected_revision=record["revision"]
            )
        elif progress["enumeration_cursor"][1] != 2147483647:
            self.sleep.continue_portion(work_id, portion=portion)
        self.coordinator.refresh_basis(work_id)
        return self._claim(work_id, profile)

    def _claim(self, work_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        previous_attempts = self.coordinator.rows("attempts", work=work_id)
        previous_actions = self.coordinator.rows("actions", work=work_id)
        finished = {r["attempt"] for r in self.coordinator.rows("results", work=work_id)}
        if any(
            a["status"] not in {"finished", "superseded"} or a["id"] not in finished
            for a in previous_attempts
        ) or any(a["state"] not in {"terminal", "not_received"} for a in previous_actions):
            raise CoreError("outcome_unknown", "sleep.pending_attempt", "reconcile")
        attempt_ids = {a["id"] for a in previous_attempts}
        action_ids = {a["id"] for a in previous_actions}
        while True:
            basis = self.sleep.progress(work_id)
            try:
                return self._prepare_claim(work_id, profile)
            except CoreError as error:
                if error.code != "resource_exhausted" or error.field != "context.max_bytes":
                    raise
                # Only this proven pre-dispatch rejection permits another preparation.
                # Every retry gets fresh Attempt/profile/command identities.
                work = self.coordinator.rows("works", work=work_id)[0]
                if (
                    work["status"] != "ready"
                    or {a["id"] for a in self.coordinator.rows("attempts", work=work_id)}
                    != attempt_ids
                    or {a["id"] for a in self.coordinator.rows("actions", work=work_id)}
                    != action_ids
                ):
                    raise CoreError(
                        "outcome_unknown", "sleep.pending_attempt", "reconcile"
                    ) from error
                record = self.sleep.progress(work_id)
                if record["revision"] != basis["revision"]:
                    raise CoreError(
                        "stale_basis", "sleep.progress_revision", "after_refresh"
                    ) from error
                selected = record["body"]["value"]["selected_source_refs"]
                if len(selected) <= 1:
                    self.sleep.select_sources(
                        work_id,
                        selected,
                        context_blocked=True,
                        expected_revision=record["revision"],
                    )
                    raise
                self.sleep.select_sources(
                    work_id,
                    selected[: max(1, len(selected) // 2)],
                    expected_revision=record["revision"],
                )

    def _prepare_claim(self, work_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        snapshot = self.coordinator.tables("heads")
        attempt = work_id + ":native-attempt:" + uuid4().hex
        profile_ref = pin_profile(self.owner, attempt + ":profile", profile)
        selection = {
            "catalog_refs": [
                {"id": h["id"], "revision": h["revision"]}
                for h in snapshot["heads"]
                if not h["id"].startswith("native-host:")
            ][:100],
            "prior_message_sequences": [],
            "prior_result_attempts": [],
            "prior_wait_ids": [],
        }
        prepared = self.coordinator.prepare(
            work_id, attempt, profile_ref, context_selection=selection
        )
        policy = json.loads(self.coordinator.rows("works", work=work_id)[0]["body"])["call_limit"]
        self.client.call(
            "claim_dispatch",
            {
                "attempt_id": attempt,
                "generation": prepared["generation"],
                "resource_upper": None if policy is None else 1,
            },
            attempt + ":claim",
            action_id=attempt + ":action",
        )
        return {
            "attempt": attempt,
            "work": work_id,
            "generation": prepared["generation"],
            "scope": self.scope,
            "mode": "sleep",
            "staged": {},
            "profile": profile,
        }

    def context(self, mapping: dict[str, Any]) -> dict[str, Any]:
        snapshot = {
            table: self.coordinator.rows(table, work=mapping["work"])
            for table in ("attempts", "works", "actions")
        }
        attempt = next(a for a in snapshot["attempts"] if a["id"] == mapping["attempt"])
        context = cast(dict[str, Any], json.loads(attempt["body"]))
        work = next(w for w in snapshot["works"] if w["id"] == mapping["work"])
        policy = json.loads(work["body"])["call_limit"]
        context["resource_state"] = {
            "call_limit": policy,
            "mode": "unlimited" if policy is None else "finite",
            "reservation_upper": None if policy is None else 1,
            "consumed_resource": work["reserved"],
            "unresolved_calls": [
                a["id"]
                for a in snapshot["actions"]
                if a["attempt"] == attempt["id"] and a["state"] not in {"terminal", "not_received"}
            ],
        }
        context["raw_messages"] = [
            base64.b64decode(m["raw"]).decode("utf-8") for m in context["messages"]
        ]
        context["cancelled_history"] = [
            {"work_id": w["id"], "status": "cancelled", "analysed_boundary_credit": False}
            for w in self.coordinator.rows("works")
            if w["status"] == "cancelled"
            and json.loads(w["body"]).get("goal") == "Sleep"
            and json.loads(w["body"]).get("scope") == self.scope
        ]
        context["coverage"] = (
            "First 100 catalog refs; exact pinned inputs and Sleep sources retained."
        )
        context["instructions"] = (
            "Follow the pinned Sleep Method in ordinary Pi. Stage actual ready/completed "
            "metadata with zara_result, then speak normally. Preserve unexamined sources. "
            "Memory and Method writes require this Sleep scope's explicit grants. "
            "No automatic replay of unknown tools. "
            "Stage changes to pinned memory or Method in zara_result for atomic completion. "
            "An intermediate memory or Method revision makes the exact basis stale; "
            "do not claim completion or rebase it automatically."
            " Copy the delivered progress template's exact format (v1 or v2), predecessor, "
            "transition and range_start; inherited evidence remains attributed to its predecessor."
        )
        if self.scope == "space":
            context["scope_contract"] = {
                "work_ownership": "workspace (space)",
                "source_read_domain": "all permitted Activities and unassigned/global history",
                "source_provenance": "Each source keeps its original scope, IDs and ownership.",
                "write_authority": (
                    "Global memory/Method grants only; local destinations need explicit grants."
                ),
            }
            context["instructions"] += (
                " This Work belongs to the workspace; its read domain spans all permitted "
                "Activities and unassigned/global sources. Work ownership is not source ownership. "
                "Preserve each material's original scope, IDs, goals and assignments. "
                "Global reading grants no local write authority. "
                "Use the existing global memory/Method grants only. "
                "For an intended local correction without a destination grant, retain a targeted "
                "proposal naming that local destination; never store local truth as universal "
                "memory or move a local record into space to bypass rights. Shared applicability "
                "requires your supported judgment, not an inference from global read access. "
                "Sleep needs no Activity output: stage real output refs or outputs:[] and then "
                "the honest final response. No Activity, finding or analysed coverage is invented."
            )
        if "continuation" not in context["work"] and context["cancelled_history"]:
            context["instructions"] += (
                " This is a fresh pass after explicit cancellation, not continuation of a "
                "cancelled queue. Use current history and current memory. Old successful changes "
                "remain; old unknown effects stay unknown. "
                "Never replay an old action automatically."
            )
        return context

    def checkpoint(self, work_id: str, attempt: str) -> None:
        self.sleep._checkpoint(work_id, attempt)
