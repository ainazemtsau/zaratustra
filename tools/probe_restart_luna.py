"""Explicit authorized Luna access probe, using fictional ordinary Work and retained evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from zaratustra_app import Coordinator, LiveProfile, Pi
from zaratustra_core import Core, CoreError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--pi-cli", type=Path, required=True)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=False)
    core, token = Core.initialize(args.root)
    owner = core.connect(token)
    changes: list[dict[str, Any]] = [
        {
            "id": "method",
            "kind": "method",
            "key": "probe",
            "body": {
                "instructions": (
                    'Return ONLY JSON: {"state":"completed",'
                    '"text":"access established"}. This is a fictional '
                    "access probe, not a usefulness evaluation."
                )
            },
        },
        {
            "id": "profile",
            "kind": "profile",
            "key": "luna",
            "body": {
                "provider": "openai",
                "api": "openai-responses",
                "model": "gpt-6-luna",
                "endpoint": "https://api.openai.com/v1",
                "credential_env": "OPENAI_API_KEY",
            },
        },
    ]
    owner.call(
        "apply_changes", {"changes": changes}, "seed", expected_heads={"method": 0, "profile": 0}
    )
    client = core.connect(
        core.grant(
            token,
            "probe",
            [
                "read",
                "open_work",
                "prepare_attempt",
                "claim_dispatch",
                "observe_attempt",
                "commit_outcome",
                "reserve_tool",
                "apply_changes",
            ],
            origin="host",
        )
    )
    client.call(
        "open_work",
        {
            "id": "probe",
            "conversation": "probe",
            "goal": "Confirm authorized model access",
            "method_ref": {"id": "method", "revision": 1},
            "inputs": [],
            "call_limit": 2,
            "continuation_policy": "durable",
        },
        "open",
    )
    profile = LiveProfile(
        endpoint="https://api.openai.com/v1",
        model="gpt-6-luna",
        credential_env="OPENAI_API_KEY",
        max_tokens=1024,
    )
    pi = Pi(args.pi_cli, args.root / "pi", profile.endpoint, live=profile)
    coordinator = Coordinator(client)
    outcome: dict[str, Any]
    try:
        prepared = coordinator.prepare("probe", "probe-attempt", {"id": "profile", "revision": 1})
        coordinator.dispatch("probe-attempt", prepared["generation"], pi)
        outcome = {"success": True, "outcome": coordinator.recover("probe-attempt", pi=True)}
    except CoreError as error:
        outcome = {"success": False, "error": error.as_dict()}
    finally:
        (args.evidence / "native-stderr.txt").write_text(pi.stderr, encoding="utf-8")
        (args.evidence / "native-events.json").write_text(
            json.dumps(pi.events, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (args.evidence / "snapshot.json").write_text(
            json.dumps(coordinator.snapshot(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
    (args.evidence / "outcome.json").write_text(json.dumps(outcome, indent=2), encoding="utf-8")
    print(json.dumps(outcome))
    return 0 if outcome["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
