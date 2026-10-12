"""Validated data effects and derived indexes in the ordinary Core transaction."""

from __future__ import annotations

import hashlib
import sqlite3
from contextvars import ContextVar
from datetime import UTC, date, datetime
from typing import Any, cast
from uuid import UUID, uuid5

from .data_formats import field_references, validate_format, validate_values
from .models import (
    ActivityStructureState,
    DataEntryState,
    DataFormatState,
    KnowledgeBody,
    KnowledgeRef,
    MemorySelector,
    ResultValidationIssue,
    WorkState,
)
from .storage import FoundationError, canonical_json

APPLYING_STRUCTURE: ContextVar[bool] = ContextVar("applying_activity_structure", default=False)


class OutputValidationError(FoundationError):
    """A rejected typed output with stable field diagnostics, never an applied result."""

    def __init__(self, detail: str, issues: tuple[ResultValidationIssue, ...]) -> None:
        super().__init__("invalid_output", detail)
        self.issues = issues

    def __reduce__(self) -> Any:
        return type(self), (self.detail, self.issues)


def exact_state(
    connection: sqlite3.Connection, ref: KnowledgeRef, actor: str, epoch: int
) -> KnowledgeBody:
    from .knowledge import BODY_ADAPTER, _require_ref

    _require_ref(connection, ref, actor, epoch)
    row = connection.execute(
        "SELECT payload,sha256 FROM knowledge_revisions WHERE record_id=? AND revision=?",
        (str(ref.record_id), ref.revision),
    ).fetchone()
    if row is None or row[0] is None:
        raise FoundationError("content_unavailable", "Exact data definition is unavailable")
    if hashlib.sha256(row[0]).hexdigest().upper() != row[1]:
        raise FoundationError("corrupt_content", "Exact data checksum differs")
    return BODY_ADAPTER.validate_json(row[0])


def head_ref(connection: sqlite3.Connection, activity_id: UUID) -> KnowledgeRef | None:
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 15:
        return None
    row = connection.execute(
        "SELECT record_id,revision FROM structure_heads WHERE activity_id=?", (str(activity_id),)
    ).fetchone()
    return KnowledgeRef(record_id=UUID(row[0]), revision=row[1]) if row else None


def work_structure(connection: sqlite3.Connection, work_id: UUID) -> KnowledgeRef | None:
    from .operations import _subject_state

    row = connection.execute(
        "SELECT current_revision FROM subject_records WHERE record_id=? "
        "AND kind='work' AND status!='deleted'",
        (str(work_id),),
    ).fetchone()
    if row is None:
        raise FoundationError("not_found", "Work is unavailable")
    return WorkState.model_validate(_subject_state(connection, work_id, row[0])).structure


def procedure_run_for_work(
    connection: sqlite3.Connection, work_id: UUID
) -> tuple[str, str, int] | None:
    """Find the nearest procedure ancestor without changing a child's own Work identity."""
    return cast(
        tuple[str, str, int] | None,
        connection.execute(
            "WITH RECURSIVE ancestors(work_id,depth) AS (SELECT ?,0 UNION "
            "SELECT p.parent_id,a.depth+1 FROM ancestors a JOIN "
            "(SELECT child_id,parent_id FROM work_plan_children UNION "
            "SELECT child_id,parent_id FROM work_plan_members) p ON p.child_id=a.work_id) "
            "SELECT r.run_id,r.snapshot_id,r.snapshot_revision FROM ancestors a "
            "JOIN procedure_runs r ON r.work_id=a.work_id ORDER BY a.depth LIMIT 1",
            (str(work_id),),
        ).fetchone(),
    )


