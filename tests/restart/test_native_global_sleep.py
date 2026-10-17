"""Global native Sleep public-API controls; fictional content is not semantic proof."""

import base64
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from zaratustra_app import Coordinator, Sleep
from zaratustra_app.native_session import NativeSession
from zaratustra_app.native_sleep import NativeSleep
from zaratustra_core import Core, CoreError, digest

from .sleep_support import save


def seed(tmp_path: Path) -> tuple[Any, str]:
    core, token = Core.initialize(tmp_path / "core")
    owner = core.connect(token)
    for scope in ("A", "B"):
        save(owner, {"id": scope, "kind": "activity", "key": scope, "body": "Fictional " + scope})
        save(
            owner,
            {
                "id": "source-" + scope,
                "kind": "data",
                "key": "source-" + scope,
                "scope": scope,
                "body": "Actual fictional source " + scope,
            },
        )
    owner.call(
        "ingest_message",
        {
            "conversation": "unassigned",
            "event_id": "free-message",
            "raw_base64": base64.b64encode(b"Fictional unassigned conversation").decode(),
        },
        "free-message",
    )
    return core, token


def settle(session: NativeSession) -> dict[str, Any]:
    session.tool("result", "stage-" + uuid4().hex, {"outputs": []})
    return session.settled(
        "final-" + uuid4().hex, "No finding established; unknowns remain.", False
    )


def test_zero_activity_global_sleep_empty_outputs_and_successor(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "core")
    session = NativeSession(core, token, "first")
    ctx = session.start_sleep("space", portion=2)
    assert ctx["sleep"]["work"]["scope"] == "space"
    assert ctx["sleep"]["scope_contract"]["work_ownership"] == "workspace (space)"
    assert "all permitted Activities" in ctx["sleep"]["scope_contract"]["source_read_domain"]
    assert "targeted proposal" in ctx["sleep"]["instructions"]
    before = Sleep(core.connect(token)).progress(ctx["current"]["work"])["body"]["value"]
    result = settle(session)
    assert (
        result["state"] == "completed" and result["outputs"] == [] and result["accepted"] is False
    )
    co = Coordinator(core.connect(token))
    assert not [h for h in co.rows("heads") if h["kind"] == "activity"]
    assert not co.rows("acceptance")
    old = Sleep(core.connect(token)).progress(ctx["current"]["work"])
    assert old["body"]["value"]["remaining_refs"] == before["remaining_refs"]
    assert not old["body"]["value"]["analysis_result_refs"]
    successor = NativeSession(core, token, "second").start_sleep("space", portion=2)
    new = Sleep(core.connect(token)).progress(successor["current"]["work"])["body"]["value"]
    assert new["format"] == "sleep-progress/v2" and new["transition"] == "same_window"
    assert new["predecessor_ref"] == {"id": old["id"], "revision": old["revision"], "role": "exact"}
    assert new["source_high_watermark"] == before["source_high_watermark"]
    assert new["remaining_refs"] == before["remaining_refs"]


def test_global_window_pages_a_b_and_unassigned_exact_sources(tmp_path: Path) -> None:
    core, token = seed(tmp_path)
    session = NativeSession(core, token, "global")
    ctx = session.start_sleep("space", portion=2)
    progress = Sleep(core.connect(token)).progress(ctx["current"]["work"])["body"]["value"]
    after = [0, 0]
    sources = []
    while True:
        page = core.connect(token).call(
            "read_history",
            {
                "scope": "space",
                "limit": 2,
                "high_watermark": progress["source_high_watermark"],
                "after_sequence": after[0],
                "after_index": after[1],
            },
            uuid4().hex,
        )
        sources.extend(page["sources"])
        if not page["has_more"]:
            break
        assert page["cursor"] > after
        after = page["cursor"]
    assert {s["material"]["scope"] for s in sources} == {"space", "A", "B"}
    assert all(digest(s["material"]) == s["source_ref"]["sha256"] for s in sources)
    records = {
        s["material"]["record"]["id"]: s["material"]["record"]
        for s in sources
        if "record" in s["material"]
    }
    assert records["source-A"]["scope"] == "A" and records["source-B"]["scope"] == "B"
    message = next(s["material"]["message"] for s in sources if "message" in s["material"])
    assert base64.b64decode(message["raw"]).decode() == "Fictional unassigned conversation"
    assert len(ctx["sleep"]["sleep_sources"]) < len(sources)
    assert not progress["analysis_result_refs"]


