"""Domain records, coherent snapshot values and the bounded create-once bootstrap."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import UUID, uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StringConstraints,
    TypeAdapter,
    model_serializer,
    model_validator,
)

from .workspace import WorkspaceError, workspace_connection

Text = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]


class AmbiguousCurrentWorkError(WorkspaceError):
    """Authoritative history has several unfinished Works and cannot select one."""

    code = "ambiguous_current_work"

    def __init__(self) -> None:
        super().__init__("ambiguous_current_work: Process has more than one draft or ready Work")


class RecordModel(BaseModel):
    """Immutable boundary values; tuples avoid mutable collections in frozen models."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class InitialRecords(RecordModel):
    """Explicit local bootstrap input, with no caller-supplied identity or authority."""

    process_title: Text
    goal: Text
    expected_result: Text
    acceptance: Annotated[tuple[Text, ...], Field(min_length=1)]
    boundaries: Annotated[tuple[Text, ...], Field(min_length=1)]
    budget: Text
    artifact_title: Text


class InitialProcess(RecordModel):
    """A standalone activity; its explicit bootstrap never invents a Work."""

    title: Text
    purpose: Text
    operation_id: UUID


class Record(RecordModel):
    id: UUID
    revision: Annotated[int, Field(strict=True, ge=1)]
    created_at: AwareDatetime


class PackReference(RecordModel):
    """Exact external identity only; no code, version selection or authority."""

    pack_id: Annotated[str, Field(strict=True, pattern="^[a-z][a-z0-9._-]{0,127}$")]
    pack_version: Annotated[str, Field(strict=True, pattern="^[0-9]+[.][0-9]+[.][0-9]+$")]
    process_type: Annotated[str, Field(strict=True, pattern="^[a-z][a-z0-9._-]{0,127}$")]
    contract_version: Annotated[int, Field(strict=True, ge=1)]
    state_version: Annotated[int, Field(strict=True, ge=1)]


