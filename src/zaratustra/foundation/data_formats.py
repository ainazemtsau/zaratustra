"""The finite declarative data language, independent of models and storage effects."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

from pydantic import JsonValue, ValidationError

from .models import DataField, DataFormatState, DataReference
from .storage import FoundationError


def decimal_value(value: object) -> Decimal:
    if not isinstance(value, str):
        raise FoundationError("invalid_data", "Decimal values must be decimal strings")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise FoundationError("invalid_data", "Invalid decimal string") from error
    if not number.is_finite():
        raise FoundationError("invalid_data", "Decimal must be finite")
    if len(number.as_tuple().digits) > 1024 or abs(int(number.as_tuple().exponent)) > 1000:
        raise FoundationError("invalid_data", "Decimal exceeds the supported finite representation")
    return number


def canonical_decimal(value: str, precision: int | None) -> str:
    number = decimal_value(value)
    if precision is not None:
        with localcontext() as context:
            context.prec = max(
                28, len(number.as_tuple().digits) + abs(number.adjusted()) + precision + 2
            )
            rounded = number.quantize(Decimal(1).scaleb(-precision))
        if rounded != number:
            raise FoundationError("invalid_data", "Value exceeds the declared decimal precision")
        return format(abs(rounded) if rounded == 0 else rounded, f".{precision}f")
    text = format(abs(number) if number == 0 else number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def validate_field(field: DataField, value: JsonValue) -> JsonValue:
    if value is None:
        if field.unknown_allowed:
            return None
        raise FoundationError("invalid_data", f"{field.key}: unknown is not allowed")
    kind = field.type
    valid = True
    if kind == "text":
        valid = isinstance(value, str)
    elif kind == "boolean":
        valid = isinstance(value, bool)
    elif kind == "integer":
        valid = type(value) is int
    elif kind == "decimal":
        valid = isinstance(value, str)
        if valid:
            value = canonical_decimal(str(value), field.precision)
    elif kind == "date":
        try:
            valid = isinstance(value, str) and date.fromisoformat(value).isoformat() == value
        except ValueError:
            valid = False
    elif kind == "datetime":
        try:
            parsed = datetime.fromisoformat(str(value))
            valid = isinstance(value, str) and parsed.utcoffset() is not None
            if valid:
                value = parsed.isoformat()
        except ValueError:
            valid = False
    elif kind == "enum":
        valid = isinstance(value, str) and value in field.choices
    elif kind == "ref":
        try:
            reference = DataReference.model_validate(value)
            value = reference.model_dump(mode="json")
        except ValidationError:
            valid = False
    elif kind == "object":
        valid = isinstance(value, dict)
        if isinstance(value, dict):
            value = validate_values(field.fields, value)
    elif kind == "list":
        valid = isinstance(value, list)
        if isinstance(value, list) and field.item is not None:
            value = [validate_field(field.item, item) for item in value]
    if not valid:
        raise FoundationError("invalid_data", f"{field.key}: expected {kind}")
    if kind in ("integer", "decimal"):
        number = Decimal(str(value))
        if field.minimum is not None and number < decimal_value(field.minimum):
            raise FoundationError("invalid_data", f"{field.key}: below minimum")
        if field.maximum is not None and number > decimal_value(field.maximum):
            raise FoundationError("invalid_data", f"{field.key}: above maximum")
    return value


def validate_values(
    fields: tuple[DataField, ...], values: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    declared = {field.key: field for field in fields}
    if set(values) - set(declared):
        raise FoundationError("invalid_data", "Values contain undeclared fields")
    result: dict[str, JsonValue] = {}
    for key, field in declared.items():
        if key not in values:
            if field.required:
                raise FoundationError("invalid_data", f"Missing required field {key}")
        else:
            result[key] = validate_field(field, values[key])
    return result


def validate_format(definition: DataFormatState) -> None:
    def check(field: DataField, depth: int = 0) -> None:
        if depth > 16 or (field.precision is not None and field.precision > 1000):
            raise FoundationError("invalid_format", "Format exceeds the finite language limits")
        if field.minimum is not None:
            decimal_value(field.minimum)
        if field.maximum is not None:
            decimal_value(field.maximum)
        if field.minimum is not None and field.maximum is not None:
            if decimal_value(field.minimum) > decimal_value(field.maximum):
                raise FoundationError("invalid_format", "Minimum exceeds maximum")
        if (field.minimum is not None or field.maximum is not None) and field.type not in (
            "integer",
            "decimal",
        ):
            raise FoundationError("invalid_format", "Bounds require a numeric field")
        for child in field.fields:
            check(child, depth + 1)
        if field.item is not None:
            check(field.item, depth + 1)

    for field in definition.fields:
        check(field)


def field_references(
    fields: tuple[DataField, ...], values: dict[str, JsonValue]
) -> tuple[DataReference, ...]:
    found: list[DataReference] = []

    def visit(field: DataField, value: JsonValue) -> None:
        if value is None:
            return
        if field.type == "ref":
            found.append(DataReference.model_validate(value))
        elif field.type == "object" and isinstance(value, dict):
            for child in field.fields:
                if child.key in value:
                    visit(child, value[child.key])
        elif field.type == "list" and isinstance(value, list) and field.item is not None:
            for item in value:
                visit(field.item, item)

    for field in fields:
        if field.key in values:
            visit(field, values[field.key])
    return tuple(dict.fromkeys(found))


def json_schema(definition: DataFormatState) -> dict[str, Any]:
    def field_schema(field: DataField) -> dict[str, Any]:
        types = {
            "text": "string",
            "boolean": "boolean",
            "integer": "integer",
            "decimal": "string",
            "date": "string",
            "datetime": "string",
            "enum": "string",
        }
        result: dict[str, Any] = {"description": field.meaning}
        if field.type in types:
            result["type"] = types[field.type]
        if field.type in ("date", "datetime"):
            result["format"] = "date" if field.type == "date" else "date-time"
        if field.type == "decimal":
            result["x-decimal-precision"] = field.precision
        if field.type == "enum":
            result["enum"] = list(field.choices)
        if field.type == "ref":
            result.update(DataReference.model_json_schema())
        if field.type == "object":
            result.update(object_schema(field.fields))
        if field.type == "list" and field.item is not None:
            result.update(type="array", items=field_schema(field.item))
        if field.unit is not None:
            result["x-unit"] = field.unit
        if field.minimum is not None:
            result["x-minimum-decimal"] = field.minimum
        if field.maximum is not None:
            result["x-maximum-decimal"] = field.maximum
        return {"anyOf": [result, {"type": "null"}]} if field.unknown_allowed else result

    def object_schema(fields: tuple[DataField, ...]) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {field.key: field_schema(field) for field in fields},
            "required": [field.key for field in fields if field.required],
        }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **object_schema(definition.fields),
    }


__all__ = ["json_schema", "validate_format", "validate_values"]
