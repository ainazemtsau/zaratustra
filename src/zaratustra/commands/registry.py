"""Explicit installed command extensions, shared by validation, schema and dispatch."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel

if TYPE_CHECKING:
    from . import Command, Context


@dataclass(frozen=True)
class CommandSpec:
    name: str
    payload: type[BaseModel]
    handler: Callable[[Context, Command, str, UUID, int | None], dict[str, Any]]
    description: str


EXTENSIONS: dict[str, CommandSpec] = {}
BUILTINS: tuple[str, ...] = ()


def register(spec: CommandSpec) -> None:
    if spec.name in EXTENSIONS or spec.name in BUILTINS:
        raise ValueError("Duplicate command: " + spec.name)
    EXTENSIONS[spec.name] = spec


def names() -> tuple[str, ...]:
    return BUILTINS + tuple(EXTENSIONS)


def action_schema(schema: dict[str, Any]) -> None:
    schema["enum"] = list(names())


def describe(query: str) -> list[dict[str, Any]]:
    return [
        {
            "action": spec.name,
            "description": spec.description,
            "payload_schema": spec.payload.model_json_schema(),
        }
        for spec in EXTENSIONS.values()
        if not query or spec.name == query
    ]
