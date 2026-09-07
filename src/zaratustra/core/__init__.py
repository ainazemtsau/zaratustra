"""Public Core surface for the admitted workspace foundation."""

from .workspace import WorkspaceError, WorkspaceInfo, init_workspace, read_workspace

__all__ = ["WorkspaceError", "WorkspaceInfo", "init_workspace", "read_workspace"]
