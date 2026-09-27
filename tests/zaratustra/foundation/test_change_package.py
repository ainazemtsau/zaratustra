"""Program bytes and a dependent Method become active only after exact installation."""

from __future__ import annotations

import hashlib
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_binding import _new_definition, _ready
from zaratustra.foundation import (
    ApplyCandidateRequest,
    ArtifactRef,
    BindingChange,
    ChangeCandidateState,
    ChangeDecisionState,
    CompositeChange,
    ConfirmProgramInstallRequest,
    CreateArtifactRequest,
    CreateDecisionRequest,
    CreateDevelopmentRequest,
    CreateKnowledgeRequest,
    CreateResourceRequest,
    CreateWorkRequest,
    FoundationError,
    KnowledgeRef,
    LocalAuthority,
    MethodChange,
    MethodDefinition,
    MethodRef,
    OutputContract,
    ProgramChange,
    ResourceState,
    ReviseDecisionRequest,
    SourceState,
    StopCandidateRequest,
    ValidationCriterion,
    ValidationPlanState,
    ValidationResultState,
    WorkState,
    apply_operation,
    method_checksum,
    pulse_space,
    read_binding_version,
    read_change_application,
    read_decision,
    read_method_version,
    upgrade_change_package_space,
    upgrade_development_space,
    upgrade_knowledge_space,
)
from zaratustra.release import _installed_program_change


@dataclass(frozen=True)
class _PreparedProgram:
    root: Path
    space: UUID
    owner: LocalAuthority
    application_id: UUID
    candidate_id: UUID
    decision_id: UUID
    method_ref: MethodRef
    installed: Path
    build: bytes
    config: dict[str, object]


