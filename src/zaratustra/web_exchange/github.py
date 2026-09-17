"""Bounded GitHub file transport through the owner's authenticated gh installation."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from typing import Any
from urllib.parse import quote

from zaratustra.journal import JournalError

from .models import Channel, Origin

MAX_FILE = 1_000_000


class GitHub:
    def __init__(self, channel: Channel) -> None:
        self.channel = channel

    def api(self, route: str, body: dict[str, Any] | None = None) -> Any:
        args = ["gh", "api", "repos/" + self.channel.repository + "/" + route]
        if body is not None:
            args += ["--method", "PUT", "--input", "-"]
        try:
            result = subprocess.run(
                args,
                input=json.dumps(body, ensure_ascii=False) if body is not None else None,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=45,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise JournalError(
                "github_unavailable", "GitHub requires working authenticated gh"
            ) from error
        if result.returncode:
            # Do not expose credentials or server-supplied instructions through errors.
            raise JournalError(
                "github_unavailable", "GitHub request failed; check access and retry"
            )
        return json.loads(result.stdout)

    def tree(self) -> tuple[str, list[dict[str, Any]]]:
        branch = self.api("commits/" + quote(self.channel.branch, safe=""))
        commit = str(branch["sha"])
        tree = self.api("git/trees/" + branch["commit"]["tree"]["sha"] + "?recursive=1")
        if tree.get("truncated"):
            raise JournalError("github_tree_truncated", "Repository listing is incomplete")
        return commit, list(tree["tree"])

    def read(self, entry: dict[str, Any]) -> bytes:
        if entry.get("type") != "blob" or entry.get("mode") not in ("100644", "100755"):
            raise JournalError("unsupported_file", "Only ordinary request files are accepted")
        if entry.get("size", MAX_FILE + 1) > MAX_FILE:
            raise JournalError(
                "file_too_large", "Request exceeds 1 MB; transfer its report separately"
            )
        blob = self.api("git/blobs/" + entry["sha"])
        raw = base64.b64decode(blob["content"].replace(chr(10), ""), validate=True)
        if len(raw) > MAX_FILE or len(raw) != entry["size"]:
            raise JournalError("invalid_blob", "GitHub blob size differs")
        digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + bytes([0]) + raw).hexdigest()
        if digest != entry["sha"]:
            raise JournalError("invalid_blob", "GitHub blob identity differs")
        return raw

    def incoming(self, prefix: str, offset: int, limit: int) -> dict[str, Any]:
        commit, entries = self.tree()
        selected = sorted(
            (e for e in entries if e["path"].startswith(prefix + "/")),
            key=lambda e: e["path"],
        )
        return {
            "commit": commit,
            "entries": selected[offset : offset + limit],
            "total": len(selected),
        }

    def origin(self, commit: str, entry: dict[str, Any]) -> Origin:
        return Origin(
            **self.channel.model_dump(), path=entry["path"], blob=entry["sha"], commit=commit
        )

    def publish(self, path: str, content: bytes) -> dict[str, Any]:
        if len(content) > MAX_FILE:
            raise JournalError("file_too_large", "Published text exceeds 1 MB")
        _, entries = self.tree()
        old = next((e for e in entries if e["path"] == path), None)
        if old:
            if self.read(old) != content:
                raise JournalError(
                    "publication_conflict", "An existing remote file differs; retained"
                )
            return {"path": path, "blob": old["sha"], "replayed": True}
        result = self.api(
            "contents/" + quote(path, safe="/"),
            {
                "branch": self.channel.branch,
                "message": "Add selected Zaratustra discussion material",
                "content": base64.b64encode(content).decode("ascii"),
            },
        )
        return {
            "path": path,
            "blob": result["content"]["sha"],
            "commit": result["commit"]["sha"],
            "url": result["content"]["html_url"],
            "replayed": False,
        }
