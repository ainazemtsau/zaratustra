"""The same installed command semantics used by all agent surfaces."""

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from zaratustra import commands, home
from zaratustra.commands import Command, Context, execute, read_context, write_context
from zaratustra.commands.connect import connect_agent
from zaratustra.core import (
    InitialRecords,
    Work,
    create_initial_records,
    init_workspace,
    migrate_workspace,
    read_records,
)
from zaratustra.entry import EntryError, add_entry
from zaratustra.home import HomeError, init_home, read_home


def run(context: Context, action: str, **fields: object) -> dict[str, Any]:
    return execute(
        context,
        Command.model_validate({"action": action, **fields}),
        source_ref="fictional owner instruction",
    )


def context_at(root: Path) -> Context:
    root.mkdir()
    init_home(root)
    context = Context(home=root.as_posix())
    write_context(root, context)
    return context


def test_complete_two_process_path_and_fresh_context(tmp_path: Path) -> None:
    root = tmp_path / "home"
    context = context_at(root)
    first_id, second_id = uuid4(), uuid4()
    first = run(
        context,
        "process.create",
        title="Учебные заметки",
        purpose="Собирать",
        operation_id=str(first_id),
    )
    run(
        context,
        "process.create",
        title="Практические пробы",
        purpose="Проверять",
        operation_id=str(second_id),
    )
    assert (
        run(
            context,
            "process.create",
            title="Учебные заметки",
            purpose="Собирать",
            operation_id=str(first_id),
        )
        == first
    )
    for name in ("Учёба", "Личное"):
        run(context, "group.create", group=name)
        run(context, "group.membership", group=name, process="Учебные заметки")
    run(context, "group.membership", group="Учёба", process="Практические пробы")
    relation = run(
        context,
        "relation.set",
        process="Учебные заметки",
        target="Практические пробы",
        relation_type="related_to",
    )
    saved = run(
        context,
        "material.save",
        process="Учебные заметки",
        title="Исходник",
        text="Проверяемый текст",
    )
    fresh = read_context(root)
    members = run(fresh, "process.list", group="Учёба")["processes"]
    assert isinstance(members, list) and len(members) == 2
    assert len(run(fresh, "process.list", group="Личное")["processes"]) == 1
    assert (
        run(fresh, "material.read", process="Учебные заметки", material=saved["material_id"])[
            "text"
        ]
        == "Проверяемый текст"
    )
    snapshot = read_records(root / "processes" / str(first_id))
    assert not any(isinstance(row, Work) for row in snapshot.records)
    run(context, "group.membership", group="Учёба", process="Практические пробы", included=False)
    assert len(run(context, "process.list", group="Учёба")["processes"]) == 1
    changed = run(
        context,
        "relation.set",
        process="Практические пробы",
        target="Учебные заметки",
        relation_type="informs",
        relation_id=relation["id"],
    )
    assert changed["type"] == "informs" and changed["id"] == relation["id"]
    run(context, "relation.delete", relation_id=relation["id"])
    assert run(context, "relation.list")["relations"] == []


def test_ambiguity_unavailable_relocation_and_direct_entry(tmp_path: Path) -> None:
    context = context_at(tmp_path / "home")
    ids = (uuid4(), uuid4())
    for identity in ids:
        run(context, "process.create", title="Notes", purpose="Collect", operation_id=str(identity))
    with pytest.raises(HomeError, match="ambiguous_name"):
        run(context, "process.open", process="Notes")
    row = run(context, "process.list", limit=1)["processes"][0]
    original = Path(row["location"])
    moved = tmp_path / "moved"
    assert original.resolve().is_relative_to(tmp_path.resolve())
    assert moved.resolve().is_relative_to(tmp_path.resolve())
    original.rename(moved)
    listing = run(context, "process.list")["processes"]
    assert any(
        item["availability"] == "unavailable" and item["current"] is None for item in listing
    )
    run(context, "process.relocate", process=row["id"], path=str(moved))
    assert run(context, "process.open", process=row["id"])["process"]["id"] == row["id"]
    direct = Context(home=context.home, workspace=moved.as_posix(), process_id=UUID(row["id"]))
    write_context(moved, direct)
    assert run(read_context(moved), "process.open")["process"]["id"] == row["id"]
    other = next(item for item in listing if item["id"] != row["id"])
    with pytest.raises(HomeError, match="identity_mismatch"):
        run(context, "process.relocate", process=other["id"], path=str(moved))


