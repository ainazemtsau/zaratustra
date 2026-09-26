"""Loopback JSON bridge from ordinary Pi to the independent Core."""

from __future__ import annotations

import base64
import json
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, TypeAdapter, ValidationError

from zaratustra.foundation import (
    AcceptWorkRequest,
    AnswerWaitRequest,
    ArtifactRef,
    ChoiceState,
    ClaimState,
    ContextState,
    CreateArtifactRequest,
    CreateBindingVersionRequest,
    CreateGrantRequest,
    CreateKnowledgeRequest,
    CreateMethodVersionRequest,
    CreateResourceRequest,
    DecisionState,
    DeleteKnowledgeRequest,
    DomainRequest,
    FireBindingRequest,
    FoundationError,
    KnowledgeRef,
    LocalAuthority,
    OpenWaitRequest,
    ProvenanceRef,
    PublishAttemptOutputRequest,
    RecordContextDeliveryRequest,
    ResolveBindingOfferRequest,
    ResourceState,
    ReviseKnowledgeRequest,
    SetBindingStateRequest,
    SourceState,
    StartAttemptRequest,
    StopAttemptRequest,
    apply_operation,
    inspect_space,
    list_binding_methods,
    list_binding_offers,
    list_bindings,
    list_knowledge,
    open_knowledge,
    read_activity,
    read_artifact,
    read_current_rights,
    read_decision,
    read_execution,
    read_execution_events,
    read_knowledge,
    read_knowledge_neighbors,
    read_method_version,
    read_receipt,
    read_space,
    read_work,
    read_work_plan,
    read_work_status,
    search_knowledge,
    upgrade_binding_space,
    upgrade_child_execution_space,
    upgrade_composition_space,
    upgrade_continuation_space,
    upgrade_knowledge_space,
    upgrade_parent_execution_space,
    upgrade_plan_revision_space,
)

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


@dataclass(frozen=True)
class Selection:
    activity_id: UUID
    work_id: UUID


