"""Host-neutral web commands; only selected Process data reaches the service."""

from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from zaratustra import home
from zaratustra.journal import JournalError, Reference, Scope, Store, shared_store
from zaratustra.web_exchange import Channel, Exchange, Review

from . import Command, Context, _selected, required
from .registry import CommandSpec, register


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Prepare(Empty):
    question: Annotated[str, Field(min_length=1, max_length=100_000)]
    references: Annotated[tuple[Reference, ...], Field(max_length=24)] = ()


class Complete(Empty):
    process_revision: Annotated[int, Field(strict=True, ge=1)]


class Listing(Empty):
    include_completed: bool = False


class Publish(Empty):
    selected_publication: Literal[True]


class Attach(Empty):
    item_key: Annotated[str, Field(min_length=1, max_length=128)]
    name: Annotated[str, Field(min_length=1, max_length=128)]


def execute_web(
    context: Context,
    command: Command,
    source_ref: str,
    operation: UUID,
    guarded_revision: int | None,
) -> dict[str, Any]:
    if command.scope != "process":
        raise JournalError("invalid_scope", "Web exchange belongs to the selected Process")
    path, source = _selected(context, command.process)
    shared = (
        shared_store(Path(context.home), UUID(home.read_home(Path(context.home))["id"]), source_ref)
        if command.include_shared
        else None
    )
    service = Exchange(
        Store(path, Scope(kind="process", id=UUID(source["id"])), source_ref),
        source,
        (shared,) if shared else (),
    )
    if (
        command.process is None
        and guarded_revision is not None
        and service.store.query.expected_revision != guarded_revision
    ):
        raise JournalError("context_changed", "Process changed while preparing the command")
    action = command.action
    if action == "web.configure":
        return service.configure(
            Channel.model_validate(command.payload), operation, command.expected_revision
        )
    if action == "web.channel":
        return {
            "channel": service.channel().model_dump(mode="json"),
            "prefix": service.prefix,
            "record": str(service.channel_id),
            "revision": service.store.get(service.channel_id).revision,
        }
    if action == "web.pull":
        return service.pull(command.offset, command.limit)
    if action == "web.list":
        return service.listing(
            command.offset,
            command.limit,
            Listing.model_validate(command.payload or {}).include_completed,
        )
    if action == "web.prepare":
        data = Prepare.model_validate(command.payload)
        return service.prepare(data.question, data.references, operation)
    if action == "web.instructions":
        return service.instructions(command.record)
    if command.record is None:
        raise JournalError("missing_record", "Select a web request or discussion context")
    if action == "web.read":
        return service.read(command.record, command.content_offset, command.content_limit)
    if action == "web.attach":
        attachment = Attach.model_validate(command.payload)
        return service.attach(
            command.record,
            attachment.item_key,
            attachment.name,
            Path(required(command.path, "owner-supplied file")),
        )
    if action == "web.publish":
        return service.publish(command.record)
    if command.expected_revision is None:
        raise JournalError("missing_revision", "Read the web request first")
    if action == "web.review":
        return service.review(
            command.record,
            command.expected_revision,
            Review.model_validate(command.payload),
            operation,
            required(command.reason, "review reason"),
        )
    return service.complete(
        command.record,
        command.expected_revision,
        Complete.model_validate(command.payload).process_revision,
        operation,
    )


for name, payload, description in (
    ("web.configure", Channel, "Save owner-selected GitHub repository/branch for this Process"),
    ("web.channel", Empty, "Read configured destination and exact per-Process inbox path"),
    (
        "web.instructions",
        Empty,
        "Get ready-to-paste Project instructions and a connection check; no packet or GitHub write",
    ),
    (
        "web.prepare",
        Prepare,
        "Save a dated discussion packet with only selected sources; no network write",
    ),
    (
        "web.publish",
        Publish,
        "Publish a selected packet and instructions to GitHub on owner instruction",
    ),
    ("web.pull", Empty, "Capture a page of GitHub requests; does not apply their content"),
    ("web.list", Listing, "List this Process's pending requests; originals are read separately"),
    (
        "web.read",
        Empty,
        "Read original text, progress, missing files and deterministic delivery operation ids",
    ),
    (
        "web.attach",
        Attach,
        "Receive declared attachment bytes from the owner-supplied path; never reconstruct text",
    ),
    (
        "web.review",
        Review,
        "Record agent interpretation/progress; request id and expected_revision required",
    ),
    (
        "web.complete",
        Complete,
        "Close only fully accounted requests against a freshly read Process revision",
    ),
):
    register(CommandSpec(name, payload, execute_web, description))
