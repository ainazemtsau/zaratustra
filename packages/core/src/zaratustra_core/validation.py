"""Pure structural staging checks derived from the authoritative wire models."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ValidationError, create_model

from .shapes import Outcome, SleepProgress, SleepProgressV2
from .types import CoreError, Request, wire


def metadata_model() -> Any:
    fields: dict[str, Any] = {}
    for name in ("state", "outputs", "changes", "wait"):
        field = deepcopy(Outcome.model_fields[name])
        if name == "state":
            field.default = "completed"
        fields[name] = (field.annotation, field)
    heads = deepcopy(Request.model_fields["expected_heads"])
    fields["expected_heads"] = (heads.annotation, heads)
    return create_model("OutcomeMetadata", __config__=Outcome.model_config, **fields)


_METADATA = metadata_model()
_PROGRESS: dict[str, type[BaseModel]] = {
    "sleep-progress/v1": SleepProgress,
    "sleep-progress/v2": SleepProgressV2,
}


def shape_error(error: ValidationError, prefix: str = "") -> CoreError:
    path = ".".join(map(str, error.errors()[0]["loc"]))
    return CoreError("invalid_request", prefix + path)


def validate_outcome_metadata(metadata: dict[str, Any]) -> None:
    """Validate shape only, without admission, reference resolution or terminal effects."""
    try:
        value = _METADATA.model_validate(metadata)
    except ValidationError as error:
        raise shape_error(error) from error
    for index, change in enumerate(value.changes):
        body = change.body
        if isinstance(body, dict) and isinstance(body.get("format"), str):
            model = _PROGRESS.get(body["format"])
            if model is not None:
                try:
                    model.model_validate(body)
                except ValidationError as error:
                    raise shape_error(error, f"changes.{index}.body.") from error
    try:
        wire(metadata)
    except ValueError as error:
        raise CoreError("invalid_request", "wire") from error


def outcome_metadata_contract() -> dict[str, Any]:
    """Return fresh schemas/guidance; callers cannot mutate shared validation state."""
    return {
        "metadata_schema": _METADATA.model_json_schema(),
        "progress_schemas": {tag: model.model_json_schema() for tag, model in _PROGRESS.items()},
        "guidance": [
            "Metadata source_refs and schema_ref are record refs: id, revision, optional role.",
            "History refs use sequence, index, sha256; place them in free analysis body.sources.",
            "Change.body is the free record value; do not add a stored record wrapper.",
            "Tagged sleep-progress/v1 and v2 bodies use their exact versioned schemas.",
            "Structural acceptance does not prove references, rights, current basis or meaning; "
            "final Core admission still checks the actual terminal and transaction.",
        ],
    }
