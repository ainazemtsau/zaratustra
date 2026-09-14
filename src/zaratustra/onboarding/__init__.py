"""Readable public onboarding over existing exact product authority surfaces."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import import_module
from io import BufferedRandom
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from zaratustra.core import (
    LocalAuthorization,
    NextWork,
    ProcessMutationReceipt,
    ProcessState,
    WorkCreationRequest,
    prepare_authorization,
    read_history,
    read_process_state,
)
from zaratustra.entry import PreparedProcessStateRead, prepare_process_state_read
from zaratustra.process_creation import (
    Clarification,
    CreationDraft,
    CreationStatus,
    ProcessCreationError,
    inspect_process_creation,
    parse_process_proposal,
    save_creation_draft,
)
from zaratustra.process_packs import (
    SUPPORTED_CAPABILITIES,
    PackRegistry,
    ProcessDefinition,
    create_later_work,
    definition_sha256,
    registration,
    work_creation_request,
)

MAX_LATER_WORK_PLAN_BYTES = 2_000_000
Text = Annotated[str, Field(strict=True, min_length=1, max_length=4096)]


class OnboardingError(RuntimeError):
    """A public onboarding composition refused without changing Core authority."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


class OnboardingModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ProseClarification(OnboardingModel):
    question: Text
    why_needed: Text
    answer: Text


class LaterWorkInput(OnboardingModel):
    goal: Text
    expected_result: Text
    acceptance: Annotated[tuple[Text, ...], Field(min_length=1, max_length=32)]
    boundaries: Annotated[tuple[Text, ...], Field(min_length=1, max_length=32)]
    budget: Text
    artifact_title: Text


class OnboardingStatus(OnboardingModel):
    version: Literal[1] = 1
    designation: str
    stage: Literal[
        "draft",
        "research_waiting",
        "research_returned",
        "proposal_pending",
        "activation_pending",
        "current_work",
        "no_current_work",
    ]
    next_action: str
    creation: CreationStatus | None
    process: ProcessState | None
    authority: Literal["persisted_stage_or_exact_authorized_core_state"] = (
        "persisted_stage_or_exact_authorized_core_state"
    )


class _LaterWorkPlan(OnboardingModel):
    version: Literal[1] = 1
    designation: str
    definition_sha256: str
    definition: ProcessDefinition
    request: WorkCreationRequest


@dataclass(frozen=True)
class PreparedOnboardingRead:
    catalog: Path
    designation: str
    creation: CreationStatus | None
    process_read: PreparedProcessStateRead | None


@dataclass(frozen=True)
class PreparedLaterWork:
    catalog: Path
    designation: str
    workspace: Path
    plan_path: Path
    request: WorkCreationRequest
    registry: PackRegistry


