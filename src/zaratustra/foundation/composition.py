"""Exact Method versions and model-independent composite Work coordination."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal, NamedTuple
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .choices import (
    check_choice_leaf,
    choice_holds,
    obligation_applicability,
    require_applicable,
    require_consistent_resolutions,
    resolve_applicability,
    validate_choice_leaf,
)
from .models import (
    CLOSED_OUTCOMES,
    AcceptWorkRequest,
    AdmitInvocationRequest,
    AnswerWaitRequest,
    ArtifactRef,
    AssignAttemptRequest,
    ChoiceApplicability,
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
    ObligationTarget,
    OpenWaitRequest,
    ParentOutputProof,
    ParentPlanPin,
    ParentResultEvidence,
    PlanCondition,
    PlanRevision,
    PrepareInvocationRequest,
    PublishAttemptOutputRequest,
    RecordAttemptStopRequest,
    RequestAttemptStopRequest,
    ResolveObligationApplicabilityRequest,
    RevalidateResultRequest,
    ReviseResourceRequest,
    ReviseWorkPlanRequest,
    SendInvocationRequest,
    SpaceInfo,
    StartAttemptRequest,
    StopAttemptRequest,
    WaivedObligation,
    WaiveObligationRequest,
    WorkPlan,
    WorkState,
)
from .operations import (
    LocalAuthority,
    _artifact_reference,
    _authorize,
    _authorize_artifact_ref,
    _hold_work_execution,
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
    PARENT_EXECUTION_SCHEMA_NAME,
    PARENT_EXECUTION_SCHEMA_SHA256,
    PARENT_EXECUTION_SCHEMA_STATEMENTS,
    PLAN_REVISION_SCHEMA_NAME,
    PLAN_REVISION_SCHEMA_SHA256,
    PLAN_REVISION_SCHEMA_STATEMENTS,
    FoundationError,
    canonical_json,
    read_space,
    space_connection,
    utc_now,
)
from .waivers import open_for_execution, require_exception, waiver_holds

REDACTED_DEPENDENCY = b'{"content":"unavailable"}'
REDACTED_METHOD_SOURCE = "[content unavailable: deleted Method version]"
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
# Refusals no progress lifts, in the order a composite condition names them.
_BLOCKING_CODES = ("decision_conflict", "premise_changed")


class _PlanDependencies(BaseModel):
    """Content-free addresses retained when an exact plan is no longer readable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    roles: tuple[str, ...]
    edges: dict[str, tuple[str, ...]]
    global_artifacts: tuple[UUID, ...]
    role_artifacts: dict[str, tuple[UUID, ...]]
    # Schema 7: the Work filling each role in this revision (role history). Absent from
    # earlier indexes, where every role had its one original member.
    role_works: dict[str, UUID] | None = Field(default=None, exclude_if=lambda value: value is None)
    # A descendant with a pre-index redacted plan has unknown Artifact addresses.
    # Keep that uncertainty with its exact role across later deletions and restarts.
    unbounded_roles: tuple[str, ...] = Field(default=(), exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def valid_roles(self) -> _PlanDependencies:
        roles = set(self.roles)
        if (
            len(roles) != len(self.roles)
            or set(self.edges) != roles
            or set(self.role_artifacts) != roles
            or (self.role_works is not None and set(self.role_works) != roles)
            or not set(self.unbounded_roles).issubset(roles)
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
            # Before schema 7, a Work cannot change Method. Bind each existing plan
            # revision to that exact version so later transitions have complete history.
            for parent_id, plan_revision, source_operation in connection.execute(
                "SELECT parent_id, revision, operation_id FROM work_plan_revisions"
            ).fetchall():
                current, _status, _ = _subject_current(connection, UUID(parent_id), "work")
                state = WorkState.model_validate(
                    _subject_state(connection, UUID(parent_id), current)
                )
                assert isinstance(state.method, MethodRef)
                _record_plan_method(
                    connection,
                    UUID(parent_id),
                    int(plan_revision),
                    state.method,
                    UUID(source_operation),
                )
            now = utc_now().isoformat()
            connection.execute(
                "INSERT INTO schema_migrations(version, name, sha256, applied_at) "
                "VALUES (7, ?, ?, ?)",
                (PLAN_REVISION_SCHEMA_NAME, PLAN_REVISION_SCHEMA_SHA256, now),
            )
            connection.execute("PRAGMA user_version = 7")
            retired = retire_bases_of_deleted_dependencies(connection)
            if retired:
                # Finishing earlier deletions is a deletion effect, not only a schema step.
                _authorize(
                    connection,
                    actor=authority.actor,
                    action="maintenance.delete",
                    epoch=info.execution_epoch,
                )
            connection.execute(
                "UPDATE spaces SET state_revision = state_revision + 1 WHERE singleton = 1"
            )
            connection.execute(
                "INSERT INTO maintenance_events(event_id, kind, occurred_at, detail_json) "
                "VALUES (?, 'schema_upgrade', ?, ?)",
                (
                    str(uuid4()),
                    now,
                    canonical_json({"from": 6, "to": 7, "retired_outcome_bases": retired}),
                ),
            )
    return read_space(path)


def upgrade_parent_execution_space(path: Path, authority: LocalAuthority) -> SpaceInfo:
    """Explicit additive schema 7 to 8 upgrade; reads never upgrade a space."""

    with space_connection(path, writable=True) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active" or info.schema_version < 7:
            raise FoundationError(
                "unsupported_schema", "Parent execution upgrade requires active schema 7"
            )
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.backup",
            epoch=info.execution_epoch,
        )
        if info.schema_version == 7:
            for statement in PARENT_EXECUTION_SCHEMA_STATEMENTS:
                connection.execute(statement)
            now = utc_now().isoformat()
            connection.execute(
                "INSERT INTO schema_migrations(version, name, sha256, applied_at) "
                "VALUES (8, ?, ?, ?)",
                (PARENT_EXECUTION_SCHEMA_NAME, PARENT_EXECUTION_SCHEMA_SHA256, now),
            )
            connection.execute("PRAGMA user_version = 8")
            connection.execute(
                "UPDATE spaces SET state_revision = state_revision + 1 WHERE singleton = 1"
            )
            connection.execute(
                "INSERT INTO maintenance_events(event_id, kind, occurred_at, detail_json) "
                "VALUES (?, 'schema_upgrade', ?, ?)",
                (str(uuid4()), now, canonical_json({"from": 7, "to": 8})),
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


def _record_plan_method(
    connection: sqlite3.Connection,
    parent_id: UUID,
    plan_revision: int,
    method: MethodRef,
    operation_id: UUID,
) -> None:
    connection.execute(
        "INSERT INTO work_plan_methods(parent_id, plan_revision, method_id, "
        "method_version, method_checksum, operation_id) VALUES (?, ?, ?, ?, ?, ?)",
        (
            str(parent_id),
            plan_revision,
            str(method.method_id),
            method.version,
            method.checksum,
            str(operation_id),
        ),
    )


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


def _schema(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def _validate_choice_leaves(connection: sqlite3.Connection, plan: WorkPlan) -> None:
    """decision_value leaves are a schema 7 payload and name an exact existing choice."""

    leaves = [
        leaf
        for condition in [child.readiness for child in plan.children] + [plan.completion]
        for leaf in _conditions(condition)
        if leaf.kind == "decision_value"
    ]
    if leaves and _schema(connection) < 7:
        raise FoundationError("unsupported_schema", "decision_value conditions need schema 7")
    for leaf in leaves:
        validate_choice_leaf(connection, leaf)


def _validate_plan(
    plan: WorkPlan,
    definition: MethodDefinition,
    activity_id: UUID,
    *,
    schema: int,
    allow_nested: bool = False,
) -> None:
    if schema < 8 and (
        plan.parent_outputs or any(item.role is None for item in definition.obligations)
    ):
        raise FoundationError("unsupported_schema", "Own parent results need explicit schema 8")
    roles = {child.role: child for child in plan.children}
    declared_methods = dict(definition.role_methods)
    for child in plan.children:
        if child.state.activity_id != activity_id or (
            not allow_nested and child.state.method != "none"
        ):
            raise FoundationError("invalid_plan", "Child must be a plain Work in parent Activity")
        if child.role in declared_methods and (child.state.method != declared_methods[child.role]):
            raise FoundationError("method_mismatch", f"Role {child.role} pins another Method")
        if child.state.status != "proposed" or child.state.linked_outputs:
            raise FoundationError("invalid_plan", "Child must start without a result")
        for leaf in _conditions(child.readiness):
            if leaf.role and leaf.role not in roles:
                raise FoundationError("invalid_plan", "Readiness names an absent child role")
            if leaf.role == child.role:
                raise FoundationError("dependency_cycle", "Child depends on itself")
    declared_outputs = {item.slot: item.media_type for item in definition.named_outputs}
    bindings = {item.parent_slot: item for item in plan.output_bindings}
    own_outputs = {item.slot: item.media_type for item in plan.parent_outputs}
    if set(bindings) | set(own_outputs) != set(declared_outputs):
        raise FoundationError("invalid_plan", "Every parent output needs one exact producer")
    if any(own_outputs[slot] != declared_outputs[slot] for slot in own_outputs):
        raise FoundationError("invalid_plan", "Parent-produced output has wrong type")
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
        if obligation.role is None:
            if own_outputs.get(obligation.slot) != obligation.media_type:
                raise FoundationError(
                    "invalid_plan", "Roleless obligation needs a parent-produced output"
                )
            continue
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


def _require_open_branch(
    connection: sqlite3.Connection, plan: WorkPlan, role: str, need: str
) -> None:
    """Integration that needs a branch closed without acceptance refuses for good.

    Only this branch is refused; independent branches go on and nothing is cancelled.
    """

    child = next((item for item in plan.children if item.role == role), None)
    if child is None:
        return
    _, status, _ = _subject_current(connection, child.work_id, "work")
    if status in CLOSED_OUTCOMES:
        raise FoundationError(
            "dependency_closed", f"{need} needs child {role} ({child.work_id}), which is {status}"
        )


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
    if _schema(connection) >= 7:
        from .revalidation import require_current_result

        # The result integrates only while its own premises hold or are rechecked.
        require_current_result(connection, child.work_id, state, role)
    return output


def _evaluate(
    connection: sqlite3.Connection,
    plan: WorkPlan,
    condition: PlanCondition | None,
    *,
    work_id: UUID,
    actor: str | None,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[ArtifactRef, ...]:
    """Evaluate the readiness or completion condition of ``work_id`` under ``plan``."""

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
                    work_id=work_id,
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
        if not errors:
            return tuple(references)
        closed = [error for error in errors if error.code == "dependency_closed"]
        # A formal conflict and a changed premise of an accepted result are lifted only by
        # an explicit act (a revised or revoked choice, a recheck), never by progress: each
        # keeps its code and every address through each enclosing condition, the conflict
        # first.
        blocking = [
            FoundationError(code, "; ".join(dict.fromkeys(error.detail for error in matching)))
            for code in _BLOCKING_CODES
            if (matching := [error for error in errors if error.code == code])
        ]
        if condition.kind == "all":
            if closed:
                # One member closed for good makes the whole conjunction unreachable.
                raise closed[0]
            raise blocking[0] if blocking else errors[0]
        still_open = [
            error
            for error in errors
            if error.code != "dependency_closed" and error.code not in _BLOCKING_CODES
        ]
        if still_open:
            raise FoundationError(
                "dependency_open", f"No any member is ready: {still_open[0].detail}"
            )
        if blocking:
            # Every other alternative is closed for good; only an explicit act lifts it.
            raise blocking[0]
        # No member can become true under this plan any more.
        raise FoundationError(
            "dependency_closed", f"No any member can become true: {errors[0].detail}"
        )
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
        current, status, _ = _subject_current(connection, child.work_id, "work")
        _require_succeeded(condition.role, child.work_id, status, "Required child is not accepted")
        if _schema(connection) >= 7:
            from .revalidation import require_current_result

            require_current_result(
                connection,
                child.work_id,
                WorkState.model_validate(_subject_state(connection, child.work_id, current)),
                condition.role,
            )
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
    assert condition.kind in ("decision_active", "decision_value")
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
    if condition.kind == "decision_value":
        # The choices that apply to this Work are recomputed in every reading transaction.
        check_choice_leaf(connection, work_id, condition)
        return ()
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
    *,
    include_retired: bool = False,
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
    retired = set(current) - set(expected)
    if (
        not set(expected).issubset(current)
        or any(current[key].status != "retired" for key in retired)
        or any(current[key].status == "retired" for key in expected if key in current)
        or any(
            connection.execute(
                "SELECT 1 FROM work_obligation_transitions WHERE parent_id = ? "
                "AND source_key = ? LIMIT 1",
                (str(parent_id), key),
            ).fetchone()
            is None
            for key in retired
        )
        or any(current[key].definition != item for key, item in expected.items())
    ):
        raise FoundationError(
            "incomplete_materialization", "Declared Method obligations differ from stored instances"
        )
    keys = current if include_retired else expected
    return tuple(current[key] for key in sorted(keys))


def _sanitize_deleted_method_sources(connection: sqlite3.Connection, ref: MethodRef) -> None:
    """Remove the exact old Method's source text copied into obligation revisions.

    The plan binding at the recording operation owns an ordinary instance. A retired
    instance is written by the transition operation but still owns its *source* Method,
    named by the transition row and the preceding plan binding. These addresses keep
    later Method versions and a reused key independent of the deleted definition.
    """

    expected = (str(ref.method_id), ref.version, ref.checksum)
    parents = [
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT parent_id FROM work_plan_methods WHERE method_id = ? "
            "AND method_version = ? AND method_checksum = ?",
            expected,
        ).fetchall()
    ]
    for parent_id in parents:
        revisions = connection.execute(
            "SELECT r.key, r.revision, r.payload, r.operation_id, o.state_revision "
            "FROM work_obligation_revisions r JOIN operations o "
            "ON o.operation_id = r.operation_id WHERE r.parent_id = ?",
            (parent_id,),
        ).fetchall()
        for key, revision, payload, operation_id, state_revision in revisions:
            if bytes(payload) == REDACTED_DEPENDENCY:
                continue
            instance = ObligationRevision.model_validate_json(bytes(payload))
            owner = None
            if instance.status == "retired":
                owner = connection.execute(
                    "SELECT m.method_id, m.method_version, m.method_checksum "
                    "FROM work_obligation_transitions t JOIN work_plan_methods m "
                    "ON m.parent_id = t.parent_id AND m.plan_revision = t.plan_revision - 1 "
                    "WHERE t.parent_id = ? AND t.source_key = ? AND t.source_revision = ? "
                    "AND t.operation_id = ?",
                    (parent_id, key, revision - 1, operation_id),
                ).fetchone()
            if owner is None:
                owner = connection.execute(
                    "SELECT m.method_id, m.method_version, m.method_checksum "
                    "FROM work_plan_methods m JOIN work_plan_revisions p "
                    "ON p.parent_id = m.parent_id AND p.revision = m.plan_revision "
                    "JOIN operations o ON o.operation_id = p.operation_id "
                    "WHERE m.parent_id = ? AND o.state_revision <= ? "
                    "ORDER BY m.plan_revision DESC LIMIT 1",
                    (parent_id, state_revision),
                ).fetchone()
            if owner is None or tuple(owner) != expected:
                continue
            scrubbed = instance.model_copy(
                update={
                    "definition": instance.definition.model_copy(
                        update={"source": REDACTED_METHOD_SOURCE}
                    )
                }
            )
            connection.execute(
                "UPDATE work_obligation_revisions SET payload = ? "
                "WHERE parent_id = ? AND key = ? AND revision = ?",
                (scrubbed.model_dump_json().encode("utf-8"), parent_id, key, revision),
            )


def apply_composition_change(
    connection: sqlite3.Connection,
    request: (
        CreateMethodVersionRequest
        | DeleteMethodVersionRequest
        | CreateCompositeWorkRequest
        | ReviseWorkPlanRequest
        | IssueChildWorkRequest
        | ConfirmObligationRequest
        | ResolveObligationApplicabilityRequest
        | WaiveObligationRequest
        | RevalidateResultRequest
    ),
    *,
    now: str,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if isinstance(
        request,
        (
            ReviseWorkPlanRequest,
            ConfirmObligationRequest,
            ResolveObligationApplicabilityRequest,
            WaiveObligationRequest,
        ),
    ):
        binding = child_binding(connection, request.work_id)
        if binding is not None:
            revision, _status, _ = _subject_current(connection, request.work_id, "work")
            state = WorkState.model_validate(_subject_state(connection, request.work_id, revision))
            check_child_plan(
                connection,
                request.work_id,
                binding,
                state,
                attempt_id=None,
                actor=request.actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            )
    if isinstance(request, RevalidateResultRequest):
        # A recheck exists precisely because this Work's held premise may have changed.
        # Recheck its *ancestors*, while revalidation validates this Work's own change.
        binding = child_binding(connection, request.work_id)
        ancestor_id = binding[0] if binding is not None else None
        ancestor_binding = (
            child_binding(connection, ancestor_id) if ancestor_id is not None else None
        )
        if ancestor_id is not None and ancestor_binding is not None:
            revision, _status, _ = _subject_current(connection, ancestor_id, "work")
            ancestor = WorkState.model_validate(_subject_state(connection, ancestor_id, revision))
            if ancestor.status != "proposed":
                raise FoundationError("work_closed", f"Ancestor Work {ancestor_id} is closed")
            check_child_plan(
                connection,
                ancestor_id,
                ancestor_binding,
                ancestor,
                attempt_id=None,
                actor=request.actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            )
    if isinstance(request, RevalidateResultRequest):
        from .revalidation import revalidate_result

        return revalidate_result(
            connection, request, now=now, epoch=epoch, grants=grants, decisions=decisions
        )
    if isinstance(request, ResolveObligationApplicabilityRequest):
        return _resolve_obligation(
            connection, request, now=now, epoch=epoch, grants=grants, decisions=decisions
        )
    if isinstance(request, WaiveObligationRequest):
        return _waive_obligation(
            connection, request, now=now, epoch=epoch, grants=grants, decisions=decisions
        )
    if isinstance(request, CreateMethodVersionRequest):
        if _schema(connection) < 8 and any(
            item.role is None for item in request.definition.obligations
        ):
            raise FoundationError(
                "unsupported_schema", "Roleless obligations need explicit schema 8"
            )
        if _schema(connection) < 7 and any(
            item.applicability != "always" for item in request.definition.obligations
        ):
            raise FoundationError(
                "unsupported_schema", "Conditional obligations need explicit schema 7"
            )
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
        if _schema(connection) >= 6:
            pinned = connection.execute(
                "SELECT 1 FROM execution_plan_pins p JOIN execution_attempts a "
                "ON a.attempt_id = p.attempt_id LEFT JOIN execution_assignments s "
                "ON s.attempt_id = a.attempt_id WHERE p.method_id = ? "
                "AND p.method_version = ? AND p.method_checksum = ? "
                "AND (a.status = 'active' OR s.status = 'unknown') LIMIT 1",
                (str(ref.method_id), ref.version, ref.checksum),
            ).fetchone()
            if pinned is not None:
                raise FoundationError("method_in_use", "Active Attempt still pins Method")
        if _schema(connection) >= 7:
            transferred = connection.execute(
                "SELECT 1 FROM execution_plan_transfers t JOIN execution_attempts a "
                "ON a.attempt_id = t.attempt_id LEFT JOIN execution_assignments s "
                "ON s.attempt_id = a.attempt_id WHERE t.method_id = ? "
                "AND t.method_version = ? AND t.method_checksum = ? "
                "AND (a.status = 'active' OR s.status = 'unknown') LIMIT 1",
                (str(ref.method_id), ref.version, ref.checksum),
            ).fetchone()
            if transferred is not None:
                raise FoundationError("method_in_use", "Active Attempt still transfers Method")
            _sanitize_deleted_method_sources(connection, ref)
        if _schema(connection) >= 8:
            pinned_parent = connection.execute(
                "SELECT 1 FROM execution_parent_pins p JOIN execution_attempts a "
                "ON a.attempt_id = p.attempt_id LEFT JOIN execution_assignments s "
                "ON s.attempt_id = a.attempt_id WHERE p.method_id = ? "
                "AND p.method_version = ? AND p.method_checksum = ? "
                "AND (a.status = 'active' OR s.status = 'unknown') LIMIT 1",
                (str(ref.method_id), ref.version, ref.checksum),
            ).fetchone()
            if pinned_parent is not None:
                raise FoundationError("method_in_use", "Active parent Attempt still pins Method")
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
        if definition.required_capabilities:
            raise FoundationError("unsupported_condition", "Method capabilities are not connected")
        if tuple(request.state.expected_outputs) != definition.named_outputs:
            raise FoundationError("method_mismatch", "Parent outputs differ from pinned Method")
        _validate_plan(
            request.plan, definition, request.state.activity_id, schema=_schema(connection)
        )
        _validate_choice_leaves(connection, request.plan)
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
        if _schema(connection) >= 7:
            assert isinstance(request.state.method, MethodRef)
            _record_plan_method(
                connection, request.work_id, 1, request.state.method, request.operation_id
            )
        for obligation in definition.obligations:
            instance = ObligationRevision(
                parent_work_id=request.work_id,
                key=obligation.key,
                revision=1,
                definition=obligation,
                # A conditional obligation is neither applicable nor inapplicable yet.
                applicability="active" if obligation.applicability == "always" else "unresolved",
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
        ).fetchone() or (
            _schema(connection) >= 7
            and connection.execute(
                "SELECT 1 FROM work_plan_members WHERE parent_id = ? "
                "AND issued_plan_revision IS NOT NULL LIMIT 1",
                (str(request.work_id),),
            ).fetchone()
        ):
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
        filled_before = {role for _child, role in _member_rows(connection, str(request.work_id))}
        if any(child.role in filled_before for child in added):
            # A role that left the plan is filled again only by an explicit node decision.
            raise FoundationError(
                "unsupported_plan_change",
                "A role filled before is filled again only through revise_active_plan",
            )
        _validate_plan(request.plan, definition, parent.activity_id, schema=_schema(connection))
        _validate_choice_leaves(connection, request.plan)
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
        if _schema(connection) >= 7:
            assert isinstance(parent.method, MethodRef)
            _record_plan_method(
                connection, request.work_id, next_revision, parent.method, request.operation_id
            )
        if _schema(connection) >= 8:
            _hold_work_execution(
                connection, request.work_id, request.operation_id, now, "revise_parent_plan"
            )
        return {"work_id": str(request.work_id), "plan_revision": next_revision}, targets
    if isinstance(request, IssueChildWorkRequest):
        _rev, parent, definition = _parent(connection, request.parent_work_id)
        parent_binding = child_binding(connection, request.parent_work_id)
        if parent_binding is not None:
            check_child_plan(
                connection,
                request.parent_work_id,
                parent_binding,
                parent,
                attempt_id=None,
                actor=request.actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            )
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
        issued = original_issue(connection, request.work_id)
        if issued is None or issued[0] != request.parent_work_id or issued[1] is not None:
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
            work_id=request.work_id,
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
        _record_issue(connection, request.work_id, plan.revision, request.operation_id)
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
    assert isinstance(parent.method, MethodRef)
    # An open instance, or a waived one whose exception no longer holds, is executed next.
    if selected_instance.revision != request.expected_obligation_revision or not (
        open_for_execution(connection, selected_instance, parent.method)
    ):
        raise FoundationError("stale_obligation", "Obligation already changed")
    if parent.status != "proposed":
        raise FoundationError("work_closed", f"Parent Work is {parent.status}")
    # Only a validly active obligation is executed; its choices are recomputed here.
    require_applicable(connection, selected_instance, f"Confirmation of {request.key}")
    parent_result: ParentResultEvidence | None = None
    if selected_instance.definition.role is None:
        actual, proof = _accepted_parent_output(
            connection,
            request.work_id,
            parent,
            plan.plan,
            selected_instance.definition.slot,
            selected_instance.definition.media_type,
            actor=request.actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
        parent_result = ParentResultEvidence(
            attempt_id=proof.attempt_id,
            plan_revision=proof.plan_revision,
            method=proof.method,
        )
    else:
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
            "parent_result": parent_result,
            "basis": request.basis,
            "operation_id": request.operation_id,
            "created_at": datetime.fromisoformat(now),
            "exception": None,
            "reopened": None,
            "carried_from_key": None,
            "carried_from_revision": None,
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


def _resolve_obligation(
    connection: sqlite3.Connection,
    request: ResolveObligationApplicabilityRequest,
    *,
    now: str,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Record applicability of one conditional obligation from one exact choice.

    The result is a new instance revision, ``active``/``open`` or ``inactive``, with the
    choice address. Applicability never switches silently: a valid resolution stays until
    its exact choice is revised or revoked, and then only a new resolution replaces it.
    """

    if _schema(connection) < 7:
        raise FoundationError("unsupported_schema", "Obligation applicability needs schema 7")
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
    selected = instances.get(request.key)
    if selected is None:
        raise FoundationError("not_found", "Method does not declare this obligation")
    if selected.revision != request.expected_obligation_revision:
        raise FoundationError("stale_obligation", "Obligation already changed")
    if parent.status != "proposed":
        raise FoundationError("work_closed", f"Parent Work is {parent.status}")
    condition = selected.definition.applicability
    if not isinstance(condition, ChoiceApplicability):
        raise FoundationError(
            "unconditional_obligation", f"Obligation {request.key} applies always"
        )
    if selected.choice is not None and choice_holds(connection, selected.choice):
        raise FoundationError(
            "applicability_resolved",
            f"Obligation {request.key} is {selected.applicability} by Decision "
            f"{selected.choice.decision_id}@{selected.choice.revision}",
        )
    applicability = resolve_applicability(connection, request.work_id, condition, request.choice)
    next_instance = ObligationRevision(
        parent_work_id=request.work_id,
        key=request.key,
        revision=selected.revision + 1,
        definition=selected.definition,
        applicability=applicability,
        status="open",
        basis=request.basis,
        operation_id=request.operation_id,
        created_at=datetime.fromisoformat(now),
        choice=request.choice,
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
        "applicability": applicability,
        "choice": request.choice.model_dump(mode="json"),
    }, [
        {"record_id": str(request.work_id), "revision": plan.revision},
        {"record_id": str(request.choice.decision_id), "revision": request.choice.revision},
    ]


def _waive_obligation(
    connection: sqlite3.Connection,
    request: WaiveObligationRequest,
    *,
    now: str,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Take one active obligation off by an exact exception within its limits.

    The waiver is a new instance revision kept apart from ``satisfied``, with the
    exception address and no evidence: it is not a result. It holds only while that exact
    exception revision is current and active.
    """

    if _schema(connection) < 7:
        raise FoundationError("unsupported_schema", "Waivers need explicit schema 7")
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
    selected = instances.get(request.key)
    if selected is None:
        raise FoundationError("not_found", "Method does not declare this obligation")
    assert isinstance(parent.method, MethodRef)
    if selected.revision != request.expected_obligation_revision or not open_for_execution(
        connection, selected, parent.method
    ):
        raise FoundationError("stale_obligation", "Obligation already changed")
    if parent.status != "proposed":
        raise FoundationError("work_closed", f"Parent Work is {parent.status}")
    # Only a validly active obligation is waived; its choices are recomputed here.
    require_applicable(connection, selected, f"Waiver of {request.key}")
    require_exception(
        connection,
        request.exception,
        ObligationTarget(work_id=request.work_id, key=request.key),
        parent.method,
    )
    next_instance = ObligationRevision.model_validate(
        selected.model_dump(mode="python")
        | {
            "revision": selected.revision + 1,
            "status": "waived",
            "evidence": None,
            "basis": request.basis,
            "operation_id": request.operation_id,
            "created_at": datetime.fromisoformat(now),
            "exception": request.exception,
            "reopened": None,
            "carried_from_key": None,
            "carried_from_revision": None,
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
        "status": "waived",
        "exception": request.exception.model_dump(mode="json"),
    }, [
        {"record_id": str(request.work_id), "revision": plan.revision},
        {"record_id": str(request.exception.decision_id), "revision": request.exception.revision},
    ]


def waived_obligations(
    connection: sqlite3.Connection, work_id: UUID, state: WorkState
) -> tuple[WaivedObligation, ...]:
    """Requirements of a composite parent taken off by exceptions, for its acceptance."""

    if _schema(connection) < 7 or not isinstance(state.method, MethodRef):
        return ()
    definition = _method(connection, state.method)
    return tuple(
        WaivedObligation(key=instance.key, exception=instance.exception)
        for instance in _obligations(connection, work_id, definition)
        if instance.status == "waived" and instance.exception is not None
    )


def _member_rows(connection: sqlite3.Connection, parent_id: str) -> list[tuple[str, str]]:
    """Every Work that ever filled a role of this parent, with its role.

    The schema 5 row keeps the original member of each role; at schema 7 Works that fill a
    role through an active plan revision are members in their own table.
    """

    rows = [
        (str(child), str(role))
        for child, role in connection.execute(
            "SELECT child_id, role FROM work_plan_children WHERE parent_id = ? ORDER BY role",
            (parent_id,),
        ).fetchall()
    ]
    if _schema(connection) >= 7:
        rows += [
            (str(child), str(role))
            for child, role in connection.execute(
                "SELECT child_id, role FROM work_plan_members WHERE parent_id = ? "
                "ORDER BY plan_revision, role",
                (parent_id,),
            ).fetchall()
        ]
    return rows


def original_issue(
    connection: sqlite3.Connection, work_id: UUID
) -> tuple[UUID, int | None, str] | None:
    """Parent, the plan revision that issued the child (if any) and its role."""

    row = connection.execute(
        "SELECT parent_id, issued_plan_revision, role FROM work_plan_children WHERE child_id = ?",
        (str(work_id),),
    ).fetchone()
    if row is None and _schema(connection) >= 7:
        row = connection.execute(
            "SELECT parent_id, issued_plan_revision, role FROM work_plan_members "
            "WHERE child_id = ?",
            (str(work_id),),
        ).fetchone()
    return None if row is None else (UUID(row[0]), row[1], str(row[2]))


def plan_membership(connection: sqlite3.Connection, work_id: UUID) -> tuple[UUID, str] | None:
    """Parent and role of one child Work; a Work fills one role of one parent for good."""

    found = original_issue(connection, work_id)
    return None if found is None else (found[0], found[2])


def _record_issue(
    connection: sqlite3.Connection, work_id: UUID, revision: int, operation_id: UUID
) -> None:
    for table in ("work_plan_children", "work_plan_members"):
        if table == "work_plan_members" and _schema(connection) < 7:
            return
        updated = connection.execute(
            f"UPDATE {table} SET issued_plan_revision = ?, issue_operation_id = ? "
            "WHERE child_id = ?",
            (revision, str(operation_id), str(work_id)),
        )
        if updated.rowcount:
            return


def child_binding(
    connection: sqlite3.Connection, work_id: UUID
) -> tuple[UUID, int | None, str] | None:
    """Return the parent, the plan revision holding its issue and the role of a child.

    The issue is held by the revision that issued the child and, at schema 7, by every later
    revision that kept the node and carried its issue; a node that left the plan holds none
    in later revisions.
    """

    binding = original_issue(connection, work_id)
    if binding is None or binding[1] is None or _schema(connection) < 7:
        return binding
    carried = connection.execute(
        "SELECT max(plan_revision) FROM work_plan_nodes WHERE parent_id = ? AND work_id = ? "
        "AND decision = 'keep' AND issue_carried = 1",
        (str(binding[0]), str(work_id)),
    ).fetchone()[0]
    if carried is not None and int(carried) > binding[1]:
        return binding[0], int(carried), binding[2]
    return binding


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
    if row is not None and tuple(row) == current:
        return
    if _schema(connection) >= 7:
        # A kept node's Attempt continues through its explicit transfer; the pin stays.
        transfer = connection.execute(
            "SELECT parent_id, role, plan_revision, method_id, method_version, method_checksum "
            "FROM execution_plan_transfers WHERE attempt_id = ? AND work_id = ? "
            "AND plan_revision = ?",
            (str(attempt_id), str(work_id), plan_revision),
        ).fetchone()
        if transfer is not None and tuple(transfer) == current:
            return
    # An older generation never applies its effect or result to another plan.
    raise FoundationError(
        "stale_plan",
        "Attempt is not pinned to or transferred into the current plan revision and Method",
    )


def _attempt_pin_current(
    connection: sqlite3.Connection, attempt_id: UUID, work_id: UUID, parent_id: UUID, role: str
) -> bool:
    """Whether the Attempt is pinned to, or transferred into, its parent's current plan."""

    revision = connection.execute(
        "SELECT max(revision) FROM work_plan_revisions WHERE parent_id = ?", (str(parent_id),)
    ).fetchone()[0]
    current, _status, _ = _subject_current(connection, parent_id, "work")
    parent = WorkState.model_validate(_subject_state(connection, parent_id, current))
    if revision is None or not isinstance(parent.method, MethodRef):
        return False
    try:
        _pinned_plan(
            connection, attempt_id, work_id, (parent_id, role, int(revision), parent.method)
        )
    except FoundationError:
        return False
    return True


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
    ancestor = child_binding(connection, parent_id)
    if ancestor is not None:
        check_child_plan(
            connection,
            parent_id,
            ancestor,
            parent,
            attempt_id=None,
            actor=actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
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
    if parent.status != "proposed":
        raise FoundationError("work_closed", f"Ancestor Work {parent_id} is {parent.status}")
    if issued != plan.revision:
        raise FoundationError(
            "child_not_issued", f"Child lacks current plan issuance under {parent_id}"
        )
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
        work_id=work_id,
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
    """Pin the parent's own plan and, for a nested Work, its ancestor's plan."""

    binding = child_binding(connection, request.work_id)
    result: dict[str, object] | None = None
    if binding is not None:
        parent_id, _issued, role = binding
        plan = _plan(connection, parent_id)
        _p_rev, parent, _definition = _parent(connection, parent_id)
        assert isinstance(parent.method, MethodRef)
        connection.execute(
            "INSERT INTO execution_plan_pins(attempt_id, work_id, parent_id, role, "
            "plan_revision, method_id, method_version, method_checksum, operation_id, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
        result = {
            "parent_work_id": str(parent_id),
            "role": role,
            "plan_revision": plan.revision,
            "method": parent.method.model_dump(mode="json"),
        }
    if (
        _schema(connection) >= 8
        and connection.execute(
            "SELECT 1 FROM work_plan_revisions WHERE parent_id = ? LIMIT 1",
            (str(request.work_id),),
        ).fetchone()
    ):
        own_plan = _plan(connection, request.work_id)
        _revision, own_state, _definition = _parent(connection, request.work_id)
        assert isinstance(own_state.method, MethodRef)
        connection.execute(
            "INSERT INTO execution_parent_pins(attempt_id, work_id, plan_revision, "
            "method_id, method_version, method_checksum, operation_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(request.attempt_id),
                str(request.work_id),
                own_plan.revision,
                str(own_state.method.method_id),
                own_state.method.version,
                own_state.method.checksum,
                str(request.operation_id),
                now,
            ),
        )
        own = {
            "work_id": str(request.work_id),
            "plan_revision": own_plan.revision,
            "method": own_state.method.model_dump(mode="json"),
        }
        return {**result, "own_plan": own} if result is not None else {"own_plan": own}
    return result


def _parent_pin(connection: sqlite3.Connection, attempt_id: UUID, work_id: UUID) -> ParentPlanPin:
    if _schema(connection) < 8:
        raise FoundationError("unsupported_schema", "Parent pins need schema 8")
    row = connection.execute(
        "SELECT plan_revision, method_id, method_version, method_checksum, operation_id "
        "FROM execution_parent_pins WHERE attempt_id = ? AND work_id = ?",
        (str(attempt_id), str(work_id)),
    ).fetchone()
    if row is None:
        raise FoundationError("stale_plan", "Attempt has no own parent-plan pin")
    return ParentPlanPin(
        attempt_id=attempt_id,
        work_id=work_id,
        plan_revision=int(row[0]),
        method=MethodRef(method_id=UUID(row[1]), version=int(row[2]), checksum=row[3]),
        operation_id=UUID(row[4]),
    )


def _require_parent_pin_current(
    connection: sqlite3.Connection, attempt_id: UUID, work_id: UUID
) -> ParentPlanPin:
    pin = _parent_pin(connection, attempt_id, work_id)
    current, _status, _ = _subject_current(connection, work_id, "work")
    state = WorkState.model_validate(_subject_state(connection, work_id, current))
    revision = connection.execute(
        "SELECT max(revision) FROM work_plan_revisions WHERE parent_id = ?", (str(work_id),)
    ).fetchone()[0]
    if revision != pin.plan_revision or state.method != pin.method:
        raise FoundationError("stale_plan", "Own Attempt is fenced by plan or Method revision")
    return pin


def _parent_output_proof(
    connection: sqlite3.Connection, work_id: UUID, slot: str, artifact: ArtifactRef
) -> ParentOutputProof:
    row = connection.execute(
        "SELECT artifact_revision, attempt_id, plan_revision, method_id, method_version, "
        "method_checksum, operation_id FROM parent_output_proofs "
        "WHERE artifact_id = ? AND work_id = ? AND slot = ?",
        (str(artifact.artifact_id), str(work_id), slot),
    ).fetchone()
    if row is None or int(row[0]) != artifact.revision:
        raise FoundationError("evidence_mismatch", "No exact own Attempt publication exists")
    proof = ParentOutputProof(
        work_id=work_id,
        slot=slot,
        artifact=artifact,
        attempt_id=UUID(row[1]),
        plan_revision=int(row[2]),
        method=MethodRef(method_id=UUID(row[3]), version=int(row[4]), checksum=row[5]),
        operation_id=UUID(row[6]),
    )
    pin = _require_parent_pin_current(connection, proof.attempt_id, work_id)
    if pin.plan_revision != proof.plan_revision or pin.method != proof.method:
        raise FoundationError("stale_plan", "Publication no longer matches its own pin")
    latest = connection.execute(
        "SELECT attempt_id FROM execution_attempts WHERE work_id = ? "
        "ORDER BY generation DESC LIMIT 1",
        (str(work_id),),
    ).fetchone()
    if latest is None or latest[0] != str(proof.attempt_id):
        raise FoundationError("stale_attempt", "Own output belongs to a superseded Attempt")
    return proof


def _accepted_parent_output(
    connection: sqlite3.Connection,
    work_id: UUID,
    state: WorkState,
    plan: WorkPlan,
    slot: str,
    media_type: str,
    *,
    actor: str | None,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[ArtifactRef, ParentOutputProof]:
    declared = next((item for item in plan.parent_outputs if item.slot == slot), None)
    if declared is None or declared.media_type != media_type:
        raise FoundationError("wrong_output", "Plan does not declare this own output slot/type")
    artifact = next((item.artifact for item in state.linked_outputs if item.slot == slot), None)
    if artifact is None:
        raise FoundationError("dependency_open", "Parent has no current own output")
    _current_artifact(
        connection,
        artifact,
        actor=actor,
        epoch=epoch,
        grants=grants,
        decisions=decisions,
        media_type=media_type,
    )
    return artifact, _parent_output_proof(connection, work_id, slot, artifact)


def record_parent_publication(
    connection: sqlite3.Connection,
    request: PublishAttemptOutputRequest,
    artifact: ArtifactRef,
    now: str,
) -> list[dict[str, object]]:
    """Keep the producer pin and reopen confirmations of an older own result."""

    if (
        _schema(connection) < 8
        or connection.execute(
            "SELECT 1 FROM work_plan_revisions WHERE parent_id = ? LIMIT 1",
            (str(request.work_id),),
        ).fetchone()
        is None
    ):
        return []
    pin = _require_parent_pin_current(connection, request.attempt_id, request.work_id)
    connection.execute(
        "INSERT INTO parent_output_proofs(artifact_id, artifact_revision, work_id, slot, "
        "attempt_id, plan_revision, method_id, method_version, method_checksum, "
        "operation_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(artifact.artifact_id),
            artifact.revision,
            str(request.work_id),
            request.slot,
            str(request.attempt_id),
            pin.plan_revision,
            str(pin.method.method_id),
            pin.method.version,
            pin.method.checksum,
            str(request.operation_id),
            now,
        ),
    )
    _rev, _state, definition = _parent(connection, request.work_id)
    targets: list[dict[str, object]] = []
    for instance in _obligations(connection, request.work_id, definition):
        if (
            instance.definition.role is not None
            or instance.definition.slot != request.slot
            or instance.status != "satisfied"
            or instance.evidence == artifact
        ):
            continue
        reopened = instance.model_copy(
            update={
                "revision": instance.revision + 1,
                "status": "open",
                "evidence": None,
                "parent_result": None,
                "basis": None,
                "operation_id": request.operation_id,
                "created_at": datetime.fromisoformat(now),
                "reopened": "parent_attempt_replaced",
                "carried_from_key": None,
                "carried_from_revision": None,
            }
        )
        connection.execute(
            "INSERT INTO work_obligation_revisions(parent_id, key, revision, payload, "
            "operation_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(request.work_id),
                instance.key,
                reopened.revision,
                reopened.model_dump_json().encode("utf-8"),
                str(request.operation_id),
                now,
            ),
        )
        targets.append({"record_id": str(request.work_id), "revision": reopened.revision})
    return targets


def composite_execution_ready(
    connection: sqlite3.Connection, work_id: UUID, attempt_id: UUID, *, actor: str, epoch: int
) -> bool:
    """Control-read form of the same assigned child/parent effect gate."""

    schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if schema < 5:
        return True
    owns_plan = (
        connection.execute(
            "SELECT 1 FROM work_plan_revisions WHERE parent_id = ? LIMIT 1", (str(work_id),)
        ).fetchone()
        is not None
    )
    if owns_plan and schema < 8:
        raise FoundationError(
            "unsupported_composite_execution", "Composite Work has no own Attempt"
        )
    binding = child_binding(connection, work_id)
    if binding is None and not owns_plan:
        return True
    if binding is not None and schema < 6:
        raise FoundationError(
            "unsupported_composite_execution", "Assigned child execution needs schema 6"
        )
    try:
        revision, _status, _ = _subject_current(connection, work_id, "work")
        state = WorkState.model_validate(_subject_state(connection, work_id, revision))
        if binding is not None:
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
        if owns_plan:
            _require_parent_pin_current(connection, attempt_id, work_id)
            if state.status != "proposed":
                return False
            _parent_current(
                connection,
                work_id,
                state,
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
    owns_plan = isinstance(state.method, MethodRef)
    if schema >= 7 and binding is not None and isinstance(request, ATTEMPT_EFFECTS):
        _require_unfenced_effect(connection, request, work_id, binding)
    if schema >= 8 and owns_plan and isinstance(request, ATTEMPT_EFFECTS):
        _require_unfenced_parent_effect(connection, request, work_id)
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
    if (
        binding is not None
        and isinstance(state.method, MethodRef)
        and schema < 8
        and not isinstance(
            request,
            (LinkWorkOutputRequest, AcceptWorkRequest, CloseWorkRequest) + _ATTEMPT_OUTCOMES,
        )
    ):
        raise FoundationError(
            "unsupported_composite_execution", "Nested composite Work has no own Attempt"
        )
    assigned_child = (
        binding is not None and schema >= 6 and not isinstance(request, _INTERACTIVE_ATTEMPTS)
    )
    assigned_parent = owns_plan and schema >= 8 and not isinstance(request, _INTERACTIVE_ATTEMPTS)
    if not direct and not assigned_child and not assigned_parent:
        raise FoundationError(
            "unsupported_composite_execution",
            "Composite parent and interactive execution are not connected; "
            "an assigned child Attempt needs explicit schema 6",
        )
    if (assigned_child or assigned_parent) and isinstance(
        request, _ATTEMPT_OUTCOMES + _RESOURCE_SETUP
    ):
        return
    if isinstance(request, AcceptWorkRequest) and isinstance(state.method, MethodRef):
        if binding is not None:
            check_child_plan(
                connection,
                work_id,
                binding,
                state,
                attempt_id=None,
                actor=actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            )
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
        if not owns_plan:
            return
    definition, plan = _parent_current(
        connection, work_id, state, actor=actor, epoch=epoch, grants=grants, decisions=decisions
    )
    if assigned_parent and isinstance(request, ATTEMPT_EFFECTS):
        attempt_id = getattr(request, "attempt_id", None)
        if isinstance(attempt_id, UUID):
            _require_parent_pin_current(connection, attempt_id, work_id)
    if isinstance(request, PublishAttemptOutputRequest):
        if request.slot not in {item.slot for item in plan.plan.parent_outputs}:
            raise FoundationError("wrong_output", "Plan does not assign this slot to its Work")
    if isinstance(request, LinkWorkOutputRequest):
        if request.output.slot in {item.slot for item in plan.plan.parent_outputs}:
            raise FoundationError("wrong_output", "Own output needs its producing Attempt")
        bound = next(
            (item for item in plan.plan.output_bindings if item.parent_slot == request.output.slot),
            None,
        )
        if bound is not None:
            _require_open_branch(connection, plan.plan, bound.role, f"Output {bound.parent_slot}")
            if _schema(connection) >= 7:
                from .revalidation import require_role_result

                # Linking integrates the bound accepted result: its premises must hold.
                require_role_result(connection, plan.plan, bound.role)
        # A later opposite choice blocks integration relying on a recorded resolution.
        require_consistent_resolutions(
            connection,
            _obligations(connection, work_id, definition),
            f"Output {request.output.slot}",
        )


def _require_unfenced_parent_effect(
    connection: sqlite3.Connection, request: object, work_id: UUID
) -> None:
    attempt_id = getattr(request, "attempt_id", None)
    if not isinstance(attempt_id, UUID):
        return
    row = connection.execute(
        "SELECT 1 FROM execution_parent_pins WHERE attempt_id = ? AND work_id = ?",
        (str(attempt_id), str(work_id)),
    ).fetchone()
    if row is None:
        return
    if isinstance(request, AnswerWaitRequest):
        wait = connection.execute(
            "SELECT status FROM execution_waits WHERE wait_id = ? AND attempt_id = ? "
            "AND work_id = ?",
            (str(request.wait_id), str(attempt_id), str(work_id)),
        ).fetchone()
        if wait is not None and wait[0] == "closed":
            raise FoundationError("stale_wait", "Wait changed or is closed")
    _require_parent_pin_current(connection, attempt_id, work_id)


def _require_unfenced_effect(
    connection: sqlite3.Connection,
    request: object,
    work_id: UUID,
    binding: tuple[UUID, int | None, str],
) -> None:
    """A fenced Attempt names its own cause before any later state of its Work.

    A late answer to a closed wait keeps the separate outcome ``stale_wait``. Any other
    effect of an Attempt neither pinned to nor transferred into the current plan revision
    refuses ``stale_plan``, also when the plan revision closed its node in the same
    transaction; stopping and recording a sent call's outcome stay possible.
    """

    attempt_id = getattr(request, "attempt_id", None)
    if not isinstance(attempt_id, UUID) or (
        connection.execute(
            "SELECT 1 FROM execution_plan_pins WHERE attempt_id = ? AND work_id = ?",
            (str(attempt_id), str(work_id)),
        ).fetchone()
        is None
    ):
        # Not an assigned Attempt of this child: the ordinary checks name the cause.
        return
    if isinstance(request, AnswerWaitRequest):
        wait = connection.execute(
            "SELECT status FROM execution_waits WHERE wait_id = ? AND attempt_id = ? "
            "AND work_id = ?",
            (str(request.wait_id), str(attempt_id), str(work_id)),
        ).fetchone()
        if wait is not None and wait[0] == "closed":
            raise FoundationError("stale_wait", "Wait changed or is closed")
    if not _attempt_pin_current(connection, attempt_id, work_id, binding[0], binding[2]):
        raise FoundationError(
            "stale_plan",
            f"Attempt {attempt_id} is not pinned to or transferred into the current plan "
            "revision and Method",
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
    if _schema(connection) >= 7:
        binding = connection.execute(
            "SELECT method_id, method_version, method_checksum FROM work_plan_methods "
            "WHERE parent_id = ? AND plan_revision = ?",
            (str(work_id), plan.revision),
        ).fetchone()
        if binding != (
            str(state.method.method_id),
            state.method.version,
            state.method.checksum,
        ):
            raise FoundationError(
                "incomplete_materialization", "Current plan and Work Method differ"
            )
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
    applicability = {item.key: obligation_applicability(connection, item) for item in instances}
    for instance in instances:
        # A formal conflict of applicable choices is never settled by time or scope.
        conflicting = applicability[instance.key][1]
        if conflicting:
            raise FoundationError(
                "decision_conflict",
                f"Choices for obligation {instance.key} disagree: "
                + ", ".join(f"Decision {item.decision_id}@{item.revision}" for item in conflicting),
            )
    for instance in instances:
        if applicability[instance.key][0] == "applicability_stale":
            raise FoundationError(
                "stale_basis", f"Applicability of obligation {instance.key} needs a new resolution"
            )
    assert isinstance(state.method, MethodRef)
    active = [item for item in instances if applicability[item.key][0] == "active"]
    for instance in active:
        # A waiver rests on its exact exception revision, rechecked in this transaction.
        if instance.status == "waived" and not waiver_holds(connection, instance, state.method):
            raise FoundationError(
                "stale_basis", f"Waiver of obligation {instance.key} needs its exception again"
            )
    unmet = [
        item
        for item in active
        if item.status != "waived" and (item.status != "satisfied" or item.evidence is None)
    ]
    for instance in unmet:
        # A closed branch can never satisfy its obligation: name it before open ones.
        if instance.definition.role is not None:
            _require_open_branch(
                connection, plan.plan, instance.definition.role, f"Obligation {instance.key}"
            )
    unresolved = [item.key for item in instances if applicability[item.key][0] == "unresolved"]
    if unresolved:
        raise FoundationError("obligation_unresolved", f"Obligation {unresolved[0]} is unresolved")
    if unmet:
        raise FoundationError("obligation_open", f"Obligation {unmet[0].key} is open")
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
    for own in plan.plan.parent_outputs:
        actual_output, _proof = _accepted_parent_output(
            connection,
            work_id,
            state,
            plan.plan,
            own.slot,
            own.media_type,
            actor=actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
        if linked.get(own.slot) != actual_output:
            raise FoundationError("output_mismatch", "Parent own output changed")
    _evaluate(
        connection,
        plan.plan,
        plan.plan.completion,
        work_id=work_id,
        actor=actor,
        epoch=epoch,
        grants=grants,
        decisions=decisions,
    )
    # An inactive or waived obligation needs no result: only satisfied ones name evidence.
    for instance in (item for item in active if item.status == "satisfied"):
        if instance.definition.role is None:
            actual, proof = _accepted_parent_output(
                connection,
                work_id,
                state,
                plan.plan,
                instance.definition.slot,
                instance.definition.media_type,
                actor=actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            )
            expected = ParentResultEvidence(
                attempt_id=proof.attempt_id,
                plan_revision=proof.plan_revision,
                method=proof.method,
            )
            if actual != instance.evidence or instance.parent_result != expected:
                raise FoundationError("stale_obligation", "Own Attempt evidence changed")
        else:
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
    permitted_succeeded_ancestors: frozenset[UUID] = frozenset(),
) -> None:
    """Shared gate of a composite Work outcome: membership, Method use and open children.

    Readiness is not required: a Work may fail, be cancelled or turn stale before it ran.
    """

    if binding is not None:
        parent_id = binding[0]
        parent_revision, _status, _ = _subject_current(connection, parent_id, "work")
        parent = WorkState.model_validate(_subject_state(connection, parent_id, parent_revision))
        if parent.status != "proposed" and not (
            parent.status == "succeeded" and parent_id in permitted_succeeded_ancestors
        ):
            raise FoundationError("work_closed", f"Ancestor Work {parent_id} is {parent.status}")
        _method_use(
            connection, parent, actor=actor, epoch=epoch, grants=grants, decisions=decisions
        )
        plan = _readable_plan(connection, parent_id)
        # A sanitized plan keeps its membership record; closing stays possible.
        if plan is not None and all(child.work_id != work_id for child in plan.plan.children):
            raise FoundationError("wrong_work", "Child is not in its parent's current plan")
        ancestor_id = parent_id
        while (ancestor_binding := child_binding(connection, ancestor_id)) is not None:
            ancestor_id = ancestor_binding[0]
            _ancestor_revision, _ancestor_status, _ = _subject_current(
                connection, ancestor_id, "work"
            )
            ancestor = WorkState.model_validate(
                _subject_state(connection, ancestor_id, _ancestor_revision)
            )
            if ancestor.status != "proposed" and not (
                ancestor.status == "succeeded" and ancestor_id in permitted_succeeded_ancestors
            ):
                raise FoundationError("work_closed", f"Ancestor Work {ancestor_id} is closed")
            _method_use(
                connection,
                ancestor,
                actor=actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            )
    if isinstance(state.method, MethodRef):
        if binding is None:
            _method_use(
                connection, state, actor=actor, epoch=epoch, grants=grants, decisions=decisions
            )
        open_children = sorted(
            f"{role}:{child_id}"
            for child_id, role in _member_rows(connection, str(work_id))
            if _subject_current(connection, UUID(child_id), "work")[1] == "proposed"
        )
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
            elif (
                leaf.kind in ("decision_active", "decision_value")
                and leaf.decision_id
                and leaf.decision_revision
            ):
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

    verify_premises_changed(
        connection,
        request.work_id,
        state,
        request.premises,
        request.decision_premises,
        actor=request.actor,
        epoch=epoch,
        grants=grants,
        decisions=decisions,
    )


def verify_premises_changed(
    connection: sqlite3.Connection,
    work_id: UUID,
    state: WorkState,
    premises: tuple[ArtifactRef, ...],
    decision_premises: tuple[DecisionRef, ...],
    *,
    actor: str,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> None:
    """Each named premise of the Work held at its exact address and is no longer current."""

    artifacts, decision_refs = _premises(connection, work_id, state)
    for reference in premises:
        address = f"Artifact {reference.artifact_id}@{reference.revision}"
        if reference not in artifacts:
            raise FoundationError("premise_mismatch", f"{address} is not a premise of this Work")
        extra_grants, extra_decisions = _authorize(
            connection,
            actor=actor,
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
    for decision in decision_premises:
        address = f"Decision {decision.decision_id}@{decision.revision}"
        if decision not in decision_refs:
            raise FoundationError("premise_mismatch", f"{address} is not a premise of this Work")
        extra_grants, extra_decisions = _authorize(
            connection,
            actor=actor,
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
    for child_id, _role in _member_rows(connection, str(work_id)):
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
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 7:
        # Result rechecks, members joined by active revisions and node decisions belong to
        # the parent and go with it.
        operation_ids += [
            row[0]
            for row in connection.execute(
                "SELECT operation_id FROM result_revalidations WHERE parent_id = ? "
                "UNION SELECT issue_operation_id FROM work_plan_members WHERE parent_id = ? "
                "AND issue_operation_id IS NOT NULL",
                (str(work_id), str(work_id)),
            ).fetchall()
        ]
        connection.execute("DELETE FROM result_revalidations WHERE parent_id = ?", (str(work_id),))
        connection.execute(
            "DELETE FROM work_obligation_transitions WHERE parent_id = ?", (str(work_id),)
        )
        connection.execute("DELETE FROM work_plan_methods WHERE parent_id = ?", (str(work_id),))
        connection.execute("DELETE FROM work_plan_nodes WHERE parent_id = ?", (str(work_id),))
        connection.execute("DELETE FROM work_plan_members WHERE parent_id = ?", (str(work_id),))
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


def _descendant_works(connection: sqlite3.Connection, ancestor_id: str) -> set[str]:
    """Address-only membership closure, including departed role fillers."""

    found: set[str] = set()
    pending = [ancestor_id]
    while pending:
        parent_id = pending.pop()
        for child_id, _role in _member_rows(connection, parent_id):
            if child_id not in found:
                found.add(child_id)
                pending.append(child_id)
    return found


def _contains_descendant(
    connection: sqlite3.Connection, ancestor_id: str, departing_id: str
) -> bool:
    return ancestor_id == departing_id or departing_id in _descendant_works(connection, ancestor_id)


def _recorded_plan_roles(
    connection: sqlite3.Connection,
    parent_id: str,
    recorded_by: str,
    plans: dict[str, list[_PlanDependencies | None]],
    *,
    artifact_id: UUID | None,
    child_id: UUID | None,
) -> set[str] | None:
    """Roles that depended on a deleted subject under the plan revision current when one
    obligation revision was recorded, with their dependents; ``None`` when unknown.

    A resolution or waiver may be recorded before the first issue, and a later plan
    revision may no longer name that subject. Its basis stays linked to the revision under
    which it was recorded, read through the retained index once sanitized. A deleted child
    seeds only the role it filled in that revision.
    """

    recorded = connection.execute(
        "SELECT state_revision FROM operations WHERE operation_id = ?", (recorded_by,)
    ).fetchone()
    stamps = [
        row[0]
        for row in connection.execute(
            "SELECT o.state_revision FROM work_plan_revisions p LEFT JOIN operations o "
            "ON o.operation_id = p.operation_id WHERE p.parent_id = ? ORDER BY p.revision",
            (parent_id,),
        ).fetchall()
    ]
    positions = [
        position
        for position, stamp in enumerate(stamps)
        if recorded is not None and stamp is not None and int(stamp) <= int(recorded[0])
    ]
    if not positions:
        return set()
    index = _plan_history(connection, parent_id, plans)[positions[-1]]
    if index is None:
        return None
    if artifact_id is not None:
        roles = _indexed_artifact_roles(index, artifact_id)
    else:
        roles = {
            role
            for role, work in _revision_role_works(connection, parent_id, index).items()
            if child_id is not None and _contains_descendant(connection, work, str(child_id))
        }
    changed = True
    while changed:
        previous_count = len(roles)
        roles.update(
            role
            for role, dependencies in index.edges.items()
            if any(dependency in roles for dependency in dependencies)
        )
        changed = len(roles) != previous_count
    return roles


def _plan_index_at_state_revision(
    connection: sqlite3.Connection,
    parent_id: str,
    state_revision: int,
    plans: dict[str, list[_PlanDependencies | None]],
) -> _PlanDependencies | None:
    row = connection.execute(
        "SELECT max(p.revision) FROM work_plan_revisions p JOIN operations o "
        "ON o.operation_id = p.operation_id WHERE p.parent_id = ? "
        "AND o.state_revision <= ?",
        (parent_id, state_revision),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return _plan_history(connection, parent_id, plans)[int(row[0]) - 1]


def _recorded_evidence_roles(
    connection: sqlite3.Connection,
    parent_id: str,
    state_revision: int,
    artifact_id: UUID,
    obligation_rows: list[tuple[str, str, int, bytes, str, int]],
    plans: dict[str, list[_PlanDependencies | None]],
) -> set[str] | None:
    """Roles whose *then-current* evidence was the deleted Artifact.

    A former role filler may have confirmed X while its replacement later confirmed Y.
    The old X must not seed the replacement's confirmation or downstream bases.
    """

    index = _plan_index_at_state_revision(connection, parent_id, state_revision, plans)
    if index is None:
        return None
    fillers = _revision_role_works(connection, parent_id, index)
    latest: dict[str, tuple[bytes, int]] = {}
    for row_parent, key, _revision, payload, _operation, recorded_at in obligation_rows:
        if row_parent == parent_id and recorded_at <= state_revision:
            previous = latest.get(key)
            if previous is None or recorded_at >= previous[1]:
                latest[key] = (bytes(payload), recorded_at)
    roles: set[str] = set()
    for payload, recorded_at in latest.values():
        if payload == REDACTED_DEPENDENCY:
            continue
        instance = ObligationRevision.model_validate_json(payload)
        if instance.evidence is None or instance.evidence.artifact_id != artifact_id:
            continue
        evidence_index = _plan_index_at_state_revision(connection, parent_id, recorded_at, plans)
        if evidence_index is None:
            return None
        role = instance.definition.role
        if role is None:
            continue
        evidence_filler = _revision_role_works(connection, parent_id, evidence_index).get(role)
        if evidence_filler is not None and fillers.get(role) == evidence_filler:
            roles.add(role)
    changed = True
    while changed:
        previous_count = len(roles)
        roles.update(
            role
            for role, dependencies in index.edges.items()
            if any(dependency in roles for dependency in dependencies)
        )
        changed = len(roles) != previous_count
    return roles


def _copied_obligation_depends(
    connection: sqlite3.Connection,
    parent_id: str,
    source_key: str,
    source_revision: int,
    role: str | None,
    plans: dict[str, list[_PlanDependencies | None]],
    *,
    artifact_id: UUID | None,
    child_id: UUID | None,
    seen: set[tuple[str, int]] | None = None,
) -> bool:
    """A copied basis retains every structural dependency of its exact source."""

    visited = set() if seen is None else seen
    address = (source_key, source_revision)
    if address in visited:
        return True
    visited.add(address)
    row = connection.execute(
        "SELECT payload, operation_id FROM work_obligation_revisions "
        "WHERE parent_id = ? AND key = ? AND revision = ?",
        (parent_id, source_key, source_revision),
    ).fetchone()
    if row is None or bytes(row[0]) == REDACTED_DEPENDENCY:
        return True
    source = ObligationRevision.model_validate_json(bytes(row[0]))
    roles = _recorded_plan_roles(
        connection,
        parent_id,
        row[1],
        plans,
        artifact_id=artifact_id,
        child_id=child_id,
    )
    if roles is None or (bool(roles) if role is None else role in roles):
        return True
    if artifact_id is not None and source.evidence is not None:
        if source.evidence.artifact_id == artifact_id:
            return True
    if source.carried_from_key is not None and source.carried_from_revision is not None:
        return _copied_obligation_depends(
            connection,
            parent_id,
            source.carried_from_key,
            source.carried_from_revision,
            role,
            plans,
            artifact_id=artifact_id,
            child_id=child_id,
            seen=visited,
        )
    return False


def sanitize_deleted_dependency(
    connection: sqlite3.Connection,
    *,
    operation_id: UUID,
    now: str,
    child_id: UUID | None = None,
    artifact_id: UUID | None = None,
) -> None:
    """Remove exact plan/confirmation copies before a referenced subject disappears.

    An obligation revision depends on the subject through its role under the current plan
    and, at schema 7, under the plan revision current when it was recorded.
    """

    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 5:
        return
    if (child_id is None) == (artifact_id is None):
        raise ValueError("Exactly one deleted dependency is required")
    # Schema 7 retires dependent outcome bases in this transaction; schemas 5-6 reach
    # here only when none depends on the deleted subject (``require_outcome_upgrade``).
    dependent_bases = (
        dependent_outcome_bases(connection, artifact_id=artifact_id, work_id=child_id)
        if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 7
        else []
    )
    dependent_rechecks: list[tuple[str, str, int]] = []
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 7:
        from .revalidation import dependent_revalidations

        # Found by the same structural dependencies before any plan is sanitized below.
        dependent_rechecks = dependent_revalidations(
            connection, artifact_id=artifact_id, work_id=child_id
        )
    backup_parents: set[str] = set()
    seed_roles: dict[str, set[str]] = {}
    membership = plan_membership(connection, child_id) if child_id is not None else None

    affected_operations: set[str] = set()
    current_plans: dict[str, WorkPlan | None] = {}
    current_indexes: dict[str, _PlanDependencies | None] = {}
    # The next plan revision can quote a departing node in its rationale. That node is
    # absent from ``children`` but is still addressed by its recorded decision.
    decision_work_revisions = (
        {
            (str(parent), int(revision))
            for parent, revision in connection.execute(
                "SELECT parent_id, plan_revision FROM work_plan_nodes "
                "WHERE work_id = ? OR replaced_work_id = ?",
                (str(child_id), str(child_id)),
            ).fetchall()
        }
        if child_id is not None
        and int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 7
        else set()
    )
    plan_rows = connection.execute(
        "SELECT p.parent_id, p.revision, p.payload, p.operation_id, o.state_revision "
        "FROM work_plan_revisions p JOIN operations o ON o.operation_id = p.operation_id "
        "ORDER BY p.parent_id, p.revision"
    ).fetchall()
    saved_plans: dict[str, list[tuple[bytes, int]]] = {}
    for parent_id, _revision, payload, _source_operation, recorded_at in plan_rows:
        saved_plans.setdefault(parent_id, []).append((bytes(payload), int(recorded_at)))
    for parent_id, revision, payload, source_operation, recorded_at in plan_rows:
        sanitized = _sanitized_plan(bytes(payload))
        if sanitized is not None:
            current_plans[parent_id] = None
            current_indexes[parent_id] = sanitized.dependencies
            continue
        parsed_plan = WorkPlan.model_validate_json(bytes(payload))
        current_plans[parent_id] = parsed_plan
        plan = json.loads(bytes(payload))
        contains_child = child_id is not None and (
            any(
                _contains_descendant(connection, child["work_id"], str(child_id))
                for child in plan["children"]
            )
            or (parent_id, int(revision)) in decision_work_revisions
        )
        contains_artifact = artifact_id is not None and _plan_text_contains_artifact(
            parsed_plan, artifact_id, int(recorded_at), saved_plans
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

    if membership is not None:
        # A deleted child seeds its role under the current plan only while it fills it.
        parent_key, role = str(membership[0]), membership[1]
        current_plan = current_plans.get(parent_key)
        current_index = current_indexes.get(parent_key)
        if current_plan is not None:
            fills = any(
                child.role == role and child.work_id == child_id for child in current_plan.children
            )
        else:
            fills = current_index is None or _revision_role_works(
                connection, parent_key, current_index
            ).get(role) == str(child_id)
        if fills:
            seed_roles.setdefault(parent_key, set()).add(role)
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
        "SELECT r.parent_id, r.key, r.revision, r.payload, r.operation_id, o.state_revision "
        "FROM work_obligation_revisions r JOIN operations o ON o.operation_id = r.operation_id "
        "ORDER BY r.parent_id, r.key, r.revision"
    ).fetchall()
    schema_seven = int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 7
    if artifact_id is not None and not schema_seven:
        # Preserve the schema 5-6 conservative role closure. Schema 7 can resolve
        # historical evidence against the Work filling the role in each revision.
        for parent_id, _key, _revision, payload, _source_operation, _recorded_at in obligation_rows:
            if bytes(payload) == REDACTED_DEPENDENCY:
                continue
            instance = ObligationRevision.model_validate_json(bytes(payload))
            if (
                instance.definition.role is not None
                and instance.evidence is not None
                and instance.evidence.artifact_id == artifact_id
            ):
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
    recorded_plans: dict[str, list[_PlanDependencies | None]] = {}
    for parent_id, key, revision, payload, source_operation, recorded_at in obligation_rows:
        if bytes(payload) == REDACTED_DEPENDENCY:
            continue
        instance = ObligationRevision.model_validate_json(bytes(payload))
        if instance.evidence is None and instance.basis is None:
            continue
        if schema_seven:
            recorded_roles = _recorded_plan_roles(
                connection,
                parent_id,
                source_operation,
                recorded_plans,
                artifact_id=artifact_id,
                child_id=child_id,
            )
            evidence_roles = (
                _recorded_evidence_roles(
                    connection,
                    parent_id,
                    int(recorded_at),
                    artifact_id,
                    obligation_rows,
                    recorded_plans,
                )
                if artifact_id is not None
                else set()
            )
            dependent = (
                (
                    artifact_id is not None
                    and instance.evidence is not None
                    and instance.evidence.artifact_id == artifact_id
                )
                or recorded_roles is None
                or evidence_roles is None
                or instance.definition.role in recorded_roles
                or instance.definition.role in evidence_roles
                or (instance.definition.role is None and bool(recorded_roles))
                or (
                    instance.carried_from_key is not None
                    and instance.carried_from_revision is not None
                    and _copied_obligation_depends(
                        connection,
                        parent_id,
                        instance.carried_from_key,
                        instance.carried_from_revision,
                        instance.definition.role,
                        recorded_plans,
                        artifact_id=artifact_id,
                        child_id=child_id,
                    )
                )
            )
        else:
            dependent_roles_for_key = affected_roles.get(parent_id, set())
            dependent = (
                dependent_roles_for_key is None
                or instance.definition.role in dependent_roles_for_key
            )
        if not dependent:
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
            # Execution reopens and a waiver is taken off; addressed applicability stays.
            reopened = instance.model_copy(
                update={
                    "revision": revision + 1,
                    "status": "open",
                    "evidence": None,
                    "parent_result": None,
                    "basis": None,
                    "operation_id": operation_id,
                    "created_at": datetime.fromisoformat(now),
                    "exception": None,
                    "reopened": None,
                    "carried_from_key": None,
                    "carried_from_revision": None,
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

    for work_id in dependent_bases:
        _retire_outcome_basis(connection, work_id, affected_operations, backup_parents)

    if dependent_rechecks:
        from .revalidation import retire_revalidation_bases

        retire_revalidation_bases(
            connection,
            dependent_rechecks,
            operations=affected_operations,
            subjects=backup_parents,
        )

    _retire_history(connection, affected_operations, backup_parents)


def _retire_history(
    connection: sqlite3.Connection, operations: set[str], subjects: set[str]
) -> None:
    """Retired operations lose receipt and fingerprint; managed backups holding them go."""

    connection.executemany(
        "DELETE FROM receipts WHERE operation_id = ?",
        ((source_operation,) for source_operation in operations),
    )
    connection.executemany(
        "UPDATE operations SET fingerprint = 'DELETED' WHERE operation_id = ?",
        ((source_operation,) for source_operation in operations),
    )
    for subject_id in subjects:
        connection.execute(
            "UPDATE backup_inventory SET status = 'contaminated' "
            "WHERE status IN ('planned', 'failed') OR (status = 'complete' AND backup_id IN "
            "(SELECT backup_id FROM backup_subjects WHERE record_id = ?))",
            (subject_id,),
        )


class _OutcomeDependencies(NamedTuple):
    """Known structural dependencies of one Work's outcome basis."""

    artifacts: frozenset[UUID]
    works: frozenset[str]
    # A pre-index sanitized plan hides its addresses: every deletion counts.
    unbounded: bool


def _held_outcome_bases(
    connection: sqlite3.Connection, work_id: str | None = None
) -> dict[str, int]:
    """Works whose acceptance or closure still holds its basis text.

    Each maps to the space state revision of the operation that recorded the outcome.
    """

    statuses = ("succeeded", *CLOSED_OUTCOMES)
    held: dict[str, int] = {}
    for record_id, payload, state_revision in connection.execute(
        "SELECT c.record_id, c.payload, o.state_revision FROM subject_content c "
        "JOIN subject_revisions v ON v.record_id = c.record_id AND v.revision = c.revision "
        "JOIN subject_records s ON s.record_id = c.record_id "
        "JOIN operations o ON o.operation_id = v.operation_id "
        f"WHERE s.kind = 'work' AND v.status IN ({', '.join('?' for _ in statuses)}) "
        "AND (? IS NULL OR c.record_id = ?)",
        (*statuses, work_id, work_id),
    ).fetchall():
        state = WorkState.model_validate_json(bytes(payload))
        outcome = state.acceptance or state.closure
        if outcome is not None and outcome.basis is not None:
            held[record_id] = min(int(state_revision), held.get(record_id, int(state_revision)))
    return dict(sorted(held.items()))


def _plan_history(
    connection: sqlite3.Connection,
    parent_id: str,
    plans: dict[str, list[_PlanDependencies | None]],
) -> list[_PlanDependencies | None]:
    """Dependency addresses of every plan revision, read from the index once sanitized."""

    if parent_id not in plans:
        history: list[_PlanDependencies | None] = []
        for (payload,) in connection.execute(
            "SELECT payload FROM work_plan_revisions WHERE parent_id = ? ORDER BY revision",
            (parent_id,),
        ).fetchall():
            sanitized = _sanitized_plan(bytes(payload))
            if sanitized is None:
                plan = WorkPlan.model_validate_json(bytes(payload))
                history.append(_plan_dependencies(connection, parent_id, plan))
            else:
                history.append(sanitized.dependencies)
        plans[parent_id] = history
    return plans[parent_id]


def _upstream_roles(edges: dict[str, tuple[str, ...]], role: str) -> set[str]:
    """The role and every role its readiness depends on, transitively."""

    found = {role}
    pending = [role]
    while pending:
        for source in edges.get(pending.pop(), ()):
            if source not in found:
                found.add(source)
                pending.append(source)
    return found


def _evidence_artifacts(
    connection: sqlite3.Connection, parent_id: str, roles: set[str] | None
) -> set[UUID]:
    found: set[UUID] = set()
    for (payload,) in connection.execute(
        "SELECT payload FROM work_obligation_revisions WHERE parent_id = ?", (parent_id,)
    ).fetchall():
        if bytes(payload) == REDACTED_DEPENDENCY:
            continue
        instance = ObligationRevision.model_validate_json(bytes(payload))
        if instance.evidence is not None and (roles is None or instance.definition.role in roles):
            found.add(instance.evidence.artifact_id)
    return found


def _evidence_artifacts_for_fillers(
    connection: sqlite3.Connection,
    parent_id: str,
    role_fillers: dict[str, set[str]],
    plans: dict[str, list[_PlanDependencies | None]],
) -> set[UUID]:
    """Evidence of the Works that filled relevant roles, at its recorded plan revision."""

    found: set[UUID] = set()
    for payload, recorded_at in connection.execute(
        "SELECT r.payload, o.state_revision FROM work_obligation_revisions r "
        "JOIN operations o ON o.operation_id = r.operation_id WHERE r.parent_id = ?",
        (parent_id,),
    ).fetchall():
        if bytes(payload) == REDACTED_DEPENDENCY:
            continue
        instance = ObligationRevision.model_validate_json(bytes(payload))
        if instance.evidence is None or instance.definition.role not in role_fillers:
            continue
        index = _plan_index_at_state_revision(connection, parent_id, int(recorded_at), plans)
        if index is None:
            # A pre-index sanitized plan cannot prove this evidence independent.
            found.add(instance.evidence.artifact_id)
            continue
        evidence_work = _revision_role_works(connection, parent_id, index).get(
            instance.definition.role
        )
        if evidence_work in role_fillers[instance.definition.role]:
            found.add(instance.evidence.artifact_id)
    return found


def _subject_artifacts(connection: sqlite3.Connection, record_id: str) -> set[UUID]:
    """Artifact addresses in every remaining revision of one subject record."""

    found: set[UUID] = set()
    for (payload,) in connection.execute(
        "SELECT payload FROM subject_content WHERE record_id = ?", (record_id,)
    ).fetchall():
        found.update(_artifact_ids(json.loads(bytes(payload))))
    return found


def _subtree_artifacts(
    connection: sqlite3.Connection,
    work_id: str,
    plans: dict[str, list[_PlanDependencies | None]],
) -> tuple[set[UUID], bool]:
    """Artifact addresses of a Work and its saved descendant membership tree.

    A parent plan names an exact child Work, while that child's own inputs, plan
    history, confirmations and further descendants may be the source of its text.
    The same closure is used while writing a retained plan index and while checking
    an outcome, so a first deletion cannot erase a later deletion's addresses.
    """

    found = _subject_artifacts(connection, work_id)
    unbounded = False
    for index in _plan_history(connection, work_id, plans):
        if index is None:
            unbounded = True
            continue
        found.update(index.global_artifacts)
        for references in index.role_artifacts.values():
            found.update(references)
        unbounded |= bool(index.unbounded_roles)
    found.update(_evidence_artifacts(connection, work_id, None))
    for child, _role in _member_rows(connection, work_id):
        child_artifacts, child_unbounded = _subtree_artifacts(connection, child, plans)
        found.update(child_artifacts)
        unbounded |= child_unbounded
    return found, unbounded


def _outcome_dependencies(
    connection: sqlite3.Connection,
    work_id: str,
    plans: dict[str, list[_PlanDependencies | None]],
) -> _OutcomeDependencies:
    """Everything an outcome basis of this Work may quote, by structure and history.

    Every revision of the Work itself (inputs, linked outputs, premises). A composite
    parent also depends on every revision of its own plan, all descendants with their
    revisions, nested plans and confirmation evidence. At each ancestor, a child depends
    on plan revisions that named that exact Work as the role filler: their global
    addresses, its own and upstream roles, and upstream subtrees. Plan revisions are
    read from the retained index once sanitized. A reference absent from the Work state
    does not make the basis independent. Before schema 5 there are no plans: only the
    Work's own revisions count.
    """

    artifacts = _subject_artifacts(connection, work_id)
    works: set[str] = set()
    unbounded = False
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 5:
        return _OutcomeDependencies(frozenset(artifacts), frozenset(works), unbounded)
    own = _plan_history(connection, work_id, plans)
    for index in own:
        if index is None:
            unbounded = True
            continue
        artifacts.update(index.global_artifacts)
        for references in index.role_artifacts.values():
            artifacts.update(references)
        unbounded |= bool(index.unbounded_roles)
    if own:
        for child, _role in _member_rows(connection, work_id):
            works.add(child)
            works.update(_descendant_works(connection, child))
            child_artifacts, child_unbounded = _subtree_artifacts(connection, child, plans)
            artifacts.update(child_artifacts)
            unbounded |= child_unbounded
        artifacts.update(_evidence_artifacts(connection, work_id, None))
    member_id = work_id
    membership = plan_membership(connection, UUID(member_id))
    while membership is not None:
        parent_id, role = str(membership[0]), membership[1]
        artifacts.update(_subject_artifacts(connection, parent_id))
        role_fillers: dict[str, set[str]] = {}
        upstream_works: set[str] = set()
        for index in _plan_history(connection, parent_id, plans):
            if index is None:
                unbounded = True
                continue
            # A plan may name this Work and a basis before it is issued. Include every
            # such revision, but never a revision filled by another Work in the role.
            # Role history also names the Works of upstream roles in that revision.
            fillers = _revision_role_works(connection, parent_id, index)
            if role not in index.roles or fillers.get(role, member_id) != member_id:
                continue
            lineage = _upstream_roles(index.edges, role)
            artifacts.update(index.global_artifacts)
            for member in lineage:
                artifacts.update(index.role_artifacts.get(member, ()))
                unbounded |= member in index.unbounded_roles
                if member in fillers:
                    upstream_works.add(fillers[member])
                    role_fillers.setdefault(member, set()).add(fillers[member])
        for child in sorted(upstream_works - {member_id}):
            works.add(child)
            works.update(_descendant_works(connection, child))
            child_artifacts, child_unbounded = _subtree_artifacts(connection, child, plans)
            artifacts.update(child_artifacts)
            unbounded |= child_unbounded
        artifacts.update(
            _evidence_artifacts_for_fillers(connection, parent_id, role_fillers, plans)
        )
        member_id = parent_id
        membership = plan_membership(connection, UUID(member_id))
    return _OutcomeDependencies(frozenset(artifacts), frozenset(works), unbounded)


def _retire_outcome_basis(
    connection: sqlite3.Connection, work_id: str, operations: set[str], subjects: set[str]
) -> None:
    """Drop the basis text of every outcome revision; outcome and addresses stay."""

    for revision, payload in connection.execute(
        "SELECT revision, payload FROM subject_content WHERE record_id = ?", (work_id,)
    ).fetchall():
        state = WorkState.model_validate_json(bytes(payload))
        if state.acceptance is not None and state.acceptance.basis is not None:
            operation = state.acceptance.operation_id
            retained = state.model_copy(
                update={"acceptance": state.acceptance.model_copy(update={"basis": None})}
            )
        elif state.closure is not None and state.closure.basis is not None:
            operation = state.closure.operation_id
            retained = state.model_copy(
                update={"closure": state.closure.model_copy(update={"basis": None})}
            )
        else:
            continue
        body = canonical_json(retained.model_dump(mode="json")).encode("utf-8")
        connection.execute(
            "UPDATE subject_content SET payload = ?, sha256 = ? "
            "WHERE record_id = ? AND revision = ?",
            (body, hashlib.sha256(body).hexdigest().upper(), work_id, revision),
        )
        operations.add(str(operation))
        subjects.add(work_id)


def dependent_outcome_bases(
    connection: sqlite3.Connection,
    *,
    artifact_id: UUID | None = None,
    work_id: UUID | None = None,
) -> list[str]:
    """Held outcome bases that structurally depend on one Artifact or Work being deleted."""

    plans: dict[str, list[_PlanDependencies | None]] = {}
    dependent: list[str] = []
    for held in _held_outcome_bases(connection):
        if work_id is not None and held == str(work_id):
            continue  # Its whole content is deleted with it.
        found = _outcome_dependencies(connection, held, plans)
        if (
            found.unbounded
            or (artifact_id is not None and artifact_id in found.artifacts)
            or (work_id is not None and str(work_id) in found.works)
        ):
            dependent.append(held)
    return dependent


def require_outcome_upgrade(
    connection: sqlite3.Connection,
    *,
    artifact_id: UUID | None = None,
    work_id: UUID | None = None,
) -> None:
    """Schemas 2-6 cannot retire a basis, so such a deletion waits for the explicit upgrade.

    Called before the deleting operation changes anything; the schema is never upgraded
    implicitly. A subject that is already gone is left to the ordinary exact checks.
    """

    if artifact_id is not None:
        row = connection.execute(
            "SELECT status FROM records WHERE record_id = ? AND kind = 'artifact'",
            (str(artifact_id),),
        ).fetchone()
        target = f"Artifact {artifact_id}"
    else:
        row = connection.execute(
            "SELECT status FROM subject_records WHERE record_id = ? AND kind = 'work'",
            (str(work_id),),
        ).fetchone()
        target = f"Work {work_id}"
    if row is None or row[0] == "deleted":
        return
    dependent = dependent_outcome_bases(connection, artifact_id=artifact_id, work_id=work_id)
    if dependent:
        raise FoundationError(
            "upgrade_required",
            f"Deleting {target} needs the explicit schema 7 upgrade first: it would retire "
            f"the outcome basis of {', '.join(f'Work {item}' for item in dependent)}",
        )


def _deleted_subjects(connection: sqlite3.Connection) -> tuple[dict[UUID, int], dict[str, int]]:
    """State revision of every Artifact and Work deletion; its revision row stays."""

    artifacts = {
        UUID(record_id): int(state_revision)
        for record_id, state_revision in connection.execute(
            "SELECT v.record_id, o.state_revision FROM record_revisions v "
            "JOIN records r ON r.record_id = v.record_id "
            "JOIN operations o ON o.operation_id = v.operation_id "
            "WHERE r.kind = 'artifact' AND v.status = 'deleted'"
        ).fetchall()
    }
    works = {
        record_id: int(state_revision)
        for record_id, state_revision in connection.execute(
            "SELECT v.record_id, o.state_revision FROM subject_revisions v "
            "JOIN subject_records s ON s.record_id = v.record_id "
            "JOIN operations o ON o.operation_id = v.operation_id "
            "WHERE s.kind = 'work' AND v.status = 'deleted'"
        ).fetchall()
    }
    return artifacts, works


def _retained_bases(connection: sqlite3.Connection, work_id: str | None = None) -> list[str]:
    """Held bases with a structural dependency deleted after the outcome was recorded.

    Schema 7 retires such a basis in the deleting transaction. Code before this rule left
    it on schemas 2-6, so only the explicit upgrade to 7 can retire it. The recorded order
    of the two operations decides only this retrospective sanitation: a basis recorded
    after the deletion stays, as schema 7 keeps it. The order does not prove that its text
    holds no copy of the deleted content; such a quote is an uncovered case.
    """

    deleted_artifacts, deleted_works = _deleted_subjects(connection)
    if not deleted_artifacts and not deleted_works:
        return []
    plans: dict[str, list[_PlanDependencies | None]] = {}
    retained: list[str] = []
    for held, recorded in _held_outcome_bases(connection, work_id).items():
        later_artifacts = {item for item, at in deleted_artifacts.items() if at > recorded}
        later_works = {item for item, at in deleted_works.items() if at > recorded}
        if not later_artifacts and not later_works:
            continue
        found = _outcome_dependencies(connection, held, plans)
        if found.unbounded or found.artifacts & later_artifacts or found.works & later_works:
            retained.append(held)
    return retained


def retained_outcome_bases(connection: sqlite3.Connection) -> tuple[UUID, ...]:
    """Addresses of Works whose basis still holds text an earlier deletion needed gone."""

    return tuple(UUID(work_id) for work_id in _retained_bases(connection))


def outcome_basis_retained(connection: sqlite3.Connection, work_id: UUID) -> bool:
    """Whether reads of this Work must withhold its basis until the explicit upgrade."""

    return bool(_retained_bases(connection, str(work_id)))


def retained_outcome_operation(connection: sqlite3.Connection, operation_id: UUID) -> UUID | None:
    """The Work whose retained basis this recording operation carries, if any."""

    statuses = ("succeeded", *CLOSED_OUTCOMES)
    row = connection.execute(
        "SELECT v.record_id FROM subject_revisions v "
        "JOIN subject_records s ON s.record_id = v.record_id "
        "WHERE v.operation_id = ? AND s.kind = 'work' "
        f"AND v.status IN ({', '.join('?' for _ in statuses)})",
        (str(operation_id), *statuses),
    ).fetchone()
    if row is None or not _retained_bases(connection, row[0]):
        return None
    return UUID(row[0])


def retire_bases_of_deleted_dependencies(connection: sqlite3.Connection) -> list[str]:
    """Retire outcome bases that earlier deletions on schemas 2-6 had to leave in place.

    Older schemas cannot represent a retired basis, so the explicit upgrade to 7 finishes
    those earlier deletions exactly as schema 7 would have at the time; ``complete_deletions``
    then purges backups and compacts. Returns the addresses of the retired Works.
    """

    operations: set[str] = set()
    subjects: set[str] = set()
    for work_id in _retained_bases(connection):
        _retire_outcome_basis(connection, work_id, operations, subjects)
    _retire_history(connection, operations, subjects)
    return sorted(subjects)


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


def _plan_text_contains_artifact(
    plan: WorkPlan,
    artifact_id: UUID,
    recorded_at: int,
    saved_plans: dict[str, list[tuple[bytes, int]]],
) -> bool:
    """A plan may quote nested plan text already present when it was recorded.

    Later child outputs and confirmations can affect outcome and confirmation bases,
    but could not have been copied into this earlier plan revision. Read the saved
    nested plan payloads from before this deletion starts, including same-operation
    nested creation, rather than the descendant's current state.
    """

    if artifact_id in _artifact_ids(plan.model_dump(mode="json")):
        return True
    for child in plan.children:
        for payload, nested_at in saved_plans.get(str(child.work_id), ()):
            if nested_at > recorded_at:
                continue
            sanitized = _sanitized_plan(payload)
            if sanitized is not None:
                index = sanitized.dependencies
                if index is None or _indexed_artifact_roles(index, artifact_id):
                    return True
            elif _plan_text_contains_artifact(
                WorkPlan.model_validate_json(payload), artifact_id, recorded_at, saved_plans
            ):
                return True
    return False


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
    unbounded_roles: set[str] = set()
    histories: dict[str, list[_PlanDependencies | None]] = {}
    for child in plan.children:
        edges[child.role] = tuple(
            sorted({leaf.role for leaf in _conditions(child.readiness) if leaf.role is not None})
        )
        references = _artifact_ids(child.state.model_dump(mode="json"))
        if child.readiness is not None:
            references.update(_artifact_ids(child.readiness.model_dump(mode="json")))
        references.update(_current_subject_artifacts(connection, str(child.work_id)))
        descendant_artifacts, unbounded = _subtree_artifacts(
            connection, str(child.work_id), histories
        )
        references.update(descendant_artifacts)
        if unbounded:
            unbounded_roles.add(child.role)
        role_artifacts[child.role] = tuple(sorted(references))
    return _PlanDependencies(
        roles=tuple(child.role for child in plan.children),
        edges=edges,
        global_artifacts=tuple(sorted(global_artifacts)),
        role_artifacts=role_artifacts,
        unbounded_roles=tuple(sorted(unbounded_roles)),
        # Earlier schemas keep their exact sanitized payload bytes.
        role_works=(
            {child.role: child.work_id for child in plan.children}
            if _schema(connection) >= 7
            else None
        ),
    )


def _revision_role_works(
    connection: sqlite3.Connection, parent_id: str, index: _PlanDependencies
) -> dict[str, str]:
    """The Work filling each role of one plan revision, read from its index.

    An index written before role history names no Works; then every role still had its
    one original member, which a later revision never rewrites.
    """

    if index.role_works is not None:
        return {role: str(work) for role, work in index.role_works.items()}
    originals = _original_members(connection, parent_id)
    return {role: originals[role] for role in index.roles if role in originals}


def _original_members(connection: sqlite3.Connection, parent_id: str) -> dict[str, str]:
    return {
        str(role): str(child)
        for child, role in connection.execute(
            "SELECT child_id, role FROM work_plan_children WHERE parent_id = ?", (parent_id,)
        ).fetchall()
    }


def revision_role_works(
    connection: sqlite3.Connection, parent_id: UUID, payload: bytes
) -> dict[str, str]:
    """Role to Work of one stored plan revision: its content, retained index or members.

    A redacted plan from before the index names no roles; before role history every role
    had its one original member.
    """

    sanitized = _sanitized_plan(payload)
    if sanitized is None:
        plan = WorkPlan.model_validate_json(payload)
        return {child.role: str(child.work_id) for child in plan.children}
    if sanitized.dependencies is None:
        return _original_members(connection, str(parent_id))
    return _revision_role_works(connection, str(parent_id), sanitized.dependencies)


def current_role_works(connection: sqlite3.Connection, parent_id: UUID) -> dict[str, str]:
    """Role to Work of the parent's current plan revision; empty without a plan."""

    row = connection.execute(
        "SELECT payload FROM work_plan_revisions WHERE parent_id = ? "
        "ORDER BY revision DESC LIMIT 1",
        (str(parent_id),),
    ).fetchone()
    return {} if row is None else revision_role_works(connection, parent_id, bytes(row[0]))


def _indexed_artifact_roles(index: _PlanDependencies, artifact_id: UUID) -> set[str]:
    if artifact_id in index.global_artifacts:
        return set(index.roles)
    return set(index.unbounded_roles) | {
        role for role, references in index.role_artifacts.items() if artifact_id in references
    }


def _legacy_plan_roles(connection: sqlite3.Connection, parent_id: str) -> set[str]:
    """Old redacted plans lack an index; preserve deletion safety conservatively."""

    return {role for _child, role in _member_rows(connection, parent_id)}


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
        row = connection.execute(
            "SELECT operation_id, created_at, actor, status FROM method_versions "
            "WHERE method_id = ? AND version = ?",
            (str(ref.method_id), ref.version),
        ).fetchone()
        if row is None:
            raise FoundationError("method_unavailable", "Exact Method version is unavailable")
        if row[3] == "deleted":
            raise FoundationError("content_unavailable", "Exact Method version was deleted")
        definition = _method(connection, ref)
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


def read_parent_plan_pin(
    path: Path, work_id: UUID, attempt_id: UUID, authority: LocalAuthority
) -> ParentPlanPin:
    """Read the exact own-plan pin, including a historical fenced Attempt."""

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 8 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Parent pins need active schema 8")
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="work",
            resource_id=work_id,
        )
        return _parent_pin(connection, attempt_id, work_id)


def read_parent_output_proof(
    path: Path, artifact_id: UUID, authority: LocalAuthority
) -> ParentOutputProof:
    """Read one exact publication address without making old evidence current."""

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 8 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Parent proofs need active schema 8")
        row = connection.execute(
            "SELECT artifact_revision, work_id, slot, attempt_id, plan_revision, method_id, "
            "method_version, method_checksum, operation_id FROM parent_output_proofs "
            "WHERE artifact_id = ?",
            (str(artifact_id),),
        ).fetchone()
        if row is None:
            raise FoundationError("not_found", "Parent publication proof is unavailable")
        work_id = UUID(row[1])
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="work",
            resource_id=work_id,
        )
        return ParentOutputProof(
            work_id=work_id,
            slot=row[2],
            artifact=ArtifactRef(artifact_id=artifact_id, revision=int(row[0])),
            attempt_id=UUID(row[3]),
            plan_revision=int(row[4]),
            method=MethodRef(method_id=UUID(row[5]), version=int(row[6]), checksum=row[7]),
            operation_id=UUID(row[8]),
        )
