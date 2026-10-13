"""Raw fictional Codex Responses SSE through ordinary installed native Pi."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4


class RawResponsesProvider(ThreadingHTTPServer):
    """No implicit final text: every fixture explicitly supplies its wire events."""

    def __init__(
        self,
        script: list[list[dict[str, Any]] | Callable[[dict[str, Any]], list[dict[str, Any]]]],
        *,
        inspect_request: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(("127.0.0.1", 0), RawResponsesHandler)
        self.script = script
        self.inspect_request = inspect_request
        self.calls = 0
        self.requests: list[dict[str, Any]] = []
        self.wire_responses: list[list[dict[str, Any]]] = []
        self.errors: list[str] = []


def decoded_request(raw: bytes, encoding: str | None) -> dict[str, Any]:
    if encoding == "zstd":
        result = subprocess.run(
            [
                shutil.which("node") or "node",
                "-e",
                "const {readFileSync}=require('node:fs');"
                "const {zstdDecompressSync}=require('node:zlib');"
                "process.stdout.write(zstdDecompressSync(readFileSync(0)));",
            ],
            input=raw,
            capture_output=True,
            check=True,
            timeout=20,
        )
        raw = result.stdout
    elif encoding not in (None, "identity"):
        raise AssertionError(f"Unsupported fictional request encoding: {encoding}")
    return cast(dict[str, Any], json.loads(raw.decode("utf-8")))


class RawResponsesHandler(BaseHTTPRequestHandler):
    server: RawResponsesProvider

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        try:
            if self.path != "/backend-api/codex/responses":
                raise AssertionError("Native request did not use the Codex Responses endpoint")
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            body = decoded_request(raw, self.headers.get("Content-Encoding"))
            self.server.requests.append(body)
            self.server.calls += 1
            if self.server.inspect_request is not None:
                self.server.inspect_request(body)
            if self.server.calls > len(self.server.script):
                raise AssertionError("Unexpected extra native provider request")
            events = self.server.script[self.server.calls - 1]
            if callable(events):
                events = events(body)
            self.server.wire_responses.append(events)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for event in events:
                self.wfile.write(
                    b"event: "
                    + event["type"].encode()
                    + b"\ndata: "
                    + json.dumps(event, ensure_ascii=False).encode("utf-8")
                    + b"\n\n"
                )
                self.wfile.flush()
        except Exception as error:
            self.server.errors.append(str(error))
            self.send_error(500, "Fictional provider fixture failed")


def completed_response(
    text: str | None,
    *,
    reasoning: bool = False,
    call: tuple[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Exact valid wire shapes, including a complete response with no visible text."""
    events: list[dict[str, Any]] = [
        {"type": "response.created", "response": {"id": "fictional-response"}}
    ]
    items: list[dict[str, Any]] = []
    if reasoning:
        item: dict[str, Any] = {"type": "reasoning", "id": "fictional-reasoning", "summary": []}
        events.extend(
            [
                {"type": "response.output_item.added", "output_index": 0, "item": item},
                {
                    "type": "response.reasoning_summary_text.delta",
                    "output_index": 0,
                    "delta": "Fictional provider reasoning.",
                },
                {"type": "response.output_item.done", "output_index": 0, "item": item},
            ]
        )
        items.append(item)
    if text is not None:
        index = len(items)
        item = {
            "type": "message",
            "id": "fictional-message",
            "phase": "final_answer",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text}],
        }
        events.extend(
            [
                {"type": "response.output_item.added", "output_index": index, "item": item},
                {"type": "response.output_text.delta", "output_index": index, "delta": text},
                {"type": "response.output_item.done", "output_index": index, "item": item},
            ]
        )
        items.append(item)
    if call is not None:
        index = len(items)
        name, arguments = call
        item = {
            "type": "function_call",
            "id": "fc-fictional",
            "call_id": "call-fictional",
            "name": name,
            "arguments": json.dumps(arguments),
        }
        events.extend(
            [
                {"type": "response.output_item.added", "output_index": index, "item": item},
                {"type": "response.output_item.done", "output_index": index, "item": item},
            ]
        )
        items.append(item)
    events.append(
        {
            "type": "response.completed",
            "response": {
                "id": "fictional-response",
                "status": "completed",
                "output": items,
                "usage": {
                    "input_tokens": 150,
                    "output_tokens": 7,
                    "total_tokens": 157,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 4 if reasoning else 0},
                },
            },
        }
    )
    return events


