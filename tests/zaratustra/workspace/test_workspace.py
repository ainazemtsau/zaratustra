"""Risks: wrong roots, lost continuation, mixed export and unintended publication."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4, uuid5

import pytest

from tests.zaratustra.foundation.test_binding import _apply
from tests.zaratustra.foundation.test_memory import note, ready
from zaratustra.foundation import (
    CreateGrantRequest,
    CreateMethodVersionRequest,
    CreateResourceRequest,
    CreateWorkRequest,
    DeleteKnowledgeRequest,
    FoundationError,
    GrantState,
    OutputContract,
    ResourceState,
    ReviseKnowledgeRequest,
    ReviseResourceRequest,
    RevokeGrantRequest,
    SourceState,
    WorkState,
    apply_operation,
    authorize_local,
    export_workspace_projection,
    initial_sleep_method,
    initial_sleep_ref,
    read_execution,
    read_knowledge,
    read_receipt,
    read_space,
    upgrade_activity_setup_space,
    validate_workspace_projection,
)
from zaratustra.pi_adapter import Bridge
from zaratustra.workspace import (
    GitDestination,
    LaunchConfig,
    ModelPreference,
    Project,
    defer_git,
    delivery,
    migrate_config,
    prepare_git,
    publish_git,
    read_config,
    register_project,
    remember_model,
    select_work_project,
    selection,
    write_config,
)


def configuration(tmp_path: Path, root: Path, space: Any) -> tuple[Path, LaunchConfig]:
    personal, runtime, external = tmp_path / "personal", tmp_path / "runtime", tmp_path / "code"
    for directory in (personal, runtime, external):
        directory.mkdir()
    path = runtime / "config.json"
    config = LaunchConfig(
        version=2,
        actor="owner",
        space_id=space,
        space=root,
        workspace=personal,
        personal_root=personal,
        runtime_root=runtime,
        sqlite_dll=runtime / "sqlite3.dll",
        pi_runtime=runtime,
        pi_source="system",
        provider_profile="local-completions",
        provider_base_url="http://127.0.0.1:1/v1",
        provider_id="fictional-local",
        model_id="fictional-model",
        reserve_units=1000,
        projects=(Project(name="code", path=external),),
        git=GitDestination(repository="fictional/personal"),
    )
    write_config(path, config)
    return path, config


def test_explicit_model_choice_persists_without_changing_provider_or_core(tmp_path: Path) -> None:
    """Risk: next session falls back to the install default or silently changes transport."""
    root, space, owner, *_ = ready(tmp_path)
    path, config = configuration(tmp_path, root, space)
    original = read_space(root)
    preference = ModelPreference(
        provider_profile=config.provider_profile,
        provider_id=config.provider_id,
        model_id="selected-model",
        thinking="high",
    )
    remembered = remember_model(path, preference)
    assert read_config(path).preferred_model == preference
    assert remembered.model_id == "fictional-model" and read_space(root) == original
    bridge = Bridge(root, owner, config.workspace, workspace_config=path)
    session = uuid4()
    bridge.connect(session)
    reported: list[dict[str, Any]] = []

    class Controller:
        def update_model(self, model: dict[str, Any]) -> None:
            reported.append(model)

    bridge.workflow_controller = Controller()
    bridge.model_selection(
        session,
        {
            "model": {
                "id": "new-selected-model",
                "provider": config.provider_id,
                "thinking": "xhigh",
            }
        },
    )
    saved = read_config(path).preferred_model
    assert (
        saved is not None and saved.model_id == "new-selected-model" and saved.thinking == "xhigh"
    )
    assert reported[0]["id"] == "new-selected-model"
    bridge.model_selection(
        session,
        {
            "persist": False,
            "model": {"id": "restored-model", "provider": config.provider_id, "thinking": "low"},
        },
    )
    assert reported[-1]["id"] == "restored-model" and read_config(path).preferred_model == saved
    with pytest.raises(FoundationError) as error:
        bridge.model_selection(
            session, {"model": {"id": "other-model", "provider": "other-provider"}}
        )
    assert error.value.code == "unsupported_provider"
    assert read_config(path).preferred_model == saved


def test_v1_migration_and_project_resume_preserve_core(tmp_path: Path) -> None:
    """Migration cannot create another Core; new sessions follow the saved Work resource."""
    root, space, owner, activity, _ = ready(tmp_path)
    upgrade_activity_setup_space(root, owner)
    path, config = configuration(tmp_path, root, space)
    old = config.model_copy(
        update={
            "version": 1,
            "workspace": config.projects[0].path,
            "personal_root": None,
            "runtime_root": None,
            "projects": (),
        }
    )
    source = path.parent / "v1.json"
    write_config(source, old)
    before = read_space(root)
    migrated = migrate_config(
        source,
        path.parent / "migrated.json",
        personal_root=config.workspace,
        runtime_root=path.parent,
        projects=config.projects,
        git=config.git,
    )
    assert migrated.space == old.space and migrated.space_id == old.space_id
    assert read_space(root) == before
    assert (
        migrate_config(
            source,
            path.parent / "migrated.json",
            personal_root=config.workspace,
            runtime_root=path.parent,
            projects=config.projects,
            git=config.git,
        )
        == migrated
    )
    work = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=work,
        state=WorkState(
            activity_id=activity,
            goal="Improve a fictional code project",
            expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
        ),
    )
    select_work_project(config, owner, work, "code")
    first = read_execution(root, work, owner)
    select_work_project(config, owner, work, "personal")
    second = read_execution(root, work, owner)
    assert first.resources[0].resource_id == second.resources[0].resource_id
    assert second.resources[0].revision == first.resources[0].revision + 1
    assert second.work == first.work and second.attempts == first.attempts
    select_work_project(config, owner, work, "code")
    bridge = Bridge(root, owner, config.workspace, workspace_config=path)
    session = uuid4()
    bridge.connect(session)
    bridge.select(session, activity, work)
    assert bridge.workspace == config.projects[0].path
    nested = config.workspace / "projects" / "small"
    nested.mkdir(parents=True)
    register_project(path, Project(name="small", path=nested))
    assert read_config(path).project_root("small") == nested
    assert not (nested / ".git").exists()


def test_project_selection_rejects_revoked_create_receipt(tmp_path: Path) -> None:
    """A replayed create receipt cannot claim the revoked resource is still selected."""
    root, space, owner, activity, _ = ready(tmp_path)
    _, config = configuration(tmp_path, root, space)
    work = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=work,
        state=WorkState(
            activity_id=activity,
            goal="Select a fictional project",
            expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
        ),
    )
    select_work_project(config, owner, work, "code")
    created = read_execution(root, work, owner).resources[0]
    operation = uuid5(created.resource_id, "create")
    receipt = read_receipt(root, operation, owner)
    _apply(
        root,
        space,
        owner,
        ReviseResourceRequest,
        resource_id=created.resource_id,
        work_id=work,
        expected_revision=created.revision,
        state=created.state.model_copy(update={"status": "revoked"}),
    )
    before, state = read_execution(root, work, owner), read_space(root)
    revoked = before.resources[0]
    with pytest.raises(FoundationError) as error:
        select_work_project(config, owner, work, "code")
    assert error.value.code == "resource_unavailable"
    assert f"{revoked.resource_id}@{revoked.revision}" in str(error.value)
    assert read_execution(root, work, owner) == before and read_space(root) == state
    assert read_receipt(root, operation, owner) == receipt


def test_project_selection_rejects_multiple_active_resources_without_effects(
    tmp_path: Path,
) -> None:
    """Core may keep multiple resources, but this single-root selector must refuse ambiguity."""
    root, space, owner, activity, _ = ready(tmp_path)
    _, config = configuration(tmp_path, root, space)
    work = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=work,
        state=WorkState(
            activity_id=activity,
            goal="Select a fictional project",
            expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
        ),
    )
    select_work_project(config, owner, work, "code")
    _apply(
        root,
        space,
        owner,
        CreateResourceRequest,
        resource_id=uuid4(),
        work_id=work,
        state=ResourceState(label="Independent resource", root=config.workspace),
    )
    before, state = read_execution(root, work, owner), read_space(root)
    operation = uuid4()
    with pytest.raises(FoundationError) as error:
        select_work_project(config, owner, work, "code", operation_id=operation)
    assert error.value.code == "resource_unavailable"
    for resource in before.resources:
        assert f"{resource.resource_id}@{resource.revision}" in str(error.value)
    assert read_execution(root, work, owner) == before and read_space(root) == state
    with pytest.raises(FoundationError) as missing:
        read_receipt(root, operation, owner)
    assert missing.value.code == "not_found"


def test_project_selection_rechecks_current_path_after_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A competing public revision after commit cannot leave a false successful root."""
    root, space, owner, activity, _ = ready(tmp_path)
    _, config = configuration(tmp_path, root, space)
    work = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=work,
        state=WorkState(
            activity_id=activity,
            goal="Select a fictional project",
            expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
        ),
    )
    ordinary_apply = apply_operation
    revised = []

    def apply_with_competing_revision(*args: Any, **kwargs: Any) -> Any:
        receipt = ordinary_apply(*args, **kwargs)
        resource = read_execution(root, work, owner).resources[0]
        _apply(
            root,
            space,
            owner,
            ReviseResourceRequest,
            resource_id=resource.resource_id,
            work_id=work,
            expected_revision=resource.revision,
            state=resource.state.model_copy(update={"root": config.workspace}),
        )
        revised.append(read_execution(root, work, owner))
        return receipt

    monkeypatch.setattr(selection, "apply_operation", apply_with_competing_revision)
    with pytest.raises(FoundationError) as error:
        select_work_project(config, owner, work, "code")
    assert error.value.code == "resource_unavailable" and len(revised) == 1
    resource = revised[0].resources[0]
    assert f"{resource.resource_id}@{resource.revision}" in str(error.value)
    assert resource.state.root == config.workspace
    assert read_execution(root, work, owner) == revised[0]


