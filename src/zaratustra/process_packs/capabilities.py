"""One seven-answer contract, derived from a single authorized Core view."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zaratustra.core import (
    ContextQuery,
    LocalAuthorization,
    MutationError,
    ProcessMetadata,
    ProcessQuery,
    ProcessView,
    WorkspaceError,
    process_view,
)

from .capability_models import CapabilitySelection, Notice
from .lifecycle import PackError, PackRegistry

NAMES = tuple(CapabilitySelection.model_fields)


@dataclass(frozen=True)
class CapabilityResponse:
    output: bytes

    @property
    def output_sha256(self) -> str:
        return hashlib.sha256(self.output).hexdigest()


def _wire(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
        + chr(10)
    ).encode("utf-8")


def _missing(code: str, *, denied: bool = False) -> dict[str, Any]:
    return dict(state="denied" if denied else "unavailable", code=code)


def _answer(value: Any) -> dict[str, Any]:
    if value is None:
        return _missing("unsupported")
    if isinstance(value, list):
        return dict(state="ok" if value else "empty", value=value, count=len(value))
    return dict(state="ok", value=value)


def _failure(code: str, *, denied: bool = False) -> CapabilityResponse:
    return CapabilityResponse(
        _wire(dict(version=1, answers={name: _missing(code, denied=denied) for name in NAMES}))
    )


def _validate(selection: CapabilitySelection, metadata: ProcessMetadata) -> None:
    works = {work.id: work for work in metadata.works}
    for notices in (
        selection.items_needing_attention,
        selection.open_decisions,
        selection.blocked_works,
    ):
        if notices is not None and (
            any(row.work_id not in works for row in notices)
            or len({row.key for row in notices}) != len(notices)
        ):
            raise PackError("invalid_read_response", "Notice must name visible state")
    available, blocked = selection.available_works, selection.blocked_works
    if available is not None and (
        len(set(available)) != len(available)
        or any(identity not in works or works[identity].status != "ready" for identity in available)
    ):
        raise PackError("invalid_read_response", "Available Work must be visible and ready")
    if blocked is not None and (
        len({row.work_id for row in blocked}) != len(blocked)
        or any(works[row.work_id].status in ("done", "cancelled") for row in blocked)
    ):
        raise PackError("invalid_read_response", "Blocked Work must be nonterminal")
    if available is not None and blocked is not None:
        active = {work.id for work in works.values() if work.status not in ("done", "cancelled")}
        blocked_ids = {row.work_id for row in blocked}
        if set(available) & blocked_ids or set(available) | blocked_ids != active:
            raise PackError(
                "invalid_read_response", "Available/blocked must partition active scope"
            )
    results = selection.recent_important_results
    requirements = selection.context_requirements
    if requirements is not None and any(
        ref not in metadata.context_references for ref in requirements.references
    ):
        raise PackError("invalid_read_response", "Context requirements exceed the selected Work")
    if results is not None and (
        len(set(results)) != len(results)
        or not set(results) <= {row.id for row in metadata.results}
    ):
        raise PackError("invalid_read_response", "Result must belong to visible state")


def _answers(
    selection: CapabilitySelection, view: ProcessView, context_query: ContextQuery | None
) -> dict[str, Any]:
    metadata = view.metadata
    works = {row.id: row for row in metadata.works}

    def notices(rows: tuple[Notice, ...] | None) -> list[dict[str, Any]] | None:
        if rows is None:
            return None
        return [
            row.model_dump(mode="json") | dict(work_revision=works[row.work_id].revision)
            for row in rows
        ]

    available = selection.available_works
    results = selection.recent_important_results
    answers = dict(
        current_status=_answer(selection.current_status),
        items_needing_attention=_answer(notices(selection.items_needing_attention)),
        open_decisions=_answer(notices(selection.open_decisions)),
        available_works=_answer(
            [works[identity].model_dump(mode="json") for identity in available]
            if available is not None
            else None
        ),
        blocked_works=_answer(notices(selection.blocked_works)),
        recent_important_results=_answer(
            [row.model_dump(mode="json") for row in metadata.results if row.id in results]
            if results is not None
            else None
        ),
    )
    requirements = selection.context_requirements
    chosen = metadata.query.selected_work_id
    if chosen is None:
        context_answer = _missing("not_requested")
    elif requirements is None:
        context_answer = _missing("unsupported")
    else:
        code = view.context_code
        if (
            code == "ok"
            and context_query is not None
            and context_query.references != requirements.references
        ):
            code = "requirements_changed"
        content = (
            dict(state="ok", value=json.loads(view.context.output))
            if code == "ok" and view.context is not None
            else _missing(code, denied=code in ("permission_denied", "scope"))
        )
        context_answer = _answer(
            dict(
                work_id=str(chosen),
                work_revision=works[chosen].revision,
                executor_requirements=list(works[chosen].executor_requirements),
                **requirements.model_dump(mode="json"),
                context=content,
            )
        )
    answers["context_requirements"] = context_answer
    return answers


def _render(
    view: ProcessView, registry: PackRegistry, context_query: ContextQuery | None
) -> CapabilityResponse:
    metadata = view.metadata
    query = metadata.query
    reference = metadata.process.pack_binding
    if reference is None:
        raise PackError("unbound_pack", "Explicit Process binding required")
    registration = registry.resolve(reference)
    if registration.reader is None:
        raise PackError("missing_read_adapter", "No read adapter registered")
    try:
        selection = registration.reader.describe(metadata)
        selection = CapabilitySelection.model_validate(selection.model_dump())
    except Exception as error:
        raise PackError("read_adapter_failed", "Adapter did not return valid values") from error
    _validate(selection, metadata)
    output = _wire(
        dict(
            version=1,
            envelope=dict(
                workspace_id=str(query.workspace_id),
                process_id=str(query.process_id),
                process_revision=metadata.process.revision,
                pack_binding=reference.model_dump(mode="json"),
                state_revision=query.expected_revision,
                visible_work_ids=[str(identity) for identity in query.visible_work_ids],
                selected_work_id=str(query.selected_work_id) if query.selected_work_id else None,
                scope="explicit_work_metadata_only; counts_are_returned_items_only",
                freshness="one_locked_revision; historical_after_return; reopen_after_change",
                context_scope="selected_work_and_Core_verified_exact_grants_only",
            ),
            answers=_answers(selection, view, context_query),
        )
    )
    if len(output) > query.max_bytes:
        raise PackError("budget_exceeded", "No partial answer")
    return CapabilityResponse(output)


def read_capabilities(
    path: Path,
    query: ProcessQuery,
    caller: LocalAuthorization | None,
    registry: PackRegistry,
    *,
    context_query: ContextQuery | None = None,
    context_caller: LocalAuthorization | None = None,
) -> CapabilityResponse:
    """Read metadata explicitly; selected bytes require their own exact authorization.

    Error envelopes have no data/counts/identities. The byte budget bounds successful
    data; a fixed small failure envelope is still returned when that budget is too low.
    """
    query = ProcessQuery.model_validate(query.model_dump())
    try:
        with process_view(
            path, query, caller, context_query=context_query, context_caller=context_caller
        ) as view:
            # Pack ValueErrors must not cross Core's workspace exception normalization.
            # Final Core revalidation still runs for successful and failed pack answers.
            try:
                response = _render(view, registry, context_query)
            except PackError as error:
                response = _failure(error.code)
        return response
    except MutationError as error:
        denied = error.code in ("permission_denied", "scope", "invalid_work")
        return _failure("permission_denied" if denied else error.code, denied=denied)
    except WorkspaceError:
        return _failure("state_unavailable")
