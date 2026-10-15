"""Agent-independent installed shared-memory operations over public Core."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from zaratustra.foundation import (
    KnowledgeRef,
    LocalAuthority,
    RuntimeMemorySelector,
    admit_runtime_selectors,
    memory_catalog,
    memory_history,
    open_memory_selection,
    prepare_memory_cache,
    read_memory_batch,
    read_runtime_material_batch,
)

from .registry import IntegrationResult, Operation, Parameters


class Query(Parameters):
    selectors: tuple[RuntimeMemorySelector, ...] = ()
    max_bytes: int = Field(default=16384, ge=1, le=32768)


class Batch(Query):
    material_refs: tuple[KnowledgeRef, ...] = ()
    material_index: int = Field(default=0, ge=0)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def one_reader(self) -> Batch:
        if "material_refs" in self.model_fields_set and not self.material_refs:
            raise ValueError("Explicit material_refs must not be empty")
        if self.material_refs and self.selectors:
            raise ValueError("Choose exact material_refs or indexed-memory selectors, not both")
        if not self.material_refs and (self.material_index or self.offset):
            raise ValueError("Material continuation requires exact material_refs")
        return self


class Catalog(Parameters):
    selectors: tuple[RuntimeMemorySelector, ...] = ()
    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = None
    full: bool = False


class Open(Parameters):
    selection_id: UUID
    part: int = Field(default=0, ge=0)
    offset: int = Field(default=0, ge=0)
    toc_offset: int = Field(default=0, ge=0)
    max_bytes: int = Field(default=16384, ge=1, le=32768)


class History(Parameters):
    record_id: UUID
    after_revision: int = Field(default=0, ge=0)
    limit: int = Field(default=25, ge=1, le=100)


def memory_operations(path: Path, authority: LocalAuthority) -> dict[str, Operation]:
    def result(output: dict[str, object]) -> IntegrationResult:
        return IntegrationResult(
            output,
            tuple(
                KnowledgeRef.model_validate(ref)
                for ref in cast(list[object], output.get("exposed", []))
            ),
        )

    def catalog(_operation_id: UUID, parameters: BaseModel) -> IntegrationResult:
        args = cast(Catalog, parameters)
        return result(
            memory_catalog(
                path,
                authority,
                selectors=admit_runtime_selectors(path, authority, args.selectors),
                limit=args.limit,
                cursor=args.cursor,
                full=args.full,
            )
        )

    def batch(operation_id: UUID, parameters: BaseModel) -> IntegrationResult:
        args = cast(Batch, parameters)
        if args.material_refs:
            return result(
                read_runtime_material_batch(
                    path,
                    authority,
                    args.material_refs,
                    material_index=args.material_index,
                    offset=args.offset,
                    max_bytes=args.max_bytes,
                )
            )
        return result(
            read_memory_batch(
                path,
                authority,
                admit_runtime_selectors(path, authority, args.selectors),
                operation_id=operation_id,
                max_bytes=args.max_bytes,
            )
        )

    def cache(_operation_id: UUID, parameters: BaseModel) -> IntegrationResult:
        args = cast(Query, parameters)
        return result(
            prepare_memory_cache(
                path,
                authority,
                admit_runtime_selectors(path, authority, args.selectors),
                max_bytes=args.max_bytes,
            )
        )

    def opened(_operation_id: UUID, parameters: BaseModel) -> IntegrationResult:
        args = cast(Open, parameters)
        return result(
            open_memory_selection(
                path,
                args.selection_id,
                authority,
                part=args.part,
                offset=args.offset,
                max_bytes=args.max_bytes,
                toc_offset=args.toc_offset,
            )
        )

    def history(_operation_id: UUID, parameters: BaseModel) -> IntegrationResult:
        args = cast(History, parameters)
        return result(
            memory_history(
                path,
                args.record_id,
                authority,
                after_revision=args.after_revision,
                limit=args.limit,
            )
        )

    return {
        "catalog": Operation(
            "Discover available areas, organized records and new intake",
            "Read only; catalog pages do not expose original bodies",
            Catalog,
            catalog,
        ),
        "read_batch": Operation(
            "Read indexed memory selectors or exact mixed material_refs with bounded continuation",
            "Indexed selections are retained; exact materials only read; no external send",
            Batch,
            batch,
        ),
        "prepare_cache": Operation(
            "Reuse unchanged selection, rebuild changed membership without a model",
            "Derived Core views; current rights required",
            Query,
            cache,
        ),
        "open_selection": Operation(
            "Continue exact selection text; only returned bytes are exposed",
            "Read only; follow next_part/next_offset",
            Open,
            opened,
        ),
        "history": Operation(
            "Read addressed revision history and open exact originals separately",
            "Read only; no new measurement is inferred from a correction",
            History,
            history,
        ),
    }
