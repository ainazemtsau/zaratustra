# File-primary memory, Activity and bounded Sleep

Implementation contract for the approved 2026-10-29 upgrade. Passing evidence is
recorded separately; this document alone is not a qualification report.

## Authority and compatibility

Portable corpus format 1, SQLite projection schema 10, control format 3.
The corpus contains workspace identity, typed records, exact revisions, compact
receipts, required pending effects and selected original bytes. Technical indexes
are rebuilt rather than exported as semantic data. Note/Episode/Procedure/Source
are semantic names for compatible Knowledge/Run/Method/Evidence records.

A normal semantic envelope is limited to 256 KiB. Large content is addressed by
hash and divided into parts (target 1 MiB; hard maximum 8 MiB). Required historical
content is retained before overwrite, including changes not yet in Git.

A coordinated save validates versions, prepares recovery before/after images,
publishes files, writes the durable COMMITTED marker and retires the journal before
cleaning its components. No success response precedes the file commit point.
Recovery rolls back an uncommitted intention or finishes a committed one. SQL is a
projection even if its local transaction committed before a publication failure.
Uncertain external effects remain UNKNOWN and are not redispatched after restore.

File membership and content hashes make missing files an error. A cache from another
workspace/epoch is not valid because its numeric revision happens to match.
Canonical envelope edits require explicit inspection/import; they are never silently
accepted or overwritten from an old SQL cache.

## Memory and retrieval

An Activity's common contract is short: purpose, boundaries, context references,
working documents, procedures and open Work. Subject-specific document formats
belong to the Activity when useful, not to a universal mandatory folder scaffold.

Only selected useful experience becomes a durable Episode. Ordinary successful
calls stay transient. Meaningful new sources state why they are retained. A fragment
preserves exact code-point offsets and hashes for both the retained fragment and
original source; a hash of omitted content never proves it can still be read.

Migration preserves the prior durable information losslessly in an explicitly
addressable legacy contour. Current Activity/Work/Knowledge/documents remain active.
Default browse/search/Sleep omit legacy churn. `zara_browse` mode `legacy`, explicit
history and search `include_legacy` provide deliberate access. Historical references
continue to resolve under current managed access rules.

`zara_candidate` explicitly retains an unverified short question or diagnostic.
It does not log successful calls. Unpinned content is a local temporary cache;
necessary pinned grounds are portable working state. Seven days /20 MiB are upper
limits; no TTL removes open obligations or UNKNOWN effects. Large chosen originals
belong in retained Source rather than temporary diagnostics.

Typed reference fields produce graph edges. Ordinary prose and object property
names do not. Index updates follow affected objects; full rebuild remains available
for migration, repair and comparison. Every page rechecks access. Live pagination
can change membership as filter properties change; it does not promise one frozen
multi-page result.

## Procedures and Sleep

Methods hold versioned instructions/applicability. A procedure controller holds the
required machine checkpoints; a model's final prose is not workflow completion.
`zara_sleep` and `/zara-sleep` use the same controller. Its private application permit
matches the exact validated proposal, runtime profile and epoch. A generic commit
cannot skip phases. Native document application reuses the existing managed write,
version, observation and receipt path with distinct delegated authority; no human
Yes is fabricated.

One active Sleep per workspace: ten cases, three improvements, twenty logical
model generations and fifteen minutes of new admissions. Counts survive restart.
Settlement/cleanup of admitted operations may finish after the deadline, but new
meaningful work may not. The stream wrapper checks admission before the native
stream function, including the actual selected recipient. Automatic SDK warming,
compaction, retries and unrelated extensions are disabled.

Possible outcomes include applied-but-unverified, proposal, insufficient evidence,
no useful change, or a stop with a continuation. Cross-Activity correlation stays a
hypothesis until supported by observations. A later grounded observation can record
whether an improvement helped; changing a Method itself is not evidence of benefit.

## Git checkpoint and restore

One repository checkpoint executor combines ordinary working files and canonical
memory, preserving manual staging. Its trusted binding pins repository identity,
private visibility, destination and main. Git network work is outside the memory
gate. Runtime exclusion policy is precise, not an exclusion of `.local` or Activity.

Before pushing, validate exact captured tree/commit and every outgoing blob,
including unsent parents. A conflicting stage, branch, hook failure, unresolved
merge, remote divergence or too-large blob is a pending reason. No force, automatic
rebase, hook bypass or direct HEAD editing is used. A lost push reply is reconciled
against the remote rather than blindly creating another commit.

A portable corpus can reconstruct a projection without the original SQLite.
A fresh runtime on a recovered/older corpus has a fresh epoch and conservative
effect-reconciliation barriers; historical receipts do not authorize redispatch.
Missing known coordination under an existing control is not silently recreated.
Live OS lease files are never restored as proof that a former process is alive.

## Personal activation order

1. Close old Pi sessions normally; verify no live operations. Never kill them for convenience.
2. Cold-copy the entire ZT, including hidden/untracked files, outside the source; verify hashes.
3. Inventory IDs, revisions, exact document/material bytes, open obligations and UNKNOWN effects.
4. Migrate a quarantined copy without deleting old durable data; verify every retained item.
5. Rebuild from its corpus in another folder without the old SQLite and compare again.
6. Install the exact checked public commit; switch authority only after these comparisons.
7. Remove precise runtime paths from the Git index only, keeping disk files and backup.
8. Verify first private main checkpoint and ordinary Activity continuation.

Before new-format writes, rollback may restore the verified original state. After
new-format writes, do not overwrite them with an older backup: preserve and reconcile
the newer corpus first. A safe-window or Git conflict requiring owner choice stops
personal activation; it does not justify risking the owner's data.

## Retention and cleanup limits

Canonical garbage collection is conservative in this release. Selected originals
and needed history are retained. Runtime-cache cleanup is explicitly labeled as
such; a canonical material may recreate its cache on a later open. Tombstoning
removes managed body access, not every physical canonical/Git/backup copy. It must
not be described as complete physical erasure. An explicit destructive retention
policy and canonical reachability GC remain a separate future change. The initial
migration never applies such deletion to prior owner data.