def test_complete_unicode_projection_and_changed_basis(tmp_path: Path) -> None:
    """Original parts stay byte-exact; a changed classification invalidates delivery."""
    root, space, owner, activity, _ = ready(tmp_path)
    upgrade_activity_setup_space(root, owner)
    text = "Вымышленное наблюдение 🐈\n" * 6000
    identifier = note(root, space, owner, text, activity=activity)
    _apply(
        root,
        space,
        owner,
        CreateMethodVersionRequest,
        method_id=initial_sleep_ref(space).method_id,
        version=1,
        definition=initial_sleep_method(),
    )
    target = tmp_path / "export"
    receipt = export_workspace_projection(root, owner, target)
    original_files = sorted(target.glob(f"source/{identifier}/000001-original*.md"))
    assert len(original_files) > 1
    assert b"".join(file.read_bytes() for file in original_files) == text.encode()
    assert receipt.complete and all((target / name).is_file() for name in receipt.files)
    validate_workspace_projection(root, owner, receipt)
    prior = read_knowledge(root, identifier, owner)
    assert isinstance(prior.state, SourceState)
    _apply(
        root,
        space,
        owner,
        ReviseKnowledgeRequest,
        record_id=identifier,
        expected_revision=1,
        state=prior.state.model_copy(update={"memory": None}),
    )
    with pytest.raises(FoundationError, match="basis changed"):
        validate_workspace_projection(root, owner, receipt)


