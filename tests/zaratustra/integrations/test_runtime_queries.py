"""Advertised runtime selectors execute populated queries through installed adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_activity_structures import (
    _activate,
    _change,
    _structured_case,
)
from tests.zaratustra.foundation.test_memory import note, ready
from zaratustra.foundation import (
    ActivitySetupRequest,
    DataEntryState,
    FoundationError,
    KnowledgeRef,
    MemoryMetadata,
    apply_operation,
    create_entry,
    read_activity_setup,
    read_space,
    start_procedure,
)
from zaratustra.integrations import IntegrationRegistry, installed_integrations

OPERATIONS = (
    ("data", "query_entries"),
    ("memory", "catalog"),
    ("memory", "read_batch"),
    ("memory", "prepare_cache"),
)


def execute(
    registry: IntegrationRegistry, adapter: str, operation: str, arguments: dict[str, Any]
) -> dict[str, object]:
    return registry.execute(uuid4(), adapter, operation, arguments, contract_version=1).output


@pytest.mark.parametrize("adapter,operation", OPERATIONS)
def test_every_runtime_contract_advertises_the_same_executable_selector(
    tmp_path: Path, adapter: str, operation: str
) -> None:
    root, _, owner, *_ = ready(tmp_path)
    registry = installed_integrations(root, owner)
    schema = cast(dict[str, Any], registry.contract(adapter, operation)["schema"])
    selector = schema["$defs"]["RuntimeMemorySelector"]
    properties = selector["properties"]
    assert {"activity_ids", "format_refs", "date_from", "query_mode"}.issubset(properties)
    assert not {"current_activity", "format_keys", "use_period"}.intersection(properties)
    assert selector["additionalProperties"] is False
    mode_schema = properties["query_mode"]
    if "$ref" in mode_schema:
        mode_schema = schema["$defs"][mode_schema["$ref"].rsplit("/", 1)[1]]
    assert mode_schema["enum"] == ["text", "fts5"]


@pytest.mark.parametrize("adapter,operation", OPERATIONS)
@pytest.mark.parametrize(
    "alias,value",
    [("current_activity", True), ("format_keys", ["observation"]), ("use_period", True)],
)
def test_invalid_runtime_alias_reports_its_field_before_selection_effects(
    tmp_path: Path, adapter: str, operation: str, alias: str, value: object
) -> None:
    root, _, owner, *_ = ready(tmp_path)
    registry = installed_integrations(root, owner)
    before = read_space(root)
    with pytest.raises(FoundationError) as caught:
        execute(registry, adapter, operation, {"selectors": [{alias: value}]})
    assert caught.value.code == "invalid_request"
    assert f"selectors.0.{alias}" in caught.value.detail
    assert read_space(root) == before


def test_advertised_query_executes_exact_scope_format_and_date_on_real_entries(
    tmp_path: Path,
) -> None:
    case = _structured_case(tmp_path)
    root, space, owner, setup, activity, *_ = case
    first = _activate(case)
    # A second Activity has exactly the same definition-local key. Runtime never
    # consults an ambient current Activity to choose between these definitions.
    second_request = ActivitySetupRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        action="begin",
        setup_id=uuid4(),
        activity_id=uuid4(),
        title="Other fictional observations",
        text="Record another independently scoped stream",
        contract_version=2,
    )
    second_receipt = apply_operation(root, second_request, owner)
    second_case = (
        root,
        space,
        owner,
        second_request.setup_id,
        second_request.activity_id,
        second_request,
        second_receipt,
    )
    second = _activate(second_case)
    chosen: KnowledgeRef | None = None
    other: KnowledgeRef | None = None
    for described, scope, setup_id in (
        (first, activity, setup),
        (second, second_request.activity_id, second_request.setup_id),
    ):
        assert scope is not None and setup_id is not None
        format_ref = KnowledgeRef.model_validate(described["state"]["formats"]["observation"])
        created = create_entry(
            root,
            owner,
            DataEntryState(
                scope_activity_id=scope,
                format_ref=format_ref,
                role="event",
                values={"day": "2026-01-02", "value": "2.50"},
                bases=(read_activity_setup(root, setup_id, owner).state.sources[0],),
                memory=MemoryMetadata(
                    title="Fictional observation", activity_id=scope, topics=("measurement",)
                ),
            ),
        )
        ref = KnowledgeRef(record_id=UUID(str(created.result["record_id"])), revision=1)
        if scope == activity:
            chosen = ref
        else:
            other = ref
    assert chosen is not None and other is not None
    registry = installed_integrations(root, owner)
    selector = {
        "activity_ids": [str(activity)],
        "format_refs": [first["state"]["formats"]["observation"]],
        "date_from": "2026-01-02",
        "date_until": "2026-01-03",
        "data_filters": [{"field": "value", "operator": "ge", "value": "2.00"}],
        "data_statuses": ["recorded"],
        "topics": ["measurement"],
    }
    for adapter, operation in OPERATIONS:
        output = execute(registry, adapter, operation, {"selectors": [selector]})
        if operation == "catalog":
            assert [item["record_id"] for item in cast(list[dict[str, Any]], output["items"])] == [
                str(chosen.record_id)
            ]
        else:
            counted = execute(
                registry,
                "data",
                "aggregate_entries",
                {
                    "selection": {
                        "record_id": output["selection_id"],
                        "revision": output["revision"],
                    },
                    "operation": "count",
                },
            )
            assert cast(list[dict[str, Any]], counted["groups"])[0]["value"] == 1
            assert counted["bases"] == [chosen.model_dump(mode="json")]
    run = start_procedure(root, owner, activity, "observe", "old-format-before-structure-change")
    updated = _activate(_change(case))
    pinned = execute(
        registry,
        "data",
        "describe_structure",
        {
            "activity_id": str(activity),
            "work_id": run["work_id"],
        },
    )
    assert pinned["structure"] == first["structure"]
    assert pinned["structure"] != updated["structure"]
    assert (
        cast(dict[str, Any], pinned["state"])["formats"]["observation"]
        == selector["format_refs"][0]
    )
    old_entries = execute(registry, "data", "query_entries", {"selectors": [selector]})
    counted = execute(
        registry,
        "data",
        "aggregate_entries",
        {
            "selection": {
                "record_id": old_entries["selection_id"],
                "revision": old_entries["revision"],
            },
            "operation": "count",
        },
    )
    assert counted["bases"] == [chosen.model_dump(mode="json")]
    # Empty DataEntry coverage must not imply that a retained original is absent.
    empty = execute(
        registry,
        "data",
        "query_entries",
        {"selectors": [{**selector, "date_from": "2027-01-01", "date_until": "2027-01-02"}]},
    )
    assert empty["members"] == 0 and empty["content_complete"] is True
    assert empty["coverage"] == "retained authorized memory"
    original = read_activity_setup(root, setup, owner).state.sources[0]
    source_page = execute(
        registry,
        "memory",
        "catalog",
        {"selectors": [{"record_ids": [str(original.record_id)]}], "full": True},
    )
    assert any(
        item["record_id"] == str(original.record_id)
        for item in cast(list[dict[str, Any]], source_page["items"])
    )


@pytest.mark.parametrize(
    "text",
    ["Pacific/Chatham", "2026-01-16", 'say "hello"', "label:value", "[token]", "Минск", "OR"],
)
def test_literal_punctuation_and_operators_work_through_installed_memory(
    tmp_path: Path, text: str
) -> None:
    root, space, owner, activity, *_ = ready(tmp_path)
    source = note(root, space, owner, text, activity=activity)
    registry = installed_integrations(root, owner)
    output = execute(
        registry,
        "memory",
        "catalog",
        {"selectors": [{"activity_ids": [str(activity)], "query": text}]},
    )
    assert [item["record_id"] for item in cast(list[dict[str, Any]], output["items"])] == [
        str(source)
    ]


def test_advanced_fts_is_explicit_and_does_not_change_plain_text_semantics(tmp_path: Path) -> None:
    root, space, owner, activity, *_ = ready(tmp_path)
    alpha = note(root, space, owner, "alpha", activity=activity)
    beta = note(root, space, owner, "beta", activity=activity)
    registry = installed_integrations(root, owner)
    selector = {"activity_ids": [str(activity)], "query": "alpha OR beta"}
    plain = execute(registry, "memory", "catalog", {"selectors": [selector]})
    advanced = execute(
        registry, "memory", "catalog", {"selectors": [{**selector, "query_mode": "fts5"}]}
    )
    assert plain["items"] == []
    assert {item["record_id"] for item in cast(list[dict[str, Any]], advanced["items"])} == {
        str(alpha),
        str(beta),
    }
    before = read_space(root)
    with pytest.raises(FoundationError, match="invalid_query"):
        execute(
            registry,
            "memory",
            "catalog",
            {"selectors": [{"query": "Pacific/Chatham", "query_mode": "fts5"}]},
        )
    assert read_space(root) == before
