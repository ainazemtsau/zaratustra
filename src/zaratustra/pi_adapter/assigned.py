"""Run one Core-assigned Work in an ordinary Pi RPC through a DBOS queue."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import queue
import secrets
import shutil
import subprocess
import sys
import threading
from contextlib import closing
from dataclasses import dataclass
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4, uuid5

from zaratustra.foundation import (
    AssignAttemptRequest,
    BackupInfo,
    ClaimAttemptLaunchRequest,
    DeletionStatus,
    FoundationError,
    LocalAuthority,
    RecordAttemptStopRequest,
    RequestAttemptStopRequest,
    TechnicalVersions,
    apply_operation,
    authorize_local,
    complete_deletions,
    create_backup,
    inspect_space,
    managed_executor_start_lock,
    managed_pi_session_lock,
    read_assigned_control,
    read_execution,
    read_execution_events,
    read_space,
    read_technical_deletion_targets,
)

from .bridge import PROTOCOL_VERSION, Bridge, BridgeServer

if TYPE_CHECKING:
    from dbos import DBOSClient

EXECUTOR_VERSION = "zara-pi-rpc-dbos-3.0.0-v1"
PI_VERSION = "0.87.0"
QUEUE_NAME = "zara-assigned-rpc"


def _attempt_queue(attempt_id: UUID) -> str:
    """Keep concurrent runners from claiming another Attempt's workspace."""

    return f"{QUEUE_NAME}-{attempt_id}"


def _attempt_app_version(attempt_id: UUID) -> str:
    """DBOS recovery belongs to the runner with this exact workspace binding."""

    return f"{EXECUTOR_VERSION}-{attempt_id}"


def _existing_workflow(client: DBOSClient, attempt_id: UUID) -> Any | None:
    return next(
        (
            item
            for item in client.list_workflows(
                name=WORKFLOW_NAME,
                application_name="zaratustra-assigned-rpc",
                load_input=False,
                load_output=False,
            )
            if item.workflow_id == _workflow_id(attempt_id)
        ),
        None,
    )


WORKFLOW_NAME = "zara-assigned-work-v1"
MAX_RPC_LINE = 16 * 1024 * 1024
# Storage or maintenance contention is not a subject refusal of the assigned child.
TECHNICAL_REFUSALS = frozenset(
    {"busy", "storage", "history_busy", "maintenance_busy", "corrupt_space", "deletion_pending"}
)


@dataclass(frozen=True)
class AssignedConfig:
    space: Path
    workspace: Path
    pi_cli: Path
    pi_runtime: Path
    node: str
    provider_profile: str
    provider_base_url: str
    provider_id: str
    model_id: str
    context_window: int | None
    max_tokens: int | None
    reserve_units: int
    limit_units: int
    offline: bool = False
    pi_tools: tuple[str, ...] = ()


def executor_database(space: Path) -> Path:
    info = read_space(space)
    if info.schema_version < 4 or info.recovery_state != "active":
        raise FoundationError("unsupported_schema", "Assigned RPC needs active schema 4 or later")
    return space.resolve() / ".zara-core" / "executor.sqlite3"


