"""Strict command shapes, separate from semantic decisions."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .types import CoreError

Id = Annotated[str, Field(min_length=1, max_length=240)]
NonEmptyText = Annotated[str, Field(min_length=1)]
Positive = Annotated[int, Field(ge=1)]
Cursor = Annotated[int, Field(ge=0)]
Hash = Annotated[str, Field(pattern="^[0-9a-f]{64}$")]


class Shape(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Ref(Shape):
    id: Id
    revision: Positive
    role: Literal["exact", "must_be_current"] = "exact"


class Change(Shape):
    id: Id
    kind: Id
    key: Id
    scope: Id = "space"
    body: Any
    source_refs: list[Ref] = Field(default_factory=list)
    schema_ref: Ref | None = None
    tombstone: bool = False
    application: Literal["active", "proposal", "withdrawn"] = "active"
    artifact_refs: list[Hash] = Field(default_factory=list, max_length=32)


class Work(Shape):
    id: Id
    conversation: Id
    goal: NonEmptyText
    scope: Id = "space"
    method_ref: Ref
    inputs: list[Ref] = Field(default_factory=list)
    call_limit: Positive | None = None
    continuation_policy: Literal["durable"]
    token_limit: Positive | None = None
    money_limit: str | None = None
    execution_policy: Literal["standard", "setup-final-only/v1", "setup-routing/v1"] = "standard"


class ContinuationFrom(Shape):
    attempt_id: Id
    result_hash: Hash
    work_revision: Positive
    basis_refs: list[Ref] = Field(min_length=1, max_length=32)


class OpenWork(Work):
    continuation_from: ContinuationFrom | None = None


class Tool(Shape):
    attempt_id: Id
    generation: Positive
    native_id: Id


class Changes(Shape):
    changes: list[Change] = Field(min_length=1, max_length=32)
    initial_work: Work | None = None
    tool: Tool | None = None


class Reply(Shape):
    id: Id
    revision: Positive


class Message(Shape):
    conversation: Id
    event_id: Id
    scope: Id = "space"
    raw_base64: str
    reply_to: Reply | None = None


class Manifest(Shape):
    sequence: Positive
    sha256: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]


class ContextSelection(Shape):
    catalog_refs: list[Ref] = Field(default_factory=list, max_length=100)
    prior_message_sequences: list[Positive] = Field(default_factory=list, max_length=100)
    prior_result_attempts: list[Id] = Field(default_factory=list, max_length=100)
    prior_wait_ids: list[Id] = Field(default_factory=list, max_length=100)


class Prepare(Shape):
    id: Id
    work_id: Id
    work_revision: Positive
    original_cursor: Cursor
    cutoff: Cursor
    message_sequences: list[Positive]
    manifest: list[Manifest]
    profile_ref: Ref
    context_selection: ContextSelection | None = None


class Claim(Shape):
    attempt_id: Id
    generation: Positive
    resource_upper: Positive | None = 1


class Evidence(Shape):
    action_id: Id
    state: Literal["running", "terminal", "not_received"]
    receiver_ref: Id


class Observe(Shape):
    attempt_id: Id
    event_id: Id
    kind: Literal["terminal", "progress", "unknown", "reconcile"]
    raw_base64: str | None = None
    evidence: Evidence | None = None


class Wait(Shape):
    id: Id
    question: NonEmptyText


class NextWork(Work):
    # An exhausted continuation remains durable and paused; C3/C4 still require
    # a positive execution budget for independently opened work.
    call_limit: Cursor | None = None


class SetupNextStep(Shape):
    goal: NonEmptyText
    inputs: list[Ref] = Field(default_factory=list)


class Outcome(Shape):
    attempt_id: Id
    generation: Positive
    terminal_event: Id
    original_cursor: Cursor
    processed_cutoff: Cursor
    state: Literal["waiting", "ready", "completed"]
    text: str = ""
    outputs: list[Ref] = Field(default_factory=list)
    changes: list[Change] = Field(default_factory=list)
    wait: Wait | None = None
    next_work: NextWork | None = None


class Control(Shape):
    work_id: Id
    revision: Positive
    action: Literal["pause", "cancel", "resume", "refresh"]
    reason: str | None = None
    inputs: list[Ref] | None = None
    method_ref: Ref | None = None


class ReserveTool(Tool):
    command_id: Id
    action_id: Id | None = None


class RenewSetup(Shape):
    attempt_id: Id
    generation: Positive
    work_revision: Positive


class Receipt(Shape):
    command_id: Id


class Artifact(Shape):
    sha256: Hash


class StageArtifact(Artifact):
    raw_base64: str
    content_type: Id


class Snapshot(Shape):
    max_rows: Annotated[int, Field(ge=1, le=1000)] = 1000


class PageToken(Shape):
    high_watermark: Cursor
    sha256: Hash


class Page(Shape):
    table: Literal[
        "heads",
        "works",
        "attempts",
        "messages",
        "conversations",
        "waits",
        "results",
        "observations",
        "actions",
        "intents",
        "tool_calls",
        "acceptance",
    ]
    cursor: Cursor = 0
    limit: Annotated[int, Field(ge=1, le=100)] = 100
    snapshot_revision: PageToken | None = None
    conversation: Id | None = None
    work: Id | None = None
    scope: Id | None = None
    columns: Annotated[list[Id], Field(min_length=1, max_length=8)] | None = Field(
        default=None,
        description=(
            "Optional unique physical column names for this public table; "
            "see PUBLIC-READ-PROJECTIONS.md. Omit for full rows."
        ),
    )


class Source(Shape):
    sequence: Positive
    index: Cursor
    sha256: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]


class History(Shape):
    high_watermark: Cursor | None = None
    after_sequence: Cursor = 0
    after_index: Cursor = 0
    limit: Annotated[int, Field(ge=1, le=100)] = 32
    scope: Id = "space"
    byte_limit: Positive | None = None


class Delivery(Shape):
    attempt_id: Id
    sha256: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]


class SleepProgress(Shape):
    format: Literal["sleep-progress/v1"]
    work_id: Id
    method_ref: Ref
    scope: Id
    source_high_watermark: Cursor
    enumeration_cursor: list[Cursor] = Field(min_length=2, max_length=2)
    enumerated_source_refs: list[Source]
    selected_source_refs: list[Source]
    delivered_manifest_refs: list[Delivery]
    analysis_result_refs: list[Ref]
    unexplored_coverage_position: Any
    applied_receipts: list[Id]
    proposed_changes: list[Any]
    remaining_refs: list[Source]
    return_conditions: list[str]
    consumed_resource: Cursor
    unresolved_calls: list[Id]
    stop_reason: str
    continuation: str


class SleepProgressV2(SleepProgress):
    format: Literal["sleep-progress/v2"]  # type: ignore[assignment]
    predecessor_ref: Ref
    transition: Literal["same_window", "new_window"]
    range_start: list[Cursor] = Field(min_length=2, max_length=2)


MODELS: dict[str, type[Shape]] = {
    "describe_contract": Shape,
    "read_snapshot": Snapshot,
    "read_page": Page,
    "read_history": History,
    "read_exact": Ref,
    "lookup_receipt": Receipt,
    "ingest_message": Message,
    "apply_changes": Changes,
    "open_work": OpenWork,
    "prepare_attempt": Prepare,
    "claim_dispatch": Claim,
    "observe_attempt": Observe,
    "commit_outcome": Outcome,
    "control_work": Control,
    "reserve_tool": ReserveTool,
    "renew_setup": RenewSetup,
    "stage_artifact": StageArtifact,
    "read_artifact": Artifact,
    "export_diagnostics": Shape,
}


def validate(operation: str, payload: dict[str, Any]) -> None:
    model = MODELS.get(operation)
    if model is None:
        raise CoreError("unsupported_capability", operation)
    try:
        model.model_validate(payload)
    except ValidationError as exc:
        location = ".".join(map(str, exc.errors()[0]["loc"]))
        raise CoreError("invalid_request", location) from exc
