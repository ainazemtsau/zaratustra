"""Exact Method versions and model-independent composite Work coordination."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from .models import (
    CLOSED_OUTCOMES,
    AcceptWorkRequest,
    AdmitInvocationRequest,
    AnswerWaitRequest,
    ArtifactRef,
    AssignAttemptRequest,
    ClaimAttemptLaunchRequest,
    CloseWorkRequest,
    ConfirmObligationRequest,
    CreateCompositeWorkRequest,
    CreateMethodVersionRequest,
    CreateResourceRequest,
    DecisionRef,
    DeleteMethodVersionRequest,
    FinishInvocationRequest,
    IssueChildWorkRequest,
    LinkWorkOutputRequest,
    MethodDefinition,
    MethodRef,
    MethodVersion,
    ObligationRevision,
    OpenWaitRequest,
    PlanCondition,
    PlanRevision,
    PrepareInvocationRequest,
    PublishAttemptOutputRequest,
    RecordAttemptStopRequest,
    RequestAttemptStopRequest,
    ReviseResourceRequest,
    ReviseWorkPlanRequest,
    SendInvocationRequest,
    SpaceInfo,
    StartAttemptRequest,
    StopAttemptRequest,
    WorkPlan,
    WorkState,
)
from .operations import (
    LocalAuthority,
    _artifact_reference,
    _authorize,
    _authorize_artifact_ref,
    _local_space,
    _subject_current,
    _subject_state,
    _write_subject,
)
from .storage import (
    CHILD_EXECUTION_SCHEMA_NAME,
    CHILD_EXECUTION_SCHEMA_SHA256,
    CHILD_EXECUTION_SCHEMA_STATEMENTS,
    COMPOSITION_SCHEMA_NAME,
    COMPOSITION_SCHEMA_SHA256,
    COMPOSITION_SCHEMA_STATEMENTS,
    PLAN_REVISION_SCHEMA_NAME,
    PLAN_REVISION_SCHEMA_SHA256,
    PLAN_REVISION_SCHEMA_STATEMENTS,
    FoundationError,
    canonical_json,
    read_space,
    space_connection,
    utc_now,
)

REDACTED_DEPENDENCY = b'{"content":"unavailable"}'
# Effects of one assigned child Attempt; each rechecks the current plan and its pin.
ATTEMPT_EFFECTS = (
    ClaimAttemptLaunchRequest,
    OpenWaitRequest,
    AnswerWaitRequest,
    PrepareInvocationRequest,
    AdmitInvocationRequest,
    SendInvocationRequest,
    PublishAttemptOutputRequest,
)
# Stopping and recording an already sent call must stay possible under a stale plan.
_ATTEMPT_OUTCOMES = (RequestAttemptStopRequest, RecordAttemptStopRequest, FinishInvocationRequest)
_RESOURCE_SETUP = (CreateResourceRequest, ReviseResourceRequest)
_INTERACTIVE_ATTEMPTS = (StartAttemptRequest, StopAttemptRequest)


class _PlanDependencies(BaseModel):
    """Content-free addresses retained when an exact plan is no longer readable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    roles: tuple[str, ...]
    edges: dict[str, tuple[str, ...]]
    global_artifacts: tuple[UUID, ...]
    role_artifacts: dict[str, tuple[UUID, ...]]

    @model_validator(mode="after")
    def valid_roles(self) -> _PlanDependencies:
        roles = set(self.roles)
        if (
            len(roles) != len(self.roles)
            or set(self.edges) != roles
            or set(self.role_artifacts) != roles
            or any(not set(dependencies).issubset(roles) for dependencies in self.edges.values())
        ):
            raise ValueError("Sanitized plan dependency roles are inconsistent")
        return self


class _SanitizedPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: Literal["unavailable"] = "unavailable"
    dependencies: _PlanDependencies | None = None


def _sanitized_plan(payload: bytes) -> _SanitizedPlan | None:
    decoded = json.loads(payload)
    if not isinstance(decoded, dict) or decoded.get("content") != "unavailable":
        return None
    try:
        return _SanitizedPlan.model_validate(decoded)
    except ValidationError as error:
        raise FoundationError("corrupt_space", "Sanitized plan index is invalid") from error


def method_checksum(definition: MethodDefinition) -> str:
    return (
        hashlib.sha256(canonical_json(definition.model_dump(mode="json")).encode("utf-8"))
        .hexdigest()
        .upper()
    )


def upgrade_composition_space(path: Path, authority: LocalAuthority) -> SpaceInfo:
    """Explicit schema 4 to 5 upgrade. Ordinary reads never upgrade a space."""

    with space_connection(path, writable=True) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active" or info.schema_version < 4:
            raise FoundationError(
                "unsupported_schema", "Composition upgrade requires active schema 4"
            )
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.backup",
            epoch=info.execution_epoch,
        )
        if info.schema_version == 4:
            for statement in COMPOSITION_SCHEMA_STATEMENTS:
                connection.execute(statement)
            now = utc_now().isoformat()
            connection.execute(
                "INSERT INTO schema_migrations(version, name, sha256, applied_at) "
                "VALUES (5, ?, ?, ?)",
                (COMPOSITION_SCHEMA_NAME, COMPOSITION_SCHEMA_SHA256, now),
            )
            connection.execute("PRAGMA user_version = 5")
            connection.execute(
                "UPDATE spaces SET state_revision = state_revision + 1 WHERE singleton = 1"
            )
            connection.execute(
                "INSERT INTO maintenance_events(event_id, kind, occurred_at, detail_json) "
                "VALUES (?, 'schema_upgrade', ?, ?)",
                (str(uuid4()), now, canonical_json({"from": 4, "to": 5})),
            )
    return read_space(path)


def upgrade_child_execution_space(path: Path, authority: LocalAuthority) -> SpaceInfo:
    """Explicit schema 5 to 6 upgrade for exact child Attempt plan pins."""

    with space_connection(path, writable=True) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active" or info.schema_version < 5:
            raise FoundationError(
                "unsupported_schema", "Child execution upgrade requires active schema 5"
            )
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.backup",
            epoch=info.execution_epoch,
        )
        if info.schema_version == 5:
            for statement in CHILD_EXECUTION_SCHEMA_STATEMENTS:
                connection.execute(statement)
            now = utc_now().isoformat()
            connection.execute(
                "INSERT INTO schema_migrations(version, name, sha256, applied_at) "
                "VALUES (6, ?, ?, ?)",
                (CHILD_EXECUTION_SCHEMA_NAME, CHILD_EXECUTION_SCHEMA_SHA256, now),
            )
            connection.execute("PRAGMA user_version = 6")
            connection.execute(
                "UPDATE spaces SET state_revision = state_revision + 1 WHERE singleton = 1"
            )
            connection.execute(
                "INSERT INTO maintenance_events(event_id, kind, occurred_at, detail_json) "
                "VALUES (?, 'schema_upgrade', ?, ?)",
                (str(uuid4()), now, canonical_json({"from": 5, "to": 6})),
            )
    return read_space(path)


def upgrade_plan_revision_space(path: Path, authority: LocalAuthority) -> SpaceInfo:
    """Explicit schema 6 to 7 upgrade; older code never meets the new Work outcomes."""

    with space_connection(path, writable=True) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active" or info.schema_version < 6:
            raise FoundationError(
                "unsupported_schema", "Plan revision upgrade requires active schema 6"
            )
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.backup",
            epoch=info.execution_epoch,
        )
        if info.schema_version == 6:
            for statement in PLAN_REVISION_SCHEMA_STATEMENTS:
                connection.execute(statement)
            now = utc_now().isoformat()
            connection.execute(
                "INSERT INTO schema_migrations(version, name, sha256, applied_at) "
                "VALUES (7, ?, ?, ?)",
                (PLAN_REVISION_SCHEMA_NAME, PLAN_REVISION_SCHEMA_SHA256, now),
            )
            connection.execute("PRAGMA user_version = 7")
            connection.execute(
                "UPDATE spaces SET state_revision = state_revision + 1 WHERE singleton = 1"
            )
            connection.execute(
                "INSERT INTO maintenance_events(event_id, kind, occurred_at, detail_json) "
                "VALUES (?, 'schema_upgrade', ?, ?)",
                (str(uuid4()), now, canonical_json({"from": 6, "to": 7})),
            )
    return read_space(path)


