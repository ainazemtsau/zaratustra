"""Package A fixed complete vertical through two actual client paths."""

from pathlib import Path

import pytest

from .support import trace


@pytest.mark.parametrize("mode", ["driver", "pi"])
def test_fixed_trace(tmp_path: Path, mode: str) -> None:
    evidence = trace(tmp_path, mode)
    assert evidence["conversations"][0]["cursor"] == 22
    assert [r["attempt"] for r in evidence["results"]] == ["A1", "A2"]
