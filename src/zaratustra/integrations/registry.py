"""Typed, code-installed operation boundary; no account registry or effect ledger."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError

from zaratustra.foundation import FoundationError, KnowledgeRef


class Parameters(BaseModel):
    """Internal operation arguments, never a schema imposed on external prose."""

    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True)
class IntegrationResult:
    output: dict[str, object]
    exposed: tuple[KnowledgeRef, ...] = ()


@dataclass(frozen=True)
class Operation:
    description: str
    effect: str
    parameters: type[Parameters]
    execute: Callable[[UUID, BaseModel], IntegrationResult]


class IntegrationRegistry:
    """Trusted code supplies adapters; neither prompts nor saved profiles install code."""

    def __init__(self, adapters: Mapping[str, Mapping[str, Operation]]) -> None:
        self._adapters = {name: dict(operations) for name, operations in adapters.items()}

    def _operation(self, adapter: str, operation: str) -> Operation:
        try:
            return self._adapters[adapter][operation]
        except KeyError as error:
            raise FoundationError(
                "unsupported_operation", "This adapter/operation is not installed; use catalog"
            ) from error

    def catalog(self) -> dict[str, object]:
        return {
            "contract_version": 1,
            "adapters": [
                {
                    "adapter": adapter,
                    "operations": [
                        {"operation": name, "description": op.description, "effect": op.effect}
                        for name, op in operations.items()
                    ],
                }
                for adapter, operations in self._adapters.items()
            ],
        }

    def contract(self, adapter: str, operation: str) -> dict[str, object]:
        op = self._operation(adapter, operation)
        return {
            "contract_version": 1,
            "adapter": adapter,
            "operation": operation,
            "effect": op.effect,
            "schema": op.parameters.model_json_schema(),
        }

    def execute(
        self,
        operation_id: UUID,
        adapter: str,
        operation: str,
        arguments: dict[str, Any],
        *,
        contract_version: int,
    ) -> IntegrationResult:
        if type(contract_version) is not int or contract_version != 1:
            raise FoundationError("unsupported_contract", "Read the installed contract version")
        op = self._operation(adapter, operation)
        try:
            parameters = op.parameters.model_validate(arguments)
        except ValidationError as error:
            raise FoundationError("invalid_request", str(error)) from error
        return op.execute(operation_id, parameters)
