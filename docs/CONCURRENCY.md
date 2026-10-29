> Schema-10 notice: this is the predecessor contract. Current file-primary storage, bounded Sleep and upgrade requirements are in [MEMORY-V2.md](MEMORY-V2.md). Historical qualification below is not new-format acceptance.

# Concurrent local workspace

## Current delivery

Several trusted Pi 1.4 sessions can read and save the same local workspace. Records,
Activity/Work, exact historical versions, Methods, Evidence and working documents
remain the same model. There is no server, daemon or separate memory per Activity.
Independent parallel execution uses separate Work or child Work. Whole-Work revision
and execution-claim guards remain; independently versioned steps are not introduced.

The owner amended qualification on 26 October 2026: ten processes are sufficient.
No further 100-process or heavy growth runs are authorized for this delivery. The
previous two failed larger attempts remain in concurrency-evidence; they are not
PASS evidence. Qualification uses synthetic directories under Windows Temp, never
private ZT/Health. Product model/provider calls: zero.

## Runtime and ordinary use

Qualified environment: Windows x64, Pi 1.4.0, isolated Node 24.22.1, SQLite 3.53.4.
The supported runtime line is Node 24.16+ in 24.x; startup checks actual SQLite 3.53+,
FTS5, JSON, NUL/Unicode/BLOB roundtrips and backup API before personal storage opens.
Node 22 is refused explicitly. Install/update Node once, then ordinary pi startup
continues; no per-launch environment ceremony is added. Global Node/Pi was not changed
by development. Private ZT was not upgraded or migrated by development.

Close old Pi sessions before updating the pinned project package. Schema 8 becomes 9
with a verified pre-migration backup. Control format 2 fences old writers. Domain IDs,
canonical records/history/receipts and material bytes survive. Memory stays under
.local/memory and canonical documents under activities/. Owner Git exclusions remain
unchanged. Commit/push remains an ordinary explicit agent workflow; GitHub is not a
live synchronization service. Cross-device concurrent work remains separate scope.

## Synchronization and failures

coordination.sqlite is stable outside replaceable generations. Its DELETE journal,
FULL synchronous commits and short BEGIN IMMEDIATE phases serialize complete commands.
FIFO queued commands wait asynchronously; thirty-second pre-admission timeout reports
retryable STORE_BUSY rather than permanently making a session read-only. A phase never
awaits a model, native dialog, parser or file tool. Nested Core calls reuse its revoked-
after-return capability. Current generation is checked once per phase, then rechecked
at the next phase. Full integrity checks remain at creation/migration/restore and doctor,
not repeated for every client opening an already validated schema-9 generation.

Each runtime owns a unique SQLite OS lease. Age, heartbeat and PID do not authorize
stealing. A live/unknown foreign lease keeps its reservations. Clean shutdown drains
callbacks and closes that lease last. An interrupted close remains retryable.

Native document/file operations reserve stable document identity and canonical paths.
Intent and dispatch admission commit before Pi writes; the global gate is released
while native work awaits. Settlement rechecks exact authority, revisions, epoch and
bytes, then registers and cleans up before releasing the resource. Known completed
but uncertain outcomes are quiescent UNKNOWN barriers, not running callbacks. An
unknown outcome is not permission to dispatch again. Explicit risk-bound retries can
transfer an inspected own/dead reservation while retaining the original unknown history.

Coordination and memory are separate databases, not one atomic transaction. A crash
can leave a durable intent without its coordination row; a known dead runtime lease
permits inspection/reconstruction, never native replay. Matching current bytes prove
a postcondition, not authorship. Arbitrary shell child processes are outside the
managed native-file guarantee.

Maintenance fences new changes while admitted operations settle. Restore preserves
unknown resource barriers, including independent documents without Work. Interrupted
administrator recovery proves the old OS lease dead and checks the atomic control
pointer against pre-/post-switch evidence; it never guesses a switch or clears a live
owner's fence. Missing/corrupt known coordination state is not silently replaced.

## Reading and indexes

Every logical result has a short coherent read snapshot; traces are recorded afterward.
Live keyset cursors bind query/access/epoch/index incarnation and an insertion boundary.
Unrelated writes do not reset traversal; existing records may change live filters,
new identities after the boundary are excluded, and current identities do not duplicate
because of new revisions. ACLs are rechecked for every page. Method bundles retain their
selected exact dependency versions. This is not an immutable multipage query snapshot.

Derived text/membership/access indexes update touched records and reverse-reachable
security components. Historical references, cycles, latent identifiers, technical rows
and Sleep inherited grounds retain the full classifier's semantics. Full rebuild stays
available as migration/recovery path and independent mechanical test oracle. Cost can
still grow with the genuinely affected dependency component; unbounded capacity is not
claimed.

## Verification

Focused coordination, memory/privacy, document, native SDK, administration and storage
regressions are recorded in CONCURRENCY-RESULT.md. The bounded multiprocess harness is
scripts/concurrent-scale.mjs; default groups are 2 and 10. Historical larger failures
are retained without relabeling. No full historical check/deliver or paid model loop
was run. Real owner usefulness and full R1/T31 remain separate.

END_OF_FILE: docs/CONCURRENCY.md
