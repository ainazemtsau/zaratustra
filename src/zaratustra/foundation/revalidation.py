"""Accepted child results under changed premises: ``premise_changed`` and explicit rechecks.

The premises of an accepted child result are the exact Artifact inputs of its accepted
revision, with the predecessor results inserted at issue, and the exact Artifact and
Decision leaves of its readiness in the plan revision that issued it. When one of them is
no longer current, the result stays a really performed action: the child stays succeeded
and its Artifact reads. Integrating that result refuses ``premise_changed`` with every
address (held revision to current one) until an explicit recheck names exactly those
changes, and again after any later change. Premises are direct: a changed premise of a
predecessor does not change this result's own premises. Reads use the caller's
transaction; only ``revalidate_result`` writes, through the shared operation path.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from .composition import (
    _conditions,
    _current_artifact,
    _method_use,
    _obligations,
    _outcome_dependencies,
    _parent,
    _plan,
    _PlanDependencies,
    _require_succeeded,
    child_binding,
)
from .models import (
    ArtifactRef,
    DecisionRef,
    PremiseChange,
    ResultRevalidation,
    RevalidateResultRequest,
    StatusReason,
    WorkPlan,
    WorkState,
)
from .operations import (
    LocalAuthority,
    _authorize,
    _local_space,
    _subject_current,
    _subject_state,
)
from .storage import FoundationError, space_connection


def _schema(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def _address(change: PremiseChange) -> str:
    current = "unavailable" if change.current is None else f"@{change.current}"
    return f"{change.kind.title()} {change.record_id}@{change.revision} -> {current}"


def result_premises(
    connection: sqlite3.Connection, work_id: UUID, state: WorkState
) -> tuple[tuple[ArtifactRef, ...], tuple[DecisionRef, ...]]:
    """Exact premises of one planned child result; a Work outside a plan has none here."""

    binding = child_binding(connection, work_id)
    if binding is None:
        return (), ()
    parent_id, issued, _role = binding
    artifacts = list(state.inputs)
    decisions: list[DecisionRef] = []
    if issued is not None:
        plan = _plan(connection, parent_id, issued)
        node = next((child for child in plan.plan.children if child.work_id == work_id), None)
        for leaf in _conditions(node.readiness if node is not None else None):
            if leaf.kind == "artifact_current" and leaf.artifact is not None:
                artifacts.append(leaf.artifact)
            elif (
                leaf.kind in ("decision_active", "decision_value")
                and leaf.decision_id is not None
                and leaf.decision_revision is not None
            ):
                decisions.append(
                    DecisionRef(decision_id=leaf.decision_id, revision=leaf.decision_revision)
                )
    return tuple(dict.fromkeys(artifacts)), tuple(dict.fromkeys(decisions))


def premise_changes(
    connection: sqlite3.Connection, work_id: UUID, state: WorkState
) -> tuple[PremiseChange, ...]:
    """Every premise of the result that no longer holds at its exact address."""

    artifacts, decisions = result_premises(connection, work_id, state)
    changes: list[PremiseChange] = []
    for reference in artifacts:
        row = connection.execute(
            "SELECT current_revision, status FROM records "
            "WHERE record_id = ? AND kind = 'artifact'",
            (str(reference.artifact_id),),
        ).fetchone()
        current = int(row[0]) if row is not None and row[1] == "active" else None
        if current != reference.revision:
            changes.append(
                PremiseChange(
                    kind="artifact",
                    record_id=reference.artifact_id,
                    revision=reference.revision,
                    current=current,
                )
            )
    for decision in decisions:
        row = connection.execute(
            "SELECT r.current_revision, v.body_json FROM records r JOIN record_revisions v "
            "ON v.record_id = r.record_id AND v.revision = r.current_revision "
            "WHERE r.record_id = ? AND r.kind = 'decision'",
            (str(decision.decision_id),),
        ).fetchone()
        current = int(row[0]) if row is not None else None
        if current != decision.revision or json.loads(row[1])["status"] != "active":
            changes.append(
                PremiseChange(
                    kind="decision",
                    record_id=decision.decision_id,
                    revision=decision.revision,
                    current=None if current == decision.revision else current,
                )
            )
    return tuple(changes)


def _latest(
    connection: sqlite3.Connection, parent_id: UUID, work_id: UUID
) -> ResultRevalidation | None:
    row = connection.execute(
        "SELECT payload FROM result_revalidations WHERE parent_id = ? AND child_id = ? "
        "ORDER BY revision DESC LIMIT 1",
        (str(parent_id), str(work_id)),
    ).fetchone()
    return None if row is None else ResultRevalidation.model_validate_json(bytes(row[0]))


def result_standing(
    connection: sqlite3.Connection, work_id: UUID, state: WorkState
) -> tuple[tuple[PremiseChange, ...], ResultRevalidation | None]:
    """Changed premises no recheck covers, and the recheck that currently covers them.

    Only the latest recheck of the child counts, and only while it names exactly the
    current changes of the same accepted outputs and keeps its basis. Before schema 7 and
    for results outside a plan nothing is checked here.
    """

    if _schema(connection) < 7 or state.status != "succeeded":
        return (), None
    binding = child_binding(connection, work_id)
    if binding is None:
        return (), None
    changes = premise_changes(connection, work_id, state)
    if not changes:
        return (), None
    record = _latest(connection, binding[0], work_id)
    if (
        record is not None
        and record.basis is not None
        and set(record.premises) == set(changes)
        and set(record.outputs) == set(state.linked_outputs)
    ):
        return (), record
    return changes, None


def require_current_result(
    connection: sqlite3.Connection, work_id: UUID, state: WorkState, role: str
) -> None:
    """Integration of an accepted child result refuses while a premise change is open."""

    changes, _record = result_standing(connection, work_id, state)
    if changes:
        raise FoundationError(
            "premise_changed",
            f"Result of child {role} ({work_id}) rests on changed premises: "
            + ", ".join(_address(change) for change in changes),
        )


def require_role_result(connection: sqlite3.Connection, plan: WorkPlan, role: str) -> None:
    """A parent output link integrates the accepted result bound to this role, if any."""

    child = next((item for item in plan.children if item.role == role), None)
    if child is None:
        return
    current, status, _ = _subject_current(connection, child.work_id, "work")
    if status != "succeeded":
        return
    state = WorkState.model_validate(_subject_state(connection, child.work_id, current))
    require_current_result(connection, child.work_id, state, role)


def premise_reasons(connection: sqlite3.Connection, work_id: UUID, role: str) -> list[StatusReason]:
    """One addressed reason per open premise change of an accepted child result."""

    current, status, _ = _subject_current(connection, work_id, "work")
    if status != "succeeded":
        return []
    state = WorkState.model_validate(_subject_state(connection, work_id, current))
    changes, _record = result_standing(connection, work_id, state)
    return [
        StatusReason(code="premise_changed", role=role, record_id=work_id, premise=change)
        for change in changes
    ]


def revalidation_in_force(connection: sqlite3.Connection, work_id: UUID) -> int | None:
    """Revision of the recheck that currently lets an accepted child result integrate."""

    current, status, _ = _subject_current(connection, work_id, "work")
    if status != "succeeded":
        return None
    state = WorkState.model_validate(_subject_state(connection, work_id, current))
    try:
        _changes, record = result_standing(connection, work_id, state)
    except FoundationError:
        return None
    return None if record is None else record.revision


def revalidate_result(
    connection: sqlite3.Connection,
    request: RevalidateResultRequest,
    *,
    now: str,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Record that one accepted child result holds under exactly its changed premises.

    The child fills the role in the current plan and is succeeded, its exact outputs are
    current, the named held revisions are exactly the changed premises and each named
    current revision is current. The record permits integration only while those
    revisions stay current.
    """

    if _schema(connection) < 7:
        raise FoundationError("unsupported_schema", "Result rechecks need explicit schema 7")
    _rev, parent, definition = _parent(connection, request.parent_work_id)
    _method_use(
        connection,
        parent,
        actor=request.actor,
        epoch=epoch,
        grants=grants,
        decisions=decisions,
    )
    plan = _plan(connection, request.parent_work_id)
    if plan.revision != request.expected_plan_revision:
        raise FoundationError("stale_plan", "Plan revision changed")
    for reference in plan.plan.basis + parent.inputs:
        _current_artifact(
            connection,
            reference,
            actor=request.actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
    _obligations(connection, request.parent_work_id, definition)
    if parent.status != "proposed":
        raise FoundationError("work_closed", f"Parent Work is {parent.status}")
    node = next((child for child in plan.plan.children if child.role == request.role), None)
    if node is None or node.work_id != request.work_id:
        raise FoundationError(
            "wrong_work",
            f"Work {request.work_id} does not fill role {request.role} in the current plan",
        )
    extra_grants, extra_decisions = _authorize(
        connection,
        actor=request.actor,
        action="record.read",
        epoch=epoch,
        resource_type="work",
        resource_id=request.work_id,
    )
    grants.extend(item for item in extra_grants if item not in grants)
    decisions.extend(item for item in extra_decisions if item not in decisions)
    current, status, _ = _subject_current(connection, request.work_id, "work")
    _require_succeeded(
        request.role, request.work_id, status, f"Child {request.role} is not accepted"
    )
    state = WorkState.model_validate(_subject_state(connection, request.work_id, current))
    if set(request.outputs) != set(state.linked_outputs):
        raise FoundationError("output_mismatch", "Outputs are not the exact accepted result")
    declared = {item.slot: item.media_type for item in state.expected_outputs}
    for output in request.outputs:
        _current_artifact(
            connection,
            output.artifact,
            actor=request.actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
            media_type=declared[output.slot],
        )
    changes = {
        (item.kind, item.record_id): item
        for item in premise_changes(connection, request.work_id, state)
    }
    if {(item.kind, item.record_id, item.revision) for item in request.premises} != {
        (item.kind, item.record_id, item.revision) for item in changes.values()
    }:
        raise FoundationError(
            "premise_mismatch",
            "Changed premises of this result are exactly: "
            + (", ".join(_address(item) for item in changes.values()) or "none"),
        )
    for named in request.premises:
        actual = changes[(named.kind, named.record_id)]
        if actual.current is None:
            raise FoundationError("content_unavailable", f"{_address(actual)} cannot be rechecked")
        if named.current != actual.current:
            raise FoundationError(
                "stale_basis", f"{_address(named)} is not current; current is @{actual.current}"
            )
        if named.kind == "artifact":
            _current_artifact(
                connection,
                ArtifactRef(artifact_id=named.record_id, revision=actual.current),
                actor=request.actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            )
            continue
        extra_grants, extra_decisions = _authorize(
            connection, actor=request.actor, action="record.read", epoch=epoch
        )
        grants.extend(item for item in extra_grants if item not in grants)
        decisions.extend(item for item in extra_decisions if item not in decisions)
        row = connection.execute(
            "SELECT body_json FROM record_revisions WHERE record_id = ? AND revision = ?",
            (str(named.record_id), actual.current),
        ).fetchone()
        if row is None or json.loads(row[0])["status"] != "active":
            raise FoundationError("stale_basis", f"{_address(named)} is not active")
    revision = 1 + int(
        connection.execute(
            "SELECT coalesce(max(revision), 0) FROM result_revalidations "
            "WHERE parent_id = ? AND child_id = ?",
            (str(request.parent_work_id), str(request.work_id)),
        ).fetchone()[0]
    )
    record = ResultRevalidation(
        parent_work_id=request.parent_work_id,
        role=request.role,
        work_id=request.work_id,
        revision=revision,
        plan_revision=plan.revision,
        outputs=request.outputs,
        premises=request.premises,
        basis=request.basis,
        operation_id=request.operation_id,
        created_at=datetime.fromisoformat(now),
    )
    connection.execute(
        "INSERT INTO result_revalidations(parent_id, child_id, revision, role, payload, "
        "operation_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            str(request.parent_work_id),
            str(request.work_id),
            revision,
            request.role,
            record.model_dump_json().encode("utf-8"),
            str(request.operation_id),
            now,
        ),
    )
    targets: list[dict[str, object]] = [
        {"record_id": str(request.work_id), "revision": current},
        {"record_id": str(request.parent_work_id), "revision": plan.revision},
    ]
    targets.extend(
        {"record_id": str(item.artifact.artifact_id), "revision": item.artifact.revision}
        for item in request.outputs
    )
    targets.extend(
        {"record_id": str(item.record_id), "revision": item.current} for item in request.premises
    )
    return {
        "parent_work_id": str(request.parent_work_id),
        "role": request.role,
        "work_id": str(request.work_id),
        "revision": revision,
        "premises": [item.model_dump(mode="json") for item in request.premises],
    }, targets


