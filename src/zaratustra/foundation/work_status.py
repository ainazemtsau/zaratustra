"""Work lifecycle states derived from Core issue, plan, Attempt and wait records.

The state is a projection, not a second editable field: every value is computed in
the reading transaction from the same records that admit or refuse an action.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID

from .choices import choice_leaf_conflict, obligation_applicability
from .composition import (
    REDACTED_DEPENDENCY,
    _accepted_output,
    _accepted_parent_output,
    _current_artifact,
    _evaluate,
    _member_rows,
    _method,
    _parent,
    _plan,
    _require_parent_pin_current,
    _sanitized_plan,
    check_child_plan,
    check_parent_acceptance,
    child_binding,
    current_role_works,
)
from .models import (
    CLOSED_OUTCOMES,
    ArtifactRef,
    ChildProgress,
    ChoiceApplicability,
    ClosedOutcome,
    CompositionView,
    DecisionRef,
    MethodObligation,
    MethodRef,
    ObligationProgress,
    ObligationRevision,
    ParentPlanPin,
    PlanCondition,
    PlanNode,
    PlanPin,
    PlanTransfer,
    StatusReason,
    WorkLifecycle,
    WorkPlan,
    WorkState,
    WorkStatus,
)
from .operations import LocalAuthority, _authorize, _local_space, _subject_current, _subject_state
from .revalidation import premise_reasons, revalidation_in_force
from .storage import FoundationError, space_connection
from .waivers import waiver_holds

# Recorded Attempt effects that show the same Attempt continued after an answer.
_CONTINUATION_EFFECTS = (
    "prepare_invocation",
    "admit_invocation",
    "send_invocation",
    "finish_invocation",
    "publish_attempt_output",
)


def _schema(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def _unmet(
    connection: sqlite3.Connection,
    plan: WorkPlan,
    condition: PlanCondition | None,
    work_id: UUID,
) -> list[StatusReason]:
    """Structural gaps of the condition of ``work_id``; rights stay with the operation."""

    if condition is None:
        return []
    if condition.kind == "all":
        return [
            gap for member in condition.members for gap in _unmet(connection, plan, member, work_id)
        ]
    if condition.kind == "any":
        gaps: list[StatusReason] = []
        possible: list[StatusReason] = []
        for member in condition.members:
            found = _unmet(connection, plan, member, work_id)
            if not found:
                return []
            gaps.extend(found)
            if all(gap.code != "dependency_closed" for gap in found):
                possible.extend(found)
        # A member that may still become true hides alternatives closed for good.
        return possible or gaps
    try:
        _evaluate(
            connection,
            plan,
            condition,
            work_id=work_id,
            actor=None,
            epoch=0,
            grants=[],
            decisions=[],
        )
    except FoundationError as error:
        if condition.kind == "decision_value" and error.code == "decision_conflict":
            # Every choice in the formal conflict keeps its own address.
            return [
                StatusReason(
                    code=error.code,
                    record_id=reference.decision_id,
                    revision=reference.revision,
                    name=condition.name,
                )
                for reference in choice_leaf_conflict(connection, work_id, condition)
            ]
        if condition.role is not None:
            child = next((item for item in plan.children if item.role == condition.role), None)
            if error.code == "premise_changed" and child is not None:
                # Each changed premise of the accepted result keeps its held and current
                # revision.
                found = premise_reasons(connection, child.work_id, condition.role)
                if found:
                    return found
            return [
                StatusReason(
                    code=error.code,
                    role=condition.role,
                    record_id=child.work_id if child is not None else None,
                )
            ]
        if condition.artifact is not None:
            return [
                StatusReason(
                    code=error.code,
                    record_id=condition.artifact.artifact_id,
                    revision=condition.artifact.revision,
                )
            ]
        return [
            StatusReason(
                code=error.code,
                record_id=condition.decision_id,
                revision=condition.decision_revision,
                name=condition.name,
            )
        ]
    return []


def _condition_gaps(
    connection: sqlite3.Connection,
    plan: WorkPlan,
    condition: PlanCondition | None,
    work_id: UUID,
) -> tuple[list[StatusReason], list[StatusReason]]:
    """Split unmet leaves into open progress and prerequisites Core refuses now."""

    if condition is None:
        return [], []
    if condition.kind in ("all", "any"):
        parts = [_condition_gaps(connection, plan, member, work_id) for member in condition.members]
        if condition.kind == "all":
            return (
                [gap for pending, _ in parts for gap in pending],
                [gap for _, blocking in parts for gap in blocking],
            )
        if any(not pending and not blocking for pending, blocking in parts):
            return [], []
        # One member that may still become true keeps the whole alternative open.
        open_members = [pending for pending, blocking in parts if not blocking]
        if open_members:
            return [gap for pending in open_members for gap in pending], []
        return [], [gap for _, blocking in parts for gap in blocking]
    gaps = _unmet(connection, plan, condition, work_id)
    return (
        [gap for gap in gaps if gap.code == "dependency_open"],
        [gap for gap in gaps if gap.code != "dependency_open"],
    )


def _artifact_gaps(
    connection: sqlite3.Connection, references: tuple[ArtifactRef, ...]
) -> list[StatusReason]:
    """Addressed Core refusals for exact Artifacts that must still be current."""

    gaps: list[StatusReason] = []
    for reference in dict.fromkeys(references):
        try:
            _current_artifact(connection, reference, actor=None, epoch=0, grants=[], decisions=[])
        except FoundationError as error:
            gaps.append(
                StatusReason(
                    code=error.code, record_id=reference.artifact_id, revision=reference.revision
                )
            )
    return gaps


def _parent_gaps(
    connection: sqlite3.Connection,
    work_id: UUID,
    plan: WorkPlan,
    state: WorkState,
    obligations: tuple[MethodObligation, ...],
) -> list[StatusReason]:
    """Parent prerequisites that Core acceptance refuses now, each with its address.

    ``obligations`` are the declared obligations that may still need a result; a validly
    inactive one needs none.
    """

    gaps = _artifact_gaps(
        connection,
        plan.basis + state.inputs + tuple(item.artifact for item in state.linked_outputs),
    )
    required = (
        [plan.completion]
        + [
            PlanCondition(
                kind="accepted_output",
                role=item.role,
                slot=item.child_slot,
                media_type=item.media_type,
            )
            for item in plan.output_bindings
        ]
        + [
            PlanCondition(
                kind="accepted_output", role=item.role, slot=item.slot, media_type=item.media_type
            )
            for item in obligations
            if item.role is not None
        ]
    )
    for condition in required:
        gaps.extend(_condition_gaps(connection, plan, condition, work_id)[1])
    return list(dict.fromkeys(gaps))


def _pending_links(
    connection: sqlite3.Connection, plan: WorkPlan, state: WorkState
) -> list[StatusReason]:
    """Exact accepted child results that parent output slots still need to link."""

    linked = {item.slot: item.artifact for item in state.linked_outputs}
    pending: list[StatusReason] = []
    for binding in plan.output_bindings:
        try:
            actual = _accepted_output(
                connection,
                plan,
                binding.role,
                binding.child_slot,
                binding.media_type,
                actor=None,
                epoch=0,
                grants=[],
                decisions=[],
            )
        except FoundationError:
            continue
        if linked.get(binding.parent_slot) != actual:
            pending.append(
                StatusReason(
                    code="output_link_pending",
                    role=binding.role,
                    record_id=actual.artifact_id,
                    revision=actual.revision,
                )
            )
    return pending


def _input_gaps(
    connection: sqlite3.Connection, references: tuple[ArtifactRef, ...]
) -> list[StatusReason]:
    gaps: list[StatusReason] = []
    for reference in references:
        row = connection.execute(
            "SELECT current_revision, status FROM records "
            "WHERE record_id = ? AND kind = 'artifact'",
            (str(reference.artifact_id),),
        ).fetchone()
        if row is None or row[1] != "active":
            code = "content_unavailable"
        elif int(row[0]) != reference.revision:
            code = "stale_input"
        else:
            continue
        gaps.append(
            StatusReason(code=code, record_id=reference.artifact_id, revision=reference.revision)
        )
    return gaps


def _child_gaps(
    connection: sqlite3.Connection,
    work_id: UUID,
    binding: tuple[UUID, int | None, str],
    state: WorkState,
    active_attempt: UUID | None,
) -> list[StatusReason]:
    parent_id, issued, role = binding
    try:
        plan = _plan(connection, parent_id)
        _revision, parent, _definition = _parent(connection, parent_id)
    except FoundationError as error:
        return [StatusReason(code=error.code, role=role, record_id=parent_id)]
    node = next((child for child in plan.plan.children if child.work_id == work_id), None)
    if parent.status != "proposed":
        return [StatusReason(code="work_closed", record_id=parent_id)]
    if node is None:
        return [
            StatusReason(
                code="child_not_issued", role=role, record_id=parent_id, revision=plan.revision
            )
        ]
    # Core issue and every child effect require these exact Artifacts to stay current.
    artifact_gaps = _artifact_gaps(connection, plan.plan.basis + parent.inputs + state.inputs)
    dependency_gaps = artifact_gaps + _unmet(connection, plan.plan, node.readiness, work_id)
    if issued is None:
        return dependency_gaps
    try:
        check_child_plan(
            connection,
            work_id,
            binding,
            state,
            attempt_id=active_attempt,
            actor=None,
            epoch=0,
            grants=[],
            decisions=[],
        )
    except FoundationError as error:
        code = "stale_plan" if error.code == "child_not_issued" else error.code
        return dependency_gaps or [
            StatusReason(code=code, role=role, record_id=parent_id, revision=plan.revision)
        ]
    return []


def work_status(connection: sqlite3.Connection, work_id: UUID) -> WorkStatus:
    """Derive the current lifecycle of one Work inside the caller's read transaction."""

    schema = _schema(connection)
    revision, record_status, _ = _subject_current(connection, work_id, "work")
    if record_status == "deleted":
        raise FoundationError("content_unavailable", f"Work {work_id} was deleted")
    state = WorkState.model_validate(_subject_state(connection, work_id, revision))
    if state.status == "succeeded":
        return _succeeded_status(connection, work_id, state, schema)
    if state.status in CLOSED_OUTCOMES:
        return _closed_status(connection, work_id, state.status, schema)
    binding = child_binding(connection, work_id) if schema >= 5 else None
    if isinstance(state.method, MethodRef):
        if binding is not None:
            gaps = _child_gaps(connection, work_id, binding, state, None)
            if gaps:
                return WorkStatus(work_id=work_id, status="blocked", reasons=tuple(gaps))
        return _parent_status(connection, work_id, state)
    attempt_id: UUID | None = None
    active = False
    assignment: str | None = None
    if schema >= 3:
        row = connection.execute(
            "SELECT attempt_id, status FROM execution_attempts WHERE work_id = ? "
            "ORDER BY generation DESC LIMIT 1",
            (str(work_id),),
        ).fetchone()
        if row is not None:
            attempt_id, active = UUID(row[0]), row[1] == "active"
            if schema >= 4:
                found = connection.execute(
                    "SELECT status FROM execution_assignments WHERE attempt_id = ?", (row[0],)
                ).fetchone()
                assignment = None if found is None else str(found[0])
    if assignment == "unknown":
        # The external outcome is unresolved and the exclusive resource stays held.
        return WorkStatus(
            work_id=work_id,
            status="blocked",
            reasons=(StatusReason(code="outcome_unknown", record_id=attempt_id),),
            attempt_id=attempt_id,
        )
    if active and assignment == "stop_requested":
        # The Attempt still holds its resource until the stop outcome is recorded.
        return WorkStatus(
            work_id=work_id,
            status="running",
            reasons=(StatusReason(code="stop_requested", record_id=attempt_id),),
            attempt_id=attempt_id,
        )
    if binding is not None:
        gaps = _child_gaps(
            connection,
            work_id,
            binding,
            state,
            attempt_id if active and assignment is not None and schema >= 6 else None,
        )
    else:
        gaps = _input_gaps(connection, state.inputs)
    if active:
        assert attempt_id is not None
        if gaps:
            return WorkStatus(
                work_id=work_id, status="blocked", reasons=tuple(gaps), attempt_id=attempt_id
            )
        return _attempt_phase(connection, work_id, attempt_id, assignment)
    if state.linked_outputs:
        blocking = [gap for gap in gaps if binding is not None or gap.code == "content_unavailable"]
        if blocking:
            return WorkStatus(work_id=work_id, status="blocked", reasons=tuple(blocking))
        return WorkStatus(
            work_id=work_id,
            status="proposed",
            reasons=(StatusReason(code="result_proposed"),),
        )
    if gaps:
        return WorkStatus(work_id=work_id, status="blocked", reasons=tuple(gaps))
    if binding is not None and binding[1] is None:
        return WorkStatus(
            work_id=work_id,
            status="proposed",
            reasons=(StatusReason(code="issue_pending", role=binding[2], record_id=binding[0]),),
        )
    return WorkStatus(work_id=work_id, status="ready")