def _prepared_program_change(tmp_path: Path) -> _PreparedProgram:
    root, space, owner, activity_id, _ = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    upgrade_development_space(root, owner)
    assert upgrade_change_package_space(root, owner).schema_version == 12
    workspace = tmp_path / "working_resource"
    workspace.mkdir()
    work_id, resource_id = uuid4(), uuid4()
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            work_id=work_id,
            state=WorkState(
                activity_id=activity_id,
                goal="Develop a fictional local capability",
                expected_outputs=(OutputContract(slot="build", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    apply_operation(
        root,
        CreateResourceRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            resource_id=resource_id,
            work_id=work_id,
            state=ResourceState(label="Fictional worktree", root=workspace, limit_units=10),
        ),
        owner,
    )
    build = b"def capability():\n    return 42\n"
    build_hash = hashlib.sha256(build).hexdigest().upper()
    build_id = uuid4()
    apply_operation(
        root,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            artifact_id=build_id,
            media_type="text/x-python",
            content=build,
        ),
        owner,
    )
    evidence_id = uuid4()
    apply_operation(
        root,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=evidence_id,
            state=SourceState(
                channel="tool_result",
                connection="local-test",
                profile_revision=1,
                source_event_id="program-build-check",
                media_type="text/plain",
                capture="full",
                content=b"Fictional target test passed for the saved build",
            ),
        ),
        owner,
    )
    evidence = KnowledgeRef(record_id=evidence_id, revision=1)
    method_id, program_id, package_id = uuid4(), uuid4(), uuid4()
    method_definition = MethodDefinition(
        instruction="Use the exact installed fictional capability",
        named_outputs=(OutputContract(slot="result", media_type="text/plain"),),
        source_ref="fictional-program-package",
    )
    method_ref = MethodRef(
        method_id=method_id, version=1, checksum=method_checksum(method_definition)
    )
    candidate_id, decision_id, validation_id = uuid4(), uuid4(), uuid4()
    candidate = ChangeCandidateState(
        target=CompositeChange(
            package_id=package_id,
            to_version=1,
            parts=(
                MethodChange(
                    method_id=method_id,
                    to_version=1,
                    definition=method_definition,
                ),
                ProgramChange(
                    program_id=program_id,
                    resource_id=resource_id,
                    resource_revision=1,
                    relative_path="capability.py",
                    to_version=1,
                    build=ArtifactRef(artifact_id=build_id, revision=1),
                    build_sha256=build_hash,
                    required_validation_keys=("exact",),
                ),
            ),
        ),
        proposal="Install a checked build together with its Method",
        expected_outcome="Exact local capability is available in the chosen resource",
        scope_activity_ids=(activity_id,),
        exclusions="No other resource is changed",
        impact="One local file and one future Method version",
        unknowns="Practical value remains unmeasured",
        validation_plan=ValidationPlanState(
            baseline="No installed capability",
            environment="Fictional local resource",
            criteria=(
                ValidationCriterion(
                    key="exact",
                    question="Are exact build bytes available?",
                    pass_condition="Installed SHA-256 matches the saved build",
                ),
            ),
            cases="One bounded local installation",
            method="Hash the installed bytes and inspect exact Method version",
            sufficiency="The byte property is directly observable",
            limits="No behavioral benefit claim",
            stop_and_restore="Stop use and remove the exact new file",
            decision_condition="Current rights and saved test result",
            follow_up="Observe later consumer Work",
        ),
        results=(
            ValidationResultState(
                result_id=validation_id,
                criterion="exact",
                outcome="met",
                evidence=(evidence,),
                actual_input="Saved build before installation",
                environment="Fictional resource",
                limitations="Installation remains separately unverified",
            ),
        ),
        restore_plan="Stop and remove only the exact new file",
        irreversible_effects="No external publication is claimed",
    )
    apply_operation(
        root,
        CreateDevelopmentRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=candidate_id,
            state=candidate,
        ),
        owner,
    )
    apply_operation(
        root,
        CreateDecisionRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            decision_id=decision_id,
            state=ChangeDecisionState(
                statement="Allow one bounded exact installation",
                candidate_id=candidate_id,
                candidate_revision=1,
                mode="trial",
                trial_use_limit=1,
                use="permitted",
                scope_activity_id=activity_id,
                validation_result_ids=(validation_id,),
                review_condition="Stop after first use and inspect the outcome",
            ),
        ),
        owner,
    )
    application_id = uuid4()
    receipt = apply_operation(
        root,
        ApplyCandidateRequest(
            operation_id=application_id,
            space_id=space,
            actor="owner",
            candidate_id=candidate_id,
            candidate_revision=1,
            decision_id=decision_id,
            decision_revision=1,
            mode="trial",
        ),
        owner,
    )
    assert receipt.result["status"] == "prepared"
    installed = workspace / "capability.py"
    config: dict[str, object] = {
        "space": str(root),
        "space_id": str(space),
        "workspace": str(workspace),
    }
    return _PreparedProgram(
        root,
        space,
        owner,
        application_id,
        candidate_id,
        decision_id,
        method_ref,
        installed,
        build,
        config,
    )


