"""Runtime admission cannot change saved process bindings or FTS semantics."""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tests.zaratustra.foundation.test_memory import note, ready
from zaratustra.foundation import (
    DataFilter,
    FoundationError,
    KnowledgeRef,
    MemoryRequirement,
    MemorySelector,
    RuntimeMemorySelector,
    runtime_selectors,
    search_expression,
    search_runtime_knowledge,
)


def test_runtime_selector_has_only_executable_fields_and_preserves_exact_values() -> None:
    definition_fields = set(MemorySelector.model_fields)
    runtime_fields = set(RuntimeMemorySelector.model_fields)
    assert definition_fields - runtime_fields == {"current_activity", "format_keys", "use_period"}
    assert runtime_fields - definition_fields == {"query_mode"}
    ref = KnowledgeRef(record_id=uuid4(), revision=3)
    runtime = RuntimeMemorySelector(
        empty=True,
        activity_ids=(uuid4(),),
        common=True,
        record_ids=(uuid4(),),
        topics=("observations",),
        query="Pacific/Chatham",
        full=True,
        context_role="required",
        kinds=("data_entry",),
        material_roles=("working",),
        format_refs=(ref,),
        data_filters=(DataFilter(field="value", operator="gt", value="1.25"),),
        date_from=date(2026, 1, 1),
        date_until=date(2026, 1, 3),
        time_from=datetime(2026, 1, 1, tzinfo=UTC),
        time_until=datetime(2026, 1, 3, tzinfo=UTC),
        data_statuses=("recorded",),
    )
    actual = runtime.to_selector()
    expected = MemorySelector.model_validate(
        {**runtime.model_dump(exclude={"query_mode"}), "query": '"Pacific/Chatham"'}
    )
    assert actual == expected
    assert actual.format_refs == (ref,)
    assert actual.current_activity is False and actual.format_keys == () and not actual.use_period
    assert runtime_selectors((runtime,)) == (actual,)


def test_saved_definition_keeps_canonical_aliases_and_expression_bytes() -> None:
    original = (
        '{"selectors":[{"use_period":true,"activity_ids":[],"current_activity":true,'
        '"common":false,"record_ids":[],"topics":[],"query":"alpha OR beta",'
        '"full":false,"context_role":null,"format_keys":["observation"]}],"required":true}'
    )
    saved = MemoryRequirement.model_validate_json(original)
    assert saved.model_dump_json() == original
    assert saved.selectors[0].query == "alpha OR beta"
    advanced = RuntimeMemorySelector(query="alpha OR beta", query_mode="fts5")
    assert advanced.to_selector().query == saved.selectors[0].query
    assert RuntimeMemorySelector(query="alpha OR beta").to_selector().query == '"alpha OR beta"'
    assert saved.model_dump_json() == original


@pytest.mark.parametrize(
    "field,value", [("current_activity", False), ("format_keys", []), ("use_period", False)]
)
def test_definition_aliases_are_rejected_even_when_false_or_empty(
    field: str, value: object
) -> None:
    with pytest.raises(ValidationError) as caught:
        RuntimeMemorySelector.model_validate({field: value})
    assert caught.value.errors()[0]["loc"] == (field,)
    assert caught.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize(
    "query",
    ["Pacific/Chatham", "2026-01-16", 'say "hello"', "label:value", "[token]", "Минск", "OR"],
)
def test_text_expression_quotes_the_whole_literal_without_interpreting_it(query: str) -> None:
    assert search_expression(query) == '"' + query.replace('"', '""') + '"'
    assert search_expression(query, "fts5") == query


@pytest.mark.parametrize("query", ["", " ", "\t\n"])
def test_blank_search_is_not_an_unrestricted_query(query: str) -> None:
    with pytest.raises(FoundationError, match="invalid_request"):
        search_expression(query)
    with pytest.raises(ValidationError):
        RuntimeMemorySelector(query=query)


