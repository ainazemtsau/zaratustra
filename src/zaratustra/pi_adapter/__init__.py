"""Local interactive bridge for upstream Pi."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from .bridge import Bridge, BridgeServer
from .manual_exchange import ManualExchange
from .runtime import PiRuntime, read_pi_runtime, system_pi_runtime
from .skills import external_workflow_skill

if TYPE_CHECKING:
    from zaratustra.foundation import BackupInfo, DeletionStatus, LocalAuthority


def prepare_space(path: Path, actor: str, *, create: bool) -> LocalAuthority:
    from .__main__ import _prepare_space

    return _prepare_space(path, actor, create=create)


def pi_main(argv: list[str]) -> int:
    from .__main__ import main

    return main(argv)


def assigned_main(argv: list[str]) -> int:
    from .assigned import main

    return main(argv)


def create_assigned_backup(
    space: Path, backup_id: UUID, authority: LocalAuthority, *, pi_version: str | None = None
) -> BackupInfo:
    from .assigned import create_assigned_backup as create_backup

    if pi_version is None:
        return create_backup(space, backup_id, authority)
    return create_backup(space, backup_id, authority, pi_version=pi_version)


def complete_assigned_deletions(space: Path, authority: LocalAuthority) -> DeletionStatus:
    from .assigned import complete_assigned_deletions as complete_deletions

    return complete_deletions(space, authority)


__all__ = [
    "Bridge",
    "BridgeServer",
    "ManualExchange",
    "external_workflow_skill",
    "PiRuntime",
    "read_pi_runtime",
    "system_pi_runtime",
    "prepare_space",
    "pi_main",
    "assigned_main",
    "create_assigned_backup",
    "complete_assigned_deletions",
]
