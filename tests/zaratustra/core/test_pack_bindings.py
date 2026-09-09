"""Real migration, atomic bind, replay and retained-history checks."""

from __future__ import annotations

import sqlite3
from importlib import import_module
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from tools.probe_m1 import query_for, restore_snapshot, work_at
from tools.probe_packs import PacksTrial, confirm, reference, registry
from tools.retain_trial import retain_trial
from zaratustra.core import (
    MutationError,
    MutationRequest,
    Process,
    apply_mutation,
    migrate_workspace,
    read_history,
    read_records,
    read_workspace,
)
from zaratustra.process_probe import BatchRule, propose_result


def domain_bytes(path: Path) -> dict[str, list[Any]]:
    database = read_workspace(path).database
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        return {
            table: connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
            for table in (
                "core_records",
                "core_state",
                "mutation_events",
                "mutation_receipts",
                "artifact_versions",
                "accepted_handoffs",
                "work_results",
            )
        }


@pytest.fixture
def trial(tmp_path: Path) -> PacksTrial:
    trial = PacksTrial(tmp_path / "workspace", tmp_path / "evidence")
    trial.bootstrap()
    return trial


def test_schema7_is_explicit_preserves_legacy_bytes_and_restores(
    trial: PacksTrial, tmp_path: Path
) -> None:
    identity = work_at(trial.path).id
    trial.observation(identity)
    snapshot = read_records(trial.path)
    history = read_history(trial.path)
    original = domain_bytes(trial.path)
    db = read_workspace(trial.path).database
    before = db.read_bytes()
    request = trial.bind(identity, reference(), registry(reference()))
    with pytest.raises(MutationError, match="schema"):
        trial.execute(request)
    assert db.read_bytes() == before and read_workspace(trial.path).schema_version == 6
    manifest = retain_trial(trial.path, tmp_path / "before.zip")
    assert migrate_workspace(trial.path, target_version=7).schema_version == 7
    assert domain_bytes(trial.path) == original
    assert read_records(trial.path) == snapshot and read_history(trial.path) == history
    migrated = db.read_bytes()
    migrate_workspace(trial.path, target_version=7)
    assert db.read_bytes() == migrated
    restored = restore_snapshot(tmp_path / "before.zip", tmp_path / "restore", manifest)
    assert domain_bytes(restored) == original
    assert read_workspace(restored).schema_version == 6


def test_binding_requires_exact_authority_and_retains_every_other_field(trial: PacksTrial) -> None:
    migrate_workspace(trial.path, target_version=7)
    identity = work_at(trial.path).id
    request = trial.bind(identity, reference(), registry(reference()))
    before = read_records(trial.path)
    db = read_workspace(trial.path).database
    original = db.read_bytes()
    with pytest.raises(MutationError, match="permission_denied"):
        apply_mutation(trial.path, request)
    caller = confirm(trial.path, request)
    changed = MutationRequest.model_validate(
        request.model_dump() | dict(pack_binding=reference("2.0.0"))
    )
    with pytest.raises(MutationError, match="permission_denied"):
        apply_mutation(trial.path, changed, caller)
    assert db.read_bytes() == original
    receipt = apply_mutation(trial.path, request, caller)
    after = read_records(trial.path)
    before_rows = {r.id: r for r in before.records}
    for row in after.records:
        old = before_rows[row.id]
        if row.id == identity or isinstance(row, Process):
            assert row.model_dump(exclude={"revision", "pack_binding"}) == old.model_dump(
                exclude={"revision", "pack_binding"}
            )
        else:
            assert row == old
    event = read_history(trial.path).events[-1]
    assert event.before.pack_binding is None and event.after.pack_binding == reference()
    assert event.process_before is not None and event.process_before.pack_binding is None
    assert event.process_after is not None and event.process_after.pack_binding == reference()
    assert receipt.new_revision == before.state_revision + 1 == after.state_revision


