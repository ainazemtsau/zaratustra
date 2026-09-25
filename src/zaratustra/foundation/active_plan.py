"""Revision of a started composite plan with an explicit decision per node.

A new plan revision names a decision for every node of the current revision (keep,
replace, cancel, stale or release) and for every new node (add). Nothing is inherited
implicitly: an issue continues only for a kept node that passes its recheck in the new
revision, and an active Attempt of that node continues only through an explicit transfer
record. Every other Attempt stays pinned to its old revision and is fenced; its node left
the plan with a recorded outcome. Roles stay the stable addresses of obligations: an
obligation whose evidence belongs to a Work that no longer fills its role reopens
(``node_replaced``), while applicability and waivers stay with the requirement.

Records here are addresses only. The rationale lives in the plan revision, the outcome
basis of a node that left unfinished lives in that Work's own revision.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from .composition import (
    _current_artifact,
    _evaluate,
    _method_use,
    _obligations,
    _parent,
    _pinned_plan,
    _plan,
    _validate_choice_leaves,
    _validate_plan,
    check_work_close,
    child_binding,
    revision_role_works,
    verify_premises_changed,
)
from .models import (
    MethodRef,
    PlanChild,
    PlanNode,
    PlanNodeDecision,
    PlanNodes,
    ReviseActivePlanRequest,
    RoleFilling,
    WorkState,
)
from .operations import (
    LocalAuthority,
    _authorize,
    _local_space,
    _subject_current,
    _subject_state,
    _write_subject,
    closed_work_state,
)
from .storage import FoundationError, space_connection

# Assignments that can still take an effect; only these Attempts are transferred.
_CONTINUING = ("assigned", "waiting", "ready")


def _node(item: PlanChild) -> str:
    return f"{item.role} ({item.work_id})"


def _extend(target: list[dict[str, object]], values: list[dict[str, object]]) -> None:
    target.extend(value for value in values if value not in target)


def _require_mapping(
    request: ReviseActivePlanRequest, old: dict[str, PlanChild], new: dict[str, PlanChild]
) -> None:
    """Every node of the current revision and every new node has an explicit decision."""

    decided = {item.role for item in request.nodes}
    for role, child in old.items():
        if role not in decided:
            raise FoundationError(
                "mapping_incomplete",
                f"Node {_node(child)} of plan revision {request.expected_plan_revision} "
                "has no decision",
            )
    for role, child in new.items():
        if role not in old and role not in decided:
            raise FoundationError(
                "mapping_incomplete", f"New node {_node(child)} needs an explicit add"
            )


def _require_valid_decision(
    connection: sqlite3.Connection,
    item: PlanNodeDecision,
    old: dict[str, PlanChild],
    new: dict[str, PlanChild],
    plan_revision: int,
) -> tuple[int, WorkState] | None:
    """Check one decision against both revisions; return the current node's Work state."""

    node = old.get(item.role)
    target = new.get(item.role)
    if item.decision == "add":
        if node is not None:
            raise FoundationError(
                "mapping_invalid", f"add names node {_node(node)} of the current revision"
            )
        if target is None or target.work_id != item.work_id:
            raise FoundationError(
                "mapping_invalid",
                f"add of role {item.role} does not match the new plan node for Work {item.work_id}",
            )
        return None
    if node is None or node.work_id != item.work_id:
        raise FoundationError(
            "mapping_invalid",
            f"{item.decision} names role {item.role} with Work {item.work_id}, which is not a "
            f"node of plan revision {plan_revision}",
        )
    revision, status, _ = _subject_current(connection, node.work_id, "work")
    if status == "deleted":
        raise FoundationError("content_unavailable", f"Node {_node(node)} was deleted")
    state = WorkState.model_validate(_subject_state(connection, node.work_id, revision))
    finished = state.status != "proposed"
    if item.decision == "keep":
        binding = child_binding(connection, node.work_id)
        issued = binding is not None and binding[1] == plan_revision
        if (
            target is None
            or target.work_id != node.work_id
            or target.state != node.state
            or ((issued or finished) and target.readiness != node.readiness)
        ):
            raise FoundationError(
                "mapping_invalid",
                f"Kept node {_node(node)} changed its definition; replace it explicitly",
            )
    elif item.decision == "replace":
        if target is None or target.work_id != item.replacement:
            raise FoundationError(
                "mapping_invalid",
                f"Replacement of node {_node(node)} is not the new plan node of role {item.role}",
            )
        if finished != (item.closure is None):
            raise FoundationError(
                "mapping_invalid",
                f"Node {_node(node)} is {state.status}: "
                + ("it keeps its outcome" if finished else "it needs an outcome as it leaves"),
            )
    else:
        if target is not None:
            raise FoundationError(
                "mapping_invalid", f"{item.decision} keeps node {_node(node)} in the new plan"
            )
        if (item.decision == "release") != finished:
            raise FoundationError(
                "mapping_invalid",
                f"Node {_node(node)} is {state.status}: "
                + (
                    "release it, it keeps its outcome"
                    if finished
                    else "cancel or stale it, release is for a finished node"
                ),
            )
    return revision, state


