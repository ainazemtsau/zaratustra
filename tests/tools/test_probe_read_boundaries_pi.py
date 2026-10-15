"""The native probe rejects false exposure and pins a genuinely older Work."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from tools.probe_read_boundaries_pi import check_exposure, fixture, last_output
from zaratustra.foundation import KnowledgeRef, describe_structure, read_work


def test_tool_observation_reads_the_actual_latest_native_output() -> None:
    body = {
        "input": [
            {"type": "message", "content": [{"text": "Not a tool response"}]},
            {"type": "function_call_output", "output": json.dumps({"members": 0})},
            {"type": "function_call_output", "output": [{"text": '{"members":1}'}]},
        ]
    }
    assert last_output(body) == {"members": 1}
    with pytest.raises(AssertionError, match="no preceding tool"):
        last_output({"input": []})


def test_probe_requires_actual_bounded_exposure_instead_of_a_whole_reference() -> None:
    ref = KnowledgeRef(record_id=uuid4(), revision=2, start=12, end=40)
    actual = ref.model_copy(update={"end": 16})
    delivered = {ref.record_id: [(12, 16)]}
    check_exposure((actual,), (ref,), delivered)
    for incorrect in (
        ref.model_copy(update={"start": None, "end": None}),
        ref.model_copy(update={"end": 17}),
        actual.model_copy(update={"revision": 3}),
    ):
        with pytest.raises(AssertionError):
            check_exposure((incorrect,), (ref,), delivered)
    with pytest.raises(AssertionError, match="did not deliver"):
        check_exposure((actual,), (ref,), {})


def test_native_fixture_retains_older_pinned_structure_and_separate_same_key_entries(
    tmp_path: Path,
) -> None:
    case = fixture(tmp_path / "case")
    pinned = describe_structure(case.root, case.activity, case.owner, work_id=case.work)
    current = describe_structure(case.root, case.activity, case.owner)
    assert pinned["structure"] == case.old_structure["structure"]
    assert current["structure"] == case.current_structure["structure"]
    assert pinned["state"]["formats"]["observation"] != current["state"]["formats"]["observation"]
    assert case.entry.record_id != case.other_entry.record_id
    assert all(ref.start is not None and ref.end is not None for ref in case.materials)
    assert read_work(case.root, case.work, case.owner).state.acceptance is None
