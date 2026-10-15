"""Executable query inputs, separate from saved process-definition selectors.

These values are adapter admission only. Saved MemorySelector payloads retain
their definition-local bindings and historical FTS5 expression semantics.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

from pydantic import AwareDatetime, Field, ValidationInfo, field_validator

from .knowledge import read_knowledge, search_knowledge
from .materials import open_material
from .models import ContractModel, DataFilter, KnowledgeRef, MaterialRole, MemorySelector
from .operations import LocalAuthority, read_artifact
from .storage import FoundationError, canonical_json

type SearchMode = Literal["text", "fts5"]


def search_expression(query: str, mode: SearchMode = "text") -> str:
    """Encode ordinary text as one literal phrase; advanced FTS is explicit."""

    if not query.strip():
        raise FoundationError("invalid_request", "Search text must not be blank")
    if "\x00" in query:
        raise FoundationError("invalid_request", "Search text must not contain NUL")
    try:
        query.encode("utf-8")
    except UnicodeEncodeError as error:
        raise FoundationError("invalid_request", "Search text must be valid UTF-8") from error
    if mode == "fts5":
        return query
    if mode != "text":
        raise FoundationError("invalid_request", "Search mode must be text or fts5")
    return '"' + query.replace('"', '""') + '"'


def search_runtime_knowledge(
    path: Path,
    authority: LocalAuthority,
    query: str,
    *,
    query_mode: SearchMode = "text",
    limit: int = 25,
    cursor: str | None = None,
) -> dict[str, object]:
    """Search indexed originals with continuation bound to original text and mode.

    The low-level Core search keeps its historical FTS5 contract. This runtime
    wrapper cannot claim coverage over ordinary Artifact or non-indexed inputs.
    """

    expression = search_expression(query, query_mode)
    namespace = hashlib.sha256(canonical_json([query_mode, query]).encode()).hexdigest()
    inner_cursor = None
    if cursor is not None:
        parts = cursor.split(".")
        if len(parts) != 2 or parts[0] != namespace:
            raise FoundationError("invalid_cursor", "Search cursor differs from this text or mode")
        try:
            inner_cursor = base64.b64decode(parts[1], altchars=b"-_", validate=True).decode("utf-8")
        except (ValueError, UnicodeError, binascii.Error) as error:
            raise FoundationError("invalid_cursor", "Search cursor is malformed") from error
    output = search_knowledge(path, authority, expression, limit=limit, cursor=inner_cursor)
    next_cursor = output["next_cursor"]
    if next_cursor is not None:
        encoded = base64.urlsafe_b64encode(str(next_cursor).encode()).decode("ascii")
        output["next_cursor"] = namespace + "." + encoded
    output["query_mode"] = query_mode
    output["index_coverage"] = output["coverage"]
    return output


def read_runtime_material_batch(
    path: Path,
    authority: LocalAuthority,
    material_refs: tuple[KnowledgeRef, ...],
    *,
    material_index: int = 0,
    offset: int = 0,
    max_bytes: int = 16384,
) -> dict[str, object]:
    """Read exact mixed materials without creating a persisted memory selection."""

    if (
        not material_refs
        or not 0 <= material_index < len(material_refs)
        or offset < 0
        or not 1 <= max_bytes <= 32768
    ):
        raise FoundationError("invalid_request", "Choose exact materials and a finite byte window")
    remaining = max_bytes
    items: list[dict[str, object]] = []
    exposed: list[dict[str, object]] = []
    current = material_index
    current_offset = offset
    while current < len(material_refs):
        # Leave room for the largest UTF-8 code point on subsequent originals.
        # An initial smaller budget is validated by the exact material reader.
        if items and remaining < 4:
            break
        item = open_material(
            path, material_refs[current], authority, offset=current_offset, max_bytes=remaining
        )
        items.append(item)
        exposed.extend(cast(list[dict[str, object]], item["exposed"]))
        remaining -= cast(int, item["returned_bytes"])
        if item["next_offset"] is not None:
            current_offset = cast(int, item["next_offset"])
            break
        current += 1
        current_offset = 0
    return {
        "kind": "material_batch",
        "items": items,
        "exposed": exposed,
        "returned_bytes": max_bytes - remaining,
        "next_material_index": current if current < len(material_refs) else None,
        "next_offset": current_offset if current < len(material_refs) else None,
        "content_complete": material_index == 0
        and offset == 0
        and current == len(material_refs)
        and all(bool(item["content_complete"]) for item in items),
        "end_of_batch": current == len(material_refs),
        "coverage": "only the exact requested material revisions and byte windows",
    }


class RuntimeMemorySelector(ContractModel):
    """An executable selection with exact scopes, formats and explicit bounds.

    Filters within one selector are conjunctive; several selectors form a union.
    Read a pinned Activity structure for format_refs. Definition-only bindings
    current_activity, format_keys and use_period are deliberately not fields.
    """

    empty: bool = False
    activity_ids: tuple[UUID, ...] = ()
    common: bool = False
    record_ids: tuple[UUID, ...] = Field(
        default=(),
        description=(
            "Indexed knowledge identities; use material_refs for exact mixed material revisions"
        ),
    )
    topics: tuple[str, ...] = ()
    query: str | None = Field(default=None, min_length=1)
    query_mode: SearchMode = Field(
        default="text",
        description="text treats query as a literal phrase; fts5 enables FTS5 expression grammar",
    )
    full: bool = False
    context_role: Literal["reference", "required", "legacy"] | None = None
    kinds: tuple[
        Literal[
            "source",
            "claim",
            "analysis",
            "link",
            "view",
            "handoff",
            "data_format",
            "data_entry",
            "activity_structure",
        ],
        ...,
    ] = ()
    material_roles: tuple[MaterialRole, ...] = ()
    format_refs: tuple[KnowledgeRef, ...] = Field(
        default=(), description="Exact DataFormat revisions from the selected pinned structure"
    )
    data_filters: tuple[DataFilter, ...] = ()
    date_from: date | None = Field(default=None, description="Inclusive event-date bound")
    date_until: date | None = Field(default=None, description="Exclusive event-date bound")
    time_from: AwareDatetime | None = Field(default=None, description="Inclusive event-time bound")
    time_until: AwareDatetime | None = Field(default=None, description="Exclusive event-time bound")
    data_statuses: tuple[str, ...] = ()

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Search text must not be blank")
        if value is not None and "\x00" in value:
            raise ValueError("Search text must not contain NUL")
        if value is not None:
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as error:
                raise ValueError("Search text must be valid UTF-8") from error
        return value

    @field_validator("date_until")
    @classmethod
    def ordered_dates(cls, value: date | None, info: ValidationInfo) -> date | None:
        lower = info.data.get("date_from")
        if value is not None and lower is not None and value < lower:
            raise ValueError("Exclusive date_until must not precede date_from")
        return value

    @field_validator("time_until")
    @classmethod
    def ordered_times(
        cls, value: AwareDatetime | None, info: ValidationInfo
    ) -> AwareDatetime | None:
        lower = info.data.get("time_from")
        if value is not None and lower is not None and value < lower:
            raise ValueError("Exclusive time_until must not precede time_from")
        return value

    def to_selector(self) -> MemorySelector:
        """Create an ordinary Core selector without changing saved definitions."""

        values = self.model_dump(exclude={"query_mode"})
        if self.query is not None:
            values["query"] = search_expression(self.query, self.query_mode)
        return MemorySelector.model_validate(values)


def runtime_selectors(
    selectors: Iterable[RuntimeMemorySelector],
) -> tuple[MemorySelector, ...]:
    """Convert already validated executable inputs before any selection effect."""

    return tuple(selector.to_selector() for selector in selectors)


def current_runtime_knowledge_reference(
    path: Path, authority: LocalAuthority, record_id: UUID
) -> KnowledgeRef:
    """Resolve legacy knowledge-only input without claiming other families absent."""

    try:
        item = read_knowledge(path, record_id, authority)
    except FoundationError as error:
        if error.code != "not_found":
            raise
        try:
            artifact = read_artifact(path, record_id, authority)
        except FoundationError as other:
            if other.code == "not_found":
                raise error from None
            raise
        raise FoundationError(
            "wrong_kind",
            "This authorized address is an ordinary Artifact, not indexed knowledge; "
            "use open or material_refs with exact revision " + str(artifact.revision),
        ) from None
    return KnowledgeRef(record_id=record_id, revision=item.revision)


def admit_runtime_selectors(
    path: Path, authority: LocalAuthority, selectors: Iterable[RuntimeMemorySelector]
) -> tuple[MemorySelector, ...]:
    """Check explicit indexed families before any runtime selection is retained."""

    result = runtime_selectors(selectors)
    for selector in result:
        for identifier in selector.record_ids:
            current_runtime_knowledge_reference(path, authority, identifier)
    return result


__all__ = [
    "RuntimeMemorySelector",
    "SearchMode",
    "runtime_selectors",
    "admit_runtime_selectors",
    "current_runtime_knowledge_reference",
    "read_runtime_material_batch",
    "search_expression",
    "search_runtime_knowledge",
]
