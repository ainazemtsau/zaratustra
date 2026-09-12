"""Explicit catalog discovery, ambiguity, isolation and relocation behavior."""

from multiprocessing import get_context
from pathlib import Path
from queue import Empty
from time import monotonic, sleep
from typing import Any
from uuid import UUID, uuid4

import pytest

import zaratustra.entry as entry_module
from zaratustra.core import (
    InitialRecords,
    LocalAuthorization,
    MutationError,
    MutationRequest,
    Work,
    apply_mutation,
    authorize_local,
    create_initial_records,
    init_workspace,
    migrate_workspace,
    prepare_authorization,
    read_basic_process,
)
from zaratustra.entry import (
    EntryError,
    add_entry,
    find_entries,
    prepare_entry_read,
    relocate_entry,
    resolve_entry,
)


def confirm(path: Path, request: MutationRequest) -> LocalAuthorization:
    return authorize_local(
        prepare_authorization(path, request),
        channel="local-chat",
        actor="generic-entry-test",
        source_ref="explicit disposable test workspace",
    )


def bootstrap(path: Path, title: str) -> UUID:
    path.mkdir()
    init_workspace(path)
    migrate_workspace(path, target_version=7)
    snapshot = create_initial_records(
        path,
        InitialRecords(
            process_title=title,
            goal="Read one explicitly selected Work",
            expected_result="A bounded metadata response",
            acceptance=("Only the selected generic workspace",),
            boundaries=("No external content",),
            budget="One local read",
            artifact_title="Generic result",
        ),
    )
    work = next(row for row in snapshot.records if isinstance(row, Work))
    request = MutationRequest(
        operation_id=uuid4(),
        workspace_id=snapshot.workspace_id,
        work_id=work.id,
        expected_revision=snapshot.state_revision,
        operation="authorize_work",
        provenance="Explicit generic test authorization",
    )
    apply_mutation(path, request, confirm(path, request))
    return work.id


def test_two_designations_ambiguous_alias_and_unavailable_neighbor(tmp_path: Path) -> None:
    first_path, second_path = tmp_path / "first", tmp_path / "second"
    first_work = bootstrap(first_path, "First generic Process")
    second_work = bootstrap(second_path, "Second generic Process")
    catalog = tmp_path / "catalog.json"
    first = add_entry(catalog, "Alpha Notes", first_path, first_work, aliases=("shared",))
    second = add_entry(catalog, "Beta Review", second_path, second_work, aliases=("shared",))

    found = find_entries(catalog)
    assert [row.entry.designation for row in found.matches] == ["Alpha Notes", "Beta Review"]
    assert [row.source_state for row in found.matches] == ["available", "available"]
    assert resolve_entry(catalog, "alpha notes") == first
    prepared = prepare_entry_read(catalog, "Alpha Notes", max_bytes=65536)
    with pytest.raises(MutationError, match="permission_denied"):
        read_basic_process(prepared.workspace, prepared.query)
    with pytest.raises(EntryError, match="choose one") as ambiguous:
        resolve_entry(catalog, "SHARED")
    assert ambiguous.value.code == "ambiguous"
    assert ambiguous.value.choices == (first.designation, second.designation)

    moved = tmp_path / "second-moved"
    second_path.rename(moved)
    isolated = find_entries(catalog)
    assert [(row.entry.id, row.source_state) for row in isolated.matches] == [
        (first.id, "available"),
        (second.id, "unavailable"),
    ]
    relocated = relocate_entry(catalog, "Beta Review", moved)
    assert relocated.id == second.id
    assert [row.source_state for row in find_entries(catalog).matches] == [
        "available",
        "available",
    ]


def test_exact_designation_precedes_alias_and_shared_choices_are_actionable(tmp_path: Path) -> None:
    first_path, second_path = tmp_path / "first", tmp_path / "second"
    first_work = bootstrap(first_path, "First exact Process")
    second_work = bootstrap(second_path, "Second exact Process")
    catalog = tmp_path / "catalog.json"
    first = add_entry(catalog, "Alpha", first_path, first_work, aliases=("shared",))
    second = add_entry(catalog, "Beta", second_path, second_work, aliases=("Alpha", "shared"))

    assert resolve_entry(catalog, "alpha") == first
    assert prepare_entry_read(catalog, "Alpha", max_bytes=65536).entry == first
    assert relocate_entry(catalog, "Alpha", first_path) == first
    with pytest.raises(EntryError, match="choose one") as ambiguous:
        resolve_entry(catalog, "shared")
    assert ambiguous.value.choices == (first.designation, second.designation)
    assert tuple(resolve_entry(catalog, choice) for choice in ambiguous.value.choices) == (
        first,
        second,
    )


def test_mismatched_source_and_failed_relocation_preserve_catalog(tmp_path: Path) -> None:
    original, foreign = tmp_path / "original", tmp_path / "foreign"
    work = bootstrap(original, "Original generic Process")
    foreign_work = bootstrap(foreign, "Foreign generic Process")
    catalog = tmp_path / "catalog.json"
    entry = add_entry(catalog, "Original", original, work)
    before = catalog.read_bytes()
    with pytest.raises(EntryError, match="identities") as mismatch:
        relocate_entry(catalog, "Original", foreign)
    assert mismatch.value.code == "source_mismatch"
    assert catalog.read_bytes() == before

    parked = tmp_path / "parked"
    original.rename(parked)
    foreign.rename(original)
    found = find_entries(catalog, "original")
    assert len(found.matches) == 1
    assert found.matches[0].entry == entry
    assert found.matches[0].source_state == "mismatched"
    assert found.matches[0].code == "source_mismatch"
    with pytest.raises(EntryError, match="identities"):
        prepare_entry_read(catalog, "Original", max_bytes=65536)
    assert foreign_work != work


