"""Finite, strict neutral formats. Valid text makes no semantic quality claim."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, NoReturn

from .shapes import Ref
from .types import CoreError


def value_references(value: Any, schema: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Validate the declaration/value, then visit only explicitly declared Ref slots."""
    validate_value(value, schema)

    def visit(item: Any, declaration: dict[str, Any]) -> Iterator[dict[str, Any]]:
        if item is None:
            return
        if declaration["type"] == "exact-ref":
            yield item
        elif declaration["type"] == "object":
            for field in declaration["fields"]:
                if field["name"] in item:
                    yield from visit(item[field["name"]], field)
        elif declaration["type"] == "list":
            for child in item:
                yield from visit(child, declaration["items"])

    yield from visit(value, schema)


TYPES = {
    "text",
    "boolean",
    "integer",
    "decimal-string",
    "date",
    "datetime",
    "enum",
    "exact-ref",
    "object",
    "list",
}


def invalid(path: str) -> NoReturn:
    raise CoreError("invalid_request", "schema." + path)


def validate_schema(schema: Any, path: str = "body") -> None:
    allowed = {
        "type",
        "required",
        "nullable",
        "min",
        "max",
        "min_length",
        "max_length",
        "fields",
        "items",
        "values",
        "name",
    }
    if (
        not isinstance(schema, dict)
        or set(schema) - allowed
        or type(schema.get("type")) is not str
        or schema["type"] not in TYPES
    ):
        invalid(path)
    for flag in ("required", "nullable"):
        if flag in schema and type(schema[flag]) is not bool:
            invalid(path + "." + flag)
    kind = schema["type"]
    if "name" in schema and (type(schema["name"]) is not str or not schema["name"]):
        invalid(path + ".name")
    for member, owner in (("fields", "object"), ("items", "list"), ("values", "enum")):
        if member in schema and kind != owner:
            invalid(path + "." + member)
    if kind == "object":
        fields = schema.get("fields")
        if not isinstance(fields, list):
            invalid(path + ".fields")
        names = []
        for field in fields:
            if (
                not isinstance(field, dict)
                or type(field.get("name")) is not str
                or not field["name"]
            ):
                invalid(path + ".fields")
            names.append(field["name"])
            validate_schema(field, path + "." + field["name"])
        if len(set(names)) != len(names):
            invalid(path + ".fields")
    if kind == "list":
        validate_schema(schema.get("items"), path + ".items")
    if kind == "enum":
        values = schema.get("values")
        if not isinstance(values, list) or any(type(v) is not str for v in values):
            invalid(path + ".values")
        if not values or len(set(values)) != len(values):
            invalid(path + ".values")
    for bound in ("min_length", "max_length"):
        if bound in schema and (
            type(schema[bound]) is not int
            or schema[bound] < 0
            or kind not in {"text", "date", "datetime", "enum", "decimal-string", "list"}
        ):
            invalid(path + "." + bound)
    for bound in ("min", "max"):
        if bound not in schema:
            continue
        limit = schema[bound]
        if kind == "integer":
            if type(limit) is not int:
                invalid(path + "." + bound)
        elif kind == "decimal-string":
            if type(limit) is not str or not re.fullmatch(r"[+-]?[0-9]+(?:[.][0-9]+)?", limit):
                invalid(path + "." + bound)
        else:
            invalid(path + "." + bound)
    for low, high in (("min_length", "max_length"), ("min", "max")):
        if low in schema and high in schema:
            lower, upper = schema[low], schema[high]
            if low == "min" and kind == "decimal-string":
                lower, upper = Decimal(lower), Decimal(upper)
            if lower > upper:
                invalid(path + "." + low)


def validate_value(value: Any, schema: dict[str, Any], path: str = "body") -> None:
    # Validate the whole declaration before any absent, empty or nullable value can short-circuit.
    validate_schema(schema, path)
    if value is None:
        if not schema.get("nullable", False):
            invalid(path)
        return
    kind = schema["type"]
    if kind in {"text", "date", "datetime", "enum", "decimal-string"}:
        if type(value) is not str:
            invalid(path)
    if kind == "boolean" and type(value) is not bool:
        invalid(path)
    if kind == "integer" and type(value) is not int:
        invalid(path)
    if kind == "decimal-string":
        if not re.fullmatch(r"[+-]?[0-9]+(?:[.][0-9]+)?", value):
            invalid(path)
        try:
            if not Decimal(value).is_finite():
                invalid(path)
        except InvalidOperation:
            invalid(path)
    if kind == "date":
        try:
            if date.fromisoformat(value).isoformat() != value:
                invalid(path)
        except ValueError:
            invalid(path)
    if kind == "datetime":
        try:
            if datetime.fromisoformat(value).utcoffset() is None:
                invalid(path)
        except ValueError:
            invalid(path)
    if kind == "enum":
        choices = schema.get("values")
        if (
            not isinstance(choices, list)
            or any(type(v) is not str for v in choices)
            or len(set(choices)) != len(choices)
            or value not in choices
        ):
            invalid(path)
    if kind == "exact-ref":
        if not isinstance(value, dict):
            invalid(path)
        Ref.model_validate(value)
    if kind == "object":
        fields = schema.get("fields")
        if not isinstance(value, dict) or not isinstance(fields, list):
            invalid(path)
        names = [field.get("name") for field in fields if isinstance(field, dict)]
        if (
            len(names) != len(fields)
            or any(type(n) is not str or not n for n in names)
            or len(set(names)) != len(names)
            or set(value) - set(names)
        ):
            invalid(path)
        for field in fields:
            name = field["name"]
            if name not in value:
                if field.get("required", False):
                    invalid(path + "." + name)
                # Check declared type even for absent fields.
                if field.get("type") not in TYPES:
                    invalid(path + "." + name)
            else:
                validate_value(value[name], field, path + "." + name)
    if kind == "list":
        if not isinstance(value, list) or not isinstance(schema.get("items"), dict):
            invalid(path)
        for n, item in enumerate(value):
            validate_value(item, schema["items"], path + "." + str(n))
    for bound in ("min_length", "max_length"):
        if bound in schema:
            limit = schema[bound]
            if type(limit) is not int or limit < 0 or not isinstance(value, str | list):
                invalid(path + "." + bound)
            if (bound == "min_length" and len(value) < limit) or (
                bound == "max_length" and len(value) > limit
            ):
                invalid(path)
    for bound in ("min", "max"):
        if bound in schema:
            limit = schema[bound]
            if kind == "integer" and type(limit) is not int:
                invalid(path + "." + bound)
            if kind == "decimal-string":
                if type(limit) is not str:
                    invalid(path + "." + bound)
                validate_value(limit, {"type": "decimal-string"}, path + "." + bound)
                observed, threshold = Decimal(value), Decimal(limit)
            elif kind == "integer":
                observed, threshold = value, limit
            else:
                invalid(path + "." + bound)
                return
            if (bound == "min" and observed < threshold) or (
                bound == "max" and observed > threshold
            ):
                invalid(path)
