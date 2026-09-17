"""Recoverable web handoffs over the existing Process journal."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from zaratustra.journal import Change, JournalError, Reference, Revision, Store, header, resolve

from .github import GitHub
from .models import Channel, Origin, Packet, Request, Review


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def identity(value: Any) -> str:
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8"))


class Exchange:
    def __init__(
        self, store: Store, process: dict[str, Any], shared: tuple[Store, ...] = ()
    ) -> None:
        self.store, self.process = store, process
        self.shared = shared
        self.prefix = "zaratustra-web/" + str(store.scope.id)
        self.channel_id = uuid5(store.scope.id, "web-channel")

    def fresh(self) -> Exchange:
        return Exchange(
            Store(self.store.path, self.store.scope, self.store.source_ref),
            self.process,
            self.shared,
        )

    def result(self, record: Revision, replayed: bool = False) -> dict[str, Any]:
        return {
            "record": header(record),
            "reference": record.reference().model_dump(mode="json"),
            "replayed": replayed,
        }

    def write(
        self,
        type_name: str,
        title: str,
        payload: dict[str, Any],
        operation: UUID,
        reason: str,
        old: Revision | None = None,
        record_id: UUID | None = None,
    ) -> dict[str, Any]:
        result = self.store.write(
            Change(
                operation_id=operation,
                action="revise" if old else "create",
                record_id=old.id if old else record_id,
                expected_revision=old.revision if old else None,
                type_name=type_name,
                title=title,
                payload=payload,
                reason=reason,
            )
        )
        return self.result(
            Revision.model_validate(result["record"]), result.get("replayed", False)
        ) | {
            key: result[key]
            for key in ("committed", "projection_warning", "receipt")
            if key in result
        }

    def channel(self) -> Channel:
        if self.channel_id not in self.store.records:
            raise JournalError(
                "web_not_configured", "Choose a private GitHub repository for exchange"
            )
        return Channel.model_validate(self.store.get(self.channel_id).payload)

    def configure(self, channel: Channel, operation: UUID, expected: int | None) -> dict[str, Any]:
        old = self.store.get(self.channel_id) if self.channel_id in self.store.records else None
        if old and old.payload == channel.model_dump(mode="json"):
            return self.result(old, True) | {"prefix": self.prefix}
        if old and old.revision != expected:
            raise JournalError("revision_conflict", "Read the channel before changing it")
        return self.write(
            "web_channel",
            "Web exchange",
            channel.model_dump(mode="json"),
            operation,
            "Owner selected GitHub exchange destination",
            old,
            self.channel_id,
        ) | {"prefix": self.prefix}

    def capture(self, origin: Origin, raw: bytes) -> dict[str, Any]:
        channel = self.channel()
        if (origin.repository, origin.branch) != (channel.repository, channel.branch):
            raise JournalError("source_mismatch", "Request belongs to another exchange channel")
        if not origin.path.startswith(self.prefix + "/requests/"):
            raise JournalError("source_mismatch", "File is outside this Process inbox")
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + bytes([0]) + raw).hexdigest()
        if len(raw) > 1_000_000 or origin.blob != blob:
            raise JournalError(
                "invalid_blob", "Request exceeds 1 MB or differs from its blob identity"
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise JournalError(
                "request_not_text", "Attach this binary file alongside a text request"
            ) from error
        if not text.lstrip(chr(0xFEFF)).strip():
            raise JournalError(
                "empty_request", "Request has no readable content; original remains remote"
            )
        request_id = uuid5(
            self.store.scope.id, identity([origin.repository.lower(), origin.path, origin.blob])
        )
        if request_id in self.store.records:
            old = self.store.get(request_id)
            if Request.model_validate(old.payload).sha256 != digest(raw):
                raise JournalError("source_conflict", "Same source identity has different bytes")
            return self.result(old, True)
        return self.write(
            "web_request",
            origin.path.rsplit("/", 1)[-1][:128],
            Request(origin=origin, original=text, sha256=digest(raw)).model_dump(mode="json"),
            request_id,
            "Capture original web request; interpretation and application are separate",
        )

    def pull(self, offset: int, limit: int, transport: GitHub | None = None) -> dict[str, Any]:
        github = transport or GitHub(self.channel())
        page = github.incoming(self.prefix + "/requests", offset, limit)
        received, failures = [], []
        for entry in page["entries"]:
            try:
                raw = github.read(entry)
                received.append(self.fresh().capture(github.origin(page["commit"], entry), raw))
            except (JournalError, UnicodeError, ValueError) as error:
                failures.append({"path": entry["path"], "error": str(error)})
        end = offset + len(page["entries"])
        return {
            "received": received,
            "failures": failures,
            "total_remote": page["total"],
            "next_offset": end if end < page["total"] else None,
            "commit": page["commit"],
            "applied": False,
        }

    def get(self, record_id: UUID, type_name: str = "web_request") -> Revision:
        record = self.store.get(record_id)
        if record.type_name != type_name:
            raise JournalError("wrong_type", "Select a " + type_name)
        return record

    def listing(self, offset: int, limit: int, completed: bool) -> dict[str, Any]:
        selected = [
            r[-1]
            for r in self.store.records.values()
            if r[-1].type_name == "web_request"
            and (completed or Request.model_validate(r[-1].payload).status != "completed")
        ]
        return {
            "requests": [
                header(r) | {"status": r.payload["status"]}
                for r in selected[offset : offset + limit]
            ],
            "total": len(selected),
            "next_offset": offset + limit if offset + limit < len(selected) else None,
        }

    def available(self, ref: Reference) -> dict[str, Any]:
        result = resolve([self.store, *self.shared], ref)
        if result["status"] != "available":
            raise JournalError(
                "scope_unavailable", "Source is outside this Process; supply selected content"
            )
        return result

    def context_status(self, reference: Reference | None) -> dict[str, Any]:
        if reference is None:
            return {
                "status": "not_linked",
                "detail": "Agent must establish the current working basis",
            }
        source = self.available(reference)
        if reference.kind != "record" or source["record"]["type_name"] != "web_context":
            raise JournalError("wrong_type", "Context must identify a prepared web packet")
        packet = Packet.model_validate(source["record"]["payload"])
        changed = []
        basis = []
        for ref in packet.references:
            self.available(ref)
            selected_store = next(s for s in [self.store, *self.shared] if s.scope == ref.scope)
            latest = selected_store.get(ref.id).revision if ref.kind == "record" else ref.revision
            basis.append([ref.model_dump(mode="json"), latest])
            if latest != ref.revision:
                changed.append(ref.model_dump(mode="json"))
        return {
            "status": "selected_sources_changed" if changed else "selected_sources_unchanged",
            "changed": changed,
            "basis_stamp": identity(basis),
            "prepared_process_revision": packet.process_revision,
            "current_process_revision": self.store.query.expected_revision,
            "limitation": "Unselected changes and semantic conflicts require the agent's review",
        }

    def read(self, record_id: UUID, offset: int, limit: int) -> dict[str, Any]:
        record = self.get(record_id)
        request = Request.model_validate(record.payload)
        end = offset + limit
        deliveries = []
        for item in request.review.items if request.review else ():
            operation = uuid5(record.id, "delivery:" + item.key)
            receipt = self.store.operations.get(operation)
            material = next(
                (m for m in self.store.materials.values() if m.operation_id == operation), None
            )
            committed = (
                receipt.reference()
                if receipt
                else (
                    Reference(
                        scope=self.store.scope,
                        kind="material",
                        id=material.id,
                        revision=material.revision,
                    )
                    if material
                    else None
                )
            )
            deliveries.append(
                {
                    "key": item.key,
                    "operation_id": str(operation),
                    "committed_result": committed.model_dump(mode="json") if committed else None,
                }
            )
        return self.result(record) | {
            "origin": request.origin.model_dump(mode="json"),
            "sha256": request.sha256,
            "status": request.status,
            "original": request.original[offset:end],
            "total": len(request.original),
            "next_offset": end if end < len(request.original) else None,
            "review": request.review.model_dump(mode="json") if request.review else None,
            "deliveries": deliveries,
            "process_revision": self.store.query.expected_revision,
            "context": self.context_status(request.review.context if request.review else None),
        }

    def review(
        self, record_id: UUID, expected: int, review: Review, operation: UUID, reason: str
    ) -> dict[str, Any]:
        prior = self.store.operations.get(operation)
        if prior is not None:
            previous_revision = prior.previous.revision if prior.previous else None
            retained = Request.model_validate(prior.payload)
            if review.context is None and retained.review and retained.review.context:
                review = review.model_copy(update={"context": retained.review.context})
            if (
                prior.id != record_id
                or previous_revision != expected
                or retained.review != review
                or prior.reason != reason
            ):
                raise JournalError("operation_conflict", "Review operation has different intent")
            return self.result(prior, True)
        old = self.get(record_id)
        request = Request.model_validate(old.payload)
        if request.review and request.review.context:
            if review.context is None:
                review = review.model_copy(update={"context": request.review.context})
            elif review.context != request.review.context:
                raise JournalError(
                    "changed_context_identity",
                    "Keep the established discussion source; add a separate correction",
                )
        if old.revision != expected or request.status == "completed":
            raise JournalError(
                "revision_conflict", "Read the unfinished request before updating it"
            )
        previous = {i.key: i for i in request.review.items} if request.review else {}
        current = {i.key: i for i in review.items}
        if previous.keys() - current.keys():
            raise JournalError(
                "dropped_item", "Keep every previously identified item accounted for"
            )
        for key, item in previous.items():
            if {a.name for a in item.files} - {a.name for a in current[key].files}:
                raise JournalError(
                    "dropped_attachment", "Keep every declared required file accounted for"
                )
            received = {a.name: a.reference for a in item.files if a.reference is not None}
            if any(
                a.name in received and a.reference != received[a.name] for a in current[key].files
            ):
                raise JournalError(
                    "changed_attachment",
                    "Keep received file references; add a separate correction item",
                )
            if item.outcome == "done" and current[key] != item:
                raise JournalError(
                    "changed_delivery", "Completed effects stay recorded; add a correction item"
                )
        for item in review.items:
            if item.source_quote not in request.original:
                raise JournalError("missing_quote", "Item must cite actual request content")
            authority_text = request.original
            if item.authority_reference:
                authority = self.available(item.authority_reference)
                authority_text += (
                    str(authority["record"].get("authority_source") or "")
                    + chr(10)
                    + str(authority["record"]["payload"].get("text") or "")
                    if "record" in authority
                    else base64.b64decode(authority["base64"]).decode("utf-8")
                )
            if item.authority_quote and item.authority_quote not in authority_text:
                raise JournalError(
                    "missing_quote", "Authority quote needs its original or later saved source"
                )
            for attachment in item.files:
                if attachment.reference:
                    prior_item = previous.get(item.key)
                    prior_file = (
                        next((a for a in prior_item.files if a.name == attachment.name), None)
                        if prior_item
                        else None
                    )
                    if prior_file is None or attachment.reference != prior_file.reference:
                        raise JournalError(
                            "attachment_not_received",
                            "Use web.attach to preserve the actual supplied file bytes",
                        )
                    result = self.available(attachment.reference)
                    if (
                        attachment.reference.kind == "record"
                        and result["record"]["type_name"] != "document"
                    ):
                        raise JournalError(
                            "missing_file", "Attachment must refer to actual saved document bytes"
                        )
            if item.result:
                result = self.available(item.result)
                if item.result.kind == "record" and result["record"]["type_name"].startswith(
                    "web_"
                ):
                    raise JournalError(
                        "invalid_delivery", "Transport records are not delivered work"
                    )
        context = self.context_status(review.context)
        if context["status"] == "selected_sources_changed" and not review.context_note.strip():
            raise JournalError(
                "changed_context", "Explain how the changed sources affect this request"
            )
        waiting = any(
            i.intent == "clarify" or any(a.reference is None for a in i.files) for i in review.items
        )
        new = request.model_copy(
            update={
                "review": review,
                "status": "waiting" if waiting else "processing",
                "context_stamp": context.get("basis_stamp"),
            }
        )
        return self.write(
            "web_request", old.title, new.model_dump(mode="json"), operation, reason, old
        )

    def attach(self, record_id: UUID, key: str, name: str, path: Path) -> dict[str, Any]:
        old = self.get(record_id)
        request = Request.model_validate(old.payload)
        if request.review is None:
            raise JournalError("request_not_open", "Read and review the pending request first")
        item = next((i for i in request.review.items if i.key == key), None)
        attachment = next((a for a in item.files if a.name == name), None) if item else None
        if item is None or attachment is None:
            raise JournalError(
                "attachment_not_declared", "Choose an outstanding declared attachment"
            )
        with path.open("rb") as stream:
            raw = stream.read(8_000_001)
        if len(raw) > 8_000_000:
            raise JournalError(
                "file_too_large", "This document exceeds the existing 8 MB material limit"
            )
        operation = uuid5(record_id, identity(["attachment", key, name, digest(raw)]))
        if attachment.reference and (
            attachment.reference.id != operation or attachment.reference.kind != "record"
        ):
            raise JournalError(
                "attachment_conflict",
                "A different file was already received; retain both and clarify",
            )
        if attachment.reference is None and (
            request.status == "completed" or item.outcome == "done"
        ):
            raise JournalError("request_not_open", "Completed work cannot receive another file")
        if operation in self.store.records:
            document = self.store.get(operation, 1)
            if document.type_name != "document" or document.payload.get(
                "base64"
            ) != base64.b64encode(raw).decode("ascii"):
                raise JournalError(
                    "operation_conflict", "Attachment identity has different stored content"
                )
        else:
            saved = self.write(
                "document",
                name,
                {
                    "media_type": "application/octet-stream",
                    "base64": base64.b64encode(raw).decode("ascii"),
                },
                operation,
                "Preserve owner-supplied attachment bytes without text reconstruction",
            )
            document = self.fresh().store.get(UUID(saved["record"]["id"]), 1)
        reference = document.reference()
        if attachment.reference is not None:
            if attachment.reference != reference:
                raise JournalError(
                    "attachment_conflict",
                    "A different file was already received; retain both and clarify",
                )
            return {
                "reference": reference.model_dump(mode="json"),
                "sha256": digest(raw),
                "size": len(raw),
                "replayed": True,
            }
        fresh = self.fresh()
        items = tuple(
            i.model_copy(
                update={
                    "files": tuple(
                        a.model_copy(update={"reference": reference}) if a.name == name else a
                        for a in i.files
                    )
                }
            )
            if i.key == key
            else i
            for i in request.review.items
        )
        updated_review = request.review.model_copy(update={"items": items})
        waiting = any(
            i.intent == "clarify" or any(a.reference is None for a in i.files) for i in items
        )
        updated = request.model_copy(
            update={"review": updated_review, "status": "waiting" if waiting else "processing"}
        )
        try:
            progress = fresh.write(
                "web_request",
                old.title,
                updated.model_dump(mode="json"),
                uuid5(operation, "bind"),
                "Received required attachment as exact saved bytes",
                old,
            )
        except JournalError as error:
            return {
                "reference": reference.model_dump(mode="json"),
                "sha256": digest(raw),
                "size": len(raw),
                "binding_pending": True,
                "detail": str(error),
            }
        return {
            "reference": reference.model_dump(mode="json"),
            "sha256": digest(raw),
            "size": len(raw),
            "request": progress,
            "replayed": False,
        }

    def complete(
        self, record_id: UUID, expected: int, process_revision: int, operation: UUID
    ) -> dict[str, Any]:
        old = self.get(record_id)
        request = Request.model_validate(old.payload)
        if request.status == "completed":
            return self.result(old, True)
        if old.revision != expected or self.store.query.expected_revision != process_revision:
            raise JournalError(
                "revision_conflict", "Read current request and Process before completion"
            )
        if request.review is None or any(i.outcome != "done" for i in request.review.items):
            raise JournalError(
                "unfinished_request", "Every independent item and required file needs delivery"
            )
        if self.context_status(request.review.context).get("basis_stamp") != request.context_stamp:
            raise JournalError(
                "changed_context",
                "Selected sources changed after review; reconcile before completion",
            )
        for item in request.review.items:
            if item.result:
                self.available(item.result)
            for attachment in item.files:
                if attachment.reference:
                    self.available(attachment.reference)
        return self.write(
            "web_request",
            old.title,
            request.model_copy(update={"status": "completed"}).model_dump(mode="json"),
            operation,
            "Agent accounted for the full request and checked its current results",
            old,
        )

    def prepare(
        self, question: str, refs: tuple[Reference, ...], operation: UUID
    ) -> dict[str, Any]:
        intent = identity([question, [r.model_dump(mode="json") for r in refs]])
        if operation in self.store.records:
            old = self.get(operation, "web_context")
            if Packet.model_validate(old.payload).intent_sha256 != intent:
                raise JournalError(
                    "operation_conflict", "Preparation id has different selected content"
                )
            return self.result(old, True)
        lines = [
            "# " + self.process["title"],
            "",
            "## Discussion request",
            question,
            "",
            "Prepared at " + datetime.now(UTC).isoformat(),
            "Process: " + str(self.store.scope.id),
            "Process revision: " + str(self.store.query.expected_revision),
            "Context reference: " + str(operation) + " revision 1",
            "",
            "Selected sources follow. This is a dated snapshot, not a live database.",
            "Unselected history, linked sources and binary files are not included.",
            "Discuss freely; save a request only when the owner asks. "
            "Pending requests are not current state.",
        ]
        for ref in refs:
            source = self.available(ref)
            lines += ["", "## Source", json.dumps(ref.model_dump(mode="json"), ensure_ascii=False)]
            if ref.kind == "record":
                record = source["record"]
                lines += [record["title"], "State: " + record["state"]]
                content = record["payload"]
                if record["type_name"] == "document" and content.get("base64"):
                    lines.append(
                        "Binary document omitted; request the selected file from the owner."
                    )
                else:
                    lines.append(json.dumps(content, ensure_ascii=False, indent=2))
            else:
                raw = base64.b64decode(source["base64"])
                lines.append(source["material"]["title"])
                try:
                    lines.append(raw.decode("utf-8"))
                except UnicodeDecodeError:
                    lines.append(
                        "Binary material omitted; request the selected file from the owner."
                    )
        packet = Packet(
            process_title=self.process["title"],
            process_revision=self.store.query.expected_revision,
            question=question,
            references=refs,
            markdown=chr(10).join(lines),
            intent_sha256=intent,
        )
        if len(packet.markdown.encode("utf-8")) > 1_000_000:
            raise JournalError("context_too_large", "Select fewer sources; no silent truncation")
        return self.write(
            "web_context",
            "Web discussion context",
            packet.model_dump(mode="json"),
            operation,
            "Prepare explicitly selected discussion context",
        )

    def publish(self, record_id: UUID, transport: GitHub | None = None) -> dict[str, Any]:
        record = self.get(record_id, "web_context")
        packet = Packet.model_validate(record.payload)
        github = transport or GitHub(self.channel())
        instructions = (
            files("zaratustra.web_exchange")
            .joinpath("PROJECT_INSTRUCTIONS.md")
            .read_text(encoding="utf-8")
        )
        instructions = instructions.replace("__REQUEST_PATH__", self.prefix + "/requests/")
        instructions = instructions.replace("__PROCESS_TITLE__", self.process["title"])
        instructions = instructions.replace("__REPOSITORY__", self.channel().repository)
        instructions = instructions.replace("__BRANCH__", self.channel().branch)
        instructions += (
            chr(10)
            + "Current selected discussion file: "
            + self.prefix
            + "/contexts/"
            + str(record.id)
            + ".md"
            + chr(10)
        )
        context_result = github.publish(
            self.prefix + "/contexts/" + str(record.id) + ".md", packet.markdown.encode("utf-8")
        )
        instructions_result = github.publish(
            self.prefix + "/instructions/" + digest(instructions.encode("utf-8"))[:16] + ".md",
            instructions.encode("utf-8"),
        )
        return {
            "context": context_result,
            "project_instructions": instructions_result,
            "reference": record.reference().model_dump(mode="json"),
            "chatgpt_access": "not_verified_by_local_publication",
        }
