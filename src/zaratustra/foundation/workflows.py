"""Versioned workflow templates over the ordinary WorkPlan and effect authority.

Run rows contain addresses, control intent and receipts. Work, Attempt and exact
validation evidence determine progress; there is no independently mutable graph.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from contextvars import ContextVar
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4, uuid5

from pydantic import ValidationError

from .models import (
    AnswerWaitRequest,
    ApplyCandidateRequest,
    ArtifactRef,
    AssignAttemptRequest,
    ChangeApplication,
    ChangeCandidateState,
    CreateArtifactRequest,
    CreateCompositeWorkRequest,
    CreateMethodVersionRequest,
    CreateResourceRequest,
    DomainRequest,
    IssueChildWorkRequest,
    KnowledgeRef,
    LinkedOutput,
    LinkWorkOutputRequest,
    MethodDefinition,
    MethodRef,
    NodeClosure,
    OutputContract,
    ParentOutputSlot,
    PlanChild,
    PlanCondition,
    PlanNodeDecision,
    PublishAttemptOutputRequest,
    RecordAttemptStopRequest,
    RecordChangeOutcomeRequest,
    RequestAttemptStopRequest,
    ResourceState,
    RestoreCandidateRequest,
    ReviseActivePlanRequest,
    SetupValidationIssue,
    SpaceInfo,
    StopCandidateRequest,
    WorkflowChange,
    WorkflowDefinition,
    WorkflowModel,
    WorkflowNode,
    WorkflowNodeResult,
    WorkflowNodeView,
    WorkflowRef,
    WorkflowRequest,
    WorkflowRunView,
    WorkflowWait,
    WorkPlan,
    WorkState,
)
from .operations import LocalAuthority, _authorize, _local_space, _subject_current, _subject_state
from .storage import (
    WORKFLOW_REBUILD_TABLES,
    WORKFLOW_SCHEMA_NAME,
    WORKFLOW_SCHEMA_SHA256,
    WORKFLOW_SCHEMA_STATEMENTS,
    FoundationError,
    _begin,
    _connect,
    _space_info,
    canonical_json,
    layout,
    read_space,
    space_connection,
    utc_now,
)

HOST_PUBLICATION: ContextVar[bool] = ContextVar("workflow_host_publication", default=False)
WORKFLOW_CORE_OPERATIONS = frozenset(
    (
        "describe_structure",
        "read_format",
        "read_entry",
        "history",
        "create_entry",
        "correct_entry",
        "ingest_batch",
        "start_procedure",
        "query_entries",
        "working_set",
        "aggregate_entries",
    )
)


def workflow_checksum(definition: WorkflowDefinition) -> str:
    return (
        hashlib.sha256(canonical_json(definition.model_dump(mode="json")).encode())
        .hexdigest()
        .upper()
    )


def upgrade_workflow_space(path: Path, authority: LocalAuthority) -> SpaceInfo:
    """Explicit 15 to 16 upgrade; reading never upgrades and old payloads stay intact."""
    root, database, _ = layout(path)
    with closing(_connect(database, writable=True)) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        _begin(connection, writable=True)
        info = _space_info(connection, root, database)
        _local_space(authority, info)
        if info.recovery_state != "active" or info.schema_version < 15:
            raise FoundationError("upgrade_required", "Workflows require active schema 15")
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.backup",
            epoch=info.execution_epoch,
        )
        if info.schema_version == 15:
            for name, definition in WORKFLOW_REBUILD_TABLES.items():
                columns = ",".join(
                    row[1] for row in connection.execute(f"PRAGMA table_info({name})")
                )
                indexes = [
                    row[0]
                    for row in connection.execute(
                        "SELECT sql FROM sqlite_schema WHERE type='index' AND tbl_name=? "
                        "AND sql IS NOT NULL",
                        (name,),
                    )
                ]
                replacement = name + "_schema16"
                connection.execute(
                    definition.replace(f"CREATE TABLE {name} ", f"CREATE TABLE {replacement} ")
                )
                connection.execute(
                    f"INSERT INTO {replacement} ({columns}) SELECT {columns} FROM {name}"
                )
                connection.execute(f"DROP TABLE {name}")
                connection.execute(f"ALTER TABLE {replacement} RENAME TO {name}")
                for index in indexes:
                    connection.execute(index)
            for statement in WORKFLOW_SCHEMA_STATEMENTS:
                connection.execute(statement)
            now = utc_now().isoformat()
            connection.execute(
                "INSERT INTO schema_migrations VALUES (16,?,?,?)",
                (WORKFLOW_SCHEMA_NAME, WORKFLOW_SCHEMA_SHA256, now),
            )
            connection.execute("PRAGMA user_version=16")
            connection.execute(
                "UPDATE spaces SET state_revision=state_revision+1 WHERE singleton=1"
            )
            connection.execute(
                "INSERT INTO maintenance_events VALUES (?,'schema_upgrade',?,?)",
                (str(uuid4()), now, canonical_json({"from": 15, "to": 16})),
            )
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise FoundationError(
                "corrupt_space", "Workflow upgrade failed foreign key verification"
            )
        connection.execute("COMMIT")
    return read_space(path)


def _schema(connection: sqlite3.Connection) -> None:
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 16:
        raise FoundationError("upgrade_required", "Workflows require explicit schema 16")


def _definition(
    connection: sqlite3.Connection, ref: WorkflowRef, *, active: bool = True
) -> WorkflowDefinition:
    row = connection.execute(
        "SELECT checksum,status,payload FROM workflow_versions WHERE workflow_id=? AND version=?",
        (str(ref.workflow_id), ref.version),
    ).fetchone()
    if row is None:
        raise FoundationError("not_found", "Workflow version is absent")
    if row[2] is None or row[1] == "deleted":
        raise FoundationError("content_unavailable", "Workflow definition lost its basis")
    definition = WorkflowDefinition.model_validate_json(row[2])
    if row[0] != ref.checksum or workflow_checksum(definition) != row[0]:
        raise FoundationError("corrupt_content", "Workflow checksum differs")
    if active and row[1] != "active":
        raise FoundationError("workflow_not_adopted", "Workflow needs its Candidate and Decision")
    return definition


def _no_recursion(
    connection: sqlite3.Connection, identifier: UUID, definition: WorkflowDefinition
) -> None:
    def visit(candidate: WorkflowDefinition, held: set[UUID]) -> None:
        for node in candidate.nodes:
            if node.workflow is None:
                continue
            if node.workflow.workflow_id in held:
                raise FoundationError("workflow_recursion", "Nested workflows cannot recurse")
            visit(_definition(connection, node.workflow), held | {node.workflow.workflow_id})

    visit(definition, {identifier})


def _definition_contracts(
    connection: sqlite3.Connection,
    definition: WorkflowDefinition,
    actor: str,
    epoch: int,
    scopes: tuple[UUID, ...] = (),
) -> None:
    from .composition import _method, _validate_plan
    from .development import check_new_method_use

    def check_plan(plan: WorkPlan, method_ref: MethodRef, activity_id: UUID) -> None:
        method = _method(connection, method_ref)
        if method.required_capabilities:
            raise FoundationError("unsupported_condition", "Method capabilities are not connected")
        _validate_plan(plan, method, activity_id, schema=16, allow_nested=True)
        for scope in scopes or (activity_id,):
            _authorize(
                connection,
                actor=actor,
                action="method.use",
                epoch=epoch,
                resource_type="activity",
                resource_id=scope,
            )
            check_new_method_use(connection, method_ref.method_id, method_ref.version, scope)
        for child in plan.children:
            if isinstance(child.state.method, MethodRef):
                if child.nested_plan is None:
                    raise FoundationError(
                        "incomplete_context", "Nested Method needs its exact child plan"
                    )
                check_plan(child.nested_plan, child.state.method, activity_id)

    for node in definition.nodes:
        if node.method is not None:
            assert node.plan is not None
            activity_id = node.plan.children[0].state.activity_id
            check_plan(node.plan, node.method, activity_id)
        if node.workflow is not None:
            nested = _definition(connection, node.workflow)
            for scope in scopes:
                _adopted(connection, node.workflow, actor, epoch, scope)
            _definition_contracts(connection, nested, actor, epoch, scopes)


def _store_definition(
    connection: sqlite3.Connection, request: WorkflowRequest, now: str, *, system: bool = False
) -> WorkflowRef:
    if request.definition is None or request.workflow_id is None:
        raise FoundationError("invalid_request", "Definition needs identifier and typed template")
    from .capabilities import ProcedureOperation

    if not set(request.definition.allowed_operations).issubset(set(ProcedureOperation)):
        raise FoundationError(
            "unsupported_operation", "Workflow operation is absent from public catalog"
        )
    for node in request.definition.nodes:
        if node.kind == "core" and node.operation not in WORKFLOW_CORE_OPERATIONS:
            raise FoundationError(
                "unsupported_operation", "Operation is not registered for a typed Core node"
            )
    _no_recursion(connection, request.workflow_id, request.definition)
    _definition_contracts(
        connection,
        request.definition,
        request.actor,
        int(connection.execute("SELECT execution_epoch FROM spaces").fetchone()[0]),
    )
    existing = connection.execute(
        "SELECT max(version) FROM workflow_versions WHERE workflow_id=?",
        (str(request.workflow_id),),
    ).fetchone()[0]
    if request.version != (existing or 0) + 1:
        raise FoundationError("stale_workflow", "Workflow versions must be consecutive")
    ref = WorkflowRef(
        workflow_id=request.workflow_id,
        version=request.version,
        checksum=workflow_checksum(request.definition),
    )
    connection.execute(
        "INSERT INTO workflow_versions VALUES (?,?,?,?,?,?,?,?)",
        (
            str(ref.workflow_id),
            ref.version,
            ref.checksum,
            "active" if system else "proposed",
            request.definition.model_dump_json().encode(),
            str(request.operation_id),
            now,
            request.actor,
        ),
    )
    return ref


def _run(
    connection: sqlite3.Connection, root: UUID
) -> tuple[WorkflowRef, int, str, tuple[KnowledgeRef, ...]]:
    row = connection.execute(
        "SELECT workflow_id,version,checksum,revision,control,sources FROM workflow_runs WHERE "
        "root_work_id=?",
        (str(root),),
    ).fetchone()
    if row is None:
        raise FoundationError("not_found", "Workflow run is absent")
    sources = tuple(KnowledgeRef.model_validate(item) for item in json.loads(row[5] or "[]"))
    return (
        WorkflowRef(workflow_id=UUID(row[0]), version=row[1], checksum=row[2]),
        row[3],
        row[4],
        sources,
    )


def _readable(connection: sqlite3.Connection, root: UUID, actor: str, epoch: int) -> None:
    _authorize(
        connection,
        actor=actor,
        action="record.read",
        epoch=epoch,
        resource_type="work",
        resource_id=root,
    )
    revision, _status, _ = _subject_current(connection, root, "work")
    _subject_state(connection, root, revision)
    from .activity_setup import _basis

    for ref in _run(connection, root)[3]:
        _basis(connection, ref, actor, epoch)
    workflow_ref = _run(connection, root)[0]
    _, _, activity = _subject_current(connection, root, "work")
    _adopted(connection, workflow_ref, actor, epoch, UUID(activity))


def _adopted(
    connection: sqlite3.Connection,
    ref: WorkflowRef,
    actor: str,
    epoch: int,
    activity_id: UUID | None = None,
    *,
    new_use: bool = False,
) -> None:
    """Current admission, scope and transitive bases are checked before every use/read."""
    from .development import _current, _references
    from .models import ChangeDecisionState

    rows = connection.execute(
        "SELECT candidate_id,candidate_revision,decision_id,decision_revision,scope_activity_id "
        "FROM workflow_adoptions WHERE workflow_id=? AND version=? "
        + (
            "AND application_id IN (SELECT application_id FROM change_packages WHERE "
            "status='active')"
            if new_use
            else ""
        ),
        (str(ref.workflow_id), ref.version),
    )
    found = False
    for candidate_id, candidate_revision, decision_id, decision_revision, scope in rows:
        if activity_id is not None and scope is not None and scope != str(activity_id):
            continue
        found = True
        _authorize(
            connection,
            actor=actor,
            action="record.read",
            epoch=epoch,
            resource_type="activity" if scope else "space",
            resource_id=UUID(scope) if scope else None,
        )
        _authorize(
            connection,
            actor=actor,
            action="record.read",
            epoch=epoch,
            resource_type="artifact",
            resource_id=UUID(candidate_id),
        )
        current, candidate = _current(connection, UUID(candidate_id))
        if current != candidate_revision or not isinstance(candidate, ChangeCandidateState):
            raise FoundationError("stale_candidate", "Workflow admission proposal changed")
        row = connection.execute(
            "SELECT r.current_revision,v.body_json FROM records r JOIN record_revisions v ON "
            "v.record_id=r.record_id AND v.revision=r.current_revision WHERE r.record_id=?",
            (decision_id,),
        ).fetchone()
        if row is None or row[0] != decision_revision:
            raise FoundationError("stale_basis", "Workflow admission Decision changed")
        decision = ChangeDecisionState.model_validate_json(row[1])
        if decision.status != "active":
            raise FoundationError("permission_denied", "Workflow admission was revoked")
        for _, basis in _references(candidate):
            # Development validation handles Artifact refs as well as Knowledge originals.
            from .knowledge import _require_ref

            _require_ref(connection, basis, actor, epoch)
        _definition_contracts(
            connection,
            _definition(connection, ref),
            actor,
            epoch,
            (activity_id,) if activity_id else (UUID(scope),) if scope else (),
        )
        return
    if not found:
        system = UUID("93e4b5c2-f5cc-52d4-8828-559898c329ba")
        if ref.workflow_id != system:
            raise FoundationError("workflow_not_adopted", "No current adoption in this Activity")


def _effect(
    connection: sqlite3.Connection,
    request: WorkflowRequest,
    kind: type[Any],
    *,
    now: str,
    epoch: int,
    authority: LocalAuthority,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
    **fields: Any,
) -> dict[str, Any]:
    from .operations import _apply_change, _operation_action

    nested = kind(
        operation_id=request.operation_id, space_id=request.space_id, actor=request.actor, **fields
    )
    action, resource_type, resource_id = _operation_action(nested)
    g, d = _authorize(
        connection,
        actor=request.actor,
        action=action,
        epoch=epoch,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    grants.extend(g)
    decisions.extend(d)
    result, _ = _apply_change(
        connection,
        cast(DomainRequest, nested),
        now=now,
        epoch=epoch,
        authority=authority,
        grants=grants,
        decisions=decisions,
    )
    return result


def _nodes(connection: sqlite3.Connection, root: UUID) -> tuple[WorkflowNodeView, ...]:
    result = []
    from .composition import _plan

    plan_exists = connection.execute(
        "SELECT 1 FROM work_plan_revisions WHERE parent_id=? LIMIT 1", (str(root),)
    ).fetchone()
    current_works = (
        {str(child.work_id) for child in _plan(connection, root).plan.children}
        if plan_exists
        else set()
    )
    for key, iteration, role, work, packet, packet_revision, model in connection.execute(
        "SELECT node_key,iteration,role,work_id,packet_id,packet_revision,model FROM "
        "workflow_nodes WHERE root_work_id=? ORDER BY rowid",
        (str(root),),
    ):
        row = connection.execute(
            "SELECT validation_id,artifact_id,artifact_revision,issues FROM "
            "workflow_validations WHERE root_work_id=? AND work_id=? ORDER BY rowid DESC LIMIT "
            "1",
            (str(root), work),
        ).fetchone()
        issues = (
            tuple(SetupValidationIssue.model_validate(item) for item in json.loads(row[3] or "[]"))
            if row
            else ()
        )
        raw_output = None
        exists = connection.execute(
            "SELECT 1 FROM subject_records WHERE record_id=?", (work,)
        ).fetchone()
        if row is None and exists:
            current = _subject_current(connection, UUID(work), "work")[0]
            body = WorkState.model_validate(_subject_state(connection, UUID(work), current))
            raw_output = next(
                (item.artifact for item in body.linked_outputs if item.slot == "report"), None
            )
        result.append(
            WorkflowNodeView(
                key=key,
                iteration=iteration,
                role=role,
                work_id=UUID(work),
                packet=ArtifactRef(artifact_id=UUID(packet), revision=packet_revision),
                model=WorkflowModel.model_validate_json(model) if model else None,
                output=ArtifactRef(artifact_id=UUID(row[1]), revision=row[2])
                if row
                else raw_output,
                validation_id=UUID(row[0]) if row and not issues else None,
                issues=issues,
                retired=bool(plan_exists and exists and work not in current_works),
            )
        )
    return tuple(result)


def _waits(
    connection: sqlite3.Connection, root: UUID, *, all_answers: bool = False
) -> tuple[WorkflowWait, ...]:
    result = []
    sql = (
        "SELECT "
        "wait_id,node_key,work_id,revision,kind,question,purpose,expected_actor,bases,answer "
        "FROM workflow_waits WHERE root_work_id=? AND closed=0"
    )
    if not all_answers:
        sql += " AND answer IS NULL"
    for row in connection.execute(sql + " ORDER BY rowid", (str(root),)):
        if row[5] is None or row[6] is None:
            raise FoundationError("content_unavailable", "Workflow interaction was retired")
        result.append(
            WorkflowWait(
                wait_id=UUID(row[0]),
                node_key=row[1],
                work_id=UUID(row[2]),
                revision=row[3],
                kind=row[4],
                question=row[5],
                purpose=row[6],
                expected_actor=row[7],
                bases=tuple(
                    KnowledgeRef.model_validate(item) for item in json.loads(row[8] or "[]")
                ),
                answer=KnowledgeRef.model_validate_json(row[9]) if row[9] else None,
                root_work_id=root,
            )
        )
    return tuple(result)


def _descendant_runs(connection: sqlite3.Connection, root: UUID) -> tuple[UUID, ...]:
    from .composition import _plan

    result = []
    for child in _plan(connection, root).plan.children:
        if connection.execute(
            "SELECT 1 FROM workflow_runs WHERE root_work_id=?", (str(child.work_id),)
        ).fetchone():
            result.append(child.work_id)
            result.extend(_descendant_runs(connection, child.work_id))
    return tuple(result)


def _work_family(connection: sqlite3.Connection, work: UUID) -> tuple[UUID, ...]:
    """Current native graph members, including issued Method descendants."""
    from .composition import _plan

    found = [work]
    if connection.execute(
        "SELECT 1 FROM work_plan_revisions WHERE parent_id=? LIMIT 1", (str(work),)
    ).fetchone():
        for child in _plan(connection, work).plan.children:
            found.extend(_work_family(connection, child.work_id))
    return tuple(dict.fromkeys(found))


def _native_waits(
    connection: sqlite3.Connection, root: UUID, actor: str, epoch: int, *, all_answers: bool = False
) -> tuple[WorkflowWait, ...]:
    results = []
    for node in _nodes(connection, root):
        if node.retired:
            continue
        for work in _work_family(connection, node.work_id):
            _authorize(
                connection,
                actor=actor,
                action="record.read",
                epoch=epoch,
                resource_type="work",
                resource_id=work,
            )
            rows = connection.execute(
                "SELECT "
                "w.wait_id,w.attempt_id,w.revision,w.status,w.question,w.expected_actor,"
                "w.created_at,a.session_id,w.answer,n.answer FROM execution_waits w JOIN "
                "execution_attempts a ON a.attempt_id=w.attempt_id LEFT JOIN "
                "workflow_native_answers n ON n.wait_id=w.wait_id WHERE w.work_id=? AND "
                "w.status IN ('open','answered','closed') ORDER BY w.created_at",
                (str(work),),
            )
            for (
                wait,
                attempt,
                revision,
                status,
                question,
                expected,
                _created,
                session,
                old_answer,
                retained,
            ) in rows:
                if question is None or (old_answer or retained) and not all_answers:
                    continue
                if (
                    status == "closed"
                    and not retained
                    and connection.execute(
                        "SELECT 1 FROM execution_invocations WHERE attempt_id=? AND "
                        "status IN ('sent','unknown')",
                        (attempt,),
                    ).fetchone()
                ):
                    continue
                results.append(
                    WorkflowWait(
                        wait_id=UUID(wait),
                        node_key=node.key,
                        work_id=work,
                        revision=revision,
                        kind="question",
                        question=bytes(question).decode("utf-8")
                        if isinstance(question, bytes)
                        else question,
                        purpose="Continue the exact interrupted Method work"
                        if status == "closed"
                        else "Answer the assigned Method executor",
                        expected_actor=expected,
                        root_work_id=root,
                        native=True,
                        attempt_id=UUID(attempt),
                        session_id=UUID(session),
                        answer=KnowledgeRef.model_validate_json(retained) if retained else None,
                    )
                )
    return tuple(results)


def _validation_leaf(node: WorkflowNodeView) -> PlanCondition:
    if node.validation_id is None or node.output is None:
        raise FoundationError("dependency_open", "Workflow dependency has no valid result")
    return PlanCondition(
        kind="validated_internal_output",
        role=node.role,
        slot="report",
        media_type="text/plain",
        artifact=node.output,
        validation_id=node.validation_id,
    )


def _transition_current(
    connection: sqlite3.Connection, root: UUID, validation_id: UUID, key: str
) -> bool:
    from .composition import _plan

    current = {str(child.work_id) for child in _plan(connection, root).plan.children}
    return any(
        row[0] in current
        for row in connection.execute(
            "SELECT target_work_id FROM workflow_transitions WHERE validation_id=? AND node_key=?",
            (str(validation_id), key),
        )
    )


def validate_internal_output(
    connection: sqlite3.Connection,
    plan: WorkPlan,
    condition: PlanCondition,
    *,
    actor: str | None,
    epoch: int,
) -> ArtifactRef:
    """Exact service evidence cannot substitute for accepted_output/work_succeeded."""
    assert condition.role and condition.artifact and condition.validation_id
    child = next((item for item in plan.children if item.role == condition.role), None)
    if child is None:
        raise FoundationError("dependency_open", "Validated producer is absent from this plan")
    row = connection.execute(
        "SELECT "
        "root_work_id,work_id,work_revision,artifact_id,artifact_revision,inputs_sha256,issues "
        "FROM workflow_validations WHERE validation_id=?",
        (str(condition.validation_id),),
    ).fetchone()
    if (
        row is None
        or row[1] != str(child.work_id)
        or row[3:5] != (str(condition.artifact.artifact_id), condition.artifact.revision)
        or row[6] not in (None, "[]")
    ):
        raise FoundationError(
            "invalid_internal_validation", "Validation does not match exact producer and output"
        )
    current, status, _ = _subject_current(connection, child.work_id, "work")
    if status != "proposed" and status != "succeeded":
        raise FoundationError("dependency_closed", "Validated producer was closed")
    state = WorkState.model_validate(_subject_state(connection, child.work_id, current))
    digest = (
        hashlib.sha256(
            canonical_json([item.model_dump(mode="json") for item in state.inputs]).encode()
        )
        .hexdigest()
        .upper()
    )
    if digest != row[5] or not any(
        item.slot == condition.slot and item.artifact == condition.artifact
        for item in state.linked_outputs
    ):
        raise FoundationError("stale_basis", "Validated producer inputs or output changed")
    if isinstance(state.method, MethodRef):
        from .composition import _evaluate, _obligations, _parent_current

        definition, own_plan = _parent_current(
            connection,
            child.work_id,
            state,
            actor=actor,
            epoch=epoch,
            grants=[],
            decisions=[],
        )
        _evaluate(
            connection,
            own_plan.plan,
            own_plan.plan.completion,
            work_id=child.work_id,
            actor=actor,
            epoch=epoch,
            grants=[],
            decisions=[],
        )
        if any(
            item.status not in ("satisfied", "waived") and item.applicability == "active"
            for item in _obligations(connection, child.work_id, definition)
        ):
            raise FoundationError("obligation_open", "Method needs its ordinary evidence")
    root_ref = _run(connection, UUID(row[0]))[0]
    node_row = connection.execute(
        "SELECT node_key FROM workflow_nodes WHERE work_id=?", (str(child.work_id),)
    ).fetchone()
    spec = next(
        (
            entry
            for entry in _definition(connection, root_ref).nodes
            if node_row and entry.key == node_row[0]
        ),
        None,
    )
    if spec and spec.kind == "nested":
        value_row = connection.execute(
            "SELECT result FROM workflow_validations WHERE validation_id=?",
            (str(condition.validation_id),),
        ).fetchone()
        nested_result = WorkflowNodeResult.model_validate_json(value_row[0])
        nested_id = UUID(str(nested_result.values["nested_root_work_id"]))
        nested_revision = _subject_current(connection, nested_id, "work")[0]
        nested_work = WorkState.model_validate(
            _subject_state(connection, nested_id, nested_revision)
        )
        for output in nested_work.linked_outputs:
            proof = connection.execute(
                "SELECT work_id,plan_revision FROM parent_output_proofs WHERE artifact_id=? "
                "AND artifact_revision=?",
                (str(output.artifact.artifact_id), output.artifact.revision),
            ).fetchone()
            from .composition import _plan

            if (
                proof is None
                or proof[0] != str(nested_id)
                or proof[1] != _plan(connection, nested_id).revision
            ):
                raise FoundationError(
                    "stale_basis", "Nested completion lost its exact root producer proof"
                )
        if actor:
            _readable(connection, nested_id, actor, epoch)
    from .composition import _current_artifact

    _current_artifact(
        connection, condition.artifact, actor=actor, epoch=epoch, grants=[], decisions=[]
    )
    for ref in state.inputs:
        _current_artifact(connection, ref, actor=actor, epoch=epoch, grants=[], decisions=[])
    if actor is not None:
        _readable(connection, UUID(row[0]), actor, epoch)
        _authorize(
            connection,
            actor=actor,
            action="record.read",
            epoch=epoch,
            resource_type="work",
            resource_id=child.work_id,
        )
    return condition.artifact


def _packet(
    connection: sqlite3.Connection,
    root: UUID,
    node: WorkflowNode,
    sources: tuple[KnowledgeRef, ...],
    actor: str,
    epoch: int,
) -> dict[str, Any]:
    from .activity_setup import _artifact, _basis

    latest = {item.key: item for item in _nodes(connection, root) if not item.retired}
    dependencies = []
    for key in node.dependencies:
        dependency = latest.get(key)
        if dependency is None or dependency.output is None or dependency.validation_id is None:
            raise FoundationError("dependency_open", f"Node {key} has no validated result")
        dependencies.append(
            {
                "node": key,
                "ref": dependency.output.model_dump(mode="json"),
                "text": _artifact(connection, dependency.output, actor, epoch).decode("utf-8"),
            }
        )
    interactions = []
    for wait in _waits(connection, root, all_answers=True):
        interactions.append(
            {
                "question": wait.question,
                "purpose": wait.purpose,
                "answer": _basis(connection, wait.answer, actor, epoch) if wait.answer else None,
            }
        )
    packet = {
        "workflow": _run(connection, root)[0].model_dump(mode="json"),
        "node": node.model_dump(mode="json"),
        "sources": [_basis(connection, ref, actor, epoch) for ref in sources],
        "dependencies": dependencies,
        "interactions": interactions,
        "result_schema": WorkflowNodeResult.model_json_schema(),
    }
    if node.method:
        from .composition import _method

        _authorize(
            connection,
            actor=actor,
            action="method.use",
            epoch=epoch,
            resource_type="space",
            resource_id=None,
        )
        method = _method(connection, node.method)
        packet["method"] = {
            "ref": node.method.model_dump(mode="json"),
            "definition": method.model_dump(mode="json"),
        }
    previous = latest.get(node.key)
    if previous and previous.output:
        packet["previous_result"] = {
            "ref": previous.output.model_dump(mode="json"),
            "text": _artifact(connection, previous.output, actor, epoch).decode("utf-8"),
            "issues": [item.model_dump(mode="json") for item in previous.issues],
        }
    return packet


def _create_node(
    connection: sqlite3.Connection,
    request: WorkflowRequest,
    node: WorkflowNode,
    *,
    now: str,
    epoch: int,
    authority: LocalAuthority,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
    initial_sources: tuple[KnowledgeRef, ...] | None = None,
    continuation: bool = False,
) -> PlanChild:
    assert request.root_work_id and request.activity_id
    root = request.root_work_id
    existing = _nodes(connection, root)
    iteration = 1 + max((item.iteration for item in existing if item.key == node.key), default=0)
    semantic_iterations = 0
    for item in existing:
        if (
            item.key == node.key
            and not item.retired
            and item.validation_id is not None
            and not item.issues
        ):
            raw = connection.execute(
                "SELECT result FROM workflow_validations WHERE validation_id=?",
                (str(item.validation_id),),
            ).fetchone()
            if (
                raw
                and raw[0]
                and WorkflowNodeResult.model_validate_json(raw[0]).outcome == "result"
            ):
                semantic_iterations += 1
    if (
        not continuation
        and semantic_iterations >= node.max_iterations
        and not any(
            item.key == node.key and (item.issues or item.output is None) for item in existing
        )
    ):
        raise FoundationError(
            "workflow_iterations_exhausted", f"Node {node.key} reached its saved limit"
        )
    role = node.key if iteration == 1 else f"{node.key}-{iteration}"
    if len(role) > 80:
        raise FoundationError("invalid_workflow", "Iteration role exceeds the WorkPlan contract")
    work = uuid5(root, f"node:{node.key}:{iteration}")
    packet_id = uuid5(work, "packet")
    sources = initial_sources if initial_sources is not None else _run(connection, root)[3]
    packet = _packet(connection, root, node, sources, request.actor, epoch)
    common: dict[str, Any] = dict(
        now=now, epoch=epoch, authority=authority, grants=grants, decisions=decisions
    )
    _effect(
        connection,
        request,
        CreateArtifactRequest,
        artifact_id=packet_id,
        media_type="application/json",
        content=canonical_json(packet).encode(),
        **common,
    )
    latest = {item.key: item for item in existing}
    leaves = tuple(_validation_leaf(latest[key]) for key in node.dependencies)
    readiness = PlanCondition(kind="all", members=leaves) if leaves else None
    nested_plan = None
    if node.method is not None:
        from .composition import _method

        definition = _method(connection, node.method)
        if definition.named_outputs != (OutputContract(slot="report", media_type="text/plain"),):
            raise FoundationError(
                "method_mismatch", "Workflow model Method must declare one text/plain report"
            )
        assert node.plan is not None

        def instantiate(template: WorkPlan, parent: UUID) -> WorkPlan:
            children = []
            for child in template.children:
                identifier = uuid5(parent, "method-role:" + child.role)
                body = child.state.model_copy(update={"activity_id": request.activity_id})
                children.append(
                    child.model_copy(
                        update={
                            "work_id": identifier,
                            "state": body,
                            "nested_plan": instantiate(child.nested_plan, identifier)
                            if child.nested_plan
                            else None,
                        }
                    )
                )
            named = tuple(
                item.model_copy(update={"artifact": ArtifactRef(artifact_id=packet_id, revision=1)})
                if item.slot == node.input_slot
                else item
                for item in template.named_inputs
            )
            return template.model_copy(update={"children": tuple(children), "named_inputs": named})

        nested_plan = instantiate(node.plan, work)
    state = WorkState(
        activity_id=request.activity_id,
        goal=node.instruction[:4096],
        inputs=tuple(item.artifact for item in nested_plan.named_inputs)
        if nested_plan
        else (ArtifactRef(artifact_id=packet_id, revision=1),),
        method=node.method or "none",
        expected_outputs=definition.named_outputs
        if node.method
        else (OutputContract(slot="report", media_type="text/plain", allow_empty=True),),
    )
    connection.execute(
        "INSERT INTO workflow_nodes VALUES (?,?,?,?,?,?,?,NULL)",
        (str(root), node.key, iteration, role, str(work), str(packet_id), 1),
    )
    connection.execute(
        "INSERT OR IGNORE INTO workflow_edges VALUES (?,'packet',?,1)", (str(root), str(packet_id))
    )
    return PlanChild(
        role=role, work_id=work, state=state, readiness=readiness, nested_plan=nested_plan
    )


def _event(
    connection: sqlite3.Connection,
    request: WorkflowRequest,
    revision: int,
    now: str,
    detail: dict[str, Any],
) -> None:
    assert request.root_work_id
    connection.execute(
        "UPDATE workflow_runs SET revision=? WHERE root_work_id=?",
        (revision, str(request.root_work_id)),
    )
    connection.execute(
        "INSERT INTO workflow_events VALUES (?,?,?,?,?,?)",
        (
            str(request.root_work_id),
            revision,
            str(request.operation_id),
            request.action,
            canonical_json(detail),
            now,
        ),
    )


def _host_result(
    connection: sqlite3.Connection,
    request: WorkflowRequest,
    node: WorkflowNodeView,
    result: WorkflowNodeResult,
    *,
    now: str,
    epoch: int,
    authority: LocalAuthority,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> None:
    """Retain and link a Core executor's result; never fabricate a provider invocation."""
    assert request.root_work_id
    common: dict[str, Any] = dict(
        now=now, epoch=epoch, authority=authority, grants=grants, decisions=decisions
    )
    base = request.model_copy(
        update={
            "action": "bind_node",
            "node_key": node.key,
            "expected_revision": _run(connection, request.root_work_id)[1],
        }
    )
    apply_workflow_change(connection, base, **common)
    identifier = uuid5(request.operation_id, "host-output")
    _effect(
        connection,
        request,
        CreateArtifactRequest,
        artifact_id=identifier,
        media_type="text/plain",
        content=result.model_dump_json().encode(),
        **common,
    )
    revision = _subject_current(connection, node.work_id, "work")[0]
    _effect(
        connection,
        request,
        LinkWorkOutputRequest,
        work_id=node.work_id,
        expected_revision=revision,
        output=LinkedOutput(
            slot="report", artifact=ArtifactRef(artifact_id=identifier, revision=1)
        ),
        **common,
    )
    validate = request.model_copy(
        update={
            "action": "validate_output",
            "node_key": node.key,
            "output": ArtifactRef(artifact_id=identifier, revision=1),
            "expected_revision": _run(connection, request.root_work_id)[1],
        }
    )
    apply_workflow_change(connection, validate, **common)


