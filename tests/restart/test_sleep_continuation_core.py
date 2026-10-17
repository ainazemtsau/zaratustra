"""Core CAS, successor uniqueness and attributed v2 progress negative controls."""

from __future__ import annotations

import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from zaratustra_app import Coordinator, Sleep
from zaratustra_app.native_session import NativeSession
from zaratustra_core import Core, CoreError

from .test_native_sleep_successor import complete, seed


def parent(tmp_path: Path) -> tuple[Core, str, dict[str, Any], dict[str, Any]]:
    core, token = seed(tmp_path)
    session = NativeSession(core, token, "parent")
    session.start_sleep("subject", portion=2)
    mapping = complete(session)
    owner = core.connect(token)
    co = Coordinator(owner)
    work = co.rows("works", work=mapping["work"])[0]
    result = co.rows("results", work=mapping["work"])[0]
    progress = Sleep(owner).progress(mapping["work"])
    payload = {
        "id": "child",
        "conversation": work["conversation"],
        "goal": "Sleep",
        "scope": "subject",
        "method_ref": json.loads(work["body"])["method_ref"],
        "inputs": [],
        "call_limit": None,
        "continuation_policy": "durable",
        "continuation_from": {
            "attempt_id": mapping["attempt"],
            "result_hash": result["fingerprint"],
            "work_revision": work["revision"],
            "basis_refs": [
                {"id": progress["id"], "revision": progress["revision"], "role": "must_be_current"}
            ],
        },
    }
    return core, token, payload, progress


def test_single_successor_concurrent_commands_and_exact_replay(tmp_path: Path) -> None:
    core, token, payload, _ = parent(tmp_path)

    def create(n: int) -> tuple[str, Any]:
        try:
            request = copy.deepcopy(payload)
            request["id"] = "child" + str(n)
            return "ok", core.connect(token).call("open_work", request, "late" + str(n))
        except CoreError as error:
            return error.code, error.field

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, [1, 2]))
    assert sorted(r[0] for r in results) == ["identity_conflict", "ok"]
    winner = next(i + 1 for i, r in enumerate(results) if r[0] == "ok")
    request = copy.deepcopy(payload)
    request["id"] = "child" + str(winner)
    replay = core.connect(token).call("open_work", request, "late" + str(winner))
    assert replay == results[winner - 1][1]
    assert replay["continuation"]["basis_refs"][0]["role"] == "exact"
    assert (
        len(
            [
                w
                for w in Coordinator(core.connect(token)).rows("works")
                if json.loads(w["body"]).get("continuation", {}).get("kind") == "late"
            ]
        )
        == 1
    )


@pytest.mark.parametrize("field", ["result_hash", "work_revision", "role", "scope"])
def test_forged_late_basis_creates_nothing(tmp_path: Path, field: str) -> None:
    core, token, payload, _ = parent(tmp_path)
    if field == "result_hash":
        payload["continuation_from"]["result_hash"] = "0" * 64
    elif field == "work_revision":
        payload["continuation_from"]["work_revision"] += 1
    elif field == "role":
        payload["continuation_from"]["basis_refs"][0]["role"] = "exact"
    else:
        payload["scope"] = "space"
    with pytest.raises(CoreError):
        core.connect(token).call("open_work", payload, "forged")
    assert len(Coordinator(core.connect(token)).rows("works")) == 1


def test_current_progress_head_cas_then_immutable_exact_binding(tmp_path: Path) -> None:
    core, token, payload, progress = parent(tmp_path)
    owner = core.connect(token)
    owner.call(
        "apply_changes",
        {
            "changes": [
                {
                    "id": progress["id"],
                    "kind": "data",
                    "key": progress["key"],
                    "scope": progress["scope"],
                    "body": progress["body"]["value"],
                }
            ]
        },
        "advance",
        expected_heads={progress["id"]: progress["revision"]},
    )
    with pytest.raises(CoreError, match="stale_basis"):
        owner.call("open_work", payload, "stale")
    payload["continuation_from"]["basis_refs"][0]["revision"] += 1
    child = owner.call("open_work", payload, "fresh")
    assert child["continuation"]["basis_refs"][0]["revision"] == progress["revision"] + 1
    assert (
        child["continuation"]["parent_work_revision"]
        == payload["continuation_from"]["work_revision"]
    )


