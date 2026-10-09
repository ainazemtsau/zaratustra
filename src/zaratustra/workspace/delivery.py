"""Prepared local Git delivery, separate from domain acceptance and local saving."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from zaratustra.foundation import (
    LocalAuthority,
    ProjectionReceipt,
    export_workspace_projection,
    read_space,
    validate_workspace_projection,
)

from .config import LaunchConfig

IGNORE_TEXT = (
    "/space/\n/.zaratustra/\n/runtime/\n/install/\n/release/\n/work/\n"
    "**/.env\n**/.env.*\n**/auth.json\n**/credentials.json\n**/node_modules/\n"
    "**/.venv/\n**/__pycache__/\n**/*.sqlite3*\n**/*.sqlite*\n**/.cache/\n"
)


class GitPreparation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preparation_id: UUID
    repository: str
    files: dict[str, str]
    removed: tuple[str, ...] = ()
    projection: ProjectionReceipt
    status: Literal[
        "prepared", "deferred", "committing", "pushing", "published", "unknown", "failed"
    ]
    commit: str | None = None
    error: str | None = None


def _command(root: Path, arguments: list[str]) -> str:
    result = subprocess.run(
        arguments, cwd=root, text=True, encoding="utf-8", capture_output=True, check=False
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "Git command failed")
    return result.stdout.rstrip("\r\n")


def _git(root: Path, *arguments: str) -> str:
    return _command(root, ["git", *arguments])


def _journal(config: LaunchConfig) -> Path:
    if config.version != 2 or config.runtime_root is None:
        raise ValueError("Git delivery requires explicit V2 workspace configuration")
    return config.runtime_root / "git-delivery.json"


def _save(config: LaunchConfig, preparation: GitPreparation) -> None:
    path = _journal(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(".pending")
    pending.write_text(preparation.model_dump_json(indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def _load(config: LaunchConfig) -> GitPreparation | None:
    path = _journal(config)
    return GitPreparation.model_validate_json(path.read_bytes()) if path.exists() else None


def check_destination(config: LaunchConfig) -> None:
    if config.git is None:
        raise ValueError("No permitted personal Git destination is configured")
    root = config.workspace.resolve()
    if Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise ValueError("Personal workspace must be its own Git repository")
    actual = _git(root, "remote", "get-url", "origin")
    permitted = {config.git.url, f"git@github.com:{config.git.repository}.git"}
    if actual not in permitted:
        raise ValueError("Origin differs from the permitted personal destination")
    metadata = json.loads(
        _command(
            root,
            ["gh", "repo", "view", config.git.repository, "--json", "nameWithOwner,visibility"],
        )
    )
    if (
        metadata["nameWithOwner"].casefold() != config.git.repository.casefold()
        or metadata["visibility"] != "PRIVATE"
    ):
        raise ValueError("Personal publication requires the configured private repository")
    if _git(root, "branch", "--show-current") != config.git.branch:
        raise ValueError("Personal publication requires main")


def initialize_git(config: LaunchConfig, *, create_private: bool = False) -> None:
    """Explicit optional connection; never inherit the product's Git ancestry."""
    if config.git is None:
        raise ValueError("Specify a personal Git destination first")
    root = config.workspace.resolve()
    if not (root / ".git").exists():
        # Refuse roots within any existing repository before creating a nested one.
        probe = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        if probe.returncode == 0:
            raise ValueError("Choose a personal folder outside the source repository")
        _git(root, "init", "--initial-branch=main")
    if create_private:
        try:
            _command(root, ["gh", "repo", "view", config.git.repository, "--json", "visibility"])
        except ValueError:
            _command(root, ["gh", "repo", "create", config.git.repository, "--private"])
    remotes = _git(root, "remote").splitlines()
    if "origin" not in remotes:
        _git(root, "remote", "add", "origin", config.git.url)
    check_destination(config)


def _plain_file(root: Path, relative: str) -> Path:
    target = root / relative
    if not target.resolve().is_relative_to(root.resolve()) or target.is_symlink():
        raise ValueError("Delivery cannot follow filesystem links outside the personal workspace")
    current = target
    while current != root:
        if current.is_symlink() or current.is_junction():
            raise ValueError("Delivery cannot contain filesystem links")
        current = current.parent
    return target


def _remove_staging(root: Path, target: Path) -> None:
    # Only product-created staging trees, after checking resolved bounds and links.
    _plain_file(root.resolve(), target.relative_to(root).as_posix())
    if target.resolve() == root.resolve():
        raise ValueError("Cannot remove the staging root")
    shutil.rmtree(target)


