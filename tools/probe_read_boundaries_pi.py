"""Ordinary Pi reads mixed exact materials and advertised runtime queries.

All data and provider replies are fictional. Run with either the checkout or an
explicit installed wheel; preserved evidence contains actual localhost requests,
native events, returned byte windows and their exact Core manifests.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import zaratustra.foundation as core
from zaratustra.pi_adapter import Bridge, read_pi_runtime
from zaratustra.pi_adapter.__main__ import INTERACTIVE_ZARA_TOOLS, _prepare_space
from zaratustra.workspace import LaunchConfig, select_work_project, write_config

from .probe_conversation_responses_pi import (
    RawResponsesProvider,
    codex_context,
    completed_response,
)
from .probe_knowledge_pi import run_process
from .probe_ordinary_selection_pi import _installed_bytes


@dataclass(frozen=True)
class Fixture:
    root: Path
    owner: core.LocalAuthority
    activity: UUID
    work: UUID
    entry: core.KnowledgeRef
    other_entry: core.KnowledgeRef
    old_structure: dict[str, Any]
    current_structure: dict[str, Any]
    materials: tuple[core.KnowledgeRef, ...]
    source_bytes: bytes
    artifact_bytes: bytes
    search_source: UUID


def fixture(directory: Path) -> Fixture:
    """Admit two same-key structures, entries and an old Work through public Core."""

    from tests.zaratustra.foundation.test_activity_structures import (
        _activate,
        _change,
        _proposal,
        _structured_case,
    )

    directory.mkdir(parents=True, exist_ok=False)
    case = _structured_case(directory)
    root, space, owner, setup, activity, *_ = case
    first = _activate(case)
    other_request = core.ActivitySetupRequest(
        operation_id=uuid4(),
        space_id=space,
        actor=owner.actor,
        setup_id=uuid4(),
        activity_id=uuid4(),
        action="begin",
        contract_version=2,
        title="Other fictional observations",
        text="Keep a distinct same-key stream",
    )
    other_receipt = core.apply_operation(root, other_request, owner)
    assert other_request.activity_id is not None
    other = _activate(
        (
            root,
            space,
            owner,
            other_request.setup_id,
            other_request.activity_id,
            other_request,
            other_receipt,
        )
    )
    entries = []
    for scope, described, original, value in (
        (activity, first, core.read_activity_setup(root, setup, owner).state.sources[0], "2.50"),
        (
            other_request.activity_id,
            other,
            core.read_activity_setup(root, other_request.setup_id, owner).state.sources[0],
            "99.00",
        ),
    ):
        created = core.create_entry(
            root,
            owner,
            core.DataEntryState(
                scope_activity_id=scope,
                format_ref=core.KnowledgeRef.model_validate(
                    described["state"]["formats"]["observation"]
                ),
                role="event",
                values={"day": "2026-01-02", "value": value},
                bases=(original,),
                memory=core.MemoryMetadata(
                    title="Dated fictional observation", activity_id=scope, topics=("measurement",)
                ),
            ),
        )
        entries.append(
            core.KnowledgeRef(record_id=UUID(str(created.result["record_id"])), revision=1)
        )

    def apply(request_type: Any, **fields: Any) -> Any:
        return core.apply_operation(
            root,
            request_type(operation_id=uuid4(), space_id=space, actor=owner.actor, **fields),
            owner,
        )

    source_id, artifact_id, packet_id, search_id, work = (uuid4() for _ in range(5))
    source_prefix, source_body = b"UNREAD_SOURCE_PREFIX:", "αβγ δεζ".encode()
    artifact_prefix, artifact_body = b"UNREAD_ARTIFACT_PREFIX:", b"packet-one-two"
    source_bytes = source_prefix + source_body + b":UNREAD_SOURCE_SUFFIX"
    artifact_bytes = artifact_prefix + artifact_body + b":UNREAD_ARTIFACT_SUFFIX"
    apply(
        core.CreateKnowledgeRequest,
        record_id=source_id,
        state=core.SourceState(
            channel="document",
            connection="fictional-read-boundaries",
            profile_revision=1,
            capture="full",
            media_type="text/plain",
            content=source_bytes,
            scope_activity_id=other_request.activity_id,
            memory=core.MemoryMetadata(
                title="Bounded original", activity_id=other_request.activity_id
            ),
        ),
    )
    apply(
        core.CreateArtifactRequest,
        artifact_id=artifact_id,
        media_type="text/plain",
        content=artifact_bytes,
    )
    refs = (
        core.KnowledgeRef(
            record_id=source_id,
            revision=1,
            start=len(source_prefix),
            end=len(source_prefix) + len(source_body),
        ),
        core.KnowledgeRef(
            record_id=artifact_id,
            revision=1,
            start=len(artifact_prefix),
            end=len(artifact_prefix) + len(artifact_body),
        ),
    )
    apply(
        core.CreateArtifactRequest,
        artifact_id=packet_id,
        media_type="application/json",
        content=json.dumps({"members": [ref.model_dump(mode="json") for ref in refs]}).encode(),
    )
    apply(
        core.CreateKnowledgeRequest,
        record_id=search_id,
        state=core.SourceState(
            channel="document",
            connection="fictional-read-boundaries",
            profile_revision=1,
            capture="full",
            media_type="text/plain",
            content=b"Fictional timezone Pacific/Chatham retained for a search test.",
            scope_activity_id=activity,
            memory=core.MemoryMetadata(title="Search fixture", activity_id=activity),
        ),
    )
    apply(
        core.CreateWorkRequest,
        work_id=work,
        state=core.WorkState(
            activity_id=activity,
            goal="Read the addressed inputs and selected dated observation",
            inputs=(core.ArtifactRef(artifact_id=packet_id, revision=1),),
            expected_outputs=(core.OutputContract(slot="report", media_type="text/plain"),),
        ),
    )
    before = core.read_work(root, work, owner)
    proposal = _proposal()
    replacement = proposal.formats[0].model_copy(
        update={
            "definition": proposal.formats[0].definition.model_copy(
                update={"title": "Refined fictional observation"}
            )
        }
    )
    changed = _activate(_change(case), proposal.model_copy(update={"formats": (replacement,)}))
    assert before == core.read_work(root, work, owner)
    assert first["structure"] != changed["structure"]
    _prepare_space(root, owner.actor, create=False, upgrade_existing=True)
    return Fixture(
        root,
        owner,
        activity,
        work,
        entries[0],
        entries[1],
        first,
        changed,
        refs,
        source_bytes,
        artifact_bytes,
        search_id,
    )


def last_output(body: dict[str, Any]) -> dict[str, Any]:
    """Read the actual preceding native tool output, never a scripted expectation."""

    outputs = [item for item in body["input"] if item.get("type") == "function_call_output"]
    assert outputs, "The native request contains no preceding tool result"
    raw = outputs[-1]["output"]
    if isinstance(raw, list):
        raw = "".join(str(part.get("text", "")) for part in raw)
    value = json.loads(raw)
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def manifest_for(body: dict[str, Any], case: Fixture) -> core.KnowledgeRevision:
    matches = re.findall(r"ZARA_MANIFEST:([0-9a-f-]+)@([0-9]+)", body["instructions"])
    assert matches
    record, revision = matches[-1]
    manifest = core.read_knowledge(case.root, UUID(record), case.owner, revision=int(revision))
    assert isinstance(manifest.state, core.ContextState)
    assert manifest.state.work_id == case.work
    assert manifest.state.pinned_structure == core.KnowledgeRef.model_validate(
        case.old_structure["structure"]
    )
    return manifest


def check_exposure(
    mandatory: tuple[core.KnowledgeRef, ...],
    selected: tuple[core.KnowledgeRef, ...],
    delivered: dict[UUID, list[tuple[int, int]]],
) -> None:
    """Reject a manifest that expands the actually observed byte windows."""

    originals = {ref.record_id: ref for ref in selected}
    for ref in mandatory:
        if ref.record_id not in originals:
            continue
        assert ref.revision == originals[ref.record_id].revision
        assert ref.start is not None and ref.end is not None, (
            "Unread original widened to a whole ref"
        )
        assert any(
            start <= ref.start and ref.end <= end for start, end in delivered.get(ref.record_id, [])
        ), "Manifest includes bytes the tool did not deliver"


def run(directory: Path, runtime: Path, *, wheel: Path | None = None) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=False)
    report: dict[str, Any] = {"outcome": "not_run", "real_model_calls": 0}
    servers: list[RawResponsesProvider] = []
    events: list[dict[str, object]] = []
    bridge_replies: list[dict[str, object]] = []
    observed_outputs: list[dict[str, object]] = []
    try:
        if wheel is not None:
            report.update(_installed_bytes(wheel))
        case = fixture(directory / "fixture")
        personal, managed = directory / "personal", directory / "runtime"
        personal.mkdir()
        managed.mkdir()
        config_path = managed / "config.json"
        config = LaunchConfig(
            version=2,
            actor=case.owner.actor,
            space_id=core.read_space(case.root).space_id,
            space=case.root,
            workspace=personal,
            personal_root=personal,
            runtime_root=managed,
            sqlite_dll=managed / "unused-sqlite.dll",
            pi_runtime=runtime,
            pi_source="system",
            provider_profile="codex-sse",
            provider_base_url="http://127.0.0.1:1/backend-api",
            provider_id="openai-codex",
            model_id="gpt-6.1-sol",
            reserve_units=1000,
        )
        select_work_project(config, case.owner, case.work, "personal")
        contracts = (
            ("data", "query_entries"),
            ("memory", "catalog"),
            ("memory", "read_batch"),
            ("memory", "prepare_cache"),
        )
        expected_kinds = {
            case.materials[0].record_id: "source",
            case.materials[1].record_id: "artifact",
        }
        delivered: dict[UUID, list[tuple[int, int]]] = {}
        observed_manifests: list[tuple[str, int]] = []
        packet_materials: list[core.KnowledgeRef] = []
        selector: dict[str, Any] = {}

        def remember(output: dict[str, Any]) -> None:
            observed_outputs.append(output)
            for raw in output.get("exposed", []):
                ref = core.KnowledgeRef.model_validate(raw)
                if ref.record_id in expected_kinds:
                    assert ref.start is not None and ref.end is not None
                    delivered.setdefault(ref.record_id, []).append((ref.start, ref.end))

        def query_result(output: dict[str, Any], *, catalog: bool = False) -> None:
            if catalog:
                assert [item["record_id"] for item in output["items"]] == [
                    str(case.entry.record_id)
                ]
            else:
                refs = [
                    core.KnowledgeRef.model_validate(item) for item in output["table_of_contents"]
                ]
                assert any(ref.record_id == case.entry.record_id for ref in refs)
                assert all(ref.record_id != case.other_entry.record_id for ref in refs)
                assert output["content_complete"] is True

        def inspect_request(body: dict[str, Any]) -> None:
            native_memory = next(tool for tool in body["tools"] if tool["name"] == "zara_memory")
            advertised = native_memory["parameters"]
            exact_selector = core.RuntimeMemorySelector.model_json_schema()
            assert advertised["properties"]["selectors"]["items"] == exact_selector
            assert advertised["$defs"] == exact_selector["$defs"]
            packet = codex_context(body)
            assert packet["work"]["work_id"] == str(case.work)
            assert packet["activity_structure"]["structure"] == case.old_structure["structure"]
            # Resolve addresses from the actual delivered packet, rather than
            # bypassing the advertised reader with fixture-only implicit inputs.
            (exact_input,) = packet["inputs"]
            selected = json.loads(exact_input["content_text"])["members"]
            discovered = [core.KnowledgeRef.model_validate(ref) for ref in selected]
            assert tuple(discovered) == case.materials
            packet_materials[:] = discovered
            encoded = json.dumps(body, ensure_ascii=False)
            assert not any(
                marker in encoded
                for marker in (
                    "UNREAD_SOURCE_PREFIX",
                    "UNREAD_SOURCE_SUFFIX",
                    "UNREAD_ARTIFACT_PREFIX",
                    "UNREAD_ARTIFACT_SUFFIX",
                )
            )

        def route(body: dict[str, Any]) -> list[dict[str, Any]]:
            number = servers[0].calls
            if number > 1:
                output = last_output(body)
                remember(output)
            manifest = manifest_for(body, case)
            observed_manifests.append((str(manifest.record_id), manifest.revision))
            assert isinstance(manifest.state, core.ContextState)
            check_exposure(manifest.state.mandatory, case.materials, delivered)
            if 2 <= number <= 5:
                previous = contracts[number - 2]
                assert (output["adapter"], output["operation"]) == previous
                fields = output["schema"]["$defs"]["RuntimeMemorySelector"]["properties"]
                assert not {"current_activity", "format_keys", "use_period"}.intersection(fields)
                assert {"activity_ids", "format_refs", "date_from", "query_mode"}.issubset(fields)
            if number <= 4:
                adapter, operation = contracts[number - 1]
                return completed_response(
                    None,
                    call=(
                        "zara_integration",
                        {
                            "mode": "contract",
                            "adapter": adapter,
                            "operation": operation,
                        },
                    ),
                )
            if number == 5:
                return completed_response(
                    None,
                    call=(
                        "zara_data",
                        {
                            "mode": "apply",
                            "operation": "describe_structure",
                            "arguments": {
                                "activity_id": str(case.activity),
                                "work_id": str(case.work),
                            },
                        },
                    ),
                )
            if number == 6:
                assert output["structure"] == case.old_structure["structure"]
                assert output["structure"] != case.current_structure["structure"]
                selector.update(
                    activity_ids=[str(case.activity)],
                    format_refs=[output["state"]["formats"]["observation"]],
                    date_from="2026-01-02",
                    date_until="2026-01-03",
                    topics=["measurement"],
                )
                return completed_response(
                    None,
                    call=(
                        "zara_data",
                        {
                            "mode": "apply",
                            "operation": "query_entries",
                            "arguments": {"selectors": [selector]},
                        },
                    ),
                )
            if number == 7:
                query_result(output)
                return completed_response(
                    None,
                    call=(
                        "zara_integration",
                        {
                            "mode": "apply",
                            "adapter": "memory",
                            "operation": "catalog",
                            "contract_version": 1,
                            "arguments": {"selectors": [selector]},
                        },
                    ),
                )
            if number == 8:
                query_result(output, catalog=True)
                return completed_response(
                    None,
                    call=(
                        "zara_memory",
                        {
                            "mode": "read_batch",
                            "selectors": [selector],
                        },
                    ),
                )
            if number == 9:
                query_result(output)
                return completed_response(
                    None,
                    call=(
                        "zara_integration",
                        {
                            "mode": "apply",
                            "adapter": "memory",
                            "operation": "prepare_cache",
                            "contract_version": 1,
                            "arguments": {"selectors": [selector]},
                        },
                    ),
                )
            if number == 10:
                query_result(output)
                return completed_response(
                    None,
                    call=(
                        "zara_memory",
                        {
                            "mode": "open",
                            **packet_materials[0].model_dump(mode="json"),
                            "max_bytes": 5,
                        },
                    ),
                )
            if number == 11:
                assert output["record_kind"] == "source" and output["content_text"] == "αβ"
                assert output["next_offset"] == 4 and output["content_complete"] is False
                return completed_response(
                    None,
                    call=(
                        "zara_memory",
                        {
                            "mode": "open",
                            **packet_materials[1].model_dump(mode="json"),
                            "max_bytes": 5,
                        },
                    ),
                )
            if number == 12:
                assert output["record_kind"] == "artifact" and output["content_text"] == "packe"
                assert output["next_offset"] == 5 and output["content_complete"] is False
                return completed_response(
                    None,
                    call=(
                        "zara_memory",
                        {
                            "mode": "read_batch",
                            "material_refs": [
                                ref.model_dump(mode="json") for ref in packet_materials
                            ],
                            "max_bytes": 128,
                        },
                    ),
                )
            if number == 13:
                assert output["kind"] == "material_batch" and output["content_complete"] is True
                assert [item["record_kind"] for item in output["items"]] == ["source", "artifact"]
                assert [base64.b64decode(item["content_base64"]) for item in output["items"]] == [
                    "αβγ δεζ".encode(),
                    b"packet-one-two",
                ]
                return completed_response(
                    None,
                    call=(
                        "zara_memory",
                        {
                            "mode": "search",
                            "query": "Pacific/Chatham",
                            "query_mode": "text",
                            "limit": 8,
                        },
                    ),
                )
            if number == 14:
                assert output["query_mode"] == "text"
                assert any(item["record_id"] == str(case.search_source) for item in output["items"])
                assert "Artifact" not in str(output["coverage"])
                return completed_response(
                    None,
                    call=(
                        "zara_result",
                        {
                            "mode": "publish",
                            "slot": "report",
                            "content_text": "Fictional exact reads and scoped query checked.",
                        },
                    ),
                )
            assert number == 15 and "publication" in output
            return completed_response(
                "The fictional checked result is retained; acceptance is separate."
            )

        def guarded_route(body: dict[str, Any]) -> list[dict[str, Any]]:
            try:
                return route(body)
            except Exception:
                (directory / "provider-failure.txt").write_text(
                    traceback.format_exc(), encoding="utf-8"
                )
                raise

        provider = RawResponsesProvider([guarded_route] * 15, inspect_request=inspect_request)
        servers.append(provider)
        config = LaunchConfig.model_validate(
            {
                **config.model_dump(),
                "provider_base_url": f"http://127.0.0.1:{provider.server_port}/backend-api",
            }
        )
        write_config(config_path, config)
        sessions = directory / "sessions"
        run_process(
            personal,
            runtime,
            Bridge(case.root, case.owner, personal, workspace_config=config_path),
            provider,
            work=(case.activity, case.work),
            session_directory=sessions,
            prompt="Read the exact selected packet materials and the pinned dated observation.",
            provider_profile="codex-sse",
            local_model_id="gpt-6.1-sol",
            tool_names=INTERACTIVE_ZARA_TOOLS,
            expected_provider_calls=15,
            on_event=lambda _process, event: events.append(event),
            on_bridge_response=lambda path, payload: bridge_replies.append(
                {
                    "path": path,
                    "payload": payload,
                }
            ),
        )
        assert provider.calls == 15 and not provider.errors
        after = core.read_execution(case.root, case.work, case.owner)
        assert after.work.state.acceptance is None and len(after.work.state.linked_outputs) == 1
        assert not any(item.status == "active" for item in after.attempts)
        invocations = {str(item.invocation_id): item for item in after.invocations}
        deliveries = [
            core.read_context_delivery(case.root, item.invocation_id, case.owner)
            for item in after.invocations
        ]
        assert len(invocations) == len(deliveries) == provider.calls
        assert len(set(observed_manifests)) == len(observed_manifests)
        assert {
            (str(item["manifest_id"]), int(str(item["manifest_revision"]))) for item in deliveries
        } == (set(observed_manifests))
        for delivery in deliveries:
            invocation = invocations[str(delivery["invocation_id"])]
            assert delivery["stage"] == invocation.status == "answered"
            assert delivery["request_sha256"] == invocation.request_sha256
            assert delivery["correlation_state"] == "exact"
            assert delivery["context_work_id"] == str(case.work)
        assert any(event.get("type") == "agent_settled" for event in events)
        (directory / "deliveries.json").write_text(
            json.dumps(deliveries, indent=2), encoding="utf-8"
        )
        report.update(
            outcome="passed",
            native_processes=1,
            native_settled=True,
            pi_version=read_pi_runtime(runtime).version,
            localhost_http=provider.calls,
            all_runtime_contracts_executed=True,
            mixed_exact_materials=True,
            partial_bytes_only=True,
            old_work_structure_preserved=True,
            same_local_key_scopes_distinct=True,
            literal_punctuation_search=True,
            acceptance=False,
            committed_units=sum(item.usage_units or 0 for item in after.invocations),
        )
        return report
    except Exception as error:
        report.update(outcome="failed", error_type=type(error).__name__, error=str(error))
        (directory / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        report["localhost_http"] = sum(server.calls for server in servers)
        for filename, value in (
            ("report", report),
            ("native-events", events),
            ("bridge-replies", bridge_replies),
            ("observed-tool-outputs", observed_outputs),
            ("http-requests", [body for server in servers for body in server.requests]),
            ("wire-responses", [body for server in servers for body in server.wire_responses]),
            ("provider-errors", [error for server in servers for error in server.errors]),
        ):
            (directory / f"{filename}.json").write_text(
                json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--wheel", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    scratch = Path(__file__).resolve().parents[1] / "_scratch"
    if directory == scratch or not directory.is_relative_to(scratch):
        parser.error("Choose a new directory inside this checkout's _scratch")
    print(json.dumps(run(directory, args.runtime.resolve(), wheel=args.wheel), indent=2))


if __name__ == "__main__":
    main()
