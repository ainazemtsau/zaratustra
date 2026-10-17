"""Real Core, synthetic native review lifecycle without external execution."""

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app.native_review import NativeReview
from zaratustra_app.native_session import NativeSession
from zaratustra_core import Core, CoreError


def delivered(tmp_path: Path) -> tuple[Any, str, str]:
    core, token = Core.initialize(tmp_path / "core")
    session = NativeSession(core, token, "builder-session")
    session.profile = {"model": "fictional", "session_id": "builder-session"}
    session.input("input", "Build a fictional useful output")
    session.tool(
        "route",
        "route",
        {
            "changes": [{"id": "subject", "kind": "activity", "key": "subject", "body": "Task"}],
            "expected_heads": {"subject": 0},
            "outputs": [{"id": "subject", "revision": 1}],
            "next_work": {"scope": "subject", "goal": "Build output", "inputs": []},
        },
    )
    attempt = session.context()["current"]["attempt"]
    session.observation("tool-result", {"tool": "read", "result": "Fictional file evidence"})
    session.tool("result", "stage", {"outputs": [{"id": "subject", "revision": 1}]})
    session.settled("builder-final", "Delivered fictional output, checks limited.", False)
    return core, token, attempt


def test_native_review_requires_fresh_session_and_readonly_grant(tmp_path: Path) -> None:
    core, token, builder = delivered(tmp_path)
    helper = NativeReview(core, token, "subject")
    with pytest.raises(CoreError, match="fresh_session_required"):
        helper.start("same-session", {"session_id": "builder-session"})
    mapping = helper.start("review", {"session_id": "review-session", "model": "fictional"})
    assert mapping["builder_attempt"] == builder and mapping["scope"] == "subject"
    context = helper.context(mapping)
    assert context["work"]["scope"] == "subject"
    assert context["profile"]["body"]["value"]["session_id"] == "review-session"
    basis = next(r for r in context["inputs"] if r["id"].startswith("native-host:review-basis:"))
    assert basis["body"]["value"]["builder_attempt"] == builder
    assert basis["body"]["value"]["observations"]
    with pytest.raises(CoreError, match="denied"):
        helper.client.call(
            "apply_changes",
            {
                "changes": [
                    {
                        "id": "no",
                        "kind": "data",
                        "key": "no",
                        "scope": "subject",
                        "body": "forbidden",
                    }
                ]
            },
            "forbidden",
            expected_heads={"no": 0},
        )
    output = {
        "state": "completed",
        "text": "Finding: evidence remains limited.",
        "outputs": [{"id": "subject", "revision": 1}],
    }
    envelope = {"assistant_text": output["text"], "outcome": output}
    helper.client.call(
        "observe_attempt",
        {
            "attempt_id": mapping["attempt"],
            "event_id": "terminal",
            "kind": "terminal",
            "raw_base64": base64.b64encode(json.dumps(envelope).encode()).decode(),
        },
        "terminal",
    )
    result = helper.coordinator.recover(
        mapping["attempt"], decoder=lambda raw: json.loads(raw)["outcome"]
    )
    assert result["state"] == "completed" and result["accepted"] is False
    state = helper.coordinator.snapshot()
    assert not state["acceptance"]
    assert next(w for w in state["works"] if w["id"] == "review")["status"] == "completed"
    with pytest.raises(CoreError, match="outcome_unknown"):
        helper.start("review", {"session_id": "third-session"})


def test_native_review_unknown_and_cross_activity_are_fenced(tmp_path: Path) -> None:
    core, token, builder = delivered(tmp_path)
    with pytest.raises(CoreError, match="no_delivered_builder"):
        NativeReview(core, token, "other").start("other-review", {"session_id": "fresh"}, builder)
    helper = NativeReview(core, token, "subject")
    mapping = helper.start("review", {"session_id": "fresh"}, builder)
    helper.client.call(
        "observe_attempt",
        {"attempt_id": mapping["attempt"], "event_id": "unknown", "kind": "unknown"},
        "unknown",
    )
    reopened = NativeReview(Core(core.root), token, "subject")
    with pytest.raises(CoreError, match="outcome_unknown"):
        reopened.start("review", {"session_id": "another"})
    assert (
        len([a for a in reopened.coordinator.snapshot()["attempts"] if a["work"] == "review"]) == 1
    )
