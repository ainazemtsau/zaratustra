"""One explicit vocabulary proposal/approval path for every agent host."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from zaratustra import home

from . import Command, Context, registry


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["tag", "category", "document_purpose"] | None = None


class Proposal(Selection):
    kind: Literal["tag", "category", "document_purpose"]
    label: str = Field(min_length=1, max_length=128)
    meaning: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=2000)
    considered: tuple[UUID, ...] = ()


class Creation(Proposal):
    generation: str
    proposal_token: str
    authority_source: str = Field(min_length=1, max_length=10000)


def _token(proposal: Proposal, generation: str) -> str:
    content = {"proposal": proposal.model_dump(mode="json"), "generation": generation}
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def execute(
    context: Context, command: Command, source: str, operation: UUID, guard: int | None
) -> dict[str, Any]:
    root = Path(context.home)
    selection = Selection.model_validate({"kind": (command.payload or {}).get("kind")})
    values = home.vocabulary(root, selection.kind)
    generation = home.vocabulary_generation(root)
    if command.action == "vocabulary.list":
        query = home.vocabulary_key(command.query)
        matches = [
            value
            for value in values
            if not query or query in home.vocabulary_key(value["label"] + " " + value["meaning"])
        ]
        return {
            "values": matches[command.offset : command.offset + command.limit],
            "total": len(matches),
            "generation": generation,
        }
    proposal = Proposal.model_validate(
        {
            key: value
            for key, value in (command.payload or {}).items()
            if key in Proposal.model_fields
        }
    )
    identical = [
        value
        for value in values
        if home.vocabulary_key(value["label"]) == home.vocabulary_key(proposal.label)
    ]
    if any(str(identity) not in {row["id"] for row in values} for identity in proposal.considered):
        raise home.HomeError("unknown_alternative", "Review actual existing vocabulary values")
    if command.action == "vocabulary.propose":
        if identical:
            return {"status": "reuse_existing", "values": identical}
        return {
            "status": "owner_decision_required",
            "proposal": proposal.model_dump(mode="json"),
            "generation": generation,
            "proposal_token": _token(proposal, generation),
            "considered": [row for row in values if UUID(row["id"]) in proposal.considered],
            "instruction": "Check meanings, show relevant alternatives and why none fits. "
            "Ask for creation unless this exact new value is already explicitly authorized.",
        }
    creation = Creation.model_validate(command.payload)
    if creation.proposal_token != _token(proposal, creation.generation):
        raise home.HomeError("changed_proposal", "Approval must refer to the exact proposed value")
    return home.add_vocabulary(
        root,
        kind=proposal.kind,
        label=proposal.label,
        meaning=proposal.meaning,
        expected_generation=creation.generation,
        authority_source=creation.authority_source,
        operation_id=operation,
    )


for action, payload in (
    ("vocabulary.list", Selection),
    ("vocabulary.propose", Proposal),
    ("vocabulary.create", Creation),
):
    registry.register(
        registry.CommandSpec(
            action,
            payload,
            execute,
            "Home vocabulary: inspect existing meanings, propose a nonduplicate value, "
            "then create the exact owner-approved proposal",
        )
    )