def check_context_pins(
    connection: sqlite3.Connection, context: object, actor: str, epoch: int
) -> None:
    from .models import ContextState, MemoryViewState

    if not isinstance(context, ContextState):
        return
    if context.pinned_structure is None and context.procedure_snapshot is None:
        return
    if context.work_id is None or int(connection.execute("PRAGMA user_version").fetchone()[0]) < 15:
        raise FoundationError("invalid_context", "Data context pins require their exact Work")
    if context.pinned_structure is not None:
        if work_structure(connection, context.work_id) != context.pinned_structure:
            raise FoundationError("stale_structure", "Context structure differs from its Work pin")
        exact_state(connection, context.pinned_structure, actor, epoch)
        check_data_access(
            connection,
            context.pinned_structure.record_id,
            context.pinned_structure.revision,
            actor,
            epoch,
        )
    if context.procedure_snapshot is not None:
        from .operations import _subject_state

        work_row = connection.execute(
            "SELECT current_revision FROM subject_records WHERE record_id=?",
            (str(context.work_id),),
        ).fetchone()
        work = WorkState.model_validate(_subject_state(connection, context.work_id, work_row[0]))
        for original_input in work.inputs:
            check_data_access(
                connection, original_input.artifact_id, original_input.revision, actor, epoch
            )
        row = procedure_run_for_work(connection, context.work_id)
        ref = context.procedure_snapshot
        if row is None or row[1:] != (str(ref.record_id), ref.revision):
            raise FoundationError(
                "stale_basis", "Context snapshot differs from the saved procedure intent"
            )
        selected = exact_state(connection, ref, actor, epoch)
        if (
            not isinstance(selected, MemoryViewState)
            or selected.selection is None
            or selected.selection.cache
        ):
            raise FoundationError(
                "invalid_context", "Procedure input must be an immutable selection"
            )
        from .knowledge import _require_ref

        for original in selected.selection.members:
            _require_ref(connection, original, actor, epoch)
            check_data_access(connection, original.record_id, original.revision, actor, epoch)


def validate_output_envelope(
    connection: sqlite3.Connection,
    work_id: UUID,
    work: WorkState,
    contract: object,
    content: bytes,
    actor: str,
    epoch: int,
    *,
    attempt_id: UUID | None = None,
) -> None:
    from pydantic import ValidationError

    from .models import DataOutputEnvelope, OutputContract

    if not isinstance(contract, OutputContract) or contract.format_ref is None:
        return
    try:
        envelope = DataOutputEnvelope.model_validate_json(content)
    except ValidationError as error:
        schema_fields = DataOutputEnvelope.model_json_schema()["properties"]
        issues = []
        for problem in error.errors(include_input=False, include_context=False, include_url=False)[
            :16
        ]:
            path = tuple(problem["loc"])
            allowed: tuple[str, ...] = ()
            if problem["type"] == "extra_forbidden":
                allowed = tuple(schema_fields)
            elif path and problem["type"] == "literal_error":
                field = schema_fields.get(path[0], {})
                if "const" in field:
                    allowed = (str(field["const"]),)
                elif "enum" in field:
                    allowed = tuple(str(value) for value in field["enum"])
            issues.append(
                ResultValidationIssue(
                    code=str(problem["type"]),
                    path=path,
                    message=str(problem["msg"])[:2048],
                    allowed_values=allowed,
                )
            )
        raise OutputValidationError(
            "Typed output must use the data result envelope", tuple(issues)
        ) from error
    if not envelope.entries and not contract.allow_empty:
        raise FoundationError("invalid_output", "This output requires typed data entries")
    if len(set(envelope.entries)) != len(envelope.entries):
        raise FoundationError("invalid_output", "Typed output cannot duplicate a revision")
    producer_id = work_id
    if work.method != "none":
        from .composition import _plan

        plan = _plan(connection, work_id).plan
        binding = next(
            (item for item in plan.output_bindings if item.parent_slot == contract.slot), None
        )
        if binding is not None:
            producer_id = next(item.work_id for item in plan.children if item.role == binding.role)
    for ref in envelope.entries:
        state = exact_state(connection, ref, actor, epoch)
        if (
            not isinstance(state, DataEntryState)
            or state.format_ref != contract.format_ref
            or (
                state.work_id != producer_id
                or state.scope_activity_id != work.activity_id
                or state.structure != work.structure
                or (
                    producer_id == work_id
                    and attempt_id is not None
                    and state.attempt_id != attempt_id
                )
            )
        ):
            raise FoundationError(
                "invalid_output",
                "Output entry differs from the exact Work format, scope or Attempt",
            )
        check_data_access(connection, ref.record_id, ref.revision, actor, epoch)
    row = procedure_run_for_work(connection, work_id)
    if row is not None and envelope.basis_snapshot != KnowledgeRef(
        record_id=UUID(row[1]), revision=row[2]
    ):
        raise FoundationError(
            "invalid_output", "Procedure output must retain its exact input snapshot"
        )
    if not envelope.complete and not envelope.limitations:
        raise FoundationError("invalid_output", "Incomplete result must explain remaining input")