def _database_url(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def _workflow_id(attempt_id: UUID) -> str:
    return f"zara-{uuid5(attempt_id, 'launch')}"


def _client(space: Path) -> DBOSClient:
    from dbos import DBOSClient

    return DBOSClient(
        system_database_url=_database_url(executor_database(space)),
        application_name="zaratustra-assigned-rpc",
        retry_connection_errors=False,
    )


def deliver_outbox(
    space: Path, authority: LocalAuthority, outbox_id: UUID | None = None
) -> tuple[UUID, ...]:
    """Relay committed Core ids to DBOS; DBOS owns queue, wait and duplicate delivery."""

    with managed_pi_session_lock(space):
        return _deliver_outbox_locked(space, authority, outbox_id)


def _deliver_outbox_locked(
    space: Path, authority: LocalAuthority, outbox_id: UUID | None
) -> tuple[UUID, ...]:

    delivered: list[UUID] = []
    overview = inspect_space(space, authority)
    client = _client(space)
    try:
        for item in overview.records:
            if item.kind != "work" or item.status == "deleted":
                continue
            snapshot = read_execution(space, item.record_id, authority)
            for entry in snapshot.outbox:
                if entry.status != "pending" or (outbox_id and entry.outbox_id != outbox_id):
                    continue
                if entry.execution_epoch != snapshot.execution_epoch:
                    continue
                attempt = next(
                    (value for value in snapshot.attempts if value.attempt_id == entry.attempt_id),
                    None,
                )
                assignment = next(
                    (
                        value
                        for value in snapshot.assignments
                        if value.attempt_id == entry.attempt_id
                    ),
                    None,
                )
                if (
                    attempt is None
                    or assignment is None
                    or attempt.status != "active"
                    or attempt.generation != entry.generation
                    or assignment.executor_version != EXECUTOR_VERSION
                ):
                    continue
                if entry.kind == "launch":
                    existing = _existing_workflow(client, entry.attempt_id)
                    client.enqueue(
                        {
                            "workflow_name": WORKFLOW_NAME,
                            "queue_name": (
                                existing.queue_name
                                if existing
                                else _attempt_queue(entry.attempt_id)
                            ),
                            "workflow_id": _workflow_id(entry.attempt_id),
                            "app_version": (
                                existing.app_version
                                if existing
                                else _attempt_app_version(entry.attempt_id)
                            ),
                            "deduplication_id": str(entry.outbox_id),
                            "duplication_policy": "return-existing",
                            "attributes": {
                                "work_id": str(entry.work_id),
                                "attempt_id": str(entry.attempt_id),
                            },
                        },
                        str(entry.work_id),
                        str(entry.attempt_id),
                        entry.execution_epoch,
                        entry.generation,
                    )
                elif entry.kind == "resume":
                    if assignment.status != "ready" or entry.wait_id is None:
                        continue
                    client.send(
                        _workflow_id(entry.attempt_id),
                        str(entry.outbox_id),
                        topic="answer",
                        idempotency_key=str(entry.outbox_id),
                    )
                delivered.append(entry.outbox_id)
    finally:
        client.destroy()
    return tuple(delivered)


def _remove_managed_tree(path: Path) -> None:
    if not path.exists():
        return
    if path.is_symlink() or path.is_junction() or not path.is_dir():
        raise FoundationError("layout", "Managed Pi RPC home is not a plain directory")
    for entry in path.rglob("*"):
        if entry.is_symlink() or entry.is_junction():
            raise FoundationError("layout", "Managed Pi RPC home contains a link")
    shutil.rmtree(path)


def _purge_technical_data(
    space: Path, authority: LocalAuthority, deleted_ids: tuple[UUID, ...]
) -> None:
    """Retire only DBOS workflows affected by Core deletion, using DBOS APIs."""

    import sqlite3

    root = space.resolve() / ".zara-core"
    targets = read_technical_deletion_targets(space, authority, deleted_ids)
    target_work_ids = {str(work_id) for work_id in targets.work_ids}
    target_attempt_ids = {str(attempt_id) for attempt_id in targets.attempt_ids}
    executor = root / "executor.sqlite3"
    if executor.is_file():
        try:
            with closing(sqlite3.connect(executor, timeout=0.25)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.rollback()
                checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                if checkpoint is None or int(checkpoint[0]) != 0:
                    raise FoundationError("maintenance_busy", "DBOS SQLite checkpoint is blocked")
                if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise FoundationError("technical_state", "DBOS SQLite integrity failed")
        except sqlite3.OperationalError as error:
            raise FoundationError(
                "maintenance_busy", f"DBOS SQLite cannot be closed for deletion: {error}"
            ) from error
        client = _client(space)
        try:
            workflows = client.list_workflows(
                name=WORKFLOW_NAME,
                application_name="zaratustra-assigned-rpc",
                load_input=False,
                load_output=False,
            )
            if (target_work_ids or target_attempt_ids) and any(
                workflow.attributes is None for workflow in workflows
            ):
                raise FoundationError("technical_state", "DBOS workflow has no deletion address")
            affected = [
                workflow
                for workflow in workflows
                if workflow.attributes is not None
                and (
                    workflow.attributes.get("work_id") in target_work_ids
                    or workflow.attributes.get("attempt_id") in target_attempt_ids
                )
            ]
            home_attempt_ids = set(target_attempt_ids)
            for workflow in affected:
                attempt = str(workflow.attributes.get("attempt_id")) if workflow.attributes else ""
                try:
                    UUID(attempt)
                except ValueError as error:
                    raise FoundationError(
                        "technical_state", "DBOS Attempt address is invalid"
                    ) from error
                home_attempt_ids.add(attempt)
            if affected:
                client.delete_workflows([workflow.workflow_id for workflow in affected])
        finally:
            client.destroy()
        with closing(sqlite3.connect(executor, timeout=0.25)) as connection:
            checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint is None or int(checkpoint[0]) != 0:
                raise FoundationError(
                    "maintenance_busy", "DBOS SQLite cleanup checkpoint is blocked"
                )
            connection.execute("VACUUM")
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise FoundationError("technical_state", "DBOS database integrity failed")
        for attempt in home_attempt_ids:
            _remove_managed_tree(root / "pi-rpc-home" / attempt)
    elif (root / "pi-rpc-home").exists():
        raise FoundationError("technical_state", "Pi RPC home has no DBOS deletion index")
    restored = root / "executor-restored.sqlite3"
    if restored.exists():
        if restored.is_symlink() or restored.is_junction() or not restored.is_file():
            raise FoundationError("layout", "Restored DBOS archive is not a plain file")
        restored.unlink()
    _remove_managed_tree(root / "pi-rpc-home-restored")


def complete_assigned_deletions(space: Path, authority: LocalAuthority) -> DeletionStatus:
    """Complete Core deletion and its managed DBOS/Pi payload cleanup under one lock."""

    return complete_deletions(space, authority, technical_cleanup=_purge_technical_data)


def create_assigned_backup(space: Path, backup_id: UUID, authority: LocalAuthority) -> BackupInfo:
    """Snapshot the managed Core/DBOS/Pi composition with its pinned runtime versions."""

    executor = space.resolve() / ".zara-core" / "executor.sqlite3"
    technical_versions = None
    if executor.exists():
        actual_dbos = version("dbos")
        if actual_dbos != "3.0.0":
            raise FoundationError("dbos_version", "Assigned backup requires DBOS 3.0.0")
        technical_versions = TechnicalVersions(
            executor=EXECUTOR_VERSION,
            dbos=actual_dbos,
            pi=PI_VERSION,
            bridge_protocol=PROTOCOL_VERSION,
        )
    return create_backup(space, backup_id, authority, technical_versions=technical_versions)


def maintenance_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Complete managed Core/Pi/DBOS deletion")
    parser.add_argument("--space", required=True, type=Path)
    args = parser.parse_args(argv)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("Start from an interactive local console for trusted maintenance")
    space = args.space.resolve()
    actor = getpass.getuser()
    print(f"Core space: {space}\nLocal user: {actor}")
    if input("Type DELETE to finish pending managed deletion: ").strip() != "DELETE":
        return 1
    authority = authorize_local(space, actor=actor, source_ref=f"local-console:{actor}:{uuid4()}")
    print(complete_assigned_deletions(space, authority).model_dump_json(indent=2))
    return 0


def _rpc_line(process: subprocess.Popen[bytes]) -> dict[str, Any]:
    if process.stdout is None:
        raise FoundationError("rpc_transport", "Pi RPC stdout is unavailable")
    raw = process.stdout.readline(MAX_RPC_LINE + 1)
    if not raw or len(raw) > MAX_RPC_LINE or not raw.endswith(b"\n"):
        raise FoundationError("rpc_transport", "Pi RPC ended or exceeded its line bound")
    try:
        result = json.loads(raw[:-1].removesuffix(b"\r"))
    except (UnicodeDecodeError, ValueError) as error:
        raise FoundationError("rpc_transport", "Pi RPC sent invalid JSONL") from error
    if not isinstance(result, dict):
        raise FoundationError("rpc_transport", "Pi RPC event is not an object")
    return result


def _rpc_line_with_stop(
    process: subprocess.Popen[bytes], stop_requested: threading.Event
) -> dict[str, Any]:
    """Keep the host responsive even if a child cannot be stopped or observed."""

    pending: queue.Queue[dict[str, Any] | Exception] = queue.Queue(maxsize=1)

    def read_one() -> None:
        try:
            pending.put(_rpc_line(process))
        except Exception as error:
            pending.put(error)

    threading.Thread(target=read_one, daemon=True).start()
    while True:
        if stop_requested.is_set():
            raise FoundationError("rpc_stop_requested", "Core closed this assigned Pi turn")
        try:
            result = pending.get(timeout=0.25)
        except queue.Empty:
            continue
        if isinstance(result, Exception):
            raise result
        return result


def _rpc_prompt(
    process: subprocess.Popen[bytes], message: str, stop_requested: threading.Event
) -> None:
    if stop_requested.is_set():
        raise FoundationError("rpc_stop_requested", "Core closed this assigned Pi turn")
    if process.stdin is None or process.poll() is not None:
        raise FoundationError("rpc_stopped", "Pi RPC is not running")
    request_id = secrets.token_hex(16)
    command = {"id": request_id, "type": "prompt", "message": message}
    process.stdin.write((json.dumps(command, ensure_ascii=False) + "\n").encode("utf-8"))
    process.stdin.flush()
    accepted = False
    while True:
        event = _rpc_line_with_stop(process, stop_requested)
        if event.get("type") == "extension_error":
            raise FoundationError("rpc_extension", "Pi extension rejected the assigned turn")
        if event.get("type") == "response" and event.get("id") == request_id:
            if event.get("success") is not True:
                raise FoundationError("rpc_prompt", "Pi refused the assigned prompt")
            accepted = True
        if event.get("type") == "agent_settled":
            if not accepted:
                raise FoundationError("rpc_transport", "Pi settled before prompt acceptance")
            return


def _control_stop_requested(
    config: AssignedConfig, authority: LocalAuthority, work_id: UUID, attempt_id: UUID
) -> bool:
    try:
        return not read_assigned_control(config.space, work_id, attempt_id, authority)
    except FoundationError:
        # Lost runner rights or an unavailable Core gate stop the child safely.
        return True


def _rpc_stop_commands(process: subprocess.Popen[bytes]) -> None:
    if process.stdin is None or process.poll() is not None:
        return
    for kind in ("clear_queue", "abort"):
        try:
            process.stdin.write(
                (json.dumps({"id": secrets.token_hex(16), "type": kind}) + "\n").encode("utf-8")
            )
            process.stdin.flush()
        except (OSError, ValueError):
            return


def _terminate_pi(process: subprocess.Popen[bytes]) -> bool:
    """Return true only after observing exit; a refused stop remains unknown."""

    try:
        if process.poll() is not None:
            return True
    except OSError:
        pass
    for action in (process.terminate, process.kill):
        try:
            action()
        except OSError:
            pass
        try:
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            continue
        return True
    try:
        return process.poll() is not None
    except OSError:
        return False


def _watch_core_stop(
    config: AssignedConfig,
    authority: LocalAuthority,
    work_id: UUID,
    attempt_id: UUID,
    process: subprocess.Popen[bytes],
    finished: threading.Event,
    stop_requested: threading.Event,
    stop_lock: threading.Lock,
) -> None:
    """Observe only this claimed Attempt and wake its DBOS wait on a Core stop."""

    while not finished.wait(0.5):
        if not _control_stop_requested(config, authority, work_id, attempt_id):
            continue
        stop_requested.set()
        _rpc_stop_commands(process)
        with stop_lock:
            _terminate_pi(process)
        client = None
        try:
            client = _client(config.space)
            signal_id = uuid5(attempt_id, "rpc-stop-signal")
            client.send(
                _workflow_id(attempt_id),
                str(signal_id),
                topic="answer",
                idempotency_key=str(signal_id),
            )
        except Exception as error:
            print(f"Assigned stop wake failed for {attempt_id}: {error}", file=sys.stderr)
        finally:
            if client is not None:
                client.destroy()
        return


def _current_snapshot(
    config: AssignedConfig,
    authority: LocalAuthority,
    work_id: UUID,
    attempt_id: UUID,
    epoch: int,
    generation: int,
    *,
    check_plan: bool = True,
) -> Any:
    snapshot = read_execution(config.space, work_id, authority)
    attempt = next((x for x in snapshot.attempts if x.attempt_id == attempt_id), None)
    assignment = next((x for x in snapshot.assignments if x.attempt_id == attempt_id), None)
    if (
        snapshot.execution_epoch != epoch
        or attempt is None
        or attempt.status != "active"
        or attempt.generation != generation
        or assignment is None
        or assignment.executor_version != EXECUTOR_VERSION
        or assignment.status not in ("assigned", "waiting", "ready")
        or "work.execute" not in snapshot.work_rights
        or "model.invoke" not in snapshot.work_rights
    ):
        raise FoundationError(
            "stale_attempt", "Assigned Work no longer has current execution authority"
        )
    # A child re-reads its pinned plan, dependencies and Method use from Core each time.
    if (
        check_plan
        and snapshot.composition is not None
        and not read_assigned_control(config.space, work_id, attempt_id, authority)
    ):
        raise FoundationError(
            "stale_plan", "Composite child no longer matches its current plan and dependencies"
        )
    return snapshot


def _record_stop(
    config: AssignedConfig,
    authority: LocalAuthority,
    work_id: UUID,
    attempt_id: UUID,
    session_id: UUID,
    *,
    observed: bool,
) -> None:
    snapshot = read_execution(config.space, work_id, authority)
    assignment = next((x for x in snapshot.assignments if x.attempt_id == attempt_id), None)
    if assignment is None or assignment.status in ("stopped", "unknown", "interrupted"):
        return
    # A stopped child does not establish the outcome of a request already sent.
    # Keep the resource fenced until that external outcome is reconciled.
    if any(
        invocation.attempt_id == attempt_id and invocation.status in ("admitted", "sent", "unknown")
        for invocation in snapshot.invocations
    ):
        observed = False
    if assignment.status != "stop_requested":
        apply_operation(
            config.space,
            RequestAttemptStopRequest(
                operation_id=uuid5(attempt_id, "rpc-stop-request"),
                space_id=authority.space_id,
                actor=authority.actor,
                attempt_id=attempt_id,
                work_id=work_id,
                session_id=session_id,
                expected_assignment_revision=assignment.revision,
                reason="Pi RPC reached a terminal process outcome",
            ),
            authority,
        )
        snapshot = read_execution(config.space, work_id, authority)
        assignment = next(x for x in snapshot.assignments if x.attempt_id == attempt_id)
    apply_operation(
        config.space,
        RecordAttemptStopRequest(
            operation_id=uuid5(attempt_id, "rpc-stop-observed" if observed else "rpc-stop-unknown"),
            space_id=authority.space_id,
            actor=authority.actor,
            attempt_id=attempt_id,
            work_id=work_id,
            session_id=session_id,
            expected_assignment_revision=assignment.revision,
            outcome="stopped" if observed else "unknown",
        ),
        authority,
    )


def _execute(
    config: AssignedConfig,
    authority: LocalAuthority,
    work_id: UUID,
    attempt_id: UUID,
    epoch: int,
    generation: int,
) -> str:
    # Hold the maintenance fence through process observation and Core stop recording.
    with managed_pi_session_lock(config.space):
        return _execute_under_lock(config, authority, work_id, attempt_id, epoch, generation)


def _execute_under_lock(
    config: AssignedConfig,
    authority: LocalAuthority,
    work_id: UUID,
    attempt_id: UUID,
    epoch: int,
    generation: int,
) -> str:
    from dbos import DBOS

    # The launch claim below is the Core gate for a child's plan, pin and dependencies.
    snapshot = _current_snapshot(
        config, authority, work_id, attempt_id, epoch, generation, check_plan=False
    )
    attempt = next(x for x in snapshot.attempts if x.attempt_id == attempt_id)
    if attempt.resource_id not in {
        x.resource_id for x in snapshot.resources if x.state.root == config.workspace.resolve()
    }:
        raise FoundationError(
            "resource_unavailable", "Assigned resource differs from RPC workspace"
        )
    # This Core receipt is committed before Pi can start. A DBOS replay has a fresh
    # nonce and therefore cannot mistake a previous launch for its own work.
    try:
        apply_operation(
            config.space,
            ClaimAttemptLaunchRequest(
                operation_id=uuid5(attempt_id, "rpc-launch-claim"),
                space_id=authority.space_id,
                actor=authority.actor,
                attempt_id=attempt_id,
                work_id=work_id,
                session_id=attempt.session_id,
                expected_assignment_revision=next(
                    x.revision for x in snapshot.assignments if x.attempt_id == attempt_id
                ),
                claim_nonce=uuid4(),
            ),
            authority,
        )
    except FoundationError as error:
        if error.code in ("operation_conflict", "history_unavailable"):
            _record_stop(config, authority, work_id, attempt_id, attempt.session_id, observed=False)
            raise FoundationError(
                "process_outcome_unknown", "Earlier Pi RPC launch cannot be replayed safely"
            ) from error
        if snapshot.composition is not None and error.code not in TECHNICAL_REFUSALS:
            # A subject refusal came before any Pi process or HTTP send; close the
            # child assignment as observed stopped so its resource is not held.
            try:
                _record_stop(
                    config, authority, work_id, attempt_id, attempt.session_id, observed=True
                )
            except FoundationError:
                pass
        raise
    extension = Path(str(files("zaratustra.pi_adapter").joinpath("extension.ts")))
    installed = config.pi_runtime / f"zaratustra-assigned-{attempt_id}.ts"
    server: BridgeServer | None = None
    thread: threading.Thread | None = None
    process: subprocess.Popen[bytes] | None = None
    monitor: threading.Thread | None = None
    monitor_done = threading.Event()
    stop_requested = threading.Event()
    stop_lock = threading.Lock()
    observed = False
    try:
        with managed_pi_session_lock(config.space):
            shutil.copy2(extension, installed)
            bridge = Bridge(
                config.space,
                authority,
                config.workspace,
                config.limit_units,
                assigned_attempt_id=attempt_id,
                assigned_session_id=attempt.session_id,
            )
            server = BridgeServer(bridge)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            parsed = urlsplit(config.provider_base_url)
            managed_home = config.space.resolve() / ".zara-core" / "pi-rpc-home" / str(attempt_id)
            managed_home.mkdir(parents=True, exist_ok=True)
            pi_agent_home = managed_home / "pi-agent"
            pi_agent_home.mkdir(exist_ok=True)
            (pi_agent_home / "settings.json").write_text(
                json.dumps(
                    {
                        "cacheWarming": "off",
                        "enableInstallTelemetry": False,
                        "defaultProjectTrust": "never",
                        "retry": {
                            "enabled": False,
                            "maxRetries": 0,
                            "provider": {"maxRetries": 0, "timeoutMs": 30000},
                        },
                    },
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
            environment = {
                key: value
                for key, value in os.environ.items()
                if key.upper()
                in {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP"}
            }
            environment.update(
                {
                    "HOME": str(managed_home),
                    "USERPROFILE": str(managed_home),
                    "APPDATA": str(managed_home / "AppData"),
                    "LOCALAPPDATA": str(managed_home / "LocalAppData"),
                    "PI_CODING_AGENT_DIR": str(pi_agent_home),
                    "ZARA_CORE_ENDPOINT": f"http://127.0.0.1:{server.server_port}",
                    "ZARA_CORE_TOKEN": bridge.token,
                    "ZARA_RESERVE_UNITS": str(config.reserve_units),
                    "ZARA_PROVIDER_PROFILE": config.provider_profile,
                    "ZARA_PROVIDER_BASE_URL": config.provider_base_url,
                    "ZARA_PROVIDER_ORIGIN": f"{parsed.scheme}://{parsed.netloc}",
                    "ZARA_LOCAL_PROVIDER_ID": config.provider_id,
                    "ZARA_LOCAL_MODEL_ID": config.model_id,
                    "ZARA_INITIAL_ACTIVITY_ID": str(snapshot.activity.activity_id),
                    "ZARA_INITIAL_WORK_ID": str(work_id),
                    "ZARA_ASSIGNED_ATTEMPT_ID": str(attempt_id),
                    "ZARA_ASSIGNED_SESSION_ID": str(attempt.session_id),
                    "PI_SKIP_VERSION_CHECK": "1",
                    "PI_TELEMETRY": "0",
                }
            )
            if config.context_window is not None:
                environment["ZARA_LOCAL_CONTEXT_WINDOW"] = str(config.context_window)
            if config.max_tokens is not None:
                environment["ZARA_LOCAL_MAX_TOKENS"] = str(config.max_tokens)
            if config.offline:
                environment["PI_OFFLINE"] = "1"
            command = [
                config.node,
                str(config.pi_cli),
                "--mode",
                "rpc",
                "--provider",
                config.provider_id,
                "--model",
                config.model_id,
                "--extension",
                str(installed),
                "--no-extensions",
                "--no-context-files",
                "--no-session",
                "--no-skills",
                "--no-prompt-templates",
                "--no-themes",
                "--no-approve",
            ]
            if config.pi_tools:
                command.extend(["--tools", ",".join(config.pi_tools)])
            else:
                command.append("--no-tools")
            if config.offline:
                command.append("--offline")
            process = subprocess.Popen(
                command,
                cwd=config.workspace,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            monitor = threading.Thread(
                target=_watch_core_stop,
                args=(
                    config,
                    authority,
                    work_id,
                    attempt_id,
                    process,
                    monitor_done,
                    stop_requested,
                    stop_lock,
                ),
                daemon=True,
            )
            monitor.start()
            _current_snapshot(config, authority, work_id, attempt_id, epoch, generation)
            first = (
                "Perform the assigned Core Work using the exact context supplied by Zaratustra. "
                "Return only one JSON object. If a condition is unknown, return "
                '{"zara":"wait","partial":"what is known",'
                '"question":"one exact question","remainder":"what remains"}. '
                'Otherwise return {"zara":"final","text":"the result"}. Do not call tools.'
            )
            _rpc_prompt(process, first, stop_requested)
            current = _current_snapshot(config, authority, work_id, attempt_id, epoch, generation)
            open_waits = [
                x for x in current.waits if x.attempt_id == attempt_id and x.status == "open"
            ]
            if open_waits:
                while True:
                    if stop_requested.is_set():
                        raise FoundationError(
                            "rpc_stop_requested", "Core closed this assigned Pi wait"
                        )
                    current = _current_snapshot(
                        config, authority, work_id, attempt_id, epoch, generation
                    )
                    signal = DBOS.recv("answer", timeout_seconds=30)
                    if signal is not None:
                        break
                current = _current_snapshot(
                    config, authority, work_id, attempt_id, epoch, generation
                )
                wait = next((x for x in current.waits if x.wait_id == open_waits[0].wait_id), None)
                if (
                    wait is None
                    or wait.status != "answered"
                    or wait.answer is None
                    or str(uuid5(wait.wait_id, "answer-continuation")) != str(signal)
                ):
                    raise FoundationError(
                        "stale_wait", "Wake signal does not match the Core answer"
                    )
                if process.poll() is not None:
                    raise FoundationError("rpc_stopped", "Pi RPC exited before the answer")
                _rpc_prompt(
                    process,
                    "Continue the same assigned Work from the saved Core remainder "
                    "and partial Artifact. "
                    "Use the addressed answer in Core context. Return only "
                    '{"zara":"final","text":"the final result"}. Do not call tools.',
                    stop_requested,
                )
                current = _current_snapshot(
                    config, authority, work_id, attempt_id, epoch, generation
                )
            if not current.outputs or current.work.state.status != "proposed":
                raise FoundationError("rpc_result", "Pi RPC did not publish the declared Artifact")
            return "proposed"
    finally:
        monitor_done.set()
        if process is not None:
            with stop_lock:
                observed = _terminate_pi(process)
        if monitor is not None:
            monitor.join(timeout=5)
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=5)
        installed.unlink(missing_ok=True)
        _record_stop(
            config,
            authority,
            work_id,
            attempt_id,
            attempt.session_id,
            observed=observed or process is None,
        )


def resolve_assigned_work(space: Path, authority: LocalAuthority, attempt_id: UUID) -> UUID:
    """Resolve a live Attempt without opening unrelated deleted Work payloads."""

    overview = inspect_space(space, authority)
    work_id = next(
        (
            item.record_id
            for item in overview.records
            if item.kind == "work"
            and item.status != "deleted"
            and any(
                x.attempt_id == attempt_id
                for x in read_execution(space, item.record_id, authority).attempts
            )
        ),
        None,
    )
    if work_id is None:
        raise FoundationError("stale_attempt", "Assigned Attempt or its Work is unavailable")
    return work_id


def run_assigned(config: AssignedConfig, authority: LocalAuthority, attempt_id: UUID) -> str:
    """Start DBOS, relay one committed launch and wait for its addressed workflow."""

    with managed_pi_session_lock(config.space):
        return _run_assigned_locked(config, authority, attempt_id)


def _run_assigned_locked(
    config: AssignedConfig, authority: LocalAuthority, attempt_id: UUID
) -> str:

    from dbos import DBOS

    config = AssignedConfig(
        **{
            **config.__dict__,
            "space": config.space.resolve(),
            "workspace": config.workspace.resolve(),
        }
    )
    package_root = config.pi_runtime / "node_modules" / "@earendil-works" / "pi-coding-agent"
    package_file = package_root / "package.json"
    expected_cli = package_root / "dist" / "bundle" / "cli.js"
    if not package_file.is_file() or not expected_cli.is_file():
        raise FoundationError("rpc_runtime", "Pinned ordinary Pi runtime is unavailable")
    try:
        package = json.loads(package_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise FoundationError("pi_version", "Pi package metadata is unreadable") from error
    if (
        not isinstance(package, dict)
        or package.get("name") != "@earendil-works/pi-coding-agent"
        or package.get("version") != PI_VERSION
        or config.pi_cli.resolve() != expected_cli.resolve()
    ):
        raise FoundationError("pi_version", "Assigned Pi RPC requires pinned Pi 0.87.0")
    if config.provider_profile not in ("local-completions", "codex-sse"):
        raise FoundationError("rpc_profile", "Pi provider transport profile is unsupported")
    parsed = urlsplit(config.provider_base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise FoundationError("rpc_profile", "Pi provider needs an absolute HTTP URL")
    if config.provider_profile == "codex-sse" and config.provider_id != "openai-codex":
        raise FoundationError("rpc_profile", "Codex SSE needs the upstream provider id")
    if config.provider_profile == "local-completions" and (
        not config.provider_id
        or not config.context_window
        or not config.max_tokens
        or config.context_window < 1
        or config.max_tokens < 1
    ):
        raise FoundationError("rpc_profile", "Local Provider needs model and context bounds")
    if any(tool not in {"read", "grep", "find", "ls"} for tool in config.pi_tools):
        raise FoundationError("rpc_tools", "Assigned RPC admits only read-only Pi tools")
    work_id = resolve_assigned_work(config.space, authority, attempt_id)
    snapshot = read_execution(config.space, work_id, authority)
    attempt = next(x for x in snapshot.attempts if x.attempt_id == attempt_id)
    assignment = next(x for x in snapshot.assignments if x.attempt_id == attempt_id)
    if assignment.executor_version != EXECUTOR_VERSION:
        raise FoundationError("executor_version", "Assigned executor version is not installed")
    if assignment.status == "stop_requested" and any(
        item.attempt_id == attempt_id and item.kind == "launch" and item.status == "cancelled"
        for item in snapshot.outbox
    ):
        # The plan closed this Attempt before its launch outbox was delivered. There
        # is no DBOS workflow to retrieve; observe the absent Pi process locally.
        cursor = 0
        claimed = False
        while rows := read_execution_events(config.space, work_id, cursor, authority):
            if any(
                row["kind"] == "claim_attempt_launch" and row["attempt_id"] == str(attempt_id)
                for row in rows
            ):
                claimed = True
                break
            cursor = int(str(rows[-1]["sequence"]))
        if not claimed:
            _record_stop(config, authority, work_id, attempt_id, attempt.session_id, observed=True)
            raise FoundationError("stale_plan", "Core fenced the Attempt before Pi launched")
    queue_name = _attempt_queue(attempt_id)
    # DBOS SQLite schema migration is not safe under two cold process starts.
    # Keep the lookup and launch in one short space-wide critical section. The
    # outer Pi session lock continues to cover maintenance for the whole run.
    with managed_executor_start_lock(config.space):
        existing = None
        if executor_database(config.space).is_file():
            client = _client(config.space)
            try:
                existing = _existing_workflow(client, attempt_id)
                if existing is not None and (
                    (
                        existing.app_version == EXECUTOR_VERSION
                        and existing.status in {"ENQUEUED", "PENDING"}
                    )
                    or (
                        existing.app_version == _attempt_app_version(attempt_id)
                        and existing.status == "PENDING"
                        and existing.executor_id == "local"
                    )
                ):
                    # Recovery stays addressed to this Attempt and retains the
                    # original workflow ID and DBOS steps.
                    client.resume_workflow(_workflow_id(attempt_id), queue_name=queue_name)
            finally:
                client.destroy()
        application_version = existing.app_version if existing else _attempt_app_version(attempt_id)
        if application_version not in (EXECUTOR_VERSION, _attempt_app_version(attempt_id)):
            raise FoundationError("executor_version", "DBOS workflow has an unexpected version")
        DBOS(
            config={
                "name": "zaratustra-assigned-rpc",
                "system_database_url": _database_url(executor_database(config.space)),
                "application_version": application_version,
                "executor_id": str(attempt_id),
            }
        )

        @DBOS.workflow(name=WORKFLOW_NAME)
        def assigned_work(work: str, attempt: str, epoch: int, generation: int) -> str:
            return _execute(config, authority, UUID(work), UUID(attempt), epoch, generation)

        # DBOS otherwise listens to every persisted queue, including the shared
        # legacy queue. Its recovery also needs this Attempt's executor identity.
        DBOS.listen_queues([queue_name])
        DBOS.launch()
    try:
        DBOS.register_queue(queue_name, worker_concurrency=1)
        deliver_outbox(config.space, authority)
        return str(DBOS.retrieve_workflow(_workflow_id(attempt_id)).get_result())
    finally:
        DBOS.destroy(destroy_registry=True, workflow_completion_timeout_sec=1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--pi-cli", required=True, type=Path)
    parser.add_argument("--pi-runtime", required=True, type=Path)
    parser.add_argument("--attempt-id", type=UUID)
    parser.add_argument("--work-id", type=UUID)
    parser.add_argument("--resource-id", type=UUID)
    parser.add_argument("--node", default="node")
    parser.add_argument(
        "--provider-profile", choices=("local-completions", "codex-sse"), required=True
    )
    parser.add_argument("--provider-base-url", required=True)
    parser.add_argument("--provider-id")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--context-window", type=int)
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--pi-tools", help="Comma-separated read-only Pi tools")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--reserve-units", required=True, type=int)
    parser.add_argument("--limit-units", required=True, type=int)
    args = parser.parse_args(argv)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("Start from an interactive local console for trusted setup")
    if args.attempt_id is None and (args.work_id is None or args.resource_id is None):
        parser.error("Choose an assigned Attempt or a Work and resource for assignment")
    if args.attempt_id is not None and (args.work_id is not None or args.resource_id is not None):
        parser.error("Choose either an Attempt or a new assignment")
    config = AssignedConfig(
        space=args.space.resolve(),
        workspace=args.workspace.resolve(),
        pi_cli=args.pi_cli.resolve(),
        pi_runtime=args.pi_runtime.resolve(),
        node=args.node,
        provider_profile=args.provider_profile,
        provider_base_url=args.provider_base_url,
        provider_id=args.provider_id
        or ("openai-codex" if args.provider_profile == "codex-sse" else ""),
        model_id=args.model_id,
        context_window=args.context_window,
        max_tokens=args.max_tokens,
        reserve_units=args.reserve_units,
        limit_units=args.limit_units,
        offline=args.offline,
        pi_tools=tuple(item.strip() for item in args.pi_tools.split(",")) if args.pi_tools else (),
    )
    actor = getpass.getuser()
    print(f"Core: {config.space}\nWorkspace: {config.workspace}\nActor: {actor}")
    print(f"Pi: {config.pi_cli}\nProvider: {config.provider_base_url}\nModel: {config.model_id}")
    if input("Type ASSIGN to use this local identity and paths: ").strip() != "ASSIGN":
        return 1
    authority = authorize_local(
        config.space, actor=actor, source_ref=f"local-console:{actor}:{uuid4()}"
    )
    attempt_id = args.attempt_id
    if attempt_id is None:
        assert args.work_id is not None and args.resource_id is not None
        snapshot = read_execution(config.space, args.work_id, authority)
        resource = next((x for x in snapshot.resources if x.resource_id == args.resource_id), None)
        if resource is None or resource.state.root != config.workspace:
            parser.error("Selected Work resource differs from the RPC workspace")
        attempt_id = uuid4()
        apply_operation(
            config.space,
            AssignAttemptRequest(
                operation_id=uuid5(attempt_id, "assign"),
                space_id=authority.space_id,
                actor=authority.actor,
                attempt_id=attempt_id,
                work_id=args.work_id,
                expected_work_revision=snapshot.work.revision,
                resource_id=args.resource_id,
                expected_resource_revision=resource.revision,
                session_id=uuid4(),
                previous_attempt_id=snapshot.attempts[-1].attempt_id if snapshot.attempts else None,
                executor_version=EXECUTOR_VERSION,
            ),
            authority,
        )
    print(run_assigned(config, authority, attempt_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