def _method(connection: sqlite3.Connection, ref: MethodRef) -> MethodDefinition:
    row = connection.execute(
        "SELECT checksum, status, payload FROM method_versions WHERE method_id = ? AND version = ?",
        (str(ref.method_id), ref.version),
    ).fetchone()
    if row is None or row[1] != "active" or row[2] is None:
        raise FoundationError("method_unavailable", "Exact Method version is unavailable")
    definition = MethodDefinition.model_validate_json(bytes(row[2]))
    if row[0] != ref.checksum or method_checksum(definition) != ref.checksum:
        raise FoundationError("method_mismatch", "Pinned Method definition differs")
    return definition


def _plan(
    connection: sqlite3.Connection, parent_id: UUID, revision: int | None = None
) -> PlanRevision:
    row = connection.execute(
        "SELECT revision, payload, operation_id, created_at, actor FROM work_plan_revisions "
        "WHERE parent_id = ? AND revision = COALESCE(?, "
        "(SELECT max(revision) FROM work_plan_revisions WHERE parent_id = ?))",
        (str(parent_id), revision, str(parent_id)),
    ).fetchone()
    if row is None:
        raise FoundationError("plan_unavailable", "Exact Work plan revision is unavailable")
    if _sanitized_plan(bytes(row[1])) is not None:
        raise FoundationError("content_unavailable", "Exact Work plan revision was sanitized")
    return PlanRevision(
        parent_work_id=parent_id,
        revision=row[0],
        plan=WorkPlan.model_validate_json(bytes(row[1])),
        operation_id=UUID(row[2]),
        created_at=datetime.fromisoformat(row[3]),
        actor=row[4],
    )


def _parent(
    connection: sqlite3.Connection, parent_id: UUID
) -> tuple[int, WorkState, MethodDefinition]:
    revision, status, _ = _subject_current(connection, parent_id, "work")
    if status == "deleted":
        raise FoundationError("content_unavailable", "Parent Work was deleted")
    state = WorkState.model_validate(_subject_state(connection, parent_id, revision))
    if state.method == "none":
        raise FoundationError("wrong_work", "Work has no composite Method")
    return revision, state, _method(connection, state.method)


