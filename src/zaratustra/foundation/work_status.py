"""Work lifecycle states derived from Core issue, plan, Attempt and wait records.

The state is a projection, not a second editable field: every value is computed in
the reading transaction from the same records that admit or refuse an action.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID

from .composition import (
    REDACTED_DEPENDENCY,
    _accepted_output,
    _current_artifact,
    _evaluate,
    _method,
    _parent,
    _plan,
    _sanitized_plan,
    check_child_plan,
    check_parent_acceptance,
    child_binding,
)
from .models import (
    CLOSED_OUTCOMES,
    ArtifactRef,
    ChildProgress,
    ClosedOutcome,
    CompositionView,
    MethodDefinition,
    MethodRef,
    ObligationProgress,
    ObligationRevision,
    PlanCondition,
    PlanPin,
    StatusReason,
    WorkLifecycle,
    WorkPlan,
    WorkState,
    WorkStatus,
)
from .operations import LocalAuthority, _authorize, _local_space, _subject_current, _subject_state
from .storage import FoundationError, space_connection

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
    connection: sqlite3.Connection, plan: WorkPlan, condition: PlanCondition | None
) -> list[StatusReason]:
    """Structural readiness gaps; current rights stay with the acting operation."""

    if condition is None:
        return []
    if condition.kind == "all":
        return [gap for member in condition.members for gap in _unmet(connection, plan, member)]
    if condition.kind == "any":
        gaps: list[StatusReason] = []
        possible: list[StatusReason] = []
        for member in condition.members:
            found = _unmet(connection, plan, member)
            if not found:
                return []
            gaps.extend(found)
            if all(gap.code != "dependency_closed" for gap in found):
                possible.extend(found)
        # A member that may still become true hides alternatives closed for good.
        return possible or gaps
    try:
        _evaluate(connection, plan, condition, actor=None, epoch=0, grants=[], decisions=[])
    except FoundationError as error:
        if condition.role is not None:
            child = next((item for item in plan.children if item.role == condition.role), None)
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
            )
        ]
    return []


def _condition_gaps(
    connection: sqlite3.Connection, plan: WorkPlan, condition: PlanCondition | None
) -> tuple[list[StatusReason], list[StatusReason]]:
    """Split unmet leaves into open progress and prerequisites Core refuses now."""

    if condition is None:
        return [], []
    if condition.kind in ("all", "any"):
        parts = [_condition_gaps(connection, plan, member) for member in condition.members]
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
    gaps = _unmet(connection, plan, condition)
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
    plan: WorkPlan,
    state: WorkState,
    definition: MethodDefinition,
) -> list[StatusReason]:
    """Parent prerequisites that Core acceptance refuses now, each with its address."""

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
            for item in definition.obligations
        ]
    )
    for condition in required:
        gaps.extend(_condition_gaps(connection, plan, condition)[1])
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
    dependency_gaps = artifact_gaps + _unmet(connection, plan.plan, node.readiness)
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
        return WorkStatus(work_id=work_id, status="succeeded")
    if state.status in CLOSED_OUTCOMES:
        return _closed_status(connection, work_id, state.status, schema)
    binding = child_binding(connection, work_id) if schema >= 5 else None
    if binding is None and isinstance(state.method, MethodRef):
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


def _children(connection: sqlite3.Connection, parent_id: UUID) -> tuple[ChildProgress, ...]:
    progress: list[ChildProgress] = []
    for role, child_id, issued in connection.execute(
        "SELECT role, child_id, issued_plan_revision FROM work_plan_children "
        "WHERE parent_id = ? ORDER BY role",
        (str(parent_id),),
    ).fetchall():
        child = UUID(child_id)
        try:
            status = work_status(connection, child)
        except FoundationError as error:
            status = WorkStatus(
                work_id=child,
                status="blocked",
                reasons=(StatusReason(code=error.code, role=role, record_id=child),),
            )
        progress.append(
            ChildProgress(role=role, work_id=child, issued_plan_revision=issued, status=status)
        )
    return tuple(progress)


def _obligation_progress(
    connection: sqlite3.Connection, parent_id: UUID
) -> tuple[ObligationProgress, ...]:
    latest: dict[str, ObligationProgress] = {}
    for key, _revision, payload in connection.execute(
        "SELECT key, revision, payload FROM work_obligation_revisions WHERE parent_id = ? "
        "ORDER BY key, revision DESC",
        (str(parent_id),),
    ).fetchall():
        if key in latest or bytes(payload) == REDACTED_DEPENDENCY:
            continue
        instance = ObligationRevision.model_validate_json(bytes(payload))
        latest[key] = ObligationProgress(
            key=instance.key,
            revision=instance.revision,
            role=instance.definition.role,
            status=instance.status,
            evidence=instance.evidence,
        )
    return tuple(latest[key] for key in sorted(latest))


def _branch_reviews(
    plan: WorkPlan,
    children: tuple[ChildProgress, ...],
    obligations: tuple[ObligationProgress, ...],
) -> list[StatusReason]:
    """Closed branches that the current plan or an open obligation still refers to."""

    planned = {child.role for child in plan.children}
    needed = {item.role for item in obligations if item.status == "open"}
    return [
        StatusReason(code="branch_review", role=child.role, record_id=child.work_id)
        for child in children
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
    children = _children(connection, work_id)
    obligations = _obligation_progress(connection, work_id)
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
    reviews = _branch_reviews(plan.plan, children, obligations)
    # A stale prerequisite blocks the parent under this plan whatever its children do; a
    # branch closed for good is reviewed instead (its dependents read dependency_closed).
    stale = [
        gap
        for gap in _parent_gaps(connection, plan.plan, state, definition)
        if gap.code != "dependency_closed"
    ]
    if stale:
        return WorkStatus(
            work_id=work_id, status="blocked", reasons=tuple(stale + active + reviews)
        )
    for phase, _code in phases:
        if any(child.status.status == phase for child in children):
            return WorkStatus(work_id=work_id, status=phase, reasons=tuple(active + reviews))
    declared = {item.key for item in definition.obligations}
    satisfied = {item.key for item in obligations if item.status == "satisfied"}
    refusal: str | None = None
    if satisfied == declared:
        # Acceptance is pending exactly when Core's own acceptance rules hold structurally:
        # every declared obligation (none may be declared), exact bound outputs and the
        # completion, which may need only some children (any). Other children need not
        # have succeeded. The separate acceptance operation still checks current rights.
        try:
            check_parent_acceptance(
                connection, work_id, state, actor=None, epoch=0, grants=[], decisions=[]
            )
        except FoundationError as error:
            if error.code not in ("dependency_open", "output_mismatch", "dependency_closed"):
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
                reasons=(StatusReason(code="acceptance_pending", record_id=work_id), *reviews),
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
        if item.status == "open" and item.role in succeeded
    ]
    next_steps += _pending_links(connection, plan.plan, state)
    if next_steps or reviews:
        # A failed branch makes the parent ready for review when nothing waits or runs.
        return WorkStatus(work_id=work_id, status="ready", reasons=tuple(next_steps + reviews))
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


def _work_state(connection: sqlite3.Connection, work_id: UUID) -> WorkState | None:
    revision, status, _ = _subject_current(connection, work_id, "work")
    if status == "deleted":
        return None
    return WorkState.model_validate(_subject_state(connection, work_id, revision))


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
        return CompositionView(
            parent_work_id=parent_id,
            method=parent.method,
            plan_revision=address[0],
            plan_available=address[1],
            role=role,
            issued_plan_revision=issued,
            pins=_pins(connection, work_id),
        )
    state = _work_state(connection, work_id)
    address = _plan_address(connection, work_id)
    if state is None or not isinstance(state.method, MethodRef) or address is None:
        return None
    return CompositionView(
        parent_work_id=work_id,
        method=state.method,
        plan_revision=address[0],
        plan_available=address[1],
        children=_children(connection, work_id),
        obligations=_obligation_progress(connection, work_id),
    )


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
