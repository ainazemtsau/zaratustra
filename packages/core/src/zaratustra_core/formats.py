"""Finite, strict neutral formats. Valid text makes no semantic quality claim."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, NoReturn

from .shapes import Ref
from .types import CoreError

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


def validate_value(value: Any, schema: dict[str, Any], path: str = "body") -> None:
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
    if not isinstance(schema, dict) or set(schema) - allowed or schema.get("type") not in TYPES:
        invalid(path)
    for flag in ("required", "nullable"):
        if flag in schema and type(schema[flag]) is not bool:
            invalid(path + "." + flag)
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
