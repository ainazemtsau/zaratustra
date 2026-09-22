"""Shared evidence types and output-boundary checks for Stage 1 probes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = (ROOT / "_scratch").resolve()


class GateStatus(StrEnum):
    """The only permitted gate conclusions."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    INCONCLUSIVE = "inconclusive"


class CheckConclusion(StrEnum):
    """Why one check passed or failed.

    A contract violation is evidence for a negative gate.  Setup failures and
    insufficient observations leave the gate inconclusive instead of silently
    turning missing evidence into either success or product failure.
    """

    PASSED = "passed"
    CONTRACT_VIOLATION = "contract-violation"
    INSUFFICIENT_OBSERVATION = "insufficient-observation"
    SETUP_FAILURE = "setup-failure"


@dataclass(frozen=True)
class CheckResult:
    """One directly observed gate check."""

    name: str
    passed: bool
    observation: str
    evidence: dict[str, Any] = field(default_factory=dict)
    conclusion: CheckConclusion | None = None

    def __post_init__(self) -> None:
        conclusion = self.conclusion
        if conclusion is None:
            conclusion = (
                CheckConclusion.PASSED if self.passed else CheckConclusion.CONTRACT_VIOLATION
            )
            object.__setattr__(self, "conclusion", conclusion)
        if self.passed != (conclusion is CheckConclusion.PASSED):
            raise ValueError("passed must agree with conclusion")


@dataclass(frozen=True)
class GateReport:
    """Machine-readable result for one technical gate."""

    gate: str
    status: GateStatus
    checks: tuple[CheckResult, ...]
    versions: dict[str, str]
    commands: tuple[str, ...]
    untested: tuple[str, ...]
    notes: tuple[str, ...] = ()

    def write(self, path: Path) -> None:
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def new_scratch_output(path: Path) -> Path:
    """Create a new probe output below this checkout's ignored scratch directory."""

    resolved = path.resolve()
    if resolved == SCRATCH or not resolved.is_relative_to(SCRATCH):
        raise ValueError(f"output must be a child of {SCRATCH}")
    if resolved.exists():
        raise FileExistsError(f"output already exists: {resolved}")
    resolved.mkdir(parents=True)
    return resolved


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def gate_status(checks: list[CheckResult], expected_checks: frozenset[str]) -> GateStatus:
    """Classify a bounded gate without conflating defects and missing evidence."""

    if any(check.conclusion is CheckConclusion.CONTRACT_VIOLATION for check in checks):
        return GateStatus.NEGATIVE
    observed = [check.name for check in checks]
    if (
        len(observed) == len(expected_checks)
        and set(observed) == expected_checks
        and all(check.conclusion is CheckConclusion.PASSED for check in checks)
    ):
        return GateStatus.POSITIVE
    return GateStatus.INCONCLUSIVE


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    """Append one LF-framed evidence record."""

    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        stream.write("\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError(f"expected JSON object in {path}")
        records.append(value)
    return records
