"""Ordinary Pi Sleep and change trace with fictional local responses."""

from __future__ import annotations

import argparse
import json
import tempfile
import threading
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from tests.zaratustra.foundation.test_binding import _ready
from tools.probe_knowledge_pi import Provider, apply, run_process, source
from zaratustra.foundation import (
    AcceptWorkRequest,
    AssignAttemptRequest,
    ChangeCandidateState,
    ChangeDecisionState,
    ContextState,
    CreateCompositeWorkRequest,
    CreateResourceRequest,
    FoundationError,
    IssueChildWorkRequest,
    KnowledgeRef,
    LocalAuthority,
    MethodChange,
    MethodRef,
    ResourceState,
    SleepDelivery,
    SleepEffect,
    SleepRemainder,
    SleepSelection,
    SleepState,
    ValidationCriterion,
    ValidationPlanState,
    ValidationResultState,
    apply_operation,
    initial_sleep_method,
    initial_sleep_ref,
    list_change_applications,
    read_change_application,
    read_context_delivery,
    read_development,
    read_execution,
    read_knowledge,
    read_method_version,
    read_sleep_usage,
    read_space,
    read_work,
    sleep_work_template,
    upgrade_knowledge_space,
)
from zaratustra.foundation.composition import method_checksum
from zaratustra.pi_adapter import Bridge
from zaratustra.pi_adapter.assigned import EXECUTOR_VERSION, AssignedConfig, run_assigned


def development(intent: dict[str, object]) -> dict[str, object]:
    return {"_tool": "zara_development", "mode": "apply", "intent": intent}


def last_tool_receipt(body: dict[str, object]) -> dict[str, object]:
    messages = body.get("messages", [])
    assert isinstance(messages, list)
    tools = [item for item in messages if isinstance(item, dict) and item.get("role") == "tool"]
    assert tools
    receipt = json.loads(str(tools[-1]["content"]))
    assert isinstance(receipt, dict) and "operation_id" in receipt
    return receipt


def assigned_child(
    root: Path,
    space: UUID,
    owner: LocalAuthority,
    directory: Path,
    runtime: Path,
    parent_id: UUID,
    child_id: UUID,
    provider: Provider,
    *,
    issue: bool = True,
) -> None:
    if issue:
        apply_operation(
            root,
            IssueChildWorkRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                parent_work_id=parent_id,
                work_id=child_id,
                expected_plan_revision=1,
                expected_work_revision=read_work(root, child_id, owner).revision,
            ),
            owner,
        )
    resource_id = uuid4()
    apply_operation(
        root,
        CreateResourceRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            resource_id=resource_id,
            work_id=child_id,
            state=ResourceState(label="Fictional Sleep", root=directory, limit_units=10000),
        ),
        owner,
    )
    execution = read_execution(root, child_id, owner)
    assignment = AssignAttemptRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        attempt_id=uuid4(),
        work_id=child_id,
        expected_work_revision=execution.work.revision,
        resource_id=resource_id,
        expected_resource_revision=execution.resources[0].revision,
        session_id=uuid4(),
        executor_version=EXECUTOR_VERSION,
    )
    apply_operation(root, assignment, owner)
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    try:
        package = runtime / "node_modules" / "@earendil-works" / "pi-coding-agent"
        config = AssignedConfig(
            space=root,
            workspace=directory,
            pi_cli=package / "dist" / "bundle" / "cli.js",
            pi_runtime=runtime,
            node="node",
            provider_profile="local-completions",
            provider_base_url=f"http://127.0.0.1:{provider.server_port}/v1",
            provider_id="fictional-local",
            model_id="fictional-model",
            context_window=16384,
            max_tokens=512,
            reserve_units=1000,
            limit_units=10000,
            offline=True,
            pi_tools=("zara_memory", "zara_development"),
        )
        assert run_assigned(config, owner, assignment.attempt_id) == "proposed"
    finally:
        provider.shutdown()
        provider.server_close()
        provider_thread.join(timeout=5)


