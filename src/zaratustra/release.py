"""Installed setup and daily entry for one selected Core space and ordinary Pi."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

SQLITE_ARCHIVE_URL = "https://www.sqlite.org/2026/sqlite-dll-win-x64-3530300.zip"
SQLITE_ARCHIVE_SHA3 = "3A494861CE24D1F330EFBC6C3FB58CE4972F2CF8DF4E43122246ED987109DC8A"
SQLITE_DLL_SHA256 = "79FD9EC89DBA3F8BD64529A2CA8E9DDE6AE6EDC486C55A1D3F1CE77975A8375C"


def _config(path: Path) -> dict[str, object]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict) or result.get("version") not in (1, 2):
        raise ValueError("Unsupported launch configuration")
    sqlite_dll = Path(str(result["sqlite_dll"])).resolve()
    if (
        not sqlite_dll.is_file()
        or hashlib.sha256(sqlite_dll.read_bytes()).hexdigest().upper() != SQLITE_DLL_SHA256
    ):
        raise ValueError("Configured SQLite DLL is missing or changed")
    os.environ["ZARATUSTRA_SQLITE_DLL"] = str(sqlite_dll)
    from .workspace import LaunchConfig

    result = LaunchConfig.model_validate(result).model_dump(mode="json", exclude_none=False)
    result["_config_path"] = str(path.resolve())
    trial_limit = result.get("trial_total_send_limit")
    if trial_limit is not None:
        if isinstance(trial_limit, bool) or not isinstance(trial_limit, int) or trial_limit < 1:
            raise ValueError("Trial send limit must be a positive integer")
        os.environ["ZARA_TRIAL_MAX_TOTAL_SENDS"] = str(trial_limit)
    else:
        os.environ.pop("ZARA_TRIAL_MAX_TOTAL_SENDS", None)
    return result


def _actor(config: dict[str, object]) -> str:
    actor = getpass.getuser()
    if actor != config["actor"]:
        raise ValueError("Current local user differs from the selected trusted identity")
    return actor


def _pi_cli(runtime: Path) -> Path:
    from .pi_adapter import read_pi_runtime

    return read_pi_runtime(runtime).cli


def _runtime(config: dict[str, object]) -> tuple[Path, Path, str]:
    from .pi_adapter import read_pi_runtime, system_pi_runtime

    source = config.get("pi_source", "managed")
    if source not in ("system", "managed"):
        raise ValueError("Choose Pi source system or managed")
    runtime = (
        system_pi_runtime()
        if source == "system"
        else read_pi_runtime(Path(str(config["pi_runtime"])))
    )
    return runtime.root, runtime.cli, runtime.version


def _launch_reference() -> Path:
    return Path.home() / ".zaratustra" / "launch-config.json"


def _register_config(path: Path) -> None:
    reference = _launch_reference()
    reference.parent.mkdir(parents=True, exist_ok=True)
    pending = reference.with_suffix(".pending")
    pending.write_text(
        json.dumps({"version": 1, "config": str(path.resolve())}) + "\n", encoding="utf-8"
    )
    pending.replace(reference)


def _selected_config(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    if os.environ.get("ZARATUSTRA_CONFIG"):
        return Path(os.environ["ZARATUSTRA_CONFIG"]).expanduser().resolve()
    reference = _launch_reference()
    if not reference.is_file():
        raise ValueError("Select your installation once: zaratustra bind --config <config.json>")
    saved = json.loads(reference.read_text(encoding="utf-8"))
    if (
        not isinstance(saved, dict)
        or saved.get("version") != 1
        or not isinstance(saved.get("config"), str)
    ):
        raise ValueError("Saved launch configuration reference is invalid")
    return Path(saved["config"]).expanduser().resolve()


def _runtime_command(args: argparse.Namespace, config: dict[str, object], path: Path) -> int:
    if args.use_system:
        from .pi_adapter import system_pi_runtime

        runtime = system_pi_runtime()
        config = {**config, "pi_source": "system", "pi_runtime": str(runtime.root)}
        pending = path.with_suffix(path.suffix + ".pending")
        pending.write_text(
            json.dumps(
                {key: value for key, value in config.items() if not key.startswith("_")}, indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        pending.replace(path)
    root, cli, version = _runtime(config)
    print(
        json.dumps(
            {
                "pi_source": config.get("pi_source", "managed"),
                "pi_version": version,
                "pi_runtime": str(root),
                "pi_cli": str(cli),
            },
            indent=2,
        )
    )
    return 0


def _prepare_sqlite(destination: Path, supplied: Path | None) -> Path:
    if supplied is not None:
        blob = supplied.read_bytes()
    else:
        if os.name != "nt":
            raise ValueError("Supply a compatible local SQLite runtime on this platform")
        with urllib.request.urlopen(SQLITE_ARCHIVE_URL, timeout=60) as response:
            archive = response.read(16 * 1024 * 1024)
        if hashlib.sha3_256(archive).hexdigest().upper() != SQLITE_ARCHIVE_SHA3:
            raise ValueError("Official SQLite archive digest differs from the pinned runtime")
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            blob = bundle.read("sqlite3.dll")
    if hashlib.sha256(blob).hexdigest().upper() != SQLITE_DLL_SHA256:
        raise ValueError("SQLite DLL differs from the pinned runtime")
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending = destination.with_name(destination.name + ".pending")
    pending.write_bytes(blob)
    pending.replace(destination)
    return destination


def _prepare_pi(supplied: Path | None) -> Path:
    from .pi_adapter import read_pi_runtime, system_pi_runtime

    return (read_pi_runtime(supplied) if supplied is not None else system_pi_runtime()).root


def _setup(args: argparse.Namespace) -> int:
    if sys.version_info[:3] != (3, 13, 7):
        raise ValueError("Use the supported Python 3.13.7 to install the wheel")
    interactive = args.workspace is None
    if interactive:
        chosen = input("Personal workspace folder (separate from the product source): ").strip()
        if not chosen:
            raise ValueError("Choose a personal workspace folder")
        args.workspace = Path(chosen)
        default_space = args.workspace / "space"
        selected = input(f"Existing Core folder, or Enter for {default_space}: ").strip()
        args.space = Path(selected) if selected else default_space
        args.new_space = not (args.space / ".zara-core").exists()
        args.git_repository = (
            input("Optional private GitHub owner/repository, or Enter to skip: ").strip() or None
        )
        if args.git_repository:
            args.create_private = (
                input("Create that private repository if absent? [y/N]: ").strip().lower() == "y"
            )
        args.model_id = (
            input(f"Codex subscription model [{args.model_id}]: ").strip() or args.model_id
        )
        args.workspace.expanduser().resolve().mkdir(parents=True, exist_ok=True)
        args.space.expanduser().resolve().mkdir(parents=True, exist_ok=True)
    if args.space is None:
        args.space = args.workspace / "space"
    if args.config is None:
        args.config = (
            Path.home() / ".zaratustra" / "instances" / args.workspace.name / "config.json"
        )
        args.config.parent.mkdir(parents=True, exist_ok=True)
    config_path = args.config.expanduser().resolve()
    if config_path.exists():
        raise ValueError("Configuration already exists; use an explicit update or another path")
    if not config_path.parent.is_dir():
        raise ValueError("Create the chosen installation directory first")
    space = args.space.expanduser().resolve()
    workspace = args.workspace.expanduser().resolve()
    if not workspace.is_dir():
        raise ValueError("Choose an existing working resource directory")
    if not space.is_dir():
        raise ValueError("Choose an existing empty or initialized Core space directory")
    if (workspace / "src" / "zaratustra" / "release.py").exists():
        raise ValueError("Choose a personal folder separate from the product source checkout")
    runtime_root = (args.runtime_root or config_path.parent / "runtime").expanduser().resolve()
    if runtime_root.is_relative_to(workspace) or workspace.is_relative_to(runtime_root):
        raise ValueError("Choose a runtime outside the personal folder")
    node_version = subprocess.run(
        [args.node, "--version"], capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout.strip()
    if node_version != "v22.19.0":
        raise ValueError(f"Supported Pi runtime needs Node v22.19.0, got {node_version}")
    parsed = urlsplit(args.provider_base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Choose an absolute HTTP provider endpoint")
    if args.provider_profile == "codex-sse" and args.provider_id != "openai-codex":
        raise ValueError("Codex SSE requires the openai-codex provider id")
    if args.provider_profile == "local-completions" and (
        not args.context_window or not args.max_tokens
    ):
        raise ValueError("Local provider needs context and output bounds")
    if args.reserve_units < 1 or (
        args.limit_units is not None
        and (args.limit_units < 1 or args.reserve_units > args.limit_units)
    ):
        raise ValueError("Choose positive model resource and reserve bounds")
    actor = getpass.getuser()
    print(f"Core space: {space}\nWorking resource: {workspace}\nLocal identity: {actor}")
    print(f"Provider: {args.provider_profile} / {args.model_id} at {args.provider_base_url}")
    print(f"New space: {args.new_space}; target schema: 14")
    if input("Type SETUP to prepare this installation and selected space: ").strip() != "SETUP":
        return 1
    sqlite_dll = _prepare_sqlite(runtime_root / "sqlite3.dll", args.sqlite_dll)
    os.environ["ZARATUSTRA_SQLITE_DLL"] = str(sqlite_dll)
    from zaratustra.foundation import authorize_local, read_space

    if args.new_space:
        from .pi_adapter import prepare_space

        authority = prepare_space(space, actor, create=True)
    else:
        info = read_space(space)
        authority = authorize_local(
            space, actor=actor, source_ref=f"local-console:{actor}:{uuid4()}"
        )
        if info.recovery_state != "active":
            raise ValueError("Recover the selected Core space before setup")
    pi_runtime = _prepare_pi(args.pi_runtime)
    config: dict[str, object] = {
        "version": 2,
        "actor": actor,
        "space_id": str(authority.space_id),
        "space": str(space),
        "workspace": str(workspace),
        "personal_root": str(workspace),
        "runtime_root": str(runtime_root),
        "projects": [],
        "git": {"repository": args.git_repository, "branch": "main"}
        if args.git_repository
        else None,
        "sqlite_dll": str(sqlite_dll),
        "pi_runtime": str(pi_runtime),
        "pi_source": "managed" if args.pi_runtime is not None else "system",
        "node": args.node,
        "provider_profile": args.provider_profile,
        "provider_base_url": args.provider_base_url,
        "provider_id": args.provider_id,
        "model_id": args.model_id,
        "context_window": args.context_window,
        "max_tokens": args.max_tokens,
        "limit_units": args.limit_units,
        "reserve_units": args.reserve_units,
    }
    temp = config_path.with_suffix(config_path.suffix + ".pending")
    temp.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    temp.replace(config_path)
    _register_config(config_path)
    if args.git_repository:
        from .workspace import initialize_git, read_config

        initialize_git(read_config(config_path), create_private=args.create_private)
    print(f"Prepared: {config_path}")
    if not args.new_space and info.schema_version < 14:
        print("Existing space requires zara-core upgrade before run or assign")
    return 0


def _run(args: argparse.Namespace, config: dict[str, object]) -> int:
    _ready_space(config)
    from .pi_adapter import pi_main

    runtime, cli, pi_version = _runtime(config)
    print(f"Pi {pi_version}: {cli}")
    command = [
        "--space",
        str(config["space"]),
        "--workspace",
        str(config["workspace"]),
        "--pi-cli",
        str(cli),
        "--pi-runtime",
        str(runtime),
        "--node",
        str(config["node"]),
        "--reserve-units",
        str(config["reserve_units"]),
        "--provider-profile",
        str(config["provider_profile"]),
        "--provider-base-url",
        str(config["provider_base_url"]),
        "--model",
        str(args.model or config["model_id"]),
    ]
    if config.get("limit_units") is not None:
        command += ["--limit-units", str(config["limit_units"])]
    if config.get("free_conversation_limit_units") is not None:
        command += ["--free-conversation-limit-units", str(config["free_conversation_limit_units"])]
    if config.get("context_max_bytes") is not None:
        command += ["--context-max-bytes", str(config["context_max_bytes"])]
    if config["provider_profile"] == "local-completions":
        command += [
            "--local-provider-id",
            str(config["provider_id"]),
            "--local-model-id",
            str(config["model_id"]),
            "--local-context-window",
            str(config["context_window"]),
            "--local-max-tokens",
            str(config["max_tokens"]),
        ]
    if args.activity_id and args.work_id:
        command += ["--activity-id", str(args.activity_id), "--work-id", str(args.work_id)]
    if args.pi_tools:
        command += ["--pi-tools", args.pi_tools]
    if args.thinking:
        command += ["--thinking", args.thinking]
    if config.get("subscription_agent_dir"):
        command += ["--subscription-agent-dir", str(config["subscription_agent_dir"])]
    if config.get("version") == 2:
        command += ["--workspace-config", str(config["_config_path"])]
    return pi_main(command)


def _assign(args: argparse.Namespace, config: dict[str, object]) -> int:
    _ready_space(config)
    from .pi_adapter import assigned_main

    runtime, cli, pi_version = _runtime(config)
    print(f"Pi {pi_version}: {cli}")
    command = [
        "--space",
        str(config["space"]),
        "--workspace",
        str(config["workspace"]),
        "--pi-cli",
        str(cli),
        "--pi-runtime",
        str(runtime),
        "--node",
        str(config["node"]),
        "--provider-profile",
        str(config["provider_profile"]),
        "--provider-base-url",
        str(config["provider_base_url"]),
        "--provider-id",
        str(config["provider_id"]),
        "--model-id",
        str(config["model_id"]),
        "--reserve-units",
        str(config["reserve_units"]),
    ]
    if config.get("limit_units") is not None:
        command += ["--limit-units", str(config["limit_units"])]
    if config["context_window"]:
        command += ["--context-window", str(config["context_window"])]
    if config["max_tokens"]:
        command += ["--max-tokens", str(config["max_tokens"])]
    if config.get("subscription_agent_dir"):
        command += ["--subscription-agent-dir", str(config["subscription_agent_dir"])]
    if args.attempt_id:
        command += ["--attempt-id", str(args.attempt_id)]
    else:
        command += ["--work-id", str(args.work_id), "--resource-id", str(args.resource_id)]
    if args.pi_tools:
        command += ["--pi-tools", args.pi_tools]
    if config.get("version") == 2:
        command += ["--workspace-config", str(config["_config_path"])]
    return assigned_main(command)


def _ready_space(config: dict[str, object], *, minimum_schema: int = 14) -> None:
    from zaratustra.foundation import read_space

    info = read_space(Path(str(config["space"])))
    if config.get("space_id") and str(info.space_id) != config["space_id"]:
        raise ValueError("Selected space identity differs from the saved configuration")
    if not minimum_schema <= info.schema_version <= 14:
        raise ValueError("Run zara-core upgrade for this selected space before execution")
    if info.recovery_state != "active":
        raise ValueError("Recover the selected space before execution")


def _preserves_operations(original: Path, restored: Path) -> None:
    """Refuse a restored branch that omits or rewrites a selected Core operation."""

    import sqlite3

    old_database = original / ".zara-core" / "core.sqlite3"
    new_database = restored / ".zara-core" / "core.sqlite3"
    with (
        closing(sqlite3.connect(f"{old_database.as_uri()}?mode=ro", uri=True)) as old,
        closing(sqlite3.connect(f"{new_database.as_uri()}?mode=ro", uri=True)) as new,
    ):
        for operation_id, fingerprint in old.execute(
            "SELECT operation_id,fingerprint FROM operations"
        ):
            row = new.execute(
                "SELECT fingerprint FROM operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if row is None or row[0] != fingerprint:
                raise ValueError(
                    f"Restored space omits or changes operation {operation_id}; "
                    "preserve both spaces"
                )


def _installed_program_change(
    args: argparse.Namespace, config: dict[str, object], actor: str
) -> int:
    """Converge exact resource bytes, then record Core's observed result."""

    from zaratustra.foundation import (
        CompositeChange,
        ConfirmProgramInstallRequest,
        FoundationError,
        ProgramChange,
        RestoreCandidateRequest,
        apply_operation,
        authorize_local,
        check_program_change_boundary,
        program_target_path,
        read_artifact,
        read_change_application,
        read_development,
    )

    _ready_space(config, minimum_schema=12)
    space = Path(str(config["space"]))
    workspace = Path(str(config["workspace"])).resolve()
    authority = authorize_local(space, actor=actor, source_ref=f"local-console:{actor}:{uuid4()}")
    application, _ = read_change_application(space, args.application_id, authority)
    installing = args.command == "change-install"
    expected_status = "prepared" if installing else "stopped"
    if application.status not in (("prepared",) if installing else ("stopped", "partial")):
        raise ValueError(f"Change must be {expected_status} before this action")
    candidate = read_development(
        space, application.candidate_id, authority, revision=application.candidate_revision
    )
    if candidate.state is None or candidate.state.kind != "candidate":
        raise ValueError("Exact change candidate is unavailable")
    target = candidate.state.target
    parts = target.parts if isinstance(target, CompositeChange) else (target,)
    programs = tuple(item for item in parts if isinstance(item, ProgramChange))
    if not programs:
        raise ValueError("Change package has no program build to install")
    actions: list[tuple[Path, bytes | None, str | None, str | None, ProgramChange]] = []
    for part in programs:
        destination = program_target_path(space, part, authority)
        selected = workspace.joinpath(*part.relative_path.split("/")).resolve()
        if destination != selected:
            raise ValueError("Program resource differs from the selected working directory")
        build_ref = part.build if installing else part.from_build
        desired_hash = part.build_sha256 if installing else part.from_checksum
        content = None
        if build_ref is not None:
            artifact = read_artifact(
                space, build_ref.artifact_id, authority, revision=build_ref.revision
            )
            content = artifact.content
            if artifact.content_sha256 != desired_hash:
                raise ValueError("Managed build bytes differ from the candidate")
        actual = (
            hashlib.sha256(destination.read_bytes()).hexdigest().upper()
            if destination.is_file()
            else None
        )
        prior_hash = part.from_checksum if installing else part.build_sha256
        if actual not in (prior_hash, desired_hash):
            raise ValueError(f"Program path changed independently: {destination}")
        actions.append((destination, content, desired_hash, prior_hash, part))
    word = "INSTALL" if installing else "RESTORE"
    print(f"Change: {application.application_id} ({application.target_kind})")
    for destination, _, digest, _, _ in actions:
        print(f"{destination}: {'absent' if digest is None else digest}")
    if input(f"Type {word} to change these exact working resource files: ").strip() != word:
        return 1
    operation = (
        ConfirmProgramInstallRequest(
            operation_id=uuid4(),
            space_id=authority.space_id,
            actor=actor,
            application_id=application.application_id,
            expected_revision=application.revision,
        )
        if installing
        else RestoreCandidateRequest(
            operation_id=uuid4(),
            space_id=authority.space_id,
            actor=actor,
            application_id=application.application_id,
            expected_revision=application.revision,
            reason=args.reason,
            data_restoration=args.data_restoration,
            external_effects=args.external_effects,
        )
    )
    if check_program_change_boundary(space, operation, authority) != programs:
        raise ValueError("Program package changed after preparation")
    for destination, _, desired_hash, prior_hash, part in actions:
        if program_target_path(space, part, authority) != destination:
            raise ValueError("Program target changed during confirmation")
        actual = (
            hashlib.sha256(destination.read_bytes()).hexdigest().upper()
            if destination.is_file()
            else None
        )
        if actual not in (prior_hash, desired_hash):
            raise ValueError(f"Program path changed independently: {destination}")
    changed = False
    for destination, content, desired_hash, prior_hash, _ in actions:
        actual = (
            hashlib.sha256(destination.read_bytes()).hexdigest().upper()
            if destination.is_file()
            else None
        )
        if actual == desired_hash:
            continue
        if actual != prior_hash:
            raise ValueError(f"Program path changed independently: {destination}")
        if content is None:
            destination.unlink()
            changed = True
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        pending: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".zara-change-", dir=destination.parent, delete=False
            ) as handle:
                pending = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if prior_hash is None:
                os.link(pending, destination)
            else:
                pending.replace(destination)
            changed = True
        finally:
            if pending is not None and pending.exists():
                pending.unlink()
    try:
        receipt = apply_operation(space, operation, authority)
    except FoundationError as error:
        if changed:
            raise ValueError(
                f"Core refused {word} after file effects ({error.code}); inspect the exact "
                "working files and application before a supported retry or restoration"
            ) from error
        raise
    print(receipt.model_dump_json(indent=2))
    return 0


