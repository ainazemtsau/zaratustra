"""The native fixture retains an older procedure and a late related Artifact."""

from pathlib import Path
from uuid import UUID

from tools.probe_related_materials_pi import fixture
from zaratustra.foundation import (
    MemorySelector,
    MemoryViewState,
    open_memory_selection,
    prepare_memory_cache,
    read_knowledge,
    read_work,
)


def test_fixture_preserves_saved_snapshot_and_late_cross_family_input(tmp_path: Path) -> None:
    case = fixture(tmp_path / "case")
    work = read_work(case.root, case.work, case.owner)
    original = read_knowledge(case.root, case.snapshot.record_id, case.owner)
    assert isinstance(original.state, MemoryViewState) and original.state.selection is not None
    assert original.state.selection.members == ()
    reopened = open_memory_selection(case.root, case.snapshot.record_id, case.owner)
    assert reopened["current"] is False and reopened["members"] == 0
    fresh = prepare_memory_cache(
        case.root, case.owner, (MemorySelector(format_refs=(case.format_ref,)),)
    )
    saved = read_knowledge(case.root, UUID(str(fresh["selection_id"])), case.owner)
    assert isinstance(saved.state, MemoryViewState) and saved.state.selection is not None
    assert (
        case.entry in saved.state.selection.members and case.packet in saved.state.selection.members
    )
    assert read_knowledge(case.root, case.snapshot.record_id, case.owner) == original
    assert read_work(case.root, case.work, case.owner) == work
    assert read_work(case.root, case.development, case.owner).state.acceptance is None
