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
    StringConstraints,
    TypeAdapter,
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
    status: Literal["draft", "ready", "cancelled"] = "draft"
    authority_scope: Literal["none", "work_metadata"] = "none"
    context_handles: tuple[()] = ()
    dependencies: tuple[()] = ()
    executor_requirements: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def draft_has_no_authority(self) -> Self:
        if self.status == "draft" and self.authority_scope != "none":
            raise ValueError("Draft Work cannot have authority")
        return self


class Artifact(Record):
    kind: Literal["artifact"] = "artifact"
    process_id: UUID
    work_id: UUID
    title: Text
    status: Literal["declared"] = "declared"
    active_version: None = None


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
        by_kind = {record.kind: record for record in self.records}
        if len(self.records) != 4 or len(by_kind) != 4:
            raise ValueError("Incomplete initial records")
        process, work, artifact, event = (
            by_kind[name] for name in ("process", "work", "artifact", "event")
        )
        if not (
            isinstance(process, Process)
            and isinstance(work, Work)
            and isinstance(artifact, Artifact)
            and isinstance(event, Event)
        ):
            raise ValueError("Invalid record kinds")
        if len({record.id for record in self.records}) != 4:
            raise ValueError("Record identities must be distinct")
        if any(record.process_id != process.id for record in (work, artifact, event)):
            raise ValueError("Record refers to another Process")
        if artifact.work_id != work.id or event.work_id != work.id:
            raise ValueError("Record refers to another Work")
        if event.affected_ids != (process.id, work.id, artifact.id):
            raise ValueError("Event does not describe these records")
        if self.state_revision < 1 or event.state_revision != 1:
            raise ValueError("Invalid state/initial event revision")
        if work.revision != self.state_revision:
            raise ValueError("Work revision must match this single-Work state")
        if work.revision == 1 and (work.status != "draft" or work.authority_scope != "none"):
            raise ValueError("Initial Work must remain a draft without rights")
        if any(record.revision != 1 for record in (process, artifact, event)):
            raise ValueError("Unsupported record revision")
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
    return RecordsSnapshot(
        workspace_id=workspace_id, state_revision=state[0][1], records=tuple(records)
    )


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
        if info.schema_version == 3 and (
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
