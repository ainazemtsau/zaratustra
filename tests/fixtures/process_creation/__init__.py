"""Load the two explicit fictional process-construction and creation inputs."""

import json
from pathlib import Path

from zaratustra.core import PackReference
from zaratustra.process_packs import (
    DataValue,
    ProcessDefinition,
    Reason,
    SourceReference,
)

ROOT = Path(__file__).resolve().parent


def _load(name: str) -> ProcessDefinition:
    return ProcessDefinition.model_validate_json((ROOT / name).read_bytes())


def small_definition() -> ProcessDefinition:
    return _load("small.json")


def project_definition() -> ProcessDefinition:
    return _load("project.json")


def small_reference() -> PackReference:
    return PackReference(
        pack_id="fictional.creation-small",
        pack_version="1.0.0",
        process_type="fictional.recurring-brief",
        contract_version=1,
        state_version=1,
    )


def project_reference() -> PackReference:
    return PackReference(
        pack_id="fictional.creation-project",
        pack_version="1.0.0",
        process_type="fictional.project-assembly",
        contract_version=1,
        state_version=1,
    )


def small_result_data() -> tuple[DataValue, ...]:
    return (DataValue(key="note", value="Fictional amber brief captured"),)


def project_request_data() -> tuple[DataValue, ...]:
    return (DataValue(key="request_fact", value="Fictional request selects three panels"),)


def project_research_data() -> tuple[DataValue, ...]:
    return (DataValue(key="research_fact", value="Fictional study permits seven marks"),)


def creation_draft(case: str) -> bytes:
    definition = small_definition() if case == "small" else project_definition()
    need = (
        "Keep a fictional amber brief as an explicitly recurring local process."
        if case == "small"
        else "Build a fictional panel decision from separate request and research facts."
    )
    outcome = (
        "Each accepted brief makes the next numbered occurrence available."
        if case == "small"
        else "Assembly becomes available only after both predecessor facts are retained."
    )
    draft = dict(
        version=1,
        process_title=definition.title,
        need=need,
        desired_outcomes=[outcome],
        constraints=["Synthetic technical development fixture only; no real user data."],
        declared_capabilities=list(definition.required_capabilities),
        clarifications=[
            dict(
                question="Should repetition be a numbered occurrence rather than a graph cycle?",
                why_needed="The constructor rejects dependency backedges.",
                answer="Yes; use numbered occurrences only."
                if case == "small"
                else "Not recurring.",
            )
        ],
        created_by=f"fictional-{case}-creation-fixture",
    )
    return (json.dumps(draft, ensure_ascii=False, indent=2) + "\n").encode()


def creation_research(case: str) -> bytes:
    text = (
        "Synthetic research return: numbered occurrences preserve recurrence without a backedge."
        if case == "small"
        else (
            "Synthetic research return: retain request and research outputs separately "
            "before assembly."
        )
    )
    return (text + "\n").encode()


def pre_fix_unicode_request() -> bytes:
    """Exact canonical request bytes saved by the 0.14.0 product."""
    return (ROOT / "pre_fix_unicode_request.json").read_bytes()


def linked_creation_definition(
    case: str, request_sha256: str, research_sha256: str
) -> ProcessDefinition:
    base = small_definition() if case == "small" else project_definition()
    request = SourceReference(
        source_id="saved-request",
        kind="request",
        locator=f"creation-request-sha256:{request_sha256}",
    )
    research = SourceReference(
        source_id="saved-research",
        kind="research",
        locator=f"research-return-sha256:{research_sha256}",
    )
    capability_sources = tuple(
        SourceReference(
            source_id=f"capability-{index}",
            kind="capability",
            locator=f"capability:{capability}",
        )
        for index, capability in enumerate(base.required_capabilities, start=1)
    )
    sources = (request, research, *capability_sources)
    all_source_ids = tuple(row.source_id for row in sources)
    nodes = tuple(
        node.model_copy(
            update=dict(
                reasons=(
                    Reason(
                        text=node.reasons[0].text,
                        source_ids=all_source_ids,
                    ),
                )
            )
        )
        for node in base.nodes
    )
    return base.model_copy(update=dict(sources=sources, nodes=nodes))
