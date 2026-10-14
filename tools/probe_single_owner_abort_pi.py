"""Native foreground abort preserves exact stopped setup and passive continuation."""

from __future__ import annotations

import argparse
import json
import shutil
import threading
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import zaratustra.foundation as core
from zaratustra.pi_adapter import Bridge, read_pi_runtime
from zaratustra.pi_adapter.__main__ import INTERACTIVE_ZARA_TOOLS, _prepare_space
from zaratustra.pi_adapter.activity_setup import SetupCoordinator
from zaratustra.pi_adapter.assigned import AssignedConfig
from zaratustra.pi_adapter.skills import activity_setup_skill

from .probe_activity_setup_pi import context, harness

LATE_DRAFT = """{
  "title":"Fictional observations", "goal":"Record dated observations",
  "instructions":"Keep originals and unknown values", "process":"Record then review",
  "first_action":"Provide a dated observation", "first_path":"Source to typed entry",
  "formats":[{"key":"observation","definition":{"title":"Observation","role":"event",
    "fields":[{"key":"day","meaning":"Event day","type":"date","indexed":true}],
    "time_field":"day"}}],
  "procedures":[{"key":"observe","purpose":"Record observations","goal":"Retain an event",
    "operations":["ingest_batch"],
    "outputs":[{"slot":"result","media_type":"application/json",
      "format_key":"observation"}]}],
  "decisions":[{"subject":"Period","status":"confirmed","explanation":"Per request"}]
}"""