def data_references(
    connection: sqlite3.Connection, state: DataEntryState
) -> list[tuple[str, KnowledgeRef]]:
    row = connection.execute(
        "SELECT payload FROM knowledge_revisions WHERE record_id=? AND revision=?",
        (str(state.format_ref.record_id), state.format_ref.revision),
    ).fetchone()
    if row is None or row[0] is None:
        raise FoundationError("invalid_format", "Exact format is unavailable")
    definition = DataFormatState.model_validate_json(row[0])
    refs = [("data_format", state.format_ref)] + [("data_basis", ref) for ref in state.bases]
    if state.structure is not None:
        refs.append(("data_structure", state.structure))
    if state.scope_activity_id is not None:
        scope_row = connection.execute(
            "SELECT current_revision FROM subject_records WHERE "
            "record_id=? AND kind='activity' AND status!='deleted'",
            (str(state.scope_activity_id),),
        ).fetchone()
        if scope_row is None:
            raise FoundationError("not_found", "Data Activity is unavailable")
        refs.append(
            ("data_scope", KnowledgeRef(record_id=state.scope_activity_id, revision=scope_row[0]))
        )
    if state.selection is not None:
        refs.append(("data_selection", state.selection))
    for link in field_references(definition.fields, state.values):
        revision = link.revision
        if link.mode == "current":
            current = connection.execute(
                "SELECT current_revision FROM knowledge_records "
                "WHERE record_id=? AND status='active'",
                (str(link.record_id),),
            ).fetchone()
            if current is None:
                raise FoundationError("not_found", "Related data object is unavailable")
            revision = current[0]
        refs.append(
            (
                "data_current" if link.mode == "current" else "data_exact",
                KnowledgeRef(record_id=link.record_id, revision=cast(int, revision)),
            )
        )
    return refs


def validate_data_state(
    connection: sqlite3.Connection, state: KnowledgeBody, actor: str, epoch: int
) -> KnowledgeBody:
    from .operations import _authorize

    if not isinstance(state, (DataFormatState, DataEntryState, ActivityStructureState)):
        return state
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 15:
        raise FoundationError("upgrade_required", "Data contracts need explicit schema 15")
    scope = state.scope_activity_id
    if state.memory is not None and state.memory.activity_id != scope:
        raise FoundationError("wrong_scope", "Memory organization cannot change data origin")
    if scope is not None:
        _authorize(
            connection,
            actor=actor,
            action="artifact.write",
            epoch=epoch,
            resource_type="activity",
            resource_id=scope,
        )
    if isinstance(state, DataFormatState):
        validate_format(state)
        return state
    if isinstance(state, ActivityStructureState):
        if not APPLYING_STRUCTURE.get():
            raise FoundationError("permission_denied", "Structure requires reviewed activation")
        return state
    definition = exact_state(connection, state.format_ref, actor, epoch)
    if not isinstance(definition, DataFormatState):
        raise FoundationError("wrong_kind", "Data entry must reference an exact DataFormat")
    if definition.role != state.role or state.status not in definition.statuses:
        raise FoundationError("invalid_data", "Role or status differs from its declared format")
    structure_ref = state.structure
    if state.work_id is not None:
        structure_ref = work_structure(connection, state.work_id)
        row = connection.execute(
            "SELECT parent_id FROM subject_records WHERE record_id=?", (str(state.work_id),)
        ).fetchone()
        if row is None or row[0] != (str(scope) if scope else None):
            raise FoundationError("wrong_scope", "Work data cannot change another Activity")
    if structure_ref is None and scope is not None:
        structure_ref = head_ref(connection, scope)
    if state.work_id is None and scope is not None:
        stopped = connection.execute(
            "SELECT status FROM structure_heads WHERE activity_id=?", (str(scope),)
        ).fetchone()
        if stopped is not None and stopped[0] != "active":
            raise FoundationError(
                "structure_stopped", "Resume or restore the structure before new writes"
            )
    if structure_ref is None:
        raise FoundationError("format_not_active", "Data entry requires an admitted structure")
    structure = exact_state(connection, structure_ref, actor, epoch)
    if (
        not isinstance(structure, ActivityStructureState)
        or (scope is not None and structure.scope_activity_id != scope)
        or state.format_ref not in (*structure.formats.values(),)
    ):
        raise FoundationError("format_not_active", "Format is not admitted by this structure")
    if scope is None:
        _authorize(
            connection, actor=actor, action="artifact.write", epoch=epoch, resource_type="space"
        )
    if state.attempt_id is not None and state.work_id is not None and state.session_id is not None:
        from .execution import _check_attempt_basis

        _check_attempt_basis(
            connection, state.attempt_id, state.work_id, state.session_id, epoch, actor=actor
        )
    values = validate_values(definition.fields, state.values)
    updates: dict[str, object] = {"values": values, "structure": structure_ref}
    if definition.time_field is not None and values.get(definition.time_field) is not None:
        field = next(item for item in definition.fields if item.key == definition.time_field)
        timestamp = str(values[field.key])
        if field.type == "date":
            value_date = date.fromisoformat(timestamp)
            if state.event_date is not None and state.event_date != value_date:
                raise FoundationError("invalid_data", "Event date contradicts its declared field")
            updates["event_date"] = value_date
        else:
            value_at = datetime.fromisoformat(timestamp)
            if state.event_at is not None and state.event_at != value_at:
                raise FoundationError("invalid_data", "Event time contradicts its declared field")
            updates["event_at"] = value_at
    return state.model_copy(update=updates)


