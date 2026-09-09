"""Immutable read adapter values; a selection is a view, never state or authority."""

from __future__ import annotations

from typing import Annotated, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from zaratustra.core import ArtifactReference, ProcessMetadata

Text = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=4096)
]


class ReadModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Notice(ReadModel):
    key: Text
    work_id: UUID
    text: Text


class ContextRequirements(ReadModel):
    notes: tuple[Text, ...] = ()
    references: Annotated[tuple[ArtifactReference, ...], Field(max_length=32)] = ()


class CapabilitySelection(ReadModel):
    # None explicitly means unsupported; empty tuples mean supported and empty.
    current_status: Text | None = None
    items_needing_attention: tuple[Notice, ...] | None = None
    open_decisions: tuple[Notice, ...] | None = None
    available_works: tuple[UUID, ...] | None = None
    blocked_works: tuple[Notice, ...] | None = None
    recent_important_results: tuple[UUID, ...] | None = None
    context_requirements: ContextRequirements | None = None


class CapabilityReader(Protocol):
    def describe(self, metadata: ProcessMetadata) -> CapabilitySelection: ...
