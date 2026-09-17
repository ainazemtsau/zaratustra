# Portable Home — 0.22

## Data and commit

Each portable Home/workspace has `.zara-data/HEAD.json` and immutable operation
packages under `operations/YYYY/MM/<uuid>/`. Packages contain changed typed table
rows and separate exact UTF-8/JSON or binary content files. They contain no SQL to
execute. Cache schemas come only from installed factories. Full historical material
and record bytes retain their hashes; unchanged history is not copied into each write.

Writes validate through existing Core/Home operations inside a working SQLite
transaction. Complete files are flushed before atomically replacing HEAD. That is
the durable commit point. SQLite commit/cache failure afterward cannot undo the file
commit; repeat uses retained operation receipts. Source packages and content hashes
are checked before cache use. A damaged head/source raises a diagnosis, not old results.
Local OS locks serialize writers; stale lock ownership does not survive process death.

`.zara-cache/` holds only derived databases, indexes, staging/locks and local backups.
Backups are retained after migration and should be copied separately if the owner
wants an additional recovery copy. `.zara-device.json` holds optional external path
mappings and is not disposable. Internal registrations use relative paths. External
workspace identity is portable; its path may require mapping on another device.
Raw artifact files and ordinary user files remain in their existing folders and must
be synchronized with `.zara-data/`; navigation alone is not a backup.

## Migration and operations

`zara-home storage-migrate --home <path>` works before portable context setup.
The common API provides storage.status, storage.migrate, storage.verify and
index.rebuild. Migration takes real file/SQLite backups, stages and verifies the file
representation, compares reconstructed rows, then activates it. Legacy databases get
a write fence before retirement so waiting old clients cannot write lost updates.
Failures retain sources/staging and backups; retry includes unfinished retirement.
Registered artifact bytes are checked separately from database integrity.

New ordinary setup uses portable files. Existing low-level legacy APIs and old Homes
remain readable until their explicit migration. Unsupported file formats do not fall
back to a surviving old database. Historical schema migration bytes are unchanged.

## Retrieval and vocabulary

Existing payload schemas remain unchanged. Optional search metadata uses a versioned
record envelope: tag ids, document-purpose id and problem status. Metadata revisions
cannot change record payload/links or resolve a problem. Decisions retain separate
adopt/replace/revoke operations. New problems need explicit status; old missing status
stays unknown. Substantive resolution uses an episode revision and actual evidence.

record.search has named views, property/date/link/tag filters, optional FTS5 prefix
terms, history mode and stable generation-based pages. Results contain compact cards
and at most 320 snippet characters, not schemas or full histories. Different filters
combine with AND; tags_all requires all, tags_any at least one. Dates use occurred_at
when timezone-aware, otherwise recorded_at; the card states the chosen source. UTC
range start is inclusive and end exclusive. No morphology/semantic guarantee.

vocabulary.list/propose/create share Home values across hosts and processes. Creation
binds the exact proposal to vocabulary generation and actual authority. Existing
normalized labels must be reused. Semantic synonym checking belongs to the supplied
agent procedure, not a claimed code-level understanding. Existing categories migrate
without rewriting their historical records. record.facets reports used values.

## Agent and repository use

Portable context paths are relative; Pi resolves its local Python environment at
runtime. Codex receives the same instructions and operations. Both guide ordinary
language requests, structural retrieval, explicit classification changes and source
opening. Owners do not maintain indexes or issue internal commands themselves.

Derived navigation gives a Home process catalog and paginated record cards by type,
with direct relative links to exact canonical files. Its source HEAD is explicit so
a web client can detect staleness. This adds no full Markdown duplicate of records.
ChatGPT instructions read repository navigation directly; web.prepare/publish remain
optional selected discussion packages. Inbound request text remains tolerant of bad
JSON or other free-form formatting.

The product does not create/replace .gitignore or push automatically. Keep complete
portable data in whichever storage the owner chooses; exclude environments/caches as
appropriate. Different process edits generally touch separate authorities; conflicting
HEAD changes for the same scope require explicit owner-directed resolution. No custom
merge engine, background job or content-fetching service is included.

## Verification

Actual evidence and unresolved limitations are recorded separately in VERIFICATION.md.
No successful run by itself establishes owner acceptance or closes the prior legacy
catalog concurrency observation in ../stage2b/OPEN-OBSERVATIONS.md.

END_OF_FILE: docs/portable-storage/IMPLEMENTATION.md
