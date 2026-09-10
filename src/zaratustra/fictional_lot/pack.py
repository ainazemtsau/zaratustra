"""Finite inspection then evidence-bound disposition; no state IO or authority."""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from zaratustra.core import InitialRecords, NextWork, PackReference, ProcessMetadata, Work
from zaratustra.process_packs import (
    CapabilitySelection,
    ContextRequirements,
    Notice,
    PackError,
    PackRegistration,
)

INSPECT = "fictional.lot/v1:inspect"
DECIDE = "fictional.lot/v1:decide"
CLOSED = "fictional.lot/v1:closed"


class Input(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class Check(Input):
    item: Literal["casing", "label"]
    observed: bool
    recorded: bool


class Inspection(Input):
    kind: Literal["inspection"]
    batch: Literal["KITE"]
    checks: tuple[Check, ...]


class Disposition(Input):
    kind: Literal["disposition"]
    batch: Literal["KITE"]
    decision: Literal["release", "discard"]
    inspection_sha256: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]


def reference() -> PackReference:
    return PackReference(
        pack_id="fictional.lot",
        pack_version="1.0.0",
        process_type="fictional.lot-release",
        contract_version=1,
        state_version=1,
    )


def initial_requirements() -> tuple[str, ...]:
    return (INSPECT,)


def initial_records() -> InitialRecords:
    return InitialRecords(
        process_title="Fictional KITE lot release",
        goal="Inspect casing and label of fictional lot KITE",
        expected_result="Exact inspection bytes with both marks for both named checks",
        acceptance=("Every required check is observed and recorded",),
        boundaries=("Fictional local evidence only; no real release or external action",),
        budget="One finite fictional lot",
        artifact_title="KITE inspection",
    )


def _stage(work: Work) -> str:
    requirements = work.executor_requirements
    if requirements == (INSPECT,):
        return "inspect"
    if len(requirements) == 2 and requirements[0] == DECIDE:
        digest = requirements[1]
        if len(digest) == 64 and all(character in "0123456789abcdef" for character in digest):
            return "decide"
    if len(requirements) == 2 and requirements[0] == CLOSED:
        if requirements[1] in ("release", "discard"):
            return "closed"
    return "unknown"


class LotRule:
    def next_work(
        self, work: Work, accepted_result: bytes, work_id: UUID, artifact_id: UUID
    ) -> NextWork:
        if work.pack_binding != reference():
            raise PackError("invalid_lot_state", "Exact fictional lot v1 binding required")
        stage = _stage(work)
        try:
            if stage == "inspect":
                inspection = Inspection.model_validate_json(accepted_result)
                if (
                    len(inspection.checks) != 2
                    or {item.item for item in inspection.checks} != {"casing", "label"}
                    or not all(item.observed and item.recorded for item in inspection.checks)
                ):
                    raise PackError("lot_blocked", "Both marks for every named check are required")
                requirements = (DECIDE, hashlib.sha256(accepted_result).hexdigest())
                goal = "Choose release or discard for inspected fictional KITE"
                expected = "Explicit disposition naming the exact accepted inspection SHA256"
                title = "KITE disposition"
            elif stage == "decide":
                disposition = Disposition.model_validate_json(accepted_result)
                if disposition.inspection_sha256 != work.executor_requirements[1]:
                    raise PackError("lot_blocked", "Disposition names a different inspection")
                requirements = (CLOSED, disposition.decision)
                goal = f"Fictional KITE {disposition.decision}; cancel unused continuation"
                expected = "No further package work; trusted host explicitly cancels this Work"
                title = "Unused closed continuation (no Result claimed)"
            else:
                raise PackError("lot_closed" if stage == "closed" else "invalid_lot_state", stage)
        except ValidationError as error:
            raise PackError("invalid_lot_input", "Input must match this fictional stage") from error
        return NextWork(
            work_id=work_id,
            artifact_id=artifact_id,
            goal=goal,
            expected_result=expected,
            acceptance=(expected,),
            boundaries=work.boundaries,
            budget=work.budget,
            executor_requirements=requirements,
            artifact_title=title,
            authority_scope="work_metadata",
        )


class LotReader:
    def describe(self, metadata: ProcessMetadata) -> CapabilitySelection:
        available: list[UUID] = []
        blocked: list[Notice] = []
        decisions: list[Notice] = []
        stages = []
        for work in metadata.works:
            stage = _stage(work)
            label = f"closed({work.executor_requirements[1]})" if stage == "closed" else stage
            stages.append(f"{label}/{work.status}")
            if work.status in ("done", "cancelled"):
                continue
            if work.status == "ready" and stage in ("inspect", "decide"):
                available.append(work.id)
                if stage == "decide":
                    decisions.append(
                        Notice(
                            key=f"disposition:{work.id}",
                            work_id=work.id,
                            text="Choose fictional release or discard with exact inspection basis",
                        )
                    )
            else:
                blocked.append(
                    Notice(
                        key=f"blocked:{work.id}",
                        work_id=work.id,
                        text="Closed continuation: cancel explicitly"
                        if stage == "closed"
                        else "Work is not an executable fictional lot stage",
                    )
                )
        return CapabilitySelection(
            current_status="Visible KITE stages: " + (", ".join(stages) or "none disclosed"),
            items_needing_attention=tuple(decisions + blocked),
            open_decisions=tuple(decisions),
            available_works=tuple(available),
            blocked_works=tuple(blocked),
            recent_important_results=tuple(row.id for row in metadata.results),
            context_requirements=ContextRequirements(
                notes=(
                    "Use only this Work and Core-verified exact inspection/disposition grounds",
                ),
                references=metadata.context_references,
            ),
        )


def registration() -> PackRegistration:
    return PackRegistration(reference(), LotRule(), LotReader())
