"""Model-free native metadata admission and final authority boundaries."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from zaratustra_app.native_session import NativeSession
from zaratustra_core import Client, Core, CoreError, outcome_metadata_contract


@pytest.fixture
def native(tmp_path: Path) -> tuple[NativeSession, Client]:
    core, token = Core.initialize(tmp_path / "core")
    session = NativeSession(core, token, "fictional-staging")
    session.start_sleep("space", portion=1)
    return session, core.connect(token)


def rows(owner: Client, table: str) -> list[dict[str, Any]]:
    return cast(
        list[dict[str, Any]],
        owner.call("read_page", {"table": table, "limit": 100}, uuid4().hex)["rows"],
    )


def progress_change(session: NativeSession) -> dict[str, Any]:
    context = session.context()["sleep"]
    progress = next(
        record
        for record in context["inputs"]
        if isinstance(record["body"]["value"], dict)
        and record["body"]["value"].get("format") == "sleep-progress/v1"
    )
    return {
        "id": progress["id"],
        "kind": "data",
        "key": progress["key"],
        "scope": progress["scope"],
        "body": copy.deepcopy(progress["body"]["value"]),
    }


@pytest.mark.parametrize("malformation", ["record-ref", "missing-v1", "extra-v1"])
def test_structural_rejection_precedes_stage_terminal_and_domain(
    native: tuple[NativeSession, Client], malformation: str
) -> None:
    session, owner = native
    change = progress_change(session)
    candidate: dict[str, Any] = {
        "outputs": [],
        "changes": [change],
        "expected_heads": {change["id"]: 2},
    }
    if malformation == "record-ref":
        change["source_refs"] = [{"sequence": 1, "index": 0, "sha256": "a" * 64}]
        expected = "changes.0.source_refs.0.id"
    elif malformation == "missing-v1":
        del change["body"]["scope"]
        expected = "changes.0.body.scope"
    else:
        change["body"]["predecessor_ref"] = None
        expected = "changes.0.body.predecessor_ref"
    before_mapping = session._load()
    before = {
        table: rows(owner, table) for table in ["heads", "observations", "actions", "results"]
    }
    result = session.tool("result", "bad-shape", candidate)
    assert result["state"] == "rejected" and result["staged"] is False
    assert result["rejection"]["code"] == "invalid_request"
    assert result["rejection"]["field"] == expected
    assert result["previous_metadata_cleared"] is False
    assert session._load() == before_mapping
    assert {table: rows(owner, table) for table in before} == before
    corrected: dict[str, Any] = {"outputs": []}
    assert session.tool("result", "corrected", corrected)["state"] == "staged"
    assert session._load()[1]["staged"] == corrected
    assert not rows(owner, "observations") and not rows(owner, "results")


def test_invalid_replacement_clears_stage_and_prevents_old_final(
    native: tuple[NativeSession, Client],
) -> None:
    session, owner = native
    session.tool("result", "first-valid", {"outputs": []})
    old_revision = session._load()[0]
    result = session.tool(
        "result", "invalid-replacement", {"outputs": [{"id": "fictional", "revision": "bad"}]}
    )
    assert result["state"] == "rejected" and result["previous_metadata_cleared"] is True
    assert result["rejection"]["field"] == "outputs.0.revision"
    revision, mapping = session._load()
    assert revision == old_revision + 1 and mapping["staged"] == {}
    retained = owner.call(
        "read_exact", {"id": session.mapping_id, "revision": old_revision}, "retained-old-stage"
    )
    assert retained["body"]["value"]["staged"] == {"outputs": []}
    assert (
        session.settled("unstaged-final", "Old metadata must not complete", False)["state"]
        == "incomplete"
    )
    assert not rows(owner, "results")
    assert not any(
        json.loads(row["body"])["kind"] == "terminal" for row in rows(owner, "observations")
    )


def test_clear_cas_failure_is_not_a_recoverable_shape_ack(
    native: tuple[NativeSession, Client], monkeypatch: pytest.MonkeyPatch
) -> None:
    session, owner = native
    session.tool("result", "valid", {"outputs": []})
    before = session._load()

    def fail_save(revision: int, value: dict[str, Any]) -> None:
        raise CoreError("stale_basis", "fictional.mapping_cas")

    monkeypatch.setattr(session, "_save", fail_save)
    with pytest.raises(CoreError, match="fictional.mapping_cas"):
        session.tool("result", "bad", {"outputs": [{"id": "x"}]})
    assert session._load() == before
    assert not rows(owner, "observations") and not rows(owner, "results")


def test_valid_pending_delivery_progress_stages_without_preview(
    native: tuple[NativeSession, Client], tmp_path: Path
) -> None:
    session, owner = native
    change = progress_change(session)
    assert change["body"]["delivered_manifest_refs"] == []
    metadata = {"outputs": [], "changes": [change], "expected_heads": {change["id"]: 2}}
    assert session.tool("result", "pending-delivery", metadata)["state"] == "staged"
    assert session._load()[1]["staged"] == metadata
    assert not rows(owner, "observations") and not rows(owner, "results")
    context = session.context()
    contract = context["outcome_metadata_contract"]
    assert contract == outcome_metadata_contract()
    assert "sleep-progress/v1" in contract["progress_schemas"]
    assert "sleep-progress/v2" in contract["progress_schemas"]
    without = {key: value for key, value in context.items() if key != "outcome_metadata_contract"}
    sizes = {
        "contract_bytes": len(
            json.dumps(contract, ensure_ascii=False, separators=(",", ":")).encode()
        ),
        "context_bytes": len(
            json.dumps(context, ensure_ascii=False, separators=(",", ":")).encode()
        ),
        "context_without_contract_bytes": len(
            json.dumps(without, ensure_ascii=False, separators=(",", ":")).encode()
        ),
    }
    (tmp_path / "contract-size.json").write_text(json.dumps(sizes), encoding="utf-8")


def test_staging_does_not_weaken_final_atomic_memory_method_cas(
    native: tuple[NativeSession, Client],
) -> None:
    session, owner = native
    changes = [
        {"id": "memory", "kind": "memory", "key": "memory", "body": "candidate memory"},
        {"id": "method", "kind": "method", "key": "method", "body": "candidate Method"},
    ]
    metadata = {"outputs": [], "changes": changes, "expected_heads": {"memory": 0, "method": 0}}
    assert session.tool("result", "valid-shape", metadata)["state"] == "staged"
    owner.call(
        "apply_changes",
        {"changes": [changes[1] | {"body": "concurrent Method"}]},
        "concurrent-method",
        expected_heads={"method": 0},
    )
    with pytest.raises(CoreError, match="stale_basis"):
        session.settled("actual-final", "Fictional actual final", False)
    assert not rows(owner, "results")
    heads = rows(owner, "heads")
    assert not any(head["id"] == "memory" for head in heads)
    assert next(head for head in heads if head["id"] == "method")["revision"] == 1


def test_denied_scope_remains_fail_closed(native: tuple[NativeSession, Client]) -> None:
    session, owner = native
    before = session._load()
    with pytest.raises(CoreError, match="denied"):
        session.tool(
            "result",
            "denied",
            {
                "outputs": [],
                "changes": [
                    {
                        "id": "foreign",
                        "kind": "memory",
                        "key": "foreign",
                        "scope": "another",
                        "body": "No authority",
                    }
                ],
            },
        )
    assert session._load() == before
    assert not rows(owner, "observations") and not rows(owner, "results")


@pytest.mark.parametrize(
    ("candidate", "path"),
    [
        ({"outputs": [], "changes": [None]}, "changes.0"),
        ({"outputs": [], "changes": "bad"}, "changes"),
        ({"outputs": [], "text": "not metadata"}, "native.result_metadata"),
        ({"outputs": [], "state": "not-a-state"}, "native.result_state"),
        ({"outputs": [], "state": {}}, "state"),
        ({"outputs": [], "state": []}, "state"),
    ],
)
def test_full_envelope_replacement_clears_old_stage(
    native: tuple[NativeSession, Client], candidate: dict[str, Any], path: str
) -> None:
    session, owner = native
    session.tool("result", "previous-valid", {"outputs": []})
    before = session._load()
    actions = rows(owner, "actions")
    result = session.tool("result", "invalid-envelope", candidate)
    assert result["state"] == "rejected"
    assert result["rejection"]["code"] == "invalid_request"
    assert result["rejection"]["field"] == path
    assert result["previous_metadata_cleared"] is True
    assert session._load()[0] == before[0] + 1
    assert session._load()[1]["staged"] == {}
    assert rows(owner, "actions") == actions
    assert not rows(owner, "observations") and not rows(owner, "results")
    assert session.tool("result", "corrected-envelope", {"outputs": []})["state"] == "staged"


def test_sdk_preexecution_rejection_retained_then_clears_stage(
    native: tuple[NativeSession, Client],
) -> None:
    session, owner = native
    session.tool("result", "old-valid", {"outputs": []})
    event = {
        "kind": "tool_execution_end",
        "sdk_preexecution_rejected": True,
        "event": {
            "toolName": "zara_result",
            "isError": True,
            "toolCallId": "sdk-invalid",
            "result": {"content": [{"type": "text", "text": "Exact SDK validation error"}]},
        },
    }
    ack = session.observation("sdk-invalid", event)
    assert ack["previous_metadata_cleared"] is True and ack["staged"] is False
    assert session._load()[1]["staged"] == {}
    observation = json.loads(rows(owner, "observations")[0]["body"])
    import base64

    assert json.loads(base64.b64decode(observation["raw_base64"])) == event
    assert (
        session.settled("after-sdk-rejection", "No prior metadata completion", False)["state"]
        == "incomplete"
    )
    assert not rows(owner, "results")


@pytest.mark.parametrize(
    "change",
    [
        {"sdk_preexecution_rejected": 1},
        {"sdk_preexecution_rejected": "true"},
        {"kind": "tool_call"},
        {"event": None},
        {"event": {"toolName": "zara_read", "isError": True}},
        {"event": {"toolName": "zara_result", "isError": False}},
        {"event": {"toolName": "zara_result", "isError": 1}},
    ],
)
def test_sdk_flag_requires_exact_trusted_shape(
    native: tuple[NativeSession, Client], change: dict[str, Any]
) -> None:
    session, owner = native
    session.tool("result", "valid", {"outputs": []})
    before = session._load()
    event = {
        "kind": "tool_execution_end",
        "sdk_preexecution_rejected": True,
        "event": {"toolName": "zara_result", "isError": True},
    } | change
    ack = session.observation("not-a-sdk-rejection", event)
    assert "previous_metadata_cleared" not in ack
    assert session._load() == before
    assert len(rows(owner, "observations")) == 1 and not rows(owner, "results")


def test_sdk_clear_cas_failure_retains_error_and_propagates(
    native: tuple[NativeSession, Client], monkeypatch: pytest.MonkeyPatch
) -> None:
    session, owner = native
    session.tool("result", "valid", {"outputs": []})

    def fail_save(revision: int, value: dict[str, Any]) -> None:
        raise CoreError("stale_basis", "sdk.mapping_cas")

    monkeypatch.setattr(session, "_save", fail_save)
    with pytest.raises(CoreError, match="sdk.mapping_cas"):
        session.observation(
            "sdk-bad",
            {
                "kind": "tool_execution_end",
                "sdk_preexecution_rejected": True,
                "event": {"toolName": "zara_result", "isError": True},
            },
        )
    assert session._load()[1]["staged"] == {"outputs": []}
    assert len(rows(owner, "observations")) == 1 and not rows(owner, "results")


def test_late_sdk_event_keeps_session_fence(native: tuple[NativeSession, Client]) -> None:
    session, owner = native
    session.tool("result", "valid", {"outputs": []})
    before = session._load()
    session.session_id = "obsolete-other-Pi"
    with pytest.raises(CoreError, match="native.session"):
        session.observation(
            "late-sdk-error",
            {
                "kind": "tool_execution_end",
                "sdk_preexecution_rejected": True,
                "event": {"toolName": "zara_result", "isError": True},
            },
        )
    assert session._load() == before
    assert not rows(owner, "observations") and not rows(owner, "results")
