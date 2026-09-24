"""Addressed choices: scope coverage, applicable choices and formal conflicts.

A choice is an ordinary Decision revision with a name, a value and one explicit scope, a
Work or an Activity. The choices that apply to a Work are the current active choices whose
scope covers it: the Work itself, a composite Work above it or its Activity. Scopes
overlap and form no tree, so Core never orders choices by locality, specificity or time:
different values among the applicable choices are a formal conflict, named by address.
Everything here is read in the caller's transaction and grants no rights.
"""

from __future__ import annotations

import sqlite3
from typing import Literal, NamedTuple
from uuid import UUID

from .models import (
    ChoiceApplicability,
    ChoiceState,
    DecisionRef,
    ObligationRevision,
    PlanCondition,
)
from .operations import _current_bodies, _decision_body, _subject_current
from .storage import FoundationError

type Applicability = Literal["active", "inactive", "unresolved", "applicability_stale"]


class Choice(NamedTuple):
    reference: DecisionRef
    value: str


def _addresses(references: tuple[DecisionRef, ...]) -> str:
    return ", ".join(f"Decision {item.decision_id}@{item.revision}" for item in references)


def covering_scopes(connection: sqlite3.Connection, work_id: UUID) -> frozenset[tuple[str, UUID]]:
    """The Work itself, every composite Work above it and its Activity."""

    scopes = {("work", work_id)}
    current = work_id
    while True:
        row = connection.execute(
            "SELECT parent_id FROM work_plan_children WHERE child_id = ?", (str(current),)
        ).fetchone()
        if row is None:
            break
        current = UUID(row[0])
        if ("work", current) in scopes:
            raise FoundationError("corrupt_space", "Composite Work ancestry has a cycle")
        scopes.add(("work", current))
    _revision, _status, activity = _subject_current(connection, work_id, "work")
    if activity is not None:
        scopes.add(("activity", UUID(activity)))
    return frozenset(scopes)


def applicable_choices(
    connection: sqlite3.Connection, work_id: UUID, name: str
) -> tuple[Choice, ...]:
    """Current active choices with this name whose scope covers the Work, by address."""

    scopes = covering_scopes(connection, work_id)
    found: list[Choice] = []
    for record_id, revision, raw in _current_bodies(connection, "decision"):
        state = _decision_body(raw)
        if (
            isinstance(state, ChoiceState)
            and state.status == "active"
            and state.name == name
            and (state.scope.kind, state.scope.record_id) in scopes
        ):
            found.append(
                Choice(DecisionRef(decision_id=UUID(record_id), revision=revision), state.value)
            )
    return tuple(found)


def formal_conflict(
    choices: tuple[Choice, ...],
    *,
    value: str | None = None,
    reference: DecisionRef | None = None,
) -> tuple[DecisionRef, ...]:
    """Every address in a formal conflict, or nothing while all values agree.

    ``value`` and ``reference`` add the exact choice a leaf names, whether or not its
    scope covers the Work.
    """

    values = {choice.value for choice in choices} | ({value} if value is not None else set())
    if len(values) < 2:
        return ()
    found = [choice.reference for choice in choices]
    if reference is not None and reference not in found:
        found.insert(0, reference)
    return tuple(found)


def require_no_conflict(connection: sqlite3.Connection, work_id: UUID, name: str) -> None:
    conflicting = formal_conflict(applicable_choices(connection, work_id, name))
    if conflicting:
        raise FoundationError(
            "decision_conflict",
            f"Choices named {name} for Work {work_id} disagree: {_addresses(conflicting)}",
        )


def _choice_revision(
    connection: sqlite3.Connection, reference: DecisionRef
) -> tuple[ChoiceState | None, bool]:
    """The exact revision's choice (``None`` for an access rule) and whether it holds now."""

    row = connection.execute(
        "SELECT v.body_json, r.current_revision FROM record_revisions v "
        "JOIN records r ON r.record_id = v.record_id "
        "WHERE v.record_id = ? AND v.revision = ? AND r.kind = 'decision'",
        (str(reference.decision_id), reference.revision),
    ).fetchone()
    if row is None:
        raise FoundationError(
            "not_found",
            f"No exact revision Decision {reference.decision_id}@{reference.revision}",
        )
    state = _decision_body(row[0])
    if not isinstance(state, ChoiceState):
        return None, False
    return state, int(row[1]) == reference.revision and state.status == "active"


def choice_holds(connection: sqlite3.Connection, reference: DecisionRef) -> bool:
    """Whether the exact choice revision is still current and active."""

    return _choice_revision(connection, reference)[1]


def resolve_applicability(
    connection: sqlite3.Connection,
    work_id: UUID,
    condition: ChoiceApplicability,
    reference: DecisionRef,
) -> Literal["active", "inactive"]:
    """Check one addressed choice for a conditional obligation of this Work."""

    address = f"Decision {reference.decision_id}@{reference.revision}"
    state, holds = _choice_revision(connection, reference)
    if state is None:
        raise FoundationError("choice_required", f"{address} is not a choice")
    if state.name != condition.choice:
        raise FoundationError(
            "choice_mismatch", f"{address} chooses {state.name}, not {condition.choice}"
        )
    if not holds:
        raise FoundationError("stale_basis", f"{address} is no longer current and active")
    if (state.scope.kind, state.scope.record_id) not in covering_scopes(connection, work_id):
        raise FoundationError("choice_mismatch", f"{address} does not cover Work {work_id}")
    if state.value not in condition.active + condition.inactive:
        raise FoundationError(
            "choice_mismatch", f"{address} value {state.value} is not listed by the obligation"
        )
    require_no_conflict(connection, work_id, condition.choice)
    return "active" if state.value in condition.active else "inactive"


