"""Pure public staging checks share Core types without pretending to admit a final."""

from __future__ import annotations

import copy
import sqlite3
from typing import Any

import pytest
from zaratustra_core import CoreError, outcome_metadata_contract, validate_outcome_metadata


def change(body: Any = "Free body", **extra: Any) -> dict[str, Any]:
    return {"id": "record", "kind": "data", "key": "record", "body": body, **extra}


def progress(version: int = 1) -> dict[str, Any]:
    source = {"sequence": 2, "index": 0, "sha256": "a" * 64}
    value: dict[str, Any] = {
        "format": f"sleep-progress/v{version}",
        "work_id": "pending-work",
        "method_ref": {"id": "method", "revision": 1},
        "scope": "space",
        "source_high_watermark": 2,
        "enumeration_cursor": [2, 2147483647],
        "enumerated_source_refs": [source],
        "selected_source_refs": [source],
        "delivered_manifest_refs": [{"attempt_id": "pending-terminal", "sha256": "b" * 64}],
        "analysis_result_refs": [],
        "unexplored_coverage_position": {"unknown": "Retained doubt"},
        "applied_receipts": [],
        "proposed_changes": [],
        "remaining_refs": [source],
        "return_conditions": [],
        "consumed_resource": 0,
        "unresolved_calls": ["pending-action"],
        "stop_reason": "pending",
        "continuation": "Still pending actual terminal",
    }
    if version == 2:
        value.update(
            predecessor_ref={"id": "predecessor", "revision": 1, "role": "exact"},
            transition="same_window",
            range_start=[0, 0],
        )
    return value


def test_defaults_refs_and_expected_heads_follow_existing_shapes_without_mutation() -> None:
    metadata = {
        "outputs": [{"id": "result", "revision": 1, "role": "exact"}],
        "changes": [
            change(
                source_refs=[{"id": "source", "revision": 2}],
                schema_ref={"id": "schema", "revision": 1},
                artifact_refs=["a" * 64],
            )
        ],
        "expected_heads": {"record": -1},
    }
    before = copy.deepcopy(metadata)
    validate_outcome_metadata(metadata)
    assert metadata == before
    validate_outcome_metadata({})
    validate_outcome_metadata(
        {"state": "waiting", "wait": {"id": "wait", "question": "Exact question"}}
    )


@pytest.mark.parametrize("version", [1, 2])
def test_valid_pending_delivery_progress_needs_no_database_or_synthetic_terminal(
    monkeypatch: Any, version: int
) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("Pure shape validation must not open SQLite")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    metadata = {"state": "ready", "changes": [change(progress(version))]}
    original = copy.deepcopy(metadata)
    validate_outcome_metadata(metadata)
    assert metadata == original


@pytest.mark.parametrize(
    "body",
    [
        None,
        "Unrestricted memory prose",
        ["Any", {"meaning": "not checked"}],
        {
            "format": "sleep-analysis/v1",
            "sources": [{"sequence": 76, "index": 0, "sha256": "a" * 64}],
            "content": {"hypothesis": "Unproved", "alternatives": []},
        },
        {"format": "unrecognized-user-format", "scope": False},
        {"format": {"arbitrary": "object"}},
    ],
)
@pytest.mark.parametrize("kind", ["data", "memory", "method"])
def test_other_bodies_remain_free_and_receive_no_semantic_validation(body: Any, kind: str) -> None:
    metadata = {"changes": [change(body, kind=kind)]}
    original = copy.deepcopy(metadata)
    validate_outcome_metadata(metadata)
    assert metadata == original


