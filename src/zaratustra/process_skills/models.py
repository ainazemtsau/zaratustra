"""Typed skill content and exact, process-owned activation configuration."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from zaratustra.journal import DEFAULT_REGISTRY, Reference, TypeSpec

Name = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=128)
]
SkillName = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=64, pattern="^[a-z0-9]+(-[a-z0-9]+)*$"),
]
Scalar = str | bool | int
SKILL_TYPE = "skill"
BINDING_TYPE = "skill_bindings"


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Dependency(Model):
    kind: Literal["command", "type", "resource"]
    name: Name
    version: Name | None = None
    required: bool = True

    @model_validator(mode="after")
    def pinned_resource(self) -> Dependency:
        if self.kind == "resource" and self.version is None:
            raise ValueError("Installed resources require an exact version")
        return self


class Parameter(Model):
    kind: Literal["string", "boolean", "integer"]
    description: Annotated[str, Field(min_length=1, max_length=1024)]
    required: bool = False
    default: Scalar | None = None
    choices: Annotated[tuple[Scalar, ...], Field(max_length=32)] = ()

    def accepts(self, value: Any) -> bool:
        expected = {"string": str, "boolean": bool, "integer": int}[self.kind]
        return type(value) is expected and (not self.choices or value in self.choices)

    @model_validator(mode="after")
    def defaults(self) -> Parameter:
        if self.default is not None and not self.accepts(self.default):
            raise ValueError("Parameter default must match its type and choices")
        if any(not self.accepts(choice) for choice in self.choices):
            raise ValueError("Parameter choices must match its type")
        return self


class Skill(Model):
    name: SkillName
    description: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=1024)
    ]
    body: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=80_000)
    ]
    dependencies: Annotated[tuple[Dependency, ...], Field(max_length=32)] = ()
    parameters: Annotated[dict[Name, Parameter], Field(max_length=16)] = {}
    derived_from: Reference | None = None

    def markdown(self) -> str:
        return chr(10).join(
            [
                "---",
                "name: " + json.dumps(self.name, ensure_ascii=False),
                "description: " + json.dumps(self.description, ensure_ascii=False),
                "---",
                "",
                self.body,
                "",
            ]
        )


class Binding(Model):
    slot: Name
    skill: Reference
    settings: Annotated[dict[Name, Scalar], Field(max_length=16)] = {}

    @model_validator(mode="after")
    def pinned_record(self) -> Binding:
        if self.skill.kind != "record":
            raise ValueError("Binding requires a versioned skill record")
        return self


class Configuration(Model):
    bindings: Annotated[tuple[Binding, ...], Field(max_length=16)] = ()

    @model_validator(mode="after")
    def distinct(self) -> Configuration:
        if len({b.slot for b in self.bindings}) != len(self.bindings):
            raise ValueError("Each role slot has exactly one selected implementation")
        identities = [(b.skill.scope.kind, b.skill.scope.id, b.skill.id) for b in self.bindings]
        if len(set(identities)) != len(identities):
            raise ValueError("A skill cannot be activated twice through different slots")
        return self


def skill_links(payload: dict[str, Any]) -> tuple[Reference, ...]:
    source = Skill.model_validate(payload).derived_from
    return (source,) if source is not None else ()


def binding_links(payload: dict[str, Any]) -> tuple[Reference, ...]:
    return tuple(item.skill for item in Configuration.model_validate(payload).bindings)


def register_types() -> None:
    """One installed module registration; no changes to Core's record union."""
    DEFAULT_REGISTRY.register(
        TypeSpec(
            SKILL_TYPE,
            1,
            Skill,
            references=skill_links,
            source="installed: zaratustra.process_skills",
        )
    )
    DEFAULT_REGISTRY.register(
        TypeSpec(
            BINDING_TYPE,
            1,
            Configuration,
            references=binding_links,
            managed_by="skill.bind/skill.unbind",
        )
    )
