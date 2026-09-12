"""Generic first-use, designation context and manual external-chat exchange."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import zaratustra.cli as cli_module
from zaratustra.core import (
    Artifact,
    AuthorizationPrompt,
    ContextPackage,
    ContextQuery,
    InitialRecords,
    LocalAuthorization,
    MutationError,
    MutationRequest,
    apply_mutation,
    authorize_local,
    create_initial_records,
    init_workspace,
    migrate_workspace,
    prepare_authorization,
    read_artifact,
    read_handoffs,
    read_records,
)
from zaratustra.entry import EntryError, find_entries
from zaratustra.first_use import (
    ExternalChatRequest,
    FirstUseError,
    FirstUseReceipt,
    PreparedFirstUse,
    SelectedContext,
    create_external_chat_request,
    execute_first_use,
    open_selected_context,
    parse_external_chat_request,
    parse_first_use_setup,
    prepare_external_chat_response,
    prepare_first_use,
    prepare_selected_context,
    save_external_chat_request,
)
from zaratustra.intake import (
    IntakeError,
    MaterialIntakeAuthorization,
    PreparedMaterialIntake,
    authorize_material_intake,
    execute_material_intake,
)


def setup_bytes(title: str = "Generic notes") -> bytes:
    return json.dumps(
        {
            "version": 1,
            "process_title": title,
            "goal": "Develop the next generic note",
            "expected_result": "One reviewed text update",
            "acceptance": ["The saved source is cited exactly"],
            "boundaries": ["Use generic demonstration data only"],
            "budget": "One bounded local exchange",
            "artifact_title": "Generic working note",
            "created_by": "local generic setup",
        }
    ).encode()


def confirm(path: Path, request: MutationRequest | ContextQuery) -> LocalAuthorization:
    return authorize_local(
        prepare_authorization(path, request),
        channel="local-chat",
        actor="generic-first-use-test",
        source_ref="explicit-disposable-test-permission",
    )


def finish(prepared: PreparedFirstUse) -> FirstUseReceipt:
    callers = tuple(confirm(prepared.workspace, request) for request in prepared.pending)
    return execute_first_use(prepared, callers)


def start(
    root: Path,
    designation: str,
    material: bytes = b"Initial generic accepted basis.\n",
    *,
    aliases: tuple[str, ...] = (),
) -> tuple[Path, Path, FirstUseReceipt]:
    catalog = root / "catalog.json"
    workspace = root / designation.casefold().replace(" ", "-")
    prepared = prepare_first_use(
        catalog,
        designation,
        workspace,
        setup_bytes(designation),
        material,
        aliases=aliases,
    )
    receipt = finish(prepared)
    return catalog, workspace, receipt


def open_context(catalog: Path, designation: str) -> tuple[SelectedContext, ContextPackage]:
    selected = prepare_selected_context(catalog, designation, max_bytes=1_048_576)
    package = open_selected_context(selected, confirm(selected.workspace, selected.query))
    return selected, package


def test_complete_setup_retry_context_and_external_response(tmp_path: Path) -> None:
    initial = b"Initial generic accepted basis.\nMeasured sample: three units.\n"
    catalog = tmp_path / "catalog.json"
    workspace = tmp_path / "generic"
    prepared = prepare_first_use(catalog, "Generic Notes", workspace, setup_bytes(), initial)
    assert len(prepared.pending) == 4
    receipt = finish(prepared)
    assert receipt.status == "ready_with_accepted_basis"
    assert receipt.state_revision == 5
    assert len(read_handoffs(workspace)) == 1
    assert read_artifact(workspace, receipt.artifact_id).content == initial

    replay = prepare_first_use(catalog, "Generic Notes", workspace, setup_bytes(), initial)
    assert replay.pending == ()
    assert execute_first_use(replay, ()).receipts == receipt.receipts

    selected, package = open_context(catalog, "Generic Notes")
    context: dict[str, Any] = json.loads(package.output)
    saved = [
        row["data"]["content_base64"]
        for row in context["context"]["sources"]
        if row["locator"].startswith("artifact-version:")
    ]
    assert base64.b64decode(saved[0]) == initial
    request = create_external_chat_request(selected, package)
    assert request.basis == (receipt.initial_version,)
    request_path = tmp_path / "manual-request.json"
    save_external_chat_request(request_path, request)
    with pytest.raises(FirstUseError, match="output_exists"):
        save_external_chat_request(request_path, request)

    returned = b"New generic external material.\nMeasured sample: five units.\n"
    intake = prepare_external_chat_response(
        catalog,
        "Generic Notes",
        request_path.read_bytes(),
        returned,
        created_by="manual external supplier",
        source_ref="generic-response.txt",
    )
    intake_caller = authorize_material_intake(
        intake,
        channel="local-chat",
        actor="generic-first-use-test",
        source_ref="explicit-review-of-returned-text",
    )
    accepted = execute_material_intake(intake, intake_caller)
    assert accepted.current_continuation.state == "selected_work_ready"
    assert accepted.completion.status == "not_requested"
    assert read_artifact(workspace, receipt.artifact_id).content == returned
    handoffs = read_handoffs(workspace)
    assert len(handoffs) == 2
    assert handoffs[-1].handoff.basis == (receipt.initial_version,)
    assert handoffs[-1].handoff.result.version_id == accepted.publication.operation_id


def test_draft_is_cataloged_but_not_ready_and_plan_loss_refuses(tmp_path: Path) -> None:
    material = b"Unconfirmed generic starting text.\n"
    catalog = tmp_path / "catalog.json"
    workspace = tmp_path / "draft"
    prepared = prepare_first_use(
        catalog, "Draft Notes", workspace, setup_bytes("Draft Notes"), material
    )
    found = find_entries(catalog, "Draft Notes")
    assert found.matches[0].current_revision == 1
    selected = prepare_selected_context(catalog, "Draft Notes", max_bytes=65_536)
    with pytest.raises(MutationError, match="not ready"):
        open_selected_context(selected, confirm(workspace, selected.query))
    replay = prepare_first_use(
        catalog, "Draft Notes", workspace, setup_bytes("Draft Notes"), material
    )
    assert replay.plan == prepared.plan
    assert len(replay.pending) == 4

    apply_mutation(workspace, prepared.pending[0], confirm(workspace, prepared.pending[0]))
    plan_path = workspace / "inbox" / "first-use" / "plan.json"
    plan_path.unlink()
    before = read_records(workspace)
    with pytest.raises(FirstUseError, match="progress_unavailable"):
        prepare_first_use(catalog, "Draft Notes", workspace, setup_bytes("Draft Notes"), material)
    assert read_records(workspace) == before


def test_wrong_stale_ambiguous_unavailable_and_altered_request(tmp_path: Path) -> None:
    catalog, first_workspace, _ = start(tmp_path, "First Notes", aliases=("shared",))
    original_records = read_records(first_workspace)
    original_catalog = catalog.read_bytes()
    colliding_workspace = tmp_path / "must-not-be-created"
    with pytest.raises(FirstUseError, match="designation_collision"):
        prepare_first_use(
            catalog,
            "First Notes",
            colliding_workspace,
            setup_bytes("Another Process"),
            b"Another source that must not be created.\n",
        )
    assert not colliding_workspace.exists()
    assert read_records(first_workspace) == original_records
    assert catalog.read_bytes() == original_catalog
    corrected = prepare_first_use(
        catalog,
        "Free Notes",
        colliding_workspace,
        setup_bytes("Another Process"),
        b"Another source that now has an unused designation.\n",
    )
    assert corrected.plan.designation == "Free Notes"
    assert len(corrected.pending) == 4
    assert find_entries(catalog, "Free Notes").matches[0].entry.work_id == corrected.plan.work_id
    second_workspace = tmp_path / "second-notes"
    second = prepare_first_use(
        catalog,
        "Second Notes",
        second_workspace,
        setup_bytes("Second Notes"),
        b"Second generic initial basis.\n",
        aliases=("shared",),
    )
    finish(second)
    selected, package = open_context(catalog, "First Notes")
    request = create_external_chat_request(selected, package)
    request_bytes = request.model_dump_json(indent=2).encode()

    with pytest.raises(FirstUseError, match="wrong_target"):
        prepare_external_chat_response(
            catalog,
            "Second Notes",
            request_bytes,
            b"Wrong target response.\n",
            created_by="manual supplier",
            source_ref="wrong.txt",
        )
    altered = json.loads(request_bytes)
    altered["context"] += " "
    with pytest.raises(FirstUseError, match="invalid_request"):
        parse_external_chat_request(json.dumps(altered).encode())

    change = MutationRequest(
        operation_id=request.request_id,
        workspace_id=request.workspace_id,
        work_id=request.work_id,
        expected_revision=request.source_revision,
        operation="set_work_requirements",
        requirements=("Generic text only",),
        provenance="Advance after external request capture",
    )
    apply_mutation(first_workspace, change, confirm(first_workspace, change))
    with pytest.raises(IntakeError, match="stale_basis"):
        prepare_external_chat_response(
            catalog,
            "First Notes",
            request_bytes,
            b"Stale response.\n",
            created_by="manual supplier",
            source_ref="stale.txt",
        )

    with pytest.raises(EntryError, match="ambiguous"):
        prepare_selected_context(catalog, "shared", max_bytes=65_536)
    second_workspace.rename(tmp_path / "second-away")
    unavailable = find_entries(catalog, "Second Notes").matches[0]
    assert unavailable.source_state == "unavailable"


def test_mismatching_retry_cannot_poison_legitimate_unplanned_draft(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    workspace = tmp_path / "interrupted-before-plan"
    workspace.mkdir()
    init_workspace(workspace)
    migrate_workspace(workspace, target_version=7)
    legitimate_setup = setup_bytes("Same Process Title")
    legitimate = parse_first_use_setup(legitimate_setup)
    original = create_initial_records(
        workspace,
        InitialRecords.model_validate(legitimate.initial_records().model_dump()),
    )
    wrong_value = json.loads(legitimate_setup)
    wrong_value["goal"] = "A mismatching goal that must not be retained"
    wrong_setup = json.dumps(wrong_value).encode()
    with pytest.raises(FirstUseError, match="setup_collision"):
        prepare_first_use(
            catalog,
            "Recovered Draft",
            workspace,
            wrong_setup,
            b"Legitimate interrupted initial text.\n",
        )
    assert read_records(workspace) == original
    assert not (workspace / "inbox" / "first-use" / "plan.json").exists()
    assert not catalog.exists()

    corrected = prepare_first_use(
        catalog,
        "Recovered Draft",
        workspace,
        legitimate_setup,
        b"Legitimate interrupted initial text.\n",
    )
    assert corrected.plan.setup == legitimate
    assert len(corrected.pending) == 4
    assert finish(corrected).status == "ready_with_accepted_basis"


def test_request_requires_real_accepted_context(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    workspace = tmp_path / "incomplete"
    prepared = prepare_first_use(
        catalog,
        "Incomplete",
        workspace,
        setup_bytes("Incomplete"),
        b"Initial bytes not yet accepted.\n",
    )
    for request in prepared.pending[:3]:
        apply_mutation(
            workspace,
            request,
            confirm(workspace, request),
            content=prepared.initial_material if request.operation == "publish_artifact" else None,
        )
    selected = prepare_selected_context(catalog, "Incomplete", max_bytes=1_048_576)
    with pytest.raises(MutationError, match="requires acceptance"):
        open_selected_context(selected, confirm(workspace, selected.query))


def test_external_request_strict_duplicate_keys() -> None:
    with pytest.raises(FirstUseError, match="strict UTF-8 JSON"):
        parse_external_chat_request(b'{"version":1,"version":1}')
    with pytest.raises(ValidationError):
        ExternalChatRequest.model_validate({"version": 1})


def test_cli_start_request_and_receive_need_no_technical_identifiers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog = tmp_path / "catalog.json"
    workspace = tmp_path / "cli-workspace"
    setup = tmp_path / "setup.json"
    initial = tmp_path / "initial.txt"
    external_request = tmp_path / "request.json"
    response = tmp_path / "response.txt"
    setup.write_bytes(setup_bytes("CLI Generic"))
    initial.write_text("CLI initial accepted text.\n", encoding="utf-8")
    response.write_text("CLI returned external text.\n", encoding="utf-8")

    def confirmed(prompt: AuthorizationPrompt, **_: object) -> LocalAuthorization:
        return authorize_local(
            prompt,
            channel="local-chat",
            actor="generic-cli-test",
            source_ref="explicit-cli-test-permission",
        )

    def intake_confirmed(
        prepared: PreparedMaterialIntake, **_: object
    ) -> MaterialIntakeAuthorization:
        return authorize_material_intake(
            prepared,
            channel="local-chat",
            actor="generic-cli-test",
            source_ref="explicit-cli-intake-test-permission",
        )

    monkeypatch.setattr(cli_module, "confirm_on_console", confirmed)
    monkeypatch.setattr(cli_module, "confirm_material_intake_on_console", intake_confirmed)
    assert (
        cli_module.main(
            [
                "entry",
                "start",
                str(catalog),
                "CLI Generic",
                str(workspace),
                str(setup),
                str(initial),
            ]
        )
        == 0
    )
    assert "ready_with_accepted_basis" in capsys.readouterr().out
    assert (
        cli_module.main(
            [
                "entry",
                "request",
                str(catalog),
                "CLI Generic",
                str(external_request),
            ]
        )
        == 0
    )
    assert "external_request_saved" in capsys.readouterr().out
    assert (
        cli_module.main(
            [
                "entry",
                "receive",
                str(catalog),
                "CLI Generic",
                str(external_request),
                str(response),
                "--created-by",
                "manual generic supplier",
            ]
        )
        == 0
    )
    assert '"status": "accepted"' in capsys.readouterr().out
    artifact = next(row for row in read_records(workspace).records if isinstance(row, Artifact))
    assert read_artifact(workspace, artifact.id).content == response.read_bytes()
