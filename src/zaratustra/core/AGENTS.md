# Core
Public API is __init__.py: init_workspace, read_workspace, WorkspaceInfo, WorkspaceError.
Core cannot import zaratustra.cli. workspace.py owns path/layout and reads;
migrations.py owns explicit schema v1. Both remain inside the Core graph boundary.
Bootstrap persists workspace identity/time and migration metadata only.
No Process/Work/Artifact/Event, revisions, grants or general mutation API yet.
Existing workspace reads are read-only; never silently migrate/repair unknown state.
Keep v1 bytes stable after release; later schemas require explicit migrations.
END_OF_FILE: src/zaratustra/core/AGENTS.md