def codex_context(body: dict[str, Any]) -> dict[str, Any]:
    """Read the technical manifest envelope from the actual Responses request."""
    text = body["instructions"]
    marker = text.rfind("ZARA_MANIFEST:")
    assert marker >= 0
    start = text.index("{", marker)
    return cast(dict[str, Any], json.JSONDecoder().raw_decode(text[start:])[0])


def feasibility_probe(directory: Path, runtime: Path) -> dict[str, object]:
    """Establish unchanged native Codex transport over a disposable local endpoint."""
    import zaratustra.foundation as core
    from zaratustra.pi_adapter import Bridge
    from zaratustra.pi_adapter.__main__ import _prepare_space

    from .probe_knowledge_pi import run_process

    directory.mkdir(parents=True, exist_ok=False)
    space = directory / "space"
    space.mkdir()
    owner = _prepare_space(space, "owner", create=True)
    assert core.read_space(space).schema_version == 18
    provider = RawResponsesProvider([completed_response("Fictional visible response.")])
    events = run_process(
        directory,
        runtime,
        Bridge(space, owner, directory),
        provider,
        prompt="Explain a fictional saved state",
        provider_profile="codex-sse",
        local_model_id="gpt-6.1-sol",
        expected_provider_calls=1,
    )
    assert provider.calls == 1 and not provider.errors
    assert "ZARA_MANIFEST:" in provider.requests[0]["instructions"]
    report: dict[str, object] = {
        "schema": core.read_space(space).schema_version,
        "http": 1,
        "real_calls": 0,
    }
    for name, value in (
        ("report", report),
        ("requests", provider.requests),
        ("raw-responses", provider.wire_responses),
        ("native-events", events),
    ):
        (directory / f"{name}.json").write_text(json.dumps(value, indent=2), encoding="utf-8")
    return report


def ordinary_empty_probe(directory: Path, runtime: Path) -> dict[str, object]:
    """Known empty ordinary final preserves the producer result and execution obstacle."""
    import zaratustra.foundation as core
    from zaratustra.pi_adapter import Bridge
    from zaratustra.pi_adapter.__main__ import _prepare_space

    from .probe_knowledge_pi import run_process

    directory.mkdir(parents=True, exist_ok=False)
    space = directory / "space"
    space.mkdir()
    owner = _prepare_space(space, "owner", create=True)
    assert core.read_space(space).schema_version == 18
    activity, work = uuid4(), uuid4()
    for request in (
        core.CreateActivityRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor=owner.actor,
            activity_id=activity,
            state=core.ActivityState(title="Fictional saved observation", goal="Retain a result"),
        ),
        core.CreateWorkRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor=owner.actor,
            work_id=work,
            state=core.WorkState(
                activity_id=activity,
                goal="Save the observation",
                expected_outputs=(core.OutputContract(slot="result", media_type="text/plain"),),
            ),
        ),
    ):
        core.apply_operation(space, request, owner)
    provider = RawResponsesProvider(
        [
            completed_response(
                None,
                call=(
                    "zara_result",
                    {
                        "mode": "publish",
                        "slot": "result",
                        "content_text": "Original fictional observation",
                    },
                ),
            ),
            completed_response(None, reasoning=True),
        ]
    )
    bridge = Bridge(space, owner, directory)
    sessions = directory / "sessions"
    sessions.mkdir()
    events = run_process(
        directory,
        runtime,
        bridge,
        provider,
        work=(activity, work),
        prompt="Save a fictional observation",
        provider_profile="codex-sse",
        local_model_id="gpt-6.1-sol",
        expected_provider_calls=2,
        session_directory=sessions,
    )
    before = core.read_work(space, work, owner)
    execution = core.read_execution(space, work, owner)
    assert before.state.linked_outputs and before.state.acceptance is None
    assert any(attempt.status == "active" for attempt in execution.attempts)
    assert core.read_ordinary_final_proof(space, work, owner) is None
    assert all(selected is None for selected in bridge.sessions.values())

    def resumed(body: dict[str, Any]) -> list[dict[str, Any]]:
        packet = codex_context(body)
        assert packet["request_origin"]["kind"] == "owner" and "work" not in packet
        assert packet["recovery_obstacle"]["work_id"] == str(work)
        return completed_response(
            "The original observation is saved; inspect the incomplete execution."
        )

    reopened = RawResponsesProvider([resumed])
    resumed_events = run_process(
        directory,
        runtime,
        Bridge(space, owner, directory),
        reopened,
        work=(activity, work),
        resume_session=next(sessions.glob("*.jsonl")),
        resume_via_switch=True,
        prompt_after_switch=True,
        prompt="What next?",
        provider_profile="codex-sse",
        local_model_id="gpt-6.1-sol",
        expected_provider_calls=1,
        wait_for=lambda: reopened.calls == 1,
    )
    assert core.read_work(space, work, owner) == before
    assert core.read_execution(space, work, owner) == execution
    report: dict[str, object] = {
        "schema": core.read_space(space).schema_version,
        "http": 2,
        "reopen_http": 1,
        "active_attempt_preserved": True,
        "result_preserved": True,
        "accepted": False,
        "real_calls": 0,
    }
    for name, value in (
        ("report", report),
        ("requests", provider.requests + reopened.requests),
        ("raw-responses", provider.wire_responses + reopened.wire_responses),
        ("native-events", events + resumed_events),
    ):
        (directory / f"{name}.json").write_text(json.dumps(value, indent=2), encoding="utf-8")
    return report