def test_home_read_does_not_mutate_and_command_conflicts_roll_back(tmp_path: Path) -> None:
    root = tmp_path / "home"
    context = context_at(root)
    database = root / ".zara-home" / "registry.sqlite3"
    identity = uuid4()
    run(context, "group.create", group="First", operation_id=str(identity))
    before = database.read_bytes()
    run(context, "home.read")
    run(context, "process.list")
    run(context, "group.list")
    assert database.read_bytes() == before
    with pytest.raises(HomeError, match="operation_conflict"):
        run(context, "group.create", group="Second", operation_id=str(identity))
    assert database.read_bytes() == before
    with pytest.raises(HomeError, match="process_not_found"):
        run(context, "group.membership", group="First", process="Missing")
    assert database.read_bytes() == before


def test_import_freezes_legacy_writer_and_upgrade_preserves_records(tmp_path: Path) -> None:
    root = tmp_path / "home"
    context = context_at(root)
    old = tmp_path / "old"
    old.mkdir()
    init_workspace(old)
    migrate_workspace(old, target_version=9)
    snapshot = create_initial_records(
        old,
        InitialRecords(
            process_title="Legacy",
            goal="Goal",
            expected_result="Result",
            acceptance=("Check",),
            boundaries=("Local",),
            budget="One work",
            artifact_title="Artifact",
        ),
    )
    work = next(row for row in snapshot.records if isinstance(row, Work))
    catalog = tmp_path / "catalog.json"
    add_entry(catalog, "Legacy", old, work.id, aliases=("Old",))
    add_entry(catalog, "Other name", old, work.id, aliases=("Another alias",))
    catalog_before = catalog.read_bytes()
    rejected_catalog = tmp_path / "rejected-catalog.json"
    rejected_catalog.write_bytes(catalog_before)
    database = old / ".zara" / "state.sqlite3"
    data_before = database.read_bytes()
    operation = uuid4()
    first = run(context, "catalog.import", path=str(catalog), operation_id=str(operation))
    with pytest.raises(HomeError, match="operation_conflict"):
        run(context, "catalog.import", path=str(rejected_catalog), operation_id=operation)
    assert not rejected_catalog.with_name(rejected_catalog.name + ".home.json").exists()
    assert run(context, "catalog.import", path=str(catalog), operation_id=str(operation)) == first
    assert catalog.read_bytes() == catalog_before and database.read_bytes() == data_before
    assert run(context, "process.open", process="Old")["process"]["title"] == "Legacy"
    assert run(context, "process.open", process="Other name")["process"]["title"] == "Legacy"
    assert run(context, "process.open", process="Another alias")["process"]["title"] == "Legacy"
    with pytest.raises(EntryError) as stopped:
        add_entry(catalog, "Another", old, work.id)
    assert stopped.value.code == "catalog_migrated"
    upgraded = run(context, "workspace.upgrade", path=str(old))
    assert read_records(old) == snapshot
    restored = tmp_path / "restored"
    shutil.copytree(old, restored)
    shutil.copyfile(Path(upgraded["backup"]), restored / ".zara" / "state.sqlite3")
    assert read_records(restored) == snapshot
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 10
    assert read_home(root)["id"]


def test_existing_context_and_unrelated_files_are_preserved(tmp_path: Path) -> None:
    context = context_at(tmp_path / "home")
    note = tmp_path / "home" / "notes.txt"
    note.write_text("Owner file", encoding="utf-8")
    initial = (tmp_path / "home" / ".zara-context.json").read_bytes()
    init_home(Path(context.home))
    write_context(Path(context.home), context)
    assert note.read_text(encoding="utf-8") == "Owner file"
    assert (tmp_path / "home" / ".zara-context.json").read_bytes() == initial
    with pytest.raises(HomeError, match="context_conflict"):
        write_context(Path(context.home), context.model_copy(update={"home": tmp_path.as_posix()}))
    assert json.loads(initial)["home"] == context.home


