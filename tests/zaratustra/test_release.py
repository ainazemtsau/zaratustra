"""Selecting a restored space preserves the already selected operation history."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from zaratustra.release import _preserves_operations, _register_config, _run, _selected_config


def _upgrade_config(
    tmp_path: Path, root: Path, actor: str, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Exercise real config parsing without requiring an installed Pi process."""
    from zaratustra import pi_adapter, release
    from zaratustra.foundation import read_space
    from zaratustra.workspace import LaunchConfig

    dll = tmp_path / "runtime" / "sqlite3.dll"
    dll.parent.mkdir()
    dll.write_bytes(b"fictional-configured-runtime")
    monkeypatch.setattr(
        release, "SQLITE_DLL_SHA256", hashlib.sha256(dll.read_bytes()).hexdigest().upper()
    )
    # _config changes this variable; restore the process's admitted runtime at teardown.
    if "ZARATUSTRA_SQLITE_DLL" in os.environ:
        monkeypatch.setenv("ZARATUSTRA_SQLITE_DLL", os.environ["ZARATUSTRA_SQLITE_DLL"])
    else:
        monkeypatch.delenv("ZARATUSTRA_SQLITE_DLL", raising=False)
    runtime = pi_adapter.PiRuntime(dll.parent, dll.parent / "cli.js", "1.0.4")
    monkeypatch.setattr(pi_adapter, "system_pi_runtime", lambda: runtime)
    monkeypatch.setattr(getpass, "getuser", lambda: actor)
    config = LaunchConfig(
        version=1,
        actor=actor,
        space_id=read_space(root).space_id,
        space=root,
        workspace=tmp_path / "workdir",
        sqlite_dll=dll,
        pi_runtime=runtime.root,
        pi_source="system",
        provider_profile="local-completions",
        provider_base_url="http://localhost:1",
        provider_id="local",
        model_id="fictional",
        reserve_units=10,
    )
    selected = tmp_path / "config.json"
    selected.write_text(config.model_dump_json(), encoding="utf-8")
    return selected


def _upgrade_to(root: Path, actor: str, target: int) -> None:
    """Create historical fixtures only through the public schema operations."""
    from zaratustra import foundation as core

    owner = core.authorize_local(root, actor=actor, source_ref="fictional-upgrade-fixture")
    upgrades = (
        core.upgrade_space,
        core.upgrade_execution_space,
        core.upgrade_continuation_space,
        core.upgrade_composition_space,
        core.upgrade_child_execution_space,
        core.upgrade_plan_revision_space,
        core.upgrade_parent_execution_space,
        core.upgrade_binding_space,
        core.upgrade_knowledge_space,
        core.upgrade_development_space,
        core.upgrade_change_package_space,
        core.upgrade_memory_space,
        core.upgrade_activity_setup_space,
        core.upgrade_structures_space,
        core.upgrade_workflow_space,
        core.upgrade_conversation_space,
        core.upgrade_delivery_correlation_space,
    )
    for version, upgrade in enumerate(upgrades, 2):
        if core.read_space(root).schema_version < version <= target:
            upgrade(root, owner)


