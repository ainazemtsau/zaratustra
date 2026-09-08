# Core
Public API is __init__.py: workspace/records, mutation and authorized receipt APIs,
owner-local history, immutable models and errors. Core never imports CLI/local adapter.
workspace.py owns checked transactions/layout/metadata; migrations.py retains released
v1/v2/v3 migration bytes stay fixed; migration_v4.py adds version metadata only.
records.py owns create-once bootstrap and record models; protocol.py owns operation
and journal values; mutations.py owns the ONE post-bootstrap domain mutation path.
Initial creation is one local bootstrap into an empty record store; it grants no rights.
LocalAuthorization comes only from trusted application code after actual owner
permission. It is not parsed from payload/CLI flags. W21 admits console access as
trust boundary, without accounts or hostile same-user isolation. Already-authorized
local-chat callers need no repeated identity check. Validate exact binding, current
Work/authority, revision, duplicate, artifacts in that order before mutation/event/
receipt commit. Artifacts may be published/restored only with the exact current
work_metadata_and_artifact scope for the sole declared Artifact. artifacts.py owns
checked bytes/immutable descriptors, never an alternate domain updater. Complete
files precede DB registration/active switch. Retain/report orphans; no automatic cleanup.
projections.py renders DB-only overview bytes; mutations.py serializes rebuild after
commit and returns the committed receipt on rebuild failure. Rebuild changes no DB state.
Read verifies registered content every time; metadata history remains inspectable
after file loss. No context, Result or successor Work. Initial Event stays fixed.
Read/init never migrate or repair existing state. Keep migration bytes stable after release.
END_OF_FILE: src/zaratustra/core/AGENTS.md