def _succeeded_status(
    connection: sqlite3.Connection, work_id: UUID, state: WorkState, schema: int
) -> WorkStatus:
    """An accepted result stays succeeded; its reasons name what integration must know.

    A parent accepted under exceptions keeps naming each waived requirement. A child
    result whose premise changed names each change while its parent is still open.
    """

    assert state.acceptance is not None
    reasons = [
        StatusReason(
            code="waived",
            key=item.key,
            record_id=item.exception.decision_id,
            revision=item.exception.revision,
        )
        for item in state.acceptance.waived
    ]
    binding = child_binding(connection, work_id) if schema >= 7 else None
    if (
        binding is not None
        and _subject_current(connection, binding[0], "work")[1] == "proposed"
        # A result that left the plan is no longer integrated there.
        and current_role_works(connection, binding[0]).get(binding[2]) == str(work_id)
    ):
        try:
            reasons += premise_reasons(connection, work_id, binding[2])
        except FoundationError:
            pass  # An unreadable issue plan is reported by the parent and by integration.
    return WorkStatus(work_id=work_id, status="succeeded", reasons=tuple(reasons))


def _closed_status(
    connection: sqlite3.Connection, work_id: UUID, outcome: ClosedOutcome, schema: int
) -> WorkStatus:
    """A recorded outcome plus what its last Attempt still holds; never a technical claim."""

    if schema < 4:
        return WorkStatus(work_id=work_id, status=outcome)
    row = connection.execute(
        "SELECT a.attempt_id, a.status, s.status FROM execution_attempts a "
        "LEFT JOIN execution_assignments s ON s.attempt_id = a.attempt_id "
        "WHERE a.work_id = ? ORDER BY a.generation DESC LIMIT 1",
        (str(work_id),),
    ).fetchone()
    if row is None:
        return WorkStatus(work_id=work_id, status=outcome)
    attempt_id = UUID(row[0])
    if row[1] == "active" and row[2] == "stop_requested":
        # The stop is requested; its observed outcome is not recorded yet.
        reason = StatusReason(code="stop_requested", record_id=attempt_id)
    elif row[2] == "unknown":
        # A sent call's result is unknown; the reserve and the resource stay held.
        reason = StatusReason(code="outcome_unknown", record_id=attempt_id)
    else:
        return WorkStatus(work_id=work_id, status=outcome, attempt_id=attempt_id)
    return WorkStatus(work_id=work_id, status=outcome, reasons=(reason,), attempt_id=attempt_id)


