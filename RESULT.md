# Core v0.1 Stage 4 plan and scenario 9 check

## outcome

The owner accepted Stage 3 at `fa4c1773b0b4a8b75a03702be1e524cf8d5ea7a9`.
`docs/core-v0.1/STAGE4-PLAN.md` defines the first ordinary-Pi-to-independent-Core
user path and its implementation boundary. One new development-only Windows run
of DBOS scenario 9 was positive. No production Pi/DBOS integration or real model
call was started.

## evidence

The source specification SHA-256 matches
`1DDCBF9DBFD58426781F61A67A170D3CE85FCD2BA27B17549773ED3356F9428D`.
The single scenario 9 run used pinned Python 3.13.7, SQLite 3.53.3, DBOS 3.0.0
and the preserved synthetic executor migration 114. Its ignored output is
`_scratch/dbos-scenario9-windows-20260923-a`; the tracked report is
`docs/core-v0.1/STAGE4-DBOS-SCENARIO9-EVIDENCE.json` with SHA-256
`3404D652208A9AC7C2FC255F012D70BF435A290302E7B775DCA7766EE5DE6315`.
The payload was present before deletion. DBOS child exit/delete succeeded;
exclusive Windows opens succeeded before and after sanitation; both databases
reported integrity `ok` and zero freelist; managed payload rows were zero and
two closed-file scans found no sentinel. No targeted repeat or other scenario run
was made. The full `uv run --locked python -m tools.check --deliver` passed:
170 formatted files, clean Ruff, strict mypy on 146 source files, 20 import
contracts, 479 tests, source/wheel build and report structure. The report's
probe hash identifies the executed pre-formatting bytes; only formatting and
import order changed in the final stand file afterward.

## assumptions

The previous `database is locked` is consistent with stand code that committed
SQLite transactions without explicitly closing connections, followed by an
exclusive journal-mode switch. The old reports did not capture the precise
blocking handle or SQL stage, so that historical attribution is not claimed as
proven. The repaired stand closes connections explicitly and reports the stage
of any future SQLite lock. Stage 4's first user scenario is an interactive Pi
path; standalone durable RPC execution is a separate DBOS-dependent boundary.

## cuts

The check covers a single synthetic Windows fixture and managed live SQLite/log
files. It does not prove production runner integration, crash during sanitation,
unmanaged copies, SSD-level erasure or a real provider. No old `.zara`, personal
data, model account, provider call, custom dispatcher or `C:\projects\zaratustra`
change was used. The full accepted Core composition remains in scope beyond the
first scenario.

## cost

One new scenario 9 run, no repeat, no external service cost. Changes are a
development-only stand repair, its focused test, a tracked machine report,
Stage 4 plan and this report.

## manual-acceptance

The owner accepted Stage 3 and authorized this planning/check/commit pass.
The positive technical check does not constitute owner acceptance of a future
production Stage 4 implementation or selection of a real provider/resource.

## next

solmax

# Historical Stage 3 result

## outcome

Stage 3 is implemented on
`codex/core-v0.1` from the owner-accepted Stage 2 commit
`62a173c7d9a875e6709bf2e0dbe0d8d7e7fa31df`. It adds a minimal,
model-free Activity/Work contract in `zaratustra.foundation`. One Work can be
accepted explicitly without completing its continuing Activity. Subject
deletion follows the owner's explicit Stage 2 replay decision.

## evidence

The source specification hash is
`1DDCBF9DBFD58426781F61A67A170D3CE85FCD2BA27B17549773ED3356F9428D`.
`docs/core-v0.1/STAGE3-PLAN.md` records the plan and
`docs/core-v0.1/STAGE3-IMPLEMENTATION.md` records the actual boundary.

The synthetic `tools.probe_stage3` run in
`_scratch/stage3-activity-work-probe-final` created only fictional data. A new
process read Activity `ongoing`, Work `succeeded` at revision 3, exact input
and output Artifact references, the acceptance basis, its source, audit and receipt.
Both Artifact presence and output linking left the Work `proposed` until the
separate acceptance operation.

