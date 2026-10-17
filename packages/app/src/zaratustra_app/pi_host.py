"""One mechanical native Pi lifecycle request; never starts a model."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from zaratustra_core import Core, CoreError

from .entry_lock import host_lock
from .native_session import NativeSession


def initialize(root: Path) -> tuple[Core, str]:
    """Publish the first DB and owner credential together, never a tokenless root."""
    staging = root.with_name(root.name + ".initializing-" + uuid4().hex)
    try:
        _, token = Core.initialize(staging)
        with (staging / "owner.credential").open("x", encoding="utf-8") as credential:
            credential.write(token)
            credential.flush()
            os.fsync(credential.fileno())
        if root.exists():
            raise CoreError("stale_basis", "native.initialization_destination")
        os.rename(staging, root)
        if os.name != "nt":
            descriptor = os.open(root.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return Core(root), token
    finally:
        if staging.exists():
            if staging.resolve().parent != root.resolve().parent:
                raise CoreError("invalid_request", "native.initialization_staging")
            shutil.rmtree(staging)


def handle(request: dict[str, Any]) -> dict[str, Any]:
    root = Path(request["data_root"]).expanduser()
    if not root.is_absolute():
        raise ValueError("An absolute data root is required")
    root = root.resolve()
    root.parent.mkdir(parents=True, exist_ok=True)
    lease = root.parent / (root.name + ".pi-host.lock")
    with host_lock(lease):
        if not root.exists():
            core, token = initialize(root)
        else:
            core = Core(root)
            token = (root / "owner.credential").read_text(encoding="utf-8").strip()
        command = request.get("command", "attach")
        if command == "backup":
            report = core.backup(token, Path(request["destination"]))
            return {"state": "backed-up", "text": "Verified backup saved.", "manifest": report}
        if command == "prepare-update":
            report = core.prepare_update(token, Path(request["destination"]))
            return {
                "state": "compatible",
                "text": "Compatible schema; verified backup retained.",
                "report": report,
            }
        if command == "restore":
            destination = Path(request["destination"]).expanduser().resolve()
            restored, _ = Core.restore_quarantined(Path(request["backup"]), destination)
            return {
                "state": "quarantined",
                "data_root": str(restored.root),
                "text": (
                    "Verified restore is quarantined. Activate it only after retiring its source."
                ),
            }
        if command == "activate-restore":
            destination = Path(request["destination"]).expanduser().resolve()
            restored = Core(destination)
            restored_token = (destination / "owner.credential").read_text(encoding="utf-8").strip()
            report = restored.activate_restored(restored_token, core, token)
            return {
                "state": "activated",
                "data_root": str(restored.root),
                "report": report,
                "text": (
                    "Original retired. Restored space is active; unknown effects remain fenced."
                ),
            }
        if command == "diagnostics":
            return {
                "state": "diagnostics",
                "text": json.dumps(
                    core.connect(token).call("export_diagnostics", {}, uuid4().hex),
                    ensure_ascii=False,
                ),
            }
        session = NativeSession(core, token, request["session_id"])
        session.profile = request.get("profile", {"adapter": "ordinary-native-pi"})
        if command == "activities":
            snapshot = session.coordinator.tables("heads", "works")
            activities = [
                {"id": h["id"], "revision": h["revision"], "label": h["key"]}
                for h in snapshot["heads"]
                if h["kind"] == "activity"
            ]
            ids = {a["id"] for a in activities}
            current = next(
                (
                    json.loads(w["body"])["scope"]
                    for w in reversed(snapshot["works"])
                    if json.loads(w["body"])["scope"] in ids
                ),
                None,
            )
            return {"state": "activities", "activities": activities, "current_scope": current}
        if command == "delivery":
            from .native_verdict import delivery

            return {"state": "delivery", **delivery(core, token, request.get("activity_id"))}
        if command == "owner-verdict":
            from .native_verdict import record

            value = record(
                core,
                token,
                request["attempt_id"],
                request["result_hash"],
                request["verdict"],
                request["owner_words"],
            )
            return {
                "state": "recorded",
                "text": "Your verdict is retained in the same Activity.",
                "verdict": value,
            }
        if command in {"attach", "context", "reopen"}:
            return session.reopen() if command in {"attach", "reopen"} else session.context()
        if command == "input":
            return session.input(request["event_id"], request["text"])
        if command == "reply":
            return session.reply(request["event_id"], request["text"], request["reply_to"])
        if command == "verify-profile":
            return session.verify_profile()
        if command == "sleep":
            return session.start_sleep(request.get("scope", "space"), request.get("portion", 16))
        if command == "review":
            return session.start_review(request["scope"], request.get("builder_attempt"))
        if command == "cancel":
            revision, mapping = session._load()
            snapshot = session.coordinator.tables("works")
            active = [
                w
                for w in snapshot["works"]
                if w["status"] not in {"completed", "cancelled"}
                and (
                    w["id"] == mapping.get("work")
                    or not mapping
                    and (
                        w["conversation"] == session.mapping_id
                        or json.loads(w["body"])["goal"] == "Sleep"
                    )
                )
                and (request.get("work_id") is None or w["id"] == request["work_id"])
            ]
            if len(active) != 1:
                raise CoreError("stale_basis", "native.cancel_work")
            work = active[0]
            session.owner.call(
                "control_work",
                {
                    "work_id": work["id"],
                    "revision": work["revision"],
                    "action": "cancel",
                    "reason": "Explicit owner cancellation; external effects stay unconfirmed.",
                },
                uuid4().hex,
            )
            session._save(revision, {})
            return {
                "state": "cancelled",
                "text": (
                    "Work cancelled. Unconfirmed effects remain recorded; no tools were repeated."
                ),
            }
        if command == "tool":
            return session.tool(
                request["name"], request["call_id"], request["payload"], request.get("origin")
            )
        if command == "admit-setup-read":
            context = session.tool("context", "trusted-read-admission", {}, request.get("origin"))
            if not context["current"].get("managed_setup"):
                raise CoreError("denied", "setup.read_profile")
            return session.observation(
                uuid4().hex, {"kind": "trusted_read_admission"}, request["origin"]
            )
        if command == "observation":
            return session.observation(request["event_id"], request["value"], request.get("origin"))
        if command == "settled":
            return session.settled(
                request["event_id"],
                request["text"],
                request["aborted"],
                request.get("terminal"),
                request.get("origin"),
            )
        raise ValueError("Unknown native command")


def main() -> int:
    try:
        result = handle(json.load(sys.stdin))
    except CoreError as error:
        result = {
            "state": "error",
            "text": "Core: " + error.code + "/" + error.field,
            "rejection": {"code": error.code, "field": error.field},
        }
    except (ValueError, KeyError, TypeError, OSError) as error:
        result = {
            "state": "error",
            "text": "Native Core hook incomplete: "
            + type(error).__name__
            + ". No automatic retry.",
        }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
