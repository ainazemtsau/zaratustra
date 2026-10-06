"""The installed manual adapter: typed operations, free-form external material."""

from __future__ import annotations

import base64
import hashlib
from importlib.resources import files
from pathlib import Path
from typing import cast
from uuid import UUID

from pydantic import BaseModel, Field

from zaratustra.foundation import (
    FoundationError,
    HandoffState,
    KnowledgeRef,
    LocalAuthority,
    SourceState,
    open_knowledge,
    read_knowledge,
)

from .manual import ManualExchange
from .memory import memory_operations
from .registry import IntegrationRegistry, IntegrationResult, Operation, Parameters


class PrepareDocument(Parameters):
    activity_id: UUID
    work_id: UUID | None = None
    external_tool: str = Field(min_length=1, max_length=160)
    document_text: str = Field(min_length=1, max_length=8388608)
    expected_return: str = Field(min_length=1, max_length=2048)
    context: tuple[KnowledgeRef, ...] = Field(default=(), max_length=64)


class RetainText(Parameters):
    activity_id: UUID
    work_id: UUID | None = None
    origin: str = Field(min_length=1, max_length=160)
    content_text: str = Field(min_length=1, max_length=8388608)
    sender: str | None = Field(default=None, max_length=200)
    previous_source: KnowledgeRef | None = None
    reply_to: KnowledgeRef | None = None


class ReadDocument(Parameters):
    record_id: UUID
    revision: int | None = Field(default=None, ge=1)
    offset: int = Field(default=0, ge=0)
    max_bytes: int = Field(default=16384, ge=1, le=32768)


class ProductContext(Parameters):
    pass


def installed_integrations(path: Path, authority: LocalAuthority) -> IntegrationRegistry:
    """A code-owned composition root, not a dynamic loader controlled by model text."""
    exchange = ManualExchange(path, authority)

    def prepare(operation_id: UUID, parameters: BaseModel) -> IntegrationResult:
        args = cast(PrepareDocument, parameters)
        result = exchange.prepare_document(
            operation_id,
            args.activity_id,
            external_tool=args.external_tool,
            document_text=args.document_text,
            expected_return=args.expected_return,
            context=args.context,
            work_id=args.work_id,
        )
        return IntegrationResult(
            {key: value for key, value in result.items() if key != "content_text"}
            | {"stage": "prepared", "sent": False}
        )

    def retain(operation_id: UUID, parameters: BaseModel) -> IntegrationResult:
        args = cast(RetainText, parameters)
        result = exchange.receive(
            operation_id,
            args.activity_id,
            work_id=args.work_id,
            origin=args.origin,
            content=args.content_text.encode("utf-8"),
            sender=args.sender,
            previous_source=args.previous_source,
            reply_to=args.reply_to,
        )
        return IntegrationResult(
            {key: value for key, value in result.items() if key != "content_text"}
            | {"stage": "retained", "accepted": False}
        )

    def read(_operation_id: UUID, parameters: BaseModel) -> IntegrationResult:
        args = cast(ReadDocument, parameters)
        item = read_knowledge(path, args.record_id, authority, revision=args.revision)
        if not isinstance(item.state, (SourceState, HandoffState)):
            raise FoundationError("wrong_kind", "Read a Source or Handoff document")
        result = open_knowledge(
            path,
            args.record_id,
            authority,
            revision=item.revision,
            offset=args.offset,
            max_bytes=args.max_bytes,
        )
        payload = result.get("content_base64")
        if isinstance(payload, str) and item.state.media_type.startswith("text/"):
            result["content_text"] = base64.b64decode(payload).decode("utf-8")
            result.pop("content_base64", None)
        exposed = (
            (KnowledgeRef(record_id=args.record_id, revision=item.revision),)
            if result.get("content_text") or result.get("content_base64")
            else ()
        )
        return IntegrationResult(result, exposed)

    def context(_operation_id: UUID, _parameters: BaseModel) -> IntegrationResult:
        resource = files("zaratustra.integrations").joinpath("product-context.md")
        content = resource.read_bytes()
        return IntegrationResult(
            {
                "content_text": content.decode("utf-8"),
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest().upper(),
                "basis": "Shipped product reference; not live instance or remote GitHub state",
            }
        )

    return IntegrationRegistry(
        {
            "manual": {
                "prepare_document": Operation(
                    "Retain a tailored instruction/context document with exact selected bases",
                    "Core Handoff prepared; nothing sent externally",
                    PrepareDocument,
                    prepare,
                ),
                "retain_text": Operation(
                    "Keep the complete delivered text; missing external fields are allowed",
                    "Core Source retained; no acceptance or external action",
                    RetainText,
                    retain,
                ),
                "read_document": Operation(
                    "Read an exact retained Source/Handoff in bounded byte windows",
                    "Read only; continue until next_offset is null",
                    ReadDocument,
                    read,
                ),
                "product_context": Operation(
                    "Read the reusable shipped Zaratustra overview for external discussions",
                    "Read only; contains no user settings or conversation journal",
                    ProductContext,
                    context,
                ),
            },
            "memory": memory_operations(path, authority),
        }
    )
