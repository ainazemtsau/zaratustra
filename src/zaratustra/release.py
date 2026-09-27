"""Installed setup and daily entry for one selected Core space and ordinary Pi."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import io
import json
import os
import shutil
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
PI_VERSION = "0.87.0"
PI_PACKAGE_SHA256 = "9BB655451E850A8593BA87F563C26D3D2AF2F503B76318E2F1BBE53EB28C9180"


def _config(path: Path) -> dict[str, object]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict) or result.get("version") != 1:
        raise ValueError("Unsupported launch configuration")
    sqlite_dll = Path(str(result["sqlite_dll"])).resolve()
    if (
        not sqlite_dll.is_file()
        or hashlib.sha256(sqlite_dll.read_bytes()).hexdigest().upper() != SQLITE_DLL_SHA256
    ):
        raise ValueError("Configured SQLite DLL is missing or changed")
    os.environ["ZARATUSTRA_SQLITE_DLL"] = str(sqlite_dll)
    return result


def _actor(config: dict[str, object]) -> str:
    actor = getpass.getuser()
    if actor != config["actor"]:
        raise ValueError("Current local user differs from the selected trusted identity")
    return actor


def _pi_cli(runtime: Path) -> Path:
    package = runtime / "node_modules" / "@earendil-works" / "pi-coding-agent"
    package_file = package / "package.json"
    data = package_file.read_bytes()
    metadata = json.loads(data)
    cli = package / "dist" / "bundle" / "cli.js"
    if (
        metadata.get("version") != PI_VERSION
        or hashlib.sha256(data).hexdigest().upper() != PI_PACKAGE_SHA256
        or not cli.is_file()
    ):
        raise ValueError(f"Selected Pi runtime must be {PI_VERSION}")
    return cli


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


def _prepare_pi(destination: Path, supplied: Path | None) -> Path:
    pending = destination.with_name(destination.name + ".pending")
    if destination.exists():
        _pi_cli(destination)
        return destination
    if pending.exists():
        _pi_cli(pending)
        pending.replace(destination)
        return destination
    if supplied is not None:
        _pi_cli(supplied)
        shutil.copytree(supplied, pending)
    else:
        pending.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "npm",
                "install",
                "--prefix",
                str(pending),
                "--no-audit",
                "--no-fund",
                "--save-exact",
                f"@earendil-works/pi-coding-agent@{PI_VERSION}",
                f"@earendil-works/pi-ai@{PI_VERSION}",
            ],
            check=True,
        )
    _pi_cli(pending)
    pending.replace(destination)
    return destination


def _setup(args: argparse.Namespace) -> int:
    if sys.version_info[:3] != (3, 13, 7):
        raise ValueError("Use the supported Python 3.13.7 to install the wheel")
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
    if args.limit_units < 1 or args.reserve_units < 1 or args.reserve_units > args.limit_units:
        raise ValueError("Choose positive model resource and reserve bounds")
    actor = getpass.getuser()
    print(f"Core space: {space}\nWorking resource: {workspace}\nLocal identity: {actor}")
    print(f"Provider: {args.provider_profile} / {args.model_id} at {args.provider_base_url}")
    print(f"New space: {args.new_space}; target schema: 12")
    if input("Type SETUP to prepare this installation and selected space: ").strip() != "SETUP":
        return 1
    runtime_root = config_path.parent / "runtime"
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
    pi_runtime = _prepare_pi(runtime_root / "pi", args.pi_runtime)
    config: dict[str, object] = {
        "version": 1,
        "actor": actor,
        "space_id": str(authority.space_id),
        "space": str(space),
        "workspace": str(workspace),
        "sqlite_dll": str(sqlite_dll),
        "pi_runtime": str(pi_runtime),
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
    print(f"Prepared: {config_path}")
    if not args.new_space and info.schema_version < 12:
        print("Existing space requires zara-core upgrade before run or assign")
    return 0


def _run(args: argparse.Namespace, config: dict[str, object]) -> int:
    _ready_space(config)
    from .pi_adapter import pi_main

    runtime = Path(str(config["pi_runtime"]))
    command = [
        "--space",
        str(config["space"]),
        "--workspace",
        str(config["workspace"]),
        "--pi-cli",
        str(_pi_cli(runtime)),
        "--pi-runtime",
        str(runtime),
        "--node",
        str(config["node"]),
        "--limit-units",
        str(config["limit_units"]),
        "--reserve-units",
        str(config["reserve_units"]),
        "--provider-profile",
        str(config["provider_profile"]),
        "--provider-base-url",
        str(config["provider_base_url"]),
        "--model",
        str(config["model_id"]),
    ]
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
    return pi_main(command)


def _assign(args: argparse.Namespace, config: dict[str, object]) -> int:
    _ready_space(config)
    from .pi_adapter import assigned_main

    runtime = Path(str(config["pi_runtime"]))
    command = [
        "--space",
        str(config["space"]),
        "--workspace",
        str(config["workspace"]),
        "--pi-cli",
        str(_pi_cli(runtime)),
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
        "--limit-units",
        str(config["limit_units"]),
    ]
    if config["context_window"]:
        command += ["--context-window", str(config["context_window"])]
    if config["max_tokens"]:
        command += ["--max-tokens", str(config["max_tokens"])]
    if args.attempt_id:
        command += ["--attempt-id", str(args.attempt_id)]
    else:
        command += ["--work-id", str(args.work_id), "--resource-id", str(args.resource_id)]
    if args.pi_tools:
        command += ["--pi-tools", args.pi_tools]
    return assigned_main(command)


def _ready_space(config: dict[str, object]) -> None:
    from zaratustra.foundation import read_space

    info = read_space(Path(str(config["space"])))
    if config.get("space_id") and str(info.space_id) != config["space_id"]:
        raise ValueError("Selected space identity differs from the saved configuration")
    if info.schema_version != 12:
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

    _ready_space(config)
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
        _ready_space(config)
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
        if info.schema_version == 12:
            print("Core space already uses schema 12")
            return 0
        if info.schema_version > 12:
            raise ValueError("Installed program cannot upgrade a newer Core schema")
        if info.recovery_state != "active":
            raise ValueError("Recover this space before a schema upgrade")
        print(f"Space {info.space_id}: schema {info.schema_version} -> 12")
        if (
            input("Type UPGRADE to save a verified backup and migrate this space: ").strip()
            != "UPGRADE"
        ):
            return 1
        from .pi_adapter import create_assigned_backup

        authority = authorize_local(
            space, actor=actor, source_ref=f"local-console:{actor}:{uuid4()}"
        )
        backup = create_assigned_backup(space, uuid4(), authority)
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
                    "pi_cli": str(_pi_cli(Path(str(config["pi_runtime"])))),
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
        updated = {**config, "space": str(selected), "space_id": str(target.space_id)}
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
        print(create_assigned_backup(space, uuid4(), authority).model_dump_json(indent=2))
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zara-core", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("setup")
    setup.add_argument("--config", required=True, type=Path)
    setup.add_argument("--space", required=True, type=Path)
    setup.add_argument("--workspace", required=True, type=Path)
    setup.add_argument("--new-space", action="store_true")
    setup.add_argument("--sqlite-dll", type=Path, help="Verified SQLite DLL for offline setup")
    setup.add_argument("--pi-runtime", type=Path, help="Pinned Pi runtime for offline setup")
    setup.add_argument("--node", default="node")
    setup.add_argument(
        "--provider-profile", choices=("codex-sse", "local-completions"), required=True
    )
    setup.add_argument("--provider-base-url", required=True)
    setup.add_argument("--provider-id", required=True)
    setup.add_argument("--model-id", required=True)
    setup.add_argument("--context-window", type=int)
    setup.add_argument("--max-tokens", type=int)
    setup.add_argument("--limit-units", type=int, required=True)
    setup.add_argument("--reserve-units", type=int, required=True)
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
    ):
        command = commands.add_parser(name)
        command.add_argument("--config", required=True, type=Path)
        if name == "run":
            command.add_argument("--activity-id", type=UUID)
            command.add_argument("--work-id", type=UUID)
            command.add_argument("--pi-tools")
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
        config = _config(args.config.expanduser().resolve())
        _actor(config)
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


if __name__ == "__main__":
    raise SystemExit(main())
