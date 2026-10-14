"""Ordinary Pi entry upgrades only explicitly and preserves legacy execution."""

import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

import zaratustra.foundation as core
from tests.zaratustra.foundation.test_conversations import _ordinary_final_case
from zaratustra.pi_adapter import Bridge, BridgeServer
from zaratustra.pi_adapter import __main__ as entry_host
from zaratustra.pi_adapter.__main__ import _prepare_space
from zaratustra.pi_adapter.conversation import conversation


def _entry_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, core.LocalAuthority, list[str]]:
    root = tmp_path / "space"
    root.mkdir()
    owner = _prepare_space(root, "fictional-owner", create=True)
    workspace, runtime = tmp_path / "workspace", tmp_path / "runtime"
    workspace.mkdir()
    (runtime / "node_modules").mkdir(parents=True)
    cli = runtime / "fictional-pi.js"
    cli.write_text("// Launcher fixture; never executed.\n", encoding="utf-8")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "CONNECT")
    monkeypatch.setattr("getpass.getuser", lambda: owner.actor)
    arguments = [
        "--space",
        str(root),
        "--workspace",
        str(workspace),
        "--pi-cli",
        str(cli),
        "--pi-runtime",
        str(runtime),
        "--reserve-units",
        "10",
        "--provider-profile",
        "local-completions",
        "--provider-base-url",
        "http://127.0.0.1:9/v1",
        "--local-provider-id",
        "fictional-local",
        "--local-model-id",
        "fictional-model",
        "--local-context-window",
        "16384",
        "--local-max-tokens",
        "512",
    ]
    return root, owner, arguments


