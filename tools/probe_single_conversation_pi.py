"""One ordinary Pi owner; fictional localhost provider and exact native evidence."""

from __future__ import annotations

import argparse
import json
import threading
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import zaratustra.foundation as core
from zaratustra.pi_adapter import Bridge
from zaratustra.pi_adapter.__main__ import INTERACTIVE_ZARA_TOOLS, _prepare_space

from .probe_conversation_responses_pi import (
    RawResponsesProvider,
    codex_context,
    completed_response,
)
from .probe_knowledge_pi import run_process


def publication_probe(
    directory: Path, runtime: Path, *, baseline: bool = False, repair: bool = False
) -> dict[str, Any]:
    """Hold a normal response until the old watcher actually observes running."""
    directory.mkdir(parents=True, exist_ok=False)
    space = directory / "space"
    space.mkdir()
    owner = _prepare_space(space, "owner", create=True)
    activity, work = uuid4(), uuid4()
    for request in (
        core.CreateActivityRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor=owner.actor,
            activity_id=activity,
            state=core.ActivityState(title="Fictional observation", goal="Save one observation"),
        ),
        core.CreateWorkRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor=owner.actor,
            work_id=work,
            state=core.WorkState(
                activity_id=activity,
                goal="Save one observation",
                expected_outputs=(core.OutputContract(slot="result", media_type="text/plain"),),
            ),
        ),
    ):
        core.apply_operation(space, request, owner)
    running_reads = 0
    running_observed = threading.Event()
    normal = host = 0

    def bridge_response(path: str, payload: object) -> None:
        nonlocal running_reads
        if path != "/v1/conversation" or not isinstance(payload, dict):
            return
        item = payload.get("item") or {}
        if item.get("subject_id") == str(work) and item.get("kind") == "running":
            running_reads += 1
            if running_reads >= 2:
                running_observed.set()

    def route(body: dict[str, Any]) -> list[dict[str, Any]]:
        nonlocal normal, host
        packet = codex_context(body)
        if packet.get("conversation_event"):
            host += 1
            assert baseline
            assert packet["conversation_event"]["kind"] == "result"
            return completed_response("A second explanation of the same saved observation.")
        normal += 1
        if normal == 1:
            action = next(
                item for item in packet["conversation_actions"] if item["subject_id"] == str(work)
            )
            return completed_response(
                None,
                call=(
                    "zara_conversation",
                    {"mode": "use_existing_work", "action_ref": action["ref"]},
                ),
            )
        if normal == 2:
            return completed_response(
                None,
                call=(
                    "zara_result",
                    {"mode": "publish", "slot": "result", "content_text": "Fictional value 8"},
                ),
            )
        if repair:
            if normal in (3, 4):
                if normal == 4:
                    assert not body.get("tools")
                return completed_response(None, reasoning=True)
            assert normal == 5 and packet.get("response_recovery")
            assert not body.get("tools")
        else:
            assert normal == 3
        if baseline:
            assert running_observed.wait(15), "Old watcher did not observe the held running pin"
        return completed_response("The observation is saved; acceptance is separate.")

    provider = RawResponsesProvider([route] * 6)
    bridge = Bridge(space, owner, directory)
    sessions = directory / "sessions"
    sessions.mkdir()
    events = run_process(
        directory,
        runtime,
        bridge,
        provider,
        prompt="Save the fictional observation in its existing Work",
        provider_profile="codex-sse",
        local_model_id="gpt-6.1-sol",
        session_directory=sessions,
        tool_names=INTERACTIVE_ZARA_TOOLS,
        expected_provider_calls=4 if baseline else 5 if repair else 3,
        wait_for=(lambda: host == 1) if baseline else None,
        on_bridge_response=bridge_response,
        timeout_seconds=45,
    )
    final = core.read_work(space, work, owner)
    assert len(final.state.linked_outputs) == 1 and final.state.acceptance is None
    assert normal == (5 if repair else 3) and host == int(baseline)
    assert not any(
        item.status == "active" for item in core.read_execution(space, work, owner).attempts
    )
    finals = []
    for item in cast(
        list[dict[str, Any]], core.list_knowledge(space, owner, kind="source", limit=100)["items"]
    ):
        retained = core.read_knowledge(space, UUID(item["record_id"]), owner)
        state = retained.state
        if (
            isinstance(state, core.SourceState)
            and state.scope_work_id == work
            and state.conversation_final
        ):
            assert state.conversation_terminal is not None
            assert state.conversation_id is not None
            proof = core.read_terminal_response(
                space,
                core.KnowledgeRef(record_id=retained.record_id, revision=retained.revision),
                owner,
                session_id=UUID(state.conversation_id),
            )
            assert proof.outcome == "visible" and proof.work_id == work
            finals.append(proof)
    assert finals
    entries = [
        json.loads(line)
        for line in next(sessions.glob("*.jsonl")).read_text(encoding="utf-8").splitlines()
    ]
    wakes = [item for item in entries if item.get("customType") == "zara-conversation-wake"]
    assert bool(wakes) is baseline
    report = {
        "baseline": baseline,
        "http": provider.calls,
        "ordinary": normal,
        "host": host,
        "running_reads": running_reads,
        "accepted": False,
        "real_calls": 0,
    }
    for name, value in (
        ("report", report),
        ("requests", provider.requests),
        ("events", events),
        ("entries", entries),
    ):
        (directory / f"{name}.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--pi-runtime", type=Path, required=True)
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--empty", action="store_true")
    parser.add_argument("--exhausted", action="store_true")
    parser.add_argument("--repair-work", action="store_true")
    args = parser.parse_args()
    result = (
        empty_probe(args.directory.resolve(), args.pi_runtime.resolve(), exhausted=args.exhausted)
        if args.empty
        else publication_probe(
            args.directory.resolve(),
            args.pi_runtime.resolve(),
            baseline=args.baseline,
            repair=args.repair_work,
        )
    )
    print(json.dumps(result, indent=2))


