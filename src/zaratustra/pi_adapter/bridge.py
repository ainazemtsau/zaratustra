"""Loopback JSON bridge from ordinary Pi to the independent Core."""

from __future__ import annotations

import json
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid5

from pydantic import BaseModel, TypeAdapter, ValidationError

from zaratustra.foundation import (
    AcceptWorkRequest,
    AnswerWaitRequest,
    ArtifactRef,
    CreateArtifactRequest,
    CreateBindingVersionRequest,
    CreateMethodVersionRequest,
    CreateResourceRequest,
    DomainRequest,
    FireBindingRequest,
    FoundationError,
    LocalAuthority,
    OpenWaitRequest,
    ProvenanceRef,
    PublishAttemptOutputRequest,
    ResolveBindingOfferRequest,
    ResourceState,
    SetBindingStateRequest,
    StartAttemptRequest,
    StopAttemptRequest,
    apply_operation,
    inspect_space,
    list_binding_methods,
    list_binding_offers,
    list_bindings,
    read_activity,
    read_execution,
    read_execution_events,
    read_receipt,
    read_space,
    read_work,
    read_work_status,
    upgrade_binding_space,
    upgrade_child_execution_space,
    upgrade_composition_space,
    upgrade_continuation_space,
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
    ) -> None:
        self.path = path.resolve()
        self.authority = authority
        self.workspace = workspace.resolve()
        if not self.workspace.is_dir() or limit_units < 1:
            raise FoundationError("resource_unavailable", "Choose an existing directory and limit")
        self.limit_units = limit_units
        if (assigned_attempt_id is None) != (assigned_session_id is None):
            raise FoundationError("invalid_request", "Assigned attempt and session must be paired")
        self.assigned_attempt_id = assigned_attempt_id
        self.assigned_session_id = assigned_session_id
        self.deliver_answer = deliver_answer
        self.token = secrets.token_urlsafe(48)
        self.sessions: dict[UUID, Selection | None] = {}
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
