"""Local observation regressions; no Pi process, subscription or model is opened."""

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

import zaratustra.foundation as core
from tools import probe_workflows_real_pi as probe


def _conversation(tmp_path: Path, thread: Any) -> probe.Conversation:
    return cast(
        probe.Conversation,
        SimpleNamespace(
            coordination_timeout=2,
            bridge=SimpleNamespace(
                path=tmp_path,
                authority=object(),
                setup_controller=SimpleNamespace(thread=thread),
            ),
        ),
    )


def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    elapsed = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: elapsed[0])

    def advance(seconds: float) -> None:
        elapsed[0] += seconds

    monkeypatch.setattr(time, "sleep", advance)


def test_settle_reads_only_after_the_live_coordinator_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Risk: an unused poll read aborts coordination during an active stage write."""

    class Thread:
        polls = 0

        def is_alive(self) -> bool:
            self.polls += 1
            return self.polls <= 2

    thread = Thread()
    conversation = _conversation(tmp_path, thread)
    setup_id = uuid4()
    boundary = object()
    reads = []
    _clock(monkeypatch)

    def read(path: Path, identifier: Any, authority: Any) -> Any:
        reads.append((path, identifier, authority))
        if thread.polls <= 2:
            raise core.FoundationError("storage", "database is locked")
        return boundary

    monkeypatch.setattr(core, "read_activity_setup", read)
    assert probe.Conversation.settle_setup(conversation, setup_id) is boundary
    assert thread.polls == 3
    assert reads == [(tmp_path, setup_id, conversation.bridge.authority)]
    assert conversation.bridge.setup_controller.thread is thread


def test_settle_transient_boundary_lock_retries_only_the_public_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Risk: observing a transient lock relaunches a stage instead of reading its outcome."""
    conversation = _conversation(tmp_path, None)
    controller = conversation.bridge.setup_controller
    setup_id = uuid4()
    boundary = object()
    reads = []
    _clock(monkeypatch)

    def read(path: Path, identifier: Any, authority: Any) -> Any:
        reads.append((path, identifier, authority))
        if len(reads) == 1:
            raise core.FoundationError(
                "storage",
                "SQLite identity failed at application_id (SQLITE_BUSY): database is locked",
            )
        return boundary

    monkeypatch.setattr(core, "read_activity_setup", read)
    assert probe.Conversation.settle_setup(conversation, setup_id) is boundary
    assert reads == [(tmp_path, setup_id, conversation.bridge.authority)] * 2
    assert conversation.bridge.setup_controller is controller and controller.thread is None


@pytest.mark.parametrize(
    ("code", "detail", "expected_reads"),
    [
        (
            "storage",
            "SQLite identity failed at application_id (SQLITE_BUSY): database is locked",
            3,
        ),
        ("permission_denied", "Current read permission was revoked", 1),
    ],
)
def test_settle_terminal_read_error_is_bounded_and_preserves_the_controller(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    detail: str,
    expected_reads: int,
) -> None:
    """Risk: persistent contention or a rights error is silently hidden by unlimited polling."""
    conversation = _conversation(tmp_path, None)
    controller = conversation.bridge.setup_controller
    setup_id = uuid4()
    reads = []
    error = core.FoundationError(code, detail)
    _clock(monkeypatch)

    def read(path: Path, identifier: Any, authority: Any) -> Any:
        reads.append((path, identifier, authority))
        raise error

    monkeypatch.setattr(core, "read_activity_setup", read)
    with pytest.raises(core.FoundationError) as raised:
        probe.Conversation.settle_setup(conversation, setup_id)
    assert raised.value is error
    assert reads == [(tmp_path, setup_id, conversation.bridge.authority)] * expected_reads
    assert conversation.bridge.setup_controller is controller and controller.thread is None