def test_export_rechecks_revocation_and_deleted_original(tmp_path: Path) -> None:
    """A saved delivery receipt cannot bypass revoked rights or deletion of its original."""
    root, space, owner, activity, _ = ready(tmp_path)
    upgrade_activity_setup_space(root, owner)
    identifier = note(root, space, owner, "Fictional original", activity=activity)
    grant = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest,
        grant_id=grant,
        state=GrantState(
            grantee="reader",
            actions=("record.read", "memory.transfer"),
        ),
    )
    reader = authorize_local(root, actor="reader", source_ref="fictional-reader")
    receipt = export_workspace_projection(root, reader, tmp_path / "export")
    _apply(root, space, owner, RevokeGrantRequest, grant_id=grant, expected_revision=1)
    with pytest.raises(FoundationError, match="permission"):
        validate_workspace_projection(root, reader, receipt)
    _apply(root, space, owner, DeleteKnowledgeRequest, record_id=identifier, expected_revision=1)
    with pytest.raises(FoundationError, match="removed"):
        validate_workspace_projection(root, owner, receipt)


def test_git_decline_changed_files_wrong_remote_and_unknown_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local Git stages only the packet; uncertain sends cannot claim success or retry."""
    root, space, owner, _, _ = ready(tmp_path)
    upgrade_activity_setup_space(root, owner)
    _, config = configuration(tmp_path, root, space)
    personal = config.workspace
    for git_args in (
        ("init", "--initial-branch=main"),
        ("config", "user.name", "Fictional"),
        ("config", "user.email", "fictional@example.invalid"),
        ("remote", "add", "origin", config.git.url if config.git else ""),
    ):
        subprocess.run(
            ["git", *git_args],
            cwd=personal,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    (personal / "README.md").write_text("Fictional personal space\n", encoding="utf-8")
    ordinary_command = delivery._command

    def command(directory: Path, args: list[str]) -> str:
        if args[0] == "gh":
            return json.dumps({"nameWithOwner": "fictional/personal", "visibility": "PRIVATE"})
        return ordinary_command(directory, args)

    monkeypatch.setattr(delivery, "_command", command)
    item = prepare_git(config, owner)
    assert all("space/" not in name for name in item.files)
    assert defer_git(config, item.preparation_id).status == "deferred"
    assert (
        not subprocess.run(
            ["git", "log", "-1"], cwd=personal, capture_output=True, text=True, encoding="utf-8"
        ).returncode
        == 0
    )
    (personal / "README.md").write_text("Changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="file changed"):
        publish_git(config, owner, item.preparation_id, approved=True)
    item = prepare_git(config, owner)
    subprocess.run(
        ["git", "remote", "set-url", "origin", "https://example.invalid/wrong"],
        cwd=personal,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Origin differs"):
        publish_git(config, owner, item.preparation_id, approved=True)
    subprocess.run(
        ["git", "remote", "set-url", "origin", config.git.url if config.git else ""],
        cwd=personal,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    sends = []
    native_git = delivery._git

    def git(directory: Path, *args: str) -> str:
        if args[0] == "push":
            sends.append(args)
            raise ValueError("Fictional lost push response")
        return native_git(directory, *args)

    monkeypatch.setattr(delivery, "_git", git)
    with pytest.raises(ValueError, match="lost push response"):
        publish_git(config, owner, item.preparation_id, approved=True)
    saved = delivery._load(config)
    assert saved is not None and saved.status == "unknown" and saved.commit
    with pytest.raises(ValueError, match="blind retry"):
        publish_git(config, owner, item.preparation_id, approved=True)
    assert len(sends) == 1
