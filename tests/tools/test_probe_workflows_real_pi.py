"""Local observation regressions; no Pi process, subscription or model is opened."""

import queue
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

import zaratustra.foundation as core
from tools import probe_workflows_real_pi as probe


@pytest.mark.parametrize("configured", [None, "", "0", "-1", "not-a-limit"])
def test_conversation_refuses_missing_host_limit_before_any_core_or_pi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configured: str | None
) -> None:
    if configured is None:
        monkeypatch.delenv("ZARA_TRIAL_MAX_TOTAL_SENDS", raising=False)
    else:
        monkeypatch.setenv("ZARA_TRIAL_MAX_TOTAL_SENDS", configured)

    def unexpected(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Invalid trial configuration must not reach Core or Pi")

    monkeypatch.setattr(core, "authorize_local", unexpected)
    monkeypatch.setattr(subprocess, "Popen", unexpected)
    with pytest.raises(ValueError, match="trial send limit"):
        probe.Conversation(tmp_path, tmp_path, tmp_path, tmp_path, tmp_path, "trial", "high")


def test_trial_preserves_additional_session_and_cumulative_core_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ZARA_TRIAL_MAX_TOTAL_SENDS", "28")
    assert probe._configured_send_limits(8) == (8, 28)


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


def test_fresh_forwarded_trial_has_its_own_twenty_send_allowance() -> None:
    selected, allowance = probe._trial_options(
        "forwarded", 20, 0, resume_trial=False, exercise_first_action=True
    )
    assert selected == (probe.SCENARIOS[2],)
    assert allowance == 20
    assert probe._trial_options("all", 40, 12, resume_trial=False, exercise_first_action=False) == (
        probe.SCENARIOS,
        28,
    )


@pytest.mark.parametrize(
    ("case", "maximum", "prior", "first_action"),
    [("forwarded", 20, 12, False), ("all", 40, 0, False), ("all", 40, 12, True)],
)
def test_resume_cannot_reset_the_old_allowance_or_add_a_new_trial(
    case: str, maximum: int, prior: int, first_action: bool
) -> None:
    previous = {"prior_trial_sends": 12, "maximum_actual_sends": 40}
    with pytest.raises(ValueError):
        probe._trial_options(
            case,
            maximum,
            prior,
            resume_trial=True,
            exercise_first_action=first_action,
            previous_report=previous,
        )
    assert previous == {"prior_trial_sends": 12, "maximum_actual_sends": 40}


def test_old_resume_defaults_keep_all_cases_and_remaining_allowance() -> None:
    selected, allowance = probe._trial_options(
        "all",
        40,
        12,
        resume_trial=True,
        exercise_first_action=False,
        previous_report={"prior_trial_sends": 12, "maximum_actual_sends": 40},
    )
    assert selected == probe.SCENARIOS and allowance == 28


def test_initial_work_choice_uses_only_addressed_native_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    activity_id, work_id, other = uuid4(), uuid4(), uuid4()
    conversation = probe.Conversation.__new__(probe.Conversation)
    conversation.bridge = cast(Any, SimpleNamespace(path=tmp_path, authority=object()))
    conversation.prompts = 0
    conversation.ui_selections = {}
    conversation.evidence = tmp_path / "rpc.jsonl"
    conversation.events = queue.Queue()
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(conversation, "send", sent.append)
    monkeypatch.setattr(
        core, "read_activity", lambda *_: SimpleNamespace(state=SimpleNamespace(title="Trial"))
    )
    monkeypatch.setattr(
        core,
        "read_work",
        lambda *_: SimpleNamespace(
            state=SimpleNamespace(activity_id=activity_id, method="none", goal="First event")
        ),
    )
    conversation.events.put(
        {
            "type": "extension_ui_request",
            "id": "activity",
            "method": "select",
            "title": "Activity",
            "options": [f"Other [{other}]", f"Trial [{activity_id}]"],
        }
    )
    conversation.events.put(
        {
            "type": "extension_ui_request",
            "id": "work",
            "method": "select",
            "title": "Work",
            "options": [f"Other [{other}]", f"First event [{work_id}]"],
        }
    )
    conversation.events.put(
        {
            "type": "response",
            "id": "prompt-1",
            "success": True,
            "data": {"disposition": "handled"},
        }
    )
    conversation.select_ordinary_work(activity_id, work_id)
    assert sent == [
        {"id": "prompt-1", "type": "prompt", "message": "/zara-work"},
        {"type": "extension_ui_response", "id": "activity", "value": f"Trial [{activity_id}]"},
        {"type": "extension_ui_response", "id": "work", "value": f"First event [{work_id}]"},
    ]
    assert conversation.ui_selections == {}


def test_first_action_explanation_without_output_is_not_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(probe, "_ordinary_outputs", lambda *_: {uuid4(): ()})
    with pytest.raises(RuntimeError, match="no saved ordinary Work result"):
        probe._first_work_evidence(tmp_path, object(), object(), {})


@pytest.mark.parametrize("wrong_proof", ["assistant_prose", "other_attempt", "accepted"])
def test_first_action_rejects_unproved_or_automatically_accepted_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wrong_proof: str
) -> None:
    work_id, attempt_id = uuid4(), uuid4()
    output = core.LinkedOutput(
        slot="report", artifact=core.ArtifactRef(artifact_id=uuid4(), revision=1)
    )
    snapshot = SimpleNamespace(
        work=SimpleNamespace(
            state=SimpleNamespace(acceptance=wrong_proof if wrong_proof == "accepted" else None)
        ),
        attempts=(SimpleNamespace(work_id=work_id, status="completed", attempt_id=attempt_id),),
    )
    provenance = (
        ()
        if wrong_proof == "assistant_prose"
        else (
            core.ProvenanceRef(relation="produced_by_attempt", external_ref=f"attempt:{uuid4()}"),
        )
    )
    monkeypatch.setattr(probe, "_ordinary_outputs", lambda *_: {work_id: (output,)})
    monkeypatch.setattr(core, "read_execution", lambda *_: snapshot)
    monkeypatch.setattr(
        core,
        "read_artifact",
        lambda *_, **__: SimpleNamespace(content=b"report", provenance=provenance),
    )
    with pytest.raises(RuntimeError, match="automatically accepted|producing Attempt"):
        probe._first_work_evidence(tmp_path, object(), object(), {})


