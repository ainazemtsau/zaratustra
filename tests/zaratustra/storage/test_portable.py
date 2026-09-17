"""Recovery and cross-device behavior, using only fictional owners and content."""

import json
import shutil
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from zaratustra import home, storage
from zaratustra.commands import Command, Context, execute
from zaratustra.commands.storage_adapter import migrate
from zaratustra.core import WorkspaceError, read_records
from zaratustra.journal import JournalError
from zaratustra.storage import files


def run(root: Path, action: str, **fields: Any) -> dict[str, Any]:
    return execute(
        Context(home=root.as_posix()),
        Command(action=action, **fields),
        source_ref="fictional owner instruction",
    )


def setup(root: Path) -> tuple[str, Path]:
    root.mkdir()
    home.init_home(root)
    created = run(root, "process.create", title="Development", purpose="Fictional work")
    return created["process"]["id"], Path(created["process"]["location"])


def clone_files(root: Path, target: Path) -> None:
    shutil.copytree(root, target, ignore=shutil.ignore_patterns(".zara-cache"))


def test_migration_clone_and_cache_loss_preserve_exact_versions(tmp_path: Path) -> None:
    root = tmp_path / "first"
    identity, workspace = setup(root)
    original = run(
        root,
        "record.create",
        process=identity,
        type_name="document",
        title="Plan",
        payload={"text": "Exact first edition\r\n", "media_type": "text/plain"},
        reason="Save owner content",
    )
    revised = run(
        root,
        "record.revise",
        process=identity,
        record=original["record"]["id"],
        expected_revision=1,
        payload={"text": "Second edition"},
        reason="Owner correction",
    )
    before = read_records(workspace).model_dump(mode="json")
    report = migrate(root)
    assert report["changed"] and Path(report["backup"]).is_dir()
    assert not (workspace / ".zara/state.sqlite3").exists()
    second = tmp_path / "second"
    clone_files(root, second)
    opened = run(second, "process.open", process=identity)
    moved = Path(opened["location"])
    assert moved.is_relative_to(second)
    assert read_records(moved).model_dump(mode="json") == before
    first = run(second, "source.read", process=identity, reference=original["reference"])
    assert json.loads(first["payload_json"])["text"] == "Exact first edition\r\n"
    found = run(second, "record.search", process=identity, query="edition")
    assert [r["revision"] for r in found["matches"]] == [revised["record"]["revision"]]
    assert "payload_schema" not in found["matches"][0]
    assert migrate(root)["changed"] is False


def test_cache_tampering_is_rebuilt_and_confirmed_file_damage_refuses(tmp_path: Path) -> None:
    root = tmp_path / "home"
    _, workspace = setup(root)
    migrate(root)
    identity = home.read_home(root)["id"]
    with closing(sqlite3.connect(root / ".zara-cache/state.sqlite3")) as db:
        db.execute("UPDATE home SET id=?", (str(uuid4()),))
        db.commit()
    assert home.read_home(root)["id"] == identity
    head = workspace / ".zara-data/HEAD.json"
    saved = head.read_bytes()
    head.write_text("<<<<<<< conflict", encoding="utf-8")
    with pytest.raises(WorkspaceError):
        read_records(workspace)
    head.write_bytes(saved)
    assert read_records(workspace).state_revision == 1


def test_failed_staging_does_not_activate(tmp_path: Path) -> None:
    root = tmp_path / "home"
    root.mkdir()
    home.init_home(root)

    def unavailable(db: sqlite3.Connection, version: int) -> None:
        raise RuntimeError("fictional interruption")

    with pytest.raises(RuntimeError, match="interruption"):
        storage.activate(root, root / ".zara-home/registry.sqlite3", "home", unavailable)
    assert not storage.enabled(root)
    assert home.read_home(root)["id"]
    assert migrate(root)["changed"]


def test_structured_search_and_explicit_vocabulary(tmp_path: Path) -> None:
    root = tmp_path / "home"
    identity, _ = setup(root)
    migrate(root)
    proposal = {
        "kind": "tag",
        "label": "Installation",
        "meaning": "Setup issues",
        "reason": "No matching tag exists",
        "considered": [],
    }
    shown = run(root, "vocabulary.propose", payload=proposal)
    tag = run(
        root,
        "vocabulary.create",
        payload=proposal
        | {
            "generation": shown["generation"],
            "proposal_token": shown["proposal_token"],
            "authority_source": "Owner: create Installation tag",
        },
    )
    repeated = run(root, "vocabulary.propose", payload=proposal | {"label": " installation "})
    assert repeated["status"] == "reuse_existing"
    problem = run(
        root,
        "record.create",
        process=identity,
        type_name="episode",
        title="Missing file",
        payload={"situation": "File missing", "outcome": "Blocked", "category": "problem"},
        metadata={"tags": [tag["id"]], "problem_status": "open"},
        reason="Journal rule",
    )
    found = run(root, "record.search", process=identity, view="open_problems", tags_all=[tag["id"]])
    assert [r["id"] for r in found["matches"]] == [problem["record"]["id"]]
    assert len(found["matches"][0]["snippet"]) <= 320
    with pytest.raises(JournalError, match="unknown_classification"):
        run(
            root,
            "record.metadata",
            process=identity,
            record=problem["record"]["id"],
            expected_revision=1,
            metadata={"tags": [str(uuid4())], "problem_status": "open"},
            reason="Must refuse unknown tag",
        )
    with pytest.raises(JournalError, match="episode_revision_required"):
        run(
            root,
            "record.metadata",
            process=identity,
            record=problem["record"]["id"],
            expected_revision=1,
            metadata={"tags": [tag["id"]], "problem_status": "resolved"},
            reason="Cannot resolve through metadata",
        )
    assert run(root, "record.search", process=identity, view="open_problems")["matches"]