def empty_probe(directory: Path, runtime: Path, *, exhausted: bool = False) -> dict[str, Any]:
    """Raw known-empty native finals repair within one read-only conversation."""
    directory.mkdir(parents=True, exist_ok=False)
    space = directory / "space"
    space.mkdir()
    owner = _prepare_space(space, "owner", create=True)
    sessions = directory / "sessions"
    sessions.mkdir()

    def response(body: dict[str, Any]) -> list[dict[str, Any]]:
        packet = codex_context(body)
        if packet.get("response_recovery"):
            assert packet["request_origin"]["kind"] == "owner"
            assert not body.get("tools"), "Reply repair cannot issue another tool action"
            assert "zara-conversation-wake" not in json.dumps(body)
        if provider.calls == 1:
            return completed_response(None, reasoning=True)
        if provider.calls == 2 or exhausted:
            return completed_response(" \n ")
        assert packet.get("response_recovery")
        return completed_response("The fictional saved state can be continued.")

    provider = RawResponsesProvider([response] * 3)
    bridge = Bridge(space, owner, directory)
    events = run_process(
        directory,
        runtime,
        bridge,
        provider,
        prompt="Explain the next step of a fictional task",
        provider_profile="codex-sse",
        local_model_id="gpt-6.1-sol",
        expected_provider_calls=3,
        session_directory=sessions,
        tool_names=INTERACTIVE_ZARA_TOOLS,
        timeout_seconds=45,
    )
    assert not provider.errors and provider.calls == 3
    entries = [
        json.loads(line)
        for line in next(sessions.glob("*.jsonl")).read_text(encoding="utf-8").splitlines()
    ]
    repairs = [item for item in entries if item.get("customType") == "zara-response-repair"]
    assert [item["data"]["ordinal"] for item in repairs] == [1, 2]
    assert len([item for item in entries if item.get("type") == "context_edit"]) == 2
    assert core.list_conversation_deliveries(space, owner) == ()
    report = {
        "http": provider.calls,
        "reserved_repairs": len(repairs),
        "exhausted": exhausted,
        "new_delivery_claims": 0,
        "real_calls": 0,
    }
    for name, value in (
        ("report", report),
        ("requests", provider.requests),
        ("events", events),
        ("entries", entries),
    ):
        (directory / f"{name}.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return report


if __name__ == "__main__":
    main()