def test_registration_failure_preserves_process_and_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = context_at(tmp_path / "home")
    operation = uuid4()

    def unavailable(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise HomeError("home_unavailable", "Injected temporary registry failure")

    with monkeypatch.context() as patch:
        patch.setattr(home, "register_process", unavailable)
        failed = run(
            context, "process.create", title="Retained", purpose="Collect", operation_id=operation
        )
    assert failed["status"] == "registration_required"
    snapshot = read_records(Path(failed["workspace"]))
    assert not any(isinstance(row, Work) for row in snapshot.records)
    registered = run(context, "process.register", path=failed["workspace"])["process"]
    assert registered["id"] == failed["process_id"]
    assert len(run(context, "process.list")["processes"]) == 1


def test_changed_creation_path_refuses_before_second_workspace(tmp_path: Path) -> None:
    context = context_at(tmp_path / "home")
    operation = uuid4()
    run(context, "process.create", title="Notes", purpose="Collect", operation_id=operation)
    changed_path = tmp_path / "unwanted-second-process"
    with pytest.raises(HomeError, match="operation_conflict"):
        run(
            context,
            "process.create",
            title="Notes",
            purpose="Collect",
            operation_id=operation,
            path=str(changed_path),
        )
    assert not changed_path.exists()
    assert len(run(context, "process.list")["processes"]) == 1


def test_material_repeat_pagination_and_binary_file(tmp_path: Path) -> None:
    context = context_at(tmp_path / "home")
    run(context, "process.create", title="Notes", purpose="Collect")
    operation = uuid4()
    command = Command(
        action="material.save", process="Notes", title="Text", text="АБВГ", operation_id=operation
    )
    first = execute(context, command, source_ref="first actual instruction")
    assert execute(context, command, source_ref="retry actual instruction") == first
    assert run(context, "process.open", process="Notes")["material_count"] == 1
    page = run(context, "material.read", process="Notes", material="Text", content_limit=2)
    assert page["text"] == "АБ" and page["next_offset"] == 2
    assert (
        run(context, "material.read", process="Notes", material="Text", content_offset=2)["text"]
        == "ВГ"
    )
    document = tmp_path / "document.bin"
    document.write_bytes(bytes([255, 254, 1, 2]))
    run(context, "material.save", process="Notes", title="Document", path=str(document))
    assert run(context, "material.read", process="Notes", material="Document")["base64"] == (
        "//4BAg=="
    )
    with pytest.raises(Exception, match="collision"):
        execute(context, command.model_copy(update={"text": "Different"}), source_ref="changed")


def test_connection_update_preserves_settings_and_owner_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "home"
    context_at(root)
    settings = root / ".pi" / "settings.json"
    settings.parent.mkdir()
    settings.write_text('{"theme":"owner"}', encoding="utf-8")
    first = connect_agent(root, root, agent="pi")
    target = Path(first["connection"])
    before = target.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(commands.connect, "INSTRUCTIONS", "Changed shipped instructions")
        with pytest.raises(HomeError, match="connection_conflict"):
            connect_agent(root, root, agent="pi")
        connect_agent(root, root, agent="pi", update=True)
    assert target.read_bytes() != before
    assert settings.read_text(encoding="utf-8") == '{"theme":"owner"}'
    target.write_text("// Owner custom connection", encoding="utf-8")
    with pytest.raises(HomeError, match="connection_conflict"):
        connect_agent(root, root, agent="pi", update=True)
    assert target.read_text(encoding="utf-8") == "// Owner custom connection"
    assert connect_agent(root, root, agent="codex")["agent"] == "codex"


def test_import_retains_unavailable_registration(tmp_path: Path) -> None:
    context = context_at(tmp_path / "home")
    old = tmp_path / "old"
    old.mkdir()
    init_workspace(old)
    migrate_workspace(old, target_version=9)
    snapshot = create_initial_records(
        old,
        InitialRecords(
            process_title="Legacy",
            goal="Goal",
            expected_result="Result",
            acceptance=("Check",),
            boundaries=("Local",),
            budget="One",
            artifact_title="Artifact",
        ),
    )
    work = next(row for row in snapshot.records if isinstance(row, Work))
    catalog = tmp_path / "catalog.json"
    add_entry(catalog, "Missing", old, work.id)
    moved = tmp_path / "moved"
    assert old.resolve().is_relative_to(tmp_path.resolve())
    assert moved.resolve().is_relative_to(tmp_path.resolve())
    old.rename(moved)
    run(context, "catalog.import", path=str(catalog))
    listing = run(context, "process.list")["processes"]
    assert len(listing) == 1
    assert listing[0]["availability"] == "unavailable"
    assert listing[0]["cache"]["revision"] is None
    run(context, "process.relocate", process="Missing", path=str(moved))
    assert run(context, "process.open", process="Missing")["process"]["title"] == "Legacy"
    run(context, "catalog.import", path=str(catalog))
    assert run(context, "process.open", process="Missing")["location"] == moved.as_posix()