Six focused tests pass. They cover exact history, incomplete and mismatched
outputs, stale revisions, distinct read/write/accept rights, pre-existing
Stage 2 Grants, backup contamination, quarantined restore, deletion,
`history_unavailable` on old replay, `not_found` on old receipt reads,
exact deletion replay, retained audit, unaffected receipts, current rights
and unavailable result references. The full `uv run --locked python -m
tools.check --deliver` passed after the deletion-contract changes: 170 files
were format-clean, Ruff was clean, strict mypy passed across 146 source
files, all 20 import contracts held, 479 tests passed, source and wheel
artifacts built, and report structure passed.

## assumptions

Trusted local authority is established outside request content, as in Stage 2.
The Work acceptance basis is the authorized actor's statement. The program
checks exact references, media type, revisions, rights and declared slots; it
does not infer semantic success from a file. Deleting an Activity/Work removes
prior revision-forming receipts and content-derived fingerprints, keeps
minimal operation identity and permitted audit, and retains the deletion
operation's own content-free receipt.

## cuts

No Pi, DBOS, scheduler, dispatcher, automatic execution, Attempt, Method
definition, memory, Sleep, old `.zara` migration or real personal Activity was
introduced. Stage 3 Work states are `proposed` and `succeeded` only.

## cost

One additive strict SQLite schema upgrade, Activity/Work records and content,
public read/mutation contracts, six focused tests, one synthetic development
probe and documentation. Probe output remains in ignored local scratch.
No external service or model cost was incurred.

## manual-acceptance

The owner accepted Stage 2, authorized this Stage 3 and explicitly chose
Stage 2 deletion/replay semantics for Activity/Work. Engineering checks do
not establish owner acceptance of the completed Stage 3 implementation.

## next

solmax

## recommendation

The next separately authorized boundary is a real first-use adapter: select
an owner-approved new space, establish actual trusted-local identity and
confirmation, then expose creation, reading and explicit acceptance of these
records in the chosen developer workflow. Work execution, Attempts and any
Pi/DBOS runner integration require their own technical decision and are not
part of Stage 3.

# Historical Stage 2 result

## stage2-outcome

The owner-authorized Stage 2 implementation is ready for manual acceptance on
`codex/core-v0.1`, based on exact commit
`7ec6033d234b0e2e870f53796a9dad0711d3b468`. It implements an independent
`zaratustra.foundation` package and stops at the requested subject foundation. It
does not read, migrate or write the old `.zara` workspace and does not modify the
separate `C:\projects\zaratustra` checkout.

The foundation provides a new empty space identity and schema; exact immutable
Artifact revisions and provenance; versioned Decision and Grant records; current
Decision/Grant admission; one atomic operation/audit/receipt path; exact replay,
conflict and stale-revision behavior; separately authorized inspection and receipt
reads; verified backup; quarantined restore with execution-epoch rotation; fresh
recovery; terminal logical deletion; and physical cleanup of managed live and backup
payloads. No successor Activity/Work execution layer was admitted.

Implementation commits are `9df390a` (foundation), `f5159fb` (terminal deletion and
backup/delete race closure), `8a62bdd` (crash-consistent backup publication), and
`e3fd379` (exact-batch concurrent deletion cleanup).

## stage2-evidence

The implementation is grounded in specification file
`Zaratustra_Core_Specification_v0.1.md`, SHA-256
`1DDCBF9DBFD58426781F61A67A170D3CE85FCD2BA27B17549773ED3356F9428D`.
`docs/core-v0.1/STAGE2-PLAN.md` records the admitted plan and
`docs/core-v0.1/STAGE2-IMPLEMENTATION.md` records the actual contracts, operations,
storage and reproduction boundary.

The runtime gate accepts Python `3.13.7`, exact SQLite `3.53.3` and FTS5. The
development run used the official Stage 1 archive identity
`3a494861ce24d1f330efbc6c3fb58ce4972f2cf8df4e43122246ed987109dc8a`
(SHA3-256) and extracted DLL identity
`79FD9EC89DBA3F8BD64529A2CA8E9DDE6AE6EDC486C55A1D3F1CE77975A8375C`
(SHA-256). The DLL is admitted per process through `ZARATUSTRA_SQLITE_DLL`; it is
not vendored, downloaded by product code or installed globally.

The model-free synthetic probe at `_scratch/stage2-foundation-probe-b` passed on
SQLite `3.53.3`. It demonstrated exact replay, exact historical/current bytes,
receipt recovery, a verified backup, quarantine-only restore, epoch rotation from 1
to 2, fresh recovery and exact restored bytes. It made no model, provider, network or
old-workspace call.