def _core_result(
    connection: sqlite3.Connection, node: WorkflowNode, actor: str, epoch: int, activity_id: UUID
) -> dict[str, Any]:
    """Finite registered read operations share the current transaction and rights."""
    from .data_store import exact_state, head_ref

    if node.operation == "describe_structure":
        _authorize(
            connection,
            actor=actor,
            action="record.read",
            epoch=epoch,
            resource_type="activity",
            resource_id=activity_id,
        )
        ref = head_ref(connection, activity_id)
        return {
            "activity_id": str(activity_id),
            "structure": ref.model_dump(mode="json") if ref else None,
            "state": exact_state(connection, ref, actor, epoch).model_dump(mode="json")
            if ref
            else None,
        }
    if node.operation in ("read_format", "read_entry"):
        raw = node.operation_arguments.get("ref")
        if raw is None:
            raise FoundationError("invalid_request", "Read operation requires its exact ref")
        ref = KnowledgeRef.model_validate(raw)
        value = exact_state(connection, ref, actor, epoch)
        expected = "data_format" if node.operation == "read_format" else "data_entry"
        if value.kind != expected:
            raise FoundationError("wrong_kind", "Core node address names the wrong kind")
        return {"ref": ref.model_dump(mode="json"), "state": value.model_dump(mode="json")}
    if node.operation == "history":
        ref = KnowledgeRef.model_validate(node.operation_arguments.get("ref"))
        from .activity_setup import _basis

        _basis(connection, ref, actor, epoch, current=False)
        return {
            "revisions": [
                row[0]
                for row in connection.execute(
                    "SELECT revision FROM knowledge_revisions WHERE record_id=? AND revision>? "
                    "ORDER BY revision LIMIT ?",
                    (
                        str(ref.record_id),
                        int(cast(Any, node.operation_arguments.get("after", 0))),
                        min(int(cast(Any, node.operation_arguments.get("limit", 25))), 100),
                    ),
                )
            ]
        }
    if node.operation in ("query_entries", "working_set", "aggregate_entries"):
        from .memory import _Reader, _rows
        from .models import ActivityStructureState, DataEntryState, MemorySelector

        args = node.operation_arguments
        selectors = tuple(
            MemorySelector.model_validate(item)
            for item in cast(list[Any], args.get("selectors", []))
        )
        if node.operation == "working_set":
            ref = head_ref(connection, activity_id)
            if ref is None:
                raise FoundationError("structure_required", "No admitted Activity structure")
            structure = exact_state(connection, ref, actor, epoch)
            assert isinstance(structure, ActivityStructureState)
            working = next(
                (item for item in structure.working_sets if item.key == args.get("key")), None
            )
            if working is None:
                raise FoundationError("not_found", "Working set is absent")
            selectors = working.selectors
        selectors = tuple(
            item.model_copy(
                update={
                    "current_activity": False,
                    "activity_ids": (activity_id,),
                    "kinds": ("data_entry",),
                }
            )
            for item in selectors
        )
        if not selectors:
            raise FoundationError("invalid_query", "Choose a finite typed selector")
        limit = int(cast(Any, args.get("limit", 25)))
        if not 1 <= limit <= 100:
            raise FoundationError("invalid_query", "Host query page is between 1 and 100")
        reader = _Reader(actor, epoch)
        entries: list[dict[str, Any]] = []
        complete = True
        for row in _rows(connection, reader, selectors, after=str(args.get("cursor") or "")):
            if len(entries) == limit:
                complete = False
                break
            ref = KnowledgeRef(record_id=UUID(row[0]), revision=row[1])
            entry = exact_state(connection, ref, actor, epoch)
            if isinstance(entry, DataEntryState):
                entries.append(
                    {"ref": ref.model_dump(mode="json"), "state": entry.model_dump(mode="json")}
                )
        if node.operation == "aggregate_entries":
            from decimal import Decimal

            operation = args.get("calculation", "count")
            if operation not in ("count", "sum", "min", "max", "mean"):
                raise FoundationError("unsupported_query", "Unsupported host aggregation")
            values = [
                Decimal(str(item["state"]["values"][str(args.get("field"))]))
                for item in entries
                if item["state"]["values"].get(str(args.get("field"))) is not None
            ]
            aggregate_value = (
                len(entries)
                if operation == "count"
                else sum(values)
                if operation == "sum"
                else min(values)
                if operation == "min" and values
                else max(values)
                if operation == "max" and values
                else sum(values) / len(values)
                if operation == "mean" and values
                else None
            )
            if not complete:
                raise FoundationError(
                    "selection_incomplete",
                    "Aggregate requires an explicitly complete bounded selection",
                )
            return {
                "value": str(aggregate_value) if aggregate_value is not None else None,
                "entries": [item["ref"] for item in entries],
                "complete": True,
            }
        return {
            "entries": entries,
            "complete": complete,
            "limit": limit,
            "next_cursor": entries[-1]["ref"]["record_id"] if not complete and entries else None,
        }
    raise FoundationError(
        "unsupported_operation", "This capability is not registered for atomic host nodes"
    )


