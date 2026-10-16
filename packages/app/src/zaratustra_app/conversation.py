"""Ordinary human input and restart through the same public Core contract."""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any
from uuid import uuid4

from zaratustra_core import Core, CoreError, digest

from .coordinator import Coordinator
from .executor_port import Executor, Pi

CONVERSATION_METHOD = """conversation/1
Help the person with their original request and corrections in raw_messages.
Choose the smallest useful action. Do the requested activity now when possible;
do not impose an interview, setup project, planning document or fixed template.
Ask only questions needed for the requested result. Respect prior_results and
prior_messages, current memory, catalog identities, exact versions and rights.
You choose all subject meaning. Inspect catalog before creating a key. Create or
update an Activity when appropriate, preserving its stable identity on later turns.
Use zara_change for intermediate changes only when needed. Changes can instead
accompany the final result atomically. Allowed kinds: activity, data; memory and
Method require explicit delegation. New IDs need expected_heads[id]=0; existing
IDs need their catalog revision, identical kind/key/scope, and a new body value.
Change shape: {id,kind,key,scope,body,source_refs?}; never store record wrappers
as body, never mutate credentials, acceptance or execution status.
Return exactly one JSON object (no Markdown fences):
{\"state\":\"completed\",\"text\":\"the actual useful response\",\"changes\":[],
 \"expected_heads\":{},\"outputs\":[]}.
For an addressed question use state waiting and wait:{id:unique_id,question:text}.
completed finishes this bounded turn; it does not claim owner acceptance, truth
or completion of the Activity. Preserve uncertainties and give concrete output.
"""


def pin_profile(owner: Any, profile_id: str, descriptor: dict[str, Any]) -> dict[str, Any]:
    snapshot = owner.call("read_snapshot", {}, uuid4().hex)
    existing = next((h for h in snapshot["heads"] if h["id"] == profile_id), None)
    if existing:
        record = owner.call("read_exact", {"id": profile_id, "revision": 1}, uuid4().hex)
        if (
            existing["kind"] != "profile"
            or existing["revision"] != 1
            or digest(record["body"]["value"]) != digest(descriptor)
        ):
            raise CoreError("stale_basis", "profile.configuration", "after_refresh")
    else:
        owner.call(
            "apply_changes",
            {
                "changes": [
                    {"id": profile_id, "kind": "profile", "key": profile_id, "body": descriptor}
                ]
            },
            profile_id + ":create",
            expected_heads={profile_id: 0},
        )
    return {"id": profile_id, "revision": 1}