def _close_node(
    connection: sqlite3.Connection,
    request: ReviseActivePlanRequest,
    item: PlanNodeDecision,
    node: PlanChild,
    revision: int,
    state: WorkState,
    *,
    now: str,
    epoch: int,
    authority_source: str,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> int:
    """Record the outcome of an unfinished node leaving the plan, as ``close_work`` does."""

    closure = item.closure
    assert closure is not None
    if revision != closure.expected_revision:
        raise FoundationError(
            "stale_work",
            f"Node {_node(node)} is at revision {revision}, not {closure.expected_revision}",
        )
    extra_grants, extra_decisions = _authorize(
        connection,
        actor=request.actor,
        action="work.accept",
        epoch=epoch,
        resource_type="work",
        resource_id=node.work_id,
    )
    _extend(grants, extra_grants)
    _extend(decisions, extra_decisions)
    check_work_close(
        connection,
        node.work_id,
        state,
        child_binding(connection, node.work_id),
        actor=request.actor,
        epoch=epoch,
        grants=grants,
        decisions=decisions,
    )
    if closure.outcome == "stale":
        verify_premises_changed(
            connection,
            node.work_id,
            state,
            closure.premises,
            closure.decision_premises,
            actor=request.actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
    closed = closed_work_state(
        connection,
        node.work_id,
        state,
        outcome=closure.outcome,
        basis=closure.basis,
        premises=closure.premises,
        decision_premises=closure.decision_premises,
        operation_id=request.operation_id,
        authority_source=authority_source,
        now=now,
        cause="revise_active_plan",
    )
    _write_subject(
        connection,
        record_id=node.work_id,
        kind="work",
        parent_id=state.activity_id,
        operation_id=request.operation_id,
        actor=request.actor,
        now=now,
        status=closure.outcome,
        state=closed,
        revision=revision + 1,
    )
    return revision + 1


def _recheck_kept(
    connection: sqlite3.Connection,
    request: ReviseActivePlanRequest,
    parent: WorkState,
    target: PlanChild,
    state: WorkState,
    *,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> None:
    """An issue continues only if the kept node is issuable again in the new revision."""

    extra_grants, extra_decisions = _authorize(
        connection,
        actor=request.actor,
        action="work.execute",
        epoch=epoch,
        resource_type="work",
        resource_id=target.work_id,
    )
    _extend(grants, extra_grants)
    _extend(decisions, extra_decisions)
    for reference in request.plan.basis + parent.inputs + state.inputs:
        _current_artifact(
            connection,
            reference,
            actor=request.actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
    references = _evaluate(
        connection,
        request.plan,
        target.readiness,
        work_id=target.work_id,
        actor=request.actor,
        epoch=epoch,
        grants=grants,
        decisions=decisions,
    )
    if not set(references).issubset(state.inputs):
        raise FoundationError("stale_input", "Kept node is missing an exact dependency input")


def _transfer_attempts(
    connection: sqlite3.Connection,
    request: ReviseActivePlanRequest,
    target: PlanChild,
    method: MethodRef,
    *,
    from_revision: int,
    now: str,
) -> list[UUID]:
    """Transfer every active Attempt of a kept node that its current pin still admits."""

    transferred: list[UUID] = []
    for (attempt_id,) in connection.execute(
        "SELECT a.attempt_id FROM execution_attempts a JOIN execution_assignments s "
        "ON s.attempt_id = a.attempt_id WHERE a.work_id = ? AND a.status = 'active' "
        f"AND s.status IN ({', '.join('?' for _ in _CONTINUING)}) ORDER BY a.generation",
        (str(target.work_id), *_CONTINUING),
    ).fetchall():
        try:
            # Old allow is not inherited: only an Attempt admitted in the current revision.
            _pinned_plan(
                connection,
                UUID(attempt_id),
                target.work_id,
                (request.work_id, target.role, from_revision, method),
            )
        except FoundationError:
            continue
        connection.execute(
            "INSERT INTO execution_plan_transfers(attempt_id, plan_revision, work_id, "
            "parent_id, role, from_plan_revision, method_id, method_version, "
            "method_checksum, operation_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                attempt_id,
                from_revision + 1,
                str(target.work_id),
                str(request.work_id),
                target.role,
                from_revision,
                str(method.method_id),
                method.version,
                method.checksum,
                str(request.operation_id),
                now,
            ),
        )
        transferred.append(UUID(attempt_id))
    return transferred


def revise_active_plan(
    connection: sqlite3.Connection,
    request: ReviseActivePlanRequest,
    *,
    now: str,
    epoch: int,
    authority_source: str,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Record plan revision N+1 with its node decisions in one transaction.

    Any refusal leaves N, every node and every Attempt unchanged.
    """

    parent_revision, _status, _ = _subject_current(connection, request.work_id, "work")
    _rev, parent, definition = _parent(connection, request.work_id)
    if parent_revision != request.expected_work_revision:
        raise FoundationError("stale_work", "Parent Work revision changed")
    _method_use(
        connection, parent, actor=request.actor, epoch=epoch, grants=grants, decisions=decisions
    )
    current = _plan(connection, request.work_id)
    if current.revision != request.expected_plan_revision:
        raise FoundationError("stale_plan", "Plan revision changed")
    if parent.status != "proposed":
        raise FoundationError("work_closed", f"Parent Work is {parent.status}")
    assert isinstance(parent.method, MethodRef)
    instances = _obligations(connection, request.work_id, definition)
    if request.plan.named_inputs != current.plan.named_inputs:
        raise FoundationError(
            "unsupported_plan_change", "Named Method inputs stay pinned for the whole Work"
        )
    _validate_plan(request.plan, definition, parent.activity_id)
    _validate_choice_leaves(connection, request.plan)
    for reference in request.plan.basis + parent.inputs:
        _current_artifact(
            connection,
            reference,
            actor=request.actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
    old = {child.role: child for child in current.plan.children}
    new = {child.role: child for child in request.plan.children}
    _require_mapping(request, old, new)
    nodes: dict[str, tuple[int, WorkState] | None] = {
        item.role: _require_valid_decision(connection, item, old, new, current.revision)
        for item in request.nodes
    }
    for item in request.nodes:
        fresh = item.replacement if item.decision == "replace" else item.work_id
        if (
            item.decision in ("add", "replace")
            and connection.execute(
                "SELECT 1 FROM subject_records WHERE record_id = ? UNION ALL "
                "SELECT 1 FROM records WHERE record_id = ?",
                (str(fresh), str(fresh)),
            ).fetchone()
        ):
            raise FoundationError("record_exists", f"Record already exists: {fresh}")

    next_revision = current.revision + 1
    targets: list[dict[str, object]] = [
        {"record_id": str(request.work_id), "revision": next_revision}
    ]
    closed: dict[str, int] = {}
    for item in request.nodes:
        known = nodes[item.role]
        if item.closure is None or known is None:
            continue
        closed[item.role] = _close_node(
            connection,
            request,
            item,
            old[item.role],
            known[0],
            known[1],
            now=now,
            epoch=epoch,
            authority_source=authority_source,
            grants=grants,
            decisions=decisions,
        )
        targets.append({"record_id": str(item.work_id), "revision": closed[item.role]})
        targets.extend(
            {"record_id": str(reference.artifact_id), "revision": reference.revision}
            for reference in item.closure.premises
        )
        targets.extend(
            {"record_id": str(reference.decision_id), "revision": reference.revision}
            for reference in item.closure.decision_premises
        )
    for item in request.nodes:
        if item.decision not in ("add", "replace"):
            continue
        fresh_node = new[item.role]
        _write_subject(
            connection,
            record_id=fresh_node.work_id,
            kind="work",
            parent_id=parent.activity_id,
            operation_id=request.operation_id,
            actor=request.actor,
            now=now,
            status="proposed",
            state=fresh_node.state,
            revision=1,
        )
        connection.execute(
            "INSERT INTO work_plan_members(child_id, parent_id, role, plan_revision) "
            "VALUES (?, ?, ?, ?)",
            (str(fresh_node.work_id), str(request.work_id), item.role, next_revision),
        )
        targets.append({"record_id": str(fresh_node.work_id), "revision": 1})
    connection.execute(
        "INSERT INTO work_plan_revisions(parent_id, revision, payload, operation_id, "
        "created_at, actor) VALUES (?, ?, ?, ?, ?, ?)",
        (
            str(request.work_id),
            next_revision,
            request.plan.model_dump_json().encode("utf-8"),
            str(request.operation_id),
            now,
            request.actor,
        ),
    )

    carried: set[str] = set()
    transfers: list[dict[str, object]] = []
    for item in request.nodes:
        known = nodes[item.role]
        if item.decision != "keep" or known is None:
            continue
        binding = child_binding(connection, item.work_id)
        if binding is None or binding[1] != current.revision:
            continue
        revision, state = known
        if state.status == "proposed":
            try:
                _recheck_kept(
                    connection,
                    request,
                    parent,
                    new[item.role],
                    state,
                    epoch=epoch,
                    grants=grants,
                    decisions=decisions,
                )
            except FoundationError as error:
                raise FoundationError(
                    error.code,
                    f"Kept node {_node(new[item.role])} fails its recheck in plan revision "
                    f"{next_revision}; decide it explicitly: {error.detail}",
                ) from error
            for attempt_id in _transfer_attempts(
                connection,
                request,
                new[item.role],
                parent.method,
                from_revision=current.revision,
                now=now,
            ):
                transfers.append(
                    {
                        "attempt_id": str(attempt_id),
                        "work_id": str(item.work_id),
                        "plan_revision": next_revision,
                    }
                )
                attempt_revision = connection.execute(
                    "SELECT revision FROM execution_attempts WHERE attempt_id = ?",
                    (str(attempt_id),),
                ).fetchone()[0]
                targets.append({"record_id": str(attempt_id), "revision": int(attempt_revision)})
        carried.add(item.role)
        targets.append({"record_id": str(item.work_id), "revision": revision})

    recorded: list[dict[str, object]] = []
    for item in request.nodes:
        replaced = item.work_id if item.decision == "replace" else None
        work_id = item.replacement if item.replacement is not None else item.work_id
        connection.execute(
            "INSERT INTO work_plan_nodes(parent_id, plan_revision, role, decision, work_id, "
            "replaced_work_id, issue_carried, closed_revision, operation_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(request.work_id),
                next_revision,
                item.role,
                item.decision,
                str(work_id),
                str(replaced) if replaced is not None else None,
                int(item.role in carried),
                closed.get(item.role),
                str(request.operation_id),
            ),
        )
        recorded.append(
            PlanNode(
                role=item.role,
                decision=item.decision,
                work_id=work_id,
                replaced_work_id=replaced,
                issue_carried=item.role in carried,
                closed_revision=closed.get(item.role),
            ).model_dump(mode="json")
        )

    reopened: list[str] = []
    for instance in instances:
        role = instance.definition.role
        before, after = old.get(role), new.get(role)
        if instance.status != "satisfied" or before is None:
            continue
        if after is not None and after.work_id == before.work_id:
            continue
        # The evidence belongs to a Work that no longer fills the role in this revision.
        reopened_instance = instance.model_copy(
            update={
                "revision": instance.revision + 1,
                "status": "open",
                "evidence": None,
                "basis": None,
                "operation_id": request.operation_id,
                "created_at": datetime.fromisoformat(now),
                "exception": None,
                "reopened": "node_replaced",
            }
        )
        connection.execute(
            "INSERT INTO work_obligation_revisions(parent_id, key, revision, payload, "
            "operation_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(request.work_id),
                instance.key,
                reopened_instance.revision,
                reopened_instance.model_dump_json().encode("utf-8"),
                str(request.operation_id),
                now,
            ),
        )
        reopened.append(instance.key)

    result: dict[str, object] = {
        "work_id": str(request.work_id),
        "plan_revision": next_revision,
        "nodes": recorded,
    }
    if reopened:
        result["reopened"] = reopened
    if transfers:
        result["transfers"] = transfers
    unique_targets: list[dict[str, object]] = []
    _extend(unique_targets, targets)
    return result, unique_targets


def role_history(
    connection: sqlite3.Connection, parent_id: UUID, role: str
) -> tuple[RoleFilling, ...]:
    """Every Work that filled one role, with the consecutive plan revisions it filled."""

    fillings: list[RoleFilling] = []
    maps = [
        (int(revision), revision_role_works(connection, parent_id, bytes(payload)))
        for revision, payload in connection.execute(
            "SELECT revision, payload FROM work_plan_revisions WHERE parent_id = ? "
            "ORDER BY revision",
            (str(parent_id),),
        ).fetchall()
    ]
    latest = maps[-1][0] if maps else None
    for revision, works in maps:
        work = works.get(role)
        last = fillings[-1] if fillings else None
        if work is None:
            continue
        if (
            last is not None
            and str(last.work_id) == work
            and last.last_plan_revision == revision - 1
        ):
            fillings[-1] = last.model_copy(update={"last_plan_revision": revision})
            continue
        fillings.append(
            RoleFilling(
                role=role,
                work_id=UUID(work),
                first_plan_revision=revision,
                last_plan_revision=revision,
            )
        )
    return tuple(
        item.model_copy(update={"last_plan_revision": None})
        if item.last_plan_revision == latest
        else item
        for item in fillings
    )


def read_plan_nodes(
    path: Path, parent_work_id: UUID, authority: LocalAuthority, *, revision: int | None = None
) -> PlanNodes:
    """Read the exact node decisions of one active plan revision (default: the latest)."""

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 7 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Plan node decisions need active schema 7")
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="work",
            resource_id=parent_work_id,
        )
        _parent(connection, parent_work_id)
        if revision is None:
            revision = connection.execute(
                "SELECT max(revision) FROM work_plan_revisions WHERE parent_id = ?",
                (str(parent_work_id),),
            ).fetchone()[0]
        rows = connection.execute(
            "SELECT role, decision, work_id, replaced_work_id, issue_carried, closed_revision, "
            "operation_id FROM work_plan_nodes WHERE parent_id = ? AND plan_revision = ? "
            "ORDER BY role",
            (str(parent_work_id), revision),
        ).fetchall()
        if not rows:
            raise FoundationError(
                "not_found", f"Plan revision {revision} has no recorded node decisions"
            )
        return PlanNodes(
            parent_work_id=parent_work_id,
            plan_revision=int(revision),
            operation_id=UUID(rows[0][6]),
            nodes=tuple(
                PlanNode(
                    role=row[0],
                    decision=row[1],
                    work_id=UUID(row[2]),
                    replaced_work_id=UUID(row[3]) if row[3] else None,
                    issue_carried=bool(row[4]),
                    closed_revision=row[5],
                )
                for row in rows
            ),
        )


def read_role_history(
    path: Path, parent_work_id: UUID, role: str, authority: LocalAuthority
) -> tuple[RoleFilling, ...]:
    """Read every Work that filled one role of a composite Work, across plan revisions."""

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 5 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Role history needs active schema 5")
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="work",
            resource_id=parent_work_id,
        )
        _parent(connection, parent_work_id)
        history = role_history(connection, parent_work_id, role)
        if not history:
            raise FoundationError("not_found", f"Role {role} was never filled")
        return history


__all__ = ["read_plan_nodes", "read_role_history", "revise_active_plan", "role_history"]
