"""Invisible integration guarantees; owner-visible choices remain a manual readout."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.fictional_lot import reference
from tools.probe_first_process import ROOT, LotTrial, confirm, footprint, installed, wire
from tools.probe_m1 import query_for, work_at
from zaratustra.core import (
    ArtifactReference,
    MutationError,
    ProcessQuery,
    apply_mutation,
    open_work,
    read_records,
)
from zaratustra.process_packs import PackError, PackRegistry, read_capabilities


@pytest.fixture
def trial(tmp_path: Path) -> LotTrial:
    value = LotTrial(tmp_path / "workspace", tmp_path / "events")
    value.bootstrap()
    return value


def inputs() -> dict[str, Any]:
    value: dict[str, Any] = json.loads((ROOT / "docs/m1-first-process/inputs.json").read_bytes())
    return value


@pytest.mark.parametrize("case", ["incomplete", "duplicate", "missing", "bool", "batch", "stage"])
def test_rule_refusal_after_real_handoff_never_changes_workspace(
    trial: LotTrial, case: str
) -> None:
    data = inputs()
    value = data["inspection"]
    if case == "incomplete":
        value = data["incomplete_inspection"]
    elif case == "duplicate":
        value["checks"][1] = value["checks"][0]
    elif case == "missing":
        value["checks"].pop()
    elif case == "bool":
        value["checks"][0]["observed"] = "true"
    elif case == "batch":
        value["batch"] = "FOREIGN"
    else:
        value["kind"] = "disposition"
    identity = work_at(trial.path).id
    trial.accept(identity, wire(value))
    before = footprint(trial.path)
    with pytest.raises(PackError):
        trial.proposal(identity, case)
    assert footprint(trial.path) == before


def test_proposal_requires_authority_and_exact_pack_without_writes(trial: LotTrial) -> None:
    identity = work_at(trial.path).id
    trial.accept(identity, wire(inputs()["inspection"]))
    before = footprint(trial.path)
    with pytest.raises(PackError, match="missing_pack"):
        trial.proposal(identity, "absent", PackRegistry())
    request = trial.proposal(identity, "installed")
    with pytest.raises(MutationError, match="permission_denied"):
        apply_mutation(trial.path, request)
    assert footprint(trial.path) == before


@pytest.mark.parametrize("decision", ["release", "discard"])
def test_exact_basis_result_grants_restore_and_terminal_guard(
    trial: LotTrial, decision: str
) -> None:
    identity = work_at(trial.path).id
    inspection = trial.accept(identity, wire(inputs()["inspection"]))
    next_id = trial.finish(identity, "inspection")
    assert work_at(trial.path, next_id).pack_binding == reference()
    assert work_at(trial.path, next_id).executor_requirements[1] == inspection.sha256
    scoped = trial.capture("scope", next_id, (next_id,))
    requirements = scoped["answers"]["context_requirements"]["value"]
    refs = tuple(ArtifactReference.model_validate(row) for row in requirements["references"])
    assert inspection in refs
    assert requirements["context"]["state"] == "ok"
    assert scoped["answers"]["recent_important_results"]["count"] == 0
    disposition = inputs()["disposition"] | dict(decision=decision, inspection_sha256="0" * 64)
    trial.accept(next_id, wire(disposition))
    before = footprint(trial.path)
    with pytest.raises(PackError, match="different inspection"):
        trial.proposal(next_id, "wrong-basis")
    assert footprint(trial.path) == before
    disposition["inspection_sha256"] = inspection.sha256
    trial.accept(next_id, wire(disposition))
    closed = trial.finish(next_id, "disposition")
    saved = json.loads((trial.evidence / "disposition.saved-result.json").read_bytes())
    assert inspection.model_dump(mode="json") in saved["event"]["result_references"]
    closed_context = trial.capture("closed-context", closed, (closed,))
    closed_refs = closed_context["answers"]["context_requirements"]["value"]["references"]
    assert inspection.model_dump(mode="json") in closed_refs
    trial.execute(trial.request(closed, "cancel_work"))
    query = query_for(trial.path, closed)
    before = footprint(trial.path)
    with pytest.raises(MutationError):
        open_work(trial.path, query, confirm(trial.path, query))
    assert footprint(trial.path) == before
    assert work_at(trial.path, identity).completion_id is not None
    assert work_at(trial.path, next_id).completion_id is not None
    assert work_at(trial.path, closed).completion_id is None


@pytest.mark.parametrize("case", ["no-caller", "stale", "revoked", "hidden"])
def test_lot_reader_preserves_t3_scope_and_freshness(trial: LotTrial, case: str) -> None:
    identity = work_at(trial.path).id
    snapshot = read_records(trial.path)
    query = ProcessQuery(
        workspace_id=snapshot.workspace_id,
        process_id=work_at(trial.path, identity).process_id,
        work_id=identity,
        expected_revision=snapshot.state_revision,
        visible_work_ids=() if case == "hidden" else (identity,),
        max_bytes=1048576,
    )
    caller = None if case == "no-caller" else confirm(trial.path, query)
    if case == "stale":
        trial.execute(trial.request(identity, "authorize_artifact"))
    elif case == "revoked":
        trial.execute(trial.request(identity, "revoke_work"))
    before = footprint(trial.path)
    result = read_capabilities(trial.path, query, caller, installed())
    assert footprint(trial.path) == before
    value = json.loads(result.output)
    if case == "hidden":
        assert str(identity) not in result.output.decode()
        assert value["answers"]["available_works"]["count"] == 0
    else:
        assert "envelope" not in value
        assert all(
            "value" not in answer and "count" not in answer for answer in value["answers"].values()
        )