def _require_idle(connection: sqlite3.Connection, root: UUID) -> None:
    descendants = _work_family(connection, root)
    ids = canonical_json([str(item) for item in descendants])
    unknown = connection.execute(
        "SELECT 1 FROM execution_invocations WHERE work_id IN (SELECT value FROM "
        "json_each(?)) AND status IN ('sent','unknown') LIMIT 1",
        (ids,),
    ).fetchone()
    if unknown:
        raise FoundationError("unknown_outcome", "A sent call has no known outcome; do not replay")
    active = connection.execute(
        "SELECT 1 FROM execution_assignments WHERE work_id IN (SELECT value FROM "
        "json_each(?)) AND status IN "
        "('assigned','waiting','ready','stop_requested','unknown') LIMIT 1",
        (ids,),
    ).fetchone()
    if active:
        raise FoundationError(
            "workflow_running", "Stop the assigned executor before replacing its inputs"
        )


def _fresh_owner_source(
    connection: sqlite3.Connection, ref: KnowledgeRef, actor: str, epoch: int, after: str
) -> None:
    from .activity_setup import _basis

    value = _basis(connection, ref, actor, epoch)["state"]
    created = connection.execute(
        "SELECT created_at FROM knowledge_revisions WHERE record_id=? AND revision=?",
        (str(ref.record_id), ref.revision),
    ).fetchone()
    if (
        value.get("kind") != "source"
        or value.get("channel") != "conversation_user"
        or value.get("sender") != actor
        or created is None
        or created[0] <= after
    ):
        raise FoundationError(
            "invalid_answer_source", "Use a new original owner message for this action"
        )


