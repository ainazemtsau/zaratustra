"""Explicit-data-root, model-free entry; no automatic provider fallback."""

import argparse
import json
from pathlib import Path

from zaratustra_core import Core


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("command", choices=["init", "diagnostics"])
    args = parser.parse_args()
    if args.command == "init":
        core, token = Core.initialize(args.data_root)
        credential = args.data_root / "owner.credential"
        credential.write_text(token, encoding="utf-8")
        print(json.dumps({"data_root": str(core.root), "credential_file": str(credential)}))
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
