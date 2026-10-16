"""Explicit-data-root, model-free entry; no automatic provider fallback."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from zaratustra_core import Core

from .executor_port import LiveProfile, Pi
from .sleep import Sleep


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("command", choices=["init", "diagnostics", "sleep"])
    parser.add_argument("--profile-file", type=Path)
    parser.add_argument("--work-id")
    parser.add_argument("--call-limit", type=int)
    parser.add_argument("--scope", default="space")
    parser.add_argument("--portion", type=int, default=16)
    parser.add_argument("--refresh-basis", action="store_true")
    args = parser.parse_args()
    if args.command == "init":
        core, token = Core.initialize(args.data_root)
        credential = args.data_root / "owner.credential"
        credential.write_text(token, encoding="utf-8")
        print(json.dumps({"data_root": str(core.root), "credential_file": str(credential)}))
    elif args.command == "sleep":
        if args.profile_file is None or args.call_limit is None or args.work_id is None:
            parser.error("sleep requires --profile-file, --call-limit and stable --work-id")
        config = json.loads(args.profile_file.read_text(encoding="utf-8"))
        pi_cli = Path(config.pop("pi_cli"))
        profile = LiveProfile(**config)
        core = Core(args.data_root)
        token = (args.data_root / "owner.credential").read_text(encoding="utf-8").strip()
        owner = core.connect(token)
        profile_id = args.work_id + ":profile"
        heads = owner.call("read_snapshot", {}, uuid4().hex)["heads"]
        if not any(h["id"] == profile_id for h in heads):
            owner.call(
                "apply_changes",
                {
                    "changes": [
                        {"id": profile_id, "kind": "profile", "key": profile_id, "body": config}
                    ]
                },
                profile_id + ":create",
                expected_heads={profile_id: 0},
            )
        client = core.connect(
            core.grant(
                token,
                "sleep:" + args.work_id,
                [
                    "read",
                    "apply_changes",
                    "open_work",
                    "prepare_attempt",
                    "claim_dispatch",
                    "observe_attempt",
                    "commit_outcome",
                    "control_work",
                    "reserve_tool",
                    "write:memory:" + args.scope,
                    "write:method:" + args.scope,
                ],
                origin="host",
            )
        )
        sleep = Sleep(client)
        sleep.start(
            work_id=args.work_id,
            scope=args.scope,
            call_limit=args.call_limit,
            portion=args.portion,
            method_id="sleep-method:" + args.scope,
        )
        if args.refresh_basis:
            sleep.coordinator.refresh_basis(args.work_id)
        result = sleep.run(
            args.work_id,
            {"id": profile_id, "revision": 1},
            Pi(pi_cli, args.data_root / "pi", profile.endpoint, live=profile),
        )
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(
            json.dumps(
                {
                    "sqlite_exists": (args.data_root / "core.sqlite3").is_file(),
                    "contract": "wire/v1",
                    "model_called": False,
                    "preview": True,
                }
            )
        )
    return 0
