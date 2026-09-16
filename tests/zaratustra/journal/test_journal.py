"""Behavioral contracts for revisions, decisions, scope, retries and data export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from zipfile import ZipFile

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from zaratustra.commands import Command, Context, execute
from zaratustra.core import MutationError, Work, read_history, read_records
from zaratustra.home import HomeError, init_home, inspect_source
from zaratustra.journal import (
    MEDIA_TYPE,
    Change,
    JournalError,
    Reference,
    Registry,
    Scope,
    Store,
    TypeSpec,
    load_export,
    read_export,
)


def run(context: Context, action: str, **fields: Any) -> dict[str, Any]:
    return execute(
        context,
        Command.model_validate({"action": action, **fields}),
        source_ref="fictional-live-instruction",
    )


@pytest.fixture
def context(tmp_path: Path) -> Context:
    root = tmp_path / "home"
    root.mkdir()
    init_home(root)
    context = Context(home=root.as_posix())
    row = run(context, "process.create", title="Notes", purpose="Fictional journal")["process"]
    run(context, "process.create", title="Other", purpose="Fictional separate context")
    return Context(home=context.home, workspace=row["location"], process_id=UUID(row["id"]))


def episode(context: Context, **fields: Any) -> dict[str, Any]:
    return run(
        context,
        "record.create",
        **{
            "type_name": "episode",
            "title": "Проверка отчёта",
            "reason": "Substantial work result",
            "payload": {"situation": "Отчёт не открывается", "outcome": "Файл недоступен"},
            **fields,
        },
    )


def payload(context: Context, identity: str, **fields: Any) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(
        run(context, "record.read", record=identity, **fields)["payload_json"]
    )
    return result


def test_revision_history_and_one_atomic_audit(context: Context) -> None:
    path = Path(context.workspace or "")
    initial = read_records(path)
    row = episode(context)
    identity = row["record"]["id"]
    after = read_records(path)
    history = read_history(path)
    assert after.state_revision == initial.state_revision + 1
    assert len(history.process_events) == 1
    assert history.process_events[0].material.id == UUID(identity)
    assert not any(isinstance(r, Work) for r in after.records)
    changed = run(
        context,
        "record.revise",
        record=identity,
        expected_revision=1,
        payload={"situation": "Отчёт не открывается", "outcome": "Проверен путь к файлу"},
        reason="Уточнили причину",
    )
    assert changed["record"]["revision"] == 2
    assert payload(context, identity, revision=1)["outcome"] == "Файл недоступен"
    assert payload(context, identity)["outcome"] == "Проверен путь к файлу"
    assert run(context, "record.history", record=identity)["total"] == 2
    exact = run(context, "source.read", reference=row["reference"])
    assert json.loads(exact["payload_json"])["outcome"] == "Файл недоступен"


def test_decision_acceptance_binds_revision_and_episode_correction_changes_nothing(
    context: Context,
) -> None:
    ep = episode(context)
    proposed = run(
        context,
        "record.create",
        type_name="decision",
        title="Смена формата",
        payload={
            "commitment": "Отложить смену формата",
            "rationale": "Не проверен источник",
            "applies_to": "Учебный отчёт",
        },
        links=[ep["reference"]],
        reason="Предложение",
    )
    identity = proposed["record"]["id"]
    assert proposed["record"]["state"] == "proposed"
    with pytest.raises(JournalError, match="missing_authority"):
        run(context, "record.adopt", record=identity, expected_revision=1, reason="Принято")
    with pytest.raises(JournalError, match="changed_acceptance"):
        run(
            context,
            "record.adopt",
            record=identity,
            expected_revision=1,
            reason="Принято",
            authority_source="Owner said adopt this proposal",
            title="Другое содержание",
        )
    accepted = run(
        context,
        "record.adopt",
        record=identity,
        expected_revision=1,
        reason="Владелец принял предложение",
        authority_source="Прими это решение",
    )
    assert accepted["record"]["state"] == "accepted"
    run(
        context,
        "record.revise",
        record=ep["record"]["id"],
        expected_revision=1,
        payload={"situation": "Проверка", "outcome": "Причина в пути, не формате"},
        reason="Исправление",
    )
    still = run(context, "record.read", record=identity)["record"]
    assert still["state"] == "accepted" and still["revision"] == 2
    assert still["links"] == [ep["reference"]]
    with pytest.raises(JournalError, match="invalid_transition"):
        run(
            context,
            "record.revise",
            record=identity,
            expected_revision=2,
            payload={"commitment": "Незаметно сменить", "rationale": "Нет", "applies_to": "Всё"},
            reason="Исправление",
        )
    replaced = run(
        context,
        "record.replace",
        record=identity,
        expected_revision=2,
        payload={
            "commitment": "Проверить новый формат",
            "rationale": "Исходник доступен",
            "applies_to": "Один отчёт",
        },
        reason="Новое решение",
        authority_source="Теперь проверь",
    )
    assert replaced["record"]["previous"]["revision"] == 2
    assert payload(context, identity, revision=2)["commitment"] == "Отложить смену формата"
    revoked = run(
        context,
        "record.revoke",
        record=identity,
        expected_revision=3,
        reason="Отменено",
        authority_source="Отмени без замены",
    )
    assert revoked["record"]["state"] == "revoked"
    assert payload(context, identity)["commitment"] == "Проверить новый формат"


def test_exact_retry_conflict_and_invalid_type_do_not_create_another_record(
    context: Context,
) -> None:
    operation = uuid4()
    first = episode(context, operation_id=operation)
    retry = episode(context, operation_id=operation)
    assert retry["replayed"] and retry["record"] == first["record"]
    with pytest.raises(JournalError, match="operation_conflict"):
        episode(context, operation_id=operation, title="Changed intent")
    with pytest.raises(JournalError, match="type_unavailable"):
        episode(context, type_name="uninstalled")
    with pytest.raises(ValidationError):
        episode(context, payload={"outcome": "No situation"})
    assert run(context, "record.search")["matches"][0]["revision"] == 1
    assert len(read_history(Path(context.workspace or "")).process_events) == 1


def test_stale_updates_and_acceptance_refuse(context: Context) -> None:
    row = episode(context)
    run(
        context,
        "record.revise",
        record=row["record"]["id"],
        expected_revision=1,
        payload={"situation": "Проверено", "outcome": "Иная причина"},
        reason="Исправление",
    )
    with pytest.raises(JournalError, match="revision_conflict"):
        run(
            context,
            "record.revise",
            record=row["record"]["id"],
            expected_revision=1,
            payload={"situation": "Устарело", "outcome": "Устарело"},
            reason="stale",
        )
    source = inspect_source(Path(context.workspace or ""))
    stale = Store(Path(source["location"]), Scope(kind="process", id=UUID(source["id"])), "live")
    episode(context)
    with pytest.raises(MutationError, match="conflict"):
        stale.write(
            Change(
                operation_id=uuid4(),
                type_name="episode",
                title="Old snapshot",
                payload={"situation": "Before", "outcome": "After"},
                reason="test",
            )
        )


def test_existing_material_is_document_v1_without_reupload_or_changed_old_links(
    context: Context,
) -> None:
    saved = run(context, "material.save", title="Объяснение", text="Исходная версия")
    identity = saved["material_id"]
    original = run(context, "material.read", material=identity)
    assert payload(context, identity)["text"] == "Исходная версия"
    revised = run(
        context,
        "record.revise",
        record=identity,
        expected_revision=1,
        payload={"text": "Исправленная версия"},
        reason="Проверили описание",
    )
    assert revised["record"]["id"] == identity
    assert payload(context, identity, revision=1)["text"] == "Исходная версия"
    assert payload(context, identity)["text"] == "Исправленная версия"
    assert run(context, "material.read", material=identity) == original
    assert len(read_history(Path(context.workspace or "")).process_events) == 2


def test_shared_copy_does_not_grant_source_context_or_follow_local_revisions(
    context: Context,
) -> None:
    local = episode(context, payload={"situation": "Private situation", "outcome": "SECRET-ZEBRA"})
    with pytest.raises(JournalError, match="explicit_sharing_required"):
        episode(context, scope="home")
    shared = episode(
        context,
        scope="home",
        title="Общий вывод",
        authority_source="Share only this conclusion",
        links=[local["reference"]],
        payload={"situation": "Проверка источников", "outcome": "Проверять доступность до разбора"},
    )
    found = run(context, "record.search", process="Other", query="доступност")
    assert [row["id"] for row in found["matches"]] == [shared["record"]["id"]]
    denied = run(context, "source.read", process="Other", reference=local["reference"])
    assert denied["status"] == "scope_unavailable" and "SECRET-ZEBRA" not in json.dumps(denied)
    assert run(context, "record.search", process="Other", query="SECRET-ZEBRA")["matches"] == []
    run(
        context,
        "record.revise",
        record=local["record"]["id"],
        expected_revision=1,
        payload={"situation": "Private", "outcome": "Changed"},
        reason="Correction",
    )
    assert (
        payload(context, shared["record"]["id"], scope="home")["outcome"]
        == "Проверять доступность до разбора"
    )
    assert len(run(context, "process.list")["processes"]) == 2


def test_russian_queries_link_search_and_absence(context: Context) -> None:
    first = episode(context)
    episode(context, title="Погода", payload={"situation": "Поездка", "outcome": "Будет дождь"})
    assert (
        run(context, "record.search", query="недоступен")["matches"][0]["id"]
        == first["record"]["id"]
    )
    assert (
        run(context, "record.search", query="недоступ")["matches"][0]["id"] == first["record"]["id"]
    )
    assert run(context, "record.search", query="телепортация")["matches"] == []
    second = episode(context, links=[first["reference"]])
    assert (
        run(context, "record.search", reference=first["reference"])["matches"][0]["id"]
        == second["record"]["id"]
    )
    assert (
        "not proof of absence" in run(context, "record.search", query="телепортация")["limitation"]
    )


def test_export_contains_pinned_bytes_history_and_explicit_omission(
    context: Context, tmp_path: Path
) -> None:
    material = run(context, "material.save", title="Лог", text="Immutable proof")
    metadata = run(context, "material.read", material=material["material_id"])["material"]
    ref = {
        "scope": {"kind": "process", "id": str(context.process_id)},
        "kind": "material",
        "id": material["material_id"],
        "revision": metadata["revision"],
    }
    ep = episode(context, links=[ref])
    run(
        context,
        "record.revise",
        record=ep["record"]["id"],
        expected_revision=1,
        payload={"situation": "Уточнение", "outcome": "Теперь известно"},
        reason="Correction",
    )
    path = tmp_path / "selected.zip"
    result = run(context, "records.export", records=[ep["record"]["id"]], path=str(path))
    assert result["entry_count"] == 3
    manifest, values = load_export(path)
    assert len(manifest["schemas"]) == 1 and len(values) == 3
    assert (
        read_export(path, reference=Reference.model_validate(ep["reference"]))["record"]["revision"]
        == 1
    )
    assert read_export(path)["record_revision_count"] == 2
    assert any("base64" in row for row in values.values())
    shared = episode(
        context, scope="home", links=[ep["reference"]], authority_source="Share conclusion only"
    )
    shared_path = tmp_path / "shared.zip"
    result = run(
        context,
        "records.export",
        scope="home",
        records=[shared["record"]["id"]],
        path=str(shared_path),
    )
    assert result["missing"][0]["status"] == "scope_unavailable"
    assert read_export(shared_path)["entry_count"] == 1
    assert (
        read_export(shared_path, reference=Reference.model_validate(ep["reference"]))["status"]
        == "scope_unavailable"
    )
    with pytest.raises(FileExistsError):
        run(context, "records.export", records=[ep["record"]["id"]], path=str(path))


def test_export_rejects_tampered_content(context: Context, tmp_path: Path) -> None:
    ep = episode(context)
    path, bad = tmp_path / "good.zip", tmp_path / "bad.zip"
    run(context, "records.export", records=[ep["record"]["id"]], path=str(path))
    with ZipFile(path) as source, ZipFile(bad, "w") as destination:
        for name in source.namelist():
            content = source.read(name) if name == "manifest.json" else b"{}"
            destination.writestr(name, content)
    with pytest.raises(JournalError, match="invalid_export"):
        read_export(bad)


def test_additional_registered_type_reuses_unchanged_storage(context: Context) -> None:
    class Checkpoint(BaseModel):
        model_config = ConfigDict(extra="forbid")
        summary: str
        passed: bool

    registry = Registry()
    registry.register(TypeSpec("test.checkpoint", 1, Checkpoint))
    path = Path(context.workspace or "")
    scope = Scope(kind="process", id=context.process_id or uuid4())
    store = Store(path, scope, "test registration", registry)
    change = Change(
        operation_id=uuid4(),
        type_name="test.checkpoint",
        title="Checkpoint",
        payload={"summary": "Observed result", "passed": True},
        reason="Test type",
    )
    record = store.write(change)["record"]
    fresh = Store(path, scope, "new call", registry)
    assert fresh.get(UUID(record["id"])).payload["passed"] is True
    assert registry.describe()[0]["type"] == "test.checkpoint"
    assert read_history(path).process_events[0].material.media_type == MEDIA_TYPE
    with pytest.raises(JournalError, match="type_conflict"):
        registry.register(TypeSpec("test.checkpoint", 1, Checkpoint))


def test_reserved_material_type_and_missing_pinned_source_refuse(context: Context) -> None:
    with pytest.raises(HomeError, match="reserved_type"):
        run(context, "material.save", media_type=MEDIA_TYPE, text="{}", title="Forgery")
    reference = Reference(
        scope=Scope(kind="process", id=context.process_id or uuid4()), id=uuid4(), revision=1
    )
    with pytest.raises(JournalError, match="not_found"):
        episode(context, links=[reference.model_dump(mode="json")])
    assert read_records(Path(context.workspace or "")).state_revision == 1


def test_document_export_pins_old_material_and_standalone_reads(
    context: Context, tmp_path: Path
) -> None:
    original = run(context, "material.save", title="Editable", text="old")
    identity = original["material_id"]
    run(
        context,
        "record.revise",
        record=identity,
        expected_revision=1,
        payload={"text": "new"},
        reason="Edit explanation",
    )
    path = tmp_path / "document.zip"
    run(context, "records.export", records=[identity], path=str(path))
    manifest, values = load_export(path)
    assert len(values) == 2 and manifest["missing"] == []
    contents = {
        value["record"]["revision"]: value["record"]["payload"]["text"] for value in values.values()
    }
    assert contents == {1: "old", 2: "new"}


def test_projection_failure_is_committed_and_exact_retry_recovers(
    context: Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zaratustra.core import mutations

    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("fictional projection failure")

    operation = uuid4()
    with monkeypatch.context() as patch:
        patch.setattr(mutations, "write_projection", fail)
        result = episode(context, operation_id=operation)
    assert result["committed"] and "projection_warning" in result
    retry = episode(context, operation_id=operation)
    assert retry["replayed"]
    assert len(read_history(Path(context.workspace or "")).process_events) == 1


def test_shared_read_does_not_initialize_and_export_excludes_shared_by_default(
    context: Context, tmp_path: Path
) -> None:
    shared_path = Path(context.home) / ".zara-home" / "shared"
    assert run(context, "record.search", scope="home")["matches"] == []
    assert not shared_path.exists()
    shared = episode(context, scope="home", authority_source="Share the conclusion")
    local = episode(context, links=[shared["reference"]])
    output = tmp_path / "local.zip"
    result = run(context, "records.export", records=[local["record"]["id"]], path=str(output))
    assert result["missing"][0]["reference"] == shared["reference"]
    included = tmp_path / "with-shared.zip"
    result = run(
        context,
        "records.export",
        records=[local["record"]["id"]],
        path=str(included),
        export_shared=True,
    )
    assert result["missing"] == [] and result["entry_count"] == 2


def test_content_paging_is_complete_for_source_and_record(context: Context) -> None:
    original = run(context, "material.save", title="Source", text="Пример текста")
    material = run(context, "material.read", material=original["material_id"])["material"]
    reference = {
        "scope": {"kind": "process", "id": str(context.process_id)},
        "kind": "material",
        "id": material["id"],
        "revision": material["revision"],
    }
    first = run(context, "source.read", reference=reference, content_limit=4)
    second = run(context, "source.read", reference=reference, content_offset=first["next_offset"])
    assert first["text"] + second["text"] == "Пример текста"
    record = episode(context)["record"]["id"]
    first = run(context, "record.read", record=record, content_limit=20)
    second = run(context, "record.read", record=record, content_offset=first["next_offset"])
    combined = json.loads(first["payload_json"] + second["payload_json"])
    assert combined["outcome"] == "Файл недоступен" and second["next_offset"] is None


def test_standalone_export_can_page_every_record_and_large_link_inventory(
    context: Context, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from zaratustra.commands.__main__ import main

    source = episode(context)
    records = [source["record"]["id"]]
    for index in range(21):
        saved = episode(context, title=f"Episode {index}", links=[source["reference"]] * 32)
        records.append(saved["record"]["id"])
    path = tmp_path / "paged.zip"
    run(context, "records.export", records=records, path=str(path))
    first = read_export(path, limit=1)
    assert len(first["records"]) == 1 and len(first["links"]) == 1
    assert first["counts"]["links"] == 672 and first["next_offset"] == 1
    assert main(["inspect-export", str(path), "--offset", "20", "--limit", "5"]) == 0
    page = json.loads(capsys.readouterr().out)["result"]
    assert len(page["records"]) == 2 and len(page["links"]) == 5
    assert page["records"][0]["id"] == records[20]
    assert page["next_offset"] == 25