def _attempt_phase(
    connection: sqlite3.Connection, work_id: UUID, attempt_id: UUID, assignment: str | None
) -> WorkStatus:
    if assignment is None:
        # An interactive Attempt has no durable assignment; it is running while active.
        return WorkStatus(work_id=work_id, status="running", attempt_id=attempt_id)
    if assignment == "waiting":
        wait = connection.execute(
            "SELECT wait_id FROM execution_waits WHERE attempt_id = ? AND status = 'open'",
            (str(attempt_id),),
        ).fetchone()
        return WorkStatus(
            work_id=work_id,
            status="waiting",
            attempt_id=attempt_id,
            wait_id=UUID(wait[0]) if wait is not None else None,
        )
    if assignment == "assigned":
        claimed = connection.execute(
            "SELECT 1 FROM execution_events WHERE attempt_id = ? "
            "AND kind = 'claim_attempt_launch' LIMIT 1",
            (str(attempt_id),),
        ).fetchone()
        if claimed is not None:
            return WorkStatus(work_id=work_id, status="running", attempt_id=attempt_id)
        return WorkStatus(
            work_id=work_id,
            status="ready",
            reasons=(StatusReason(code="launch_pending", record_id=attempt_id),),
            attempt_id=attempt_id,
        )
    if assignment == "ready":
        answered = connection.execute(
            "SELECT max(sequence) FROM execution_events WHERE attempt_id = ? "
            "AND kind = 'answer_wait'",
            (str(attempt_id),),
        ).fetchone()[0]
        continued = connection.execute(
            "SELECT 1 FROM execution_events WHERE attempt_id = ? AND sequence > ? "
            "AND kind IN (" + ",".join("?" for _ in _CONTINUATION_EFFECTS) + ") LIMIT 1",
            (str(attempt_id), answered or 0, *_CONTINUATION_EFFECTS),
        ).fetchone()
        if continued is not None:
            return WorkStatus(work_id=work_id, status="running", attempt_id=attempt_id)
        return WorkStatus(
            work_id=work_id,
            status="ready",
            reasons=(StatusReason(code="continuation_ready", record_id=attempt_id),),
            attempt_id=attempt_id,
        )
    return WorkStatus(
        work_id=work_id,
        status="blocked",
        reasons=(StatusReason(code=f"assignment_{assignment}", record_id=attempt_id),),
        attempt_id=attempt_id,
    )