class Conversation:
    def __init__(self, core: Core, token: str, conversation: str = "ordinary"):
        self.core, self.owner, self.conversation = core, core.connect(token), conversation
        self.coordinator = Coordinator(
            core.connect(
                core.grant(
                    token,
                    "conversation:" + conversation,
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
                    ],
                    origin="host",
                )
            )
        )

    def submit(self, text: str, reply_to: dict[str, Any] | None = None) -> None:
        """Stable outbox ID and exact input are synchronized before first API delivery."""
        event = uuid4().hex
        packet: dict[str, Any] = {
            "conversation": self.conversation,
            "event_id": event,
            "raw_base64": base64.b64encode(text.encode("utf-8")).decode(),
        }
        if reply_to:
            packet["reply_to"] = reply_to
        directory = self.core.root / "entry-outbox"
        directory.mkdir(exist_ok=True)
        pending = directory / (str(time.time_ns()) + "-" + event + ".json")
        staging = pending.with_suffix(".staging")
        with staging.open("x", encoding="utf-8") as handle:
            json.dump(packet, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, pending)
        self.deliver_input()

    def deliver_input(self) -> None:
        for path in sorted((self.core.root / "entry-outbox").glob("*.json")):
            packet = json.loads(path.read_text(encoding="utf-8"))
            if packet["conversation"] == self.conversation:
                self.owner.call("ingest_message", packet, "entry:" + packet["event_id"])
                path.unlink()

    def run(
        self,
        executor: Executor,
        descriptor: dict[str, Any],
        call_limit: int,
        *,
        refresh: bool = False,
    ) -> dict[str, Any]:
        self.deliver_input()
        snapshot = self.coordinator.snapshot()
        works = [w for w in snapshot["works"] if w["conversation"] == self.conversation]
        active = [w for w in works if w["status"] not in {"completed", "cancelled"}]
        if len(active) > 1:
            raise CoreError("identity_conflict", "conversation.active_work")
        if active:
            work = active[0]
            work_id = work["id"]
            if work["status"] == "waiting":
                wait = next(
                    w
                    for w in snapshot["waits"]
                    if w["work"] == work_id and w["status"] == "waiting"
                )
                return {
                    "state": "waiting",
                    "text": json.loads(wait["body"])["question"],
                    "reply_to": {"id": wait["id"], "revision": wait["revision"]},
                }
            profile = pin_profile(self.owner, work_id + ":profile", descriptor)
            if refresh:
                self.coordinator.refresh_basis(work_id)
                snapshot = self.coordinator.snapshot()
                work = next(w for w in snapshot["works"] if w["id"] == work_id)
            if work["status"] in {"paused", "blocked"}:
                raise CoreError(
                    "outcome_unknown" if work["status"] == "blocked" else "resource_exhausted",
                    "work." + work["status"],
                    "reconcile",
                )
        else:
            conversation = next(
                (c for c in snapshot["conversations"] if c["id"] == self.conversation), None
            )
            cursor = conversation["cursor"] if conversation else 0
            messages = [
                m
                for m in snapshot["messages"]
                if m["conversation"] == self.conversation and m["seq"] > cursor
            ]
            if not messages:
                return {"state": "idle", "text": "Введите запрос обычными словами."}
            work_id = "turn:" + messages[0]["event"]
            cancelled = {w["id"] for w in works if w["status"] == "cancelled"}
            base_id, successor = work_id, 0
            while work_id in cancelled:
                control = next(
                    (
                        i
                        for i in snapshot["intents"]
                        if i["kind"] == "control" and i["subject"] == work_id
                    ),
                    None,
                )
                watermark = json.loads(control["body"]).get("input_watermark") if control else None
                if watermark is None:
                    raise CoreError("outcome_unknown", "cancelled_input_boundary", "reconcile")
                fresh_human_input = any(
                    m["seq"] > watermark and m["origin"] == "human" for m in messages
                )
                if not fresh_human_input:
                    return {
                        "state": "cancelled",
                        "text": "Работа отменена. Напишите новый запрос для новой работы.",
                    }
                successor += 1
                work_id = base_id + ":after-cancel:" + str(successor)
            profile = pin_profile(self.owner, work_id + ":profile", descriptor)
            method = next((h for h in snapshot["heads"] if h["id"] == "conversation-method"), None)
            if method is None:
                self.owner.call(
                    "apply_changes",
                    {
                        "changes": [
                            {
                                "id": "conversation-method",
                                "kind": "method",
                                "key": "conversation/1",
                                "body": CONVERSATION_METHOD,
                            }
                        ]
                    },
                    "conversation-method:create",
                    expected_heads={"conversation-method": 0},
                )
            self.coordinator.open_work(
                {
                    "id": work_id,
                    "conversation": self.conversation,
                    "goal": "Help with the original human request and its corrections.",
                    "method_ref": {"id": "conversation-method", "revision": 1},
                    "call_limit": call_limit,
                    "continuation_policy": "durable",
                }
            )
            snapshot = self.coordinator.snapshot()
            work = next(w for w in snapshot["works"] if w["id"] == work_id)
        attempts = [
            a
            for a in snapshot["attempts"]
            if a["work"] == work_id and a["status"] in {"prepared", "claimed", "unknown"}
        ]
        if attempts:
            attempt = attempts[0]
            if attempt["status"] != "prepared":
                result = self.coordinator.recover(attempt["id"], pi=isinstance(executor, Pi))
                return self._present(result)
        else:
            attempt_id = work_id + ":attempt:" + uuid4().hex
            prepared = self.coordinator.prepare(work_id, attempt_id, profile)
            attempt = {"id": attempt_id, "generation": prepared["generation"]}
        self.coordinator.dispatch(attempt["id"], attempt["generation"], executor)
        result = self.coordinator.recover(attempt["id"], pi=isinstance(executor, Pi))
        return self._present(result)

    def _present(self, result: dict[str, Any]) -> dict[str, Any]:
        if result["state"] == "waiting":
            waits = self.coordinator.snapshot()["waits"]
            wait = next(
                w
                for w in waits
                if json.loads(w["body"]).get("attempt_id") == result["attempt_id"]
                and w["status"] == "waiting"
            )
            return result | {"reply_to": {"id": wait["id"], "revision": wait["revision"]}}
        return result