@pytest.mark.parametrize(
    ("metadata", "field"),
    [
        (
            {"changes": [change(source_refs=[{"sequence": 76, "index": 0, "sha256": "a" * 64}])]},
            "changes.0.source_refs.0.id",
        ),
        ({"outputs": [{"sequence": 76, "index": 0, "sha256": "a" * 64}]}, "outputs.0.id"),
        (
            {"changes": [change(source_refs=[{"id": "source", "revision": True}])]},
            "changes.0.source_refs.0.revision",
        ),
        (
            {"changes": [change(schema_ref={"id": "schema", "revision": 0})]},
            "changes.0.schema_ref.revision",
        ),
        ({"changes": [change(artifact_refs=["bad-hash"])]}, "changes.0.artifact_refs.0"),
        ({"changes": [change(tombstone=1)]}, "changes.0.tombstone"),
        ({"expected_heads": {"record": True}}, "expected_heads.record"),
        ({"expected_heads": {"record": "1"}}, "expected_heads.record"),
        ({"expected_heads": {1: 2}}, "expected_heads.1.[key]"),
        ({"state": True}, "state"),
        ({"state": "failed"}, "state"),
        ({"wait": {"id": "wait"}}, "wait.question"),
        ({"text": "Final text belongs to actual settlement"}, "text"),
        ({"next_work": {}}, "next_work"),
    ],
)
def test_structural_errors_return_exact_paths(metadata: dict[str, Any], field: str) -> None:
    with pytest.raises(CoreError) as rejected:
        validate_outcome_metadata(metadata)
    assert rejected.value.code == "invalid_request"
    assert rejected.value.field == field


@pytest.mark.parametrize(
    ("version", "mutation", "field"),
    [
        (1, "missing_scope", "scope"),
        (1, "v2_extra", "predecessor_ref"),
        (2, "missing_predecessor", "predecessor_ref"),
        (2, "extra", "invented"),
        (1, "source_boolean", "selected_source_refs.0.sequence"),
        (2, "boundary_boolean", "range_start.0"),
    ],
)
def test_tagged_progress_uses_its_exact_versioned_model(
    version: int, mutation: str, field: str
) -> None:
    value = copy.deepcopy(progress(version))
    if mutation == "missing_scope":
        value.pop("scope")
    elif mutation == "v2_extra":
        value["predecessor_ref"] = {"id": "old", "revision": 1}
    elif mutation == "missing_predecessor":
        value.pop("predecessor_ref")
    elif mutation == "extra":
        value["invented"] = "extra"
    elif mutation == "source_boolean":
        value["selected_source_refs"][0] = value["selected_source_refs"][0] | {"sequence": True}
    else:
        value["range_start"][0] = False
    with pytest.raises(CoreError) as rejected:
        validate_outcome_metadata({"changes": [change("Other change"), change(value)]})
    assert rejected.value.code == "invalid_request"
    assert rejected.value.field == "changes.1.body." + field


def test_contract_exposes_same_ref_and_progress_versions_with_fresh_schema_objects() -> None:
    contract = outcome_metadata_contract()
    schema = contract["metadata_schema"]
    assert set(schema["properties"]) == {"state", "outputs", "changes", "wait", "expected_heads"}
    assert schema["properties"]["state"]["default"] == "completed"
    assert schema["additionalProperties"] is False
    assert set(schema["$defs"]["Ref"]["properties"]) == {"id", "revision", "role"}
    assert schema["$defs"]["Change"]["properties"]["source_refs"]["items"] == {
        "$ref": "#/$defs/Ref"
    }
    versions = contract["progress_schemas"]
    assert "scope" in versions["sleep-progress/v1"]["required"]
    assert "predecessor_ref" not in versions["sleep-progress/v1"]["properties"]
    assert "predecessor_ref" in versions["sleep-progress/v2"]["required"]
    contract["metadata_schema"]["properties"].clear()
    assert outcome_metadata_contract()["metadata_schema"]["properties"]


@pytest.mark.parametrize(
    "body", [1.5, b"not JSON text", {1: "non-string key"}, {"unsupported": {1, 2}}]
)
def test_free_body_still_obeys_existing_canonical_wire_types(body: Any) -> None:
    with pytest.raises(CoreError) as rejected:
        validate_outcome_metadata({"changes": [change(body)]})
    assert rejected.value.code == "invalid_request"
    assert rejected.value.field == "wire"


def test_free_canonical_unicode_integer_and_nested_body_bytes_are_preserved() -> None:
    from zaratustra_core import wire

    metadata = {
        "changes": [
            change(
                {
                    "text": "".join(
                        map(chr, [38634, 128578, 32, 101, 769, 32, 233, 32, 92, 34, 10])
                    ),
                    "integer": 10**50,
                    "nested": [True, False, None, -7, {"free": "meaning"}],
                }
            )
        ]
    }
    original = wire(metadata)
    validate_outcome_metadata(metadata)
    assert wire(metadata) == original