def _progress(connection: sqlite3.Connection, role: str, child: UUID) -> ChildProgress:
    try:
        status = work_status(connection, child)
    except FoundationError as error:
        status = WorkStatus(
            work_id=child,
            status="blocked",
            reasons=(StatusReason(code=error.code, role=role, record_id=child),),
        )
    binding = child_binding(connection, child)
    return ChildProgress(
        role=role,
        work_id=child,
        issued_plan_revision=None if binding is None else binding[1],
        status=status,
        revalidation=(
            revalidation_in_force(connection, child)
            if status.status == "succeeded" and _schema(connection) >= 7
            else None
        ),
    )


def _children(
    connection: sqlite3.Connection, parent_id: UUID
) -> tuple[tuple[ChildProgress, ...], tuple[ChildProgress, ...]]:
    """Nodes of the current plan revision, then Works that left the plan (role history)."""

    current = current_role_works(connection, parent_id)
    members = _member_rows(connection, str(parent_id))
    if not current:
        current = {role: child for child, role in members}
    filling = set(current.values())
    return (
        tuple(_progress(connection, role, UUID(current[role])) for role in sorted(current)),
        tuple(
            _progress(connection, role, UUID(child))
            for child, role in members
            if child not in filling
        ),
    )


def _obligation_states(
    connection: sqlite3.Connection, parent_id: UUID, method: MethodRef
) -> tuple[tuple[ObligationProgress, tuple[DecisionRef, ...]], ...]:
    """Latest instance of each obligation with derived applicability, waiver and conflict."""

    latest: dict[str, tuple[ObligationProgress, tuple[DecisionRef, ...]]] = {}
    seen: set[str] = set()
    for key, _revision, payload in connection.execute(
        "SELECT key, revision, payload FROM work_obligation_revisions WHERE parent_id = ? "
        "ORDER BY key, revision DESC",
        (str(parent_id),),
    ).fetchall():
        if key in seen:
            continue
        seen.add(key)
        if bytes(payload) == REDACTED_DEPENDENCY:
            continue
        instance = ObligationRevision.model_validate_json(bytes(payload))
        if instance.status == "retired":
            continue
        applicability, conflicting = obligation_applicability(connection, instance)
        waiver_stale = instance.status == "waived" and not waiver_holds(
            connection, instance, method
        )
        latest[key] = (
            ObligationProgress(
                key=instance.key,
                revision=instance.revision,
                role=instance.definition.role,
                applicability=applicability,
                status="waiver_stale" if waiver_stale else instance.status,
                evidence=instance.evidence,
                choice=instance.choice,
                exception=instance.exception,
                reopened=instance.reopened,
            ),
            conflicting,
        )
    return tuple(latest[key] for key in sorted(latest))