def _maintenance(args: argparse.Namespace, config: dict[str, object]) -> int:
    from importlib.metadata import version

    from zaratustra.foundation import (
        CompositeChange,
        FoundationError,
        ProgramChange,
        RecoverRequest,
        RestoreCandidateRequest,
        StopCandidateRequest,
        apply_operation,
        authorize_local,
        authorize_recovery,
        inspect_recovery,
        inspect_space,
        pulse_space,
        read_activity,
        read_change_application,
        read_development,
        read_execution,
        read_receipt,
        read_space,
        read_work,
        restore_backup,
    )

    actor = _actor(config)
    if args.command == "change-install":
        return _installed_program_change(args, config, actor)
    space = Path(str(config["space"]))
    if args.command == "change-restore":
        _ready_space(config, minimum_schema=12)
        authority = authorize_local(
            space, actor=actor, source_ref=f"local-console:{actor}:{uuid4()}"
        )
        application, _ = read_change_application(space, args.application_id, authority)
        candidate = read_development(
            space, application.candidate_id, authority, revision=application.candidate_revision
        )
        if candidate.state is None or candidate.state.kind != "candidate":
            raise ValueError("Exact change candidate is unavailable")
        change_target = candidate.state.target
        parts = (
            change_target.parts if isinstance(change_target, CompositeChange) else (change_target,)
        )
        if any(isinstance(part, ProgramChange) for part in parts):
            return _installed_program_change(args, config, actor)
        if application.status not in ("stopped", "partial"):
            raise ValueError("Stop the change before restoration")
        print(f"Change {application.application_id}: {application.status} -> restore")
        if input("Type RESTORE to apply the exact Core restoration: ").strip() != "RESTORE":
            return 1
        print(
            apply_operation(
                space,
                RestoreCandidateRequest(
                    operation_id=uuid4(),
                    space_id=authority.space_id,
                    actor=actor,
                    application_id=application.application_id,
                    expected_revision=application.revision,
                    reason=args.reason,
                    data_restoration=args.data_restoration,
                    external_effects=args.external_effects,
                ),
                authority,
            ).model_dump_json(indent=2)
        )
        return 0
    if args.command == "upgrade":
        info = read_space(space)
        if config.get("space_id") and str(info.space_id) != config["space_id"]:
            raise ValueError("Selected space identity differs from the saved configuration")
        if info.schema_version == 14:
            print("Core space already uses schema 14")
            return 0
        if info.schema_version > 14:
            raise ValueError("Installed program cannot upgrade a newer Core schema")
        if info.recovery_state != "active":
            raise ValueError("Recover this space before a schema upgrade")
        print(f"Space {info.space_id}: schema {info.schema_version} -> 14")
        if (
            input("Type UPGRADE to save a verified backup and migrate this space: ").strip()
            != "UPGRADE"
        ):
            return 1
        from .pi_adapter import create_assigned_backup

        authority = authorize_local(
            space, actor=actor, source_ref=f"local-console:{actor}:{uuid4()}"
        )
        backup = create_assigned_backup(space, uuid4(), authority, pi_version=_runtime(config)[2])
        print(f"Pre-upgrade backup: {backup.package}")
        from .pi_adapter import prepare_space

        prepare_space(space, actor, create=False)
        print(f"Core schema: {read_space(space).schema_version}")
        return 0
    if args.command == "verify":
        info = read_space(space)
        if config.get("space_id") and str(info.space_id) != config["space_id"]:
            raise ValueError("Selected space identity differs from the saved configuration")
        print(
            json.dumps(
                {
                    "program": version("zaratustra"),
                    "space_id": str(info.space_id),
                    "schema_version": info.schema_version,
                    "execution_epoch": info.execution_epoch,
                    "recovery_state": info.recovery_state,
                    "workspace": str(config["workspace"]),
                    "pi_cli": str(_runtime(config)[1]),
                    "pi_version": _runtime(config)[2],
                    "pi_source": config.get("pi_source", "managed"),
                },
                indent=2,
            )
        )
        return 0
    if args.command == "select":
        selected = args.space.expanduser().resolve()
        output = args.output.expanduser().resolve()
        if output.exists():
            raise ValueError("Selected configuration output already exists")
        original_space = read_space(space)
        target = read_space(selected)
        if target.space_id != original_space.space_id or target.recovery_state != "active":
            raise ValueError("Select an active restored space with the same identity")
        if (
            target.schema_version < original_space.schema_version
            or target.state_revision < original_space.state_revision
        ):
            raise ValueError(
                "Restored space is behind the selected history or schema; preserve both spaces"
            )
        _preserves_operations(space, selected)
        print(f"Space {target.space_id}: {space} -> {selected}; epoch {target.execution_epoch}")
        if input("Type SELECT to save this restored space: ").strip() != "SELECT":
            return 1
        updated = {key: value for key, value in config.items() if not key.startswith("_")}
        updated.update(space=str(selected), space_id=str(target.space_id))
        pending = output.with_name(output.name + ".pending")
        pending.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
        pending.replace(output)
        print(f"Saved: {output}")
        return 0
    if args.command == "restore":
        destination = args.destination.expanduser().resolve()
        print(f"Backup: {args.package}\nNew quarantined space: {destination}")
        if input("Type RESTORE to restore into this empty directory: ").strip() != "RESTORE":
            return 1
        recovery = authorize_recovery(actor=actor, source_ref=f"local-console:{actor}:{uuid4()}")
        print(restore_backup(args.package, destination, recovery).model_dump_json(indent=2))
        return 0
    if args.command == "recover":
        restored = args.space.expanduser().resolve()
        recovery = authorize_recovery(actor=actor, source_ref=f"local-console:{actor}:{uuid4()}")
        print(json.dumps(inspect_recovery(restored, recovery), indent=2))
        if input("Type RECOVER to establish a new local epoch: ").strip() != "RECOVER":
            return 1
        info = read_space(restored)
        receipt = apply_operation(
            restored,
            RecoverRequest(
                operation_id=uuid4(),
                space_id=info.space_id,
                actor=actor,
                decision_id=uuid4(),
                grant_id=uuid4(),
            ),
            recovery,
        )
        print(receipt.model_dump_json(indent=2))
        return 0
    authority = authorize_local(space, actor=actor, source_ref=f"local-console:{actor}:{uuid4()}")
    if args.command == "change-stop":
        application, _ = read_change_application(space, args.application_id, authority)
        print(f"Change {application.application_id}: {application.status} -> stopped")
        if input("Type STOP to prevent new use of this change: ").strip() != "STOP":
            return 1
        receipt = apply_operation(
            space,
            StopCandidateRequest(
                operation_id=uuid4(),
                space_id=authority.space_id,
                actor=actor,
                application_id=application.application_id,
                expected_revision=application.revision,
                reason=args.reason,
                started_works=args.started_works,
                external_effects=args.external_effects,
            ),
            authority,
        )
        print(receipt.model_dump_json(indent=2))
        return 0
    if args.command == "inspect":
        if args.kind == "space":
            result: object = inspect_space(space, authority).model_dump(mode="json")
        else:
            if args.id is None:
                raise ValueError("Choose --id for this inspection")
            if args.kind == "application":
                application, events = read_change_application(space, args.id, authority)
                result = {"application": application.model_dump(mode="json"), "events": events}
            elif args.kind == "activity":
                result = read_activity(space, args.id, authority).model_dump(mode="json")
            elif args.kind == "work":
                result = read_work(space, args.id, authority).model_dump(mode="json")
            elif args.kind == "development":
                result = read_development(space, args.id, authority).model_dump(mode="json")
            elif args.kind == "execution":
                result = read_execution(space, args.id, authority).model_dump(mode="json")
            else:
                result = read_receipt(space, args.id, authority).model_dump(mode="json")
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "pulse":
        checkpoint = 0
        prior: tuple[UUID, ...] = ()
        prior_operations: tuple[UUID, ...] = ()
        if args.previous_report:
            previous = json.loads(args.previous_report.read_text(encoding="utf-8"))
            if UUID(previous["space_id"]) != authority.space_id:
                raise ValueError("Pulse report belongs to another Core space")
            checkpoint = int(previous["through_revision"])
            prior = tuple(UUID(item) for item in previous["checked_records"])
            prior_operations = tuple(
                UUID(item["address"].split(":", 1)[1])
                for item in previous["findings"]
                if item["code"] == "missing_audit"
            )
        print(
            pulse_space(
                space,
                authority,
                checkpoint=checkpoint,
                previous_addresses=prior,
                previous_operations=prior_operations,
            ).model_dump_json(indent=2)
        )
        return 0
    from .pi_adapter import complete_assigned_deletions, create_assigned_backup

    if args.command == "backup":
        if input("Type BACKUP for this selected Core space: ").strip() != "BACKUP":
            return 1
        print(
            create_assigned_backup(
                space, uuid4(), authority, pi_version=_runtime(config)[2]
            ).model_dump_json(indent=2)
        )
    elif args.command == "repair":
        report = pulse_space(space, authority)
        observations: list[dict[str, str]] = []
        for record in inspect_space(space, authority).records:
            if record.kind != "work" or record.status == "deleted":
                continue
            try:
                execution = read_execution(space, record.record_id, authority)
            except (FoundationError, ValueError) as error:
                # A damaged Work must remain addressable even when its full view fails.
                observations.append(
                    {
                        "address": f"work:{record.record_id}",
                        "condition": "inspection_failed",
                        "reason": str(error),
                        "action": (
                            "Inspect the addressed Work and Pulse findings; "
                            "restore a verified backup if required."
                        ),
                    }
                )
                continue
            for assignment in execution.assignments:
                if assignment.status == "unknown":
                    observations.append(
                        {
                            "address": f"assignment:{assignment.attempt_id}",
                            "condition": "external_outcome_unknown",
                            "reason": "The assigned execution has no confirmed external outcome.",
                            "action": (
                                "Keep its resource fenced; inspect the provider or executor "
                                "record before a new assignment on that resource."
                            ),
                        }
                    )
            for invocation in execution.invocations:
                if invocation.status == "unknown":
                    observations.append(
                        {
                            "address": f"invocation:{invocation.invocation_id}",
                            "condition": "provider_outcome_unknown",
                            "reason": "The provider response is unconfirmed.",
                            "action": (
                                "Preserve the ledger and use an independent resource until "
                                "the external outcome is established."
                            ),
                        }
                    )
            for wait in execution.waits:
                if wait.status == "open":
                    observations.append(
                        {
                            "address": f"wait:{wait.wait_id}",
                            "condition": "awaiting_answer",
                            "reason": f"Waiting for {wait.expected_actor} on Work {wait.work_id}.",
                            "action": (
                                "Answer through /zara-answer in the selected space when ready."
                            ),
                        }
                    )
        print(
            json.dumps(
                {
                    "pulse": report.model_dump(mode="json"),
                    "operational_observations": observations,
                    "safe_operations": [
                        "inspect the addressed record",
                        "answer an open wait through Pi",
                        "complete pending managed deletions with DELETE",
                        "backup, restore to an empty directory, recover, then select",
                    ],
                },
                indent=2,
            )
        )
        if (
            input("Type DELETE to complete pending managed deletions, or press Enter: ").strip()
            == "DELETE"
        ):
            print(complete_assigned_deletions(space, authority).model_dump_json(indent=2))
    return 0


