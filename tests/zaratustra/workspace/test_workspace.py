"""Risks: wrong roots, lost continuation, mixed export and unintended publication."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from tests.zaratustra.foundation.test_binding import _apply
from tests.zaratustra.foundation.test_memory import note, ready
from zaratustra.foundation import (
    CreateGrantRequest,
    CreateMethodVersionRequest,
    CreateWorkRequest,
    DeleteKnowledgeRequest,
    FoundationError,
    GrantState,
    OutputContract,
    ReviseKnowledgeRequest,
    RevokeGrantRequest,
    SourceState,
    WorkState,
    authorize_local,
    export_workspace_projection,
    initial_sleep_method,
    initial_sleep_ref,
    read_execution,
    read_knowledge,
    read_space,
    upgrade_activity_setup_space,
    validate_workspace_projection,
)
from zaratustra.pi_adapter import Bridge
from zaratustra.workspace import (
    GitDestination,
    LaunchConfig,
    Project,
    defer_git,
    delivery,
    migrate_config,
    prepare_git,
    publish_git,
    read_config,
    register_project,
    select_work_project,
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
