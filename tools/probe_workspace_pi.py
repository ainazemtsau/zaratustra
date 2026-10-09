"""Installed ordinary Pi: real root-bound tools, local Git offer, compact and resume."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

import zaratustra.foundation as core
from zaratustra.pi_adapter import Bridge, prepare_space, read_pi_runtime
from zaratustra.pi_adapter.assigned import EXECUTOR_VERSION, AssignedConfig, run_assigned
from zaratustra.workspace import (
    GitDestination,
    LaunchConfig,
    Project,
    delivery,
    select_work_project,
    write_config,
)


def run_probe(directory: Path, runtime: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=False)
    personal, external, installed = (
        directory / name for name in ("personal", "external", "runtime")
    )
    for folder in (personal, external, installed):
        folder.mkdir()
    root = personal / "space"
    root.mkdir()
    authority = prepare_space(root, "owner", create=True)
    activity, work, setup, configuring = uuid4(), uuid4(), uuid4(), uuid4()
    core.apply_operation(
        root,
        core.CreateActivityRequest(
            operation_id=uuid4(),
            space_id=authority.space_id,
            actor="owner",
            activity_id=activity,
            state=core.ActivityState(title="Fictional development", goal="Write a project note"),
        ),
        authority,
    )
    core.apply_operation(
        root,
        core.CreateWorkRequest(
            operation_id=uuid4(),
            space_id=authority.space_id,
            actor="owner",
            work_id=work,
            state=core.WorkState(
                activity_id=activity,
                goal="Prepare a fictional deliverable",
                expected_outputs=(core.OutputContract(slot="report", media_type="text/plain"),),
            ),
        ),
        authority,
    )
    core.apply_operation(
        root,
        core.ActivitySetupRequest(
            operation_id=uuid4(),
            space_id=authority.space_id,
            actor="owner",
            setup_id=setup,
            activity_id=configuring,
            action="begin",
            title="Fictional future activity",
            text="Retain a fictional routine",
        ),
        authority,
    )
    question = "Which fictional routine should we retain?"
    config = LaunchConfig(
        version=2,
        actor="owner",
        space_id=authority.space_id,
        space=root,
        workspace=personal,
        personal_root=personal,
        runtime_root=installed,
        sqlite_dll=installed / "unused.dll",
        pi_runtime=runtime,
        pi_source="system",
        provider_profile="local-completions",
        provider_base_url="http://127.0.0.1:1/v1",
        provider_id="fictional-local",
        model_id="fictional-model",
        reserve_units=1000,
        projects=(Project(name="external", path=external),),
        git=GitDestination(repository="fictional/personal"),
    )
    config_path = installed / "config.json"
    write_config(config_path, config)
    for args in (
        ("init", "--initial-branch=main"),
        ("remote", "add", "origin", "https://github.com/fictional/personal.git"),
    ):
        subprocess.run(
            ["git", *args],
            cwd=personal,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    (personal / "README.md").write_text("Fictional personal workspace\n", encoding="utf-8")
    native_command = delivery._command

    def command(root: Path, arguments: list[str]) -> str:
        if arguments[0] == "gh":
            return json.dumps({"nameWithOwner": "fictional/personal", "visibility": "PRIVATE"})
        return native_command(root, arguments)

    delivery._command = command
    specification = importlib.util.spec_from_file_location(
        "workspace_pi_harness", Path(__file__).with_name("probe_knowledge_pi.py")
    )
    assert specification and specification.loader
    harness = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(harness)
    try:
        provider = harness.Provider(
            [
                {"_tool": "zara_workspace", "mode": "select", "name": "external"},
                {"_tool": "write", "path": "note.txt", "content": "Fictional project bytes 🐈"},
                {"_tool": "read", "path": "note.txt"},
                {"_tool": "bash", "command": "pwd"},
                {
                    "_tool": "zara_activity",
                    "mode": "question",
                    "setup_id": str(setup),
                    "question": question,
                },
                {
                    "_tool": "zara_result",
                    "mode": "publish",
                    "slot": "report",
                    "content_text": "Fictional result from external project",
                },
                {"_tool": "zara_workspace", "mode": "prepare"},
                {"_tool": "zara_workspace", "mode": "publish"},
            ]
        )
        bridge = Bridge(root, authority, personal, workspace_config=config_path)
        sessions = root / ".zara-core" / "pi-sessions"
        sessions.mkdir(exist_ok=True)
        events = harness.run_process(
            directory,
            runtime,
            bridge,
            provider,
            work=(activity, work),
            compact=True,
            confirmation_answers=(False,),
            session_directory=sessions,
            prompt="Prepare the fictional deliverable and offer Git publication.",
        )
        assert (external / "note.txt").read_text(encoding="utf-8") == "Fictional project bytes 🐈"
        assert not (personal / "note.txt").exists() and not (directory / "note.txt").exists()
        bash = [
            event
            for event in events
            if event.get("type") == "tool_execution_end" and event.get("toolName") == "bash"
        ]
        assert bash and "external" in json.dumps(bash)
        snapshot = core.read_execution(root, work, authority)
        assert snapshot.work.state.acceptance is None and snapshot.work.state.linked_outputs
        assert snapshot.resources[0].state.root == external
        prepared = delivery._load(config)
        assert prepared is not None and prepared.status == "deferred"
        first_requests = provider.requests[:]
        assert core.read_activity_setup(root, setup, authority).state.phase == "needs_input"
        session_file = next(sessions.glob("*.jsonl"))
        restarted = harness.Provider(
            [
                {"_tool": "write", "path": "continued.txt", "content": "Resumed external root"},
            ]
        )
        new_bridge = Bridge(root, authority, personal, workspace_config=config_path)
        harness.run_process(
            directory,
            runtime,
            new_bridge,
            restarted,
            resume_session=session_file,
            resume_via_switch=True,
            prompt_after_switch=True,
            compact=True,
            expected_provider_calls=4,
        )
        assert (external / "continued.txt").read_text(encoding="utf-8") == "Resumed external root"
        assert not (personal / "continued.txt").exists()
        requests = first_requests + restarted.requests
        assert all("ZARA_MANIFEST:" in json.dumps(body) for body in requests)
        assert not any(
            message.get("role") == "user"
            and (
                message.get("content") == question
                or any(
                    block.get("type") == "text" and block.get("text") == question
                    for block in message.get("content", [])
                    if isinstance(block, dict)
                )
            )
            for body in requests
            for message in body["messages"]
        )
        delivered = core.read_execution(root, work, authority)
        assert delivered.work.state.acceptance is None
        usage = core.read_current_rights(root, authority)
        assigned_work, assigned_attempt, assigned_session = uuid4(), uuid4(), uuid4()
        core.apply_operation(
            root,
            core.CreateWorkRequest(
                operation_id=uuid4(),
                space_id=authority.space_id,
                actor="owner",
                work_id=assigned_work,
                state=core.WorkState(
                    activity_id=activity,
                    goal="Write the fictional assigned file",
                    expected_outputs=(core.OutputContract(slot="report", media_type="text/plain"),),
                ),
            ),
            authority,
        )
        select_work_project(config, authority, assigned_work, "external")
        resource = core.read_execution(root, assigned_work, authority).resources[0]
        core.apply_operation(
            root,
            core.AssignAttemptRequest(
                operation_id=uuid4(),
                space_id=authority.space_id,
                actor="owner",
                work_id=assigned_work,
                expected_work_revision=1,
                resource_id=resource.resource_id,
                expected_resource_revision=resource.revision,
                attempt_id=assigned_attempt,
                session_id=assigned_session,
                executor_version=EXECUTOR_VERSION,
            ),
            authority,
        )
        assigned = harness.Provider(
            [{"_tool": "write", "path": "assigned.txt", "content": "Assigned external root"}],
            final_content=json.dumps({"zara": "final", "text": "Fictional assigned report"}),
        )
        thread = threading.Thread(target=assigned.serve_forever, daemon=True)
        thread.start()
        try:
            run_assigned(
                AssignedConfig(
                    space=root,
                    workspace=personal,
                    workspace_config=config_path,
                    pi_cli=read_pi_runtime(runtime).cli,
                    pi_runtime=runtime,
                    node=shutil.which("node") or "node",
                    provider_profile="local-completions",
                    provider_base_url=f"http://127.0.0.1:{assigned.server_port}/v1",
                    provider_id="fictional-local",
                    model_id="fictional-model",
                    context_window=16384,
                    max_tokens=512,
                    reserve_units=1000,
                    limit_units=None,
                    offline=True,
                    pi_tools=("write",),
                ),
                authority,
                assigned_attempt,
            )
        finally:
            assigned.shutdown()
            assigned.server_close()
            thread.join(timeout=5)
        assert (external / "assigned.txt").read_text(encoding="utf-8") == "Assigned external root"
        assert not (personal / "assigned.txt").exists()
        assert core.read_work(root, assigned_work, authority).state.acceptance is None
        assert assigned.calls == 2 and all(
            "ZARA_MANIFEST:" in json.dumps(body) for body in assigned.requests
        )
        report = {
            "ordinary_pi": True,
            "native_file_and_command_roots": True,
            "saved_work_project_after_resume": True,
            "git_confirmation_count": 1,
            "publication_declined_local_data_kept": True,
            "work_accepted": False,
            "manifest_in_every_request": True,
            "phantom_user_question": False,
            "actual_synthetic_http": len(requests) + assigned.calls,
            "assigned_project_root": True,
            "assigned_synthetic_http": assigned.calls,
            "real_model_calls": 0,
            "work_invocations": len(delivered.invocations),
            "rights_available": bool(usage),
            "activity": str(activity),
            "work": str(work),
            "ordinary_resources": [str(item.resource_id) for item in delivered.resources],
            "ordinary_results": [
                item.model_dump(mode="json")
                for item in core.read_work(root, work, authority).state.linked_outputs
            ],
            "assigned_work": str(assigned_work),
            "assigned_resources": [
                str(item.resource_id)
                for item in core.read_execution(root, assigned_work, authority).resources
            ],
            "assigned_results": [
                item.model_dump(mode="json")
                for item in core.read_work(root, assigned_work, authority).state.linked_outputs
            ],
        }
        (directory / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        return report
    finally:
        delivery._command = native_command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--runtime", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run_probe(args.directory.resolve(), args.runtime.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