def _exchange(args: argparse.Namespace, config: dict[str, object]) -> int:
    from .foundation import KnowledgeRef, authorize_local, read_space
    from .pi_adapter import ManualExchange

    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")

    space = Path(str(config["space"]))
    info = read_space(space)
    if str(info.space_id) != config["space_id"]:
        raise ValueError("Selected space differs from the saved configuration")
    authority = authorize_local(
        space, actor=str(config["actor"]), source_ref=f"local-manual-exchange:{uuid4()}"
    )
    exchange = ManualExchange(space, authority)
    operation_id = args.operation_id or uuid4()
    if args.mode == "prepare":
        result = exchange.prepare(
            operation_id,
            args.activity_id,
            work_id=args.work_id,
            external_tool=args.external_tool,
        )
    elif args.mode == "import":
        content = args.file.read_bytes() if args.file is not None else sys.stdin.buffer.read()
        if (args.reply_id is None) != (args.reply_revision is None):
            raise ValueError("Reply needs the exact document ID and revision")
        if (args.previous_source_id is None) != (args.previous_source_revision is None):
            raise ValueError("Previous Source needs an exact ID and revision")
        result = exchange.receive(
            operation_id,
            args.activity_id,
            work_id=args.work_id,
            origin=args.origin,
            content=content,
            previous_source=KnowledgeRef(
                record_id=args.previous_source_id, revision=args.previous_source_revision
            )
            if args.previous_source_id is not None
            else None,
            sender=args.sender,
            locator=str(args.file.resolve()) if args.file is not None else None,
            reply_to=KnowledgeRef(record_id=args.reply_id, revision=args.reply_revision)
            if args.reply_id is not None
            else None,
        )
    else:
        result = exchange.read(args.record_id, revision=args.revision)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{result['kind']} {result['record_id']}@{result['revision']}")
        print(result["content_text"], end="")
    return 0


