"""Live schema 7 continuation through ordinary Pi RPC, DBOS and localhost SSE.

All subject text is fictional. This development probe creates one new disposable
space and reports provider HTTP after every meaningful step.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from tools.probe_stage6_rpc import (
    ISOLATED_UTF8,
    SyntheticProvider,
    _apply,
    _assign,
    _contains,
    _issue,
    _refusal,
    _space,
    _technical_copies,
    status_via_pi,
)
from zaratustra.foundation import (
    AcceptWorkRequest,
    ArtifactRef,
    ChoiceApplicability,
    ChoiceState,
    ConfirmObligationRequest,
    CreateArtifactRequest,
    CreateCompositeWorkRequest,
    CreateDecisionRequest,
    CreateMethodVersionRequest,
    CreateResourceRequest,
    DecisionRef,
    DecisionScope,
    DeleteArtifactRequest,
    DeleteWorkRequest,
    ExceptionState,
    FoundationError,
    LinkedOutput,
    LinkWorkOutputRequest,
    MethodDefinition,
    MethodObligation,
    MethodRef,
    NamedInput,
    NodeClosure,
    ObligationMapping,
    ObligationTarget,
    OutputContract,
    PlanChild,
    PlanCondition,
    PlanNodeDecision,
    PlanOutputBinding,
    PremiseChange,
    RecoverRequest,
    ResolveObligationApplicabilityRequest,
    ResourceState,
    RevalidateResultRequest,
    ReviseActivePlanRequest,
    ReviseArtifactRequest,
    WaiveObligationRequest,
    WorkPlan,
    WorkState,
    apply_operation,
    authorize_local,
    authorize_recovery,
    read_execution,
    read_obligation,
    read_plan_method,
    read_plan_nodes,
    read_work,
    read_work_plan,
    read_work_status,
    restore_backup,
    upgrade_plan_revision_space,
)
from zaratustra.pi_adapter import Bridge
from zaratustra.pi_adapter.assigned import (
    AssignedConfig,
    complete_assigned_deletions,
    create_assigned_backup,
    deliver_outbox,
    run_assigned,
)


def _method(
    root: Path, owner: Any, method_id: UUID, version: int, definition: MethodDefinition
) -> MethodRef:
    receipt = _apply(
        root,
        owner,
        CreateMethodVersionRequest,
        method_id=method_id,
        version=version,
        definition=definition,
    )
    return MethodRef(method_id=method_id, version=version, checksum=str(receipt.result["checksum"]))


def _accept(root: Path, owner: Any, work: UUID, basis: str) -> Any:
    return _apply(
        root,
        owner,
        AcceptWorkRequest,
        work_id=work,
        expected_revision=read_work(root, work, owner).revision,
        basis=basis,
    )


def _issue_now(root: Path, owner: Any, parent: UUID, child: UUID) -> None:
    apply_operation(
        root,
        _issue(root, owner, parent, child, read_work_plan(root, parent, owner).revision),
        owner,
    )


def _confirm(
    root: Path, owner: Any, parent: UUID, key: str, evidence: ArtifactRef, basis: str
) -> Any:
    return _apply(
        root,
        owner,
        ConfirmObligationRequest,
        work_id=parent,
        key=key,
        expected_plan_revision=read_work_plan(root, parent, owner).revision,
        expected_obligation_revision=read_obligation(root, parent, key, owner).revision,
        evidence=evidence,
        basis=basis,
    )


def _link(root: Path, owner: Any, work: UUID, slot: str, artifact: ArtifactRef) -> None:
    _apply(
        root,
        owner,
        LinkWorkOutputRequest,
        work_id=work,
        expected_revision=read_work(root, work, owner).revision,
        output=LinkedOutput(slot=slot, artifact=artifact),
    )


def _result(root: Path, owner: Any, work: UUID) -> ArtifactRef:
    output = read_execution(root, work, owner).outputs[0]
    return ArtifactRef(artifact_id=output.artifact_id, revision=output.revision)


def _run(output: Path, pi_runtime: Path) -> dict[str, object]:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    token = uuid4().hex[:12]
    markers = {
        "plan": f"fictional-plan-{token}",
        "basis": f"fictional-basis-{token}",
        "exception": f"fictional-exception-{token}",
        "question": f"Which fictional line? [{token}-q]",
        "answer": f"The first fictional line [{token}-a]",
        "partial": f"Two fictional lines [{token}-p]",
        "a": f"Checked fictional line [{token}-ra]",
        "b": f"Summarized fictional line [{token}-rb]",
        "g": f"Nested fictional result [{token}-rg]",
    }
    responses = (
        json.dumps(
            {
                "zara": "wait",
                "partial": markers["partial"],
                "question": markers["question"],
                "remainder": "Finish the fictional summary",
            }
        ),
        json.dumps({"zara": "final", "text": markers["a"]}),
        json.dumps({"zara": "final", "text": markers["b"]}),
        json.dumps({"zara": "final", "text": markers["g"]}),
    )
    provider = SyntheticProvider(responses)
    server = threading.Thread(target=provider.serve_forever, daemon=True)
    server.start()
    report: dict[str, object] = {"status": "started", "http_steps": []}
    try:
        data = _space(output)
        root, owner = cast(Path, data["root"]), data["owner"]
        assert upgrade_plan_revision_space(root, owner).schema_version == 7
        activity, source = cast(UUID, data["activity"]), cast(UUID, data["source"])
        source_ref = ArtifactRef(artifact_id=source, revision=1)
        parent, a, b, art, art2, nested, grandchild = (uuid4() for _ in range(7))
        premise = uuid4()
        _apply(
            root,
            owner,
            CreateArtifactRequest,
            artifact_id=premise,
            media_type="text/plain",
            content=b"first fictional premise",
        )
        premise_ref = ArtifactRef(artifact_id=premise, revision=1)
        final = OutputContract(slot="final", media_type="text/plain")
        checked = OutputContract(slot="checked", media_type="text/plain")
        reviewed = OutputContract(slot="reviewed", media_type="text/plain")
        nested_method = _method(
            root,
            owner,
            uuid4(),
            1,
            MethodDefinition(
                instruction="Integrate the fictional grandchild",
                named_outputs=(final,),
                obligations=(
                    MethodObligation(
                        key="g_final",
                        source="nested fictional source",
                        role="g",
                        slot="final",
                        media_type="text/plain",
                    ),
                ),
                source_ref="fictional-nested-method",
            ),
        )
        method_id = uuid4()
        v1_definition = MethodDefinition(
            instruction="Integrate independent fictional branches",
            named_inputs=(OutputContract(slot="source", media_type="text/plain"),),
            named_outputs=(final,),
            obligations=(
                MethodObligation(
                    key="checked",
                    source="fictional check",
                    role="a",
                    slot="checked",
                    media_type="text/plain",
                ),
                MethodObligation(
                    key="final",
                    source="fictional final",
                    role="b",
                    slot="final",
                    media_type="text/plain",
                ),
                MethodObligation(
                    key="art_review",
                    source="fictional conditional",
                    role="art",
                    slot="reviewed",
                    media_type="text/plain",
                    applicability=ChoiceApplicability(
                        choice="art_needed", active=("yes",), inactive=("no",)
                    ),
                ),
            ),
            source_ref="fictional-parent-method-v1",
        )
        v1 = _method(root, owner, method_id, 1, v1_definition)
        v2_definition = v1_definition.model_copy(
            update={
                "instruction": "Integrate the nested fictional branch",
                "source_ref": "fictional-parent-method-v2",
                "obligations": (
                    v1_definition.obligations[0].model_copy(update={"key": "checked_v2"}),
                    v1_definition.obligations[1].model_copy(update={"key": "final_v2"}),
                    v1_definition.obligations[2],
                    MethodObligation(
                        key="nested_final",
                        source="fictional nested",
                        role="nested",
                        slot="final",
                        media_type="text/plain",
                    ),
                ),
            }
        )
        v2 = _method(root, owner, method_id, 2, v2_definition)
        a_node = PlanChild(
            role="a",
            work_id=a,
            state=WorkState(
                activity_id=activity,
                goal="Check a fictional line",
                inputs=(premise_ref,),
                expected_outputs=(checked,),
            ),
        )
        b_node = PlanChild(
            role="b",
            work_id=b,
            state=WorkState(
                activity_id=activity, goal="Summarize a fictional line", expected_outputs=(final,)
            ),
        )
        art_node = PlanChild(
            role="art",
            work_id=art,
            state=WorkState(
                activity_id=activity, goal="Review fictional art", expected_outputs=(reviewed,)
            ),
        )
        original = WorkPlan(
            named_inputs=(NamedInput(slot="source", artifact=source_ref),),
            output_bindings=(
                PlanOutputBinding(
                    parent_slot="final", role="b", child_slot="final", media_type="text/plain"
                ),
            ),
            children=(a_node, b_node, art_node),
            completion=PlanCondition(
                kind="all",
                members=(
                    PlanCondition(kind="work_succeeded", role="a"),
                    PlanCondition(kind="work_succeeded", role="b"),
                ),
            ),
            basis=(source_ref,),
            rationale=markers["plan"],
            source_ref="fictional-plan-v1",
        )
        _apply(
            root,
            owner,
            CreateCompositeWorkRequest,
            work_id=parent,
            state=WorkState(
                activity_id=activity,
                goal="Integrate fictional packet",
                inputs=(source_ref,),
                expected_outputs=(final,),
                method=v1,
            ),
            plan=original,
        )
        package = pi_runtime.resolve() / "node_modules" / "@earendil-works" / "pi-coding-agent"
        base_config = AssignedConfig(
            space=root,
            workspace=output / "workspace-b",
            pi_cli=package / "dist" / "bundle" / "cli.js",
            pi_runtime=pi_runtime.resolve(),
            node="node",
            provider_profile="local-completions",
            provider_base_url=f"http://127.0.0.1:{provider.server_port}/v1",
            provider_id="zara-synthetic",
            model_id="synthetic-model",
            context_window=4096,
            max_tokens=512,
            reserve_units=1000,
            limit_units=10000,
            offline=True,
        )
        workspaces = {
            "a": output / "workspace-a",
            "b": base_config.workspace,
            "art": base_config.workspace,
            "g": output / "workspace-g",
        }
        for workspace in set(workspaces.values()):
            workspace.mkdir(exist_ok=True)

        def config(role: str) -> AssignedConfig:
            return AssignedConfig(**{**base_config.__dict__, "workspace": workspaces[role]})

        def mark(step: str) -> None:
            cast(list[dict[str, object]], report["http_steps"]).append(
                {
                    "step": step,
                    "total": len(provider.digests),
                    "parent": read_work_status(root, parent, owner).status,
                    "a": read_work_status(root, a, owner).status,
                    "b": read_work_status(root, b, owner).status,
                }
            )

        _issue_now(root, owner, parent, a)
        _issue_now(root, owner, parent, b)
        _issue_now(root, owner, parent, art)
        for role, work in (("a", a), ("b", b), ("art", art)):
            _apply(
                root,
                owner,
                CreateResourceRequest,
                resource_id=uuid4(),
                work_id=work,
                state=ResourceState(
                    label=f"Fictional {role}", root=workspaces[role], limit_units=10000
                ),
            )
        b_assign = _assign(root, owner, b)
        apply_operation(root, b_assign, owner)
        assigned_input = output / "assigned-b.json"
        assigned_input.write_text(
            json.dumps(
                {
                    "space": str(root),
                    "attempt": str(b_assign.attempt_id),
                    "config": {
                        key: str(value) if isinstance(value, Path) else value
                        for key, value in config("b").__dict__.items()
                    },
                }
            ),
            encoding="utf-8",
        )
        b_out_path, b_err_path = output / "assigned-b.out", output / "assigned-b.err"
        with b_out_path.open("wb") as b_out, b_err_path.open("wb") as b_err:
            b_worker = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "tools.probe_stage6_pass3",
                    "--assigned",
                    str(assigned_input),
                ],
                cwd=Path(__file__).resolve().parents[1],
                stdout=b_out,
                stderr=b_err,
            )
        deadline = time.monotonic() + 45
        wait = None
        while time.monotonic() < deadline:
            if b_worker.poll() is not None:
                raise RuntimeError(b_err_path.read_text(encoding="utf-8", errors="replace")[-6000:])
            try:
                b_snapshot = read_execution(root, b, owner)
                wait = next(
                    (item for item in b_snapshot.waits if item.status == "open"),
                    None,
                )
                if b_snapshot.assignments and b_snapshot.assignments[-1].status == "unknown":
                    b_worker.terminate()
                    b_worker.wait(timeout=10)
                    raise RuntimeError(
                        "B became unknown before wait; "
                        + b_err_path.read_text(encoding="utf-8", errors="replace")[-6000:]
                    )
            except FoundationError as error:
                if error.code not in ("busy", "storage"):
                    raise
            if wait is not None:
                break
            time.sleep(0.1)
        if wait is None:
            b_worker.terminate()
            b_worker.wait(timeout=10)
            raise AssertionError(
                "B did not wait; "
                + b_err_path.read_text(encoding="utf-8", errors="replace")[-6000:]
            )
        assert len(provider.digests) == 1
        mark("B waiting for addressed answer")
        art_assign = _assign(root, owner, art)
        assert _refusal(lambda: apply_operation(root, art_assign, owner)) == "resource_busy"
        mark("shared resource conflict, no HTTP")
        a_assign = _assign(root, owner, a)
        apply_operation(root, a_assign, owner)
        a_run = run_assigned(config("a"), owner, a_assign.attempt_id)
        a_output = _result(root, owner, a)
        _accept(root, owner, a, markers["basis"] + " A")
        assert len(provider.digests) == 2
        mark("A result accepted while B waits")
        _apply(
            root,
            owner,
            ReviseArtifactRequest,
            artifact_id=premise,
            expected_revision=1,
            media_type="text/plain",
            content=b"corrected fictional premise",
        )
        premise_status = read_work_status(root, a, owner)
        assert any(item.code == "premise_changed" for item in premise_status.reasons)
        recheck = _apply(
            root,
            owner,
            RevalidateResultRequest,
            parent_work_id=parent,
            role="a",
            work_id=a,
            outputs=read_work(root, a, owner).state.linked_outputs,
            expected_plan_revision=1,
            premises=(PremiseChange(kind="artifact", record_id=premise, revision=1, current=2),),
            basis=markers["basis"] + " revalidation",
        )
        parent_view = read_execution(root, parent, owner).composition
        assert parent_view is not None and parent_view.children[0].revalidation == 1
        mark("premise corrected and result revalidated")
        # Free the shared root by assigning Art before B instead of after it: the
        # conflict above is sufficient; the fenced Attempt uses a distinct root.
        workspaces["art"] = output / "workspace-art"
        workspaces["art"].mkdir()
        _apply(
            root,
            owner,
            CreateResourceRequest,
            resource_id=uuid4(),
            work_id=art,
            state=ResourceState(
                label="Fictional art independent root", root=workspaces["art"], limit_units=10000
            ),
        )
        art_snapshot = read_execution(root, art, owner)
        art_resource = next(
            item for item in art_snapshot.resources if item.state.root == workspaces["art"]
        )
        art_assign = _assign(root, owner, art).model_copy(
            update={
                "resource_id": art_resource.resource_id,
                "expected_resource_revision": art_resource.revision,
            }
        )
        apply_operation(root, art_assign, owner)
        art2_node = art_node.model_copy(update={"work_id": art2})
        g_node = PlanChild(
            role="g",
            work_id=grandchild,
            state=WorkState(
                activity_id=activity,
                goal="Produce fictional nested result",
                expected_outputs=(final,),
            ),
        )
        nested_plan = WorkPlan(
            children=(g_node,),
            output_bindings=(
                PlanOutputBinding(
                    parent_slot="final", role="g", child_slot="final", media_type="text/plain"
                ),
            ),
            completion=PlanCondition(kind="work_succeeded", role="g"),
            rationale=markers["plan"] + " nested",
            source_ref="fictional-nested-plan",
        )
        nested_node = PlanChild(
            role="nested",
            work_id=nested,
            state=WorkState(
                activity_id=activity,
                goal="Integrate fictional grandchild",
                expected_outputs=(final,),
                method=nested_method,
            ),
        )
        revised = original.model_copy(
            update={
                "children": (a_node, b_node, art2_node, nested_node),
                "completion": PlanCondition(
                    kind="all",
                    members=tuple(
                        PlanCondition(kind="work_succeeded", role=role)
                        for role in ("a", "b", "nested")
                    ),
                ),
                "rationale": markers["plan"] + " revision 2",
            }
        )
        replacement = _apply(
            root,
            owner,
            ReviseActivePlanRequest,
            work_id=parent,
            expected_plan_revision=1,
            expected_work_revision=read_work(root, parent, owner).revision,
            plan=revised,
            nodes=(
                PlanNodeDecision(role="a", decision="keep", work_id=a),
                PlanNodeDecision(role="b", decision="keep", work_id=b),
                PlanNodeDecision(
                    role="art",
                    decision="replace",
                    work_id=art,
                    replacement=art2,
                    closure=NodeClosure(
                        expected_revision=read_work(root, art, owner).revision,
                        outcome="cancelled",
                        basis=markers["basis"] + " fence",
                    ),
                ),
                PlanNodeDecision(
                    role="nested", decision="add", work_id=nested, nested_plan=nested_plan
                ),
            ),
        )
        b_view = read_execution(root, b, owner).composition
        assert b_view is not None and b_view.transfers
        assert any(
            item.role == "art" and item.decision == "replace"
            for item in read_plan_nodes(root, parent, owner).nodes
        )
        fenced = _refusal(lambda: run_assigned(config("art"), owner, art_assign.attempt_id))
        assert fenced in ("stale_plan", "work_closed", "stale_attempt")
        assert len(provider.digests) == 2
        mark("Art replaced and fenced; waiting B transferred")
        bridge = Bridge(
            root,
            owner,
            workspaces["b"],
            10000,
            deliver_answer=lambda outbox: deliver_outbox(root, owner, outbox),
        )
        session = uuid4()
        bridge.connect(session)
        bridge.select(session, activity, b)
        bridge.answer_wait(session, wait.wait_id, markers["answer"])
        assert b_worker.wait(timeout=90) == 0, b_err_path.read_text(
            encoding="utf-8", errors="replace"
        )[-6000:]
        b_run = json.loads(b_out_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        b_output = _result(root, owner, b)
        _accept(root, owner, b, markers["basis"] + " B")
        assert len(provider.digests) == 3
        mark("B continued after transfer and accepted")
        choice_id = uuid4()
        _apply(
            root,
            owner,
            CreateDecisionRequest,
            decision_id=choice_id,
            state=ChoiceState(
                statement="Fictional art is not required",
                name="art_needed",
                value="no",
                scope=DecisionScope(kind="work", record_id=parent),
            ),
        )
        choice = DecisionRef(decision_id=choice_id, revision=1)
        _apply(
            root,
            owner,
            ResolveObligationApplicabilityRequest,
            work_id=parent,
            key="art_review",
            expected_plan_revision=2,
            expected_obligation_revision=read_obligation(
                root, parent, "art_review", owner
            ).revision,
            choice=choice,
            basis=markers["basis"] + " choice",
        )
        _confirm(root, owner, parent, "final", b_output, markers["basis"] + " final")
        mark("conditional inactive by addressed choice")
        _issue_now(root, owner, parent, nested)
        _issue_now(root, owner, nested, grandchild)
        _apply(
            root,
            owner,
            CreateResourceRequest,
            resource_id=uuid4(),
            work_id=grandchild,
            state=ResourceState(
                label="Fictional grandchild", root=workspaces["g"], limit_units=10000
            ),
        )
        g_assign = _assign(root, owner, grandchild)
        apply_operation(root, g_assign, owner)
        g_run = run_assigned(config("g"), owner, g_assign.attempt_id)
        g_output = _result(root, owner, grandchild)
        _accept(root, owner, grandchild, markers["basis"] + " grandchild")
        _confirm(root, owner, nested, "g_final", g_output, markers["basis"] + " nested")
        _link(root, owner, nested, "final", g_output)
        _accept(root, owner, nested, markers["basis"] + " nested accepted")
        assert len(provider.digests) == 4
        visible_nested = read_execution(root, nested, owner).composition
        assert visible_nested is not None and visible_nested.nested is not None
        assert visible_nested.nested.children[0].work_id == grandchild
        mark("grandchild and nested composite accepted")
        current = read_work_plan(root, parent, owner).plan
        _apply(
            root,
            owner,
            ReviseActivePlanRequest,
            work_id=parent,
            expected_plan_revision=2,
            expected_work_revision=read_work(root, parent, owner).revision,
            plan=current.model_copy(update={"rationale": markers["plan"] + " v2"}),
            nodes=tuple(
                PlanNodeDecision(role=role, decision="keep", work_id=work)
                for role, work in (("a", a), ("b", b), ("art", art2), ("nested", nested))
            ),
            target_method=v2,
            obligation_mapping=(
                ObligationMapping(source_key="checked", action="carry", target_key="checked_v2"),
                ObligationMapping(source_key="final", action="carry", target_key="final_v2"),
                ObligationMapping(source_key="art_review", action="carry", target_key="art_review"),
            ),
        )
        assert read_plan_method(root, parent, owner).version == 2
        assert read_obligation(root, parent, "art_review", owner).applicability == "inactive"
        exception_id = uuid4()
        _apply(
            root,
            owner,
            CreateDecisionRequest,
            decision_id=exception_id,
            state=ExceptionState(
                statement="Fictional exception for the current exact Method",
                target=ObligationTarget(work_id=parent, key="checked_v2"),
                methods=(v2,),
            ),
        )
        exception = DecisionRef(decision_id=exception_id, revision=1)
        _apply(
            root,
            owner,
            WaiveObligationRequest,
            work_id=parent,
            key="checked_v2",
            expected_plan_revision=3,
            expected_obligation_revision=read_obligation(
                root, parent, "checked_v2", owner
            ).revision,
            exception=exception,
            basis=markers["basis"] + " waiver " + markers["exception"],
        )
        assert read_obligation(root, parent, "checked_v2", owner).status == "waived"
        _confirm(root, owner, parent, "nested_final", g_output, markers["basis"] + " nested final")
        _link(root, owner, parent, "final", b_output)
        _accept(root, owner, parent, markers["basis"] + " parent accepted")
        assert read_work_status(root, parent, owner).status == "succeeded"
        mark("Method v2 parent accepted with visible exceptions")
        shown = status_via_pi(
            root,
            workspaces["b"],
            owner,
            base_config,
            activity,
            parent,
            ("succeeded", "checked_v2", "inactive", "exception", "nested", "Method"),
        )
        assert len(provider.digests) == 4
        report["interactive_status"] = shown.splitlines()[:18]
        report["runs"] = {
            "a": a_run,
            "b": b_run,
            "g": g_run,
            "fenced_code": fenced,
            "revision_operation": str(replacement.operation_id),
            "recheck_operation": str(recheck.operation_id),
        }
        mark("separate ordinary Pi status, no HTTP")
        copies = _technical_copies(root, tuple(markers.values()))
        assert not copies["text_found"], copies
        report["technical_copies"] = copies
        fresh = subprocess.run(
            [
                sys.executable,
                *ISOLATED_UTF8,
                "-c",
                "import json,sys; from pathlib import Path; from uuid import UUID; "
                "from zaratustra.foundation import authorize_local,read_execution,"
                "read_plan_method; "
                "p=Path(sys.argv[1]); o=authorize_local(p,actor='owner',source_ref='fresh'); "
                "w=UUID(sys.argv[2]); n=UUID(sys.argv[3]); "
                "print(json.dumps({'parent':read_execution(p,w,o).status.status,"
                "'nested':read_execution(p,n,o).composition.nested.children[0].status.status,"
                "'method':read_plan_method(p,w,o).version}))",
                str(root),
                str(parent),
                str(nested),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        assert fresh.returncode == 0, fresh.stderr
        report["fresh_process"] = json.loads(fresh.stdout.strip().splitlines()[-1])
        assert report["fresh_process"] == {
            "parent": "succeeded",
            "nested": "succeeded",
            "method": 2,
        }
        old_backup = create_assigned_backup(root, uuid4(), owner)
        restored_root = output / "restored-space"
        restored_root.mkdir()
        recovery = authorize_recovery(actor="owner", source_ref="fictional-restore")
        restored = restore_backup(old_backup.package, restored_root, recovery)
        apply_operation(
            restored_root,
            RecoverRequest(
                operation_id=uuid4(),
                space_id=owner.space_id,
                actor="owner",
                decision_id=uuid4(),
                grant_id=uuid4(),
            ),
            recovery,
        )
        restored_owner = authorize_local(
            restored_root, actor="owner", source_ref="fictional-new-epoch"
        )
        assert read_work_status(restored_root, parent, restored_owner).status == "succeeded"
        assert (restored_root / ".zara-core" / "executor-restored.sqlite3").is_file()
        report["backup_restore"] = {
            "format": old_backup.manifest.format_version,
            "schema": old_backup.manifest.schema_version,
            "old_epoch": restored.execution_epoch - 1,
            "new_epoch": restored.execution_epoch,
            "pi_files": len(old_backup.manifest.pi_rpc_home_files),
            "inert_executor": True,
        }
        mark("fresh process and quarantined restore, no HTTP")
        # Delete the grandchild first; its copied text in nested and parent outcomes
        # must retire. Then remove each Work bottom-up, checking managed copies and a
        # new backup after each step. The old package must be purged by first deletion.
        deletion: list[dict[str, object]] = []
        removed: set[str] = set()
        for label, work in (
            ("g", grandchild),
            ("nested", nested),
            ("art", art),
            ("art2", art2),
            ("a", a),
            ("b", b),
            ("parent", parent),
        ):
            _apply(
                root,
                owner,
                DeleteWorkRequest,
                work_id=work,
                expected_revision=read_work(root, work, owner).revision,
            )
            for artifact in {
                "g": (g_output,),
                "a": (a_output,),
                "b": (b_output, *wait.partial_refs),
            }.get(label, ()):
                _apply(
                    root,
                    owner,
                    DeleteArtifactRequest,
                    artifact_id=artifact.artifact_id,
                    expected_revision=artifact.revision,
                )
            completed = complete_assigned_deletions(root, owner)
            assert completed.pending_jobs == 0 and completed.live_store_sanitized
            if label == "g":
                removed.add(markers["g"])
            if label == "a":
                removed.add(markers["a"])
            if label == "b":
                removed.update(
                    (markers["b"], markers["question"], markers["answer"], markers["partial"])
                )
            if label == "parent":
                removed.update((markers["plan"], markers["basis"], markers["exception"]))
            clean = create_assigned_backup(root, uuid4(), owner)
            found = {
                text: _contains(root / ".zara-core", text)
                for text in removed
                if _contains(root / ".zara-core", text)
            }
            packed = {
                text: _contains(clean.package, text)
                for text in removed
                if _contains(clean.package, text)
            }
            assert not found and not packed, (label, found, packed)
            deletion.append(
                {
                    "step": label,
                    "pending": completed.pending_jobs,
                    "sanitized": completed.live_store_sanitized,
                    "markers_absent": len(removed),
                    "new_backup": str(clean.package),
                }
            )
        assert not old_backup.package.exists()
        report["deletion"] = deletion
        report["http_total"] = len(provider.digests)
        assert report["http_total"] == 4
        report["status"] = "passed"
        return report
    finally:
        provider.shutdown()
        provider.server_close()
        server.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pi-runtime", type=Path)
    parser.add_argument("--assigned", type=Path)
    args = parser.parse_args()
    if args.assigned is not None:
        payload = json.loads(args.assigned.read_text(encoding="utf-8"))
        settings = {
            key: Path(value) if key in ("space", "workspace", "pi_cli", "pi_runtime") else value
            for key, value in payload["config"].items()
        }
        assigned_config = AssignedConfig(**cast(Any, settings))
        assigned_owner = authorize_local(
            Path(payload["space"]), actor="owner", source_ref="fictional-assigned-child"
        )
        assigned_result = run_assigned(assigned_config, assigned_owner, UUID(payload["attempt"]))
        print(json.dumps(assigned_result, ensure_ascii=False, default=str))
        return 0
    if args.output is None or args.pi_runtime is None:
        parser.error("--output and --pi-runtime are required for the full probe")
    report = _run(args.output, args.pi_runtime)
    (args.output / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "http_total": report["http_total"],
                "steps": report["http_steps"],
            },
            ensure_ascii=False,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
