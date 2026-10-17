"""Fresh native Pi review preparation; subject mutation is never delegated."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, cast
from uuid import uuid4

from zaratustra_core import Core, CoreError

from .conversation import pin_profile
from .coordinator import Coordinator

REVIEW_METHOD = """native-review/1
Refute the delivered task using its exact builder result, files and check evidence.
Use only read-only Pi tools read/grep/find/ls and Core context/read/result.
Do not run bash, mutate files, change Core subject records or accept on the owner's behalf.
Inspect actual evidence rather than repeating builder claims. Report actionable findings,
their evidence and limits, including checks you could not establish. The host records a
fresh session identifier; this alone proves neither independence nor correctness.
Stage completed result metadata with zara_result and speak the actual review normally.
Keep outputs in the same Activity. No owner acceptance or invented passing checks.
"""


class NativeReview:
    def __init__(self, core: Core, token: str, scope: str):
        self.scope, self.owner = scope, core.connect(token)
        self.client = core.connect(
            core.grant(
                token,
                "native-review:" + scope,
                [
                    "read",
                    "open_work",
                    "prepare_attempt",
                    "claim_dispatch",
                    "observe_attempt",
                    "commit_outcome",
                    "control_work",
                ],
                origin="host",
            )
        )
        self.coordinator = Coordinator(self.client)

    def start(
        self, work_id: str, profile: dict[str, Any], builder_attempt: str | None = None
    ) -> dict[str, Any]:
        state = self.coordinator.tables("heads", "works", "attempts", "results")
        if any(a["work"] == work_id for a in state["attempts"]):
            raise CoreError("outcome_unknown", "review.pending_attempt", "reconcile")
        works = {w["id"]: w for w in state["works"]}
        attempts = {a["id"]: a for a in state["attempts"]}
        candidates = []
        for result in state["results"]:
            attempt = attempts[result["attempt"]]
            work = works[attempt["work"]]
            body = json.loads(work["body"])
            if (
                ":native-attempt:" in attempt["id"]
                and body.get("scope") == self.scope
                and not body["method_ref"]["id"].startswith("native-host:review-method:")
                and body.get("goal") != "Sleep"
                and json.loads(result["body"])["state"] == "completed"
                and (builder_attempt is None or attempt["id"] == builder_attempt)
            ):
                candidates.append(result)
        if not candidates:
            raise CoreError("invalid_request", "review.no_delivered_builder")
        result = candidates[-1]
        builder = attempts[result["attempt"]]
        pinned = json.loads(builder["body"])
        builder_session = pinned["profile"]["body"]["value"].get("session_id")
        if not profile.get("session_id") or profile.get("session_id") == builder_session:
            raise CoreError("denied", "review.fresh_session_required")
        activity = next(
            (h for h in state["heads"] if h["id"] == self.scope and h["kind"] == "activity"), None
        )
        if activity is None:
            raise CoreError("invalid_request", "review.activity")
        method_id = "native-host:review-method:" + self.scope
        method = next((h for h in state["heads"] if h["id"] == method_id), None)
        if method is None:
            self.owner.call(
                "apply_changes",
                {
                    "changes": [
                        {
                            "id": method_id,
                            "kind": "method",
                            "key": method_id,
                            "scope": self.scope,
                            "body": REVIEW_METHOD,
                        }
                    ]
                },
                method_id + ":install",
                expected_heads={method_id: 0},
            )
        basis_id = "native-host:review-basis:" + uuid4().hex
        output = json.loads(result["body"])
        refs = [{"id": activity["id"], "revision": activity["revision"]}]
        for original in output.get("outputs", []):
            ref = {"id": original["id"], "revision": original["revision"]}
            if ref not in refs:
                refs.append(ref)
        observations = [
            o
            for o in self.coordinator.rows("observations", work=builder["work"])
            if o["attempt"] == builder["id"]
        ]
        observed_refs = [
            {
                "attempt": o["attempt"],
                "event": o["event"],
                "fingerprint": o["fingerprint"],
                "kind": json.loads(o["body"])["kind"],
            }
            for o in observations[:100]
        ]
        tools = [
            t
            for t in self.coordinator.rows("tool_calls", work=builder["work"])
            if t["attempt"] == builder["id"]
        ]
        self.owner.call(
            "apply_changes",
            {
                "changes": [
                    {
                        "id": basis_id,
                        "kind": "data",
                        "key": basis_id,
                        "scope": self.scope,
                        "source_refs": refs,
                        "body": {
                            "builder_attempt": builder["id"],
                            "builder_work": builder["work"],
                            "result_sha256": hashlib.sha256(result["body"].encode()).hexdigest(),
                            "builder_result": output,
                            "builder_task": pinned["work"],
                            "raw_messages": [
                                base64.b64decode(m["raw"]).decode("utf-8")
                                for m in pinned["messages"]
                            ],
                            "observations": observed_refs,
                            "tool_correlations": tools[:100],
                            "coverage": {
                                "observations_total": len(observations),
                                "included": min(100, len(observations)),
                                "tool_correlations_total": len(tools),
                                "more": "Use Core read_history for additional evidence",
                            },
                        },
                    }
                ]
            },
            basis_id + ":create",
            expected_heads={basis_id: 0},
        )
        host = Coordinator(self.owner)
        host.open_work(
            {
                "id": work_id,
                "conversation": work_id + ":conversation",
                "goal": "Review delivered task in the same Activity",
                "call_limit": None,
                "continuation_policy": "durable",
                "method_ref": {"id": method_id, "revision": method["revision"] if method else 1},
                "inputs": [r | {"role": "must_be_current"} for r in refs[:1]]
                + [{"id": basis_id, "revision": 1, "role": "must_be_current"}],
            },
            scope=self.scope,
        )
        attempt = work_id + ":native-attempt:" + uuid4().hex
        profile_ref = pin_profile(
            self.owner,
            attempt + ":profile",
            profile | {"reviewer_role": "independent fresh native session"},
        )
        selection = {
            "catalog_refs": [
                {"id": h["id"], "revision": h["revision"]}
                for h in state["heads"]
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
            "mode": "review",
            "attempt": attempt,
            "work": work_id,
            "generation": prepared["generation"],
            "scope": self.scope,
            "staged": {},
            "profile": profile,
            "builder_attempt": builder["id"],
        }

    def context(self, mapping: dict[str, Any]) -> dict[str, Any]:
        attempt = next(
            a
            for a in self.coordinator.rows("attempts", work=mapping["work"])
            if a["id"] == mapping["attempt"]
        )
        context = cast(dict[str, Any], json.loads(attempt["body"]))
        return context | {
            "instructions": REVIEW_METHOD,
            "allowed_builtin_tools": ["read", "grep", "find", "ls"],
            "coverage": (
                "First 100 catalog refs; mandatory Activity, basis and current memory retained."
            ),
        }
