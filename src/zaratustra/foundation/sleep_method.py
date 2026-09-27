"""Shipped version-one Sleep Method and ordinary composite Work template."""

from __future__ import annotations

from uuid import UUID, uuid5

from .composition import method_checksum
from .models import (
    MethodDefinition,
    MethodObligation,
    MethodRef,
    OutputContract,
    PlanChild,
    PlanCondition,
    PlanOutputBinding,
    WorkPlan,
    WorkState,
)

SEED_SOURCE = "zaratustra:initial-sleep:v1"


def initial_sleep_method_id(space_id: UUID) -> UUID:
    return uuid5(space_id, SEED_SOURCE)


def initial_sleep_method() -> MethodDefinition:
    """Both obligations are finite; no finding is a valid supported conclusion."""

    instruction = (
        "Review authorized accumulated experience in bounded portions. First consolidate "
        "the selected work and conversation material into useful current memory when needed: "
        "open exact sources, distinguish observation, report, hypothesis and effect, preserve "
        "provenance, counterevidence and unfinished analysis. A usable existing representation "
        "may need no new record. Then make one bounded exploratory comparison that is not "
        "driven by a complaint: rotate beyond the anchor's known links to another authorized "
        "area, period or unlinked source; open actual content and ask whether a concrete "
        "relationship helps another work. No finding is acceptable. Record the intake cutoff, "
        "enumeration and exploration positions, selected and actually delivered sources, "
        "analysis, committed effects, remaining questions and resource use. A selected but "
        "undelivered or unfinished item remains open. Use ordinary source, Claim, analysis, "
        "link and view operations for memory; a reusable change needs an addressed candidate, "
        "validation, Decision and current Grant. Do not inherit or execute other Works' tasks. "
        "Stop on exhausted resource, missing authority, unavailable necessary source, unknown "
        "effect or unresolved significant premise; save partial progress and resume only from "
        "the retained remainder. Finish only after both consolidation and exploration have "
        "real bounded outcomes and the Work's ordinary output contract is met."
    )
    return MethodDefinition(
        instruction=instruction,
        named_outputs=(OutputContract(slot="report", media_type="text/plain"),),
        obligations=(
            MethodObligation(
                key="consolidation",
                source=SEED_SOURCE,
                role="consolidation",
                slot="report",
                media_type="text/plain",
            ),
            MethodObligation(
                key="exploration",
                source=SEED_SOURCE,
                role="exploration",
                slot="report",
                media_type="text/plain",
            ),
        ),
        source_ref=SEED_SOURCE,
    )


def initial_sleep_ref(space_id: UUID) -> MethodRef:
    definition = initial_sleep_method()
    return MethodRef(
        method_id=initial_sleep_method_id(space_id),
        version=1,
        checksum=method_checksum(definition),
    )


def sleep_work_template(
    *,
    activity_id: UUID,
    method: MethodRef,
    work_id: UUID,
    consolidation_id: UUID,
    exploration_id: UUID,
    scope: str,
) -> tuple[WorkState, WorkPlan]:
    """One ordinary Work with two visible obligations and no separate Sleep status."""

    output = (OutputContract(slot="report", media_type="text/plain"),)
    parent = WorkState(
        activity_id=activity_id,
        goal=f"Bounded Sleep review: {scope}",
        expected_outputs=output,
        method=method,
    )
    consolidation = WorkState(
        activity_id=activity_id,
        goal="Consolidate the selected experience and preserve memory or a reason for no change",
        expected_outputs=output,
    )
    exploration = WorkState(
        activity_id=activity_id,
        goal="Compare material outside ready links and preserve a bounded finding or no finding",
        expected_outputs=output,
    )
    plan = WorkPlan(
        children=(
            PlanChild(role="consolidation", work_id=consolidation_id, state=consolidation),
            PlanChild(role="exploration", work_id=exploration_id, state=exploration),
        ),
        output_bindings=(
            PlanOutputBinding(
                parent_slot="report",
                role="exploration",
                child_slot="report",
                media_type="text/plain",
            ),
        ),
        completion=PlanCondition(
            kind="all",
            members=(
                PlanCondition(kind="work_succeeded", role="consolidation"),
                PlanCondition(kind="work_succeeded", role="exploration"),
            ),
        ),
        rationale="Consolidation and independent exploration have separate accepted results",
        source_ref=f"{SEED_SOURCE}:{work_id}",
    )
    return parent, plan
