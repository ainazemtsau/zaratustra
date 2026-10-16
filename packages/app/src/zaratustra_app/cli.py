"""Explicit-data-root, model-free entry; no automatic provider fallback."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from zaratustra_core import Core, CoreError, digest

from .conversation import Conversation
from .executor_port import LiveProfile, Pi
from .sleep import Sleep


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument(
        "command", choices=["init", "diagnostics", "sleep", "chat", "backup", "restore", "artifact"]
    )
    parser.add_argument("--profile-file", type=Path)
    parser.add_argument("--work-id")
    parser.add_argument("--call-limit", type=int)
    parser.add_argument("--scope", default="space")
    parser.add_argument("--portion", type=int, default=16)
    parser.add_argument("--refresh-basis", action="store_true")
    parser.add_argument("--message")
    parser.add_argument("--conversation", default="ordinary")
    parser.add_argument("--reply-to")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.command == "init":
        core, token = Core.initialize(args.data_root)
        credential = args.data_root / "owner.credential"
        credential.write_text(token, encoding="utf-8")
        print(json.dumps({"data_root": str(core.root), "credential_file": str(credential)}))
    elif args.command == "restore":
        if args.file is None:
            parser.error(
                "restore requires --file <backup directory>; --data-root is the NEW destination"
            )
        core, _ = Core.restore_quarantined(args.file, args.data_root)
        print("Restored for inspection only (quarantined): " + str(core.root))
    elif args.command == "backup":
        if args.destination is None:
            parser.error("backup requires --destination <new directory>")
        core = Core(args.data_root)
        token = (args.data_root / "owner.credential").read_text(encoding="utf-8").strip()
        print(json.dumps(core.backup(token, args.destination), ensure_ascii=False))
    elif args.command == "artifact":
        if args.file is None:
            parser.error("artifact requires --file <chosen file>")
        import base64
        import hashlib

        raw = args.file.read_bytes()
        core = Core(args.data_root)
        token = (args.data_root / "owner.credential").read_text(encoding="utf-8").strip()
        print(
            json.dumps(
                core.connect(token).call(
                    "stage_artifact",
                    {
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "raw_base64": base64.b64encode(raw).decode(),
                        "content_type": "application/octet-stream",
                    },
                    uuid4().hex,
                )
            )
        )
    elif args.command == "chat":
        if args.profile_file is None or args.call_limit is None:
            parser.error("chat requires --profile-file and finite --call-limit")
        config = json.loads(args.profile_file.read_text(encoding="utf-8"))
        pi_cli = Path(config.pop("pi_cli"))
        profile = LiveProfile(**config)
        core = Core(args.data_root)
        token = (args.data_root / "owner.credential").read_text(encoding="utf-8").strip()
        session = Conversation(core, token, args.conversation)
        descriptor = asdict(profile) | {
            "pi_cli": str(pi_cli.resolve()),
            "resource_upper": Pi.resource_upper,
        }
        reply = None
        if args.reply_to:
            waits = session.coordinator.snapshot()["waits"]
            wait = next(
                (
                    w
                    for w in waits
                    if w["id"] == args.reply_to
                    and w["conversation"] == args.conversation
                    and w["status"] == "waiting"
                ),
                None,
            )
            if wait is None:
                raise CoreError("stale_basis", "reply_to")
            reply = {"id": wait["id"], "revision": wait["revision"]}
        if args.message is not None:
            session.submit(args.message, reply)
        while True:
            executor = Pi(pi_cli, args.data_root / "pi", profile.endpoint, live=profile)
            result = session.run(executor, descriptor, args.call_limit, refresh=args.refresh_basis)
            print(result["text"])
            if result["state"] not in {"idle", "completed", "waiting"}:
                print("Состояние: " + result["state"])
            if args.message is not None:
                break
            try:
                prompt = "Ответ на показанный вопрос> " if result.get("reply_to") else "Вы> "
                text = input(prompt)
            except (EOFError, KeyboardInterrupt):
                break
            if text.strip() == "/exit":
                break
            if text.strip():
                session.submit(text, result.get("reply_to"))
            args.refresh_basis = False
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
        descriptor = asdict(profile) | {
            "pi_cli": str(pi_cli.resolve()),
            "resource_upper": Pi.resource_upper,
        }
        heads = owner.call("read_snapshot", {}, uuid4().hex)["heads"]
        existing = next((h for h in heads if h["id"] == profile_id), None)
        if existing is not None:
            pinned = owner.call(
                "read_exact", {"id": profile_id, "revision": existing["revision"]}, str(uuid4())
            )
            if (
                existing["kind"] != "profile"
                or existing["revision"] != 1
                or digest(pinned["body"]["value"]) != digest(descriptor)
            ):
                raise CoreError("stale_basis", "profile.configuration", "after_refresh")
        else:
            owner.call(
                "apply_changes",
                {
                    "changes": [
                        {"id": profile_id, "kind": "profile", "key": profile_id, "body": descriptor}
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
        core = Core(args.data_root)
        token = (args.data_root / "owner.credential").read_text(encoding="utf-8").strip()
        preview = core.connect(token).call("export_diagnostics", {}, uuid4().hex)
        rendered = json.dumps(preview, ensure_ascii=False, indent=2)
        print(rendered)
        if args.destination:
            with args.destination.open("x", encoding="utf-8") as output:
                output.write(rendered)
    return 0