def _replace_from_node(
    connection: sqlite3.Connection,
    request: WorkflowRequest,
    key: str,
    definition: WorkflowDefinition,
    *,
    now: str,
    epoch: int,
    authority: LocalAuthority,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> None:
    """Keep exact history, cancel affected proposals and materialize a fresh first step."""
    from .composition import _conditions, _plan

    assert request.root_work_id and request.activity_id
    root = request.root_work_id
    common: dict[str, Any] = dict(
        now=now, epoch=epoch, authority=authority, grants=grants, decisions=decisions
    )
    plan = _plan(connection, root)
    nodes = tuple(item for item in _nodes(connection, root) if not item.retired)
    affected_keys = {key}
    changed = True
    while changed:
        changed = False
        for declared_node in definition.nodes:
            if declared_node.key not in affected_keys and set(
                declared_node.dependencies
            ).intersection(affected_keys):
                affected_keys.add(declared_node.key)
                changed = True
    affected_works = {item.work_id for item in nodes if item.key in affected_keys}
    affected_roles = {child.role for child in plan.plan.children if child.work_id in affected_works}
    changed = True
    while changed:
        changed = False
        for child in plan.plan.children:
            if child.work_id not in affected_works and any(
                leaf.role in affected_roles for leaf in _conditions(child.readiness)
            ):
                affected_works.add(child.work_id)
                affected_roles.add(child.role)
                changed = True
    for item in nodes:
        if item.work_id in affected_works:
            spec = next(entry for entry in definition.nodes if entry.key == item.key)
            if spec.kind in ("core", "nested") and item.output is not None:
                raise FoundationError(
                    "effect_mapping_required",
                    "Performed effects need an explicit compatible version transfer",
                )
            revision, status, _ = _subject_current(connection, item.work_id, "work")
            if status == "succeeded":
                raise FoundationError(
                    "accepted_result_mapping_required",
                    "Keep accepted Work and start a separate explicit continuation",
                )
    replacement = _create_node(
        connection,
        request,
        next(item for item in definition.nodes if item.key == key),
        continuation=True,
        **common,
    )
    kept = tuple(child for child in plan.plan.children if child.work_id not in affected_works)
    next_plan = plan.plan.model_copy(update={"children": kept + (replacement,), "completion": None})
    dispositions = tuple(
        PlanNodeDecision(
            role=child.role,
            work_id=child.work_id,
            decision="cancel",
            closure=NodeClosure(
                expected_revision=_subject_current(connection, child.work_id, "work")[0],
                outcome="cancelled",
                basis="The owner corrected an addressed input; keep the old result as history",
            ),
        )
        if child.work_id in affected_works
        else PlanNodeDecision(role=child.role, work_id=child.work_id, decision="keep")
        for child in plan.plan.children
    ) + (
        PlanNodeDecision(
            role=replacement.role,
            work_id=replacement.work_id,
            decision="add",
            nested_plan=replacement.nested_plan,
        ),
    )
    _effect(
        connection,
        request,
        ReviseActivePlanRequest,
        work_id=root,
        expected_plan_revision=plan.revision,
        expected_work_revision=_subject_current(connection, root, "work")[0],
        plan=next_plan,
        nodes=dispositions,
        **common,
    )
    connection.execute(
        "UPDATE workflow_runs SET control='running' WHERE root_work_id=?", (str(root),)
    )


def apply_workflow_change(
    connection: sqlite3.Connection,
    request: WorkflowRequest,
    *,
    now: str,
    epoch: int,
    authority: LocalAuthority,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, Any], list[dict[str, object]]]:
    _schema(connection)
    common: dict[str, Any] = dict(
        now=now, epoch=epoch, authority=authority, grants=grants, decisions=decisions
    )
    if request.action == "create_definition":
        created_ref = _store_definition(connection, request, now)
        return {"workflow": created_ref.model_dump(mode="json"), "adopted": False}, [
            {"record_id": str(created_ref.workflow_id), "revision": created_ref.version}
        ]
    if request.root_work_id is None:
        raise FoundationError("invalid_request", "Run needs its exact root Work")
    root = request.root_work_id
    if request.action == "start":
        if request.workflow is None or request.activity_id is None:
            raise FoundationError("invalid_request", "Start requires adopted workflow and Activity")
        definition = _definition(connection, request.workflow)
        _adopted(
            connection, request.workflow, request.actor, epoch, request.activity_id, new_use=True
        )
        _definition_contracts(connection, definition, request.actor, epoch, (request.activity_id,))
        if connection.execute(
            "SELECT 1 FROM workflow_runs WHERE root_work_id=?", (str(root),)
        ).fetchone():
            raise FoundationError("record_exists", "Continue this existing workflow run")
        from .activity_setup import _basis
        from .composition import method_checksum

        for ref in request.source_refs:
            _basis(connection, ref, request.actor, epoch)
        method_id = uuid5(root, "workflow-method")
        method = MethodDefinition(
            instruction=definition.purpose,
            named_inputs=definition.inputs,
            named_outputs=definition.outputs,
            source_ref=f"workflow:{request.workflow.workflow_id}@{request.workflow.version}",
        )
        _effect(
            connection,
            request,
            CreateMethodVersionRequest,
            method_id=method_id,
            version=1,
            definition=method,
            **common,
        )
        connection.execute(
            "INSERT INTO workflow_runs VALUES (?,?,?,?,1,'running',?,?)",
            (
                str(root),
                str(request.workflow.workflow_id),
                request.workflow.version,
                request.workflow.checksum,
                canonical_json([ref.model_dump(mode="json") for ref in request.source_refs]),
                str(request.operation_id),
            ),
        )
        children = tuple(
            _create_node(connection, request, node, **common, initial_sources=request.source_refs)
            for node in definition.nodes
            if node.key in definition.entry_nodes
        )
        plan = WorkPlan(
            named_inputs=request.inputs,
            parent_outputs=tuple(
                ParentOutputSlot(slot=output.slot, media_type=output.media_type)
                for output in definition.outputs
            ),
            children=children,
            rationale=definition.purpose,
            source_ref="workflow-initial-plan",
        )
        parent = WorkState(
            activity_id=request.activity_id,
            goal=definition.purpose,
            method=MethodRef(method_id=method_id, version=1, checksum=method_checksum(method)),
            inputs=tuple(item.artifact for item in request.inputs),
            expected_outputs=definition.outputs,
        )
        _effect(
            connection,
            request,
            CreateCompositeWorkRequest,
            work_id=root,
            state=parent,
            plan=plan,
            **common,
        )
        _event(connection, request, 1, now, {"workflow": request.workflow.model_dump(mode="json")})
        for ref in request.source_refs:
            connection.execute(
                "INSERT OR IGNORE INTO workflow_edges VALUES (?,'basis',?,?)",
                (str(root), str(ref.record_id), ref.revision),
            )
        return {"root_work_id": str(root), "revision": 1}, [{"record_id": str(root), "revision": 1}]
    workflow, revision, control, sources = _run(connection, root)
    if revision != request.expected_revision:
        raise FoundationError("stale_workflow_run", "Workflow run revision changed")
    _readable(connection, root, request.actor, epoch)
    definition = _definition(connection, workflow)
    work_revision, work_status, activity = _subject_current(connection, root, "work")
    if control == "cancelled" or work_status != "proposed":
        raise FoundationError("workflow_closed", "Workflow run is closed")
    if control == "paused" and request.action not in (
        "resume",
        "cancel",
        "correct_answer",
        "migrate",
        "retry",
        "answer",
    ):
        raise FoundationError("workflow_paused", "Explicit continuation is required")
    request = request.model_copy(update={"activity_id": UUID(activity)})
    nodes = _nodes(connection, root)
    node = next(
        (
            item
            for item in reversed(nodes)
            if item.key == request.node_key
            and (request.iteration is None or request.iteration == item.iteration)
        ),
        None,
    )
    declared = next((item for item in definition.nodes if item.key == request.node_key), None)
    detail: dict[str, Any] = {}
    if request.action in ("bind_node", "validate_output", "ask") and (
        node is None or declared is None
    ):
        raise FoundationError("not_found", "Node is absent from the current WorkPlan")
    if request.action == "bind_node":
        assert node and declared
        if node.model is not None and request.model != node.model:
            raise FoundationError(
                "stale_node_model", "An already bound node keeps its model choice"
            )
        if declared.kind == "model" and request.model is None:
            raise FoundationError(
                "invalid_request", "Model node needs selected provider/profile/reasoning"
            )
        _authorize(
            connection,
            actor=request.actor,
            action="work.execute",
            epoch=epoch,
            resource_type="work",
            resource_id=node.work_id,
        )
        from .composition import _plan

        plan_revision = _plan(connection, root).revision
        child_revision = _subject_current(connection, node.work_id, "work")[0]
        from .composition import original_issue

        issue = original_issue(connection, node.work_id)
        if issue is None or issue[1] is None:
            _effect(
                connection,
                request,
                IssueChildWorkRequest,
                parent_work_id=root,
                work_id=node.work_id,
                expected_plan_revision=plan_revision,
                expected_work_revision=child_revision,
                **common,
            )
        connection.execute(
            "UPDATE workflow_nodes SET model=? WHERE work_id=?",
            (request.model.model_dump_json() if request.model else None, str(node.work_id)),
        )
        detail = {"work_id": str(node.work_id), "packet": node.packet.model_dump(mode="json")}
    elif request.action == "validate_output":
        assert node and declared
        if request.output is None:
            raise FoundationError("invalid_request", "Validation needs exact retained output")
        from .activity_setup import _artifact
        from .data_formats import validate_values

        raw = _artifact(connection, request.output, request.actor, epoch)
        child_revision = _subject_current(connection, node.work_id, "work")[0]
        state = WorkState.model_validate(_subject_state(connection, node.work_id, child_revision))
        if not any(
            item.artifact == request.output and item.slot == "report"
            for item in state.linked_outputs
        ):
            raise FoundationError("stale_basis", "Output was not published by this node Work")
        result = None
        issues: tuple[SetupValidationIssue, ...] = ()
        try:
            result = WorkflowNodeResult.model_validate_json(raw)
            if result.outcome == "result" and declared.result_fields:
                validate_values(declared.result_fields, result.values)
            if not set(result.next_nodes).issubset(set(declared.successors)):
                raise FoundationError(
                    "invalid_transition", "Result selects an undeclared successor"
                )
        except ValidationError as error:
            from .setup_validation import validation_issues

            issues = validation_issues(error)
        except FoundationError as error:
            issues = (
                SetupValidationIssue(code=error.code, path=("values",), message=error.detail),
            )
        inputs_sha = (
            hashlib.sha256(
                canonical_json([ref.model_dump(mode="json") for ref in state.inputs]).encode()
            )
            .hexdigest()
            .upper()
        )
        contract_sha = hashlib.sha256(declared.model_dump_json().encode()).hexdigest().upper()
        connection.execute(
            "INSERT INTO workflow_validations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(request.operation_id),
                str(root),
                str(node.work_id),
                child_revision,
                str(request.output.artifact_id),
                request.output.revision,
                inputs_sha,
                contract_sha,
                result.model_dump_json() if result else None,
                canonical_json([item.model_dump(mode="json") for item in issues]),
                now,
            ),
        )
        connection.execute(
            "INSERT OR IGNORE INTO workflow_edges VALUES (?,'output',?,?)",
            (str(root), str(request.output.artifact_id), request.output.revision),
        )
        detail = {
            "validation_id": str(request.operation_id),
            "issues": [item.model_dump(mode="json") for item in issues],
        }
    elif request.action == "ask":
        assert node
        if not request.question or not request.purpose:
            raise FoundationError("invalid_request", "Interaction needs exact question and purpose")
        if _waits(connection, root) and any(
            wait.work_id == node.work_id for wait in _waits(connection, root)
        ):
            raise FoundationError("wait_open", "Answer this node's existing question")
        from .activity_setup import _basis

        for ref in request.source_refs:
            _basis(connection, ref, request.actor, epoch)
        wait_id = request.wait_id or uuid5(request.operation_id, "host-wait")
        connection.execute(
            "INSERT INTO workflow_waits VALUES (?,?,?, ?,1,?,?,?,?,?,NULL,?,0)",
            (
                str(wait_id),
                str(root),
                str(node.work_id),
                node.key,
                request.interaction_kind,
                request.question,
                request.purpose,
                request.actor,
                canonical_json([ref.model_dump(mode="json") for ref in request.source_refs]),
                str(request.operation_id),
            ),
        )
        detail = {"wait_id": str(wait_id), "wait_revision": 1}
    elif request.action == "correct_answer":
        _require_idle(connection, root)
        if request.wait_id is None or request.answer is None:
            raise FoundationError(
                "invalid_request", "Correction needs the addressed answer and new owner Source"
            )
        wait = next(
            (
                item
                for item in _waits(connection, root, all_answers=True)
                if item.wait_id == request.wait_id
            ),
            None,
        )
        if wait is None or wait.answer is None or wait.revision != request.expected_wait_revision:
            raise FoundationError("stale_wait", "Correct the exact saved answered interaction")
        after = connection.execute(
            "SELECT committed_at FROM operations WHERE operation_id=(SELECT operation_id "
            "FROM workflow_waits WHERE wait_id=?)",
            (str(wait.wait_id),),
        ).fetchone()[0]
        _fresh_owner_source(connection, request.answer, request.actor, epoch, after)
        from .activity_setup import _basis

        for corrected_basis in (request.answer,) + request.source_refs:
            _basis(connection, corrected_basis, request.actor, epoch)
            connection.execute(
                "INSERT OR IGNORE INTO workflow_edges VALUES (?,'basis',?,?)",
                (str(root), str(corrected_basis.record_id), corrected_basis.revision),
            )
        all_sources = tuple(dict.fromkeys(sources + (request.answer,) + request.source_refs))
        connection.execute(
            "UPDATE workflow_runs SET sources=? WHERE root_work_id=?",
            (canonical_json([ref.model_dump(mode="json") for ref in all_sources]), str(root)),
        )
        connection.execute(
            "UPDATE workflow_waits SET answer=?,revision=revision+1 WHERE wait_id=?",
            (request.answer.model_dump_json(), str(wait.wait_id)),
        )
        _replace_from_node(connection, request, wait.node_key, definition, **common)
        detail = {
            "wait_id": str(wait.wait_id),
            "previous_answer": wait.answer.model_dump(mode="json"),
            "answer": request.answer.model_dump(mode="json"),
        }
    elif request.action == "retry":
        _require_idle(connection, root)
        if node is None or request.answer is None:
            raise FoundationError(
                "invalid_request", "Explicit retry needs a node and fresh owner request"
            )
        last = connection.execute(
            "SELECT o.committed_at FROM workflow_events e JOIN operations o ON "
            "o.operation_id=e.operation_id WHERE e.root_work_id=? ORDER BY e.revision DESC "
            "LIMIT 1",
            (str(root),),
        ).fetchone()[0]
        _fresh_owner_source(connection, request.answer, request.actor, epoch, last)
        connection.execute(
            "INSERT OR IGNORE INTO workflow_edges VALUES (?,'basis',?,?)",
            (str(root), str(request.answer.record_id), request.answer.revision),
        )
        connection.execute(
            "UPDATE workflow_runs SET sources=? WHERE root_work_id=?",
            (
                canonical_json(
                    [
                        ref.model_dump(mode="json")
                        for ref in tuple(dict.fromkeys(sources + (request.answer,)))
                    ]
                ),
                str(root),
            ),
        )
        connection.execute(
            "INSERT INTO workflow_recovery_boundaries VALUES (?,?,?,?) ON "
            "CONFLICT(root_work_id,node_key) DO UPDATE SET "
            "iteration=excluded.iteration,operation_id=excluded.operation_id",
            (str(root), node.key, node.iteration, str(request.operation_id)),
        )
        _replace_from_node(connection, request, node.key, definition, **common)
        detail = {"retry_node": node.key, "request_source": request.answer.model_dump(mode="json")}
    elif request.action == "answer":
        if request.wait_id is None or request.answer is None:
            raise FoundationError(
                "invalid_request", "Answer requires exact wait and original user Source"
            )
        native_wait = next(
            (
                entry
                for scoped in (root,) + _descendant_runs(connection, root)
                for entry in _native_waits(connection, scoped, request.actor, epoch)
                if entry.wait_id == request.wait_id
            ),
            None,
        )
        if native_wait:
            if (
                native_wait.revision != request.expected_wait_revision
                or native_wait.expected_actor != request.actor
            ):
                raise FoundationError(
                    "stale_wait", "Answer the exact native wait as its expected owner"
                )
            raw_wait = connection.execute(
                "SELECT status,created_at,remainder,partial_refs_json FROM "
                "execution_waits WHERE wait_id=?",
                (str(native_wait.wait_id),),
            ).fetchone()
            _fresh_owner_source(connection, request.answer, request.actor, epoch, raw_wait[1])
            from .activity_setup import _artifact, _basis

            source_value = _basis(connection, request.answer, request.actor, epoch)
            answer_text = source_value["state"].get("text")
            if not answer_text:
                raise FoundationError(
                    "invalid_answer_source", "Native continuation needs retained answer bytes"
                )
            native_result: dict[str, Any] = {}
            if raw_wait[0] == "open":
                native_result = _effect(
                    connection,
                    request,
                    AnswerWaitRequest,
                    wait_id=native_wait.wait_id,
                    attempt_id=native_wait.attempt_id,
                    work_id=native_wait.work_id,
                    session_id=native_wait.session_id,
                    expected_wait_revision=native_wait.revision,
                    answer=answer_text,
                    **common,
                )
            else:
                _require_idle(connection, root)
            partials = tuple(ArtifactRef.model_validate(item) for item in json.loads(raw_wait[3]))
            for partial in partials:
                _artifact(connection, partial, request.actor, epoch)
            packet_id = uuid5(request.operation_id, "native-continuation")
            packet = {
                "wait_id": str(native_wait.wait_id),
                "work_id": str(native_wait.work_id),
                "attempt_id": str(native_wait.attempt_id),
                "wait_revision": native_wait.revision,
                "question": native_wait.question,
                "answer": source_value,
                "remainder": bytes(raw_wait[2]).decode("utf-8")
                if isinstance(raw_wait[2], bytes)
                else raw_wait[2],
                "partial_refs": [item.model_dump(mode="json") for item in partials],
            }
            _effect(
                connection,
                request,
                CreateArtifactRequest,
                artifact_id=packet_id,
                media_type="application/json",
                content=canonical_json(packet).encode(),
                **common,
            )
            connection.execute(
                "INSERT INTO workflow_native_answers VALUES (?,?,?,?,?,1,?)",
                (
                    str(root),
                    str(native_wait.wait_id),
                    str(native_wait.work_id),
                    request.answer.model_dump_json(),
                    str(packet_id),
                    str(request.operation_id),
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO workflow_edges VALUES (?,'packet',?,1)",
                (str(root), str(packet_id)),
            )
            connection.execute(
                "INSERT OR IGNORE INTO workflow_edges VALUES (?,'basis',?,?)",
                (str(root), str(request.answer.record_id), request.answer.revision),
            )
            connection.execute(
                "UPDATE workflow_runs SET sources=? WHERE root_work_id=?",
                (
                    canonical_json(
                        [
                            entry.model_dump(mode="json")
                            for entry in tuple(dict.fromkeys(sources + (request.answer,)))
                        ]
                    ),
                    str(root),
                ),
            )
            detail = {
                **native_result,
                "wait_id": str(native_wait.wait_id),
                "native": True,
                "continuation_packet": ArtifactRef(artifact_id=packet_id, revision=1).model_dump(
                    mode="json"
                ),
            }
            _event(connection, request, revision + 1, now, detail)
            return {"root_work_id": str(root), "revision": revision + 1, **detail}, []
        wait = next(
            (item for item in _waits(connection, root) if item.wait_id == request.wait_id), None
        )
        if wait is None:
            nested_wait = next(
                (
                    item
                    for child in _descendant_runs(connection, root)
                    for item in _waits(connection, child)
                    if item.wait_id == request.wait_id
                ),
                None,
            )
            if nested_wait and nested_wait.root_work_id:
                nested_request = request.model_copy(
                    update={
                        "root_work_id": nested_wait.root_work_id,
                        "expected_revision": _run(connection, nested_wait.root_work_id)[1],
                    }
                )
                return apply_workflow_change(connection, nested_request, **common)
        if wait is None or wait.revision != request.expected_wait_revision:
            raise FoundationError("stale_wait", "Question is not the current open interaction")
        if wait.expected_actor != request.actor:
            raise FoundationError("permission_denied", "This actor cannot answer the interaction")
        from .activity_setup import _basis

        basis = _basis(connection, request.answer, request.actor, epoch)
        state = basis["state"]
        if (
            state.get("kind") != "source"
            or state.get("channel") != "conversation_user"
            or state.get("sender") != request.actor
        ):
            raise FoundationError(
                "invalid_answer_source", "Only original owner messages can answer"
            )
        timing = connection.execute(
            "SELECT k.created_at,o.committed_at FROM knowledge_revisions k JOIN workflow_waits "
            "w ON w.wait_id=? JOIN operations o ON o.operation_id=w.operation_id WHERE "
            "k.record_id=? AND k.revision=?",
            (str(wait.wait_id), str(request.answer.record_id), request.answer.revision),
        ).fetchone()
        if timing is None or timing[0] <= timing[1]:
            raise FoundationError(
                "invalid_answer_source", "Answer must be a new owner message after this question"
            )
        connection.execute(
            "UPDATE workflow_waits SET answer=?,revision=revision+1 WHERE wait_id=?",
            (request.answer.model_dump_json(), str(wait.wait_id)),
        )
        for ref in (request.answer,) + request.source_refs:
            _basis(connection, ref, request.actor, epoch)
        all_sources = tuple(dict.fromkeys(sources + (request.answer,) + request.source_refs))
        connection.execute(
            "UPDATE workflow_runs SET sources=? WHERE root_work_id=?",
            (canonical_json([ref.model_dump(mode="json") for ref in all_sources]), str(root)),
        )
        connection.execute(
            "INSERT OR IGNORE INTO workflow_edges VALUES (?,'basis',?,?)",
            (str(root), str(request.answer.record_id), request.answer.revision),
        )
        detail = {"wait_id": str(wait.wait_id), "answer": request.answer.model_dump(mode="json")}
    elif request.action == "advance":
        from .composition import _plan

        saved_plan = _plan(connection, root)
        plan_revision, plan = saved_plan.revision, saved_plan.plan
        latest = {item.key: item for item in nodes if not item.retired}
        next_keys = request.next_nodes
        if not next_keys and node is not None and declared is not None:
            if node.output is None and declared.kind in ("question", "external"):
                answers = tuple(
                    wait
                    for wait in _waits(connection, root, all_answers=True)
                    if wait.node_key == node.key and wait.answer
                )
                if answers:
                    _host_result(
                        connection,
                        request,
                        node,
                        WorkflowNodeResult(
                            outcome="result",
                            values={
                                "answer": cast(KnowledgeRef, answers[-1].answer).model_dump(
                                    mode="json"
                                )
                            },
                            next_nodes=declared.successors,
                        ),
                        **common,
                    )
                    _event(
                        connection,
                        request,
                        _run(connection, root)[1] + 1,
                        now,
                        {"host_node": node.key},
                    )
                    return {"root_work_id": str(root), "revision": _run(connection, root)[1]}, []
                ask = request.model_copy(
                    update={
                        "action": "ask",
                        "question": request.question or declared.instruction,
                        "purpose": request.purpose or definition.purpose,
                        "interaction_kind": "external"
                        if declared.kind == "external"
                        else "question",
                    }
                )
                return apply_workflow_change(connection, ask, **common)
            if node.output is None and declared.kind == "core":
                args = declared.operation_arguments
                if declared.operation in (
                    "create_entry",
                    "correct_entry",
                    "ingest_batch",
                    "start_procedure",
                ):
                    from .models import (
                        CreateKnowledgeRequest,
                        DataEntryState,
                        IngestDataRequest,
                        ReviseKnowledgeRequest,
                        StartProcedureRequest,
                    )

                    if declared.operation in ("create_entry", "correct_entry"):
                        entry = DataEntryState.model_validate(args.get("state"))
                        if entry.scope_activity_id != UUID(activity):
                            raise FoundationError(
                                "out_of_scope", "Core node entries remain in their Activity"
                            )
                        fields: dict[str, Any] = {
                            "record_id": UUID(str(args["record_id"]))
                            if args.get("record_id")
                            else uuid5(node.work_id, "entry"),
                            "state": entry,
                        }
                        if declared.operation == "correct_entry":
                            fields["expected_revision"] = int(
                                cast(Any, args.get("expected_revision"))
                            )
                        value = _effect(
                            connection,
                            request,
                            CreateKnowledgeRequest
                            if declared.operation == "create_entry"
                            else ReviseKnowledgeRequest,
                            **fields,
                            **common,
                        )
                    else:
                        kind = (
                            IngestDataRequest
                            if declared.operation == "ingest_batch"
                            else StartProcedureRequest
                        )
                        typed = kind.model_validate(
                            {
                                **args,
                                "operation_id": request.operation_id,
                                "space_id": request.space_id,
                                "actor": request.actor,
                            }
                        )
                        if isinstance(typed, StartProcedureRequest) and typed.activity_id != UUID(
                            activity
                        ):
                            raise FoundationError(
                                "out_of_scope", "Procedure stays in the selected Activity"
                            )
                        if isinstance(typed, IngestDataRequest) and any(
                            element.mutation
                            and element.mutation.state.scope_activity_id != UUID(activity)
                            for element in typed.elements
                        ):
                            raise FoundationError(
                                "out_of_scope", "Intake stays in the selected Activity"
                            )
                        value = _effect(
                            connection,
                            request,
                            kind,
                            **typed.model_dump(
                                exclude={
                                    "protocol_version",
                                    "kind",
                                    "operation_id",
                                    "space_id",
                                    "actor",
                                }
                            ),
                            **common,
                        )
                    value = {"receipt_operation_id": str(request.operation_id), "effect": value}
                else:
                    value = _core_result(connection, declared, request.actor, epoch, UUID(activity))
                _host_result(
                    connection,
                    request,
                    node,
                    WorkflowNodeResult(
                        outcome="result", values=value, next_nodes=declared.successors
                    ),
                    **common,
                )
                _event(
                    connection, request, _run(connection, root)[1] + 1, now, {"host_node": node.key}
                )
                return {"root_work_id": str(root), "revision": _run(connection, root)[1]}, []
            if node.output is None and declared.kind == "nested":
                assert declared.workflow
                nested_run = uuid5(node.work_id, "nested-workflow")
                if (
                    connection.execute(
                        "SELECT 1 FROM workflow_runs WHERE root_work_id=?", (str(nested_run),)
                    ).fetchone()
                    is None
                ):
                    # A nested root is a fresh ordinary composite child, created atomically
                    # by the native active-plan path; no historical Work is reparented.
                    nested_definition = _definition(connection, declared.workflow)
                    _adopted(connection, declared.workflow, request.actor, epoch, UUID(activity))
                    from .composition import method_checksum

                    method_id = uuid5(nested_run, "workflow-method")
                    method = MethodDefinition(
                        instruction=nested_definition.purpose,
                        named_inputs=nested_definition.inputs,
                        named_outputs=nested_definition.outputs,
                        source_ref=f"workflow:{declared.workflow.workflow_id}@{declared.workflow.version}",
                    )
                    _effect(
                        connection,
                        request,
                        CreateMethodVersionRequest,
                        method_id=method_id,
                        version=1,
                        definition=method,
                        **common,
                    )
                    connection.execute(
                        "INSERT INTO workflow_runs VALUES (?,?,?,?,1,'running',?,?)",
                        (
                            str(nested_run),
                            str(declared.workflow.workflow_id),
                            declared.workflow.version,
                            declared.workflow.checksum,
                            canonical_json([ref.model_dump(mode="json") for ref in sources]),
                            str(request.operation_id),
                        ),
                    )
                    subrequest = request.model_copy(update={"root_work_id": nested_run})
                    subchildren = tuple(
                        _create_node(
                            connection, subrequest, entry, **common, initial_sources=sources
                        )
                        for entry in nested_definition.nodes
                        if entry.key in nested_definition.entry_nodes
                    )
                    nested_plan = WorkPlan(
                        named_inputs=declared.inputs,
                        parent_outputs=tuple(
                            ParentOutputSlot(slot=item.slot, media_type=item.media_type)
                            for item in nested_definition.outputs
                        ),
                        children=subchildren,
                        rationale=nested_definition.purpose,
                        source_ref="nested-workflow-plan",
                    )
                    nested_state = WorkState(
                        activity_id=UUID(activity),
                        goal=nested_definition.purpose,
                        method=MethodRef(
                            method_id=method_id, version=1, checksum=method_checksum(method)
                        ),
                        inputs=tuple(item.artifact for item in declared.inputs),
                        expected_outputs=nested_definition.outputs,
                    )
                    role = f"{node.role}-process"
                    if len(role) > 80:
                        raise FoundationError(
                            "invalid_workflow", "Nested role exceeds the plan contract"
                        )
                    nested_child = PlanChild(role=role, work_id=nested_run, state=nested_state)
                    next_plan = plan.model_copy(
                        update={"children": plan.children + (nested_child,)}
                    )
                    plan_nodes = tuple(
                        PlanNodeDecision(role=child.role, work_id=child.work_id, decision="keep")
                        for child in plan.children
                    ) + (
                        PlanNodeDecision(
                            role=role, work_id=nested_run, decision="add", nested_plan=nested_plan
                        ),
                    )
                    _effect(
                        connection,
                        request,
                        ReviseActivePlanRequest,
                        work_id=root,
                        expected_plan_revision=plan_revision,
                        expected_work_revision=work_revision,
                        plan=next_plan,
                        nodes=plan_nodes,
                        **common,
                    )
                    _effect(
                        connection,
                        request,
                        IssueChildWorkRequest,
                        parent_work_id=root,
                        work_id=nested_run,
                        expected_plan_revision=plan_revision + 1,
                        expected_work_revision=1,
                        **common,
                    )
                    _event(
                        connection,
                        subrequest.model_copy(update={"action": "start"}),
                        1,
                        now,
                        {"parent_work_id": str(root), "host_work_id": str(node.work_id)},
                    )
                    for source in sources:
                        connection.execute(
                            "INSERT OR IGNORE INTO workflow_edges VALUES (?,'basis',?,?)",
                            (str(nested_run), str(source.record_id), source.revision),
                        )
                    detail = {"nested_root_work_id": str(nested_run)}
                    _event(connection, request, _run(connection, root)[1] + 1, now, detail)
                    return {
                        "root_work_id": str(root),
                        "revision": _run(connection, root)[1],
                        **detail,
                    }, []
                last = connection.execute(
                    "SELECT kind FROM workflow_events WHERE root_work_id=? ORDER BY revision "
                    "DESC LIMIT 1",
                    (str(nested_run),),
                ).fetchone()
                if last is None or last[0] != "finish":
                    return {
                        "root_work_id": str(root),
                        "revision": revision,
                        "nested_root_work_id": str(nested_run),
                    }, []
                nested_revision = _subject_current(connection, nested_run, "work")[0]
                nested_work = WorkState.model_validate(
                    _subject_state(connection, nested_run, nested_revision)
                )
                _host_result(
                    connection,
                    request,
                    node,
                    WorkflowNodeResult(
                        outcome="result",
                        values={
                            "nested_root_work_id": str(nested_run),
                            "outputs": [
                                item.model_dump(mode="json") for item in nested_work.linked_outputs
                            ],
                        },
                        next_nodes=declared.successors,
                    ),
                    **common,
                )
                _event(
                    connection,
                    request,
                    _run(connection, root)[1] + 1,
                    now,
                    {"nested_complete": str(nested_run)},
                )
                return {"root_work_id": str(root), "revision": _run(connection, root)[1]}, []
            if node.issues:
                boundary_row = connection.execute(
                    "SELECT iteration FROM workflow_recovery_boundaries WHERE "
                    "root_work_id=? AND node_key=?",
                    (str(root), node.key),
                ).fetchone()
                boundary = boundary_row[0] if boundary_row else 0
                rejected = [
                    item
                    for item in nodes
                    if item.key == node.key and item.issues and item.iteration > boundary
                ]

                def identity(item: WorkflowNodeView) -> set[tuple[str, tuple[str | int, ...]]]:
                    return {(issue.code, issue.path) for issue in item.issues}

                repeated = len(rejected) > 1 and identity(rejected[-1]) == identity(rejected[-2])
                if repeated or len(rejected) >= 3:
                    return apply_workflow_change(
                        connection,
                        request.model_copy(
                            update={
                                "action": "attention",
                                "code": "workflow_result_exhausted",
                                "text": "Repeated error or two corrections exhausted; explicit "
                                "retry is required",
                            }
                        ),
                        **common,
                    )
                next_keys = (node.key,)
            elif node.output is not None and node.validation_id is None:
                return apply_workflow_change(
                    connection,
                    request.model_copy(update={"action": "validate_output", "output": node.output}),
                    **common,
                )
            elif node.validation_id:
                result_row = connection.execute(
                    "SELECT result FROM workflow_validations WHERE validation_id=?",
                    (str(node.validation_id),),
                ).fetchone()
                typed_result = WorkflowNodeResult.model_validate_json(result_row[0])
                if typed_result.outcome in ("question", "external"):
                    answered = tuple(
                        wait
                        for wait in _waits(connection, root, all_answers=True)
                        if wait.node_key == node.key and wait.answer
                    )
                    if not answered:
                        return apply_workflow_change(
                            connection,
                            request.model_copy(
                                update={
                                    "action": "ask",
                                    "question": typed_result.question,
                                    "purpose": typed_result.purpose,
                                    "interaction_kind": typed_result.outcome,
                                }
                            ),
                            **common,
                        )
                    next_keys = (node.key,)
                elif typed_result.outcome == "obstacle":
                    return apply_workflow_change(
                        connection,
                        request.model_copy(
                            update={"action": "attention", "text": typed_result.explanation}
                        ),
                        **common,
                    )
                else:
                    next_keys = typed_result.next_nodes or declared.successors
                    if not next_keys:
                        return {
                            "root_work_id": str(root),
                            "revision": revision,
                            "terminal_node": node.key,
                        }, []
        allowed: set[str] = set()
        for item in nodes:
            if item.validation_id:
                result_row = connection.execute(
                    "SELECT result FROM workflow_validations WHERE validation_id=?",
                    (str(item.validation_id),),
                ).fetchone()
                result = WorkflowNodeResult.model_validate_json(result_row[0])
                if result.outcome == "result":
                    declared_item = next(
                        entry for entry in definition.nodes if entry.key == item.key
                    )
                    allowed.update(result.next_nodes or declared_item.successors)
        if node is not None and (
            node.issues or (node.validation_id and not next_keys == request.next_nodes)
        ):
            allowed.add(node.key)
        for key in next_keys:
            if key not in allowed:
                raise FoundationError(
                    "invalid_transition", "Node was not selected by a validated predecessor"
                )
            target_node = next((entry for entry in definition.nodes if entry.key == key), None)
            if target_node is None:
                raise FoundationError("invalid_transition", "Unknown workflow node")
            for dependency in target_node.dependencies:
                if dependency not in latest:
                    return {
                        "root_work_id": str(root),
                        "revision": revision,
                        "waiting_dependency": dependency,
                    }, []
                if latest[dependency].validation_id is None:
                    return {
                        "root_work_id": str(root),
                        "revision": revision,
                        "waiting_dependency": dependency,
                    }, []
                validate_internal_output(
                    connection,
                    plan,
                    _validation_leaf(latest[dependency]),
                    actor=request.actor,
                    epoch=epoch,
                )
        source_validations = tuple(
            item
            for item in nodes
            if item.validation_id and (request.node_key is None or item.key == request.node_key)
        )
        source_positions = [index for index, item in enumerate(nodes) if item in source_validations]
        for key in next_keys:
            target = latest.get(key)
            if (
                target is not None
                and source_positions
                and nodes.index(target) > max(source_positions)
            ):
                for source_validation in source_validations:
                    connection.execute(
                        "INSERT OR IGNORE INTO workflow_transitions VALUES (?,?,?,?)",
                        (
                            str(source_validation.validation_id),
                            key,
                            str(target.work_id),
                            str(request.operation_id),
                        ),
                    )
        new_keys = tuple(
            key
            for key in next_keys
            if not source_validations
            or not all(
                _transition_current(connection, root, cast(UUID, item.validation_id), key)
                for item in source_validations
            )
        )
        if not new_keys:
            return {"root_work_id": str(root), "revision": revision, "already_advanced": True}, []
        children = tuple(
            _create_node(
                connection,
                request,
                next(item for item in definition.nodes if item.key == key),
                continuation=bool(node and node.key == key),
                **common,
            )
            for key in new_keys
        )
        if not children:
            raise FoundationError("invalid_request", "Advance requires selected next nodes")
        next_plan = plan.model_copy(update={"children": plan.children + children})
        decisions_nodes = tuple(
            PlanNodeDecision(role=child.role, work_id=child.work_id, decision="keep")
            for child in plan.children
        ) + tuple(
            PlanNodeDecision(
                role=child.role,
                work_id=child.work_id,
                decision="add",
                nested_plan=child.nested_plan,
            )
            for child in children
        )
        _effect(
            connection,
            request,
            ReviseActivePlanRequest,
            work_id=root,
            expected_plan_revision=plan_revision,
            expected_work_revision=work_revision,
            plan=next_plan,
            nodes=decisions_nodes,
            **common,
        )
        for child in children:
            key = next(
                item.key for item in _nodes(connection, root) if item.work_id == child.work_id
            )
            for source_validation in source_validations:
                connection.execute(
                    "INSERT OR IGNORE INTO workflow_transitions VALUES (?,?,?,?)",
                    (
                        str(source_validation.validation_id),
                        key,
                        str(child.work_id),
                        str(request.operation_id),
                    ),
                )
        detail = {"next_nodes": list(next_keys)}
    elif request.action == "attention":
        if not request.text:
            raise FoundationError("invalid_request", "Obstacle needs its concrete explanation")
        obstacle = uuid5(request.operation_id, "obstacle")
        _effect(
            connection,
            request,
            CreateArtifactRequest,
            artifact_id=obstacle,
            media_type="application/json",
            content=canonical_json(
                {"code": request.code or "technical_obstacle", "explanation": request.text}
            ).encode(),
            **common,
        )
        connection.execute(
            "INSERT OR IGNORE INTO workflow_edges VALUES (?,'obstacle',?,1)",
            (str(root), str(obstacle)),
        )
        detail = {
            "obstacle": str(obstacle),
            "code": request.code or "technical_obstacle",
            "explanation": request.text,
        }
    elif request.action == "finish":
        from .composition import _plan

        current_plan = _plan(connection, root)
        if _waits(connection, root):
            raise FoundationError("incomplete_context", "An addressed interaction remains open")
        latest = {item.key: item for item in nodes if not item.retired}
        for item in latest.values():
            validate_internal_output(
                connection,
                current_plan.plan,
                _validation_leaf(item),
                actor=request.actor,
                epoch=epoch,
            )
            row = connection.execute(
                "SELECT result FROM workflow_validations WHERE validation_id=?",
                (str(item.validation_id),),
            ).fetchone()
            result = WorkflowNodeResult.model_validate_json(row[0])
            if result.outcome != "result":
                raise FoundationError("incomplete_context", "A node has no finished result")
            spec = next(entry for entry in definition.nodes if entry.key == item.key)
            selected = result.next_nodes or (
                spec.successors if spec.result_protocol == "workflow_json" else ()
            )
            if any(key not in latest for key in selected):
                raise FoundationError(
                    "workflow_incomplete", "A declared selected successor has not run"
                )
        resource_id, attempt_id, session_id = (
            uuid5(request.operation_id, name)
            for name in ("host-resource", "host-attempt", "host-session")
        )
        # A Core host executor owns a real assigned Attempt and its plan pin; it has no Pi RPC.
        _effect(
            connection,
            request,
            CreateResourceRequest,
            resource_id=resource_id,
            work_id=root,
            state=ResourceState(
                label="Core workflow completion", root=authority.space_root, mode="shared"
            ),
            **common,
        )
        previous = connection.execute(
            "SELECT attempt_id FROM execution_attempts WHERE work_id=? ORDER BY generation DESC "
            "LIMIT 1",
            (str(root),),
        ).fetchone()
        _effect(
            connection,
            request,
            AssignAttemptRequest,
            attempt_id=attempt_id,
            work_id=root,
            expected_work_revision=work_revision,
            resource_id=resource_id,
            expected_resource_revision=1,
            session_id=session_id,
            previous_attempt_id=UUID(previous[0]) if previous else None,
            executor_version="zaratustra-core/workflow-host-v1",
            **common,
        )
        report = canonical_json(
            {
                "workflow": workflow.model_dump(mode="json"),
                "root_work_id": str(root),
                "plan_revision": current_plan.revision,
                "results": [
                    {
                        "node": item.key,
                        "work_id": str(item.work_id),
                        "artifact": item.output.model_dump(mode="json") if item.output else None,
                        "validation_id": str(item.validation_id),
                    }
                    for item in latest.values()
                ],
            }
        ).encode()
        token = HOST_PUBLICATION.set(True)
        try:
            for output in definition.outputs:
                _effect(
                    connection,
                    request,
                    PublishAttemptOutputRequest,
                    attempt_id=attempt_id,
                    work_id=root,
                    session_id=session_id,
                    slot=output.slot,
                    media_type=output.media_type,
                    content=report,
                    **common,
                )
        finally:
            HOST_PUBLICATION.reset(token)
        _effect(
            connection,
            request,
            RequestAttemptStopRequest,
            work_id=root,
            attempt_id=attempt_id,
            session_id=session_id,
            expected_assignment_revision=1,
            reason="Core host completion finished",
            **common,
        )
        _effect(
            connection,
            request,
            RecordAttemptStopRequest,
            work_id=root,
            attempt_id=attempt_id,
            session_id=session_id,
            expected_assignment_revision=2,
            outcome="stopped",
            **common,
        )
        detail = {"attempt_id": str(attempt_id), "plan_revision": current_plan.revision}
    elif request.action in ("pause", "resume", "cancel"):
        all_roots = (root,) + _descendant_runs(connection, root)
        if request.action in ("pause", "cancel"):
            root_args = canonical_json([str(item) for item in _work_family(connection, root)])
            for work_id, attempt_id, session_id, assignment_revision in connection.execute(
                "SELECT a.work_id,a.attempt_id,t.session_id,a.revision FROM "
                "execution_assignments a JOIN execution_attempts t ON t.attempt_id=a.attempt_id "
                "WHERE a.work_id IN (SELECT value FROM json_each(?)) "
                "AND a.status IN ('assigned','waiting','ready')",
                (root_args,),
            ):
                _effect(
                    connection,
                    request,
                    RequestAttemptStopRequest,
                    work_id=UUID(work_id),
                    attempt_id=UUID(attempt_id),
                    session_id=UUID(session_id),
                    expected_assignment_revision=assignment_revision,
                    reason="Workflow paused or cancelled by owner",
                    **common,
                )
        for identifier in all_roots:
            connection.execute(
                "UPDATE workflow_runs SET control=? WHERE root_work_id=?",
                (
                    {"pause": "paused", "resume": "running", "cancel": "cancelled"}[request.action],
                    str(identifier),
                ),
            )
    elif request.action == "migrate":
        if request.workflow is None:
            raise FoundationError(
                "invalid_request", "Migration needs an exact adopted target version"
            )
        _require_idle(connection, root)
        target_definition = _definition(connection, request.workflow)
        _adopted(
            connection, request.workflow, request.actor, epoch, request.activity_id, new_use=True
        )
        assert request.activity_id is not None
        _definition_contracts(
            connection, target_definition, request.actor, epoch, (request.activity_id,)
        )
        if (
            target_definition.inputs != definition.inputs
            or target_definition.outputs != definition.outputs
        ):
            raise FoundationError(
                "workflow_migration_required",
                "Pinned root input/output contracts must remain compatible",
            )
        old_keys = {item.key: item for item in definition.nodes}
        target_keys = {item.key: item for item in target_definition.nodes}
        current = tuple(item for item in nodes if not item.retired)
        choices: dict[UUID, tuple[str, str]] = {}
        for item in current:
            address = item.role if item.role in request.node_dispositions else item.key
            if address not in request.node_dispositions or address not in request.node_mapping:
                raise FoundationError(
                    "mapping_incomplete",
                    "Every retained node/iteration needs an explicit mapping and disposition",
                )
            mapped, disposition = request.node_mapping[address], request.node_dispositions[address]
            if disposition != "retire" and mapped not in target_keys:
                raise FoundationError("mapping_invalid", "Mapped target node is absent")
            if disposition == "keep" and (
                mapped != item.key or target_keys[mapped] != old_keys[item.key]
            ):
                raise FoundationError(
                    "workflow_migration_required",
                    "A kept node retains its exact contract, inputs, result and resource",
                )
            if disposition != "keep":
                if old_keys[item.key].kind in ("core", "nested") and item.output:
                    raise FoundationError(
                        "effect_mapping_required",
                        "Performed effects must be kept; migration cannot replay them",
                    )
                if _subject_current(connection, item.work_id, "work")[1] == "succeeded":
                    raise FoundationError(
                        "accepted_result_mapping_required",
                        "Accepted results must be kept with an unchanged contract",
                    )
            choices[item.work_id] = mapped, disposition
        from .composition import _plan

        held = _plan(connection, root)
        kept = tuple(
            child
            for child in held.plan.children
            if choices.get(child.work_id, (child.role, "keep"))[1] == "keep"
        )
        kept_keys = {item.key for item in current if choices[item.work_id][1] == "keep"}
        changed_keys = {
            mapped for mapped, disposition in choices.values() if disposition == "replace"
        }
        added: list[PlanChild] = []
        for key in target_definition.entry_nodes + tuple(sorted(changed_keys)):
            spec = target_keys[key]
            if key in kept_keys or any(
                child.role == key or child.role.startswith(key + "-") for child in added
            ):
                continue
            if not set(spec.dependencies).issubset(kept_keys):
                continue
            added.append(_create_node(connection, request, spec, continuation=True, **common))
        if not kept and not added:
            raise FoundationError(
                "workflow_migration_required",
                "Migration must retain or materialize a ready first step",
            )
        plan_decisions = []
        for child in held.plan.children:
            _, held_disposition = choices.get(child.work_id, (child.role, "keep"))
            if held_disposition == "keep":
                plan_decisions.append(
                    PlanNodeDecision(role=child.role, work_id=child.work_id, decision="keep")
                )
            else:
                plan_decisions.append(
                    PlanNodeDecision(
                        role=child.role,
                        work_id=child.work_id,
                        decision="cancel",
                        closure=NodeClosure(
                            expected_revision=_subject_current(connection, child.work_id, "work")[
                                0
                            ],
                            outcome="cancelled",
                            basis=(
                                "Explicit workflow version transfer; "
                                "preserve prior results as history"
                            ),
                        ),
                    )
                )
                connection.execute(
                    "UPDATE workflow_waits SET closed=1,revision=revision+1 WHERE "
                    "root_work_id=? AND work_id=? AND closed=0",
                    (str(root), str(child.work_id)),
                )
        plan_decisions.extend(
            PlanNodeDecision(
                role=child.role,
                work_id=child.work_id,
                decision="add",
                nested_plan=child.nested_plan,
            )
            for child in added
        )
        _effect(
            connection,
            request,
            ReviseActivePlanRequest,
            work_id=root,
            expected_plan_revision=held.revision,
            expected_work_revision=work_revision,
            plan=held.plan.model_copy(update={"children": kept + tuple(added), "completion": None}),
            nodes=tuple(plan_decisions),
            **common,
        )
        connection.execute(
            "UPDATE workflow_runs SET workflow_id=?,version=?,checksum=? WHERE root_work_id=?",
            (
                str(request.workflow.workflow_id),
                request.workflow.version,
                request.workflow.checksum,
                str(root),
            ),
        )
        detail = {
            "from": workflow.model_dump(mode="json"),
            "to": request.workflow.model_dump(mode="json"),
            "node_mapping": request.node_mapping,
            "node_dispositions": request.node_dispositions,
        }
    else:
        raise FoundationError("invalid_request", "Unknown workflow operation")
    next_revision = _run(connection, root)[1] + 1
    _event(connection, request, next_revision, now, detail)
    return {"root_work_id": str(root), "revision": next_revision, **detail}, [
        {"record_id": str(root), "revision": next_revision}
    ]


def read_workflow(path: Path, ref: WorkflowRef, authority: LocalAuthority) -> WorkflowDefinition:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        _schema(connection)
        definition = _definition(connection, ref, active=False)
        status = connection.execute(
            "SELECT status FROM workflow_versions WHERE workflow_id=? AND version=?",
            (str(ref.workflow_id), ref.version),
        ).fetchone()[0]
        if status == "active":
            _adopted(connection, ref, authority.actor, info.execution_epoch)
        else:
            _authorize(
                connection, actor=authority.actor, action="method.write", epoch=info.execution_epoch
            )
        return definition


def read_workflow_node_for_work(
    path: Path, work_id: UUID, authority: LocalAuthority
) -> WorkflowNodeView | None:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 16:
            return None
        row = connection.execute(
            "SELECT root_work_id FROM workflow_nodes WHERE work_id=?", (str(work_id),)
        ).fetchone()
        if row is None:
            return None
        root = UUID(row[0])
        _readable(connection, root, authority.actor, info.execution_epoch)
        return next(item for item in _nodes(connection, root) if item.work_id == work_id)


def read_workflow_method_tasks(
    path: Path, work_id: UUID, authority: LocalAuthority
) -> dict[str, Any]:
    """Expose native ready roles and ordinary acceptance needs; never accept an output."""
    from .composition import _evaluate, _obligations, _parent_current, original_issue

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="work",
            resource_id=work_id,
        )
        revision, status, _ = _subject_current(connection, work_id, "work")
        state = WorkState.model_validate(_subject_state(connection, work_id, revision))
        if not isinstance(state.method, MethodRef):
            raise FoundationError("wrong_kind", "Work has no composite Method")
        definition, plan = _parent_current(
            connection,
            work_id,
            state,
            actor=authority.actor,
            epoch=info.execution_epoch,
            grants=[],
            decisions=[],
        )
        children = []
        owner_waiting: list[dict[str, Any]] = []
        for child in plan.plan.children:
            _authorize(
                connection,
                actor=authority.actor,
                action="record.read",
                epoch=info.execution_epoch,
                resource_type="work",
                resource_id=child.work_id,
            )
            child_revision, child_status, _ = _subject_current(connection, child.work_id, "work")
            body = WorkState.model_validate(
                _subject_state(connection, child.work_id, child_revision)
            )
            ready = child_status == "proposed"
            reason = None
            try:
                _evaluate(
                    connection,
                    plan.plan,
                    child.readiness,
                    work_id=child.work_id,
                    actor=authority.actor,
                    epoch=info.execution_epoch,
                    grants=[],
                    decisions=[],
                )
            except FoundationError as error:
                ready = False
                reason = error.code
            if connection.execute(
                "SELECT 1 FROM execution_waits w LEFT JOIN workflow_native_answers n ON "
                "n.wait_id=w.wait_id WHERE w.work_id=? AND w.status IN ('open','closed') "
                "AND w.answer IS NULL AND n.answer IS NULL AND w.question IS NOT NULL "
                "LIMIT 1",
                (str(child.work_id),),
            ).fetchone():
                ready = False
                reason = "native_wait_open"
            issue = original_issue(connection, child.work_id)
            children.append(
                {
                    "role": child.role,
                    "work_id": str(child.work_id),
                    "work_revision": child_revision,
                    "issued": bool(issue and issue[1]),
                    "ready": ready and not body.linked_outputs,
                    "method": body.method.model_dump(mode="json")
                    if isinstance(body.method, MethodRef)
                    else "none",
                    "outputs": [item.model_dump(mode="json") for item in body.linked_outputs],
                    "status": child_status,
                    "reason": reason,
                }
            )
            if body.linked_outputs and child_status == "proposed":
                owner_waiting.append(
                    {
                        "work_id": str(child.work_id),
                        "role": child.role,
                        "reason": "proposed_result_requires_owner_acceptance",
                    }
                )
        parent_ready = status == "proposed"
        try:
            _evaluate(
                connection,
                plan.plan,
                plan.plan.completion,
                work_id=work_id,
                actor=authority.actor,
                epoch=info.execution_epoch,
                grants=[],
                decisions=[],
            )
        except FoundationError as error:
            parent_ready = False
            if error.code in ("dependency_open", "obligation_open") and not owner_waiting:
                owner_waiting.append({"work_id": str(work_id), "reason": error.code})
        for obligation in _obligations(connection, work_id, definition):
            if (
                (obligation.definition.role is not None or state.linked_outputs)
                and obligation.applicability == "active"
                and obligation.status not in ("satisfied", "waived")
            ):
                parent_ready = False
                owner_waiting.append(
                    {
                        "work_id": str(work_id),
                        "role": obligation.definition.role,
                        "key": obligation.key,
                        "reason": "obligation_requires_ordinary_evidence",
                    }
                )
        return {
            "method": state.method.model_dump(mode="json"),
            "plan_revision": plan.revision,
            "work_revision": revision,
            "children": children,
            "parent_ready": parent_ready,
            "owner_waiting": owner_waiting,
            "own_output_pending": not bool(state.linked_outputs),
        }


