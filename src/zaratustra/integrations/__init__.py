"""Public integration boundary above Core, independent of agent and CLI surfaces."""

from .adapters import installed_integrations
from .manual import ManualExchange
from .registry import IntegrationRegistry, IntegrationResult, Operation, Parameters

__all__ = [
    "IntegrationRegistry",
    "IntegrationResult",
    "ManualExchange",
    "Operation",
    "Parameters",
    "installed_integrations",
]
