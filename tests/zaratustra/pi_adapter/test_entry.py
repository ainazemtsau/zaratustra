"""Ordinary Pi entry upgrades only explicitly and preserves legacy execution."""

from pathlib import Path

import pytest

import zaratustra.foundation as core
from tests.zaratustra.foundation.test_conversations import _ordinary_final_case
from zaratustra.pi_adapter import Bridge
from zaratustra.pi_adapter.__main__ import _prepare_space
from zaratustra.pi_adapter.conversation import conversation


def test_new_ordinary_space_has_delivery_correlation_schema(tmp_path: Path) -> None:
    root = tmp_path / "space"
    root.mkdir()
    authority = _prepare_space(root, "owner", create=True)
    info = core.read_space(root)
    assert info.schema_version == 18 and authority.space_id == info.space_id
    assert core.inspect_space(root, authority).records


def test_existing_schema17_requires_explicit_upgrade_before_ordinary_pi(tmp_path: Path) -> None:
    case, work, _, _ = _ordinary_final_case(tmp_path, "tool")
    root, authority = case[0], case[2]
    before = core.read_space(root)
    execution = core.read_execution(root, work, authority)
    assert before.schema_version == 17
    with pytest.raises(core.FoundationError) as refused:
        _prepare_space(root, "owner", create=False)
    assert refused.value.code == "upgrade_required"
    assert core.read_space(root) == before
    assert core.read_execution(root, work, authority) == execution


def test_explicit_entry_upgrade_preserves_old_work_and_invocation_outcomes(tmp_path: Path) -> None:
    case, work, _, _ = _ordinary_final_case(tmp_path, "valid")
    root, authority = case[0], case[2]
    old_work = core.read_work(root, work, authority)
    old_execution = core.read_execution(root, work, authority)
    upgraded = _prepare_space(root, "owner", create=False, upgrade_existing=True)
    assert core.read_space(root).schema_version == 18
    assert core.read_work(root, work, upgraded) == old_work
    assert core.read_execution(root, work, upgraded) == old_execution
    assert _prepare_space(root, "owner", create=False).space_id == upgraded.space_id


def test_legacy_cleanup_reports_upgrade_without_changing_attempt_or_sends(tmp_path: Path) -> None:
    case, work, attempt, session = _ordinary_final_case(tmp_path, "tool")
    bridge = Bridge(case[0], case[2], tmp_path)
    bridge.connect(session)
    old_work = core.read_work(case[0], work, case[2])
    bridge.select(session, old_work.state.activity_id, work)
    before = core.read_execution(case[0], work, case[2])
    with pytest.raises(core.FoundationError) as refused:
        conversation(
            bridge,
            session,
            {
                "mode": "restore",
                "work_id": str(work),
                "attempt_id": str(attempt),
                "cleanup_unsent": True,
            },
        )
    assert refused.value.code == "upgrade_required" and "18" in refused.value.detail
    assert core.read_execution(case[0], work, case[2]) == before
    assert core.read_work(case[0], work, case[2]) == old_work
    assert bridge.sessions[session] is not None