def dependent_revalidations(
    connection: sqlite3.Connection,
    *,
    artifact_id: UUID | None = None,
    work_id: UUID | None = None,
) -> list[tuple[str, str, int]]:
    """Recheck records whose basis structurally depends on an Artifact or Work being deleted.

    A basis may quote anything the rechecked result rests on, changed or not: the child
    and its outputs, every input and readiness leaf, the parent's inputs and plan history
    with its basis, and upstream children. These are the known structural dependencies of
    the child's outcome (``_outcome_dependencies``, read through the retained index once a
    plan is sanitized) together with the record's own addresses. Called before the deleting
    transaction changes anything; a quote without a stored structural link is not covered.
    """

    plans: dict[str, list[_PlanDependencies | None]] = {}
    dependent: list[tuple[str, str, int]] = []
    for parent_id, child, revision, payload in connection.execute(
        "SELECT parent_id, child_id, revision, payload FROM result_revalidations "
        "ORDER BY parent_id, child_id, revision"
    ).fetchall():
        record = ResultRevalidation.model_validate_json(bytes(payload))
        if record.basis is None:
            continue
        if work_id is not None and child == str(work_id):
            dependent.append((parent_id, child, revision))
            continue
        found = _outcome_dependencies(connection, child, plans)
        named = {item.record_id for item in record.premises if item.kind == "artifact"} | {
            item.artifact.artifact_id for item in record.outputs
        }
        if (
            found.unbounded
            or (artifact_id is not None and artifact_id in found.artifacts | named)
            or (work_id is not None and str(work_id) in found.works)
        ):
            dependent.append((parent_id, child, revision))
    return dependent


