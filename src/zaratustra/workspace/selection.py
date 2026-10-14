"""Project choice uses ordinary versioned Core resources, never another Work store."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4, uuid5

from zaratustra.foundation import (
    CreateResourceRequest,
    ExecutionSnapshot,
    FoundationError,
    LocalAuthority,
    ResourceRevision,
    ResourceState,
    ReviseResourceRequest,
    apply_operation,
    read_execution,
)

from .config import LaunchConfig


def _single_active_resource(snapshot: ExecutionSnapshot) -> ResourceRevision | None:
    resources = tuple(item for item in snapshot.resources if item.state.status == "active")
    if len(resources) > 1:
        addresses = ", ".join(f"{item.resource_id}@{item.revision}" for item in resources)
        raise FoundationError(
            "resource_unavailable",
            f"Work {snapshot.work.work_id} has multiple active resources: {addresses}",
        )
    return resources[0] if resources else None


def _check_selected_resource(
    config: LaunchConfig,
    authority: LocalAuthority,
    work_id: UUID,
    resource_id: UUID,
    root: Path,
) -> Path:
    """An operation receipt proves its historical effect, not current project selection."""
    snapshot = read_execution(config.space, work_id, authority)
    active = _single_active_resource(snapshot)
    selected = next((item for item in snapshot.resources if item.resource_id == resource_id), None)
    if selected is None:
        raise FoundationError(
            "resource_unavailable", f"Selected resource {resource_id} is absent for Work {work_id}"
        )
    address = f"{selected.resource_id}@{selected.revision}"
    if selected.state.status != "active":
        raise FoundationError("resource_unavailable", f"Selected resource {address} is revoked")
    if active is None or active.resource_id != resource_id or selected.state.root.resolve() != root:
        raise FoundationError(
            "resource_unavailable",
            f"Selected resource {address} does not match project root {root}",
        )
    if not root.is_dir():
        raise FoundationError(
            "resource_unavailable", f"Selected resource {address} has unavailable root {root}"
        )
    return root


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
    resource = _single_active_resource(snapshot)
    if resource is not None and resource.state.root.resolve() == root:
        return root
    if any(item.status == "active" for item in snapshot.attempts):
        raise FoundationError(
            "active_attempt", "Finish or stop this Attempt before changing project"
        )
    if snapshot.work.state.status != "proposed":
        raise FoundationError("work_closed", "A closed Work keeps its historical project")
    if resource is not None:
        prior = resource
        resource_id = prior.resource_id
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
    return _check_selected_resource(config, authority, work_id, resource_id, root)