def test_global_adaptation_propagates_but_local_destinations_stay_guarded(tmp_path: Path) -> None:
    core, token = seed(tmp_path)
    owner = core.connect(token)
    for change in [
        {"id": "shared", "kind": "memory", "key": "shared", "body": "Earlier global note"},
        {"id": "practice", "kind": "method", "key": "practice", "body": "Earlier global method"},
        {
            "id": "local-memory",
            "kind": "memory",
            "key": "local-memory",
            "scope": "A",
            "body": "Local A truth",
        },
        {
            "id": "local-method",
            "kind": "method",
            "key": "local-method",
            "scope": "A",
            "body": "Local A method",
        },
    ]:
        save(owner, change)
    session = NativeSession(core, token, "global")
    ctx = session.start_sleep("space", portion=100)
    for kind, identity in [("memory", "local-memory"), ("method", "local-method")]:
        change = {
            "id": identity,
            "kind": kind,
            "key": identity,
            "scope": "A",
            "body": "Proposed local correction",
        }
        with pytest.raises(CoreError, match="native.sleep_scope"):
            session.tool(
                "change", "local-" + kind, {"changes": [change], "expected_heads": {identity: 1}}
            )
        helper = NativeSleep(core, token, "space")
        with pytest.raises(CoreError, match="denied"):
            helper.client.call(
                "apply_changes",
                {"changes": [change]},
                "direct-local-" + kind,
                expected_heads={identity: 1},
            )
    changes = [
        {
            "id": "shared",
            "kind": "memory",
            "key": "shared",
            "body": "Explicit fictional shared correction",
        },
        {
            "id": "practice",
            "kind": "method",
            "key": "practice",
            "body": "Explicit fictional shared method",
        },
        {
            "id": "unrelated",
            "kind": "method",
            "key": "unrelated",
            "body": "Not selected automatically",
        },
        {
            "id": "local-proposal",
            "kind": "data",
            "key": "local-proposal",
            "body": {
                "destination_scope": "A",
                "target_ref": {"id": "local-memory", "revision": 1},
                "proposal": "Local-only correction; not active universal memory",
            },
        },
    ]
    session.tool(
        "change",
        "shared-and-proposal",
        {
            "changes": changes,
            "expected_heads": {"shared": 1, "practice": 1, "unrelated": 0, "local-proposal": 0},
        },
    )
    assert settle(session)["accepted"] is False
    co = Coordinator(owner)
    profile_ref = ctx["sleep"]["profile_ref"]
    for scope in ("A", "B"):
        co.open_work(
            {
                "id": "next-" + scope,
                "conversation": "next-" + scope,
                "goal": "Try correction",
                "method_ref": {"id": "practice", "revision": 1},
                "call_limit": None,
                "continuation_policy": "durable",
            },
            scope=scope,
        )
        prepared = co.prepare("next-" + scope, "next-attempt-" + scope, profile_ref)["pinned"]
        assert prepared["method"]["id"] == "practice" and prepared["method"]["revision"] == 2
        assert next(r for r in prepared["inputs"] if r["id"] == "shared")["revision"] == 2
        assert not any(r["id"] in {"unrelated", "local-proposal"} for r in prepared["inputs"])
    local = owner.call("read_exact", {"id": "local-memory", "revision": 1}, "local-unchanged")
    assert local["scope"] == "A" and local["body"]["value"] == "Local A truth"
    assert next(h for h in co.rows("heads") if h["id"] == "local-memory")["revision"] == 1


