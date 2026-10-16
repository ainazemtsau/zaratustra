"""Fresh-process crash injection; all state is fictional and disposable."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, cast

from zaratustra_core import Core

from .support import ingest


def main() -> None:
    packet = json.load(sys.stdin)
    if packet["phase"] == "oracle":
        with sqlite3.connect(Path(packet["root"]) / "core.sqlite3") as db:
            db.row_factory = sqlite3.Row
            tables = (
                "messages",
                "intents",
                "receipts",
                "works",
                "attempts",
                "actions",
                "heads",
                "results",
                "conversations",
            )
            print(
                json.dumps({t: [dict(r) for r in db.execute("SELECT * FROM " + t)] for t in tables})
            )
        return
    core = Core(Path(packet["root"]))
    client = core.connect(packet["token"])
    phase = packet["phase"]
    if phase == "ingest_mid":
        intent = Core._intent

        def crash_intent(
            self: Core, db: sqlite3.Connection, kind: str, subject: str, body: Any
        ) -> None:
            intent(self, db, kind, subject, body)
            os._exit(91)

        type.__setattr__(Core, "_intent", crash_intent)
    if phase in {"outcome_mid", "outcome_after_final", "claim_mid"}:
        connect = sqlite3.connect

        class CrashConnection(sqlite3.Connection):
            def execute(self, sql: str, parameters: Any = (), /) -> sqlite3.Cursor:
                result = super().execute(sql, parameters)
                if (
                    (phase == "outcome_mid" and sql.startswith("UPDATE conversations SET cursor="))
                    or (phase == "outcome_after_final" and sql.startswith("INSERT INTO results"))
                    or (phase == "claim_mid" and sql.startswith("UPDATE works SET reserved="))
                ):
                    os._exit(91)
                return result

        def crash_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
            return cast(sqlite3.Connection, connect(*args, **kwargs, factory=CrashConnection))

        sqlite3.__dict__["connect"] = crash_connect
    if phase.startswith("ingest"):
        ingest(client, "21", "Now five minutes")
    elif phase.startswith("outcome"):
        client.call(
            "commit_outcome",
            packet["payload"],
            "crash-outcome",
            expected_heads=packet.get("heads", {}),
        )
    elif phase.startswith("claim"):
        client.call(
            "claim_dispatch",
            {"attempt_id": "A1", "generation": 1},
            "A1:claim",
            action_id="A1:action",
        )
        if phase == "claim_after_receiver":
            with (core.root / "receiver-effects.jsonl").open("ab") as file:
                file.write(b'{"action_id":"A1:action","state":"terminal"}' + bytes([10]))
                file.flush()
                os.fsync(file.fileno())
    elif phase == "recover":
        from zaratustra_app import Coordinator

        result = Coordinator(client).recover("A1")
        print(json.dumps(result))
        return
    os._exit(91)


if __name__ == "__main__":
    main()