def _obligation_progress(
    connection: sqlite3.Connection, parent_id: UUID, method: MethodRef
) -> tuple[ObligationProgress, ...]:
    return tuple(progress for progress, _ in _obligation_states(connection, parent_id, method))


def _branch_reviews(
    plan: WorkPlan,
    children: tuple[ChildProgress, ...],
    obligations: tuple[ObligationProgress, ...],
    departed: tuple[ChildProgress, ...] = (),
) -> list[StatusReason]:
    """Closed branches that the current plan or an open obligation still refers to.

    A role that left the plan is still referred to by its open obligation: its last Work
    is the branch under review until a new node fills the role or a waiver takes it off.
    """

    planned = {child.role for child in plan.children}
    # A validly inactive or waived obligation needs no result from its role.
    needed = {
        item.role
        for item in obligations
        if item.status in ("open", "waiver_stale") and item.applicability != "inactive"
    }
    last_departed = {child.role: child for child in departed if child.role not in planned}
    return [
        StatusReason(code="branch_review", role=child.role, record_id=child.work_id)
        for child in children + tuple(last_departed.values())
        if child.status.status in CLOSED_OUTCOMES
        and (child.role in planned or child.role in needed)
    ]


def _parent_status(connection: sqlite3.Connection, work_id: UUID, state: WorkState) -> WorkStatus:
    assert isinstance(state.method, MethodRef)
    try:
        plan = _plan(connection, work_id)
        definition = _method(connection, state.method)
    except FoundationError as error:
        return WorkStatus(
            work_id=work_id,
            status="blocked",
            reasons=(StatusReason(code=error.code, record_id=work_id),),
        )
    children, departed = _children(connection, work_id)
    states = _obligation_states(connection, work_id, state.method)
    obligations = tuple(progress for progress, _ in states)
    applicability = {item.key: item.applicability for item in obligations}
    execution = {item.key: item.status for item in obligations}
    # A requirement taken off by an exact exception is shown, never counted as a result.
    waived = [
        StatusReason(
            code="waived",
            key=item.key,
            record_id=item.exception.decision_id,
            revision=item.exception.revision,
        )
        for item in obligations
        if item.status == "waived" and item.exception is not None
    ]
    names = {
        item.key: item.applicability.choice
        for item in definition.obligations
        if isinstance(item.applicability, ChoiceApplicability)
    }
    phases: tuple[tuple[WorkLifecycle, str], ...] = (
        ("waiting", "child_waiting"),
        ("running", "child_running"),
    )
    # Every active branch and every closed branch under review keeps its own address,
    # whatever the phase: there is no global pipeline failure and no cascade.
    active = [
        StatusReason(code=code, role=child.role, record_id=child.work_id)
        for phase, code in phases
        for child in children
        if child.status.status == phase
    ]
    own_phase: WorkStatus | None = None
    if _schema(connection) >= 8:
        own = connection.execute(
            "SELECT a.attempt_id, a.status, s.status FROM execution_attempts a "
            "LEFT JOIN execution_assignments s ON s.attempt_id = a.attempt_id "
            "WHERE a.work_id = ? ORDER BY a.generation DESC LIMIT 1",
            (str(work_id),),
        ).fetchone()
        if own is not None:
            own_id = UUID(own[0])
            if own[2] == "unknown":
                own_phase = WorkStatus(
                    work_id=work_id,
                    status="blocked",
                    attempt_id=own_id,
                    reasons=(StatusReason(code="outcome_unknown", record_id=own_id),),
                )
            elif own[1] == "active" and own[2] == "stop_requested":
                own_phase = WorkStatus(
                    work_id=work_id,
                    status="running",
                    attempt_id=own_id,
                    reasons=(StatusReason(code="stop_requested", record_id=own_id),),
                )
            elif own[1] == "active":
                try:
                    _require_parent_pin_current(connection, own_id, work_id)
                except FoundationError as error:
                    own_phase = WorkStatus(
                        work_id=work_id,
                        status="blocked",
                        attempt_id=own_id,
                        reasons=(StatusReason(code=error.code, record_id=own_id),),
                    )
                else:
                    own_phase = _attempt_phase(connection, work_id, own_id, own[2])
    if own_phase is not None and own_phase.status in ("waiting", "running"):
        active.append(
            StatusReason(code=f"parent_{own_phase.status}", record_id=own_phase.attempt_id)
        )
    reviews = _branch_reviews(plan.plan, children, obligations, departed)
    # A formal conflict of applicable choices names every address; it is settled only
    # by revising or revoking a choice, never by scope or time.
    conflicts = [
        StatusReason(
            code="decision_conflict",
            key=progress.key,
            name=names.get(progress.key),
            record_id=reference.decision_id,
            revision=reference.revision,
        )
        for progress, conflicting in states
        for reference in conflicting
    ]
    # A stale prerequisite blocks the parent under this plan whatever its children do; a
    # branch closed for good is reviewed instead (its dependents read dependency_closed).
    stale = [
        gap
        for gap in _parent_gaps(
            connection,
            work_id,
            plan.plan,
            state,
            tuple(
                item
                for item in definition.obligations
                if applicability.get(item.key) != "inactive" and execution.get(item.key) != "waived"
            ),
        )
        if gap.code != "dependency_closed"
    ] + conflicts
    if own_phase is not None and own_phase.status == "blocked":
        stale.extend(own_phase.reasons)
    if stale:
        return WorkStatus(
            work_id=work_id,
            status="blocked",
            reasons=tuple(stale + active + reviews),
            attempt_id=own_phase.attempt_id if own_phase is not None else None,
        )
    if own_phase is not None and own_phase.status == "waiting":
        return WorkStatus(
            work_id=work_id,
            status="waiting",
            reasons=tuple(active + reviews),
            attempt_id=own_phase.attempt_id,
            wait_id=own_phase.wait_id,
        )
    for phase, _code in phases:
        if any(child.status.status == phase for child in children):
            return WorkStatus(work_id=work_id, status=phase, reasons=tuple(active + reviews))
    if own_phase is not None and own_phase.status == "running":
        return WorkStatus(
            work_id=work_id,
            status="running",
            reasons=tuple(active + reviews),
            attempt_id=own_phase.attempt_id,
        )
    declared = {item.key for item in definition.obligations}
    settled = {
        item.key
        for item in obligations
        if item.applicability == "inactive"
        or (item.applicability == "active" and item.status in ("satisfied", "waived"))
    }
    refusal: str | None = None
    if settled == declared:
        # Acceptance is pending exactly when Core's own acceptance rules hold structurally:
        # every declared obligation (none may be declared) is satisfied, validly waived or
        # validly inactive, exact bound outputs and the completion, which may need only some
        # children (any). Other children need not have succeeded. The separate acceptance
        # operation still checks current rights.
        try:
            check_parent_acceptance(
                connection, work_id, state, actor=None, epoch=0, grants=[], decisions=[]
            )
        except FoundationError as error:
            if error.code not in (
                "dependency_open",
                "output_mismatch",
                "dependency_closed",
                "stale_plan",
            ):
                return WorkStatus(
                    work_id=work_id,
                    status="blocked",
                    reasons=(StatusReason(code=error.code, record_id=work_id), *reviews),
                )
            refusal = error.code
        else:
            return WorkStatus(
                work_id=work_id,
                status="ready",
                reasons=(
                    StatusReason(code="acceptance_pending", record_id=work_id),
                    *waived,
                    *reviews,
                ),
            )
    succeeded = {child.role for child in children if child.status.status == "succeeded"}
    next_steps = [
        StatusReason(
            code="child_ready" if child.status.status == "ready" else child.status.reasons[0].code,
            role=child.role,
            record_id=child.work_id,
        )
        for child in children
        if child.status.status == "ready"
        or (child.status.status == "proposed" and child.status.reasons)
    ] + [
        StatusReason(code="confirmation_pending", role=item.role, record_id=work_id)
        for item in obligations
        if item.applicability == "active"
        and item.status in ("open", "waiver_stale")
        and (
            item.role in succeeded
            or (
                item.role is None
                and any(
                    output.slot == need.slot
                    for output in state.linked_outputs
                    for need in definition.obligations
                    if need.key == item.key
                )
            )
        )
    ]
    if own_phase is not None and own_phase.status == "ready":
        next_steps.append(StatusReason(code="parent_attempt_ready", record_id=own_phase.attempt_id))
    for output in plan.plan.parent_outputs:
        try:
            _accepted_parent_output(
                connection,
                work_id,
                state,
                plan.plan,
                output.slot,
                output.media_type,
                actor=None,
                epoch=0,
                grants=[],
                decisions=[],
            )
        except FoundationError:
            next_steps.append(StatusReason(code="parent_output_pending", record_id=work_id))
    # A waiver whose exact exception no longer holds needs a result or a new exception.
    for item in obligations:
        if item.status == "waiver_stale":
            assert item.exception is not None
            next_steps.append(
                StatusReason(
                    code="waiver_stale",
                    key=item.key,
                    record_id=item.exception.decision_id,
                    revision=item.exception.revision,
                )
            )
    # Resolving applicability is the next step of an unresolved or stale obligation.
    for item in obligations:
        if item.applicability == "unresolved":
            next_steps.append(
                StatusReason(
                    code="applicability_pending",
                    key=item.key,
                    name=names.get(item.key),
                    record_id=work_id,
                )
            )
        elif item.applicability == "applicability_stale":
            assert item.choice is not None
            next_steps.append(
                StatusReason(
                    code="applicability_stale",
                    key=item.key,
                    name=names.get(item.key),
                    record_id=item.choice.decision_id,
                    revision=item.choice.revision,
                )
            )
    next_steps += _pending_links(connection, plan.plan, state)
    if next_steps or reviews:
        # A failed branch makes the parent ready for review when nothing waits or runs.
        return WorkStatus(
            work_id=work_id,
            status="ready",
            reasons=tuple(next_steps + reviews),
            attempt_id=(own_phase.attempt_id if own_phase is not None else None),
        )
    return WorkStatus(
        work_id=work_id,
        status="blocked",
        reasons=tuple(
            StatusReason(code="child_blocked", role=child.role, record_id=child.work_id)
            for child in children
            if child.status.status == "blocked"
        )
        or (StatusReason(code=refusal or "obligation_open", record_id=work_id),),
    )