def test_external_registration_survives_cache_rebuild(tmp_path: Path) -> None:
    root = tmp_path / "home"
    setup(root)
    migrate(root)
    external_home = tmp_path / "external"
    identity, path = setup(external_home)
    run(root, "process.register", path=path.as_posix())
    storage.verify(root, home.storage_factory, rebuild=True)
    assert home.resolve_process(root, identity)["location"] == path.as_posix()
    assert run(root, "process.open", process=identity)["process"]["id"] == identity


def test_shared_creation_on_canonical_only_clone(tmp_path: Path) -> None:
    root = tmp_path / "first"
    identity, _ = setup(root)
    migrate(root)
    target = tmp_path / "clone"
    clone_files(root, target)
    # Git does not preserve empty .zara-home directories.
    (target / ".zara-home").rmdir()
    created = run(
        target,
        "record.create",
        scope="home",
        type_name="document",
        title="Shared",
        payload={"text": "Explicitly shared"},
        reason="Save",
        authority_source="Fictional owner: share this document",
    )
    assert created["record"]["scope"]["kind"] == "home"
    assert run(target, "record.search", process=identity)["matches"]


def test_git_exchange_refreshes_independent_processes(tmp_path: Path) -> None:
    root = tmp_path / "first"
    first_id, _ = setup(root)
    second_id = run(root, "process.create", title="Study", purpose="Fictional study")["process"][
        "id"
    ]
    migrate(root)
    (root / ".gitignore").write_text(".zara-cache/\n", encoding="utf-8")

    def git(path: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(path), *arguments],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )
        return result.stdout

    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "Fictional test")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "add", ".")
    git(root, "commit", "-m", "Initial fictional Home")
    other = tmp_path / "second"
    git(tmp_path, "clone", str(root), str(other))
    git(other, "config", "user.name", "Fictional test")
    git(other, "config", "user.email", "test@example.invalid")
    # Prime the second machine's index before either edit.
    assert not run(other, "record.search", process=first_id)["matches"]
    left = run(
        root,
        "record.create",
        process=first_id,
        type_name="document",
        title="Left",
        payload={"text": "alpha work"},
        reason="Fictional owner",
    )
    right = run(
        other,
        "record.create",
        process=second_id,
        type_name="document",
        title="Right",
        payload={"text": "beta study"},
        reason="Fictional owner",
    )
    for path in (root, other):
        git(path, "add", ".")
        git(path, "commit", "-m", "Independent process work")
    git(other, "pull", "--no-rebase", "--no-edit", "origin", "main")
    found = run(other, "record.search", process=first_id, query="alpha")
    assert [r["id"] for r in found["matches"]] == [left["record"]["id"]]
    assert (
        run(other, "record.search", process=second_id)["matches"][0]["id"] == right["record"]["id"]
    )
    assert ".zara-cache" not in git(other, "ls-files")


def test_metadata_preserves_accepted_decision_and_pinned_basis(tmp_path: Path) -> None:
    root = tmp_path / "home"
    identity, _ = setup(root)
    migrate(root)
    decision = run(
        root,
        "record.create",
        process=identity,
        type_name="decision",
        title="Decision",
        payload={"commitment": "Keep format", "rationale": "Known source", "applies_to": "Here"},
        reason="Owner proposal",
    )
    adopted = run(
        root,
        "record.adopt",
        process=identity,
        record=decision["record"]["id"],
        expected_revision=1,
        reason="Owner adoption",
        authority_source="Owner: accept",
    )
    result = run(
        root,
        "record.metadata",
        process=identity,
        record=decision["record"]["id"],
        expected_revision=2,
        metadata={"tags": []},
        reason="Metadata review",
    )
    assert result["record"]["state"] == "accepted" and result["record"]["revision"] == 3
    pinned = run(root, "source.read", process=identity, reference=adopted["reference"])
    assert pinned["record"]["revision"] == 2
    assert json.loads(pinned["payload_json"])["commitment"] == "Keep format"


def test_interrupted_write_and_post_commit_cache_failure_are_retry_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "home"
    identity, workspace = setup(root)
    migrate(root)
    operation = uuid4()
    fields = {
        "process": identity,
        "operation_id": operation,
        "type_name": "document",
        "title": "Exact bytes",
        "payload": {"text": "Retained source"},
        "reason": "Save",
    }
    replace = files._replace

    def before_head(path: Path, content: bytes) -> None:
        if path == workspace / ".zara-data/HEAD.json":
            raise OSError("fictional interruption before confirmation")
        replace(path, content)

    with monkeypatch.context() as patch:
        patch.setattr(files, "_replace", before_head)
        with pytest.raises(WorkspaceError, match="interruption"):
            run(root, "record.create", **fields)
    assert not run(root, "record.search", process=identity)["matches"]
    failed = False

    def after_head(path: Path, content: bytes) -> None:
        nonlocal failed
        if path == workspace / ".zara-cache/source.json" and not failed:
            failed = True
            raise OSError("fictional cache stamp failure")
        replace(path, content)

    with monkeypatch.context() as patch:
        patch.setattr(files, "_replace", after_head)
        saved = run(root, "record.create", **fields)
    repeated = run(root, "record.create", **fields)
    assert repeated["replayed"] and repeated["reference"] == saved["reference"]
    assert len(run(root, "record.search", process=identity)["matches"]) == 1