def check_choice_leaf(connection: sqlite3.Connection, work_id: UUID, leaf: PlanCondition) -> None:
    """A decision_value leaf of the given Work's condition, in the refusal order of Core."""

    assert leaf.decision_id and leaf.decision_revision and leaf.name and leaf.value
    reference = DecisionRef(decision_id=leaf.decision_id, revision=leaf.decision_revision)
    address = f"Decision {reference.decision_id}@{reference.revision}"
    state, holds = _choice_revision(connection, reference)
    if state is None or state.name != leaf.name:
        raise FoundationError("invalid_plan", f"{address} is not a choice named {leaf.name}")
    if state.value != leaf.value:
        # The exact revision never changes, so this leaf can never become true.
        raise FoundationError("dependency_closed", f"{address} chose {state.value}")
    if not holds:
        raise FoundationError("stale_basis", f"{address} is no longer current and active")
    conflicting = choice_leaf_conflict(connection, work_id, leaf)
    if conflicting:
        raise FoundationError(
            "decision_conflict",
            f"Choices named {leaf.name} for Work {work_id} disagree: {_addresses(conflicting)}",
        )


def choice_leaf_conflict(
    connection: sqlite3.Connection, work_id: UUID, leaf: PlanCondition
) -> tuple[DecisionRef, ...]:
    assert leaf.decision_id and leaf.decision_revision and leaf.name and leaf.value
    return formal_conflict(
        applicable_choices(connection, work_id, leaf.name),
        value=leaf.value,
        reference=DecisionRef(decision_id=leaf.decision_id, revision=leaf.decision_revision),
    )


def validate_choice_leaf(connection: sqlite3.Connection, leaf: PlanCondition) -> None:
    """A plan may name only an existing exact choice revision with the leaf's name."""

    assert leaf.decision_id and leaf.decision_revision and leaf.name
    reference = DecisionRef(decision_id=leaf.decision_id, revision=leaf.decision_revision)
    try:
        state, _holds = _choice_revision(connection, reference)
    except FoundationError as error:
        raise FoundationError("invalid_plan", error.detail) from error
    if state is None or state.name != leaf.name:
        raise FoundationError(
            "invalid_plan",
            f"Decision {reference.decision_id}@{reference.revision} is not a choice named "
            f"{leaf.name}",
        )


def obligation_applicability(
    connection: sqlite3.Connection, instance: ObligationRevision
) -> tuple[Applicability, tuple[DecisionRef, ...]]:
    """Derived applicability of one recorded instance and any formal conflict over it.

    A recorded resolution is never rewritten: when its exact choice is no longer current
    and active it reads ``applicability_stale`` until a new resolution is recorded.
    """

    condition = instance.definition.applicability
    if not isinstance(condition, ChoiceApplicability):
        return "active", ()
    conflicting = formal_conflict(
        applicable_choices(connection, instance.parent_work_id, condition.choice)
    )
    if instance.applicability == "unresolved":
        return "unresolved", conflicting
    assert instance.choice is not None
    if not choice_holds(connection, instance.choice):
        return "applicability_stale", conflicting
    return instance.applicability, conflicting


def _conflict_error(
    need: str, instance: ObligationRevision, conflicting: tuple[DecisionRef, ...]
) -> FoundationError:
    return FoundationError(
        "decision_conflict",
        f"{need}: choices for obligation {instance.key} disagree: {_addresses(conflicting)}",
    )


def require_applicable(
    connection: sqlite3.Connection, instance: ObligationRevision, need: str
) -> None:
    """Refuse execution of an obligation that is not validly active now, with its state."""

    applicability, conflicting = obligation_applicability(connection, instance)
    if applicability == "applicability_stale":
        raise FoundationError(
            "stale_basis", f"{need}: applicability of obligation {instance.key} is stale"
        )
    if applicability != "active":
        raise FoundationError(
            f"obligation_{applicability}", f"{need}: obligation {instance.key} is {applicability}"
        )
    if conflicting:
        raise _conflict_error(need, instance, conflicting)


def require_consistent_resolutions(
    connection: sqlite3.Connection,
    instances: tuple[ObligationRevision, ...],
    need: str,
    *,
    unresolved: bool = False,
) -> None:
    """A recorded resolution is never rewritten, but a later opposite choice blocks
    integration that relies on it; with ``unresolved`` open conditions count as well."""

    for instance in instances:
        if instance.applicability == "unresolved" and not unresolved:
            continue
        _applicability, conflicting = obligation_applicability(connection, instance)
        if conflicting:
            raise _conflict_error(need, instance, conflicting)


__all__ = [
    "Applicability",
    "Choice",
    "applicable_choices",
    "check_choice_leaf",
    "choice_holds",
    "choice_leaf_conflict",
    "covering_scopes",
    "formal_conflict",
    "obligation_applicability",
    "require_applicable",
    "require_consistent_resolutions",
    "require_no_conflict",
    "resolve_applicability",
    "validate_choice_leaf",
]
