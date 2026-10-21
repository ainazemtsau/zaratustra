# E3 backup, restored lineage and retained content

Accepted E2 base:094c0df4ef893a0668ee87dcff92e5abbad3514d. This design is executor
work under the accepted E3 gate, not independent review, owner usefulness or full R1.
No new dependency/license or model/workflow/installer runtime is introduced.

| Mechanism               | Missing guarantee, reuse and authority                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Consistent bundle       | node:sqlite backup under a short administrative admission gate, no SQL transaction across await. Broad capture pin prevents GC, then exact blobs from the completed snapshot are pinned/copied. Manifest and versioned JSON derive only from that snapshot. Raw immutable originals/derivatives are copied independently and verified by length/hash; no source_locator copies or hardlink backup. Missing/corrupt bytes refuse completeness.                                                                                                                                                                      |
| Fixed full policy       | Entire SQLite/JSON bundles can expose hidden data. Full backup/export/list/verify require preconfigured restricted:read; restore and technical cleanup require read+write, before inspecting paths/counts. Default scopes remain[]. This is conservative administration, no new auth server/per-read consent.                                                                                                                                                                                                                                                                                                      |
| Stable control          | active.json and writer.lock remain in the trusted home. Existing data stays generation dot through filled schema5-to6 migration; restore creates generations/UUID. Authoritative epoch/location and lease are checked at Core admission and storage access after async waits. Cached workspace/meta agreement alone cannot authorize an old callback. Old generations remain separate retained copies.                                                                                                                                                                                                             |
| Exact restore           | Real hashes/lengths, SQLite schema/integrity/FKs, domain refs/versions/materials and rebuilt search checked in new quarantine. Exact prepared quarantine bytes/control fingerprint/backup identity/destination/coverage/loss are bound to the E2 native preview. Only atomic control-pointer publication activates it. Current state is retained; faults leave verified old active or verified new with barriers. No writable partial/empty replacement.                                                                                                                                                           |
| Unavailable-DB approval | The SAME Approvals binding/presentation/expiry/one-time logic uses a narrow read/write preview store: existing intents for Core, bounded control JSON for restore administration. It does not open/create a substitute memory DB or require old receipts/transcript. Native dialog authority remains E2 trusted TUI/registered synthetic controller only.                                                                                                                                                                                                                                                          |
| Restored effects        | New epoch/barrier is recorded before switch, outside restored snapshot authority. Every restored Work and step is blocked at managed claim/dispatch until named inspection and fresh bound reconciliation, even if backup predates all intents. Actual matching output means current state, author unknown. Risky repeat remains an explicit new decision; read-only recovery and demonstrably independent new work are allowed. No arbitrary command exactly-once or raw manual rollback detection.                                                                                                               |
| Archive/tombstone       | Archive keeps discoverable compact cards and explicit body reads, excluded from ordinary snapshots. Tombstone has its own minimal data schema and explicit CONTENT_NOT_RETAINED history. All selected retained revisions and addressed technical payload copies are removed from managed reads/FTS/JSON; stable IDs/type/hash/receipt metadata remain. External artifacts/transcripts/backups/logs/prior generations/shared retained blobs are separate coverage, no forensic-erasure claim.                                                                                                                       |
| Retention/cleanup       | Exact native target/version/dependency previews; conservative reverse refs, open Work, unresolved effects and explicit library pins refuse deletion. Signal reviews do not resolve Signals. No frequency-based semantic forgetting. Pending import/source pins span pre-commit material files; 30-minute handle/staging expiry is explicit. GC checks actual refs/history/pins, hash/length/dev/ino and resolved containment before each single-file unlink. No recursive removal/daemon/system-rights changes. Held live backup pins have separately approved release only after independent bundle verification. |

Schema6 adds small pin/barrier/administrative-event tables and old-writer admission;
filled migration uses existing verified SQLite migration backup/transaction/manifest repair.
Existing canonical/support/history/receipt/material rows are preserved during upgrade.
Restored claims/approvals are history, not revived permission. Every supported import-as-
active path is the quarantine restore protocol; edited JSON synchronization is unsupported.

Bounds: at most1000 managed blobs and1GiB per bundle; each component <=512MiB; exact
previews <=256KB; at most10 storage targets; cleanup <=200 files/128MiB per decision;
staging/source transient lifetime30min; current-world inspection freshness5min. Exceeding
limits is an explicit refusal/incomplete outcome, not silent completeness. Bundle copies
are independent; holding their duplicate live pin forever is optional, not required.

Windows11x64/Node22.19.0/npm11.6.2/Pi1.3.0, one trusted writer/no outside file writers,
no unconsented router. No OS isolation/CAS/author attribution/hardware power-loss claim.
M fault injection is not physical power-off or NTFS ACL qualification. Pi alone selects
provider/auth; existing transcript is not purged by a managed denial. Known braces dev
advisory is separate from package runtime audit and Pi-host security.

Full retained-version body deletion also requires fixed full-read/write administrative
setup before dependency analysis: the complete reverse graph/technical-copy coverage
cannot be exposed or modified by a lower-scope observer. Archive/retain remain per-record.

Stable lease remains owned across SQLite connection close and pointer publication;
no new fingerprint baseline can absorb an intervening writer. Restore refuses while
native effects, imports or dialogs are in flight. One recipient authorization state
covers healthy Core and unavailable-DB administration and survives internal reopen.
Finite exact historical grounds are traversed from open obligations/library/future
checks; releasing an obligation does not pin all history forever. Tombstones preserve
effective inherited restriction. Redacted operations retain bounded metadata cards.
Backup discovery has scope/generation-bound continuation; truncated recovery hints
point to ordinary Work reads exposing every per-step barrier.

Candidate01a111fd independent access finding: redacted denied-read traces carried
affected_ids arrays which the JavaScript technical walker missed. The narrow correction
recognizes string IDs at every depth, matching existing JSON-tree classification;
nested protected arrays are filtered while unrelated low-visible traces remain.
Own RED/source snapshot and GREEN are retained; no blanket diagnostics suppression.
