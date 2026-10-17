"""Exact human verdicts are separate from model output and technical check results."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from zaratustra_core import Core, CoreError, digest

from .coordinator import Coordinator
from .ordinary import EXECUTION_ID


def delivery(core: Core, token: str, activity: str | None = None) -> dict[str, Any]:
    owner = core.connect(token)
    snapshot = Coordinator(owner).snapshot()
    works = {w["id"]: w for w in snapshot["works"]}
    attempts = {a["id"]: a for a in snapshot["attempts"]}
    for result in reversed(snapshot["results"]):
        work = works[attempts[result["attempt"]]["work"]]
        body = json.loads(work["body"])
        if body["method_ref"]["id"] != EXECUTION_ID or work["status"] != "completed":
            continue
        if activity is not None and body["scope"] != activity:
            continue
        selected = {
            "attempt_id": result["attempt"],
            "result_hash": result["fingerprint"],
            "activity_id": body["scope"],
            "result": json.loads(result["body"]),
        }
        selected["review"] = None
        for report in reversed(snapshot["results"]):
            review_work = works[attempts[report["attempt"]]["work"]]
            review_body = json.loads(review_work["body"])
            if review_body.get("scope") != body["scope"] or not review_body["method_ref"][
                "id"
            ].startswith("native-host:review-method:"):
                continue
            for ref in review_body.get("inputs", []):
                if not ref["id"].startswith("native-host:review-basis:"):
                    continue
                basis = owner.call("read_exact", ref, uuid4().hex)["body"]["value"]
                if basis["builder_attempt"] == result["attempt"]:
                    selected["review"] = json.loads(report["body"])
                    return selected
        return selected
    raise CoreError("invalid_request", "native.no_delivered_result")


def record(
    core: Core, token: str, attempt: str, result_hash: str, verdict: str, owner_words: str
) -> dict[str, Any]:
    if verdict not in {"accepted", "revised", "rejected"} or not owner_words.strip():
        raise CoreError("invalid_request", "native.owner_verdict")
    owner = core.connect(token)
    snapshot = Coordinator(owner).snapshot()
    row = next(
        (
            r
            for r in snapshot["results"]
            if r["attempt"] == attempt and r["fingerprint"] == result_hash
        ),
        None,
    )
    if row is None:
        raise CoreError("stale_basis", "native.owner_result")
    work_id = next(a["work"] for a in snapshot["attempts"] if a["id"] == attempt)
    work = next(w for w in snapshot["works"] if w["id"] == work_id)
    body = json.loads(work["body"])
    if body["method_ref"]["id"] != EXECUTION_ID or body["scope"] == "space":
        raise CoreError("denied", "native.owner_result_kind")
    value = {
        "format": "owner-verdict/v1",
        "attempt_id": attempt,
        "result_hash": result_hash,
        "verdict": verdict,
        "owner_words": owner_words,
        "activity_id": body["scope"],
    }
    identity = "owner-verdict:" + digest(value)
    command = "human:" + identity
    existing = owner.call("lookup_receipt", {"command_id": command}, uuid4().hex)
    if not existing.get("missing"):
        return value
    if verdict == "accepted" and not any(a["attempt"] == attempt for a in snapshot["acceptance"]):
        core.accept_result(token, attempt, result_hash)
    outputs = [
        {"id": r["id"], "revision": r["revision"]} for r in json.loads(row["body"])["outputs"]
    ]
    owner.call(
        "apply_changes",
        {
            "changes": [
                {
                    "id": identity,
                    "kind": "data",
                    "key": identity,
                    "scope": body["scope"],
                    "body": value,
                    "source_refs": outputs,
                }
            ]
        },
        command,
        expected_heads={identity: 0},
    )
    return value
