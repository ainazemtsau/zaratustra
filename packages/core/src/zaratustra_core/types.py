"""Strict public wire types. No import-time I/O."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    contract_version: Literal["wire/v1"] = "wire/v1"
    instance_id: str
    space_id: str
    recovery_epoch: int
    command_id: str = Field(min_length=1)
    operation: str
    payload: dict[str, Any]
    expected_heads: dict[str, int] = Field(default_factory=dict)
    action_id: str | None = None
    confirmation_ref: str | None = None


def wire(value: Any) -> bytes:
    """Object order canonical; strings, Unicode and array order preserved."""

    def check(item: Any) -> None:
        if item is None or type(item) in (str, int, bool):
            return
        if isinstance(item, list):
            for child in item:
                check(child)
            return
        if isinstance(item, dict) and all(type(k) is str for k in item):
            for child in item.values():
                check(child)
            return
        raise ValueError("wire/v1 requires integers or decimal strings")

    check(value)
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(wire(value)).hexdigest()


class CoreError(Exception):
    def __init__(self, code: str, field: str = "", retry_policy: str = "never"):
        self.code = code
        self.field = field
        self.retry_policy = retry_policy
        self.diagnostic_id = hashlib.sha256(f"{code}:{field}".encode()).hexdigest()[:16]
        super().__init__(f"{code}: {field} [{self.diagnostic_id}]")

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "field": self.field,
            "retry_policy": self.retry_policy,
            "diagnostic_id": self.diagnostic_id,
        }
