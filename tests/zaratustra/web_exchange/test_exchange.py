"""User-path, recovery and transport boundaries through the real common commands."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError

from zaratustra.commands import Command, Context, execute
from zaratustra.commands.connect import connect_agent
from zaratustra.commands.registry import EXTENSIONS, CommandSpec, register
from zaratustra.core import read_records
from zaratustra.home import init_home
from zaratustra.journal import JournalError, Reference, Scope, Store, read_export
from zaratustra.web_exchange import Exchange, GitHub, Origin


def run(context: Context, action: str, **fields: Any) -> dict[str, Any]:
    return execute(
        context,
        Command.model_validate({"action": action, **fields}),
        source_ref="fictional-owner-web-work",
    )


@pytest.fixture
def context(tmp_path: Path) -> Context:
    root = tmp_path / "home"
    root.mkdir()
    init_home(root)
    base = Context(home=root.as_posix())
    row = run(base, "process.create", title="Учебный Development", purpose="Web exchange trial")[
        "process"
    ]
    selected = Context(home=base.home, workspace=row["location"], process_id=UUID(row["id"]))
    run(selected, "web.configure", payload={"repository": "fictional-owner/private-home"})
    return selected


def service(context: Context) -> Exchange:
    assert context.workspace is not None and context.process_id is not None
    return Exchange(
        Store(
            Path(context.workspace),
            Scope(kind="process", id=context.process_id),
            "fictional-owner-web-work",
        ),
        {"id": str(context.process_id), "title": "Учебный Development"},
    )


def capture(context: Context, text: str, name: str = "request.md") -> dict[str, Any]:
    current = service(context)
    raw = text.encode("utf-8")
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + bytes([0]) + raw).hexdigest()
    return current.capture(
        Origin(
            repository="fictional-owner/private-home",
            branch="main",
            path=current.prefix + "/requests/" + name,
            blob=blob,
            commit="a" * 40,
        ),
        raw,
    )


def saved(context: Context, text: str, **extra: Any) -> dict[str, Any]:
    return run(
        context,
        "record.create",
        type_name="document",
        title="Выбранный материал",
        payload={"text": text},
        reason="Owner asked to preserve source",
        **extra,
    )


def review(
    ctx: Context, request: dict[str, Any], items: list[dict[str, Any]], **extra: Any
) -> dict[str, Any]:
    current = run(ctx, "web.read", record=request["record"]["id"])
    return run(
        ctx,
        "web.review",
        record=current["record"]["id"],
        expected_revision=current["record"]["revision"],
        payload={"reviewed_full_request": True, "items": items, **extra},
        reason="Reviewed full incoming request",
    )


def test_freeform_original_replay_changed_file_and_pages(context: Context) -> None:
    text = chr(0xFEFF) + "{ broken JSON " + chr(13) + chr(10) + "Сохрани идею.  "
    first = capture(context, text)
    before = read_records(Path(context.workspace or "")).state_revision
    repeated = capture(context, text)
    assert repeated["replayed"] and first["reference"] == repeated["reference"]
    assert read_records(Path(context.workspace or "")).state_revision == before
    opened = run(context, "web.read", record=first["record"]["id"], content_limit=5)
    tail = run(
        context, "web.read", record=first["record"]["id"], content_offset=opened["next_offset"]
    )
    assert opened["original"] + tail["original"] == text
    assert opened["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    changed = capture(context, text + " Исправление.")
    assert changed["record"]["id"] != first["record"]["id"]
    assert run(context, "web.list")["total"] == 2
    assert (
        run(context, "record.read", record=first["record"]["id"], revision=1)["record"]["type_name"]
        == "web_request"
    )


def test_attachment_partial_progress_interrupted_delivery_and_new_chat(context: Context) -> None:
    request = capture(context, "Сохрани текст. Приложи отчёт.pdf.")
    items: list[dict[str, Any]] = [
        {
            "key": "text",
            "source_quote": "Сохрани текст.",
            "intent": "store",
            "description": "Preserve text",
        },
        {
            "key": "report",
            "source_quote": "Приложи отчёт.pdf.",
            "intent": "store",
            "description": "Preserve report",
            "files": [{"name": "отчёт.pdf"}],
        },
    ]
    review(context, request, items)
    opened = run(context, "web.read", record=request["record"]["id"])
    assert opened["status"] == "waiting"
    operation = opened["deliveries"][0]["operation_id"]
    result = saved(context, "Сохраняемый текст", operation_id=operation)
    # Crash boundary: canonical write committed, progress update did not happen.
    fresh = Context.model_validate_json(context.model_dump_json())
    resumed = run(fresh, "web.read", record=request["record"]["id"])
    assert resumed["deliveries"][0]["committed_result"] == result["reference"]
    assert saved(fresh, "Сохраняемый текст", operation_id=operation)["replayed"]
    items[0].update(outcome="done", result=result["reference"])
    review(fresh, request, items)
    state = run(fresh, "web.read", record=request["record"]["id"])
    with pytest.raises(JournalError, match="unfinished_request"):
        run(
            fresh,
            "web.complete",
            record=state["record"]["id"],
            expected_revision=state["record"]["revision"],
            payload={"process_revision": state["process_revision"]},
        )
    report_path = Path(fresh.home or "") / "report.pdf"
    raw_report = b"fictional report" + bytes([13, 10, 0, 255])
    report_path.write_bytes(raw_report)
    report = run(
        fresh,
        "web.attach",
        record=request["record"]["id"],
        path=report_path.as_posix(),
        payload={"item_key": "report", "name": "отчёт.pdf"},
    )
    assert report["sha256"] == hashlib.sha256(raw_report).hexdigest()
    with pytest.raises(JournalError, match="changed_attachment"):
        review(fresh, request, items)
    exact = run(fresh, "source.read", reference=report["reference"])
    assert base64.b64decode(json.loads(exact["payload_json"])["base64"]) == raw_report
    assert run(
        fresh,
        "web.attach",
        record=request["record"]["id"],
        path=report_path.as_posix(),
        payload={"item_key": "report", "name": "отчёт.pdf"},
    )["replayed"]
    items[1].update(
        outcome="done",
        result=report["reference"],
        files=[{"name": "отчёт.pdf", "reference": report["reference"]}],
    )
    review(fresh, request, items)
    state = run(fresh, "web.read", record=request["record"]["id"])
    run(
        fresh,
        "web.complete",
        record=state["record"]["id"],
        expected_revision=state["record"]["revision"],
        payload={"process_revision": state["process_revision"]},
    )
    assert run(fresh, "web.list")["requests"] == []
    assert run(fresh, "web.list", payload={"include_completed": True})["total"] == 1
    assert capture(fresh, "Сохрани текст. Приложи отчёт.pdf.")["replayed"]
    assert run(fresh, "web.list")["total"] == 0
    assert run(
        fresh,
        "web.attach",
        record=request["record"]["id"],
        path=report_path.as_posix(),
        payload={"item_key": "report", "name": "отчёт.pdf"},
    )["replayed"]
    report_path.write_bytes(b"changed file")
    before = read_records(Path(fresh.workspace or "")).state_revision
    with pytest.raises(JournalError, match="attachment_conflict"):
        run(
            fresh,
            "web.attach",
            record=request["record"]["id"],
            path=report_path.as_posix(),
            payload={"item_key": "report", "name": "отчёт.pdf"},
        )
    assert read_records(Path(fresh.workspace or "")).state_revision == before


def test_attachment_pins_bytes_and_recovers_interrupted_binding(
    context: Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = capture(context, "Сохрани файл.")
    review(
        context,
        request,
        [
            {
                "key": "file",
                "source_quote": "Сохрани файл.",
                "intent": "store",
                "description": "File",
                "files": [{"name": "file.txt"}],
            }
        ],
    )
    path = Path(context.home or "") / "file.txt"
    path.write_bytes(b"original" + bytes([13, 10]))
    original_write = Exchange.write

    def concurrent_write(
        self: Exchange, type_name: str, *args: Any, **kwargs: Any
    ) -> dict[str, Any]:
        if type_name == "web_request":
            raise JournalError("revision_conflict", "Simulated interruption before binding")
        result = original_write(self, type_name, *args, **kwargs)
        run(
            context,
            "record.revise",
            record=result["record"]["id"],
            expected_revision=1,
            payload={"text": "Later edited explanation"},
            reason="Concurrent edit",
        )
        return result

    monkeypatch.setattr(Exchange, "write", concurrent_write)
    received = run(
        context,
        "web.attach",
        record=request["record"]["id"],
        path=path.as_posix(),
        payload={"item_key": "file", "name": "file.txt"},
    )
    assert received["binding_pending"] and received["reference"]["revision"] == 1
    monkeypatch.setattr(Exchange, "write", original_write)
    retried = run(
        context,
        "web.attach",
        record=request["record"]["id"],
        path=path.as_posix(),
        payload={"item_key": "file", "name": "file.txt"},
    )
    assert retried["reference"] == received["reference"]
    source = run(context, "source.read", reference=retried["reference"])
    assert base64.b64decode(json.loads(source["payload_json"])["base64"]) == path.read_bytes()
    opened = run(context, "web.read", record=request["record"]["id"])
    assert opened["review"]["items"][0]["files"][0]["reference"] == received["reference"]


def test_no_dropped_items_fabricated_quotes_or_foreign_file(context: Context) -> None:
    request = capture(context, "Сохрани отчёт. Есть вопрос.")
    items: list[dict[str, Any]] = [
        {
            "key": "report",
            "source_quote": "Сохрани отчёт.",
            "intent": "store",
            "description": "Report",
            "files": [{"name": "Report"}],
        },
        {
            "key": "question",
            "source_quote": "Есть вопрос.",
            "intent": "clarify",
            "description": "Ask owner",
        },
    ]
    review(context, request, items)
    with pytest.raises(JournalError, match="dropped_item"):
        review(context, request, items[:1])
    with pytest.raises(JournalError, match="dropped_attachment"):
        review(context, request, [items[0] | {"files": []}, items[1]])
    with pytest.raises(JournalError, match="missing_quote"):
        review(context, request, [items[0], items[1] | {"source_quote": "Владелец утвердил всё"}])
    foreign = Reference(scope=Scope(kind="process", id=uuid4()), id=uuid4(), revision=1).model_dump(
        mode="json"
    )
    with pytest.raises(JournalError, match="attachment_not_received"):
        review(
            context,
            request,
            [items[0] | {"files": [{"name": "Report", "reference": foreign}]}, items[1]],
        )
    with pytest.raises(JournalError, match="scope_unavailable"):
        review(context, request, [items[0] | {"result": foreign}, items[1]])
    with pytest.raises(JournalError, match="managed_type"):
        run(
            context,
            "record.revise",
            record=request["record"]["id"],
            expected_revision=2,
            payload={},
            reason="Attempt bypass",
        )
    with pytest.raises(ValidationError):
        review(context, request, [items[0] | {"outcome": "done"}, items[1]])


def test_snapshot_only_selected_sources_staleness_and_export(
    context: Context, tmp_path: Path
) -> None:
    selected = saved(context, "Approved basis v1")
    saved(context, "PRIVATE UNSELECTED HISTORY")
    operation = uuid4()
    packet = run(
        context,
        "web.prepare",
        operation_id=operation,
        payload={"question": "Discuss this basis", "references": [selected["reference"]]},
    )
    assert run(
        context,
        "web.prepare",
        operation_id=operation,
        payload={"question": "Discuss this basis", "references": [selected["reference"]]},
    )["replayed"]
    read = run(context, "record.read", record=packet["record"]["id"])
    assert (
        "Approved basis v1" in read["payload_json"]
        and "PRIVATE UNSELECTED" not in read["payload_json"]
    )
    request = capture(context, "Сохрани предложение.")
    item = {
        "key": "proposal",
        "source_quote": "Сохрани предложение.",
        "intent": "store",
        "description": "Discussion proposal",
    }
    run(
        context,
        "record.revise",
        record=selected["record"]["id"],
        expected_revision=1,
        payload={"text": "Approved basis v2"},
        reason="Owner corrected basis",
    )
    with pytest.raises(JournalError, match="changed_context"):
        review(context, request, [item], context=packet["reference"])
    review(
        context,
        request,
        [item],
        context=packet["reference"],
        context_note="Basis changed; retain proposal only, revisit before application",
    )
    opened = run(context, "web.read", record=request["record"]["id"])
    assert opened["context"]["status"] == "selected_sources_changed"
    package = tmp_path / "request.zip"
    run(context, "records.export", records=[request["record"]["id"]], path=package.as_posix())
    assert (
        read_export(package, reference=Reference.model_validate(packet["reference"]))["status"]
        == "available"
    )


def test_completion_requires_fresh_process_and_actual_apply_authority(context: Context) -> None:
    request = capture(context, "Прими правило: один фокус.")
    decision = run(
        context,
        "record.create",
        type_name="decision",
        title="Фокус",
        payload={
            "commitment": "Один фокус",
            "rationale": "Согласовано",
            "applies_to": "Учебный процесс",
        },
        reason="Preserve specific proposal",
    )
    accepted = run(
        context,
        "record.adopt",
        record=decision["record"]["id"],
        expected_revision=1,
        authority_source="Прими правило: один фокус.",
        reason="Specific owner instruction",
    )
    item = {
        "key": "rule",
        "source_quote": "Прими правило: один фокус.",
        "intent": "apply",
        "description": "Accept focus rule",
        "outcome": "done",
        "result": accepted["reference"],
    }
    with pytest.raises(ValidationError):
        review(context, request, [item])
    item["authority_quote"] = "Прими правило: один фокус."
    review(context, request, [item])
    state = run(context, "web.read", record=request["record"]["id"])
    saved(context, "Concurrent later work")
    with pytest.raises(JournalError, match="revision_conflict"):
        run(
            context,
            "web.complete",
            record=state["record"]["id"],
            expected_revision=state["record"]["revision"],
            payload={"process_revision": state["process_revision"]},
        )
    with pytest.raises(JournalError, match="changed_delivery"):
        review(context, request, [item | {"outcome": "pending"}])


def test_registry_schema_connection_and_no_source_edits_for_extra_command(
    context: Context, tmp_path: Path
) -> None:
    class Input(BaseModel):
        message: str

    def handler(
        ctx: Context, command: Command, source: str, operation: UUID, guard: int | None
    ) -> dict[str, Any]:
        return {"echo": Input.model_validate(command.payload).message}

    name = "test.web_echo"
    register(CommandSpec(name, Input, handler, "Fictional registered extension"))
    try:
        assert run(context, name, payload={"message": "hello"}) == {"echo": "hello"}
        assert name in Command.model_json_schema()["properties"]["action"]["enum"]
        assert name in {r["name"] for r in run(context, "context.read")["capabilities"]["commands"]}
        with pytest.raises(ValidationError):
            run(context, name, payload={})
        with pytest.raises(ValueError, match="Duplicate"):
            register(CommandSpec(name, Input, handler, "duplicate"))
    finally:
        del EXTENSIONS[name]
    directory = tmp_path / "agent"
    directory.mkdir()
    result = connect_agent(directory, Path(context.home), agent="pi")
    installed = Path(result["connection"]).read_text(encoding="utf-8")
    assert "web.pull" in installed and "web.review" in installed and "committed_result" in installed
    assert run(context, "command.list", query="web.review")["extensions"][0]["payload_schema"][
        "required"
    ] == ["reviewed_full_request", "items"]


class Remote:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.calls: list[tuple[str, Any]] = []

    def entries(self) -> list[dict[str, Any]]:
        return [
            {
                "path": path,
                "mode": "100644",
                "type": "blob",
                "size": len(raw),
                "sha": hashlib.sha1(
                    b"blob " + str(len(raw)).encode() + bytes([0]) + raw
                ).hexdigest(),
            }
            for path, raw in self.files.items()
        ]

    def api(self, route: str, body: dict[str, Any] | None = None) -> Any:
        self.calls.append((route, body))
        if route.startswith("commits/"):
            return {"sha": "a" * 40, "commit": {"tree": {"sha": "b" * 40}}}
        if route.startswith("git/trees/"):
            return {"tree": self.entries(), "truncated": False}
        if route.startswith("git/blobs/"):
            entry = next(e for e in self.entries() if e["sha"] == route.split("/")[-1])
            return {"content": base64.b64encode(self.files[entry["path"]]).decode()}
        assert body is not None
        path = route.removeprefix("contents/")
        assert path not in self.files
        self.files[path] = base64.b64decode(body["content"])
        entry = next(e for e in self.entries() if e["path"] == path)
        return {
            "content": {"sha": entry["sha"], "html_url": "https://example.invalid/" + path},
            "commit": {"sha": "c" * 40},
        }


def test_github_selected_transport_retries_partial_failures_and_pagination(
    context: Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = Remote()
    monkeypatch.setattr(GitHub, "api", lambda self, route, body=None: remote.api(route, body))
    prefix = service(context).prefix
    remote.files[prefix + "/requests/a.md"] = "Сохрани эту идею".encode()
    remote.files[prefix + "/requests/b.json"] = b"{ broken: keep everything"
    remote.files[prefix + "/requests/c.pdf"] = bytes([255, 254])
    remote.files["other-process/requests/private.md"] = b"not selected"
    remote.files["home.sqlite3"] = b"never synchronize"
    page = run(context, "web.pull", limit=2)
    assert len(page["received"]) == 2 and page["next_offset"] == 2
    second = run(context, "web.pull", offset=2, limit=2)
    assert len(second["failures"]) == 1 and second["next_offset"] is None
    assert run(context, "web.pull", limit=2)["received"][0]["replayed"]
    assert run(context, "web.list")["total"] == 2
    packet = run(context, "web.prepare", payload={"question": "Discuss selected question"})
    published = run(
        context,
        "web.publish",
        record=packet["record"]["id"],
        payload={"selected_publication": True},
    )
    assert published["chatgpt_access"] == "not_verified_by_local_publication"
    assert run(
        context,
        "web.publish",
        record=packet["record"]["id"],
        payload={"selected_publication": True},
    )["context"]["replayed"]
    writes = [route for route, body in remote.calls if body is not None]
    assert len(writes) == 2 and all(route.startswith("contents/" + prefix) for route in writes)
    assert b"branch main" in remote.files[published["project_instructions"]["path"]]
    assert remote.files["home.sqlite3"] == b"never synchronize"
    remote.files[published["context"]["path"]] = b"concurrent edit"
    with pytest.raises(JournalError, match="publication_conflict"):
        run(
            context,
            "web.publish",
            record=packet["record"]["id"],
            payload={"selected_publication": True},
        )


def test_material_receipt_recovery_and_later_owner_authority(context: Context) -> None:
    request = capture(context, "Обсуди правило.")
    item: dict[str, Any] = {
        "key": "rule",
        "source_quote": "Обсуди правило.",
        "intent": "clarify",
        "description": "Await specific owner choice",
    }
    review(context, request, [item])
    opened = run(context, "web.read", record=request["record"]["id"])
    operation = opened["deliveries"][0]["operation_id"]
    run(
        context,
        "material.save",
        title="Later owner instruction",
        text='Прими правило "один фокус".',
        operation_id=operation,
    )
    resumed = run(context, "web.read", record=request["record"]["id"])
    authority = resumed["deliveries"][0]["committed_result"]
    assert authority["kind"] == "material" and authority["id"] == operation
    result = saved(context, 'Действующее правило: "один фокус".')
    item.update(
        intent="apply",
        authority_quote='Прими правило "один фокус".',
        authority_reference=authority,
        outcome="done",
        result=result["reference"],
    )
    review(context, request, [item])
    assert (
        run(context, "web.read", record=request["record"]["id"])["review"]["items"][0][
            "authority_reference"
        ]
        == authority
    )


def test_changed_source_after_review_requires_new_reconciliation(context: Context) -> None:
    basis = saved(context, "Basis v1")
    packet = run(
        context, "web.prepare", payload={"question": "Discuss", "references": [basis["reference"]]}
    )
    request = capture(context, "Сохрани предложение.")
    result = saved(context, "Proposal retained only")
    item = {
        "key": "proposal",
        "source_quote": "Сохрани предложение.",
        "intent": "store",
        "description": "Store only",
        "outcome": "done",
        "result": result["reference"],
    }
    review(context, request, [item], context=packet["reference"])
    run(
        context,
        "record.revise",
        record=basis["record"]["id"],
        expected_revision=1,
        payload={"text": "Basis v2"},
        reason="Concurrent correction",
    )
    fresh = run(context, "web.read", record=request["record"]["id"])
    with pytest.raises(JournalError, match="changed_context"):
        run(
            context,
            "web.complete",
            record=fresh["record"]["id"],
            expected_revision=fresh["record"]["revision"],
            payload={"process_revision": fresh["process_revision"]},
        )
    with pytest.raises(JournalError, match="changed_context"):
        review(context, request, [item])
    review(
        context,
        request,
        [item],
        context=packet["reference"],
        context_note="New basis reviewed; stored proposal still unaccepted",
    )
    fresh = run(context, "web.read", record=request["record"]["id"])
    assert (
        run(
            context,
            "web.complete",
            record=fresh["record"]["id"],
            expected_revision=fresh["record"]["revision"],
            payload={"process_revision": fresh["process_revision"]},
        )["record"]["revision"]
        == 4
    )


def test_committed_projection_failure_retains_recovery_warning(
    context: Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zaratustra.core import mutations

    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("fictional projection failure")

    with monkeypatch.context() as patch:
        patch.setattr(mutations, "write_projection", fail)
        result = capture(context, "Сохрани источник после сбоя проекции.")
    assert result["committed"] and "projection_warning" in result and "receipt" in result
    assert capture(context, "Сохрани источник после сбоя проекции.")["replayed"]


def test_explicit_shared_selection_and_review_exact_retry(context: Context) -> None:
    shared = saved(
        context, "Shared selected source", scope="home", authority_source="Make this source shared"
    )
    packet = run(
        context,
        "web.prepare",
        payload={"question": "Discuss shared source", "references": [shared["reference"]]},
    )
    assert (
        "Shared selected source"
        in run(context, "record.read", record=packet["record"]["id"])["payload_json"]
    )
    with pytest.raises(JournalError, match="scope_unavailable"):
        run(
            context,
            "web.prepare",
            include_shared=False,
            payload={"question": "No shared scope", "references": [shared["reference"]]},
        )
    request = capture(context, "Сохрани источник.")
    operation = uuid4()
    fields = {
        "record": request["record"]["id"],
        "expected_revision": 1,
        "operation_id": operation,
        "reason": "Record full review",
        "payload": {
            "reviewed_full_request": True,
            "items": [
                {
                    "key": "source",
                    "source_quote": "Сохрани источник.",
                    "intent": "store",
                    "description": "Preserve source",
                }
            ],
        },
    }
    first = run(context, "web.review", **fields)
    assert run(context, "web.review", **fields)["reference"] == first["reference"]
    review(context, request, fields["payload"]["items"], context=packet["reference"])
    assert run(context, "web.review", **fields)["reference"] == first["reference"]
