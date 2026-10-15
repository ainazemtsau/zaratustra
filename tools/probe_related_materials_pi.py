"""Ordinary Pi continues a saved procedure after a cross-family late arrival."""

from __future__ import annotations

import argparse
import json
import re
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import zaratustra.foundation as core
from zaratustra.pi_adapter import Bridge
from zaratustra.pi_adapter.__main__ import INTERACTIVE_ZARA_TOOLS, _prepare_space
from zaratustra.pi_adapter.runtime import system_pi_runtime

from .probe_conversation_responses_pi import RawResponsesProvider, codex_context, completed_response
from .probe_knowledge_pi import run_process
from .probe_ordinary_selection_pi import _installed_bytes
from .probe_read_boundaries_pi import last_output


@dataclass(frozen=True)
class Fixture:
    root: Path
    owner: core.LocalAuthority
    activity: UUID
    work: UUID
    snapshot: core.KnowledgeRef
    packet: core.KnowledgeRef
    entry: core.KnowledgeRef
    format_ref: core.KnowledgeRef
    development: UUID
    saved_members: int


def fixture(directory: Path) -> Fixture:
    from tests.zaratustra.foundation.test_activity_structures import (
        _activate,
        _proposal,
        _structured_case,
    )

    directory.mkdir(parents=True, exist_ok=False)
    case = _structured_case(directory)
    root, space, owner, setup, activity, *_ = case
    draft = _proposal()
    definition = draft.formats[0].definition
    definition = definition.model_copy(
        update={
            "fields": definition.fields
            + (
                core.DataField(
                    key="related", meaning="Exact supporting material", type="ref", required=False
                ),
            )
        }
    )
    draft = draft.model_copy(
        update={
            "formats": (draft.formats[0].model_copy(update={"definition": definition}),),
            "procedures": (
                draft.procedures[0].model_copy(
                    update={
                        "inputs": (
                            core.MemorySelector(
                                current_activity=True, format_keys=("observation",)
                            ),
                        )
                    }
                ),
            ),
        }
    )
    head = _activate(case, draft)
    _prepare_space(root, owner.actor, create=False, upgrade_existing=True)
    format_ref = core.KnowledgeRef.model_validate(head["state"]["formats"]["observation"])
    run = core.start_procedure(root, owner, activity, "observe", "late-related-material")
    work = UUID(str(run["work_id"]))
    saved_run = core.procedure_for_work(root, owner, work)
    assert saved_run is not None
    snapshot = core.KnowledgeRef.model_validate(saved_run["snapshot"])
    old = core.read_knowledge(root, snapshot.record_id, owner, revision=snapshot.revision).state
    assert isinstance(old, core.MemoryViewState) and old.selection is not None
    saved_members = len(old.selection.members)
    assert saved_members == 0
    (input_ref,) = core.read_work(root, work, owner).state.inputs
    packet = core.KnowledgeRef(record_id=input_ref.artifact_id, revision=input_ref.revision)
    original = core.read_activity_setup(root, setup, owner).state.sources[0]
    created = core.create_entry(
        root,
        owner,
        core.DataEntryState(
            scope_activity_id=activity,
            format_ref=format_ref,
            role="event",
            values={
                "day": "2026-01-02",
                "value": "2.50",
                "related": {
                    "record_id": str(packet.record_id),
                    "revision": packet.revision,
                    "mode": "exact",
                },
            },
            bases=(original,),
        ),
    )
    entry = core.KnowledgeRef(record_id=UUID(str(created.result["record_id"])), revision=1)
    development_activity, development = uuid4(), uuid4()
    for request in (
        core.CreateActivityRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            activity_id=development_activity,
            state=core.ActivityState(title="Fictional Development", goal="Keep independent work"),
        ),
        core.CreateWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            work_id=development,
            state=core.WorkState(
                activity_id=development_activity,
                goal="Retain independent history",
                inputs=(input_ref,),
                expected_outputs=(core.OutputContract(slot="report", media_type="text/plain"),),
            ),
        ),
    ):
        core.apply_operation(root, request, owner)
    return Fixture(
        root, owner, activity, work, snapshot, packet, entry, format_ref, development, saved_members
    )


