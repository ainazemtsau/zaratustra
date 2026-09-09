"""Core-backed checks of authority, isolation, freshness and read-only consistency."""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tools.probe_capabilities import (
    CapabilitiesTrial,
    FixtureReader,
    confirm,
    installed,
    process_query,
)
from tools.probe_m1 import query_for, work_at
from tools.probe_packs import proposed, reference, registry
from zaratustra.core import (
    ArtifactReference,
    LocalAuthorization,
    ProcessMetadata,
    ProcessQuery,
    apply_mutation,
    migrate_workspace,
    read_artifact,
    read_handoffs,
    read_records,
)
from zaratustra.process_packs import (
    CapabilitySelection,
    ContextRequirements,
    Notice,
    PackError,
    PackRegistry,
    read_capabilities,
)


@pytest.fixture
def trial(tmp_path: Path) -> CapabilitiesTrial:
    value = CapabilitiesTrial(tmp_path / "workspace", tmp_path / "events")
    identity = value.bootstrap()
    migrate_workspace(value.path, target_version=7)
    value.execute(value.bind(identity, reference(), registry(reference())))
    value.observation(identity)
    return value


def footprint(path: Path) -> tuple[tuple[str, bytes | None], ...]:
    return tuple(
        (item.relative_to(path).as_posix(), item.read_bytes() if item.is_file() else None)
        for item in sorted(path.rglob("*"))
    )


def read(trial: CapabilitiesTrial, **options: Any) -> dict[str, Any]:
    identity = work_at(trial.path).id
    query = options.pop("query", process_query(trial.path, identity, (identity,), identity))
    caller = options.pop("caller", confirm(trial.path, query))
    registration = options.pop("registry", installed())
    before = footprint(trial.path)
    result = read_capabilities(trial.path, query, caller, registration, **options)
    assert footprint(trial.path) == before
    decoded: dict[str, Any] = json.loads(result.output)
    return decoded


def test_seven_answers_share_revision_and_sources_without_content(trial: CapabilitiesTrial) -> None:
    value = read(trial)
    state = read_records(trial.path)
    assert value["envelope"]["state_revision"] == state.state_revision
    assert set(value["answers"]) == set(CapabilitySelection.model_fields)
    assert value["answers"]["available_works"]["value"][0] == work_at(trial.path).model_dump(
        mode="json"
    )
    assert value["answers"]["context_requirements"]["value"]["context"] == {
        "state": "unavailable",
        "code": "not_requested",
    }
    assert "content_base64" not in json.dumps(value)


def test_empty_scope_has_no_hidden_counts_or_work_metadata(trial: CapabilitiesTrial) -> None:
    identity = work_at(trial.path).id
    value = read(trial, query=process_query(trial.path, identity, ()))
    assert str(identity) not in json.dumps(value)
    assert value["envelope"]["visible_work_ids"] == []
    for name in ("available_works", "blocked_works", "open_decisions", "recent_important_results"):
        assert value["answers"][name] == dict(state="empty", value=[], count=0)


@pytest.mark.parametrize(
    "mode",
    ["none", "query_changed", "revoked", "stale", "foreign", "foreign_visible", "path_changed"],
)
def test_denied_or_stale_query_never_dispatches_or_discloses(
    trial: CapabilitiesTrial, mode: str
) -> None:
    identity = work_at(trial.path).id
    query = process_query(trial.path, identity, (identity,), identity)
    caller: LocalAuthorization | None = confirm(trial.path, query)
    if mode == "none":
        caller = None
    elif mode == "query_changed":
        query = query.model_copy(update=dict(max_bytes=10000))
    elif mode == "foreign":
        query = query.model_copy(update=dict(process_id=uuid4()))
        caller = confirm(trial.path, query)
    elif mode == "foreign_visible":
        query = query.model_copy(update=dict(visible_work_ids=(identity, uuid4())))
        caller = confirm(trial.path, query)
    elif mode == "path_changed":
        assert caller is not None
        caller = replace(
            caller, confirmation=caller.confirmation.model_copy(update=dict(workspace_path="other"))
        )
    elif mode in ("revoked", "stale"):
        trial.execute(
            trial.request(
                identity,
                "revoke_work" if mode == "revoked" else "set_work_requirements",
                **({} if mode == "revoked" else dict(requirements=("new",))),
            )
        )

    class NeverCalled(FixtureReader):
        def describe(self, metadata: ProcessMetadata) -> CapabilitySelection:
            raise AssertionError("Unauthorized adapter execution")

    value = read(trial, query=query, caller=caller, registry=installed(NeverCalled()))
    assert "envelope" not in value
    expected = (
        dict(state="unavailable", code="conflict")
        if mode == "stale"
        else dict(state="denied", code="permission_denied")
    )
    assert all(answer == expected for answer in value["answers"].values())
    assert str(identity) not in json.dumps(value)