def _plan_address(connection: sqlite3.Connection, parent_id: UUID) -> tuple[int, bool] | None:
    row = connection.execute(
        "SELECT revision, payload FROM work_plan_revisions WHERE parent_id = ? "
        "ORDER BY revision DESC LIMIT 1",
        (str(parent_id),),
    ).fetchone()
    if row is None:
        return None
    return int(row[0]), _sanitized_plan(bytes(row[1])) is None


def _pins(connection: sqlite3.Connection, work_id: UUID) -> tuple[PlanPin, ...]:
    if _schema(connection) < 6:
        return ()
    return tuple(
        PlanPin(
            attempt_id=UUID(row[0]),
            work_id=work_id,
            parent_work_id=UUID(row[1]),
            role=row[2],
            plan_revision=row[3],
            method=MethodRef(method_id=UUID(row[4]), version=row[5], checksum=row[6]),
        )
        for row in connection.execute(
            "SELECT attempt_id, parent_id, role, plan_revision, method_id, method_version, "
            "method_checksum FROM execution_plan_pins WHERE work_id = ? "
            "ORDER BY created_at, attempt_id",
            (str(work_id),),
        ).fetchall()
    )


def _own_pins(connection: sqlite3.Connection, work_id: UUID) -> tuple[ParentPlanPin, ...]:
    if _schema(connection) < 8:
        return ()
    return tuple(
        ParentPlanPin(
            attempt_id=UUID(row[0]),
            work_id=work_id,
            plan_revision=int(row[1]),
            method=MethodRef(method_id=UUID(row[2]), version=int(row[3]), checksum=row[4]),
            operation_id=UUID(row[5]),
        )
        for row in connection.execute(
            "SELECT attempt_id, plan_revision, method_id, method_version, method_checksum, "
            "operation_id FROM execution_parent_pins WHERE work_id = ? "
            "ORDER BY created_at, attempt_id",
            (str(work_id),),
        ).fetchall()
    )


