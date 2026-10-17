"""Sleep preparation for the existing native Pi conversation, without dispatch."""

from __future__ import annotations

import base64
import json
from typing import Any, cast
from uuid import uuid4

from zaratustra_core import Core, CoreError

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

    def start(self, work_id: str, profile: dict[str, Any], portion: int = 16) -> dict[str, Any]:
        self.sleep.start(
            work_id=work_id,
            scope=self.scope,
            portion=portion,
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
        self.client.call(
            "claim_dispatch",
            {"attempt_id": attempt, "generation": prepared["generation"], "resource_upper": None},
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
        context["resource_state"] = {
            "call_limit": None,
            "mode": "unlimited",
            "reservation_upper": None,
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
        context["coverage"] = (
            "First 100 catalog refs; exact pinned inputs and Sleep sources retained."
        )
        context["instructions"] = (
            "Follow the pinned Sleep Method in ordinary Pi. Stage actual ready/completed "
            "metadata with zara_result, then speak normally. Preserve unexamined sources. "
            "Memory and Method writes require this Sleep scope's explicit grants. "
            "No automatic replay of unknown tools."
        )
        return context

    def checkpoint(self, work_id: str, attempt: str) -> None:
        self.sleep._checkpoint(work_id, attempt)