Twenty-three focused foundation tests pass. They cover new/reopened spaces, unsupported
runtime/schema refusal, exact binary/text revisions, provenance, replay/conflict,
stale writes, current Decision/Grant behavior, atomic rollback, response recovery,
concurrency, tamper refusal, quarantine/recovery, terminal deletion, backup/delete
interleaving and both backup publication crash windows. In particular, a renamed
package remains non-restorable before inventory commit and becomes verifiably
complete immediately after commit. The corrective deletion tests reproduce the
confirmed cleanup/finalization race, require concurrent work to remain pending for a
second run, and prove retry after interruptions on both sides of status finalization.

The final full `uv run --locked python -m tools.check --deliver` run passed: 168
files were format-clean, Ruff was clean, strict mypy passed across 144 source files,
all 20 import contracts were kept, all 473 tests passed, source and wheel artifacts
built, and delivery-report structure passed. Wheel inspection confirms the
foundation package is installed while development tools remain excluded.

The required bounded setup evaluator found no setup blocker. Independent adversarial
review first found two Critical defects (deleted-record resurrection and a
backup/delete publication race) and then one Important inventory/publication crash
window. Commits `f5159fb` and `8a62bdd` fixed them with deterministic regression
tests. Final bounded re-review found no Critical or Important issue and returned
ready. This review is engineering evidence, not owner acceptance or a Direction G5
artifact.

On September 23 the owner supplied a deterministic reproducer for a later-confirmed
race in `complete_deletions`: a broad final status update could mark a concurrently
created deletion job and contaminated backup complete/purged without removing that
backup. The reproducer passed on `09122dd` with the defect present. Commit `e3fd379`
replaces broad finalization with exact captured ids, rereads actual remaining work,
and keeps concurrent work retryable. The original defect assertions no longer hold;
the second cleanup now removes the concurrently contaminated package.

## stage2-assumptions

Trusted-local authority is established by an adapter outside model/request content,
then bound to the resolved space path, space id and execution epoch. This stage
implements and tests that seam but does not choose the future UI, OS identity or
interactive confirmation adapter.

SQLite `3.53.3` remains an exact build requirement for WAL-backed foundation spaces.
The ordinary managed Python runtime's SQLite `3.50.4` is intentionally refused; a
deployment must supply the already verified build or another owner-approved exact
distribution mechanism without weakening runtime admission.

The deletion claim covers files managed by this stage: the live Core database and
its WAL/SHM plus registered managed backup packages. SSD remapping, OS snapshots,
manually copied packages and external systems are outside the claim. Audit keeps
permitted identifiers and outcome references, but managed payload, payload digest,
provenance and replayable payload-derived receipt intent are removed.

## stage2-cuts

There is no Activity/Work runtime, Attempt, scheduler, dispatcher, outbox, memory,
Sleep, Pi integration, DBOS dependency, model router, CLI workflow, installer,
updater, migration from old `.zara`, remote publication, CI/CD, GitHub Action or push
notification. No real personal data, paid service or new external right was used.

DBOS remains an open technical question rather than a selected dependency. Its Stage
1 Windows closed-handle sanitation evidence is still inconclusive; this stage neither
silently narrows deletion semantics nor introduces a custom dispatcher.

## stage2-cost

The installed change is one independent Python package, one strict SQLite schema and
its tests/docs/probe. New workspace state exists only under a user-selected empty
directory. Test/probe outputs and the verified SQLite runtime remain in ignored local
scratch space. No external service cost was incurred.

## stage2-manual-acceptance

The owner explicitly authorized Stage 2 planning, implementation, local commits and
the foundation-only boundary. Automated checks and review establish the engineering
evidence above; they do not declare owner acceptance. The owner should decide whether
this Stage 2 foundation is accepted before authorizing any successor stage.

## stage2-recommendation

Keep `zaratustra.foundation` as the sole subject-state authority and preserve its
public module boundary. For a successor, first obtain a separate owner CALL that
defines the smallest Activity/Work contract consuming this foundation. Do not bind
that work to DBOS until the open Windows deletion/handle gate is resolved, and do not
add a replacement dispatcher merely to bypass that gate.

## stage2-next

solmax

END_OF_FILE: RESULT.md
