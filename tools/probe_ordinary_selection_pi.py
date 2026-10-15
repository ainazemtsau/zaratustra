"""Fictional ordinary Pi Work handoff, exact send pins and native restart.

Run against either the checkout or an explicitly installed wheel. Only localhost
Responses traffic is used; the actual upstream Pi executes its own native tools.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import traceback
import zipfile
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import zaratustra.foundation as core
from zaratustra.pi_adapter import Bridge
from zaratustra.pi_adapter.__main__ import INTERACTIVE_ZARA_TOOLS, _prepare_space
from zaratustra.pi_adapter.runtime import system_pi_runtime
from zaratustra.workspace import LaunchConfig, Project, select_work_project, write_config

from .probe_conversation_responses_pi import (
    RawResponsesProvider,
    codex_context,
    completed_response,
)
from .probe_knowledge_pi import run_process


def _dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _installed_bytes(wheel: Path) -> dict[str, object]:
    product = Path(core.__file__).resolve().parents[1]
    members = 0
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith("zaratustra/") and not name.endswith("/"):
                assert archive.read(name) == (product.parent / name).read_bytes(), name
                members += 1
    assert members > 0
    return {
        "product_root": str(product),
        "version": importlib.metadata.version("zaratustra"),
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "verified_product_files": members,
    }


def run(directory: Path, wheel: Path, *, external: bool = False) -> dict[str, Any]:
    """Observe the committed old interruption before returning any target reply."""
    assert not directory.exists()
    directory.mkdir(parents=True)
    report: dict[str, Any] = {"outcome": "not_run", "real_model_calls": 0}
    all_events: list[dict[str, object]] = []
    replies: list[dict[str, object]] = []
    providers: list[RawResponsesProvider] = []
    try:
        report.update(_installed_bytes(wheel))
        root = directory / "core"
        root.mkdir()
        owner = _prepare_space(root, "fictional-owner", create=True, upgrade_existing=True)
        space = core.read_space(root)
        assert space.schema_version == 18
        activity, original_work, target_work = uuid4(), uuid4(), uuid4()

        def apply(request_type: Any, **fields: Any) -> Any:
            return core.apply_operation(
                root,
                request_type(
                    operation_id=uuid4(), space_id=space.space_id, actor=owner.actor, **fields
                ),
                owner,
            )

        apply(
            core.CreateActivityRequest,
            activity_id=activity,
            state=core.ActivityState(
                title="Fictional transition", goal="Preserve and continue work"
            ),
        )
        for work_id, goal in (
            (original_work, "Save the fictional assessment"),
            (target_work, "Continue the fictional next step"),
        ):
            apply(
                core.CreateWorkRequest,
                work_id=work_id,
                state=core.WorkState(
                    activity_id=activity,
                    goal=goal,
                    expected_outputs=(core.OutputContract(slot="report", media_type="text/plain"),),
                ),
            )
        personal, code, runtime = (directory / name for name in ("personal", "code", "runtime"))
        for item in (personal, code, runtime):
            item.mkdir()
        native = system_pi_runtime()
        config_path = runtime / "config.json"
        configuration = LaunchConfig(
            version=2,
            actor=owner.actor,
            space_id=space.space_id,
            space=root,
            workspace=personal,
            personal_root=personal,
            runtime_root=runtime,
            sqlite_dll=runtime / "unused-sqlite.dll",
            pi_runtime=native.root,
            pi_source="system",
            provider_profile="codex-sse",
            provider_base_url="http://127.0.0.1:1/backend-api",
            provider_id="openai-codex",
            model_id="gpt-6.1-sol",
            reserve_units=1000,
            projects=(Project(name="code", path=code),),
        )
        write_config(config_path, configuration)
        select_work_project(configuration, owner, original_work, "personal")
        select_work_project(configuration, owner, target_work, "code" if external else "personal")
        target_root = code if external else personal
        originals = (b"Fictional assessment retained", b"Fictional next step retained")
        before_b = core.read_work(root, target_work, owner)
        sessions = directory / "sessions"
        sessions.mkdir()

        def context(body: dict[str, Any], expected: UUID) -> dict[str, Any]:
            packet = codex_context(body)
            assert packet["work"]["work_id"] == str(expected)
            assert packet["request_origin"]["kind"] == "owner"
            return packet

        def route(body: dict[str, Any]) -> list[dict[str, Any]]:
            provider = providers[0]
            if provider.calls == 1:
                context(body, original_work)
                return completed_response(
                    None,
                    call=(
                        "zara_result",
                        {
                            "mode": "publish",
                            "slot": "report",
                            "content_text": originals[0].decode(),
                        },
                    ),
                )
            if provider.calls == 2:
                packet = context(body, original_work)
                old = core.read_execution(root, original_work, owner)
                assert [item.status for item in old.attempts] == ["completed", "active"]
                action = next(
                    item
                    for item in packet["conversation_actions"]
                    if item.get("work_id") == str(target_work)
                )
                response = completed_response(
                    None,
                    call=(
                        "zara_conversation",
                        {"mode": "use_existing_work", "action_ref": action["ref"]},
                    ),
                )
                if external:
                    item = {
                        "type": "function_call",
                        "id": "fictional-later-write",
                        "call_id": "fictional-later-write-call",
                        "name": "write",
                        "arguments": json.dumps(
                            {"path": "blocked-batch.txt", "content": "Must not be written"}
                        ),
                    }
                    response[-1]["response"]["output"].append(item)
                    response[-1:-1] = [
                        {"type": "response.output_item.added", "output_index": 1, "item": item},
                        {"type": "response.output_item.done", "output_index": 1, "item": item},
                    ]
                return response
            context(body, target_work)
            old = core.read_execution(root, original_work, owner)
            target = core.read_execution(root, target_work, owner)
            assert not (personal / "blocked-batch.txt").exists()
            assert not (code / "blocked-batch.txt").exists()
            assert [item.status for item in old.attempts] == ["completed", "interrupted"]
            assert all(item.status == "answered" for item in old.invocations)
            assert old.work.state.acceptance is None and target.work.state.acceptance is None
            active = next(item for item in target.attempts if item.status == "active")
            resource = next(
                item for item in target.resources if item.resource_id == active.resource_id
            )
            assert resource.revision == active.resource_revision
            assert resource.state.root == target_root
            if provider.calls == 3:
                return completed_response(
                    None, call=("write", {"path": "handoff.txt", "content": "Target root effect"})
                )
            if provider.calls == 4:
                assert (target_root / "handoff.txt").read_text(
                    encoding="utf-8"
                ) == "Target root effect"
                return completed_response(
                    None,
                    call=(
                        "zara_result",
                        {
                            "mode": "publish",
                            "slot": "report",
                            "content_text": originals[1].decode(),
                        },
                    ),
                )
            assert provider.calls == 5
            return completed_response(
                "The fictional next step is saved; acceptance remains separate."
            )

        provider = RawResponsesProvider([route] * 5)
        providers.append(provider)
        configuration = LaunchConfig.model_validate(
            {
                **configuration.model_dump(),
                "provider_base_url": f"http://127.0.0.1:{provider.server_port}/backend-api",
            }
        )
        write_config(config_path, configuration)
        bridge = Bridge(root, owner, personal, workspace_config=config_path)

        def observed_reply(path: str, payload: object) -> None:
            replies.append({"path": path, "payload": payload})

        run_process(
            personal,
            native.root,
            bridge,
            provider,
            work=(activity, original_work),
            prompt=(
                "Retain the assessment, then continue the existing next-step Work and save it."
            ),
            provider_profile="codex-sse",
            local_model_id="gpt-6.1-sol",
            session_directory=sessions,
            tool_names=(*INTERACTIVE_ZARA_TOOLS, "write"),
            expected_provider_calls=5,
            expected_tool_errors=1 if external else 0,
            on_bridge_response=observed_reply,
            on_event=lambda _process, event: all_events.append(event),
        )
        assert provider.calls == 5 and not provider.errors
        assert any(item.get("type") == "agent_settled" for item in all_events)
        after_a = core.read_execution(root, original_work, owner)
        after_b = core.read_execution(root, target_work, owner)
        assert len(after_a.invocations) == 2 and len(after_b.invocations) == 3
        assert not any(item.status == "active" for item in (*after_a.attempts, *after_b.attempts))
        assert after_b.work.state.goal == before_b.state.goal
        pinned_outputs = []
        for execution, content in ((after_a, originals[0]), (after_b, originals[1])):
            assert execution.work.state.status == "proposed"
            assert execution.work.state.acceptance is None
            assert len(execution.work.state.linked_outputs) == 1
            ref = execution.work.state.linked_outputs[0].artifact
            assert (
                core.read_artifact(root, ref.artifact_id, owner, revision=ref.revision).content
                == content
            )
            pinned_outputs.append(ref.model_dump(mode="json"))
        (session_file,) = sessions.glob("*.jsonl")
        before_reopen = [item.model_dump(mode="json") for item in after_b.work.state.linked_outputs]

        def reopened(body: dict[str, Any]) -> list[dict[str, Any]]:
            context(body, target_work)
            assert core.read_work(root, target_work, owner).state.acceptance is None
            return completed_response(
                "The retained fictional result is available; choose the next action."
            )

        second = RawResponsesProvider([reopened])
        providers.append(second)
        configuration = LaunchConfig.model_validate(
            {
                **configuration.model_dump(),
                "provider_base_url": f"http://127.0.0.1:{second.server_port}/backend-api",
            }
        )
        write_config(config_path, configuration)
        run_process(
            personal,
            native.root,
            Bridge(root, owner, personal, workspace_config=config_path),
            second,
            resume_session=session_file,
            resume_via_switch=True,
            prompt_after_switch=True,
            prompt="Continue the saved next step after reopening.",
            provider_profile="codex-sse",
            local_model_id="gpt-6.1-sol",
            tool_names=INTERACTIVE_ZARA_TOOLS,
            expected_provider_calls=1,
            on_bridge_response=observed_reply,
            on_event=lambda _process, event: all_events.append(event),
        )
        assert second.calls == 1 and not second.errors
        final_b = core.read_execution(root, target_work, owner)
        assert [
            item.model_dump(mode="json") for item in final_b.work.state.linked_outputs
        ] == before_reopen
        assert not any(item.status == "active" for item in final_b.attempts)
        assert final_b.work.state.acceptance is None
        invocations = [*after_a.invocations, *final_b.invocations]
        by_manifest = {}
        for invocation in invocations:
            delivery = core.read_context_delivery(root, invocation.invocation_id, owner)
            by_manifest[str(delivery["manifest_id"])] = invocation, delivery
        deliveries = []
        requests = [item for server in providers for item in server.requests]
        assert len(requests) == len(invocations) == 6
        for body in requests:
            marker = re.findall(r"ZARA_MANIFEST:([0-9a-f-]+)@([0-9]+)", body["instructions"])[-1]
            manifest = core.read_knowledge(root, UUID(marker[0]), owner, revision=int(marker[1]))
            assert isinstance(manifest.state, core.ContextState)
            invocation, delivery = by_manifest[str(manifest.record_id)]
            assert invocation.status == delivery["stage"] == "answered"
            assert delivery["correlation_state"] == "exact"
            assert delivery["request_sha256"] == invocation.request_sha256
            assert delivery["context_work_id"] == str(manifest.state.work_id)
            assert delivery["context_attempt_id"] == str(invocation.attempt_id)
            assert delivery["context_session_id"] == str(manifest.state.session_id)
            deliveries.append(delivery)
        assert not any(item.get("type") == "extension_error" for item in all_events)
        _dump(directory / "after-a.json", after_a.model_dump(mode="json"))
        _dump(directory / "after-b.json", final_b.model_dump(mode="json"))
        _dump(directory / "deliveries.json", deliveries)
        report.update(
            outcome="passed",
            pi_version=native.version,
            native_processes=2,
            localhost_http=6,
            exact_request_pins=True,
            native_settled=True,
            old_output_retained=True,
            target_output_retained=True,
            restart_preserved=True,
            acceptance=False,
            external=external,
            target_root=str(target_root),
            stale_batch_effect_refused=external,
            output_refs=pinned_outputs,
            committed_units=sum(item.usage_units or 0 for item in invocations),
        )
        return report
    except Exception as error:
        report.update(outcome="failed", error_type=type(error).__name__, error=str(error))
        (directory / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        report["localhost_http"] = sum(server.calls for server in providers)
        _dump(directory / "report.json", report)
        _dump(directory / "native-events.json", all_events)
        _dump(directory / "bridge-replies.json", replies)
        _dump(
            directory / "http-requests.json",
            [item for server in providers for item in server.requests],
        )
        _dump(
            directory / "wire-responses.json",
            [item for server in providers for item in server.wire_responses],
        )
        _dump(
            directory / "provider-errors.json",
            [item for server in providers for item in server.errors],
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--external", action="store_true")
    args = parser.parse_args()
    directory = args.directory.resolve()
    scratch = Path(__file__).resolve().parents[1] / "_scratch"
    if directory == scratch or not directory.is_relative_to(scratch):
        parser.error("Choose a new directory inside this checkout's _scratch")
    print(json.dumps(run(directory, args.wheel.resolve(), external=args.external), indent=2))


if __name__ == "__main__":
    main()
