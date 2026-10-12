"""Public data queries, exact calculations, intake and ordinary procedure Work."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .data_formats import json_schema, validate_values
from .data_migration import upgrade_structures_space
from .data_store import exact_state, head_ref
from .knowledge import _checked_read, _require_ref, apply_knowledge_change, read_knowledge
from .memory import memory_catalog, prepare_memory_cache, refresh_intake
from .models import (
    ActivityStructureState,
    ArtifactRef,
    CreateArtifactRequest,
    CreateCompositeWorkRequest,
    CreateKnowledgeRequest,
    CreateWorkRequest,
    DataEntryState,
    DataFormatState,
    DataOutputEnvelope,
    IngestDataRequest,
    KnowledgeRef,
    MemorySelector,
    MemoryViewState,
    OperationReceipt,
    PrepareProcedureRequest,
    ReviseKnowledgeRequest,
    SourceState,
    StartProcedureRequest,
    WorkState,
)
from .operations import LocalAuthority, _authorize, _local_space, apply_operation
from .storage import FoundationError, canonical_json, space_connection


def output_publication_contracts(work: WorkState) -> tuple[dict[str, Any], ...]:
    """Describe actual output validation without changing Work, rights or its results."""

    contracts: list[dict[str, Any]] = []
    for output in work.expected_outputs:
        typed = output.format_ref is not None
        requirements = (
            (
                "Publish one JSON object matching content_schema; entries are exact retained "
                "DataEntry revisions, not new inline data or a summary of unsaved entries.",
                "Each entry must use this slot's exact format_ref and the current Work's "
                "Activity and structure. Current Core read and write rights still apply.",
                "Direct output entries belong to the current Work and publishing Attempt. "
                "For a composite output binding, entries belong to its bound producing child.",
                "For a procedure Work or its descendant, basis_snapshot must be the exact "
                "input snapshot returned by procedure_for_work, not a newly selected snapshot.",
                "Entry revision references must not repeat. Empty entries are allowed only "
                "when allow_empty is true.",
                "An incomplete output (complete=false) must retain non-empty limitations.",
            )
            if typed
            else ("Publish the actual content in the declared media_type.",)
        )
        contracts.append(
            {
                "slot": output.slot,
                "media_type": output.media_type,
                "format_ref": output.format_ref.model_dump(mode="json")
                if output.format_ref is not None
                else None,
                "allow_empty": output.allow_empty,
                "allow_incomplete": True if typed else None,
                "content_schema": DataOutputEnvelope.model_json_schema() if typed else None,
                "technical_requirements": requirements,
            }
        )
    return tuple(contracts)


def describe_structure(
    path: Path, activity_id: UUID, authority: LocalAuthority, *, work_id: UUID | None = None
) -> dict[str, Any]:
    from .data_store import work_structure

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="activity",
            resource_id=activity_id,
        )
        ref = (
            work_structure(connection, work_id)
            if work_id is not None
            else head_ref(connection, activity_id)
        )
        if ref is None:
            return {"activity_id": str(activity_id), "structure": None, "legacy": True}
        state = exact_state(connection, ref, authority.actor, info.execution_epoch)
        if not isinstance(state, ActivityStructureState) or state.scope_activity_id != activity_id:
            raise FoundationError("wrong_scope", "Structure belongs to another Activity")
        return {
            "activity_id": str(activity_id),
            "structure": ref.model_dump(mode="json"),
            "state": state.model_dump(mode="json"),
            "legacy": False,
        }


def read_format(path: Path, ref: KnowledgeRef, authority: LocalAuthority) -> dict[str, Any]:
    item = read_knowledge(path, ref.record_id, authority, revision=ref.revision)
    if not isinstance(item.state, DataFormatState):
        raise FoundationError("wrong_kind", "Address must name an exact DataFormat")
    return {
        "ref": ref.model_dump(mode="json"),
        "definition": item.state.model_dump(mode="json"),
        "json_schema": json_schema(item.state),
    }


def query_entries(
    path: Path,
    authority: LocalAuthority,
    selectors: tuple[MemorySelector, ...],
    *,
    cache: bool = False,
    max_bytes: int = 16384,
) -> dict[str, object]:
    if not selectors:
        raise FoundationError(
            "invalid_query", "Choose an Activity, format, period or data addresses"
        )
    if any(selector.kinds and selector.kinds != ("data_entry",) for selector in selectors):
        raise FoundationError("invalid_query", "Data queries select data entries")
    data_selectors = tuple(item.model_copy(update={"kinds": ("data_entry",)}) for item in selectors)
    return prepare_memory_cache(path, authority, data_selectors, cache=cache, max_bytes=max_bytes)


def list_formats(
    path: Path,
    authority: LocalAuthority,
    *,
    activity_id: UUID | None = None,
    limit: int = 25,
    cursor: str | None = None,
) -> dict[str, object]:
    return memory_catalog(
        path,
        authority,
        selectors=(
            MemorySelector(
                activity_ids=(activity_id,) if activity_id else (),
                common=activity_id is None,
                kinds=("data_format",),
            ),
        ),
        limit=limit,
        cursor=cursor,
    )


def aggregate_entries(
    path: Path,
    selection: KnowledgeRef,
    authority: LocalAuthority,
    *,
    field: str | None = None,
    operation: str = "count",
    group_by: str | None = None,
    group_period: str | None = None,
    timezone: str = "UTC",
    limit: int = 100,
    cursor: str | None = None,
    precision: int = 6,
) -> dict[str, Any]:
    if (
        operation not in ("count", "sum", "min", "max", "mean", "last")
        or not 0 <= precision <= 1000
    ):
        raise FoundationError("unsupported_query", "Unsupported aggregate or precision")
    if group_period not in (None, "day", "week", "month") or not 1 <= limit <= 100:
        raise FoundationError("unsupported_query", "Unsupported grouping or page size")
    try:
        calendar = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise FoundationError("invalid_timezone", "Use an installed IANA timezone") from error
    groups: dict[str, dict[str, Any]] = {}
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        checked_snapshot = _checked_read(
            connection, info, authority, selection.record_id, selection.revision
        )
        snapshot = checked_snapshot.state
        if not isinstance(snapshot, MemoryViewState) or snapshot.selection is None:
            raise FoundationError("wrong_kind", "Aggregate requires an exact memory selection")
        formats: dict[KnowledgeRef, DataFormatState] = {}
        used: list[KnowledgeRef] = []
        roots = (
            snapshot.selection.query_members
            if snapshot.selection.query_members is not None
            else snapshot.selection.members
        )
        for ref in roots:
            item = _checked_read(connection, info, authority, ref.record_id, ref.revision)
            if not isinstance(item.state, DataEntryState):
                continue
            entry = item.state
            definition = formats.get(entry.format_ref)
            if definition is None:
                state = exact_state(
                    connection, entry.format_ref, authority.actor, info.execution_epoch
                )
                if not isinstance(state, DataFormatState):
                    raise FoundationError("wrong_kind", "Entry format is unavailable")
                definition = state
                formats[entry.format_ref] = definition
            declared = {item.key: item for item in definition.fields}
            if field is not None and field not in declared:
                raise FoundationError("unsupported_query", "Aggregate field is not declared")
            if group_by is not None and (
                group_by not in declared or declared[group_by].type in ("object", "list")
            ):
                raise FoundationError("unsupported_query", "Grouping requires a declared scalar")
            group_value: Any = entry.values.get(group_by) if group_by else None
            if group_by and group_by not in entry.values:
                group_value = {"state": "missing"}
            if group_period is not None:
                if definition.time_field is None:
                    raise FoundationError(
                        "unsupported_query", "Calendar grouping needs a declared time"
                    )
                raw_time = entry.values.get(definition.time_field)
                if raw_time is None:
                    group_value = {
                        "state": "unknown" if definition.time_field in entry.values else "missing"
                    }
                else:
                    time_field = declared[definition.time_field]
                    day = (
                        datetime.fromisoformat(str(raw_time)).astimezone(calendar).date()
                        if time_field.type == "datetime"
                        else date.fromisoformat(str(raw_time))
                    )
                    begin = (
                        day - timedelta(days=day.weekday())
                        if group_period == "week"
                        else day.replace(day=1)
                        if group_period == "month"
                        else day
                    )
                    group_value = {
                        "period": group_period,
                        "from": begin.isoformat(),
                        "timezone": timezone,
                        "group": group_value,
                    }
            # Different definitions stay separate; no implicit unit/schema conversion.
            key = canonical_json(
                {
                    "format": entry.format_ref.model_dump(mode="json"),
                    "group": group_value,
                }
            )
            group = groups.setdefault(
                key,
                {
                    "format": entry.format_ref.model_dump(mode="json"),
                    "group": group_value,
                    "records": 0,
                    "known": 0,
                    "missing": 0,
                    "unknown": 0,
                    "unit": declared[field].unit if field else None,
                    "sum": Decimal(0),
                    "minimum": None,
                    "maximum": None,
                    "last": None,
                    "digits": 28,
                    "refs": [],
                },
            )
            group["records"] += 1
            group["refs"].append(ref.model_dump(mode="json"))
            used.append(ref)
            if field is None:
                if operation != "count":
                    raise FoundationError("invalid_query", "This operation requires a field")
                continue
            if field not in entry.values:
                group["missing"] += 1
                continue
            value = entry.values[field]
            if value is None:
                group["unknown"] += 1
                continue
            group["known"] += 1
            if operation == "last":
                if definition.time_field is None or entry.values.get(definition.time_field) is None:
                    raise FoundationError(
                        "unsupported_query", "Last requires a known declared time"
                    )
                time_value = str(entry.values[definition.time_field])
                ordering = (
                    datetime.fromisoformat(time_value).astimezone(UTC)
                    if declared[definition.time_field].type == "datetime"
                    else datetime.combine(date.fromisoformat(time_value), datetime.min.time(), UTC)
                )
                last = (ordering, str(ref.record_id), value)
                if group["last"] is None or last[:2] > group["last"][:2]:
                    group["last"] = last
            elif operation != "count":
                if declared[field].type not in ("integer", "decimal"):
                    raise FoundationError(
                        "unsupported_query", "Numeric aggregate needs a numeric field"
                    )
                number = Decimal(str(value))
                group["digits"] = max(
                    group["digits"],
                    len(number.as_tuple().digits) + abs(number.adjusted()) + precision + 3,
                )
                with localcontext() as context:
                    context.prec = group["digits"] + len(str(group["known"]))
                    group["sum"] += number
                group["minimum"] = (
                    number if group["minimum"] is None else min(number, group["minimum"])
                )
                group["maximum"] = (
                    number if group["maximum"] is None else max(number, group["maximum"])
                )
        result = []
        for group in groups.values():
            total, minimum, maximum, last, digits = (
                group.pop(key) for key in ("sum", "minimum", "maximum", "last", "digits")
            )
            aggregate_value: object = None
            if operation == "count":
                aggregate_value = group["known"] if field else group["records"]
            elif group["known"]:
                if operation == "last":
                    aggregate_value = last[2]
                else:
                    with localcontext() as context:
                        context.prec = max(28, digits + len(str(group["known"])) + precision + 3)
                        number = (
                            total
                            if operation in ("sum", "mean")
                            else minimum
                            if operation == "min"
                            else maximum
                        )
                        if operation == "mean":
                            number /= Decimal(group["known"])
                        aggregate_value = format(
                            number.quantize(
                                Decimal(1).scaleb(-precision), rounding=ROUND_HALF_EVEN
                            ),
                            "f",
                        )
            result.append({**group, "value": aggregate_value})
        from .memory import selection_current_for_actor

        current = selection_current_for_actor(
            connection, authority.actor, info.execution_epoch, snapshot.selection
        )
        page_keys = sorted(groups)
        offset = int(cursor or "0")
        if offset < 0 or offset > len(result):
            raise FoundationError("invalid_cursor", "Aggregate cursor is outside this snapshot")
        by_key = dict(zip(groups, result, strict=True))
        page = [by_key[key] for key in page_keys[offset : offset + limit]]
        return {
            "selection": selection.model_dump(mode="json"),
            "operation": operation,
            "field": field,
            "groups": page,
            "bases": [ref for group in page for ref in group["refs"]],
            "next_cursor": str(offset + limit) if offset + limit < len(result) else None,
            "total_groups": len(result),
            "membership_complete": True,
            "current": current,
            "observation_complete": None,
            "limitations": [
                "Complete membership does not establish complete observation of a period"
            ],
            "rounding": "ROUND_HALF_EVEN",
            "precision": precision,
        }


def apply_data_change(
    connection: sqlite3.Connection,
    request: IngestDataRequest | StartProcedureRequest | PrepareProcedureRequest,
    *,
    now: str,
    epoch: int,
    authority: LocalAuthority,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    from .operations import _apply_change

    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 15:
        raise FoundationError("upgrade_required", "Data effects require schema 15")
    state_revision = connection.execute("SELECT state_revision FROM spaces").fetchone()[0]
    if isinstance(request, IngestDataRequest):
        _require_ref(connection, request.source, request.actor, epoch)
        original = exact_state(connection, request.source, request.actor, epoch)
        if not isinstance(original, SourceState) or original.content is None:
            raise FoundationError("invalid_input", "Intake requires a retained original Source")
        signature = hashlib.sha256(
            canonical_json(
                request.model_dump(mode="json", exclude={"operation_id", "protocol_version"})
            ).encode()
        ).hexdigest()
        previous = connection.execute(
            "SELECT operation_id,signature FROM data_deliveries WHERE delivery_key=?",
            (request.delivery_key,),
        ).fetchone()
        if previous is not None:
            if previous[1] != signature:
                raise FoundationError(
                    "delivery_conflict", "Delivery key already describes another batch"
                )
            return {
                "delivery_key": request.delivery_key,
                "operation_id": previous[0],
                "repeated": True,
            }, []
        if len({item.key for item in request.elements}) != len(request.elements):
            raise FoundationError("invalid_request", "Intake element keys must be unique")
        targets: list[dict[str, object]] = []
        for element in request.elements:
            previous_element = connection.execute(
                "SELECT status,record_id,revision FROM data_intake WHERE source_id=? "
                "AND source_revision=? AND element_key=?",
                (str(request.source.record_id), request.source.revision, element.key),
            ).fetchone()
            if previous_element and previous_element[0] == "saved" and element.mutation is None:
                raise FoundationError(
                    "intake_conflict", "A saved element needs an explicit correction"
                )
            record = None
            revision = None
            if element.mutation is not None:
                mutation = element.mutation
                if request.source not in mutation.state.bases:
                    raise FoundationError(
                        "invalid_provenance", "Imported data must name its exact original"
                    )
                if previous_element is not None and previous_element[0] == "saved":
                    if previous_element[1] != str(mutation.record_id):
                        raise FoundationError(
                            "duplicate_event", "Original element already has a data address"
                        )
                    if mutation.expected_revision is None:
                        from .data_store import validate_data_state

                        old_state = exact_state(
                            connection,
                            KnowledgeRef(
                                record_id=mutation.record_id, revision=previous_element[2]
                            ),
                            request.actor,
                            epoch,
                        )
                        proposed = validate_data_state(
                            connection, mutation.state, request.actor, epoch
                        )
                        if old_state != proposed:
                            raise FoundationError(
                                "intake_conflict",
                                "Changed content needs an explicit correction revision",
                            )
                        record, revision = previous_element[1], previous_element[2]
                if record is None:
                    kind = (
                        CreateKnowledgeRequest
                        if mutation.expected_revision is None
                        else ReviseKnowledgeRequest
                    )
                    fields: dict[str, Any] = dict(
                        operation_id=request.operation_id,
                        space_id=request.space_id,
                        actor=request.actor,
                        record_id=mutation.record_id,
                        state=mutation.state,
                    )
                    if mutation.expected_revision is not None:
                        fields["expected_revision"] = mutation.expected_revision
                    _authorize(
                        connection,
                        actor=request.actor,
                        action="artifact.write",
                        epoch=epoch,
                        resource_type="artifact",
                        resource_id=mutation.record_id,
                    )
                    result, changed = apply_knowledge_change(
                        connection,
                        kind(**fields),
                        now=now,
                        state_revision=state_revision,
                        epoch=epoch,
                    )
                    targets.extend(changed)
                    record, revision = str(mutation.record_id), result["revision"]
            connection.execute(
                "INSERT INTO data_intake VALUES (?,?,?,?,?,?,?) ON CONFLICT "
                "(source_id,source_revision,element_key) DO UPDATE SET status=excluded.status,"
                "record_id=excluded.record_id,revision=excluded.revision,reason=excluded.reason",
                (
                    str(request.source.record_id),
                    request.source.revision,
                    element.key,
                    element.status,
                    record,
                    revision,
                    element.reason,
                ),
            )
        connection.execute(
            "INSERT INTO data_deliveries VALUES (?,?,?,?,?,?)",
            (
                request.delivery_key,
                str(request.source.record_id),
                request.source.revision,
                int(request.complete),
                str(request.operation_id),
                signature,
            ),
        )
        connection.execute(
            "INSERT INTO data_intake_heads VALUES (?,?,?) ON CONFLICT(source_id,source_revision) "
            "DO UPDATE SET delivery_key=excluded.delivery_key",
            (str(request.source.record_id), request.source.revision, request.delivery_key),
        )
        refresh_intake(connection)
        remaining = connection.execute(
            "SELECT count(*) FROM data_intake WHERE source_id=? AND "
            "source_revision=? AND status='deferred'",
            (str(request.source.record_id), request.source.revision),
        ).fetchone()[0]
        return {
            "delivery_key": request.delivery_key,
            "source": request.source.model_dump(mode="json"),
            "complete": request.complete and remaining == 0,
            "deferred": remaining,
            "entries": targets,
            "repeated": False,
        }, targets
    if isinstance(request, PrepareProcedureRequest):
        intent_values = (
            str(request.structure.record_id),
            request.structure.revision,
            canonical_json(request.parameters),
            request.period_from.isoformat() if request.period_from else None,
            request.period_until.isoformat() if request.period_until else None,
        )
        previous_intent = connection.execute(
            "SELECT structure_id,structure_revision,parameters,period_from,period_until,bases "
            "FROM procedure_intents WHERE activity_id=? AND procedure_key=? AND request_key=?",
            (str(request.activity_id), request.procedure, request.request_key),
        ).fetchone()
        if previous_intent is not None:
            basis = json.loads(previous_intent[5])
            if isinstance(basis, list):
                basis = {"sources": basis, "rerun_of": None}
            if previous_intent[:5] != intent_values or basis != {
                "sources": [ref.model_dump(mode="json") for ref in request.request_basis],
                "rerun_of": str(request.rerun_of) if request.rerun_of else None,
            }:
                raise FoundationError("procedure_conflict", "Saved intent has different parameters")
            return {"prepared": True, "repeated": True}, []
        structure = exact_state(connection, request.structure, request.actor, epoch)
        if not isinstance(structure, ActivityStructureState) or (
            structure.scope_activity_id != request.activity_id
            or head_ref(connection, request.activity_id) != request.structure
        ):
            raise FoundationError(
                "stale_structure", "Prepare against the current Activity structure"
            )
        procedure = next(
            (item for item in structure.procedures if item.key == request.procedure), None
        )
        if procedure is None:
            raise FoundationError("not_found", "Procedure is not declared")
        validate_values(procedure.parameters, request.parameters)
        for ref in request.request_basis:
            _require_ref(connection, ref, request.actor, epoch)
        connection.execute(
            "INSERT INTO procedure_intents VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                str(request.activity_id),
                request.procedure,
                request.request_key,
                *intent_values,
                str(request.operation_id),
                canonical_json(
                    {
                        "sources": [ref.model_dump(mode="json") for ref in request.request_basis],
                        "rerun_of": str(request.rerun_of) if request.rerun_of else None,
                    }
                ),
            ),
        )
        return {"prepared": True, "repeated": False}, []
    prepared = connection.execute(
        "SELECT structure_id,structure_revision,parameters,period_from,period_until,bases "
        "FROM procedure_intents WHERE activity_id=? AND procedure_key=? AND request_key=?",
        (str(request.activity_id), request.procedure, request.request_key),
    ).fetchone()
    if prepared is None:
        raise FoundationError(
            "procedure_unprepared", "Save the procedure intent before selecting inputs"
        )
    basis = json.loads(prepared[5])
    if isinstance(basis, list):
        basis = {"sources": basis, "rerun_of": None}
    if prepared[:5] != (
        str(request.structure.record_id),
        request.structure.revision,
        canonical_json(request.parameters),
        request.period_from.isoformat() if request.period_from else None,
        request.period_until.isoformat() if request.period_until else None,
    ) or basis != {
        "sources": [ref.model_dump(mode="json") for ref in request.request_basis],
        "rerun_of": str(request.rerun_of) if request.rerun_of else None,
    }:
        raise FoundationError("procedure_conflict", "Launch differs from its saved preparation")
    prior_intent = connection.execute(
        "SELECT run_id,work_id,structure_id,structure_revision,parameters,period_from,period_until "
        "FROM procedure_runs WHERE activity_id=? AND procedure_key=? AND request_key=?",
        (str(request.activity_id), request.procedure, request.request_key),
    ).fetchone()
    if prior_intent is not None:
        if (
            prior_intent[2:4] != (str(request.structure.record_id), request.structure.revision)
            or json.loads(prior_intent[4]) != request.parameters
            or prior_intent[5:7]
            != (
                request.period_from.isoformat() if request.period_from else None,
                request.period_until.isoformat() if request.period_until else None,
            )
        ):
            raise FoundationError("procedure_conflict", "Saved request already has another intent")
        return {"run_id": prior_intent[0], "work_id": prior_intent[1], "repeated": True}, []
    structure = exact_state(connection, request.structure, request.actor, epoch)
    if (
        not isinstance(structure, ActivityStructureState)
        or structure.scope_activity_id != request.activity_id
    ):
        raise FoundationError("wrong_scope", "Procedure structure belongs to another Activity")
    if head_ref(connection, request.activity_id) != request.structure:
        raise FoundationError("stale_structure", "New procedure requires the current structure")
    head = connection.execute(
        "SELECT status FROM structure_heads WHERE activity_id=?", (str(request.activity_id),)
    ).fetchone()
    if head is None or head[0] != "active":
        raise FoundationError("structure_stopped", "Structure is stopped")
    procedure = next((item for item in structure.procedures if item.key == request.procedure), None)
    if procedure is None:
        raise FoundationError("not_found", "Procedure is not declared")
    parameters = validate_values(procedure.parameters, request.parameters)
    snapshot = exact_state(connection, request.snapshot, request.actor, epoch)
    if (
        not isinstance(snapshot, MemoryViewState)
        or snapshot.selection is None
        or snapshot.selection.cache
    ):
        raise FoundationError("invalid_input", "Procedure requires an immutable input selection")
    from .memory import selection_current_for_actor

    if not selection_current_for_actor(connection, request.actor, epoch, snapshot.selection):
        raise FoundationError("stale_context", "Procedure input selection changed before launch")
    canonical = {
        "structure": request.structure.model_dump(mode="json"),
        "procedure": request.procedure,
        "parameters": parameters,
        "period_from": str(request.period_from),
        "period_until": str(request.period_until),
        "members": [ref.model_dump(mode="json") for ref in snapshot.selection.members],
    }
    signature = hashlib.sha256(canonical_json(canonical).encode()).hexdigest()
    if request.rerun_of is not None:
        predecessor = connection.execute(
            "SELECT activity_id,procedure_key FROM procedure_runs WHERE run_id=?",
            (str(request.rerun_of),),
        ).fetchone()
        if (
            predecessor != (str(request.activity_id), request.procedure)
            or not request.request_basis
        ):
            raise FoundationError(
                "invalid_rerun", "Explicit rerun needs the earlier run and a retained request basis"
            )
        signature = hashlib.sha256(
            canonical_json(
                {
                    **canonical,
                    "rerun_of": str(request.rerun_of),
                    "request_basis": [ref.model_dump(mode="json") for ref in request.request_basis],
                }
            ).encode()
        ).hexdigest()
    logical_key = hashlib.sha256(
        canonical_json(
            {key: value for key, value in canonical.items() if key != "members"}
        ).encode()
    ).hexdigest()
    previous = connection.execute(
        "SELECT run_id,signature,work_id FROM procedure_runs WHERE "
        "activity_id=? AND procedure_key=? AND (request_key=? OR signature=?)",
        (str(request.activity_id), request.procedure, request.request_key, signature),
    ).fetchone()
    if previous is not None:
        return {"run_id": previous[0], "work_id": previous[2], "repeated": True}, []
    active = connection.execute(
        "SELECT r.run_id,r.work_id FROM procedure_runs r WHERE r.activity_id=? "
        "AND r.procedure_key=? AND r.logical_key=? AND (EXISTS (SELECT 1 FROM "
        "execution_attempts a WHERE a.work_id=r.work_id AND a.status='active') "
        "OR EXISTS (SELECT 1 FROM execution_invocations i WHERE i.work_id=r.work_id "
        "AND i.status IN ('admitted','sent','unknown'))) LIMIT 1",
        (str(request.activity_id), request.procedure, logical_key),
    ).fetchone()
    if active is not None:
        return {
            "run_id": active[0],
            "work_id": active[1],
            "repeated": True,
            "pending_update": True,
        }, []
    _authorize(
        connection,
        actor=request.actor,
        action="work.write",
        epoch=epoch,
        resource_type="activity",
        resource_id=request.activity_id,
    )
    work_id = uuid5(request.operation_id, "procedure-work")
    artifact_id = uuid5(request.operation_id, "procedure-input")
    input_content = canonical_json(
        {
            **canonical,
            "selection": request.snapshot.model_dump(mode="json"),
            "request_basis": [ref.model_dump(mode="json") for ref in request.request_basis],
        }
    ).encode()
    input_request = CreateArtifactRequest(
        operation_id=request.operation_id,
        space_id=request.space_id,
        actor=request.actor,
        artifact_id=artifact_id,
        media_type="application/json",
        content=input_content,
    )
    _apply_change(
        connection,
        input_request,
        now=now,
        epoch=epoch,
        authority=authority,
        grants=grants,
        decisions=decisions,
    )
    connection.execute(
        "INSERT INTO data_artifact_bases VALUES (?,1,?,?)",
        (str(artifact_id), str(request.snapshot.record_id), request.snapshot.revision),
    )
    for ref in request.request_basis:
        _require_ref(connection, ref, request.actor, epoch)
        connection.execute(
            "INSERT OR IGNORE INTO data_artifact_bases VALUES (?,1,?,?)",
            (str(artifact_id), str(ref.record_id), ref.revision),
        )
    plan = procedure.plan
    if plan is not None:
        assert procedure.input_slot is not None
        old_input = next(
            value.artifact for value in plan.named_inputs if value.slot == procedure.input_slot
        )
        child_ids = {
            item.work_id: uuid5(request.operation_id, "child:" + item.role)
            for item in plan.children
        }
        plan = plan.model_copy(
            update={
                "named_inputs": tuple(
                    item.model_copy(
                        update={"artifact": ArtifactRef(artifact_id=artifact_id, revision=1)}
                    )
                    if item.slot == procedure.input_slot
                    else item
                    for item in plan.named_inputs
                ),
                "children": tuple(
                    item.model_copy(
                        update={
                            "work_id": child_ids[item.work_id],
                            "state": item.state.model_copy(
                                update={
                                    "inputs": tuple(
                                        ArtifactRef(artifact_id=artifact_id, revision=1)
                                        if old == old_input
                                        else old
                                        for old in item.state.inputs
                                    ),
                                }
                            ),
                        }
                    )
                    for item in plan.children
                ),
            }
        )
    state = WorkState(
        activity_id=request.activity_id,
        goal=procedure.goal,
        inputs=tuple(item.artifact for item in plan.named_inputs)
        if plan is not None
        else (ArtifactRef(artifact_id=artifact_id, revision=1),),
        constraints=(structure.instructions,),
        expected_outputs=procedure.outputs,
        method=procedure.method or "none",
        structure=request.structure,
    )
    work_request = (
        CreateCompositeWorkRequest(
            operation_id=request.operation_id,
            space_id=request.space_id,
            actor=request.actor,
            work_id=work_id,
            state=state,
            plan=plan,
        )
        if plan is not None
        else CreateWorkRequest(
            operation_id=request.operation_id,
            space_id=request.space_id,
            actor=request.actor,
            work_id=work_id,
            state=state,
        )
    )
    _apply_change(
        connection,
        work_request,
        now=now,
        epoch=epoch,
        authority=authority,
        grants=grants,
        decisions=decisions,
    )
    connection.execute(
        "INSERT INTO procedure_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            str(request.operation_id),
            str(request.activity_id),
            request.procedure,
            request.request_key,
            signature,
            logical_key,
            str(request.structure.record_id),
            request.structure.revision,
            str(request.snapshot.record_id),
            request.snapshot.revision,
            canonical_json(parameters),
            request.period_from.isoformat() if request.period_from else None,
            request.period_until.isoformat() if request.period_until else None,
            str(work_id),
        ),
    )
    return {"run_id": str(request.operation_id), "work_id": str(work_id), "repeated": False}, [
        {"record_id": str(work_id), "revision": 1},
        {"record_id": str(artifact_id), "revision": 1},
    ]


def ingest_batch(
    path: Path, request: IngestDataRequest, authority: LocalAuthority
) -> OperationReceipt:
    return apply_operation(path, request, authority)


def create_entry(
    path: Path,
    authority: LocalAuthority,
    state: DataEntryState,
    *,
    record_id: UUID | None = None,
    operation_id: UUID | None = None,
) -> OperationReceipt:
    from .storage import read_space

    return apply_operation(
        path,
        CreateKnowledgeRequest(
            operation_id=operation_id or uuid4(),
            space_id=read_space(path).space_id,
            actor=authority.actor,
            record_id=record_id or uuid4(),
            state=state,
        ),
        authority,
    )


def correct_entry(
    path: Path,
    authority: LocalAuthority,
    record_id: UUID,
    expected_revision: int,
    state: DataEntryState,
    *,
    operation_id: UUID | None = None,
) -> OperationReceipt:
    from .storage import read_space

    return apply_operation(
        path,
        ReviseKnowledgeRequest(
            operation_id=operation_id or uuid4(),
            space_id=read_space(path).space_id,
            actor=authority.actor,
            record_id=record_id,
            expected_revision=expected_revision,
            state=state,
        ),
        authority,
    )


def read_entry(path: Path, authority: LocalAuthority, ref: KnowledgeRef) -> dict[str, Any]:
    item = read_knowledge(path, ref.record_id, authority, revision=ref.revision)
    if item.kind != "data_entry":
        raise FoundationError("wrong_kind", "Address must name a DataEntry")
    return {
        "ref": ref.model_dump(mode="json"),
        "state": item.state.model_dump(mode="json") if item.state is not None else None,
        "stale": item.stale,
        "availability": item.availability,
    }


def entry_history(
    path: Path,
    authority: LocalAuthority,
    record_id: UUID,
    *,
    limit: int = 25,
    cursor: str | None = None,
) -> dict[str, object]:
    from .memory import memory_history

    return memory_history(
        path, record_id, authority, limit=limit, after_revision=int(cursor or "0")
    )


def working_set(
    path: Path,
    authority: LocalAuthority,
    activity_id: UUID,
    key: str,
    *,
    work_id: UUID | None = None,
) -> dict[str, object]:
    structure = describe_structure(path, activity_id, authority, work_id=work_id)
    if structure["legacy"]:
        raise FoundationError(
            "structure_required", "Activity has no admitted structured working set"
        )
    definition = ActivityStructureState.model_validate(structure["state"])
    selection = next((item for item in definition.working_sets if item.key == key), None)
    if selection is None:
        raise FoundationError("not_found", "Working set is not declared")
    selectors = tuple(
        item.model_copy(update={"current_activity": False, "activity_ids": (activity_id,)})
        if item.current_activity
        else item
        for item in selection.selectors
    )
    page = memory_catalog(
        path, authority, selectors=selectors, limit=2 if selection.cardinality == "one" else 25
    )
    count = len(cast(list[dict[str, Any]], page["items"]))
    status = (
        "waiting"
        if count == 0
        else "conflict"
        if selection.cardinality == "one" and count > 1
        else "ready"
    )
    return {
        "key": key,
        "status": status,
        "catalog": page,
        "structure": structure["structure"],
        "cardinality": selection.cardinality,
    }


def procedure_status(path: Path, authority: LocalAuthority, run_id: UUID) -> dict[str, Any]:
    from .operations import read_work

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        row = connection.execute(
            "SELECT activity_id,procedure_key,request_key,work_id,structure_id,structure_revision,"
            "snapshot_id,snapshot_revision,parameters,period_from,period_until "
            "FROM procedure_runs WHERE run_id=?",
            (str(run_id),),
        ).fetchone()
        if row is None:
            raise FoundationError("not_found", "Procedure run does not exist")
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="work",
            resource_id=UUID(row[3]),
        )
        work_id = UUID(row[3])
    work = read_work(path, work_id, authority)
    return {
        "run_id": str(run_id),
        "activity_id": row[0],
        "procedure": row[1],
        "request_key": row[2],
        "work_id": row[3],
        "work_revision": work.revision,
        "work": work.state.model_dump(mode="json"),
        "structure": {"record_id": row[4], "revision": row[5]},
        "snapshot": {"record_id": row[6], "revision": row[7]},
        "parameters": json.loads(row[8]) if row[8] else None,
        "period_from": row[9],
        "period_until": row[10],
    }


def procedure_for_work(
    path: Path, authority: LocalAuthority, work_id: UUID
) -> dict[str, Any] | None:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        from .data_store import procedure_run_for_work

        row = procedure_run_for_work(connection, work_id)
    return procedure_status(path, authority, UUID(row[0])) if row else None


def _period(procedure: Any, when: datetime) -> tuple[date | None, date | None]:
    if procedure.period is None:
        return None, None
    day = when.astimezone(ZoneInfo(procedure.timezone or "UTC")).date()
    if procedure.period == "day":
        return day, day + timedelta(days=1)
    if procedure.period == "week":
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=7)
    start = day.replace(day=1)
    return start, (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )


def start_procedure(
    path: Path,
    authority: LocalAuthority,
    activity_id: UUID,
    procedure_key: str,
    request_key: str,
    *,
    parameters: dict[str, Any] | None = None,
    rerun_of: UUID | None = None,
    period_from: date | None = None,
    period_until: date | None = None,
    when: datetime | None = None,
    snapshot: KnowledgeRef | None = None,
    request_basis: tuple[KnowledgeRef, ...] = (),
) -> dict[str, object]:
    from .storage import read_space, utc_now

    if when is not None and when.tzinfo is None:
        raise FoundationError("invalid_time", "Procedure time must include its timezone")

    # Restore the existing intent before computing dates or selecting new inputs.
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        prior = connection.execute(
            "SELECT run_id FROM procedure_runs WHERE activity_id=? "
            "AND procedure_key=? AND request_key=?",
            (str(activity_id), procedure_key, request_key),
        ).fetchone()
        intent = connection.execute(
            "SELECT structure_id,structure_revision,parameters,period_from,period_until,bases "
            "FROM procedure_intents WHERE activity_id=? AND procedure_key=? AND request_key=?",
            (str(activity_id), procedure_key, request_key),
        ).fetchone()
    if prior is not None:
        saved_basis = json.loads(intent[5]) if intent else {}
        saved_rerun = saved_basis.get("rerun_of") if isinstance(saved_basis, dict) else None
        if rerun_of is not None and str(rerun_of) != saved_rerun:
            raise FoundationError(
                "procedure_conflict", "Request key already has another rerun basis"
            )
        status = procedure_status(path, authority, UUID(prior[0]))
        if (
            parameters is not None
            and status["parameters"] != parameters
            or (period_from is not None and status["period_from"] != period_from.isoformat())
            or (period_until is not None and status["period_until"] != period_until.isoformat())
        ):
            raise FoundationError(
                "procedure_conflict", "Request key already has a different saved intent"
            )
        return {**status, "repeated": True}
    described = describe_structure(path, activity_id, authority)
    if described["legacy"]:
        raise FoundationError("structure_required", "Configure this Activity structure first")
    structure = ActivityStructureState.model_validate(described["state"])
    procedure = next((item for item in structure.procedures if item.key == procedure_key), None)
    if procedure is None:
        raise FoundationError("not_found", "Procedure is not declared")
    begin, end = _period(procedure, when or utc_now())
    if period_from is not None or period_until is not None:
        begin, end = period_from, period_until
    normalized = validate_values(
        procedure.parameters,
        parameters
        if parameters is not None
        else json.loads(intent[2])
        if intent and intent[2]
        else {},
    )
    if intent is not None:
        if intent[2] is None:
            raise FoundationError("content_unavailable", "Saved procedure intent basis was deleted")
        if intent[:2] != (described["structure"]["record_id"], described["structure"]["revision"]):
            raise FoundationError(
                "stale_structure", "Saved preparation requires explicit reconsideration"
            )
        saved = json.loads(intent[2])
        if parameters is not None and normalized != saved:
            raise FoundationError("procedure_conflict", "Saved preparation has other parameters")
        normalized = saved
        if (period_from is not None and intent[3] != period_from.isoformat()) or (
            period_until is not None and intent[4] != period_until.isoformat()
        ):
            raise FoundationError("procedure_conflict", "Saved preparation has another period")
        begin, end = (date.fromisoformat(value) if value else None for value in intent[3:5])
        saved_basis = json.loads(intent[5])
        if isinstance(saved_basis, list):
            saved_basis = {"sources": saved_basis, "rerun_of": None}
        if rerun_of is not None and str(rerun_of) != saved_basis["rerun_of"]:
            raise FoundationError("procedure_conflict", "Saved preparation has another rerun basis")
        rerun_of = UUID(saved_basis["rerun_of"]) if saved_basis["rerun_of"] else None
        request_basis = tuple(KnowledgeRef.model_validate(ref) for ref in saved_basis["sources"])
    if (begin is None) != (end is None) or (begin is not None and end is not None and begin >= end):
        raise FoundationError(
            "invalid_period", "Period must have ordered inclusive/exclusive boundaries"
        )
    apply_operation(
        path,
        PrepareProcedureRequest(
            operation_id=uuid4(),
            space_id=read_space(path).space_id,
            actor=authority.actor,
            activity_id=activity_id,
            procedure=procedure_key,
            request_key=request_key,
            structure=KnowledgeRef.model_validate(described["structure"]),
            parameters=normalized,
            rerun_of=rerun_of,
            request_basis=request_basis,
            period_from=begin,
            period_until=end,
        ),
        authority,
    )
    selectors = tuple(
        item.model_copy(
            update={
                **(
                    {"activity_ids": (activity_id,), "current_activity": False}
                    if item.current_activity
                    else {}
                ),
                **(
                    {"date_from": begin, "date_until": end, "use_period": False}
                    if item.use_period
                    else {}
                ),
            }
        )
        for item in procedure.inputs
    )
    if not selectors:
        # No required input means an empty exact snapshot, not the whole Activity.
        selectors = (MemorySelector(empty=True),)
    if snapshot is None:
        selected = prepare_memory_cache(path, authority, selectors, cache=False)
        snapshot = KnowledgeRef(
            record_id=UUID(str(selected["selection_id"])), revision=int(str(selected["revision"]))
        )
    request = StartProcedureRequest(
        operation_id=uuid4(),
        space_id=read_space(path).space_id,
        actor=authority.actor,
        activity_id=activity_id,
        procedure=procedure_key,
        request_key=request_key,
        structure=KnowledgeRef.model_validate(described["structure"]),
        parameters=normalized,
        rerun_of=rerun_of,
        request_basis=request_basis,
        snapshot=snapshot,
        period_from=begin,
        period_until=end,
    )
    receipt = apply_operation(path, request, authority)
    return dict(receipt.result)


def due_procedures(
    path: Path, authority: LocalAuthority, activity_id: UUID, *, when: datetime | None = None
) -> dict[str, Any]:
    from .storage import utc_now

    described = describe_structure(path, activity_id, authority)
    if described["legacy"]:
        return {"activity_id": str(activity_id), "procedures": [], "legacy": True}
    structure = ActivityStructureState.model_validate(described["state"])
    result: list[dict[str, Any]] = []
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        for procedure in structure.procedures:
            if procedure.trigger == "manual":
                continue
            start, end = _period(procedure, when or utc_now())
            row = connection.execute(
                "SELECT run_id,snapshot_id,snapshot_revision FROM procedure_runs "
                "WHERE activity_id=? AND procedure_key=? "
                "AND structure_id=? AND structure_revision=? AND period_from IS ? "
                "AND period_until IS ? ORDER BY rowid DESC LIMIT 1",
                (
                    str(activity_id),
                    procedure.key,
                    described["structure"]["record_id"],
                    described["structure"]["revision"],
                    start.isoformat() if start else None,
                    end.isoformat() if end else None,
                ),
            ).fetchone()
            inputs_current: bool | None = None
            if row:
                from .memory import selection_current_for_actor

                saved = exact_state(
                    connection,
                    KnowledgeRef(record_id=UUID(row[1]), revision=row[2]),
                    authority.actor,
                    info.execution_epoch,
                )
                if isinstance(saved, MemoryViewState) and saved.selection:
                    inputs_current = selection_current_for_actor(
                        connection, authority.actor, info.execution_epoch, saved.selection
                    )
            # Event conditions are advertised for the agent to evaluate from declared inputs.
            result.append(
                {
                    "key": procedure.key,
                    "trigger": procedure.trigger,
                    "period_from": start.isoformat() if start else None,
                    "period_until": end.isoformat() if end else None,
                    "status": "inputs_changed"
                    if row and inputs_current is False
                    else "existing"
                    if row
                    else "available"
                    if procedure.trigger == "period"
                    else "inspect_inputs",
                    "run_id": row[0] if row else None,
                    "inputs_current": inputs_current,
                    "autonomy": procedure.autonomy,
                }
            )
    return {
        "activity_id": str(activity_id),
        "structure": described["structure"],
        "procedures": result,
    }


__all__ = [
    "aggregate_entries",
    "describe_structure",
    "ingest_batch",
    "list_formats",
    "query_entries",
    "read_format",
    "upgrade_structures_space",
    "create_entry",
    "correct_entry",
    "read_entry",
    "entry_history",
    "working_set",
    "start_procedure",
    "procedure_status",
    "procedure_for_work",
    "due_procedures",
]
