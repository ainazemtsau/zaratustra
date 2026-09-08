# Core
Public API is __init__.py: workspace init/read/migrate, initial-record creation/read,
their immutable boundary models and WorkspaceError. Core never imports CLI.
workspace.py owns checked transactions/layout/metadata; migrations.py retains released
v1 bytes; migration_v2.py adds explicit schema 2. records.py owns the sole domain write
entry create_initial_records and coherent snapshot validation within this Core boundary.
Initial creation is one local bootstrap into an empty record store; it grants no rights.
Work is draft; Artifact has no active file; updates/replay/receipts need Work 3 admission.
Read/init never migrate or repair existing state. Keep migration bytes stable after release.
END_OF_FILE: src/zaratustra/core/AGENTS.md
