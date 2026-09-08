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


class Record(RecordModel):
    id: UUID
    revision: Annotated[int, Field(strict=True, ge=1)]
    created_at: AwareDatetime


class Process(Record):
    kind: Literal["process"] = "process"
    title: Text


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

    @model_serializer(mode="wrap")
    def serialized(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        value: dict[str, object] = handler(self)
        if self.completion_id is None:
            value.pop("completion_id", None)
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


class Event(Record):
    kind: Literal["event"] = "event"
    process_id: UUID
    work_id: UUID
    action: Literal["initial_records_created"] = "initial_records_created"
    actor: Literal["local-invocation"] = "local-invocation"
    basis: Literal["explicit-workspace-bootstrap"] = "explicit-workspace-bootstrap"
    product_version: Text
    state_revision: Annotated[int, Field(strict=True, ge=1)]
    affected_ids: tuple[UUID, UUID, UUID]


DomainRecord = Annotated[Process | Work | Artifact | Event, Field(discriminator="kind")]
RECORD_ADAPTER: TypeAdapter[DomainRecord] = TypeAdapter(DomainRecord)


class RecordsSnapshot(RecordModel):
    """One database snapshot. It is neither work-open context nor a mutation receipt."""

    workspace_id: UUID
    state_revision: Annotated[int, Field(strict=True, ge=0)]
    records: tuple[DomainRecord, ...]

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
        if len(processes) != 1 or len(events) != 1 or not works or len(artifacts) != len(works):
            raise ValueError("Incomplete Process/Work/Artifact graph")
        process, event = processes[0], events[0]
        if len({r.id for r in self.records}) != len(self.records):
            raise ValueError("Record identities must be distinct")
        members: tuple[Work | Artifact | Event, ...] = (*works.values(), *artifacts, event)
        if any(r.process_id != process.id for r in members):
            raise ValueError("Record refers to another Process")
        if {r.work_id for r in artifacts} != set(works):
            raise ValueError("Every Work must have exactly one declared Artifact")
        initial = works.get(event.work_id)
        artifact = next((r for r in artifacts if r.work_id == event.work_id), None)
        if (
            initial is None
            or artifact is None
            or event.affected_ids != (process.id, initial.id, artifact.id)
        ):
            raise ValueError("Initial event does not describe initial records")
        if self.state_revision < 1 or event.state_revision != 1:
            raise ValueError("Invalid state/initial event revision")
        if max(w.revision for w in works.values()) != self.state_revision:
            raise ValueError("Latest Work revision must match global state")
        if any(
            w.revision == 1 and (w.status != "draft" or w.authority_scope != "none")
            for w in works.values()
        ):
            raise ValueError("Initial Work must remain a draft without rights")
        if any(r.revision > self.state_revision for r in self.records):
            raise ValueError("Record revision exceeds state")
        if process.revision != 1 or event.revision != 1:
            raise ValueError("Unsupported Process/initial event revision")
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
    snapshot = RecordsSnapshot(
        workspace_id=workspace_id, state_revision=state[0][1], records=tuple(records)
    )
    if connection.execute("PRAGMA user_version").fetchone()[0] < 6 and (
        len(records) not in (0, 4)
        or any(isinstance(r, Work) and r.status == "done" for r in records)
    ):
        raise WorkspaceError("Result/continuation records require explicit schema 6")
    return snapshot


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