def retire_revalidation_bases(
    connection: sqlite3.Connection,
    records: list[tuple[str, str, int]],
    *,
    operations: set[str],
    subjects: set[str],
) -> None:
    """Remove the basis of each dependent recheck; addresses, audit and outcomes stay.

    Such a record no longer permits integration. Its receipt leaves replay and managed
    backups holding its parent are contaminated with the caller's history retirement.
    """

    for parent_id, child, revision in records:
        row = connection.execute(
            "SELECT payload, operation_id FROM result_revalidations "
            "WHERE parent_id = ? AND child_id = ? AND revision = ?",
            (parent_id, child, revision),
        ).fetchone()
        retained = ResultRevalidation.model_validate_json(bytes(row[0])).model_copy(
            update={"basis": None}
        )
        connection.execute(
            "UPDATE result_revalidations SET payload = ? "
            "WHERE parent_id = ? AND child_id = ? AND revision = ?",
            (retained.model_dump_json().encode("utf-8"), parent_id, child, revision),
        )
        operations.add(str(row[1]))
        subjects.add(parent_id)


def read_revalidation(
    path: Path,
    parent_work_id: UUID,
    work_id: UUID,
    authority: LocalAuthority,
    *,
    revision: int | None = None,
) -> ResultRevalidation:
    """Read the latest or one exact recheck of a child result; never falls forward."""

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 7 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Result rechecks need active schema 7")
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="work",
            resource_id=parent_work_id,
        )
        _parent(connection, parent_work_id)
        row = connection.execute(
            "SELECT payload FROM result_revalidations WHERE parent_id = ? AND child_id = ? "
            "AND revision = COALESCE(?, (SELECT max(revision) FROM result_revalidations "
            "WHERE parent_id = ? AND child_id = ?))",
            (str(parent_work_id), str(work_id), revision, str(parent_work_id), str(work_id)),
        ).fetchone()
        if row is None:
            raise FoundationError("not_found", "Exact result recheck is unavailable")
        return ResultRevalidation.model_validate_json(bytes(row[0]))


__all__ = [
    "dependent_revalidations",
    "premise_changes",
    "premise_reasons",
    "read_revalidation",
    "require_current_result",
    "require_role_result",
    "result_premises",
    "result_standing",
    "retire_revalidation_bases",
    "revalidate_result",
    "revalidation_in_force",
]