def test_entry_thread_start_failure_releases_acquired_server_and_core(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, owner, arguments = _entry_case(tmp_path, monkeypatch)
    before = core.read_space(root)
    records = core.inspect_space(root, owner)
    servers: list[BridgeServer] = []
    failure = RuntimeError("Fictional native server thread start failed")
    native_start = threading.Thread.start

    def start(thread: threading.Thread) -> None:
        server = getattr(getattr(thread, "_target", None), "__self__", None)
        if isinstance(server, BridgeServer):
            servers.append(server)
            with (
                pytest.raises(core.FoundationError, match="history_busy"),
                core.managed_pi_lock(root),
            ):
                raise AssertionError("Acquired server must hold the Core fence")
            raise failure
        native_start(thread)

    def no_process(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("A failed Bridge thread must not launch Pi")

    monkeypatch.setattr(threading.Thread, "start", start)
    monkeypatch.setattr(subprocess, "run", no_process)
    with pytest.raises(RuntimeError) as refused:
        entry_host.main(arguments)
    assert refused.value is failure
    assert len(servers) == 1 and servers[0].socket.fileno() == -1
    with core.managed_pi_lock(root):
        assert core.read_space(root) == before
        assert core.inspect_space(root, owner) == records


def test_entry_controller_refusal_does_not_skip_remaining_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, owner, arguments = _entry_case(tmp_path, monkeypatch)
    owner_grant = next(
        item.record_id for item in core.inspect_space(root, owner).records if item.kind == "grant"
    )
    core.apply_operation(
        root,
        core.CreateGrantRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor=owner.actor,
            grant_id=uuid4(),
            state=core.GrantState(
                grantee=owner.actor, actions=("record.read", "space.inspect", "receipt.read")
            ),
        ),
        owner,
    )
    setup, activity = uuid4(), uuid4()
    core.apply_operation(
        root,
        core.ActivitySetupRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor=owner.actor,
            action="begin",
            setup_id=setup,
            activity_id=activity,
            title="Fictional cleanup activity",
            text="Keep ordinary project observations",
        ),
        owner,
    )
    before = core.read_activity_setup(root, setup, owner)
    servers: list[BridgeServer] = []
    boundaries: list[core.SpaceInfo] = []

    def server(bridge: Bridge) -> BridgeServer:
        created = BridgeServer(bridge)
        servers.append(created)
        return created

    def process(
        command: list[str], *, cwd: Path, env: dict[str, str], check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert not check and cwd.is_dir() and env["ZARA_PROVIDER_PROFILE"] == "local-completions"
        assert servers[0].bridge.setup_controller is not None
        servers[0].bridge.setup_controller.active = setup
        core.apply_operation(
            root,
            core.RevokeGrantRequest(
                operation_id=uuid4(),
                space_id=owner.space_id,
                actor=owner.actor,
                grant_id=owner_grant,
                expected_revision=1,
            ),
            owner,
        )
        boundaries.append(core.read_space(root))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(entry_host, "BridgeServer", server)
    monkeypatch.setattr(subprocess, "run", process)
    with pytest.raises(core.FoundationError, match="permission_denied"):
        entry_host.main(arguments)
    assert len(servers) == len(boundaries) == 1 and servers[0].socket.fileno() == -1
    bridge = servers[0].bridge
    assert bridge.setup_controller is not None and bridge.setup_controller.stop.is_set()
    assert bridge.procedure_controller is not None and bridge.procedure_controller.stop.is_set()
    assert bridge.workflow_controller is not None and bridge.workflow_controller.stop.is_set()
    with core.managed_pi_lock(root):
        assert core.read_space(root) == boundaries[0]
        assert core.read_activity_setup(root, setup, owner) == before


def test_new_ordinary_space_has_delivery_correlation_schema(tmp_path: Path) -> None:
    root = tmp_path / "space"
    root.mkdir()
    authority = _prepare_space(root, "owner", create=True)
    info = core.read_space(root)
    assert info.schema_version == 18 and authority.space_id == info.space_id
    assert core.inspect_space(root, authority).records


def test_existing_schema17_requires_explicit_upgrade_before_ordinary_pi(tmp_path: Path) -> None:
    case, work, _, _ = _ordinary_final_case(tmp_path, "tool")
    root, authority = case[0], case[2]
    before = core.read_space(root)
    execution = core.read_execution(root, work, authority)
    assert before.schema_version == 17
    with pytest.raises(core.FoundationError) as refused:
        _prepare_space(root, "owner", create=False)
    assert refused.value.code == "upgrade_required"
    assert core.read_space(root) == before
    assert core.read_execution(root, work, authority) == execution


def test_explicit_entry_upgrade_preserves_old_work_and_invocation_outcomes(tmp_path: Path) -> None:
    case, work, _, _ = _ordinary_final_case(tmp_path, "valid")
    root, authority = case[0], case[2]
    old_work = core.read_work(root, work, authority)
    old_execution = core.read_execution(root, work, authority)
    upgraded = _prepare_space(root, "owner", create=False, upgrade_existing=True)
    assert core.read_space(root).schema_version == 18
    assert core.read_work(root, work, upgraded) == old_work
    assert core.read_execution(root, work, upgraded) == old_execution
    assert _prepare_space(root, "owner", create=False).space_id == upgraded.space_id


def test_legacy_cleanup_reports_upgrade_without_changing_attempt_or_sends(tmp_path: Path) -> None:
    case, work, attempt, session = _ordinary_final_case(tmp_path, "tool")
    bridge = Bridge(case[0], case[2], tmp_path)
    bridge.connect(session)
    old_work = core.read_work(case[0], work, case[2])
    bridge.select(session, old_work.state.activity_id, work)
    before = core.read_execution(case[0], work, case[2])
    with pytest.raises(core.FoundationError) as refused:
        conversation(
            bridge,
            session,
            {
                "mode": "restore",
                "work_id": str(work),
                "attempt_id": str(attempt),
                "cleanup_unsent": True,
            },
        )
    assert refused.value.code == "upgrade_required" and "18" in refused.value.detail
    assert core.read_execution(case[0], work, case[2]) == before
    assert core.read_work(case[0], work, case[2]) == old_work
    assert bridge.sessions[session] is not None