def index_data(
    connection: sqlite3.Connection, record_id: UUID, state: KnowledgeBody, revision: int
) -> None:
    if not isinstance(state, DataEntryState):
        return
    identifier = str(record_id)
    connection.execute("DELETE FROM data_index WHERE record_id=?", (identifier,))
    connection.execute("DELETE FROM data_values WHERE record_id=?", (identifier,))
    connection.execute(
        "INSERT INTO data_index VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            identifier,
            revision,
            str(state.scope_activity_id) if state.scope_activity_id else None,
            str(state.format_ref.record_id),
            state.format_ref.revision,
            state.role,
            state.status,
            state.event_date.isoformat() if state.event_date else None,
            state.event_at.astimezone(UTC).isoformat() if state.event_at else None,
            state.period_from.isoformat() if state.period_from else None,
            state.period_until.isoformat() if state.period_until else None,
            int(state.complete),
        ),
    )
    raw = connection.execute(
        "SELECT payload FROM knowledge_revisions WHERE record_id=? AND revision=?",
        (str(state.format_ref.record_id), state.format_ref.revision),
    ).fetchone()[0]
    definition = DataFormatState.model_validate_json(raw)
    for field in definition.fields:
        if field.indexed and field.key in state.values:
            value = state.values[field.key]
            indexed = str(value)
            if field.type == "ref" and isinstance(value, dict):
                indexed = str(value["record_id"])
            connection.execute(
                "INSERT INTO data_values VALUES (?,?,?,?,?)",
                (
                    identifier,
                    field.key,
                    field.type,
                    indexed if value is not None else None,
                    int(value is None),
                ),
            )
    if state.external_key is not None:
        activity_key = str(state.scope_activity_id) if state.scope_activity_id else "common"
        existing = connection.execute(
            "SELECT record_id FROM data_external WHERE activity_key=? "
            "AND namespace=? AND external_key=?",
            (activity_key, state.external_namespace, state.external_key),
        ).fetchone()
        if existing is not None and existing[0] != identifier:
            raise FoundationError("duplicate_event", "External identity already has a data address")
        connection.execute(
            "INSERT OR IGNORE INTO data_external VALUES (?,?,?,?)",
            (activity_key, state.external_namespace, state.external_key, identifier),
        )