@pytest.mark.parametrize(
    "mode", ["missing", "other_version", "incompatible", "no_reader", "unsupported"]
)
def test_unavailable_is_never_a_supported_empty_answer(trial: CapabilitiesTrial, mode: str) -> None:
    class Unsupported(FixtureReader):
        def describe(self, metadata: ProcessMetadata) -> CapabilitySelection:
            return CapabilitySelection()

    selected = {
        "missing": PackRegistry(),
        "other_version": registry(reference("2.0.0")),
        "incompatible": registry(reference(state_version=2)),
        "no_reader": registry(reference()),
        "unsupported": installed(Unsupported()),
    }[mode]
    value = read(trial, registry=selected)
    assert all(
        answer["state"] == "unavailable" and "count" not in answer and "value" not in answer
        for answer in value["answers"].values()
    )


@pytest.mark.parametrize(
    "mode",
    [
        "foreign_notice",
        "foreign_result",
        "overlap",
        "missing_active",
        "foreign_requirement",
        "duplicate_available",
    ],
)
def test_adapter_cannot_fabricate_reference_membership_or_partition(
    trial: CapabilitiesTrial, mode: str
) -> None:
    class Invalid(FixtureReader):
        def describe(self, metadata: ProcessMetadata) -> CapabilitySelection:
            selection = super().describe(metadata)
            identity = metadata.works[0].id
            variants: dict[str, dict[str, Any]] = {
                "foreign_notice": dict(
                    open_decisions=(Notice(key="fake", work_id=uuid4(), text="bad"),)
                ),
                "foreign_result": dict(recent_important_results=(uuid4(),)),
                "overlap": dict(blocked_works=(Notice(key="fake", work_id=identity, text="bad"),)),
                "missing_active": dict(available_works=()),
                "foreign_requirement": dict(
                    context_requirements=ContextRequirements(
                        references=(
                            ArtifactReference(
                                artifact_id=uuid4(), version_id=uuid4(), sha256="a" * 64
                            ),
                        )
                    )
                ),
                "duplicate_available": dict(available_works=(identity, identity)),
            }
            return selection.model_copy(update=variants[mode])

    value = read(trial, registry=installed(Invalid()))
    assert all(
        answer == dict(state="unavailable", code="invalid_read_response")
        for answer in value["answers"].values()
    )


def test_selection_and_context_query_scope_are_validated(trial: CapabilitiesTrial) -> None:
    identity = work_at(trial.path).id
    query = process_query(trial.path, identity, (identity,), identity)
    for changes in (dict(visible_work_ids=(identity, identity)), dict(selected_work_id=uuid4())):
        with pytest.raises(ValidationError):
            ProcessQuery.model_validate(query.model_dump() | changes)
    context = query_for(trial.path, identity).model_copy(update=dict(process_id=uuid4()))
    value = read(trial, context_query=context, context_caller=confirm(trial.path, context))
    assert value["answers"]["context_requirements"]["value"]["context"] == dict(
        state="denied", code="scope"
    )


