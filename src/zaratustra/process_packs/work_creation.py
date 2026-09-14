"""Resolve an exact installed Pack around explicit ordinary Work admission."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from zaratustra.core import (
    LocalAuthorization,
    NextWork,
    PackReference,
    ProcessMutationReceipt,
    WorkCreationRequest,
)
from zaratustra.core import create_work as apply_work_creation

from .lifecycle import PackRegistry


def work_creation_request(
    registry: PackRegistry,
    reference: PackReference,
    *,
    operation_id: UUID,
    workspace_id: UUID,
    process_id: UUID,
    expected_revision: int,
    provenance: str,
    work: NextWork,
) -> WorkCreationRequest:
    """Resolve the exact installed Pack and build a complete explicit request."""
    registered = registry.resolve(reference)
    return WorkCreationRequest(
        operation_id=operation_id,
        workspace_id=workspace_id,
        process_id=process_id,
        expected_revision=expected_revision,
        provenance=provenance,
        pack_binding=registered.reference,
        work=work,
    )


def create_later_work(
    path: Path,
    request: WorkCreationRequest,
    caller: LocalAuthorization | None,
    registry: PackRegistry,
) -> ProcessMutationReceipt:
    """Re-resolve compatibility immediately before delegating the effect to Core."""
    request = WorkCreationRequest.model_validate(request.model_dump())
    registry.resolve(request.pack_binding)
    return apply_work_creation(path, request, caller)