def run(directory: Path, *, wheel: Path | None = None, negative: bool = False) -> dict[str, Any]:
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    report: dict[str, Any] = {"outcome": "not_run", "real_model_calls": 0}
    providers: list[RawResponsesProvider] = []
    events: list[dict[str, object]] = []
    try:
        if wheel is not None:
            report.update(_installed_bytes(wheel))
        case = fixture(directory / "fixture")
        before = core.read_execution(case.root, case.development, case.owner)
        target_before = core.read_work(case.root, case.work, case.owner)
        packet_bytes = core.read_artifact(
            case.root, case.packet.record_id, case.owner, revision=case.packet.revision
        ).content
        assert packet_bytes is not None
        selector = {
            "activity_ids": [str(case.activity)],
            "format_refs": [case.format_ref.model_dump(mode="json")],
        }
        queried: list[dict[str, Any]] = []
        manifests: list[str] = []
        selected = False
        sessions = directory / "sessions"
        sessions.mkdir()

        def route(body: dict[str, Any]) -> list[dict[str, Any]]:
            nonlocal selected
            packet = codex_context(body)
            marker = packet.get("work", {}).get("work_id")
            if marker != str(case.work):
                actions = packet["conversation_actions"]
                chosen = next(
                    item for item in actions if item["ref"]["action_id"] == str(case.work)
                )
                return completed_response(
                    None,
                    call=(
                        "zara_conversation",
                        {
                            "mode": "use_existing_work",
                            "action_ref": chosen["ref"],
                        },
                    ),
                )
            selected = True
            assert packet["procedure"]["work_id"] == str(case.work)
            assert packet["procedure_input"]["members"] == case.saved_members
            assert packet["procedure_input"]["current"] is False
            (exact_input,) = packet["inputs"]
            assert exact_input["artifact_id"] == str(case.packet.record_id)
            assert exact_input["content_text"].encode() == packet_bytes
            if len(queried) == 0 or last_output(body).get("selection_id") is None:
                queried.append({})
                return completed_response(
                    None,
                    call=(
                        "zara_data",
                        {
                            "mode": "apply",
                            "operation": "query_entries",
                            "arguments": {"selectors": [selector], "max_bytes": 32768},
                        },
                    ),
                )
            output = last_output(body)
            refs = [
                core.KnowledgeRef.model_validate(value) for value in output["table_of_contents"]
            ]
            assert case.entry in refs and case.packet in refs
            assert output["content_complete"] is True
            assert packet_bytes.decode() in output["content_text"]
            queried[-1] = output
            return completed_response(
                "The retained inputs and related material are available. Continue the work."
            )

        provider = RawResponsesProvider([route] * 4)
        providers.append(provider)
        bridge = Bridge(case.root, case.owner, directory)
        events.extend(
            run_process(
                directory,
                system_pi_runtime().root,
                bridge,
                provider,
                work=(case.activity, case.work) if negative else None,
                provider_profile="codex-sse",
                local_model_id="gpt-6.1-sol",
                prompt="Continue the existing fictional observations procedure from saved data.",
                tool_names=INTERACTIVE_ZARA_TOOLS,
                expected_pre_send_failure=negative,
                expected_provider_calls=0 if negative else 3,
                timeout_seconds=60,
                session_directory=sessions,
            )
        )
        if negative:
            failures = [
                str(event.get("error", ""))
                for event in events
                if event.get("type") == "extension_error"
            ]
            assert any("Related definition disappeared" in failure for failure in failures), (
                failures
            )
            report.update(
                outcome="reproduced", localhost_http=0, failure="Related definition disappeared"
            )
            return report
        assert selected and len(queried) == 1 and queried[0]
        (session_file,) = sessions.glob("*.jsonl")
        queried.clear()
        second = RawResponsesProvider([route] * 2)
        providers.append(second)
        events.extend(
            run_process(
                directory,
                system_pi_runtime().root,
                Bridge(case.root, case.owner, directory),
                second,
                resume_session=session_file,
                resume_via_switch=True,
                prompt_after_switch=True,
                provider_profile="codex-sse",
                local_model_id="gpt-6.1-sol",
                prompt="Continue the saved procedure after reopening; verify the related material.",
                tool_names=INTERACTIVE_ZARA_TOOLS,
                expected_provider_calls=2,
                timeout_seconds=60,
            )
        )
        assert len(queried) == 1 and queried[0]
        assert core.read_work(case.root, case.work, case.owner) == target_before
        assert core.read_execution(case.root, case.development, case.owner) == before
        execution = core.read_execution(case.root, case.work, case.owner)
        assert not execution.outputs and execution.work.state.acceptance is None
        deliveries = {}
        for item in execution.invocations:
            delivery = core.read_context_delivery(case.root, item.invocation_id, case.owner)
            assert item.status == delivery["stage"] == "answered"
            assert delivery["context_work_id"] == str(case.work)
            assert delivery["correlation_state"] == "exact"
            assert delivery["context_attempt_id"] == str(item.attempt_id)
            assert delivery["request_sha256"] == item.request_sha256
            deliveries[str(delivery["manifest_id"])] = delivery
            manifests.append(str(delivery["manifest_id"]))
        sent_manifests = []
        for body in [request for p in providers for request in p.requests]:
            identifier, revision = re.findall(
                r"ZARA_MANIFEST:([0-9a-f-]+)@([0-9]+)", body["instructions"]
            )[-1]
            manifest = core.read_knowledge(
                case.root, UUID(identifier), case.owner, revision=int(revision)
            )
            assert isinstance(manifest.state, core.ContextState)
            if manifest.state.work_id == case.work:
                assert deliveries[identifier]["context_session_id"] == str(
                    manifest.state.session_id
                )
                sent_manifests.append(identifier)
        assert len(sent_manifests) == len(manifests) == 4
        assert set(sent_manifests) == set(manifests)
        assert not any(event.get("type") == "extension_error" for event in events)
        report.update(
            outcome="passed",
            localhost_http=sum(p.calls for p in providers),
            native_processes=2,
            selected_ordinary_work=True,
            late_related_material_read=True,
            snapshot_preserved=True,
            restart_preserved=True,
            exact_request_pins=True,
            development_preserved=True,
            acceptance=False,
            target_manifests=manifests,
        )
        return report
    except Exception as error:
        report.update(outcome="failed", error=repr(error))
        (directory / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        for name, value in (
            ("report", report),
            ("native-events", events),
            ("http-requests", [r for p in providers for r in p.requests]),
            ("provider-errors", [e for p in providers for e in p.errors]),
        ):
            (directory / f"{name}.json").write_text(
                json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--negative", action="store_true")
    args = parser.parse_args()
    directory = args.directory.resolve()
    scratch = Path(__file__).resolve().parents[1] / "_scratch"
    if not directory.is_relative_to(scratch) or directory == scratch:
        parser.error("Use a new directory inside the checkout's _scratch")
    print(json.dumps(run(directory, wheel=args.wheel, negative=args.negative), indent=2))


if __name__ == "__main__":
    main()
