"""Behavior and adversarial checks for the installed process-creation path."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest

import zaratustra.cli as cli_module
from tests.fixtures.process_creation import (
    creation_draft,
    creation_research,
    linked_creation_definition,
)
from zaratustra.core import (
    InitialRecords,
    MutationRequest,
    apply_mutation,
    authorize_local,
    create_initial_records,
    init_workspace,
    migrate_workspace,
    prepare_authorization,
    read_records,
    read_workspace,
)
from zaratustra.first_use import open_selected_context, prepare_selected_context
from zaratustra.process_creation import (
    CreationDraft,
    PreparedActivation,
    ProcessActivationAuthorization,
    ProcessCreationError,
    activation_preview_bytes,
    authorize_process_activation,
    create_research_request,
    execute_process_activation,
    inspect_process_creation,
    prepare_process_activation,
    receive_research_return,
    save_creation_draft,
    save_research_request,
    save_supported_proposal,
)
from zaratustra.process_packs import (
    ProcessDefinition,
    ProcessSnapshot,
    Reason,
    SourceReference,
    evaluate_snapshot,
)


def _research_and_proposal(root: Path, case: str) -> tuple[Path, Path, bytes, ProcessDefinition]:
    catalog = root / "catalog.json"
    designation = f"Fictional {case} creation"
    save_creation_draft(catalog, designation, creation_draft(case))
    request = create_research_request(catalog, designation)
    request_file = root / "research-request.json"
    save_research_request(request_file, request)
    request_bytes = request_file.read_bytes()
    returned = creation_research(case)
    receive_research_return(
        catalog,
        designation,
        request_bytes,
        returned,
        created_by=f"fictional-{case}-manual-research",
        source_ref=f"fixture:{case}:research-return",
    )
    definition = linked_creation_definition(
        case,
        hashlib.sha256(request_bytes).hexdigest(),
        hashlib.sha256(returned).hexdigest(),
    )
    save_supported_proposal(catalog, designation, definition.model_dump_json().encode())
    return catalog, root / "workspace", request_bytes, definition


def _activation_authorization(
    prepared: PreparedActivation,
) -> ProcessActivationAuthorization:
    return authorize_process_activation(
        prepared,
        channel="local-chat",
        actor="process-creation-test",
        source_ref="test-owner-confirmation",
    )


@pytest.mark.parametrize("case", ["small", "project"])
def test_two_fictional_inputs_activate_and_open_through_common_entry(
    tmp_path: Path, case: str
) -> None:
    catalog, workspace, _request, definition = _research_and_proposal(tmp_path, case)
    designation = f"Fictional {case} creation"
    prepared = prepare_process_activation(catalog, designation, workspace)
    shown = json.loads(activation_preview_bytes(prepared))
    assert shown["proposal"]["definition"] == definition.model_dump(mode="json")
    assert shown["first_work"]["node"]["goal"] == definition.nodes[0].goal
    assert shown["first_work"]["node"]["reasons"] == [
        row.model_dump(mode="json") for row in definition.nodes[0].reasons
    ]
    assert shown["source_texts"][1]["trust"] == "untrusted_research_not_approval"
    with pytest.raises(ProcessCreationError, match="permission_denied"):
        execute_process_activation(prepared, None)
    receipt = execute_process_activation(prepared, _activation_authorization(prepared))

    assert receipt.creation.stage == "activated"
    assert receipt.creation.first_work_openable
    assert receipt.creation.current_authority_scope == "work_metadata_and_artifact"
    assert len(receipt.receipts) == 6

    selected = prepare_selected_context(catalog, designation, max_bytes=1_048_576)
    prompt = prepare_authorization(selected.workspace, selected.query)
    caller = authorize_local(
        prompt,
        channel="local-chat",
        actor="process-creation-test",
        source_ref="test-common-entry-open",
    )
    package = open_selected_context(selected, caller)
    opened = json.loads(package.output)
    locators = {row["locator"] for row in opened["context"]["sources"]}
    assert f"work:{receipt.creation.first_work_id}" in locators
    assert any(row.startswith("acceptance:") for row in locators)

    plan_snapshot = ProcessSnapshot(definition=definition)
    assert evaluate_snapshot(plan_snapshot).selected is not None
    status = inspect_process_creation(catalog, designation)
    assert status.research_return is not None and status.research_return.approval is False
    assert status.proposal is not None
    assert status.proposal.definition.nodes[0].reasons


def test_unanswered_clarification_stays_draft_and_refuses_request(tmp_path: Path) -> None:
    draft = json.loads(creation_draft("small"))
    draft["clarifications"][0]["answer"] = None
    catalog = tmp_path / "catalog.json"
    status = save_creation_draft(catalog, "Needs clarification", json.dumps(draft).encode())
    assert status.stage == "draft"
    assert status.open_clarifications == (draft["clarifications"][0]["question"],)
    with pytest.raises(ProcessCreationError, match="clarification_required"):
        create_research_request(catalog, "Needs clarification")


def test_valid_model_json_round_trips_through_strict_draft_boundary(tmp_path: Path) -> None:
    draft = CreationDraft.model_validate_json(creation_draft("small"))
    status = save_creation_draft(
        tmp_path / "catalog.json",
        "Model JSON round trip",
        draft.model_dump_json().encode("utf-8"),
    )
    assert status.draft == draft
    assert status.stage == "draft"


def test_changed_request_or_return_identity_cannot_replace_saved_research(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    designation = "Exact research link"
    save_creation_draft(catalog, designation, creation_draft("small"))
    request = create_research_request(catalog, designation)
    output = tmp_path / "request.json"
    save_research_request(output, request)
    exact = output.read_bytes()
    returned = creation_research("small")
    receive_research_return(
        catalog,
        designation,
        exact,
        returned,
        created_by="fictional-provider",
        source_ref="fixture:first-return",
    )
    with pytest.raises(ProcessCreationError, match="request_mismatch"):
        receive_research_return(
            catalog,
            designation,
            exact + b" ",
            returned,
            created_by="fictional-provider",
            source_ref="fixture:first-return",
        )
    with pytest.raises(ProcessCreationError, match="research_collision"):
        receive_research_return(
            catalog,
            designation,
            exact,
            returned + b"changed\n",
            created_by="fictional-provider",
            source_ref="fixture:changed-return",
        )
    status = inspect_process_creation(catalog, designation)
    assert status.research_return is not None
    assert status.research_return.content.encode() == returned
    assert status.research_is_approval is False


def test_source_trace_and_unknown_capability_refuse_before_activation(tmp_path: Path) -> None:
    draft = json.loads(creation_draft("small"))
    unknown = "fictional.unsupported-provider/v1"
    draft["declared_capabilities"].append(unknown)
    catalog = tmp_path / "catalog.json"
    designation = "Unsupported fictional need"
    save_creation_draft(catalog, designation, json.dumps(draft).encode())
    request = create_research_request(catalog, designation)
    request_file = tmp_path / "request.json"
    save_research_request(request_file, request)
    returned = creation_research("small")
    receive_research_return(
        catalog,
        designation,
        request_file.read_bytes(),
        returned,
        created_by="fictional-provider",
        source_ref="fixture:unsupported-research",
    )
    definition = linked_creation_definition(
        "small",
        hashlib.sha256(request_file.read_bytes()).hexdigest(),
        hashlib.sha256(returned).hexdigest(),
    )
    extra = SourceReference(
        source_id="capability-unsupported",
        kind="capability",
        locator=f"capability:{unknown}",
    )
    node = definition.nodes[0]
    reason = Reason(
        text=node.reasons[0].text,
        source_ids=(*node.reasons[0].source_ids, extra.source_id),
    )
    unsupported = definition.model_copy(
        update=dict(
            required_capabilities=(*definition.required_capabilities, unknown),
            sources=(*definition.sources, extra),
            nodes=(node.model_copy(update=dict(reasons=(reason,))),),
        )
    )
    with pytest.raises(ProcessCreationError, match="unsupported_capability"):
        save_supported_proposal(catalog, designation, unsupported.model_dump_json().encode())
    status = inspect_process_creation(catalog, designation)
    assert status.stage == "research_returned"
    assert status.capability_refusals == (f"unsupported_capability:{unknown}",)


def test_wrong_source_digest_and_proposal_replacement_refuse(tmp_path: Path) -> None:
    catalog, _workspace, request, definition = _research_and_proposal(tmp_path, "project")
    designation = "Fictional project creation"
    changed_source = definition.sources[0].model_copy(
        update=dict(locator=f"creation-request-sha256:{'0' * 64}")
    )
    changed = definition.model_copy(update=dict(sources=(changed_source, *definition.sources[1:])))
    with pytest.raises(ProcessCreationError, match="source_mismatch"):
        save_supported_proposal(catalog, designation, changed.model_dump_json().encode())

    replacement = definition.model_copy(update=dict(title="Changed fictional proposal"))
    with pytest.raises(ProcessCreationError, match="proposal_collision"):
        save_supported_proposal(catalog, designation, replacement.model_dump_json().encode())
    status = inspect_process_creation(catalog, designation)
    assert status.research_request is not None
    assert status.proposal is not None
    assert hashlib.sha256(request).hexdigest() in status.proposal.definition.sources[0].locator


def test_partial_restart_keeps_identities_and_reports_current_rights(tmp_path: Path) -> None:
    catalog, workspace, _request, _definition = _research_and_proposal(tmp_path, "small")
    designation = "Fictional small creation"
    prepared = prepare_process_activation(catalog, designation, workspace)
    first = prepared.pending[0]
    prompt = prepare_authorization(workspace, first)
    caller = authorize_local(
        prompt,
        channel="local-chat",
        actor="process-creation-test",
        source_ref="test-partial-prefix",
    )
    apply_mutation(workspace, first, caller)
    partial = inspect_process_creation(catalog, designation)
    assert partial.stage == "activation_pending"
    assert partial.completed_operations == ("authorize_work",)
    assert partial.current_work_status == "ready"
    assert partial.current_authority_scope == "work_metadata"
    assert partial.first_work_openable is False

    with pytest.raises(ProcessCreationError, match="stale_activation"):
        execute_process_activation(prepared, _activation_authorization(prepared))
    recovered = prepare_process_activation(catalog, designation, workspace)
    assert recovered.pending == prepared.pending[1:]
    receipt = execute_process_activation(recovered, _activation_authorization(recovered))
    assert receipt.creation.stage == "activated"

    repeated = prepare_process_activation(catalog, designation, workspace)
    assert repeated.pending == () and repeated.completed == receipt.receipts
    replay = execute_process_activation(repeated, _activation_authorization(repeated))
    assert replay.receipts == receipt.receipts

    current = read_records(workspace)
    assert receipt.creation.first_work_id is not None
    cancellation = MutationRequest(
        operation_id=uuid4(),
        workspace_id=current.workspace_id,
        work_id=receipt.creation.first_work_id,
        expected_revision=current.state_revision,
        operation="cancel_work",
        provenance="Synthetic terminal-status distinction",
    )
    cancellation_caller = authorize_local(
        prepare_authorization(workspace, cancellation),
        channel="local-chat",
        actor="process-creation-test",
        source_ref="test-terminal-status",
    )
    apply_mutation(workspace, cancellation, cancellation_caller)
    terminal = inspect_process_creation(catalog, designation)
    assert terminal.stage == "activated"
    assert terminal.current_work_status == "cancelled"
    assert terminal.first_work_openable is False


def test_cli_exposes_saved_stages_and_exact_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog = tmp_path / "catalog.json"
    workspace = tmp_path / "workspace"
    draft_file = tmp_path / "draft.json"
    request_file = tmp_path / "request.json"
    response_file = tmp_path / "response.txt"
    proposal_file = tmp_path / "proposal.json"
    designation = "CLI fictional process"
    draft_file.write_bytes(creation_draft("project"))
    response_file.write_bytes(creation_research("project"))
    assert (
        cli_module.main(["entry", "create", "draft", str(catalog), designation, str(draft_file)])
        == 0
    )
    capsys.readouterr()
    assert (
        cli_module.main(
            ["entry", "create", "request", str(catalog), designation, str(request_file)]
        )
        == 0
    )
    request_presentation = capsys.readouterr()
    assert "Need\nBuild a fictional panel decision" in request_presentation.out
    assert "Relevant declared capabilities\n" in request_presentation.out
    assert '"provider_contacted": false' in request_presentation.err
    assert (
        cli_module.main(
            [
                "entry",
                "create",
                "receive",
                str(catalog),
                designation,
                str(request_file),
                str(response_file),
                "--created-by",
                "fictional-cli-research",
            ]
        )
        == 0
    )
    definition = linked_creation_definition(
        "project",
        hashlib.sha256(request_file.read_bytes()).hexdigest(),
        hashlib.sha256(response_file.read_bytes()).hexdigest(),
    )
    proposal_file.write_text(definition.model_dump_json(indent=2), encoding="utf-8")
    assert (
        cli_module.main(
            ["entry", "create", "propose", str(catalog), designation, str(proposal_file)]
        )
        == 0
    )

    monkeypatch.setattr(
        cli_module,
        "confirm_process_activation_on_console",
        _activation_authorization,
    )
    assert (
        cli_module.main(["entry", "create", "activate", str(catalog), designation, str(workspace)])
        == 0
    )
    assert cli_module.main(["entry", "create", "status", str(catalog), designation]) == 0
    assert inspect_process_creation(catalog, designation).stage == "activated"


def test_activation_preview_keeps_cyrillic_source_text_readable(tmp_path: Path) -> None:
    draft = json.loads(creation_draft("small"))
    draft["need"] = "Нужен вымышленный повторяемый процесс."
    catalog = tmp_path / "catalog.json"
    designation = "Readable UTF-8 proposal"
    save_creation_draft(catalog, designation, json.dumps(draft, ensure_ascii=False).encode())
    request = create_research_request(catalog, designation)
    request_file = tmp_path / "request.json"
    save_research_request(request_file, request)
    returned = "Вымышленное исследование, не одобрение.\n".encode()
    receive_research_return(
        catalog,
        designation,
        request_file.read_bytes(),
        returned,
        created_by="fictional-utf8-provider",
        source_ref="fixture:utf8-research",
    )
    definition = linked_creation_definition(
        "small",
        hashlib.sha256(request_file.read_bytes()).hexdigest(),
        hashlib.sha256(returned).hexdigest(),
    )
    save_supported_proposal(catalog, designation, definition.model_dump_json().encode())
    prepared = prepare_process_activation(catalog, designation, tmp_path / "workspace")
    preview = activation_preview_bytes(prepared)
    assert "Нужен вымышленный" in preview.decode("utf-8")
    assert "Вымышленное исследование" in preview.decode("utf-8")
    assert b"\\u041d" not in preview


def test_wrong_existing_target_refuses_before_migration_or_state_change(tmp_path: Path) -> None:
    creation_root = tmp_path / "creation"
    creation_root.mkdir()
    catalog, _workspace, _request, _definition = _research_and_proposal(creation_root, "small")
    unrelated = tmp_path / "unrelated-workspace"
    unrelated.mkdir()
    init_workspace(unrelated)
    migrate_workspace(unrelated, target_version=2)
    create_initial_records(
        unrelated,
        InitialRecords(
            process_title="Unrelated fictional process",
            goal="Keep unrelated state unchanged",
            expected_result="No T2 activation",
            acceptance=("Unrelated state is preserved",),
            boundaries=("Synthetic wrong-target test",),
            budget="No mutation",
            artifact_title="Unrelated artifact",
        ),
    )
    before_info = read_workspace(unrelated)
    before_records = read_records(unrelated)
    with pytest.raises(ProcessCreationError, match="workspace_collision"):
        prepare_process_activation(catalog, "Fictional small creation", unrelated)
    assert read_workspace(unrelated) == before_info
    assert read_records(unrelated) == before_records
    assert before_info.schema_version == 2
