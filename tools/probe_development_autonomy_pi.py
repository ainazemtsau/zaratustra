"""Autonomous development saves and separate owner actions through ordinary Pi."""

from __future__ import annotations

import argparse
import base64
import json
import tempfile
from pathlib import Path
from uuid import uuid4

# Admit the configured SQLite runtime before importing development fixtures.
from zaratustra.foundation import (
    ChangeCandidateState,
    FoundationError,
    MethodDefinition,
    MethodRef,
    OutputContract,
    initial_sleep_method,
    initial_sleep_ref,
    read_artifact,
    read_development,
    read_knowledge,
    read_method_version,
    read_work,
    upgrade_development_space,
    upgrade_knowledge_space,
)
from zaratustra.pi_adapter import Bridge

# isort: split
from tests.zaratustra.foundation.test_binding import _ready
from tools.probe_knowledge_pi import Provider, apply, run_process, source


def run_probe(tmp_path: Path, runtime: Path) -> dict[str, object]:
    root, space, owner, activity, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    upgrade_development_space(root, owner)
    method_id = initial_sleep_ref(space).method_id
    proposed_method_id, work_id, resource_id = (uuid4() for _ in range(3))
    source_id, analysis_id, candidate_id, artifact_id = (uuid4() for _ in range(4))
    output = {"slot": "report", "media_type": "text/plain"}
    definition = MethodDefinition(
        instruction="Prepare a fictional proposal and save its evidence for owner review.",
        named_outputs=(OutputContract(**output),),
        source_ref="fictional-development-probe",
    ).model_dump(mode="json")
    evidence = {"record_id": str(source_id), "revision": 1}
    candidate = {
        "kind": "candidate",
        "target": {
            "kind": "method",
            "method_id": str(proposed_method_id),
            "to_version": 1,
            "definition": definition,
        },
        "proposal": "Try a fictional revised workflow after owner review.",
        "evidence": [evidence],
        "expected_outcome": "A saved proposal with inspectable validation.",
        "scope_activity_ids": [str(activity)],
        "exclusions": "Other Activities",
        "impact": "Future Work only after separate adoption",
        "unknowns": "Usefulness is not established",
        "restore_plan": "Retain the current workflow",
        "irreversible_effects": "None in this fictional proposal",
    }
    plan = {
        "baseline": "Fictional current workflow",
        "environment": "Disposable local Core",
        "criteria": [
            {
                "key": "saved",
                "question": "Is the original saved?",
                "pass_condition": "Exact Source bytes are readable",
                "basis": [evidence],
            }
        ],
        "cases": "Read one original",
        "method": "Core exact read",
        "sufficiency": "Direct structural observation",
        "limits": "No model quality claim",
        "stop_and_restore": "Do not adopt the proposal",
        "decision_condition": "Separate owner action",
        "follow_up": "Owner reviews the saved result",
    }
    revised = {
        **candidate,
        "validation_plan": plan,
        "results": [
            {
                "result_id": str(uuid4()),
                "criterion": "saved",
                "outcome": "met",
                "evidence": [evidence],
                "actual_input": "Fictional original",
                "environment": "Disposable local Core",
            }
        ],
    }

    def development(kind: str, **fields: object) -> dict[str, object]:
        return {"_tool": "zara_development", "mode": "apply", "intent": {"kind": kind, **fields}}

    writes = Provider(
        [
            apply(source_id, source("Fictional original for unattended development.")),
            apply(
                analysis_id,
                {
                    "kind": "analysis",
                    "task": "Inspect the fictional original",
                    "inputs": [evidence],
                    "executor": "fictional-agent",
                    "status": "result",
                    "conclusion": "Original is addressable",
                },
            ),
            development(
                "create_method",
                method_id=str(method_id),
                version=1,
                definition=initial_sleep_method().model_dump(mode="json"),
            ),
            development(
                "create_work",
                work_id=str(work_id),
                state={
                    "activity_id": str(activity),
                    "goal": "Save a fictional addressed proposal",
                    "expected_outputs": [output],
                },
            ),
            development(
                "register_resource",
                resource_id=str(resource_id),
                work_id=str(work_id),
                state={"label": "Fictional local work", "root": str(tmp_path)},
            ),
            development(
                "create_artifact",
                artifact_id=str(artifact_id),
                media_type="text/plain",
                content=base64.b64encode(b"Fictional development report").decode(),
            ),
            development(
                "link_work_output",
                work_id=str(work_id),
                expected_revision=1,
                output={
                    "slot": "report",
                    "artifact": {"artifact_id": str(artifact_id), "revision": 1},
                },
            ),
            development("create_development", record_id=str(candidate_id), state=candidate),
            development(
                "revise_development",
                record_id=str(candidate_id),
                expected_revision=1,
                state=revised,
            ),
        ]
    )
    # An unexpected Yes/No fails run_process immediately. No automatic answers.
    run_process(tmp_path, runtime, Bridge(root, owner, tmp_path), writes)
    assert read_work(root, work_id, owner).state.acceptance is None
    assert read_artifact(root, artifact_id, owner).content == b"Fictional development report"
    assert (
        read_method_version(root, initial_sleep_ref(space), owner).definition
        == initial_sleep_method()
    )
    saved = read_development(root, candidate_id, owner)
    assert saved.revision == 2 and isinstance(saved.state, ChangeCandidateState)
    assert saved.state.model_dump(
        mode="json", exclude_defaults=True
    ) == ChangeCandidateState.model_validate(revised).model_dump(mode="json", exclude_defaults=True)
    assert read_development(root, candidate_id, owner, revision=1).revision == 1
    assert read_knowledge(root, analysis_id, owner).availability == "available"

    reopened = Provider(
        [
            {"_tool": "zara_development", "mode": "read", "record_id": str(candidate_id)},
            {"mode": "open", "record_id": str(source_id), "revision": 1},
        ]
    )
    events = run_process(tmp_path, runtime, Bridge(root, owner, tmp_path), reopened)
    assert any(
        str(candidate_id) in json.dumps(event) and "validation_plan" in json.dumps(event)
        for event in events
        if event.get("type") == "tool_execution_end"
    )
    assert (
        read_work(root, work_id, owner).state.linked_outputs[0].artifact.artifact_id == artifact_id
    )

    acceptance = development(
        "accept_work",
        work_id=str(work_id),
        expected_revision=2,
        basis="Fictional explicit owner review",
    )
    deletion = development("delete_development", record_id=str(candidate_id), expected_revision=2)
    refused = Provider(
        [
            acceptance,
            deletion,
            development(
                "create_decision",
                decision_id=str(uuid4()),
                state={
                    "statement": "Fictional owner decision",
                    "effect": "deny",
                    "actions": ["record.write"],
                },
            ),
            development(
                "apply_candidate",
                candidate_id=str(candidate_id),
                candidate_revision=2,
                decision_id=str(uuid4()),
                decision_revision=1,
                mode="regular",
            ),
        ]
    )
    run_process(
        tmp_path,
        runtime,
        Bridge(root, owner, tmp_path),
        refused,
        confirmation_answers=(False, False, False, False),
    )
    assert read_work(root, work_id, owner).state.acceptance is None
    assert read_development(root, candidate_id, owner).availability == "available"
    try:
        read_method_version(
            root, MethodRef(method_id=proposed_method_id, version=1, checksum="0" * 64), owner
        )
    except FoundationError as error:
        assert error.code == "method_unavailable"
    else:
        raise AssertionError("Saving a Candidate applied its proposed Method")
    approved = Provider([acceptance, deletion])
    run_process(
        tmp_path,
        runtime,
        Bridge(root, owner, tmp_path),
        approved,
        confirmation_answers=(True, True),
    )
    assert read_work(root, work_id, owner).state.acceptance is not None
    assert read_development(root, candidate_id, owner).availability == "deleted"
    return {
        "routine_confirmations": 0,
        "owner_confirmations": 6,
        "restart_read": True,
        "candidate_did_not_apply": True,
        "synthetic_http_calls": sum(p.calls for p in (writes, reopened, refused, approved)),
        "real_model_calls": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi-runtime", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(
        prefix="development-pi-", dir=Path.cwd() / "_scratch"
    ) as directory:
        result = run_probe(Path(directory), args.pi_runtime.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