def run_probe(directory: Path, runtime: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=False)
    space, working, sessions = (directory / item for item in ("space", "work", "sessions"))
    for item in (space, working, sessions):
        item.mkdir()
    owner = _prepare_space(space, "owner", create=True)
    core.ActivitySetupDraftV2.model_validate_json(LATE_DRAFT)
    native, actual = harness(), read_pi_runtime(runtime)
    sent = threading.Event()
    release = threading.Event()
    response_released = threading.Event()
    paused = threading.Event()
    abort_requested = False
    abort_acknowledged = False
    ordinary_calls = assigned_calls = 0
    pause_snapshot: dict[str, Any] = {}
    observed_boundaries: list[dict[str, Any]] = []
    assigned_packet: dict[str, Any] = {}
    observed_events: list[dict[str, Any]] = []
    storage_diagnostics: list[dict[str, Any]] = []
    stop_events: tuple[dict[str, object], ...] = ()

    def setup() -> Any:
        items = core.list_activity_setups(space, owner)
        assert len(items) == 1
        return items[0]

    def route(body: dict[str, Any]) -> dict[str, Any]:
        nonlocal ordinary_calls, assigned_calls, assigned_packet
        packet = context(body)
        assert not packet.get("conversation_event"), "Worker started an owner conversation"
        if "work" in packet:
            assigned_calls += 1
            assert assigned_calls == 1, "Abort launched another assigned provider request"
            assigned_packet = packet
            input_packet = json.loads(packet["inputs"][0]["content_text"])
            assert input_packet["sources"] and input_packet["result_schema"]
            sent.set()
            assert release.wait(40), "Native abort never committed an addressed pause"
            response_released.set()
            return {"_final_text": LATE_DRAFT}
        ordinary_calls += 1
        if ordinary_calls == 1:
            return {
                "_tool": "zara_activity",
                "mode": "create",
                "title": "Fictional observations",
                "goal": "Keep dated observations and review them",
            }
        assert ordinary_calls == 2, "A new conversation appeared after native abort"
        return {"_tool": "zara_activity", "mode": "submit", "setup_id": str(setup().setup_id)}

    provider = native.Provider([route] * 4)

    class DiagnosticBridge(Bridge):
        """Observe the public bridge refusal without retrying or changing it."""

        def record_storage(self, endpoint: str, error: core.FoundationError) -> None:
            import sqlite3

            if error.code not in ("busy", "storage"):
                return
            database = (space / ".zara-core" / "core.sqlite3").resolve()
            cause: BaseException | None = error
            causes = []
            while cause is not None:
                causes.append(
                    {
                        "type": type(cause).__name__,
                        "message": str(cause),
                        "sqlite_errorcode": getattr(cause, "sqlite_errorcode", None),
                        "sqlite_errorname": getattr(cause, "sqlite_errorname", None),
                    }
                )
                cause = cause.__cause__
            detail: dict[str, Any] = {
                "observed_at": datetime.now(UTC).isoformat(),
                "endpoint": endpoint,
                "database": str(database),
                "code": error.code,
                "detail": error.detail,
                "causes": causes,
                "sidecars": {
                    suffix: {
                        "exists": Path(str(database) + suffix).exists(),
                        "bytes": Path(str(database) + suffix).stat().st_size
                        if Path(str(database) + suffix).exists()
                        else None,
                    }
                    for suffix in ("-wal", "-shm")
                },
            }
            # Read-only pragmas cannot identify another connection's lock owner.
            # They establish only whether the same exact database remains busy.
            try:
                connection = sqlite3.connect(
                    database.as_uri() + "?mode=ro", uri=True, autocommit=True, timeout=0
                )
                try:
                    detail["read_only_inspection"] = {
                        name: connection.execute("PRAGMA " + name).fetchall()
                        for name in (
                            "database_list",
                            "locking_mode",
                            "journal_mode",
                            "application_id",
                        )
                    }
                finally:
                    connection.close()
            except sqlite3.Error as inspection:
                detail["read_only_inspection"] = {
                    "error": str(inspection),
                    "sqlite_errorcode": getattr(inspection, "sqlite_errorcode", None),
                    "sqlite_errorname": getattr(inspection, "sqlite_errorname", None),
                }
            storage_diagnostics.append(detail)

        def process_boundary(self, session_id: UUID, raw: dict[str, Any]) -> dict[str, Any]:
            try:
                return super().process_boundary(session_id, raw)
            except core.FoundationError as error:
                self.record_storage("process-boundary", error)
                raise

        def capture_source(self, session_id: UUID, **fields: Any) -> dict[str, object]:
            try:
                return super().capture_source(session_id, **fields)
            except core.FoundationError as error:
                self.record_storage("knowledge-capture", error)
                raise

    bridge = DiagnosticBridge(space, owner, working)
    config = AssignedConfig(
        space=space,
        workspace=working,
        pi_cli=actual.cli,
        pi_runtime=runtime,
        node=shutil.which("node") or "node",
        provider_profile="local-completions",
        provider_base_url=f"http://127.0.0.1:{provider.server_port}/v1",
        provider_id="fictional-local",
        model_id="fictional-model",
        context_window=1000000,
        max_tokens=32768,
        reserve_units=1000,
        limit_units=None,
        offline=True,
        disable_tools=True,
    )
    bridge.setup_controller = SetupCoordinator(bridge, config)

    def retain_pause() -> None:
        nonlocal pause_snapshot, stop_events
        current = setup()
        assert current.state.phase == "paused", "Abort acknowledged without saved pause"
        stage = current.state.stages[-1]
        execution = core.read_execution(space, stage.work_id, owner)
        assert execution.invocations and len(execution.invocations) == 1
        stop_events = core.read_execution_events(space, stage.work_id, 0, owner)
        assert any(item["kind"] == "request_attempt_stop" for item in stop_events)
        assert execution.invocations[0].status in ("sent", "unknown")
        pause_snapshot = execution.model_dump(mode="json")
        paused.set()
        # Release only after the exact native observer has saved its stop. The
        # provider must not win the race by completing before cancellation.
        release.set()

    def bridge_response(path: str, payload: object) -> None:
        if path != "/v1/process-boundary" or not isinstance(payload, dict):
            return
        observed_boundaries.append(payload)
        if payload.get("kind") == "paused":
            assert payload["lease_token"] and payload["target"]["id"] == str(setup().setup_id)
            retain_pause()

    def event(process: Any, observed: dict[str, Any]) -> None:
        nonlocal abort_requested, abort_acknowledged
        observed_events.append(observed)
        if (
            observed.get("type") == "tool_execution_update"
            and observed.get("toolName") == "zara_activity"
            and sent.is_set()
            and not abort_requested
        ):
            assert observed_boundaries and observed_boundaries[-1]["lease_token"]
            assert observed_boundaries[-1]["kind"] == "running"
            assert process.stdin is not None
            process.stdin.write(b'{"id":"native-abort","type":"abort"}\n')
            process.stdin.flush()
            abort_requested = True
        if observed.get("type") == "response" and observed.get("id") == "native-abort":
            assert observed.get("success") is True, observed
            abort_acknowledged = True
            # A cancelled observation connection may have no HTTP reply. Native
            # acknowledgement plus the exact public saved pause is sufficient;
            # losing that response must not make us invent a second stop/send.
            if not paused.is_set():
                retain_pause()

    events: list[dict[str, Any]] = []
    try:
        events = native.run_process(
            working,
            runtime,
            bridge,
            provider,
            prompt="Create an Activity for fictional dated observations",
            skills=(activity_setup_skill(),),
            confirmation_answers=(True,),
            session_directory=sessions,
            tool_names=INTERACTIVE_ZARA_TOOLS,
            expected_provider_calls=3,
            expected_tool_errors=1,
            on_event=event,
            on_bridge_response=bridge_response,
            wait_for=lambda: paused.is_set() and abort_acknowledged,
            timeout_seconds=60,
        )
    except Exception:
        (directory / "failure-traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        release.set()
        for name, value in (
            ("requests-before-reopen", provider.requests),
            ("boundaries", observed_boundaries),
            ("pause-execution", pause_snapshot),
            ("stop-events", stop_events),
            ("events-before-reopen", observed_events),
            ("storage-diagnostics", storage_diagnostics),
        ):
            (directory / f"{name}.json").write_text(
                json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    assert abort_requested and abort_acknowledged and paused.is_set()
    assert response_released.is_set()
    current = setup()
    assert current.state.phase == "paused"
    assert not current.state.activated_works and not current.state.activated_methods
    stage = current.state.stages[-1]
    assert stage.output is None and not stage.retired
    execution = core.read_execution(space, stage.work_id, owner)
    assert len(execution.invocations) == 1
    invocation = execution.invocations[0]
    assert invocation.status == "unknown", execution.model_dump_json(indent=2)
    assert invocation.invocation_id == UUID(pause_snapshot["invocations"][0]["invocation_id"])
    delivery = core.read_context_delivery(space, invocation.invocation_id, owner)
    assert delivery["stage"] == "unknown"
    assert delivery["context_work_id"] == str(stage.work_id)
    assert delivery["context_attempt_id"] == str(invocation.attempt_id)
    manifest = core.read_knowledge(space, UUID(str(delivery["manifest_id"])), owner)
    assert isinstance(manifest.state, core.ContextState)
    assert manifest.state.attempt_id == invocation.attempt_id
    assert assigned_packet["work"]["work_id"] == str(stage.work_id)
    assert manifest.state.session_id == UUID(str(delivery["context_session_id"]))
    assert not execution.outputs and execution.work.state.acceptance is None
    assert all(item.status != "active" for item in execution.attempts)
    originals = [
        core.read_knowledge(space, ref.record_id, owner, revision=ref.revision)
        for ref in current.state.sources
    ]
    assert originals and all(
        isinstance(item.state, core.SourceState) and item.state.content for item in originals
    )
    context_refs = [
        item
        for item in cast(
            list[dict[str, Any]],
            core.list_knowledge(space, owner, kind="context", limit=100)["items"],
        )
    ]

    reopened_calls = 0

    def reopen_route(body: dict[str, Any]) -> dict[str, str]:
        nonlocal reopened_calls
        reopened_calls += 1
        packet = context(body)
        assert "work" not in packet and not packet.get("conversation_event")
        assert setup().state.phase == "paused"
        assert any(
            item["subject_id"] == str(current.setup_id) and item["kind"] == "paused"
            for item in packet["conversation_actions"]
        )
        return {"_final_text": "The saved preparation is paused; its provider outcome is unknown."}

    reopened = native.Provider([reopen_route])
    reopened_events = native.run_process(
        working,
        runtime,
        Bridge(space, owner, working),
        reopened,
        prompt="What next with the saved fictional Activity?",
        resume_session=next(sessions.glob("*.jsonl")),
        resume_via_switch=True,
        prompt_after_switch=True,
        expected_provider_calls=1,
        tool_names=INTERACTIVE_ZARA_TOOLS,
        timeout_seconds=45,
    )
    assert reopened_calls == 1 and len(setup().state.stages) == 1
    assert core.read_execution(space, stage.work_id, owner).invocations == execution.invocations
    entries = [
        json.loads(line)
        for line in next(sessions.glob("*.jsonl")).read_text(encoding="utf-8").splitlines()
    ]
    assert not any(item.get("customType") == "zara-conversation-wake" for item in entries)
    visible_finals = [
        item
        for item in entries
        if item.get("type") == "message"
        and item.get("message", {}).get("role") == "assistant"
        and item["message"].get("stopReason") == "stop"
        and any(
            part.get("type") == "text" and str(part.get("text", "")).strip()
            for part in item["message"].get("content", [])
        )
    ]
    assert len(visible_finals) == 1, "Late worker completion produced an owner explanation"
    report = {
        "http": provider.calls + reopened.calls,
        "ordinary_http": ordinary_calls + reopened_calls,
        "assigned_http": assigned_calls,
        "abort_acknowledged": abort_acknowledged,
        "saved_phase": setup().state.phase,
        "unknown_invocation": str(invocation.invocation_id),
        "activated": False,
        "accepted": False,
        "real_model_calls": 0,
        "paid_api_calls": 0,
    }
    for name, value in (
        ("report", report),
        ("events", events),
        ("entries", entries),
        ("reopened-events", reopened_events),
        ("reopened-requests", reopened.requests),
        ("assigned-packet", assigned_packet),
        ("final-execution", execution.model_dump(mode="json")),
        ("assigned-delivery", delivery),
        ("assigned-manifest", manifest.model_dump(mode="json")),
        ("context-refs", context_refs),
    ):
        (directory / f"{name}.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--pi-runtime", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_probe(args.directory.resolve(), args.pi_runtime.resolve()), indent=2))


if __name__ == "__main__":
    main()
