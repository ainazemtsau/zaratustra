"""An observational read must not interrupt native background work."""

import time
from types import SimpleNamespace
from typing import Any, cast

import pytest

from tools import probe_knowledge_pi as probe
from zaratustra.foundation import FoundationError
from zaratustra.pi_adapter import Bridge


def _bridge(thread: Any = None) -> Bridge:
    return cast(
        Bridge,
        SimpleNamespace(
            workflow_controller=SimpleNamespace(thread=thread),
            setup_controller=None,
            procedure_controller=None,
        ),
    )


def test_completed_observation_leaves_a_live_coordinator_running() -> None:
    thread = SimpleNamespace(is_alive=lambda: True)
    bridge = _bridge(thread)
    reads = []

    def read() -> bool:
        reads.append(True)
        raise FoundationError("storage", "SQLITE_BUSY at a live observation")

    assert not probe._completed_observation(bridge, read)
    assert reads == [] and bridge.workflow_controller.thread is thread


def test_completed_observation_retries_only_an_idle_public_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge()
    reads = []
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    def read() -> bool:
        reads.append(True)
        if len(reads) == 1:
            raise FoundationError("storage", "SQLite identity failed (SQLITE_BUSY)")
        return True

    assert probe._completed_observation(bridge, read)
    assert len(reads) == 2 and len(sleeps) == 1
    assert bridge.workflow_controller.thread is None


@pytest.mark.parametrize(
    ("code", "detail", "expected_reads"),
    [
        ("storage", "SQLite identity failed (SQLITE_BUSY)", 3),
        ("permission_denied", "Read permission revoked", 1),
        ("storage", "Stored content checksum does not match", 1),
    ],
)
def test_completed_observation_does_not_hide_a_terminal_failure(
    monkeypatch: pytest.MonkeyPatch, code: str, detail: str, expected_reads: int
) -> None:
    bridge = _bridge()
    reads = []
    error = FoundationError(code, detail)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    def read() -> bool:
        reads.append(True)
        raise error

    with pytest.raises(FoundationError) as refusal:
        probe._completed_observation(bridge, read)
    assert refusal.value is error and len(reads) == expected_reads
    assert bridge.workflow_controller.thread is None


def test_dynamic_selected_work_waits_for_durable_attempt_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge()
    runtime = cast(Any, bridge)
    runtime.sessions = {"native": SimpleNamespace(work_id="selected-after-start")}
    runtime.path = "fictional"
    runtime.authority = "owner"
    observed = []
    active = True

    def execution(*args: Any) -> Any:
        observed.append(args)
        return SimpleNamespace(
            assignments=[],
            attempts=[
                SimpleNamespace(status="active" if active else "completed", attempt_id="commentary")
            ],
        )

    monkeypatch.setattr(probe, "read_execution", execution)
    assert not probe._completed_observation(bridge, lambda: True)
    active = False
    assert probe._completed_observation(bridge, lambda: True)
    assert len(observed) == 2