def _integration(args: argparse.Namespace, config: dict[str, object]) -> int:
    from .foundation import authorize_local, read_space
    from .integrations import installed_integrations

    space = Path(str(config["space"]))
    if str(read_space(space).space_id) != config["space_id"]:
        raise ValueError("Selected space differs from the saved configuration")
    authority = authorize_local(
        space, actor=str(config["actor"]), source_ref=f"local-integration:{uuid4()}"
    )
    registry = installed_integrations(space, authority)
    if args.mode == "catalog":
        result = registry.catalog()
    elif args.mode == "contract":
        result = registry.contract(args.adapter, args.operation)
    else:
        arguments = json.loads(args.arguments.read_text(encoding="utf-8"))
        if not isinstance(arguments, dict):
            raise ValueError("Expected one typed operation argument object")
        result = registry.execute(
            args.operation_id,
            args.adapter,
            args.operation,
            arguments,
            contract_version=args.contract_version,
        ).output
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _memory(args: argparse.Namespace, config: dict[str, object]) -> int:
    from .foundation import (
        MemorySelector,
        authorize_local,
        export_memory_selection,
        memory_catalog,
        memory_history,
        open_memory_selection,
        prepare_memory_cache,
        read_memory_batch,
    )

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    _ready_space(config)
    space = Path(str(config["space"]))
    authority = authorize_local(
        space, actor=str(config["actor"]), source_ref="local-memory-console"
    )
    if args.mode == "export":
        result = export_memory_selection(space, args.selection_id, authority, args.file)
    elif args.mode == "open_selection":
        result = open_memory_selection(
            space,
            args.selection_id,
            authority,
            part=args.part,
            offset=args.offset,
            max_bytes=args.max_bytes,
            toc_offset=args.toc_offset,
        )
    elif args.mode == "history":
        result = memory_history(
            space, args.record_id, authority, after_revision=args.after_revision, limit=args.limit
        )
    else:
        selectors = (
            MemorySelector(
                activity_ids=tuple(args.activity or ()),
                common=args.common,
                record_ids=tuple(args.record or ()),
                topics=tuple(args.topic or ()),
                query=args.query,
                full=args.full,
            ),
        )
        if args.mode == "catalog":
            result = memory_catalog(
                space,
                authority,
                selectors=selectors,
                limit=args.limit,
                cursor=args.cursor,
                full=args.full,
            )
        else:
            function = prepare_memory_cache if args.mode == "prepare_cache" else read_memory_batch
            result = function(space, authority, selectors, max_bytes=args.max_bytes)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _workspace_cli(args: argparse.Namespace, path: Path) -> int:
    from .foundation import authorize_local
    from .workspace import (
        GitDestination,
        Project,
        defer_git,
        git_status,
        initialize_git,
        migrate_config,
        prepare_git,
        publish_git,
        read_config,
        reconcile_git,
        register_project,
        select_work_project,
        workspace_info,
    )

    config = read_config(path)
    authority = authorize_local(
        config.space, actor=config.actor, source_ref=f"local-console:{config.actor}:{uuid4()}"
    )
    result: object
    if args.command == "workspace":
        if args.mode == "migrate":
            config = migrate_config(
                path,
                args.output,
                personal_root=args.personal_root,
                runtime_root=args.runtime_root,
                projects=config.projects,
                git=GitDestination(repository=args.git_repository)
                if args.git_repository
                else config.git,
            )
            _register_config(args.output)
        result = workspace_info(config)
    elif args.command == "projects":
        if args.mode == "register":
            config = register_project(path, Project(name=args.name, path=args.path))
        elif args.mode == "select":
            result = {"root": str(select_work_project(config, authority, args.work_id, args.name))}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        result = workspace_info(config)["projects"]
    elif args.mode == "init":
        initialize_git(config, create_private=args.create_private)
        result = git_status(config)
    elif args.mode == "prepare":
        result = prepare_git(config, authority).model_dump(mode="json")
    elif args.mode in ("publish", "defer"):
        if args.mode == "defer":
            result = defer_git(config, args.preparation_id).model_dump(mode="json")
        else:
            status = git_status(config)
            delivery = status["delivery"]
            if not isinstance(delivery, dict) or delivery["preparation_id"] != str(
                args.preparation_id
            ):
                raise ValueError("No matching prepared delivery")
            print(f"Destination: {config.git}\nPrepared files:")
            print("\n".join(delivery["files"]))
            approved = (
                input("Type PUSH to publish exactly these personal files: ").strip() == "PUSH"
            )
            result = publish_git(
                config, authority, args.preparation_id, approved=approved
            ).model_dump(mode="json")
    elif args.mode == "check":
        item = reconcile_git(config)
        result = item.model_dump(mode="json") if item else {"delivery": None}
    else:
        result = git_status(config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None, *, prog: str = "zara-core") -> int:
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, workspace_modes in (
        ("workspace", ("info", "migrate")),
        ("projects", ("list", "register", "select")),
        ("git", ("status", "init", "prepare", "publish", "defer", "check")),
    ):
        group = commands.add_parser(name)
        actions = group.add_subparsers(dest="mode")
        group.set_defaults(mode=workspace_modes[0], config=None)
        for mode in workspace_modes:
            command = actions.add_parser(mode)
            command.add_argument("--config", type=Path)
            if name == "workspace" and mode == "migrate":
                command.add_argument("--personal-root", required=True, type=Path)
                command.add_argument("--runtime-root", required=True, type=Path)
                command.add_argument("--output", required=True, type=Path)
                command.add_argument("--git-repository")
            elif name == "projects" and mode in ("register", "select"):
                command.add_argument("name")
                if mode == "register":
                    command.add_argument("path", type=Path)
                else:
                    command.add_argument("--work-id", required=True, type=UUID)
            elif name == "git" and mode == "init":
                command.add_argument("--create-private", action="store_true")
            elif name == "git" and mode in ("publish", "defer"):
                command.add_argument("preparation_id", type=UUID)
    memory = commands.add_parser("memory", help="Shared indexed memory and exact text selections")
    memory_modes = memory.add_subparsers(dest="mode", required=True)
    for mode in ("catalog", "read_batch", "prepare_cache", "open_selection", "history", "export"):
        command = memory_modes.add_parser(mode)
        command.add_argument("--config", type=Path)
        if mode in ("catalog", "read_batch", "prepare_cache"):
            command.add_argument("--activity", action="append", type=UUID)
            command.add_argument("--common", action="store_true")
            command.add_argument("--record", action="append", type=UUID)
            command.add_argument("--topic", action="append")
            command.add_argument("--query")
            command.add_argument("--full", action="store_true")
        if mode in ("catalog", "history"):
            command.add_argument("--limit", type=int, default=25)
        if mode == "catalog":
            command.add_argument("--cursor")
        if mode in ("read_batch", "prepare_cache", "open_selection"):
            command.add_argument("--max-bytes", type=int, default=16384)
        if mode in ("open_selection", "export"):
            command.add_argument("selection_id", type=UUID)
        if mode == "open_selection":
            command.add_argument("--part", type=int, default=0)
            command.add_argument("--offset", type=int, default=0)
            command.add_argument("--toc-offset", type=int, default=0)
        if mode == "export":
            command.add_argument("--file", type=Path, required=True)
        if mode == "history":
            command.add_argument("record_id", type=UUID)
            command.add_argument("--after-revision", type=int, default=0)
    integration = commands.add_parser("integration", help="Installed typed integration operations")
    integration_modes = integration.add_subparsers(dest="mode", required=True)
    for mode in ("catalog", "contract", "apply"):
        command = integration_modes.add_parser(mode)
        command.add_argument("--config", type=Path)
        if mode != "catalog":
            command.add_argument("--adapter", required=True)
            command.add_argument("--operation", required=True)
        if mode == "apply":
            command.add_argument("--arguments", required=True, type=Path)
            command.add_argument("--contract-version", required=True, type=int)
            command.add_argument("--operation-id", required=True, type=UUID)
    exchange = commands.add_parser("exchange", help="Manual exchange with an external tool")
    modes = exchange.add_subparsers(dest="mode", required=True)
    for mode in ("prepare", "import", "read"):
        command = modes.add_parser(mode)
        command.add_argument("--config", type=Path)
        command.add_argument("--operation-id", type=UUID)
        command.add_argument("--json", action="store_true")
        if mode == "read":
            command.add_argument("--record-id", required=True, type=UUID)
            command.add_argument("--revision", type=int)
        else:
            command.add_argument("--activity-id", required=True, type=UUID)
            command.add_argument("--work-id", type=UUID)
            if mode == "prepare":
                command.add_argument("--external-tool", required=True)
            else:
                content = command.add_mutually_exclusive_group(required=True)
                content.add_argument("--file", type=Path)
                content.add_argument("--stdin", action="store_true")
                command.add_argument("--origin", required=True)
                command.add_argument("--sender")
                command.add_argument("--previous-source-id", type=UUID)
                command.add_argument("--previous-source-revision", type=int)
                command.add_argument("--reply-id", type=UUID)
                command.add_argument("--reply-revision", type=int)
    setup = commands.add_parser("setup")
    setup.add_argument("--config", type=Path)
    setup.add_argument("--space", type=Path)
    setup.add_argument("--workspace", type=Path)
    setup.add_argument("--new-space", action="store_true")
    setup.add_argument("--runtime-root", type=Path)
    setup.add_argument("--git-repository", help="Optional permitted private owner/repository")
    setup.add_argument("--create-private", action="store_true")
    setup.add_argument("--sqlite-dll", type=Path, help="Verified SQLite DLL for offline setup")
    setup.add_argument(
        "--pi-runtime", type=Path, help="Explicit Pi runtime; default uses pi on PATH"
    )
    setup.add_argument("--node", default="node")
    setup.add_argument(
        "--provider-profile", choices=("codex-sse", "local-completions"), default="codex-sse"
    )
    setup.add_argument("--provider-base-url", default="https://chatgpt.com/backend-api")
    setup.add_argument("--provider-id", default="openai-codex")
    setup.add_argument("--model-id", default="gpt-5.6-luna")
    setup.add_argument("--context-window", type=int)
    setup.add_argument("--max-tokens", type=int)
    setup.add_argument("--limit-units", type=int)
    setup.add_argument("--reserve-units", type=int, default=3000)
    for name in (
        "run",
        "assign",
        "verify",
        "upgrade",
        "select",
        "inspect",
        "pulse",
        "backup",
        "repair",
        "restore",
        "recover",
        "change-install",
        "change-stop",
        "change-restore",
        "bind",
        "runtime",
        "models",
    ):
        command = commands.add_parser(name)
        command.add_argument("--config", type=Path)
        if name == "run":
            command.add_argument("--activity-id", type=UUID)
            command.add_argument("--work-id", type=UUID)
            command.add_argument("--pi-tools")
            command.add_argument("--model", help="Codex subscription model for this run")
            command.add_argument("--thinking")
        elif name == "runtime":
            command.add_argument("--use-system", action="store_true")
        elif name == "models":
            command.add_argument("search", nargs="?")
        elif name == "assign":
            command.add_argument("--attempt-id", type=UUID)
            command.add_argument("--work-id", type=UUID)
            command.add_argument("--resource-id", type=UUID)
            command.add_argument("--pi-tools")
        elif name == "pulse":
            command.add_argument("--previous-report", type=Path)
        elif name == "inspect":
            command.add_argument(
                "--kind",
                choices=(
                    "space",
                    "activity",
                    "work",
                    "development",
                    "execution",
                    "receipt",
                    "application",
                ),
                required=True,
            )
            command.add_argument("--id", type=UUID)
        elif name == "select":
            command.add_argument("--space", required=True, type=Path)
            command.add_argument("--output", required=True, type=Path)
        elif name == "restore":
            command.add_argument("--package", required=True, type=Path)
            command.add_argument("--destination", required=True, type=Path)
        elif name == "recover":
            command.add_argument("--space", required=True, type=Path)
        elif name in ("change-install", "change-stop", "change-restore"):
            command.add_argument("--application-id", required=True, type=UUID)
            if name == "change-restore":
                command.add_argument("--reason", required=True)
                command.add_argument("--data-restoration", required=True)
                command.add_argument("--external-effects", required=True)
            elif name == "change-stop":
                command.add_argument("--reason", required=True)
                command.add_argument("--started-works", required=True)
                command.add_argument("--external-effects", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "setup":
            return _setup(args)
        config_path = _selected_config(args.config)
        config = _config(config_path)
        _actor(config)
        if args.command in ("workspace", "projects", "git"):
            return _workspace_cli(args, config_path)
        if args.command == "memory":
            return _memory(args, config)
        if args.command == "integration":
            return _integration(args, config)
        if args.command == "bind":
            _runtime(config)
            _register_config(config_path)
            print(f"Selected installation: {config_path}")
            return 0
        if args.command == "runtime":
            return _runtime_command(args, config, config_path)
        if args.command == "models":
            _, cli, pi_version = _runtime(config)
            print(f"Pi {pi_version}: {cli}", flush=True)
            environment = os.environ.copy()
            if config.get("subscription_agent_dir"):
                environment["PI_CODING_AGENT_DIR"] = str(config["subscription_agent_dir"])
            return subprocess.run(
                [
                    str(config["node"]),
                    str(cli),
                    "--list-models",
                    *([args.search] if args.search else []),
                ],
                env=environment,
                check=False,
            ).returncode
        if args.command == "exchange":
            return _exchange(args, config)
        if args.command == "run":
            return _run(args, config)
        if args.command == "assign":
            return _assign(args, config)
        return _maintenance(args, config)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"zara-core: {error}\n")
    except Exception as error:
        from .foundation import FoundationError

        if isinstance(error, FoundationError):
            parser.exit(1, f"zara-core: {error.code}: {error}\n")
        raise


def app_main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["--version"]:
        from importlib.metadata import version

        print(f"Zaratustra {version('zaratustra')}")
        return 0
    if not arguments or (arguments[0].startswith("-") and arguments[0] not in ("--help", "-h")):
        arguments.insert(0, "run")
    return main(arguments, prog="zaratustra")


if __name__ == "__main__":
    raise SystemExit(main())
