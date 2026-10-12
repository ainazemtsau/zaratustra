"""Fictional ordinary Pi selections: actual reasoning, exact pins and retained preference."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any
from uuid import UUID

import zaratustra.foundation as core
from zaratustra.pi_adapter import Bridge, read_pi_runtime
from zaratustra.pi_adapter.__main__ import INTERACTIVE_ZARA_TOOLS
from zaratustra.pi_adapter.assigned import AssignedConfig
from zaratustra.pi_adapter.workflows import WorkflowCoordinator
from zaratustra.workspace import LaunchConfig, read_config, write_config

from .probe_activity_setup_pi import context, harness


def run_probe(directory: Path, runtime: Path) -> dict[str, Any]:
    from tests.zaratustra.foundation.test_workflows import _setup

    directory.mkdir(parents=True, exist_ok=False)
    root, space, owner, _, _, identifier = _setup(
        directory,
        (
            core.WorkflowNode(
                key="first",
                kind="model",
                instruction="Inspect original facts",
                successors=("period",),
            ),
            core.WorkflowNode(
                key="period",
                kind="question",
                instruction="Which period should I compare?",
                dependencies=("first",),
                successors=("second",),
            ),
            core.WorkflowNode(
                key="second",
                kind="model",
                instruction="Compare the addressed period",
                dependencies=("period",),
            ),
        ),
    )
    personal, installed_runtime, agent = (
        directory / name for name in ("personal", "runtime", "fixture-agent")
    )
    for path in (personal, installed_runtime, agent):
        path.mkdir()
    # This is an isolated fictional catalog. No existing authorization is read.
    (agent / "auth.json").write_text("{}\n", encoding="utf-8")
    overrides: dict[str, object] = {
        identifier: {"reasoning": True} for identifier in ("fictional-first", "fictional-second")
    }
    (agent / "models.json").write_text(
        json.dumps({"providers": {"fictional-local": {"modelOverrides": overrides}}}) + "\n",
        encoding="utf-8",
    )
    native, actual = harness(), read_pi_runtime(runtime)
    observed: list[dict[str, Any]] = []
    node_requests: dict[str, dict[str, Any]] = {}
    config_path = directory / "launch.json"

    def run(provider: Any, model: str, thinking: str, *, remember: bool, **options: Any) -> None:
        address = f"http://127.0.0.1:{provider.server_port}/v1"
        if not config_path.exists():
            write_config(
                config_path,
                LaunchConfig(
                    version=2,
                    actor=owner.actor,
                    space_id=space,
                    space=root,
                    workspace=personal,
                    personal_root=personal,
                    runtime_root=installed_runtime,
                    sqlite_dll=Path(os.environ["ZARATUSTRA_SQLITE_DLL"]),
                    pi_runtime=runtime,
                    provider_profile="local-completions",
                    provider_base_url=address,
                    provider_id="fictional-local",
                    model_id="fictional-first",
                    reserve_units=1000,
                ),
            )
        bridge = Bridge(root, owner, personal, workspace_config=config_path)
        config = AssignedConfig(
            space=root,
            workspace=personal,
            workspace_config=config_path,
            pi_cli=actual.cli,
            pi_runtime=runtime,
            node=shutil.which("node") or "node",
            provider_profile="local-completions",
            provider_base_url=address,
            provider_id="fictional-local",
            model_id="fictional-first",
            thinking="off",
            context_window=1000000,
            max_tokens=32768,
            reserve_units=1000,
            limit_units=None,
            offline=True,
            subscription_agent_dir=agent,
        )
        bridge.workflow_controller = WorkflowCoordinator(bridge, config)
        try:
            native.run_process(
                personal,
                runtime,
                bridge,
                provider,
                local_model_id=model,
                thinking=thinking,
                model_overrides=overrides,
                remember_selection=remember,
                fixture_agent_dir=agent,
                tool_names=("read", "write", "edit", "bash", *INTERACTIVE_ZARA_TOOLS),
                **options,
            )
        finally:
            bridge.workflow_controller.close()
        for body in provider.requests:
            assert body["model"] == model, body["model"]
            assert body.get("reasoning_effort") == thinking, body.get("reasoning_effort")
            assert "ZARA_MANIFEST:" in json.dumps(body)
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
                else {"_final_text": "A period choice is saved."}
            )
        exact = json.loads(packet["inputs"][0]["content_text"])
        assert exact["node"]["key"] == "first"
        node_requests["first"] = body
        return {
            "_final_text": '{"outcome":"result","values":{"facts":"checked"},'
            '"next_nodes":["period"]}'
        }

    first = native.Provider([first_reply] * 8)
    run(
        first,
        "fictional-first",
        "low",
        remember=True,
        prompt="Start the fictional comparison",
        expected_provider_calls=3,
        wait_for=lambda: bool(core.read_workflow_run(root, identifier, owner).waits),
    )
    current = core.read_workflow_run(root, identifier, owner)
    first_pin = next(node.model for node in current.nodes if node.key == "first")
    assert first_pin and (first_pin.model_id, first_pin.reasoning) == ("fictional-first", "low")
    preference = read_config(config_path).preferred_model
    assert preference and (preference.model_id, preference.thinking) == ("fictional-first", "low")
    saved_wait = current.waits[0]
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
                    "wait_id": str(saved_wait.wait_id),
                    "expected_wait_revision": saved_wait.revision,
                }
            if second_calls == 2:
                return {"_tool": "zara_workflow", "mode": "resume", "root_work_id": str(identifier)}
            return {"_final_text": "The compared result is proposed."}
        exact = json.loads(packet["inputs"][0]["content_text"])
        assert exact["node"]["key"] == "second" and exact["interactions"]
        node_requests["second"] = body
        return {"_final_text": '{"outcome":"result","values":{"comparison":"checked"}}'}

    second = native.Provider([second_reply] * 8)
    run(
        second,
        "fictional-second",
        "high",
        remember=True,
        prompt="Compare the previous complete month and continue",
        expected_provider_calls=4,
        wait_for=lambda: bool(core.read_work(root, identifier, owner).state.linked_outputs),
    )
    nodes = core.read_workflow_run(root, identifier, owner).nodes
    assert next(node.model for node in nodes if node.key == "first") == first_pin
    second_pin = next(node.model for node in nodes if node.key == "second")
    assert second_pin and (second_pin.model_id, second_pin.reasoning) == (
        "fictional-second",
        "high",
    )
    preference = read_config(config_path).preferred_model
    assert preference and (preference.model_id, preference.thinking) == ("fictional-second", "high")
    before_reopen = config_path.read_bytes()
    reopened = native.Provider([{"_final_text": "The proposed comparison remains available."}])
    run(
        reopened,
        preference.model_id,
        str(preference.thinking),
        remember=False,
        prompt="Explain the saved comparison",
        expected_provider_calls=1,
    )
    assert config_path.read_bytes() == before_reopen
    assert core.read_work(root, identifier, owner).state.acceptance is None
    with sqlite3.connect(
        f"{(root / '.zara-core' / 'core.sqlite3').as_uri()}?mode=ro", uri=True
    ) as connection:
        deliveries = [
            core.read_context_delivery(root, UUID(row[0]), owner)
            for row in connection.execute("SELECT invocation_id FROM knowledge_delivery")
        ]
    assert len(observed) == len(deliveries) == 8
    assert all(delivery["stage"] == "answered" for delivery in deliveries)
    result = {
        "http_requests": len(observed),
        "accounted_sends": len(deliveries),
        "first_actual_selection": {"model": first_pin.model_id, "reasoning": first_pin.reasoning},
        "second_actual_selection": {
            "model": second_pin.model_id,
            "reasoning": second_pin.reasoning,
        },
        "first_pin_immutable": True,
        "persisted_preference_used_on_reopen": True,
        "automatic_work_acceptance": False,
        "limits": "Native Pi reopen uses the retained preference; "
        "full release CLI fallback is tested separately",
    }
    (directory / "requests.json").write_text(
        json.dumps(observed, indent=2) + "\n", encoding="utf-8"
    )
    (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--pi-runtime", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_probe(args.directory.resolve(), args.pi_runtime.resolve()), indent=2))


if __name__ == "__main__":
    main()
