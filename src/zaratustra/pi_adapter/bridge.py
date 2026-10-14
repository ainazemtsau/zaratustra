"""Loopback JSON bridge from ordinary Pi to the independent Core."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from zaratustra.foundation import (
    AcceptWorkRequest,
    ActivitySetupRequest,
    ActivityState,
    AnswerWaitRequest,
    ApplyCandidateRequest,
    ArtifactRef,
    ChangeDecisionState,
    ChoiceState,
    ClaimState,
    CloseWorkRequest,
    ConfirmObligationRequest,
    ConfirmProgramInstallRequest,
    ContextState,
    CreateActivityRequest,
    CreateArtifactRequest,
    CreateBindingVersionRequest,
    CreateCompositeWorkRequest,
    CreateDecisionRequest,
    CreateDevelopmentRequest,
    CreateGrantRequest,
    CreateKnowledgeRequest,
    CreateMethodVersionRequest,
    CreateResourceRequest,
    CreateWorkRequest,
    DecisionState,
    DeleteDevelopmentRequest,
    DeleteKnowledgeRequest,
    DomainRequest,
    FireBindingRequest,
    FoundationError,
    IssueChildWorkRequest,
    KnowledgeRef,
    LinkWorkOutputRequest,
    LocalAuthority,
    MemorySelector,
    MemoryViewState,
    OpenWaitRequest,
    OutputValidationError,
    ProvenanceRef,
    PublishAttemptOutputRequest,
    RecordChangeOutcomeRequest,
    RecordContextDeliveryRequest,
    ReorganizeActivitiesRequest,
    ResolveBindingOfferRequest,
    ResolveObligationApplicabilityRequest,
    ResourceState,
    RestoreCandidateRequest,
    RevalidateResultRequest,
    ReviseDecisionRequest,
    ReviseDevelopmentRequest,
    ReviseKnowledgeRequest,
    ReviseWorkPlanRequest,
    SetBindingStateRequest,
    SleepRemainder,
    SleepState,
    SourceState,
    StartAttemptRequest,
    StopAttemptRequest,
    StopCandidateRequest,
    WaiveObligationRequest,
    activity_setup_memory,
    apply_operation,
    export_memory_selection,
    initial_sleep_method,
    initial_sleep_ref,
    inspect_space,
    list_activity_setups,
    list_binding_methods,
    list_binding_offers,
    list_bindings,
    list_change_applications,
    list_development,
    list_knowledge,
    list_sleep_sources,
    memory_catalog,
    memory_history,
    memory_required_refs,
    open_knowledge,
    open_memory_selection,
    output_publication_contracts,
    prepare_memory_cache,
    read_activity,
    read_activity_setup,
    read_artifact,
    read_change_application,
    read_current_rights,
    read_decision,
    read_development,
    read_execution,
    read_execution_events,
    read_knowledge,
    read_knowledge_neighbors,
    read_memory_batch,
    read_method_version,
    read_receipt,
    read_setup_stage,
    read_sleep_for_work,
    read_sleep_usage,
    read_space,
    read_work,
    read_work_plan,
    read_work_status,
    read_workflow_node_for_work,
    search_knowledge,
    sleep_work_template,
    upgrade_binding_space,
    upgrade_change_package_space,
    upgrade_child_execution_space,
    upgrade_composition_space,
    upgrade_continuation_space,
    upgrade_development_space,
    upgrade_knowledge_space,
    upgrade_parent_execution_space,
    upgrade_plan_revision_space,
)
from zaratustra.integrations import installed_integrations
from zaratustra.workspace import (
    GitPreparation,
    LaunchConfig,
    ModelPreference,
    Project,
    defer_git,
    git_status,
    prepare_git,
    publish_git,
    read_config,
    reconcile_git,
    register_project,
    remember_model,
    select_work_project,
    workspace_info,
)

from .manual_exchange import ManualExchange

PROTOCOL_VERSION = 1
MAX_BODY_BYTES = 9 * 1024 * 1024
REQUEST_ADAPTER: TypeAdapter[DomainRequest] = TypeAdapter(DomainRequest)
BINDING_INTENTS: dict[str, type[BaseModel]] = {
    "create_method_version": CreateMethodVersionRequest,
    "create_binding_version": CreateBindingVersionRequest,
    "set_binding_state": SetBindingStateRequest,
    "fire_binding": FireBindingRequest,
    "resolve_binding_offer": ResolveBindingOfferRequest,
}
KNOWLEDGE_INTENTS: dict[str, type[BaseModel]] = {
    "create_knowledge": CreateKnowledgeRequest,
    "revise_knowledge": ReviseKnowledgeRequest,
    "delete_knowledge": DeleteKnowledgeRequest,
    "create_grant": CreateGrantRequest,
}
DEVELOPMENT_INTENTS: dict[str, type[BaseModel]] = {
    "create_activity": CreateActivityRequest,
    "reorganize_activities": ReorganizeActivitiesRequest,
    "create_work": CreateWorkRequest,
    "create_artifact": CreateArtifactRequest,
    "create_method_version": CreateMethodVersionRequest,
    "create_resource": CreateResourceRequest,
    "revise_work_plan": ReviseWorkPlanRequest,
    "issue_child_work": IssueChildWorkRequest,
    "link_work_output": LinkWorkOutputRequest,
    "accept_work": AcceptWorkRequest,
    "close_work": CloseWorkRequest,
    "confirm_obligation": ConfirmObligationRequest,
    "resolve_obligation_applicability": ResolveObligationApplicabilityRequest,
    "waive_obligation": WaiveObligationRequest,
    "revalidate_result": RevalidateResultRequest,
    "create_development": CreateDevelopmentRequest,
    "revise_development": ReviseDevelopmentRequest,
    "delete_development": DeleteDevelopmentRequest,
    "apply_candidate": ApplyCandidateRequest,
    "confirm_program_install": ConfirmProgramInstallRequest,
    "stop_candidate": StopCandidateRequest,
    "restore_candidate": RestoreCandidateRequest,
    "record_change_outcome": RecordChangeOutcomeRequest,
    "create_decision": CreateDecisionRequest,
    "revise_decision": ReviseDecisionRequest,
    "create_composite_work": CreateCompositeWorkRequest,
}


@dataclass(frozen=True)
class Selection:
    activity_id: UUID
    work_id: UUID


class ProviderPreflightRefusal(BaseModel):
    """Trusted native transport refusal, never inferred from Pi/model prose."""

    model_config = {"extra": "forbid", "frozen": True}
    protocol: Literal["zara.pi.preflight.v1"] = "zara.pi.preflight.v1"
    attempt_id: UUID
    session_id: UUID
    boundary: Literal[
        "context-prepare",
        "context-prepared",
        "context-sent",
        "prepare_invocation",
        "admit_invocation",
        "send_invocation",
    ]
    invocation_id: UUID | None = None
    code: str = Field(min_length=1, max_length=100)
    detail: str = Field(min_length=1)
    diagnostic: KnowledgeRef | None = None


class Bridge:
    """One trusted local process and one selected Core space."""

    def __init__(
        self,
        path: Path,
        authority: LocalAuthority,
        workspace: Path,
        limit_units: int | None = None,
        *,
        assigned_attempt_id: UUID | None = None,
        assigned_session_id: UUID | None = None,
        deliver_answer: Callable[[UUID], object] | None = None,
        context_max_bytes: int | None = None,
        free_conversation_limit_units: int | None = None,
        workspace_config: Path | None = None,
        restricted_core_reads: bool = False,
    ) -> None:
        self.path = path.resolve()
        self.authority = authority
        self.workspace = workspace.resolve()
        self.workspace_config = workspace_config
        self.restricted_core_reads = restricted_core_reads
        if not self.workspace.is_dir() or (limit_units is not None and limit_units < 1):
            raise FoundationError("resource_unavailable", "Choose an existing directory and limit")
        self.limit_units = limit_units
        self.trial_total_send_limit: int | None
        trial_limit = os.environ.get("ZARA_TRIAL_MAX_TOTAL_SENDS")
        if trial_limit is not None:
            try:
                self.trial_total_send_limit = int(trial_limit)
            except ValueError as error:
                raise FoundationError(
                    "invalid_request", "Trial send limit must be positive"
                ) from error
            if self.trial_total_send_limit < 1:
                raise FoundationError("invalid_request", "Trial send limit must be positive")
        else:
            self.trial_total_send_limit = None
        if free_conversation_limit_units is not None and free_conversation_limit_units < 1:
            raise FoundationError("invalid_request", "Free conversation budget must be positive")
        self.free_conversation_limit_units = free_conversation_limit_units
        if context_max_bytes is not None and context_max_bytes < 1:
            raise FoundationError("invalid_request", "Context byte limit must be finite")
        self.context_max_bytes = context_max_bytes
        if (assigned_attempt_id is None) != (assigned_session_id is None):
            raise FoundationError("invalid_request", "Assigned attempt and session must be paired")
        self.assigned_attempt_id = assigned_attempt_id
        self.assigned_session_id = assigned_session_id
        self.deliver_answer = deliver_answer
        self.token = secrets.token_urlsafe(48)
        self.sessions: dict[UUID, Selection | None] = {}
        self.last_sources: dict[UUID, KnowledgeRef] = {}
        # Receipt is not consumption. The native request binds its actually
        # delivered owner entries before preparing context or executing tools.
        self.request_sources: dict[UUID, tuple[KnowledgeRef, ...]] = {}
        self.request_origins: dict[UUID, str] = {}
        self.conversation_hosts: dict[UUID, dict[str, str]] = {}
        self.process_observations: dict[tuple[UUID, str], Any] = {}
        self.response_only: dict[UUID, dict[str, Any]] = {}
        self.conversation_actions: dict[UUID, Any] = {}
        self.recovery_obstacles: dict[UUID, UUID] = {}
        self.exposed_refs: dict[UUID, set[KnowledgeRef]] = {}
        self.selected_file_refs: dict[UUID, set[KnowledgeRef]] = {}
        self.memory_rules: dict[UUID, dict[str, tuple[MemorySelector, ...]]] = {}
        self.memory_snapshots: dict[UUID, set[KnowledgeRef]] = {}
        self.accept_previews: dict[UUID, tuple[UUID, int, UUID]] = {}
        self.accept_results: dict[UUID, dict[str, object]] = {}
        self.git_previews: dict[UUID, UUID] = {}
        self.lock = threading.Lock()
        self.provider_preflight_refusal: ProviderPreflightRefusal | None = None
        self.workflow_executor_pool: Any = None
        self.setup_controller: Any = None
        self.procedure_controller: Any = None
        self.workflow_controller: Any = None

    def capture_provider_refusal(
        self,
        session_id: UUID,
        endpoint: str,
        raw: dict[str, Any],
        error: FoundationError,
    ) -> None:
        """Capture only an explicitly marked native preflight of this assignment."""
        if (
            raw.get("provider_preflight") is not True
            or self.assigned_attempt_id is None
            or session_id != self.assigned_session_id
        ):
            return
        boundary: Any = None
        invocation: Any = raw.get("invocation_id")
        if endpoint == "/v1/context-prepare":
            boundary = "context-prepare"
        elif endpoint == "/v1/context-delivery" and raw.get("stage") in ("prepared", "sent"):
            boundary = "context-" + str(raw["stage"])
        elif endpoint == "/v1/operation":
            operation = raw.get("request")
            if (
                isinstance(operation, dict)
                and operation.get("kind")
                in ("prepare_invocation", "admit_invocation", "send_invocation")
                and str(operation.get("attempt_id")) == str(self.assigned_attempt_id)
                and str(operation.get("session_id")) == str(session_id)
            ):
                boundary = operation["kind"]
                invocation = operation.get("invocation_id")
        if boundary is None:
            return
        try:
            refusal = ProviderPreflightRefusal(
                attempt_id=self.assigned_attempt_id,
                session_id=session_id,
                boundary=boundary,
                invocation_id=UUID(str(invocation)) if invocation is not None else None,
                code=error.code,
                detail=error.detail,
            )
        except (ValueError, ValidationError):
            return
        with self.lock:
            if (
                self.sessions.get(session_id) is not None
                and self.provider_preflight_refusal is None
            ):
                self.provider_preflight_refusal = refusal

    def complete_provider_preflight(
        self, session_id: UUID, endpoint: str, raw: dict[str, Any]
    ) -> None:
        """A recovered exact preflight receipt is not a terminal refusal."""
        if raw.get("provider_preflight") is not True or session_id != self.assigned_session_id:
            return
        with self.lock:
            refusal = self.provider_preflight_refusal
            if refusal is None:
                return
            if (endpoint == "/v1/context-prepare" and refusal.boundary == "context-prepare") or (
                endpoint == "/v1/context-delivery"
                and raw.get("stage") == "sent"
                and str(raw.get("invocation_id")) == str(refusal.invocation_id)
            ):
                self.provider_preflight_refusal = None

    def model_selection(self, session_id: UUID, raw: dict[str, Any]) -> dict[str, Any]:
        """The extension reports its current selection before future node dispatch."""
        self._session(session_id)
        if self.assigned_attempt_id is not None:
            return {"pinned": True}
        selection = dict(raw["model"])
        config = self._workspace_configuration()
        if config is not None:
            preference = ModelPreference(
                provider_profile=config.provider_profile,
                provider_id=str(selection.get("provider", "")),
                model_id=str(selection.get("id", "")),
                thinking=selection.get("thinking"),
            )
            assert self.workspace_config is not None
            try:
                if (preference.provider_profile, preference.provider_id) != (
                    config.provider_profile,
                    config.provider_id,
                ):
                    raise ValueError("Selected model must use the configured provider and profile")
                if raw.get("persist", True):
                    remember_model(self.workspace_config, preference)
            except ValueError as error:
                raise FoundationError("unsupported_provider", str(error)) from error
        for controller in (
            self.setup_controller,
            self.procedure_controller,
            self.workflow_controller,
        ):
            if controller is not None and hasattr(controller, "update_model"):
                controller.update_model(selection)
        return {"model": selection}

    def _exposed_sources(self, session_id: UUID, raw: dict[str, Any]) -> tuple[KnowledgeRef, ...]:
        supplied = tuple(KnowledgeRef.model_validate(ref) for ref in raw.get("source_refs", []))
        permitted = self.exposed_refs.get(session_id, set()) | self.selected_file_refs.get(
            session_id, set()
        )
        if any(ref not in permitted for ref in supplied):
            raise FoundationError(
                "permission_denied", "Select only exact actually exposed authorized memory"
            )
        return tuple(dict.fromkeys(supplied))

    def _fresh_user_source(
        self, session_id: UUID, selected_ref: dict[str, Any] | None = None
    ) -> tuple[KnowledgeRef, str]:
        if session_id in self.response_only:
            raise FoundationError(
                "permission_denied", "Response repair cannot supply an owner answer"
            )
        original = (
            KnowledgeRef.model_validate(selected_ref)
            if selected_ref
            else self._request_source(session_id)
        )
        if read_space(self.path).schema_version >= 17 and (
            self.request_origins.get(session_id) != "owner"
            or original not in self.request_sources.get(session_id, ())
        ):
            raise FoundationError("incomplete_context", "Choose an exact delivered owner Source")
        if original is None:
            raise FoundationError("incomplete_context", "No actual user message to retain")
        message = read_knowledge(
            self.path, original.record_id, self.authority, revision=original.revision
        )
        if (
            not isinstance(message.state, SourceState)
            or message.state.channel != "conversation_user"
            or message.state.content is None
            or message.state.sender != self.authority.actor
        ):
            raise FoundationError(
                "permission_denied", "Answer must come from a fresh received user message"
            )
        return original, message.state.content.decode("utf-8")

    def _request_source(self, session_id: UUID) -> KnowledgeRef | None:
        if read_space(self.path).schema_version < 17:
            return self.last_sources.get(session_id)
        sources = self.request_sources.get(session_id, ())
        if self.request_origins.get(session_id) != "owner" or len(sources) != 1:
            return None
        return sources[0]

    def _require_model_effect(self, session_id: UUID) -> None:
        if session_id in self.response_only:
            raise FoundationError("permission_denied", "Response repair has read-only authority")
        if (
            self.assigned_attempt_id is None
            and read_space(self.path).schema_version >= 17
            and (self.request_origins.get(session_id) in ("host", "history", "unsupported"))
        ):
            raise FoundationError(
                "permission_denied", "Host/history conversation has read-only authority"
            )

    def _answer_temporal_guard(
        self, source: KnowledgeRef, *, kind: str, subject: UUID, wait: UUID | None = None
    ) -> None:
        if read_space(self.path).schema_version < 17:
            return
        from zaratustra.foundation import validate_conversation_answer

        validate_conversation_answer(
            self.path,
            self.authority,
            source,
            kind=cast(Any, kind),
            subject_id=subject,
            wait_id=wait,
        )

    def bind_request_origin(self, session_id: UUID, raw: dict[str, Any]) -> dict[str, object]:
        """Trusted native adapter binds consumed sources, never arbitrary model text."""
        self._session(session_id)
        refs = tuple(KnowledgeRef.model_validate(item) for item in raw.get("sources", ()))
        origin = str(raw.get("origin", "unsupported"))
        if origin not in ("owner", "host", "history", "unsupported"):
            raise FoundationError("invalid_request", "Unknown native request origin")
        for ref in refs:
            item = read_knowledge(self.path, ref.record_id, self.authority, revision=ref.revision)
            if not isinstance(item.state, SourceState) or item.state.channel != "conversation_user":
                raise FoundationError("invalid_request", "Native origin must address a user Source")
            if origin == "owner" and (
                item.state.sender != self.authority.actor
                or item.state.conversation_id != str(session_id)
            ):
                raise FoundationError("permission_denied", "Origin is not a delivered owner entry")
        if origin != "owner" and refs:
            raise FoundationError("invalid_request", "Host origin has no fresh owner answer")
        with self.lock:
            self.request_origins[session_id] = origin
            self.request_sources[session_id] = refs
            if origin == "owner" and raw.get("fresh_owner") is True:
                self.response_only.pop(session_id, None)
        return {"origin": origin, "sources": [ref.model_dump(mode="json") for ref in refs]}

    def process_boundary(self, session_id: UUID, raw: dict[str, Any]) -> dict[str, Any]:
        from .boundary import process_boundary

        return process_boundary(self, session_id, raw)

    def native_response_mode(self, session_id: UUID, raw: dict[str, Any]) -> dict[str, Any]:
        """Native-only exact terminal validation and response-only admission."""
        from zaratustra.foundation import read_terminal_response

        self._session(session_id)
        if self.assigned_attempt_id is not None:
            raise FoundationError("permission_denied", "Assigned nodes cannot repair owner replies")
        source = KnowledgeRef.model_validate(raw["assistant_source"])
        manifest = KnowledgeRef.model_validate(raw["manifest"])
        view = read_terminal_response(
            self.path,
            source,
            self.authority,
            session_id=session_id,
            invocation_id=UUID(str(raw["invocation_id"])),
            manifest=manifest,
            assistant_entry_id=str(raw["assistant_entry_id"]),
        )
        result = view.model_dump(mode="json")
        if raw["mode"] == "terminal":
            return result
        host = self.conversation_hosts.get(session_id)
        if host is None or int(host.get("generation", -1)) != int(raw["generation"]):
            raise FoundationError("stale_session", "Reply repair belongs to another native branch")
        if raw.get("enabled") is not True:
            raise FoundationError("permission_denied", "Only a fresh owner input ends reply repair")
        if view.outcome != "empty" or view.diagnostics:
            raise FoundationError(
                "response_not_repairable", "Only an accounted empty stop can repair"
            )
        owner_sources = tuple(KnowledgeRef.model_validate(ref) for ref in raw["owner_sources"])
        if (
            not owner_sources
            or len(set(owner_sources)) != len(owner_sources)
            or self.request_origins.get(session_id) != "owner"
            or owner_sources != self.request_sources.get(session_id, ())
        ):
            raise FoundationError(
                "incomplete_context", "Reply repair needs its delivered owner roots"
            )
        original = read_knowledge(
            self.path, manifest.record_id, self.authority, revision=manifest.revision
        ).state
        if not isinstance(original, ContextState) or any(
            ref not in original.mandatory for ref in owner_sources
        ):
            raise FoundationError(
                "incomplete_context", "Owner roots were absent from the producing context"
            )
        for reference in owner_sources:
            item = read_knowledge(
                self.path, reference.record_id, self.authority, revision=reference.revision
            ).state
            if (
                reference.start is not None
                or reference.end is not None
                or not isinstance(item, SourceState)
                or item.channel != "conversation_user"
                or item.sender != self.authority.actor
                or item.conversation_id != str(session_id)
                or item.content is None
            ):
                raise FoundationError(
                    "permission_denied", "Reply repair root is not an owner original"
                )
        with self.lock:
            self.response_only[session_id] = {
                "assistant_source": source,
                "manifest": manifest,
                "invocation_id": view.invocation_id,
                "assistant_entry_id": view.assistant_entry_id,
                "owner_sources": owner_sources,
                "generation": int(raw["generation"]),
                "branch_id": host["branch_id"],
            }
        return {"enabled": True, "terminal": result}

    def _setup_request_source(self, session_id: UUID, raw: dict[str, Any]) -> KnowledgeRef | None:
        """Select an original received request; never turn it into an answer."""
        original = (
            KnowledgeRef.model_validate(raw["request_source"])
            if raw.get("request_source") is not None
            else self._request_source(session_id)
        )
        if original is None:
            return None
        if read_space(self.path).schema_version >= 17 and (
            self.request_origins.get(session_id) != "owner"
            or original not in self.request_sources.get(session_id, ())
        ):
            raise FoundationError("permission_denied", "Request must use a delivered owner Source")
        if original != self._request_source(session_id) and original not in self.exposed_refs.get(
            session_id, set()
        ):
            raise FoundationError("permission_denied", "Original request must be exposed")
        record = read_knowledge(
            self.path, original.record_id, self.authority, revision=original.revision
        ).state
        if (
            not isinstance(record, SourceState)
            or record.channel != "conversation_user"
            or record.sender != self.authority.actor
            or record.content is None
        ):
            raise FoundationError(
                "invalid_request", "Request anchor must be an original user Source"
            )
        return original

    def _setup_status(self, identifier: UUID) -> dict[str, Any]:
        """Derive local execution and permitted continuation from current Core records."""
        current = read_activity_setup(self.path, identifier, self.authority)
        state = current.state
        usage: list[dict[str, Any]] = []
        current_snapshot = None
        stage = state.stages[-1] if state.stages else None
        for item in state.stages:
            snapshot = read_execution(self.path, item.work_id, self.authority)
            usage.extend(invocation.model_dump(mode="json") for invocation in snapshot.invocations)
            if stage is not None and item.work_id == stage.work_id:
                current_snapshot = snapshot
        status = "idle"
        unresolved: list[str] = []
        running = False
        if stage is not None and not stage.retired and stage.output is None:
            assert current_snapshot is not None
            assignments = current_snapshot.assignments
            running = any(
                item.status in ("assigned", "waiting", "ready", "stop_requested")
                for item in assignments
            )
            unresolved = [
                str(item.invocation_id)
                for item in current_snapshot.invocations
                if item.status in ("admitted", "sent", "unknown")
            ]
            if any(item.status == "stop_requested" for item in assignments):
                status = "stopping"
            elif running:
                status = "active"
            elif unresolved or any(item.status == "unknown" for item in assignments):
                status = "unknown"
            else:
                status = "stopped"
        closed = state.phase in ("ready", "cancelled")
        pending_outcome = current_snapshot is not None and (
            any(
                item.status in ("admitted", "sent", "unknown")
                for item in current_snapshot.invocations
            )
            or any(item.status == "unknown" for item in current_snapshot.assignments)
        )
        can_attach = not closed and (
            state.phase == "paused"
            and pending_outcome
            or not running
            and (
                stage is None
                or stage.output is not None
                or stage.retired
                or state.phase == "paused"
            )
        )
        can_retry = (
            not closed
            and state.phase == "paused"
            and state.question is None
            and stage is not None
            and current_snapshot is not None
            and status == "unknown"
            and stage.input_version != state.input_version
            and stage.result_protocol == "setup_json"
            and not any(item.status == "active" for item in current_snapshot.attempts)
            and all(item.status == "stopped" for item in current_snapshot.assignments)
            and not any(
                item.status in ("admitted", "sent") for item in current_snapshot.invocations
            )
        )
        can_resume = (
            not closed
            and not running
            and status != "unknown"
            and state.question is None
            and state.phase
            in (
                "paused",
                "needs_attention",
                "collecting",
                "drafting",
                "correcting",
                "reviewing",
                "activating",
            )
        )
        next_action = (
            "use_activity"
            if state.phase == "ready"
            else "none"
            if closed
            else "answer"
            if state.question
            and (
                state.phase == "needs_input"
                or state.phase == "paused"
                and (pending_outcome or not running)
            )
            else "wait_for_stop"
            if status == "stopping"
            else "wait"
            if status == "active"
            else "retry_new_stage"
            if can_retry
            else "inspect_unknown"
            if status == "unknown"
            else "answer"
            if state.question
            else "resume"
            if state.phase == "paused" and can_resume
            else "submit"
            if state.phase == "collecting"
            else "inspect"
            if state.phase == "needs_attention"
            else "resume"
        )
        return {
            **current.model_dump(mode="json"),
            "invocations": usage,
            "execution": {
                "status": status,
                "stage_work_id": str(stage.work_id) if stage else None,
                "can_attach_sources": can_attach,
                "can_resume": can_resume,
                "can_retry": can_retry,
                "next_action": next_action,
                "blocking_unknown_invocations": unresolved,
                "unknown_invocations": [
                    item["invocation_id"] for item in usage if item["status"] == "unknown"
                ],
            },
        }

    def workflow(self, session_id: UUID, raw: dict[str, Any]) -> dict[str, Any]:
        if raw.get("mode", "status") not in (
            "contract",
            "runs",
            "catalog",
            "read",
            "interaction",
            "method_tasks",
            "read_packet",
            "status",
            "explain",
        ):
            self._require_model_effect(session_id)
        """Public conversation actions; dispatch/validation remain host-owned."""
        from zaratustra.foundation import (
            WorkflowDefinition,
            WorkflowRef,
            WorkflowRequest,
            list_workflow_runs,
            list_workflows,
            read_workflow,
            read_workflow_method_tasks,
            read_workflow_packet,
            read_workflow_run,
            read_workflow_wait,
        )

        from .workflows import workflow_view

        self._session(session_id)
        action = str(raw.get("mode", "status"))
        if action == "contract":
            return {
                "definition_schema": WorkflowDefinition.model_json_schema(),
                "request_schema": WorkflowRequest.model_json_schema(),
            }
        if action == "runs":
            if self.assigned_attempt_id is not None:
                raise FoundationError("permission_denied", "Assigned nodes cannot enumerate runs")
            runs = list_workflow_runs(
                self.path,
                self.authority,
                after=UUID(str(raw["after"])) if raw.get("after") else None,
                limit=int(raw.get("limit", 25)),
                pending_only=bool(raw.get("pending_only", False)),
            )
            return {
                "items": [
                    workflow_view(self.path, run.root_work_id, self.authority) for run in runs
                ],
                "after": str(runs[-1].root_work_id) if runs else None,
            }
        if action == "catalog":
            after = raw.get("after")
            refs = list_workflows(
                self.path,
                self.authority,
                after=(str(after["workflow_id"]), int(after["version"])) if after else None,
                limit=int(raw.get("limit", 25)),
            )
            return {
                "items": [
                    {
                        "workflow": ref.model_dump(mode="json"),
                        "description": read_workflow(self.path, ref, self.authority).model_dump(
                            mode="json", include={"title", "purpose"}
                        ),
                    }
                    for ref in refs
                ],
                "after": refs[-1].model_dump(mode="json") if refs else None,
            }
        if action == "read":
            ref = WorkflowRef.model_validate(raw["workflow"])
            return {
                "workflow": ref.model_dump(mode="json"),
                "definition": read_workflow(self.path, ref, self.authority).model_dump(mode="json"),
            }
        root_id = UUID(str(raw["root_work_id"])) if raw.get("root_work_id") else None
        if action == "interaction":
            if root_id is None:
                raise FoundationError("invalid_request", "Name the workflow root Work")
            if self.assigned_attempt_id is not None:
                from .workflows import workflow_work_ids

                if self._selection(session_id).work_id not in workflow_work_ids(
                    self.path, root_id, self.authority
                ):
                    raise FoundationError("wrong_scope", "Read only the assigned workflow")
            return read_workflow_wait(
                self.path, root_id, UUID(str(raw["wait_id"])), self.authority
            ).model_dump(mode="json")
        if action == "method_tasks":
            from .workflows import workflow_work_ids

            if root_id is None:
                raise FoundationError("invalid_request", "Name the workflow root Work")
            work_id = UUID(str(raw["work_id"]))
            if work_id not in workflow_work_ids(self.path, root_id, self.authority):
                raise FoundationError("wrong_scope", "Method Work is not in this workflow")
            if self.assigned_attempt_id is not None and self._selection(session_id).work_id not in (
                workflow_work_ids(self.path, root_id, self.authority)
            ):
                raise FoundationError("wrong_scope", "Read only the assigned workflow")
            return read_workflow_method_tasks(self.path, work_id, self.authority)
        if action == "read_packet":
            if raw.get("setup_id"):
                return self.activity_setup(session_id, {**raw, "action": "read_packet"})
            if root_id is None:
                raise FoundationError("invalid_request", "Name the workflow root Work")
            if self.assigned_attempt_id is not None:
                from .workflows import workflow_work_ids

                selected = self._selection(session_id)
                if selected.work_id not in workflow_work_ids(self.path, root_id, self.authority):
                    raise FoundationError("wrong_scope", "Read only the assigned workflow")
            packet_ref = ArtifactRef.model_validate(raw["reference"])
            content = read_workflow_packet(self.path, root_id, packet_ref, self.authority)
            offset, maximum = int(raw.get("offset", 0)), int(raw.get("max_bytes", 16384))
            if offset < 0 or offset > len(content) or not 1 <= maximum <= 65536:
                raise FoundationError("invalid_request", "Use a bounded workflow window")
            end = min(offset + maximum, len(content))
            while end > offset:
                try:
                    content[offset:end].decode("utf-8")
                    break
                except UnicodeDecodeError:
                    end -= 1
            if end == offset and offset < len(content):
                raise FoundationError("invalid_request", "Window cannot hold a UTF-8 character")
            return {
                "reference": packet_ref.model_dump(mode="json"),
                "offset": offset,
                "total_bytes": len(content),
                "content_base64": base64.b64encode(content[offset:end]).decode(),
                "content_text": content[offset:end].decode("utf-8"),
                "next_offset": end if end < len(content) else None,
            }
        if action in ("status", "explain"):
            if root_id is None:
                raise FoundationError("invalid_request", "Name the workflow root Work")
            from .activity_setup import _observe

            status_root = root_id

            def current_status() -> dict[str, Any]:
                if self.assigned_attempt_id is not None:
                    from .workflows import workflow_work_ids

                    selected = self._selection(session_id)
                    if selected.work_id not in workflow_work_ids(
                        self.path, status_root, self.authority
                    ):
                        raise FoundationError("wrong_scope", "Read only the assigned workflow")
                return workflow_view(self.path, status_root, self.authority)

            return cast(dict[str, Any], _observe(current_status))
        if self.assigned_attempt_id is not None:
            raise FoundationError(
                "permission_denied", "Assigned nodes may only read workflow state"
            )
        if action not in (
            "propose",
            "start",
            "answer",
            "correct_answer",
            "retry",
            "pause",
            "resume",
            "cancel",
            "migrate",
        ):
            raise FoundationError(
                "permission_denied", "Internal workflow transitions are host-owned"
            )
        operation_key = str(raw["operation_key"])
        operation_id = uuid5(session_id, "workflow:" + operation_key)
        try:
            earlier = read_receipt(self.path, operation_id, self.authority)
        except FoundationError as error:
            if error.code != "not_found":
                raise
        else:
            if action == "propose":
                return {
                    "receipt": earlier.model_dump(mode="json"),
                    "next_action": (
                        "Validate and apply a scoped workflow Candidate; proposal is not executable"
                    ),
                }
            if "root_work_id" not in earlier.result and action == "answer" and root_id is not None:
                if str(earlier.result.get("wait_id")) != str(raw["wait_id"]):
                    raise FoundationError(
                        "operation_conflict", "Call already answered another question"
                    )
                return workflow_view(self.path, root_id, self.authority)
            recorded_root = UUID(str(earlier.result["root_work_id"]))
            if root_id is not None and root_id != recorded_root:
                raise FoundationError(
                    "operation_conflict", "Call already addressed another workflow"
                )
            return workflow_view(self.path, recorded_root, self.authority)
        fields: dict[str, Any] = {}
        if action in ("pause", "cancel", "migrate", "correct_answer") and (
            self.workflow_controller is not None and self.workflow_controller.active == root_id
        ):
            self.workflow_controller.request_pause(root_id)
        if action == "propose":
            fields.update(
                workflow_id=UUID(str(raw.get("workflow_id", uuid5(operation_id, "definition")))),
                version=int(raw.get("version", 1)),
                definition=raw["definition"],
            )
        elif action == "start":
            root_id = root_id or uuid5(operation_id, "root")
            original, _ = self._fresh_user_source(session_id, raw.get("answer_source"))
            fields.update(
                root_work_id=root_id,
                workflow=raw["workflow"],
                activity_id=UUID(str(raw["activity_id"])),
                source_refs=tuple(
                    dict.fromkeys((original,) + self._exposed_sources(session_id, raw))
                ),
                inputs=raw.get("inputs", ()),
            )
        else:
            if root_id is None:
                raise FoundationError("invalid_request", "Name the workflow root Work")
            current = read_workflow_run(self.path, root_id, self.authority)
            fields.update(root_work_id=root_id, expected_revision=current.revision)
            if action == "answer":
                original, _ = self._fresh_user_source(session_id, raw.get("answer_source"))
                wait_id = UUID(str(raw["wait_id"]))
                self._answer_temporal_guard(
                    original, kind="workflow", subject=root_id, wait=wait_id
                )
                wait = next((wait for wait in current.waits if wait.wait_id == wait_id), None)
                if wait is None:
                    raise FoundationError("stale_wait", "Named question is no longer open")
                fields.update(
                    wait_id=wait_id,
                    expected_wait_revision=int(raw.get("expected_wait_revision", wait.revision)),
                    answer=original,
                )
            elif action == "correct_answer":
                original, _ = self._fresh_user_source(session_id, raw.get("answer_source"))
                fields.update(
                    wait_id=UUID(str(raw["wait_id"])),
                    expected_wait_revision=int(raw["expected_wait_revision"]),
                    answer=original,
                )
            elif action == "retry":
                original, _ = self._fresh_user_source(session_id, raw.get("answer_source"))
                fields.update(node_key=str(raw["node_key"]), answer=original)
            elif action == "migrate":
                fields.update(
                    workflow=raw["workflow"],
                    node_mapping=raw.get("node_mapping", {}),
                    node_dispositions=raw["node_dispositions"],
                )
        receipt = apply_operation(
            self.path,
            WorkflowRequest.model_validate(
                {
                    "operation_id": operation_id,
                    "space_id": self.authority.space_id,
                    "actor": self.authority.actor,
                    "action": "create_definition" if action == "propose" else action,
                    **fields,
                }
            ),
            self.authority,
        )
        if action == "propose":
            return {
                "receipt": receipt.model_dump(mode="json"),
                "next_action": (
                    "Validate and apply a scoped workflow Candidate; proposal is not executable"
                ),
            }
        if action in ("start", "answer", "correct_answer", "retry", "resume"):
            if self.workflow_controller is None:
                raise FoundationError(
                    "workflow_executor_unavailable", "No window workflow executor"
                )
            assert root_id is not None
            if (
                action == "answer"
                and self.deliver_answer is not None
                and receipt.result.get("outbox_id")
            ):
                self.deliver_answer(UUID(str(receipt.result["outbox_id"])))
            self.workflow_controller.start(root_id, raw.get("model", {}))
        assert root_id is not None
        return workflow_view(self.path, root_id, self.authority)

    def _workspace_configuration(self) -> LaunchConfig | None:
        return read_config(self.workspace_config) if self.workspace_config else None

    def workspace_operation(self, session_id: UUID, raw: dict[str, Any]) -> dict[str, Any]:
        if raw.get("mode") not in ("info", "projects", "status", "check") or (
            session_id in self.response_only and raw.get("mode") == "check"
        ):
            self._require_model_effect(session_id)
        self._session(session_id)
        config = self._workspace_configuration()
        if config is None:
            return {
                "personal_root": str(self.workspace),
                "selected_root": str(self.workspace),
                "selected_project": "legacy",
                "projects": [],
                "git": {"connected": False},
            }
        action = raw.get("mode", "info")
        if action == "register":
            if self.assigned_attempt_id is not None:
                raise FoundationError("permission_denied", "Assigned Work cannot register projects")
            assert self.workspace_config is not None
            config = register_project(
                self.workspace_config, Project(name=str(raw["name"]), path=Path(str(raw["path"])))
            )
        elif action == "select":
            root = config.project_root(str(raw["name"]))
            if not root.is_dir():
                raise FoundationError("resource_unavailable", "Registered project is unavailable")
            selected = self._session(session_id)
            if selected:
                if self.assigned_attempt_id is not None:
                    raise FoundationError("permission_denied", "Assigned resource cannot change")
                snapshot = read_execution(self.path, selected.work_id, self.authority)
                active = next((item for item in snapshot.attempts if item.status == "active"), None)
                if active and self.workspace.resolve() != root:
                    if active.session_id != session_id or any(
                        item.attempt_id == active.attempt_id and item.status != "answered"
                        for item in snapshot.invocations
                    ):
                        raise FoundationError(
                            "active_attempt", "Resolve the existing send before changing project"
                        )
                    apply_operation(
                        self.path,
                        StopAttemptRequest(
                            operation_id=uuid5(active.attempt_id, f"project:{root.as_posix()}"),
                            space_id=self.authority.space_id,
                            actor=self.authority.actor,
                            attempt_id=active.attempt_id,
                            work_id=selected.work_id,
                            session_id=session_id,
                            outcome="interrupted",
                        ),
                        self.authority,
                    )
                select_work_project(
                    config,
                    self.authority,
                    selected.work_id,
                    str(raw["name"]),
                    operation_id=UUID(str(raw.get("operation_id", uuid4()))),
                )
            elif self.assigned_attempt_id is not None:
                raise FoundationError("permission_denied", "Assigned resource cannot change")
            self.workspace = root
        elif action in ("prepare", "publish", "defer", "check"):
            item: GitPreparation | None
            if self.assigned_attempt_id is not None:
                raise FoundationError(
                    "permission_denied", "Assigned Work cannot publish the workspace"
                )
            if action == "prepare":
                item = prepare_git(config, self.authority)
            elif action == "check":
                item = reconcile_git(config)
            elif action == "defer":
                item = defer_git(config, UUID(str(raw["preparation_id"])))
            else:
                # This endpoint is reached only after the extension's trusted UI approval.
                nonce = UUID(str(raw["nonce"]))
                prepared = self.git_previews.pop(nonce, None)
                if prepared is None or prepared != UUID(str(raw["preparation_id"])):
                    raise FoundationError(
                        "confirmation_required", "No local approval for this Git packet"
                    )
                item = publish_git(config, self.authority, prepared, approved=True)
            result: dict[str, Any] = (
                {
                    "preparation_id": str(item.preparation_id),
                    "status": item.status,
                    "repository": item.repository,
                    "commit": item.commit,
                    "error": item.error,
                    "file_count": len(item.files),
                    "files": list(item.files)[:50],
                    "more_files": max(0, len(item.files) - 50),
                }
                if item
                else {"delivery": None}
            )
            if action == "prepare" and item:
                nonce = uuid4()
                self.git_previews[nonce] = item.preparation_id
                result["nonce"] = str(nonce)
            return result
        elif action not in ("info", "projects", "status"):
            raise FoundationError("invalid_request", "Unsupported workspace operation")
        git = git_status(config)
        delivery = git.get("delivery")
        if isinstance(delivery, dict):
            delivery["files"] = list(delivery["files"])[:50]
        return {
            **workspace_info(config),
            "selected_root": str(self.workspace),
            "selected_project": config.project_name(self.workspace),
            "git": git,
        }

    def activity_setup(self, session_id: UUID, raw: dict[str, Any]) -> dict[str, Any]:
        if raw.get("action", "status") not in ("status", "list", "read_packet", "window_close"):
            self._require_model_effect(session_id)
        """Only the interactive trusted host controls a bounded new-Activity setup."""
        self._session(session_id)
        if self.assigned_attempt_id is not None and raw.get("action") != "read_packet":
            raise FoundationError(
                "permission_denied", "Assigned Work cannot control Activity setup"
            )
        action = str(raw.get("action", "status"))
        if action == "window_close":
            if self.setup_controller is not None:
                self.setup_controller.close()
            return {"closed": True}
        if action == "list":
            return {
                "items": [
                    item.model_dump(mode="json")
                    for item in list_activity_setups(
                        self.path, self.authority, pending_only=bool(raw.get("pending_only", False))
                    )
                ]
            }
        identifier = UUID(str(raw["setup_id"]))
        if action == "retain_file":
            current = read_activity_setup(self.path, identifier, self.authority)
            original, _ = self._fresh_user_source(session_id, raw.get("answer_source"))
            content = base64.b64decode(str(raw["content_base64"]), validate=True)
            content.decode("utf-8")
            digest = hashlib.sha256(content).hexdigest().upper()
            if digest != str(raw["content_sha256"]).upper():
                raise FoundationError("invalid_request", "Selected file digest differs from bytes")
            source_id = uuid5(identifier, "selected-file:" + str(raw["operation_key"]))
            receipt = apply_operation(
                self.path,
                CreateKnowledgeRequest(
                    operation_id=uuid5(source_id, "retain"),
                    space_id=self.authority.space_id,
                    actor=self.authority.actor,
                    record_id=source_id,
                    state=SourceState(
                        channel="document",
                        connection="ordinary-pi-selected-file",
                        profile_revision=1,
                        scope_activity_id=current.state.activity_id,
                        media_type="text/plain; charset=utf-8",
                        capture="full",
                        content=content,
                        locator=str(raw["locator"]),
                        derived_from=(original,),
                        limitations=(
                            "File selected explicitly; archived names are origin labels, "
                            "not Core addresses",
                        ),
                    ),
                ),
                self.authority,
            )
            reference = KnowledgeRef(record_id=source_id, revision=1)
            self.selected_file_refs.setdefault(session_id, set()).add(reference)
            return {
                "selected_source": reference.model_dump(mode="json"),
                "content_sha256": digest,
                "total_bytes": len(content),
                "exposed": [],
                "receipt": receipt.model_dump(mode="json"),
            }
        if action == "read_packet":
            current = read_activity_setup(self.path, identifier, self.authority)
            if self.assigned_attempt_id is not None and not any(
                stage.work_id == self._selection(session_id).work_id
                for stage in current.state.stages
            ):
                raise FoundationError("wrong_scope", "Read only packets of the assigned setup")
            packet_reference = ArtifactRef.model_validate(raw["reference"])
            allowed = {
                ref
                for ref in (current.state.manifest, current.state.draft, current.state.review)
                if ref is not None
            }
            allowed.update(stage.packet for stage in current.state.stages)
            allowed.update(stage.output for stage in current.state.stages if stage.output)
            if packet_reference not in allowed:
                raise FoundationError(
                    "wrong_scope", "Artifact is not a packet/result of this setup"
                )
            item = read_artifact(
                self.path,
                packet_reference.artifact_id,
                self.authority,
                revision=packet_reference.revision,
            )
            packet_content = item.content
            if packet_content is None or item.media_type is None:
                raise FoundationError(
                    "unavailable_context", "Setup artifact content is unavailable"
                )
            offset, maximum = int(raw.get("offset", 0)), int(raw.get("max_bytes", 16384))
            if offset < 0 or offset > len(packet_content) or not 1 <= maximum <= 65536:
                raise FoundationError("invalid_request", "Use a bounded artifact window")
            end = min(offset + maximum, len(packet_content))
            if item.media_type.startswith("text/") or item.media_type == "application/json":
                while end > offset:
                    try:
                        packet_content[offset:end].decode("utf-8")
                        break
                    except UnicodeDecodeError:
                        end -= 1
                if end == offset and offset < len(packet_content):
                    raise FoundationError("invalid_request", "Window cannot hold a UTF-8 character")
            return {
                "reference": packet_reference.model_dump(mode="json"),
                "media_type": item.media_type,
                "offset": offset,
                "total_bytes": len(packet_content),
                "content_base64": base64.b64encode(packet_content[offset:end]).decode("ascii"),
                "next_offset": end if end < len(packet_content) else None,
            }
        if action == "status":
            from .activity_setup import _observe

            return cast(dict[str, Any], _observe(self._setup_status, identifier))
        if action not in (
            "begin",
            "answer",
            "attach_sources",
            "question",
            "submit",
            "pause",
            "resume",
            "cancel",
            "retry",
        ):
            raise FoundationError(
                "permission_denied", "Internal review/adoption operations are host-owned"
            )
        fields: dict[str, Any] = {}
        if action == "begin":
            fields.update(
                activity_id=UUID(str(raw["activity_id"])),
                title=raw["title"],
                text=raw["goal"],
                contract_version=2 if read_space(self.path).schema_version >= 15 else 1,
                mode=raw.get("mode", "create"),
            )
            source = self._setup_request_source(session_id, raw)
            if source is not None:
                fields["source_refs"] = (source,)
        else:
            current = read_activity_setup(self.path, identifier, self.authority)
            fields.update(activity_id=current.state.activity_id, expected_revision=current.revision)
        if action == "answer":
            original, fields["text"] = self._fresh_user_source(session_id, raw.get("answer_source"))
            fields["source_refs"] = (original,)
            state = current.state
            if state.question:
                self._answer_temporal_guard(original, kind="setup", subject=identifier)
            if original in state.sources:
                supplied = self._exposed_sources(session_id, raw)
                if not any(ref not in state.sources for ref in supplied):
                    return self._setup_status(identifier)
                action = "attach_sources"
                fields.pop("text")
                fields["source_refs"] = supplied
            if action == "answer" and state.stages and state.stages[-1].output is None:
                stage = state.stages[-1]
                snapshot = read_execution(self.path, stage.work_id, self.authority)
                opened = next((wait for wait in snapshot.waits if wait.status == "open"), None)
                interrupted = state.phase == "paused" and (
                    any(
                        item.status in ("admitted", "sent", "unknown")
                        for item in snapshot.invocations
                    )
                    or any(item.status == "unknown" for item in snapshot.assignments)
                )
                if opened is not None and not interrupted:
                    answered = apply_operation(
                        self.path,
                        AnswerWaitRequest(
                            operation_id=uuid5(
                                original.record_id, f"setup-answer:{opened.wait_id}"
                            ),
                            space_id=self.authority.space_id,
                            actor=self.authority.actor,
                            wait_id=opened.wait_id,
                            attempt_id=opened.attempt_id,
                            work_id=stage.work_id,
                            session_id=next(
                                item.session_id
                                for item in snapshot.attempts
                                if item.attempt_id == opened.attempt_id
                            ),
                            expected_wait_revision=opened.revision,
                            answer=fields["text"],
                        ),
                        self.authority,
                    )
                    from .assigned import deliver_outbox

                    deliver_outbox(
                        self.path, self.authority, UUID(str(answered.result["outbox_id"]))
                    )
        elif action == "question":
            fields["text"] = str(raw["question"])
        if action == "attach_sources":
            request_anchor = self._setup_request_source(session_id, raw)
            if request_anchor is not None:
                fields["source_refs"] = tuple(
                    dict.fromkeys(fields.get("source_refs", ()) + (request_anchor,))
                )
        if action in ("begin", "answer", "attach_sources", "submit"):
            supplied = self._exposed_sources(session_id, raw)
            fields["source_refs"] = tuple(dict.fromkeys(fields.get("source_refs", ()) + supplied))
        if action == "submit":
            current = read_activity_setup(self.path, identifier, self.authority)
            supplied = fields.get("source_refs", ())
            if any(ref not in current.state.sources for ref in supplied):
                apply_operation(
                    self.path,
                    ActivitySetupRequest(
                        operation_id=uuid5(
                            identifier,
                            "submit-sources:"
                            + json.dumps(
                                [ref.model_dump(mode="json") for ref in supplied], sort_keys=True
                            ),
                        ),
                        space_id=self.authority.space_id,
                        actor=self.authority.actor,
                        setup_id=identifier,
                        action="attach_sources",
                        activity_id=current.state.activity_id,
                        expected_revision=current.revision,
                        source_refs=supplied,
                    ),
                    self.authority,
                )
                current = read_activity_setup(self.path, identifier, self.authority)
            if current.state.phase == "needs_input":
                raise FoundationError(
                    "incomplete_context", "Answer the saved question before submitting setup"
                )
        if action != "submit":
            apply_operation(
                self.path,
                ActivitySetupRequest(
                    operation_id=UUID(str(raw.get("operation_id", uuid4()))),
                    space_id=self.authority.space_id,
                    actor=self.authority.actor,
                    setup_id=identifier,
                    action=cast(Any, action),
                    **fields,
                ),
                self.authority,
            )
        if action in ("pause", "cancel") and self.setup_controller is not None:
            self.setup_controller.request_pause(identifier)
        if action in ("submit", "resume", "retry"):
            if self.setup_controller is None:
                raise FoundationError(
                    "setup_executor_unavailable", "The interactive host has no setup executor"
                )
            self.setup_controller.start(identifier, raw.get("model", {}))
        from .activity_setup import _observe

        return cast(dict[str, Any], _observe(self._setup_status, identifier))

    def connect(self, session_id: UUID) -> dict[str, object]:
        if self.assigned_session_id is not None and session_id != self.assigned_session_id:
            raise FoundationError("unknown_session", "RPC session differs from assignment")
        space = read_space(self.path)
        if (
            space.space_id != self.authority.space_id
            or space.execution_epoch != self.authority.execution_epoch
        ):
            raise FoundationError("stale_epoch", "Bridge authority no longer matches this space")
        if space.schema_version < 3 or space.recovery_state != "active":
            raise FoundationError(
                "unsupported_schema", "Interactive Pi needs active execution schema"
            )
        overview = inspect_space(self.path, self.authority)
        if overview.pending_deletions:
            raise FoundationError("deletion_pending", "Complete Core deletion before opening Pi")
        choices = []
        for item in overview.records:
            if item.status == "deleted":
                continue
            if item.kind == "activity":
                try:
                    activity_detail = read_activity(self.path, item.record_id, self.authority)
                    choices.append(
                        {**item.model_dump(mode="json"), "label": activity_detail.state.title}
                    )
                except FoundationError:
                    continue
            elif item.kind == "work":
                try:
                    work_detail = read_work(self.path, item.record_id, self.authority)
                    lifecycle = read_work_status(self.path, item.record_id, self.authority)
                    choices.append(
                        {
                            **item.model_dump(mode="json"),
                            "label": work_detail.state.goal,
                            "activity_id": str(work_detail.state.activity_id),
                            "lifecycle": lifecycle.status,
                        }
                    )
                except FoundationError:
                    continue
        with self.lock:
            self.sessions.setdefault(session_id, None)
            selected = self.sessions[session_id]
        return {
            "protocol_version": PROTOCOL_VERSION,
            "space_id": str(space.space_id),
            "execution_epoch": space.execution_epoch,
            "schema_version": space.schema_version,
            "actor": self.authority.actor,
            "session_id": str(session_id),
            "records": choices,
            "selection": {
                "activity_id": str(selected.activity_id),
                "work_id": str(selected.work_id),
            }
            if selected
            else None,
        }

    def activity_read(self, session_id: UUID, activity_id: UUID) -> dict[str, object]:
        self._session(session_id)
        return read_activity(self.path, activity_id, self.authority).model_dump(mode="json")

    def select(self, session_id: UUID, activity_id: UUID, work_id: UUID) -> dict[str, object]:
        if session_id in self.response_only:
            raise FoundationError(
                "permission_denied", "Response repair cannot change Work selection"
            )
        self._session(session_id)
        activity = read_activity(self.path, activity_id, self.authority)
        work = read_work(self.path, work_id, self.authority)
        if work.state.activity_id != activity.activity_id:
            raise FoundationError("wrong_work", "Work is not in the selected Activity")
        snapshot = read_execution(self.path, work_id, self.authority)
        if self.assigned_attempt_id is not None and not any(
            item.attempt_id == self.assigned_attempt_id and item.status == "active"
            for item in snapshot.attempts
        ):
            raise FoundationError("stale_attempt", "Assigned RPC cannot select this Work")
        resource = next(
            (
                item
                for item in snapshot.resources
                if item.state.root == self.workspace and item.state.status == "active"
            ),
            None,
        )
        config = self._workspace_configuration()
        if config is not None:
            active = [item for item in snapshot.resources if item.state.status == "active"]
            if len(active) > 1:
                raise FoundationError("resource_unavailable", "Work has multiple active resources")
            if active:
                resource = active[0]
                config.project_name(
                    resource.state.root
                )  # Old session cwd grants no project access.
                if not resource.state.root.is_dir():
                    raise FoundationError(
                        "resource_unavailable", "Saved Work project is unavailable"
                    )
                self.workspace = resource.state.root.resolve()
        # A composite parent or child runs only through a Core-assigned Attempt.
        if resource is None and work.state.status == "proposed" and snapshot.composition is None:
            resource_id = uuid5(
                self.authority.space_id, f"resource:{work_id}:{self.workspace.as_posix()}"
            )
            request = CreateResourceRequest(
                operation_id=uuid5(resource_id, "create"),
                space_id=self.authority.space_id,
                actor=self.authority.actor,
                resource_id=resource_id,
                work_id=work_id,
                state=ResourceState(
                    label=self.workspace.name, root=self.workspace, limit_units=self.limit_units
                ),
            )
            apply_operation(self.path, request, self.authority)
            snapshot = read_execution(self.path, work_id, self.authority)
        with self.lock:
            self.sessions[session_id] = Selection(activity_id=activity_id, work_id=work_id)
        return snapshot.model_dump(mode="json")

    def _session(self, session_id: UUID) -> Selection | None:
        with self.lock:
            if session_id not in self.sessions:
                raise FoundationError("unknown_session", "Connect this Pi session first")
            return self.sessions[session_id]

    def _selection(self, session_id: UUID) -> Selection:
        selected = self._session(session_id)
        if selected is None:
            raise FoundationError("no_work", "Select an Activity and Work first")
        return selected

    def snapshot(self, session_id: UUID) -> dict[str, object]:
        selected = self._selection(session_id)
        current = read_execution(self.path, selected.work_id, self.authority)
        result = current.model_dump(mode="json")
        result["output_publication_contracts"] = output_publication_contracts(current.work.state)
        if self.assigned_attempt_id is not None:
            stage = read_setup_stage(self.path, selected.work_id, self.authority)
            if stage is not None and stage.result_protocol is not None:
                result["setup_result_protocol"] = stage.result_protocol
            if read_workflow_node_for_work(self.path, selected.work_id, self.authority) is not None:
                result["workflow_result_protocol"] = "workflow_json"
        return result

    def operation(self, session_id: UUID, raw: dict[str, object]) -> dict[str, object]:
        selected = self._selection(session_id)
        try:
            request = REQUEST_ADAPTER.validate_python(raw)
        except ValidationError as error:
            raise FoundationError("invalid_request", str(error)) from error
        if isinstance(request, CreateResourceRequest):
            self._require_model_effect(session_id)
        if not isinstance(
            request,
            (
                CreateResourceRequest,
                # Resource revisions are handled by the trusted local host, not model text.
            ),
        ) and request.kind not in (
            "start_attempt",
            "stop_attempt",
            "prepare_invocation",
            "admit_invocation",
            "send_invocation",
            "finish_invocation",
        ):
            raise FoundationError(
                "permission_denied", "This endpoint accepts execution operations only"
            )
        if getattr(request, "work_id", None) != selected.work_id:
            if request.kind != "finish_invocation":
                raise FoundationError("wrong_work", "Operation does not address the selected Work")
            pinned = read_execution(self.path, request.work_id, self.authority)
            if not any(
                item.invocation_id == request.invocation_id
                and item.attempt_id == request.attempt_id
                for item in pinned.invocations
            ) or not any(
                item.attempt_id == request.attempt_id and item.session_id == session_id
                for item in pinned.attempts
            ):
                raise FoundationError("wrong_work", "Finish lacks the exact native invocation pin")
        if self.assigned_attempt_id is not None:
            if (
                request.kind
                not in (
                    "prepare_invocation",
                    "admit_invocation",
                    "send_invocation",
                    "finish_invocation",
                )
                or getattr(request, "attempt_id", None) != self.assigned_attempt_id
            ):
                raise FoundationError("permission_denied", "RPC bridge is bound to one Attempt")
        if getattr(request, "session_id", session_id) != session_id:
            raise FoundationError("unknown_session", "Operation session does not match Pi")
        if request.actor != self.authority.actor or request.space_id != self.authority.space_id:
            raise FoundationError(
                "permission_denied", "Actor or space differs from local authority"
            )
        receipt = apply_operation(self.path, request, self.authority)
        return receipt.model_dump(mode="json")

    def binding_catalog(self, session_id: UUID) -> dict[str, object]:
        self._session(session_id)
        if self.assigned_attempt_id is not None:
            raise FoundationError("permission_denied", "Assigned RPC cannot manage Bindings")
        info = read_space(self.path)
        return {
            "schema_version": info.schema_version,
            "methods": [
                item.model_dump(mode="json")
                for item in list_binding_methods(self.path, self.authority)
            ],
            "bindings": [
                item.model_dump(mode="json") for item in list_bindings(self.path, self.authority)
            ]
            if info.schema_version >= 9
            else [],
            "offers": [
                item.model_dump(mode="json")
                for item in list_binding_offers(self.path, self.authority)
            ]
            if info.schema_version >= 9
            else [],
        }

    def binding_contract(self, session_id: UUID, kind: str) -> dict[str, object]:
        self._session(session_id)
        if self.assigned_attempt_id is not None:
            raise FoundationError("permission_denied", "Assigned RPC cannot manage Bindings")
        model = BINDING_INTENTS.get(kind)
        if model is None:
            raise FoundationError("invalid_request", "Unknown Binding operation kind")
        return {"kind": kind, "schema": model.model_json_schema()}

    def binding_upgrade(self, session_id: UUID) -> dict[str, object]:
        self._session(session_id)
        if self.assigned_attempt_id is not None:
            raise FoundationError("permission_denied", "Assigned RPC cannot upgrade Bindings")
        for version, upgrade in (
            (4, upgrade_continuation_space),
            (5, upgrade_composition_space),
            (6, upgrade_child_execution_space),
            (7, upgrade_plan_revision_space),
            (8, upgrade_parent_execution_space),
            (9, upgrade_binding_space),
        ):
            if read_space(self.path).schema_version < version:
                upgrade(self.path, self.authority)
        return {"schema_version": read_space(self.path).schema_version}

    def binding_operation(self, session_id: UUID, raw: dict[str, object]) -> dict[str, object]:
        self._require_model_effect(session_id)
        self._session(session_id)
        if self.assigned_attempt_id is not None:
            raise FoundationError("permission_denied", "Assigned RPC cannot manage Bindings")
        try:
            request = REQUEST_ADAPTER.validate_python(raw)
        except ValidationError as error:
            raise FoundationError("invalid_request", str(error)) from error
        if not isinstance(
            request,
            (
                CreateMethodVersionRequest,
                CreateBindingVersionRequest,
                SetBindingStateRequest,
                FireBindingRequest,
                ResolveBindingOfferRequest,
            ),
        ):
            raise FoundationError("permission_denied", "Only Binding operations use this endpoint")
        if request.actor != self.authority.actor or request.space_id != self.authority.space_id:
            raise FoundationError(
                "permission_denied", "Binding actor/space differs from host authority"
            )
        return apply_operation(self.path, request, self.authority).model_dump(mode="json")

    def knowledge_upgrade(self, session_id: UUID) -> dict[str, object]:
        self._session(session_id)
        if self.assigned_attempt_id is not None:
            raise FoundationError("permission_denied", "Assigned RPC cannot upgrade Core")
        for version, upgrade in (
            (4, upgrade_continuation_space),
            (5, upgrade_composition_space),
            (6, upgrade_child_execution_space),
            (7, upgrade_plan_revision_space),
            (8, upgrade_parent_execution_space),
            (9, upgrade_binding_space),
            (10, upgrade_knowledge_space),
        ):
            if read_space(self.path).schema_version < version:
                upgrade(self.path, self.authority)
        return {"schema_version": read_space(self.path).schema_version}

    def knowledge_contract(self, session_id: UUID, kind: str) -> dict[str, object]:
        self._session(session_id)
        model = KNOWLEDGE_INTENTS.get(kind)
        if model is None:
            raise FoundationError("invalid_request", "Unknown knowledge operation")
        return {"kind": kind, "schema": model.model_json_schema()}

    def integration(self, session_id: UUID, raw: dict[str, Any]) -> dict[str, object]:
        if (
            session_id in self.response_only
            and raw.get("mode") == "apply"
            and (
                raw.get("adapter") == "memory"
                and raw.get("operation") in ("read_batch", "prepare_cache")
                or raw.get("adapter") == "data"
                and raw.get("operation") == "query_entries"
            )
        ):
            self._require_model_effect(session_id)
        if raw.get("mode") not in ("catalog", "contract") and raw.get("operation") not in (
            "read_document",
            "product_context",
            "catalog",
            "history",
            "open_selection",
            "read_batch",
            "prepare_cache",
            "describe_structure",
            "list_formats",
            "read_format",
            "read_entry",
            "query_entries",
            "aggregate_entries",
            "working_set",
            "procedure_status",
            "due_procedures",
        ):
            self._require_model_effect(session_id)
        self._session(session_id)
        if self.assigned_attempt_id is not None:
            raise FoundationError("permission_denied", "Integration setup is interactive only")
        registry = installed_integrations(self.path, self.authority)
        mode = raw["mode"]
        if mode == "catalog":
            return registry.catalog()
        adapter, operation = str(raw["adapter"]), str(raw["operation"])
        if mode == "contract":
            return registry.contract(adapter, operation)
        if mode != "apply" or not isinstance(raw.get("arguments"), dict):
            raise FoundationError("invalid_request", "Use catalog, contract or typed apply")
        # Pi call identity is bound to this session, never an actor supplied by the model.
        operation_id = uuid5(session_id, f"integration:{raw['operation_key']}")
        result = registry.execute(
            operation_id,
            adapter,
            operation,
            raw["arguments"],
            contract_version=raw["contract_version"],
        )
        with self.lock:
            self.exposed_refs.setdefault(session_id, set()).update(result.exposed)
            if adapter == "memory" and operation in ("read_batch", "open_selection"):
                self.memory_snapshots.setdefault(session_id, set()).add(
                    KnowledgeRef(
                        record_id=UUID(str(result.output["selection_id"])),
                        revision=1,
                    )
                )
            if adapter == "memory" and operation == "prepare_cache":
                selectors = tuple(
                    MemorySelector.model_validate(s) for s in raw["arguments"].get("selectors", [])
                )
                self.memory_rules.setdefault(session_id, {})[
                    json.dumps([s.model_dump(mode="json") for s in selectors], sort_keys=True)
                ] = selectors
        return result.output

    def data_operation(self, session_id: UUID, raw: dict[str, Any]) -> dict[str, object]:
        if (
            session_id in self.response_only
            and raw.get("mode") != "contract"
            and raw.get("operation") == "query_entries"
        ):
            self._require_model_effect(session_id)
        if raw.get("mode") != "contract" and raw.get("operation", "describe_structure") not in (
            "describe_structure",
            "list_formats",
            "read_format",
            "read_entry",
            "history",
            "query_entries",
            "aggregate_entries",
            "working_set",
            "procedure_status",
            "due_procedures",
        ):
            self._require_model_effect(session_id)
        selected = self._session(session_id)
        if raw.get("mode") == "run":
            self._require_model_effect(session_id)
            if self.assigned_attempt_id is not None or self.procedure_controller is None:
                raise FoundationError(
                    "permission_denied", "Procedure execution belongs to an interactive Pi window"
                )
            return cast(
                dict[str, object],
                self.procedure_controller.start(UUID(str(raw["run_id"])), raw.get("model", {})),
            )
        registry = installed_integrations(self.path, self.authority)
        operation = str(raw.get("operation", "describe_structure"))
        if self.restricted_core_reads and operation not in (
            "describe_structure",
            "list_formats",
            "read_format",
            "read_entry",
            "history",
            "query_entries",
            "aggregate_entries",
            "working_set",
            "procedure_status",
            "due_procedures",
        ):
            raise FoundationError("permission_denied", "This node permits Core reads only")
        if raw.get("mode") == "contract":
            return registry.contract("data", operation)
        arguments = dict(raw.get("arguments", {}))
        if operation == "start_procedure" and "request_basis" not in arguments:
            original = self._request_source(session_id)
            arguments["request_basis"] = [original.model_dump(mode="json")] if original else []
        if operation in ("create_entry", "correct_entry", "ingest_batch") and selected is not None:
            attempt = next(
                (
                    item
                    for item in read_execution(self.path, selected.work_id, self.authority).attempts
                    if item.session_id == session_id and item.status == "active"
                ),
                None,
            )
            if attempt is None:
                raise FoundationError(
                    "stale_attempt", "No active Attempt belongs to this Work session"
                )
            states = (
                [arguments["state"]]
                if operation != "ingest_batch"
                else [
                    item["mutation"]["state"]
                    for item in arguments.get("elements", [])
                    if item.get("mutation")
                ]
            )
            for state in states:
                if (
                    "scope_activity_id" in state
                    and state["scope_activity_id"] != str(selected.activity_id)
                ) or (state.get("work_id") not in (None, str(selected.work_id))):
                    raise FoundationError(
                        "wrong_scope", "Work cannot write data of another Activity"
                    )
                state.update(
                    work_id=str(selected.work_id),
                    scope_activity_id=str(selected.activity_id),
                    attempt_id=str(attempt.attempt_id),
                    session_id=str(session_id),
                )
        if self.assigned_attempt_id is not None and operation == "start_procedure":
            raise FoundationError(
                "permission_denied", "Assigned Work cannot launch another procedure"
            )
        result = registry.execute(
            uuid5(session_id, "data:" + str(raw["operation_key"])),
            "data",
            operation,
            arguments,
            contract_version=1,
        )
        with self.lock:
            self.exposed_refs.setdefault(session_id, set()).update(result.exposed)
            if operation == "query_entries":
                ref = KnowledgeRef(record_id=UUID(str(result.output["selection_id"])), revision=1)
                self.memory_snapshots.setdefault(session_id, set()).add(ref)
        return result.output

    def manual_exchange(self, session_id: UUID, raw: dict[str, object]) -> dict[str, object]:
        if raw.get("mode") != "read":
            self._require_model_effect(session_id)
        self._session(session_id)
        exchange = ManualExchange(self.path, self.authority)
        mode = str(raw["mode"])
        if mode == "read":
            return self._expose_exchange(
                session_id,
                exchange.read(
                    UUID(str(raw["record_id"])),
                    revision=int(str(raw["revision"])) if raw.get("revision") is not None else None,
                ),
            )
        if raw.get("work_id") is not None and raw.get("activity_id") is None:
            raise FoundationError("invalid_request", "Explicit Work also needs its Activity")
        if raw.get("activity_id") is not None:
            activity_id = UUID(str(raw["activity_id"]))
            work_id = UUID(str(raw["work_id"])) if raw.get("work_id") is not None else None
        else:
            selected = self._selection(session_id)
            activity_id, work_id = selected.activity_id, selected.work_id
        if self.assigned_attempt_id is not None:
            selected = self._selection(session_id)
            if (activity_id, work_id) != (selected.activity_id, selected.work_id):
                raise FoundationError("wrong_work", "Use the assigned Work for manual exchange")
        operation_id = (
            uuid5(session_id, f"manual-exchange:{raw['operation_key']}")
            if raw.get("operation_key") is not None
            else UUID(str(raw["operation_id"]))
        )
        if mode == "prepare":
            return self._expose_exchange(
                session_id,
                exchange.prepare(
                    operation_id,
                    activity_id,
                    work_id=work_id,
                    external_tool=str(raw["external_tool"]),
                ),
            )
        if mode == "import":
            content = base64.b64decode(str(raw["content_base64"]), validate=True)
            reply = raw.get("reply_to")
            previous = raw.get("previous_source")
            return exchange.receive(
                operation_id,
                activity_id,
                work_id=work_id,
                origin=str(raw["origin"]),
                content=content,
                previous_source=KnowledgeRef.model_validate(previous)
                if previous is not None
                else None,
                sender=str(raw["sender"]) if raw.get("sender") is not None else None,
                locator=str(raw["locator"]) if raw.get("locator") is not None else None,
                reply_to=KnowledgeRef.model_validate(reply) if reply is not None else None,
            )
        raise FoundationError("invalid_request", "Unknown manual exchange mode")

    def _expose_exchange(self, session_id: UUID, result: dict[str, object]) -> dict[str, object]:
        with self.lock:
            self.exposed_refs.setdefault(session_id, set()).add(
                KnowledgeRef(
                    record_id=UUID(str(result["record_id"])),
                    revision=int(str(result["revision"])),
                )
            )
        return result

    def knowledge_operation(self, session_id: UUID, raw: dict[str, object]) -> dict[str, object]:
        self._require_model_effect(session_id)
        self._session(session_id)
        if self.restricted_core_reads:
            raise FoundationError("permission_denied", "This node permits Core reads only")
        prepared = dict(raw)
        state_raw = prepared.get("state")
        if isinstance(state_raw, dict):
            state = dict(state_raw)
            if (
                state.get("conversation_final") not in (None, False)
                or state.get("conversation_terminal") is not None
            ):
                raise FoundationError(
                    "permission_denied", "Native final proof cannot be supplied by model memory"
                )
            if state.get("kind") in ("data_entry", "data_format", "activity_structure"):
                raise FoundationError(
                    "invalid_request",
                    "Use zara_data for typed data and reviewed setup for structure",
                )
            if state.get("kind") == "source" and isinstance(state.get("content_text"), str):
                state["content"] = base64.b64encode(
                    state.pop("content_text").encode("utf-8")
                ).decode("ascii")
            if state.get("kind") == "handoff" and isinstance(state.get("document_text"), str):
                state["document"] = base64.b64encode(
                    state.pop("document_text").encode("utf-8")
                ).decode("ascii")
            prepared["state"] = state
        try:
            request = REQUEST_ADAPTER.validate_json(json.dumps(prepared))
        except ValidationError as error:
            raise FoundationError("invalid_request", str(error)) from error
        if not isinstance(
            request,
            (
                CreateKnowledgeRequest,
                ReviseKnowledgeRequest,
                DeleteKnowledgeRequest,
                CreateGrantRequest,
            ),
        ):
            raise FoundationError(
                "permission_denied", "Only knowledge operations use this endpoint"
            )
        if self.assigned_attempt_id is not None and isinstance(request, CreateGrantRequest):
            raise FoundationError("permission_denied", "Assigned Work cannot create a Grant")
        if self.assigned_attempt_id is not None and isinstance(request, DeleteKnowledgeRequest):
            raise FoundationError(
                "permission_denied", "Knowledge deletion requires the interactive owner path"
            )
        if request.actor != self.authority.actor or request.space_id != self.authority.space_id:
            raise FoundationError("permission_denied", "Knowledge actor/space differs from host")
        return apply_operation(self.path, request, self.authority).model_dump(mode="json")

    def development_contract(self, session_id: UUID, kind: str) -> dict[str, object]:
        self._session(session_id)
        model = DEVELOPMENT_INTENTS.get(kind)
        if model is None:
            raise FoundationError("invalid_request", "Unknown development operation")
        return {"kind": kind, "schema": model.model_json_schema()}

    def development_upgrade(self, session_id: UUID) -> dict[str, object]:
        self._session(session_id)
        if self.assigned_attempt_id is not None:
            raise FoundationError("permission_denied", "Assigned Work cannot upgrade Core")
        self.knowledge_upgrade(session_id)
        if read_space(self.path).schema_version < 11:
            upgrade_development_space(self.path, self.authority)
        if read_space(self.path).schema_version < 12:
            upgrade_change_package_space(self.path, self.authority)
        return {"schema_version": read_space(self.path).schema_version}

    def development_start_sleep(
        self, session_id: UUID, raw: dict[str, object]
    ) -> dict[str, object]:
        self._require_model_effect(session_id)
        self._session(session_id)
        if self.assigned_attempt_id is not None:
            raise FoundationError(
                "permission_denied", "Assigned Work cannot create a new Sleep Work"
            )
        if read_space(self.path).schema_version < 11:
            raise FoundationError("upgrade_required", "Prepare explicit schema 11 before Sleep")
        start_id = UUID(str(raw["start_id"]))
        scope = str(raw["scope"]).strip()
        if not scope or len(scope) > 2048:
            raise FoundationError("invalid_request", "Sleep needs a bounded scope description")
        raw_units = raw.get("resource_limit_units")
        units = int(str(raw_units)) if raw_units is not None else self.limit_units
        if units is not None and (
            units < 1 or (self.limit_units is not None and units > self.limit_units)
        ):
            raise FoundationError(
                "resource_exhausted", "Sleep resource exceeds the chosen Work limit"
            )
        activity_id = (
            UUID(str(raw["activity_id"]))
            if raw.get("activity_id")
            else uuid5(self.authority.space_id, "zaratustra-development-activity")
        )
        if not raw.get("activity_id"):
            try:
                read_activity(self.path, activity_id, self.authority)
            except FoundationError as error:
                if error.code != "not_found":
                    raise
                apply_operation(
                    self.path,
                    CreateActivityRequest(
                        operation_id=uuid5(activity_id, "create"),
                        space_id=self.authority.space_id,
                        actor=self.authority.actor,
                        activity_id=activity_id,
                        state=ActivityState(
                            title="Zaratustra development",
                            goal="Review experience and improve authorized methods",
                        ),
                    ),
                    self.authority,
                )
        activity = read_activity(self.path, activity_id, self.authority)
        if activity.state.status != "ongoing":
            raise FoundationError("activity_not_ongoing", "Sleep Work needs an ongoing Activity")
        ref = initial_sleep_ref(self.authority.space_id)
        try:
            read_method_version(self.path, ref, self.authority)
        except FoundationError as error:
            if error.code != "method_unavailable":
                raise
            apply_operation(
                self.path,
                CreateMethodVersionRequest(
                    operation_id=uuid5(ref.method_id, "publish-v1"),
                    space_id=self.authority.space_id,
                    actor=self.authority.actor,
                    method_id=ref.method_id,
                    version=1,
                    definition=initial_sleep_method(),
                ),
                self.authority,
            )
        work_id = uuid5(start_id, "sleep-work")
        sleep_id = uuid5(start_id, "sleep-analysis")
        parent, plan = sleep_work_template(
            activity_id=activity_id,
            method=ref,
            work_id=work_id,
            consolidation_id=uuid5(start_id, "consolidation"),
            exploration_id=uuid5(start_id, "exploration"),
            scope=scope,
        )
        work_receipt = apply_operation(
            self.path,
            CreateCompositeWorkRequest(
                operation_id=uuid5(start_id, "create-work"),
                space_id=self.authority.space_id,
                actor=self.authority.actor,
                work_id=work_id,
                state=parent,
                plan=plan,
            ),
            self.authority,
        )
        # The Work receipt pins the intake boundary across retries and sessions.
        cutoff = work_receipt.state_revision
        scope_activities = tuple(
            UUID(str(item)) for item in cast(list[object], raw.get("scope_activity_ids", []))
        )
        sleep_receipt = apply_operation(
            self.path,
            CreateDevelopmentRequest(
                operation_id=uuid5(start_id, "create-analysis"),
                space_id=self.authority.space_id,
                actor=self.authority.actor,
                record_id=sleep_id,
                state=SleepState(
                    work_id=work_id,
                    method=ref,
                    scope_activity_ids=scope_activities,
                    include_free_conversation=raw.get("include_free_conversation") is not False,
                    intake_cutoff_revision=cutoff,
                    resource_limit_units=units,
                    remainder=(
                        SleepRemainder(
                            kind="new_intake",
                            description="Enumerate received material to the saved cutoff",
                        ),
                        SleepRemainder(
                            kind="question",
                            description="Make one bounded exploration outside ready links",
                        ),
                    ),
                ),
            ),
            self.authority,
        )
        return {
            "activity_id": str(activity_id),
            "work_id": str(work_id),
            "sleep_id": str(sleep_id),
            "method": ref.model_dump(mode="json"),
            "work_receipt": work_receipt.model_dump(mode="json"),
            "sleep_receipt": sleep_receipt.model_dump(mode="json"),
        }

    def development_operation(self, session_id: UUID, raw: dict[str, object]) -> dict[str, object]:
        self._require_model_effect(session_id)
        self._session(session_id)
        if self.restricted_core_reads:
            raise FoundationError("permission_denied", "This node permits Core reads only")
        state = raw.get("state")
        if (
            raw.get("kind") in ("create_development", "revise_development")
            and isinstance(state, dict)
            and state.get("kind") == "sleep"
        ):
            work_id = UUID(str(state["work_id"]))
            spent, reserved = read_sleep_usage(self.path, work_id, self.authority)
            raw = {
                **raw,
                "state": {**state, "spent_units": spent, "reserved_units": reserved},
            }
        try:
            request = REQUEST_ADAPTER.validate_json(json.dumps(raw))
        except ValidationError as error:
            raise FoundationError("invalid_request", str(error)) from error
        if not isinstance(request, tuple(DEVELOPMENT_INTENTS.values())):
            raise FoundationError(
                "permission_denied", "Only development operations use this endpoint"
            )
        if request.actor != self.authority.actor or request.space_id != self.authority.space_id:
            raise FoundationError("permission_denied", "Development actor/space differs from host")
        if isinstance(request, CreateResourceRequest) and request.state.root != self.workspace:
            raise FoundationError(
                "resource_unavailable", "Resource must be the locally selected working directory"
            )
        if self.assigned_attempt_id is not None:
            if not isinstance(request, (CreateDevelopmentRequest, ReviseDevelopmentRequest)):
                raise FoundationError(
                    "permission_denied", "Assigned Work may save analysis or candidate only"
                )
            if isinstance(request.state, SleepState):
                selected = self._selection(session_id)
                members = {
                    item.work_id
                    for item in read_work_plan(
                        self.path, request.state.work_id, self.authority
                    ).plan.children
                }
                if selected.work_id not in members and selected.work_id != request.state.work_id:
                    raise FoundationError(
                        "wrong_work", "Sleep analysis belongs to the assigned Work family"
                    )
        return apply_operation(self.path, request, self.authority).model_dump(mode="json")

    def development_read(self, session_id: UUID, raw: dict[str, object]) -> dict[str, object]:
        self._session(session_id)
        mode = str(raw["mode"])
        if mode == "list":
            return {
                "items": [
                    item.model_dump(mode="json")
                    for item in list_development(
                        self.path,
                        self.authority,
                        kind=cast(str | None, raw.get("kind")),
                        limit=int(str(raw.get("limit", 50))),
                    )
                ]
            }
        if mode == "read":
            item = read_development(
                self.path,
                UUID(str(raw["record_id"])),
                self.authority,
                revision=int(str(raw["revision"])) if raw.get("revision") else None,
            )
            result = item.model_dump(mode="json")
            if isinstance(item.state, SleepState):
                spent, reserved = read_sleep_usage(self.path, item.state.work_id, self.authority)
                result["live_resource"] = {
                    "spent_units": spent,
                    "reserved_units": reserved,
                    "remaining_units": None
                    if item.state.resource_limit_units is None
                    else item.state.resource_limit_units - spent - reserved,
                }
            return result
        if mode == "application":
            app, history = read_change_application(
                self.path, UUID(str(raw["application_id"])), self.authority
            )
            return {"application": app.model_dump(mode="json"), "history": history}
        if mode == "applications":
            return {
                "items": [
                    item.model_dump(mode="json")
                    for item in list_change_applications(
                        self.path,
                        self.authority,
                        limit=int(str(raw.get("limit", 50))),
                    )
                ]
            }
        if mode == "enumerate":
            return list_sleep_sources(
                self.path,
                UUID(str(raw["record_id"])),
                self.authority,
                purpose=str(raw["purpose"]),
                limit=int(str(raw.get("limit", 20))),
            )
        raise FoundationError("invalid_request", "Unknown development read mode")

    def capture_source(
        self,
        session_id: UUID,
        *,
        channel: str,
        content: str,
        source_event_id: str,
        input_source: str = "interactive",
        limitations: tuple[str, ...] = (),
        replay_session_id: UUID | None = None,
        conversation_final: bool = False,
        final_manifest: KnowledgeRef | None = None,
        conversation_terminal: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        selected = self._session(session_id)
        if channel not in ("conversation_user", "conversation_assistant", "tool_result"):
            raise FoundationError("invalid_request", "Unsupported Pi capture channel")
        if read_space(self.path).schema_version < 10:
            raise FoundationError("unsupported_schema", "Capture needs explicit schema 10")
        if replay_session_id is not None and (
            channel != "conversation_user" or input_source != "session-resume"
        ):
            raise FoundationError("invalid_request", "Replay identity needs saved Pi user input")
        if conversation_terminal is not None:
            if channel != "conversation_assistant":
                raise FoundationError(
                    "invalid_request", "Native terminal must describe an assistant"
                )
            observed_manifest = KnowledgeRef.model_validate(conversation_terminal["manifest"])
            if final_manifest is not None and final_manifest != observed_manifest:
                raise FoundationError("invalid_request", "Terminal manifest differs from capture")
            final_manifest = observed_manifest
            if conversation_terminal["assistant_entry_id"] != source_event_id:
                raise FoundationError(
                    "invalid_request", "Terminal native entry differs from capture"
                )
            conversation_final = (
                conversation_terminal["native_outcome"] == "completed"
                and conversation_terminal["stop_reason"] == "stop"
                and bool(content.strip())
            )
        if conversation_final and (channel != "conversation_assistant" or not content):
            raise FoundationError("invalid_request", "Final proof needs assistant text")
        if final_manifest is not None:
            manifest = read_knowledge(
                self.path,
                final_manifest.record_id,
                self.authority,
                revision=final_manifest.revision,
            )
            if (
                not (conversation_final or conversation_terminal is not None)
                or not isinstance(manifest.state, ContextState)
                or manifest.state.session_id != session_id
            ):
                raise FoundationError(
                    "invalid_request", "Final manifest differs from native session"
                )
            if manifest.state.work_id is not None:
                pinned_work = read_work(self.path, manifest.state.work_id, self.authority)
                selected = Selection(
                    activity_id=pinned_work.state.activity_id, work_id=manifest.state.work_id
                )
            else:
                selected = None
        identity_session = replay_session_id or session_id
        identity = (
            f"pi-resume:{identity_session}:{source_event_id}"
            if replay_session_id is not None
            else f"pi:{session_id}:{source_event_id}"
        )
        source_id = uuid5(self.authority.space_id, identity)
        operation_id = uuid5(source_id, "capture")
        with self.lock:
            derived = set(self.exposed_refs.get(session_id, set()))
            if final_manifest is not None:
                derived.add(final_manifest)
            if channel == "conversation_assistant":
                source = self._request_source(session_id)
                if source is not None:
                    derived.add(source)
        state = SourceState.model_validate(
            {
                "channel": channel,
                "connection": "ordinary-pi",
                "profile_revision": 1,
                "source_event_id": f"{identity_session}:{source_event_id}",
                "conversation_id": str(identity_session),
                "scope_activity_id": selected.activity_id
                if selected and replay_session_id is None
                else None,
                "scope_work_id": selected.work_id
                if selected and replay_session_id is None
                else None,
                "sender": self.authority.actor
                if channel == "conversation_user"
                and input_source in ("interactive", "rpc")
                and self.assigned_attempt_id is None
                and replay_session_id is None
                else "pi-session-history"
                if replay_session_id is not None
                else "pi-rpc"
                if channel == "conversation_user"
                else "pi-assistant"
                if channel == "conversation_assistant"
                else "pi-tool",
                "media_type": "text/plain; charset=utf-8",
                "capture": "full" if content or conversation_terminal is not None else "excluded",
                "content": content.encode()
                if content or conversation_terminal is not None
                else None,
                "limitations": limitations,
                "conversation_final": conversation_final,
                **(
                    {"conversation_terminal": conversation_terminal}
                    if conversation_terminal is not None
                    else {}
                ),
                "derived_from": sorted(derived, key=lambda ref: (str(ref.record_id), ref.revision))
                if channel == "conversation_assistant"
                else (),
            }
        )
        receipt = apply_operation(
            self.path,
            CreateKnowledgeRequest(
                operation_id=operation_id,
                space_id=self.authority.space_id,
                actor=self.authority.actor,
                record_id=source_id,
                state=state,
            ),
            self.authority,
        )
        if channel == "conversation_user":
            with self.lock:
                self.last_sources[session_id] = KnowledgeRef(record_id=source_id, revision=1)
        return {
            **receipt.model_dump(mode="json"),
            "source_ref": KnowledgeRef(record_id=source_id, revision=1).model_dump(mode="json"),
        }

    def knowledge_read(self, session_id: UUID, body: dict[str, Any]) -> dict[str, object]:
        self._session(session_id)
        mode = body.get("mode")
        if mode == "export" or (
            session_id in self.response_only and mode in ("read_batch", "prepare_cache")
        ):
            self._require_model_effect(session_id)
        if self.restricted_core_reads and mode in ("export", "prepare_cache"):
            raise FoundationError("permission_denied", "This node cannot export or prepare caches")
        if mode in (
            "catalog",
            "read_batch",
            "history",
            "open_selection",
            "prepare_cache",
            "export",
        ):
            selectors = tuple(
                MemorySelector.model_validate(value) for value in body.get("selectors", [])
            )
            maximum = int(body.get("max_bytes", 16384))
            if mode == "export":
                destination = (self.workspace / str(body["file"])).resolve()
                if not destination.is_relative_to(self.workspace.resolve()):
                    raise FoundationError(
                        "wrong_scope", "Export must stay in the selected workspace"
                    )
                return export_memory_selection(
                    self.path, UUID(str(body["selection_id"])), self.authority, destination
                )
            if mode == "catalog":
                return memory_catalog(
                    self.path,
                    self.authority,
                    selectors=selectors,
                    limit=int(body.get("limit", 25)),
                    cursor=body.get("cursor"),
                    full=bool(body.get("full", False)),
                )
            if mode == "history":
                return memory_history(
                    self.path,
                    UUID(str(body["record_id"])),
                    self.authority,
                    after_revision=int(body.get("after_revision", 0)),
                    limit=int(body.get("limit", 25)),
                )
            if mode == "open_selection":
                result = open_memory_selection(
                    self.path,
                    UUID(str(body["selection_id"])),
                    self.authority,
                    part=int(body.get("part", 0)),
                    offset=int(body.get("offset", 0)),
                    max_bytes=maximum,
                    toc_offset=int(body.get("toc_offset", 0)),
                )
            else:
                function = prepare_memory_cache if mode == "prepare_cache" else read_memory_batch
                result = function(self.path, self.authority, selectors, max_bytes=maximum)
            with self.lock:
                self.exposed_refs.setdefault(session_id, set()).update(
                    KnowledgeRef.model_validate(ref) for ref in cast(list[Any], result["exposed"])
                )
                if mode in ("read_batch", "open_selection"):
                    self.memory_snapshots.setdefault(session_id, set()).add(
                        KnowledgeRef(
                            record_id=UUID(str(result["selection_id"])),
                            revision=1,
                        )
                    )
                if mode == "prepare_cache":
                    self.memory_rules.setdefault(session_id, {})[
                        json.dumps([s.model_dump(mode="json") for s in selectors], sort_keys=True)
                    ] = selectors
            return result
        if mode == "list":
            return list_knowledge(
                self.path,
                self.authority,
                kind=body.get("kind"),
                limit=int(body.get("limit", 25)),
                cursor=body.get("cursor"),
            )
        if mode == "search":
            return search_knowledge(
                self.path,
                self.authority,
                str(body["query"]),
                limit=int(body.get("limit", 25)),
                cursor=str(body["cursor"]) if body.get("cursor") is not None else None,
            )
        record_id = UUID(str(body["record_id"]))
        if mode == "open":
            result = open_knowledge(
                self.path,
                record_id,
                self.authority,
                revision=int(body["revision"]) if body.get("revision") else None,
                offset=int(body.get("offset", 0)),
                max_bytes=int(body.get("max_bytes", 16384)),
            )
            if result.get("content_base64") is not None:
                start = int(cast(int, result["offset"]))
                end = start + len(base64.b64decode(str(result["content_base64"])))
                complete = start == 0 and end == result["total_bytes"]
                reference = KnowledgeRef(
                    record_id=record_id,
                    revision=cast(int, result["revision"]),
                    start=None if complete else start,
                    end=None if complete else end,
                )
                result["exposed"] = [reference.model_dump(mode="json")]
                with self.lock:
                    self.exposed_refs.setdefault(session_id, set()).add(reference)
            return result
        if mode == "neighbors":
            return read_knowledge_neighbors(
                self.path,
                record_id,
                self.authority,
                limit=int(body.get("limit", 25)),
                cursor=str(body["cursor"]) if body.get("cursor") is not None else None,
            )
        raise FoundationError("invalid_request", "Unknown knowledge read")

    def prepare_context(
        self,
        session_id: UUID,
        purpose: str = "content",
        historical_memory: tuple[KnowledgeRef, ...] = (),
    ) -> dict[str, object]:
        selected = self._session(session_id)
        if self.request_origins.get(session_id) == "host":
            selected = None
        info = read_space(self.path)
        if info.schema_version < 10:
            raise FoundationError("unsupported_schema", "Context needs explicit schema 10")
        mandatory: list[KnowledgeRef] = []
        structure_pin: KnowledgeRef | None = None
        procedure_snapshot: KnowledgeRef | None = None
        evidence_refs: list[KnowledgeRef] = []
        included_conversation: list[Any] = []
        packet: dict[str, object] = {
            "space_id": str(info.space_id),
            "epoch": info.execution_epoch,
            "purpose": purpose,
        }
        recovery_work = self.recovery_obstacles.get(session_id)
        if recovery_work is not None:
            recovery = read_execution(self.path, recovery_work, self.authority)
            packet["recovery_obstacle"] = {
                "work_id": str(recovery_work),
                "goal": recovery.work.state.goal,
                "reason": "The former window left an active execution without exact final proof. "
                "No request was repeated and no Work was accepted. Read its saved result; "
                "interrupt_execution requires an actual addressed owner request and confirmation.",
                "attempts": [
                    item.model_dump(mode="json")
                    for item in recovery.attempts
                    if item.status == "active"
                ],
                "invocations": [
                    item.model_dump(mode="json") for item in recovery.invocations[-10:]
                ],
                "invocation_count": len(recovery.invocations),
            }
        if info.schema_version >= 13:
            packet["memory_access"] = (
                "Shared memory: use zara_memory catalog/read_batch/prepare_cache/history/"
                "open_selection/export. "
                "Select common or Activity areas/topics/addresses together; full includes history. "
                "Use memory relevant to this request; do not load the whole catalog by default."
            )
        if info.schema_version >= 15:
            packet["data_access"] = (
                "Use zara_data for declared formats, typed entries, exact queries/calculations "
                "and durable procedures. Use contract to read operation schemas. "
                "Plan periods and event dates are explicit; "
                "never turn missing observations into zero."
            )
        with self.lock:
            latest_source = self._request_source(session_id)
            origin_sources = self.request_sources.get(session_id, ())
        if info.schema_version >= 17:
            mandatory.extend(origin_sources)
            packet["request_origin"] = {
                "kind": self.request_origins.get(session_id, "history"),
                "sources": [ref.model_dump(mode="json") for ref in origin_sources],
            }
            response = self.response_only.get(session_id)
            if response is not None:
                host = self.conversation_hosts.get(session_id)
                if host is None or (host["branch_id"], int(host.get("generation", -1))) != (
                    response["branch_id"],
                    response["generation"],
                ):
                    raise FoundationError("stale_session", "Reply repair native branch changed")
                from zaratustra.foundation import read_terminal_response

                proof = read_terminal_response(
                    self.path,
                    response["assistant_source"],
                    self.authority,
                    session_id=session_id,
                    invocation_id=response["invocation_id"],
                    manifest=response["manifest"],
                    assistant_entry_id=response["assistant_entry_id"],
                )
                if proof.outcome != "empty" or proof.diagnostics:
                    raise FoundationError(
                        "response_not_repairable", "Reply repair proof is unavailable"
                    )
                mandatory.extend(response["owner_sources"])
                mandatory.extend((response["assistant_source"], response["manifest"]))
                packet["response_recovery"] = {
                    **proof.model_dump(mode="json"),
                    "owner_sources": [
                        ref.model_dump(mode="json") for ref in response["owner_sources"]
                    ],
                    "instruction": "Finish the same owner's conversation with a visible reply. "
                    "Read the current saved facts and exact prior result. This request permits "
                    "only reading and explaining: do not repeat effects, answer a user wait, "
                    "publish a result, accept Work or start execution.",
                }
            if purpose != "compaction-summary" and self.assigned_attempt_id is None:
                from zaratustra.foundation import (
                    read_conversation_action,
                    read_conversation_actions_page,
                )

                action_page = read_conversation_actions_page(self.path, self.authority, limit=20)
                actions = list(action_page.actions)
                packet["conversation_next_offset"] = action_page.next_offset
                host_ref = (
                    self.conversation_actions.get(session_id)
                    if self.request_origins.get(session_id) == "host"
                    else None
                )
                from .conversation import delivery_summaries

                repair = None
                if host_ref is not None:
                    host_action = read_conversation_action(self.path, host_ref, self.authority)
                    host_deliveries = delivery_summaries(self, [host_action])
                    repair = host_deliveries[0] if host_deliveries else None
                    host = self.conversation_hosts.get(session_id)
                    if (
                        repair is None
                        or repair["status"] not in ("claimed", "included")
                        or repair["response_outcome"] not in ("unproven", "empty")
                        or repair["diagnostics"]
                        or repair["session_id"] != str(session_id)
                        or host is None
                        or any(repair[key] != host[key] for key in ("host_id", "branch_id"))
                    ):
                        host_ref = None
                if host_ref is not None:
                    if all(item.ref != host_ref for item in actions):
                        actions.insert(0, host_action)
                    packet["conversation_event"] = host_action.model_dump(mode="json")
                    included_conversation.append(host_action)
                packet["conversation_actions"] = [item.model_dump(mode="json") for item in actions]
                packet["conversation_delivery_outcomes"] = delivery_summaries(self, actions)
                if host_ref is not None:
                    repair_number = int(cast(int, repair.get("repair_count", 0))) if repair else 0
                    if repair is not None and repair_number > 0:
                        for key in ("response_source", "manifest"):
                            if repair.get(key) is not None:
                                mandatory.append(KnowledgeRef.model_validate(repair[key]))
                    packet["conversation_task"] = {
                        "kind": "explain_saved_action",
                        "action_ref": host_ref.model_dump(mode="json"),
                        "response_required": True,
                        "instruction": "Produce a visible conversational response now. Explain "
                        "this exact saved result or question and the next useful step. "
                        "Use the current saved facts and selected originals; do not create Work "
                        "or act as the owner. This task is a trusted host continuation, "
                        "not another owner message. A silent or thinking-only final is incomplete.",
                        "repair": {
                            "number": repair_number,
                            "previous_source": repair["response_source"],
                            "previous_manifest": repair["manifest"],
                            "response_outcome": repair["response_outcome"],
                            "diagnostics": repair["diagnostics"],
                        }
                        if repair is not None and repair_number > 0
                        else None,
                    }
                packet["conversation_guidance"] = (
                    "These are current Core facts, not owner messages. Explain the result and next "
                    "useful step in ordinary conversation. Lost notifications do not lose results. "
                    "Use zara_conversation catalog/read/use_existing_work to select existing Work "
                    "only from an actual owner request; never duplicate it or accept it. "
                    "Host/history origins cannot answer a user's wait or authorize new Work."
                )
                for action_item in included_conversation:
                    mandatory.extend(action_item.bases)
        elif latest_source is not None:
            mandatory.append(latest_source)
        if info.schema_version >= 14 and selected is None and purpose != "compaction-summary":
            pending = list_activity_setups(self.path, self.authority, pending_only=True, limit=2)
            if len(pending) == 1:
                pending_setup = pending[0]
                activity = read_activity(self.path, pending_setup.state.activity_id, self.authority)
                packet["activity_setup"] = {
                    "setup_id": str(pending_setup.setup_id),
                    "revision": pending_setup.revision,
                    "activity_id": str(pending_setup.state.activity_id),
                    "goal": activity.state.goal,
                    "phase": pending_setup.state.phase,
                    "question": pending_setup.state.question,
                    "reviews_started": pending_setup.state.reviews_started,
                    "source_refs": [
                        ref.model_dump(mode="json") for ref in pending_setup.state.sources
                    ],
                }
                mandatory.append(
                    KnowledgeRef(record_id=activity.activity_id, revision=activity.revision)
                )
        # A cache explicitly used in this conversation is rechecked before each send.
        # New matches are refreshed by ordinary code; old tool messages remain historical.
        with self.lock:
            rules = dict(self.memory_rules.get(session_id, {}))
            snapshots = set(self.memory_snapshots.get(session_id, set()))
        snapshots.update(historical_memory)
        historic = tuple(sorted(snapshots, key=lambda ref: str(ref.record_id)))
        # Native Pi persists tool responses across sessions. Recover the saved cache
        # rule from Core, while retaining its old revision as historical provenance.
        for historic_ref in historic:
            saved = read_knowledge(
                self.path, historic_ref.record_id, self.authority, revision=historic_ref.revision
            )
            if (
                isinstance(saved.state, MemoryViewState)
                and saved.state.selection is not None
                and saved.state.selection.cache
            ):
                selectors = saved.state.selection.selectors
                rules[
                    json.dumps([s.model_dump(mode="json") for s in selectors], sort_keys=True)
                ] = selectors
        if historic:
            packet["memory_snapshots"] = [ref.model_dump(mode="json") for ref in historic]
        if info.schema_version >= 13 and purpose != "compaction-summary":
            packet["conversation_memory"] = []
            for selectors in rules.values():
                selected_memory = prepare_memory_cache(self.path, self.authority, selectors)
                mandatory.append(
                    KnowledgeRef(
                        record_id=UUID(str(selected_memory["selection_id"])),
                        revision=1,
                    )
                )
                cast(list[Any], packet["conversation_memory"]).append(
                    {key: value for key, value in selected_memory.items() if key != "exposed"}
                )
        if selected is not None and purpose == "compaction-summary":
            current = read_execution(self.path, selected.work_id, self.authority)
            work = current.work
            if info.schema_version >= 15:
                structure_pin = work.state.structure
                from zaratustra.foundation import procedure_for_work

                run = procedure_for_work(self.path, self.authority, selected.work_id)
                if run is not None:
                    procedure_snapshot = KnowledgeRef.model_validate(run["snapshot"])
                    packet["procedure_address"] = run["run_id"]
            mandatory.extend(
                (
                    KnowledgeRef(
                        record_id=current.activity.activity_id, revision=current.activity.revision
                    ),
                    KnowledgeRef(record_id=work.work_id, revision=work.revision),
                )
            )
            packet["work_address"] = f"{work.work_id}@{work.revision}"
            packet["activity_address"] = (
                f"{current.activity.activity_id}@{current.activity.revision}"
            )
            if work.state.method != "none":
                packet["method_address"] = work.state.method.model_dump(mode="json")
            if current.composition is not None:
                packet["plan_address"] = {
                    "work_id": str(current.composition.parent_work_id),
                    "revision": current.composition.plan_revision,
                    "method": current.composition.method.model_dump(mode="json"),
                }
        elif selected is not None:
            activity = read_activity(self.path, selected.activity_id, self.authority)
            work = read_work(self.path, selected.work_id, self.authority)
            current = read_execution(self.path, selected.work_id, self.authority)
            if current.work.unavailable_refs or len(current.inputs) != len(work.state.inputs):
                raise FoundationError("incomplete_context", "Required Work input is unavailable")
            mandatory.extend(
                (
                    KnowledgeRef(record_id=activity.activity_id, revision=activity.revision),
                    KnowledgeRef(record_id=work.work_id, revision=work.revision),
                )
            )
            packet["activity"] = activity.model_dump(mode="json")
            packet["work"] = work.model_dump(mode="json")
            packet["output_publication_contracts"] = output_publication_contracts(work.state)
            if info.schema_version >= 15:
                from zaratustra.foundation import describe_structure

                description = describe_structure(
                    self.path, selected.activity_id, self.authority, work_id=selected.work_id
                )
                if not description["legacy"]:
                    structure_pin = KnowledgeRef.model_validate(description["structure"])
                    packet["activity_structure"] = description
                from zaratustra.foundation import procedure_for_work

                run = procedure_for_work(self.path, self.authority, selected.work_id)
                if run is not None:
                    procedure_snapshot = KnowledgeRef.model_validate(run["snapshot"])
                    packet["procedure"] = run
                    selected_input = open_memory_selection(
                        self.path, procedure_snapshot.record_id, self.authority, max_bytes=16384
                    )
                    packet["procedure_input"] = selected_input
            packet["status"] = current.status.model_dump(mode="json") if current.status else None
            packet["composition"] = (
                current.composition.model_dump(mode="json") if current.composition else None
            )
            if work.state.method != "none":
                method = read_method_version(self.path, work.state.method, self.authority)
                packet["method"] = method.model_dump(mode="json")
                if current.composition is not None:
                    packet["plan"] = read_work_plan(
                        self.path, selected.work_id, self.authority
                    ).model_dump(mode="json")
            elif current.composition is not None:
                method = read_method_version(self.path, current.composition.method, self.authority)
                packet["method"] = method.model_dump(mode="json")
                packet["plan"] = read_work_plan(
                    self.path, current.composition.parent_work_id, self.authority
                ).model_dump(mode="json")
            if info.schema_version >= 13:
                packet["memory"] = []
                requirements = (
                    activity_setup_memory(
                        self.path, selected.activity_id, self.authority, work_id=selected.work_id
                    )
                    if info.schema_version >= 14
                    else ()
                )
                if work.state.method != "none" or current.composition is not None:
                    requirements = tuple(
                        dict.fromkeys(requirements + method.definition.memory_requirements)
                    )
                if requirements:
                    for requirement in requirements:
                        selectors = tuple(
                            selector.model_copy(
                                update={
                                    "current_activity": False,
                                    "activity_ids": selector.activity_ids + (selected.activity_id,),
                                }
                            )
                            if selector.current_activity
                            else selector
                            for selector in requirement.selectors
                        )
                        try:
                            cached = prepare_memory_cache(self.path, self.authority, selectors)
                        except FoundationError as error:
                            if requirement.required or error.code not in (
                                "permission_denied",
                                "decision_denied",
                                "not_found",
                                "content_unavailable",
                            ):
                                raise
                            cast(list[Any], packet["memory"]).append(
                                {
                                    "required": False,
                                    "available": False,
                                    "reason": error.code,
                                }
                            )
                            continue
                        selection_id = UUID(str(cached["selection_id"]))
                        cache_ref = KnowledgeRef(
                            record_id=selection_id, revision=int(str(cached["revision"]))
                        )
                        mandatory.append(cache_ref)
                        cast(list[Any], packet["memory"]).append(
                            {
                                **{key: value for key, value in cached.items() if key != "exposed"},
                                "selection": cache_ref.model_dump(mode="json"),
                                "text": cached["content_text"],
                                "content_complete": cached["content_complete"],
                                "next_part": cached["next_part"],
                                "next_offset": cached["next_offset"],
                                "required": requirement.required,
                            }
                        )
                required = memory_required_refs(self.path, self.authority, selected.activity_id)
                constraints = prepare_memory_cache(
                    self.path,
                    self.authority,
                    (
                        MemorySelector(
                            activity_ids=(selected.activity_id,),
                            common=True,
                            context_role="required",
                        ),
                    ),
                )
                constraint_id = UUID(str(constraints["selection_id"]))
                mandatory.append(
                    KnowledgeRef(
                        record_id=constraint_id, revision=int(str(constraints["revision"]))
                    )
                )
                mandatory.extend(required)
                evidence_refs.extend(required)
                packet["memory_constraints"] = [
                    read_knowledge(
                        self.path, ref.record_id, self.authority, revision=ref.revision
                    ).model_dump(mode="json")
                    for ref in required
                ]
                intake = memory_catalog(
                    self.path,
                    self.authority,
                    selectors=(MemorySelector(activity_ids=(selected.activity_id,), common=True),),
                    unprocessed_only=True,
                )
                packet["memory_intake"] = intake
                for entry in cast(list[dict[str, Any]], intake["items"]):
                    mandatory.append(
                        KnowledgeRef(record_id=UUID(entry["record_id"]), revision=entry["revision"])
                    )
            inputs: list[dict[str, object]] = []
            if info.schema_version >= 16:
                from zaratustra.foundation import read_workflow_continuation_for_work

                continuation = read_workflow_continuation_for_work(
                    self.path, selected.work_id, self.authority
                )
                if continuation is not None:
                    exact_continuation = read_artifact(
                        self.path,
                        continuation.artifact_id,
                        self.authority,
                        revision=continuation.revision,
                    )
                    if exact_continuation.content is None:
                        raise FoundationError(
                            "incomplete_context", "Native continuation is unavailable"
                        )
                    mandatory.append(
                        KnowledgeRef(
                            record_id=continuation.artifact_id, revision=continuation.revision
                        )
                    )
                    packet["workflow_continuation"] = {
                        "reference": continuation.model_dump(mode="json"),
                        "content_text": exact_continuation.content.decode("utf-8"),
                    }
                    partial_materials: list[dict[str, Any]] = []
                    for raw_partial in json.loads(exact_continuation.content)["partial_refs"]:
                        partial_ref = ArtifactRef.model_validate(raw_partial)
                        partial = read_artifact(
                            self.path,
                            partial_ref.artifact_id,
                            self.authority,
                            revision=partial_ref.revision,
                        )
                        if partial.content is None:
                            raise FoundationError(
                                "incomplete_context", "Native partial is unavailable"
                            )
                        mandatory.append(
                            KnowledgeRef(
                                record_id=partial_ref.artifact_id, revision=partial_ref.revision
                            )
                        )
                        partial_materials.append(
                            {
                                "reference": partial_ref.model_dump(mode="json"),
                                "content_base64": base64.b64encode(partial.content).decode("ascii"),
                            }
                        )
                    cast(dict[str, Any], packet["workflow_continuation"])["partials"] = (
                        partial_materials
                    )
            for ref in work.state.inputs:
                exact = read_artifact(
                    self.path, ref.artifact_id, self.authority, revision=ref.revision
                )
                mandatory.append(KnowledgeRef(record_id=ref.artifact_id, revision=ref.revision))
                item = exact.model_dump(mode="json", exclude={"content"})
                item["content_text"] = (
                    exact.content.decode("utf-8")
                    if exact.content is not None
                    and exact.media_type
                    and (
                        exact.media_type.startswith("text/")
                        or exact.media_type == "application/json"
                    )
                    else None
                )
                inputs.append(item)
            packet["inputs"] = inputs
            inspection = inspect_space(self.path, self.authority)
            decisions: list[dict[str, object]] = []
            for row in inspection.records:
                if row.kind != "decision":
                    continue
                decision = read_decision(self.path, row.record_id, self.authority)
                relevant = (
                    (
                        isinstance(decision.state, DecisionState)
                        and decision.state.status == "active"
                        and (
                            "*" in decision.state.subjects
                            or self.authority.actor in decision.state.subjects
                        )
                    )
                    or (
                        isinstance(decision.state, ChoiceState)
                        and decision.state.status == "active"
                        and (
                            (
                                decision.state.scope.kind == "activity"
                                and decision.state.scope.record_id == selected.activity_id
                            )
                            or (
                                decision.state.scope.kind == "work"
                                and decision.state.scope.record_id == selected.work_id
                            )
                        )
                    )
                    or (
                        isinstance(decision.state, ChangeDecisionState)
                        and decision.state.status == "active"
                        and (
                            decision.state.scope_global
                            or decision.state.scope_activity_id == selected.activity_id
                        )
                    )
                )
                if relevant:
                    mandatory.append(
                        KnowledgeRef(record_id=row.record_id, revision=decision.revision)
                    )
                    decisions.append(decision.model_dump(mode="json"))
            packet["decisions"] = decisions
            rights = read_current_rights(self.path, self.authority)
            packet["rights"] = rights
            for grant in cast(list[dict[str, Any]], rights["grants"]):
                mandatory.append(
                    KnowledgeRef(
                        record_id=UUID(grant["record_id"]), revision=int(grant["revision"])
                    )
                )
            # Current Claims in the selected Activity and global Claims have a structural
            # route into this continuation; every selected basis remains in the packet.
            cursor: str | None = None
            claims: list[dict[str, object]] = []
            while True:
                page = (
                    memory_catalog(
                        self.path,
                        self.authority,
                        selectors=(
                            MemorySelector(
                                activity_ids=(selected.activity_id,),
                                common=True,
                                context_role="legacy",
                            ),
                        ),
                        limit=100,
                        cursor=cursor,
                    )
                    if info.schema_version >= 13
                    else list_knowledge(
                        self.path, self.authority, kind="claim", limit=100, cursor=cursor
                    )
                )
                for entry in cast(list[dict[str, Any]], page["items"]):
                    if entry["kind"] != "claim":
                        continue
                    claim_item = read_knowledge(self.path, UUID(entry["record_id"]), self.authority)
                    state = claim_item.state
                    if (
                        isinstance(state, ClaimState)
                        and state.memory is None
                        and (state.scope_global or state.scope_activity_id == selected.activity_id)
                        and state.status in ("current", "contested", "unsupported")
                    ):
                        mandatory.append(
                            KnowledgeRef(
                                record_id=claim_item.record_id, revision=claim_item.revision
                            )
                        )
                        claims.append(claim_item.model_dump(mode="json"))
                        for evidence_ref in state.evidence + state.counter_evidence:
                            mandatory.append(evidence_ref)
                            evidence_refs.append(evidence_ref)
                cursor = cast(str | None, page["next_cursor"])
                if cursor is None:
                    break
            packet["claims"] = claims
        if selected is not None and info.schema_version >= 11:
            sleep = read_sleep_for_work(self.path, selected.work_id, self.authority)
            if sleep is not None:
                mandatory.append(KnowledgeRef(record_id=sleep.record_id, revision=sleep.revision))
                packet["sleep_analysis"] = sleep.model_dump(mode="json")
                if isinstance(sleep.state, SleepState):
                    spent, reserved = read_sleep_usage(
                        self.path, sleep.state.work_id, self.authority
                    )
                    packet["sleep_resource"] = {
                        "spent_units": spent,
                        "reserved_units": reserved,
                        "remaining_units": None
                        if sleep.state.resource_limit_units is None
                        else sleep.state.resource_limit_units - spent - reserved,
                    }
                    role = current.composition.role if current.composition else None
                    selected_sources: list[dict[str, object]] = []
                    for sleep_selection in sleep.state.selected:
                        if role is not None and sleep_selection.purpose != role:
                            continue
                        record = read_knowledge(
                            self.path,
                            sleep_selection.source.record_id,
                            self.authority,
                            revision=sleep_selection.source.revision,
                        )
                        mandatory.append(sleep_selection.source)
                        selected_sources.append(record.model_dump(mode="json"))
                    packet["sleep_sources"] = selected_sources
            if purpose != "compaction-summary":
                applications: list[dict[str, object]] = []
                for app in list_change_applications(self.path, self.authority):
                    if app.status != "active":
                        continue
                    decision = read_decision(self.path, app.decision_id, self.authority)
                    if (
                        isinstance(decision.state, ChangeDecisionState)
                        and decision.revision == app.decision_revision
                        and decision.state.status == "active"
                        and (
                            decision.state.scope_global
                            or decision.state.scope_activity_id == selected.activity_id
                        )
                    ):
                        mandatory.append(
                            KnowledgeRef(record_id=app.decision_id, revision=app.decision_revision)
                        )
                        applications.append(app.model_dump(mode="json"))
                packet["active_changes"] = applications
        if not mandatory:
            raise FoundationError("incomplete_context", "No received prompt or selected Work")
        if latest_source is not None:
            source = read_knowledge(self.path, latest_source.record_id, self.authority)
            packet["prompt_source"] = source.model_dump(mode="json", exclude={"state"})
            if isinstance(source.state, SourceState):
                packet["prompt_source_state"] = source.state.model_dump(
                    mode="json", exclude={"content"}
                )
                packet["prompt_text"] = (
                    source.state.content.decode("utf-8") if source.state.content else None
                )
        additional: list[dict[str, object]] = []
        input_keys = (
            {(ref.artifact_id, ref.revision) for ref in work.state.inputs} if selected else set()
        )
        for required_ref in dict.fromkeys(evidence_refs):
            if (
                required_ref == latest_source
                or (required_ref.record_id, required_ref.revision) in input_keys
            ):
                continue
            try:
                required_item = read_knowledge(
                    self.path,
                    required_ref.record_id,
                    self.authority,
                    revision=required_ref.revision,
                )
            except FoundationError as error:
                if error.code == "not_found":
                    try:
                        artifact = read_artifact(
                            self.path,
                            required_ref.record_id,
                            self.authority,
                            revision=required_ref.revision,
                        )
                    except FoundationError as missing:
                        if missing.code == "not_found":
                            continue
                        raise
                    if artifact.content is None:
                        raise FoundationError(
                            "incomplete_context", "Mandatory Artifact is unavailable"
                        ) from None
                    artifact_bytes = artifact.content
                    fragment = (
                        artifact_bytes[required_ref.start : required_ref.end]
                        if required_ref.start is not None
                        else artifact_bytes
                    )
                    additional.append(
                        {
                            "record_id": str(required_ref.record_id),
                            "revision": required_ref.revision,
                            "text": fragment.decode("utf-8")
                            if artifact.media_type and artifact.media_type.startswith("text/")
                            else None,
                            "bytes_base64": base64.b64encode(fragment).decode("ascii")
                            if not artifact.media_type
                            or not artifact.media_type.startswith("text/")
                            else None,
                        }
                    )
                    continue
                raise
            if isinstance(required_item.state, SourceState):
                source_bytes = required_item.state.content
                if source_bytes is None:
                    raise FoundationError(
                        "incomplete_context", "Mandatory source lacks retained bytes"
                    )
                fragment = (
                    source_bytes[required_ref.start : required_ref.end]
                    if required_ref.start is not None
                    else source_bytes
                )
                additional.append(
                    {
                        "record_id": str(required_ref.record_id),
                        "revision": required_ref.revision,
                        "fragment": {"start": required_ref.start, "end": required_ref.end},
                        "text": fragment.decode("utf-8")
                        if required_item.state.media_type.startswith("text/")
                        else None,
                        "bytes_base64": base64.b64encode(fragment).decode("ascii")
                        if not required_item.state.media_type.startswith("text/")
                        else None,
                    }
                )
        packet["primary_sources"] = additional
        rendered = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
        if (
            self.context_max_bytes is not None
            and len(rendered.encode("utf-8")) > self.context_max_bytes
        ):
            raise FoundationError(
                "context_overflow", "Mandatory context exceeds configured byte limit"
            )
        context_state = ContextState(
            purpose="compaction summary"
            if purpose == "compaction-summary"
            else "selected Work continuation"
            if selected
            else "conversation continuation",
            session_id=session_id,
            work_id=selected.work_id if selected else None,
            attempt_id=next(
                (
                    item.attempt_id
                    for item in current.attempts
                    if item.session_id == session_id and item.status == "active"
                ),
                None,
            )
            if selected
            else None,
            method=(
                work.state.method
                if selected and work.state.method != "none"
                else current.composition.method
                if selected and current.composition
                else None
            ),
            plan_revision=current.composition.plan_revision
            if selected and current.composition
            else None,
            mandatory=tuple(dict.fromkeys(mandatory)),
            historical_memory=historic,
            pinned_structure=structure_pin,
            procedure_snapshot=procedure_snapshot,
            max_bytes=self.context_max_bytes,
            conversation_actions=tuple(item.ref for item in included_conversation)
            if info.schema_version >= 17
            and purpose != "compaction-summary"
            and self.assigned_attempt_id is None
            else (),
        )
        # Reuse unchanged packets, but identity must also cover exact persisted
        # pins that need not appear in model prose (for example an Attempt).
        identity_bytes = rendered.encode("utf-8")
        if info.schema_version >= 17:
            canonical_state = json.dumps(
                context_state.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            identity_bytes += b"\0" + canonical_state
        manifest_id = uuid5(
            session_id,
            f"context:{self.context_max_bytes}:{hashlib.sha256(identity_bytes).hexdigest()}",
        )
        receipt = apply_operation(
            self.path,
            CreateKnowledgeRequest(
                operation_id=uuid5(manifest_id, "prepare"),
                space_id=info.space_id,
                actor=self.authority.actor,
                record_id=manifest_id,
                state=context_state,
            ),
            self.authority,
        )
        with self.lock:
            self.exposed_refs.setdefault(session_id, set()).update(mandatory)
            self.exposed_refs[session_id].update(historic)
        return {
            "manifest_id": str(manifest_id),
            "manifest_revision": 1,
            "state_revision": receipt.state_revision,
            "packet": packet,
            "byte_count": len(rendered.encode("utf-8")),
        }

    def context_delivery(self, session_id: UUID, raw: dict[str, Any]) -> dict[str, object]:
        self._session(session_id)
        manifest = read_knowledge(
            self.path,
            UUID(str(raw["manifest_id"])),
            self.authority,
            revision=int(raw["manifest_revision"]),
        )
        if not isinstance(manifest.state, ContextState) or manifest.state.session_id != session_id:
            raise FoundationError("wrong_scope", "Invocation manifest differs from native session")
        free_call = manifest.state.work_id is None
        request = RecordContextDeliveryRequest.model_validate(
            {
                "operation_id": str(uuid4()),
                "space_id": str(self.authority.space_id),
                "actor": self.authority.actor,
                "invocation_id": raw["invocation_id"],
                "manifest": {"record_id": raw["manifest_id"], "revision": raw["manifest_revision"]},
                "stage": raw["stage"],
                "request_sha256": raw.get("request_sha256"),
                "request_bytes": raw.get("request_bytes"),
                "free_call": free_call,
                "reserve_units": int(raw.get("reserve_units", 0)) if free_call else 0,
                "usage_units": raw.get("usage_units"),
                "budget_limit_units": self.free_conversation_limit_units if free_call else 0,
                "trial_total_send_limit": self.trial_total_send_limit,
            }
        )
        return apply_operation(self.path, request, self.authority).model_dump(mode="json")

    def start_attempt(self, session_id: UUID, *, interrupt_previous: bool) -> dict[str, object]:
        if interrupt_previous:
            self._require_model_effect(session_id)
        if self.assigned_attempt_id is not None:
            raise FoundationError("permission_denied", "Assigned RPC already has an Attempt")
        selected = self._selection(session_id)
        snapshot = read_execution(self.path, selected.work_id, self.authority)
        resource = next(
            (
                item
                for item in snapshot.resources
                if item.state.root == self.workspace and item.state.status == "active"
            ),
            None,
        )
        if resource is None:
            raise FoundationError("resource_unavailable", "Selected resource is not current")
        previous = snapshot.attempts[-1] if snapshot.attempts else None
        if previous is not None and previous.status == "active":
            if not interrupt_previous:
                raise FoundationError(
                    "active_attempt", "Previous Attempt needs explicit interruption"
                )
            stop = StopAttemptRequest(
                operation_id=uuid5(previous.attempt_id, "interrupt-for-new-session"),
                space_id=self.authority.space_id,
                actor=self.authority.actor,
                attempt_id=previous.attempt_id,
                work_id=selected.work_id,
                session_id=previous.session_id,
                outcome="interrupted",
            )
            apply_operation(self.path, stop, self.authority)
        attempt_id = UUID(bytes=secrets.token_bytes(16))
        start = StartAttemptRequest(
            operation_id=uuid5(attempt_id, "start"),
            space_id=self.authority.space_id,
            actor=self.authority.actor,
            attempt_id=attempt_id,
            work_id=selected.work_id,
            expected_work_revision=snapshot.work.revision,
            resource_id=resource.resource_id,
            expected_resource_revision=resource.revision,
            session_id=session_id,
            previous_attempt_id=previous.attempt_id if previous else None,
        )
        receipt = apply_operation(self.path, start, self.authority)
        return {"attempt_id": str(attempt_id), "receipt": receipt.model_dump(mode="json")}

    def publish(
        self, session_id: UUID, attempt_id: UUID, slot: str, media_type: str, content: str
    ) -> dict[str, object]:
        self._require_model_effect(session_id)
        selected = self._selection(session_id)
        if self.assigned_attempt_id is not None and attempt_id != self.assigned_attempt_id:
            raise FoundationError("permission_denied", "RPC cannot publish another Attempt")
        data = content.encode("utf-8")
        setup_stage = (
            read_setup_stage(self.path, selected.work_id, self.authority)
            if self.assigned_attempt_id is not None
            else None
        )
        raw_setup = setup_stage is not None and setup_stage.result_protocol == "setup_json"
        raw_workflow = (
            self.assigned_attempt_id is not None
            and read_workflow_node_for_work(self.path, selected.work_id, self.authority) is not None
        )
        if (not data and not (raw_setup or raw_workflow)) or len(data) > 8 * 1024 * 1024:
            raise FoundationError("invalid_request", "Result is empty or too large")
        publication = PublishAttemptOutputRequest(
            operation_id=uuid5(attempt_id, f"publish:{slot}"),
            space_id=self.authority.space_id,
            actor=self.authority.actor,
            attempt_id=attempt_id,
            work_id=selected.work_id,
            session_id=session_id,
            slot=slot,
            media_type=media_type,
            content=data,
        )
        receipt = apply_operation(self.path, publication, self.authority)
        return {"publication": receipt.model_dump(mode="json")}

    def open_wait(
        self,
        session_id: UUID,
        attempt_id: UUID,
        wait_id: UUID,
        partial: str,
        question: str,
        remainder: str,
    ) -> dict[str, object]:
        selected = self._selection(session_id)
        if self.assigned_attempt_id != attempt_id or self.assigned_session_id != session_id:
            raise FoundationError("permission_denied", "Only the assigned RPC can open its wait")
        data = partial.encode("utf-8")
        if not data or len(data) > 8 * 1024 * 1024:
            raise FoundationError("invalid_request", "Partial result is empty or too large")
        artifact_id = uuid5(wait_id, "partial-artifact")
        artifact = CreateArtifactRequest(
            operation_id=uuid5(wait_id, "partial-create"),
            space_id=self.authority.space_id,
            actor=self.authority.actor,
            artifact_id=artifact_id,
            media_type="text/plain",
            content=data,
            provenance=(
                ProvenanceRef(relation="pi-rpc-partial", external_ref=f"attempt:{attempt_id}"),
            ),
        )
        created = apply_operation(self.path, artifact, self.authority)
        snapshot = read_execution(self.path, selected.work_id, self.authority)
        assignment = next(
            (item for item in snapshot.assignments if item.attempt_id == attempt_id), None
        )
        if assignment is None:
            raise FoundationError("stale_attempt", "Assignment is unavailable")
        request = OpenWaitRequest(
            operation_id=uuid5(wait_id, "open"),
            space_id=self.authority.space_id,
            actor=self.authority.actor,
            wait_id=wait_id,
            attempt_id=attempt_id,
            work_id=selected.work_id,
            session_id=session_id,
            expected_assignment_revision=assignment.revision,
            question=question,
            expected_actor=self.authority.actor,
            remainder=remainder,
            partial_refs=(ArtifactRef(artifact_id=artifact_id, revision=1),),
        )
        opened = apply_operation(self.path, request, self.authority)
        return {
            "partial": created.model_dump(mode="json"),
            "wait": opened.model_dump(mode="json"),
        }

    def answer_wait(self, session_id: UUID, wait_id: UUID, answer: str) -> dict[str, object]:
        if session_id in self.response_only:
            raise FoundationError("permission_denied", "Response repair cannot answer a user wait")
        selected = self._selection(session_id)
        if self.assigned_attempt_id is not None:
            raise FoundationError("permission_denied", "RPC cannot answer its own question")
        snapshot = read_execution(self.path, selected.work_id, self.authority)
        wait = next((item for item in snapshot.waits if item.wait_id == wait_id), None)
        if wait is None:
            raise FoundationError("stale_wait", "Question is unavailable")
        operation_id = uuid5(wait_id, "addressed-answer")
        if wait.status == "answered":
            if wait.answer != answer:
                raise FoundationError("stale_wait", "Question already has another answer")
            receipt = read_receipt(self.path, operation_id, self.authority)
        else:
            attempt = next(
                (item for item in snapshot.attempts if item.attempt_id == wait.attempt_id), None
            )
            if attempt is None:
                raise FoundationError("stale_attempt", "Question has no current Attempt")
            request = AnswerWaitRequest(
                operation_id=operation_id,
                space_id=self.authority.space_id,
                actor=self.authority.actor,
                wait_id=wait_id,
                attempt_id=wait.attempt_id,
                work_id=selected.work_id,
                session_id=attempt.session_id,
                expected_wait_revision=wait.revision,
                answer=answer,
            )
            receipt = apply_operation(self.path, request, self.authority)
        outbox_id = UUID(str(receipt.result["outbox_id"]))
        if self.deliver_answer is not None:
            self.deliver_answer(outbox_id)
        return receipt.model_dump(mode="json")

    def accept_preview(self, session_id: UUID) -> dict[str, object]:
        selected = self._selection(session_id)
        snapshot = read_execution(self.path, selected.work_id, self.authority)
        if snapshot.work.state.status != "proposed" or not snapshot.work.state.linked_outputs:
            raise FoundationError("not_ready", "Work has no proposed linked result")
        nonce = UUID(bytes=secrets.token_bytes(16))
        operation_id = uuid5(nonce, "accept")
        with self.lock:
            self.accept_previews[nonce] = (selected.work_id, snapshot.work.revision, operation_id)
        return {
            "nonce": str(nonce),
            "operation_id": str(operation_id),
            "work_id": str(selected.work_id),
            "revision": snapshot.work.revision,
            "outputs": [item.model_dump(mode="json") for item in snapshot.outputs],
        }

    def accept(self, session_id: UUID, nonce: UUID, basis: str) -> dict[str, object]:
        if session_id in self.response_only:
            raise FoundationError("permission_denied", "Response repair cannot accept Work")
        selected = self._selection(session_id)
        with self.lock:
            if nonce in self.accept_results:
                return self.accept_results[nonce]
            preview = self.accept_previews.pop(nonce, None)
        if preview is None or preview[0] != selected.work_id:
            raise FoundationError("confirmation_required", "No current local acceptance preview")
        current = read_execution(self.path, selected.work_id, self.authority)
        if current.work.revision != preview[1]:
            raise FoundationError("stale_work", "Work changed after acceptance preview")
        request = AcceptWorkRequest(
            operation_id=preview[2],
            space_id=self.authority.space_id,
            actor=self.authority.actor,
            work_id=preview[0],
            expected_revision=preview[1],
            basis=basis,
        )
        confirmed = LocalAuthority(
            actor=self.authority.actor,
            source_ref=f"pi-ui-confirm:{nonce}",
            established_at=self.authority.established_at,
            space_root=self.authority.space_root,
            space_id=self.authority.space_id,
            execution_epoch=self.authority.execution_epoch,
        )
        receipt = apply_operation(self.path, request, confirmed).model_dump(mode="json")
        with self.lock:
            self.accept_results[nonce] = receipt
        return receipt

    def receipt(self, session_id: UUID, operation_id: UUID) -> dict[str, object]:
        self._session(session_id)
        return read_receipt(self.path, operation_id, self.authority).model_dump(mode="json")

    def events(self, session_id: UUID, cursor: int, timeout: float) -> dict[str, object]:
        selected = self._selection(session_id)
        until = time.monotonic() + min(max(timeout, 0), 20)
        while True:
            rows = read_execution_events(self.path, selected.work_id, cursor, self.authority)
            if rows or time.monotonic() >= until:
                return {"events": rows, "cursor": rows[-1]["sequence"] if rows else cursor}
            time.sleep(0.2)


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, bridge: Bridge) -> None:
        super().__init__(("127.0.0.1", 0), BridgeHandler)
        self.bridge = bridge


class BridgeHandler(BaseHTTPRequestHandler):
    server: BridgeServer

    def log_message(self, format: str, *args: object) -> None:
        pass

    def _reply(self, status: HTTPStatus, payload: object) -> None:
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        expected = f"Bearer {self.server.bridge.token}"
        return secrets.compare_digest(self.headers.get("Authorization", ""), expected)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > MAX_BODY_BYTES:
            raise FoundationError("invalid_request", "JSON body size is unsupported")
        data = json.loads(self.rfile.read(length))
        if not isinstance(data, dict):
            raise FoundationError("invalid_request", "Expected one JSON object")
        return data

    def _dispatch(self, *, post: bool) -> None:
        if not self._authorized():
            self._reply(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        body: dict[str, Any] = {}
        session_id: UUID | None = None
        path = urlsplit(self.path)
        try:
            path = urlsplit(self.path)
            params = parse_qs(path.query)
            bridge = self.server.bridge
            body = self._body() if post else {}
            session_id = UUID(str(body.get("session_id") if post else params["session_id"][0]))
            if post and path.path == "/v1/connect":
                result = bridge.connect(session_id)
            elif post and path.path == "/v1/workspace":
                result = bridge.workspace_operation(session_id, body)
            elif post and path.path == "/v1/select":
                result = bridge.select(session_id, UUID(body["activity_id"]), UUID(body["work_id"]))
            elif post and path.path == "/v1/operation":
                result = bridge.operation(session_id, body["request"])
            elif post and path.path == "/v1/binding-upgrade":
                result = bridge.binding_upgrade(session_id)
            elif post and path.path == "/v1/binding-operation":
                result = bridge.binding_operation(session_id, body["request"])
            elif post and path.path == "/v1/knowledge-upgrade":
                result = bridge.knowledge_upgrade(session_id)
            elif post and path.path == "/v1/knowledge-operation":
                result = bridge.knowledge_operation(session_id, body["request"])
            elif post and path.path == "/v1/knowledge-capture":
                result = bridge.capture_source(
                    session_id,
                    channel=str(body["channel"]),
                    content=str(body["content"]),
                    source_event_id=str(body["source_event_id"]),
                    input_source=str(body.get("input_source", "interactive")),
                    limitations=tuple(body.get("limitations", ())),
                    replay_session_id=UUID(str(body["replay_session_id"]))
                    if body.get("replay_session_id") is not None
                    else None,
                    conversation_final=body.get("conversation_final") is True,
                    final_manifest=KnowledgeRef.model_validate(body["final_manifest"])
                    if body.get("final_manifest") is not None
                    else None,
                    conversation_terminal=body.get("conversation_terminal"),
                )
            elif post and path.path == "/v1/request-origin":
                result = bridge.bind_request_origin(session_id, body)
            elif post and path.path == "/v1/conversation":
                from .conversation import conversation

                result = conversation(bridge, session_id, body)
            elif post and path.path == "/v1/process-boundary":
                result = bridge.process_boundary(session_id, body)
            elif post and path.path == "/v1/knowledge-read":
                result = bridge.knowledge_read(session_id, body)
            elif post and path.path == "/v1/integration":
                result = bridge.integration(session_id, body)
            elif post and path.path == "/v1/data":
                result = bridge.data_operation(session_id, body)
            elif post and path.path == "/v1/manual-exchange":
                result = bridge.manual_exchange(session_id, body)
            elif post and path.path == "/v1/development-upgrade":
                result = bridge.development_upgrade(session_id)
            elif post and path.path == "/v1/development-start-sleep":
                result = bridge.development_start_sleep(session_id, body)
            elif post and path.path == "/v1/development-operation":
                result = bridge.development_operation(session_id, body["request"])
            elif post and path.path == "/v1/development-read":
                result = bridge.development_read(session_id, body)
            elif post and path.path == "/v1/activity-read":
                result = bridge.activity_read(session_id, UUID(body["activity_id"]))
            elif post and path.path == "/v1/activity-setup":
                result = bridge.activity_setup(session_id, body)
            elif post and path.path == "/v1/model-selection":
                result = bridge.model_selection(session_id, body)
            elif post and path.path == "/v1/workflow":
                result = bridge.workflow(session_id, body)
            elif post and path.path == "/v1/context-prepare":
                result = bridge.prepare_context(
                    session_id,
                    str(body.get("purpose", "content")),
                    tuple(
                        KnowledgeRef.model_validate(ref)
                        for ref in body.get("historical_memory", [])
                    ),
                )
            elif post and path.path == "/v1/context-delivery":
                result = bridge.context_delivery(session_id, body)
            elif post and path.path == "/v1/start-attempt":
                result = bridge.start_attempt(
                    session_id, interrupt_previous=body.get("interrupt_previous") is True
                )
            elif post and path.path == "/v1/publish":
                result = bridge.publish(
                    session_id,
                    UUID(body["attempt_id"]),
                    str(body["slot"]),
                    str(body["media_type"]),
                    str(body["content"]),
                )
            elif post and path.path == "/v1/wait":
                result = bridge.open_wait(
                    session_id,
                    UUID(body["attempt_id"]),
                    UUID(body["wait_id"]),
                    str(body["partial"]),
                    str(body["question"]),
                    str(body["remainder"]),
                )
            elif post and path.path == "/v1/answer":
                result = bridge.answer_wait(session_id, UUID(body["wait_id"]), str(body["answer"]))
            elif post and path.path == "/v1/accept-preview":
                result = bridge.accept_preview(session_id)
            elif post and path.path == "/v1/accept":
                result = bridge.accept(session_id, UUID(body["nonce"]), str(body["basis"]))
            elif not post and path.path == "/v1/snapshot":
                result = bridge.snapshot(session_id)
            elif not post and path.path == "/v1/bindings":
                result = bridge.binding_catalog(session_id)
            elif not post and path.path == "/v1/binding-contract":
                result = bridge.binding_contract(session_id, params["kind"][0])
            elif not post and path.path == "/v1/knowledge-contract":
                result = bridge.knowledge_contract(session_id, params["kind"][0])
            elif not post and path.path == "/v1/development-contract":
                result = bridge.development_contract(session_id, params["kind"][0])
            elif not post and path.path == "/v1/receipt":
                result = bridge.receipt(session_id, UUID(params["operation_id"][0]))
            elif not post and path.path == "/v1/events":
                result = bridge.events(
                    session_id,
                    int(params.get("cursor", ["0"])[0]),
                    float(params.get("timeout", ["0"])[0]),
                )
            else:
                self._reply(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            bridge.complete_provider_preflight(session_id, path.path, body)
            self._reply(HTTPStatus.OK, result)
        except (FoundationError, KeyError, ValueError, TypeError, json.JSONDecodeError) as error:
            code = error.code if isinstance(error, FoundationError) else "invalid_request"
            if isinstance(error, FoundationError) and session_id is not None:
                self.server.bridge.capture_provider_refusal(session_id, path.path, body, error)
            error_result: dict[str, object] = {"error": code, "detail": str(error)}
            if isinstance(error, FoundationError):
                error_result["foundation_detail"] = error.detail
            if isinstance(error, OutputValidationError):
                error_result["validation_issues"] = [
                    issue.model_dump(mode="json") for issue in error.issues
                ]
            self._reply(HTTPStatus.CONFLICT, error_result)

    def do_GET(self) -> None:
        self._dispatch(post=False)

    def do_POST(self) -> None:
        self._dispatch(post=True)