@pytest.mark.parametrize("changed_input", [False, True])
@pytest.mark.parametrize("missing_output", [False, True])
def test_first_action_requires_the_producers_actual_input_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed_input: bool, missing_output: bool
) -> None:
    work_id, attempt_id = uuid4(), uuid4()
    inputs = (core.ArtifactRef(artifact_id=uuid4(), revision=1),)
    output = core.LinkedOutput(
        slot="report", artifact=core.ArtifactRef(artifact_id=uuid4(), revision=1)
    )
    producer = core.AttemptRecord(
        attempt_id=attempt_id,
        revision=2,
        work_id=work_id,
        work_revision=1,
        resource_id=uuid4(),
        resource_revision=1,
        session_id=uuid4(),
        previous_attempt_id=None,
        execution_epoch=1,
        generation=1,
        input_refs=inputs,
        status="completed",
    )
    snapshot = SimpleNamespace(
        work=SimpleNamespace(
            revision=2,
            state=SimpleNamespace(
                acceptance=None,
                inputs=() if changed_input else inputs,
                linked_outputs=(output,),
                expected_outputs=tuple(
                    SimpleNamespace(slot=slot)
                    for slot in (("report", "second") if missing_output else ("report",))
                ),
            ),
        ),
        attempts=(producer,),
        invocations=(SimpleNamespace(attempt_id=attempt_id, status="answered"),),
    )
    artifact = SimpleNamespace(
        content=b"Actual saved output",
        content_sha256="A" * 64,
        provenance=(
            core.ProvenanceRef(
                relation="produced_by_attempt", external_ref=f"attempt:{attempt_id}"
            ),
        ),
    )
    monkeypatch.setattr(probe, "_ordinary_outputs", lambda *_: {work_id: (output,)})
    monkeypatch.setattr(core, "read_execution", lambda *_: snapshot)
    monkeypatch.setattr(core, "read_artifact", lambda *_, **__: artifact)
    monkeypatch.setattr(
        core, "read_work", lambda *_, **__: SimpleNamespace(state=SimpleNamespace(inputs=inputs))
    )
    if changed_input:
        with pytest.raises(RuntimeError, match="pinned inputs"):
            probe._first_work_evidence(tmp_path, object(), object(), {})
    elif missing_output:
        with pytest.raises(RuntimeError, match="unpublished declared output slots"):
            probe._first_work_evidence(tmp_path, object(), object(), {})
    else:
        result = probe._first_work_evidence(tmp_path, object(), object(), {})
        assert len(result) == 1 and result[0]["acceptance"] is None
        assert result[0]["work_id"] == str(work_id)
        assert result[0]["inputs"] == [inputs[0].model_dump(mode="json")]
        assert result[0]["outputs"][0]["producer_attempt"] == producer.model_dump(mode="json")


def test_setup_outputs_and_other_activity_work_are_not_first_action_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, stage, host_node, ordinary, other_activity_work = (uuid4() for _ in range(5))
    activity_id = uuid4()
    setup = SimpleNamespace(
        state=SimpleNamespace(
            stages=(SimpleNamespace(work_id=stage),), root_work_id=root, activity_id=activity_id
        )
    )
    monkeypatch.setattr(
        core,
        "read_workflow_run",
        lambda *_: SimpleNamespace(nodes=(SimpleNamespace(work_id=host_node),)),
    )
    monkeypatch.setattr(
        core,
        "inspect_space",
        lambda *_: SimpleNamespace(
            records=tuple(
                SimpleNamespace(kind="work", status="proposed", record_id=identifier)
                for identifier in (root, stage, host_node, ordinary, other_activity_work)
            )
        ),
    )
    seen = []

    def read(_path: Any, identifier: Any, _authority: Any) -> Any:
        seen.append(identifier)
        return SimpleNamespace(
            work_id=identifier,
            state=SimpleNamespace(
                activity_id=activity_id if identifier == ordinary else uuid4(), linked_outputs=()
            ),
        )

    monkeypatch.setattr(core, "read_work", read)
    assert probe._ordinary_outputs(tmp_path, object(), setup) == {ordinary: ()}
    assert seen == [ordinary, other_activity_work]
