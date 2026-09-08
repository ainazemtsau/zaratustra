# Core
Public API is __init__.py: workspace/records, mutation and authorized receipt APIs,
owner-local history, immutable models and errors. Core never imports CLI/local adapter.
workspace.py owns checked transactions/layout/metadata; migrations.py retains released
v1/v2/v3/v4 migration bytes stay fixed; migration_v5.py adds accepted Handoff storage.
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
after file loss. handoffs.py parses bounded portable accepted_result data, grants no
authority and delegates mutations. accept_handoff preserves exact result/basis refs,
owner text and provenance, with acceptance/event/receipt in one transaction. Current
ready Work metadata scope is required. Source revision stays immutable on replay;
only explicit transport expected_revision refresh can return a prior receipt.
read_handoffs is owner-local inspection, not Work-scoped context. context.py owns
the read-only open_work compiler: exact ContextQuery/current caller, ready Work,
scope, revision, all accepted bases and verified content closure. Revalidate the
entire collection under the existing writer lock before returning exact JSON bytes.
No DML, projection rebuild or inferred budget in this read seam. Reject overflow;
manifest accounts for actual output. Schema6 adds atomic submit_result and read_result;
all writes still use apply_mutation. Completion carries the Result operation identity.
Records/journal validate the whole single-Process Work chain by explicit Work/Artifact
ids, global revisions and exact created records. Result retains all source acceptances
and complete exact historical content grants. results.py re-derives those edges;
it never writes. A next Work is separately confirmed with full content and metadata
scope; its inherited grounds are not acceptance of its new goal or arbitrary foreign
Artifact access. Done refuses renewed execution/authorization; only exact registered
Artifact repair under retained artifact rights and revocation remain administrative
writes. read_result needs current source metadata rights and returns historical
metadata, never current-byte availability. New Work opening revalidates full bytes.
Released migrations1–5 stay fixed; new explicit6 never changes default migrate4.
Initial Event stays fixed.
Read/init never migrate or repair existing state. Keep migration bytes stable after release.
END_OF_FILE: src/zaratustra/core/AGENTS.md