def _check_packet(config: LaunchConfig, item: GitPreparation, *, commit: str | None = None) -> None:
    for name, digest in item.files.items():
        target = _plain_file(config.workspace.resolve(), name)
        if (
            not target.is_file()
            or hashlib.sha256(target.read_bytes()).hexdigest().upper() != digest
        ):
            raise ValueError(f"Prepared file changed: {name}; prepare again")
        if commit:
            data = subprocess.run(
                ["git", "show", f"{commit}:{name}"],
                cwd=config.workspace,
                capture_output=True,
                check=True,
            ).stdout
            if hashlib.sha256(data).hexdigest().upper() != digest:
                raise ValueError(f"Commit contains different bytes: {name}; no push attempted")
    for name in item.removed:
        if _plain_file(config.workspace.resolve(), name).exists():
            raise ValueError(f"Prepared removal changed: {name}; prepare again")


def _delivery_files(config: LaunchConfig) -> dict[str, str]:
    root = config.workspace.resolve()
    candidates = [root / "README.md", root / ".gitignore", root / ".gitattributes"]
    for folder in ("activities", "documents", "projects"):
        chosen = root / folder
        if chosen.exists():
            candidates.extend(chosen.rglob("*"))
    files = {}
    excluded = {".git", "node_modules", ".venv", "__pycache__", ".cache"}
    for target in candidates:
        relative = target.relative_to(root).as_posix()
        if any(part in excluded for part in target.relative_to(root).parts):
            continue
        if target.name.startswith(".env") or target.name in ("auth.json", "credentials.json"):
            continue
        if ".sqlite" in target.name or not target.is_file():
            continue
        target = _plain_file(root, relative)
        files[relative] = hashlib.sha256(target.read_bytes()).hexdigest().upper()
    return files


def prepare_git(config: LaunchConfig, authority: LocalAuthority) -> GitPreparation:
    check_destination(config)
    prior = _load(config)
    if prior and prior.status in ("committing", "pushing", "unknown"):
        raise ValueError("Resolve the previous unknown delivery before preparing another one")
    assert config.runtime_root is not None and config.git is not None
    staging_root = config.workspace / ".zaratustra"
    _plain_file(config.workspace.resolve(), ".zaratustra")
    staging_root.mkdir(parents=True, exist_ok=True)
    staging = staging_root / f"projection-{uuid4()}"
    try:
        receipt = export_workspace_projection(config.space, authority, staging)
        target = config.workspace / "activities"
        _plain_file(config.workspace.resolve(), "activities")
        previous = staging_root / "previous-projection"
        # Recover a crash between the two directory renames before another replacement.
        if previous.exists() and not target.exists():
            previous.rename(target)
        elif previous.exists():
            _remove_staging(staging_root, previous)
        if target.exists():
            target.rename(previous)
        try:
            staging.rename(target)
        except OSError:
            if previous.exists():
                previous.rename(target)
            raise
        if previous.exists():
            _remove_staging(staging_root, previous)
    finally:
        if staging.exists():
            _remove_staging(staging_root, staging)
    ignore = config.workspace / ".gitignore"
    _plain_file(config.workspace.resolve(), ".gitignore")
    existing = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    if IGNORE_TEXT not in existing:
        ignore.write_text(existing + "\n" + IGNORE_TEXT, encoding="utf-8")
    attributes = config.workspace / ".gitattributes"
    _plain_file(config.workspace.resolve(), ".gitattributes")
    existing_attributes = attributes.read_text(encoding="utf-8") if attributes.exists() else ""
    exact = "\n# Preserve exact prepared bytes (including original line endings).\n* -text\n"
    if exact not in existing_attributes:
        attributes.write_bytes((existing_attributes + exact).encode("utf-8"))
    files = _delivery_files(config)
    tracked = _git(config.workspace, "ls-files", "-z").split("\0")
    # Stale derived files may be removed. Never stage unrelated tracked deletions.
    removed = tuple(
        name for name in tracked if name.startswith("activities/") and name not in files
    )
    preparation = GitPreparation(
        preparation_id=uuid4(),
        repository=config.git.repository,
        files=files,
        removed=removed,
        projection=receipt,
        status="prepared",
    )
    _save(config, preparation)
    return preparation


def defer_git(config: LaunchConfig, preparation_id: UUID) -> GitPreparation:
    item = _load(config)
    if item is None or item.preparation_id != preparation_id or item.status != "prepared":
        raise ValueError("No matching prepared delivery")
    item.status = "deferred"
    _save(config, item)
    return item


