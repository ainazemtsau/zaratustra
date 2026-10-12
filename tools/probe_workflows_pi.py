"""Ordinary Pi/DBOS workflow probe: parallel nodes and addressed resumed questions."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

import zaratustra.foundation as core
from zaratustra.pi_adapter import Bridge, read_pi_runtime
from zaratustra.pi_adapter.__main__ import INTERACTIVE_ZARA_TOOLS
from zaratustra.pi_adapter.assigned import AssignedConfig
from zaratustra.pi_adapter.workflows import WorkflowCoordinator
from zaratustra.workspace import LaunchConfig, Project, write_config

from .probe_activity_setup_pi import context, harness


def project_read_probe(directory: Path, runtime: Path) -> dict[str, Any]:
    """Configured native project reads refuse an unselected neighboring file."""
    from tests.zaratustra.foundation.test_workflows import (
        _adopt_workflow,
        _op,
        _owner_source,
        _setup,
    )

    directory.mkdir(parents=True, exist_ok=False)
    case = _setup(
        directory, (core.WorkflowNode(key="seed", kind="model", instruction="Keep seed"),)
    )
    root, space, owner, activity, _, _ = case
    source = _owner_source(case, b"Inspect the explicitly registered fictional project")
    definition = core.WorkflowDefinition(
        title="Scoped project check",
        purpose="Read the selected project's files",
        entry_nodes=("inspect",),
        allowed_action_classes=("core_read", "project_read"),
        nodes=(
            core.WorkflowNode(
                key="inspect",
                kind="model",
                instruction="Inspect project evidence",
                resource="project",
                project="fictional",
                allowed_actions=("core_read", "project_read"),
            ),
        ),
    )
    ref = _adopt_workflow(root, space, owner, activity, source, definition)
    identifier = uuid4()
    _op(
        root,
        space,
        owner,
        core.WorkflowRequest,
        action="start",
        root_work_id=identifier,
        workflow=ref,
        activity_id=activity,
        source_refs=(source,),
    )
    personal, project, runtime_root = (
        directory / name for name in ("personal", "project", "runtime")
    )
    for path in (personal, project, runtime_root):
        path.mkdir()
    outside = directory / "unselected.txt"
    outside.write_text("Fictional unread neighboring content", encoding="utf-8")
    actual, native = read_pi_runtime(runtime), harness()
    provider_calls = 0
    blocked = False

    def reply(body: dict[str, Any]) -> dict[str, Any]:
        nonlocal provider_calls, blocked
        packet = context(body)
        if "work" not in packet:
            provider_calls += 1
            return (
                {"_tool": "zara_workflow", "mode": "resume", "root_work_id": str(identifier)}
                if provider_calls == 1
                else {"_final_text": "The scoped check is proposed."}
            )
        tools = [message for message in body["messages"] if message["role"] == "tool"]
        if not tools:
            return {"_tool": "read", "path": str(outside)}
        diagnostic = str(tools[-1]["content"])
        assert "selected" in diagnostic.lower() or "outside" in diagnostic.lower()
        assert "Fictional unread neighboring content" not in diagnostic
        blocked = True
        return {"_final_text": '{"outcome":"result","values":{"outside_read":"refused"}}'}

    provider = native.Provider([reply] * 8)
    config_path = directory / "launch.json"
    config = LaunchConfig(
        version=2,
        actor=owner.actor,
        space_id=space,
        space=root,
        workspace=personal,
        personal_root=personal,
        runtime_root=runtime_root,
        projects=(Project(name="fictional", path=project),),
        sqlite_dll=Path(os.environ["ZARATUSTRA_SQLITE_DLL"]),
        pi_runtime=runtime,
        provider_profile="local-completions",
        provider_id="fictional-local",
        provider_base_url=f"http://127.0.0.1:{provider.server_port}/v1",
        model_id="fictional-model",
        reserve_units=1000,
    )
    write_config(config_path, config)
    bridge = Bridge(root, owner, personal, workspace_config=config_path)
    assigned = AssignedConfig(
        space=root,
        workspace=personal,
        workspace_config=config_path,
        pi_cli=actual.cli,
        pi_runtime=runtime,
        node=shutil.which("node") or "node",
        provider_profile=config.provider_profile,
        provider_id=config.provider_id,
        provider_base_url=config.provider_base_url,
        model_id=config.model_id,
        context_window=1000000,
        max_tokens=32768,
        reserve_units=1000,
        limit_units=None,
        offline=True,
    )
    bridge.workflow_controller = WorkflowCoordinator(bridge, assigned)
    try:
        native.run_process(
            personal,
            runtime,
            bridge,
            provider,
            prompt="Inspect the registered fictional project",
            expected_provider_calls=4,
            tool_names=("read", "write", "edit", "bash", *INTERACTIVE_ZARA_TOOLS),
            wait_for=lambda: bool(core.read_work(root, identifier, owner).state.linked_outputs),
        )
    finally:
        bridge.workflow_controller.close()
    state = core.read_workflow_run(root, identifier, owner)
    assert blocked and state.next_action == "closed"
    execution = core.read_execution(root, state.nodes[0].work_id, owner)
    assert (
        execution.resources[0].state.root == project
        and execution.resources[0].state.mode == "shared"
    )
    with sqlite3.connect(
        f"{(root / '.zara-core' / 'core.sqlite3').as_uri()}?mode=ro", uri=True
    ) as connection:
        deliveries = [
            core.read_context_delivery(root, UUID(row[0]), owner)
            for row in connection.execute("SELECT invocation_id FROM knowledge_delivery")
        ]
    assert len(deliveries) == len(provider.requests) == 4
    assert all(item["stage"] == "answered" for item in deliveries)
    result = {
        "http_requests": len(provider.requests),
        "accounted_sends": len(deliveries),
        "outside_project_read_refused": blocked,
        "registered_project_resource": True,
    }
    directory.joinpath("result.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    directory.joinpath("requests.json").write_text(
        json.dumps(provider.requests, indent=2) + "\n", encoding="utf-8"
    )
    return result


def method_wait_probe(directory: Path, runtime: Path) -> dict[str, Any]:
    """Run a real native Method question through close/reopen and owner acceptance."""
    from tests.zaratustra.foundation.test_workflows import _op
    from tests.zaratustra.pi_adapter.test_workflows import _method_case

    directory.mkdir(parents=True, exist_ok=False)
    with pytest.MonkeyPatch.context() as patch:
        case, node, base = _method_case(
            directory,
            patch,
            provider_id="fictional-local",
            model_id="fictional-model",
            reasoning="off",
        )
    root, space, owner, _, _, identifier = case
    actual, native = read_pi_runtime(runtime), harness()
    working = directory / "work"
    working.mkdir()
    observed: list[dict[str, Any]] = []
    assigned_packets: list[dict[str, Any]] = []

    def run(provider: Any, **options: Any) -> None:
        bridge = Bridge(root, owner, working)
        config = replace(
            base,
            pi_cli=actual.cli,
            pi_runtime=runtime,
            node=shutil.which("node") or "node",
            workspace=working,
            provider_id="fictional-local",
            model_id="fictional-model",
            provider_base_url=f"http://127.0.0.1:{provider.server_port}/v1",
            context_window=1000000,
            max_tokens=32768,
            reserve_units=1000,
            offline=True,
        )
        bridge.workflow_controller = WorkflowCoordinator(bridge, config)
        try:
            native.run_process(
                working,
                runtime,
                bridge,
                provider,
                tool_names=("read", "write", "edit", "bash", *INTERACTIVE_ZARA_TOOLS),
                **options,
            )
        finally:
            bridge.workflow_controller.close()
        observed.extend(provider.requests)

    first_calls = 0

    def first_reply(body: dict[str, Any]) -> dict[str, Any]:
        nonlocal first_calls
        packet = context(body)
        if "work" not in packet:
            first_calls += 1
            return (
                {"_tool": "zara_workflow", "mode": "resume", "root_work_id": str(identifier)}
                if first_calls == 1
                else {"_final_text": "The role has a saved question."}
            )
        assert packet["composition"]["role"] == "analyse"
        assigned_packets.append(packet)
        return {
            "_final_text": json.dumps(
                {
                    "zara": "wait",
                    "partial": "Original observations",
                    "question": "Which exact period should I analyse?",
                    "remainder": "Analyse the owner's chosen period",
                }
            )
        }

    first = native.Provider([first_reply] * 8)
    run(
        first,
        prompt="Continue the fictional Method review",
        expected_provider_calls=3,
        wait_for=lambda: bool(core.read_workflow_run(root, identifier, owner).waits),
    )
    wait = core.read_workflow_run(root, identifier, owner).waits[0]
    child = wait.work_id
    assert wait.native and core.read_execution(root, child, owner).waits[0].status == "closed"
    assert core.read_workflow_run(root, identifier, owner).control == "paused"
    second_calls = 0

    def second_reply(body: dict[str, Any]) -> dict[str, Any]:
        nonlocal second_calls
        packet = context(body)
        if "work" not in packet:
            second_calls += 1
            if second_calls == 1:
                return {
                    "_tool": "zara_workflow",
                    "mode": "answer",
                    "root_work_id": str(identifier),
                    "wait_id": str(wait.wait_id),
                    "expected_wait_revision": wait.revision,
                }
            if second_calls == 2:
                return {"_tool": "zara_workflow", "mode": "resume", "root_work_id": str(identifier)}
            return {"_final_text": "The native role result awaits your acceptance."}
        continuation = packet["workflow_continuation"]
        assert "previous complete month" in continuation["content_text"]
        assert continuation["partials"]
        assigned_packets.append(packet)
        return {"_final_text": '{"zara":"final","text":"Compared the chosen month"}'}

    second = native.Provider([second_reply] * 9)
    run(
        second,
        prompt="Compare the previous complete month and continue this saved process",
        expected_provider_calls=4,
        wait_for=lambda: bool(core.read_work(root, child, owner).state.linked_outputs),
    )
    assert core.read_work(root, child, owner).state.acceptance is None
    assert core.read_workflow_run(root, identifier, owner).next_action == "resume"
    execution = core.read_execution(root, child, owner)
    assert (
        len(execution.attempts) == 2
        and execution.attempts[-1].previous_attempt_id == execution.attempts[0].attempt_id
    )
    assert all(item.status == "answered" for item in execution.invocations)
    _op(
        root,
        space,
        owner,
        core.AcceptWorkRequest,
        work_id=child,
        expected_revision=core.read_work(root, child, owner).revision,
        basis="Fictional owner explicitly checked the native role",
    )
    last_calls = 0

    def last_reply(body: dict[str, Any]) -> dict[str, Any]:
        nonlocal last_calls
        packet = context(body)
        if "work" not in packet:
            last_calls += 1
            return (
                {"_tool": "zara_workflow", "mode": "resume", "root_work_id": str(identifier)}
                if last_calls == 1
                else {"_final_text": "The Method report is proposed."}
            )
        assert packet["work"]["work_id"] == str(node.work_id)
        assigned_packets.append(packet)
        return {"_final_text": '{"outcome":"result","values":{"report":"Reviewed month"}}'}

    last = native.Provider([last_reply] * 8)
    run(
        last,
        prompt="Continue after my explicit role acceptance",
        expected_provider_calls=3,
        wait_for=lambda: bool(core.read_work(root, identifier, owner).state.linked_outputs),
    )
    assert core.read_work(root, node.work_id, owner).state.acceptance is None
    assert core.read_work(root, identifier, owner).state.acceptance is None
    assert len(observed) == 10 and len(assigned_packets) == 3
    assert (
        sum(
            len(core.read_execution(root, work, owner).invocations)
            for work in (child, node.work_id)
        )
        == 3
    )
    for body in observed:
        assert "ZARA_MANIFEST:" in json.dumps(body)
    with sqlite3.connect(
        f"{(root / '.zara-core' / 'core.sqlite3').as_uri()}?mode=ro", uri=True
    ) as connection:
        deliveries = [
            core.read_context_delivery(root, UUID(row[0]), owner)
            for row in connection.execute("SELECT invocation_id FROM knowledge_delivery")
        ]
    assert len(deliveries) == len(observed) and all(
        item["stage"] == "answered" for item in deliveries
    )
    result = {
        "http_requests": len(observed),
        "accounted_sends": len(deliveries),
        "native_role_requests": 3,
        "closed_question_preserved": True,
        "new_attempt_has_exact_continuation": True,
        "root_report_after_owner_acceptance": True,
    }
    directory.joinpath("result.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    directory.joinpath("requests.json").write_text(
        json.dumps(observed, indent=2) + "\n", encoding="utf-8"
    )
    return result


def run_probe(directory: Path, runtime: Path) -> dict[str, Any]:
    from tests.zaratustra.foundation.test_workflows import _op, _setup

    directory.mkdir(parents=True, exist_ok=False)
    case = _setup(
        directory,
        (
            core.WorkflowNode(
                key="route",
                kind="model",
                instruction="Choose both independent checks",
                successors=("left", "right"),
            ),
            core.WorkflowNode(
                key="left", kind="model", instruction="Check originals", dependencies=("route",)
            ),
            core.WorkflowNode(
                key="right",
                kind="model",
                instruction="Check dates",
                dependencies=("route",),
                successors=("join",),
            ),
            core.WorkflowNode(
                key="join",
                kind="model",
                instruction="Integrate both exact checks",
                dependencies=("left", "right"),
            ),
        ),
    )
    root, space, owner, activity, _, identifier = case
    working = directory / "work"
    working.mkdir()
    native, actual = harness(), read_pi_runtime(runtime)
    observed: list[dict[str, Any]] = []
    assigned_packets: dict[str, dict[str, Any]] = {}
    right_received = threading.Event()

    def bridge_for(provider: Any) -> Bridge:
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
        )
        bridge.workflow_controller = WorkflowCoordinator(bridge, config)
        return bridge

    def run(provider: Any, **options: Any) -> None:
        bridge = bridge_for(provider)
        try:
            native.run_process(
                working,
                runtime,
                bridge,
                provider,
                tool_names=("read", "write", "edit", "bash", *INTERACTIVE_ZARA_TOOLS),
                **options,
            )
        finally:
            bridge.workflow_controller.close()
        observed.extend(provider.requests)

    main_calls = 0

    def parallel_route(body: dict[str, Any]) -> dict[str, Any]:
        nonlocal main_calls
        packet = context(body)
        if "work" not in packet:
            main_calls += 1
            return (
                {"_tool": "zara_workflow", "mode": "resume", "root_work_id": str(identifier)}
                if main_calls == 1
                else {"_final_text": "The saved workflow is running."}
            )
        exact = json.loads(packet["inputs"][0]["content_text"])
        key = exact["node"]["key"]
        assert exact["sources"] and exact["result_schema"]["title"] == "WorkflowNodeResult"
        assert body["model"] == "fictional-model"
        assert {tool["function"]["name"] for tool in body.get("tools", [])} <= {
            "zara_workflow",
            "zara_memory",
        }
        assigned_packets[key] = exact
        if key == "left":
            assert right_received.wait(30), (
                "Independent right request could not run while left waited"
            )
        if key == "right":
            right_received.set()
        if key == "join":
            assert {dependency["node"] for dependency in exact["dependencies"]} == {"left", "right"}
        next_nodes = ["left", "right"] if key == "route" else ["join"] if key == "right" else []
        return {
            "_final_text": json.dumps(
                {"outcome": "result", "values": {"checked": key}, "next_nodes": next_nodes}
            )
        }

    parallel = native.Provider([parallel_route] * 20)
    run(
        parallel,
        prompt="Continue the fictional review with both independent checks",
        expected_provider_calls=6,
        wait_for=lambda: bool(core.read_work(root, identifier, owner).state.linked_outputs),
    )
    assert set(assigned_packets) == {"route", "left", "right", "join"}
    final = core.read_work(root, identifier, owner)
    assert final.state.acceptance is None
    proof = core.read_parent_output_proof(
        root, final.state.linked_outputs[0].artifact.artifact_id, owner
    )
    assert proof is not None and proof.work_id == identifier

    candidate = core.list_development(root, owner, kind="candidate")[0].state
    assert isinstance(candidate, core.ChangeCandidateState)
    question_definition = core.WorkflowDefinition(
        title="Fictional period choice",
        purpose="Ask which observations to compare",
        entry_nodes=("period",),
        nodes=(
            core.WorkflowNode(
                key="period", kind="question", instruction="Which period should be compared?"
            ),
        ),
    )
    workflow_id = uuid4()
    proposed = _op(
        root,
        space,
        owner,
        core.WorkflowRequest,
        action="create_definition",
        workflow_id=workflow_id,
        definition=question_definition,
    )
    reference = core.WorkflowRef.model_validate(proposed.result["workflow"])
    candidate_id, decision_id, result_id = uuid4(), uuid4(), uuid4()
    proposal = candidate.model_copy(
        update={
            "target": core.WorkflowChange(
                workflow_id=workflow_id, to_version=1, definition=question_definition
            ),
            "results": tuple(
                result.model_copy(update={"result_id": result_id}) for result in candidate.results
            ),
        }
    )
    _op(root, space, owner, core.CreateDevelopmentRequest, record_id=candidate_id, state=proposal)
    _op(
        root,
        space,
        owner,
        core.CreateDecisionRequest,
        decision_id=decision_id,
        state=core.ChangeDecisionState(
            statement="Adopt the fictional question workflow",
            candidate_id=candidate_id,
            candidate_revision=1,
            mode="regular",
            use="recommended",
            scope_activity_id=activity,
            validation_result_ids=(result_id,),
            review_condition="Observe use",
        ),
    )
    _op(
        root,
        space,
        owner,
        core.ApplyCandidateRequest,
        candidate_id=candidate_id,
        candidate_revision=1,
        decision_id=decision_id,
        decision_revision=1,
        mode="regular",
    )
    first, second = uuid4(), uuid4()
    for pending in (first, second):
        _op(
            root,
            space,
            owner,
            core.WorkflowRequest,
            action="start",
            workflow=reference,
            root_work_id=pending,
            activity_id=activity,
            source_refs=proposal.evidence,
        )
        state = core.read_workflow_run(root, pending, owner)
        _op(
            root,
            space,
            owner,
            core.WorkflowRequest,
            action="advance",
            root_work_id=pending,
            expected_revision=state.revision,
            node_key="period",
        )
    before = [core.read_workflow_run(root, work, owner).waits[0] for work in (first, second)]
    clarify = native.Provider(
        [
            {"_tool": "zara_workflow", "mode": "status", "root_work_id": str(first)},
            {"_tool": "zara_workflow", "mode": "status", "root_work_id": str(second)},
            {"_final_text": "Both questions remain open; choose which process to continue."},
        ]
    )
    run(clarify, prompt="I do not understand why the process stopped", expected_provider_calls=3)
    assert [
        core.read_workflow_run(root, work, owner).waits[0] for work in (first, second)
    ] == before
    answer = native.Provider(
        [
            {
                "_tool": "zara_workflow",
                "mode": "answer",
                "root_work_id": str(first),
                "wait_id": str(before[0].wait_id),
                "expected_wait_revision": before[0].revision,
            },
            {"_final_text": "Your answer is retained for the first process only."},
        ]
    )
    run(
        answer,
        prompt="For the first process compare the previous complete month",
        expected_provider_calls=2,
        wait_for=lambda: bool(core.read_work(root, first, owner).state.linked_outputs),
    )
    assert core.read_workflow_run(root, second, owner).waits == (before[1],)
    assert core.read_work(root, first, owner).state.acceptance is None
    for body in observed:
        assert "ZARA_MANIFEST:" in json.dumps(body)
    assigned_sends = sum(
        len(core.read_execution(root, record.record_id, owner).invocations)
        for record in core.inspect_space(root, owner).records
        if record.kind == "work"
    )
    database = root / ".zara-core" / "core.sqlite3"
    with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True) as connection:
        ids = [
            UUID(row[0])
            for row in connection.execute("SELECT invocation_id FROM knowledge_delivery")
        ]
    deliveries = [core.read_context_delivery(root, item, owner) for item in ids]
    assert len(deliveries) == len(observed) == 11 and assigned_sends == 4
    assert all(item["stage"] == "answered" for item in deliveries)
    method_result = method_wait_probe(directory / "native-method", runtime)
    project_result = project_read_probe(directory / "project-read", runtime)
    result = {
        "http_requests": len(observed),
        "accounted_sends": len(deliveries),
        "assigned_nodes": sorted(assigned_packets),
        "overlapping_independent_requests": right_received.is_set(),
        "saved_questions": 2,
        "targeted_answer": True,
        "automatic_work_acceptance": False,
        "native_method": method_result,
        "project_read": project_result,
        "total_http_requests": len(observed)
        + method_result["http_requests"]
        + project_result["http_requests"],
        "total_accounted_sends": len(deliveries)
        + method_result["accounted_sends"]
        + project_result["accounted_sends"],
    }
    (directory / "requests.json").write_text(
        json.dumps(observed, indent=2) + "\n", encoding="utf-8"
    )
    (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--pi-runtime", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run_probe(args.directory.resolve(), args.pi_runtime.resolve()), indent=2))


if __name__ == "__main__":
    main()
