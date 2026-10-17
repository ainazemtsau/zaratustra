"""Rebuild the setup frontier from public Core facts; mapping is only a cache."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from zaratustra_core import CoreError

if TYPE_CHECKING:
    from .native_session import NativeSession

POLICIES = {"setup-final-only/v1", "setup-routing/v1"}


def managed(work: dict[str, Any]) -> bool:
    return json.loads(work["body"]).get("execution_policy") in POLICIES


def recover(session: NativeSession) -> dict[str, Any]:
    revision, mapping = session._load()
    if mapping.get("mode") in {"sleep", "review"}:
        return session.context()
    retained = next(
        (
            r
            for r in session.coordinator.rows("results", conversation=session.mapping_id)
            if r["attempt"] == mapping.get("attempt")
        ),
        None,
    )

    def context() -> dict[str, Any]:
        value = session.context()
        if retained is not None:
            saved = json.loads(retained["body"])
            if saved.get("text"):
                value["recovered_result"] = saved
        return value

    rows = session.coordinator.rows("works", conversation=session.mapping_id)
    active = [w for w in rows if w["status"] not in {"completed", "cancelled"}]
    if len(active) > 1:
        raise CoreError("stale_basis", "setup.ambiguous_frontier")
    if not active:
        if mapping.get("managed_setup"):
            session._save(revision, {})
        return context()
    work = active[0]
    if not managed(work):
        return context()  # Ordinary external effects retain their reconciliation boundary.
    body = json.loads(work["body"])
    link = body.get("continuation")
    if link:
        parent = next(
            (
                r
                for r in session.coordinator.rows("results", conversation=session.mapping_id)
                if r["attempt"] == link["attempt_id"]
            ),
            None,
        )
        if parent is None or json.loads(parent["body"]).get("next_work_id") != work["id"]:
            raise CoreError("stale_basis", "setup.missing_predecessor")
    attempts = session.coordinator.rows("attempts", work=work["id"])
    current = attempts[-1] if attempts else None
    if work["status"] == "waiting":
        waits = [
            w
            for w in session.coordinator.rows("waits", work=work["id"])
            if w["status"] == "waiting"
        ]
        if len(waits) != 1 or current is None:
            raise CoreError("stale_basis", "setup.wait")
        value = session._mapping(current, work) | {
            "wait": {"id": waits[0]["id"], "revision": waits[0]["revision"]}
        }
    elif work["status"] == "ready":
        value = session._claim(work["id"])
    elif work["status"] in {"running", "blocked"} and current is not None:
        observations = [
            json.loads(o["body"])
            for o in session.coordinator.rows("observations", work=work["id"])
            if o["attempt"] == current["id"]
        ]
        terminal = next(
            (o for o in observations if o["kind"] == "terminal" and not o["late"]), None
        )
        if terminal is not None:
            raw = json.loads(base64.b64decode(terminal["raw_base64"]))
            session.coordinator.recover(
                current["id"], ordinary=True, decoder=lambda _: raw.get("outcome", raw)
            )
            return recover(session)  # At most one committed successor; never repeat inference.
        session.coordinator.client.call(
            "renew_setup",
            {
                "attempt_id": current["id"],
                "generation": current["generation"],
                "work_revision": work["revision"],
            },
            "renew-setup:" + uuid4().hex,
        )
        value = session._claim(work["id"])
    else:
        raise CoreError("stale_basis", "setup.frontier_status")
    session._save(revision, value)
    return context()
