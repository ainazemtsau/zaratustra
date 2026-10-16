"""Reached behavioral mutations for the additional package B seams."""

from pathlib import Path

import pytest

from .test_negative_controls import API, M
from .test_negative_controls import test_seeded_defect_is_killed as run_seed

SEEDS: list[tuple[str, str, list[tuple[str, str]], str]] = [
    (
        "B-initial-refresh-requires-attempt",
        API,
        [
            (
                '            elif action == "refresh":',
                '            elif action == "refresh":'
                + chr(10)
                + '                if not db.execute("SELECT 1 FROM attempts WHERE work=?", '
                '(work["id"],)).fetchone():'
                + chr(10)
                + "                    "
                + M
                + chr(10)
                + '                    fail("stale_basis", "refresh.attempt")',
            )
        ],
        "test_continuation.py::test_initial_work_correction_without_attempt",
    ),
    (
        "B-resume-stale-basis",
        API,
        [
            (
                'for ref in body.get("inputs", []) + [body["method_ref"]]:',
                "for ref in ([] if (" + M + ' or True) else body.get("inputs", [])):',
            )
        ],
        "test_continuation.py::test_resume_current_basis_and_explicit_correction",
    ),
    (
        "B-resume-exhausted-resource",
        API,
        [
            (
                'if state == "ready" and work["reserved"] >= body["call_limit"]:',
                "if (" + M + " or False):",
            )
        ],
        "test_continuation.py::test_resume_preserves_exhausted_reserve",
    ),
    (
        "B-observe-intent-address",
        API,
        [
            (
                'last["attempt"] if state == "running" else work["id"],',
                "(" + M + ' or work["id"]),',
            )
        ],
        "test_continuation.py::test_unknown_proven_continuation_without_resend[running]",
    ),
    (
        "B-control-leaves-stale-dispatch",
        API,
        [
            (
                "DELETE FROM intents WHERE kind IN ('dispatch','observe') AND subject IN ",
                "DELETE FROM intents WHERE 0 AND subject IN ",
            ),
            (
                'state = "paused" if action == "pause" else "cancelled"',
                M
                + chr(10)
                + '                state = "paused" if action == "pause" else "cancelled"',
            ),
        ],
        "test_continuation.py::test_control_fences_every_supported_stage[pause-prepared]",
    ),
    (
        "B-fenced-running-resume",
        API,
        [
            (
                'if last and last["state"] == "running":',
                "if (" + M + " or False):",
            )
        ],
        "test_continuation.py::test_pause_unknown_requires_terminal_proof",
    ),
]


@pytest.mark.parametrize("seed", SEEDS, ids=[s[0] for s in SEEDS])
def test_continuation_mutation(
    tmp_path: Path, seed: tuple[str, str, list[tuple[str, str]], str]
) -> None:
    run_seed(tmp_path, seed)
    assert (tmp_path / "mutant" / API).is_file()
