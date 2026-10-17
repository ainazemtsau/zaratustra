"""Hot application reads exclude unrelated retained bodies without changing Core replay."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from zaratustra_app import Coordinator, Driver
from zaratustra_app.conversation import pin_profile
from zaratustra_app.native_session import NativeSession
from zaratustra_core import Client, Core, wire

from .support import MEMORY, METHOD, PROFILE, Receiver, inspect
from .test_contract import prepared


def test_actual_native_claim_and_profile_lookup_beyond_one_thousand_heads(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "native")
    owner = core.connect(token)
    for start in range(0, 1001, 32):
        changes = [
            {"id": f"retained-{n}", "kind": "data", "key": f"retained-{n}", "body": str(n)}
            for n in range(start, min(start + 32, 1001))
        ]
        owner.call(
            "apply_changes",
            {"changes": changes},
            f"seed-{start}",
            expected_heads={change["id"]: 0 for change in changes},
        )
    session = NativeSession(core, token, "fictional-long-history")
    session.profile = {"provider": "fictional", "model": "fictional-model"}
    context = session.input("fictional-input", "Continue the fictional Activity")
    attempt = context["current"]["attempt"]
    assert attempt
    assert (
        next(row for row in inspect(core, "attempts") if row["id"] == attempt)["status"]
        == "claimed"
    )
    assert len(inspect(core, "heads")) > 1001
    descriptor = {"provider": "fictional", "model": "standalone"}
    ref = pin_profile(owner, "stable-profile", descriptor)
    assert pin_profile(owner, "stable-profile", descriptor) == ref
    assert owner.call("read_exact", ref, "exact-profile")["body"]["value"] == descriptor


def test_dispatch_and_recover_read_only_current_work_observations(
    tmp_path: Path, monkeypatch: Any
) -> None:
    core, owner, executor, coordinator = prepared(tmp_path)
    owner.call(
        "open_work",
        {
            "id": "other-work",
            "conversation": "other-conversation",
            "goal": "Unrelated retained work",
            "method_ref": METHOD,
            "inputs": [MEMORY],
            "call_limit": 4,
            "continuation_policy": "durable",
        },
        "other-open",
    )
    foreign = Coordinator(owner)
    foreign.prepare("other-work", "other-attempt", PROFILE)
    owner.call(
        "claim_dispatch",
        {"attempt_id": "other-attempt", "generation": 1},
        "other-claim",
        action_id="other-action",
    )
    marker = "unrelated-large-history-" + "x" * 250_000
    owner.call(
        "observe_attempt",
        {
            "attempt_id": "other-attempt",
            "event_id": "large-observation",
            "kind": "progress",
            "raw_base64": base64.b64encode(marker.encode()).decode(),
        },
        "other-observation",
    )
    calls: list[tuple[str, dict[str, Any], int, str]] = []
    original = Client.call

    def tracked(
        self: Client, operation: str, payload: dict[str, Any], command: str, **kwargs: Any
    ) -> Any:
        result = original(self, operation, payload, command, **kwargs)
        calls.append((operation, payload, len(wire(result)), json.dumps(result)))
        return result

    monkeypatch.setattr(Client, "call", tracked)
    coordinator.dispatch("A1", 1, Driver(Receiver()))
    retained = Coordinator(executor).recover("A1")
    assert retained["state"] == "waiting"
    observation_reads = [
        call for call in calls if call[0] == "read_page" and call[1]["table"] == "observations"
    ]
    assert observation_reads
    assert all(call[1]["work"] == "work" for call in observation_reads)
    assert all(call[2] < 10_000 for call in observation_reads)
    assert not any(call[0] == "read_snapshot" for call in calls)
    assert not any(base64.b64encode(marker.encode()).decode() in call[3] for call in calls)
    assert len(inspect(core, "observations")) >= 2


def test_selected_tables_match_public_snapshot_and_preserve_old_command_replay(
    tmp_path: Path,
) -> None:
    core, owner, _, coordinator = prepared(tmp_path)
    before = owner.call("read_snapshot", {}, "old-snapshot-command")
    owner.call(
        "apply_changes",
        {
            "changes": [
                {"id": "new-data", "kind": "data", "key": "new-data", "body": "new exact value"},
            ]
        },
        "new-record",
        expected_heads={"new-data": 0},
    )
    assert owner.call("read_snapshot", {}, "old-snapshot-command") == before
    fresh = owner.call("read_snapshot", {}, "new-snapshot-command")
    assert {row["id"] for row in fresh["heads"]} == {row["id"] for row in before["heads"]} | {
        "new-data"
    }
    selected = coordinator.tables("heads", "works")
    assert set(selected) == {"heads", "works"}
    assert selected["heads"] == fresh["heads"]
    assert selected["works"] == fresh["works"]
    assert coordinator.rows("works", work="work") == fresh["works"]
    assert coordinator.rows("works", work="absent") == []
    assert inspect(core, "records")[-1]["id"] == "new-data"