def reconcile_git(config: LaunchConfig) -> GitPreparation | None:
    """Read remote refs after an uncertain push; never resend here."""
    check_destination(config)
    item = _load(config)
    if item is None:
        return None
    if item.status == "committing" and item.commit is None:
        # The exact id in the commit message lets restart observe a completed commit.
        try:
            _git(config.workspace, "rev-parse", "HEAD")
        except ValueError:
            item.status, item.error = "failed", "No commit exists; no push was attempted"
            _save(config, item)
            return item
        match = _git(
            config.workspace,
            "log",
            "-1",
            "--format=%H",
            "--fixed-strings",
            f"--grep=Zaratustra-Preparation: {item.preparation_id}",
        )
        if match:
            item.commit = match
            item.status = "unknown"
        else:
            item.status = "failed"
            item.error = "Commit was not observed; no push was attempted"
    if item.commit and item.status in ("pushing", "unknown"):
        assert config.git is not None
        remote = _git(config.workspace, "ls-remote", "origin", f"refs/heads/{config.git.branch}")
        if remote.split()[:1] == [item.commit]:
            item.status, item.error = "published", None
        else:
            item.status = "unknown"
            item.error = "Remote does not yet confirm the exact commit; no automatic retry"
    _save(config, item)
    return item


def publish_git(
    config: LaunchConfig,
    authority: LocalAuthority,
    preparation_id: UUID,
    *,
    approved: bool,
) -> GitPreparation:
    """Only a trusted console/UI caller may supply approval for this exact packet."""
    if not approved:
        return defer_git(config, preparation_id)
    check_destination(config)
    item = _load(config)
    if item is None or item.preparation_id != preparation_id:
        raise ValueError("No matching prepared delivery")
    if item.status == "published":
        return item
    if item.status not in ("prepared", "deferred"):
        raise ValueError("Previous delivery needs reconciliation, not a blind retry")
    validate_workspace_projection(config.space, authority, item.projection)
    _check_packet(config, item)
    staged = set(
        filter(None, _git(config.workspace, "diff", "--cached", "--name-only", "-z").split("\0"))
    )
    if staged - set(item.files) - set(item.removed):
        raise ValueError("Unrelated staged files must be preserved outside this delivery")
    item.status = "committing"
    _save(config, item)
    try:
        # A pathspec file avoids shell interpretation and command-line size limits.
        assert config.runtime_root is not None
        paths = config.runtime_root / "git-paths"
        paths.write_bytes(
            b"\0".join(name.encode() for name in (*item.files, *item.removed)) + b"\0"
        )
        _git(
            config.workspace,
            "--literal-pathspecs",
            "add",
            f"--pathspec-from-file={paths}",
            "--pathspec-file-nul",
        )
        if _git(config.workspace, "diff", "--cached", "--name-only"):
            body = config.runtime_root / "git-commit-message"
            body.write_text(
                f"Save personal workspace snapshot\n\nZaratustra-Preparation: "
                f"{item.preparation_id}\n",
                encoding="utf-8",
            )
            _git(config.workspace, "commit", "--file", str(body))
        item.commit = _git(config.workspace, "rev-parse", "HEAD")
        _check_packet(config, item, commit=item.commit)
        item.status = "pushing"
        _save(config, item)  # Persist expected ref before any network effect.
        check_destination(config)
        validate_workspace_projection(config.space, authority, item.projection)
        _git(config.workspace, "push", "origin", f"{item.commit}:refs/heads/main")
    except (OSError, ValueError) as error:
        item.status = "unknown" if item.commit else "committing"
        item.error = str(error)
        _save(config, item)
        raise
    observed = reconcile_git(config)
    assert observed is not None
    if observed.status != "published":
        raise ValueError("Push returned but the exact remote ref is not confirmed")
    return observed


def git_status(config: LaunchConfig) -> dict[str, object]:
    if config.git is None:
        return {"connected": False, "pending": True}
    item = _load(config)
    root = config.workspace.resolve()
    try:
        changed = _git(root, "status", "--porcelain", "--untracked-files=normal")
    except ValueError:
        changed = "Git is not initialized"
    current = read_space(config.space)
    return {
        "connected": True,
        "repository": config.git.repository,
        "branch": "main",
        "pending": bool(changed)
        or item is None
        or item.status != "published"
        or item.projection.state_revision != current.state_revision,
        "changes": changed,
        "delivery": {
            "preparation_id": str(item.preparation_id),
            "status": item.status,
            "commit": item.commit,
            "error": item.error,
            "file_count": len(item.files),
            "files": list(item.files),
            "snapshot_state_revision": item.projection.state_revision,
        }
        if item
        else None,
    }