def catalog_process_operation(
    operation: str,
    catalog: Path,
    designation: str,
    workspace: Path,
    work_id: UUID,
    rendezvous: Path,
    participant: str,
    results: Any,
) -> None:
    entry_adapter: Any = entry_module
    original = entry_adapter.read_workspace
    synchronized = False

    def synchronized_source(path: Path) -> Any:
        nonlocal synchronized
        if not synchronized:
            synchronized = True
            (rendezvous / f"{participant}.ready").write_text("ready\n", encoding="utf-8")
            deadline = monotonic() + 20
            while len(tuple(rendezvous.glob("*.ready"))) < 2:
                if monotonic() >= deadline:
                    raise RuntimeError("Concurrent catalog test rendezvous timed out")
                sleep(0.01)
        return original(path)

    entry_adapter.read_workspace = synchronized_source
    try:
        if operation == "add":
            value = add_entry(catalog, designation, workspace, work_id)
        else:
            value = relocate_entry(catalog, designation, workspace)
        results.put(dict(state="ok", designation=value.designation))
    except EntryError as error:
        results.put(dict(state="error", code=error.code))


def overlapping_processes(
    tmp_path: Path, operations: tuple[tuple[str, str, Path, UUID], ...]
) -> tuple[dict[str, str], ...]:
    context = get_context("spawn")
    rendezvous = tmp_path / f"rendezvous-{uuid4()}"
    rendezvous.mkdir()
    results = context.Queue()
    catalog = tmp_path / "catalog.json"
    processes = tuple(
        context.Process(
            target=catalog_process_operation,
            args=(*operation[:1], catalog, *operation[1:], rendezvous, str(index), results),
        )
        for index, operation in enumerate(operations)
    )
    for process in processes:
        process.start()
    for process in processes:
        process.join(30)
    alive = tuple(process for process in processes if process.is_alive())
    for process in alive:
        process.terminate()
        process.join()
    assert not alive
    assert [process.exitcode for process in processes] == [0, 0]
    collected = []
    try:
        for _ in processes:
            collected.append(results.get(timeout=5))
    except Empty as error:
        raise AssertionError("Concurrent catalog worker returned no result") from error
    return tuple(collected)


def test_overlapping_process_adds_preserve_both_successes(tmp_path: Path) -> None:
    first_path, second_path = tmp_path / "first", tmp_path / "second"
    first_work = bootstrap(first_path, "First concurrent Process")
    second_work = bootstrap(second_path, "Second concurrent Process")
    results = overlapping_processes(
        tmp_path,
        (
            ("add", "Alpha", first_path, first_work),
            ("add", "Beta", second_path, second_work),
        ),
    )

    assert {row["designation"] for row in results} == {"Alpha", "Beta"}
    assert {row.entry.designation for row in find_entries(tmp_path / "catalog.json").matches} == {
        "Alpha",
        "Beta",
    }


def test_overlapping_same_designation_has_one_explicit_failure(tmp_path: Path) -> None:
    first_path, second_path = tmp_path / "first", tmp_path / "second"
    first_work = bootstrap(first_path, "First collision Process")
    second_work = bootstrap(second_path, "Second collision Process")
    results = overlapping_processes(
        tmp_path,
        (
            ("add", "Same", first_path, first_work),
            ("add", "Same", second_path, second_work),
        ),
    )

    assert {tuple(sorted(row.items())) for row in results} == {
        (("designation", "Same"), ("state", "ok")),
        (("code", "designation_exists"), ("state", "error")),
    }
    assert [row.entry.designation for row in find_entries(tmp_path / "catalog.json").matches] == [
        "Same"
    ]


def test_relocation_preserves_concurrently_added_independent_row(tmp_path: Path) -> None:
    original, added_path = tmp_path / "original", tmp_path / "added"
    original_work = bootstrap(original, "Relocated Process")
    added_work = bootstrap(added_path, "Added Process")
    catalog = tmp_path / "catalog.json"
    add_entry(catalog, "Alpha", original, original_work)
    moved = tmp_path / "moved"
    original.rename(moved)
    results = overlapping_processes(
        tmp_path,
        (
            ("relocate", "Alpha", moved, original_work),
            ("add", "Beta", added_path, added_work),
        ),
    )

    assert {row["designation"] for row in results} == {"Alpha", "Beta"}
    found = find_entries(catalog)
    assert {row.entry.designation for row in found.matches} == {"Alpha", "Beta"}
    assert {row.source_state for row in found.matches} == {"available"}
    assert prepare_entry_read(catalog, "Alpha", max_bytes=65536).workspace == moved.resolve()


def test_source_resolution_failure_is_isolated_to_its_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_path, second_path = tmp_path / "first", tmp_path / "second"
    first_work = bootstrap(first_path, "Bad source Process")
    second_work = bootstrap(second_path, "Available source Process")
    catalog = tmp_path / "catalog.json"
    first = add_entry(catalog, "Alpha", first_path, first_work)
    add_entry(catalog, "Beta", second_path, second_work)
    original = entry_module.source_path

    def sometimes_unresolvable(path: Path, entry: Any) -> Path:
        if entry.id == first.id:
            raise RuntimeError("Synthetic path resolution failure")
        return original(path, entry)

    monkeypatch.setattr(entry_module, "source_path", sometimes_unresolvable)
    found = find_entries(catalog)

    assert [(row.entry.designation, row.source_state) for row in found.matches] == [
        ("Alpha", "unavailable"),
        ("Beta", "available"),
    ]
    with pytest.raises(EntryError, match="unavailable") as selected:
        prepare_entry_read(catalog, "Alpha", max_bytes=65536)
    assert selected.value.code == "source_unavailable"
