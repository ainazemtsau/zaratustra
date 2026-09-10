"""One derived overview of several selected Processes through the same seven answers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zaratustra.core import ContextQuery, LocalAuthorization, ProcessQuery

from .capabilities import NAMES, _wire, read_capabilities
from .lifecycle import PackError, PackRegistry

MAX_ROWS = 16
MAX_BYTES = 16777216
STATUS_LIMIT = 96


@dataclass(frozen=True)
class OverviewRow:
    """One explicitly selected Process; every row carries its own exact authorization."""

    path: Path
    query: ProcessQuery
    caller: LocalAuthorization | None
    context_query: ContextQuery | None = None
    context_caller: LocalAuthorization | None = None


@dataclass(frozen=True)
class OverviewResponse:
    output: bytes

    @property
    def output_sha256(self) -> str:
        return hashlib.sha256(self.output).hexdigest()


def _request(row: OverviewRow) -> dict[str, Any]:
    # Echo only the consumer's own query fields, never state a refused row withheld.
    query = row.query
    chosen = query.selected_work_id
    return dict(
        workspace_id=str(query.workspace_id),
        process_id=str(query.process_id),
        expected_revision=query.expected_revision,
        visible_work_ids=[str(identity) for identity in query.visible_work_ids],
        selected_work_id=str(chosen) if chosen is not None else None,
        context_requested=row.context_query is not None,
    )


def _summary(answers: dict[str, Any]) -> dict[str, Any]:
    # Mirror state, count and refusal code; each already belongs to that same answer.
    summary: dict[str, Any] = {}
    for name in NAMES:
        answer = answers[name]
        projection: dict[str, Any] = dict(state=answer["state"])
        for key in ("count", "code"):
            if key in answer:
                projection[key] = answer[key]
        summary[name] = projection
    return summary


def _row(row: OverviewRow, registry: PackRegistry) -> dict[str, Any]:
    response = read_capabilities(
        row.path,
        row.query,
        row.caller,
        registry,
        context_query=row.context_query,
        context_caller=row.context_caller,
    )
    document: dict[str, Any] = json.loads(response.output)
    return dict(
        request=_request(row),
        response_sha256=response.output_sha256,
        response=document,
        answers=_summary(document["answers"]),
    )


def _coordinates(rows: Sequence[OverviewRow]) -> list[tuple[str, str]]:
    return [(Path(row.path).resolve().as_posix(), str(row.query.process_id)) for row in rows]


def read_overview(
    rows: Sequence[OverviewRow], registry: PackRegistry, *, max_bytes: int = 1048576
) -> OverviewResponse:
    """Read each selected Process through the one public contract, then only project it.

    Rows stay independent: one workspace Process is one consistency unit, and this view
    promises neither a shared transaction nor a shared revision. It derives no new value,
    grants no authority and writes nothing. A refused row stays visible and hides no other.
    """
    if not 1 <= len(rows) <= MAX_ROWS:
        raise PackError("invalid_overview", "An overview names one to sixteen explicit rows")
    if not 1 <= max_bytes <= MAX_BYTES:
        raise PackError("invalid_overview", "The overview byte budget is out of range")
    coordinates = _coordinates(rows)
    if len(set(coordinates)) != len(coordinates):
        raise PackError("duplicate_row", "One workspace Process appears at most once")
    packs = [item.reference.model_dump(mode="json") for item in registry.registrations]
    output = _wire(
        dict(
            version=1,
            envelope=dict(
                consumer="shared_process_overview",
                derived="read_only_view_of_the_same_seven_answers; grants_no_authority",
                consistency="row_local; one workspace Process is one consistency unit",
                cross_workspace="no_shared_transaction; no_shared_revision; rows_read_apart",
                ordering="caller_declared_row_order",
                scope="explicit_rows_only; counts_are_returned_items_only; no_hidden_rows",
                registry=packs,
                row_count=len(rows),
            ),
            rows=[_row(row, registry) for row in rows],
        )
    )
    if len(output) > max_bytes:
        refusal = dict(version=1, state="unavailable", code="budget_exceeded")
        return OverviewResponse(_wire(refusal))
    return OverviewResponse(output)


def _flat(value: Any) -> str:
    # Read values are free pack text; one rendered element must stay one safe line.
    plain = "".join(item if item.isprintable() else " " for item in str(value))
    return " ".join(plain.split())


def _clip(text: str) -> str:
    return text if len(text) <= STATUS_LIMIT else text[: STATUS_LIMIT - 3] + "..."


def _title(envelope: dict[str, Any] | None) -> str:
    if envelope is None:
        return "unavailable"
    binding = envelope["pack_binding"]
    process_type = _flat(binding["process_type"])
    pack = _flat(binding["pack_id"]) + "@" + _flat(binding["pack_version"])
    return f"{process_type} pack={pack}"


def overview_lines(output: bytes) -> tuple[str, ...]:
    """Render exactly these bytes; this view reads no state, registry or instructions.

    Every read value is flattened to one printable line, so pack text can never forge
    a row, a count or an envelope claim here. The document keeps the exact bytes.
    A refused row names its code and only the revision its consumer asked for.
    """
    document: dict[str, Any] = json.loads(output)
    if "rows" not in document:
        code = _flat(document["code"])
        return (f"shared process overview unavailable: {code}",)
    envelope = document["envelope"]
    count = _flat(envelope["row_count"])
    lines: list[str] = [
        f"shared process overview: {count} rows",
        "derived: " + _flat(envelope["derived"]),
        "consistency: " + _flat(envelope["consistency"]),
        "across workspaces: " + _flat(envelope["cross_workspace"]),
    ]
    for index, row in enumerate(document["rows"], start=1):
        answers = row["answers"]
        states: list[str] = []
        for name in NAMES:
            answer = answers[name]
            amount, reason = answer.get("count"), answer.get("code")
            state = name + "=" + _flat(answer["state"])
            state = state if amount is None else state + "(" + _flat(amount) + ")"
            states.append(state if reason is None else state + ":" + _flat(reason))
        header = row["response"].get("envelope")
        title = _title(header)
        process = _flat(row["request"]["process_id"])
        # A refused row read no revision; only the consumer's own number exists.
        revision = (
            "requested_revision=" + _flat(row["request"]["expected_revision"])
            if header is None
            else "revision=" + _flat(header["state_revision"])
        )
        lines.append(f"{index}. {title} process={process} {revision}")
        lines.append("   " + "  ".join(states))
        status = row["response"]["answers"]["current_status"]
        if status["state"] == "ok":
            lines.append("   status: " + _clip(_flat(status["value"])))
    return tuple(lines)