@pytest.mark.parametrize("schema", (1, 2, 6, 14, 15, 16, 17))
def test_confirmed_upgrade_uses_the_public_chain_after_a_verified_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schema: int
) -> None:
    from zaratustra import foundation as core
    from zaratustra import pi_adapter, release

    root = tmp_path / "space"
    root.mkdir()
    info = core.initialize_space(root)
    actor = "fictional-owner"
    owner = core.authorize_local(root, actor=actor, source_ref="fictional-console")
    bootstrap = core.BootstrapRequest(
        operation_id=uuid4(),
        space_id=info.space_id,
        actor=actor,
        decision_id=uuid4(),
        grant_id=uuid4(),
    )
    receipt = core.apply_operation(root, bootstrap, owner)
    _upgrade_to(root, actor, schema)
    before = core.read_space(root)
    with pytest.raises(core.FoundationError, match="upgrade_required"):
        pi_adapter.prepare_space(root, actor, create=False)
    assert core.read_space(root) == before
    selected = _upgrade_config(tmp_path, root, actor, monkeypatch)
    prompts: list[str] = []

    def confirm(prompt: str) -> str:
        prompts.append(prompt)
        return "UPGRADE"

    monkeypatch.setattr("builtins.input", confirm)
    assert release.main(["upgrade", "--config", str(selected)]) == 0
    current = core.read_space(root)
    assert current.schema_version == 18
    assert current.space_id == before.space_id
    assert current.execution_epoch == before.execution_epoch
    assert len(prompts) == 1 and "verified backup" in prompts[0]
    assert core.read_receipt(root, bootstrap.operation_id, owner) == receipt
    packages = list((root / ".zara-core" / "backups").iterdir())
    assert len(packages) == 1
    manifest = json.loads((packages[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == schema
    restored = tmp_path / "restored"
    restored.mkdir()
    core.restore_backup(
        packages[0], restored, core.authorize_recovery(actor=actor, source_ref="fictional-restore")
    )
    assert core.read_space(restored).schema_version == schema
    assert core.read_space(restored).space_id == before.space_id
    assert core.read_space(restored).recovery_state == "quarantined"


def test_declined_upgrade_preserves_the_existing_space_without_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.zaratustra.foundation.test_execution import ready
    from zaratustra import foundation as core
    from zaratustra import release

    root, _, _, _, work_id, _, owner = ready(tmp_path)
    _upgrade_to(root, owner.actor, 15)
    selected = _upgrade_config(tmp_path, root, owner.actor, monkeypatch)
    before = core.inspect_space(root, owner)
    execution = core.read_execution(root, work_id, owner)
    monkeypatch.setattr("builtins.input", lambda _: "cancel")
    assert release.main(["upgrade", "--config", str(selected)]) == 1
    assert core.inspect_space(root, owner) == before
    assert core.read_execution(root, work_id, owner) == execution


@pytest.mark.parametrize("schema", (15, 16, 17))
def test_upgrade_keeps_exact_results_acceptance_and_send_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schema: int
) -> None:
    from tests.zaratustra.foundation.test_execution import (
        InvocationFields,
        invocation,
        ready,
        start,
    )
    from zaratustra import foundation as core
    from zaratustra import release

    root, _, space, input_id, work_id, resource_id, owner = ready(tmp_path)
    _upgrade_to(root, owner.actor, schema)
    attempt, session = start(root, space, work_id, resource_id, owner)
    invocation_id, _ = invocation(root, space, work_id, attempt, session, owner, 10)
    common: InvocationFields = dict(
        invocation_id=invocation_id, attempt_id=attempt, work_id=work_id, session_id=session
    )
    for request in (
        core.AdmitInvocationRequest(
            operation_id=uuid4(), space_id=space, actor=owner.actor, **common
        ),
        core.SendInvocationRequest(
            operation_id=uuid4(), space_id=space, actor=owner.actor, **common
        ),
        core.FinishInvocationRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            outcome="answered",
            usage_units=7,
            **common,
        ),
        core.PublishAttemptOutputRequest(
            operation_id=uuid4(),
            space_id=space,
            actor=owner.actor,
            attempt_id=attempt,
            work_id=work_id,
            session_id=session,
            slot="summary",
            media_type="text/plain",
            content=b"Fictional verified summary",
        ),
    ):
        core.apply_operation(root, request, owner)
    accepted = core.AcceptWorkRequest(
        operation_id=uuid4(),
        space_id=space,
        actor=owner.actor,
        work_id=work_id,
        expected_revision=core.read_work(root, work_id, owner).revision,
        basis="Fictional owner separately checked the exact result",
    )
    accepted_receipt = core.apply_operation(root, accepted, owner)
    before = core.read_execution(root, work_id, owner)
    original = core.read_artifact(root, input_id, owner)
    selected = _upgrade_config(tmp_path, root, owner.actor, monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _: "UPGRADE")
    assert release.main(["upgrade", "--config", str(selected)]) == 0
    current = core.read_execution(root, work_id, owner)
    assert core.read_space(root).schema_version == 18
    assert current.space_id == before.space_id
    assert current.activity == before.activity
    assert current.work == before.work
    assert current.inputs == before.inputs and current.outputs == before.outputs
    assert current.attempts == before.attempts and current.invocations == before.invocations
    assert current.resources == before.resources
    assert current.committed_units == before.committed_units == 7
    assert current.held_units == before.held_units == 0
    assert core.read_artifact(root, input_id, owner) == original
    assert core.read_work(root, work_id, owner, revision=1).state.status == "proposed"
    assert core.read_receipt(root, accepted.operation_id, owner) == accepted_receipt


def _history(root: Path, fingerprint: str | None) -> None:
    import sqlite3

    database = root / ".zara-core" / "core.sqlite3"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE operations(operation_id TEXT PRIMARY KEY, fingerprint TEXT)"
        )
        if fingerprint is not None:
            connection.execute("INSERT INTO operations VALUES ('operation-1',?)", (fingerprint,))


