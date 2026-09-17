# Approved scope — portable storage and structured retrieval

Owner approved implementation on September 17, 2026 after discussing these choices.
This is the current implementation scope, not permission to start another stage.

1. Files are the sole durable authority. SQLite remains a disposable working cache
   and structured/keyword index. Clone and ordinary pull need no DB transfer, import,
   daemon or Git hook. Local commands validate source files before serving cached data.
2. Preserve all Home registrations, groups, relations, shared records, process identities,
   historical records/events/receipts, raw materials, journal and document versions,
   decisions, skills/configurations and web requests/attachments. Exact old references
   keep their meaning. Reuse installed type schemas and operations.
3. Canonical writes go through shared product tools. Complete immutable operation
   packages are grouped by year/month; one confirmed pointer determines current state.
   Broken source files or merge conflicts are reported, never silently ignored.
   Direct external edits do not automatically become valid document revisions.
4. Structured search uses existing types/states/categories/links/dates, plus optional
   tags, document purposes and explicit problem status. Current revisions by default,
   deliberate historical search, compact cards and explicit source opening, bounded
   pages tied to a generation. Legacy unknown problem status is not resolved.
5. Home-wide vocabulary: reuse existing meanings first. Propose new label, definition,
   relevant alternatives and reason; create only on actual owner authority. No silent
   new strings through a record save. Code checks normalized exact duplicates and
   proposal freshness; agents judge semantic equivalence. New executable record types
   still require installed schema/code. No taxonomy platform or semantic search.
6. The owner chooses storage service and synchronization. Here: save locally; ordinary
   Git synchronization on request. No automatic pushes or imposed data-exclusion rules.
   Machine-specific external-workspace mappings remain separate from portable identities.
7. Full backed-up, checked and recoverable migration. Do not switch before staged bytes
   can rebuild equivalent data. Retire old DB writers, retain real backups. Update the
   general public product, then the authorized private installation with all user data.
8. Supply portable Pi/Codex connections, compact repository navigation for ChatGPT and
   the existing tolerant web-request path. No mandatory packet publication for reading
   owner-synchronized process data. Do not invent personal records or owner decisions.

Verification: preserve historical bytes/ids; delete/rebuild caches; interrupt saves and
migration; inspect corruption/conflicts; ordinary Git exchange between separate process
edits; precise filters and bounded results; decisions unchanged by metadata corrections;
vocabulary reuse/approval/staleness; installed Pi; clean clone of the private installation.
Native delivery gate remains required. Show results and limitations, then stop.

Excluded: semantic/vector/QMD search, automatic summaries, scheduled work, new model
routing, a custom Git synchronization platform or automatic merging of competing
semantic changes to the same process. Storage provider choice remains the owner's.

END_OF_FILE: docs/portable-storage/PLAN.md
