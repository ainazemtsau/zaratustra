"""Installed, explicit schema registration; data never loads Python handlers."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StringConstraints,
    model_serializer,
    model_validator,
)

from zaratustra.core import WorkspaceError

Text = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=100_000)
]
Name = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=128)
]
Positive = Annotated[int, Field(strict=True, ge=1)]
MEDIA_TYPE = "application/vnd.zaratustra.record+json"
MAX_CONTENT = 8_000_000
Action = Literal["create", "revise", "adopt", "replace", "revoke", "metadata"]


class JournalError(WorkspaceError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Scope(Model):
    kind: Literal["process", "home"]
    id: UUID


class Reference(Model):
    scope: Scope
    kind: Literal["record", "material"] = "record"
    id: UUID
    revision: Positive


class Episode(Model):
    situation: Text
    actions: tuple[Text, ...] = ()
    outcome: Text
    evidence: tuple[Text, ...] = ()
    unknowns: tuple[Text, ...] = ()
    next_action: Text | None = None
    category: Name = "work"
    occurred_at: datetime | None = None


class Decision(Model):
    commitment: Text
    rationale: Text
    applies_to: Text


class Document(Model):
    media_type: Name = "text/plain"
    text: str | None = None
    base64: str | None = None

    @model_validator(mode="after")
    def content(self) -> Document:
        if (self.text is None) == (self.base64 is None):
            raise ValueError("Document needs exactly one text or base64 content")
        if len(self.bytes()) > MAX_CONTENT:
            raise ValueError("Document exceeds 8 MB")
        return self

    def bytes(self) -> bytes:
        if self.text is not None:
            return self.text.encode("utf-8")
        return base64.b64decode(self.base64 or "", validate=True)


def mutable_transition(state: str, action: Action) -> str:
    if state != "active" or action != "revise":
        raise JournalError("invalid_transition", f"Cannot {action} from {state}")
    return state


def decision_transition(state: str, action: Action) -> str:
    allowed = {
        ("proposed", "revise"): "proposed",
        ("proposed", "adopt"): "accepted",
        ("accepted", "replace"): "accepted",
        ("accepted", "revoke"): "revoked",
    }
    if (state, action) not in allowed:
        raise JournalError("invalid_transition", f"Cannot {action} from {state}")
    return allowed[state, action]


def no_references(payload: dict[str, Any]) -> tuple[Reference, ...]:
    return ()


@dataclass(frozen=True)
class TypeSpec:
    name: str
    version: int
    payload_model: type[BaseModel]
    operations: tuple[Action, ...] = ("create", "revise")
    initial_state: str = "active"
    source: str = "installed: zaratustra.journal"
    transition: Callable[[str, Action], str] = mutable_transition
    references: Callable[[dict[str, Any]], tuple[Reference, ...]] = no_references
    managed_by: str | None = None

    def schema(self) -> dict[str, Any]:
        return self.payload_model.model_json_schema()

    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.payload_model.model_validate(payload).model_dump(mode="json")


class Registry:
    def __init__(self) -> None:
        self._types: dict[tuple[str, int], TypeSpec] = {}

    def register(self, spec: TypeSpec) -> None:
        key = (spec.name, spec.version)
        if key in self._types or spec.version < 1 or not spec.name.strip():
            raise JournalError("type_conflict", "Type name/version must be unique and valid")
        self._types[key] = spec

    def get(self, name: str, version: int) -> TypeSpec:
        try:
            return self._types[(name, version)]
        except KeyError as error:
            raise JournalError(
                "type_unavailable", f"No installed type {name} v{version}"
            ) from error

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "type": spec.name,
                "schema_version": spec.version,
                "schema": spec.schema(),
                "operations": spec.operations,
                "source": spec.source,
                "managed_by": spec.managed_by,
            }
            for spec in self._types.values()
        ]


DEFAULT_REGISTRY = Registry()
DEFAULT_REGISTRY.register(TypeSpec("episode", 1, Episode))
DEFAULT_REGISTRY.register(TypeSpec("document", 1, Document))
DEFAULT_REGISTRY.register(
    TypeSpec(
        "decision",
        1,
        Decision,
        ("create", "revise", "adopt", "replace", "revoke"),
        "proposed",
        transition=decision_transition,
    )
)


class Change(Model):
    operation_id: UUID
    action: Action = "create"
    record_id: UUID | None = None
    expected_revision: Positive | None = None
    type_name: Name | None = None
    schema_version: Positive = 1
    title: Name | None = None
    payload: dict[str, Any] | None = None
    links: Annotated[tuple[Reference, ...], Field(max_length=32)] | None = None
    reason: Text
    authority_source: Text | None = None
    metadata: SearchMetadata | None = None

    @model_serializer(mode="wrap")
    def serialize(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.metadata is None:
            result.pop("metadata", None)
        return result

    def fingerprint(self) -> str:
        return hashlib.sha256(canonical(self.model_dump(mode="json"))).hexdigest()


class SearchMetadata(Model):
    tags: Annotated[tuple[UUID, ...], Field(max_length=32)] = ()
    document_purpose: UUID | None = None
    problem_status: Literal["open", "resolved"] | None = None

    @model_validator(mode="after")
    def unique_tags(self) -> SearchMetadata:
        if len(set(self.tags)) != len(self.tags):
            raise ValueError("Duplicate tag references")
        return self


class Revision(Model):
    format: Literal[1, 2] = 1
    id: UUID
    revision: Positive
    scope: Scope
    type_name: Name
    schema_version: Positive
    payload_schema: dict[str, Any]
    type_source: Text
    title: Name
    payload: dict[str, Any]
    links: tuple[Reference, ...] = ()
    state: Name
    action: Action
    reason: Text
    authority_source: Text | None = None
    previous: Reference | None = None
    recorded_at: datetime
    source_ref: Text
    operation_id: UUID
    fingerprint: str
    metadata: SearchMetadata = SearchMetadata()

    @model_serializer(mode="wrap")
    def serialize(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.format == 1:
            result.pop("metadata", None)
        return result

    def reference(self) -> Reference:
        return Reference(scope=self.scope, id=self.id, revision=self.revision)


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


Change.model_rebuild()