def list_workflow_runs(
    path: Path,
    authority: LocalAuthority,
    *,
    limit: int = 25,
    after: UUID | None = None,
    pending_only: bool = False,
) -> tuple[WorkflowRunView, ...]:
    if not 1 <= limit <= 100:
        raise FoundationError("invalid_request", "Run catalog limit is between 1 and 100")
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 16:
            return ()
        suffix = (
            " AND r.control!='cancelled' AND s.status='proposed' AND NOT EXISTS (SELECT 1 FROM "
            "work_plan_children c JOIN workflow_runs p ON p.root_work_id=c.parent_id WHERE "
            "c.child_id=r.root_work_id) AND NOT EXISTS (SELECT 1 FROM work_plan_members c JOIN "
            "workflow_runs p ON p.root_work_id=c.parent_id WHERE c.child_id=r.root_work_id)"
            if pending_only
            else ""
        )
        ids = tuple(
            UUID(row[0])
            for row in connection.execute(
                "SELECT r.root_work_id FROM workflow_runs r JOIN subject_records s ON "
                "s.record_id=r.root_work_id WHERE r.root_work_id>?"
                + suffix
                + " ORDER BY r.root_work_id LIMIT ?",
                (str(after) if after else "", limit),
            )
        )
    result = []
    for identifier in ids:
        try:
            result.append(read_workflow_run(path, identifier, authority))
        except FoundationError as error:
            if error.code not in ("permission_denied", "content_unavailable", "stale_basis"):
                raise
    return tuple(result)


