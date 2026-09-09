"""Behavior checks of exact installation, retained state and authority boundaries."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from tools.probe_m1 import query_for, work_at
from tools.probe_packs import (
    FictionalBatchAdapter,
    PacksTrial,
    confirm,
    proposed,
    reference,
    registry,
)
from zaratustra.core import (
    ContextQuery,
    LocalAuthorization,
    MutationError,
    MutationRequest,
    Process,
    migrate_workspace,
    open_work,
    read_history,
    read_records,
    read_workspace,
    submit_result,
)
from zaratustra.process_packs import PackError, PackRegistration, PackRegistry, propose_result


@pytest.fixture
def trial(tmp_path: Path) -> PacksTrial:
    trial = PacksTrial(tmp_path / "workspace", tmp_path / "evidence")
    identity = trial.bootstrap()
    migrate_workspace(trial.path, target_version=7)
    trial.execute(trial.bind(identity, reference(), registry(reference())))
    trial.observation(identity)
    return trial


def test_registration_identity_is_immutable_and_versions_coexist() -> None:
    ref = reference()
    registration = PackRegistration(ref, FictionalBatchAdapter())
    empty = PackRegistry()
    installed = empty.register(registration)
    assert empty.registrations == ()
    assert installed.register(registration) is installed
    for collision in (
        PackRegistration(ref, FictionalBatchAdapter()),
        replace(registration, reference=reference(state_version=2)),
    ):
        with pytest.raises(PackError, match="registration_collision"):
            installed.register(collision)
    v2 = PackRegistration(reference("2.0.0"), FictionalBatchAdapter())
    both = installed.register(v2)
    assert both.resolve(ref) is registration
    assert both.resolve(v2.reference) is v2
    with pytest.raises(PackError, match="registration_collision"):
        PackRegistry((registration, registration))


@pytest.mark.parametrize("field", ["contract_version", "state_version"])
def test_unsupported_version_never_resolves_even_when_registered(field: str) -> None:
    ref = reference(**{field: 2})
    with pytest.raises(PackError, match="incompatible_pack"):
        registry(ref).resolve(ref)


@pytest.mark.parametrize(
    ("installed", "error"),
    [
        (registry(), "missing_pack"),
        (registry(reference("2.0.0")), "missing_pack"),
        (registry(reference(state_version=2)), "incompatible_pack"),
        (registry(reference(contract_version=2)), "incompatible_pack"),
        (registry(reference(process_type="other.type")), "incompatible_pack"),
    ],
)
def test_missing_and_incompatible_pack_preserve_state(
    trial: PacksTrial, installed: PackRegistry, error: str
) -> None:
    state = read_records(trial.path)
    history = read_history(trial.path)
    before = read_workspace(trial.path).database.read_bytes()
    with pytest.raises(PackError, match=error):
        proposed(trial.path, work_at(trial.path).id, installed)
    assert read_workspace(trial.path).database.read_bytes() == before
    assert read_records(trial.path) == state and read_history(trial.path) == history


def test_reinstall_exact_version_continues_old_work_and_inherits_binding(trial: PacksTrial) -> None:
    identity = work_at(trial.path).id
    before = read_records(trial.path)
    request = proposed(trial.path, identity, registry(reference(), reference("2.0.0")))
    assert read_records(trial.path) == before
    with pytest.raises(MutationError, match="permission_denied"):
        submit_result(trial.path, request)
    changed = MutationRequest.model_validate(request.model_dump() | dict(provenance="replacement"))
    with pytest.raises(MutationError, match="permission_denied"):
        submit_result(trial.path, changed, confirm(trial.path, request))
    receipt = trial.execute(request)
    assert request.submission is not None
    continuation = work_at(trial.path, request.submission.next_work.work_id)
    assert continuation.pack_binding == work_at(trial.path, identity).pack_binding == reference()
    assert continuation.authority_scope == "work_metadata"
    assert receipt.new_revision == before.state_revision + 1
    event = read_history(trial.path).events[-1]
    assert event.next_work == continuation and event.after.status == "done"
    query = query_for(trial.path, continuation.id)
    content = json.loads(open_work(trial.path, query, confirm(trial.path, query)).output)
    rows = {s["locator"]: s["data"] for s in content["context"]["sources"]}
    assert rows[f"work:{continuation.id}"]["pack_binding"] == reference().model_dump(mode="json")
    assert (
        rows[f"process:{continuation.process_id}"]["pack_binding"]
        == rows[f"work:{continuation.id}"]["pack_binding"]
    )
    with pytest.raises(PackError, match="missing_observation"):
        proposed(trial.path, continuation.id, registry(reference()))
    trial.observation(continuation.id)
    second = proposed(trial.path, continuation.id, registry(reference()))
    trial.execute(second)
    assert second.submission is not None
    assert work_at(trial.path, second.submission.next_work.work_id).pack_binding == reference()


def test_bound_process_and_work_cannot_be_retargeted(trial: PacksTrial) -> None:
    identity = work_at(trial.path).id
    before = read_workspace(trial.path).database.read_bytes()
    for ref in (reference("2.0.0"), reference()):
        request = trial.bind(identity, ref, registry(ref))
        with pytest.raises(MutationError, match="permission_denied|pack_bound"):
            trial.execute(request)
        assert read_workspace(trial.path).database.read_bytes() == before
    trial.execute(
        trial.request(identity, "set_work_requirements", requirements=("plain metadata",))
    )
    assert work_at(trial.path).pack_binding == reference()
    process = next(r for r in read_records(trial.path).records if isinstance(r, Process))
    assert process.pack_binding == reference()


@pytest.mark.parametrize("mode", ["none", "revoked", "cancelled", "stale", "foreign", "changed"])
def test_context_authority_precedes_pack_dispatch(trial: PacksTrial, mode: str) -> None:
    identity = work_at(trial.path).id
    query = query_for(trial.path, identity)
    caller: LocalAuthorization | None = confirm(trial.path, query)
    if mode == "none":
        caller = None
    elif mode in ("revoked", "cancelled"):
        operation = "revoke_work" if mode == "revoked" else "cancel_work"
        trial.execute(trial.request(identity, operation))
    elif mode == "stale":
        trial.execute(
            trial.request(identity, "set_work_requirements", requirements=("probe.batch/v1",))
        )
    else:
        payload: dict[str, Any] = (
            dict(process_id=uuid4()) if mode == "foreign" else dict(max_bytes=99999)
        )
        query = ContextQuery.model_validate(query.model_dump() | payload)
        if mode == "foreign":
            caller = confirm(trial.path, query)
    before = read_workspace(trial.path).database.read_bytes()

    class NeverCalled(FictionalBatchAdapter):
        def next_work(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("Rule ran without a current authorized context")

    installed = PackRegistry((PackRegistration(reference(), NeverCalled()),))
    with pytest.raises(MutationError):
        propose_result(
            trial.path,
            query,
            caller,
            installed,
            operation_id=uuid4(),
            next_work_id=uuid4(),
            next_artifact_id=uuid4(),
        )
    assert read_workspace(trial.path).database.read_bytes() == before


def test_change_between_proposal_and_submit_conflicts(trial: PacksTrial) -> None:
    identity = work_at(trial.path).id
    proposal = proposed(trial.path, identity, registry(reference()))
    trial.execute(
        trial.request(identity, "set_work_requirements", requirements=("probe.batch/v1",))
    )
    before = read_workspace(trial.path).database.read_bytes()
    with pytest.raises(MutationError, match="conflict"):
        submit_result(trial.path, proposal, confirm(trial.path, proposal))
    assert read_workspace(trial.path).database.read_bytes() == before


def test_legacy_unbound_work_requires_explicit_binding(tmp_path: Path) -> None:
    trial = PacksTrial(tmp_path / "workspace", tmp_path / "evidence")
    identity = trial.bootstrap()
    trial.observation(identity)
    before = read_workspace(trial.path).database.read_bytes()
    with pytest.raises(PackError, match="unbound_pack"):
        proposed(trial.path, identity, registry(reference()))
    assert read_workspace(trial.path).database.read_bytes() == before
