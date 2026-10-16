"""Physical crash/maintenance worker over disposable test roots."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from zaratustra_core import Core


def main() -> None:
    packet = json.load(sys.stdin)
    core = Core(Path(packet["root"]))
    phase = packet["phase"]
    if phase == "restore":
        restored, token = Core.restore_quarantined(
            Path(packet["backup"]), Path(packet["destination"])
        )
        print(json.dumps({"restored": True, "epoch": restored.connect(token).meta["epoch"]}))
        return
    if phase == "read":
        print(
            json.dumps(
                core.connect(packet["token"]).call(
                    "read_artifact", {"sha256": packet["sha256"]}, "read-child"
                )
            )
        )
        return
    if phase in {"stage_sync", "stage_replace"}:
        from zaratustra_core import storage

        original = os.fsync if phase == "stage_sync" else os.replace

        def crash(*args: Any, **kwargs: Any) -> None:
            original(*args, **kwargs)
            os._exit(91)

        storage.__dict__["os"].__dict__["fsync" if phase == "stage_sync" else "replace"] = crash
    if phase in {"backup_partial", "backup_hold", "backup_hold_inventory"}:
        from zaratustra_core import maintenance

        original_durable = maintenance.__dict__["durable"]

        def hold() -> None:
            Path(packet["ready"]).write_text("locked", encoding="utf-8")
            deadline = time.monotonic() + 20
            while not Path(packet["release"]).exists():
                if time.monotonic() > deadline:
                    raise RuntimeError("test maintenance release missing")
                time.sleep(0.01)

        def durable(path: Path, raw: bytes) -> None:
            if path.name == "manifest.json":
                if phase == "backup_partial":
                    os._exit(91)
                if phase == "backup_hold":
                    hold()
            original_durable(path, raw)

        maintenance.__dict__["durable"] = durable
        if phase == "backup_hold_inventory":
            original_target = maintenance.__dict__["target"]

            def held_target(source: Path, destination: Path) -> Path:
                result: Path = original_target(source, destination)
                hold()
                return result

            maintenance.__dict__["target"] = held_target
        core.backup(packet["token"], Path(packet["destination"]))
        return
    raw = base64.b64decode(packet["raw_base64"])
    result = core.connect(packet["token"]).call(
        "stage_artifact",
        {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "raw_base64": packet["raw_base64"],
            "content_type": "application/octet-stream",
        },
        "stage-child",
    )
    if phase == "stage_committed":
        os._exit(91)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