def list_workflows(
    path: Path, authority: LocalAuthority, *, after: tuple[str, int] | None = None, limit: int = 50
) -> tuple[WorkflowRef, ...]:
    if not 1 <= limit <= 100:
        raise FoundationError("invalid_request", "Catalog limit is between 1 and 100")
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        _schema(connection)
        cursor = after or ("", 0)
        result = []
        for row in connection.execute(
            "SELECT workflow_id,version,checksum,status FROM workflow_versions WHERE "
            "status!='deleted' AND (workflow_id,version)>(?,?) ORDER BY workflow_id,version "
            "LIMIT ?",
            (*cursor, limit),
        ):
            ref = WorkflowRef(workflow_id=UUID(row[0]), version=row[1], checksum=row[2])
            try:
                if row[3] == "active":
                    _adopted(connection, ref, authority.actor, info.execution_epoch)
                else:
                    _authorize(
                        connection,
                        actor=authority.actor,
                        action="method.write",
                        epoch=info.execution_epoch,
                    )
                result.append(ref)
            except FoundationError as error:
                if error.code not in (
                    "permission_denied",
                    "content_unavailable",
                    "workflow_not_adopted",
                    "stale_basis",
                    "stale_candidate",
                ):
                    raise
        return tuple(result)


def read_workflow_run(path: Path, root_work_id: UUID, authority: LocalAuthority) -> WorkflowRunView:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        _schema(connection)
        _readable(connection, root_work_id, authority.actor, info.execution_epoch)
        ref, revision, control, _ = _run(connection, root_work_id)
        nodes = _nodes(connection, root_work_id)
        waits = _waits(connection, root_work_id)
        waits += _native_waits(connection, root_work_id, authority.actor, info.execution_epoch)
        for child in _descendant_runs(connection, root_work_id):
            _readable(connection, child, authority.actor, info.execution_epoch)
            waits += _waits(connection, child)
            waits += _native_waits(connection, child, authority.actor, info.execution_epoch)
        _, status, activity = _subject_current(connection, root_work_id, "work")
        latest = {item.key: item for item in nodes if not item.retired}
        from .composition import _evaluate, _plan

        plan = _plan(connection, root_work_id).plan
        ready_list = []
        definition = _definition(connection, ref)
        specs = {item.key: item for item in definition.nodes}
        for item in latest.values():
            if any(wait.work_id == item.work_id for wait in waits):
                continue
            if specs[item.key].method is not None and any(
                wait.native and wait.work_id in _work_family(connection, item.work_id)
                for wait in waits
            ):
                native_tasks = read_workflow_method_tasks(path, item.work_id, authority)
                if not any(task["ready"] for task in native_tasks["children"]):
                    continue
            if specs[item.key].kind == "nested" and item.output is None:
                nested_root = uuid5(item.work_id, "nested-workflow")
                if connection.execute(
                    "SELECT 1 FROM workflow_runs WHERE root_work_id=?", (str(nested_root),)
                ).fetchone():
                    nested_view = read_workflow_run(path, nested_root, authority)
                    if nested_view.next_action in ("answer", "owner_action", "resume", "attention"):
                        continue
            if item.output is not None:
                if item.issues or item.validation_id is None:
                    ready_list.append(item.key)
                    continue
                row = connection.execute(
                    "SELECT result FROM workflow_validations WHERE validation_id=?",
                    (str(item.validation_id),),
                ).fetchone()
                value = WorkflowNodeResult.model_validate_json(row[0])
                if specs[item.key].result_protocol != "workflow_json":
                    continue
                if value.outcome in ("question", "external", "obstacle"):
                    ready_list.append(item.key)
                    continue
                targets = value.next_nodes or specs[item.key].successors
                for target in targets:
                    if _transition_current(connection, root_work_id, item.validation_id, target):
                        continue
                    if all(
                        key in latest and latest[key].validation_id
                        for key in specs[target].dependencies
                    ):
                        ready_list.append(item.key)
                        break
                continue
            plan_child = next(entry for entry in plan.children if entry.work_id == item.work_id)
            try:
                _evaluate(
                    connection,
                    plan,
                    plan_child.readiness,
                    work_id=item.work_id,
                    actor=authority.actor,
                    epoch=info.execution_epoch,
                    grants=[],
                    decisions=[],
                )
            except FoundationError:
                continue
            ready_list.append(item.key)
        owner_waiting = []
        for item in latest.values():
            if specs[item.key].method is None:
                continue
            tasks = read_workflow_method_tasks(path, item.work_id, authority)
            if tasks["owner_waiting"] and not any(child["ready"] for child in tasks["children"]):
                owner_waiting.extend(tasks["owner_waiting"])
                ready_list = [key for key in ready_list if key != item.key]
        ready = tuple(dict.fromkeys(ready_list))
        last = connection.execute(
            "SELECT kind,detail FROM workflow_events WHERE root_work_id=? ORDER BY revision "
            "DESC LIMIT 1",
            (str(root_work_id),),
        ).fetchone()
        obstacle = last and last[0] == "attention"
        finished = last and last[0] == "finish"
        action = (
            "closed"
            if control == "cancelled" or status != "proposed" or finished
            else "resume"
            if control == "paused"
            else "attention"
            if obstacle
            else "run"
            if ready
            else "answer"
            if waits
            else "owner_action"
            if owner_waiting
            else "finish"
        )
        explanation = {
            "closed": "Процесс завершён или отменён",
            "resume": "Процесс приостановлен; доступно продолжение",
            "answer": "Сохранён вопрос; ожидается ответ пользователя",
            "attention": "Сохранён конкретный дефект результата",
            "run": "Есть готовый следующий этап",
            "finish": "Результаты этапов сохранены; координатор проверяет следующий переход",
            "owner_action": "Результат Method подготовлен. Для продолжения нужно "
            "отдельное принятие "
            "результата или подтверждение его требований владельцем",
        }[action]
        if obstacle and last[1]:
            explanation = json.loads(last[1])["explanation"]
        return WorkflowRunView(
            root_work_id=root_work_id,
            revision=revision,
            workflow=ref,
            activity_id=UUID(activity),
            nodes=nodes,
            waits=waits,
            ready_nodes=ready,
            next_action=cast(Any, action),
            explanation=explanation,
            control=cast(Any, control),
            diagnostics=tuple(
                ArtifactRef(artifact_id=UUID(identifier), revision=artifact_revision)
                for identifier, artifact_revision in connection.execute(
                    "SELECT target_id,target_revision FROM workflow_edges WHERE "
                    "root_work_id=? AND role='obstacle' ORDER BY target_id,target_revision",
                    (str(root_work_id),),
                )
            ),
        )


