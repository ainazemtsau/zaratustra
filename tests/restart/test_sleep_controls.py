"""Reached, behaviorally killed negative controls for Sleep and adaptation mechanics."""

from pathlib import Path

import pytest

from .test_negative_controls import API, M
from .test_negative_controls import test_seeded_defect_is_killed as run_seed

SLEEP = "app/src/zaratustra_app/sleep.py"
SEEDS: list[tuple[str, str, list[tuple[str, str]], str]] = [
    (
        "C-R1-core-cross-scope",
        API,
        [('fail("denied", "method.scope")', M)],
        "test_sleep.py::test_core_method_application_guards[scope-open]",
    ),
    (
        "C-R2-refresh-inactive",
        API,
        [('fail("stale_basis", "inactive_method")', M)],
        "test_sleep.py::test_core_method_application_guards[proposal-refresh]",
    ),
    (
        "C-R3-exhausted-ready",
        API,
        [
            (
                'if state == "ready" and work["reserved"] >= loads(work["body"])["call_limit"]:',
                "if (" + M + " or False):",
            )
        ],
        "test_sleep.py::test_exhausted_ready_outcome_persists_paused",
    ),
    (
        "C-R3-residual-upper-stop",
        SLEEP,
        [("self._stop_resource(work_id)", M)],
        "test_sleep.py::test_next_call_beyond_remaining_is_rejected",
    ),
    (
        "C-prepared-pretends-delivery",
        API,
        [('fail("invalid_request", "progress.unobserved_delivery")', M)],
        "test_sleep.py::test_prepared_unknown_is_not_delivered[prepared]",
    ),
    (
        "C-unknown-pretends-delivery",
        API,
        [('fail("invalid_request", "progress.unobserved_delivery")', M)],
        "test_sleep.py::test_prepared_unknown_is_not_delivered[unknown]",
    ),
    (
        "C-delivered-pretends-analysis",
        API,
        [('fail("invalid_request", "progress.remainder")', M)],
        "test_sleep.py::test_progress_rejects_false_claims[remainder]",
    ),
    (
        "C-read-pretends-applied",
        API,
        [('fail("invalid_request", "progress.receipt")', M)],
        "test_sleep.py::test_progress_rejects_false_claims[receipt]",
    ),
    (
        "C-reset-reservation",
        API,
        [('if work["reserved"] + upper > body["call_limit"]:', "if (" + M + " or False):")],
        "test_sleep.py::test_next_call_beyond_remaining_is_rejected",
    ),
    (
        "C-false-consumption",
        API,
        [('fail("stale_basis", "progress.resource")', M)],
        "test_sleep.py::test_progress_rejects_false_claims[resource]",
    ),
    (
        "C-self-expand-method-scope",
        API,
        [
            (
                "f\"write:{change['kind']}:{change.get('scope', 'space')}\"",
                "(" + M + ' or "apply_changes")',
            )
        ],
        "test_sleep.py::test_delegated_scope_does_not_expand[method-other]",
    ),
    (
        "C-stale-method-delivery",
        API,
        [
            (
                '"method": method,',
                '"method": (method | {"revision": ('
                + M
                + ' or 1)}) if method["id"] == "practice" else method,',
            )
        ],
        "test_sleep.py::test_sleep_adaptation_trace[driver]",
    ),
    (
        "C-retained-regenerates",
        SLEEP,
        [
            (
                'if terminal and result is None and latest["status"] in {"claimed", "prepared"}:',
                "if (" + M + " or False):",
            )
        ],
        "test_sleep.py::test_sleep_run_recovers_retained_terminal_without_inference",
    ),
]


@pytest.mark.parametrize("seed", SEEDS, ids=[s[0] for s in SEEDS])
def test_sleep_negative(tmp_path: Path, seed: tuple[str, str, list[tuple[str, str]], str]) -> None:
    run_seed(tmp_path, seed)
    assert (tmp_path / "mutant" / seed[1]).is_file()