def test_metadata_authorization_cannot_authorize_context_or_mutation(
    trial: CapabilitiesTrial,
) -> None:
    identity = work_at(trial.path).id
    query = process_query(trial.path, identity, (identity,), identity)
    context = query_for(trial.path, identity)
    caller = confirm(trial.path, query)
    value = read(trial, query=query, caller=caller, context_query=context, context_caller=caller)
    assert value["answers"]["context_requirements"]["value"]["context"] == dict(
        state="denied", code="permission_denied"
    )
    before = footprint(trial.path)
    with pytest.raises(Exception, match="permission_denied"):
        apply_mutation(trial.path, trial.request(identity, "revoke_work"), caller)
    assert footprint(trial.path) == before


def test_materialized_selected_context_matches_real_open_work(trial: CapabilitiesTrial) -> None:
    from zaratustra.core import open_work

    context = query_for(trial.path, work_at(trial.path).id)
    caller = confirm(trial.path, context)
    expected = json.loads(open_work(trial.path, context, caller).output)
    value = read(trial, context_query=context, context_caller=caller)
    content = value["answers"]["context_requirements"]["value"]["context"]
    assert content == dict(state="ok", value=expected)
    assert expected["context"]["envelope"]["state_revision"] == value["envelope"]["state_revision"]


def test_exact_required_reference_and_changed_request(trial: CapabilitiesTrial) -> None:
    ref = read_handoffs(trial.path)[0].handoff.result
    context = query_for(trial.path, work_at(trial.path).id)
    value = read(
        trial,
        registry=installed(FixtureReader((ref,))),
        context_query=context,
        context_caller=confirm(trial.path, context),
    )
    assert value["answers"]["context_requirements"]["value"]["context"] == dict(
        state="unavailable", code="requirements_changed"
    )
    context = context.model_copy(update=dict(references=(ref,)))
    value = read(
        trial,
        registry=installed(FixtureReader((ref,))),
        context_query=context,
        context_caller=confirm(trial.path, context),
    )
    assert value["answers"]["context_requirements"]["value"]["context"]["state"] == "ok"


def test_foreign_context_ref_is_not_read_even_with_exact_confirmation(
    trial: CapabilitiesTrial,
) -> None:
    foreign = ArtifactReference(artifact_id=uuid4(), version_id=uuid4(), sha256="a" * 64)
    context = query_for(trial.path, work_at(trial.path).id).model_copy(
        update=dict(references=(foreign,))
    )
    value = read(trial, context_query=context, context_caller=confirm(trial.path, context))
    content = value["answers"]["context_requirements"]["value"]["context"]
    assert content["state"] == "denied" and content["code"] == "scope" and "value" not in content
    assert str(foreign.artifact_id) not in json.dumps(value)


def test_unavailable_bytes_keep_requirements_but_never_partial_context(
    trial: CapabilitiesTrial,
) -> None:
    ref = read_handoffs(trial.path)[0].handoff.result
    descriptor = read_artifact(trial.path, ref.artifact_id, ref.version_id).version
    source = trial.path / descriptor.relative_path
    retained = source.with_suffix(".retained")
    source.rename(retained)
    try:
        context = query_for(trial.path, work_at(trial.path).id)
        value = read(trial, context_query=context, context_caller=confirm(trial.path, context))
        requirements = value["answers"]["context_requirements"]
        assert requirements["state"] == "ok"
        assert requirements["value"]["context"] == dict(
            state="unavailable", code="context_unavailable"
        )
        assert "content_base64" not in json.dumps(value)
    finally:
        retained.rename(source)


