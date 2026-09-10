"""Run the finite T4 fictional lot through public Core and shared host mechanics."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from tests.fixtures.fictional_lot import (
    initial_records,
    initial_requirements,
    reference,
    registration,
)
from zaratustra.core import (
    ContextQuery,
    LocalAuthorization,
    MutationRequest,
    ProcessQuery,
    ReceiptQuery,
)
from zaratustra.process_packs import PackRegistry

from .probe_m1 import save
from .probe_process_host import ProcessTrial, refused
from .probe_process_host import confirm as host_confirm
from .probe_process_host import footprint as footprint
from .probe_process_host import wire as wire
from .retain_trial import retain_trial

ROOT = Path(__file__).resolve().parents[1]
CALL = "c-solmax-zaratustra-m1-first-process-20260910-exec"


def confirm(
    path: Path, value: MutationRequest | ContextQuery | ReceiptQuery | ProcessQuery
) -> LocalAuthorization:
    return host_confirm(path, value, call=CALL)


def installed() -> PackRegistry:
    return PackRegistry((registration(),))


class LotTrial(ProcessTrial):
    def __init__(
        self,
        path: Path,
        evidence: Path,
        *,
        registry: PackRegistry | None = None,
        call: str = CALL,
    ) -> None:
        super().__init__(
            path,
            evidence,
            package=registration(),
            initial=initial_records(),
            requirements=initial_requirements(),
            call=call,
            registry=registry,
        )


def run(
    base: Path, inputs: Path, *, registry: PackRegistry | None = None, call: str = CALL
) -> dict[str, Any]:
    base.mkdir()
    raw_inputs = inputs.read_bytes()
    (base / "inputs.json").write_bytes(raw_inputs)
    data = json.loads(raw_inputs)
    save(
        base / "runtime.json",
        dict(
            call=call,
            python=sys.version,
            executable=sys.executable,
            argv=sys.argv,
            commit=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, encoding="utf-8"
            ).strip(),
            source_diff=subprocess.check_output(
                ["git", "diff", "HEAD", "--", "src", "tools", "tests", "pyproject.toml", "uv.lock"],
                cwd=ROOT,
                encoding="utf-8",
            ),
            inputs_sha256=hashlib.sha256(raw_inputs).hexdigest(),
        ),
    )
    trial = LotTrial(base / "workspace", base / "events", registry=registry, call=call)
    inspection_id = trial.bootstrap()
    trial.capture("initial", inspection_id, (inspection_id,))
    trial.accept(inspection_id, wire(data["incomplete_inspection"]))
    incomplete = refused(trial, inspection_id, "incomplete")
    inspection = trial.accept(inspection_id, wire(data["inspection"]))
    missing = refused(trial, inspection_id, "missing-pack", PackRegistry())
    decision_id = trial.finish(inspection_id, "inspection")
    decision = trial.capture("decision", decision_id, (inspection_id, decision_id))
    scoped = trial.capture("selected-only", decision_id, (decision_id,))
    invalid = data["disposition"] | dict(inspection_sha256="0" * 64)
    trial.accept(decision_id, wire(invalid))
    wrong_basis = refused(trial, decision_id, "wrong-basis")
    disposition_input = data["disposition"] | dict(inspection_sha256=inspection.sha256)
    disposition = trial.accept(decision_id, wire(disposition_input))
    closed_id = trial.finish(decision_id, "disposition")
    trial.capture("closed-before-cancel", closed_id, (inspection_id, decision_id, closed_id))
    trial.execute(trial.request(closed_id, "cancel_work"))
    final = trial.capture(
        "final", closed_id, (inspection_id, decision_id, closed_id), selected=False
    )
    save(
        base / "final-workspace-manifest.json",
        retain_trial(trial.path, base / "final-workspace.zip"),
    )
    summary = dict(
        process="fictional.lot-release",
        pack=reference().model_dump(mode="json"),
        inspection=inspection.model_dump(mode="json"),
        disposition=disposition.model_dump(mode="json"),
        outcome=disposition_input["decision"],
        work_ids=[str(inspection_id), str(decision_id), str(closed_id)],
        expected_refusals=dict(
            incomplete=incomplete, missing_pack=missing, wrong_basis=wrong_basis
        ),
        decision_revision=decision["envelope"]["state_revision"],
        selected_context=scoped["answers"]["context_requirements"]["value"]["context"]["state"],
        selected_only_result_headers=scoped["answers"]["recent_important_results"],
        final_revision=final["envelope"]["state_revision"],
        final_answers=final["answers"],
        rollback="Two exact pre-Result snapshots restored and same requests replayed through Core",
        manual_acceptance="pending",
        binding_fresh_G5="pending",
        next="solmax",
    )
    save(base / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--inputs", type=Path, default=ROOT / "docs/m1-first-process/inputs.json")
    args = parser.parse_args()
    if (ROOT / "STOP").exists() or (ROOT / "STEER.md").exists():
        parser.error("Read and resolve STOP/STEER before running")
    base = args.output.resolve()
    scratch = (ROOT / "_scratch").resolve()
    if base == scratch or not base.is_relative_to(scratch) or base.exists():
        parser.error("Choose a NEW directory inside this execution worktree's ignored _scratch")
    summary = run(base, args.inputs)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
