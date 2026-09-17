"""Installed exchange schemas; web authors need not produce any of these models."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from zaratustra.journal import DEFAULT_REGISTRY, Reference, TypeSpec

Name = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)]
Text = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100_000)]
Repository = Annotated[
    str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
]
Digest = Annotated[str, StringConstraints(pattern="^[0-9a-f]{64}$")]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Channel(Model):
    repository: Repository
    branch: Name = "main"


class Origin(Model):
    repository: Repository
    branch: Name
    path: Text
    blob: Annotated[str, StringConstraints(pattern="^[0-9a-f]{40}$")]
    commit: Annotated[str, StringConstraints(pattern="^[0-9a-f]{40}$")]


class Attachment(Model):
    name: Name
    reference: Reference | None = None


class Item(Model):
    key: Name
    source_quote: Text
    intent: Literal["store", "backlog", "apply", "clarify"]
    description: Text
    authority_quote: Text | None = None
    authority_reference: Reference | None = None
    files: Annotated[tuple[Attachment, ...], Field(max_length=16)] = ()
    outcome: Literal["pending", "done"] = "pending"
    result: Reference | None = None
    note: str = ""

    @model_validator(mode="after")
    def valid(self) -> Item:
        if len({a.name for a in self.files}) != len(self.files):
            raise ValueError("Attachment names must be distinct within an item")
        if self.outcome == "done" and (
            self.result is None
            or self.intent == "clarify"
            or any(a.reference is None for a in self.files)
            or (self.intent == "apply" and not self.authority_quote)
        ):
            raise ValueError("Done needs a result, required files and actual application authority")
        return self


class Review(Model):
    reviewed_full_request: Literal[True]
    items: Annotated[tuple[Item, ...], Field(min_length=1, max_length=24)]
    context: Reference | None = None
    context_note: str = ""

    @model_validator(mode="after")
    def distinct(self) -> Review:
        if len({item.key for item in self.items}) != len(self.items):
            raise ValueError("Item keys must be distinct")
        return self


class Request(Model):
    origin: Origin
    original: str
    sha256: Digest
    status: Literal["pending", "processing", "waiting", "completed"] = "pending"
    review: Review | None = None
    context_stamp: str | None = None


class Packet(Model):
    process_title: Name
    process_revision: int
    question: Text
    references: Annotated[tuple[Reference, ...], Field(max_length=24)] = ()
    markdown: str
    intent_sha256: Digest


def request_references(payload: dict[str, Any]) -> tuple[Reference, ...]:
    request = Request.model_validate(payload)
    review = request.review
    if review is None:
        return ()
    refs = [review.context] if review.context else []
    for item in review.items:
        if item.authority_reference:
            refs.append(item.authority_reference)
        if item.result:
            refs.append(item.result)
        refs.extend(a.reference for a in item.files if a.reference)
    return tuple(dict.fromkeys(refs))


for spec in (
    TypeSpec("web_channel", 1, Channel, managed_by="web.configure"),
    TypeSpec("web_request", 1, Request, references=request_references, managed_by="web.*"),
    TypeSpec(
        "web_context",
        1,
        Packet,
        operations=("create",),
        references=lambda p: Packet.model_validate(p).references,
        managed_by="web.prepare",
    ),
):
    DEFAULT_REGISTRY.register(spec)
