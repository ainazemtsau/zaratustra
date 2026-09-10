"""Repeat observations, inserting an evidence-bound comparison only on change."""

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

OBSERVE = "fictional.signal/v1:observe"
COMPARE = "fictional.signal/v1:compare"


class Input(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class Observation(Input):
    kind: Literal["observation"]
    signal: Literal["BEACON"]
    observation: Literal["steady", "changed"]


class Comparison(Input):
    kind: Literal["comparison"]
    signal: Literal["BEACON"]
    observation_sha256: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]
    assessment: Literal["explained", "unexplained"]


def reference() -> PackReference:
    return PackReference(
        pack_id="fictional.signal",
        pack_version="1.0.0",
        process_type="fictional.signal-rounds",
        contract_version=1,
        state_version=1,
    )


def initial_requirements() -> tuple[str, ...]:
    return (OBSERVE,)


def initial_records() -> InitialRecords:
    return InitialRecords(
        process_title="Fictional BEACON observation rounds",
        goal="Observe the fictional BEACON signal",
        expected_result="Exact observation bytes: steady or changed",
        acceptance=("One explicit fictional observation",),
        boundaries=("Fictional local evidence only; no schedule or autonomous execution",),
        budget="One explicitly requested round at a time",
        artifact_title="BEACON observation",
    )


def _stage(work: Work) -> str:
    if work.pack_binding != reference():
        return "unknown"
    requirements = work.executor_requirements
    if requirements == (OBSERVE,):
        return "observe"
    if len(requirements) == 2 and requirements[0] == COMPARE:
        digest = requirements[1]
        if len(digest) == 64 and all(character in "0123456789abcdef" for character in digest):
            return "compare"
    return "unknown"


class SignalRule:
    def next_work(
        self, work: Work, accepted_result: bytes, work_id: UUID, artifact_id: UUID
    ) -> NextWork:
        stage = _stage(work)
        requirements = initial_requirements()
        goal = "Observe the fictional BEACON signal again"
        expected = "Exact observation bytes: steady or changed"
        title = "BEACON observation"
        try:
            if stage == "observe":
                observation = Observation.model_validate_json(accepted_result)
                if observation.observation == "changed":
                    requirements = (COMPARE, hashlib.sha256(accepted_result).hexdigest())
                    goal = "Compare the changed fictional BEACON observation"
                    expected = "Comparison naming the exact changed observation SHA256"
                    title = "BEACON comparison"
            elif stage == "compare":
                comparison = Comparison.model_validate_json(accepted_result)
                if comparison.observation_sha256 != work.executor_requirements[1]:
                    raise PackError("signal_blocked", "Comparison names a different observation")
            else:
                raise PackError("invalid_signal_state", "Exact signal binding and stage required")
        except ValidationError as error:
            raise PackError(
                "invalid_signal_input", "Input must match this fictional stage"
            ) from error
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


class SignalReader:
    def describe(self, metadata: ProcessMetadata) -> CapabilitySelection:
        available: list[UUID] = []
        blocked: list[Notice] = []
        decisions: list[Notice] = []
        stages = []
        for work in metadata.works:
            stage = _stage(work)
            stages.append(f"{stage}/{work.status}")
            if work.status in ("done", "cancelled"):
                continue
            if work.status == "ready" and stage in ("observe", "compare"):
                available.append(work.id)
                if stage == "compare":
                    decisions.append(
                        Notice(
                            key=f"comparison:{work.id}",
                            work_id=work.id,
                            text="Assess the exact changed BEACON observation, then observe again",
                        )
                    )
            else:
                blocked.append(
                    Notice(
                        key=f"blocked:{work.id}",
                        work_id=work.id,
                        text="Work is not an executable fictional signal stage",
                    )
                )
        return CapabilitySelection(
            current_status="Visible BEACON stages: " + (", ".join(stages) or "none disclosed"),
            items_needing_attention=tuple(decisions + blocked),
            open_decisions=tuple(decisions),
            available_works=tuple(available),
            blocked_works=tuple(blocked),
            recent_important_results=tuple(row.id for row in metadata.results),
            context_requirements=ContextRequirements(
                notes=(
                    "Use only this Work and Core-verified exact observation/comparison grounds",
                ),
                references=metadata.context_references,
            ),
        )


def registration() -> PackRegistration:
    return PackRegistration(reference(), SignalRule(), SignalReader())
