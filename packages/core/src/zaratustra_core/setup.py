"""Narrow final-only setup renewal; unknown inference remains unknown history."""

from __future__ import annotations

import json
from typing import Any

from .types import CoreError

POLICY = "setup-final-only/v1"
ADMISSION = "native-setup/v1"


def profile(db: Any, actor: Any, work: Any, pinned_profile: Any) -> None:
    if json.loads(work["body"]).get("execution_policy") not in {POLICY, "setup-routing/v1"}:
        raise CoreError("denied", "setup.policy")
    value = pinned_profile["body"]["value"]
    if (
        actor["origin"] != "host"
        or not isinstance(value, dict)
        or value.get("setup_admission") != ADMISSION
    ):
        raise CoreError("denied", "setup.admission_profile")


def renew(core: Any, db: Any, actor: Any, payload: dict[str, Any]) -> dict[str, Any]:
    attempt, work = core._attempt(db, payload["attempt_id"])
    if (
        payload["generation"] != work["generation"]
        or attempt["generation"] != work["generation"]
        or attempt["status"] not in {"prepared", "claimed", "unknown"}
    ):
        raise CoreError("stale_basis", "setup.generation")
    if work["revision"] != payload["work_revision"] or work["status"] not in {"running", "blocked"}:
        raise CoreError("stale_basis", "setup.work")
    pinned = json.loads(attempt["body"])
    profile(db, actor, work, pinned["profile"])
    action = db.execute("SELECT * FROM actions WHERE attempt=?", (attempt["id"],)).fetchone()
    if action is not None and action["executor"] != actor["principal"]:
        raise CoreError("denied", "executor")
    if db.execute("SELECT 1 FROM results WHERE attempt=?", (attempt["id"],)).fetchone():
        raise CoreError("stale_basis", "setup.result")
    # Any retained terminal must be recovered, never replaced by a new model turn.
    if any(
        json.loads(row[0])["kind"] == "terminal"
        for row in db.execute("SELECT body FROM observations WHERE attempt=?", (attempt["id"],))
    ):
        raise CoreError("stale_basis", "setup.recover_terminal")
    if db.execute("SELECT 1 FROM tool_calls WHERE attempt=?", (attempt["id"],)).fetchone():
        raise CoreError("denied", "setup.intermediate_effect")
    body = json.loads(work["body"])
    if body["call_limit"] is not None and work["reserved"] >= body["call_limit"]:
        raise CoreError("resource_exhausted", "calls")
    db.execute("UPDATE attempts SET status='superseded' WHERE id=?", (attempt["id"],))
    db.execute(
        "UPDATE works SET status='ready',revision=revision+1,generation=generation+1 WHERE id=?",
        (work["id"],),
    )
    db.execute(
        "DELETE FROM intents WHERE kind IN ('dispatch','observe') AND subject=?", (attempt["id"],)
    )
    core._intent(db, "prepare", work["id"], {"superseded_attempt": attempt["id"]})
    # Actions, observations, usage/reservations and immutable pinned inputs stay untouched.
    return {
        "work_id": work["id"],
        "revision": work["revision"] + 1,
        "generation": work["generation"] + 1,
        "superseded_attempt": attempt["id"],
        "outside_effects": "forbidden_by_setup_profile",
        "prior_inference": "unknown",
    }
