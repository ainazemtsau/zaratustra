"""Invisible guarantees for a second external rule set; executed in Claude Code."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from tests.fixtures.fictional_signal import initial_requirements, reference, registration
from tools.probe_first_process import LotTrial
from tools.probe_m1 import query_for, work_at
from tools.probe_process_host import ProcessTrial, footprint, wire
from tools.probe_second_process import (
    ROOT,
    SignalTrial,
    cross_refusals,
    installed,
    process_query,
)
from zaratustra.core import ArtifactReference, MutationError, apply_mutation
from zaratustra.process_packs import PackError, PackRegistration, PackRegistry, read_capabilities


def observation(value: str = "steady") -> dict[str, Any]:
    return dict(kind="observation", signal="BEACON", observation=value)


@pytest.fixture
def trial(tmp_path: Path) -> SignalTrial:
    value = SignalTrial(tmp_path / "workspace", tmp_path / "events", registry=installed())
    value.bootstrap()
    return value


@pytest.mark.parametrize("case", ["signal", "kind", "value", "extra", "unknown-state"])
def test_signal_refuses_invalid_accepted_bytes_or_stage_without_writes(
    trial: SignalTrial, case: str
) -> None:
    identity = work_at(trial.path).id
    value = observation()
    if case == "signal":
        value["signal"] = "FOREIGN"
    elif case == "kind":
        value["kind"] = "comparison"
    elif case == "value":
        value["observation"] = True
    elif case == "extra":
        value["schedule"] = "tomorrow"
    else:
        trial.execute(
            trial.request(identity, "set_work_requirements", requirements=("unknown-stage",))
        )
    trial.accept(identity, wire(value))
    before = footprint(trial.path)
    with pytest.raises(PackError):
        trial.proposal(identity, case)
    assert footprint(trial.path) == before


@pytest.mark.parametrize("assessment", ["explained", "unexplained"])
def test_changed_basis_is_exact_and_continuation_preserves_history_context_and_replay(
    trial: SignalTrial, assessment: str
) -> None:
    first = work_at(trial.path).id
    steady = trial.accept(first, wire(observation()))
    second = trial.finish(first, "steady")
    assert work_at(trial.path, second).executor_requirements == initial_requirements()
    changed = trial.accept(second, wire(observation("changed")))
    comparison_id = trial.finish(second, "changed")
    assert work_at(trial.path, comparison_id).pack_binding == reference()
    assert work_at(trial.path, comparison_id).executor_requirements[1] == changed.sha256
    scoped = trial.capture("compare-scope", comparison_id, (comparison_id,))
    requirements = scoped["answers"]["context_requirements"]["value"]
    refs = tuple(ArtifactReference.model_validate(row) for row in requirements["references"])
    assert changed in refs and requirements["context"]["state"] == "ok"
    assert scoped["answers"]["recent_important_results"]["count"] == 0
    value = dict(
        kind="comparison", signal="BEACON", assessment=assessment, observation_sha256=steady.sha256
    )
    trial.accept(comparison_id, wire(value))
    before = footprint(trial.path)
    with pytest.raises(PackError, match="different observation"):
        trial.proposal(comparison_id, "earlier-round-is-not-current-basis")
    assert footprint(trial.path) == before
    value["observation_sha256"] = changed.sha256
    comparison = trial.accept(comparison_id, wire(value))
    next_id = trial.finish(comparison_id, "comparison")
    saved = json.loads((trial.evidence / "comparison.saved-result.json").read_bytes())
    assert saved["event"]["request"]["submission"]["result"] == comparison.model_dump(mode="json")
    assert changed.model_dump(mode="json") in saved["event"]["result_references"]
    assert work_at(trial.path, next_id).executor_requirements == initial_requirements()
    assert work_at(trial.path, next_id).status == "ready"
    assert work_at(trial.path, next_id).completion_id is None
    assert all(
        work_at(trial.path, identity).completion_id is not None
        for identity in (first, second, comparison_id)
    )


@pytest.mark.parametrize("case", ["missing", "incompatible"])
def test_other_package_does_not_replace_signal_version(trial: SignalTrial, case: str) -> None:
    identity = work_at(trial.path).id
    trial.accept(identity, wire(observation()))
    if case == "missing":
        registry = PackRegistry((installed().registrations[0],))
    else:
        package = registration()
        registry = PackRegistry(
            (
                PackRegistration(
                    reference().model_copy(update=dict(state_version=2)),
                    package.rule,
                    package.reader,
                ),
            )
        )
    before = footprint(trial.path)
    with pytest.raises(PackError, match=f"{case}_pack"):
        trial.proposal(identity, case, registry)
    assert footprint(trial.path) == before


@pytest.mark.parametrize("case", ["no-caller", "stale", "revoked", "hidden", "context-caller"])
def test_signal_read_scope_freshness_and_context_authority(trial: SignalTrial, case: str) -> None:
    identity = work_at(trial.path).id
    query = process_query(trial.path, identity).model_copy(
        update=dict(
            visible_work_ids=() if case == "hidden" else (identity,),
            selected_work_id=identity if case == "context-caller" else None,
        )
    )
    caller = None if case == "no-caller" else trial.confirm(trial.path, query)
    context = query_for(trial.path, identity) if case == "context-caller" else None
    if case == "stale":
        trial.execute(trial.request(identity, "authorize_artifact"))
    elif case == "revoked":
        trial.execute(trial.request(identity, "revoke_work"))
    before = footprint(trial.path)
    result = read_capabilities(trial.path, query, caller, trial.registry, context_query=context)
    assert footprint(trial.path) == before
    value = json.loads(result.output)
    if case == "hidden":
        assert str(identity) not in result.output.decode()
        assert value["answers"]["available_works"]["count"] == 0
    elif case == "context-caller":
        answer = value["answers"]["context_requirements"]["value"]["context"]
        assert answer["state"] == "denied" and "value" not in answer
    else:
        assert "envelope" not in value
        assert all(
            "value" not in answer and "count" not in answer for answer in value["answers"].values()
        )


def test_shared_registry_never_grants_foreign_read_write_or_cross_package_execution(
    tmp_path: Path,
) -> None:
    registry = installed()
    lot = LotTrial(tmp_path / "lot", tmp_path / "lot-events", registry=registry)
    signal = SignalTrial(tmp_path / "signal", tmp_path / "signal-events", registry=registry)
    lot_id, signal_id = lot.bootstrap(), signal.bootstrap()
    lot.accept(lot_id, wire(observation()))
    before = footprint(lot.path)
    with pytest.raises(PackError, match="invalid_lot_input"):
        lot.proposal(lot_id, "signal-bytes-are-not-lot-input")
    assert footprint(lot.path) == before
    lot_input = json.loads((ROOT / "docs/m1-first-process/inputs.json").read_bytes())["inspection"]
    lot.accept(lot_id, wire(lot_input))
    signal.accept(signal_id, wire(observation()))
    crossings = cross_refusals(
        (lot.path, lot_id), (signal.path, signal_id), registry, tmp_path / "crossings"
    )
    assert len(crossings) == 4
    pairs: tuple[tuple[ProcessTrial, UUID, ProcessTrial], ...] = (
        (lot, lot_id, signal),
        (signal, signal_id, lot),
    )
    for source, identity, target in pairs:
        proposal = source.proposal(identity, "own-valid-proposal")
        caller = source.confirm(source.path, proposal)
        own_before, other_before = footprint(source.path), footprint(target.path)
        with pytest.raises(MutationError):
            apply_mutation(target.path, proposal, caller)
        with pytest.raises(MutationError, match="permission_denied"):
            apply_mutation(source.path, proposal)
        assert (footprint(source.path), footprint(target.path)) == (own_before, other_before)
        source.execute(proposal)
        assert footprint(target.path) == other_before
        assert work_at(source.path, identity).completion_id is not None
