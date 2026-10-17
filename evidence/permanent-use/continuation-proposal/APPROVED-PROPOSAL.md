# Sleep continuation: decision proposal, not implementation

Status: **owner decision required**. Source inspected: `bc95ceb412210e5bb8355e60cdff537088fdf25a`. No Core/app implementation, migration, live retry or state change is authorized by this document. UTF-8 presentation repair is separate.

Recommendation: **A — retain completed passes and create a verified successor**. It covers both unfinished old-cutoff material and later arrivals. B is a smaller prospective convenience for genuinely ready results, not an equivalent repair of completed passes.

## Observed behavior

`NativeSession.settled` clears its mapping after actual completed. `_unclaimed_sleep` excludes completed Works; the next explicit Sleep creates a different Work and `Sleep._start_progress` reads history from zero. `NativeSleep.resume` accepts only an actual ready Work/result.

Two disposable public-API reproductions are retained beside this proposal. `sleep-continuation-reproduction.json`: completed with no analysis and remaining sources creates a new Work selecting the same prefix. `sleep-fully-processed-restart-reproduction.json`: a mechanical fixture completely declares all seven cutoff sources analysed, then a new arrival is added; the next Sleep nevertheless selects those same seven sources again. Scripted fixture analysis is not semantic evidence. The real completed pass0169 also retained four selected, sixteen remaining and unenumerated material; it is not credited as useful adaptation.

## Reuse before extension

Core already creates generic child Works atomically at `commit_outcome.next_work` (`api.py:675–725`), recording parent Attempt, delivered/processed message cutoffs, reservation and optional Activity ref in `Work.continuation`. It conserves optional finite call resources and prevents another active child in that conversation. Existing tables already retain Works, results, exact data revisions and receipts; no new database/table, daemon, sidecar truth file or sync service is proposed.

That path only operates while committing the original outcome. It cannot be added retrospectively to a completed result without violating receipt replay. `backup_refs.py` also requires that original result to name its child. Current `sleep-progress/v1` binds delivery and applied receipts to one Work (`api.py:539–634`). Merely copying old progress into a different Work therefore fails existing truth guards. Refresh/resume of a completed Work is forbidden and remains forbidden.

The generic lineage's message cutoffs are not Sleep's event-source cutoff. The new progress contract must verify the latter independently from exact predecessor progress; it must never infer analysed history from a processed message cursor.

## A — verified successor lineage

Public behavior: the next explicit Sleep in an Activity discovers its unambiguous durable continuation and resumes from it. A completed pass/result stays completed and byte-identical. Ordinary work remains available between passes. No automatic model send is introduced.

Minimal proposed wire delta, subject to owner approval:

1. An additive **generic late continuation** admission using exact parent Attempt/result hash, expected parent Work revision, a child Work descriptor, and exact `basis_refs` (including the retained progress revision). Prefer an optional `continuation_from` basis on existing `open_work`, validated by a separate OpenWork shape, over adding a new operation; keep existing initial_work/next_work descriptors unchanged. Reuse the internal generic child-Work constructor and resource checks. It is a fresh command/receipt, never a modification of the old outcome. A child created at original `next_work` and a late child occupy the same single-successor slot. Existing `next_work` and old receipts retain their behavior.
2. A versioned **sleep-progress/v2** predecessor reference, admitted only when its exact predecessor progress belongs to the verified generic Work lineage. Keep v1 validation unchanged. V2 distinguishes evidence owned by this Work from inherited evidence reached through the predecessor, preserving original attribution instead of relabelling old deliveries/receipts as new ones. Contract introspection and backup-reference closure validate the new additive shape. No new SQLite table is proposed, but a durable version gate and transactional preserving upgrade are mandatory, as specified below.

Two required transitions:

- **Old cutoff unfinished**: remaining refs nonempty OR enumeration has not reached the old cutoff. Preserve that cutoff, exact cursor, complete honest remaining set and exploration position. Inherit prior analysed evidence by reference; select a whole bounded subset of the old remainder, or enumerate the next old-cutoff portion when that remainder is empty. Newly delivered/analysed refs belong to the successor. Never skip an unanalysed source to make apparent progress.
- **Old cutoff fully declared processed**: enumeration reached the old cutoff and all enumerated refs have valid retained analysis/delivery linkage, leaving no remaining refs. Capture a new cutoff and enumerate strictly after the old proved boundary. The predecessor remains the evidence for the earlier range; the new range never restarts at zero. This is structural proof of retained analysis claims, not a machine verdict on their meaning or exhaustive environmental understanding.

Preserve exploration position, unknown coverage and unresolved doubt through the exact predecessor in BOTH transitions. A fully processed history window does not prove the whole environment understood or erase unexamined questions.

Past Method/Memory/results retain their exact refs. The successor pins the then-current applicable Method under existing authority and records it separately from the predecessor's Method; no old content is rewritten. No finding, Memory edit or successful adaptation is mandatory merely to finish an honest pass.

Durability: one Core transaction verifies parent status/result/ref rights and absence of unresolved effects. Admission requires both expected parent Work revision and the selected progress revision matching its expected CURRENT head, alongside exact terminal result/Attempt hash. Revalidate that progress's structural invariants and then freeze its exact revision into the child basis; it is not a moving latest pointer afterward. A racing checkpoint/head advance produces stale_basis before child creation, unless the same already committed child is being discovered. Parent Work CAS alone is insufficient because checkpoint revisions can advance independently.