def data_filter_sql(selector: MemorySelector) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if selector.format_refs:
        clauses.append(
            "(d.format_id,d.format_revision) IN "
            "(SELECT json_extract(value,'$.record_id'),json_extract(value,'$.revision') "
            "FROM json_each(?))"
        )
        params.append(canonical_json([ref.model_dump(mode="json") for ref in selector.format_refs]))
    for name, operator, value in (
        ("event_date", ">=", selector.date_from),
        ("event_date", "<", selector.date_until),
    ):
        if value is not None:
            clauses.append(f"d.{name}{operator}?")
            params.append(value.isoformat())
    for operator, value in ((">=", selector.time_from), ("<", selector.time_until)):
        if value is not None:
            clauses.append(f"d.event_at{operator}?")
            params.append(value.astimezone(UTC).isoformat())
    if selector.data_statuses:
        clauses.append("d.status IN (SELECT value FROM json_each(?))")
        params.append(canonical_json(selector.data_statuses))
    operators = {"eq": "=", "ne": "!=", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}
    for predicate in selector.data_filters:
        test = "v.record_id=d.record_id AND v.field=?"
        params.append(predicate.field)
        if predicate.operator == "missing":
            clauses.append(f"NOT EXISTS (SELECT 1 FROM data_values v WHERE {test})")
            continue
        if predicate.operator == "unknown":
            test += " AND v.unknown=1"
        else:
            operator = operators[predicate.operator]
            test += " AND v.unknown=0 AND CASE WHEN v.type IN ('integer','decimal') "
            test += f"THEN decimal_compare(v.value,?){operator}0 ELSE v.value{operator}? END"
            params.extend((str(predicate.value), str(predicate.value)))
        clauses.append(f"EXISTS (SELECT 1 FROM data_values v WHERE {test})")
    return " AND ".join(clauses or ["1"]), params


def validate_data_selectors(
    connection: sqlite3.Connection, selectors: tuple[MemorySelector, ...], actor: str, epoch: int
) -> None:
    for selector in selectors:
        if selector.format_keys or selector.use_period:
            raise FoundationError(
                "invalid_query", "Resolve local format keys through the structure"
            )
        extended = bool(
            selector.material_roles
            or selector.format_refs
            or selector.data_filters
            or selector.date_from
            or selector.date_until
            or selector.data_statuses
            or selector.time_from
            or selector.time_until
            or selector.kinds
        )
        if extended and int(connection.execute("PRAGMA user_version").fetchone()[0]) < 15:
            raise FoundationError("upgrade_required", "Data selectors require schema 15")
        if selector.data_filters and not selector.format_refs:
            raise FoundationError(
                "invalid_query", "Field predicates require explicit format versions"
            )
        for ref in selector.format_refs:
            definition = exact_state(connection, ref, actor, epoch)
            if not isinstance(definition, DataFormatState):
                raise FoundationError("wrong_kind", "Selector format must be a DataFormat")
            for predicate in selector.data_filters:
                field = next(
                    (field for field in definition.fields if field.key == predicate.field), None
                )
                if field is None or not field.indexed:
                    raise FoundationError(
                        "unsupported_query", "Predicate needs a declared indexed field"
                    )
                if predicate.operator not in ("missing", "unknown"):
                    if field.type == "ref":
                        UUID(str(predicate.value))
                        if predicate.operator not in ("eq", "ne"):
                            raise FoundationError(
                                "unsupported_query", "Relations support equality only"
                            )
                    else:
                        from .data_formats import validate_field

                        validate_field(field, predicate.value)


def sanitize_data_dependency(
    connection: sqlite3.Connection, identifiers: set[str], now: str
) -> None:
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 15:
        return
    for identifier in identifiers:
        retire_data_artifact(connection, identifier, now)
        for table in ("data_index", "data_values", "data_external"):
            connection.execute(f"DELETE FROM {table} WHERE record_id=?", (identifier,))
        connection.execute(
            "DELETE FROM structure_heads WHERE record_id=? OR activity_id=?",
            (identifier, identifier),
        )
        connection.execute("UPDATE data_intake SET reason=NULL WHERE source_id=?", (identifier,))
        connection.execute(
            "UPDATE procedure_runs SET parameters=NULL WHERE snapshot_id=? "
            "OR structure_id=? OR work_id=?",
            (identifier, identifier, identifier),
        )
        connection.execute(
            "UPDATE procedure_intents SET parameters=NULL WHERE structure_id=? OR EXISTS "
            "(SELECT 1 FROM json_tree(procedure_intents.bases) WHERE key='record_id' AND value=?)",
            (identifier, identifier),
        )
        connection.execute(
            "UPDATE procedure_runs SET parameters=NULL WHERE work_id IN ("
            "SELECT s.record_id FROM subject_content s JOIN json_each(s.payload,'$.inputs') i "
            "WHERE json_extract(i.value,'$.artifact_id')=?)",
            (identifier,),
        )


def index_output_bases(
    connection: sqlite3.Connection, artifact_id: UUID, revision: int, content: bytes
) -> None:
    from .models import DataOutputEnvelope

    envelope = DataOutputEnvelope.model_validate_json(content)
    refs = envelope.entries + ((envelope.basis_snapshot,) if envelope.basis_snapshot else ())
    connection.executemany(
        "INSERT OR IGNORE INTO data_artifact_bases VALUES (?,?,?,?)",
        ((str(artifact_id), revision, str(ref.record_id), ref.revision) for ref in refs),
    )