class Process(Record):
    kind: Literal["process"] = "process"
    title: Text
    purpose: Text | None = None
    pack_binding: PackReference | None = None

    @model_serializer(mode="wrap")
    def serialized(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        value: dict[str, object] = handler(self)
        if self.purpose is None:
            value.pop("purpose", None)
        if self.pack_binding is None:
            value.pop("pack_binding", None)
        return value


class Work(Record):
    kind: Literal["work"] = "work"
    process_id: UUID
    goal: Text
    expected_result: Text
    acceptance: Annotated[tuple[Text, ...], Field(min_length=1)]
    boundaries: Annotated[tuple[Text, ...], Field(min_length=1)]
    budget: Text
    status: Literal["draft", "ready", "cancelled", "done"] = "draft"
    authority_scope: Literal["none", "work_metadata", "work_metadata_and_artifact"] = "none"
    context_handles: tuple[()] = ()
    dependencies: tuple[()] = ()
    executor_requirements: tuple[Text, ...] = ()
    completion_id: UUID | None = None
    pack_binding: PackReference | None = None

    @model_serializer(mode="wrap")
    def serialized(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        value: dict[str, object] = handler(self)
        if self.completion_id is None:
            value.pop("completion_id", None)
        if self.pack_binding is None:
            value.pop("pack_binding", None)
        return value

    @model_validator(mode="after")
    def draft_has_no_authority(self) -> Self:
        if (self.status == "done") != (self.completion_id is not None):
            raise ValueError("Completed Work requires its Result operation identity")
        if self.status == "draft" and self.authority_scope != "none":
            raise ValueError("Draft Work cannot have authority")
        return self


class Artifact(Record):
    kind: Literal["artifact"] = "artifact"
    process_id: UUID
    work_id: UUID
    title: Text
    status: Literal["declared", "registered"] = "declared"
    active_version: UUID | None = None

    @model_validator(mode="after")
    def version_status(self) -> Self:
        if self.status == "declared":
            if self.active_version is not None or self.revision != 1:
                raise ValueError("Declared Artifact has no version")
        elif self.active_version is None or self.revision < 2:
            raise ValueError("Registered Artifact requires an active version")
        return self


class ProcessMaterial(Record):
    """Immutable content identity owned by a Process, never by a Work."""

    kind: Literal["process_material"] = "process_material"
    process_id: UUID
    operation_id: UUID
    title: Text
    media_type: Text
    content_sha256: Annotated[str, Field(strict=True, pattern="^[0-9a-f]{64}$")]
    content_size: Annotated[int, Field(strict=True, ge=0)]


class Event(Record):
    kind: Literal["event"] = "event"
    process_id: UUID
    work_id: UUID | None = None
    action: Literal["initial_records_created", "process_created"] = "initial_records_created"
    actor: Literal["local-invocation"] = "local-invocation"
    basis: Literal["explicit-workspace-bootstrap", "explicit-process-bootstrap"] = (
        "explicit-workspace-bootstrap"
    )
    product_version: Text
    state_revision: Annotated[int, Field(strict=True, ge=1)]
    affected_ids: tuple[UUID, ...]

    @model_validator(mode="after")
    def bootstrap_shape(self) -> Self:
        if self.action == "process_created":
            if (
                self.work_id is not None
                or self.affected_ids != (self.process_id,)
                or self.basis != "explicit-process-bootstrap"
            ):
                raise ValueError("Standalone bootstrap names only its Process")
        elif (
            self.work_id is None
            or len(self.affected_ids) != 3
            or self.basis != "explicit-workspace-bootstrap"
        ):
            raise ValueError("Legacy bootstrap must name Process, Work and Artifact")
        return self

    @model_serializer(mode="wrap")
    def serialized(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        value: dict[str, object] = handler(self)
        if self.work_id is None:
            value.pop("work_id", None)
        return value


DomainRecord = Annotated[Process | Work | Artifact | Event, Field(discriminator="kind")]
RECORD_ADAPTER: TypeAdapter[DomainRecord] = TypeAdapter(DomainRecord)


class RecordsSnapshot(RecordModel):
    """One database snapshot. It is neither work-open context nor a mutation receipt."""

    workspace_id: UUID
    state_revision: Annotated[int, Field(strict=True, ge=0)]
    records: tuple[DomainRecord, ...]

    @property
    def current_work(self) -> Work | None:
        """The sole unfinished Work, or normal no-current truth; never historical fallback."""
        current = [
            record
            for record in self.records
            if isinstance(record, Work) and record.status in ("draft", "ready")
        ]
        if len(current) > 1:
            raise ValueError("A Process cannot have more than one current Work")
        return current[0] if current else None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if not self.records:
            if self.state_revision != 0:
                raise ValueError("Empty records require revision zero")
            return self
        processes = [r for r in self.records if isinstance(r, Process)]
        events = [r for r in self.records if isinstance(r, Event)]
        works = {r.id: r for r in self.records if isinstance(r, Work)}
        artifacts = [r for r in self.records if isinstance(r, Artifact)]
        if len(processes) != 1 or len(events) != 1 or len(artifacts) != len(works):
            raise ValueError("Incomplete Process/Work/Artifact graph")
        process, event = processes[0], events[0]
        if len({r.id for r in self.records}) != len(self.records):
            raise ValueError("Record identities must be distinct")
        members: tuple[Work | Artifact | Event, ...] = (*works.values(), *artifacts, event)
        if any(r.process_id != process.id for r in members):
            raise ValueError("Record refers to another Process")
        if {r.work_id for r in artifacts} != set(works):
            raise ValueError("Every Work must have exactly one declared Artifact")
        initial = works.get(event.work_id) if event.work_id is not None else None
        artifact = next((r for r in artifacts if r.work_id == event.work_id), None)
        if event.action == "initial_records_created" and (
            initial is None
            or artifact is None
            or event.affected_ids != (process.id, initial.id, artifact.id)
        ):
            raise ValueError("Initial event does not describe initial records")
        if event.action == "process_created" and process.purpose is None:
            raise ValueError("Standalone Process requires a purpose")
        if self.state_revision < 1 or event.state_revision != 1:
            raise ValueError("Invalid state/initial event revision")
        if max(r.revision for r in (process, *works.values())) != self.state_revision:
            raise ValueError("Latest Process-owned revision must match global state")
        _ = self.current_work
        if any(
            w.revision == 1 and (w.status != "draft" or w.authority_scope != "none")
            for w in works.values()
        ):
            raise ValueError("Initial Work must remain a draft without rights")
        if any(r.revision > self.state_revision for r in self.records):
            raise ValueError("Record revision exceeds state")
        if event.revision != 1 or process.revision < (1 if process.pack_binding is None else 2):
            raise ValueError("Unsupported Process/initial event revision")
        if any(
            w.pack_binding is not None and w.pack_binding != process.pack_binding
            for w in works.values()
        ):
            raise ValueError("Work binding must match its Process")
        return self


def _read_records(connection: sqlite3.Connection, workspace_id: UUID) -> RecordsSnapshot:
    state = connection.execute("SELECT singleton, revision FROM core_state").fetchall()
    if len(state) != 1 or state[0][0] != 1:
        raise WorkspaceError("Invalid record state")
    records = []
    for identity, kind, revision, body in connection.execute(
        "SELECT id, kind, revision, body FROM core_records ORDER BY kind, id"
    ):
        record = RECORD_ADAPTER.validate_json(body)
        if (str(record.id), record.kind, record.revision) != (identity, kind, revision):
            raise WorkspaceError("Record metadata does not match its content")
        records.append(record)
    if (
        sum(isinstance(record, Work) and record.status in ("draft", "ready") for record in records)
        > 1
    ):
        raise AmbiguousCurrentWorkError
    snapshot = RecordsSnapshot(
        workspace_id=workspace_id, state_revision=state[0][1], records=tuple(records)
    )
    if connection.execute("PRAGMA user_version").fetchone()[0] < 10 and any(
        isinstance(r, Event) and r.action == "process_created" for r in records
    ):
        raise WorkspaceError("Standalone Process requires explicit schema 10")
    if connection.execute("PRAGMA user_version").fetchone()[0] < 7 and any(
        isinstance(r, Process | Work) and r.pack_binding is not None for r in records
    ):
        raise WorkspaceError("Pack bindings require explicit schema 7")
    if connection.execute("PRAGMA user_version").fetchone()[0] < 6 and (
        len(records) not in (0, 4)
        or any(isinstance(r, Work) and r.status == "done" for r in records)
    ):
        raise WorkspaceError("Result/continuation records require explicit schema 6")
    return snapshot


def create_process(path: Path, initial: InitialProcess) -> RecordsSnapshot:
    """Create a Process and its bootstrap journal in one transaction.

    A retry of the same operation returns its existing Process, including later
    material revisions. Existing legacy or different bootstrap content conflicts.
    """
    initial = InitialProcess.model_validate(initial.model_dump())
    with workspace_connection(path, write=True) as (connection, info):
        if info.schema_version < 10:
            raise WorkspaceError("Standalone Process requires explicit schema 10")
        before = _read_records(connection, info.workspace_id)
        if before.records:
            from .mutations import _history

            _history(connection, before, artifacts_enabled=True)
            process = next(r for r in before.records if isinstance(r, Process))
            event = next(r for r in before.records if isinstance(r, Event))
            if (
                event.action == "process_created"
                and event.id == initial.operation_id
                and process.title == initial.title
                and process.purpose == initial.purpose
            ):
                return before
            raise WorkspaceError("Process already exists; bootstrap intent differs")
        if (
            connection.execute("SELECT COUNT(*) FROM mutation_events").fetchone()[0]
            or (connection.execute("SELECT COUNT(*) FROM mutation_receipts").fetchone()[0])
        ):
            raise WorkspaceError("Bootstrap cannot replace existing history")
        now = datetime.now(UTC)
        process = Process(
            id=uuid4(), revision=1, created_at=now, title=initial.title, purpose=initial.purpose
        )
        event = Event(
            id=initial.operation_id,
            revision=1,
            created_at=now,
            process_id=process.id,
            action="process_created",
            basis="explicit-process-bootstrap",
            product_version=version("zaratustra"),
            state_revision=1,
            affected_ids=(process.id,),
        )
        for record in (process, event):
            connection.execute(
                "INSERT INTO core_records (id, kind, revision, body) VALUES (?, ?, ?, ?)",
                (str(record.id), record.kind, record.revision, record.model_dump_json()),
            )
        connection.execute("UPDATE core_state SET revision = 1 WHERE singleton = 1")
        return _read_records(connection, info.workspace_id)


def create_initial_records(path: Path, initial: InitialRecords) -> RecordsSnapshot:
    """Create initial drafts only in an empty record store, never update a Work.

    This direct local bootstrap grants no authority and never executes a Work.
    Every later domain change goes through mutations.apply_mutation.
    """
    initial = InitialRecords.model_validate(initial.model_dump())
    with workspace_connection(path, write=True) as (connection, info):
        if info.schema_version < 2:
            raise WorkspaceError("Records require schema 2 or later; run zara migrate explicitly.")
        before = _read_records(connection, info.workspace_id)
        if before.records:
            raise WorkspaceError("Initial records already exist; no changes made.")
        if info.schema_version >= 3 and (
            connection.execute("SELECT COUNT(*) FROM mutation_events").fetchone()[0]
            or connection.execute("SELECT COUNT(*) FROM mutation_receipts").fetchone()[0]
        ):
            raise WorkspaceError("Initial creation cannot replace existing mutation history")
        now = datetime.now(UTC)
        process = Process(id=uuid4(), revision=1, created_at=now, title=initial.process_title)
        work = Work(
            id=uuid4(),
            revision=1,
            created_at=now,
            process_id=process.id,
            goal=initial.goal,
            expected_result=initial.expected_result,
            acceptance=initial.acceptance,
            boundaries=initial.boundaries,
            budget=initial.budget,
        )
        artifact = Artifact(
            id=uuid4(),
            revision=1,
            created_at=now,
            process_id=process.id,
            work_id=work.id,
            title=initial.artifact_title,
        )
        event = Event(
            id=uuid4(),
            revision=1,
            created_at=now,
            process_id=process.id,
            work_id=work.id,
            product_version=version("zaratustra"),
            state_revision=1,
            affected_ids=(process.id, work.id, artifact.id),
        )
        for record in (process, work, artifact, event):
            connection.execute(
                "INSERT INTO core_records (id, kind, revision, body) VALUES (?, ?, ?, ?)",
                (str(record.id), record.kind, record.revision, record.model_dump_json()),
            )
        connection.execute("UPDATE core_state SET revision = 1 WHERE singleton = 1")
        return _read_records(connection, info.workspace_id)