def test_late_context_byte_loss_refuses_whole_response(trial: CapabilitiesTrial) -> None:
    ref = read_handoffs(trial.path)[0].handoff.result
    source = (
        trial.path
        / read_artifact(trial.path, ref.artifact_id, ref.version_id).version.relative_path
    )
    retained = source.with_suffix(".retained")

    class LosingContent(FixtureReader):
        def describe(self, metadata: ProcessMetadata) -> CapabilitySelection:
            source.rename(retained)
            return super().describe(metadata)

    context = query_for(trial.path, work_at(trial.path).id)
    query = process_query(trial.path, context.work_id, (context.work_id,), context.work_id)
    try:
        response = read_capabilities(
            trial.path,
            query,
            confirm(trial.path, query),
            installed(LosingContent()),
            context_query=context,
            context_caller=confirm(trial.path, context),
        )
        value = json.loads(response.output)
        assert all(
            answer == dict(state="unavailable", code="dependency_changed")
            for answer in value["answers"].values()
        )
        assert "content_base64" not in response.output.decode()
    finally:
        if retained.exists():
            retained.rename(source)


def test_hidden_completed_work_not_disclosed_but_exact_inherited_context_is_legal(
    trial: CapabilitiesTrial,
) -> None:
    first = work_at(trial.path).id
    request = proposed(trial.path, first, registry(reference()))
    trial.execute(request)
    assert request.submission is not None
    next_id = request.submission.next_work.work_id
    query = process_query(trial.path, next_id, (next_id,), next_id)
    value = read(trial, query=query)
    assert str(first) not in json.dumps(value)
    assert str(request.operation_id) not in json.dumps(value)
    assert value["answers"]["recent_important_results"] == dict(state="empty", value=[], count=0)
    context = query_for(trial.path, next_id)
    with_context = read(
        trial, query=query, context_query=context, context_caller=confirm(trial.path, context)
    )
    package = with_context["answers"]["context_requirements"]["value"]["context"]
    assert package["state"] == "ok"
    assert package["value"]["context"]["envelope"]["work_id"] == str(next_id)
    assert f"result:{request.operation_id}" in {
        row["locator"] for row in package["value"]["context"]["sources"]
    }
    all_value = read(trial, query=process_query(trial.path, next_id, (first, next_id), next_id))
    header = all_value["answers"]["recent_important_results"]["value"][0]
    assert header == dict(
        id=str(request.operation_id),
        work_id=str(first),
        state_revision=read_records(trial.path).state_revision,
    )


def test_byte_budget_returns_no_partial_metadata(trial: CapabilitiesTrial) -> None:
    identity = work_at(trial.path).id
    query = process_query(trial.path, identity, (identity,), identity).model_copy(
        update=dict(max_bytes=1)
    )
    value = read(trial, query=query)
    assert all(
        answer == dict(state="unavailable", code="budget_exceeded")
        for answer in value["answers"].values()
    )
    assert "envelope" not in value


def test_reader_identity_cannot_replace_registered_adapter() -> None:
    registration = installed().registrations[0]
    selected = PackRegistry((registration,))
    assert selected.register(registration) is selected
    with pytest.raises(PackError, match="registration_collision"):
        selected.register(replace(registration, reader=FixtureReader()))


def test_managed_writer_cannot_interleave_a_seven_answer_read(trial: CapabilitiesTrial) -> None:
    identity = work_at(trial.path).id
    query = process_query(trial.path, identity, (identity,), identity)
    request = trial.request(identity, "revoke_work")
    caller = confirm(trial.path, request)
    started, finished = threading.Event(), threading.Event()
    failures: list[BaseException] = []

    def writer() -> None:
        started.set()
        try:
            apply_mutation(trial.path, request, caller)
        except BaseException as error:
            failures.append(error)
        finally:
            finished.set()

    thread = threading.Thread(target=writer)

    class Interleaved(FixtureReader):
        def describe(self, metadata: ProcessMetadata) -> CapabilitySelection:
            thread.start()
            assert started.wait(1)
            assert not finished.wait(0.05)
            return super().describe(metadata)

    response = read_capabilities(
        trial.path, query, confirm(trial.path, query), installed(Interleaved())
    )
    thread.join(3)
    assert finished.is_set() and not failures
    assert json.loads(response.output)["envelope"]["state_revision"] == query.expected_revision
    assert read_records(trial.path).state_revision == query.expected_revision + 1
    assert work_at(trial.path).authority_scope == "none"
