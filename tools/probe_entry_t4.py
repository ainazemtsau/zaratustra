"""Reproduce installed material-transfer restart recovery with one set of effects."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]


def _save(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + chr(10),
        encoding="utf-8",
    )


def recover(base: Path) -> dict[str, Any]:
    """Run only against the installed wheel from a fresh isolated Python process."""
    from zaratustra.core import read_handoffs, read_records
    from zaratustra.entry import resolve_entry, source_path
    from zaratustra.intake import (
        IntakeSelection,
        MaterialIntakeReceipt,
        authorize_material_intake,
        execute_material_intake,
        inspect_material_intake_progress,
        prepare_material_intake,
    )

    catalog = base / "catalog.json"
    external = base / "incoming" / "generic-report.json"
    entry = resolve_entry(catalog, "Generic Research")
    workspace = source_path(catalog, entry)
    selection = IntakeSelection(
        workspace_id=entry.workspace_id,
        process_id=entry.process_id,
        work_id=entry.work_id,
    )
    original = MaterialIntakeReceipt.model_validate_json(
        (base / "evidence" / "receipt.json").read_bytes()
    )
    before = read_records(workspace)
    accepted_before = read_handoffs(workspace)
    inspection = inspect_material_intake_progress(workspace, original.intake_id)
    if inspection is None or inspection.claimed_stages != ("publication", "acceptance"):
        raise AssertionError("Unconfirmed progress inspection did not show both journal claims")
    incoming = external.read_bytes()
    prepared = prepare_material_intake(
        workspace, selection, incoming, source_ref=external.as_posix()
    )
    authorization = authorize_material_intake(
        prepared,
        channel="local-chat",
        actor="generic-installed-recovery-demo",
        source_ref="new-trusted-session-reviewed-exact-transfer",
    )
    recovered = execute_material_intake(prepared, authorization)
    after = read_records(workspace)
    accepted_after = read_handoffs(workspace)
    if (
        recovered.publication != original.publication
        or recovered.acceptance != original.acceptance
        or recovered.continuation != original.continuation
        or after != before
        or accepted_after != accepted_before
        or len(accepted_after) != 1
    ):
        raise AssertionError("Fresh-process recovery created or changed a transfer effect")
    result = dict(
        restart_process=True,
        exact_publication_receipt_recovered=True,
        exact_acceptance_receipt_recovered=True,
        saved_continuation_recovered=True,
        current_continuation_state=recovered.current_continuation.state,
        no_revision_change=True,
        one_acceptance=True,
        unconfirmed_progress_fields=sorted(inspection.model_dump(mode="json")),
    )
    summary = cast(dict[str, Any], json.loads((base / "summary.json").read_text(encoding="utf-8")))
    summary["recovery"] = result
    summary["scenario"] = "installed-recoverable-external-material-transfer"
    _save(base / "summary.json", summary)
    _save(base / "evidence" / "recovered-receipt.json", recovered.model_dump(mode="json"))
    return summary


def orchestrate(output: Path) -> dict[str, Any]:
    for name in ("STOP", "STEER.md"):
        if (ROOT / name).exists():
            raise SystemExit(f"STOP: read and resolve {name}")
    from tools.probe_entry_t3 import orchestrate as create_installed_transfer
    from tools.probe_entry_t3 import run

    target = output.resolve()
    create_installed_transfer(target)
    environment = target / "venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    recovery_script = target / "recover.py"
    shutil.copyfile(Path(__file__), recovery_script)
    commands = cast(
        list[dict[str, Any]],
        json.loads((target / "commands.json").read_text(encoding="utf-8")),
    )
    run(
        [str(python), "-I", str(recovery_script), "--phase", "recover", "--base", str(target)],
        target / "unrelated-cwd",
        commands,
    )
    _save(target / "commands.json", commands)
    return cast(dict[str, Any], json.loads((target / "summary.json").read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--phase", choices=("recover",))
    parser.add_argument("--base", type=Path)
    args = parser.parse_args(argv)
    if args.phase == "recover":
        if args.base is None:
            parser.error("--base is required for recovery")
        print(json.dumps(recover(args.base), ensure_ascii=True, indent=2))
        return 0
    if args.output is None:
        parser.error("--output is required")
    print(json.dumps(orchestrate(args.output), ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