The same transaction checks the single-successor slot, creates the child/link and retains its receipt. A replay of the same command returns that receipt. A competing different command cannot create a second successor. A crash before commit creates nothing; after commit the exact child is discoverable from Core. A crash before native attachment is recovered by discovering that committed child, without another send. App progress initialization/binding is idempotent with CAS and fresh reads; a discoverable unclaimed child must remain recoverable if interrupted between those steps. No timeout declares an unknown send safe.

Resource policy: normal `None` stays unlimited. An explicit finite parent policy passes only its unspent allowance to the successor, including all retained reservations and unknown effects; a new Work cannot reset it. If finite remainder is zero, preserve parent/spend/proof and return recorded or derivable exhaustion with NO child and NO send: current positive call_limit cannot represent zero, and neither None nor a giant integer is a substitute. Reuse existing resource/receipt semantics; this does not invent receipts for rejected commands. A paused zero-budget child would be a separate unapproved shape change. The external evaluation ledger remains cumulative across all Works.

Old data: v1 records/results/receipts are never rewritten. A unique eligible completed checkpoint can be adopted by the first explicit Sleep through the new admission and a new v2 progress record. Multiple unrelated old roots, inconsistent evidence, or unresolved effects produce an explicit choice/blocker rather than an arbitrary merge, deletion or guessed processed boundary. Only an Activity with NO established eligible checkpoint/lineage may start an initial range from zero. If an explicit or established predecessor is missing, unavailable, inconsistent or ambiguous, return the exact blocker and never fall back to zero. Cancelled/unknown runs supply no automatic analysed boundary; their existence does not authorize guessing one.

### Durable compatibility boundary

Advertising a new wire capability is insufficient: the old Core must refuse this data before any mutation once v2 is enabled. Current Core0.2 `lifecycle.compatibility` rejects every `PRAGMA user_version` other than0, and `_locked_transaction` invokes that check before yielding a connection to a command. Therefore the minimal concrete marker is a supported nonzero `user_version` for the new required protocol (for example1), without a new table. Its exact value belongs to the reviewed implementation/version manifest. A new Core may explicitly support reading the old version for validation/upgrade, but must not create v2 records under marker0. Fresh new-format databases also carry the new marker.

The installation/update path must validate the exact old format and reference closure, retain the existing internal safety snapshot, and change the required-protocol marker plus its audit receipt atomically under the existing exclusion/transaction. All old record/result/receipt bytes, IDs, space identity and history survive; no semantic content migration or Activity reconstruction is involved. Failure before commit leaves the old marker/data unchanged. After marker commit, old Core0.2 is deliberately blocked, including if runtime publication is interrupted; re-entry through the verified new package must recover/finish publication idempotently without init, downgrade, deletion or repeated model effects. Runtime verification precedes this boundary. There is no promise that the old binary remains usable after the new protocol is durably enabled.

Required compatibility tests use an actual frozen old Core0.2 wheel: it must reject the upgraded database before any data/event/receipt/credential mutation, with unchanged protected fingerprints. The new package must read unchanged legacy v1 history and new v2 lineage, preserve technical integrity/update snapshots, and survive crashes before/after marker commit and runtime selection. Unsupported versions, partial/corrupt upgrade evidence, or an attempted old-runtime downgrade fail closed. This is a required schema/protocol transition even though no table layout change is necessary; it must not be presented as a mere package-version label change.

## B — honest ready with dormant attachment

When the model actually stages ready, keep that exact ready result and same Work. App can detach the finished Sleep attachment from the ordinary conversation and rediscover it on a later explicit Sleep. Existing `NativeSleep.resume` preserves its cutoff, progress and manifests; no cross-Work Core guard relaxation is needed. Discovery must distinguish terminal/finished attempts from unknown sends, detect ambiguity and recover a crash during detachment. Core records, not a new file, hold the dormant continuation.

This does not repair genuine completed+remaining. It also does not solve the next new-cutoff pass after a fully processed completed Work: without A's verified boundary/lineage, current start still reads from zero. Rewriting the model's completed state into ready is explicitly excluded. Therefore B alone is only acceptable with those remaining limitations stated; it is not the recommended complete solution.

## Acceptance controls before any readiness claim

Positive controls cover both transitions, later ordinary work between passes, fresh Pi reopen, exact prior refs/history retained, and an explicit no-finding analysis that preserves uncertainty. Negative controls reject forged/wrong-scope/missing/future predecessor refs, altered cutoff/cursor/source SHA, dropped historical evidence, false fully-processed claims, foreign delivery/receipt attribution, cycles/forks and conflicting successors. Exercise stale CAS, duplicate replay, concurrent commands, crashes before/after commit and attachment/progress binding, unresolved sends/tools, revoked authority, and finite exhaustion versus true unlimited.

Update must preserve old v1 bytes and existing Activities. Compatible new packages must pass technical integrity/backup closure on mixed v1/v2 history; unsupported capability must fail before mutating existing data. Old `next_work` receipt/default behavior and current protected CAS/fencing remain unchanged. Independent exact-package review plus actual Sleep and subsequent same-Activity ordinary work remain required. Full gate follows those live checks. No semantic keyword validator, forced useful finding, automatic analysis or owner acceptance is introduced.

END_OF_FILE: _scratch/permanent-bc95ceb/SLEEP-CONTINUATION-PROPOSAL.md
