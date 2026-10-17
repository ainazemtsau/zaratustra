"""Native Pi lifecycle adapter. Core is authority; outside tools are observations."""

from __future__ import annotations

import base64
import json
from typing import Any
from uuid import uuid4

from zaratustra_core import Core, CoreError

from .conversation import Conversation, pin_profile
from .ordinary import EXECUTION_ID, EXECUTION_METHOD, ROUTING_ID, ROUTING_METHOD, subject_scope

PREFIX = "native-host:"


class NativeSession:
    def __init__(self, core: Core, token: str, session_id: str):
        if not session_id:
            raise ValueError("Native session ID required")
        self.owner = core.connect(token)
        self.core, self.token = core, token
        self.session_id = session_id
        self.mapping_id = PREFIX + "ordinary"
        self.conversation = Conversation(core, token, self.mapping_id)
        self.coordinator = self.conversation.coordinator
        self.profile: dict[str, Any] = {"adapter": "ordinary-native-pi"}

    def _load(self) -> tuple[int, dict[str, Any]]:
        head = next((h for h in self.coordinator.rows("heads") if h["id"] == self.mapping_id), None)
        if head is None:
            return 0, {}
        record = self.owner.call(
            "read_exact", {"id": self.mapping_id, "revision": head["revision"]}, uuid4().hex
        )
        mapping = record["body"]["value"]
        if mapping.get("mode") == "sleep":
            self.coordinator = self._sleep(mapping["scope"]).coordinator
            return head["revision"], mapping
        if mapping.get("mode") == "review":
            self.coordinator = self._review(mapping["scope"]).coordinator
            return head["revision"], mapping
        if mapping.get("scope") or not mapping.get("attempt"):
            return head["revision"], mapping
        retained = next(
            (
                r
                for r in self.coordinator.rows("results", work=mapping["work"])
                if r["attempt"] == mapping["attempt"]
            ),
            None,
        )
        if retained and not mapping.get("scope"):
            result = json.loads(retained["body"])
            child = result.get("next_work_id")
            if child:
                work = self.coordinator.rows("works", work=child)[0]
                attempts = self.coordinator.rows("attempts", work=child)
                actual_profile = self.profile
                self.profile = mapping["profile"]
                if attempts:
                    attempt = attempts[-1]
                    mapping = mapping | {
                        "work": child,
                        "attempt": attempt["id"],
                        "generation": attempt["generation"],
                        "incomplete": True,
                    }
                else:
                    mapping = self._claim(child)
                mapping["scope"] = json.loads(work["body"])["scope"]
                self._save(head["revision"], mapping)
                self.profile = actual_profile
                return head["revision"] + 1, mapping
        return head["revision"], mapping

    def _save(self, revision: int, value: dict[str, Any]) -> None:
        self.owner.call(
            "apply_changes",
            {
                "changes": [
                    {"id": self.mapping_id, "kind": "data", "key": self.mapping_id, "body": value}
                ]
            },
            uuid4().hex,
            expected_heads={self.mapping_id: revision},
        )

    def _assert_session(self, mapping: dict[str, Any]) -> None:
        if mapping.get("attempt") and mapping.get("session_id") != self.session_id:
            raise CoreError("stale_basis", "native.session", "reconcile")

    def context(self) -> dict[str, Any]:
        revision, mapping = self._load()
        if mapping.get("mode") == "sleep":
            return {
                "state": "attached",
                "current": mapping,
                "sleep": self._sleep(mapping["scope"]).context(mapping),
                "waiting": [],
            }
        if mapping.get("mode") == "review":
            return {
                "state": "attached",
                "current": mapping,
                "waiting": [],
                "review": self._review(mapping["scope"]).context(mapping),
            }
        snapshot = {
            table: self.coordinator.rows(table, conversation=self.mapping_id)
            for table in ("works", "waits", "results")
        }
        snapshot.update(
            {
                table: self.coordinator.rows(table, work=mapping["work"])
                if mapping.get("work")
                else []
                for table in ("attempts", "actions")
            }
        )
        snapshot["heads"] = self.coordinator.rows("heads")
        unresolved = [
            {"id": w["id"], "status": w["status"], "scope": json.loads(w["body"])["scope"]}
            for w in snapshot["works"]
            if w["conversation"] == self.mapping_id
            and w["status"] not in {"completed", "cancelled"}
            and w["id"] != mapping.get("work")
        ]
        attempt = next((a for a in snapshot["attempts"] if a["id"] == mapping.get("attempt")), None)
        pinned = json.loads(attempt["body"]) if attempt else None
        waits = [
            w
            for w in snapshot["waits"]
            if w["conversation"] == self.mapping_id and w["status"] == "waiting"
        ]
        # Host transport bookkeeping is never offered as editable subject data.
        snapshot["heads"] = [h for h in snapshot["heads"] if not h["id"].startswith(PREFIX)]
        snapshot = {
            key: rows[-100:] if key == "results" else rows[:100]
            for key, rows in snapshot.items()
            if key in {"heads", "results", "attempts", "actions", "works"}
            and isinstance(rows, list)
        }
        from .native_verdict import delivery

        latest_delivery = None
        try:
            delivered = delivery(self.core, self.token, mapping.get("scope"), compact=True)
            latest_delivery = {
                key: delivered[key]
                for key in (
                    "activity_id",
                    "attempt_id",
                    "result_hash",
                    "review_ref",
                    "related_results",
                    "related_coverage",
                )
            }
        except CoreError as error:
            if error.code != "invalid_request" or error.field != "native.no_delivered_result":
                raise
        return {
            "state": "attached",
            "mapping_revision": revision,
            "current": mapping,
            "unmapped_work": unresolved,
            "waiting": [
                {
                    "id": w["id"],
                    "revision": w["revision"],
                    "question": json.loads(w["body"])["question"],
                }
                for w in waits
            ],
            "core": snapshot,
            "pinned": pinned,
            "latest_delivery": latest_delivery,
            "coverage": (
                "First 100 non-host heads; first 100 conversation Works and latest 100 "
                "conversation results. Attempts/actions show only the current Work's first "
                "100 rows, or none when idle/unmapped. Waiting questions belong to this "
                "conversation; mandatory pinned execution inputs are complete. "
                "Use zara_read for pages, exact records or history."
            ),
            "projection": {
                "conversation": self.mapping_id,
                "attempts_actions_work": mapping.get("work"),
                "max_rows_per_core_table": 100,
                "retained_history": (
                    "Use Core read_page/read_history; omitted rows remain retained."
                ),
            },
            "instructions": (
                "Use zara_route to choose an Activity before useful work. "
                "Use normal Pi coding tools. Their effects are observations, "
                "not Core transactions. Stage outputs with zara_result; speak normally. "
                "Core commits actual final assistant text only at agent_settled. "
                "Pinned Methods describe JSON for older adapters; here use route/result "
                "tools for metadata and ordinary plaintext for the actual reply. "
                "zara_result accepts only outputs, changes, expected_heads, state and wait. "
                "Never pass a text field or an old JSON outcome envelope to that tool. "
                "After staging metadata, write the actual final reply normally in Pi. "
                "latest_delivery exposes retained review and related Activity result pointers. "
                "Read a matching independent review before continuing that delivered Activity; "
                "its supplied public read query requires no owner retelling. "
                "Unknown previous tools must never be repeated automatically."
            ),
        }

    def input(
        self, event_id: str, text: str, reply_to: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not event_id or not isinstance(text, str):
            raise ValueError("Exact native input and durable event ID required")
        revision, mapping = self._load()
        if not mapping:
            active = [
                w
                for w in self.coordinator.rows("works", conversation=self.mapping_id)
                if w["conversation"] == self.mapping_id
                and w["status"] not in {"completed", "cancelled"}
            ]
            if active:
                raise CoreError("outcome_unknown", "native.unmapped_work", "reconcile")
        if mapping.get("wait") and reply_to is None:
            raise CoreError("stale_basis", "native.addressed_reply_required", "reconcile")
        if mapping.get("attempt") and not mapping.get("wait"):
            raise CoreError("outcome_unknown", "native.previous_attempt", "reconcile")
        if reply_to is not None and reply_to != mapping.get("wait"):
            raise CoreError("stale_basis", "native.wait_ref", "reconcile")
        self.owner.call(
            "ingest_message",
            {
                "conversation": self.mapping_id,
                "event_id": event_id,
                "raw_base64": base64.b64encode(text.encode()).decode(),
            }
            | ({"reply_to": reply_to} if reply_to else {}),
            "native-input:" + event_id,
        )
        if reply_to:
            self._save(revision, self._claim(mapping["work"]) | {"scope": mapping["scope"]})
            return self.context()
        for identity, method in [(ROUTING_ID, ROUTING_METHOD), (EXECUTION_ID, EXECUTION_METHOD)]:
            if not any(h["id"] == identity for h in self.coordinator.rows("heads")):
                self.owner.call(
                    "apply_changes",
                    {
                        "changes": [
                            {
                                "id": identity,
                                "kind": "method",
                                "key": method.splitlines()[0],
                                "body": method,
                            }
                        ]
                    },
                    identity + ":create",
                    expected_heads={identity: 0},
                )
        work_id = self.mapping_id + ":work:" + event_id
        self.coordinator.open_work(
            {
                "id": work_id,
                "conversation": self.mapping_id,
                "goal": "Choose Activity for exact human input",
                "method_ref": {"id": ROUTING_ID, "revision": 1},
                "call_limit": None,
                "continuation_policy": "durable",
            }
        )
        self._save(revision, self._claim(work_id))
        return self.context()

    def _claim(self, work_id: str) -> dict[str, Any]:
        attempt = work_id + ":native-attempt:" + uuid4().hex
        profile = pin_profile(
            self.owner,
            attempt + ":profile",
            self.profile | {"outside_tools": "observations-only", "session_id": self.session_id},
        )
        snapshot = self.coordinator.tables("heads")
        selection = {
            "catalog_refs": [
                {"id": h["id"], "revision": h["revision"]}
                for h in snapshot["heads"]
                if not h["id"].startswith(PREFIX)
            ][:100],
            "prior_message_sequences": [],
            "prior_result_attempts": [],
            "prior_wait_ids": [],
        }
        prepared = self.coordinator.prepare(work_id, attempt, profile, context_selection=selection)
        self.coordinator.client.call(
            "claim_dispatch",
            {"attempt_id": attempt, "generation": prepared["generation"], "resource_upper": None},
            attempt + ":claim",
            action_id=attempt + ":action",
        )
        return {
            "attempt": attempt,
            "work": work_id,
            "generation": prepared["generation"],
            "staged": {},
            "profile": self.profile,
            "session_id": self.session_id,
        }

    def reply(self, event_id: str, text: str, reply_to: dict[str, Any]) -> dict[str, Any]:
        return self.input(event_id, text, reply_to)

    def verify_profile(self) -> dict[str, Any]:
        _, mapping = self._load()
        if mapping.get("attempt") and (
            mapping.get("profile") != self.profile or mapping.get("session_id") != self.session_id
        ):
            raise CoreError("stale_basis", "native.actual_profile", "reconcile")
        return self.context()

    def _sleep(self, scope: str) -> Any:
        from .native_sleep import NativeSleep

        return NativeSleep(self.core, self.token, scope)

    def _review(self, scope: str) -> Any:
        from .native_review import NativeReview

        return NativeReview(self.core, self.token, scope)

    def start_review(self, scope: str, builder_attempt: str | None = None) -> dict[str, Any]:
        revision, mapping = self._load()
        if mapping.get("attempt"):
            raise CoreError("outcome_unknown", "native.previous_attempt", "reconcile")
        helper = self._review(scope)
        mapping = helper.start(
            "native-review-work:" + uuid4().hex,
            self.profile | {"session_id": self.session_id},
            builder_attempt,
        )
        mapping.update({"session_id": self.session_id, "profile": self.profile})
        self._save(revision, mapping)
        return self.context()

    def start_sleep(self, scope: str, portion: int = 16) -> dict[str, Any]:
        revision, mapping = self._load()
        resume = (
            mapping.get("mode") == "sleep" and mapping.get("ready") and mapping["scope"] == scope
        )
        if mapping.get("attempt") and not resume:
            raise CoreError("outcome_unknown", "native.previous_attempt", "reconcile")
        helper = self._sleep(scope)
        actual_profile = self.profile | {"session_id": self.session_id}
        mapping = (
            helper.resume(mapping["work"], actual_profile, portion)
            if resume
            else helper.follow(actual_profile, portion)
        )
        mapping["session_id"] = self.session_id
        mapping["profile"] = self.profile
        self._save(revision, mapping)
        return self.context()

    def _observe(self, mapping: dict[str, Any], event: str, kind: str, value: Any) -> None:
        self.coordinator.client.call(
            "observe_attempt",
            {
                "attempt_id": mapping["attempt"],
                "event_id": event,
                "kind": kind,
                "raw_base64": base64.b64encode(
                    json.dumps(value, ensure_ascii=False).encode()
                ).decode(),
            },
            mapping["attempt"] + ":observation:" + event,
        )

    def _validate_changes(
        self, payload: dict[str, Any], scope: str | None, sleep: bool = False
    ) -> None:
        for change in payload.get("changes", []):
            allowed = {"memory", "method", "data"} if sleep else {"activity", "data"}
            if change.get("kind") not in allowed or any(
                str(change.get(k, "")).startswith(PREFIX) for k in ("id", "key", "scope")
            ):
                raise CoreError("denied", "native.host_namespace")
            if sleep and change.get("scope", "space") != scope:
                raise CoreError("denied", "native.sleep_scope")
        if scope and not sleep:
            subject_scope(payload.get("changes", []), scope)

    def tool(self, name: str, call_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if name == "read":
            operation = payload.get("operation")
            if operation not in {"read_page", "read_exact", "read_history"}:
                raise CoreError("denied", "native.read_operation")
            if str(payload.get("arguments", {}).get("id", "")).startswith(PREFIX):
                raise CoreError("denied", "native.host_namespace")
            return self.owner.call(operation, payload.get("arguments", {}), uuid4().hex)
        if name == "context":
            return self.context()
        revision, mapping = self._load()
        if not mapping.get("attempt") or not call_id:
            raise CoreError("invalid_request", "native.no_attempt")
        if mapping.get("incomplete"):
            raise CoreError("outcome_unknown", "native.recovered_claim", "reconcile")
        self._assert_session(mapping)
        if mapping.get("ready"):
            raise CoreError("stale_basis", "native.sleep_ready_use_sleep_command", "after_refresh")
        sleep = mapping.get("mode") == "sleep"
        review = mapping.get("mode") == "review"
        if review and (
            name in {"route", "change"}
            or payload.get("changes")
            or payload.get("expected_heads")
            or payload.get("wait")
            or payload.get("state", "completed") != "completed"
        ):
            raise CoreError("denied", "native.read_only_review")
        self._validate_changes(payload, mapping.get("scope"), sleep)
        if name == "route":
            if mapping.get("scope"):
                raise CoreError("denied", "native.already_scoped")
            output = {"state": "completed", "text": "", **payload}
            self._observe(mapping, "terminal", "terminal", output)
            result = self.coordinator.recover(mapping["attempt"], ordinary=True)
            child = result["next_work_id"]
            self.profile = mapping["profile"]
            mapping = self._claim(child) | {"scope": payload["next_work"]["scope"]}
            self._save(revision, mapping)
            return self.context()
        if not mapping.get("scope"):
            raise CoreError("denied", "native.choose_activity_first")
        if name == "result":
            if set(payload) - {"changes", "expected_heads", "outputs", "state", "wait"}:
                raise CoreError("invalid_request", "native.result_metadata")
            states = {"ready", "completed"} if sleep else {"completed", "waiting"}
            if payload.get("state", "completed") not in states:
                raise CoreError("invalid_request", "native.result_state")
            if review and not any(
                r.get("id") == mapping["scope"] for r in payload.get("outputs", [])
            ):
                raise CoreError("invalid_request", "native.review_activity_output")
            self._save(revision, mapping | {"staged": payload})
            return {"state": "staged", "completed": False}
        if name == "change":
            command = mapping["attempt"] + ":tool:" + call_id
            self.coordinator.client.call(
                "reserve_tool",
                {
                    "attempt_id": mapping["attempt"],
                    "generation": mapping["generation"],
                    "native_id": call_id,
                    "command_id": command,
                },
                command + ":reserve",
            )
            return self.coordinator.client.call(
                "apply_changes",
                {
                    "changes": payload["changes"],
                    "tool": {
                        "attempt_id": mapping["attempt"],
                        "generation": mapping["generation"],
                        "native_id": call_id,
                    },
                },
                command,
                expected_heads=payload["expected_heads"],
            )
        raise ValueError("Unknown native tool")

    def observation(self, event_id: str, value: Any) -> dict[str, Any]:
        _, mapping = self._load()
        self._assert_session(mapping)
        if mapping.get("attempt"):
            self._observe(mapping, event_id, "progress", value)
        return {"state": "observed", "outside_effects": "unconfirmed"}

    def settled(
        self, event_id: str, text: str, aborted: bool, terminal: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        revision, mapping = self._load()
        self._assert_session(mapping)
        if not mapping.get("attempt"):
            return {"state": "idle"}
        failed_terminal = terminal is not None and (
            terminal.get("stop_reason") != "stop" or bool(terminal.get("error_message"))
        )
        if (
            aborted
            or failed_terminal
            or not text
            or not mapping.get("scope")
            or not mapping.get("staged")
        ):
            self._observe(
                mapping,
                event_id,
                "unknown",
                {"aborted": aborted, "text": text, "terminal": terminal},
            )
            return {
                "state": "incomplete",
                "text": "Core Work remains open; no automatic tool replay.",
            }
        output = {"state": "completed", "text": text, **mapping.get("staged", {})}
        self._observe(
            mapping,
            "terminal",
            "terminal",
            {
                "native_event_id": event_id,
                "assistant_text": text,
                "terminal": terminal,
                "outcome": output,
            },
        )
        result = self.coordinator.recover(
            mapping["attempt"],
            decoder=lambda raw: json.loads(raw)["outcome"],
            ordinary=mapping.get("mode") not in {"sleep", "review"},
        )
        if mapping.get("mode") == "sleep":
            self._sleep(mapping["scope"]).checkpoint(mapping["work"], mapping["attempt"])
        if result["state"] == "ready" and mapping.get("mode") == "sleep":
            self._save(revision, mapping | {"ready": True, "staged": {}})
        elif result["state"] == "waiting":
            waits = self.coordinator.rows("waits", work=mapping["work"])
            wait = next(
                w for w in waits if w["work"] == mapping["work"] and w["status"] == "waiting"
            )
            self._save(
                revision, mapping | {"wait": {"id": wait["id"], "revision": wait["revision"]}}
            )
        else:
            self._save(revision, {})
        return result
