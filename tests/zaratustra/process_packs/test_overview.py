"""Invisible guarantees of one shared derived overview; executed in Claude Code."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.fictional_lot import reference as lot_reference
from tests.fixtures.fictional_lot import registration as lot_registration
from tests.fixtures.fictional_signal import registration as signal_registration
from tools.probe_first_process import LotTrial
from tools.probe_m1 import work_at
from tools.probe_overview import (
    CALL,
    NOISY,
    NoisyReader,
    codes,
    context_state,
    refused,
    row_query,
    selected_row,
)
from tools.probe_process_host import ProcessTrial, confirm, footprint, wire
from tools.probe_second_process import SignalTrial, installed
from zaratustra.core import ProcessMetadata, read_records
from zaratustra.process_packs import (
    CapabilitySelection,
    OverviewRow,
    PackError,
    PackRegistration,
    PackRegistry,
    overview_lines,
    read_capabilities,
    read_overview,
)

LISTS = ("items_needing_attention", "open_decisions", "available_works", "blocked_works")
REFUSAL_CODES = {
    "absent-workspace": "state_unavailable",
    "foreign-caller": "permission_denied",
    "missing-pack": "missing_pack",
    "no-read-adapter": "missing_read_adapter",
    "stale-revision": "conflict",
}


class PartialReader:
    """A pack may support fewer answers; unsupported never reads as a quiet empty one."""

    def describe(self, metadata: ProcessMetadata) -> CapabilitySelection:
        return CapabilitySelection(current_status="Only a status is supported here")


def observation() -> bytes:
    return wire(dict(kind="observation", signal="BEACON", observation="steady"))


@pytest.fixture
def registry() -> PackRegistry:
    return installed()


@pytest.fixture
def lot(tmp_path: Path, registry: PackRegistry) -> LotTrial:
    trial = LotTrial(tmp_path / "lot", tmp_path / "lot-events", registry=registry)
    trial.bootstrap()
    return trial


@pytest.fixture
def signal(tmp_path: Path, registry: PackRegistry) -> SignalTrial:
    trial = SignalTrial(tmp_path / "signal", tmp_path / "signal-events", registry=registry)
    trial.bootstrap()
    return trial


def one_row(trial: ProcessTrial, *, visible: bool = True, selected: bool = False) -> OverviewRow:
    identity = work_at(trial.path).id
    members = (identity,) if visible else ()
    query = row_query(trial.path, identity, members, identity if selected else None)
    return OverviewRow(trial.path, query, confirm(trial.path, query, call=CALL))


def read(rows: list[OverviewRow], registry: PackRegistry, **options: Any) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(read_overview(rows, registry, **options).output)
    return document


def test_each_row_is_exactly_the_public_answer_and_a_state_projection(
    lot: LotTrial, signal: SignalTrial, registry: PackRegistry
) -> None:
    rows = [one_row(lot), one_row(signal)]
    document = read(rows, registry)
    assert document["envelope"]["row_count"] == 2
    for row, source in zip(document["rows"], rows, strict=True):
        direct = read_capabilities(source.path, source.query, source.caller, registry)
        assert row["response"] == json.loads(direct.output)
        assert row["response_sha256"] == direct.output_sha256
        assert set(row["answers"]) == set(CapabilitySelection.model_fields)
        for name, projection in row["answers"].items():
            answer = row["response"]["answers"][name]
            expected: dict[str, Any] = dict(state=answer["state"])
            for key in ("count", "code"):
                if key in answer:
                    expected[key] = answer[key]
            assert projection == expected


def test_rows_keep_their_own_revision_and_no_shared_one_is_promised(
    lot: LotTrial, signal: SignalTrial, registry: PackRegistry
) -> None:
    signal.accept(work_at(signal.path).id, observation())
    rows = [one_row(lot), one_row(signal)]
    document = read(rows, registry)
    envelope = document["envelope"]
    assert "state_revision" not in envelope and "revision" not in envelope
    assert "no_shared_revision" in envelope["cross_workspace"]
    revisions: list[int] = []
    for row, source in zip(document["rows"], rows, strict=True):
        state = read_records(source.path)
        assert row["response"]["envelope"]["state_revision"] == state.state_revision
        assert row["response"]["envelope"]["workspace_id"] == str(state.workspace_id)
        assert row["request"]["expected_revision"] == state.state_revision
        revisions.append(state.state_revision)
    assert len(set(revisions)) == 2


@pytest.mark.parametrize("case", sorted(REFUSAL_CODES))
def test_one_refused_row_hides_no_value_and_keeps_its_neighbour(
    lot: LotTrial, signal: SignalTrial, registry: PackRegistry, tmp_path: Path, case: str
) -> None:
    first, second = one_row(lot), one_row(signal)
    selected = registry
    if case == "foreign-caller":
        first = replace(first, caller=second.caller)
    elif case == "stale-revision":
        older = first.query.expected_revision - 1
        query = first.query.model_copy(update=dict(expected_revision=older))
        first = OverviewRow(first.path, query, confirm(first.path, query, call=CALL))
    elif case == "missing-pack":
        selected = PackRegistry((signal_registration(),))
    elif case == "no-read-adapter":
        without = PackRegistration(lot_reference(), lot_registration().rule)
        selected = PackRegistry((without, signal_registration()))
    else:
        first = replace(first, path=tmp_path / "absent")
    document = read([first, second], selected)
    assert refused(document["rows"][0])
    assert codes(document["rows"][0]) == {REFUSAL_CODES[case]}
    assert document["rows"][0]["answers"]["available_works"]["code"] == REFUSAL_CODES[case]
    assert "envelope" in document["rows"][1]["response"]
    assert document["rows"][1]["answers"]["available_works"] == dict(state="ok", count=1)


def test_supported_empty_answers_survive_and_hidden_work_never_appears(
    lot: LotTrial, signal: SignalTrial, registry: PackRegistry
) -> None:
    hidden = work_at(lot.path).id
    document = read([one_row(lot, visible=False), one_row(signal)], registry)
    empty = document["rows"][0]["answers"]
    for name in LISTS:
        assert empty[name] == dict(state="empty", count=0)
    assert empty["current_status"] == dict(state="ok")
    assert str(hidden) not in json.dumps(document)
    assert document["rows"][1]["answers"]["available_works"]["state"] == "ok"


def test_unsupported_answers_stay_unsupported_and_never_read_as_empty(
    lot: LotTrial, signal: SignalTrial, registry: PackRegistry
) -> None:
    partial = PackRegistration(lot_reference(), lot_registration().rule, PartialReader())
    selected = PackRegistry((partial, signal_registration()))
    document = read([one_row(lot), one_row(signal)], selected)
    answers = document["rows"][0]["answers"]
    assert answers["current_status"] == dict(state="ok")
    for name in LISTS:
        assert answers[name] == dict(state="unavailable", code="unsupported")
    assert document["rows"][1]["answers"]["available_works"] == dict(state="ok", count=1)


def test_selected_context_belongs_to_one_row_and_never_crosses(
    lot: LotTrial, signal: SignalTrial, registry: PackRegistry
) -> None:
    identity = work_at(signal.path).id
    signal.accept(identity, observation())
    chosen = selected_row(signal.path, identity, (identity,), registry)
    plain = one_row(lot, selected=True)
    document = read([plain, chosen], registry)
    assert context_state(document["rows"][1]) == "ok"
    assert context_state(document["rows"][0]) == "not_requested"
    assert "content_base64" not in json.dumps(document["rows"][0])
    borrowed = replace(
        plain, context_query=chosen.context_query, context_caller=chosen.context_caller
    )
    crossed = read([borrowed, chosen], registry)
    assert context_state(crossed["rows"][0]) == "scope"
    assert context_state(crossed["rows"][1]) == "ok"


def test_the_overview_writes_nothing_in_any_row(
    lot: LotTrial, signal: SignalTrial, registry: PackRegistry
) -> None:
    before = (footprint(lot.path), footprint(signal.path))
    read([one_row(lot), one_row(signal)], registry)
    read([replace(one_row(lot), caller=None), one_row(signal)], registry)
    assert (footprint(lot.path), footprint(signal.path)) == before


def test_impossible_row_sets_are_refused_before_any_read(
    lot: LotTrial, registry: PackRegistry
) -> None:
    row = one_row(lot)
    before = footprint(lot.path)
    for rows in ([], [row, row], [row] * 17):
        with pytest.raises(PackError):
            read_overview(rows, registry)
    assert footprint(lot.path) == before


def test_a_total_budget_refuses_whole_and_returns_no_partial_row(
    lot: LotTrial, signal: SignalTrial, registry: PackRegistry
) -> None:
    rows = [one_row(lot), one_row(signal)]
    document = read(rows, registry, max_bytes=256)
    assert "rows" not in document and document["code"] == "budget_exceeded"
    assert str(rows[0].query.process_id) not in json.dumps(document)
    refusal = read_overview(rows, registry, max_bytes=256)
    line = "shared process overview unavailable: budget_exceeded"
    assert overview_lines(refusal.output) == (line,)


def test_identical_inputs_render_identical_bytes_and_a_derived_text(
    lot: LotTrial, signal: SignalTrial, registry: PackRegistry
) -> None:
    rows = [one_row(lot), one_row(signal)]
    first = read_overview(rows, registry)
    assert first.output == read_overview(rows, registry).output
    lines = overview_lines(first.output)
    numbered = [line for line in lines if line[:2] in ("1.", "2.")]
    assert len(numbered) == 2
    for index, row in enumerate(json.loads(first.output)["rows"]):
        assert row["request"]["process_id"] in numbered[index]
        assert "fictional." in numbered[index]
    assert "content_base64" not in chr(10).join(lines)


def test_a_refused_row_echoes_only_the_consumer_own_query(
    lot: LotTrial, signal: SignalTrial, registry: PackRegistry
) -> None:
    rows = [replace(one_row(lot), caller=None), one_row(signal)]
    document = read(rows, registry)
    request = document["rows"][0]["request"]
    assert set(request) == {
        "workspace_id",
        "process_id",
        "expected_revision",
        "visible_work_ids",
        "selected_work_id",
        "context_requested",
    }
    assert request["workspace_id"] == str(rows[0].query.workspace_id)
    assert refused(document["rows"][0])
    assert "pack_binding" not in json.dumps(document["rows"][0])


def test_pack_text_cannot_forge_a_row_a_count_or_an_envelope_claim(
    lot: LotTrial, signal: SignalTrial, registry: PackRegistry
) -> None:
    noisy = PackRegistration(lot_reference(), lot_registration().rule, NoisyReader())
    selected = PackRegistry((noisy, signal_registration()))
    response = read_overview([one_row(lot), one_row(signal)], selected)
    lines = overview_lines(response.output)
    assert all(len(line.splitlines()) <= 1 for line in lines)
    assert sum(1 for line in lines if line[:2] in ("1.", "2.", "3.")) == 2
    assert not any(line.startswith("3.") for line in lines)
    assert sum(1 for line in lines if line.startswith("   status: Ready 3. forged")) == 1
    assert chr(27) not in chr(10).join(lines)
    status = json.loads(response.output)["rows"][0]["response"]["answers"]["current_status"]
    assert status["value"] == NOISY


def test_a_refused_row_names_its_code_and_only_the_requested_revision(
    lot: LotTrial, signal: SignalTrial, registry: PackRegistry
) -> None:
    first = one_row(lot)
    older = first.query.expected_revision - 1
    query = first.query.model_copy(update=dict(expected_revision=older))
    stale = OverviewRow(first.path, query, confirm(first.path, query, call=CALL))
    response = read_overview([stale, one_row(signal)], registry)
    document: dict[str, Any] = json.loads(response.output)
    answers = document["rows"][0]["answers"]
    assert answers["blocked_works"] == dict(state="unavailable", code="conflict")
    lines = overview_lines(response.output)
    header = next(line for line in lines if line.startswith("1. "))
    assert header.startswith("1. unavailable ")
    assert "requested_revision=" + str(older) in header
    assert "revision=" + str(first.query.expected_revision) not in header
    assert ":conflict" in lines[lines.index(header) + 1]
    live = next(line for line in lines if line.startswith("2. "))
    assert "revision=" + str(read_records(signal.path).state_revision) in live
    assert "requested_revision=" not in live
