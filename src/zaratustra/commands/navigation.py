"""Compact derived file indexes for clients that cannot run local product tools."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from zaratustra import home, storage
from zaratustra.core import read_workspace
from zaratustra.journal import Scope, Store, card

from .connect import _replace


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _replace(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def refresh(root: Path, *, selected: Path | None = None, all_processes: bool = False) -> None:
    if not storage.enabled(root):
        return
    processes = []
    offset = 0
    while True:
        page = home.list_processes(root, limit=100, offset=offset)
        processes.extend(page)
        if len(page) < 100:
            break
        offset += 100
    compact = []
    scopes = []
    for process in processes:
        path = Path(process["location"])
        relative = path.relative_to(root).as_posix() if path.is_relative_to(root) else None
        compact.append(
            {
                "id": process["id"],
                "name": process["name"],
                "location": relative,
                "availability": process["availability"],
                "navigation": relative + "/.zara-data/navigation/index.json" if relative else None,
                "external_workspace": process["workspace_id"] if relative is None else None,
            }
        )
        if (all_processes or selected == path) and storage.enabled(path):
            scopes.append((path, Scope(kind="process", id=UUID(process["id"]))))
    shared = root / ".zara-home/shared"
    if storage.enabled(shared) and (all_processes or selected == shared):
        scopes.append((shared, Scope(kind="home", id=UUID(home.read_home(root)["id"]))))
    for path, scope in scopes:
        if read_workspace(path).schema_version < 8:
            continue
        with storage.locked(path):
            store = Store(path, scope, "derived file navigation")
            sources = storage.content_paths(path).get("process_materials", {})
            groups: dict[str, list[dict[str, Any]]] = {}
            for record in store.current():
                source = sources.get(json.dumps([str(record.operation_id)]), {}).get("content")
                groups.setdefault(record.type_name, []).append(
                    card(record) | {"source_file": source}
                )
            indexes = []
            for name, cards in sorted(groups.items()):
                cards.sort(key=lambda value: (value["date"], value["id"]), reverse=True)
                pages = []
                for page_no, start in enumerate(range(0, len(cards), 20), start=1):
                    filename = f"{hashlib.sha256(name.encode()).hexdigest()[:16]}-{page_no}.json"
                    relative = ".zara-data/navigation/" + filename
                    _save(path / relative, {"type": name, "records": cards[start : start + 20]})
                    pages.append(relative)
                indexes.append({"type": name, "count": len(cards), "pages": pages})
            _save(
                path / ".zara-data/navigation/index.json",
                {
                    "derived": True,
                    "source_head": json.loads((path / ".zara-data/HEAD.json").read_bytes()),
                    "scope": scope.model_dump(mode="json"),
                    "types": indexes,
                    "reading": "Read relevant cards, then source_file. "
                    "Paths are relative to this scope root. "
                    "Historical sources retain exact bytes in confirmed operation packages.",
                },
            )
    _save(
        root / ".zara-data/navigation/index.json",
        {
            "derived": True,
            "home": home.read_home(root)["id"],
            "source_head": json.loads((root / ".zara-data/HEAD.json").read_bytes()),
            "processes": compact,
            "vocabulary": home.vocabulary(root),
            "shared_navigation": ".zara-home/shared/.zara-data/navigation/index.json"
            if storage.enabled(shared)
            else None,
            "reading": "Repository paths are relative to Home. Read the chosen process index, "
            "then selected cards and exact source files; do not load every process or history.",
        },
    )
