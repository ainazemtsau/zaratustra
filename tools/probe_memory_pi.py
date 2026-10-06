"""Installed-compatible shared memory trial using ordinary Pi and localhost only.

Copy this file and probe_knowledge_pi.py together to run with an installed wheel.
The harness lazily imports old fixtures only in its unrelated legacy trials.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import threading
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import TypeAdapter

import zaratustra.foundation as core
from zaratustra.pi_adapter import Bridge, read_pi_runtime
from zaratustra.pi_adapter.assigned import EXECUTOR_VERSION, AssignedConfig, run_assigned


def harness() -> Any:
    specification = importlib.util.spec_from_file_location(
        "memory_pi_harness", Path(__file__).with_name("probe_knowledge_pi.py")
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def run_probe(directory: Path, runtime: Path) -> dict[str, object]:
    directory.mkdir(parents=True, exist_ok=False)
    root, working = directory / "space", directory / "work"
    root.mkdir()
    working.mkdir()
    info = core.initialize_space(root)
    authority = core.authorize_local(root, actor="owner", source_ref="fictional-memory-trial")
    adapter: TypeAdapter[core.DomainRequest] = TypeAdapter(core.DomainRequest)

    def operation(kind: str, **fields: Any) -> core.OperationReceipt:
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
    ):
        upgrade(root, authority)
    activities = (uuid4(), uuid4())
    for identifier in activities:
        operation(
            "create_activity",
            activity_id=identifier,
            state={"title": "Fictional research", "goal": "Review fictional records"},
        )

    native = harness()
    sources = (uuid4(), uuid4(), uuid4())
    markers = ("FICTIONAL_COMMON_MEMORY", "FICTIONAL_FIRST_MEMORY", "FICTIONAL_OTHER_MEMORY")
    script = []
    for identifier, marker, activity in zip(sources, markers, (None, *activities), strict=True):
        state = native.source(marker + " — вымышленные сведения 🧭")
        state["scope_activity_id"] = str(activity) if activity else None
        state["memory"] = {
            "title": marker,
            "activity_id": str(activity) if activity else None,
            "topics": ["working"],
        }
        script.append(native.apply(identifier, state))
    selectors = [
        {
            "common": True,
            "activity_ids": list(map(str, activities)),
            "topics": ["working"],
            "full": True,
        }
    ]
    script.extend(
        [
            {"mode": "catalog", "selectors": selectors},
            {"mode": "read_batch", "selectors": selectors},
        ]
    )
    first = native.Provider(script)
    sessions = directory / "sessions"
    native.run_process(
        working, runtime, Bridge(root, authority, working, None), first, session_directory=sessions
    )
    selectors_typed = tuple(core.MemorySelector.model_validate(s) for s in selectors)
    cached = core.prepare_memory_cache(root, authority, selectors_typed)
    old_selection = str(cached["selection_id"])
    assert cached["content_complete"] and all(m in str(cached["content_text"]) for m in markers)
    extra = uuid4()
    operation(
        "create_knowledge",
        record_id=extra,
        state={
            "kind": "source",
            "channel": "document",
            "connection": "fictional",
            "profile_revision": 1,
            "media_type": "text/plain",
            "capture": "full",
            "content": b"FICTIONAL_NEW_MEMORY",
            "scope_activity_id": str(activities[0]),
            "memory": {
                "title": "New intake",
                "activity_id": str(activities[0]),
                "topics": ["working"],
            },
        },
    )
    assert not core.open_memory_selection(root, UUID(old_selection), authority)["current"]

    def export_request(body: dict[str, Any]) -> dict[str, object]:
        outputs = [m for m in body["messages"] if m["role"] == "tool"]
        latest = json.loads(outputs[-1]["content"])
        assert latest["members"] == 4 and latest["selection_id"] != old_selection
        return {"mode": "export", "selection_id": latest["selection_id"], "file": "snapshot.md"}

    second = native.Provider([{"mode": "prepare_cache", "selectors": selectors}, export_request])
    native.run_process(
        working, runtime, Bridge(root, authority, working, None), second, compact=True
    )
    exported = (working / "snapshot.md").read_text(encoding="utf-8")
    assert all(m in exported for m in (*markers, "FICTIONAL_NEW_MEMORY"))

    # A reusable Method is admitted through the existing Candidate/Decision seam.
    method_id, candidate_id, decision_id, validation_id = (uuid4() for _ in range(4))
    evidence = {"record_id": str(sources[0]), "revision": 1}
    definition = {
        "instruction": "Read selected fictional memory and retain an addressed report.",
        "named_outputs": [{"slot": "report", "media_type": "text/plain"}],
        "source_ref": "fictional-memory-trial",
        "memory_requirements": [
            {"selectors": [{"common": True, "current_activity": True, "topics": ["working"]}]}
        ],
    }
    operation(
        "create_development",
        record_id=candidate_id,
        state={
            "kind": "candidate",
            "target": {
                "kind": "method",
                "method_id": str(method_id),
                "to_version": 1,
                "definition": definition,
            },
            "proposal": "Use selected memory",
            "evidence": [evidence],
            "expected_outcome": "Exact addressed memory in Work",
            "scope_activity_ids": [str(activities[0])],
            "exclusions": "Other Activities",
            "impact": "New Work",
            "unknowns": "Fictional only",
            "restore_plan": "Stop new use",
            "irreversible_effects": "None",
            "validation_plan": {
                "baseline": "No selection",
                "environment": "Fictional Core",
                "criteria": [
                    {
                        "key": "exact",
                        "question": "Are inputs addressable?",
                        "pass_condition": "Exact refs",
                        "basis": [evidence],
                    }
                ],
                "cases": "Selected facts",
                "method": "Inspect Core",
                "sufficiency": "Structural trial",
                "limits": "No model quality claim",
                "stop_and_restore": "Stop new use",
                "decision_condition": "Current rights",
                "follow_up": "Review result",
            },
            "results": [
                {
                    "result_id": str(validation_id),
                    "criterion": "exact",
                    "outcome": "met",
                    "evidence": [evidence],
                    "actual_input": "Exact Source",
                    "environment": "Core",
                }
            ],
        },
    )
    operation(
        "create_decision",
        decision_id=decision_id,
        state={
            "variant": "change_adoption",
            "statement": "Admit fictional memory Method",
            "candidate_id": str(candidate_id),
            "candidate_revision": 1,
            "mode": "regular",
            "use": "recommended",
            "scope_activity_id": str(activities[0]),
            "validation_result_ids": [str(validation_id)],
            "review_condition": "After trial",
        },
    )
    operation(
        "apply_candidate",
        candidate_id=candidate_id,
        candidate_revision=1,
        decision_id=decision_id,
        decision_revision=1,
        mode="regular",
    )
    method_ref = {
        "method_id": str(method_id),
        "version": 1,
        "checksum": core.method_checksum(core.MethodDefinition.model_validate(definition)),
    }
    core.read_method_version(root, core.MethodRef.model_validate(method_ref), authority)

    def create_work(*, method_work: bool = False) -> UUID:
        work_id = uuid4()
        state = {
            "activity_id": str(activities[0]),
            "goal": "Use exact fictional memory",
            "expected_outputs": definition["named_outputs"],
        }
        if not method_work:
            operation("create_work", work_id=work_id, state=state)
            return work_id
        operation(
            "create_composite_work",
            work_id=work_id,
            state={
                "activity_id": str(activities[0]),
                "goal": "Use exact fictional memory",
                "method": method_ref,
                "expected_outputs": definition["named_outputs"],
            },
            plan={
                "parent_outputs": definition["named_outputs"],
                "children": [
                    {
                        "role": "review",
                        "work_id": str(uuid4()),
                        "state": {
                            "activity_id": str(activities[0]),
                            "goal": "Review the fictional report",
                            "expected_outputs": [{"slot": "review", "media_type": "text/plain"}],
                        },
                    }
                ],
                "rationale": "Retain own result before separate review",
                "source_ref": "fictional-memory-plan",
            },
        )
        return work_id

    def inspect_request(body: dict[str, Any]) -> dict[str, object]:
        serialized = json.dumps(body, ensure_ascii=False)
        assert all(
            marker in serialized for marker in (markers[0], markers[1], "FICTIONAL_NEW_MEMORY")
        )
        assert markers[2] not in serialized
        return {
            "_tool": "zara_result",
            "mode": "publish",
            "slot": "report",
            "content_text": "Fictional memory report; acceptance remains separate",
        }

    interactive_work = create_work()
    third = native.Provider(
        [
            {
                "mode": "prepare_cache",
                "selectors": [
                    {"common": True, "activity_ids": [str(activities[0])], "topics": ["working"]}
                ],
            },
            inspect_request,
        ]
    )
    work_sessions = directory / "work-sessions"
    native.run_process(
        working,
        runtime,
        Bridge(root, authority, working, None),
        third,
        work=(activities[0], interactive_work),
        compact=True,
        continue_after_compact=True,
        session_directory=work_sessions,
    )
    saved = core.read_work(root, interactive_work, authority)
    assert saved.state.linked_outputs and saved.state.acceptance is None

    # Resumed multi-turn history uses two distinct compaction summaries before content.
    resumed = native.Provider([None, None, {"mode": "catalog", "selectors": [{"common": True}]}])
    native.run_process(
        working,
        runtime,
        Bridge(root, authority, working, None),
        resumed,
        work=(activities[0], interactive_work),
        resume_session=next(work_sessions.glob("*.jsonl")),
        compact=True,
        continue_after_compact=True,
        expected_provider_calls=4,
    )
    resumed_system = json.dumps(resumed.requests[2]["messages"][0], ensure_ascii=False)
    assert "conversation_memory" in resumed_system
    assert all(
        marker in resumed_system for marker in (markers[0], markers[1], "FICTIONAL_NEW_MEMORY")
    )
    assert markers[2] not in resumed_system

    # The assigned runner uses the same public API and Method selection in a fresh session.
    reopened = native.Provider([{"_tool": "zara_result", "mode": "read"}])
    reopened_events = native.run_process(
        working,
        runtime,
        Bridge(root, authority, working, None),
        reopened,
        work=(activities[0], interactive_work),
    )
    assert any(
        "Fictional memory report; acceptance remains separate" in json.dumps(event)
        for event in reopened_events
        if event.get("type") == "tool_execution_end"
    )
    assigned_work = create_work(method_work=True)
    resource_id, attempt_id, session_id = (uuid4() for _ in range(3))
    operation(
        "create_resource",
        work_id=assigned_work,
        resource_id=resource_id,
        state={"label": "Fictional assigned work", "root": working},
    )
    operation(
        "assign_attempt",
        work_id=assigned_work,
        expected_work_revision=1,
        resource_id=resource_id,
        expected_resource_revision=1,
        attempt_id=attempt_id,
        session_id=session_id,
        executor_version=EXECUTOR_VERSION,
    )

    def inspect_assigned(body: dict[str, Any]) -> dict[str, object]:
        inspect_request(body)
        return {"mode": "catalog", "selectors": [{"common": True, "topics": ["working"]}]}

    assigned = native.Provider(
        [inspect_assigned],
        final_content=json.dumps(
            {
                "zara": "final",
                "text": "Fictional assigned memory report",
            }
        ),
    )
    thread = threading.Thread(target=assigned.serve_forever, daemon=True)
    thread.start()
    actual_runtime = read_pi_runtime(runtime)
    try:
        run_assigned(
            AssignedConfig(
                space=root,
                workspace=working,
                pi_cli=actual_runtime.cli,
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
            ),
            authority,
            attempt_id,
        )
    finally:
        assigned.shutdown()
        assigned.server_close()
        thread.join(timeout=5)
    final = core.read_work(root, assigned_work, authority)
    assert final.state.linked_outputs and final.state.acceptance is None
    assert assigned.calls == 2
    fresh = core.authorize_local(root, actor="owner", source_ref="fictional-reopen")
    updated = core.prepare_memory_cache(root, fresh, selectors_typed)
    assert updated["members"] == 4 and updated["current"]
    registry = __import__("zaratustra.integrations", fromlist=["installed_integrations"])
    boundary = registry.installed_integrations(root, fresh).execute(
        uuid4(), "memory", "read_batch", {"selectors": selectors}, contract_version=1
    )
    assert boundary.output["members"] == 4
    return {
        "schema": core.read_space(root).schema_version,
        "foundation_module": str(core.__file__),
        "interactive_http": first.calls
        + second.calls
        + third.calls
        + resumed.calls
        + reopened.calls,
        "native_resume_http": resumed.calls,
        "assigned_http": assigned.calls,
        "real_model_calls": 0,
        "paid_api_calls": 0,
        "cache_members": updated["members"],
        "export_bytes": len(exported.encode()),
        "work": str(interactive_work),
        "assigned_work": str(assigned_work),
        "owner_acceptance": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pi-runtime", required=True, type=Path)
    args = parser.parse_args()
    report = run_probe(args.output.resolve(), args.pi_runtime.resolve())
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