def test_binding_replay_conflict_and_collision_have_one_effect(trial: PacksTrial) -> None:
    migrate_workspace(trial.path, target_version=7)
    identity = work_at(trial.path).id
    request = trial.bind(identity, reference(), registry(reference()))
    receipt = trial.execute(request)
    db = read_workspace(trial.path).database
    before = db.read_bytes()
    with pytest.raises(MutationError, match="conflict"):
        trial.execute(request)
    refreshed = MutationRequest.model_validate(
        request.model_dump() | dict(expected_revision=receipt.new_revision)
    )
    assert trial.execute(refreshed) == receipt
    collision = MutationRequest.model_validate(
        refreshed.model_dump() | dict(provenance="different")
    )
    with pytest.raises(MutationError, match="collision"):
        trial.execute(collision)
    repeated = MutationRequest.model_validate(refreshed.model_dump() | dict(operation_id=uuid4()))
    with pytest.raises(MutationError, match="pack_bound"):
        trial.execute(repeated)
    assert db.read_bytes() == before
    assert (
        len([e for e in read_history(trial.path).events if e.request.operation == "bind_pack"]) == 1
    )


@pytest.mark.parametrize("operation", ["revoke_work", "cancel_work"])
def test_binding_respects_current_work_rights(trial: PacksTrial, operation: str) -> None:
    migrate_workspace(trial.path, target_version=7)
    identity = work_at(trial.path).id
    trial.execute(trial.request(identity, operation))
    request = trial.bind(identity, reference(), registry(reference()))
    before = read_workspace(trial.path).database.read_bytes()
    with pytest.raises(MutationError, match="permission_denied"):
        trial.execute(request)
    assert read_workspace(trial.path).database.read_bytes() == before


def test_binding_transaction_failure_rolls_back_both_records_and_history(
    trial: PacksTrial, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrate_workspace(trial.path, target_version=7)
    identity = work_at(trial.path).id
    request = trial.bind(identity, reference(), registry(reference()))
    caller = confirm(trial.path, request)
    before = read_workspace(trial.path).database.read_bytes()
    state = read_records(trial.path)
    history = read_history(trial.path)
    mutation_module = import_module("zaratustra.core.mutations")

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Injected failure after Process/Work/event writes, before receipt")

    original = mutation_module.event_receipt

    # Earlier history validation also calls event_receipt; fail only on the new bind event.
    def fail_new(event: Any) -> Any:
        if event.request.operation == "bind_pack":
            return fail(event)
        return original(event)

    with monkeypatch.context() as patch:
        patch.setattr(mutation_module, "event_receipt", fail_new)
        with pytest.raises(RuntimeError, match="Injected failure"):
            apply_mutation(trial.path, request, caller)
    assert read_workspace(trial.path).database.read_bytes() == before
    assert read_records(trial.path) == state and read_history(trial.path) == history
    receipt = apply_mutation(trial.path, request, caller)
    assert receipt.new_revision == state.state_revision + 1


def test_binding_later_work_preserves_legacy_result_and_process_history(trial: PacksTrial) -> None:
    identity = work_at(trial.path).id
    trial.observation(identity)
    query = query_for(trial.path, identity)
    proposal = propose_result(
        trial.path,
        query,
        confirm(trial.path, query),
        BatchRule(),
        operation_id=uuid4(),
        next_work_id=uuid4(),
        next_artifact_id=uuid4(),
    )
    trial.execute(proposal)
    before = domain_bytes(trial.path)
    legacy_history = read_history(trial.path)
    migrate_workspace(trial.path, target_version=7)
    assert domain_bytes(trial.path) == before
    assert proposal.submission is not None
    next_id = proposal.submission.next_work.work_id
    trial.execute(trial.bind(next_id, reference(), registry(reference())))
    assert read_history(trial.path).events[:-1] == legacy_history.events
    assert work_at(trial.path, identity).pack_binding is None
    assert work_at(trial.path, next_id).pack_binding == reference()
    after = domain_bytes(trial.path)
    assert after["work_results"] == before["work_results"]
    assert after["accepted_handoffs"] == before["accepted_handoffs"]