def test_composite_program_install_stop_and_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = _prepared_program_change(tmp_path)
    root, space, owner = prepared.root, prepared.space, prepared.owner
    application_id = prepared.application_id
    candidate_id, decision_id = prepared.candidate_id, prepared.decision_id
    method_ref, installed, build, config = (
        prepared.method_ref,
        prepared.installed,
        prepared.build,
        prepared.config,
    )
    apply_operation(
        root,
        StopCandidateRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            application_id=application_id,
            expected_revision=1,
            reason="Stop an interrupted installation",
            started_works="No Work used the unpublished Method",
            external_effects="Exact file may already have been installed",
        ),
        owner,
    )
    installed.write_bytes(build)
    monkeypatch.setattr("builtins.input", lambda _: "RESTORE")
    assert (
        _installed_program_change(
            Namespace(
                command="change-restore",
                application_id=application_id,
                reason="Resolve the interrupted preparation",
                data_restoration="Remove the exact new file",
                external_effects="No external publication was reversed",
            ),
            config,
            "owner",
        )
        == 0
    )
    assert not installed.exists()
    application_id = uuid4()
    assert (
        apply_operation(
            root,
            ApplyCandidateRequest(
                operation_id=application_id,
                space_id=space,
                actor="owner",
                candidate_id=candidate_id,
                candidate_revision=1,
                decision_id=decision_id,
                decision_revision=1,
                mode="trial",
            ),
            owner,
        ).result["status"]
        == "prepared"
    )
    with pytest.raises(FoundationError):
        read_method_version(root, method_ref, owner)
    with pytest.raises(FoundationError, match="Observed program bytes differ"):
        apply_operation(
            root,
            ConfirmProgramInstallRequest(
                operation_id=uuid4(),
                space_id=space,
                actor="owner",
                application_id=application_id,
                expected_revision=1,
            ),
            owner,
        )
    monkeypatch.setattr("builtins.input", lambda _: "INSTALL")
    assert (
        _installed_program_change(
            Namespace(command="change-install", application_id=application_id), config, "owner"
        )
        == 0
    )
    assert installed.read_bytes() == build
    assert read_method_version(root, method_ref, owner).definition.instruction.startswith("Use")
    app, events = read_change_application(root, application_id, owner)
    assert app.status == "active" and [item["kind"] for item in events] == ["prepare", "confirm"]
    installed.write_bytes(b"independent modification")
    assert any(item.code == "program_unavailable" for item in pulse_space(root, owner).findings)
    installed.write_bytes(build)
    apply_operation(
        root,
        StopCandidateRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            application_id=application_id,
            expected_revision=2,
            reason="One use completed",
            started_works="Existing Work remains separately addressed",
            external_effects="No external publication",
        ),
        owner,
    )
    monkeypatch.setattr("builtins.input", lambda _: "RESTORE")
    assert (
        _installed_program_change(
            Namespace(
                command="change-restore",
                application_id=application_id,
                reason="Return to prior state after the bounded trial",
                data_restoration="Only the exact new program file was removed",
                external_effects="No external publication was reversed",
            ),
            config,
            "owner",
        )
        == 0
    )
    assert not installed.exists()
    assert read_change_application(root, application_id, owner)[0].status == "restored"


def test_revoked_program_admission_has_no_file_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = _prepared_program_change(tmp_path)
    decision = read_decision(prepared.root, prepared.decision_id, prepared.owner)
    apply_operation(
        prepared.root,
        ReviseDecisionRequest(
            operation_id=uuid4(),
            space_id=prepared.space,
            actor="owner",
            decision_id=decision.decision_id,
            expected_revision=decision.revision,
            state=decision.state.model_copy(update={"status": "revoked"}),
        ),
        prepared.owner,
    )
    monkeypatch.setattr("builtins.input", lambda _: "INSTALL")
    with pytest.raises(FoundationError) as failure:
        _installed_program_change(
            Namespace(command="change-install", application_id=prepared.application_id),
            prepared.config,
            "owner",
        )
    assert failure.value.code == "stale_decision"
    assert not prepared.installed.exists()
    app, events = read_change_application(prepared.root, prepared.application_id, prepared.owner)
    assert app.status == "prepared" and app.revision == 1
    assert [event["kind"] for event in events] == ["prepare"]


def test_program_edit_during_install_confirmation_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = _prepared_program_change(tmp_path)
    independent = b"owner independently edited this file\n"

    def confirm(_: str) -> str:
        prepared.installed.write_bytes(independent)
        return "INSTALL"

    monkeypatch.setattr("builtins.input", confirm)
    with pytest.raises(ValueError, match="Program path changed independently"):
        _installed_program_change(
            Namespace(command="change-install", application_id=prepared.application_id),
            prepared.config,
            "owner",
        )
    assert prepared.installed.read_bytes() == independent
    app, events = read_change_application(prepared.root, prepared.application_id, prepared.owner)
    assert app.status == "prepared" and app.revision == 1
    assert [event["kind"] for event in events] == ["prepare"]


