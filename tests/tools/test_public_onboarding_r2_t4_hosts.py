"""Native discovery evidence must identify the named project skill exactly."""

from pathlib import Path

import pytest

from tools.probe_public_onboarding_r2_t4_hosts import selected_skill


def test_discovery_rejects_name_in_unrelated_metadata(tmp_path: Path) -> None:
    events = [
        dict(id=0, result=dict(userAgent="zaratustra probe")),
        dict(id=1, result=dict(data=[dict(cwd=str(tmp_path), skills=[])])),
    ]
    with pytest.raises(StopIteration):
        selected_skill("codex", events, tmp_path)


def test_discovery_refuses_disabled_skill(tmp_path: Path) -> None:
    events = [
        dict(
            id=1,
            result=dict(
                data=[
                    dict(
                        cwd=str(tmp_path),
                        skills=[
                            dict(
                                name="zaratustra",
                                enabled=False,
                                path=str(tmp_path / ".agents/skills/zaratustra/SKILL.md"),
                            )
                        ],
                    )
                ]
            ),
        )
    ]
    with pytest.raises(AssertionError):
        selected_skill("codex", events, tmp_path)
