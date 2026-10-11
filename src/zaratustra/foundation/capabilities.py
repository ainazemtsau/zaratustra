"""Code-owned procedure capabilities, shared by schemas, compilation and adapters."""

from dataclasses import asdict, dataclass
from enum import StrEnum


class ProcedureOperation(StrEnum):
    DESCRIBE_STRUCTURE = "describe_structure"
    LIST_FORMATS = "list_formats"
    READ_FORMAT = "read_format"
    CREATE_ENTRY = "create_entry"
    CORRECT_ENTRY = "correct_entry"
    INGEST_BATCH = "ingest_batch"
    READ_ENTRY = "read_entry"
    HISTORY = "history"
    QUERY_ENTRIES = "query_entries"
    AGGREGATE_ENTRIES = "aggregate_entries"
    WORKING_SET = "working_set"
    START_PROCEDURE = "start_procedure"
    PROCEDURE_STATUS = "procedure_status"
    DUE_PROCEDURES = "due_procedures"
    CATALOG = "catalog"
    READ_BATCH = "read_batch"
    PREPARE_CACHE = "prepare_cache"
    OPEN_SELECTION = "open_selection"
    RETAIN = "retain"
    PREPARE = "prepare"
    PUBLISH = "publish"
    REQUEST_INPUT = "request_input"


@dataclass(frozen=True)
class ProcedureCapability:
    operation: ProcedureOperation
    purpose: str
    interfaces: tuple[str, ...]
    calls: tuple[str, ...]
    procedure_applicable: bool = True


def procedure_capabilities() -> tuple[ProcedureCapability, ...]:
    """Names are existing interfaces; this catalog never grants permission."""
    details = {
        "describe_structure": ("Read the exact Activity structure", ("data",)),
        "list_formats": ("List typed formats", ("data",)),
        "read_format": ("Read an exact format revision", ("data",)),
        "create_entry": ("Create source-backed typed data", ("data",)),
        "correct_entry": ("Correct an entry with retained history", ("data",)),
        "ingest_batch": ("Ingest typed entries with exact event keys", ("data",)),
        "read_entry": ("Read an exact data entry", ("data",)),
        "history": ("Read addressed revisions and origins", ("data", "memory")),
        "query_entries": ("Select exact entries", ("data",)),
        "aggregate_entries": ("Calculate over an exact selection", ("data",)),
        "working_set": ("Read a checked Activity working set", ("data",)),
        "start_procedure": ("Save a procedure intent and ordinary Work", ("data",)),
        "procedure_status": ("Read a saved procedure run", ("data",)),
        "due_procedures": ("Read due procedure intents", ("data",)),
        "catalog": ("Find memory without loading all content", ("memory",)),
        "read_batch": ("Read selected memory in one request", ("memory",)),
        "prepare_cache": ("Prepare or check an exact memory cache", ("memory",)),
        "open_selection": ("Read further pages of a saved selection", ("memory",)),
        "retain": ("Retain an external original with provenance", ("manual",)),
        "prepare": ("Prepare selected external-chat context", ("manual",)),
        "publish": ("Publish the declared Work output", ("pi-result",)),
        "request_input": ("Save a question and continuation", ("pi-wait",)),
    }
    manual_calls = {"prepare": "prepare_document", "retain": "retain_text"}
    return tuple(
        ProcedureCapability(
            item,
            details[item][0],
            details[item][1],
            tuple(
                f"{interface}.{manual_calls.get(item, item)}"
                if interface == "manual"
                else f"{interface}.{item}"
                for interface in details[item][1]
            ),
        )
        for item in ProcedureOperation
    )


def procedure_operation_catalog() -> list[dict[str, object]]:
    return [asdict(item) for item in procedure_capabilities()]


def capability_names(interface: str) -> frozenset[str]:
    return frozenset(
        item.operation for item in procedure_capabilities() if interface in item.interfaces
    )