def test_restored_selection_keeps_each_exact_operation(tmp_path: Path) -> None:
    import sqlite3

    original, restored = tmp_path / "original", tmp_path / "restored"
    _history(original, "original-fingerprint")
    _history(restored, "original-fingerprint")
    _preserves_operations(original, restored)
    with sqlite3.connect(restored / ".zara-core" / "core.sqlite3") as connection:
        connection.execute("UPDATE operations SET fingerprint='changed'")
    with pytest.raises(ValueError, match="omits or changes operation"):
        _preserves_operations(original, restored)
    with sqlite3.connect(restored / ".zara-core" / "core.sqlite3") as connection:
        connection.execute("DELETE FROM operations")
    with pytest.raises(ValueError, match="omits or changes operation"):
        _preserves_operations(original, restored)


def test_default_launch_reference_and_explicit_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zaratustra import release

    monkeypatch.delenv("ZARATUSTRA_CONFIG", raising=False)
    monkeypatch.setattr(release, "_launch_reference", lambda: tmp_path / "reference.json")
    with pytest.raises(ValueError, match="Select your installation"):
        _selected_config(None)
    chosen = tmp_path / "instance" / "config.json"
    _register_config(chosen)
    assert _selected_config(None) == chosen.resolve()
    other = tmp_path / "other.json"
    assert _selected_config(other) == other.resolve()
    monkeypatch.setenv("ZARATUSTRA_CONFIG", str(other))
    assert _selected_config(None) == other.resolve()
    # Bare navigation commands must inspect the selected space, not fail parsing.
    observed: list[tuple[str, str, Path]] = []
    monkeypatch.setattr(release, "_config", lambda _: {})
    monkeypatch.setattr(release, "_actor", lambda _: None)

    def inspect(args: argparse.Namespace, path: Path) -> int:
        observed.append((args.command, args.mode, path))
        return 0

    monkeypatch.setattr(release, "_workspace_cli", inspect)
    for command in ("workspace", "projects", "git"):
        assert release.main([command]) == 0
    assert observed == [
        ("workspace", "info", other.resolve()),
        ("projects", "list", other.resolve()),
        ("git", "status", other.resolve()),
    ]


@pytest.mark.parametrize("explicit", [True, False])
def test_run_uses_system_pi_and_selected_subscription_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, explicit: bool
) -> None:
    from zaratustra import pi_adapter, release

    runtime = pi_adapter.PiRuntime(tmp_path, tmp_path / "cli.js", "1.0.4")
    monkeypatch.setattr(pi_adapter, "system_pi_runtime", lambda: runtime)
    monkeypatch.setattr(release, "_ready_space", lambda _: None)
    observed: list[list[str]] = []

    def launch(command: list[str]) -> int:
        observed.append(command)
        return 0

    monkeypatch.setattr(pi_adapter, "pi_main", launch)
    config: dict[str, object] = {
        "pi_source": "system",
        "pi_runtime": str(tmp_path / "old"),
        "space": str(tmp_path / "space"),
        "workspace": str(tmp_path / "work"),
        "node": "node",
        "reserve_units": 3000,
        "provider_profile": "codex-sse",
        "provider_id": "openai-codex",
        "provider_base_url": "https://chatgpt.com/backend-api",
        "model_id": "gpt-5.6-luna",
        "subscription_agent_dir": str(tmp_path / "subscription"),
        "preferred_model": {
            "provider_profile": "codex-sse",
            "provider_id": "openai-codex",
            "model_id": "gpt-6.1-sol",
            "thinking": "high",
        },
    }
    args = argparse.Namespace(
        model="gpt-6.1-sol" if explicit else None,
        thinking="medium" if explicit else None,
        activity_id=None,
        work_id=None,
        pi_tools=None,
    )
    assert _run(args, config) == 0
    command = observed[0]
    assert command[command.index("--pi-cli") + 1] == str(runtime.cli)
    assert command[command.index("--model") + 1] == "gpt-6.1-sol"
    assert command[command.index("--thinking") + 1] == ("medium" if explicit else "high")
    assert ("--remember-selection" in command) is explicit
    assert command[command.index("--provider-profile") + 1] == "codex-sse"
    assert command[command.index("--subscription-agent-dir") + 1] == str(tmp_path / "subscription")
