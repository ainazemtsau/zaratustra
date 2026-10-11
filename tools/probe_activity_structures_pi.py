"""Synthetic ordinary Pi: reviewed structure, typed procedure, compact and legacy continuation."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

import zaratustra.foundation as core
from zaratustra.pi_adapter import Bridge, read_pi_runtime
from zaratustra.pi_adapter.__main__ import INTERACTIVE_ZARA_TOOLS
from zaratustra.pi_adapter.activity_setup import SetupCoordinator
from zaratustra.pi_adapter.assigned import AssignedConfig
from zaratustra.pi_adapter.procedures import ProcedureCoordinator
from zaratustra.pi_adapter.skills import activity_setup_skill

from .probe_activity_setup_pi import context, harness

SetupArea = Literal[
    "goal", "workflow", "history", "continuation", "extension", "capabilities", "consistency"
]
AREAS: tuple[SetupArea, ...] = (
    "goal",
    "workflow",
    "history",
    "continuation",
    "extension",
    "capabilities",
    "consistency",
)


def draft(period: Literal["day", "week", "month"] = "week") -> core.ActivitySetupDraftV2:
    return core.ActivitySetupDraftV2(
        title="Fictional observations",
        goal="Keep and compare observations",
        instructions="Keep dated originals; revise corrections and preserve previous editions",
        process="Import events; review an explicit period; propose the next plan",
        first_action="Record the first observation",
        first_path="Original → event → review → next plan",
        formats=(
            core.SetupFormatTemplate(
                key="observation",
                definition=core.DataFormatState(
                    title="Observation",
                    role="event",
                    fields=(
                        core.DataField(key="day", meaning="Event day", type="date", indexed=True),
                        core.DataField(
                            key="value",
                            meaning="Measured value",
                            type="decimal",
                            precision=2,
                            unit="fictional_unit",
                            indexed=True,
                            unknown_allowed=True,
                        ),
                    ),
                    identity_fields=("day",),
                    time_field="day",
                ),
            ),
        ),
        procedures=(
            core.SetupProcedureTemplate(
                key="observe",
                purpose="Record a supplied observation",
                goal="Save the observation and its exact source",
                parameters=(
                    core.DataField(key="day", meaning="Event date", type="date"),
                    core.DataField(
                        key="value", meaning="Observed value", type="decimal", precision=2
                    ),
                ),
                operations=("create_entry",),
                outputs=(
                    core.SetupOutputTemplate(
                        slot="result", media_type="application/json", format_key="observation"
                    ),
                ),
                trigger="period",
                period=period,
                timezone="UTC",
                autonomy="run",
            ),
        ),
        working_sets=(
            core.WorkingSet(
                key="observations",
                purpose="Current observations",
                selectors=(
                    core.MemorySelector(current_activity=True, format_keys=("observation",)),
                ),
            ),
        ),
        decisions=(
            core.SetupDecisionBasis(
                subject="Review horizon",
                status="confirmed",
                explanation="The user chose the stated period",
            ),
        ),
    )


def run_probe(directory: Path, runtime: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=False)
    root, working = directory / "space", directory / "work"
    root.mkdir()
    working.mkdir()
    info = core.initialize_space(root)
    authority = core.authorize_local(root, actor="owner", source_ref="fictional-structure-probe")

    def operation(model: Any, **fields: Any) -> Any:
        return core.apply_operation(
            root,
            model(operation_id=uuid4(), space_id=info.space_id, actor="owner", **fields),
            authority,
        )

    operation(core.BootstrapRequest, decision_id=uuid4(), grant_id=uuid4())
    for upgrade in (
        core.upgrade_space,
        core.upgrade_execution_space,
        core.upgrade_continuation_space,
        core.upgrade_composition_space,
        core.upgrade_child_execution_space,
        core.upgrade_plan_revision_space,
        core.upgrade_parent_execution_space,
        core.upgrade_binding_space,
        core.upgrade_knowledge_space,
        core.upgrade_development_space,
        core.upgrade_change_package_space,
        core.upgrade_memory_space,
        core.upgrade_activity_setup_space,
    ):
        upgrade(root, authority)
    legacy_activity, legacy_work, legacy_result = uuid4(), uuid4(), uuid4()
    operation(
        core.CreateActivityRequest,
        activity_id=legacy_activity,
        state=core.ActivityState(title="Fictional Development", goal="Continue existing work"),
    )
    operation(
        core.CreateArtifactRequest,
        artifact_id=legacy_result,
        media_type="text/plain",
        content=b"Existing fictional development result",
    )
    operation(
        core.CreateWorkRequest,
        work_id=legacy_work,
        state=core.WorkState(
            activity_id=legacy_activity,
            goal="Continue the saved development result",
            inputs=(core.ArtifactRef(artifact_id=legacy_result, revision=1),),
            expected_outputs=(core.OutputContract(slot="report", media_type="text/plain"),),
        ),
    )
    legacy_before = core.read_work(root, legacy_work, authority)
    core.upgrade_structures_space(root, authority)
    native, actual = harness(), read_pi_runtime(runtime)
    requests: list[dict[str, Any]] = []
    bridges: list[Bridge] = []

    def bridge_for(provider: Any) -> Bridge:
        bridge = Bridge(root, authority, working)
        config = AssignedConfig(
            space=root,
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
        bridge.procedure_controller = ProcedureCoordinator(bridge, config)
        bridges.append(bridge)
        return bridge

    def run(provider: Any, **options: Any) -> None:
        bridge = bridge_for(provider)
        options["tool_names"] = ("read", "write", "edit", "bash", *INTERACTIVE_ZARA_TOOLS)
        waiting = options.get("wait_for")
        if waiting is not None:

            def poll() -> bool:
                try:
                    return bool(waiting())
                except core.FoundationError as error:
                    if error.code in ("storage", "busy") and "locked" in str(error):
                        return False
                    raise

            options["wait_for"] = poll
        try:
            native.run_process(working, runtime, bridge, provider, **options)
        finally:
            bridge.procedure_controller.close()
        requests.extend(provider.requests)

    question = "How often should the period be reviewed?"

    def reply_question(body: dict[str, Any]) -> dict[str, str]:
        assert not any(
            message.get("role") == "user" and message.get("content") == question
            for message in body["messages"]
        )
        return {"_final_text": question}

    first = native.Provider(
        [
            {
                "_tool": "zara_activity",
                "mode": "create",
                "title": "Fictional observations",
                "goal": "Keep daily observations and review a chosen period",
            },
            lambda _body: {
                "_tool": "zara_activity",
                "mode": "question",
                "setup_id": str(core.list_activity_setups(root, authority)[0].setup_id),
                "question": question,
            },
            reply_question,
        ]
    )
    run(
        first,
        confirmation_answers=(True,),
        skills=(activity_setup_skill(),),
        expected_provider_calls=3,
        prompt="Create observations; ask about the review period",
    )
    setup_id = core.list_activity_setups(root, authority)[0].setup_id
    reviews, packets = 0, []
    cadence: Literal["day", "week", "month"] = "week"

    def stage_reply(body: dict[str, Any]) -> dict[str, Any]:
        nonlocal reviews
        packet = context(body)
        if "work" in packet:
            assert not body.get("tools"), "Review must not expose file/command tools"
            incoming = json.loads(packet["inputs"][0]["content_text"])
            packets.append(incoming)
            if incoming["result_schema"]["title"] == "ActivitySetupReviewV2":
                reviews += 1
                manifest = incoming["activation_manifest"]
                assert manifest["structure"]["formats"] and manifest["structure"]["working_sets"]
                report = core.ActivitySetupReviewV2(
                    draft=core.ArtifactRef.model_validate(incoming["draft_ref"]),
                    manifest=core.ArtifactRef.model_validate(incoming["manifest_ref"]),
                    input_version=incoming["input_version"],
                    checked=AREAS,
                    coverage=tuple(
                        core.SetupAreaEvidence(
                            area=area,
                            explanation="Checked the full dated intake, exact revisions "
                            "and executable first path",
                            components=(
                                "process",
                                "formats.observation",
                                "procedures.observe",
                                "working_sets",
                            ),
                        )
                        for area in AREAS
                    ),
                    findings=(
                        core.SetupFinding(
                            area="history",
                            problem="Date meanings need clarification",
                            cause="The process conflates event and import",
                            blocking=True,
                        ),
                    )
                    if reviews == 1
                    else (),
                    conclusion="Correct the whole process"
                    if reviews == 1
                    else "No blocking obstacle",
                )
                if reviews == 2:
                    assert "event and import" in incoming["draft"]["process"]
                    assert "event and import" in incoming["draft"]["instructions"]
                result = report.model_dump_json()
            elif incoming.get("draft"):
                changed = core.ActivitySetupDraftV2.model_validate(incoming["draft"])
                result = changed.model_copy(
                    update={
                        "process": changed.process + "; event and import dates differ",
                        "instructions": changed.instructions + "; event and import dates differ",
                    }
                ).model_dump_json()
            else:
                result = draft(cadence).model_dump_json()
            return {"_final_text": json.dumps({"zara": "final", "text": result})}
        tools = [message for message in body["messages"] if message["role"] == "tool"]
        if not tools:
            return {"_tool": "zara_activity", "mode": "answer", "setup_id": str(setup_id)}
        if len(tools) == 1:
            return {"_tool": "zara_activity", "mode": "submit", "setup_id": str(setup_id)}
        return {"_final_text": "Setup runs in this Pi window"}

    second = native.Provider([stage_reply] * 32)
    run(
        second,
        skills=(activity_setup_skill(),),
        expected_provider_calls=7,
        prompt="Daily observations, weekly review; preserve originals and event dates",
        wait_for=lambda: (
            core.read_activity_setup(root, setup_id, authority).state.phase
            in ("ready", "needs_attention")
        ),
    )
    setup = core.read_activity_setup(root, setup_id, authority)
    assert setup.state.phase == "ready", setup.model_dump_json()
    assert setup.state.reviews_completed == 2 and len(packets) == 4
    activity = setup.state.activity_id
    start = native.Provider(
        [
            {
                "_tool": "zara_data",
                "mode": "apply",
                "operation": "start_procedure",
                "arguments": {
                    "activity_id": str(activity),
                    "procedure": "observe",
                    "request_key": "first-observation",
                    "parameters": {"day": "2026-01-04", "value": "1.25"},
                    "when": "2026-01-04T12:00:00Z",
                },
            },
            {"_final_text": "The dated intent and Work are saved"},
        ]
    )
    run(
        start,
        expected_provider_calls=2,
        prompt="Record the fictional observation: 4 January, value 1.25",
    )
    saved = core.start_procedure(root, authority, activity, "observe", "first-observation")
    run_id, work_id, entry_id = UUID(str(saved["run_id"])), UUID(str(saved["work_id"])), uuid4()

    def execution_reply(body: dict[str, Any]) -> dict[str, Any]:
        packet = context(body)
        if "work" not in packet:
            tools = [message for message in body["messages"] if message["role"] == "tool"]
            return (
                {"_tool": "zara_data", "mode": "run", "run_id": str(run_id)}
                if not tools
                else {"_final_text": "Executing saved Work"}
            )
        input_ref = packet["work"]["state"]["inputs"][0]
        contract = packet["work"]["state"]["expected_outputs"][0]
        if not any(message["role"] == "tool" for message in body["messages"]):
            return {
                "_tool": "zara_data",
                "mode": "apply",
                "operation": "create_entry",
                "arguments": {
                    "record_id": str(entry_id),
                    "state": {
                        "kind": "data_entry",
                        "role": "event",
                        "format_ref": contract["format_ref"],
                        "values": {"day": "2026-01-04", "value": "1.25"},
                        "bases": [
                            {
                                "record_id": input_ref["artifact_id"],
                                "revision": input_ref["revision"],
                            }
                        ],
                    },
                },
            }
        result = core.DataOutputEnvelope(
            complete=True,
            entries=(core.KnowledgeRef(record_id=entry_id, revision=1),),
            basis_snapshot=core.KnowledgeRef.model_validate(packet["procedure"]["snapshot"]),
            result="Observation saved with its event date and original",
        )
        return {"_final_text": json.dumps({"zara": "final", "text": result.model_dump_json()})}

    execution = native.Provider([execution_reply] * 16)
    run(
        execution,
        expected_provider_calls=4,
        wait_for=lambda: bool(core.read_work(root, work_id, authority).state.linked_outputs),
        prompt="Execute the saved observation procedure",
    )
    result = core.read_work(root, work_id, authority)
    assert result.state.acceptance is None and result.state.linked_outputs
    format_ref = result.state.expected_outputs[0].format_ref
    assert format_ref is not None
    third = native.Provider(
        [
            {
                "_tool": "zara_data",
                "mode": "apply",
                "operation": "describe_structure",
                "arguments": {"activity_id": str(activity), "work_id": str(work_id)},
            }
        ]
    )
    run(
        third, work=(activity, work_id), compact=True, split_compact=True, expected_provider_calls=5
    )
    assert core.start_procedure(root, authority, activity, "observe", "first-observation")[
        "work_id"
    ] == str(work_id)
    legacy = native.Provider([{"_final_text": "Existing Development context remains available"}])
    run(legacy, work=(legacy_activity, legacy_work), expected_provider_calls=1)
    assert core.read_work(root, legacy_work, authority) == legacy_before
    assert (
        core.read_artifact(root, legacy_result, authority).content
        == b"Existing fictional development result"
    )
    # Adopt a structured monthly process into the old Development Activity,
    # then continue the same pre-upgrade Work with its legacy context.
    cadence = "month"
    change = native.Provider(
        [
            {
                "_tool": "zara_activity",
                "mode": "change_structure",
                "record_id": str(legacy_activity),
            },
            {"_final_text": "Prepare a monthly process for the existing Activity"},
        ]
    )
    run(
        change,
        confirmation_answers=(True,),
        expected_provider_calls=2,
        prompt="Configure this existing Development Activity for monthly reviews",
    )
    setup_id = next(
        item.setup_id
        for item in core.list_activity_setups(root, authority)
        if item.state.activity_id == legacy_activity and item.state.mode == "change_structure"
    )
    adoption = native.Provider([stage_reply] * 16)
    run(
        adoption,
        expected_provider_calls=5,
        skills=(activity_setup_skill(),),
        prompt="Use a monthly process; preserve existing history",
        wait_for=lambda: (
            core.read_activity_setup(root, setup_id, authority).state.phase
            in ("ready", "needs_attention")
        ),
    )
    assert core.read_activity_setup(root, setup_id, authority).state.phase == "ready"
    assert (
        core.describe_structure(root, legacy_activity, authority)["state"]["procedures"][0][
            "period"
        ]
        == "month"
    )
    assert core.describe_structure(root, legacy_activity, authority, work_id=legacy_work)["legacy"]
    continued = native.Provider([{"_final_text": "The old Development Work continues"}])
    run(continued, work=(legacy_activity, legacy_work), expected_provider_calls=1)
    assert core.read_work(root, legacy_work, authority) == legacy_before
    assert all("ZARA_MANIFEST:" in json.dumps(body) for body in requests)
    report = {
        "schema": 15,
        "pi_version": actual.version,
        "review_passes": reviews,
        "typed_work": str(work_id),
        "typed_entry": str(entry_id),
        "activity_id": str(activity),
        "setup_id": str(setup_id),
        "legacy_history_preserved": True,
        "compact_requests": 2,
        "synthetic_http": len(requests),
        "real_model_calls": 0,
        "paid_api_calls": 0,
        "work_accepted": False,
        "module": str(Path(core.__file__).resolve()),
    }
    (directory / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--pi-runtime", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_probe(args.directory.resolve(), args.pi_runtime.resolve()), indent=2))


if __name__ == "__main__":
    main()