def run_probe(directory: Path, runtime: Path) -> None:
    root, space, owner, activity, _ = _ready(directory)
    upgrade_knowledge_space(root, owner)
    source_id, other_source_id = uuid4(), uuid4()
    start_id = uuid4()
    work_id = uuid5(start_id, "sleep-work")
    sleep_id = uuid5(start_id, "sleep-analysis")
    initial = Provider(
        [
            apply(source_id, source("Fictional review found an incomplete handoff.")),
            apply(
                other_source_id, source("Fictional planning note has no known link to the handoff.")
            ),
            {
                "_tool": "zara_development",
                "mode": "start_sleep",
                "start_id": str(start_id),
                "scope": "Review one fictional handoff and explore beyond its ready links",
                "scope_activity_ids": [str(activity)],
                "resource_limit_units": 10000,
            },
        ]
    )
    run_process(directory, runtime, Bridge(root, owner, directory, 10000), initial)
    assert read_space(root).schema_version == 11
    original = read_development(root, sleep_id, owner)
    assert isinstance(original.state, SleepState)
    selected = original.state.model_copy(
        update={
            "selected": (
                SleepSelection(
                    source=KnowledgeRef(record_id=source_id, revision=1), purpose="consolidation"
                ),
            ),
            "consolidation": "partial",
            "remainder": original.state.remainder,
        }
    )
    partial = Provider(
        [
            development(
                {
                    "kind": "revise_development",
                    "record_id": str(sleep_id),
                    "expected_revision": 1,
                    "state": selected.model_dump(mode="json"),
                }
            )
        ],
        final_content=json.dumps(
            {"zara": "final", "text": "Fictional consolidation remains partial."}
        ),
    )
    child_id = uuid5(start_id, "consolidation")
    assigned_child(root, space, owner, directory, runtime, work_id, child_id, partial)
    saved = read_development(root, sleep_id, owner)
    for model_request in partial.requests:
        for message in model_request.get("messages", []):
            if isinstance(message, dict) and message.get("role") == "tool":
                print(json.dumps({"tool_result": message.get("content")}, default=str)[:2500])
    print(json.dumps({"provider_calls": partial.calls, "saved_revision": saved.revision}))
    assert saved.revision == 2 and isinstance(saved.state, SleepState)
    spent, reserved = read_sleep_usage(root, work_id, owner)
    assert spent >= 100 and reserved == 0
    seen = []
    for invocation in read_execution(root, child_id, owner).invocations:
        delivery = read_context_delivery(root, invocation.invocation_id, owner)
        manifest = read_knowledge(root, UUID(str(delivery["manifest_id"])), owner)
        assert isinstance(manifest.state, ContextState)
        seen.append(
            {
                "stage": delivery["stage"],
                "source_in_manifest": source_id
                in {ref.record_id for ref in (*manifest.state.mandatory, *manifest.state.optional)},
            }
        )
    assert seen[-1]["source_in_manifest"] is True
    print(json.dumps({"phase": "partial", "spent": spent, "delivery": seen}))

    first_invocation = read_execution(root, child_id, owner).invocations[-1]
    first_context = read_context_delivery(root, first_invocation.invocation_id, owner)
    first_delivery = SleepDelivery(
        source=KnowledgeRef(record_id=source_id, revision=1),
        manifest=KnowledgeRef(
            record_id=UUID(str(first_context["manifest_id"])),
            revision=int(str(first_context["manifest_revision"])),
        ),
        invocation_id=first_invocation.invocation_id,
        stage="answered",
    )
    exploration_id = uuid5(start_id, "exploration")
    claim_id, analysis_id = uuid4(), uuid4()
    exploration_selected = saved.state.model_copy(
        update={
            "selected": saved.state.selected
            + (
                SleepSelection(
                    source=KnowledgeRef(record_id=other_source_id, revision=1),
                    purpose="exploration",
                ),
            ),
            "deliveries": (first_delivery,),
            "exploration": "partial",
            "remainder": (
                SleepRemainder(
                    kind="selected",
                    source=KnowledgeRef(record_id=source_id, revision=1),
                    description="Finish the selected consolidation question",
                ),
            ),
        }
    )

    def finish_sleep(body: dict[str, object]) -> dict[str, object]:
        analysis_receipt = last_tool_receipt(body)
        claim_receipt = last_tool_receipt(exploration.requests[-2])
        execution_two = read_execution(root, exploration_id, owner)
        delivered_invocation = execution_two.invocations[1]
        delivered = read_context_delivery(root, delivered_invocation.invocation_id, owner)
        second_delivery = SleepDelivery(
            source=KnowledgeRef(record_id=other_source_id, revision=1),
            manifest=KnowledgeRef(
                record_id=UUID(str(delivered["manifest_id"])),
                revision=int(str(delivered["manifest_revision"])),
            ),
            invocation_id=delivered_invocation.invocation_id,
            stage="answered",
        )
        completed = exploration_selected.model_copy(
            update={
                "deliveries": (first_delivery, second_delivery),
                "analyses": (KnowledgeRef(record_id=analysis_id, revision=1),),
                "effects": (
                    SleepEffect(
                        operation_id=UUID(str(claim_receipt["operation_id"])),
                        result=KnowledgeRef(record_id=claim_id, revision=1),
                    ),
                    SleepEffect(
                        operation_id=UUID(str(analysis_receipt["operation_id"])),
                        result=KnowledgeRef(record_id=analysis_id, revision=1),
                    ),
                ),
                "exploration": "no_material",
                "conclusion": "No relation found here; consolidation remains open.",
            }
        )
        return development(
            {
                "kind": "revise_development",
                "record_id": str(sleep_id),
                "expected_revision": 3,
                "state": completed.model_dump(mode="json"),
            }
        )

    exploration = Provider(
        [
            development(
                {
                    "kind": "revise_development",
                    "record_id": str(sleep_id),
                    "expected_revision": 2,
                    "state": exploration_selected.model_dump(mode="json"),
                }
            ),
            apply(
                claim_id,
                {
                    "kind": "claim",
                    "proposition": "The fictional handoff is incomplete",
                    "epistemic_kind": "reported",
                    "status": "current",
                    "scope_activity_id": str(activity),
                    "evidence": [{"record_id": str(source_id), "revision": 1}],
                    "interpretation_basis": "Exact fictional handoff source",
                },
            ),
            apply(
                analysis_id,
                {
                    "kind": "analysis",
                    "task": "Compare the unrelated planning note",
                    "inputs": [{"record_id": str(other_source_id), "revision": 1}],
                    "executor": "fictional-local-pi",
                    "status": "no_change",
                    "conclusion": "No concrete useful relation in the selected note",
                },
            ),
            finish_sleep,
        ],
        final_content=json.dumps(
            {"zara": "final", "text": "Bounded exploration found no relation."}
        ),
    )
    assigned_child(root, space, owner, directory, runtime, work_id, exploration_id, exploration)
    final_sleep = read_development(root, sleep_id, owner)
    assert final_sleep.revision == 4 and isinstance(final_sleep.state, SleepState)
    assert len(final_sleep.state.effects) == 2
    total_spent, held = read_sleep_usage(root, work_id, owner)
    assert total_spent > spent and held == 0
    print(
        json.dumps(
            {"phase": "resumed", "spent": total_spent, "effects": len(final_sleep.state.effects)}
        )
    )

    seed = initial_sleep_ref(space)
    assert read_method_version(root, seed, owner).definition == initial_sleep_method()
    revised_definition = initial_sleep_method().model_copy(
        update={
            "instruction": initial_sleep_method().instruction
            + " Preserve exact negative experience and the return condition."
        }
    )
    revised_checksum = method_checksum(revised_definition)
    assert revised_checksum != seed.checksum
    assert revised_definition.named_outputs == initial_sleep_method().named_outputs
    assert revised_definition.obligations == initial_sleep_method().obligations
    check_id, candidate_id, decision_id, result_id = (uuid4() for _ in range(4))
    development_activity = uuid5(space, "zaratustra-development-activity")
    candidate = ChangeCandidateState(
        target=MethodChange(
            method_id=seed.method_id,
            from_version=1,
            from_checksum=seed.checksum,
            to_version=2,
            definition=revised_definition,
        ),
        proposal="Preserve a negative result and its return condition in the Sleep instruction",
        evidence=(
            KnowledgeRef(record_id=sleep_id, revision=4),
            KnowledgeRef(record_id=check_id, revision=1),
        ),
        expected_outcome="New Work pins the exact revised instruction",
        scope_activity_ids=(development_activity,),
        exclusions="Other Activities do not receive this Method admission",
        impact="New Work only; the existing Sleep Work remains pinned to version 1",
        affected_work_ids=(work_id,),
        unknowns="Practical usefulness is not yet observed",
        validation_plan=ValidationPlanState(
            baseline="Exact original Sleep Method version 1",
            environment="Synthetic local Core and Pi",
            criteria=(
                ValidationCriterion(
                    key="structure",
                    question="Does the proposed version preserve output and obligations?",
                    pass_condition="Exact checksum differs while outputs and obligations are equal",
                    basis=(KnowledgeRef(record_id=check_id, revision=1),),
                ),
            ),
            cases="Compare the exact shipped Method definitions",
            method="Read version 1 and compare typed definition fields and checksum",
            sufficiency="One structural instruction change has direct exact checks",
            limits="No claim of practical usefulness",
            stop_and_restore="Stop new use and return to the original version",
            decision_condition="Current Decision and Grant in development Activity",
            follow_up="Inspect the next Work and later observed result",
        ),
        results=(
            ValidationResultState(
                result_id=result_id,
                criterion="structure",
                outcome="met",
                evidence=(KnowledgeRef(record_id=check_id, revision=1),),
                actual_input="Method v1 and proposed v2 exact definitions",
                environment="Synthetic local Core",
            ),
        ),
        restore_plan="Block new v2 Work and retain existing pinned Work history",
        irreversible_effects="Started Work remains; no external effects in this probe",
    )
    changed_work_id = uuid4()
    changed_method = MethodRef(method_id=seed.method_id, version=2, checksum=revised_checksum)
    changed_work, changed_plan = sleep_work_template(
        activity_id=development_activity,
        method=changed_method,
        work_id=changed_work_id,
        consolidation_id=uuid4(),
        exploration_id=uuid4(),
        scope="Use the checked synthetic Method revision",
    )
    adoption = Provider(
        [
            apply(
                check_id,
                source("Structural check: v1 read; v2 checksum differs; obligations match."),
            ),
            development(
                {
                    "kind": "create_development",
                    "record_id": str(candidate_id),
                    "state": candidate.model_dump(mode="json"),
                }
            ),
            development(
                {
                    "kind": "create_decision",
                    "decision_id": str(decision_id),
                    "state": ChangeDecisionState(
                        statement="Admit checked Method v2 in the development Activity",
                        candidate_id=candidate_id,
                        candidate_revision=1,
                        mode="regular",
                        use="recommended",
                        scope_activity_id=development_activity,
                        validation_result_ids=(result_id,),
                        review_condition="Inspect the next Work result",
                    ).model_dump(mode="json"),
                }
            ),
            development(
                {
                    "kind": "apply_candidate",
                    "candidate_id": str(candidate_id),
                    "candidate_revision": 1,
                    "decision_id": str(decision_id),
                    "decision_revision": 1,
                    "mode": "regular",
                }
            ),
            development(
                {
                    "kind": "create_composite_work",
                    "work_id": str(changed_work_id),
                    "state": changed_work.model_dump(mode="json"),
                    "plan": changed_plan.model_dump(mode="json"),
                }
            ),
        ]
    )
    run_process(directory, runtime, Bridge(root, owner, directory, 10000), adoption)
    applications = [
        item for item in list_change_applications(root, owner) if item.candidate_id == candidate_id
    ]
    assert len(applications) == 1 and applications[0].status == "active"
    application = applications[0]
    assert read_work(root, changed_work_id, owner).state.method == changed_method
    print(
        json.dumps(
            {
                "phase": "applied",
                "application": str(application.application_id),
                "next_work": str(changed_work_id),
            }
        )
    )

    for child in changed_plan.children:
        print(json.dumps({"phase": "next_child_start", "role": child.role}))
        child_provider = Provider(
            [],
            final_content=json.dumps(
                {
                    "zara": "final",
                    "text": f"Fictional result for {child.role}",
                }
            ),
        )
        assigned_child(
            root, space, owner, directory, runtime, changed_work_id, child.work_id, child_provider
        )
        assert child_provider.calls == 1
        assert "Preserve exact negative experience" in json.dumps(child_provider.requests[0])
        apply_operation(
            root,
            AcceptWorkRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                work_id=child.work_id,
                expected_revision=read_work(root, child.work_id, owner).revision,
                basis=f"Checked fictional {child.role} result",
            ),
            owner,
        )
    print(
        json.dumps(
            {
                "phase": "used",
                "child_http": 2,
                "pinned_method": changed_method.model_dump(mode="json"),
            }
        )
    )

    stopped = Provider(
        [
            development(
                {
                    "kind": "stop_candidate",
                    "application_id": str(application.application_id),
                    "expected_revision": 1,
                    "reason": "Pause new uses while a fictional downstream result is reviewed",
                    "started_works": f"Work {changed_work_id} stays pinned for separate review",
                    "external_effects": "None in this synthetic local probe",
                }
            )
        ]
    )
    run_process(directory, runtime, Bridge(root, owner, directory, 10000), stopped)
    assert read_change_application(root, application.application_id, owner)[0].status == "stopped"
    blocked_work_id = uuid4()
    blocked_work, blocked_plan = sleep_work_template(
        activity_id=development_activity,
        method=changed_method,
        work_id=blocked_work_id,
        consolidation_id=uuid4(),
        exploration_id=uuid4(),
        scope="This new use must be blocked",
    )
    try:
        apply_operation(
            root,
            CreateCompositeWorkRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                work_id=blocked_work_id,
                state=blocked_work,
                plan=blocked_plan,
            ),
            owner,
        )
    except FoundationError as error:
        assert error.code == "change_stopped"
    else:
        raise AssertionError("Stopped Method admitted a new Work")

    negative_id = uuid4()
    late = Provider(
        [
            apply(
                negative_id,
                source("Fictional result: revised instruction did not improve the output."),
            ),
            development(
                {
                    "kind": "record_change_outcome",
                    "application_id": str(application.application_id),
                    "expected_revision": 2,
                    "outcome": "negative",
                    "evidence": [{"record_id": str(negative_id), "revision": 1}],
                    "observation": "Synthetic later result retained after stopping new use",
                }
            ),
        ]
    )
    run_process(directory, runtime, Bridge(root, owner, directory, 10000), late)
    prior_work_id = uuid4()
    prior_work, prior_plan = sleep_work_template(
        activity_id=development_activity,
        method=seed,
        work_id=prior_work_id,
        consolidation_id=uuid4(),
        exploration_id=uuid4(),
        scope="Return to the exact original Method",
    )
    restored = Provider(
        [
            development(
                {
                    "kind": "restore_candidate",
                    "application_id": str(application.application_id),
                    "expected_revision": 3,
                    "reason": "Return new uses to v1 after the synthetic negative note",
                    "data_restoration": "No user data was changed by this Method revision",
                    "external_effects": "None; already started Work remains pinned to v2",
                }
            ),
            development(
                {
                    "kind": "create_composite_work",
                    "work_id": str(prior_work_id),
                    "state": prior_work.model_dump(mode="json"),
                    "plan": prior_plan.model_dump(mode="json"),
                }
            ),
        ]
    )
    run_process(directory, runtime, Bridge(root, owner, directory, 10000), restored)
    after, history = read_change_application(root, application.application_id, owner)
    assert after.status == "restored" and after.revision == 4
    assert [item["kind"] for item in history] == ["apply", "stop", "outcome", "restore"]
    assert read_work(root, prior_work_id, owner).state.method == seed
    assert read_work(root, changed_work_id, owner).state.method == changed_method
    print(
        json.dumps(
            {"phase": "restored", "history": len(history), "original_work": str(prior_work_id)}
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi-runtime", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="zara-development-pi-") as directory:
        run_probe(Path(directory), args.pi_runtime.resolve())
    print("ordinary Pi Sleep and change probe: passed")


if __name__ == "__main__":
    main()
