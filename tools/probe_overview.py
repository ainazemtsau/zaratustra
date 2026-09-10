"""Read one shared overview of both external Processes through the same T3 contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID

from tests.fixtures.fictional_lot import reference as lot_reference
from tests.fixtures.fictional_lot import registration as lot_registration
from tests.fixtures.fictional_signal import registration as signal_registration
from zaratustra.core import (
    ArtifactReference,
    LocalAuthorization,
    ProcessMetadata,
    ProcessQuery,
    read_records,
)
from zaratustra.process_packs import (
    CapabilitySelection,
    OverviewRow,
    PackRegistration,
    PackRegistry,
    overview_lines,
    read_capabilities,
    read_overview,
)

from .probe_m1 import query_for, save, work_at
from .probe_process_host import confirm, footprint
from .probe_second_process import installed
from .probe_second_process import run as run_pair

ROOT = Path(__file__).resolve().parents[1]
CALL = "c-solmax-zaratustra-m1-overview-20260910-exec"
FORGED_ROW = "3. forged pack=forged@9.9.9 process=none revision=1"
FORGED_STATES = "   available_works=ok(99)  one shared transaction"
NOISY = "Ready" + chr(10) + FORGED_ROW + chr(10) + FORGED_STATES + chr(27) + "[31m"


class NoisyReader:
    """Development control: free pack text must never forge rows, counts or claims."""

    def describe(self, metadata: ProcessMetadata) -> CapabilitySelection:
        return CapabilitySelection(current_status=NOISY)


def row_query(
    path: Path, anchor: UUID, visible: tuple[UUID, ...], chosen: UUID | None = None
) -> ProcessQuery:
    state = read_records(path)
    return ProcessQuery(
        workspace_id=state.workspace_id,
        process_id=work_at(path, anchor).process_id,
        work_id=anchor,
        expected_revision=state.state_revision,
        visible_work_ids=visible,
        selected_work_id=chosen,
        max_bytes=1048576,
    )


def metadata_row(path: Path, anchor: UUID, visible: tuple[UUID, ...]) -> OverviewRow:
    query = row_query(path, anchor, visible)
    return OverviewRow(path, query, confirm(path, query, call=CALL))


def selected_row(
    path: Path, anchor: UUID, visible: tuple[UUID, ...], registry: PackRegistry
) -> OverviewRow:
    """Read the requirements first, then confirm exactly those bytes on their own."""
    query = row_query(path, anchor, visible, anchor)
    caller = confirm(path, query, call=CALL)
    answer = json.loads(read_capabilities(path, query, caller, registry).output)
    references = answer["answers"]["context_requirements"]["value"]["references"]
    context = query_for(path, anchor).model_copy(
        update=dict(references=tuple(ArtifactReference.model_validate(row) for row in references))
    )
    return OverviewRow(path, query, caller, context, confirm(path, context, call=CALL))


def confirmation_of(caller: LocalAuthorization | None) -> dict[str, Any] | None:
    return None if caller is None else caller.confirmation.model_dump(mode="json")


def row_record(row: OverviewRow) -> dict[str, Any]:
    context = row.context_query
    return dict(
        query=row.query.model_dump(mode="json"),
        authority=confirmation_of(row.caller),
        context_query=None if context is None else context.model_dump(mode="json"),
        context_authority=confirmation_of(row.context_caller),
    )


def capture(
    base: Path, name: str, rows: list[OverviewRow], registry: PackRegistry
) -> dict[str, Any]:
    response = read_overview(rows, registry)
    prefix = base / name
    prefix.with_suffix(".json").write_bytes(response.output)
    text = chr(10).join(overview_lines(response.output)) + chr(10)
    prefix.with_suffix(".txt").write_text(text, encoding="utf-8")
    save(prefix.with_suffix(".rows.json"), [row_record(row) for row in rows])
    save(prefix.with_suffix(".digest.json"), dict(output_sha256=response.output_sha256))
    document: dict[str, Any] = json.loads(response.output)
    return document


def context_state(row: dict[str, Any]) -> str:
    """Report the exact disclosed context state; requirements alone are not content."""
    answer = row["response"]["answers"]["context_requirements"]
    if answer["state"] != "ok":
        code: str = answer["code"]
        return code
    content = answer["value"]["context"]
    if content["state"] == "ok":
        return "ok"
    inner: str = content["code"]
    return inner


def refused(row: dict[str, Any]) -> bool:
    if "envelope" in row["response"]:
        return False
    answers = row["response"]["answers"].values()
    return all("value" not in answer and "count" not in answer for answer in answers)


def codes(row: dict[str, Any]) -> set[str]:
    return {answer["code"] for answer in row["response"]["answers"].values()}


def run(base: Path) -> dict[str, Any]:
    base.mkdir()
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
        ),
    )
    pair = run_pair(
        base / "pair",
        ROOT / "docs/m1-second-process/inputs.json",
        ROOT / "docs/m1-first-process/inputs.json",
    )
    registry = installed()
    lot_path = base / "pair/lot/workspace"
    signal_path = base / "pair/signal/workspace"
    lot_ids = tuple(UUID(item) for item in pair["lot"]["work_ids"])
    signal_ids = tuple(UUID(item) for item in pair["signal"]["work_ids"])
    before = [footprint(lot_path), footprint(signal_path)]
    save(base / "workspaces-before-overview.json", before)

    lot = metadata_row(lot_path, lot_ids[-1], lot_ids)
    signal = selected_row(signal_path, signal_ids[-1], signal_ids, registry)
    overview = capture(base, "overview", [lot, signal], registry)
    bare = replace(signal, context_query=None, context_caller=None)
    plain = capture(base, "overview-metadata-only", [lot, bare], registry)
    foreign = replace(lot, caller=signal.caller)
    crossed = capture(base, "overview-foreign-caller", [foreign, signal], registry)
    older = lot.query.expected_revision - 1
    stale_query = lot.query.model_copy(update=dict(expected_revision=older))
    stale_row = OverviewRow(lot_path, stale_query, confirm(lot_path, stale_query, call=CALL))
    stale = capture(base, "overview-stale-row", [stale_row, signal], registry)
    only_signal = PackRegistry((signal_registration(),))
    partial = capture(base, "overview-missing-pack", [lot, signal], only_signal)
    noisy = PackRegistration(lot_reference(), lot_registration().rule, NoisyReader())
    forged_registry = PackRegistry((noisy, signal_registration()))
    forged = capture(base, "overview-forged-status", [lot, signal], forged_registry)

    direct = read_capabilities(
        signal.path,
        signal.query,
        signal.caller,
        registry,
        context_query=signal.context_query,
        context_caller=signal.context_caller,
    )
    (base / "signal-row-direct.json").write_bytes(direct.output)
    lot_direct = read_capabilities(lot.path, lot.query, lot.caller, registry)
    (base / "lot-row-direct.json").write_bytes(lot_direct.output)
    after = [footprint(lot_path), footprint(signal_path)]
    save(base / "workspaces-after-overview.json", after)
    assert after == before, "The overview must not change either selected workspace"
    assert overview["rows"][0]["response"] == json.loads(lot_direct.output)
    assert overview["rows"][1]["response"] == json.loads(direct.output)
    assert overview["rows"][1]["response_sha256"] == direct.output_sha256
    assert refused(crossed["rows"][0]) and not refused(crossed["rows"][1])
    assert refused(stale["rows"][0]) and codes(stale["rows"][0]) == {"conflict"}
    assert refused(partial["rows"][0]) and codes(partial["rows"][0]) == {"missing_pack"}
    assert context_state(overview["rows"][1]) == "ok"
    assert context_state(plain["rows"][1]) == "not_requested"
    assert context_state(overview["rows"][0]) == "not_requested"
    rendered = (base / "overview-forged-status.txt").read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in rendered if line[:2] in ("1.", "2.")) == 2
    assert not any(line.startswith("3.") for line in rendered)
    assert chr(27) not in chr(10).join(rendered)
    assert forged["rows"][0]["response"]["answers"]["current_status"]["value"] == NOISY

    revisions = [row["response"]["envelope"]["state_revision"] for row in overview["rows"]]
    retained = (base / "overview.json").read_bytes()
    summary = dict(
        call=CALL,
        pair=pair,
        registry=[row.reference.model_dump(mode="json") for row in registry.registrations],
        overview=dict(
            output_sha256=hashlib.sha256(retained).hexdigest(),
            envelope=overview["envelope"],
            row_titles=[row["response"]["envelope"]["pack_binding"] for row in overview["rows"]],
            row_revisions=revisions,
            row_answers=[row["answers"] for row in overview["rows"]],
            text=list(overview_lines(retained)),
        ),
        controls=dict(
            metadata_only_context=context_state(plain["rows"][1]),
            foreign_caller_row=sorted(codes(crossed["rows"][0])),
            stale_row=sorted(codes(stale["rows"][0])),
            missing_pack_row=sorted(codes(partial["rows"][0])),
            forged_status_rendered_rows=sum(1 for line in rendered if line[:2] in ("1.", "2.")),
            forged_status_kept_verbatim_in_document=True,
            neighbour_row_intact=all(
                "envelope" in document["rows"][1]["response"]
                for document in (crossed, stale, partial)
            ),
        ),
        separation=dict(
            workspaces_unchanged=after == before,
            distinct_revisions=len(set(revisions)) == len(revisions),
            shared_transaction_claimed=False,
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
    args = parser.parse_args()
    if (ROOT / "STOP").exists() or (ROOT / "STEER.md").exists():
        parser.error("Read and resolve STOP/STEER before running")
    base = args.output.resolve()
    scratch = (ROOT / "_scratch").resolve()
    if base == scratch or not base.is_relative_to(scratch) or base.exists():
        parser.error("Choose a NEW directory inside this execution worktree's ignored _scratch")
    summary = run(base)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