def _transfers(connection: sqlite3.Connection, work_id: UUID) -> tuple[PlanTransfer, ...]:
    if _schema(connection) < 7:
        return ()
    return tuple(
        PlanTransfer(
            attempt_id=UUID(row[0]),
            work_id=work_id,
            parent_work_id=UUID(row[1]),
            role=row[2],
            from_plan_revision=row[3],
            plan_revision=row[4],
            method=MethodRef(method_id=UUID(row[5]), version=row[6], checksum=row[7]),
            operation_id=UUID(row[8]),
        )
        for row in connection.execute(
            "SELECT attempt_id, parent_id, role, from_plan_revision, plan_revision, method_id, "
            "method_version, method_checksum, operation_id FROM execution_plan_transfers "
            "WHERE work_id = ? ORDER BY plan_revision, attempt_id",
            (str(work_id),),
        ).fetchall()
    )


def _work_state(connection: sqlite3.Connection, work_id: UUID) -> WorkState | None:
    revision, status, _ = _subject_current(connection, work_id, "work")
    if status == "deleted":
        return None
    return WorkState.model_validate(_subject_state(connection, work_id, revision))


def _plan_nodes(
    connection: sqlite3.Connection, parent_id: UUID, revision: int
) -> tuple[PlanNode, ...]:
    if _schema(connection) < 7 or revision < 2:
        return ()
    return tuple(
        PlanNode(
            role=row[0],
            decision=row[1],
            work_id=UUID(row[2]),
            replaced_work_id=UUID(row[3]) if row[3] else None,
            issue_carried=bool(row[4]),
            closed_revision=row[5],
        )
        for row in connection.execute(
            "SELECT role, decision, work_id, replaced_work_id, issue_carried, closed_revision "
            "FROM work_plan_nodes WHERE parent_id = ? AND plan_revision = ? ORDER BY role",
            (str(parent_id), revision),
        ).fetchall()
    )


