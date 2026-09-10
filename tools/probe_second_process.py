"""Run two distinct external Processes against one Core and one explicit registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from tests.fixtures.fictional_lot import registration as lot_registration
from tests.fixtures.fictional_signal import (
    initial_records,
    initial_requirements,
    reference,
    registration,
)
from zaratustra.core import ArtifactReference, ProcessQuery, read_records
from zaratustra.process_packs import PackRegistry, read_capabilities

from .probe_first_process import run as run_lot
from .probe_m1 import save, work_at
from .probe_process_host import ProcessTrial, confirm, footprint, refused, wire
from .retain_trial import retain_trial

ROOT = Path(__file__).resolve().parents[1]
CALL = "c-solmax-zaratustra-m1-second-process-20260910-exec"


def installed() -> PackRegistry:
    return PackRegistry((lot_registration(), registration()))


class SignalTrial(ProcessTrial):
    def __init__(self, path: Path, evidence: Path, *, registry: PackRegistry | None = None) -> None:
        super().__init__(
            path,
            evidence,
            package=registration(),
            initial=initial_records(),
            requirements=initial_requirements(),
            call=CALL,
            registry=registry,
        )


def process_query(path: Path, identity: UUID) -> ProcessQuery:
    state = read_records(path)
    return ProcessQuery(
        workspace_id=state.workspace_id,
        process_id=work_at(path, identity).process_id,
        work_id=identity,
        expected_revision=state.state_revision,
        visible_work_ids=(identity,),
        max_bytes=1048576,
    )


def cross_refusals(
    left: tuple[Path, UUID], right: tuple[Path, UUID], registry: PackRegistry, output: Path
) -> dict[str, Any]:
    """A shared package registry is neither cross-workspace visibility nor authority."""
    output.mkdir()
    before = [footprint(item[0]) for item in (left, right)]
    receipts: dict[str, Any] = {}
    for index, (source, target) in enumerate(((left, right), (right, left))):
        source_query = process_query(*source)
        target_query = process_query(*target)
        caller = confirm(source[0], source_query, call=CALL)
        target_caller = confirm(target[0], target_query, call=CALL)
        own = read_capabilities(source[0], source_query, caller, registry)
        own_target = read_capabilities(target[0], target_query, target_caller, registry)
        assert "envelope" in json.loads(own.output) and "envelope" in json.loads(own_target.output)
        save(output / f"{index}-source-query.json", source_query.model_dump(mode="json"))
        save(output / f"{index}-target-query.json", target_query.model_dump(mode="json"))
        save(output / f"{index}-source-authority.json", caller.confirmation.model_dump(mode="json"))
        save(
            output / f"{index}-target-authority.json",
            target_caller.confirmation.model_dump(mode="json"),
        )
        (output / f"{index}-own-source.json").write_bytes(own.output)
        (output / f"{index}-own-target.json").write_bytes(own_target.output)
        for name, query in (("foreign-query", source_query), ("foreign-caller", target_query)):
            result = read_capabilities(target[0], query, caller, registry)
            (output / f"{index}-{name}.json").write_bytes(result.output)
            value = json.loads(result.output)
            assert "envelope" not in value
            assert all(
                "value" not in answer and "count" not in answer
                for answer in value["answers"].values()
            )
            receipts[f"{index}-{name}"] = value
    assert [footprint(item[0]) for item in (left, right)] == before
    return receipts


def run(base: Path, inputs: Path, lot_inputs: Path) -> dict[str, Any]:
    base.mkdir()
    raw = inputs.read_bytes()
    (base / "inputs.json").write_bytes(raw)
    data = json.loads(raw)
    registry = installed()
    save(
        base / "runtime.json",
        dict(
            call=CALL,
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
            inputs_sha256=hashlib.sha256(raw).hexdigest(),
            registry=[row.reference.model_dump(mode="json") for row in registry.registrations],
        ),
    )
    trial = SignalTrial(base / "signal/workspace", base / "signal/events", registry=registry)
    identity = trial.bootstrap()
    identities = [identity]
    trial.capture("initial", identity, (identity,))
    signal_before = footprint(trial.path)
    save(base / "signal-before-lot.json", signal_before)
    lot = run_lot(base / "lot", lot_inputs, registry=registry, call=CALL)
    signal_after = footprint(trial.path)
    save(base / "signal-after-lot.json", signal_after)
    assert signal_after == signal_before
    lot_path = base / "lot/workspace"
    lot_before = footprint(lot_path)
    save(base / "lot-before-signal.json", lot_before)

    trial.accept(identity, wire(data["invalid_observation"]))
    invalid = refused(trial, identity, "invalid-observation")
    changed: ArtifactReference | None = None
    results = []
    missing = "not-run"
    wrong_basis = "not-run"
    for index, item in enumerate(data["rounds"]):
        name = f"round-{index + 1}"
        actual = dict(item)
        if actual["kind"] == "comparison":
            assert changed is not None, "Scenario needs its changed observation before comparison"
            trial.accept(identity, wire(actual | dict(observation_sha256="0" * 64)))
            wrong_basis = refused(trial, identity, name + "-wrong-basis")
            actual["observation_sha256"] = changed.sha256
        accepted = trial.accept(identity, wire(actual))
        if index == 0:
            missing = refused(
                trial, identity, "missing-signal-pack", PackRegistry((lot_registration(),))
            )
        if actual.get("observation") == "changed":
            changed = accepted
        next_id = trial.finish(identity, name)
        results.append(
            dict(
                work_id=str(identity),
                input=actual,
                result=accepted.model_dump(mode="json"),
                next_work=work_at(trial.path, next_id).model_dump(mode="json"),
            )
        )
        identity = next_id
        identities.append(identity)
        trial.capture(name + "-after", identity, tuple(identities))
    final = trial.capture("final", identity, tuple(identities))
    scoped = trial.capture("selected-only", identity, (identity,))
    lot_after = footprint(lot_path)
    save(base / "lot-after-signal.json", lot_after)
    assert lot_after == lot_before
    crossings = cross_refusals(
        (lot_path, UUID(lot["work_ids"][-1])),
        (trial.path, identity),
        registry,
        base / "cross-refusals",
    )
    save(
        base / "signal/final-workspace-manifest.json",
        retain_trial(trial.path, base / "signal/final-workspace.zip"),
    )
    summary = dict(
        call=CALL,
        shared_registry=[row.reference.model_dump(mode="json") for row in registry.registrations],
        lot=lot,
        signal=dict(
            process="fictional.signal-rounds",
            pack=reference().model_dump(mode="json"),
            work_ids=[str(item) for item in identities],
            results=results,
            expected_refusals=dict(invalid=invalid, missing_pack=missing, wrong_basis=wrong_basis),
            final_revision=final["envelope"]["state_revision"],
            final_answers=final["answers"],
            selected_only_answers=scoped["answers"],
            rollback="Each pre-Result snapshot restored; exact context and request replayed",
        ),
        separation=dict(
            signal_unchanged_by_lot=signal_after == signal_before,
            lot_unchanged_by_signal=lot_after == lot_before,
            cross_refusals=crossings,
            revisions="Separate workspace revisions; no shared transaction claimed",
        ),
        manual_acceptance="pending",
        binding_fresh_G5="pending",
        next="solmax",
    )
    save(base / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--inputs", type=Path, default=ROOT / "docs/m1-second-process/inputs.json")
    parser.add_argument(
        "--lot-inputs", type=Path, default=ROOT / "docs/m1-first-process/inputs.json"
    )
    args = parser.parse_args()
    if (ROOT / "STOP").exists() or (ROOT / "STEER.md").exists():
        parser.error("Read and resolve STOP/STEER before running")
    base = args.output.resolve()
    scratch = (ROOT / "_scratch").resolve()
    if base == scratch or not base.is_relative_to(scratch) or base.exists():
        parser.error("Choose a NEW directory inside this execution worktree's ignored _scratch")
    summary = run(base, args.inputs, args.lot_inputs)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
