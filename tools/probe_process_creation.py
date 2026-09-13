"""Emit one exact fictional construction trace through the public product API."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Literal

from tests.fixtures.process_creation import (
    project_definition,
    project_request_data,
    project_research_data,
    small_definition,
    small_result_data,
)
from zaratustra.process_packs import (
    ProcessSnapshot,
    evaluate_snapshot,
    initial_records,
    initial_requirements,
    record_result,
    snapshot_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
Case = Literal["small", "project"]


def _view(snapshot: ProcessSnapshot) -> dict[str, Any]:
    return evaluate_snapshot(snapshot).model_dump(mode="json")


def run(output: Path, case: Case) -> dict[str, Any]:
    output.mkdir()
    states: tuple[dict[str, Any], ...]
    if case == "small":
        definition = small_definition()
        empty = ProcessSnapshot(definition=definition)
        accepted = record_result(empty, small_result_data())
        states = (
            dict(name="initial", view=_view(empty)),
            dict(name="after-result", view=_view(accepted)),
        )
    else:
        definition = project_definition()
        empty = ProcessSnapshot(definition=definition)
        request_done = record_result(empty, project_request_data())
        accepted = record_result(request_done, project_research_data())
        states = (
            dict(name="initial", view=_view(empty)),
            dict(name="after-request", view=_view(request_done)),
            dict(name="after-research", view=_view(accepted)),
        )
    retained = snapshot_bytes(accepted)
    (output / "accepted-snapshot.json").write_bytes(retained)
    summary = dict(
        case=case,
        commit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, encoding="utf-8"
        ).strip(),
        definition=definition.model_dump(mode="json"),
        initial_records=initial_records(definition).model_dump(mode="json"),
        initial_requirements=list(initial_requirements(definition)),
        states=states,
        accepted_snapshot_sha256=hashlib.sha256(retained).hexdigest(),
        writes="isolated probe output only; product construction API is read-only",
    )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=("small", "project"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if (ROOT / "STOP").exists() or (ROOT / "STEER.md").exists():
        parser.error("Read and resolve STOP/STEER before running")
    output = args.output.resolve()
    scratch = (ROOT / "_scratch").resolve()
    if output == scratch or not output.is_relative_to(scratch) or output.exists():
        parser.error("Choose a NEW directory inside this worktree's ignored _scratch")
    print(json.dumps(run(output, args.case), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
