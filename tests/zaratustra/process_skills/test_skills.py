"""Pinned behavior, scope and change boundaries over the real common API."""

import json
from importlib import metadata
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from zaratustra.commands import Command, Context, ContextGuard, execute
from zaratustra.home import HomeError, init_home
from zaratustra.journal import DEFAULT_REGISTRY, JournalError, Reference, read_export
from zaratustra.process_skills import Catalog, Dependency, Skill


def run(context: Context, action: str, **fields: Any) -> dict[str, Any]:
    return execute(
        context,
        Command.model_validate({"action": action, **fields}),
        source_ref="fictional-owner-request",
    )


@pytest.fixture
def contexts(tmp_path: Path) -> tuple[Context, Context]:
    root = tmp_path / "home"
    root.mkdir()
    init_home(root)
    base = Context(home=root.as_posix())
    rows = [
        run(base, "process.create", title=name, purpose="Fictional skill check")["process"]
        for name in ("A", "B")
    ]
    return tuple(
        Context(home=base.home, workspace=r["location"], process_id=UUID(r["id"])) for r in rows
    )  # type: ignore[return-value]


def saved(context: Context, *, shared: bool = True, **fields: Any) -> dict[str, Any]:
    payload = {
        "name": "state-overview",
        "description": "Inspect journal state",
        "body": "Read episodes and list unresolved work.",
        **fields,
    }
    return run(
        context,
        "record.create",
        type_name="skill",
        title="State overview",
        payload=payload,
        scope="home" if shared else "process",
        reason="Owner chose method",
        authority_source="Save as shared" if shared else None,
    )


def bind(context: Context, reference: Any, **fields: Any) -> dict[str, Any]:
    revision = run(context, "context.read")["configuration_revision"]
    return run(
        context,
        "skill.bind",
        **{
            "slot": "overview",
            "reference": reference,
            "expected_configuration_revision": revision,
            "reason": "Apply chosen version",
            **fields,
        },
    )


def test_versions_apply_to_one_process_and_preserve_history(
    contexts: tuple[Context, Context],
) -> None:
    a, b = contexts
    v1 = saved(a)
    bind(a, v1["reference"])
    bind(b, v1["reference"])
    v2 = run(
        a,
        "record.revise",
        scope="home",
        record=v1["record"]["id"],
        expected_revision=1,
        payload={
            "name": "state-overview",
            "description": "Inspect journal state",
            "body": "Read the evidence and lead with unfinished work.",
        },
        reason="Previously overlooked unfinished work",
        authority_source="Improve shared skill",
    )
    assert run(a, "context.read")["skills"][0]["reference"]["revision"] == 1
    assert run(b, "context.read")["skills"][0]["reference"]["revision"] == 1
    bind(a, v2["reference"])
    assert "unfinished" in run(a, "skill.load", slot="overview")["markdown"]
    assert run(b, "skill.load", slot="overview")["reference"] == v1["reference"]
    old_context = run(a, "context.read", loaded_slots=["overview"])
    bind(a, v1["reference"])
    fresh = run(a, "context.read", loaded_slots=["overview"])
    assert fresh["stamp"] != old_context["stamp"]
    assert fresh["skills"][0]["reference"] == v1["reference"]
    run(a, "skill.unbind", slot="overview", expected_configuration_revision=3, reason="Disable")
    assert run(a, "context.read")["skills"] == []
    assert run(a, "record.history", record=fresh["configuration_record"])["total"] == 4
    assert run(a, "record.history", scope="home", record=v1["record"]["id"])["total"] == 2


