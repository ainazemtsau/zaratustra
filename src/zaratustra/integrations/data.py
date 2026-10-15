"""Installed data contracts shared by Pi, CLI and future adapters."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel, Field

from zaratustra.foundation import (
    DataEntryState,
    IngestDataRequest,
    IntakeElement,
    KnowledgeRef,
    LocalAuthority,
    RuntimeMemorySelector,
    admit_runtime_selectors,
    aggregate_entries,
    correct_entry,
    create_entry,
    describe_structure,
    due_procedures,
    entry_history,
    ingest_batch,
    list_formats,
    procedure_status,
    query_entries,
    read_entry,
    read_format,
    read_space,
    start_procedure,
    working_set,
)

from .registry import IntegrationResult, Operation, Parameters


class Structure(Parameters):
    activity_id: UUID
    work_id: UUID | None = None


class Formats(Parameters):
    activity_id: UUID | None = None
    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = None


class Exact(Parameters):
    ref: KnowledgeRef


class Create(Parameters):
    state: DataEntryState
    record_id: UUID | None = None


class Correct(Create):
    record_id: UUID
    expected_revision: int = Field(ge=1)


class Ingest(Parameters):
    source: KnowledgeRef
    delivery_key: str = Field(min_length=1, max_length=200)
    elements: tuple[IntakeElement, ...] = Field(min_length=1)
    complete: bool = False


class Query(Parameters):
    selectors: tuple[RuntimeMemorySelector, ...] = Field(min_length=1)
    cache: bool = False
    max_bytes: int = Field(default=16384, ge=1, le=32768)


class Aggregate(Parameters):
    selection: KnowledgeRef
    field: str | None = None
    operation: str = "count"
    group_by: str | None = None
    group_period: str | None = None
    timezone: str = "UTC"
    limit: int = Field(default=100, ge=1, le=100)
    cursor: str | None = None
    precision: int = Field(default=6, ge=0, le=1000)


class History(Parameters):
    record_id: UUID
    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = None


class Procedure(Parameters):
    activity_id: UUID
    procedure: str
    request_key: str = Field(min_length=1, max_length=200)
    parameters: dict[str, Any] | None = None
    period_from: date | None = None
    period_until: date | None = None
    when: datetime | None = None
    snapshot: KnowledgeRef | None = None
    request_basis: tuple[KnowledgeRef, ...] = ()
    rerun_of: UUID | None = None


class Run(Parameters):
    run_id: UUID


class Due(Parameters):
    activity_id: UUID
    when: datetime | None = None


class WorkingSet(Structure):
    key: str


def data_operations(path: Path, authority: LocalAuthority) -> dict[str, Operation]:
    from zaratustra.foundation import FoundationError, capability_names

    def execute(name: str, operation_id: UUID, parameters: BaseModel) -> IntegrationResult:
        args = parameters.model_dump()
        if isinstance(parameters, Exact):
            args["ref"] = parameters.ref
        output: dict[str, Any]
        if name == "describe_structure":
            output = describe_structure(path, authority=authority, **args)
        elif name == "list_formats":
            output = dict(list_formats(path, authority, **args))
        elif name == "read_format":
            output = read_format(path, authority=authority, **args)
        elif name == "read_entry":
            output = read_entry(path, authority=authority, **args)
        elif name in ("create_entry", "correct_entry"):
            args["state"] = cast(Create, parameters).state
            receipt = (create_entry if name == "create_entry" else correct_entry)(
                path, authority, operation_id=operation_id, **args
            )
            output = receipt.model_dump(mode="json")
        elif name == "ingest_batch":
            receipt = ingest_batch(
                path,
                IngestDataRequest(
                    operation_id=operation_id,
                    space_id=read_space(path).space_id,
                    actor=authority.actor,
                    **args,
                ),
                authority,
            )
            output = receipt.model_dump(mode="json")
        elif name == "query_entries":
            args["selectors"] = admit_runtime_selectors(
                path, authority, cast(Query, parameters).selectors
            )
            output = dict(query_entries(path, authority, **args))
        elif name == "aggregate_entries":
            args["selection"] = cast(Aggregate, parameters).selection
            output = aggregate_entries(path, authority=authority, **args)
        elif name == "history":
            output = dict(entry_history(path, authority, **args))
        elif name == "working_set":
            output = dict(working_set(path, authority, **args))
        elif name == "start_procedure":
            args["request_basis"] = cast(Procedure, parameters).request_basis
            args["procedure_key"] = args.pop("procedure")
            if args["snapshot"] is not None:
                args["snapshot"] = cast(Procedure, parameters).snapshot
            output = dict(start_procedure(path, authority, **args))
        elif name == "procedure_status":
            output = procedure_status(path, authority, **args)
        else:
            output = due_procedures(path, authority, **args)
        exposed: list[KnowledgeRef] = []
        if name in ("read_entry", "read_format"):
            exposed.append(cast(Exact, parameters).ref)
        if name == "describe_structure" and output.get("structure"):
            exposed.append(KnowledgeRef.model_validate(output["structure"]))
        exposed.extend(KnowledgeRef.model_validate(ref) for ref in output.get("exposed", []))
        return IntegrationResult(output, tuple(exposed))

    definitions: dict[str, type[Parameters]] = {
        "describe_structure": Structure,
        "list_formats": Formats,
        "read_format": Exact,
        "create_entry": Create,
        "correct_entry": Correct,
        "ingest_batch": Ingest,
        "read_entry": Exact,
        "history": History,
        "query_entries": Query,
        "aggregate_entries": Aggregate,
        "working_set": WorkingSet,
        "start_procedure": Procedure,
        "procedure_status": Run,
        "due_procedures": Due,
    }
    if frozenset(definitions) != capability_names("data"):
        raise FoundationError(
            "unsupported_contract", "Installed data capabilities differ from Core"
        )

    def operation(name: str, model: type[Parameters]) -> Operation:
        return Operation(
            "Public typed data: " + name,
            "Core receipt; no Work acceptance"
            if name in ("create_entry", "correct_entry", "ingest_batch", "start_procedure")
            else "Read exact data through current rights",
            model,
            lambda operation_id, parameters: execute(name, operation_id, parameters),
        )

    return {name: operation(name, model) for name, model in definitions.items()}


__all__ = ["data_operations"]