@pytest.mark.parametrize(
    "mutation", ["new_window", "drop_prefix", "future_high", "foreign_delivery", "v1_downgrade"]
)
def test_v2_cannot_forge_processed_boundary_or_attribution(tmp_path: Path, mutation: str) -> None:
    core, token, _, _ = parent(tmp_path)
    session = NativeSession(core, token, "child")
    context = session.start_sleep("subject", portion=2)
    owner = core.connect(token)
    co = Coordinator(owner)
    work_id = context["current"]["work"]
    progress = Sleep(owner).progress(work_id)
    value = copy.deepcopy(progress["body"]["value"])
    work = co.rows("works", work=work_id)[0]
    actions = co.rows("actions", work=work_id)
    value["consumed_resource"] = work["reserved"]
    value["unresolved_calls"] = sorted(
        a["id"] for a in actions if a["state"] not in {"terminal", "not_received"}
    )
    if mutation == "new_window":
        value["transition"] = "new_window"
        value["range_start"] = [value["source_high_watermark"], 2147483647]
        value["enumeration_cursor"] = value["range_start"]
        value["enumerated_source_refs"] = []
        value["selected_source_refs"] = []
        value["remaining_refs"] = []
    elif mutation == "drop_prefix":
        value["enumerated_source_refs"] = []
        value["remaining_refs"] = []
        value["selected_source_refs"] = []
    elif mutation == "future_high":
        value["source_high_watermark"] += 100000
    elif mutation == "foreign_delivery":
        previous = owner.call("read_exact", value["predecessor_ref"], uuid4().hex)["body"]["value"]
        parent_attempt = co.rows("attempts", work=previous["work_id"])[0]
        pinned = json.loads(parent_attempt["body"])
        value["delivered_manifest_refs"] = [pinned["sleep_delivery_manifest"]]
    else:
        value["format"] = "sleep-progress/v1"
        for field in ("predecessor_ref", "transition", "range_start"):
            value.pop(field)
    with pytest.raises(CoreError):
        owner.call(
            "apply_changes",
            {
                "changes": [
                    {
                        "id": progress["id"],
                        "kind": "data",
                        "key": progress["key"],
                        "scope": "subject",
                        "body": value,
                    }
                ]
            },
            "bad",
            expected_heads={progress["id"]: progress["revision"]},
        )
    assert Sleep(owner).progress(work_id) == progress


def test_historical_lineage_over_python_recursion_limit_and_cycle(tmp_path: Path) -> None:
    # Deliberately synthetic relational fixture: tests traversal, never semantic evidence.
    from zaratustra_core.continuation import progress_proof

    core, _ = Core.initialize(tmp_path / "deep")
    with sqlite3.connect(core.path) as db:
        db.row_factory = sqlite3.Row
        db.execute("INSERT INTO conversations(id) VALUES('chat')")
        method = {"id": "method", "revision": 1}
        db.execute(
            "INSERT INTO records VALUES('method',1,'method','method','space',?)",
            (json.dumps({"value": "Synthetic method"}),),
        )
        previous = None
        for number in range(1101):
            identifier = "p" + str(number)
            work_id = "w" + str(number)
            value = {
                "format": "sleep-progress/v1",
                "work_id": work_id,
                "method_ref": method,
                "scope": "space",
                "source_high_watermark": 0,
                "enumeration_cursor": [0, 2147483647],
                "enumerated_source_refs": [],
                "selected_source_refs": [],
                "delivered_manifest_refs": [],
                "analysis_result_refs": [],
                "unexplored_coverage_position": {"unknown": True},
                "applied_receipts": [],
                "proposed_changes": [],
                "remaining_refs": [],
                "return_conditions": [],
                "consumed_resource": 0,
                "unresolved_calls": [],
                "stop_reason": "",
                "continuation": "",
            }
            body: dict[str, Any] = {"scope": "space", "method_ref": method}
            if number:
                ref = {"id": "p" + str(number - 1), "revision": 1, "role": "exact"}
                value.update(
                    format="sleep-progress/v2",
                    predecessor_ref=ref,
                    transition="same_window",
                    range_start=[0, 0],
                )
                body["continuation"] = {
                    "kind": "late",
                    "parent_work_id": "w" + str(number - 1),
                    "attempt_id": "a" + str(number - 1),
                    "result_hash": "0" * 64,
                    "basis_refs": [ref],
                }
            db.execute(
                "INSERT INTO works(id,revision,conversation,status,generation,body) "
                "VALUES(?,1,'chat','completed',1,?)",
                (work_id, json.dumps(body)),
            )
            db.execute(
                "INSERT INTO attempts VALUES(?,?,'chat','finished',1,0,0,'{}')",
                ("a" + str(number), work_id),
            )
            db.execute(
                "INSERT INTO results VALUES(?,'final',?,?)",
                ("a" + str(number), "0" * 64, json.dumps({"state": "completed"})),
            )
            db.execute(
                "INSERT INTO records VALUES(?,1,'data',?,'space',?)",
                (identifier, identifier, json.dumps({"value": value})),
            )
            if number == 0:
                previous = copy.deepcopy(value)
        assert progress_proof(core, db, value, "space")["analysed"] == []
        assert previous is not None
        previous.update(
            format="sleep-progress/v2",
            predecessor_ref={"id": "p1100", "revision": 1},
            transition="same_window",
            range_start=[0, 0],
        )
        db.execute("UPDATE records SET body=? WHERE id='p0'", (json.dumps({"value": previous}),))
        with pytest.raises(CoreError, match="progress.cycle"):
            progress_proof(core, db, value, "space")