def test_local_replacement_is_complete_and_origin_is_versioned(
    contexts: tuple[Context, Context],
) -> None:
    a, b = contexts
    source = saved(a)
    bind(a, source["reference"])
    bind(b, source["reference"])
    local = saved(
        b,
        shared=False,
        name="local-overview",
        body="Show questions first.",
        derived_from=source["reference"],
    )
    with pytest.raises(JournalError, match="ambiguous_replacement"):
        bind(b, local["reference"], slot="another-overview")
    bind(b, local["reference"])
    assert len(run(b, "context.read")["skills"]) == 1
    assert "questions" in run(b, "skill.load", slot="overview")["markdown"]
    assert run(a, "skill.load", slot="overview")["reference"] == source["reference"]
    assert run(b, "record.read", record=local["record"]["id"])["record"]["links"] == [
        source["reference"]
    ]
    with pytest.raises(JournalError, match="scope_unavailable"):
        bind(a, local["reference"])
    independent = saved(b, shared=False, name="writing-style", body="Use short paragraphs.")
    bind(b, independent["reference"], slot="writing")
    assert len(run(b, "context.read")["skills"]) == 2


def test_prepared_context_refuses_changed_binding_and_sessions_are_local(
    contexts: tuple[Context, Context],
) -> None:
    a, b = contexts
    source = saved(a)
    before = run(a, "context.read")
    assert a.process_id is not None
    guard = ContextGuard(process_id=a.process_id, stamp=before["stamp"])
    bind(a, source["reference"])
    with pytest.raises(HomeError, match="context_changed"):
        execute(
            a,
            Command(action="material.save", title="Old action", text="old"),
            source_ref="old turn",
            guard=guard,
        )
    in_b = execute(
        a,
        Command(action="context.read"),
        source_ref="another session",
        session_process=b.process_id,
    )
    assert in_b["process"]["id"] == str(b.process_id)
    assert in_b["skills"] == []
    assert run(a, "context.read")["process"]["id"] == str(a.process_id)
    assert run(a, "process.open")["material_count"] == 1  # binding only; no stale material


def test_exact_retry_and_conflicting_binding_writes(contexts: tuple[Context, Context]) -> None:
    a, _ = contexts
    skill = saved(a)
    op = uuid4()
    first = bind(a, skill["reference"], operation_id=op)
    retry = bind(a, skill["reference"], operation_id=op, expected_configuration_revision=0)
    assert retry["replayed"] and retry["record"] == first["record"]
    with pytest.raises(JournalError, match="revision_conflict"):
        bind(a, skill["reference"], expected_configuration_revision=0)
    with pytest.raises(JournalError, match="operation_conflict"):
        bind(
            a,
            skill["reference"],
            operation_id=op,
            expected_configuration_revision=0,
            reason="Changed",
        )
    config = run(a, "context.read")
    with pytest.raises(JournalError, match="managed_type"):
        run(
            a,
            "record.revise",
            record=config["configuration_record"],
            expected_revision=1,
            payload={"bindings": []},
            reason="Bypass",
        )
    with pytest.raises(JournalError, match="managed_type"):
        run(
            a,
            "record.create",
            type_name="skill_bindings",
            title="Bypass",
            payload={"bindings": []},
            reason="Bypass",
        )


def test_settings_and_missing_dependencies_do_not_fake_readiness(
    contexts: tuple[Context, Context],
) -> None:
    a, _ = contexts
    skill = saved(
        a,
        parameters={
            "format": {
                "kind": "string",
                "description": "Summary format",
                "required": True,
                "choices": ["short", "long"],
            }
        },
    )
    row = run(a, "skill.catalog")["skills"][0]
    assert {r["status"] for r in row["readiness"]["reasons"]} == {
        "needs_configuration",
        "not_connected",
    }
    with pytest.raises(JournalError, match="needs_configuration"):
        bind(a, skill["reference"])
    with pytest.raises(JournalError, match="invalid_setting"):
        bind(a, skill["reference"], settings={"format": "unknown"})
    bind(a, skill["reference"], settings={"format": "short"})
    assert run(a, "skill.catalog")["skills"][0]["readiness"]["ready_by_configuration"]
    missing = saved(
        a, name="missing-operation", dependencies=[{"kind": "command", "name": "imaginary.send"}]
    )
    with pytest.raises(JournalError, match="not_found"):
        bind(a, missing["reference"], slot="other")
    optional = saved(
        a,
        name="optional-operation",
        dependencies=[{"kind": "command", "name": "imaginary.send", "required": False}],
    )
    bind(a, optional["reference"], slot="optional")
    assert run(a, "context.read")["skills"][1]["readiness"]["ready_by_configuration"]