def _own_composition(
    connection: sqlite3.Connection, work_id: UUID, state: WorkState
) -> CompositionView | None:
    address = _plan_address(connection, work_id)
    if not isinstance(state.method, MethodRef) or address is None:
        return None
    children, departed = _children(connection, work_id)
    return CompositionView(
        parent_work_id=work_id,
        method=state.method,
        plan_revision=address[0],
        plan_available=address[1],
        own_pins=_own_pins(connection, work_id),
        children=children,
        obligations=_obligation_progress(connection, work_id, state.method),
        departed=departed,
        nodes=_plan_nodes(connection, work_id, address[0]),
    )


def composition_view(connection: sqlite3.Connection, work_id: UUID) -> CompositionView | None:
    """Addresses and derived states of a composite parent or one of its children."""

    if _schema(connection) < 5:
        return None
    binding = child_binding(connection, work_id)
    if binding is not None:
        parent_id, issued, role = binding
        parent = _work_state(connection, parent_id)
        address = _plan_address(connection, parent_id)
        if parent is None or not isinstance(parent.method, MethodRef) or address is None:
            return None
        own_state = _work_state(connection, work_id)
        return CompositionView(
            parent_work_id=parent_id,
            method=parent.method,
            plan_revision=address[0],
            plan_available=address[1],
            role=role,
            issued_plan_revision=issued,
            pins=_pins(connection, work_id),
            transfers=_transfers(connection, work_id),
            obligations=_obligation_progress(connection, parent_id, parent.method),
            nodes=_plan_nodes(connection, parent_id, address[0]),
            nested=(
                _own_composition(connection, work_id, own_state) if own_state is not None else None
            ),
        )
    state = _work_state(connection, work_id)
    return None if state is None else _own_composition(connection, work_id, state)


def read_work_status(path: Path, work_id: UUID, authority: LocalAuthority) -> WorkStatus:
    """Read one derived Work state with current read authority."""

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 2 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Work status needs an active schema 2")
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="work",
            resource_id=work_id,
        )
        return work_status(connection, work_id)


__all__ = ["composition_view", "read_work_status", "work_status"]