def retire_data_artifact(connection: sqlite3.Connection, identifier: str, now: str) -> None:
    from .composition import sanitize_deleted_dependency

    row = connection.execute(
        "SELECT status FROM records WHERE record_id=? AND kind='artifact'", (identifier,)
    ).fetchone()
    if row is None or row[0] == "deleted":
        return
    assigned = [
        {"work_id": work, "attempt_id": attempt}
        for work, attempt in connection.execute(
            "SELECT a.work_id,a.attempt_id FROM execution_assignments a JOIN execution_attempts t "
            "ON t.attempt_id=a.attempt_id JOIN json_each(t.input_refs_json) j WHERE "
            "json_extract(j.value,'$.artifact_id')=? UNION SELECT a.work_id,a.attempt_id "
            "FROM execution_assignments a JOIN execution_events e ON e.attempt_id=a.attempt_id "
            "JOIN record_revisions r ON r.operation_id=e.operation_id WHERE r.record_id=?",
            (identifier, identifier),
        )
    ]
    retirement = connection.execute(
        "SELECT operation_id FROM record_revisions WHERE record_id=? ORDER BY revision LIMIT 1",
        (identifier,),
    ).fetchone()[0]
    connection.execute(
        "INSERT OR IGNORE INTO deletion_jobs"
        "(operation_id,record_id,status,created_at) VALUES (?,?,'pending',?)",
        (retirement, identifier, now),
    )
    connection.execute(
        "INSERT OR REPLACE INTO maintenance_events VALUES (?,'technical_deletion_targets',?,?)",
        (retirement, now, canonical_json({"artifact_id": identifier, "assigned": assigned})),
    )
    connection.execute("DELETE FROM managed_content WHERE record_id=?", (identifier,))
    connection.execute("UPDATE records SET status='deleted' WHERE record_id=?", (identifier,))
    for (operation,) in connection.execute(
        "SELECT operation_id FROM record_revisions WHERE record_id=?", (identifier,)
    ):
        connection.execute("DELETE FROM receipts WHERE operation_id=?", (operation,))
        connection.execute(
            "UPDATE operations SET fingerprint='DELETED' WHERE operation_id=?", (operation,)
        )
    sanitize_deleted_dependency(
        connection,
        artifact_id=UUID(identifier),
        operation_id=uuid5(UUID(identifier), "retire-data"),
        now=now,
    )


