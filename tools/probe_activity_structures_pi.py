"""Synthetic ordinary Pi: reviewed structure, typed procedure, compact and legacy continuation."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import threading
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import zaratustra.foundation as core
from zaratustra.pi_adapter import Bridge, read_pi_runtime
from zaratustra.pi_adapter.__main__ import INTERACTIVE_ZARA_TOOLS
from zaratustra.pi_adapter.activity_setup import SetupCoordinator
from zaratustra.pi_adapter.assigned import AssignedConfig
from zaratustra.pi_adapter.procedures import ProcedureCoordinator
from zaratustra.pi_adapter.skills import activity_setup_skill
from zaratustra.pi_adapter.workflows import WorkflowCoordinator
from zaratustra.workspace import LaunchConfig, Project, write_config

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
                operations=(
                    core.ProcedureOperation.CREATE_ENTRY,
                    core.ProcedureOperation.WORKING_SET,
                ),
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


def run_probe(
    directory: Path,
    runtime: Path,
    *,
    blank_response: bool = False,
    terminal_proof: bool = False,
    procedure_project: Literal["personal", "external"] = "personal",
) -> dict[str, Any]:
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
    core.upgrade_structures_space(root, authority)
    assert core.read_space(root).schema_version == 15
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
    core.upgrade_workflow_space(root, authority)
    if terminal_proof:
        core.upgrade_conversation_space(root, authority)
        core.upgrade_delivery_correlation_space(root, authority)
        assert core.read_work(root, legacy_work, authority) == legacy_before
    native, actual = harness(), read_pi_runtime(runtime)
    launch_runtime = directory / "launch-runtime"
    launch_runtime.mkdir()
    external = directory / "external-project"
    external.mkdir()
    launch_path = launch_runtime / "config.json"
    requests: list[dict[str, Any]] = []
    bridges: list[Bridge] = []

    def bridge_for(provider: Any) -> Bridge:
        write_config(
            launch_path,
            LaunchConfig(
                version=2,
                actor=authority.actor,
                space_id=authority.space_id,
                space=root,
                workspace=working,
                personal_root=working,
                runtime_root=launch_runtime,
                sqlite_dll=launch_runtime / "sqlite3.dll",
                pi_runtime=runtime,
                pi_source="system",
                provider_profile="local-completions",
                provider_base_url=f"http://127.0.0.1:{provider.server_port}/v1",
                provider_id="fictional-local",
                model_id="fictional-model",
                reserve_units=1000,
                projects=(Project(name="external", path=external),),
            ),
        )
        bridge = Bridge(root, authority, working, workspace_config=launch_path)
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
            workspace_config=launch_path,
        )
        bridge.setup_controller = SetupCoordinator(bridge, config)
        bridge.procedure_controller = ProcedureCoordinator(bridge, config)
        bridge.workflow_controller = WorkflowCoordinator(bridge, config)
        bridges.append(bridge)
        return bridge

    def run(provider: Any, **options: Any) -> None:
        bridge = bridge_for(provider)
        options["tool_names"] = ("read", "write", "edit", "bash", *INTERACTIVE_ZARA_TOOLS)
        options["timeout_seconds"] = 240
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
    first_wait = core.read_activity_setup(root, setup_id, authority)
    confusion = native.Provider(
        [
            {
                "_tool": "zara_activity",
                "mode": "status",
                "setup_id": str(setup_id),
            },
            {"_final_text": "The saved question asks how often to review; it is still open"},
        ]
    )
    run(
        confusion,
        expected_provider_calls=2,
        prompt="Why did everything stop? I do not understand the question",
    )
    unchanged = core.read_activity_setup(root, setup_id, authority)
    assert unchanged.state.question == first_wait.state.question
    assert unchanged.state.input_version == first_wait.state.input_version
    assert unchanged.state.phase == "needs_input"
    followup_question = "Should corrections retain their original event date?"
    followup = native.Provider(
        [
            {"_tool": "zara_activity", "mode": "answer", "setup_id": str(setup_id)},
            {
                "_tool": "zara_activity",
                "mode": "question",
                "setup_id": str(setup_id),
                "question": followup_question,
            },
            {"_final_text": followup_question},
        ]
    )
    run(
        followup,
        expected_provider_calls=3,
        prompt="Review weekly",
    )
    following = core.read_activity_setup(root, setup_id, authority)
    assert following.state.phase == "needs_input"
    assert following.state.question == followup_question
    assert len(following.state.interactions) == len(first_wait.state.interactions) + 1
    reviews, packets = 0, []
    raw_drafts = 0
    malformed = "" if blank_response else '{"contract_version":2,'
    cadence: Literal["day", "week", "month"] = "week"

    def configured_draft() -> core.ActivitySetupDraftV2:
        proposal = draft(cadence)
        if procedure_project == "external":
            procedure = proposal.procedures[0].model_copy(
                update={"resource": "project", "project": "external"}
            )
            proposal = proposal.model_copy(update={"procedures": (procedure,)})
        return proposal

    def stage_reply(body: dict[str, Any]) -> dict[str, Any]:
        nonlocal reviews, raw_drafts
        packet = context(body)
        if "work" in packet:
            assert {item["function"]["name"] for item in body.get("tools", [])}.issubset(
                {"zara_workflow", "zara_memory"}
            ), "Review must not expose file/command or mutation tools"
            incoming = json.loads(packet["inputs"][0]["content_text"])
            packets.append(incoming)
            assert "working_set" in {item["operation"] for item in incoming["supported_operations"]}
            if not incoming.get("draft"):
                raw_drafts += 1
                if raw_drafts == 1:
                    return {"_final_text": malformed}
                if raw_drafts == 2:
                    assert incoming["rejected_result"]["content_text"] == malformed
                    invalid = json.loads(configured_draft().model_dump_json())
                    invalid["procedures"][0]["operations"] = ["Preserve the original separately"]
                    return {"_final_text": json.dumps(invalid)}
                if raw_drafts == 3:
                    assert incoming["rejected_result"]["issues"][0]["path"] == [
                        "procedures",
                        0,
                        "operations",
                        0,
                    ]
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
                result = configured_draft().model_dump_json()
            return {"_final_text": result}
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
        expected_provider_calls=9,
        prompt="Yes, preserve originals and event dates; daily observations and weekly review",
        wait_for=lambda: (
            core.read_activity_setup(root, setup_id, authority).state.phase
            in ("ready", "needs_attention")
        ),
    )
    setup = core.read_activity_setup(root, setup_id, authority)
    assert setup.state.phase == "ready", setup.model_dump_json()
    assert setup.state.reviews_completed == 2 and len(packets) == 6
    assert sum(stage.rejection is not None for stage in setup.state.stages) == 2
    terminal_proofs: list[dict[str, Any]] = []
    if terminal_proof:
        stage_originals = []
        cursor: str | None = None
        while True:
            source_page = core.list_knowledge(
                root, authority, kind="source", limit=100, cursor=cursor
            )
            for source_item in cast(list[dict[str, Any]], source_page["items"]):
                original = core.read_knowledge(root, UUID(source_item["record_id"]), authority)
                if (
                    isinstance(original.state, core.SourceState)
                    and original.state.channel == "conversation_assistant"
                ):
                    stage_originals.append(original)
            cursor = cast(str | None, source_page["next_cursor"])
            if cursor is None:
                break
        for stage in setup.state.stages:
            retained = stage.output or (stage.rejection.artifact if stage.rejection else None)
            assert retained is not None, "Stage lacks its completed or rejected original"
            if stage.rejection is not None:
                assert stage.retired and stage.output is None
            output = core.read_artifact(
                root, retained.artifact_id, authority, revision=retained.revision
            )
            terminal_sources = [
                original
                for original in stage_originals
                if isinstance(original.state, core.SourceState)
                and original.state.scope_work_id == stage.work_id
                and original.state.conversation_terminal is not None
            ]
            assert len(terminal_sources) == 1, "Stage lacks one exact native terminal original"
            original = terminal_sources[0]
            assert isinstance(original.state, core.SourceState)
            observation = original.state.conversation_terminal
            assert observation is not None and observation.result_protocol == "setup_json"
            assert original.state.capture == "full" and original.state.content == output.content
            proof = core.read_terminal_response(
                root,
                core.KnowledgeRef(record_id=original.record_id, revision=original.revision),
                authority,
                session_id=UUID(str(original.state.conversation_id)),
                invocation_id=observation.invocation_id,
                manifest=observation.manifest,
                assistant_entry_id=observation.assistant_entry_id,
            )
            assert proof.work_id == stage.work_id
            assert proof.outcome == ("visible" if output.content else "empty")
            header = f"ZARA_MANIFEST:{proof.manifest.record_id}@{proof.manifest.revision}"
            matching_requests = [body for body in requests if header in json.dumps(body)]
            assert len(matching_requests) == 1, "Terminal manifest differs from actual HTTP"
            assert context(matching_requests[0])["work"]["work_id"] == str(stage.work_id)
            early_originals = [
                item
                for item in stage_originals
                if isinstance(item.state, core.SourceState)
                and item.state.scope_work_id == stage.work_id
                and item.state.conversation_terminal is None
                and item.state.capture == "full"
                and item.state.content == output.content
            ]
            assert len(early_originals) == 1, "Early bytes were not retained before accounting"
            events = core.read_execution_events(root, stage.work_id, 0, authority)
            finish_events = [
                event
                for event in events
                if event["kind"] == "finish_invocation"
                and event["invocation_id"] == str(proof.invocation_id)
            ]
            publications = [
                event
                for event in events
                if event["kind"] == "publish_attempt_output"
                and event["attempt_id"] == str(proof.attempt_id)
            ]
            assert len(finish_events) == len(publications) == 1
            revisions = [
                core.read_receipt(root, operation_id, authority).state_revision
                for operation_id in (
                    early_originals[0].operation_id,
                    UUID(str(finish_events[0]["operation_id"])),
                    original.operation_id,
                    UUID(str(publications[0]["operation_id"])),
                )
            ]
            assert revisions == sorted(set(revisions)), "Capture/account/publication order differs"
            terminal_proofs.append(
                {
                    **proof.model_dump(mode="json"),
                    "result_protocol": observation.result_protocol,
                    "raw_bytes": len(output.content or b""),
                    "matching_actual_requests": len(matching_requests),
                    "state_revisions": revisions,
                    "rejected": stage.rejection is not None,
                }
            )
        assert len(terminal_proofs) == len(setup.state.stages)
        assert any(item["rejected"] for item in terminal_proofs)
        if blank_response:
            assert any(
                item["outcome"] == "empty" and item["raw_bytes"] == 0 for item in terminal_proofs
            )
        (directory / "stage-terminal-proofs.json").write_text(
            json.dumps(terminal_proofs, indent=2), encoding="utf-8"
        )
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
        tools = [message for message in body["messages"] if message["role"] == "tool"]
        assigned = core.read_execution(root, work_id, authority)
        active = [item for item in assigned.resources if item.state.status == "active"]
        expected_root = working if procedure_project == "personal" else external
        assert len(active) == 1 and active[0].state.root == expected_root
        assert assigned.attempts[-1].resource_id == active[0].resource_id
        if not tools:
            return {
                "_tool": "write",
                "path": "procedure-root-proof.txt",
                "content": "Fictional configured procedure — exact working directory",
            }
        if len(tools) == 1:
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
        expected_provider_calls=5,
        wait_for=lambda: bool(core.read_work(root, work_id, authority).state.linked_outputs),
        prompt="Execute the saved observation procedure",
    )
    result = core.read_work(root, work_id, authority)
    assert result.state.acceptance is None and result.state.linked_outputs
    expected_root = working if procedure_project == "personal" else external
    assert (expected_root / "procedure-root-proof.txt").read_text(encoding="utf-8") == (
        "Fictional configured procedure — exact working directory"
    )
    other_root = external if procedure_project == "personal" else working
    assert not (other_root / "procedure-root-proof.txt").exists()
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

    # An ordinary selected Work uses the same typed publication schema. The raw
    # responses mirror the observed object-result / invented-kind failure, without
    # repairing or interpreting the provider's text in the product.
    ordinary_work, ordinary_entry = uuid4(), uuid4()
    ordinary_state = core.WorkState(
        activity_id=activity,
        goal="Save one supplied dated observation and publish its exact result",
        inputs=result.state.inputs,
        structure=result.state.structure,
        expected_outputs=(
            core.OutputContract(
                slot="result", media_type="application/json", format_ref=format_ref
            ),
        ),
    )
    operation(core.CreateWorkRequest, work_id=ordinary_work, state=ordinary_state)
    bad_result = '{"entries":[],"complete":true,"result":{"value":"1.25"}}'
    bad_kind = '{"kind":"data_output_envelope","entries":[],"complete":true,"result":"Saved"}'
    good_result = (
        '{"contract_version":1,"entries":[{"record_id":"'
        + str(ordinary_entry)
        + '","revision":1}],"complete":true,"limitations":[],"result":"Observation saved"}'
    )

    def issues_in_last_tool(body: dict[str, Any]) -> list[dict[str, Any]]:
        tools = [message for message in body["messages"] if message["role"] == "tool"]
        text = str(tools[-1]["content"])
        marker = text.index('{"validation_issues":')
        return cast(
            list[dict[str, Any]],
            json.JSONDecoder().raw_decode(text[marker:])[0]["validation_issues"],
        )

    def ordinary_step(index: int, body: dict[str, Any]) -> dict[str, Any]:
        incoming = context(body)
        assert incoming["work"]["work_id"] == str(ordinary_work)
        actual_schema = incoming["output_publication_contracts"][0]["content_schema"]
        assert actual_schema == core.DataOutputEnvelope.model_json_schema()
        assert actual_schema["properties"]["result"]["type"] == "string"
        if index == 0:
            return {
                "_tool": "zara_data",
                "mode": "apply",
                "operation": "create_entry",
                "arguments": {
                    "record_id": str(ordinary_entry),
                    "state": {
                        "kind": "data_entry",
                        "role": "event",
                        "format_ref": format_ref.model_dump(mode="json"),
                        "values": {"day": "2026-01-05", "value": "1.25"},
                        "bases": [
                            {
                                "record_id": str(ordinary_state.inputs[0].artifact_id),
                                "revision": ordinary_state.inputs[0].revision,
                            }
                        ],
                    },
                },
            }
        if index in (1, 3, 5):
            if index in (3, 5):
                issues = issues_in_last_tool(body)
                assert any(
                    item["code"] == ("string_type" if index == 3 else "extra_forbidden")
                    and item["path"] == (["result"] if index == 3 else ["kind"])
                    for item in issues
                )
                if index == 5:
                    assert not any(item["path"] == ["result"] for item in issues)
            return {"_tool": "zara_result", "mode": "contract", "slot": "result"}
        if index in (2, 4, 6):
            tools = [message for message in body["messages"] if message["role"] == "tool"]
            supplied = json.loads(tools[-1]["content"])["contract"]["content_schema"]
            assert supplied == actual_schema
            return {
                "_tool": "zara_result",
                "mode": "publish",
                "slot": "result",
                "content_text": bad_result
                if index == 2
                else bad_kind
                if index == 4
                else good_result,
            }
        return {"_final_text": "The actual observation result is saved; acceptance is separate"}

    ordinary = native.Provider(
        [lambda body, index=index: ordinary_step(index, body) for index in range(8)]
    )
    run(
        ordinary,
        work=(activity, ordinary_work),
        expected_provider_calls=8,
        expected_tool_errors=2,
        prompt="Record 5 January: observed value 1.25; save the result",
    )
    ordinary_saved = core.read_execution(root, ordinary_work, authority)
    assert ordinary_saved.work.state.acceptance is None
    assert ordinary_saved.work.state.inputs == ordinary_state.inputs
    assert len(ordinary_saved.outputs) == 1
    assert ordinary_saved.outputs[0].content == good_result.encode("utf-8")
    assert any(
        attempt.status == "completed"
        and any(
            ref.relation == "produced_by_attempt"
            and ref.external_ref == f"attempt:{attempt.attempt_id}"
            for ref in ordinary_saved.outputs[0].provenance
        )
        for attempt in ordinary_saved.attempts
    )

    repeated_work = uuid4()
    operation(core.CreateWorkRequest, work_id=repeated_work, state=ordinary_state)
    repeated_publication = native.Provider(
        [
            {
                "_tool": "zara_result",
                "mode": "publish",
                "slot": "result",
                "content_text": bad_result,
            },
            {"_tool": "zara_data", "mode": "contract", "operation": "query_entries"},
            {
                "_tool": "zara_result",
                "mode": "publish",
                "slot": "result",
                "content_text": '{"kind":"data_result",' + bad_result[1:],
            },
        ]
    )
    run(
        repeated_publication,
        work=(activity, repeated_work),
        expected_provider_calls=3,
        expected_repeated_tool_failure=True,
        prompt="Exercise the exact repeated publication failure across an unrelated contract read",
    )
    failed_publication = core.read_execution(root, repeated_work, authority)
    assert not failed_publication.work.state.linked_outputs
    assert failed_publication.work.state.acceptance is None
    assert not failed_publication.assignments
    assert len(failed_publication.attempts) == 1
    failed_attempt = failed_publication.attempts[0]
    assert failed_attempt.status == "active"
    assert len(failed_publication.invocations) == 3
    assert all(item.status == "answered" for item in failed_publication.invocations)
    assert len(repeated_publication.requests) == 3
    # Native Pi is now closed. The fixture owner explicitly interrupts this
    # exact failed execution; no successful final or no-send cleanup is invented.
    operation(
        core.StopAttemptRequest,
        work_id=repeated_work,
        attempt_id=failed_attempt.attempt_id,
        session_id=failed_attempt.session_id,
        outcome="interrupted",
    )
    stopped_publication = core.read_execution(root, repeated_work, authority)
    assert stopped_publication.attempts[0].status == "interrupted"
    assert stopped_publication.invocations == failed_publication.invocations
    assert stopped_publication.committed_units == failed_publication.committed_units
    assert stopped_publication.held_units == failed_publication.held_units
    assert stopped_publication.work == failed_publication.work
    reopened_result = native.Provider([{"_final_text": "Read the preserved ordinary result"}])
    run(reopened_result, work=(activity, ordinary_work), expected_provider_calls=1)
    assert core.read_work(root, ordinary_work, authority) == ordinary_saved.work
    assert (
        core.read_artifact(root, ordinary_saved.outputs[0].artifact_id, authority)
        == ordinary_saved.outputs[0]
    )
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
    missing_a, missing_b = uuid4(), uuid4()
    different_errors = native.Provider(
        [
            {"mode": "open", "record_id": str(missing_a), "revision": 1},
            {"mode": "open", "record_id": str(missing_b), "revision": 1},
            {"_final_text": "Two different addresses are absent; this is not a repeated call"},
        ]
    )
    run(
        different_errors,
        expected_provider_calls=3,
        expected_tool_errors=2,
        prompt="Inspect two fictional missing addresses and report the exact obstacles",
    )
    repeated_error = native.Provider(
        [
            {"mode": "open", "record_id": str(missing_b), "revision": 1},
            {"mode": "open", "record_id": str(missing_b), "revision": 1},
        ]
    )
    run(
        repeated_error,
        expected_repeated_tool_failure=True,
        prompt="Repeat the same fictional missing address only to test the stop guard",
    )
    assert all("ZARA_MANIFEST:" in json.dumps(body) for body in requests)
    # Read the fictional ledger independently of provider callbacks; never modify it.
    ledger_path = root / ".zara-core" / "core.sqlite3"
    with sqlite3.connect(f"{ledger_path.as_uri()}?mode=ro", uri=True) as connection:
        invocation_ids = [
            UUID(row[0])
            for row in connection.execute("SELECT invocation_id FROM knowledge_delivery")
        ]
    deliveries = [core.read_context_delivery(root, item, authority) for item in invocation_ids]
    assert len(deliveries) == len(requests), (len(deliveries), len(requests))
    assert all(item["stage"] == "answered" for item in deliveries), deliveries
    report = {
        "schema": core.read_space(root).schema_version,
        "workspace_config_version": 2,
        "procedure_project": procedure_project,
        "procedure_single_resource": True,
        "native_procedure_file_root_verified": True,
        "upgrade_from_schema": 15,
        "pi_version": actual.version,
        "review_passes": reviews,
        "raw_result_repairs": 2,
        "successive_user_questions": 2,
        "clarification_preserved_wait": True,
        "question_answered_in_new_pi": True,
        "different_missing_addresses_do_not_abort": True,
        "same_failed_operation_stops": True,
        "blank_response_retained": blank_response,
        "native_stage_terminal_proofs": len(terminal_proofs),
        "native_stage_protocol_bytes_and_order": terminal_proof,
        "typed_work": str(work_id),
        "typed_entry": str(entry_id),
        "activity_id": str(activity),
        "setup_id": str(setup_id),
        "legacy_history_preserved": True,
        "compact_requests": 2,
        "synthetic_http": len(requests),
        "accounted_sends": len(deliveries),
        "real_model_calls": 0,
        "paid_api_calls": 0,
        "work_accepted": False,
        "ordinary_typed_work": str(ordinary_work),
        "ordinary_output_schema_in_actual_requests": True,
        "ordinary_field_diagnostics_delivered": True,
        "different_publication_cause_can_be_corrected": True,
        "repeated_publication_cause_stops_across_contract_read": True,
        "ordinary_output_preserved_after_reopen": True,
        "module": str(Path(core.__file__).resolve()),
    }
    (directory / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def run_pause_inputs_probe(directory: Path, runtime: Path) -> dict[str, Any]:
    """Actual in-flight stop, new originals, explicit replacement and whole review."""
    from zaratustra.pi_adapter import prepare_space
    from zaratustra.pi_adapter.activity_setup import INSTRUCTIONS

    directory.mkdir(parents=True, exist_ok=False)
    root, working = directory / "space", directory / "work"
    root.mkdir()
    working.mkdir()
    owner = prepare_space(root, "owner", create=True)
    native, actual = harness(), read_pi_runtime(runtime)
    setup_id, activity_id = uuid4(), uuid4()

    def operation(model: Any, **fields: Any) -> Any:
        return core.apply_operation(
            root,
            model(operation_id=uuid4(), space_id=owner.space_id, actor="owner", **fields),
            owner,
        )

    def step(action: str, **fields: Any) -> None:
        current = core.read_activity_setup(root, setup_id, owner)
        operation(
            core.ActivitySetupRequest,
            setup_id=setup_id,
            activity_id=activity_id,
            expected_revision=current.revision,
            action=action,
            **fields,
        )

    def retain_result(text: str) -> core.ArtifactRef:
        stage = core.read_activity_setup(root, setup_id, owner).state.stages[-1]
        identifier = uuid4()
        reference = core.ArtifactRef(artifact_id=identifier, revision=1)
        operation(
            core.CreateArtifactRequest,
            artifact_id=identifier,
            media_type="text/plain",
            content=text.encode("utf-8"),
        )
        work = core.read_work(root, stage.work_id, owner)
        operation(
            core.LinkWorkOutputRequest,
            work_id=stage.work_id,
            expected_revision=work.revision,
            output=core.LinkedOutput(slot="report", artifact=reference),
        )
        step("complete_stage", output=reference)
        return reference

    operation(
        core.ActivitySetupRequest,
        action="begin",
        setup_id=setup_id,
        activity_id=activity_id,
        title="Fictional observations",
        contract_version=2,
        text="Keep supplied observations and review their period",
    )
    step("start_stage", stage_kind="draft", stage_instruction=INSTRUCTIONS["draft"])
    original_draft = retain_result(draft("week").model_dump_json())
    step("start_stage", stage_kind="review", stage_instruction=INSTRUCTIONS["review"])

    def report_for(state: Any, blocking: bool) -> core.ActivitySetupReviewV2:
        return core.ActivitySetupReviewV2(
            draft=state.draft,
            manifest=state.manifest,
            input_version=state.input_version,
            checked=AREAS,
            coverage=tuple(
                core.SetupAreaEvidence(
                    area=area,
                    explanation="Checked the complete current dated intake and first path",
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
                    problem="Clarify the event date",
                    cause="The process needs a correction",
                    blocking=True,
                ),
            )
            if blocking
            else (),
            conclusion="Correct the whole process" if blocking else "No blocking obstacle",
        )

    retain_result(
        report_for(core.read_activity_setup(root, setup_id, owner).state, True).model_dump_json()
    )
    step("start_stage", stage_kind="correction", stage_instruction=INSTRUCTIONS["correction"])
    original_stage = core.read_activity_setup(root, setup_id, owner).state.stages[-1]
    supplemental_text = (
        "Use the selected fictional research; preserve event dates. Новые пожелания."
    )
    original_file = "# Fictional research\nExact original: разные даты и UTF-8.\n".encode()
    (working / "research.md").write_bytes(original_file)
    barrier = threading.Event()
    release = threading.Event()
    packets: list[dict[str, Any]] = []
    old_request_seen = False
    outer_calls = 0
    review_calls = 0
    selected_source: dict[str, Any] | None = None
    bridge: Bridge
    config: AssignedConfig

    def route(body: dict[str, Any]) -> dict[str, Any]:
        nonlocal old_request_seen, outer_calls, review_calls, selected_source
        manifest = context(body)
        if "work" in manifest:
            incoming = json.loads(manifest["inputs"][0]["content_text"])
            if not old_request_seen:
                old_request_seen = True
                assert incoming["input_version"] == original_stage.input_version
                barrier.set()
                assert release.wait(40), "The ordinary pause must reach its next tool response"
                return {"_final_text": incoming["draft"] and json.dumps(incoming["draft"])}
            packets.append(incoming)
            assert incoming["input_version"] > original_stage.input_version
            originals = [item["state"]["text"] for item in incoming["sources"]]
            assert supplemental_text in originals
            assert original_file.decode() in originals
            assert "working_set" in {item["operation"] for item in incoming["supported_operations"]}
            if incoming["result_schema"]["title"] == "ActivitySetupReviewV2":
                review_calls += 1
                current = core.read_activity_setup(root, setup_id, owner).state
                assert current.draft is not None and current.manifest is not None
                assert incoming["draft_ref"] == current.draft.model_dump(mode="json")
                assert incoming["manifest_ref"] == current.manifest.model_dump(mode="json")
                return {"_final_text": report_for(current, False).model_dump_json()}
            return {"_final_text": draft("week").model_dump_json()}
        count = outer_calls
        outer_calls += 1
        if count == 0:
            assert bridge.setup_controller is not None
            bridge.setup_controller.start(
                setup_id,
                {"id": "fictional-model", "provider": "fictional-local", "thinking": "off"},
            )
            assert barrier.wait(40), "The correction must actually send before pause"
            return {
                "_tool": "zara_activity",
                "mode": "retain_file",
                "setup_id": str(setup_id),
                "path": "research.md",
            }
        if selected_source is None:
            tools = [item for item in body["messages"] if item["role"] == "tool"]
            selected_source = json.loads(tools[0]["content"])["selected_source"]
        if count in (1, 3):
            if count == 3:
                release.set()
            return {
                "_tool": "zara_activity",
                "mode": "attach_sources",
                "setup_id": str(setup_id),
                "source_refs": [selected_source],
            }
        if count == 2:
            return {"_tool": "zara_activity", "mode": "pause", "setup_id": str(setup_id)}
        if count == 4:
            paused = core.read_activity_setup(root, setup_id, owner)
            assert (
                paused.state.phase == "paused"
                and paused.state.input_version > original_stage.input_version
            )
            assert not paused.state.stages[-1].retired
            interrupted = core.read_execution(root, original_stage.work_id, owner)
            assert interrupted.assignments[-1].status == "stopped"
            assert interrupted.invocations[-1].status == "unknown"
            assert not interrupted.outputs
            return {"_tool": "zara_activity", "mode": "status", "setup_id": str(setup_id)}
        if count == 5:
            return {"_tool": "zara_activity", "mode": "retry", "setup_id": str(setup_id)}
        return {
            "_final_text": "New originals are retained; explicit replacement runs "
            "a fresh full preparation and review."
        }

    provider = native.Provider([route] * 10)
    bridge = Bridge(root, owner, working)
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
    bridge.workflow_controller = WorkflowCoordinator(bridge, config)
    try:
        events = native.run_process(
            working,
            runtime,
            bridge,
            provider,
            prompt=supplemental_text,
            skills=(activity_setup_skill(),),
            tool_names=("read", "write", "edit", "bash", *INTERACTIVE_ZARA_TOOLS),
            confirmation_answers=(True,),
            expected_tool_errors=1,
            expected_provider_calls=10,
            wait_for=lambda: core.read_activity_setup(root, setup_id, owner).state.phase == "ready",
            timeout_seconds=180,
        )
    finally:
        release.set()
        bridge.workflow_controller.close()
    state = core.read_activity_setup(root, setup_id, owner).state
    assert state.phase == "ready" and state.stages[2].retired
    assert state.stages[0].output == original_draft
    assert review_calls == 1 and len(packets) == 2
    assert state.reviews_started == 2 and state.pass_boundary == 1
    assert not any("Одинаковая ошибка" in json.dumps(event, ensure_ascii=False) for event in events)
    interrupted = core.read_execution(root, original_stage.work_id, owner)
    assert len(interrupted.invocations) == 1 and interrupted.invocations[0].status == "unknown"
    assert not any(
        work.work.state.acceptance is not None
        for work in (
            core.read_execution(root, identifier, owner) for identifier in state.activated_works
        )
    )
    with sqlite3.connect(
        f"{core.read_space(root).database.as_uri()}?mode=ro", uri=True
    ) as connection:
        ids = [
            UUID(row[0])
            for row in connection.execute("SELECT invocation_id FROM knowledge_delivery")
        ]
    deliveries = [core.read_context_delivery(root, identifier, owner) for identifier in ids]
    assert len(ids) == len(provider.requests) == 10
    assert sum(item["stage"] == "unknown" for item in deliveries) == 1
    assert sum(item["stage"] == "answered" for item in deliveries) == 9
    assert all("ZARA_MANIFEST:" in json.dumps(body) for body in provider.requests)
    result = {
        "module": str(Path(core.__file__).resolve()),
        "schema": 16,
        "pi_version": actual.version,
        "actual_http": 10,
        "accounted_sends": len(ids),
        "unknown_outcomes_preserved": 1,
        "owner_confirmations": 1,
        "source_file_exact": True,
        "supplemental_owner_text_exact": True,
        "new_complete_packets": len(packets),
        "fresh_whole_reviews": review_calls,
        "same_activity_identity": True,
        "automatic_acceptance": False,
        "real_model_calls": 0,
        "paid_api_calls": 0,
    }
    (directory / "report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--pi-runtime", type=Path, required=True)
    parser.add_argument("--blank-response", action="store_true")
    parser.add_argument("--terminal-proof", action="store_true")
    parser.add_argument("--procedure-project", choices=("personal", "external"), default="personal")
    parser.add_argument("--pause-inputs", action="store_true")
    args = parser.parse_args()
    if args.pause_inputs:
        print(
            json.dumps(
                run_pause_inputs_probe(args.directory.resolve(), args.pi_runtime.resolve()),
                indent=2,
            )
        )
        return
    print(
        json.dumps(
            run_probe(
                args.directory.resolve(),
                args.pi_runtime.resolve(),
                blank_response=args.blank_response,
                terminal_proof=args.terminal_proof,
                procedure_project=args.procedure_project,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