def test_local_completed_proof_is_not_a_global_boundary(tmp_path: Path) -> None:
    core, token = seed(tmp_path)
    local = NativeSession(core, token, "local")
    ctx = local.start_sleep("A", portion=100)
    assert settle(local)["state"] == "completed"
    sleep = Sleep(core.connect(token))
    old = sleep.progress(ctx["current"]["work"])
    global_ctx = NativeSession(core, token, "global").start_sleep("space", portion=100)
    value = sleep.progress(global_ctx["current"]["work"])["body"]["value"]
    assert value["format"] == "sleep-progress/v1" and "predecessor_ref" not in value
    first_source = core.connect(token).call(
        "read_history",
        {
            "scope": "space",
            "limit": 1,
            "high_watermark": value["source_high_watermark"],
            "after_sequence": 0,
            "after_index": 0,
        },
        "first-global-source",
    )["sources"][0]["source_ref"]
    assert value["enumerated_source_refs"][0] == first_source
    assert any(
        s["material"].get("record", {}).get("id") == "source-B"
        for s in global_ctx["sleep"]["sleep_sources"]
    )
    assert sleep.progress(ctx["current"]["work"]) == old


@pytest.mark.parametrize("mode", ["ordinary", "unknown", "waiting", "review"])
def test_global_request_preserves_active_native_guards(tmp_path: Path, mode: str) -> None:
    core, token = seed(tmp_path)
    session = NativeSession(core, token, "native")
    session.input("ordinary", "Fictional task")
    if mode in {"waiting", "review"}:
        session.tool(
            "route",
            "route",
            {
                "outputs": [{"id": "A", "revision": 1}],
                "next_work": {"scope": "A", "goal": "Fictional ordinary task", "inputs": []},
            },
        )
        metadata: dict[str, Any] = {"outputs": [{"id": "A", "revision": 1}]}
        if mode == "waiting":
            metadata.update(
                {"state": "waiting", "wait": {"id": "question", "question": "Which example?"}}
            )
        session.tool("result", "stage", metadata)
        session.settled(
            "final", "Which example?" if mode == "waiting" else "Delivered fictional task.", False
        )
        if mode == "review":
            session = NativeSession(core, token, "fresh-review")
            session.start_review("A")
    elif mode == "unknown":
        session.settled("aborted", "", True)
    before = session.context()["current"]
    with pytest.raises(CoreError, match="outcome_unknown"):
        session.start_sleep("space")
    assert session.context()["current"] == before
    assert not [
        w for w in session.coordinator.rows("works") if json.loads(w["body"])["goal"] == "Sleep"
    ]
    if mode == "waiting":
        assert session.coordinator.rows("waits")[0]["status"] == "waiting"
    if mode == "review":
        with pytest.raises(CoreError, match="read_only_review"):
            session.tool("change", "forbidden", {"changes": []})


@pytest.mark.parametrize("condition", ["cancelled", "missing", "ambiguous"])
def test_global_frontier_blockers_never_restart_zero(tmp_path: Path, condition: str) -> None:
    core, token = Core.initialize(tmp_path / "core")
    helper = NativeSleep(core, token, "space")
    for work_id in ["one", "two"] if condition == "ambiguous" else ["one"]:
        mapping = helper.start(work_id, {"model": "fictional"})
        if condition == "cancelled":
            work = helper.coordinator.rows("works", work=work_id)[0]
            helper.client.call(
                "control_work",
                {
                    "work_id": work_id,
                    "revision": work["revision"],
                    "action": "cancel",
                    "reason": "Explicit fictional cancellation",
                },
                "cancel",
            )
        else:
            helper.client.call(
                "observe_attempt",
                {
                    "attempt_id": mapping["attempt"],
                    "event_id": "terminal",
                    "kind": "terminal",
                    "raw_base64": base64.b64encode(
                        json.dumps({"state": "completed", "text": "No analysis claimed"}).encode()
                    ).decode(),
                },
                uuid4().hex,
            )
            helper.coordinator.recover(mapping["attempt"])
            helper.checkpoint(work_id, mapping["attempt"])
    if condition == "missing":
        record = helper.sleep.progress("one")
        save(
            core.connect(token),
            {
                "id": record["id"],
                "kind": "data",
                "key": record["key"],
                "body": "Unavailable established progress",
            },
            record["revision"],
        )
    expected = {
        "cancelled": "no_eligible_predecessor",
        "missing": "progress_unavailable",
        "ambiguous": "ambiguous_unclaimed_sleep",
    }[condition]
    before = helper.coordinator.rows("works")
    with pytest.raises(CoreError, match=expected):
        NativeSession(core, token, "next").start_sleep("space")
    assert helper.coordinator.rows("works") == before