class Bridge:
    """One trusted local process and one selected Core space."""

    def __init__(
        self,
        path: Path,
        authority: LocalAuthority,
        workspace: Path,
        limit_units: int,
        *,
        assigned_attempt_id: UUID | None = None,
        assigned_session_id: UUID | None = None,
        deliver_answer: Callable[[UUID], object] | None = None,
        context_max_bytes: int = 65536,
        free_conversation_limit_units: int = 100000,
    ) -> None:
        self.path = path.resolve()
        self.authority = authority
        self.workspace = workspace.resolve()
        if not self.workspace.is_dir() or limit_units < 1:
            raise FoundationError("resource_unavailable", "Choose an existing directory and limit")
        self.limit_units = limit_units
        if free_conversation_limit_units < 1:
            raise FoundationError("invalid_request", "Free conversation budget must be positive")
        self.free_conversation_limit_units = free_conversation_limit_units
        if not 1 <= context_max_bytes <= 2 * 1024 * 1024:
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
        self.exposed_refs: dict[UUID, set[KnowledgeRef]] = {}
        self.accept_previews: dict[UUID, tuple[UUID, int, UUID]] = {}
        self.accept_results: dict[UUID, dict[str, object]] = {}
        self.lock = threading.Lock()

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

    def select(self, session_id: UUID, activity_id: UUID, work_id: UUID) -> dict[str, object]:
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
        return read_execution(self.path, selected.work_id, self.authority).model_dump(mode="json")

    def operation(self, session_id: UUID, raw: dict[str, object]) -> dict[str, object]:
        selected = self._selection(session_id)
        try:
            request = REQUEST_ADAPTER.validate_python(raw)
        except ValidationError as error:
            raise FoundationError("invalid_request", str(error)) from error
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
            raise FoundationError("wrong_work", "Operation does not address the selected Work")
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

    def knowledge_operation(self, session_id: UUID, raw: dict[str, object]) -> dict[str, object]:
        self._session(session_id)
        if self.assigned_attempt_id is not None:
            raise FoundationError("permission_denied", "Assigned RPC cannot change knowledge")
        prepared = dict(raw)
        state_raw = prepared.get("state")
        if isinstance(state_raw, dict):
            state = dict(state_raw)
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
        if request.actor != self.authority.actor or request.space_id != self.authority.space_id:
            raise FoundationError("permission_denied", "Knowledge actor/space differs from host")
        return apply_operation(self.path, request, self.authority).model_dump(mode="json")

    def capture_source(
        self,
        session_id: UUID,
        *,
        channel: str,
        content: str,
        source_event_id: str,
        input_source: str = "interactive",
        limitations: tuple[str, ...] = (),
    ) -> dict[str, object]:
        selected = self._session(session_id)
        if channel not in ("conversation_user", "conversation_assistant", "tool_result"):
            raise FoundationError("invalid_request", "Unsupported Pi capture channel")
        if read_space(self.path).schema_version < 10:
            raise FoundationError("unsupported_schema", "Capture needs explicit schema 10")
        source_id = uuid5(self.authority.space_id, f"pi:{session_id}:{source_event_id}")
        operation_id = uuid5(source_id, "capture")
        with self.lock:
            derived = set(self.exposed_refs.get(session_id, set()))
            if channel == "conversation_assistant" and session_id in self.last_sources:
                derived.add(self.last_sources[session_id])
        state = SourceState.model_validate(
            {
                "channel": channel,
                "connection": "ordinary-pi",
                "profile_revision": 1,
                "source_event_id": f"{session_id}:{source_event_id}",
                "conversation_id": str(session_id),
                "scope_activity_id": selected.activity_id if selected else None,
                "scope_work_id": selected.work_id if selected else None,
                "sender": self.authority.actor
                if channel == "conversation_user" and input_source == "interactive"
                else "pi-rpc"
                if channel == "conversation_user"
                else "pi-assistant"
                if channel == "conversation_assistant"
                else "pi-tool",
                "media_type": "text/plain; charset=utf-8",
                "capture": "excluded" if not content else "full",
                "content": content.encode() if content else None,
                "limitations": limitations,
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
        return receipt.model_dump(mode="json")

    def knowledge_read(self, session_id: UUID, body: dict[str, Any]) -> dict[str, object]:
        self._session(session_id)
        mode = body.get("mode")
        if mode == "list":
            return list_knowledge(
                self.path,
                self.authority,
                kind=body.get("kind"),
                limit=int(body.get("limit", 25)),
                cursor=body.get("cursor"),
            )
        if mode == "search":
            result = search_knowledge(
                self.path,
                self.authority,
                str(body["query"]),
                limit=int(body.get("limit", 25)),
                cursor=str(body["cursor"]) if body.get("cursor") is not None else None,
            )
            with self.lock:
                exposed = self.exposed_refs.setdefault(session_id, set())
                for entry in cast(list[dict[str, Any]], result["items"]):
                    exposed.add(
                        KnowledgeRef(
                            record_id=UUID(entry["record_id"]), revision=int(entry["revision"])
                        )
                    )
            return result
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
                with self.lock:
                    self.exposed_refs.setdefault(session_id, set()).add(
                        KnowledgeRef(record_id=record_id, revision=cast(int, result["revision"]))
                    )
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

    def prepare_context(self, session_id: UUID, purpose: str = "content") -> dict[str, object]:
        selected = self._session(session_id)
        info = read_space(self.path)
        if info.schema_version < 10:
            raise FoundationError("unsupported_schema", "Context needs explicit schema 10")
        mandatory: list[KnowledgeRef] = []
        evidence_refs: list[KnowledgeRef] = []
        packet: dict[str, object] = {
            "space_id": str(info.space_id),
            "epoch": info.execution_epoch,
            "purpose": purpose,
        }
        with self.lock:
            latest_source = self.last_sources.get(session_id)
        if latest_source is not None:
            mandatory.append(latest_source)
        if selected is not None and purpose == "compaction-summary":
            current = read_execution(self.path, selected.work_id, self.authority)
            work = current.work
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
            inputs: list[dict[str, object]] = []
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
                    and exact.media_type.startswith("text/")
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
                    isinstance(decision.state, DecisionState)
                    and decision.state.status == "active"
                    and (
                        "*" in decision.state.subjects
                        or self.authority.actor in decision.state.subjects
                    )
                ) or (
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
            # route into this continuation. An overlarge set blocks rather than truncates.
            cursor: str | None = None
            claims: list[dict[str, object]] = []
            while True:
                page = list_knowledge(
                    self.path, self.authority, kind="claim", limit=100, cursor=cursor
                )
                for entry in cast(list[dict[str, Any]], page["items"]):
                    claim_item = read_knowledge(self.path, UUID(entry["record_id"]), self.authority)
                    state = claim_item.state
                    if (
                        isinstance(state, ClaimState)
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
        if len(rendered.encode("utf-8")) > self.context_max_bytes:
            raise FoundationError(
                "context_overflow", "Mandatory context exceeds configured byte limit"
            )
        manifest_id = UUID(bytes=secrets.token_bytes(16))
        receipt = apply_operation(
            self.path,
            CreateKnowledgeRequest(
                operation_id=uuid5(manifest_id, "prepare"),
                space_id=info.space_id,
                actor=self.authority.actor,
                record_id=manifest_id,
                state=ContextState(
                    purpose="compaction summary"
                    if purpose == "compaction-summary"
                    else "selected Work continuation"
                    if selected
                    else "conversation continuation",
                    session_id=session_id,
                    work_id=selected.work_id if selected else None,
                    method=work.state.method if selected and work.state.method != "none" else None,
                    plan_revision=current.composition.plan_revision
                    if selected and current.composition
                    else None,
                    mandatory=tuple(dict.fromkeys(mandatory)),
                    max_bytes=self.context_max_bytes,
                ),
            ),
            self.authority,
        )
        with self.lock:
            self.exposed_refs.setdefault(session_id, set()).update(mandatory)
        return {
            "manifest_id": str(manifest_id),
            "manifest_revision": 1,
            "state_revision": receipt.state_revision,
            "packet": packet,
            "byte_count": len(rendered.encode("utf-8")),
        }

    def context_delivery(self, session_id: UUID, raw: dict[str, Any]) -> dict[str, object]:
        selected = self._session(session_id)
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
                "free_call": selected is None,
                "reserve_units": int(raw.get("reserve_units", 0)) if selected is None else 0,
                "usage_units": raw.get("usage_units"),
                "budget_limit_units": self.free_conversation_limit_units if selected is None else 0,
            }
        )
        return apply_operation(self.path, request, self.authority).model_dump(mode="json")

    def start_attempt(self, session_id: UUID, *, interrupt_previous: bool) -> dict[str, object]:
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
        selected = self._selection(session_id)
        if self.assigned_attempt_id is not None and attempt_id != self.assigned_attempt_id:
            raise FoundationError("permission_denied", "RPC cannot publish another Attempt")
        data = content.encode("utf-8")
        if not data or len(data) > 8 * 1024 * 1024:
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
        try:
            path = urlsplit(self.path)
            params = parse_qs(path.query)
            bridge = self.server.bridge
            body = self._body() if post else {}
            session_id = UUID(str(body.get("session_id") if post else params["session_id"][0]))
            if post and path.path == "/v1/connect":
                result = bridge.connect(session_id)
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
                )
            elif post and path.path == "/v1/knowledge-read":
                result = bridge.knowledge_read(session_id, body)
            elif post and path.path == "/v1/context-prepare":
                result = bridge.prepare_context(session_id, str(body.get("purpose", "content")))
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
            self._reply(HTTPStatus.OK, result)
        except (FoundationError, KeyError, ValueError, TypeError, json.JSONDecodeError) as error:
            code = error.code if isinstance(error, FoundationError) else "invalid_request"
            self._reply(HTTPStatus.CONFLICT, {"error": code, "detail": str(error)})

    def do_GET(self) -> None:
        self._dispatch(post=False)

    def do_POST(self) -> None:
        self._dispatch(post=True)
