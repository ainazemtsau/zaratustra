"""Addressed exceptions: one requirement, explicit limits, never an access rule.

An exception is an ordinary Decision revision that names exactly one requirement, a
composite parent Work and one obligation key, and the exact Method versions within which
it holds. A waiver records the exact exception address in a new obligation revision. It
is not a result and opens no dependency that needs the role's output, and it holds only
while that exception revision is current and active. Everything here is read in the
caller's transaction and grants no rights.
"""

from __future__ import annotations

import sqlite3

from .models import DecisionRef, ExceptionState, MethodRef, ObligationRevision, ObligationTarget
from .operations import _decision_body
from .storage import FoundationError


def _address(reference: DecisionRef) -> str:
    return f"Decision {reference.decision_id}@{reference.revision}"


def _exception_revision(
    connection: sqlite3.Connection, reference: DecisionRef
) -> tuple[ExceptionState | None, bool]:
    """The exact revision's exception (``None`` for another variant) and whether it holds."""

    row = connection.execute(
        "SELECT v.body_json, r.current_revision FROM record_revisions v "
        "JOIN records r ON r.record_id = v.record_id "
        "WHERE v.record_id = ? AND v.revision = ? AND r.kind = 'decision'",
        (str(reference.decision_id), reference.revision),
    ).fetchone()
    if row is None:
        raise FoundationError("not_found", f"No exact revision {_address(reference)}")
    state = _decision_body(row[0])
    if not isinstance(state, ExceptionState):
        return None, False
    return state, int(row[1]) == reference.revision and state.status == "active"


def require_exception(
    connection: sqlite3.Connection,
    reference: DecisionRef,
    target: ObligationTarget,
    method: MethodRef,
) -> None:
    """Check one exact exception for this requirement under this exact Method version.

    Another Decision variant, however broad, and any Grant never replace it.
    """

    state, holds = _exception_revision(connection, reference)
    if state is None:
        raise FoundationError("exception_required", f"{_address(reference)} is not an exception")
    if state.target != target:
        raise FoundationError(
            "exception_mismatch",
            f"{_address(reference)} targets obligation {state.target.key} of Work "
            f"{state.target.work_id}",
        )
    if method not in state.methods:
        raise FoundationError(
            "exception_mismatch",
            f"{_address(reference)} does not cover Method {method.method_id} "
            f"version {method.version}",
        )
    if not holds:
        raise FoundationError(
            "stale_basis", f"{_address(reference)} is no longer current and active"
        )


def waiver_holds(
    connection: sqlite3.Connection, instance: ObligationRevision, method: MethodRef
) -> bool:
    """Whether a recorded waiver still rests on its exact exception within its limits."""

    if instance.status != "waived" or instance.exception is None:
        return False
    try:
        require_exception(
            connection,
            instance.exception,
            ObligationTarget(work_id=instance.parent_work_id, key=instance.key),
            method,
        )
    except FoundationError:
        return False
    return True


def open_for_execution(
    connection: sqlite3.Connection, instance: ObligationRevision, method: MethodRef
) -> bool:
    """An open instance, or a waived one whose exception no longer holds (``waiver_stale``).

    Only such an instance may be confirmed or waived by its next revision.
    """

    return instance.status == "open" or (
        instance.status == "waived" and not waiver_holds(connection, instance, method)
    )


__all__ = ["open_for_execution", "require_exception", "waiver_holds"]