def read_workflow_packet(
    path: Path, root_work_id: UUID, ref: ArtifactRef, authority: LocalAuthority
) -> bytes:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        _readable(connection, root_work_id, authority.actor, info.execution_epoch)
        included = bool(
            connection.execute(
                "SELECT 1 FROM workflow_edges WHERE root_work_id=? AND target_id=? AND "
                "target_revision=? AND role IN ('packet','output','obstacle')",
                (str(root_work_id), str(ref.artifact_id), ref.revision),
            ).fetchone()
        )
        if not included:
            from .composition import _parent_current

            def artifacts(work: UUID) -> bool:
                _authorize(
                    connection,
                    actor=authority.actor,
                    action="record.read",
                    epoch=info.execution_epoch,
                    resource_type="work",
                    resource_id=work,
                )
                current, _, _ = _subject_current(connection, work, "work")
                state = WorkState.model_validate(_subject_state(connection, work, current))
                if ref in state.inputs or any(
                    output.artifact == ref for output in state.linked_outputs
                ):
                    return True
                if isinstance(state.method, MethodRef):
                    _, plan = _parent_current(
                        connection,
                        work,
                        state,
                        actor=authority.actor,
                        epoch=info.execution_epoch,
                        grants=[],
                        decisions=[],
                    )
                    _authorize(
                        connection,
                        actor=authority.actor,
                        action="method.use",
                        epoch=info.execution_epoch,
                        resource_type="activity",
                        resource_id=state.activity_id,
                    )
                    return any(artifacts(child.work_id) for child in plan.plan.children)
                return False

            included = any(
                artifacts(node.work_id)
                for scoped in (root_work_id,) + _descendant_runs(connection, root_work_id)
                for node in _nodes(connection, scoped)
                if not node.retired
            )
        if not included:
            raise FoundationError("out_of_scope", "Artifact is not in this workflow")
        from .activity_setup import _artifact

        return _artifact(connection, ref, authority.actor, info.execution_epoch, current=False)


def read_workflow_wait(
    path: Path, root_work_id: UUID, wait_id: UUID, authority: LocalAuthority
) -> WorkflowWait:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        _readable(connection, root_work_id, authority.actor, info.execution_epoch)
        for root in (root_work_id,) + _descendant_runs(connection, root_work_id):
            _readable(connection, root, authority.actor, info.execution_epoch)
            wait = next(
                (
                    item
                    for item in _waits(connection, root, all_answers=True)
                    if item.wait_id == wait_id
                ),
                None,
            )
            if wait is None:
                wait = next(
                    (
                        entry
                        for entry in _native_waits(
                            connection,
                            root,
                            authority.actor,
                            info.execution_epoch,
                            all_answers=True,
                        )
                        if entry.wait_id == wait_id
                    ),
                    None,
                )
            if wait:
                return wait
        raise FoundationError("not_found", "Interaction is absent from this workflow scope")


def read_workflow_continuation_for_work(
    path: Path, work_id: UUID, authority: LocalAuthority
) -> ArtifactRef | None:
    """Exact retained native interaction packet for the next ordinary Attempt."""
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 16:
            return None
        row = connection.execute(
            "SELECT root_work_id,packet_id,packet_revision FROM workflow_native_answers "
            "WHERE work_id=? ORDER BY rowid DESC LIMIT 1",
            (str(work_id),),
        ).fetchone()
        if row is None:
            return None
        root = UUID(row[0])
        _readable(connection, root, authority.actor, info.execution_epoch)
        if work_id not in _work_family(connection, root):
            raise FoundationError("stale_wait", "Native continuation Work left the current plan")
        ref = ArtifactRef(artifact_id=UUID(row[1]), revision=row[2])
        from .activity_setup import _artifact

        _artifact(connection, ref, authority.actor, info.execution_epoch)
        return ref


def apply_workflow_candidate(
    connection: sqlite3.Connection,
    request: ApplyCandidateRequest,
    candidate: ChangeCandidateState,
    *,
    now: str,
    epoch: int,
    authority: LocalAuthority,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, Any], list[dict[str, object]]]:
    from .development import _decision, _package_event

    _schema(connection)
    target = candidate.target
    assert isinstance(target, WorkflowChange)
    application_id = uuid5(request.operation_id, f"workflow-application:{request.candidate_id}")
    decision = _decision(connection, request, candidate)
    for (scope,) in connection.execute(
        "SELECT w.scope_activity_id FROM workflow_adoptions w JOIN change_packages a ON "
        "a.application_id=w.application_id WHERE w.workflow_id=? AND w.version=? AND "
        "a.status='active'",
        (str(target.workflow_id), target.to_version),
    ):
        if scope is None or decision.scope_global or scope == str(decision.scope_activity_id):
            raise FoundationError("change_already_active", "Workflow already adopted in this scope")
    _definition_contracts(
        connection, target.definition, request.actor, epoch, candidate.scope_activity_ids
    )
    ref = WorkflowRef(
        workflow_id=target.workflow_id,
        version=target.to_version,
        checksum=workflow_checksum(target.definition),
    )
    row = connection.execute(
        "SELECT checksum,status FROM workflow_versions WHERE workflow_id=? AND version=?",
        (str(target.workflow_id), target.to_version),
    ).fetchone()
    if row is None:
        proposal = WorkflowRequest(
            operation_id=request.operation_id,
            space_id=request.space_id,
            actor=request.actor,
            action="create_definition",
            workflow_id=target.workflow_id,
            version=target.to_version,
            definition=target.definition,
        )
        _store_definition(connection, proposal, now)
    elif row[0] != ref.checksum or row[1] == "deleted":
        raise FoundationError(
            "version_conflict", "Proposed workflow differs from validated Candidate"
        )
    if target.from_version is not None:
        previous = connection.execute(
            "SELECT 1 FROM workflow_versions WHERE workflow_id=? AND version=? AND status='active'",
            (str(target.workflow_id), target.from_version),
        ).fetchone()
        if previous is None:
            raise FoundationError("stale_basis", "Previous workflow is not active")
    connection.execute(
        "UPDATE workflow_versions SET status='active' WHERE workflow_id=? AND version=?",
        (str(target.workflow_id), target.to_version),
    )
    connection.execute(
        "INSERT INTO workflow_adoptions VALUES (?,?,?,?,?,?,?,?)",
        (
            str(target.workflow_id),
            target.to_version,
            str(application_id),
            str(request.candidate_id),
            request.candidate_revision,
            str(request.decision_id),
            request.decision_revision,
            str(decision.scope_activity_id) if decision.scope_activity_id else None,
        ),
    )
    connection.execute(
        "INSERT INTO change_packages VALUES (?,?,?,?,?,?,?,?,?,?,'active',1,?,?)",
        (
            str(application_id),
            str(request.candidate_id),
            request.candidate_revision,
            str(request.decision_id),
            request.decision_revision,
            request.mode,
            "workflow",
            str(target.workflow_id),
            target.to_version,
            ref.checksum,
            now,
            now,
        ),
    )
    connection.execute(
        "INSERT INTO change_package_parts VALUES (?,0,'workflow',?,?,?,?)",
        (
            str(application_id),
            str(target.workflow_id),
            target.to_version,
            ref.checksum,
            target.model_dump_json(),
        ),
    )
    _package_event(
        connection,
        application_id,
        1,
        request.operation_id,
        "apply",
        {"workflow": ref.model_dump(mode="json")},
        now,
    )
    return {
        "application_id": str(application_id),
        "workflow": ref.model_dump(mode="json"),
        "status": "active",
    }, [{"record_id": str(target.workflow_id), "revision": target.to_version}]


