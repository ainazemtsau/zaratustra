"""Real Core tests for the rule seam's invisible state and authority obligations."""

from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from tests.fixtures.process_probe import BatchRule, CycleRule, Rule, RuleBlocked, propose_result
from tools.probe_m1 import Trial, confirm, proposed, query_for, work_at
from zaratustra.core import (
    MutationError,
    MutationRequest,
    ReceiptQuery,
    read_history,
    read_records,
    read_result,
    read_workspace,
    submit_result,
)


@pytest.fixture(params=[BatchRule(), CycleRule()])
def rule(request: pytest.FixtureRequest) -> Rule:
    return cast(Rule, request.param)


@pytest.fixture
def trial(tmp_path: Path, rule: Rule) -> Trial:
    trial = Trial(tmp_path / "workspace", tmp_path / "evidence")
    binding = "probe.batch/v1" if isinstance(rule, BatchRule) else "probe.cycle/v1:observe"
    identity = trial.bootstrap(binding)
    trial.observation(identity, dict(observed=True, recorded=True))
    return trial


def test_rule_proposal_requires_separate_exact_authority(trial: Trial, rule: Rule) -> None:
    request = proposed(trial.path, work_at(trial.path).id, rule)
    db = read_workspace(trial.path).database
    before = db.read_bytes()
    with pytest.raises(MutationError, match="permission_denied"):
        submit_result(trial.path, request)
    caller = confirm(trial.path, request)
    changed = MutationRequest.model_validate(
        request.model_dump() | dict(provenance="Changed after confirmation")
    )
    with pytest.raises(MutationError, match="permission_denied"):
        submit_result(trial.path, changed, caller)
    assert db.read_bytes() == before


def test_stale_context_foreign_process_and_unbound_rule_do_not_write(
    trial: Trial, rule: Rule
) -> None:
    identity = work_at(trial.path).id
    query = query_for(trial.path, identity)
    before = read_workspace(trial.path).database.read_bytes()
    variants: list[tuple[dict[str, Any], str]] = [
        (dict(expected_revision=query.expected_revision - 1), "conflict"),
        (dict(process_id=uuid4()), "scope"),
    ]
    for changes, code in variants:
        changed = type(query).model_validate(query.model_dump() | changes)
        with pytest.raises(MutationError, match=code):
            propose_result(
                trial.path,
                changed,
                confirm(trial.path, changed),
                rule,
                operation_id=uuid4(),
                next_work_id=uuid4(),
                next_artifact_id=uuid4(),
            )
    assert read_workspace(trial.path).database.read_bytes() == before
    trial.execute(trial.request(identity, "set_work_requirements", requirements=("unknown/v2",)))
    before = read_workspace(trial.path).database.read_bytes()
    with pytest.raises(RuleBlocked, match="not bound"):
        proposed(trial.path, identity, rule)
    assert read_workspace(trial.path).database.read_bytes() == before


def test_state_change_after_proposal_and_replay_preserve_one_effect(
    trial: Trial, rule: Rule
) -> None:
    identity = work_at(trial.path).id
    request = proposed(trial.path, identity, rule)
    trial.execute(
        trial.request(
            identity,
            "set_work_requirements",
            requirements=work_at(trial.path, identity).executor_requirements,
        )
    )
    before = read_workspace(trial.path).database.read_bytes()
    with pytest.raises(MutationError, match="conflict"):
        submit_result(trial.path, request, confirm(trial.path, request))
    assert read_workspace(trial.path).database.read_bytes() == before
    request = proposed(trial.path, identity, rule)
    receipt = submit_result(trial.path, request, confirm(trial.path, request))
    before = read_workspace(trial.path).database.read_bytes()
    replay = MutationRequest.model_validate(
        request.model_dump() | dict(expected_revision=read_records(trial.path).state_revision)
    )
    # M0 deliberately refuses renewed execution of done Work before replay lookup.
    # Recovery discovers the committed Result through the separate read seam.
    with pytest.raises(MutationError, match="permission_denied"):
        submit_result(trial.path, replay, confirm(trial.path, replay))
    query = ReceiptQuery(
        workspace_id=request.workspace_id, work_id=identity, operation_id=request.operation_id
    )
    assert read_result(trial.path, query, confirm(trial.path, query)).receipt == receipt
    assert read_workspace(trial.path).database.read_bytes() == before
    assert len([e for e in read_history(trial.path).events if e.request.submission]) == 1


def test_rule_refusal_preserves_records_and_journal(trial: Trial, rule: Rule) -> None:
    identity = work_at(trial.path).id
    trial.observation(identity, dict(observed=False, recorded=False))
    before = read_workspace(trial.path).database.read_bytes()
    history = read_history(trial.path)
    with pytest.raises(RuleBlocked):
        proposed(trial.path, identity, rule)
    assert read_workspace(trial.path).database.read_bytes() == before
    assert read_history(trial.path) == history
