"""Reproduce the Core v0.1 foundation on synthetic data without a model."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def _new_output(path: Path) -> Path:
    output = path.expanduser().resolve()
    scratch = (ROOT / "_scratch").resolve()
    if output == scratch or not output.is_relative_to(scratch) or output.exists():
        raise ValueError("Choose a NEW output directory inside this checkout's _scratch")
    output.mkdir(parents=True)
    return output


def run(output: Path) -> dict[str, Any]:
    from zaratustra.foundation import (
        BootstrapRequest,
        CreateArtifactRequest,
        ProvenanceRef,
        RecoverRequest,
        ReviseArtifactRequest,
        apply_operation,
        authorize_local,
        authorize_recovery,
        create_backup,
        initialize_space,
        inspect_recovery,
        inspect_space,
        read_artifact,
        read_receipt,
        restore_backup,
    )

    output = _new_output(output)
    workspace = output / "workspace"
    workspace.mkdir()
    info = initialize_space(workspace)
    owner = authorize_local(workspace, actor="synthetic-owner", source_ref="probe-confirmation")
    bootstrap = apply_operation(
        workspace,
        BootstrapRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=owner.actor,
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        owner,
    )
    artifact_id = uuid4()
    create = CreateArtifactRequest(
        operation_id=uuid4(),
        space_id=info.space_id,
        actor=owner.actor,
        artifact_id=artifact_id,
        media_type="text/plain; charset=utf-8",
        content="Синтетическая предметная запись".encode(),
        provenance=(ProvenanceRef(relation="received-from", external_ref="probe:synthetic"),),
    )
    created = apply_operation(workspace, create, owner)
    replay = apply_operation(workspace, create, owner)
    revised = apply_operation(
        workspace,
        ReviseArtifactRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=owner.actor,
            artifact_id=artifact_id,
            expected_revision=1,
            media_type="application/octet-stream",
            content=b"synthetic revision two\x00",
            provenance=(ProvenanceRef(relation="revises", record_id=artifact_id, revision=1),),
        ),
        owner,
    )
    historical = read_artifact(workspace, artifact_id, owner, revision=1)
    current = read_artifact(workspace, artifact_id, owner)
    recovered_receipt = read_receipt(workspace, create.operation_id, owner)
    backup = create_backup(workspace, uuid4(), owner)

    restored = output / "restored"
    restored.mkdir()
    recovery = authorize_recovery(
        actor="synthetic-owner", source_ref="probe-fresh-recovery-confirmation"
    )
    quarantined = restore_backup(backup.package, restored, recovery)
    recovery_view = inspect_recovery(restored, recovery)
    recovered = apply_operation(
        restored,
        RecoverRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor="synthetic-owner",
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        recovery,
    )
    restored_owner = authorize_local(
        restored,
        actor="synthetic-owner",
        source_ref="probe-post-restore-confirmation",
    )
    restored_current = read_artifact(restored, artifact_id, restored_owner)
    inspection = inspect_space(workspace, owner)

    summary = {
        "space_id": str(info.space_id),
        "sqlite_version": info.sqlite_version,
        "bootstrap_operation": str(bootstrap.operation_id),
        "create_operation": str(created.operation_id),
        "exact_replay_same_receipt": replay == created == recovered_receipt,
        "revision_operation": str(revised.operation_id),
        "historical_bytes_utf8": historical.content.decode() if historical.content else None,
        "current_bytes_hex": current.content.hex() if current.content else None,
        "state_revision": inspection.space.state_revision,
        "record_count": len(inspection.records),
        "backup_manifest": backup.manifest.model_dump(mode="json"),
        "restored_quarantine": quarantined.recovery_state,
        "recovery_view": recovery_view,
        "recovery_operation": str(recovered.operation_id),
        "restored_current_matches": restored_current.content == current.content,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--sqlite-dll",
        type=Path,
        help="Verified official SQLite 3.53.3 sqlite3.dll; sets the process-local runtime.",
    )
    args = parser.parse_args()
    if args.sqlite_dll is not None:
        os.environ["ZARATUSTRA_SQLITE_DLL"] = str(args.sqlite_dll.resolve())
    summary = run(args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