def _wire(value: BaseModel) -> bytes:
    return (
        json.dumps(
            value.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def save_prose_creation_draft(
    catalog: Path,
    designation: str,
    *,
    process_title: str,
    need: str,
    desired_outcomes: tuple[str, ...],
    constraints: tuple[str, ...],
    created_by: str,
    clarifications: tuple[ProseClarification, ...] = (),
) -> CreationStatus:
    """Persist exact ordinary prose through the existing strict creation draft."""
    try:
        draft = CreationDraft(
            process_title=process_title,
            need=need,
            desired_outcomes=desired_outcomes,
            constraints=constraints,
            declared_capabilities=tuple(sorted(SUPPORTED_CAPABILITIES)),
            clarifications=tuple(
                Clarification(
                    question=row.question,
                    why_needed=row.why_needed,
                    answer=row.answer,
                )
                for row in clarifications
            ),
            created_by=created_by,
        )
    except ValidationError as error:
        raise OnboardingError(
            "invalid_prose", "Prose title, need, outcomes or constraints are invalid"
        ) from error
    return save_creation_draft(catalog, designation, draft.model_dump_json().encode("utf-8"))


def creation_status_text(status: CreationStatus) -> str:
    """Render only the readable facts retained in one creation journal."""
    draft = status.draft
    lines = [
        f"Process: {status.designation}",
        f"Stage: {status.stage}",
        f"Title: {draft.process_title}",
        "Need:",
        draft.need,
        "Desired outcomes:",
        *(f"- {row}" for row in draft.desired_outcomes),
        "Constraints:",
        *(f"- {row}" for row in draft.constraints),
    ]
    if draft.clarifications:
        lines.append("Clarifications:")
        lines.extend(
            f"- {row.question} | why: {row.why_needed} | answer: {row.answer}"
            for row in draft.clarifications
        )
    lines.extend(
        (
            "Installed construction capabilities:",
            *(f"- {row}" for row in draft.declared_capabilities),
        )
    )
    return "\n".join(lines) + "\n"


def prepare_onboarding_read(catalog: Path, designation: str) -> PreparedOnboardingRead:
    """Prepare a persisted-stage read or one exact authoritative Process query."""
    creation: CreationStatus | None
    try:
        creation = inspect_process_creation(catalog, designation)
    except ProcessCreationError as error:
        if error.code != "creation_not_found":
            raise
        creation = None
    if creation is not None and creation.stage != "activated":
        return PreparedOnboardingRead(
            catalog.expanduser().resolve(), creation.designation, creation, None
        )
    prepared = prepare_process_state_read(catalog, designation)
    return PreparedOnboardingRead(
        catalog.expanduser().resolve(), prepared.entry.designation, creation, prepared
    )


def _unfinished_action(stage: str) -> str:
    return {
        "draft": "Answer saved clarifications, then create the manual research request.",
        "research_waiting": "Return the exact manual research response for the saved request.",
        "research_returned": "Author and retain one supported proposal from the exact grounds.",
        "proposal_pending": (
            "Choose the target workspace, review the saved proposal's activation preview, "
            "and exactly confirm activation."
        ),
        "activation_pending": "Review and exactly confirm the saved activation preview.",
    }[stage]


def read_onboarding(
    prepared: PreparedOnboardingRead, caller: LocalAuthorization | None = None
) -> OnboardingStatus:
    """Return a truthful fresh-chat stage without using a retained file as authority."""
    if prepared.process_read is None:
        assert prepared.creation is not None and prepared.creation.stage != "activated"
        return OnboardingStatus(
            designation=prepared.designation,
            stage=prepared.creation.stage,
            next_action=_unfinished_action(prepared.creation.stage),
            creation=prepared.creation,
            process=None,
        )
    process_read = prepared.process_read
    state = read_process_state(process_read.workspace, process_read.query, caller)
    if state.current_work is None:
        stage: Literal["current_work", "no_current_work"] = "no_current_work"
        action = (
            "Leave the Process without current Work or exactly confirm one explicit later Work."
        )
    else:
        stage = "current_work"
        action = "Open the exact current Work; review a safe change only against this revision."
    return OnboardingStatus(
        designation=prepared.designation,
        stage=stage,
        next_action=action,
        creation=prepared.creation,
        process=state,
    )


def onboarding_status_text(status: OnboardingStatus) -> str:
    if status.process is None:
        assert status.creation is not None
        return creation_status_text(status.creation) + f"Next: {status.next_action}\n"
    state = status.process
    current = str(state.current_work.id) if state.current_work is not None else "none"
    lines = [
        f"Process: {status.designation}",
        f"Stage: {status.stage}",
        f"Core revision: {state.state_revision}",
        f"Current Work: {current}",
        f"Saved Process materials: {len(state.materials)}",
    ]
    lines.extend(
        f"- {row.id} | {row.title} | {row.content_sha256} | {row.content_size} bytes"
        for row in state.materials
    )
    lines.append(f"Saved Results: {len(state.results)}")
    lines.extend(
        f"- {row.event.request.operation_id} | source Work {row.event.before.id}"
        for row in state.results
    )
    lines.append(f"Next: {status.next_action}")
    return "\n".join(lines) + "\n"


def _plan_path(catalog: Path, designation: str) -> Path:
    selected = catalog.expanduser().resolve()
    key = hashlib.sha256(designation.strip().casefold().encode("utf-8")).hexdigest()
    return selected.parent / f"{selected.name}.later-works" / f"{key}.json"


def _acquire_file_lock(stream: BufferedRandom) -> None:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
    else:
        fcntl: Any = import_module("fcntl")
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)


def _release_file_lock(stream: BufferedRandom) -> None:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl: Any = import_module("fcntl")
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def _plan_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    with lock.open("a+b") as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"0")
            stream.flush()
        _acquire_file_lock(stream)
        try:
            yield
        finally:
            _release_file_lock(stream)


def _save_plan(path: Path, plan: _LaterWorkPlan) -> None:
    content = _wire(plan)
    if len(content) > MAX_LATER_WORK_PLAN_BYTES:
        raise OnboardingError("plan_too_large", "Later Work plan exceeds its limit")
    temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise OnboardingError("plan_unavailable", "Later Work plan cannot be saved") from error


def _load_plan(path: Path) -> _LaterWorkPlan:
    try:
        content = path.read_bytes()
        if not content or len(content) > MAX_LATER_WORK_PLAN_BYTES:
            raise ValueError("invalid size")
        return _LaterWorkPlan.model_validate_json(content)
    except FileNotFoundError as error:
        raise OnboardingError("plan_not_found", "No later Work plan exists") from error
    except (OSError, ValidationError, ValueError) as error:
        raise OnboardingError("plan_invalid", "Later Work plan is invalid") from error


