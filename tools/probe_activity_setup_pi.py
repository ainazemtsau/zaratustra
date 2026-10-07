"""Fictional Activity setup through ordinary Pi, assigned DBOS and localhost only."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from pydantic import TypeAdapter

import zaratustra.foundation as core
from zaratustra.pi_adapter import (
    Bridge,
    complete_assigned_deletions,
    create_assigned_backup,
    read_pi_runtime,
)
from zaratustra.pi_adapter.activity_setup import SetupCoordinator
from zaratustra.pi_adapter.assigned import AssignedConfig
from zaratustra.pi_adapter.skills import activity_setup_skill


def harness() -> Any:
    specification = importlib.util.spec_from_file_location(
        "activity_pi_harness", Path(__file__).with_name("probe_knowledge_pi.py")
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def context(body: dict[str, Any]) -> dict[str, Any]:
    text = str(body["messages"][0]["content"])
    marker = text.rfind("ZARA_MANIFEST:")
    assert marker >= 0, "Actual HTTP lacks the mandatory manifest"
    start = text.index("{", marker)
    return cast(dict[str, Any], json.JSONDecoder().raw_decode(text[start:])[0])


def fictional_draft(activity: UUID) -> core.ActivitySetupDraft:
    output = core.OutputContract(slot="report", media_type="text/plain")
    definition = core.MethodDefinition(
        instruction="Retain originals and publish a weekly summary",
        named_outputs=(output,),
        obligations=(
            core.MethodObligation(
                key="summary",
                source="fictional:setup",
                role="prepare",
                slot="report",
                media_type="text/plain",
            ),
        ),
        source_ref="fictional:setup",
    )
    plan = core.WorkPlan(
        children=(
            core.PlanChild(
                role="prepare",
                work_id=uuid4(),
                state=core.WorkState(
                    activity_id=activity,
                    goal="Prepare the weekly summary",
                    expected_outputs=(output,),
                ),
            ),
        ),
        output_bindings=(
            core.PlanOutputBinding(
                parent_slot="report", role="prepare", child_slot="report", media_type="text/plain"
            ),
        ),
        completion=core.PlanCondition(kind="work_succeeded", role="prepare"),
        rationale="First weekly summary",
        source_ref="fictional:setup",
    )
    return core.ActivitySetupDraft(
        title="Fictional workshop",
        goal="Keep notes and revise summaries",
        instructions=(
            "Keep original notes, distinguish evidence from conclusions; improve through Sleep"
        ),
        methods=(core.SetupMethodTemplate(key="weekly", definition=definition),),
        works=(
            core.SetupWorkTemplate(
                key="first_note", goal="Retain the first fictional note", expected_outputs=(output,)
            ),
            core.SetupWorkTemplate(
                key="weekly", goal="Prepare weekly summary", method_key="weekly", plan=plan
            ),
        ),
        extensions=("Later support another input source",),
        first_action="Bring the first project note",
    )


def run_probe(directory: Path, runtime: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=False)
    root, working = directory / "space", directory / "work"
    root.mkdir()
    working.mkdir()
    info = core.initialize_space(root)
    authority = core.authorize_local(root, actor="owner", source_ref="fictional-activity-setup")
    adapter: TypeAdapter[core.DomainRequest] = TypeAdapter(core.DomainRequest)

    def operation(kind: str, **fields: Any) -> Any:
        return core.apply_operation(
            root,
            adapter.validate_python(
                {
                    "kind": kind,
                    "space_id": info.space_id,
                    "actor": "owner",
                    "operation_id": uuid4(),
                    **fields,
                }
            ),
            authority,
        )

    operation("bootstrap", decision_id=uuid4(), grant_id=uuid4())
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
        if upgrade is core.upgrade_activity_setup_space:
            assert core.read_space(root).schema_version == 13
            old_artifact = uuid4()
            operation(
                "create_artifact",
                artifact_id=old_artifact,
                media_type="text/plain",
                content=b"Fictional schema 13 original",
            )
            assert core.read_space(root).schema_version == 13
        upgrade(root, authority)
    assert (
        core.read_artifact(root, old_artifact, authority).content == b"Fictional schema 13 original"
    )
    native = harness()
    actual = read_pi_runtime(runtime)
    requests: list[dict[str, Any]] = []

    def bridge_for(provider: Any) -> Bridge:
        bridge = Bridge(root, authority, working, None)
        bridge.setup_controller = SetupCoordinator(
            bridge,
            AssignedConfig(
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
            ),
        )
        return bridge

    first = native.Provider(
        [
            {
                "_tool": "zara_activity",
                "mode": "create",
                "title": "Fictional workshop",
                "goal": "Keep project notes and prepare summaries",
            },
            lambda _body: {
                "_tool": "zara_activity",
                "mode": "question",
                "setup_id": str(core.list_activity_setups(root, authority)[0].setup_id),
                "question": "How do you normally bring your project notes?",
            },
        ]
    )
    native.run_process(
        working,
        runtime,
        bridge_for(first),
        first,
        confirmation_answers=(True,),
        skills=(activity_setup_skill(),),
        expected_provider_calls=3,
        prompt="Create a fictional workshop Activity for notes and summaries",
    )
    requests.extend(first.requests)
    setup = core.list_activity_setups(root, authority)[0]
    identifier = setup.setup_id
    assert setup.state.phase == "needs_input"
    reviews = 0
    seen_packets: list[dict[str, Any]] = []

    def route(body: dict[str, Any]) -> dict[str, Any]:
        nonlocal reviews
        packet = context(body)
        if "work" in packet:
            assert not body.get("tools"), "Setup stages must not expose model tools"
            input_packet = json.loads(packet["inputs"][0]["content_text"])
            seen_packets.append(input_packet)
            assert input_packet["sources"] and input_packet["result_schema"]
            kind = input_packet["result_schema"]["title"]
            if kind == "ActivitySetupReview":
                reviews += 1
                report = core.ActivitySetupReview(
                    draft=core.ArtifactRef.model_validate(input_packet["draft_ref"]),
                    input_version=input_packet["input_version"],
                    checked=(
                        "goal",
                        "workflow",
                        "history",
                        "continuation",
                        "extension",
                        "capabilities",
                        "consistency",
                    ),
                    findings=(
                        core.SetupFinding(
                            area="history",
                            problem="Event and import dates are conflated",
                            cause="The original intake rule does not distinguish these dates",
                            blocking=True,
                        ),
                    )
                    if reviews == 1
                    else (),
                    conclusion="Correct the intake rule"
                    if reviews == 1
                    else "No material obstacle",
                )
                if reviews == 2:
                    assert "event date and import date" in input_packet["draft"]["instructions"]
                    assert input_packet["draft"]["works"] and input_packet["draft"]["methods"]
                result = report.model_dump_json()
            elif "draft" in input_packet:
                changed = core.ActivitySetupDraft.model_validate(input_packet["draft"])
                changed = changed.model_copy(
                    update={
                        "instructions": changed.instructions
                        + "; keep event date and import date separately"
                    }
                )
                result = changed.model_dump_json()
            else:
                result = fictional_draft(UUID(input_packet["activity_id"])).model_dump_json()
            return {"_final_text": json.dumps({"zara": "final", "text": result})}
        tools = [message for message in body["messages"] if message["role"] == "tool"]
        if not tools:
            assert packet["activity_setup"]["setup_id"] == str(identifier)
            assert (
                packet["activity_setup"]["question"]
                == "How do you normally bring your project notes?"
            )
            return {"_tool": "zara_activity", "mode": "answer", "setup_id": str(identifier)}
        if len(tools) == 1:
            return {"_tool": "zara_activity", "mode": "submit", "setup_id": str(identifier)}
        return {"_final_text": "The fictional setup is running"}

    second = native.Provider([route] * 32)

    def done() -> bool:
        try:
            return core.read_activity_setup(root, identifier, authority).state.phase in (
                "ready",
                "needs_attention",
            )
        except core.FoundationError as error:
            if error.code in ("busy", "storage") and "locked" in str(error):
                return False
            raise

    native.run_process(
        working,
        runtime,
        bridge_for(second),
        second,
        skills=(activity_setup_skill(),),
        wait_for=done,
        expected_provider_calls=7,
        prompt=(
            "One original text note per day; preserve previous versions and distinguish event dates"
        ),
    )
    requests.extend(second.requests)
    final = core.read_activity_setup(root, identifier, authority)
    assert final.state.phase == "ready", final.model_dump_json(indent=2)
    assert final.state.reviews_started == final.state.reviews_completed == 2
    assert len(seen_packets) == 4
    assert len(final.state.activated_methods) == 1
    assert all(
        core.read_work(root, work, authority).state.acceptance is None
        for work in final.state.activated_works
    )

    third = native.Provider(
        [{"_tool": "zara_activity", "mode": "status", "setup_id": str(identifier)}]
    )
    native.run_process(
        working,
        runtime,
        Bridge(root, authority, working),
        third,
        compact=True,
        expected_provider_calls=4,
    )
    requests.extend(third.requests)
    first_work = final.state.activated_works[0]
    fourth = native.Provider(
        [
            {
                "_tool": "zara_result",
                "mode": "publish",
                "content_text": "Fictional note retained with its event date and original version",
            }
        ]
    )
    native.run_process(
        working,
        runtime,
        Bridge(root, authority, working),
        fourth,
        work=(final.state.activity_id, first_work),
    )
    requests.extend(fourth.requests)
    retained = core.read_work(root, first_work, authority)
    assert retained.state.acceptance is None and retained.state.linked_outputs
    fifth = native.Provider([{"_tool": "zara_result", "mode": "read"}])
    native.run_process(
        working,
        runtime,
        Bridge(root, authority, working),
        fifth,
        work=(final.state.activity_id, first_work),
    )
    requests.extend(fifth.requests)
    assert all("ZARA_MANIFEST:" in json.dumps(body) for body in requests)
    usage = [
        item
        for stage in final.state.stages
        for item in core.read_execution(root, stage.work_id, authority).invocations
    ]
    assert len(usage) == 4 and all(item.status == "answered" for item in usage)
    backup = create_assigned_backup(root, uuid4(), authority, pi_version=actual.version)
    operation("delete_knowledge", record_id=final.state.sources[0].record_id, expected_revision=1)
    assert complete_assigned_deletions(root, authority).live_store_sanitized
    assert not backup.package.exists()
    report = {
        "schema": core.read_space(root).schema_version,
        "upgrade_from": 13,
        "schema13_original_preserved": True,
        "deletion_and_technical_purge": True,
        "setup_id": str(identifier),
        "activity_id": str(final.state.activity_id),
        "works": [str(work) for work in final.state.activated_works],
        "review_passes": 2,
        "assigned_http": len(usage),
        "all_synthetic_http": len(requests),
        "real_model_calls": 0,
        "paid_api_calls": 0,
        "work_accepted": False,
        "module": str(Path(core.__file__).resolve()),
        "state": final.model_dump(mode="json"),
    }
    (directory / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--pi-runtime", type=Path, required=True)
    args = parser.parse_args()
    report = run_probe(args.directory.resolve(), args.pi_runtime.resolve())
    print(json.dumps({key: value for key, value in report.items() if key != "state"}, indent=2))


if __name__ == "__main__":
    main()
