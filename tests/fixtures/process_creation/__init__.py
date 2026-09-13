"""Load the two explicit fictional process-construction inputs."""

from pathlib import Path

from zaratustra.core import PackReference
from zaratustra.process_packs import DataValue, ProcessDefinition

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