def prepare_later_work(
    catalog: Path,
    designation: str,
    status: OnboardingStatus,
    definition_content: bytes,
    work: LaterWorkInput,
) -> PreparedLaterWork:
    """Retain one exact no-current Work intent; never refresh unrelated state."""
    if status.designation != designation or status.process is None:
        raise OnboardingError("wrong_target", "Later Work requires this exact Process state")
    definition = parse_process_proposal(definition_content)
    state = status.process
    reference = state.process.pack_binding
    if reference is None:
        raise OnboardingError("binding_missing", "Process has no exact Pack binding")
    digest = definition_sha256(definition)
    if (
        reference.pack_id != f"zaratustra.definition.{digest}"
        or reference.process_type != definition.definition_id
    ):
        raise OnboardingError(
            "binding_mismatch", "Definition does not match the constructed Process binding"
        )
    registry = PackRegistry((registration(reference, definition),))
    registry.resolve(reference)
    prepared_read = prepare_process_state_read(catalog, designation)
    if (
        prepared_read.query.workspace_id != state.workspace_id
        or prepared_read.query.process_id != state.process.id
        or prepared_read.query.expected_revision != state.state_revision
    ):
        raise OnboardingError("stale_state", "Process changed after the authorized read")
    path = _plan_path(catalog, prepared_read.entry.designation)
    with _plan_lock(path):
        try:
            saved = _load_plan(path)
        except OnboardingError as error:
            if error.code != "plan_not_found":
                raise
            if status.stage != "no_current_work" or state.current_work is not None:
                raise OnboardingError(
                    "current_work_present", "A new later Work requires exact no-current state"
                ) from error
            next_work = NextWork(
                work_id=uuid4(),
                artifact_id=uuid4(),
                goal=work.goal,
                expected_result=work.expected_result,
                acceptance=work.acceptance,
                boundaries=work.boundaries,
                budget=work.budget,
                executor_requirements=(f"definition-sha256:{digest}",),
                artifact_title=work.artifact_title,
                authority_scope="work_metadata",
            )
            request = work_creation_request(
                registry,
                reference,
                operation_id=uuid4(),
                workspace_id=state.workspace_id,
                process_id=state.process.id,
                expected_revision=state.state_revision,
                provenance="Explicit confirmed public-onboarding later Work",
                work=next_work,
            )
            saved = _LaterWorkPlan(
                designation=prepared_read.entry.designation,
                definition_sha256=digest,
                definition=definition,
                request=request,
            )
            _save_plan(path, saved)
        expected = saved.request.work.model_copy(
            update={
                "goal": work.goal,
                "expected_result": work.expected_result,
                "acceptance": work.acceptance,
                "boundaries": work.boundaries,
                "budget": work.budget,
                "executor_requirements": (f"definition-sha256:{digest}",),
                "artifact_title": work.artifact_title,
            }
        )
        if (
            saved.designation != prepared_read.entry.designation
            or saved.definition != definition
            or saved.definition_sha256 != digest
            or saved.request.workspace_id != state.workspace_id
            or saved.request.process_id != state.process.id
            or saved.request.pack_binding != reference
            or saved.request.work != expected
        ):
            raise OnboardingError("later_work_collision", "Saved later Work intent differs")
        request = saved.request
        if state.state_revision != request.expected_revision:
            events = tuple(
                row
                for row in read_history(prepared_read.workspace).work_creation_events
                if row.request.operation_id == request.operation_id
            )
            if len(events) != 1 or events[0].request != request:
                raise OnboardingError("stale_state", "Process changed before later Work commit")
            if state.current_work is not None and state.current_work.id != request.work.work_id:
                raise OnboardingError("later_work_collision", "Another current Work is present")
            request = request.model_copy(update={"expected_revision": state.state_revision})
        elif state.current_work is not None:
            raise OnboardingError("current_work_present", "A current Work is already present")
    return PreparedLaterWork(
        catalog=catalog.expanduser().resolve(),
        designation=prepared_read.entry.designation,
        workspace=prepared_read.workspace,
        plan_path=path,
        request=request,
        registry=registry,
    )


def execute_later_work(
    prepared: PreparedLaterWork, caller: LocalAuthorization | None
) -> ProcessMutationReceipt:
    """Revalidate the retained plan and delegate its one effect to Core."""
    with _plan_lock(prepared.plan_path):
        saved = _load_plan(prepared.plan_path)
        if (
            saved.designation != prepared.designation
            or saved.definition_sha256 != definition_sha256(saved.definition)
            or saved.request.operation_id != prepared.request.operation_id
            or saved.request.model_copy(
                update={"expected_revision": prepared.request.expected_revision}
            )
            != prepared.request
        ):
            raise OnboardingError("later_work_collision", "Prepared later Work changed")
        prompt = prepare_authorization(prepared.workspace, prepared.request)
        if (
            caller is None
            or caller.confirmation.workspace_path != prompt.workspace_path
            or caller.confirmation.request_sha256 != prompt.request_sha256
        ):
            raise OnboardingError("permission_denied", "Exact later Work was not confirmed")
        return create_later_work(
            prepared.workspace,
            prepared.request,
            caller,
            prepared.registry,
        )


__all__ = [
    "LaterWorkInput",
    "OnboardingError",
    "OnboardingStatus",
    "PreparedLaterWork",
    "PreparedOnboardingRead",
    "ProseClarification",
    "creation_status_text",
    "execute_later_work",
    "onboarding_status_text",
    "prepare_later_work",
    "prepare_onboarding_read",
    "read_onboarding",
    "save_prose_creation_draft",
]
