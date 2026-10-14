"""Fictional schema-18 conversation continuation in ordinary Pi over localhost."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any
from uuid import UUID

import zaratustra.foundation as core
from zaratustra.pi_adapter import Bridge, read_pi_runtime
from zaratustra.pi_adapter.__main__ import INTERACTIVE_ZARA_TOOLS, _prepare_space
from zaratustra.pi_adapter.activity_setup import SetupCoordinator
from zaratustra.pi_adapter.assigned import AssignedConfig

from .probe_activity_setup_pi import context, harness
from .probe_activity_structures_pi import AREAS


def run_probe(directory: Path, runtime: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=False)
    space, workdir = directory / "space", directory / "work"
    space.mkdir()
    workdir.mkdir()
    owner = _prepare_space(space, "owner", create=True)
    assert core.read_space(space).schema_version == 18
    native, actual = harness(), read_pi_runtime(runtime)
    setup_id: UUID | None = None
    first_work: UUID | None = None
    ordinary_calls = 0
    submitted = False
    owner_answer_sent = False
    first_step_sent = False
    first_work_settled = False

    def route(body: dict[str, Any]) -> dict[str, Any]:
        nonlocal setup_id, first_work, ordinary_calls, submitted
        packet = context(body)
        assert "zara-conversation-wake" not in json.dumps(body)
        assert not packet.get("conversation_event"), (
            "Worker completion cannot initiate conversation"
        )
        if packet.get("work") and packet.get("inputs"):
            incoming = json.loads(packet["inputs"][0]["content_text"])
            if incoming.get("result_schema", {}).get("title") == "ActivitySetupReviewV2":
                report = core.ActivitySetupReviewV2(
                    draft=core.ArtifactRef.model_validate(incoming["draft_ref"]),
                    manifest=core.ArtifactRef.model_validate(incoming["manifest_ref"]),
                    input_version=incoming["input_version"],
                    checked=AREAS,
                    coverage=tuple(
                        core.SetupAreaEvidence(
                            area=area,
                            explanation="The original and first useful Work agree",
                            components=("process", "works.first"),
                        )
                        for area in AREAS
                    ),
                    conclusion="No material obstacle",
                )
                return {"_final_text": report.model_dump_json()}
            if incoming.get("result_schema"):
                draft = core.ActivitySetupDraftV2(
                    title="Fictional observation",
                    goal="Keep and compare observations",
                    instructions="Preserve original observations",
                    process="Receive observation, save result, review next step",
                    first_action="Supply the first observation",
                    first_path="Original → result → review",
                    decisions=(
                        core.SetupDecisionBasis(
                            subject="Review period",
                            status="confirmed",
                            explanation="Owner chose a week",
                        ),
                    ),
                    works=(
                        core.SetupWorkTemplate(
                            key="first",
                            goal="Keep the first observation",
                            expected_outputs=(
                                core.OutputContract(slot="result", media_type="text/plain"),
                            ),
                        ),
                    ),
                )
                return {"_final_text": draft.model_dump_json()}
        ordinary_calls += 1
        last_user = max(
            index for index, message in enumerate(body["messages"]) if message["role"] == "user"
        )
        tools = [
            message for message in body["messages"][last_user + 1 :] if message["role"] == "tool"
        ]
        assert packet["request_origin"]["kind"] == "owner"
        if setup_id is None:
            if not tools:
                return {
                    "_tool": "zara_activity",
                    "mode": "create",
                    "title": "Fictional observation",
                    "goal": "Keep observations and review a chosen period",
                }
            setup_id = core.list_activity_setups(space, owner)[0].setup_id
        state = core.read_activity_setup(space, setup_id, owner).state
        if not state.question and not submitted and ordinary_calls <= 3:
            return {
                "_tool": "zara_activity",
                "mode": "question",
                "setup_id": str(setup_id),
                "question": "Which review period?",
            }
        if state.phase == "needs_input":
            if tools:
                return {"_final_text": "Which review period?"}
            return {"_tool": "zara_activity", "mode": "answer", "setup_id": str(setup_id)}
        if state.phase != "ready":
            if not submitted:
                submitted = True
                return {"_tool": "zara_activity", "mode": "submit", "setup_id": str(setup_id)}
            raise AssertionError("Foreground submit returned before an actionable setup boundary")
        first_work = state.activated_works[0]
        if not first_step_sent:
            assert submitted and tools
            return {"_final_text": "The activity is ready. Supply the first observation."}
        if not packet.get("work"):
            action = next(
                item
                for item in packet["conversation_actions"]
                if item["work_id"] == str(first_work)
            )
            return {
                "_tool": "zara_conversation",
                "mode": "use_existing_work",
                "action_ref": action["ref"],
            }
        if not core.read_work(space, first_work, owner).state.linked_outputs:
            return {
                "_tool": "zara_result",
                "mode": "publish",
                "slot": "result",
                "content_text": "Fictional observation 8; original owner message retained.",
            }
        return {"_final_text": "The observation is saved. Owner acceptance remains separate."}

    provider = native.Provider([route] * 20)
    bridge = Bridge(space, owner, workdir)
    bridge.setup_controller = SetupCoordinator(
        bridge,
        AssignedConfig(
            space=space,
            workspace=workdir,
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
        ),
    )

    def event(process: Any, observed: dict[str, Any]) -> None:
        nonlocal owner_answer_sent, first_step_sent, first_work_settled
        if observed.get("type") != "agent_settled" or setup_id is None:
            return
        state = core.read_activity_setup(space, setup_id, owner).state
        prompt = None
        if state.phase == "needs_input" and not owner_answer_sent:
            owner_answer_sent = True
            prompt = "One week. Keep exact originals."
        elif state.phase == "ready" and not first_step_sent:
            first_step_sent = True
            prompt = "Start the existing first Work. My fictional observation is 8."
        elif first_work and core.read_work(space, first_work, owner).state.linked_outputs:
            first_work_settled = True
        if prompt:
            process.stdin.write(
                json.dumps({"id": "owner-next", "type": "prompt", "message": prompt}).encode()
                + b"\n"
            )
            process.stdin.flush()

    def done() -> bool:
        return bool(
            first_work
            and core.read_work(space, first_work, owner).state.linked_outputs
            and first_work_settled
            and ordinary_calls >= 9
        )

    sessions = directory / "sessions"
    sessions.mkdir()
    try:
        events = native.run_process(
            workdir,
            runtime,
            bridge,
            provider,
            prompt="Create an Activity for keeping and reviewing observations",
            confirmation_answers=(True,),
            tool_names=("read", "write", "edit", "bash", *INTERACTIVE_ZARA_TOOLS),
            wait_for=done,
            on_event=event,
            session_directory=sessions,
            timeout_seconds=240,
            expected_provider_calls=11,
        )
    finally:
        (directory / "http-requests.json").write_text(
            json.dumps(provider.requests, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        bridge.setup_controller.close()
    assert done()
    assert setup_id is not None and first_work is not None
    state = core.read_activity_setup(space, setup_id, owner).state
    assert state.phase == "ready" and state.reviews_completed == 1
    work = core.read_work(space, first_work, owner)
    assert work.state.acceptance is None and len(work.state.linked_outputs) == 1
    deliveries = core.list_conversation_deliveries(space, owner)
    delivery_json = [item.model_dump(mode="json") for item in deliveries]
    assert len(deliveries) == 0, "Ordinary conversation must not create completion delivery claims"
    with sqlite3.connect(space / ".zara-core" / "core.sqlite3") as connection:
        ledger = connection.execute(
            "SELECT invocation_id, stage FROM knowledge_delivery"
        ).fetchall()
        final_rows = connection.execute(
            "SELECT r.record_id,r.revision FROM knowledge_records k JOIN knowledge_revisions r "
            "ON r.record_id=k.record_id AND r.revision=k.current_revision WHERE k.kind='source' "
            "AND json_extract(r.payload,'$.scope_work_id')=? "
            "AND json_extract(r.payload,'$.conversation_terminal.stop_reason')='stop'",
            (str(first_work),),
        ).fetchall()
    assert len(final_rows) == 1
    final_ref = core.KnowledgeRef(record_id=UUID(final_rows[0][0]), revision=final_rows[0][1])
    final_source = core.read_knowledge(space, final_ref.record_id, owner).state
    assert isinstance(final_source, core.SourceState) and final_source.conversation_final
    final_proof = core.read_terminal_response(
        space,
        final_ref,
        owner,
        session_id=UUID(final_source.conversation_id or ""),
    )
    assert final_proof.work_id == first_work and final_proof.outcome == "visible"
    assert len(ledger) == len(provider.requests) and all(row[1] == "answered" for row in ledger)
    assert not any(
        event.get("type") == "tool_execution_end" and event.get("isError") for event in events
    )
    session = next(sessions.glob("*.jsonl"))
    before_work = core.read_work(space, first_work, owner)

    def resumed(body: dict[str, Any]) -> dict[str, Any]:
        packet = context(body)
        assert not packet.get("conversation_event")
        assert packet["request_origin"]["kind"] == "owner"
        assert any(
            item["subject_id"] == str(setup_id) and item["kind"] == "ready"
            for item in packet["conversation_actions"]
        )
        assert "zara-conversation-wake" not in json.dumps(body)
        return {"_final_text": "The activity is ready and the first observation is already saved."}

    reopened = native.Provider([resumed])
    native.run_process(
        workdir,
        runtime,
        Bridge(space, owner, workdir),
        reopened,
        resume_session=session,
        resume_via_switch=True,
        prompt_after_switch=True,
        prompt="What next? Where did we stop?",
        expected_provider_calls=1,
        wait_for=lambda: reopened.calls == 1,
        tool_names=("read", "write", "edit", "bash", *INTERACTIVE_ZARA_TOOLS),
    )
    assert core.read_work(space, first_work, owner) == before_work
    assert core.list_conversation_deliveries(space, owner) == ()
    with sqlite3.connect(space / ".zara-core" / "core.sqlite3") as connection:
        connection.row_factory = sqlite3.Row
        all_ledger = [dict(row) for row in connection.execute("SELECT * FROM knowledge_delivery")]
    (directory / "http-requests.json").write_text(
        json.dumps(provider.requests + reopened.requests, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (directory / "ledger.json").write_text(
        json.dumps(all_ledger, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (directory / "native-events.json").write_text(
        json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (directory / "delivery.json").write_text(
        json.dumps(delivery_json, indent=2),
        encoding="utf-8",
    )
    return {
        "schema": core.read_space(space).schema_version,
        "http_requests": len(provider.requests),
        "ledger": len(ledger),
        "ordinary_calls": ordinary_calls,
        "host_calls": 0,
        "reviews": state.reviews_completed,
        "normal_followup": True,
        "first_work_saved": True,
        "work_accepted": False,
        "resume_owner_request": True,
        "resume_http_requests": len(reopened.requests),
        "session": str(session),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--pi-runtime", type=Path, required=True)
    args = parser.parse_args()
    result = run_probe(args.directory.resolve(), args.pi_runtime.resolve())
    (args.directory / "report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


def origin_probe(directory: Path, runtime: Path) -> dict[str, Any]:
    """Identical queued owner entries and identical extension input are distinct."""
    directory.mkdir(parents=True, exist_ok=False)
    space = directory / "space"
    space.mkdir()
    owner = _prepare_space(space, "owner", create=True)
    assert core.read_space(space).schema_version == 18
    native = harness()
    fixture = directory / "origin-fixture.ts"
    fixture.write_text(
        "export default function(pi) { let once=false; "
        'pi.on("before_agent_start", () => { if(!once) { once=true; '
        'pi.sendUserMessage("Identical fictional input"); } }); }',
        encoding="utf-8",
    )
    seen: list[list[dict[str, Any]]] = []

    def route(body: dict[str, Any]) -> dict[str, str]:
        packet = context(body)
        assert packet["request_origin"]["kind"] == "owner"
        refs = packet["request_origin"]["sources"]
        seen.append(refs)
        for ref in refs:
            source = core.read_knowledge(space, UUID(ref["record_id"]), owner).state
            assert isinstance(source, core.SourceState)
            assert source.sender == "owner" and ":native:" in (source.source_event_id or "")
            assert source.content == b"Identical fictional input"
        return {"_final_text": "The delivered fictional input is recorded."}

    provider = native.Provider([route] * 3)
    queued = False

    def event(process: Any, observed: dict[str, Any]) -> None:
        nonlocal queued
        if (
            not queued
            and observed.get("type") == "message_start"
            and observed.get("message", {}).get("role") == "assistant"
        ):
            queued = True
            for delivery in ("steer", "followUp"):
                process.stdin.write(
                    json.dumps(
                        {
                            "id": delivery,
                            "type": "prompt",
                            "message": "Identical fictional input",
                            "streamingBehavior": delivery,
                        }
                    ).encode()
                    + b"\n"
                )
            process.stdin.flush()

    def done() -> bool:
        if provider.calls != 3:
            return False
        with sqlite3.connect(space / ".zara-core" / "core.sqlite3") as connection:
            return bool(
                connection.execute(
                    "SELECT COUNT(*) FROM knowledge_delivery WHERE stage='answered'"
                ).fetchone()[0]
                == 3
            )

    events = native.run_process(
        directory,
        runtime,
        Bridge(space, owner, directory),
        provider,
        prompt="Identical fictional input",
        on_event=event,
        wait_for=done,
        expected_provider_calls=3,
        extra_extensions=(fixture,),
        timeout_seconds=90,
    )
    refs = {ref["record_id"] for batch in seen for ref in batch}
    assert len(refs) == 3 and queued
    assert any("Сообщение расширения сохранено" in str(event) for event in events)
    report = {
        "http_requests": 3,
        "native_owner_entries": 3,
        "identical_steer_followup": True,
        "extension_input_blocked": True,
    }
    (directory / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (directory / "http-requests.json").write_text(
        json.dumps(provider.requests, indent=2), encoding="utf-8"
    )
    (directory / "native-events.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
    return report


def stale_wake_probe(directory: Path, runtime: Path) -> dict[str, Any]:
    """A native wake addressed to the former branch cannot send in the new one."""
    directory.mkdir(parents=True, exist_ok=False)
    space = directory / "space"
    space.mkdir()
    owner = _prepare_space(space, "owner", create=True)
    assert core.read_space(space).schema_version == 18
    native = harness()
    fixture = directory / "stale-fixture.ts"
    fixture.write_text(
        'export default function(pi) { pi.registerCommand("stale-fixture", '
        "{handler: async(_args,ctx) => { await ctx.newSession({withSession: async fresh => { "
        'await fresh.sendMessage({customType:"zara-conversation-wake", content:[], display:false, '
        'details:{delivery_id:"00000000-0000-4000-8000-000000000001", generation:-1}}, '
        '{triggerTurn:true,deliverAs:"followUp"}); }}); }}); }',
        encoding="utf-8",
    )
    provider = native.Provider([{"_final_text": "The original owner turn finished."}])
    switched = False

    def event(process: Any, observed: dict[str, Any]) -> None:
        nonlocal switched
        if observed.get("type") == "agent_end" and not switched:
            switched = True
            process.stdin.write(b'{"id":"new-branch","type":"prompt","message":"/stale-fixture"}\n')
            process.stdin.flush()

    events = native.run_process(
        directory,
        runtime,
        Bridge(space, owner, directory),
        provider,
        prompt="Keep a fictional ordinary turn",
        on_event=event,
        expected_pre_send_failure=True,
        expected_provider_calls=1,
        extra_extensions=(fixture,),
        wait_for=lambda: False,
        timeout_seconds=60,
    )
    (directory / "native-events.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
    assert switched and provider.calls == 1
    assert any(event.get("type") == "extension_error" for event in events)
    report = {"original_http_requests": 1, "stale_wake_http_requests": 0, "branch_switch": True}
    (directory / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (directory / "native-events.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
    return report


def abrupt_final_probe(
    directory: Path,
    runtime: Path,
    *,
    clean_close: bool = False,
) -> dict[str, Any]:
    """Close native Pi after saved proof, before ordinary Attempt settlement."""
    from uuid import uuid4

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
            state=core.ActivityState(title="Fictional crash", goal="Preserve a completed result"),
        ),
        core.CreateWorkRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor=owner.actor,
            work_id=work,
            state=core.WorkState(
                activity_id=activity,
                goal="Keep the first result",
                expected_outputs=(core.OutputContract(slot="result", media_type="text/plain"),),
            ),
        ),
    ):
        core.apply_operation(space, request, owner)
    native = harness()
    fixture = directory / "crash-boundary.ts"
    fixture.write_text(
        'export default function(pi) { pi.on("turn_end", async event => { '
        'if(event.message.stopReason==="stop") await new Promise(() => {}); }); }',
        encoding="utf-8",
    )
    provider = native.Provider(
        [
            {
                "_tool": "zara_result",
                "mode": "publish",
                "slot": "result",
                "content_text": "Fictional complete result",
            },
            {"_final_text": "The result is saved."},
        ]
    )
    sessions = directory / "sessions"
    sessions.mkdir()

    saved_proof = None

    def final_saved() -> bool:
        nonlocal saved_proof
        saved_proof = core.read_ordinary_final_proof(space, work, owner)
        return saved_proof is not None

    events = native.run_process(
        directory,
        runtime,
        Bridge(space, owner, directory),
        provider,
        work=(activity, work),
        prompt="Prepare and save the fictional result",
        expected_provider_calls=2,
        session_directory=sessions,
        extra_extensions=(fixture,),
        abrupt_end_predicate=None if clean_close else final_saved,
        input_eof_predicate=final_saved if clean_close else None,
    )
    proof = core.read_ordinary_final_proof(space, work, owner)
    if clean_close:
        assert proof is None
    else:
        assert proof is not None
    before = core.read_work(space, work, owner)
    assert before.state.linked_outputs and before.state.acceptance is None
    execution = core.read_execution(space, work, owner)
    if clean_close:
        assert all(item.status == "completed" for item in execution.attempts)
    else:
        assert any(item.status == "active" for item in execution.attempts)
    saved_attempts = {item.attempt_id for item in execution.attempts}

    def resumed(body: dict[str, Any]) -> dict[str, str]:
        packet = context(body)
        assert packet["request_origin"]["kind"] == "owner"
        assert packet["work"]["work_id"] == str(work)
        assert core.read_ordinary_final_proof(space, work, owner) is None
        assert all(
            item.status == "completed"
            for item in core.read_execution(space, work, owner).attempts
            if item.attempt_id in saved_attempts
        )
        return {"_final_text": "The original result is saved; continue from that result."}

    reopened = native.Provider([resumed])
    resumed_events = native.run_process(
        directory,
        runtime,
        Bridge(space, owner, directory),
        reopened,
        work=(activity, work),
        resume_session=next(sessions.glob("*.jsonl")),
        resume_via_switch=True,
        prompt_after_switch=True,
        prompt="What next?",
        expected_provider_calls=1,
    )
    assert core.read_work(space, work, owner) == before
    assert all(item.status != "active" for item in core.read_execution(space, work, owner).attempts)
    report = {
        "schema": core.read_space(space).schema_version,
        "initial_http": 2,
        "resume_http": 1,
        "old_final_observed": True,
        "result_unchanged": True,
        "accepted": False,
        "blind_repeat": False,
        "native_eof_close": clean_close,
    }
    for name, value in (
        ("report", report),
        ("http-requests", provider.requests + reopened.requests),
        ("native-events", events + resumed_events),
        ("final-proof", saved_proof.model_dump(mode="json") if saved_proof else None),
        ("closed-execution", execution.model_dump(mode="json")),
    ):
        (directory / f"{name}.json").write_text(json.dumps(value, indent=2), encoding="utf-8")
    return report


def missing_final_capture_probe(directory: Path, runtime: Path) -> dict[str, Any]:
    """A failed native final capture cannot turn agent_settled into completion."""
    from uuid import uuid4

    class FailedCaptureBridge(Bridge):
        def capture_source(self, session_id: UUID, **kwargs: Any) -> dict[str, object]:
            if kwargs.get("conversation_terminal") is not None:
                raise core.FoundationError("storage", "Fictional final capture failure")
            return super().capture_source(session_id, **kwargs)

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
            state=core.ActivityState(
                title="Fictional capture failure", goal="Keep actual evidence"
            ),
        ),
        core.CreateWorkRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor=owner.actor,
            work_id=work,
            state=core.WorkState(
                activity_id=activity,
                goal="Save the original result",
                expected_outputs=(core.OutputContract(slot="result", media_type="text/plain"),),
            ),
        ),
    ):
        core.apply_operation(space, request, owner)
    native = harness()
    bridge = FailedCaptureBridge(space, owner, directory)
    provider = native.Provider(
        [
            {
                "_tool": "zara_result",
                "mode": "publish",
                "slot": "result",
                "content_text": "Original fictional result",
            },
            {"_final_text": "The result was saved."},
        ]
    )
    sessions = directory / "sessions"
    sessions.mkdir()
    events = native.run_process(
        directory,
        runtime,
        bridge,
        provider,
        work=(activity, work),
        prompt="Save the fictional result",
        expected_provider_calls=2,
        session_directory=sessions,
    )
    before = core.read_work(space, work, owner)
    execution = core.read_execution(space, work, owner)
    active = [item for item in execution.attempts if item.status == "active"]
    assert len(active) == 1
    assert core.read_ordinary_final_proof(space, work, owner) is None
    assert before.state.linked_outputs and before.state.acceptance is None
    assert all(value is None for value in bridge.sessions.values())
    assert any("Fictional final capture failure" in str(event) for event in events)

    def resumed(body: dict[str, Any]) -> dict[str, str]:
        packet = context(body)
        assert packet["request_origin"]["kind"] == "owner"
        assert "work" not in packet
        assert packet["recovery_obstacle"]["work_id"] == str(work)
        assert any(
            item.attempt_id == active[0].attempt_id and item.status == "active"
            for item in core.read_execution(space, work, owner).attempts
        )
        return {"_final_text": "The result is saved; the interrupted execution needs inspection."}

    reopened = native.Provider([resumed])
    resumed_events = native.run_process(
        directory,
        runtime,
        Bridge(space, owner, directory),
        reopened,
        work=(activity, work),
        resume_session=next(sessions.glob("*.jsonl")),
        resume_via_switch=True,
        prompt_after_switch=True,
        prompt="What next?",
        expected_provider_calls=1,
    )
    assert core.read_work(space, work, owner) == before
    assert core.read_execution(space, work, owner) == execution
    report = {
        "initial_http": 2,
        "resume_http": 1,
        "final_capture_failed": True,
        "active_execution_preserved": True,
        "free_conversation_after_failure": True,
        "false_completion": False,
        "result_unchanged": True,
        "accepted": False,
    }
    for name, value in (
        ("report", report),
        ("http-requests", provider.requests + reopened.requests),
        ("native-events", events + resumed_events),
        ("execution", execution.model_dump(mode="json")),
    ):
        (directory / f"{name}.json").write_text(json.dumps(value, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    main()