def sanitize_data_revision(connection: sqlite3.Connection, ref: KnowledgeRef, now: str) -> None:
    """Retire one setup-owned edition; older adopted definitions remain addressable."""
    pending = [(str(ref.record_id), ref.revision)]
    visited: set[tuple[str, int]] = set()
    while pending:
        identifier, revision = pending.pop()
        if (identifier, revision) in visited:
            continue
        visited.add((identifier, revision))
        pending.extend(
            connection.execute(
                "SELECT record_id,revision FROM knowledge_edges "
                "WHERE target_id=? AND target_revision=?",
                (identifier, revision),
            )
        )
        for (artifact,) in connection.execute(
            "SELECT artifact_id FROM data_artifact_bases WHERE target_id=? AND target_revision=? "
            "UNION SELECT record_id FROM revision_provenance "
            "WHERE source_record_id=? AND source_revision=?",
            (identifier, revision, identifier, revision),
        ):
            retire_data_artifact(connection, artifact, now)
            pending.extend(
                connection.execute(
                    "SELECT record_id,revision FROM knowledge_edges WHERE target_id=?", (artifact,)
                )
            )
        operation = connection.execute(
            "SELECT operation_id FROM knowledge_revisions WHERE record_id=? AND revision=?",
            (identifier, revision),
        ).fetchone()
        if operation is None:
            continue
        connection.execute(
            "UPDATE knowledge_revisions SET payload=NULL,sha256=NULL "
            "WHERE record_id=? AND revision=?",
            (identifier, revision),
        )
        connection.execute("DELETE FROM receipts WHERE operation_id=?", (operation[0],))
        connection.execute(
            "UPDATE operations SET fingerprint='DELETED' WHERE operation_id=?", (operation[0],)
        )
        connection.execute(
            "DELETE FROM knowledge_fts WHERE record_id=? AND revision=?", (identifier, revision)
        )
        connection.execute(
            "DELETE FROM structure_heads WHERE record_id=? AND revision=?", (identifier, revision)
        )
        connection.execute(
            "UPDATE procedure_runs SET parameters=NULL WHERE "
            "(snapshot_id=? AND snapshot_revision=?) OR (structure_id=? AND structure_revision=?)",
            (identifier, revision, identifier, revision),
        )
        connection.execute(
            "UPDATE procedure_intents SET parameters=NULL WHERE structure_id=? "
            "AND structure_revision=?",
            (identifier, revision),
        )
        for (work,) in connection.execute(
            "SELECT work_id FROM structure_work_pins WHERE record_id=? AND revision=?",
            (identifier, revision),
        ):
            connection.execute("DELETE FROM subject_content WHERE record_id=?", (work,))
            for (effect,) in connection.execute(
                "SELECT operation_id FROM subject_revisions WHERE record_id=?", (work,)
            ):
                connection.execute("DELETE FROM receipts WHERE operation_id=?", (effect,))
                connection.execute(
                    "UPDATE operations SET fingerprint='DELETED' WHERE operation_id=?", (effect,)
                )
        row = connection.execute(
            "SELECT current_revision FROM knowledge_records WHERE record_id=?", (identifier,)
        ).fetchone()
        if row and row[0] == revision:
            connection.execute(
                "UPDATE knowledge_records SET status='unavailable' WHERE record_id=?", (identifier,)
            )
            for table in (
                "memory_index",
                "memory_topics",
                "data_index",
                "data_values",
                "data_external",
            ):
                connection.execute(f"DELETE FROM {table} WHERE record_id=?", (identifier,))


def check_data_access(
    connection: sqlite3.Connection, record_id: UUID, revision: int, actor: str, epoch: int
) -> None:
    from .knowledge import _require_ref
    from .operations import _authorize

    row = connection.execute(
        "SELECT kind FROM knowledge_records WHERE record_id=?", (str(record_id),)
    ).fetchone()
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 15:
        return
    if (
        row is None or row[0] not in ("data_entry", "data_format", "activity_structure")
    ) and not connection.execute(
        "SELECT 1 FROM data_artifact_bases WHERE artifact_id=? AND revision=? UNION ALL "
        "SELECT 1 FROM revision_provenance WHERE record_id=? AND revision=? "
        "AND source_record_id IS NOT NULL LIMIT 1",
        (str(record_id), revision, str(record_id), revision),
    ).fetchone():
        return
    scope = connection.execute(
        "SELECT activity_id FROM memory_index WHERE record_id=?", (str(record_id),)
    ).fetchone()
    if scope is not None and scope[0] is not None:
        _authorize(
            connection,
            actor=actor,
            action="record.read",
            epoch=epoch,
            resource_type="activity",
            resource_id=UUID(scope[0]),
        )
    for target, target_revision in connection.execute(
        "WITH RECURSIVE links(id,revision,target_id,target_revision) AS ("
        "SELECT record_id,revision,target_id,target_revision FROM knowledge_edges UNION "
        "SELECT artifact_id,revision,target_id,target_revision FROM data_artifact_bases UNION "
        "SELECT record_id,revision,source_record_id,source_revision FROM revision_provenance "
        "WHERE source_record_id IS NOT NULL AND source_revision IS NOT NULL), "
        "basis(id,revision) AS (SELECT target_id,target_revision FROM links "
        "WHERE id=? AND revision=? UNION SELECT e.target_id,e.target_revision FROM "
        "links e JOIN basis b ON e.id=b.id AND e.revision=b.revision) "
        "SELECT id,revision FROM basis",
        (str(record_id), revision),
    ):
        _require_ref(
            connection, KnowledgeRef(record_id=UUID(target), revision=target_revision), actor, epoch
        )
        scope = connection.execute(
            "SELECT activity_id FROM memory_index WHERE record_id=?", (target,)
        ).fetchone()
        if scope is not None and scope[0] is not None:
            _authorize(
                connection,
                actor=actor,
                action="record.read",
                epoch=epoch,
                resource_type="activity",
                resource_id=UUID(scope[0]),
            )


__all__ = ["head_ref", "work_structure"]
