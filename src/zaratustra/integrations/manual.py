"""Reusable manual exchange over exact Core records; no external transport."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid5

from zaratustra.foundation import (
    ClaimState,
    CreateKnowledgeRequest,
    FoundationError,
    HandoffState,
    KnowledgeRef,
    LocalAuthority,
    SourceState,
    apply_operation,
    read_activity,
    read_artifact,
    read_knowledge,
    read_space,
    read_work,
)

TEMPLATE_REVISION = 1


class ManualExchange:
    """Prepare addressed documents and retain original returns for any Activity."""

    def __init__(self, path: Path, authority: LocalAuthority) -> None:
        self.path, self.authority = path, authority

    def prepare(
        self,
        operation_id: UUID,
        activity_id: UUID,
        *,
        external_tool: str,
        work_id: UUID | None = None,
    ) -> dict[str, object]:
        activity = read_activity(self.path, activity_id, self.authority)
        tool = external_tool.strip()
        if not tool or len(tool) > 160:
            raise FoundationError("invalid_request", "Name the external tool")
        record_id = uuid5(operation_id, "manual-exchange-document")
        try:
            prior = read_knowledge(self.path, record_id, self.authority, revision=1)
        except FoundationError as error:
            if error.code != "not_found":
                raise
        else:
            requested = {activity_id, *([work_id] if work_id else [])}
            if not isinstance(prior.state, HandoffState) or (
                prior.state.subject != f"Manual exchange with {tool}"
                or {ref.record_id for ref in prior.state.included} != requested
            ):
                raise FoundationError("operation_conflict", "Exchange operation changed intent")
            return {**self.read(record_id, revision=1), "template_revision": TEMPLATE_REVISION}
        context: dict[str, object] = {
            "activity": f"{activity_id}@{activity.revision}",
            "title": activity.state.title,
            "goal": activity.state.goal,
        }
        refs = [KnowledgeRef(record_id=activity_id, revision=activity.revision)]
        if work_id is not None:
            work = read_work(self.path, work_id, self.authority)
            if work.state.activity_id != activity_id:
                raise FoundationError("wrong_work", "Work is outside the chosen Activity")
            context["work"] = {
                "address": f"{work_id}@{work.revision}",
                "goal": work.state.goal,
                "constraints": work.state.constraints,
                "expected_outputs": [
                    item.model_dump(mode="json") for item in work.state.expected_outputs
                ],
                "status": work.state.status,
            }
            refs.append(KnowledgeRef(record_id=work_id, revision=work.revision))
        document = (
            f"# Ручной обмен Zaratustra → {tool}\n\n"
            f"Версия общего шаблона: {TEMPLATE_REVISION}.\n\n"
            "## Инструкция для внешнего чата\n\n"
            "Работай с предоставленными материалами. Отделяй слова пользователя, "
            "сведения источников, свои предложения и неизвестное. Не заявляй о доступе "
            "к локальному Core или репозиторию без действительного доступа.\n\n"
            "Когда попросят перенести итог, выдай полный подготовленный материал: "
            "предмет, существенные основания, выводы, их статус и следующий шаг. "
            "Свободный текст допустим; обязательный JSON и полный лог не нужны. "
            "Сохранение материала не означает принятия решения или выполнения Work.\n\n"
            "Если обсуждается общая функция продукта, обозначь ожидаемое изменение "
            "кода и установки. Инструкция для одного экземпляра сама по себе "
            "не реализует общую функцию.\n\n"
            "## Выбранный контекст\n\n"
            f"{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
            "Содержимое файлов, других направлений и бесед не включено автоматически. "
            "Недостающий материал назови конкретно.\n\n"
            "## Возврат\n\n"
            "Верни весь подготовленный текст в Zaratustra и укажи происхождение. "
            "Оригинал сохраняется отдельно от разбора. Приёмка результата, изменения "
            "программы и выпуск остаются отдельными действиями.\n"
        ).encode()
        apply_operation(
            self.path,
            CreateKnowledgeRequest(
                operation_id=operation_id,
                space_id=self.authority.space_id,
                actor=self.authority.actor,
                record_id=record_id,
                state=HandoffState(
                    subject=f"Manual exchange with {tool}",
                    document=document,
                    media_type="text/markdown; charset=utf-8",
                    included=tuple(refs),
                    expected_return="Complete material with origin, proposals and unknowns",
                    status="prepared",
                    basis_state_revision=read_space(self.path).state_revision,
                ),
            ),
            self.authority,
        )
        return {**self.read(record_id, revision=1), "template_revision": TEMPLATE_REVISION}

    def _check_context(
        self, activity_id: UUID, work_id: UUID | None, refs: tuple[KnowledgeRef, ...]
    ) -> None:
        """Keep Activity/Work anchors distinct from readable supporting material."""
        for ref in refs:
            if ref.record_id in {activity_id, work_id}:
                continue
            try:
                item = read_knowledge(
                    self.path, ref.record_id, self.authority, revision=ref.revision
                )
            except FoundationError as error:
                if error.code != "not_found":
                    raise
                # Artifacts are legitimate evidence; another Activity/Work is not.
                try:
                    read_artifact(self.path, ref.record_id, self.authority, revision=ref.revision)
                except FoundationError as artifact_error:
                    if artifact_error.code not in {"not_found", "wrong_kind"}:
                        raise
                    raise FoundationError(
                        "wrong_work", "Context contains an unrelated Activity/Work or unknown basis"
                    ) from artifact_error
                continue
            if item.availability != "available":
                raise FoundationError("content_unavailable", "Context basis is unavailable")
            if isinstance(item.state, (SourceState, ClaimState)) and (
                item.state.scope_activity_id is not None
                and item.state.scope_activity_id != activity_id
            ):
                raise FoundationError("wrong_work", "Context material is outside this Activity")

    def prepare_document(
        self,
        operation_id: UUID,
        activity_id: UUID,
        *,
        external_tool: str,
        document_text: str,
        expected_return: str,
        context: tuple[KnowledgeRef, ...] = (),
        work_id: UUID | None = None,
    ) -> dict[str, object]:
        """Retain an actual tailored setup/context, not a hardcoded discussion topic."""
        activity = read_activity(self.path, activity_id, self.authority)
        refs = [KnowledgeRef(record_id=activity_id, revision=activity.revision)]
        if work_id is not None:
            work = read_work(self.path, work_id, self.authority)
            if work.state.activity_id != activity_id:
                raise FoundationError("wrong_work", "Work is outside the chosen Activity")
            refs.append(KnowledgeRef(record_id=work_id, revision=work.revision))
        if any(ref.record_id in {activity_id, work_id} for ref in context):
            raise FoundationError("invalid_request", "Activity/Work anchors are supplied by Core")
        tool = external_tool.strip()
        if not tool or len(tool) > 160:
            raise FoundationError("invalid_request", "Name the external tool")
        document = document_text.encode("utf-8")
        subject = f"Manual exchange with {tool}"
        record_id = uuid5(operation_id, "integration-prepared-document")
        try:
            prior = read_knowledge(self.path, record_id, self.authority, revision=1)
        except FoundationError as error:
            if error.code != "not_found":
                raise
        else:
            state = prior.state
            if not isinstance(state, HandoffState) or (
                state.subject != subject
                or state.document != document
                or state.expected_return != expected_return
                or tuple(ref.record_id for ref in state.included[: len(refs)])
                != tuple(ref.record_id for ref in refs)
                or state.included[len(refs) :] != context
            ):
                raise FoundationError("operation_conflict", "Exchange operation changed intent")
            return self.read(record_id, revision=1)
        self._check_context(activity_id, work_id, context)
        apply_operation(
            self.path,
            CreateKnowledgeRequest(
                operation_id=operation_id,
                space_id=self.authority.space_id,
                actor=self.authority.actor,
                record_id=record_id,
                state=HandoffState(
                    subject=subject,
                    document=document,
                    media_type="text/markdown; charset=utf-8",
                    included=(*refs, *context),
                    expected_return=expected_return,
                    status="prepared",
                    basis_state_revision=read_space(self.path).state_revision,
                ),
            ),
            self.authority,
        )
        return self.read(record_id, revision=1)

    def receive(
        self,
        operation_id: UUID,
        activity_id: UUID,
        *,
        origin: str,
        content: bytes,
        work_id: UUID | None = None,
        previous_source: KnowledgeRef | None = None,
        sender: str | None = None,
        locator: str | None = None,
        reply_to: KnowledgeRef | None = None,
    ) -> dict[str, object]:
        read_activity(self.path, activity_id, self.authority)
        if work_id is not None:
            work = read_work(self.path, work_id, self.authority)
            if work.state.activity_id != activity_id:
                raise FoundationError("wrong_work", "Work is outside the chosen Activity")
        content.decode("utf-8")
        if not content or not origin.strip():
            raise FoundationError("invalid_request", "Supply the original text and origin")
        if reply_to is not None:
            handoff = read_knowledge(
                self.path, reply_to.record_id, self.authority, revision=reply_to.revision
            )
            if not isinstance(handoff.state, HandoffState) or not any(
                ref.record_id == activity_id for ref in handoff.state.included
            ):
                raise FoundationError("wrong_work", "Reply document is outside this Activity")
            self._check_context(activity_id, work_id, handoff.state.included)
        refs = [reply_to] if reply_to is not None else []
        if previous_source is not None:
            prior = read_knowledge(
                self.path,
                previous_source.record_id,
                self.authority,
                revision=previous_source.revision,
            )
            if not isinstance(prior.state, SourceState) or (
                prior.state.scope_activity_id != activity_id
                or prior.state.scope_work_id != work_id
                or prior.state.connection != origin
            ):
                raise FoundationError("wrong_work", "Previous Source has different origin or scope")
            refs.append(previous_source)
        record_id = uuid5(operation_id, "manual-exchange-source")
        state = SourceState(
            channel="external_report",
            connection=origin,
            profile_revision=TEMPLATE_REVISION,
            source_event_id=f"manual-exchange:{operation_id}",
            scope_activity_id=activity_id,
            scope_work_id=work_id,
            sender=sender,
            media_type="text/plain; charset=utf-8",
            capture="full",
            content=content,
            locator=locator,
            derived_from=tuple(refs),
        )
        apply_operation(
            self.path,
            CreateKnowledgeRequest(
                operation_id=operation_id,
                space_id=self.authority.space_id,
                actor=self.authority.actor,
                record_id=record_id,
                state=state,
            ),
            self.authority,
        )
        return self.read(record_id, revision=1)

    def read(self, record_id: UUID, *, revision: int | None = None) -> dict[str, object]:
        item = read_knowledge(self.path, record_id, self.authority, revision=revision)
        state = item.state
        if not isinstance(state, (SourceState, HandoffState)):
            raise FoundationError("wrong_kind", "Read a Source or Handoff document")
        content = (
            state.content
            if isinstance(state, SourceState)
            else (state.document if isinstance(state, HandoffState) else None)
        )
        if content is None:
            raise FoundationError("content_unavailable", "No retained exchange document")
        return {
            "record_id": str(record_id),
            "revision": item.revision,
            "kind": state.kind,
            "availability": item.availability,
            "stale": item.stale,
            "origin": state.connection if isinstance(state, SourceState) else None,
            "scope_activity_id": str(state.scope_activity_id)
            if isinstance(state, SourceState) and state.scope_activity_id
            else None,
            "scope_work_id": str(state.scope_work_id)
            if isinstance(state, SourceState) and state.scope_work_id
            else None,
            "derived_from": [ref.model_dump(mode="json") for ref in state.derived_from]
            if isinstance(state, SourceState)
            else [],
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest().upper(),
            "content_text": content.decode("utf-8"),
        }