def test_catalog_unknown_is_not_absent_and_resource_versions_are_exact() -> None:
    def unavailable(name: str) -> str:
        raise OSError("unreadable")

    catalog = Catalog(("record.read",), DEFAULT_REGISTRY, unavailable)
    dependency = Dependency(kind="resource", name="sample", version="1")
    assert catalog.check(dependency)["status"] == "unknown"
    assert catalog.inventory()["resources"][0]["status"] == "unknown"

    def missing(name: str) -> str:
        raise metadata.PackageNotFoundError(name)

    assert Catalog((), DEFAULT_REGISTRY, missing).check(dependency)["status"] == "not_found"
    assert (
        Catalog((), DEFAULT_REGISTRY, lambda name: "2").check(dependency)["status"]
        == "incompatible_version"
    )
    with pytest.raises(ValidationError, match="exact version"):
        Dependency(kind="resource", name="sample")


def test_managed_context_progressive_loading_and_export_scope(
    contexts: tuple[Context, Context], tmp_path: Path
) -> None:
    a, b = contexts
    episode = run(
        a,
        "record.create",
        type_name="episode",
        title="Local ground",
        payload={"situation": "Private fictional work", "outcome": "Improve overview"},
        reason="Log",
    )
    skill = run(
        a,
        "record.create",
        type_name="skill",
        scope="home",
        title="Shared overview",
        payload={
            "name": "state-overview",
            "description": "Inspect journal",
            "body": "Read episodes.",
        },
        links=[episode["reference"]],
        reason="Shared improvement",
        authority_source="Share method only",
    )
    bind(b, skill["reference"])
    context = run(b, "context.read")
    assert "markdown" not in context["skills"][0]
    assert "Private fictional work" not in json.dumps(context)
    loaded = run(b, "context.read", loaded_slots=["overview"])
    assert "Read episodes" in loaded["skills"][0]["markdown"]
    assert loaded["stamp"] == context["stamp"]
    assert run(b, "source.read", reference=episode["reference"])["status"] == "scope_unavailable"
    destination = tmp_path / "skills.zip"
    run(
        b,
        "records.export",
        records=[context["configuration_record"]],
        export_shared=True,
        path=str(destination),
    )
    exported = read_export(destination, reference=Reference.model_validate(skill["reference"]))
    assert exported["record"]["payload"]["body"] == "Read episodes."
    assert (
        read_export(destination, reference=Reference.model_validate(episode["reference"]))["status"]
        != "available"
    )


def test_markdown_view_has_agent_skills_frontmatter() -> None:
    skill = Skill(
        name="state-overview", description="A colon: and a quote " + chr(34), body="## Read first"
    )
    lines = skill.markdown().splitlines()
    assert lines[0] == lines[3] == "---"
    assert json.loads(lines[1].removeprefix("name: ")) == skill.name
    assert json.loads(lines[2].removeprefix("description: ")) == skill.description
    assert "## Read first" in lines


def test_committed_retry_survives_changed_dependency_readiness(
    contexts: tuple[Context, Context], monkeypatch: pytest.MonkeyPatch
) -> None:
    a, _ = contexts
    skill = saved(a, dependencies=[{"kind": "command", "name": "record.read"}])
    op = uuid4()
    original = bind(a, skill["reference"], operation_id=op)
    monkeypatch.setattr(
        Catalog,
        "check",
        lambda self, dep: {"dependency": dep.model_dump(mode="json"), "status": "unknown"},
    )
    retry = bind(a, skill["reference"], operation_id=op, expected_configuration_revision=0)
    assert retry["replayed"] and retry["record"] == original["record"]
    with pytest.raises(JournalError, match="skill_not_ready"):
        bind(a, skill["reference"])