@pytest.mark.parametrize(
    "arguments,field",
    [
        ({"date_from": "2026-02-02", "date_until": "2026-02-01"}, "date_until"),
        (
            {"time_from": "2026-02-02T00:00:00Z", "time_until": "2026-02-01T00:00:00Z"},
            "time_until",
        ),
        ({"query": "bad\x00text"}, "query"),
        ({"query": "bad\ud800text"}, "query"),
        ({"query_mode": "guessed"}, "query_mode"),
    ],
)
def test_invalid_runtime_values_have_the_exact_field(arguments: dict[str, str], field: str) -> None:
    with pytest.raises(ValidationError) as caught:
        RuntimeMemorySelector.model_validate(arguments)
    assert caught.value.errors()[0]["loc"] == (field,)


def test_equal_bounds_remain_a_valid_explicit_empty_period() -> None:
    result = RuntimeMemorySelector(
        date_from=date(2026, 1, 1),
        date_until=date(2026, 1, 1),
        time_from=datetime(2026, 1, 1, tzinfo=UTC),
        time_until=datetime(2026, 1, 1, tzinfo=UTC),
    ).to_selector()
    assert result.date_from == result.date_until
    assert result.time_from == result.time_until


def test_runtime_search_cursor_is_bound_to_original_query_and_mode(tmp_path: Path) -> None:
    root, space, owner, activity, *_ = ready(tmp_path)
    first = note(root, space, owner, "word", activity=activity)
    second = note(root, space, owner, "word", activity=activity)
    page = search_runtime_knowledge(root, owner, "word", limit=1)
    cursor = page["next_cursor"]
    assert isinstance(cursor, str)
    assert page["query_mode"] == "text"
    assert page["index_coverage"] == "retained UTF-8 source and knowledge revisions"
    following = search_runtime_knowledge(root, owner, "word", limit=1, cursor=cursor)
    assert following["next_cursor"] is None
    items = cast(list[dict[str, Any]], page["items"]) + cast(
        list[dict[str, Any]], following["items"]
    )
    ids = {item["record_id"] for item in items}
    assert ids == {str(first), str(second)}
    # Both modes compile to the exact same FTS expression, but are distinct
    # runtime requests; they cannot share a continuation accidentally.
    with pytest.raises(FoundationError, match="invalid_cursor"):
        search_runtime_knowledge(root, owner, '"word"', query_mode="fts5", cursor=cursor)
    with pytest.raises(FoundationError, match="invalid_cursor"):
        search_runtime_knowledge(root, owner, "other", cursor=cursor)
    malformed = cursor.split(".", 1)[0] + ".%%%"
    with pytest.raises(FoundationError, match="invalid_cursor"):
        search_runtime_knowledge(root, owner, "word", cursor=malformed)


@pytest.mark.parametrize(
    "text",
    ["Pacific/Chatham", "2026-01-16", 'say "hello"', "label:value", "[token]", "Минск", "OR"],
)
def test_runtime_text_search_executes_literal_punctuation_and_operator_words(
    tmp_path: Path, text: str
) -> None:
    root, space, owner, activity, *_ = ready(tmp_path)
    source = note(root, space, owner, text, activity=activity)
    page = search_runtime_knowledge(root, owner, text)
    assert [item["record_id"] for item in cast(list[dict[str, Any]], page["items"])] == [
        str(source)
    ]
    with pytest.raises(FoundationError, match="invalid_query"):
        search_runtime_knowledge(root, owner, "Pacific/Chatham", query_mode="fts5")


def test_punctuation_only_text_is_a_safe_index_query_not_an_absence_claim(tmp_path: Path) -> None:
    root, space, owner, activity, *_ = ready(tmp_path)
    original = note(root, space, owner, "/ - : []", activity=activity)
    for query in ("/", "-", '"', ":", "[]"):
        page = search_runtime_knowledge(root, owner, query)
        assert page["items"] == []
        assert page["index_coverage"] == "retained UTF-8 source and knowledge revisions"
    from zaratustra.foundation import SourceState, read_knowledge

    saved = read_knowledge(root, original, owner).state
    assert isinstance(saved, SourceState) and saved.content == b"/ - : []"