def followup_workflow(
    connection: sqlite3.Connection,
    request: StopCandidateRequest | RestoreCandidateRequest | RecordChangeOutcomeRequest,
    app: ChangeApplication,
    *,
    now: str,
    epoch: int,
) -> tuple[dict[str, Any], list[dict[str, object]]]:
    """Use the common Candidate application lifecycle; existing runs retain their pins."""
    from .development import _package_event
    from .knowledge import _require_ref

    row = connection.execute(
        "SELECT detail_json FROM change_package_parts WHERE application_id=? AND ordinal=0",
        (str(app.application_id),),
    ).fetchone()
    if row is None:
        raise FoundationError("content_unavailable", "Workflow application lost its target")
    target = WorkflowChange.model_validate_json(row[0])
    _definition(
        connection,
        WorkflowRef(workflow_id=app.target_id, version=app.version, checksum=app.checksum),
    )
    status = app.status
    detail: dict[str, object]
    if isinstance(request, StopCandidateRequest):
        if status != "active":
            raise FoundationError("invalid_transition", "Only active workflow adoption can stop")
        status, kind = "stopped", "stop"
        detail = {
            "reason": request.reason,
            "started_works": request.started_works,
            "external_effects": request.external_effects,
        }
    elif isinstance(request, RestoreCandidateRequest):
        if status not in ("stopped", "partial"):
            raise FoundationError("invalid_transition", "Stop new workflow use before restoration")
        pending = None
        if target.from_version is not None:
            prior = connection.execute(
                "SELECT checksum FROM workflow_versions WHERE workflow_id=? AND version=? "
                "AND status='active'",
                (str(app.target_id), target.from_version),
            ).fetchone()
            if prior is None:
                pending = "prior_workflow_unavailable"
            else:
                try:
                    _adopted(
                        connection,
                        WorkflowRef(
                            workflow_id=app.target_id,
                            version=target.from_version,
                            checksum=prior[0],
                        ),
                        request.actor,
                        epoch,
                        new_use=True,
                    )
                except FoundationError:
                    pending = "prior_workflow_needs_current_admission"
        status, kind = ("partial" if pending else "restored"), "restore"
        detail = {
            "reason": request.reason,
            "data_restoration": request.data_restoration,
            "external_effects": request.external_effects,
            "restored_version": target.from_version,
            "pending": pending,
        }
    else:
        for basis in request.evidence:
            _require_ref(connection, basis, request.actor, epoch)
        kind, detail = (
            "outcome",
            {
                "outcome": request.outcome,
                "observation": request.observation,
                "evidence": [item.model_dump(mode="json") for item in request.evidence],
            },
        )
    connection.execute(
        "UPDATE change_packages SET status=?,revision=revision+1,changed_at=? WHERE "
        "application_id=?",
        (status, now, str(app.application_id)),
    )
    _package_event(
        connection, app.application_id, app.revision + 1, request.operation_id, kind, detail, now
    )
    return {"application_id": str(app.application_id), "status": status}, []


def sanitize_workflow_dependency(
    connection: sqlite3.Connection,
    record_id: UUID,
    now: str,
    *,
    workflow_version: int | None = None,
) -> None:
    """Retire derived packets/results/questions when their exact basis is deleted."""
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 16:
        return
    roots = (
        {
            row[0]
            for row in connection.execute(
                "SELECT root_work_id FROM workflow_edges WHERE target_id=?", (str(record_id),)
            )
        }
        if workflow_version is None
        else set()
    )
    if workflow_version is None:
        roots.update(
            row[0]
            for row in connection.execute(
                "SELECT root_work_id FROM workflow_nodes WHERE work_id=? OR root_work_id=?",
                (str(record_id), str(record_id)),
            )
        )
    if workflow_version is None:
        definitions = tuple(
            connection.execute(
                "SELECT DISTINCT w.workflow_id,w.version FROM workflow_adoptions w JOIN "
                "development_edges e ON e.record_id=w.candidate_id JOIN workflow_versions v ON "
                "v.workflow_id=w.workflow_id AND v.version=w.version WHERE e.target_id=? AND "
                "v.payload IS NOT NULL UNION SELECT w.workflow_id,w.version FROM "
                "workflow_adoptions w "
                "JOIN workflow_versions v ON v.workflow_id=w.workflow_id AND v.version=w.version "
                "WHERE candidate_id=? AND v.payload IS NOT NULL",
                (str(record_id), str(record_id)),
            )
        )
    else:
        definitions = tuple(
            connection.execute(
                "SELECT DISTINCT w.workflow_id,w.version FROM workflow_adoptions w JOIN "
                "development_edges e ON e.record_id=w.candidate_id AND "
                "e.revision=w.candidate_revision JOIN workflow_versions v ON "
                "v.workflow_id=w.workflow_id AND v.version=w.version WHERE e.target_id=? AND "
                "e.target_revision=? AND e.role='nested_workflow' AND v.payload IS NOT NULL",
                (str(record_id), workflow_version),
            )
        )
    for identifier, version in definitions:
        connection.execute(
            "UPDATE workflow_versions SET payload=NULL,status='deleted' WHERE workflow_id=? AND "
            "version=?",
            (identifier, version),
        )
        from .development import _sanitize_development

        for (candidate_id,) in connection.execute(
            "SELECT DISTINCT candidate_id FROM workflow_adoptions WHERE workflow_id=? "
            "AND version=?",
            (identifier, version),
        ).fetchall():
            _sanitize_development(connection, UUID(candidate_id), now, deleted=False)
        sanitize_workflow_dependency(connection, UUID(identifier), now, workflow_version=version)
        connection.execute(
            "UPDATE change_package_parts SET detail_json='{}' WHERE application_id IN "
            "(SELECT application_id FROM workflow_adoptions WHERE workflow_id=? AND "
            "version=?)",
            (identifier, version),
        )
        roots.update(
            row[0]
            for row in connection.execute(
                "SELECT root_work_id FROM workflow_runs WHERE workflow_id=? AND version=?",
                (identifier, version),
            )
        )
    for root in roots:
        held = connection.execute(
            "SELECT sources FROM workflow_runs WHERE root_work_id=?", (root,)
        ).fetchone()
        if held is None or held[0] is None:
            continue
        # Mark before following derived dependencies so recursive sanitation terminates.
        connection.execute(
            "UPDATE workflow_runs SET sources=NULL,control='paused' WHERE root_work_id=?", (root,)
        )
        connection.execute(
            "UPDATE workflow_waits SET "
            "question=NULL,purpose=NULL,bases=NULL,answer=NULL,closed=1 WHERE root_work_id=?",
            (root,),
        )
        connection.execute(
            "UPDATE workflow_validations SET result=NULL,issues=NULL WHERE root_work_id=?", (root,)
        )
        connection.execute("UPDATE workflow_events SET detail=NULL WHERE root_work_id=?", (root,))
        for (operation,) in connection.execute(
            "SELECT operation_id FROM workflow_events WHERE root_work_id=?", (root,)
        ):
            connection.execute("DELETE FROM receipts WHERE operation_id=?", (operation,))
            connection.execute(
                "UPDATE operations SET fingerprint='DELETED' WHERE operation_id=?", (operation,)
            )
        works = {str(work) for work in _work_family(connection, UUID(root))}
        assigned = [
            {"work_id": row[0], "attempt_id": row[1]}
            for row in connection.execute(
                "SELECT work_id,attempt_id FROM execution_assignments WHERE work_id IN "
                "(SELECT value FROM json_each(?))",
                (canonical_json(sorted(works)),),
            )
        ]
        for work in works:
            connection.execute("DELETE FROM subject_content WHERE record_id=?", (work,))
            connection.execute(
                "UPDATE execution_waits SET "
                "question=NULL,remainder=NULL,answer=NULL,status='purged' WHERE work_id=?",
                (work,),
            )
        method_id = str(uuid5(UUID(root), "workflow-method"))
        connection.execute(
            "UPDATE method_versions SET payload=NULL,status='deleted' WHERE method_id=?",
            (method_id,),
        )
        for artifact_id, revision in connection.execute(
            "SELECT target_id,target_revision FROM workflow_edges WHERE root_work_id=? AND role "
            "IN ('packet','output','obstacle')",
            (root,),
        ):
            from .operations import _queue_derived_artifact_deletion

            origin = connection.execute(
                "SELECT operation_id FROM record_revisions WHERE record_id=? ORDER BY revision "
                "LIMIT 1",
                (artifact_id,),
            ).fetchone()
            if origin:
                _queue_derived_artifact_deletion(connection, origin[0], artifact_id, assigned, now)
            connection.execute(
                "DELETE FROM managed_content WHERE record_id=? AND revision=?",
                (artifact_id, revision),
            )
        connection.execute(
            "UPDATE backup_inventory SET status='contaminated' "
            "WHERE status IN ('planned','failed','complete')"
        )


def setup_workflow_begin(
    connection: sqlite3.Connection,
    request: Any,
    sources: tuple[KnowledgeRef, ...],
    *,
    now: str,
    epoch: int,
    authority: LocalAuthority,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[WorkflowRef, UUID]:
    """A shipped workflow is trusted product code; its run is still ordinary scoped Work."""
    identifier = UUID("93e4b5c2-f5cc-52d4-8828-559898c329ba")
    definition = WorkflowDefinition(
        title="Create Activity",
        purpose="Design and review a usable Activity with the owner",
        nodes=(
            WorkflowNode(
                key="interview",
                kind="question",
                instruction="Use known facts and ask only missing owner decisions",
                successors=("draft", "review", "correction"),
                max_iterations=100,
            ),
            WorkflowNode(
                key="draft",
                kind="model",
                instruction="Design the complete minimal Activity",
                successors=("review", "draft"),
                max_iterations=100,
                result_protocol="setup_draft",
            ),
            WorkflowNode(
                key="review",
                kind="model",
                instruction="Review the whole current proposal and original needs",
                successors=("correction", "review"),
                max_iterations=100,
                result_protocol="setup_review",
            ),
            WorkflowNode(
                key="correction",
                kind="model",
                instruction="Correct causes across the whole current proposal",
                successors=("review", "correction"),
                max_iterations=100,
                result_protocol="setup_draft",
            ),
        ),
        entry_nodes=("interview",),
    )
    ref = WorkflowRef(workflow_id=identifier, version=1, checksum=workflow_checksum(definition))
    common: dict[str, Any] = dict(
        now=now, epoch=epoch, authority=authority, grants=grants, decisions=decisions
    )
    if (
        connection.execute(
            "SELECT 1 FROM workflow_versions WHERE workflow_id=? AND version=1", (str(identifier),)
        ).fetchone()
        is None
    ):
        _store_definition(
            connection,
            WorkflowRequest(
                operation_id=request.operation_id,
                space_id=request.space_id,
                actor=request.actor,
                action="create_definition",
                workflow_id=identifier,
                definition=definition,
            ),
            now,
            system=True,
        )
    _definition(connection, ref)
    root = uuid5(request.setup_id, "workflow-root")
    start = WorkflowRequest(
        operation_id=request.operation_id,
        space_id=request.space_id,
        actor=request.actor,
        action="start",
        workflow=ref,
        root_work_id=root,
        activity_id=request.activity_id,
        source_refs=sources,
    )
    apply_workflow_change(connection, start, **common)
    return ref, root


def setup_workflow_add_stage(
    connection: sqlite3.Connection,
    request: Any,
    state: Any,
    child: PlanChild,
    packet: ArtifactRef,
    *,
    now: str,
    epoch: int,
    authority: LocalAuthority,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> None:
    """A setup stage is a child in the one root WorkPlan; old stages remain addressed."""
    from .composition import _plan

    root = state.root_work_id
    assert root
    common: dict[str, Any] = dict(
        now=now, epoch=epoch, authority=authority, grants=grants, decisions=decisions
    )
    ref, revision, _, _ = _run(connection, root)
    base = WorkflowRequest(
        operation_id=request.operation_id,
        space_id=request.space_id,
        actor=request.actor,
        action="advance",
        root_work_id=root,
        activity_id=state.activity_id,
        expected_revision=revision,
    )
    current = _plan(connection, root)
    nodes = _nodes(connection, root)
    # The host interview produces a checked context result once preparation starts.
    interview = next(item for item in nodes if item.key == "interview")
    if interview.validation_id is None:
        bind = base.model_copy(update={"action": "bind_node", "node_key": "interview"})
        apply_workflow_change(connection, bind, **common)
        host_output = uuid5(request.operation_id, "interview-output")
        _effect(
            connection,
            base,
            CreateArtifactRequest,
            artifact_id=host_output,
            media_type="text/plain",
            content=WorkflowNodeResult(
                outcome="result",
                values={"input_version": state.input_version},
                next_nodes=(request.stage_kind,),
            )
            .model_dump_json()
            .encode(),
            **common,
        )
        work_revision = _subject_current(connection, interview.work_id, "work")[0]
        _effect(
            connection,
            base,
            LinkWorkOutputRequest,
            work_id=interview.work_id,
            expected_revision=work_revision,
            output=LinkedOutput(
                slot="report", artifact=ArtifactRef(artifact_id=host_output, revision=1)
            ),
            **common,
        )
        validate = base.model_copy(
            update={
                "action": "validate_output",
                "node_key": "interview",
                "output": ArtifactRef(artifact_id=host_output, revision=1),
                "expected_revision": _run(connection, root)[1],
            }
        )
        apply_workflow_change(connection, validate, **common)
        nodes = _nodes(connection, root)
    previous = nodes[-1]
    leaves = (_validation_leaf(previous),) if previous.validation_id else ()
    readiness = PlanCondition(kind="all", members=leaves) if leaves else None
    child = child.model_copy(update={"readiness": readiness})
    key = request.stage_kind
    iteration = 1 + max((item.iteration for item in nodes if item.key == key), default=0)
    role = key if iteration == 1 else f"{key}-{iteration}"
    child = child.model_copy(update={"role": role})
    plan = current.plan.model_copy(update={"children": current.plan.children + (child,)})
    decisions_nodes = tuple(
        PlanNodeDecision(role=item.role, work_id=item.work_id, decision="keep")
        for item in current.plan.children
    ) + (PlanNodeDecision(role=role, work_id=child.work_id, decision="add"),)
    _effect(
        connection,
        base,
        ReviseActivePlanRequest,
        work_id=root,
        expected_work_revision=_subject_current(connection, root, "work")[0],
        expected_plan_revision=current.revision,
        plan=plan,
        nodes=decisions_nodes,
        **common,
    )
    connection.execute(
        "INSERT INTO workflow_nodes VALUES (?,?,?,?,?,?,?,?)",
        (
            str(root),
            key,
            iteration,
            role,
            str(child.work_id),
            str(packet.artifact_id),
            packet.revision,
            request.stage_model.model_dump_json() if request.stage_model else None,
        ),
    )
    connection.execute(
        "INSERT OR IGNORE INTO workflow_edges VALUES (?,'packet',?,?)",
        (str(root), str(packet.artifact_id), packet.revision),
    )
    _effect(
        connection,
        base,
        IssueChildWorkRequest,
        parent_work_id=root,
        work_id=child.work_id,
        expected_plan_revision=current.revision + 1,
        expected_work_revision=_subject_current(connection, child.work_id, "work")[0],
        **common,
    )
    _event(
        connection,
        base,
        _run(connection, root)[1] + 1,
        now,
        {"stage": key, "work_id": str(child.work_id)},
    )


def setup_workflow_complete_stage(
    connection: sqlite3.Connection,
    request: Any,
    state: Any,
    stage: Any,
    issues: tuple[SetupValidationIssue, ...],
    *,
    now: str,
) -> None:
    root = state.root_work_id
    assert root and request.output
    node = next(item for item in _nodes(connection, root) if item.work_id == stage.work_id)
    definition = _definition(connection, _run(connection, root)[0])
    contract = next(item for item in definition.nodes if item.key == node.key)
    work_revision = _subject_current(connection, node.work_id, "work")[0]
    work = WorkState.model_validate(_subject_state(connection, node.work_id, work_revision))
    digest = (
        hashlib.sha256(
            canonical_json([ref.model_dump(mode="json") for ref in work.inputs]).encode()
        )
        .hexdigest()
        .upper()
    )
    # Schema16 stage packets have already passed the exact typed setup validator.
    result = WorkflowNodeResult(outcome="result", values={"input_version": state.input_version})
    connection.execute(
        "INSERT INTO workflow_validations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            str(request.operation_id),
            str(root),
            str(node.work_id),
            work_revision,
            str(request.output.artifact_id),
            request.output.revision,
            digest,
            hashlib.sha256(contract.model_dump_json().encode()).hexdigest().upper(),
            result.model_dump_json(),
            canonical_json([item.model_dump(mode="json") for item in issues]),
            now,
        ),
    )
    connection.execute(
        "INSERT OR IGNORE INTO workflow_edges VALUES (?,'output',?,?)",
        (str(root), str(request.output.artifact_id), request.output.revision),
    )
    base = WorkflowRequest(
        operation_id=request.operation_id,
        space_id=request.space_id,
        actor=request.actor,
        action="validate_output",
        root_work_id=root,
    )
    _event(
        connection,
        base,
        _run(connection, root)[1] + 1,
        now,
        {"stage": node.key, "issues": [item.model_dump(mode="json") for item in issues]},
    )
