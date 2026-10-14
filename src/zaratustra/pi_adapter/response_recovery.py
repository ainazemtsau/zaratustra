"""Use the Core-owned completed response before admitting another model execution."""

from pathlib import Path
from uuid import UUID, uuid5

from zaratustra.foundation import (
    AttemptResponseView,
    FoundationError,
    LocalAuthority,
    RecoverAttemptOutputRequest,
    apply_operation,
    read_attempt_response,
)


def recover_response(path: Path, work_id: UUID, authority: LocalAuthority) -> AttemptResponseView:
    """Recover exact retained bytes; never infer an answer or replay an invocation."""
    view = read_attempt_response(path, work_id, authority)
    if view.outcome == "recoverable":
        if (
            view.attempt_id is None
            or view.session_id is None
            or view.invocation_id is None
            or view.assistant_source is None
            or view.slot is None
        ):
            raise FoundationError(
                "invalid_response_proof", "Recoverable response lacks an exact output address"
            )
        apply_operation(
            path,
            RecoverAttemptOutputRequest(
                operation_id=uuid5(view.invocation_id, f"recover-output:{view.slot}"),
                space_id=authority.space_id,
                actor=authority.actor,
                work_id=work_id,
                expected_work_revision=view.work_revision,
                attempt_id=view.attempt_id,
                session_id=view.session_id,
                slot=view.slot,
                assistant_source=view.assistant_source,
                invocation_id=view.invocation_id,
            ),
            authority,
        )
        view = read_attempt_response(path, work_id, authority)
    if view.outcome in ("unknown", "attention"):
        issue = view.diagnostics[0] if view.diagnostics else None
        detail = issue.message if issue is not None else "Saved response requires inspection"
        raise FoundationError(
            issue.code if issue is not None else "response_recovery_required",
            f"{detail}; Work {work_id}, Attempt {view.attempt_id}, "
            f"invocation {view.invocation_id}. No new model request was made.",
        )
    return view


def missing_executor(view: AttemptResponseView) -> FoundationError:
    """A saved running send is not authority to recreate its executor."""
    return FoundationError(
        "response_execution_unavailable",
        f"Work {view.work_id}, Attempt {view.attempt_id}, invocation {view.invocation_id} "
        "is still executing but its local executor is unavailable. Inspect the saved "
        "execution before continuing; no new model request was made.",
    )
