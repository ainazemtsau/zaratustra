# Core
Public API is __init__.py: workspace/records, mutation and authorized receipt APIs,
owner-local history, immutable models and errors. Core never imports CLI/local adapter.
workspace.py owns checked transactions/layout/metadata; migrations.py retains released
v1/v2 bytes; migration_v3.py adds explicit schema 3 without data changes or grants.
records.py owns create-once bootstrap and record models; protocol.py owns operation
and journal values; mutations.py owns the ONE post-bootstrap domain mutation path.
Initial creation is one local bootstrap into an empty record store; it grants no rights.
LocalAuthorization comes only from trusted application code after actual owner
permission. It is not parsed from payload/CLI flags. W21 admits console access as
trust boundary, without accounts or hostile same-user isolation. Already-authorized
local-chat callers need no repeated identity check. Validate exact binding, current
Work/authority, revision, duplicate, artifacts in that order before mutation/event/
receipt commit. Only the documented narrow DB operations are admitted; no files,
context, Result or successor Work. Initial Event and released migrations stay fixed.
Read/init never migrate or repair existing state. Keep migration bytes stable after release.
END_OF_FILE: src/zaratustra/core/AGENTS.md