def response_probe(
    directory: Path,
    runtime: Path,
    *,
    exhausted: bool = False,
    tool_step: bool = False,
    storage_failure: bool = False,
    failed_response: bool = False,
) -> dict[str, object]:
    """Native create, public reviewed fixture, raw empty reply, durable repair and reopen."""
    import zaratustra.foundation as core
    from tests.zaratustra.foundation.test_activity_setup import _complete, _step
    from zaratustra.pi_adapter import Bridge
    from zaratustra.pi_adapter.__main__ import _prepare_space

    from .probe_activity_structures_pi import AREAS
    from .probe_knowledge_pi import run_process

    if storage_failure and failed_response:
        raise ValueError("Native faults are independent scenarios")
    directory.mkdir(parents=True, exist_ok=False)
    space = directory / "space"
    space.mkdir()
    owner = _prepare_space(space, "owner", create=True)
    assert core.read_space(space).schema_version == 18

    class CaptureRefusalBridge(Bridge):
        def capture_source(self, session_id: UUID, **kwargs: Any) -> dict[str, object]:
            if (
                kwargs.get("conversation_terminal") is not None
                and self.request_origins.get(session_id) == "host"
            ):
                raise core.FoundationError("storage", "Fictional terminal capture refusal")
            return super().capture_source(session_id, **kwargs)

    setup_id: UUID | None = None
    activated = False
    host_calls = 0
    finished = False
    fault_owner_sent = False
    interrupted_response = storage_failure or failed_response
    expected_calls = (4 if interrupted_response else 5) + int(tool_step)

    def host(body: dict[str, Any]) -> list[dict[str, Any]]:
        nonlocal host_calls
        host_calls += 1
        packet = codex_context(body)
        task = packet["conversation_task"]
        assert task["response_required"] is True
        assert task["instruction"] in body["instructions"]
        assert task["action_ref"] == packet["conversation_event"]["ref"]
        assert packet["request_origin"] == {"kind": "host", "sources": []}
        assert "zara-conversation-wake" not in json.dumps(body)
        if failed_response:
            return [
                {"type": "response.created", "response": {"id": "fictional-failed"}},
                {
                    "type": "response.failed",
                    "response": {
                        "id": "fictional-failed",
                        "status": "failed",
                        "output": [],
                        "error": {
                            "code": "fictional_provider_failure",
                            "message": "Fictional native error",
                        },
                    },
                },
            ]
        if tool_step and host_calls == 1:
            assert task["repair"] is None
            return completed_response(
                None, call=("zara_conversation", {"mode": "read", "action_ref": task["action_ref"]})
            )
        reply_number = host_calls - int(tool_step)
        if reply_number > 1:
            assert task["repair"]["number"] == reply_number - 1
            original = core.read_knowledge(
                space, UUID(task["repair"]["previous_source"]["record_id"]), owner
            )
            assert isinstance(original.state, core.SourceState)
            assert (
                original.state.content is not None and not original.state.content.decode().strip()
            )
            marker = body["instructions"].split("ZARA_MANIFEST:")[-1].split()[0]
            manifest = core.read_knowledge(space, UUID(marker.split("@")[0]), owner)
            assert isinstance(manifest.state, core.ContextState)
            assert (
                core.KnowledgeRef.model_validate(task["repair"]["previous_source"])
                in manifest.state.mandatory
            )
            assert (
                core.KnowledgeRef.model_validate(task["repair"]["previous_manifest"])
                in manifest.state.mandatory
            )
        if reply_number == 1:
            return completed_response(None, reasoning=True)
        if reply_number == 2:
            return completed_response("\u0085 \n")
        return completed_response(
            None if exhausted else "The saved activity is ready. Supply an observation."
        )

    def independent_owner(body: dict[str, Any]) -> list[dict[str, Any]]:
        packet = codex_context(body)
        assert packet["request_origin"]["kind"] == "owner"
        assert not packet.get("conversation_event")
        assert not packet.get("conversation_task")
        assert any(
            item["response_outcome"] == ("unknown" if failed_response else "attention")
            for item in packet["conversation_delivery_outcomes"]
        )
        return completed_response("The response capture failed; the saved activity is intact.")

    provider = RawResponsesProvider(
        [
            completed_response(
                None,
                call=(
                    "zara_activity",
                    {
                        "mode": "create",
                        "title": "Fictional observation",
                        "goal": "Keep observations",
                    },
                ),
            ),
            completed_response("Preparing the fictional structure."),
            *([host] * (1 if interrupted_response else 3)),
            *([host] if tool_step else []),
            *([independent_owner] if interrupted_response else []),
        ]
    )

    observed_events = []

    def event(process: Any, observed: dict[str, Any]) -> None:
        nonlocal activated, setup_id, finished, fault_owner_sent
        observed_events.append(observed)
        if (
            interrupted_response
            and not fault_owner_sent
            and provider.calls == 3
            and observed.get("type") == "agent_settled"
        ):
            fault_owner_sent = True
            process.stdin.write(
                json.dumps(
                    {
                        "id": "independent-owner",
                        "type": "prompt",
                        "message": "Explain another fictional project topic",
                        "streamingBehavior": "followUp",
                    }
                ).encode()
                + b"\n"
            )
            process.stdin.flush()
        if observed.get("type") == "agent_settled" and provider.calls >= expected_calls:
            finished = True
        if activated or observed.get("type") != "agent_end":
            return
        setup = core.list_activity_setups(space, owner)[0]
        setup_id = setup.setup_id
        # These are explicit owner-local public Core fixture effects, not model
        # judgement or a replacement for the assigned-stage native scenario.
        # The helpers use only the first five addressed values; trailing fields
        # belong to their independent begin-idempotence fixture and are unused.
        fixture_case = cast(Any, (space, owner.space_id, owner, setup_id, setup.state.activity_id))
        _step(fixture_case, "start_stage", stage_kind="draft", stage_instruction="Prepare fixture")
        draft = _complete(
            fixture_case,
            core.ActivitySetupDraftV2(
                title="Fictional observation",
                goal="Keep observations",
                instructions="Retain originals",
                process="Save an observation, then compare",
                first_action="Supply an observation",
                first_path="Original to saved result",
                decisions=(
                    core.SetupDecisionBasis(
                        subject="First step",
                        status="proposed",
                        explanation="Start with one observation",
                    ),
                ),
                works=(
                    core.SetupWorkTemplate(
                        key="first",
                        goal="Save an observation",
                        expected_outputs=(
                            core.OutputContract(slot="result", media_type="text/plain"),
                        ),
                    ),
                ),
            ),
        )
        _step(fixture_case, "start_stage", stage_kind="review", stage_instruction="Review fixture")
        stage = core.read_activity_setup(space, setup_id, owner).state.stages[-1]
        work = core.read_work(space, stage.work_id, owner)
        retained = core.read_artifact(space, work.state.inputs[0].artifact_id, owner).content
        assert retained is not None
        packet = json.loads(retained)
        _complete(
            fixture_case,
            core.ActivitySetupReviewV2(
                draft=draft,
                manifest=core.ArtifactRef.model_validate(packet["manifest_ref"]),
                input_version=packet["input_version"],
                checked=AREAS,
                coverage=tuple(
                    core.SetupAreaEvidence(
                        area=area,
                        explanation="First step exists",
                        components=("process", "works.first"),
                    )
                    for area in AREAS
                ),
                conclusion="Fixture ready",
            ),
        )
        _step(fixture_case, "finish")
        activated = True

    def done() -> bool:
        deliveries = core.list_conversation_deliveries(space, owner)
        return bool(
            finished
            and deliveries
            and (
                deliveries[0].response_outcome == ("unknown" if failed_response else "attention")
                if exhausted or interrupted_response
                else deliveries[0].status == "responded"
            )
        )

    sessions = directory / "sessions"
    sessions.mkdir()
    try:
        events = run_process(
            directory,
            runtime,
            (CaptureRefusalBridge if storage_failure else Bridge)(space, owner, directory),
            provider,
            prompt="Create an activity for fictional observations",
            confirmation_answers=(True,),
            provider_profile="codex-sse",
            local_model_id="gpt-6.1-sol",
            expected_provider_calls=expected_calls,
            on_event=event,
            wait_for=done,
            session_directory=sessions,
            timeout_seconds=120,
        )
    finally:
        for name, value in (
            ("requests", provider.requests),
            ("raw-responses", provider.wire_responses),
            ("native-events", observed_events),
            ("fixture-errors", provider.errors),
        ):
            (directory / f"{name}.json").write_text(json.dumps(value, indent=2), encoding="utf-8")
    assert activated and done() and not provider.errors and setup_id is not None
    delivery = core.list_conversation_deliveries(space, owner)[0]
    assert delivery.repair_count == (0 if interrupted_response else 2)
    if exhausted:
        assert delivery.diagnostics[0].code == "response_repair_exhausted"
    setup = core.read_activity_setup(space, setup_id, owner)
    before = core.read_work(space, setup.state.activated_works[0], owner)
    assert before.state.acceptance is None

    def resumed(body: dict[str, Any]) -> list[dict[str, Any]]:
        packet = codex_context(body)
        assert packet["request_origin"]["kind"] == "owner"
        assert not packet.get("conversation_event")
        assert not packet.get("conversation_task")
        assert any(
            item["delivery_id"] == str(delivery.delivery_id)
            for item in packet["conversation_delivery_outcomes"]
        )
        if exhausted:
            assert any(
                item["diagnostics"]
                and item["diagnostics"][0]["code"] == "response_repair_exhausted"
                for item in packet["conversation_delivery_outcomes"]
            )
        return completed_response("Continue from the saved activity and observation.")

    reopened = RawResponsesProvider([resumed])
    resumed_events = run_process(
        directory,
        runtime,
        Bridge(space, owner, directory),
        reopened,
        resume_session=next(sessions.glob("*.jsonl")),
        resume_via_switch=True,
        prompt_after_switch=True,
        prompt="What next?",
        provider_profile="codex-sse",
        local_model_id="gpt-6.1-sol",
        expected_provider_calls=1,
        wait_for=lambda: reopened.calls == 1,
    )
    if exhausted or interrupted_response:
        assert any(
            event.get("method") == "setWidget"
            and event.get("widgetKey") == "zara-conversation"
            and event.get("widgetLines")
            for event in resumed_events
        )
    assert core.read_work(space, before.work_id, owner) == before
    assert len(core.list_conversation_deliveries(space, owner)) == 1
    report: dict[str, object] = {
        "schema": core.read_space(space).schema_version,
        "http": provider.calls,
        "reopen_http": reopened.calls,
        "repairs": delivery.repair_count,
        "exhausted": exhausted,
        "tool_step": tool_step,
        "storage_failure": storage_failure,
        "failed_response": failed_response,
        "same_session_after_capture_failure": storage_failure and fault_owner_sent,
        "same_session_after_provider_failure": failed_response and fault_owner_sent,
        "response_outcome": delivery.response_outcome,
        "accepted": False,
        "real_calls": 0,
    }
    for report_name, report_value in (
        ("report", report),
        ("requests", provider.requests + reopened.requests),
        ("native-events", events + resumed_events),
        ("raw-responses", provider.wire_responses + reopened.wire_responses),
        ("delivery", delivery.model_dump(mode="json")),
    ):
        (directory / f"{report_name}.json").write_text(
            json.dumps(report_value, indent=2), encoding="utf-8"
        )
    return report