def test_internal_method_and_binding_package_is_one_admitted_change(tmp_path: Path) -> None:
    root, space, owner, producer, consumer = _ready(tmp_path)
    upgrade_knowledge_space(root, owner)
    upgrade_development_space(root, owner)
    upgrade_change_package_space(root, owner)
    evidence_id = uuid4()
    apply_operation(
        root,
        CreateKnowledgeRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=evidence_id,
            state=SourceState(
                channel="tool_result",
                connection="fictional-check",
                profile_revision=1,
                source_event_id="binding-package-shape",
                media_type="text/plain",
                capture="full",
                content=b"The exact fictional input and output slots match",
            ),
        ),
        owner,
    )
    evidence = KnowledgeRef(record_id=evidence_id, revision=1)
    method_id, binding_id, package_id = uuid4(), uuid4(), uuid4()
    method = MethodDefinition(
        instruction="Plan from one accepted fictional source",
        named_inputs=(OutputContract(slot="source", media_type="text/plain"),),
        named_outputs=(OutputContract(slot="plan", media_type="text/plain"),),
        source_ref="fictional-internal-package",
    )
    method_ref = MethodRef(method_id=method_id, version=1, checksum=method_checksum(method))
    binding = _new_definition(producer, consumer, method_ref, goal="Plan from the accepted source")
    candidate_id, decision_id, validation_id = uuid4(), uuid4(), uuid4()
    candidate = ChangeCandidateState(
        target=CompositeChange(
            package_id=package_id,
            to_version=1,
            parts=(
                MethodChange(method_id=method_id, to_version=1, definition=method),
                BindingChange(binding_id=binding_id, to_version=1, definition=binding),
            ),
        ),
        proposal="Admit the dependent Method and Binding together",
        expected_outcome="One exact future transfer is allowed",
        scope_activity_ids=(consumer,),
        exclusions="Other Activities are excluded",
        impact="A bounded new consumer Work may be created",
        unknowns="Practical value remains unmeasured",
        validation_plan=ValidationPlanState(
            baseline="Neither version is published",
            environment="Fictional local Core",
            criteria=(
                ValidationCriterion(
                    key="shape",
                    question="Do the exact Method and Binding contracts match?",
                    pass_condition="The saved slot check succeeds",
                    basis=(evidence,),
                ),
            ),
            cases="One accepted fictional source",
            method="Check exact typed slots before bounded use",
            sufficiency="A single structural check permits one trial",
            limits="No general behavioral claim",
            stop_and_restore="Pause Binding and stop new Method use",
            decision_condition="Saved check and current rights",
            follow_up="Inspect actual consumer Work",
        ),
        results=(
            ValidationResultState(
                result_id=validation_id,
                criterion="shape",
                outcome="met",
                evidence=(evidence,),
                actual_input="Saved exact Method and Binding",
                environment="Fictional local Core",
            ),
        ),
        restore_plan="Pause Binding and stop new Method use",
        irreversible_effects="No external effect is claimed",
    )
    apply_operation(
        root,
        CreateDevelopmentRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            record_id=candidate_id,
            state=candidate,
        ),
        owner,
    )
    apply_operation(
        root,
        CreateDecisionRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            decision_id=decision_id,
            state=ChangeDecisionState(
                statement="Allow one bounded dependent transfer",
                candidate_id=candidate_id,
                candidate_revision=1,
                mode="trial",
                trial_use_limit=1,
                use="permitted",
                scope_activity_id=consumer,
                validation_result_ids=(validation_id,),
                review_condition="Inspect the first real transfer",
            ),
        ),
        owner,
    )
    application_id = uuid4()
    receipt = apply_operation(
        root,
        ApplyCandidateRequest(
            operation_id=application_id,
            space_id=space,
            actor="owner",
            candidate_id=candidate_id,
            candidate_revision=1,
            decision_id=decision_id,
            decision_revision=1,
            mode="trial",
        ),
        owner,
    )
    assert receipt.result["status"] == "active"
    assert read_method_version(root, method_ref, owner).definition == method
    assert read_binding_version(root, binding_id, 1, owner).state == "trial"
    app, history = read_change_application(root, application_id, owner)
    assert app.status == "active" and [item["kind"] for item in history] == ["apply"]
    apply_operation(
        root,
        StopCandidateRequest(
            operation_id=uuid4(),
            space_id=space,
            actor="owner",
            application_id=application_id,
            expected_revision=1,
            reason="Bounded trial complete",
            started_works="No Work started",
            external_effects="No external effect",
        ),
        owner,
    )
    assert read_binding_version(root, binding_id, 1, owner).state == "paused"
