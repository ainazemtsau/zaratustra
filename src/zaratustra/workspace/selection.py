"""Project choice uses ordinary versioned Core resources, never another Work store."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4, uuid5

from zaratustra.foundation import (
    CreateResourceRequest,
    FoundationError,
    LocalAuthority,
    ResourceState,
    ReviseResourceRequest,
    apply_operation,
    read_execution,
)

from .config import LaunchConfig


def select_work_project(
    config: LaunchConfig,
    authority: LocalAuthority,
    work_id: UUID,
    name: str,
    *,
    operation_id: UUID | None = None,
) -> Path:
    root = config.project_root(name)
    if not root.is_dir():
        raise FoundationError("resource_unavailable", "Registered project is unavailable")
    snapshot = read_execution(config.space, work_id, authority)
    resources = [item for item in snapshot.resources if item.state.status == "active"]
    if len(resources) > 1:
        raise FoundationError("resource_unavailable", "Work has multiple active resources")
    if resources and resources[0].state.root.resolve() == root:
        return root
    if any(item.status == "active" for item in snapshot.attempts):
        raise FoundationError(
            "active_attempt", "Finish or stop this Attempt before changing project"
        )
    if snapshot.work.state.status != "proposed":
        raise FoundationError("work_closed", "A closed Work keeps its historical project")
    if resources:
        prior = resources[0]
        request = ReviseResourceRequest(
            operation_id=operation_id or uuid4(),
            space_id=authority.space_id,
            actor=authority.actor,
            resource_id=prior.resource_id,
            work_id=work_id,
            expected_revision=prior.revision,
            state=prior.state.model_copy(update={"root": root, "label": name}),
        )
        apply_operation(config.space, request, authority)
    else:
        resource_id = uuid5(work_id, f"project:{root.as_posix()}")
        create = CreateResourceRequest(
            operation_id=operation_id or uuid5(resource_id, "create"),
            space_id=authority.space_id,
            actor=authority.actor,
            resource_id=resource_id,
            work_id=work_id,
            state=ResourceState(label=name, root=root, limit_units=config.limit_units),
        )
        apply_operation(config.space, create, authority)
    return root