def _method_use(
    connection: sqlite3.Connection,
    state: WorkState,
    *,
    actor: str,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> None:
    extra_grants, extra_decisions = _authorize(
        connection,
        actor=actor,
        action="method.use",
        epoch=epoch,
        resource_type="activity",
        resource_id=state.activity_id,
    )
    grants.extend(extra_grants)
    decisions.extend(extra_decisions)


def _current_artifact(
    connection: sqlite3.Connection,
    reference: ArtifactRef,
    *,
    actor: str | None,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
    media_type: str | None = None,
) -> None:
    # A missing actor asks only the structural question used by derived state reads.
    if actor is None:
        _artifact_reference(connection, reference, media_type=media_type)
    else:
        _authorize_artifact_ref(
            connection,
            reference,
            actor=actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
            media_type=media_type,
        )
    row = connection.execute(
        "SELECT current_revision, status FROM records WHERE record_id = ? AND kind = 'artifact'",
        (str(reference.artifact_id),),
    ).fetchone()
    if row is None or row[1] != "active" or row[0] != reference.revision:
        raise FoundationError("stale_basis", "Exact Artifact is not current")
    content = connection.execute(
        "SELECT payload, sha256 FROM managed_content WHERE record_id = ? AND revision = ?",
        (str(reference.artifact_id), reference.revision),
    ).fetchone()
    if content is None or hashlib.sha256(bytes(content[0])).hexdigest().upper() != content[1]:
        raise FoundationError("corrupt_space", "Exact Artifact bytes failed verification")


def _conditions(condition: PlanCondition | None) -> tuple[PlanCondition, ...]:
    if condition is None:
        return ()
    return (condition,) + tuple(
        leaf for member in condition.members for leaf in _conditions(member)
    )


def _validate_plan(plan: WorkPlan, definition: MethodDefinition, activity_id: UUID) -> None:
    roles = {child.role: child for child in plan.children}
    for child in plan.children:
        if child.state.activity_id != activity_id or child.state.method != "none":
            raise FoundationError("invalid_plan", "Child must be a plain Work in parent Activity")
        if child.state.status != "proposed" or child.state.linked_outputs:
            raise FoundationError("invalid_plan", "Child must start without a result")
        for leaf in _conditions(child.readiness):
            if leaf.role and leaf.role not in roles:
                raise FoundationError("invalid_plan", "Readiness names an absent child role")
            if leaf.role == child.role:
                raise FoundationError("dependency_cycle", "Child depends on itself")
    declared_outputs = {item.slot: item.media_type for item in definition.named_outputs}
    bindings = {item.parent_slot: item for item in plan.output_bindings}
    if set(bindings) != set(declared_outputs):
        raise FoundationError("invalid_plan", "Every parent output needs an exact child binding")
    for slot, binding in bindings.items():
        if binding.media_type != declared_outputs[slot]:
            raise FoundationError("invalid_plan", "Parent output binding has wrong type")
        source = roles.get(binding.role)
        if source is not None and not any(
            item.slot == binding.child_slot and item.media_type == binding.media_type
            for item in source.state.expected_outputs
        ):
            raise FoundationError("invalid_plan", "Bound child output slot/type differs")
    for obligation in definition.obligations:
        obligation_child = roles.get(obligation.role)
        if obligation_child is None:
            continue
        if not any(
            output.slot == obligation.slot and output.media_type == obligation.media_type
            for output in obligation_child.state.expected_outputs
        ):
            raise FoundationError("invalid_plan", "Obligation slot/type differs from child")
    edges = {
        child.role: {leaf.role for leaf in _conditions(child.readiness) if leaf.role}
        for child in plan.children
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(role: str) -> None:
        if role in visiting:
            raise FoundationError("dependency_cycle", "Plan readiness has a cycle")
        if role in visited:
            return
        visiting.add(role)
        for source in edges[role]:
            visit(source)
        visiting.remove(role)
        visited.add(role)

    for role in roles:
        visit(role)


def _require_succeeded(role: str, work_id: UUID, status: str, open_detail: str) -> None:
    """A child closed without acceptance can never satisfy its leaf under this plan."""

    if status in CLOSED_OUTCOMES:
        raise FoundationError("dependency_closed", f"Child {role} ({work_id}) is {status}")
    if status != "succeeded":
        raise FoundationError("dependency_open", open_detail)


def _accepted_output(
    connection: sqlite3.Connection,
    plan: WorkPlan,
    role: str,
    slot: str,
    media_type: str,
    *,
    actor: str | None,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> ArtifactRef:
    child = next((item for item in plan.children if item.role == role), None)
    if child is None:
        raise FoundationError("dependency_open", f"Required child role {role} has not been planned")
    current, status, _ = _subject_current(connection, child.work_id, "work")
    _require_succeeded(role, child.work_id, status, f"Child {role} is not accepted")
    state = WorkState.model_validate(_subject_state(connection, child.work_id, current))
    declared = {item.slot: item.media_type for item in state.expected_outputs}
    if declared.get(slot) != media_type:
        raise FoundationError("dependency_mismatch", "Child output slot/type differs")
    output = next((item.artifact for item in state.linked_outputs if item.slot == slot), None)
    if output is None:
        raise FoundationError("dependency_open", "Accepted child has no required output")
    if actor is not None:
        extra_grants, extra_decisions = _authorize(
            connection,
            actor=actor,
            action="record.read",
            epoch=epoch,
            resource_type="work",
            resource_id=child.work_id,
        )
        grants.extend(extra_grants)
        decisions.extend(extra_decisions)
    _current_artifact(
        connection,
        output,
        actor=actor,
        epoch=epoch,
        grants=grants,
        decisions=decisions,
        media_type=media_type,
    )
    return output


def _evaluate(
    connection: sqlite3.Connection,
    plan: WorkPlan,
    condition: PlanCondition | None,
    *,
    actor: str | None,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[ArtifactRef, ...]:
    if condition is None:
        return ()
    if condition.kind in ("all", "any"):
        references: list[ArtifactRef] = []
        errors: list[FoundationError] = []
        for member in condition.members:
            try:
                found = _evaluate(
                    connection,
                    plan,
                    member,
                    actor=actor,
                    epoch=epoch,
                    grants=grants,
                    decisions=decisions,
                )
            except FoundationError as error:
                errors.append(error)
                continue
            if condition.kind == "any":
                return found
            references.extend(found)
        closed = [error for error in errors if error.code == "dependency_closed"]
        if condition.kind == "all":
            if errors:
                # One member closed for good makes the whole conjunction unreachable.
                raise (closed or errors)[0]
            return tuple(references)
        still_open = [error for error in errors if error.code != "dependency_closed"]
        if not still_open:
            # No member can become true under this plan any more.
            raise FoundationError(
                "dependency_closed", f"No any member can become true: {errors[0].detail}"
            )
        raise FoundationError("dependency_open", f"No any member is ready: {still_open[0].detail}")
    if condition.kind == "accepted_output":
        assert condition.role and condition.slot and condition.media_type
        return (
            _accepted_output(
                connection,
                plan,
                condition.role,
                condition.slot,
                condition.media_type,
                actor=actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            ),
        )
    if condition.kind == "work_succeeded":
        assert condition.role
        child = next((item for item in plan.children if item.role == condition.role), None)
        if child is None:
            raise FoundationError("dependency_open", "Required child has not been planned")
        if actor is not None:
            extra_grants, extra_decisions = _authorize(
                connection,
                actor=actor,
                action="record.read",
                epoch=epoch,
                resource_type="work",
                resource_id=child.work_id,
            )
            grants.extend(extra_grants)
            decisions.extend(extra_decisions)
        _, status, _ = _subject_current(connection, child.work_id, "work")
        _require_succeeded(condition.role, child.work_id, status, "Required child is not accepted")
        return ()
    if condition.kind == "artifact_current":
        assert condition.artifact
        _current_artifact(
            connection,
            condition.artifact,
            actor=actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
        return (condition.artifact,)
    assert condition.kind == "decision_active"
    assert condition.decision_id and condition.decision_revision
    if actor is not None:
        extra_grants, extra_decisions = _authorize(
            connection,
            actor=actor,
            action="record.read",
            epoch=epoch,
            resource_type="space",
            resource_id=None,
        )
        grants.extend(extra_grants)
        decisions.extend(extra_decisions)
    row = connection.execute(
        "SELECT r.current_revision, v.body_json FROM records r JOIN record_revisions v "
        "ON v.record_id = r.record_id AND v.revision = r.current_revision "
        "WHERE r.record_id = ? AND r.kind = 'decision'",
        (str(condition.decision_id),),
    ).fetchone()
    if (
        row is None
        or row[0] != condition.decision_revision
        or json.loads(row[1])["status"] != "active"
    ):
        raise FoundationError("stale_basis", "Required Decision is no longer active at revision")
    return ()


def _obligations(
    connection: sqlite3.Connection,
    parent_id: UUID,
    definition: MethodDefinition,
) -> tuple[ObligationRevision, ...]:
    rows = connection.execute(
        "SELECT key, revision, payload FROM work_obligation_revisions WHERE parent_id = ? "
        "ORDER BY key, revision DESC",
        (str(parent_id),),
    ).fetchall()
    current: dict[str, ObligationRevision] = {}
    for key, _revision, payload in rows:
        if key not in current:
            if bytes(payload) == REDACTED_DEPENDENCY:
                raise FoundationError("content_unavailable", "Current obligation was sanitized")
            current[key] = ObligationRevision.model_validate_json(bytes(payload))
    expected = {item.key: item for item in definition.obligations}
    if set(current) != set(expected) or any(
        current[key].definition != item for key, item in expected.items()
    ):
        raise FoundationError(
            "incomplete_materialization", "Declared Method obligations differ from stored instances"
        )
    return tuple(current[key] for key in sorted(current))


def apply_composition_change(
    connection: sqlite3.Connection,
    request: (
        CreateMethodVersionRequest
        | DeleteMethodVersionRequest
        | CreateCompositeWorkRequest
        | ReviseWorkPlanRequest
        | IssueChildWorkRequest
        | ConfirmObligationRequest
    ),
    *,
    now: str,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if isinstance(request, CreateMethodVersionRequest):
        if connection.execute(
            "SELECT 1 FROM method_versions WHERE method_id = ? AND version = ?",
            (str(request.method_id), request.version),
        ).fetchone():
            raise FoundationError("record_exists", "Method version already exists")
        if request.version != 1:
            previous = connection.execute(
                "SELECT max(version) FROM method_versions WHERE method_id = ?",
                (str(request.method_id),),
            ).fetchone()[0]
            if previous != request.version - 1:
                raise FoundationError("stale_method", "Method versions must be consecutive")
        checksum = method_checksum(request.definition)
        connection.execute(
            "INSERT INTO method_versions(method_id, version, checksum, status, payload, "
            "operation_id, created_at, actor) VALUES (?, ?, ?, 'active', ?, ?, ?, ?)",
            (
                str(request.method_id),
                request.version,
                checksum,
                request.definition.model_dump_json().encode("utf-8"),
                str(request.operation_id),
                now,
                request.actor,
            ),
        )
        return {
            "method_id": str(request.method_id),
            "version": request.version,
            "checksum": checksum,
        }, [{"record_id": str(request.method_id), "revision": request.version}]
    if isinstance(request, DeleteMethodVersionRequest):
        ref = MethodRef(
            method_id=request.method_id, version=request.version, checksum=request.checksum
        )
        _method(connection, ref)
        for (payload,) in connection.execute(
            "SELECT c.payload FROM subject_records s JOIN subject_content c "
            "ON c.record_id = s.record_id AND c.revision = s.current_revision "
            "WHERE s.kind = 'work' AND s.status != 'deleted'"
        ).fetchall():
            if WorkState.model_validate_json(bytes(payload)).method == ref:
                raise FoundationError(
                    "method_in_use", "Delete dependent Work before Method version"
                )
        row = connection.execute(
            "SELECT operation_id FROM method_versions WHERE method_id = ? AND version = ?",
            (str(request.method_id), request.version),
        ).fetchone()
        assert row is not None
        connection.execute("DELETE FROM receipts WHERE operation_id = ?", (row[0],))
        connection.execute(
            "UPDATE operations SET fingerprint = 'DELETED' WHERE operation_id = ?", (row[0],)
        )
        connection.execute(
            "UPDATE method_versions SET status = 'deleted', payload = NULL "
            "WHERE method_id = ? AND version = ?",
            (str(request.method_id), request.version),
        )
        connection.execute(
            "INSERT INTO method_deletion_jobs(operation_id, method_id, version, "
            "status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (str(request.operation_id), str(request.method_id), request.version, now),
        )
        connection.execute(
            "UPDATE backup_inventory SET status = 'contaminated' "
            "WHERE status IN ('planned', 'failed', 'complete')"
        )
        return {
            "method_id": str(request.method_id),
            "version": request.version,
            "content": "unavailable",
        }, [{"record_id": str(request.method_id), "revision": request.version}]
    if isinstance(request, CreateCompositeWorkRequest):
        if not isinstance(request.state.method, MethodRef):
            raise FoundationError("invalid_request", "Composite Work needs an exact Method")
        definition = _method(connection, request.state.method)
        _method_use(
            connection,
            request.state,
            actor=request.actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
        if definition.required_capabilities or definition.role_methods:
            raise FoundationError(
                "unsupported_condition", "Method capabilities or role Methods are not connected"
            )
        if tuple(request.state.expected_outputs) != definition.named_outputs:
            raise FoundationError("method_mismatch", "Parent outputs differ from pinned Method")
        _validate_plan(request.plan, definition, request.state.activity_id)
        declared_inputs = {item.slot: item.media_type for item in definition.named_inputs}
        actual_inputs = {item.slot: item.artifact for item in request.plan.named_inputs}
        if set(declared_inputs) != set(actual_inputs) or set(actual_inputs.values()) != set(
            request.state.inputs
        ):
            raise FoundationError("method_mismatch", "Named Method inputs do not match Work")
        for slot, reference in actual_inputs.items():
            _current_artifact(
                connection,
                reference,
                actor=request.actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
                media_type=declared_inputs[slot],
            )
        activity_rev, status, _ = _subject_current(
            connection, request.state.activity_id, "activity"
        )
        if status != "ongoing":
            raise FoundationError("activity_not_ongoing", "Composite Work needs ongoing Activity")
        if request.work_id in {child.work_id for child in request.plan.children}:
            raise FoundationError("invalid_plan", "Parent cannot be its own child")
        for reference in request.state.inputs + request.plan.basis:
            _current_artifact(
                connection,
                reference,
                actor=request.actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            )
        _write_subject(
            connection,
            record_id=request.work_id,
            kind="work",
            parent_id=request.state.activity_id,
            operation_id=request.operation_id,
            actor=request.actor,
            now=now,
            status="proposed",
            state=request.state,
            revision=1,
        )
        targets = [
            {"record_id": str(request.work_id), "revision": 1},
            {"record_id": str(request.state.activity_id), "revision": activity_rev},
        ]
        for child in request.plan.children:
            _write_subject(
                connection,
                record_id=child.work_id,
                kind="work",
                parent_id=request.state.activity_id,
                operation_id=request.operation_id,
                actor=request.actor,
                now=now,
                status="proposed",
                state=child.state,
                revision=1,
            )
            connection.execute(
                "INSERT INTO work_plan_children(child_id, parent_id, role) VALUES (?, ?, ?)",
                (str(child.work_id), str(request.work_id), child.role),
            )
            targets.append({"record_id": str(child.work_id), "revision": 1})
        connection.execute(
            "INSERT INTO work_plan_revisions(parent_id, revision, payload, operation_id, "
            "created_at, actor) VALUES (?, 1, ?, ?, ?, ?)",
            (
                str(request.work_id),
                request.plan.model_dump_json().encode("utf-8"),
                str(request.operation_id),
                now,
                request.actor,
            ),
        )
        for obligation in definition.obligations:
            instance = ObligationRevision(
                parent_work_id=request.work_id,
                key=obligation.key,
                revision=1,
                definition=obligation,
                status="open",
                operation_id=request.operation_id,
                created_at=datetime.fromisoformat(now),
            )
            connection.execute(
                "INSERT INTO work_obligation_revisions(parent_id, key, revision, payload, "
                "operation_id, created_at) VALUES (?, ?, 1, ?, ?, ?)",
                (
                    str(request.work_id),
                    obligation.key,
                    instance.model_dump_json().encode("utf-8"),
                    str(request.operation_id),
                    now,
                ),
            )
        return {
            "work_id": str(request.work_id),
            "plan_revision": 1,
            "obligation_count": len(definition.obligations),
        }, targets
    if isinstance(request, ReviseWorkPlanRequest):
        _rev, parent, definition = _parent(connection, request.work_id)
        _method_use(
            connection,
            parent,
            actor=request.actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
        current = _plan(connection, request.work_id)
        if current.revision != request.expected_plan_revision:
            raise FoundationError("stale_plan", "Plan revision changed")
        _obligations(connection, request.work_id, definition)
        if request.plan.named_inputs != current.plan.named_inputs:
            raise FoundationError(
                "unsupported_plan_change", "Named Method inputs are pinned before execution"
            )
        if parent.status != "proposed":
            raise FoundationError("work_closed", f"Parent Work is {parent.status}")
        if parent.linked_outputs:
            raise FoundationError("plan_started", "Parent already has a linked output")
        if connection.execute(
            "SELECT 1 FROM work_plan_children WHERE parent_id = ? "
            "AND issued_plan_revision IS NOT NULL LIMIT 1",
            (str(request.work_id),),
        ).fetchone():
            raise FoundationError("plan_started", "Plan may change only before issuing any child")
        existing = {child.role: child for child in current.plan.children}
        proposed = {child.role: child for child in request.plan.children}
        if any(
            proposed.get(role) is None
            or proposed[role].work_id != child.work_id
            or proposed[role].state != child.state
            for role, child in existing.items()
        ):
            raise FoundationError(
                "unsupported_plan_change", "Existing child identity and state are pinned"
            )
        added = tuple(child for role, child in proposed.items() if role not in existing)
        _validate_plan(request.plan, definition, parent.activity_id)
        for reference in request.plan.basis:
            _current_artifact(
                connection,
                reference,
                actor=request.actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            )
        next_revision = current.revision + 1
        targets = [{"record_id": str(request.work_id), "revision": next_revision}]
        for child in added:
            _write_subject(
                connection,
                record_id=child.work_id,
                kind="work",
                parent_id=parent.activity_id,
                operation_id=request.operation_id,
                actor=request.actor,
                now=now,
                status="proposed",
                state=child.state,
                revision=1,
            )
            connection.execute(
                "INSERT INTO work_plan_children(child_id, parent_id, role) VALUES (?, ?, ?)",
                (str(child.work_id), str(request.work_id), child.role),
            )
            targets.append({"record_id": str(child.work_id), "revision": 1})
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
        return {"work_id": str(request.work_id), "plan_revision": next_revision}, targets
    if isinstance(request, IssueChildWorkRequest):
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
        _obligations(connection, request.parent_work_id, definition)
        if plan.revision != request.expected_plan_revision:
            raise FoundationError("stale_plan", "Plan revision changed")
        if parent.status != "proposed":
            raise FoundationError("work_closed", f"Parent Work is {parent.status}")
        node = next((c for c in plan.plan.children if c.work_id == request.work_id), None)
        if node is None:
            raise FoundationError("wrong_work", "Child is not in current plan")
        issued = connection.execute(
            "SELECT issued_plan_revision FROM work_plan_children "
            "WHERE child_id = ? AND parent_id = ?",
            (str(request.work_id), str(request.parent_work_id)),
        ).fetchone()
        if issued is None or issued[0] is not None:
            raise FoundationError("already_issued", "Child was already issued or is unavailable")
        child_revision, status, _ = _subject_current(connection, request.work_id, "work")
        if child_revision != request.expected_work_revision:
            raise FoundationError("stale_work", "Child Work revision changed")
        if status != "proposed":
            raise FoundationError("work_closed", f"Child Work is {status} and cannot be issued")
        for reference in plan.plan.basis + parent.inputs:
            _current_artifact(
                connection,
                reference,
                actor=request.actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            )
        refs = _evaluate(
            connection,
            plan.plan,
            node.readiness,
            actor=request.actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
        state = WorkState.model_validate(
            _subject_state(connection, request.work_id, child_revision)
        )
        inputs = tuple(dict.fromkeys(state.inputs + refs))
        for reference in inputs:
            _current_artifact(
                connection,
                reference,
                actor=request.actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            )
        _write_subject(
            connection,
            record_id=request.work_id,
            kind="work",
            parent_id=state.activity_id,
            operation_id=request.operation_id,
            actor=request.actor,
            now=now,
            status="proposed",
            state=state.model_copy(update={"inputs": inputs}),
            revision=child_revision + 1,
        )
        connection.execute(
            "UPDATE work_plan_children SET issued_plan_revision = ?, issue_operation_id = ? "
            "WHERE child_id = ?",
            (plan.revision, str(request.operation_id), str(request.work_id)),
        )
        return {
            "work_id": str(request.work_id),
            "revision": child_revision + 1,
            "plan_revision": plan.revision,
            "inputs": [r.model_dump(mode="json") for r in inputs],
        }, [
            {"record_id": str(request.work_id), "revision": child_revision + 1},
            {"record_id": str(request.parent_work_id), "revision": plan.revision},
        ]
    assert isinstance(request, ConfirmObligationRequest)
    _rev, parent, definition = _parent(connection, request.work_id)
    _method_use(
        connection,
        parent,
        actor=request.actor,
        epoch=epoch,
        grants=grants,
        decisions=decisions,
    )
    plan = _plan(connection, request.work_id)
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
    instances = {item.key: item for item in _obligations(connection, request.work_id, definition)}
    selected_instance = instances.get(request.key)
    if selected_instance is None:
        raise FoundationError("not_found", "Method does not declare this obligation")
    if (
        selected_instance.revision != request.expected_obligation_revision
        or selected_instance.status != "open"
    ):
        raise FoundationError("stale_obligation", "Obligation already changed")
    if parent.status != "proposed":
        raise FoundationError("work_closed", f"Parent Work is {parent.status}")
    actual = _accepted_output(
        connection,
        plan.plan,
        selected_instance.definition.role,
        selected_instance.definition.slot,
        selected_instance.definition.media_type,
        actor=request.actor,
        epoch=epoch,
        grants=grants,
        decisions=decisions,
    )
    if request.evidence != actual:
        raise FoundationError("evidence_mismatch", "Evidence does not name exact accepted output")
    next_instance = selected_instance.model_copy(
        update={
            "revision": selected_instance.revision + 1,
            "status": "satisfied",
            "evidence": request.evidence,
            "basis": request.basis,
            "operation_id": request.operation_id,
            "created_at": datetime.fromisoformat(now),
        }
    )
    connection.execute(
        "INSERT INTO work_obligation_revisions(parent_id, key, revision, payload, operation_id, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            str(request.work_id),
            request.key,
            next_instance.revision,
            next_instance.model_dump_json().encode("utf-8"),
            str(request.operation_id),
            now,
        ),
    )
    return {
        "work_id": str(request.work_id),
        "key": request.key,
        "revision": next_instance.revision,
        "status": "satisfied",
    }, [
        {"record_id": str(request.work_id), "revision": plan.revision},
        {"record_id": str(request.evidence.artifact_id), "revision": request.evidence.revision},
    ]


def child_binding(
    connection: sqlite3.Connection, work_id: UUID
) -> tuple[UUID, int | None, str] | None:
    """Return the parent, issued plan revision and role of one planned child Work."""

    row = connection.execute(
        "SELECT parent_id, issued_plan_revision, role FROM work_plan_children WHERE child_id = ?",
        (str(work_id),),
    ).fetchone()
    return None if row is None else (UUID(row[0]), row[1], str(row[2]))


def _pinned_plan(
    connection: sqlite3.Connection,
    attempt_id: UUID,
    work_id: UUID,
    expected: tuple[UUID, str, int, MethodRef],
) -> None:
    row = connection.execute(
        "SELECT parent_id, role, plan_revision, method_id, method_version, method_checksum "
        "FROM execution_plan_pins WHERE attempt_id = ? AND work_id = ?",
        (str(attempt_id), str(work_id)),
    ).fetchone()
    parent_id, role, plan_revision, method = expected
    current = (
        str(parent_id),
        role,
        plan_revision,
        str(method.method_id),
        method.version,
        method.checksum,
    )
    if row is None or tuple(row) != current:
        # An older generation never applies its effect or result to another plan.
        raise FoundationError(
            "stale_plan", "Attempt is not pinned to the current plan revision and Method"
        )


def check_child_plan(
    connection: sqlite3.Connection,
    work_id: UUID,
    binding: tuple[UUID, int | None, str],
    state: WorkState,
    *,
    attempt_id: UUID | None,
    actor: str | None,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[PlanRevision, MethodRef]:
    """Recheck current issue, dependencies, exact inputs and an optional Attempt pin."""

    parent_id, issued, _role = binding
    plan = _plan(connection, parent_id)
    _p_rev, parent, definition = _parent(connection, parent_id)
    assert isinstance(parent.method, MethodRef)
    if actor is not None:
        _method_use(
            connection,
            parent,
            actor=actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
    _obligations(connection, parent_id, definition)
    if issued != plan.revision or parent.status != "proposed":
        raise FoundationError("child_not_issued", "Child lacks current plan issuance")
    node = next((child for child in plan.plan.children if child.work_id == work_id), None)
    if node is None:
        raise FoundationError("child_not_issued", "Child is not in the current plan")
    for ref in plan.plan.basis + parent.inputs + state.inputs:
        _current_artifact(
            connection,
            ref,
            actor=actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
    refs = _evaluate(
        connection,
        plan.plan,
        node.readiness,
        actor=actor,
        epoch=epoch,
        grants=grants,
        decisions=decisions,
    )
    if not set(refs).issubset(state.inputs):
        raise FoundationError("stale_input", "Child is missing exact dependency input")
    if attempt_id is not None:
        _pinned_plan(
            connection, attempt_id, work_id, (parent_id, node.role, plan.revision, parent.method)
        )
    return plan, parent.method


def pin_child_attempt(
    connection: sqlite3.Connection, request: AssignAttemptRequest, now: str
) -> dict[str, object] | None:
    """Record the exact plan and Method address of a newly assigned child Attempt."""

    binding = child_binding(connection, request.work_id)
    if binding is None:
        return None
    parent_id, _issued, role = binding
    plan = _plan(connection, parent_id)
    _p_rev, parent, _definition = _parent(connection, parent_id)
    assert isinstance(parent.method, MethodRef)
    connection.execute(
        "INSERT INTO execution_plan_pins(attempt_id, work_id, parent_id, role, plan_revision, "
        "method_id, method_version, method_checksum, operation_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(request.attempt_id),
            str(request.work_id),
            str(parent_id),
            role,
            plan.revision,
            str(parent.method.method_id),
            parent.method.version,
            parent.method.checksum,
            str(request.operation_id),
            now,
        ),
    )
    return {
        "parent_work_id": str(parent_id),
        "role": role,
        "plan_revision": plan.revision,
        "method": parent.method.model_dump(mode="json"),
    }


def composite_execution_ready(
    connection: sqlite3.Connection, work_id: UUID, attempt_id: UUID, *, actor: str, epoch: int
) -> bool:
    """Control-read form of the child gate; a parent or old schema stays unconnected."""

    schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if schema < 5:
        return True
    binding = child_binding(connection, work_id)
    if binding is None:
        if connection.execute(
            "SELECT 1 FROM work_plan_revisions WHERE parent_id = ? LIMIT 1", (str(work_id),)
        ).fetchone():
            raise FoundationError(
                "unsupported_composite_execution", "Composite parent execution is not connected"
            )
        return True
    if schema < 6:
        raise FoundationError(
            "unsupported_composite_execution", "Assigned child execution needs schema 6"
        )
    try:
        revision, _status, _ = _subject_current(connection, work_id, "work")
        state = WorkState.model_validate(_subject_state(connection, work_id, revision))
        check_child_plan(
            connection,
            work_id,
            binding,
            state,
            attempt_id=attempt_id,
            actor=actor,
            epoch=epoch,
            grants=[],
            decisions=[],
        )
    except FoundationError:
        return False
    return True


def check_composite_action(
    connection: sqlite3.Connection,
    request: object,
    *,
    actor: str,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> None:
    """Shared Core gate for old paths, the direct path and assigned child Attempts."""

    work_id = getattr(request, "work_id", None)
    if not isinstance(work_id, UUID):
        return
    schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if schema < 5:
        return
    if isinstance(request, CloseWorkRequest) and schema < 7:
        raise FoundationError("unsupported_schema", "Work outcomes need explicit schema 7")
    binding = child_binding(connection, work_id)
    revision, status, _ = _subject_current(connection, work_id, "work")
    state = WorkState.model_validate(_subject_state(connection, work_id, revision))
    if binding is None and state.method == "none":
        return
    if state.status in CLOSED_OUTCOMES and not isinstance(request, _ATTEMPT_OUTCOMES):
        # Stopping and recording a sent call stay possible; nothing else changes it.
        raise FoundationError("work_closed", f"Work is closed as {state.status}")
    if isinstance(request, CloseWorkRequest):
        check_work_close(
            connection,
            work_id,
            state,
            binding,
            actor=actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
        return
    direct = isinstance(request, (LinkWorkOutputRequest, AcceptWorkRequest))
    assigned_child = (
        binding is not None and schema >= 6 and not isinstance(request, _INTERACTIVE_ATTEMPTS)
    )
    if not direct and not assigned_child:
        raise FoundationError(
            "unsupported_composite_execution",
            "Composite parent and interactive execution are not connected; "
            "an assigned child Attempt needs explicit schema 6",
        )
    if assigned_child and isinstance(request, _ATTEMPT_OUTCOMES + _RESOURCE_SETUP):
        return
    if binding is None and isinstance(request, AcceptWorkRequest):
        check_parent_acceptance(
            connection,
            work_id,
            state,
            actor=actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
        return
    if direct:
        references = tuple(item.artifact for item in state.linked_outputs)
        if isinstance(request, LinkWorkOutputRequest):
            references += (request.output.artifact,)
        for reference in references:
            _current_artifact(
                connection,
                reference,
                actor=actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            )
    if binding is not None:
        attempt_id = getattr(request, "attempt_id", None)
        check_child_plan(
            connection,
            work_id,
            binding,
            state,
            attempt_id=attempt_id
            if isinstance(request, ATTEMPT_EFFECTS) and isinstance(attempt_id, UUID)
            else None,
            actor=actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
        return
    _parent_current(
        connection, work_id, state, actor=actor, epoch=epoch, grants=grants, decisions=decisions
    )


def _parent_current(
    connection: sqlite3.Connection,
    work_id: UUID,
    state: WorkState,
    *,
    actor: str | None,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[MethodDefinition, PlanRevision]:
    """Current Method, plan, obligations and exact basis/inputs of a composite parent."""

    assert isinstance(state.method, MethodRef)
    if actor is not None:
        _method_use(
            connection,
            state,
            actor=actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
    definition = _method(connection, state.method)
    plan = _plan(connection, work_id)
    _obligations(connection, work_id, definition)
    for ref in plan.plan.basis + state.inputs:
        _current_artifact(
            connection,
            ref,
            actor=actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
    return definition, plan


def check_parent_acceptance(
    connection: sqlite3.Connection,
    work_id: UUID,
    state: WorkState,
    *,
    actor: str | None,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> None:
    """Core rules for accepting a composite parent.

    A missing actor asks only the structural question for derived state reads; the
    acceptance operation passes its actor, so its current rights are checked here and
    in the ordinary Work route.
    """

    for item in state.linked_outputs:
        _current_artifact(
            connection,
            item.artifact,
            actor=actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
    definition, plan = _parent_current(
        connection, work_id, state, actor=actor, epoch=epoch, grants=grants, decisions=decisions
    )
    instances = _obligations(connection, work_id, definition)
    for instance in instances:
        if instance.status != "satisfied" or instance.evidence is None:
            raise FoundationError("obligation_open", f"Obligation {instance.key} is open")
    linked = {item.slot: item.artifact for item in state.linked_outputs}
    for output_binding in plan.plan.output_bindings:
        actual_output = _accepted_output(
            connection,
            plan.plan,
            output_binding.role,
            output_binding.child_slot,
            output_binding.media_type,
            actor=actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
        if linked.get(output_binding.parent_slot) != actual_output:
            raise FoundationError(
                "output_mismatch", "Parent output is not exact bound child result"
            )
    _evaluate(
        connection,
        plan.plan,
        plan.plan.completion,
        actor=actor,
        epoch=epoch,
        grants=grants,
        decisions=decisions,
    )
    for instance in instances:
        actual = _accepted_output(
            connection,
            plan.plan,
            instance.definition.role,
            instance.definition.slot,
            instance.definition.media_type,
            actor=actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
        if actual != instance.evidence:
            raise FoundationError("stale_obligation", "Obligation evidence changed")


def _readable_plan(connection: sqlite3.Connection, parent_id: UUID) -> PlanRevision | None:
    """Current plan revision, or ``None`` when its content was sanitized."""

    try:
        return _plan(connection, parent_id)
    except FoundationError as error:
        if error.code != "content_unavailable":
            raise
        return None


def _extend_unique(target: list[dict[str, object]], values: list[dict[str, object]]) -> None:
    target.extend(value for value in values if value not in target)


def check_work_close(
    connection: sqlite3.Connection,
    work_id: UUID,
    state: WorkState,
    binding: tuple[UUID, int | None, str] | None,
    *,
    actor: str,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> None:
    """Shared gate of a composite Work outcome: membership, Method use and open children.

    Readiness is not required: a Work may fail, be cancelled or turn stale before it ran.
    """

    if binding is not None:
        parent_id = binding[0]
        parent_revision, _status, _ = _subject_current(connection, parent_id, "work")
        parent = WorkState.model_validate(_subject_state(connection, parent_id, parent_revision))
        _method_use(
            connection, parent, actor=actor, epoch=epoch, grants=grants, decisions=decisions
        )
        plan = _readable_plan(connection, parent_id)
        # A sanitized plan keeps its membership record; closing stays possible.
        if plan is not None and all(child.work_id != work_id for child in plan.plan.children):
            raise FoundationError("wrong_work", "Child is not in its parent's current plan")
    if isinstance(state.method, MethodRef):
        if binding is None:
            _method_use(
                connection, state, actor=actor, epoch=epoch, grants=grants, decisions=decisions
            )
        open_children = [
            f"{role}:{child_id}"
            for role, child_id in connection.execute(
                "SELECT p.role, p.child_id FROM work_plan_children p JOIN subject_records s "
                "ON s.record_id = p.child_id WHERE p.parent_id = ? AND s.status = 'proposed' "
                "ORDER BY p.role",
                (str(work_id),),
            ).fetchall()
        ]
        if open_children:
            # No cascade: every open child gets its own explicit outcome first.
            raise FoundationError(
                "open_children", "Finish or close child Works first: " + ", ".join(open_children)
            )


def _premises(
    connection: sqlite3.Connection, work_id: UUID, state: WorkState
) -> tuple[set[ArtifactRef], set[DecisionRef]]:
    """Exact premises of one Work: inputs, plan basis and exact condition leaves."""

    artifacts = set(state.inputs)
    decision_refs: set[DecisionRef] = set()

    def add_leaves(condition: PlanCondition | None) -> None:
        for leaf in _conditions(condition):
            if leaf.kind == "artifact_current" and leaf.artifact is not None:
                artifacts.add(leaf.artifact)
            elif leaf.kind == "decision_active" and leaf.decision_id and leaf.decision_revision:
                decision_refs.add(
                    DecisionRef(decision_id=leaf.decision_id, revision=leaf.decision_revision)
                )

    binding = child_binding(connection, work_id)
    if binding is not None:
        parent_id = binding[0]
        parent_revision, _status, _ = _subject_current(connection, parent_id, "work")
        parent = WorkState.model_validate(_subject_state(connection, parent_id, parent_revision))
        artifacts.update(parent.inputs)
        plan = _readable_plan(connection, parent_id)
        if plan is not None:
            artifacts.update(plan.plan.basis)
            node = next((item for item in plan.plan.children if item.work_id == work_id), None)
            if node is not None:
                add_leaves(node.readiness)
    if isinstance(state.method, MethodRef):
        own_plan = _readable_plan(connection, work_id)
        if own_plan is not None:
            artifacts.update(own_plan.plan.basis)
            add_leaves(own_plan.plan.completion)
    return artifacts, decision_refs


def _held_revision(
    connection: sqlite3.Connection, record_id: UUID, revision: int, kind: str
) -> bool:
    """Whether retained revision metadata shows this exact address as held.

    An Artifact revision held content; a Decision revision was active. Deleted content
    keeps this metadata, so the check never restores or reads the removed bytes.
    """

    row = connection.execute(
        "SELECT v.status FROM record_revisions v JOIN records r ON r.record_id = v.record_id "
        "WHERE v.record_id = ? AND v.revision = ? AND r.kind = ?",
        (str(record_id), revision, kind),
    ).fetchone()
    return row is not None and row[0] == "active"


def verify_changed_premises(
    connection: sqlite3.Connection,
    request: CloseWorkRequest,
    state: WorkState,
    *,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> None:
    """A stale outcome names only this Work's own premises that held and then changed."""

    artifacts, decision_refs = _premises(connection, request.work_id, state)
    for reference in request.premises:
        address = f"Artifact {reference.artifact_id}@{reference.revision}"
        if reference not in artifacts:
            raise FoundationError("premise_mismatch", f"{address} is not a premise of this Work")
        extra_grants, extra_decisions = _authorize(
            connection,
            actor=request.actor,
            action="record.read",
            epoch=epoch,
            resource_type="artifact",
            resource_id=reference.artifact_id,
        )
        _extend_unique(grants, extra_grants)
        _extend_unique(decisions, extra_decisions)
        if not _held_revision(connection, reference.artifact_id, reference.revision, "artifact"):
            # An address that never held content cannot have changed since.
            raise FoundationError("premise_unknown", f"{address} never held content")
        row = connection.execute(
            "SELECT current_revision, status FROM records "
            "WHERE record_id = ? AND kind = 'artifact'",
            (str(reference.artifact_id),),
        ).fetchone()
        if row is not None and row[1] == "active" and int(row[0]) == reference.revision:
            raise FoundationError("premise_current", f"{address} is still current")
    for decision in request.decision_premises:
        address = f"Decision {decision.decision_id}@{decision.revision}"
        if decision not in decision_refs:
            raise FoundationError("premise_mismatch", f"{address} is not a premise of this Work")
        extra_grants, extra_decisions = _authorize(
            connection,
            actor=request.actor,
            action="record.read",
            epoch=epoch,
            resource_type="space",
            resource_id=None,
        )
        _extend_unique(grants, extra_grants)
        _extend_unique(decisions, extra_decisions)
        if not _held_revision(connection, decision.decision_id, decision.revision, "decision"):
            raise FoundationError("premise_unknown", f"{address} was never recorded as active")
        row = connection.execute(
            "SELECT r.current_revision, v.body_json FROM records r JOIN record_revisions v "
            "ON v.record_id = r.record_id AND v.revision = r.current_revision "
            "WHERE r.record_id = ? AND r.kind = 'decision'",
            (str(decision.decision_id),),
        ).fetchone()
        if (
            row is not None
            and int(row[0]) == decision.revision
            and json.loads(row[1])["status"] == "active"
        ):
            raise FoundationError("premise_current", f"{address} is still active and current")


def prepare_work_deletion(connection: sqlite3.Connection, work_id: UUID) -> None:
    """Preserve child requirements; purge parent-owned content only with its parent."""

    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 5:
        return
    if (
        connection.execute(
            "SELECT 1 FROM work_plan_revisions WHERE parent_id = ? LIMIT 1", (str(work_id),)
        ).fetchone()
        is None
    ):
        return
    for (child_id,) in connection.execute(
        "SELECT child_id FROM work_plan_children WHERE parent_id = ?", (str(work_id),)
    ).fetchall():
        _, status, _ = _subject_current(connection, UUID(child_id), "work")
        if status != "deleted":
            raise FoundationError("dependent_work", "Delete child Works before parent")
    operation_ids = [
        row[0]
        for row in connection.execute(
            "SELECT operation_id FROM work_plan_revisions WHERE parent_id = ? "
            "UNION SELECT operation_id FROM work_obligation_revisions WHERE parent_id = ? "
            "UNION SELECT issue_operation_id FROM work_plan_children WHERE parent_id = ? "
            "AND issue_operation_id IS NOT NULL",
            (str(work_id), str(work_id), str(work_id)),
        ).fetchall()
    ]
    connection.executemany(
        "DELETE FROM receipts WHERE operation_id = ?", ((op,) for op in operation_ids)
    )
    connection.executemany(
        "UPDATE operations SET fingerprint = 'DELETED' WHERE operation_id = ?",
        ((op,) for op in operation_ids),
    )
    connection.execute("DELETE FROM work_obligation_revisions WHERE parent_id = ?", (str(work_id),))
    connection.execute("DELETE FROM work_plan_revisions WHERE parent_id = ?", (str(work_id),))
    connection.execute("DELETE FROM work_plan_children WHERE parent_id = ?", (str(work_id),))


def sanitize_deleted_dependency(
    connection: sqlite3.Connection,
    *,
    operation_id: UUID,
    now: str,
    child_id: UUID | None = None,
    artifact_id: UUID | None = None,
) -> None:
    """Remove exact plan/confirmation copies before a referenced subject disappears."""

    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 5:
        return
    if (child_id is None) == (artifact_id is None):
        raise ValueError("Exactly one deleted dependency is required")
    backup_parents: set[str] = set()
    seed_roles: dict[str, set[str]] = {}
    if child_id is not None:
        row = connection.execute(
            "SELECT parent_id, role FROM work_plan_children WHERE child_id = ?",
            (str(child_id),),
        ).fetchone()
        if row is not None:
            seed_roles.setdefault(row[0], set()).add(row[1])

    affected_operations: set[str] = set()
    current_plans: dict[str, WorkPlan | None] = {}
    current_indexes: dict[str, _PlanDependencies | None] = {}
    plan_rows = connection.execute(
        "SELECT parent_id, revision, payload, operation_id "
        "FROM work_plan_revisions ORDER BY parent_id, revision"
    ).fetchall()
    for parent_id, revision, payload, source_operation in plan_rows:
        sanitized = _sanitized_plan(bytes(payload))
        if sanitized is not None:
            current_plans[parent_id] = None
            current_indexes[parent_id] = sanitized.dependencies
            continue
        parsed_plan = WorkPlan.model_validate_json(bytes(payload))
        current_plans[parent_id] = parsed_plan
        plan = json.loads(bytes(payload))
        contains_child = child_id is not None and any(
            child["work_id"] == str(child_id) for child in plan["children"]
        )
        contains_artifact = artifact_id is not None and _contains_artifact_ref(
            plan, str(artifact_id)
        )
        if not contains_child and not contains_artifact:
            continue
        backup_parents.add(parent_id)
        affected_operations.add(source_operation)
        retained = _SanitizedPlan(
            dependencies=_plan_dependencies(connection, parent_id, parsed_plan)
        )
        connection.execute(
            "UPDATE work_plan_revisions SET payload = ? WHERE parent_id = ? AND revision = ?",
            (retained.model_dump_json().encode("utf-8"), parent_id, revision),
        )

    if artifact_id is not None:
        for parent_id, plan in current_plans.items():
            if plan is not None:
                seed_roles.setdefault(parent_id, set()).update(
                    _artifact_dependent_roles(connection, parent_id, plan, artifact_id)
                )
            elif (index := current_indexes.get(parent_id)) is not None:
                seed_roles.setdefault(parent_id, set()).update(
                    _indexed_artifact_roles(index, artifact_id)
                )
            else:
                seed_roles.setdefault(parent_id, set()).update(
                    _legacy_plan_roles(connection, parent_id)
                )

    # A confirmed basis can quote its child's work or an Artifact used by the
    # plan. Retire such confirmations without removing the Method requirement.
    obligation_rows = connection.execute(
        "SELECT parent_id, key, revision, payload, operation_id "
        "FROM work_obligation_revisions ORDER BY parent_id, key, revision"
    ).fetchall()
    if artifact_id is not None:
        for parent_id, _key, _revision, payload, _source_operation in obligation_rows:
            if bytes(payload) == REDACTED_DEPENDENCY:
                continue
            instance = ObligationRevision.model_validate_json(bytes(payload))
            if instance.evidence is not None and instance.evidence.artifact_id == artifact_id:
                seed_roles.setdefault(parent_id, set()).add(instance.definition.role)

    affected_roles: dict[str, set[str] | None] = {}
    for parent_id, roles in seed_roles.items():
        plan = current_plans.get(parent_id)
        if plan is None:
            index = current_indexes.get(parent_id)
            if index is None:
                affected_roles[parent_id] = None
                continue
            edges = index.edges
        else:
            edges = {
                child.role: tuple(
                    leaf.role for leaf in _conditions(child.readiness) if leaf.role is not None
                )
                for child in plan.children
            }
        changed = True
        while changed:
            previous = len(roles)
            roles.update(
                role
                for role, dependencies in edges.items()
                if any(dependency in roles for dependency in dependencies)
            )
            changed = len(roles) != previous
        affected_roles[parent_id] = roles
    for parent_id, key, revision, payload, source_operation in obligation_rows:
        if bytes(payload) == REDACTED_DEPENDENCY:
            continue
        instance = ObligationRevision.model_validate_json(bytes(payload))
        dependent_roles_for_key = affected_roles.get(parent_id, set())
        dependent = (
            dependent_roles_for_key is None or instance.definition.role in dependent_roles_for_key
        )
        if not dependent or (instance.evidence is None and instance.basis is None):
            continue
        backup_parents.add(parent_id)
        affected_operations.add(source_operation)
        connection.execute(
            "UPDATE work_obligation_revisions SET payload = ? "
            "WHERE parent_id = ? AND key = ? AND revision = ?",
            (REDACTED_DEPENDENCY, parent_id, key, revision),
        )
        latest = connection.execute(
            "SELECT max(revision) FROM work_obligation_revisions WHERE parent_id = ? AND key = ?",
            (parent_id, key),
        ).fetchone()[0]
        if revision == latest:
            reopened = instance.model_copy(
                update={
                    "revision": revision + 1,
                    "status": "open",
                    "evidence": None,
                    "basis": None,
                    "operation_id": operation_id,
                    "created_at": datetime.fromisoformat(now),
                }
            )
            connection.execute(
                "INSERT INTO work_obligation_revisions(parent_id, key, revision, payload, "
                "operation_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    parent_id,
                    key,
                    reopened.revision,
                    reopened.model_dump_json().encode("utf-8"),
                    str(operation_id),
                    now,
                ),
            )

    if (
        artifact_id is not None
        and int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 7
    ):
        # Closed Works are backup subjects of their own; their bases retire like confirmations.
        _retire_dependent_closure_bases(
            connection, artifact_id, affected_operations, backup_parents
        )

    connection.executemany(
        "DELETE FROM receipts WHERE operation_id = ?",
        ((source_operation,) for source_operation in affected_operations),
    )
    connection.executemany(
        "UPDATE operations SET fingerprint = 'DELETED' WHERE operation_id = ?",
        ((source_operation,) for source_operation in affected_operations),
    )
    for parent_id in backup_parents:
        connection.execute(
            "UPDATE backup_inventory SET status = 'contaminated' "
            "WHERE status IN ('planned', 'failed') OR (status = 'complete' AND backup_id IN "
            "(SELECT backup_id FROM backup_subjects WHERE record_id = ?))",
            (parent_id,),
        )


def _retire_dependent_closure_bases(
    connection: sqlite3.Connection,
    artifact_id: UUID,
    affected_operations: set[str],
    backup_subjects: set[str],
) -> None:
    """Drop the basis of every closure whose Work revision names the deleted Artifact.

    The revision's Artifact addresses (inputs, linked outputs, stale premises) are its
    dependency addresses, as for any Work state. The outcome and addresses stay; the text
    that may quote the deleted content goes, and the closing receipt leaves replay.
    """

    closed = ", ".join("?" for _ in CLOSED_OUTCOMES)
    rows = connection.execute(
        "SELECT c.record_id, c.revision, c.payload FROM subject_content c "
        "JOIN subject_revisions v ON v.record_id = c.record_id AND v.revision = c.revision "
        "JOIN subject_records s ON s.record_id = c.record_id "
        f"WHERE s.kind = 'work' AND v.status IN ({closed})",
        CLOSED_OUTCOMES,
    ).fetchall()
    for record_id, revision, payload in rows:
        state = WorkState.model_validate_json(bytes(payload))
        closure = state.closure
        if closure is None or closure.basis is None:
            continue
        if artifact_id not in _artifact_ids(json.loads(bytes(payload))):
            continue
        retained = state.model_copy(update={"closure": closure.model_copy(update={"basis": None})})
        body = canonical_json(retained.model_dump(mode="json")).encode("utf-8")
        connection.execute(
            "UPDATE subject_content SET payload = ?, sha256 = ? "
            "WHERE record_id = ? AND revision = ?",
            (body, hashlib.sha256(body).hexdigest().upper(), record_id, revision),
        )
        affected_operations.add(str(closure.operation_id))
        backup_subjects.add(record_id)


def _contains_artifact_ref(value: object, artifact_id: str) -> bool:
    if isinstance(value, dict):
        return value.get("artifact_id") == artifact_id or any(
            _contains_artifact_ref(item, artifact_id) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_artifact_ref(item, artifact_id) for item in value)
    return False


def _artifact_dependent_roles(
    connection: sqlite3.Connection, parent_id: str, plan: WorkPlan, artifact_id: UUID
) -> set[str]:
    return _indexed_artifact_roles(_plan_dependencies(connection, parent_id, plan), artifact_id)


def _artifact_ids(value: object) -> set[UUID]:
    if isinstance(value, dict):
        found = {UUID(value["artifact_id"])} if "artifact_id" in value else set()
        for member in value.values():
            found.update(_artifact_ids(member))
        return found
    if isinstance(value, list):
        return {artifact_id for member in value for artifact_id in _artifact_ids(member)}
    return set()


def _current_subject_artifacts(connection: sqlite3.Connection, subject_id: str) -> set[UUID]:
    row = connection.execute(
        "SELECT payload FROM subject_content WHERE record_id = ? AND revision = "
        "(SELECT current_revision FROM subject_records WHERE record_id = ?)",
        (subject_id, subject_id),
    ).fetchone()
    return _artifact_ids(json.loads(bytes(row[0]))) if row is not None else set()


def _plan_dependencies(
    connection: sqlite3.Connection, parent_id: str, plan: WorkPlan
) -> _PlanDependencies:
    global_artifacts = {item.artifact.artifact_id for item in plan.named_inputs}
    global_artifacts.update(reference.artifact_id for reference in plan.basis)
    if plan.completion is not None:
        global_artifacts.update(_artifact_ids(plan.completion.model_dump(mode="json")))
    global_artifacts.update(_current_subject_artifacts(connection, parent_id))
    edges: dict[str, tuple[str, ...]] = {}
    role_artifacts: dict[str, tuple[UUID, ...]] = {}
    for child in plan.children:
        edges[child.role] = tuple(
            sorted({leaf.role for leaf in _conditions(child.readiness) if leaf.role is not None})
        )
        references = _artifact_ids(child.state.model_dump(mode="json"))
        if child.readiness is not None:
            references.update(_artifact_ids(child.readiness.model_dump(mode="json")))
        references.update(_current_subject_artifacts(connection, str(child.work_id)))
        role_artifacts[child.role] = tuple(sorted(references))
    return _PlanDependencies(
        roles=tuple(child.role for child in plan.children),
        edges=edges,
        global_artifacts=tuple(sorted(global_artifacts)),
        role_artifacts=role_artifacts,
    )


def _indexed_artifact_roles(index: _PlanDependencies, artifact_id: UUID) -> set[str]:
    if artifact_id in index.global_artifacts:
        return set(index.roles)
    return {role for role, references in index.role_artifacts.items() if artifact_id in references}


def _legacy_plan_roles(connection: sqlite3.Connection, parent_id: str) -> set[str]:
    """Old redacted plans lack an index; preserve deletion safety conservatively."""

    return {
        role
        for (role,) in connection.execute(
            "SELECT role FROM work_plan_children WHERE parent_id = ?", (parent_id,)
        ).fetchall()
    }


def read_method_version(
    path: Path,
    ref: MethodRef,
    authority: LocalAuthority,
) -> MethodVersion:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 5 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Method reads require active schema 5")
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
        )
        definition = _method(connection, ref)
        row = connection.execute(
            "SELECT operation_id, created_at, actor FROM method_versions "
            "WHERE method_id = ? AND version = ?",
            (str(ref.method_id), ref.version),
        ).fetchone()
        assert row is not None
        return MethodVersion(
            reference=ref,
            definition=definition,
            operation_id=UUID(row[0]),
            created_at=datetime.fromisoformat(row[1]),
            actor=row[2],
        )


def read_work_plan(
    path: Path,
    work_id: UUID,
    authority: LocalAuthority,
    *,
    revision: int | None = None,
) -> PlanRevision:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 5 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Plan reads require active schema 5")
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="work",
            resource_id=work_id,
        )
        _parent(connection, work_id)
        return _plan(connection, work_id, revision)


def read_obligation(
    path: Path,
    work_id: UUID,
    key: str,
    authority: LocalAuthority,
    *,
    revision: int | None = None,
) -> ObligationRevision:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 5 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Obligation reads require active schema 5")
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="work",
            resource_id=work_id,
        )
        _rev, _state, definition = _parent(connection, work_id)
        _obligations(connection, work_id, definition)
        row = connection.execute(
            "SELECT payload FROM work_obligation_revisions WHERE parent_id = ? AND key = ? "
            "AND revision = COALESCE(?, (SELECT max(revision) FROM work_obligation_revisions "
            "WHERE parent_id = ? AND key = ?))",
            (str(work_id), key, revision, str(work_id), key),
        ).fetchone()
        if row is None:
            raise FoundationError("not_found", "Exact obligation revision is unavailable")
        if bytes(row[0]) == REDACTED_DEPENDENCY:
            raise FoundationError("content_unavailable", "Exact obligation revision was sanitized")
        return ObligationRevision.model_validate_json(bytes(row[0]))