def test_successor_own_analysis_commits_with_its_own_receipt(tmp_path: Path) -> None:
    core, token, _, _ = parent(tmp_path)
    session = NativeSession(core, token, "child")
    context = session.start_sleep("subject", portion=2)
    complete(session, analysed=True)
    value = Sleep(core.connect(token)).progress(context["current"]["work"])["body"]["value"]
    assert value["analysis_result_refs"] and value["delivered_manifest_refs"]
    with core._transaction() as db:
        from zaratustra_core.continuation import progress_proof

        assert progress_proof(core, db, value, "subject")["analysed"]


def test_v2_cannot_claim_foreign_empty_source_analysis_as_own(tmp_path: Path) -> None:
    core, token, _, _ = parent(tmp_path)
    owner = core.connect(token)
    owner.call(
        "apply_changes",
        {
            "changes": [
                {
                    "id": "foreign",
                    "kind": "data",
                    "key": "foreign",
                    "scope": "subject",
                    "body": {
                        "format": "sleep-analysis/v1",
                        "sources": [],
                        "content": "Synthetic unrelated claim",
                    },
                }
            ]
        },
        "foreign",
        expected_heads={"foreign": 0},
    )
    session = NativeSession(core, token, "child")
    context = session.start_sleep("subject", portion=2)
    co = Coordinator(owner)
    work_id = context["current"]["work"]
    progress = Sleep(owner).progress(work_id)
    value = copy.deepcopy(progress["body"]["value"])
    value["analysis_result_refs"] = [{"id": "foreign", "revision": 1}]
    value["consumed_resource"] = co.rows("works", work=work_id)[0]["reserved"]
    value["unresolved_calls"] = [a["id"] for a in co.rows("actions", work=work_id)]
    with pytest.raises(CoreError, match="progress.analysis_owner"):
        owner.call(
            "apply_changes",
            {
                "changes": [
                    {
                        "id": progress["id"],
                        "kind": "data",
                        "key": progress["key"],
                        "scope": "subject",
                        "body": value,
                    }
                ]
            },
            "foreign-proof",
            expected_heads={progress["id"]: progress["revision"]},
        )


def test_late_continuation_never_runs_under_legacy_protocol(tmp_path: Path) -> None:
    core, token, payload, _ = parent(tmp_path)
    with sqlite3.connect(core.path) as db:
        db.execute("PRAGMA user_version=0")
    assert Core(core.root).data_protocol == 0
    with pytest.raises(CoreError, match="continuation.protocol"):
        core.connect(token).call("open_work", payload, "legacy")
    assert len(Coordinator(core.connect(token)).rows("works")) == 1
